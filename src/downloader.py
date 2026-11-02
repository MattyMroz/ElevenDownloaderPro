"""Record ElevenReader audio from a real Chrome session to an MP3 file.

Launches the installed Google Chrome with its own profile and attaches to it over CDP, so Google sign-in works.
Starts in passive mode (not recording, normal speed). Keys in the terminal window: SPACE toggles recording with
playback speed-up, C clears the output file, Ctrl+C quits. Every audio chunk is appended to disk as it arrives,
so stopping never loses recorded data.

Usage:
    uv run src/downloader.py [FILE.mp3] [--speed 64] [--url https://elevenreader.io/] [--chrome PATH]

Without FILE the recording goes to the first free workspace/output/recording_N.mp3. An existing FILE is appended to.
"""

import argparse
import base64
import hashlib
import json
import msvcrt
import os
import queue
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Final, TextIO

from playwright.sync_api import Browser, BrowserContext, Error, Page, Playwright, WebSocket, sync_playwright

from timestamps import build_subtitles, mp3_cut_ms, mp3_duration_ms

# ── Constants ────────────────────────────────────────────────────────────────

ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
"""Project root that anchors the default paths."""

PROFILE_DIR: Final[Path] = ROOT_DIR / ".chrome-profile"
"""Chrome user data directory that keeps the ElevenReader sign-in."""

OUTPUT_DIR: Final[Path] = ROOT_DIR / "workspace" / "output"
"""Default directory for recordings."""

CDP_PORT: Final[int] = 9222
"""Chrome remote debugging port."""

