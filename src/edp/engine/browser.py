"""Google Chrome started on the private ElevenReader profile and attached over CDP, with its failures."""

from __future__ import annotations

import asyncio
import socket
import subprocess
from typing import TYPE_CHECKING, Final

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from edp.errors import ErrorCode, ErrorContext, TtsConfigError, TtsProviderUnavailableError
from edp.private_dir import PrivateDirectoryError, restrict_directory
from edp.process_lock import ProcessLock
from edp.utils.logger import get_logger

from .api_backend import ReaderPage, speed_script, unavailable_error
from .config import find_chrome, profile_dir
from .constants import CONNECT_ATTEMPTS, CONNECT_INTERVAL_S, PAGE_SPEED, UNAVAILABLE_RETRY_S

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Browser, BrowserContext, CDPSession, Playwright

__all__ = ["ChromeBusyError", "ChromeMissingError", "ChromeSession"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_LOCK_NAME: Final[str] = "chrome.lock"
"""Lock file guarding the profile against a second edp browser."""

_LOOPBACK: Final[str] = "127.0.0.1"
"""Interface the remote debugging port listens on."""

_EXIT_TIMEOUT_S: Final[float] = 10.0
"""Wait for Chrome to exit after an exit request or terminate before the next, harder stop."""

_BLANK_URLS: Final[frozenset[str]] = frozenset({"about:blank", "chrome://newtab/", "chrome://new-tab-page/"})
"""Empty tabs Chrome opens at start, closed so each attempt works in its own tab."""

_HEADLESS_ARGS: Final[tuple[str, ...]] = (
    "--headless=new",
    "--window-size=1600,1000",
    "--autoplay-policy=no-user-gesture-required",
    "--mute-audio",
)
"""Flags for a recording run: no window, desktop layout, silent playback without a user gesture."""


class ChromeMissingError(TtsConfigError):
    """Google Chrome is not installed in a standard location or on ``PATH``."""


class ChromeBusyError(TtsProviderUnavailableError):
    """Another edp browser already holds the ElevenReader profile."""


class ChromeSession:
    """One Chrome process on the private profile, owned until :meth:`close`."""

    def __init__(self, root: Path, *, headless: bool) -> None:
        """Bind the session to the ElevenReader *root*, without starting anything yet."""
        self._root: Path = root
        self._headless: bool = headless
        self._lock: ProcessLock = ProcessLock(root / _LOCK_NAME)
        self._process: subprocess.Popen[bytes] | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    @property
    def alive(self) -> bool:
        """Whether the browser is started, attached and its process still runs."""
        return (
            self._browser is not None
            and self._browser.is_connected()
            and self._process is not None
            and self._process.poll() is None
        )

    async def start(self) -> None:
        """Lock the profile, restrict it to the current account, start Chrome and attach to it."""
        if self.alive:
            return
        chrome: Path | None = find_chrome()
        if chrome is None:
            raise ChromeMissingError(context=_missing_chrome_context())
        if not self._lock.acquire():
            raise ChromeBusyError(retry_after_s=UNAVAILABLE_RETRY_S, context=_busy_context())
        try:
            await self._launch(chrome)
        except BaseException:
            await self.close()
            raise

    async def new_page(self) -> ReaderPage:
        """Open a fresh tab in the attached browser."""
        if self._context is None:
            message: str = "ElevenReader browser is not started"
            raise unavailable_error(message)
        try:
            return ReaderPage(await self._context.new_page())
        except PlaywrightError:
            reason: str = "ElevenReader browser could not open a tab"
            raise unavailable_error(reason) from None

    async def close(self) -> None:
        """Ask Chrome to exit so the profile is saved, detach, stop it and release the lock; safe to repeat."""
        browser: Browser | None = self._browser
        playwright: Playwright | None = self._playwright
        process: subprocess.Popen[bytes] | None = self._process
        self._browser, self._playwright, self._process, self._context = None, None, None, None
        exiting: bool = False
        try:
            exiting = await _request_exit(browser)
            await _detach(browser, playwright)
        finally:
            try:
                if process is not None:
                    await asyncio.to_thread(_stop_process, process, grace_s=_EXIT_TIMEOUT_S if exiting else 0.0)
            finally:
                self._lock.release()

    async def _launch(self, chrome: Path) -> None:
        user_data: Path = profile_dir(self._root)
        try:
            user_data.mkdir(parents=True, exist_ok=True)
            restrict_directory(self._root)
        except (OSError, PrivateDirectoryError) as error:
            raise TtsConfigError(context=_profile_context()) from error
        port: int = _free_port()
        try:
            process: subprocess.Popen[bytes] = subprocess.Popen(  # noqa: S603 - installed Chrome with own argv
                _chrome_args(chrome, user_data, port, headless=self._headless),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            reason: str = "Google Chrome could not be started"
            raise unavailable_error(reason) from None
        self._process = process
        try:
            await self._attach(process, port)
        except PlaywrightError:
            reason = "ElevenReader could not drive Chrome"
            raise unavailable_error(reason) from None
        logger.info("ElevenReader browser started", headless=self._headless)

    async def _attach(self, process: subprocess.Popen[bytes], port: int) -> None:
        playwright: Playwright = await async_playwright().start()
        self._playwright = playwright
        browser: Browser = await _connect(playwright, process, port)
        self._browser = browser
        context: BrowserContext = browser.contexts[0]
        self._context = context
        if self._headless:
            await context.add_init_script(speed_script(PAGE_SPEED))
        for page in context.pages:
            if page.url in _BLANK_URLS:
                await page.close()


async def _connect(playwright: Playwright, process: subprocess.Popen[bytes], port: int) -> Browser:
    for _ in range(CONNECT_ATTEMPTS):
        if process.poll() is not None:
            break
        try:
            return await playwright.chromium.connect_over_cdp(f"http://{_LOOPBACK}:{port}")
        except PlaywrightError:
            await asyncio.sleep(CONNECT_INTERVAL_S)
    reason: str = "ElevenReader could not attach to Chrome"
    raise unavailable_error(reason)


def _chrome_args(chrome: Path, user_data: Path, port: int, *, headless: bool) -> list[str]:
    args: list[str] = [
        str(chrome),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        args.extend(_HEADLESS_ARGS)
    return [*args, "about:blank"]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((_LOOPBACK, 0))
        port: int = probe.getsockname()[1]
    return port


async def _request_exit(browser: Browser | None) -> bool:
    if browser is None or not browser.is_connected():
        return False
    try:
        cdp: CDPSession = await browser.new_browser_cdp_session()
    except PlaywrightError:
        return False
    try:
        await cdp.send("Browser.close")
    except PlaywrightError:
        logger.debug("ElevenReader browser closed its connection while exiting")
    return True


async def _detach(browser: Browser | None, playwright: Playwright | None) -> None:
    try:
        if browser is not None:
            await browser.close()
    except PlaywrightError:
        logger.debug("ElevenReader browser was already disconnected")
    finally:
        if playwright is not None:
            await _stop_driver(playwright)


async def _stop_driver(playwright: Playwright) -> None:
    try:
        await playwright.stop()
    except PlaywrightError:
        logger.debug("ElevenReader Playwright driver was already stopped")


def _stop_process(process: subprocess.Popen[bytes], *, grace_s: float) -> None:
    if process.poll() is not None or _exits_within(process, grace_s):
        return
    try:
        process.terminate()
        process.wait(timeout=_EXIT_TIMEOUT_S)
    except subprocess.TimeoutExpired, OSError:
        _kill(process)


def _exits_within(process: subprocess.Popen[bytes], timeout_s: float) -> bool:
    if timeout_s <= 0:
        return False
    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        logger.warning("ElevenReader Chrome ignored the exit request and is stopped by force")
        return False
    return True


def _kill(process: subprocess.Popen[bytes]) -> None:
    try:
        process.kill()
        process.wait(timeout=_EXIT_TIMEOUT_S)
    except subprocess.TimeoutExpired, OSError:
        logger.warning("ElevenReader Chrome could not be stopped")


def _missing_chrome_context() -> ErrorContext:
    return ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message="Google Chrome is not installed",
        suggestion="Install Google Chrome (winget install Google.Chrome).",
    )


def _busy_context() -> ErrorContext:
    return ErrorContext(
        code=ErrorCode.TTS_ENGINE_UNAVAILABLE,
        message="ElevenReader browser profile is in use",
        suggestion="Close the `edp login` window or the other edp process using this home directory and try again.",
    )


def _profile_context() -> ErrorContext:
    return ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message="ElevenReader browser profile could not be prepared",
        suggestion="Check the permissions of the edp home directory.",
    )
