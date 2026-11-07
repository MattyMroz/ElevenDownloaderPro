from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import cast

import pytest
from fakes import FakePlaywrightPage
from loguru import logger as loguru_logger
from playwright.async_api import Error as PlaywrightError

from edp.engine import browser as browser_module
from edp.engine.api_backend import ReaderPage
from edp.engine.browser import (
    ChromeBusyError,
    ChromeMissingError,
    ChromeSession,
    _chrome_args,
    _stop_process,
)
from edp.errors import FatalError, TtsProviderUnavailableError
from edp.process_lock import ProcessLock

pytestmark = pytest.mark.unit


class _Process:
    def __init__(
        self,
        *,
        exited: bool = False,
        stubborn: bool = False,
        unkillable: bool = False,
        terminate_error: OSError | None = None,
    ) -> None:
        self.returncode: int | None = 1 if exited else None
        self.stubborn: bool = stubborn
        self.unkillable: bool = unkillable
        self.terminate_error: OSError | None = terminate_error
        self.exit_requested: bool = False
        self.calls: list[str] = []

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.calls.append("terminate")
        if self.terminate_error is not None:
            raise self.terminate_error
        if not self.stubborn:
            self.returncode = 0

    def wait(self, timeout: float) -> int:
        self.calls.append("wait")
        if self.exit_requested:
            self.returncode = 0
        if self.returncode is None:
            raise subprocess.TimeoutExpired("chrome", timeout)
        return self.returncode

    def kill(self) -> None:
        self.calls.append("kill")
        if not self.unkillable:
            self.returncode = -9


class _Tab:
    def __init__(self, url: str) -> None:
        self.url: str = url
        self.closed: bool = False

    async def close(self) -> None:
        self.closed = True


class _Context:
    def __init__(self) -> None:
        self.pages: list[_Tab] = [_Tab("about:blank"), _Tab("https://elevenreader.io/reader/library")]
        self.scripts: list[str] = []
        self.page_error: Exception | None = None
        self.script_error: Exception | None = None

    async def add_init_script(self, script: str) -> None:
        if self.script_error is not None:
            raise self.script_error
        self.scripts.append(script)

    async def new_page(self) -> FakePlaywrightPage:
        if self.page_error is not None:
            raise self.page_error
        return FakePlaywrightPage()


class _Cdp:
    def __init__(self, browser: _Browser) -> None:
        self.browser: _Browser = browser

    async def send(self, method: str) -> dict[str, object]:
        self.browser.sent.append(method)
        self.browser.process.exit_requested = self.browser.exits
        self.browser.connected = False
        message: str = "Target page, context or browser has been closed"
        raise PlaywrightError(message)


class _Browser:
    def __init__(self, process: _Process) -> None:
        self.process: _Process = process
        self.contexts: list[_Context] = [_Context()]
        self.connected: bool = True
        self.exits: bool = True
        self.cdp_error: Exception | None = None
        self.sent: list[str] = []
        self.close_error: Exception | None = None

    def is_connected(self) -> bool:
        return self.connected

    async def new_browser_cdp_session(self) -> _Cdp:
        if self.cdp_error is not None:
            raise self.cdp_error
        return _Cdp(self)

    async def close(self) -> None:
        self.connected = False
        if self.close_error is not None:
            raise self.close_error


class _Chromium:
    def __init__(self, browser: _Browser, failures: int) -> None:
        self.browser: _Browser = browser
        self.failures: int = failures
        self.urls: list[str] = []

    async def connect_over_cdp(self, url: str) -> _Browser:
        self.urls.append(url)
        if self.failures:
            self.failures -= 1
            message: str = "connect ECONNREFUSED"
            raise PlaywrightError(message)
        return self.browser


class _Playwright:
    def __init__(self, browser: _Browser, failures: int) -> None:
        self.chromium: _Chromium = _Chromium(browser, failures)
        self.stopped: bool = False

    async def stop(self) -> None:
        self.stopped = True


class _Starter:
    def __init__(self, playwright: _Playwright, error: Exception | None) -> None:
        self.playwright: _Playwright = playwright
        self.error: Exception | None = error

    async def start(self) -> _Playwright:
        if self.error is not None:
            raise self.error
        return self.playwright


class _Chrome:
    def __init__(self, root: Path) -> None:
        self.root: Path = root
        self.process: _Process = _Process()
        self.browser: _Browser = _Browser(self.process)
        self.playwright: _Playwright = _Playwright(self.browser, failures=1)
        self.argv: list[str] = []
        self.restricted: list[Path] = []
        self.driver_error: Exception | None = None

    def starter(self) -> _Starter:
        return _Starter(self.playwright, self.driver_error)

    def popen(self, argv: list[str], **kwargs: object) -> _Process:
        self.argv = argv
        return self.process


