"""Process-wide host of the ElevenReader Chrome: one browser per profile, a tab per recording, one account cleanup."""

from __future__ import annotations

import asyncio
import itertools
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final

from edp.cancellation import Cancellation
from edp.errors import (
    ErrorCode,
    ErrorContext,
    TtsCancelledError,
    TtsError,
    TtsProviderUnavailableError,
    TtsTimeoutError,
)
from edp.utils.logger import get_logger

from .api_backend import clean_account, load_cleanup, require_signed_in, save_cleanup
from .types import AccountCleanup

if TYPE_CHECKING:
    import concurrent.futures
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
    from pathlib import Path

    from .api_backend import ReaderPage
    from .browser import ChromeSession
    from .types import AccountSettings, DocumentTrace

__all__ = [
    "CLEANUP_WARNING",
    "ReaderAttempt",
    "ReaderHub",
    "cancelled_error",
    "finish_shielded",
    "headless_session",
    "timeout_error",
    "unless_cancelled",
    "within_deadline",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

CLEANUP_WARNING: Final[str] = (
    "ElevenReader account cleanup failed: run `edp login` to retry it, or delete from the library the last "
    "document uploaded by edp (its title is the first sentence of the text) and check the account voice"
)
"""Owner-facing warning left when account cleanup failed for good."""

_THREAD_NAME: Final[str] = "edp-elevenreader"
"""Name of the thread running the host loop."""

_SUSPECT_ERRORS: Final[tuple[type[TtsError], ...]] = (TtsCancelledError, TtsProviderUnavailableError, TtsTimeoutError)
"""Failures after which the browser is restarted once no other recording uses it."""

_HUBS: Final[dict[Path, ReaderHub]] = {}
"""Live host of every profile in the process."""

_HUBS_LOCK: Final[threading.Lock] = threading.Lock()
"""Guard of the host registry and of every host's reference count."""

type _CleanupState = tuple[AccountSettings | None, tuple[DocumentTrace, ...]]
"""Saved account restore and document traces, compared to skip unchanged writes."""


@dataclass(frozen=True, slots=True)
class ReaderAttempt:
    """One recording's tab and account state on the host loop; ``started`` lets the next recording start."""

    page: ReaderPage
    uploads: AccountCleanup
    account: AccountCleanup
    save: Callable[[], None]
    started: Callable[[], None]
    cancel: Cancellation
    entered_at: float


class ReaderHub:
    """Owner of the profile's Chrome, tabs, account cleanup and ``session.json``, on its own thread and loop."""

    def __init__(
        self, root: Path, browser_factory: Callable[[Path], ChromeSession], *, after: ReaderHub | None
    ) -> None:
        """Start the host thread; it waits for *after*, the closing host of the same profile, before loading state."""
        self._root: Path = root
        self._browser_factory: Callable[[Path], ChromeSession] = browser_factory
        self._after: ReaderHub | None = after
        self._references: int = 0
        self._closing: bool = False
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._browser: ChromeSession | None = None
        self._suspect: bool = False
        self._account: AccountCleanup = AccountCleanup()
        self._uploads: list[AccountCleanup] = []
        self._saved: _CleanupState = (None, ())
        self._start_lock: asyncio.Lock = asyncio.Lock()
        self._gate: asyncio.Condition = asyncio.Condition()
        self._active: int = 0
        self._tabs: int = 0
        self._voice: str | None = None
        self._waiting: dict[int, str] = {}
        self._tickets: Iterator[int] = itertools.count()
        self._thread: threading.Thread = threading.Thread(target=self._serve, name=_THREAD_NAME, daemon=True)
        self._thread.start()

    @classmethod
    def acquire(cls, root: Path, browser_factory: Callable[[Path], ChromeSession]) -> ReaderHub:
        """Return the live host of *root*, creating it on first use; every acquire needs one :meth:`release`."""
        with _HUBS_LOCK:
            current: ReaderHub | None = _HUBS.get(root)
            if current is not None and current.retain():
                return current
            hub: ReaderHub = cls(root, browser_factory, after=current)
            hub.retain()
            _HUBS[root] = hub
            return hub

    def retain(self) -> bool:
        """Count one more user unless the host is closing; the caller holds the registry lock."""
        if self._closing:
            return False
        self._references += 1
        return True

    async def release(self) -> None:
        """Drop one user; the last one cleans the account, stops Chrome and ends the host thread."""
        with _HUBS_LOCK:
            self._references -= 1
            if self._references:
                return
            self._closing = True
        done: concurrent.futures.Future[None] = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        done.add_done_callback(lambda _: self._loop.call_soon_threadsafe(self._loop.stop))
        await finish_shielded(asyncio.wrap_future(done))
        await asyncio.to_thread(self._thread.join)

    async def record[T](
        self,
        read: Callable[[ReaderAttempt], Awaitable[T]],
        *,
        voice_id: str,
        deadline_s: float,
        cancel: Cancellation,
    ) -> T:
        """Run *read* in its own tab on the host loop; return only after the tab and its documents are cleaned up."""
        stop: Cancellation = Cancellation()
        attempt: concurrent.futures.Future[T] = asyncio.run_coroutine_threadsafe(
            self._attempt(read, voice_id, deadline_s, stop), self._loop
        )
        return await _until_done(asyncio.wrap_future(attempt), cancel, stop)

    def _serve(self) -> None:
        after: ReaderHub | None = self._after
        self._after = None
        if after is not None:
            after.wait_closed()
        self._account = load_cleanup(self._root)
        self._saved = (self._account.restore, tuple(self._account.documents))
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.run_until_complete(self._loop.shutdown_default_executor())
            self._loop.close()
            with _HUBS_LOCK:
                if _HUBS.get(self._root) is self:
                    del _HUBS[self._root]

    def wait_closed(self) -> None:
        """Block until the host thread has ended."""
        self._thread.join()

    async def _attempt[T](
        self,
        read: Callable[[ReaderAttempt], Awaitable[T]],
        voice_id: str,
        deadline_s: float,
        cancel: Cancellation,
    ) -> T:
        await unless_cancelled(self._enter(voice_id), cancel)
        entered_at: float = time.monotonic()
        uploads: AccountCleanup = AccountCleanup()
        self._uploads.append(uploads)
        page: ReaderPage | None = None
        try:
            async with within_deadline(deadline_s), self._starting(cancel) as started:
                page = await self._open_page(cancel)
                self._tabs += 1
                await unless_cancelled(require_signed_in(page, self._root), cancel)
                if self._account.documents:
                    await finish_shielded(clean_account(page, self._account, restore=False))
                    self._save()
                return await read(
                    ReaderAttempt(page, uploads, self._account, self._save, started, cancel, entered_at),
                )
        except _SUSPECT_ERRORS:
            self._suspect = True
            raise
        finally:
            await finish_shielded(self._leave(page, uploads))

    async def _enter(self, voice_id: str) -> None:
        ticket: int = next(self._tickets)
        async with self._gate:
            self._waiting[ticket] = voice_id
            try:
                if not self._may_enter(ticket, voice_id):
                    logger.info("ElevenReader recording waits for another voice to finish", active=self._active)
                    await self._gate.wait_for(partial(self._may_enter, ticket, voice_id))
            finally:
                del self._waiting[ticket]
                self._gate.notify_all()
            self._active += 1
            self._voice = voice_id

    def _may_enter(self, ticket: int, voice_id: str) -> bool:
        if any(voice != voice_id for earlier, voice in self._waiting.items() if earlier < ticket):
            return False
        return not self._active or self._voice == voice_id

    async def _exit(self) -> None:
        async with self._gate:
            self._active -= 1
            if not self._active:
                self._voice = None
            self._gate.notify_all()

    @asynccontextmanager
    async def _starting(self, cancel: Cancellation) -> AsyncIterator[Callable[[], None]]:
        await _take(self._start_lock, cancel)
        holding: bool = True

        def started() -> None:
            nonlocal holding
            if holding:
                holding = False
                self._start_lock.release()

        try:
            yield started
        finally:
            started()

    async def _open_page(self, cancel: Cancellation) -> ReaderPage:
        browser: ChromeSession | None = self._browser
        if browser is None or not browser.alive or (self._suspect and self._active == 1):
            await self._close_browser()
            browser = self._browser_factory(self._root)
            self._browser = browser
            self._suspect = False
            await unless_cancelled(browser.start(), cancel)
        return await unless_cancelled(browser.new_page(), cancel)

    async def _leave(self, page: ReaderPage | None, uploads: AccountCleanup) -> None:
        if page is not None:
            self._tabs -= 1
        try:
            if page is not None:
                await self._clean_up(page, uploads)
        finally:
            self._uploads.remove(uploads)
            self._account.documents.extend(uploads.documents)
            self._save()
            try:
                if page is not None:
                    await page.close()
            finally:
                await self._exit()

    async def _clean_up(self, page: ReaderPage, uploads: AccountCleanup) -> None:
        page.unwatch_stream()
        await clean_account(page, uploads, restore=False)
        if self._tabs or not self._account.pending:
            return
        async with self._start_lock:
            if not self._tabs:
                await clean_account(page, self._account, restore=True)

    async def _shutdown(self) -> None:
        browser: ChromeSession | None = self._browser
        try:
            if self._account.pending and browser is not None and browser.alive:
                await finish_shielded(self._clean_in_new_tab(browser))
        finally:
            self._save()
            if self._account.pending:
                logger.warning(CLEANUP_WARNING, steps=list(self._account.pending))
            await self._close_browser()

    async def _clean_in_new_tab(self, browser: ChromeSession) -> None:
        try:
            page: ReaderPage = await browser.new_page()
        except TtsError as error:
            logger.warning("ElevenReader cleanup tab could not open", code=error.context.code.value)
            return
        try:
            await page.open_library()
            await clean_account(page, self._account, restore=True)
        finally:
            await page.close()

    def _save(self) -> None:
        documents: tuple[DocumentTrace, ...] = (
            *self._account.documents,
            *(trace for uploads in self._uploads for trace in uploads.documents),
        )
        state: _CleanupState = (self._account.restore, documents)
        owed: AccountCleanup = AccountCleanup(restore=self._account.restore, documents=list(documents))
        if state != self._saved and save_cleanup(self._root, owed):
            self._saved = state

    async def _close_browser(self) -> None:
        browser: ChromeSession | None = self._browser
        self._browser = None
        if browser is not None:
            await browser.close()


def headless_session(root: Path) -> ChromeSession:
    """Return a headless Chrome session on the profile under *root*, loading Playwright only now."""
    from .browser import ChromeSession  # noqa: PLC0415 - keeps Playwright out of the package import

    return ChromeSession(root, headless=True)


async def unless_cancelled[T](work: Awaitable[T], cancel: Cancellation) -> T:
    """Await *work*, abandoning it with TtsCancelledError as soon as *cancel* fires."""
    task: asyncio.Future[T] = asyncio.ensure_future(work)
    waiter: asyncio.Future[None] = asyncio.ensure_future(cancel.wait())
    try:
        done, _ = await asyncio.wait((task, waiter), return_when=asyncio.FIRST_COMPLETED)
    except BaseException:
        task.cancel()
        waiter.cancel()
        raise
    waiter.cancel()
    if task in done:
        return task.result()
    task.cancel()
    await asyncio.wait((task,))
    raise cancelled_error()


@asynccontextmanager
async def within_deadline(deadline_s: float) -> AsyncIterator[None]:
    """Turn the expiry of *deadline_s* into TtsTimeoutError."""
    limit: asyncio.Timeout = asyncio.timeout(deadline_s)
    try:
        async with limit:
            yield
    except TimeoutError:
        if not limit.expired():
            raise
        reason: str = "ElevenReader document exceeded its deadline"
        raise timeout_error(reason) from None


async def finish_shielded(work: Awaitable[None]) -> None:
    """Run *work* to its end even when the caller is cancelled, then pass the cancellation on."""
    task: asyncio.Future[None] = asyncio.ensure_future(work)
    interrupted: bool = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            interrupted = True
    if interrupted:
        raise asyncio.CancelledError
    task.result()


def cancelled_error() -> TtsCancelledError:
    """Return the error of a cancelled ElevenReader attempt."""
    return TtsCancelledError("ElevenReader synthesis cancelled")


def timeout_error(message: str) -> TtsTimeoutError:
    """Return the retryable timeout error with *message*."""
    context: ErrorContext = ErrorContext(code=ErrorCode.TTS_TIMEOUT, message=message)
    return TtsTimeoutError(context=context)


async def _take(lock: asyncio.Lock, cancel: Cancellation) -> None:
    taking: asyncio.Future[bool] = asyncio.ensure_future(lock.acquire())
    try:
        await unless_cancelled(taking, cancel)
    except BaseException:
        if taking.done() and not taking.cancelled() and taking.exception() is None:
            lock.release()
        raise


async def _until_done[T](work: asyncio.Future[T], cancel: Cancellation, stop: Cancellation) -> T:
    watcher: asyncio.Future[None] = asyncio.ensure_future(cancel.wait())
    watcher.add_done_callback(partial(_relay, stop))
    interrupted: bool = False
    try:
        while not work.done():
            try:
                await asyncio.wait((work,))
            except asyncio.CancelledError:
                interrupted = True
                stop.cancel()
    finally:
        watcher.cancel()
    if interrupted:
        raise asyncio.CancelledError
    return work.result()


def _relay(stop: Cancellation, watcher: asyncio.Future[None]) -> None:
    if not watcher.cancelled():
        stop.cancel()
