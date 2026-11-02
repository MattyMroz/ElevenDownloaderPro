"""Upload every document from workspace/input to ElevenReader and record its audio, one after another.

For each supported file: import it into the library, open the new document (it always starts at the beginning),
record at the given speed until the player reaches the end, save workspace/output/<name>.mp3 with its text,
sentence subtitles (.srt) and word timings (.json), and move the input to workspace/input/done. A file that fails goes to workspace/input/failed and the log prints the downloader.py
command that resumes it by hand.

Usage:
    uv run src/auto.py [--speed 64] [--parallel N] [--headless] [--chrome PATH]
"""

import argparse
import subprocess
import time
from collections import deque
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Final

from playwright.sync_api import BrowserContext, Error, Locator, Page, sync_playwright

from downloader import (
    MB,
    OUTPUT_DIR,
    ROOT_DIR,
    V4_READING_SPEED,
    Monitor,
    Recorder,
    connect,
    find_chrome,
    fresh_page,
    launch_chrome,
    log,
    open_recording,
    set_speed,
    speed_script,
)

# ── Constants ────────────────────────────────────────────────────────────────

INPUT_DIR: Final[Path] = ROOT_DIR / "workspace" / "input"
"""Documents waiting to be converted."""

DONE_DIR: Final[Path] = INPUT_DIR / "done"
"""Inputs whose recording finished."""

FAILED_DIR: Final[Path] = INPUT_DIR / "failed"
"""Inputs whose recording did not finish; resume them with downloader.py."""

SUPPORTED_SUFFIXES: Final[frozenset[str]] = frozenset({".txt", ".md", ".epub", ".pdf", ".docx", ".doc", ".html"})
"""File types accepted by the ElevenReader import dialog."""

LIBRARY_URL: Final[str] = "https://elevenreader.io/reader/library"
"""Library page with the Import button."""

ADD_ENDPOINT: Final[str] = "/v1/reader/reads/add/v2"
"""API call made by the Upload button; its JSON response carries the new read_id."""

USER_CONFIG_URL: Final[str] = "https://api.elevenlabs.io/v1/reader/user_config"
"""Account settings, including the reading speed a document starts its stream at (playback_speed_rate)."""

READY_TIMEOUT_MS: Final[int] = 10 * 60 * 1000
"""How long to wait for a document to become playable after upload."""

ACTION_TIMEOUT_MS: Final[int] = 2 * 60 * 1000
"""Time allowed for a click or page load; the site can lag for tens of seconds."""

LIBRARY_LOAD_MS: Final[int] = 45_000
"""How long the library may take to show its Import button before the site counts as unavailable."""

SITE_WAIT_MINUTES: Final[int] = 120
"""How long to keep retrying while ElevenReader is down."""

END_IDLE_SECONDS: Final[float] = 10.0
"""Quiet time after the player stops at the end before the recording counts as complete."""

END_SLACK_CHARS: Final[int] = 30
"""Player position this close to the end counts as the end; at high speed it can hang on the final pause."""

START_TIMEOUT_SECONDS: Final[int] = 60
"""How long to wait for the first audio after pressing Play."""

PLAY_ATTEMPTS: Final[int] = 3
"""How many times to press Play before the document counts as failed."""

STALL_SECONDS: Final[float] = 5 * 60.0
"""Time without new audio, before the end, after which the recording counts as failed."""

PLAYER_STATE_JS: Final[str] = """
() => {
    const slider = document.querySelector('input[type=range], [role=slider]');
    const value = slider ? Number(slider.value || slider.getAttribute('aria-valuenow')) : 0;
    const max = slider ? Number(slider.max || slider.getAttribute('aria-valuemax')) : 0;
    return {value, max};
}
"""
"""Report the player position and the document length, both in characters."""


def pending_inputs() -> list[Path]:
    return sorted(p for p in INPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)


def free_output(stem: str) -> Path:
    path: Path = OUTPUT_DIR / f"{stem}.mp3"
    n: int = 2
    while path.exists():
        path = OUTPUT_DIR / f"{stem} ({n}).mp3"
        n += 1
    return path


def button(page: Page, name: str) -> Locator:
    """Return the visible button with this exact name; narrow layouts keep hidden duplicates in the page."""
    return page.get_by_role("button", name=name, exact=True).filter(visible=True)