CHROME_PATHS: Final[tuple[Path, ...]] = tuple(
    Path(os.environ.get(var, default), r"Google\Chrome\Application\chrome.exe")
    for var, default in (
        ("PROGRAMFILES", r"C:\Program Files"),
        ("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        ("LOCALAPPDATA", ""),
    )
)
"""Standard Chrome install locations on Windows."""

CONNECT_ATTEMPTS: Final[int] = 30
"""How many times to try attaching to the freshly started Chrome."""

CONNECT_RETRY_SECONDS: Final[float] = 0.5
"""Pause between attach attempts."""

POLL_MS: Final[int] = 300
"""Main loop tick; Playwright events are dispatched while it waits."""

STATUS_INTERVAL_SECONDS: Final[float] = 10.0
"""How often to report the recorded size."""

GAP_REPORT_SECONDS: Final[float] = 5.0
"""Wait between audio chunks long enough to be worth reporting."""

MIN_DEDUP_BYTES: Final[int] = 8 * 1024
"""Smaller chunks are short pauses that may legitimately repeat byte for byte, so they are never skipped."""

TAIL_CHARS: Final[int] = 20_000
"""Recent text kept to recognise what a reconnected stream sends again."""

MIN_PROBE_CHARS: Final[int] = 10
"""Leading chars of the first chunk after a reconnect searched for in the recent text; shorter chunks are kept."""

MB: Final[int] = 1024 * 1024
"""Bytes in a megabyte."""

KEY_TOGGLE: Final[str] = " "
"""Starts or pauses recording."""

KEY_CLEAR: Final[str] = "c"
"""Clears the output file."""

KEY_CTRL_C: Final[str] = "\x03"
"""Ctrl+C as returned by msvcrt.getwch, which swallows the console interrupt."""

BLANK_URLS: Final[tuple[str, ...]] = ("about:blank", "chrome://newtab/", "chrome://new-tab-page/")
"""Empty tabs left by starting Chrome; closed so each run works in a single tab."""

HEADLESS_WINDOW: Final[str] = "--window-size=1600,1000"
"""Desktop-sized viewport for headless runs; the default 800x600 switches the site to its narrow layout."""

SPEED_JS: Final[str] = """
(() => {
    if (window.__edpState) return;
    window.__edpSpeed = __INITIAL_SPEED__;
    const playing = new Set();
    const contexts = new WeakSet();
    let contextCount = 0;
    window.__edpSetSpeed = (speed) => {
        window.__edpSpeed = speed;
        for (const src of playing) {
            try { src.playbackRate.value = speed; } catch (e) {}
        }
    };
    window.__edpState = () => ({
        target: window.__edpSpeed,
        rates: [...playing].map((src) => src.playbackRate.value),
        contexts: contextCount,
    });
    for (const Ctx of [window.AudioContext, window.webkitAudioContext]) {
        if (!Ctx) continue;
        const originalCreate = Ctx.prototype.createBufferSource;
        Ctx.prototype.createBufferSource = function () {
            if (!contexts.has(this)) {
                contexts.add(this);
                contextCount += 1;
            }
            const src = originalCreate.call(this);
            const origStart = src.start;
            src.start = function () {
                if (window.__edpSpeed !== 1) {
                    try { src.playbackRate.value = window.__edpSpeed; } catch (e) {}
                }
                playing.add(src);
                src.addEventListener("ended", () => playing.delete(src));
                return origStart.apply(this, arguments);
            };
            return src;
        };
    }
})();
"""
"""Init script that plays audio buffers at window.__edpSpeed; window.__edpSetSpeed also retunes buffers already playing."""

SPEED_STATE_JS: Final[str] = "() => window.__edpState ? window.__edpState() : null"
"""Read the speed script state of a frame: target speed, rates of playing buffers, audio contexts; null when absent."""

SPEED_CHECK_SECONDS: Final[float] = 3.0
"""How often a recording page is checked for audio playing slower or faster than the target speed."""

SPEED_TOLERANCE: Final[float] = 0.01
"""Playback rate difference from the target that still counts as the target speed."""

V4_READING_SPEED: Final[float] = 1.0
"""ElevenReader reading speed for the Eleven v4 voice model; at about 3x the server reads with the older v2 instead."""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Recorder:
    """Append audio chunks, their text and their character timings from ElevenReader WebSocket frames."""

    def __init__(self, out: BinaryIO, transcript: TextIO, alignment: TextIO, offset_ms: float = 0.0) -> None:
        self.out: BinaryIO = out
        self.transcript: TextIO = transcript
        self.alignment: TextIO = alignment
        self.offset_ms: float = offset_ms
        self.resumed: bool = offset_ms > 0
        self.recording: bool = False
        self.total: int = 0
        self.chars: int = 0
        self.last_audio_at: float | None = None
        self.seen: set[bytes] = set()
        self.warned_no_text: bool = False
        self.tail: str = ""
        self.expect: str | None = None
        self.expect_anchored: bool = False
        self.listening_speed: float | None = None

    def on_websocket(self, ws: WebSocket) -> None:
        log(f"WS open {ws.url}")
        ws.on("framesent", self.on_sent)
        ws.on("framereceived", self.on_frame)
        ws.on("close", lambda _: log(f"WS close {ws.url}"))
        ws.on("socketerror", lambda err: log(f"WS error {err}"))

    def on_sent(self, payload: str | bytes) -> None:
        """Track the reading speed the page streams at; the server picks the voice model from it."""
        try:
            data: object = json.loads(payload)
        except ValueError:
            return
        speed: object = data.get("listening_speed") if isinstance(data, dict) else None
        if not isinstance(speed, int | float) or speed == self.listening_speed:
            return
        self.listening_speed = float(speed)
        if self.listening_speed == V4_READING_SPEED:
            log(f"reading speed {speed}x: Eleven v4")
        else:
            log(f"WARNING: reading speed {speed}x - the server reads with Eleven v2, not v4; set 1x and reopen")

    def on_frame(self, payload: str | bytes) -> None:
        if not self.recording:
            return
        if isinstance(payload, bytes):
            log(f"binary message, {len(payload)} B")
            return
        try:
            data: object = json.loads(payload)
        except ValueError:
            log(f"non-JSON message: {payload[:300]}")
            return
        if not isinstance(data, dict):
            return

        if data.get("type") == "config" and self.chars:
            self.expect, self.expect_anchored = self.tail, False
        audio: str | None = data.pop("audio", None)
        if audio:
            self.write_chunk(base64.b64decode(audio), data)
        if not audio or data.get("isFinal"):
            log(f"message: {json.dumps(data)[:500]}")

    def write_chunk(self, chunk: bytes, data: dict[str, object]) -> None:
        alignment: object = data.get("alignment") or data.get("normalizedAlignment")
        chars: object = alignment.get("chars") if isinstance(alignment, dict) else None
        digest: bytes = hashlib.sha1(chunk + json.dumps(chars).encode()).digest()
        if len(chunk) >= MIN_DEDUP_BYTES:
            if digest in self.seen:
                log(f"skipped duplicate chunk ({len(chunk)} B)")
                return
            self.seen.add(digest)
        if isinstance(alignment, dict) and isinstance(chars, list) and chars:
            repeated: int = self.repeated_prefix("".join(chars))
            if repeated == len(chars):
                log(f"skipped text repeated after a reconnect ({repeated} chars)")
                return
            if repeated:
                chunk, alignment = trim_chunk(chunk, alignment, repeated)
                chars = alignment["chars"]
                log(f"trimmed {repeated} chars repeated after a reconnect")
        self.out.write(chunk)
        self.out.flush()
        self.total += len(chunk)

        if isinstance(alignment, dict) and chars:
            self.write_alignment(alignment)
        elif not self.warned_no_text:
            self.warned_no_text = True
            log(f"audio chunk without text (e.g. a pause), timing kept; fields: {list(data)}")
        self.offset_ms += mp3_duration_ms(chunk)

        now: float = time.monotonic()
        if self.last_audio_at and now - self.last_audio_at > GAP_REPORT_SECONDS:
            log(f"next chunk arrived after {now - self.last_audio_at:.0f} s (nothing is missing in the file)")
        self.last_audio_at = now

    def write_alignment(self, alignment: dict[str, object]) -> None:
        chars: object = alignment["chars"]
        text: str = "".join(chars) if isinstance(chars, list) else ""
        self.transcript.write(text)
        self.transcript.flush()
        self.chars += len(text)
        self.tail = (self.tail + text)[-TAIL_CHARS:]
        line: dict[str, object] = {
            "offset_ms": round(self.offset_ms, 1),
            "chars": chars,
            "start_ms": alignment.get("charStartTimesMs"),
            "dur_ms": alignment.get("charDurationsMs"),
        }
        if self.resumed:
            line["resume"] = True
            self.resumed = False
        self.alignment.write(json.dumps(line, ensure_ascii=False) + "\n")
        self.alignment.flush()
        log(f"+ {' '.join(text.split())[:100]}")

    def repeated_prefix(self, text: str) -> int:
        """Return how many leading chars of a chunk repeat text recorded before the stream reconnected."""
        expect: str | None = self.expect
        if expect is None:
            return 0
        if self.expect_anchored:
            starts: Iterator[int] = iter((0,))
        elif len(text) < MIN_PROBE_CHARS:
            return 0
        else:
            starts = rfind_all(expect, text[:MIN_PROBE_CHARS])
        for at in starts:
            if expect.startswith(text, at):
                self.expect, self.expect_anchored = expect[at + len(text) :] or None, True
                return len(text)
            if len(expect) - at <= len(text) and text.startswith(expect[at:]):
                self.expect = None
                return len(expect) - at
        self.expect = None
        return 0

    def clear(self) -> None:
        for f in (self.out, self.transcript, self.alignment):
            f.seek(0)
            f.truncate()
        self.offset_ms = 0.0
        self.resumed = False
        self.tail, self.expect = "", None
        self.total = 0
        self.chars = 0
        self.seen.clear()


def rfind_all(text: str, sub: str) -> Iterator[int]:
    """Yield every position of sub in text from the last to the first, overlapping ones included."""
    at: int = text.rfind(sub)
    while at >= 0:
        yield at
        at = text.rfind(sub, 0, at + len(sub) - 1)


def trim_chunk(chunk: bytes, alignment: dict[str, object], drop: int) -> tuple[bytes, dict[str, object]]:
    """Drop the first `drop` characters of a chunk: its audio up to that character and their timings."""
    chars: object
    starts: object
    durations: object
    chars, starts, durations = alignment["chars"], alignment["charStartTimesMs"], alignment["charDurationsMs"]
    assert isinstance(chars, list) and isinstance(starts, list) and isinstance(durations, list)
    cut: float
    chunk, cut = mp3_cut_ms(chunk, float(starts[drop]))
    trimmed: dict[str, object] = {
        "chars": chars[drop:],
        "charStartTimesMs": [max(0.0, float(t) - cut) for t in starts[drop:]],
        "charDurationsMs": durations[drop:],
    }
    return chunk, trimmed


@contextmanager
def open_recording(output: Path) -> Iterator[Recorder]:
    """Open the MP3, text and timing files for appending; on exit write the .srt and .json subtitles."""
    offset_ms: float = mp3_duration_ms(output.read_bytes()) if output.exists() else 0.0
    align_path: Path = output.with_suffix(".align.jsonl")
    try:
        with (
            output.open("ab") as out,
            output.with_suffix(".txt").open("a", encoding="utf-8") as transcript,
            align_path.open("a", encoding="utf-8") as alignment,
        ):
            yield Recorder(out, transcript, alignment, offset_ms)
    finally:
        files: tuple[Path, Path, Path] = (output, output.with_suffix(".txt"), align_path)
        if all(f.exists() and not f.stat().st_size for f in files):
            for f in files:
                f.unlink()
        elif align_path.exists() and align_path.stat().st_size:
            sentences: int = build_subtitles(align_path)
            log(f"Timestamps: {sentences} sentences in {output.with_suffix('.srt').name} and .json")


def read_keys(presses: queue.SimpleQueue[str]) -> None:
    while True:
        presses.put(msvcrt.getwch().lower())


def speed_script(initial: float) -> str:
    """Return the init script with the speed every page starts at."""
    return SPEED_JS.replace("__INITIAL_SPEED__", str(initial))


def set_speed(context: BrowserContext, speed: float) -> None:
    for page in context.pages:
        for frame in page.frames:
            try:
                frame.evaluate(f"window.__edpSetSpeed({speed})")
            except Error:
                pass


class Monitor:
    """Keep a recording page at the target playback speed and log progress with the audio throughput.

    Every frame is checked every SPEED_CHECK_SECONDS: a frame without the speed script gets it injected (the page
    creates a buffer source per chunk, so all later audio plays at the target speed), and a frame whose target or
    playing buffers are off the target speed is retuned. The status line shows how many seconds of audio arrived per
    second of wall time and what the speed checks did since the previous line.
    """

    def __init__(self, page: Page, rec: Recorder, speed: float, label: str = "") -> None:
        self.page: Page = page
        self.prefix: str = f"[{label}] " if label else ""
        self.rec: Recorder = rec
        self.speed: float = speed
        now: float = time.monotonic()
        self.last_check: float = now
        self.last_status: float = now
        self.last_total: int = rec.total
        self.last_offset_ms: float = rec.offset_ms
        self.injected: int = 0
        self.retuned: int = 0
        self.stray_rates: set[float] = set()
        self.hooked: bool = False

    def tick(self) -> None:
        now: float = time.monotonic()
        if now - self.last_check >= SPEED_CHECK_SECONDS:
            self.last_check = now
            self.check_speed()
        fixed: int = self.injected or self.retuned
        if now - self.last_status >= STATUS_INTERVAL_SECONDS and (self.rec.total != self.last_total or fixed):
            self.report(now)

    def check_speed(self) -> None:
        for frame in self.page.frames:
            try:
                state: dict[str, Any] | None = frame.evaluate(SPEED_STATE_JS)
                if state is None:
                    frame.evaluate(speed_script(self.speed))
                    self.injected += 1
                    continue
                self.hooked = self.hooked or state["contexts"] > 0
                stray: list[float] = [rate for rate in state["rates"] if abs(rate - self.speed) > SPEED_TOLERANCE]
                if stray or abs(state["target"] - self.speed) > SPEED_TOLERANCE:
                    frame.evaluate(f"window.__edpSetSpeed({self.speed})")
                    self.retuned += 1
                    self.stray_rates.update(stray)
            except Error:
                continue

    def report(self, now: float) -> None:
        audio_seconds: float = max(0.0, self.rec.offset_ms - self.last_offset_ms) / 1000
        throughput: float = audio_seconds / (now - self.last_status)
        log(f"{self.prefix}saved {self.rec.total / MB:.2f} MB, throughput {throughput:.1f}x, {self.speed_summary()}")
        self.last_status, self.last_total, self.last_offset_ms = now, self.rec.total, self.rec.offset_ms
        self.injected, self.retuned = 0, 0
        self.stray_rates.clear()

    def speed_summary(self) -> str:
        target: str = f"speed {self.speed:g}x"
        fixes: list[str] = []
        if self.injected:
            fixes.append(f"speed script was missing, injected into {self.injected} frame(s)")
        if self.retuned:
            rates: str = ", ".join(f"{rate:g}x" for rate in sorted(self.stray_rates)) or "none playing"
            fixes.append(f"retuned {self.retuned} frame(s) (stray rates: {rates})")
        if fixes:
            return f"{target} FIXED: {'; '.join(fixes)}"
        if not self.hooked:
            return f"{target} not applied yet: no audio buffer started through the speed script"
        return f"{target} ok"


def parse_args() -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="Record ElevenReader audio to an MP3 file.")
    parser.add_argument(
        "output", type=Path, nargs="?", help="output file; default: first free workspace/output/recording_N.mp3"
    )
    parser.add_argument("--speed", type=float, default=64.0, help="playback speed while recording (1 = normal)")
    parser.add_argument("--url", default="https://elevenreader.io/", help="page to open, e.g. a document link")
    parser.add_argument("--chrome", type=Path, help="path to chrome.exe when it is not in a standard location")
    return parser.parse_args()


