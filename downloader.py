"""Record ElevenReader audio from a real Chrome session to an MP3 file.

Launches the installed Google Chrome with its own profile and attaches to it over CDP, so Google sign-in works.
Starts in passive mode (not recording, normal speed). Keys in the terminal window: SPACE toggles recording with
playback speed-up, C clears the output file, Ctrl+C quits. Every audio chunk is appended to disk as it arrives,
so stopping never loses recorded data.

Usage:
    uv run downloader.py [FILE.mp3] [--speed 16] [--url https://elevenreader.io/] [--chrome PATH]

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
from pathlib import Path
from typing import BinaryIO, Final, TextIO

from playwright.sync_api import Browser, BrowserContext, Error, Page, Playwright, WebSocket, sync_playwright

# ── Constants ────────────────────────────────────────────────────────────────

ROOT_DIR: Final[Path] = Path(__file__).resolve().parent
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

MB: Final[int] = 1024 * 1024
"""Bytes in a megabyte."""

KEY_TOGGLE: Final[str] = " "
"""Starts or pauses recording."""

KEY_CLEAR: Final[str] = "c"
"""Clears the output file."""

KEY_CTRL_C: Final[str] = "\x03"
"""Ctrl+C as returned by msvcrt.getwch, which swallows the console interrupt."""

SPEED_JS: Final[str] = """
(() => {
    window.__edpSpeed = 1;
    for (const Ctx of [window.AudioContext, window.webkitAudioContext]) {
        if (!Ctx) continue;
        const originalCreate = Ctx.prototype.createBufferSource;
        Ctx.prototype.createBufferSource = function () {
            const src = originalCreate.call(this);
            const origStart = src.start;
            src.start = function () {
                if (window.__edpSpeed !== 1) {
                    try { src.playbackRate.value = window.__edpSpeed; } catch (e) {}
                }
                return origStart.apply(this, arguments);
            };
            return src;
        };
    }
})();
"""
"""Init script that plays every new audio buffer at window.__edpSpeed."""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Recorder:
    """Append audio chunks and their text from ElevenReader WebSocket frames to the output files."""

    def __init__(self, out: BinaryIO, transcript: TextIO) -> None:
        self.out: BinaryIO = out
        self.transcript: TextIO = transcript
        self.recording: bool = False
        self.total: int = 0
        self.last_audio_at: float | None = None
        self.seen: set[bytes] = set()
        self.warned_no_text: bool = False

    def on_websocket(self, ws: WebSocket) -> None:
        log(f"WS open {ws.url}")
        ws.on("framereceived", self.on_frame)
        ws.on("close", lambda _: log(f"WS close {ws.url}"))
        ws.on("socketerror", lambda err: log(f"WS error {err}"))

    def on_frame(self, payload: str | bytes) -> None:
        if not self.recording:
            return
        if isinstance(payload, bytes):
            log(f"binary message, {len(payload)} B")
            return
        try:
            data = json.loads(payload)
        except ValueError:
            log(f"non-JSON message: {payload[:300]}")
            return
        if not isinstance(data, dict):
            return

        audio = data.pop("audio", None)
        if audio:
            self.write_chunk(base64.b64decode(audio), data)
        if not audio or data.get("isFinal"):
            log(f"message: {json.dumps(data)[:500]}")

    def write_chunk(self, chunk: bytes, data: dict[str, object]) -> None:
        digest = hashlib.sha1(chunk).digest()
        if digest in self.seen:
            log(f"skipped duplicate chunk ({len(chunk)} B)")
            return
        self.seen.add(digest)
        self.out.write(chunk)
        self.out.flush()
        self.total += len(chunk)
        self.write_text(data)

        now = time.monotonic()
        if self.last_audio_at and now - self.last_audio_at > GAP_REPORT_SECONDS:
            log(f"next chunk arrived after {now - self.last_audio_at:.0f} s (nothing is missing in the file)")
        self.last_audio_at = now

    def write_text(self, data: dict[str, object]) -> None:
        alignment = data.get("alignment") or data.get("normalizedAlignment")
        chars = alignment.get("chars") if isinstance(alignment, dict) else None
        text = "".join(chars) if isinstance(chars, list) else ""
        if text:
            self.transcript.write(text)
            self.transcript.flush()
            log(f"+ {' '.join(text.split())[:100]}")
        elif not self.warned_no_text:
            self.warned_no_text = True
            log(f"server sends no text with the audio, message fields: {list(data)}")

    def clear(self) -> None:
        for f in (self.out, self.transcript):
            f.seek(0)
            f.truncate()
        self.total = 0
        self.seen.clear()


def read_keys(presses: queue.SimpleQueue[str]) -> None:
    while True:
        presses.put(msvcrt.getwch().lower())


def set_speed(context: BrowserContext, speed: float) -> None:
    for page in context.pages:
        try:
            page.evaluate(f"window.__edpSpeed = {speed}")
        except Error:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record ElevenReader audio to an MP3 file.")
    parser.add_argument(
        "output", type=Path, nargs="?", help="output file; default: first free workspace/output/recording_N.mp3"
    )
    parser.add_argument("--speed", type=float, default=16.0, help="playback speed while recording (1 = normal)")
    parser.add_argument("--url", default="https://elevenreader.io/", help="page to open, e.g. a document link")
    parser.add_argument("--chrome", type=Path, help="path to chrome.exe when it is not in a standard location")
    return parser.parse_args()


def find_chrome(explicit: Path | None) -> Path:
    chrome = explicit or next((p for p in CHROME_PATHS if p.is_file()), None)
    if not chrome or not chrome.is_file():
        raise SystemExit("chrome.exe not found - pass its path with --chrome")
    return chrome


def next_free_output() -> Path:
    n = 1
    while (OUTPUT_DIR / f"recording_{n}.mp3").exists():
        n += 1
    return OUTPUT_DIR / f"recording_{n}.mp3"


def launch_chrome(chrome: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            str(chrome),
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ]
    )


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


def run(browser: Browser, rec: Recorder, url: str, speed: float) -> None:
    context = browser.contexts[0]
    context.add_init_script(SPEED_JS)

    def watch(page: Page) -> None:
        page.on("websocket", rec.on_websocket)

    context.on("page", watch)
    for page in context.pages:
        watch(page)
    (context.pages[0] if context.pages else context.new_page()).goto(url)
    log("Passive mode: not recording, normal speed.")
    log("IN THE TERMINAL: SPACE = record/pause, C = clear file, Ctrl+C = quit.")

    presses: queue.SimpleQueue[str] = queue.SimpleQueue()
    threading.Thread(target=read_keys, args=(presses,), daemon=True).start()
    last_reported = -1
    last_status = time.monotonic()
    while browser.is_connected() and context.pages:
        context.pages[0].wait_for_timeout(POLL_MS)
        while not presses.empty():
            handle_key(presses.get(), rec, context, speed)
        if time.monotonic() - last_status >= STATUS_INTERVAL_SECONDS and rec.total != last_reported:
            log(f"saved {rec.total / MB:.2f} MB")
            last_reported = rec.total
            last_status = time.monotonic()


def main() -> None:
    args = parse_args()
    chrome = find_chrome(args.chrome)
    output: Path = args.output or next_free_output()
    output.parent.mkdir(parents=True, exist_ok=True)
    log(f"Saving to {output}")
    if output.exists():
        log(f"File exists - appending to it ({output.stat().st_size / MB:.2f} MB)")

    chrome_proc = launch_chrome(chrome)
    try:
        with (
            sync_playwright() as pw,
            output.open("ab") as out,
            output.with_suffix(".txt").open("a", encoding="utf-8") as transcript,
        ):
            rec = Recorder(out, transcript)
            try:
                run(connect(pw), rec, args.url, args.speed)
            except KeyboardInterrupt, Error:
                pass
    finally:
        chrome_proc.terminate()
    log(f"Done. Saved {rec.total / MB:.2f} MB to {output}")


if __name__ == "__main__":
    main()