def open_library(page: Page) -> None:
    """Open the library, waiting out ElevenReader outages (e.g. 502 Bad Gateway) for up to SITE_WAIT_MINUTES."""
    import_button: Locator = button(page, "Import")
    for minute in range(SITE_WAIT_MINUTES):
        try:
            page.goto(LIBRARY_URL)
            import_button.wait_for(timeout=LIBRARY_LOAD_MS)
            return
        except Error:
            if page.is_closed():
                raise
            log(f"ElevenReader unavailable ({page.title() or 'no response'}), retrying in 1 min ({minute + 1})")
            page.wait_for_timeout(60_000)
    raise SystemExit(f"ElevenReader still unavailable after {SITE_WAIT_MINUTES} min")


def upload(page: Page, document: Path) -> tuple[str, int, str]:
    """Import the document and return its read_id, the character count the server will read and the API token."""
    open_library(page)
    button(page, "Import").click()
    with page.expect_response(lambda r: ADD_ENDPOINT in r.url and r.request.method == "POST") as response:
        page.locator("input[type=file]").set_input_files(document)
        button(page, "Upload").click()
    read: dict[str, Any] = response.value.json()
    token: str = response.value.request.all_headers()["authorization"]
    return str(read["read_id"]), int(read.get("char_count") or 0), token


def reset_reading_speed(page: Page, token: str) -> None:
    """Set the account reading speed to 1x before a document opens.

    The page starts its stream at the account speed as soon as the document loads, and the server picks the voice
    model when the stream starts, so changing the speed in the open player is too late.
    """
    headers: dict[str, str] = {"authorization": token}
    config: dict[str, Any] = page.request.get(USER_CONFIG_URL, headers=headers).json()
    speed: object = config.get("playback_speed_rate")
    if speed == V4_READING_SPEED:
        return
    config["playback_speed_rate"] = V4_READING_SPEED
    status: int = page.request.post(USER_CONFIG_URL, headers=headers, data=config).status
    log(f"Reading speed was {speed}x, set to {V4_READING_SPEED}x (HTTP {status})")


class Job:
    """One document from its uploaded read to finished files, advanced in small steps so several can run at once."""

    def __init__(self, document: Path, read_id: str, char_count: int, page: Page, speed: float) -> None:
        self.document: Path = document
        self.name: str = document.name
        self.char_count: int = char_count
        self.page: Page = page
        self.speed: float = speed
        self.url: str = f"{LIBRARY_URL}/{read_id}"
        self.output: Path = free_output(document.stem)
        self.files: ExitStack = ExitStack()
        self.rec: Recorder = self.files.enter_context(open_recording(self.output))
        self.monitor: Monitor = Monitor(page, self.rec, speed, label=self.name)
        self.play_attempts: int = 0
        self.played_at: float = 0.0
        self.last_total: int = 0
        self.last_progress: float = 0.0

    def start(self) -> None:
        """Open the document and press Play; recording runs from page load because the page may start on its own."""
        log(f"[{self.name}] uploaded as {self.url}, recording to {self.output.name}")
        self.page.on("websocket", self.rec.on_websocket)
        self.rec.recording = True
        self.page.goto(self.url)
        button(self.page, "Play").wait_for(timeout=READY_TIMEOUT_MS)
        set_speed(self.page.context, self.speed)
        self.press_play()

    def press_play(self) -> None:
        play: Locator = button(self.page, "Play")
        if play.count():
            play.click()
        self.play_attempts += 1
        self.played_at = self.last_progress = time.monotonic()

    def step(self) -> bool | None:
        """Advance one tick; return True when finished, False when it failed, None while still recording."""
        now: float = time.monotonic()
        if self.rec.listening_speed not in (None, V4_READING_SPEED):
            return False
        self.monitor.tick()
        if not self.rec.total:
            if now - self.played_at < START_TIMEOUT_SECONDS:
                return None
            log(f"[{self.name}] no audio {START_TIMEOUT_SECONDS} s after Play ({self.play_attempts}/{PLAY_ATTEMPTS})")
            if self.play_attempts >= PLAY_ATTEMPTS:
                return False
            self.press_play()
            return None
        if self.rec.total != self.last_total:
            self.last_total, self.last_progress = self.rec.total, now
        state: dict[str, float] = self.page.evaluate(PLAYER_STATE_JS)
        player_done: bool = state["max"] > 0 and state["max"] - state["value"] <= END_SLACK_CHARS
        text_done: bool = self.char_count > 0 and self.rec.chars >= self.char_count
        if (player_done or text_done) and now - self.last_progress >= END_IDLE_SECONDS:
            return True
        return False if now - self.last_progress >= STALL_SECONDS else None

    def close(self) -> None:
        self.rec.recording = False
        if not self.page.is_closed():
            self.page.remove_listener("websocket", self.rec.on_websocket)
            self.page.close()
        self.files.close()

    def finish(self, finished: bool) -> None:
        """Close the files, report completeness and move the input to done/ or failed/."""
        self.close()
        rec: Recorder
        name: str
        rec, name = self.rec, self.name
        log(f"[{name}] text received: {rec.chars}/{self.char_count} chars")
        if rec.chars > self.char_count:
            log(
                f"[{name}] WARNING: {rec.chars - self.char_count} extra chars - a sentence may repeat after a reconnect"
            )
        if finished and rec.chars >= self.char_count:
            self.document.replace(DONE_DIR / name)
            log(f"[{name}] Done: {self.output.name} ({rec.total / MB:.2f} MB)")
            return
        self.document.replace(FAILED_DIR / name)
        if rec.listening_speed not in (None, V4_READING_SPEED):
            log(
                f"[{name}] FAILED: streamed at {rec.listening_speed}x (Eleven v2); delete {self.output.name} and convert again"
            )
        elif finished:
            missing: int = self.char_count - rec.chars
            log(f"[{name}] INCOMPLETE: {missing} chars missing; delete {self.output.name} and convert again")
        else:
            log(f"[{name}] FAILED: no audio progress ({rec.total / MB:.2f} MB saved). Resume by hand:")
            log(f'  uv run src/downloader.py "{self.output}" --url "{self.url}"')