def find_chrome(explicit: Path | None) -> Path:
    chrome: Path | None = explicit or next((p for p in CHROME_PATHS if p.is_file()), None)
    if not chrome or not chrome.is_file():
        raise SystemExit("chrome.exe not found - pass its path with --chrome")
    return chrome


def next_free_output() -> Path:
    n: int = 1
    while (OUTPUT_DIR / f"recording_{n}.mp3").exists():
        n += 1
    return OUTPUT_DIR / f"recording_{n}.mp3"


def launch_chrome(chrome: Path, *, headless: bool = False) -> subprocess.Popen[bytes]:
    args: list[str] = [
        str(chrome),
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--force-dark-mode",
        "--enable-features=WebContentsForceDark",
    ]
    if headless:
        args += ["--headless=new", HEADLESS_WINDOW, "--autoplay-policy=no-user-gesture-required"]
    return subprocess.Popen([*args, "about:blank"])


def connect(pw: Playwright) -> Browser:
    for _ in range(CONNECT_ATTEMPTS):
        try:
            return pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        except Error:
            time.sleep(CONNECT_RETRY_SECONDS)
    raise SystemExit(f"Could not connect to Chrome (is port {CDP_PORT} free?)")


def handle_key(key: str, rec: Recorder, context: BrowserContext, speed: float) -> None:
    if key == KEY_CTRL_C:
        raise KeyboardInterrupt
    if key == KEY_CLEAR:
        rec.clear()
        log("CLEARED the file - starting from zero")
    elif key == KEY_TOGGLE:
        rec.recording = not rec.recording
        rec.last_audio_at = None
        set_speed(context, speed if rec.recording else 1)
        log(f"RECORDING ({speed}x)" if rec.recording else "PAUSED")