@pytest.fixture
def chrome(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Chrome:
    fake: _Chrome = _Chrome(tmp_path / "elevenreader")
    monkeypatch.setattr(browser_module, "find_chrome", lambda: tmp_path / "chrome.exe")
    monkeypatch.setattr(browser_module, "restrict_directory", fake.restricted.append)
    monkeypatch.setattr(subprocess, "Popen", fake.popen)
    monkeypatch.setattr(browser_module, "async_playwright", fake.starter)
    monkeypatch.setattr(browser_module, "CONNECT_INTERVAL_S", 0.0)
    return fake


def _lock_free(root: Path) -> bool:
    lock: ProcessLock = ProcessLock(root / "chrome.lock")
    acquired: bool = lock.acquire()
    lock.release()
    return acquired


def test_chrome_session_start_launches_attaches_and_closes_blank_tabs(chrome: _Chrome, tmp_path: Path) -> None:
    session = ChromeSession(chrome.root, headless=True)

    asyncio.run(session.start())

    assert session.alive
    assert chrome.argv[0] == str(tmp_path / "chrome.exe")
    assert "--headless=new" in chrome.argv
    assert f"--user-data-dir={chrome.root / 'chrome-profile'}" in chrome.argv
    assert (chrome.root / "chrome-profile").is_dir()
    assert chrome.restricted == [chrome.root]
    assert len(chrome.playwright.chromium.urls) == 2
    context: _Context = chrome.browser.contexts[0]
    assert "__edpSpeed" in context.scripts[0]
    assert [tab.closed for tab in context.pages] == [True, False]
    assert not _lock_free(chrome.root)
    asyncio.run(session.close())


def test_chrome_session_visible_start_adds_no_speed_script(chrome: _Chrome) -> None:
    session = ChromeSession(chrome.root, headless=False)

    asyncio.run(session.start())
    asyncio.run(session.close())

    assert chrome.browser.contexts[0].scripts == []
    assert "--headless=new" not in chrome.argv


def test_chrome_session_close_asks_chrome_to_exit_and_releases_lock(chrome: _Chrome) -> None:
    session = ChromeSession(chrome.root, headless=True)
    asyncio.run(session.start())

    asyncio.run(session.close())
    asyncio.run(session.close())

    assert not session.alive
    assert chrome.browser.sent == ["Browser.close"]
    assert chrome.playwright.stopped
    assert chrome.process.calls == ["wait"]
    assert _lock_free(chrome.root)


def test_chrome_session_close_chrome_ignoring_exit_request_terminates_it(chrome: _Chrome) -> None:
    session = ChromeSession(chrome.root, headless=True)
    asyncio.run(session.start())
    chrome.browser.exits = False
    captured: list[str] = []
    handler_id: int = loguru_logger.add(lambda message: captured.append(str(message)), level="WARNING")

    try:
        asyncio.run(session.close())
    finally:
        loguru_logger.remove(handler_id)

    assert any("ignored the exit request" in message for message in captured)
    assert chrome.browser.sent == ["Browser.close"]
    assert chrome.process.calls == ["wait", "terminate", "wait"]
    assert _lock_free(chrome.root)


def test_chrome_session_close_without_cdp_session_terminates_without_waiting(chrome: _Chrome) -> None:
    session = ChromeSession(chrome.root, headless=True)
    asyncio.run(session.start())
    chrome.browser.cdp_error = PlaywrightError("Browser has been closed")

    asyncio.run(session.close())

    assert chrome.browser.sent == []
    assert chrome.process.calls == ["terminate", "wait"]
    assert _lock_free(chrome.root)


def test_chrome_session_close_browser_breaking_still_stops_chrome_and_releases_lock(chrome: _Chrome) -> None:
    session = ChromeSession(chrome.root, headless=True)
    asyncio.run(session.start())
    chrome.browser.close_error = RuntimeError("driver crashed")

    with pytest.raises(RuntimeError, match="driver crashed"):
        asyncio.run(session.close())

    assert chrome.playwright.stopped
    assert chrome.process.calls == ["wait"]
    assert _lock_free(chrome.root)


def test_chrome_session_close_gone_browser_is_tolerated(chrome: _Chrome) -> None:
    session = ChromeSession(chrome.root, headless=True)
    asyncio.run(session.start())
    chrome.browser.close_error = PlaywrightError("Browser has been closed")

    asyncio.run(session.close())

    assert chrome.process.calls == ["wait"]
    assert _lock_free(chrome.root)


def test_chrome_session_start_without_chrome_raises_missing_and_keeps_lock_free(
    chrome: _Chrome,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(browser_module, "find_chrome", lambda: None)

    with pytest.raises(ChromeMissingError):
        asyncio.run(ChromeSession(chrome.root, headless=True).start())

    assert chrome.argv == []


def test_chrome_session_start_with_profile_locked_raises_busy(chrome: _Chrome) -> None:
    chrome.root.mkdir(parents=True)
    holder: ProcessLock = ProcessLock(chrome.root / "chrome.lock")
    assert holder.acquire()

    try:
        with pytest.raises(ChromeBusyError) as error:
            asyncio.run(ChromeSession(chrome.root, headless=True).start())
    finally:
        holder.release()

    assert isinstance(error.value, FatalError)
    assert chrome.argv == []


def test_chrome_session_start_chrome_exiting_raises_unavailable_and_cleans_up(chrome: _Chrome) -> None:
    chrome.process.returncode = 1
    session = ChromeSession(chrome.root, headless=True)

    with pytest.raises(TtsProviderUnavailableError, match="attach"):
        asyncio.run(session.start())

    assert not session.alive
    assert chrome.playwright.stopped
    assert chrome.process.calls == []
    assert _lock_free(chrome.root)


@pytest.mark.parametrize("failing", ["driver", "init_script"])
def test_chrome_session_start_playwright_failing_raises_unavailable_and_cleans_up(
    chrome: _Chrome, failing: str
) -> None:
    error: PlaywrightError = PlaywrightError("Target page, context or browser has been closed")
    if failing == "driver":
        chrome.driver_error = error
    else:
        chrome.browser.contexts[0].script_error = error
    session = ChromeSession(chrome.root, headless=True)

    with pytest.raises(TtsProviderUnavailableError) as raised:
        asyncio.run(session.start())

    assert raised.value.__cause__ is None
    assert not session.alive
    assert chrome.process.returncode is not None
    assert _lock_free(chrome.root)


def test_chrome_session_start_popen_failing_raises_unavailable(
    chrome: _Chrome,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(argv: list[str], **kwargs: object) -> _Process:
        message: str = "access denied"
        raise PermissionError(message)

    monkeypatch.setattr(subprocess, "Popen", refuse)

    with pytest.raises(TtsProviderUnavailableError) as error:
        asyncio.run(ChromeSession(chrome.root, headless=True).start())

    assert error.value.__cause__ is None
    assert _lock_free(chrome.root)


def test_chrome_session_new_page_wraps_tab_or_raises_unavailable(chrome: _Chrome) -> None:
    session = ChromeSession(chrome.root, headless=True)
    with pytest.raises(TtsProviderUnavailableError, match="not started"):
        asyncio.run(session.new_page())

    async def scenario() -> ReaderPage:
        await session.start()
        try:
            page: ReaderPage = await session.new_page()
            chrome.browser.contexts[0].page_error = PlaywrightError("Target closed")
            with pytest.raises(TtsProviderUnavailableError, match="tab"):
                await session.new_page()
            return page
        finally:
            await session.close()

    assert isinstance(asyncio.run(scenario()), ReaderPage)


@pytest.mark.parametrize(("headless", "flags"), [(True, True), (False, False)])
def test_chrome_args_headless_flags_follow_mode(tmp_path: Path, headless: bool, flags: bool) -> None:
    args: list[str] = _chrome_args(tmp_path / "chrome.exe", tmp_path / "profile", 9333, headless=headless)

    assert args[0] == str(tmp_path / "chrome.exe")
    assert "--remote-debugging-port=9333" in args
    assert f"--user-data-dir={tmp_path / 'profile'}" in args
    assert ("--headless=new" in args) is flags
    assert ("--mute-audio" in args) is flags
    assert args[-1] == "about:blank"


@pytest.mark.parametrize(
    ("process", "calls"),
    [
        (_Process(exited=True), []),
        (_Process(), ["terminate", "wait"]),
        (_Process(stubborn=True), ["terminate", "wait", "kill", "wait"]),
        (_Process(terminate_error=PermissionError("gone")), ["terminate", "kill", "wait"]),
    ],
)
def test_stop_process_state_stops_with_matching_calls(process: _Process, calls: list[str]) -> None:
    _stop_process(cast("subprocess.Popen[bytes]", process), grace_s=0.0)

    assert process.calls == calls
    assert process.returncode is not None


def test_stop_process_unkillable_chrome_warns_without_raising() -> None:
    process = _Process(stubborn=True, unkillable=True)
    captured: list[str] = []
    handler_id: int = loguru_logger.add(lambda message: captured.append(str(message)), level="WARNING")

    try:
        _stop_process(cast("subprocess.Popen[bytes]", process), grace_s=0.0)
    finally:
        loguru_logger.remove(handler_id)

    assert process.calls == ["terminate", "wait", "kill", "wait"]
    assert any("could not be stopped" in message for message in captured)