def begin(main_page: Page, document: Path, speed: float) -> Job:
    """Upload a document from the main tab and start recording it in a tab of its own."""
    log(f"=== {document.name}")
    read_id: str
    char_count: int
    token: str
    read_id, char_count, token = upload(main_page, document)
    reset_reading_speed(main_page, token)
    page: Page = main_page.context.new_page()
    page.set_default_timeout(ACTION_TIMEOUT_MS)
    job: Job = Job(document, read_id, char_count, page, speed)
    try:
        job.start()
    except Error:
        job.close()
        raise
    return job


def run_all(main_page: Page, documents: list[Path], speed: float, parallel: int) -> Page:
    """Keep up to `parallel` documents recording at once until all are done; return the (possibly new) main tab."""
    pending: deque[Path] = deque(documents)
    active: list[Job] = []
    try:
        while pending or active:
            while pending and len(active) < parallel:
                document: Path = pending.popleft()
                try:
                    active.append(begin(main_page, document, speed))
                except Error as e:
                    if main_page.is_closed():
                        raise
                    document.replace(FAILED_DIR / document.name)
                    log(f"FAILED: {document.name}: {e.message.splitlines()[0]}")
                    main_page = replace_page(main_page)
            main_page.wait_for_timeout(1000)
            for job in list(active):
                try:
                    result: bool | None = job.step()
                except Error as e:
                    if job.page.is_closed() or main_page.is_closed():
                        raise
                    log(f"[{job.name}] error: {e.message.splitlines()[0]}")
                    result = False
                if result is not None:
                    active.remove(job)
                    job.finish(result)
    except Error:
        for job in active:
            job.close()
        log(f"Browser closed - stopping; unfinished files stay in {INPUT_DIR.name}/")
    return main_page


def replace_page(page: Page) -> Page:
    """Continue in a new tab; a tab whose renderer crashed rejects every later action but never reports closed."""
    fresh: Page = page.context.new_page()
    fresh.set_default_timeout(ACTION_TIMEOUT_MS)
    page.close()
    return fresh


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Convert every document in workspace/input to an MP3 file."
    )
    parser.add_argument("--speed", type=float, default=64.0, help="playback speed while recording (1 = normal)")
    parser.add_argument("--parallel", type=int, default=1, help="documents recorded at once, each in its own tab")
    parser.add_argument("--headless", action="store_true", help="run Chrome without a window")
    parser.add_argument("--chrome", type=Path, help="path to chrome.exe when it is not in a standard location")
    args: argparse.Namespace = parser.parse_args()

    for directory in (INPUT_DIR, DONE_DIR, FAILED_DIR, OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    documents: list[Path] = pending_inputs()
    if not documents:
        log(f"No supported files in {INPUT_DIR}")
        return
    log(f"{len(documents)} file(s) to convert")

    chrome_proc: subprocess.Popen[bytes] = launch_chrome(find_chrome(args.chrome), headless=args.headless)
    try:
        with sync_playwright() as pw:
            context: BrowserContext = connect(pw).contexts[0]
            context.add_init_script(speed_script(args.speed))
            page: Page = fresh_page(context)
            page.set_default_timeout(ACTION_TIMEOUT_MS)
            try:
                page = run_all(page, documents, args.speed, args.parallel)
            finally:
                if not page.is_closed():
                    page.close()
    except KeyboardInterrupt:
        log("Stopped by user")
    finally:
        chrome_proc.terminate()


if __name__ == "__main__":
    main()