def fresh_page(context: BrowserContext) -> Page:
    """Open the one tab this run works in and close the empty tabs Chrome opened at start."""
    page: Page = context.new_page()
    for other in context.pages:
        if other is not page and other.url in BLANK_URLS:
            other.close()
    return page


def run(browser: Browser, rec: Recorder, url: str, speed: float) -> None:
    context: BrowserContext = browser.contexts[0]
    context.add_init_script(speed_script(1))
    page: Page = fresh_page(context)
    page.on("websocket", rec.on_websocket)
    page.goto(url)
    log("Passive mode: not recording, normal speed.")
    log("IN THE TERMINAL: SPACE = record/pause, C = clear file, Ctrl+C = quit.")

    presses: queue.SimpleQueue[str] = queue.SimpleQueue()
    threading.Thread(target=read_keys, args=(presses,), daemon=True).start()
    monitor: Monitor | None = None
    try:
        while browser.is_connected() and not page.is_closed():
            page.wait_for_timeout(POLL_MS)
            while not presses.empty():
                handle_key(presses.get(), rec, context, speed)
            if not rec.recording:
                monitor = None
                continue
            monitor = monitor or Monitor(page, rec, speed)
            monitor.tick()
    finally:
        if browser.is_connected() and not page.is_closed():
            page.close()


def main() -> None:
    args: argparse.Namespace = parse_args()
    chrome: Path = find_chrome(args.chrome)
    output: Path = args.output or next_free_output()
    output.parent.mkdir(parents=True, exist_ok=True)
    log(f"Saving to {output}")
    if output.exists():
        log(f"File exists - appending to it ({output.stat().st_size / MB:.2f} MB)")

    chrome_proc: subprocess.Popen[bytes] = launch_chrome(chrome)
    try:
        with sync_playwright() as pw, open_recording(output) as rec:
            try:
                run(connect(pw), rec, args.url, args.speed)
            except KeyboardInterrupt, Error:
                pass
    finally:
        chrome_proc.terminate()
    log(f"Done. Saved {rec.total / MB:.2f} MB to {output}")


if __name__ == "__main__":
    main()
