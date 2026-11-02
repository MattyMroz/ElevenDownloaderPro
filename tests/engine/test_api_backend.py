from __future__ import annotations

import asyncio
import io
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast

import pytest
from fakes import (
    FIRST_LINE,
    FRONCZEWSKI_ID,
    LIBRARY_PAGE_URL,
    READ_ID,
    READS_URL,
    SIGN_IN_BUTTON,
    TOKEN,
    FakeFrame,
    FakePage,
    FakePlaywrightPage,
    FakeRequest,
    FakeResponse,
    FakeSite,
    FakeSocket,
    document_trace,
    library_read,
)
from loguru import logger as loguru_logger
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from edp.engine import SignInOutcome, api_backend, read_session, sign_in
from edp.engine import browser as browser_module
from edp.engine.api_backend import (
    ReaderPage,
    clean_account,
    document_titles,
    load_cleanup,
    map_http_status,
    map_playwright_error,
    save_cleanup,
    write_session,
)
from edp.engine.browser import ChromeBusyError, ChromeMissingError
from edp.engine.recorder import StreamRecorder
from edp.engine.types import (
    AccountCleanup,
    AccountSettings,
    DocumentTrace,
    LibraryState,
    PlayerState,
    UploadedRead,
)
from edp.errors import (
    ErrorCode,
    FatalError,
    TransientError,
    TtsAuthError,
    TtsError,
    TtsProviderUnavailableError,
    TtsQuotaError,
    TtsRateLimitError,
    TtsTimeoutError,
)

if TYPE_CHECKING:
    from playwright.async_api import Page

pytestmark = pytest.mark.unit

PREVIOUS = AccountSettings(voice_id="previous-voice", speed=1.5)


@pytest.mark.parametrize(
    ("status", "error_type", "code"),
    [
        (401, TtsAuthError, ErrorCode.TTS_AUTH_FAILED),
        (403, TtsAuthError, ErrorCode.TTS_AUTH_FAILED),
        (402, TtsQuotaError, ErrorCode.TTS_QUOTA_EXHAUSTED),
        (429, TtsRateLimitError, ErrorCode.TTS_RATE_LIMITED),
        (500, TtsProviderUnavailableError, ErrorCode.TTS_ENGINE_UNAVAILABLE),
        (503, TtsProviderUnavailableError, ErrorCode.TTS_ENGINE_UNAVAILABLE),
    ],
)
def test_map_http_status_known_status_returns_typed_error(
    status: int,
    error_type: type[TtsError],
    code: ErrorCode,
) -> None:
    error: TtsError = map_http_status(status, action="upload")

    assert type(error) is error_type
    assert error.context.code is code
    assert error.context.details == {"action": "upload", "status": status}


@pytest.mark.parametrize("status", [401, 402, 403])
def test_map_http_status_permanent_failure_is_fatal_with_suggestion(status: int) -> None:
    error: TtsError = map_http_status(status, action="read_account")

    assert isinstance(error, FatalError)
    assert error.context.suggestion


def test_map_http_status_unauthorized_suggests_edp_login() -> None:
    assert "edp login" in map_http_status(401, action="upload").context.suggestion


def test_map_http_status_forbidden_mentions_blocked_account() -> None:
    assert "blocked" in map_http_status(403, action="upload").context.suggestion


@pytest.mark.parametrize(
    ("header", "expected"), [("42", 42.0), ("1.5", 1.5), ("soon", None), ("-3", None), (None, None)]
)
def test_map_http_status_rate_limit_reads_retry_after(header: str | None, expected: float | None) -> None:
    error: TtsError = map_http_status(429, action="upload", retry_after=header)

    assert isinstance(error, TtsRateLimitError)
    assert error.retry_after_s == expected


def test_map_http_status_server_error_is_transient_with_retry_delay() -> None:
    error: TtsError = map_http_status(502, action="delete_read")

    assert isinstance(error, TransientError)
    assert isinstance(error, TtsProviderUnavailableError)
    assert error.retry_after_s == 60.0


def test_map_playwright_error_timeout_returns_tts_timeout() -> None:
    error: TtsError = map_playwright_error(PlaywrightTimeoutError("Timeout 1000ms exceeded"), action="open_document")

    assert isinstance(error, TtsTimeoutError)
    assert error.context.details == {"action": "open_document"}


def test_map_playwright_error_browser_failure_returns_unavailable_without_original_text() -> None:
    error: TtsError = map_playwright_error(PlaywrightError("Target closed wss://secret"), action="upload")

    assert isinstance(error, TtsProviderUnavailableError)
    assert "secret" not in str(error)
    assert error.retry_after_s == 60.0


class _ReadyLaterPage(FakePage):
    async def library_ready(self) -> bool:
        return True


class _SignInSession:
    instances: ClassVar[list[_SignInSession]] = []
    failure: ClassVar[TtsError | None] = None
    site: ClassVar[FakeSite] = FakeSite()
    page_type: ClassVar[type[FakePage]] = FakePage

    def __init__(self, root: Path, *, headless: bool) -> None:
        self.root: Path = root
        self.headless: bool = headless
        self.closed: bool = False
        _SignInSession.instances.append(self)

    async def start(self) -> None:
        if _SignInSession.failure is not None:
            raise _SignInSession.failure

    async def new_page(self) -> FakePage:
        return _SignInSession.page_type(_SignInSession.site)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_chrome(monkeypatch: pytest.MonkeyPatch) -> type[_SignInSession]:
    monkeypatch.setattr(browser_module, "ChromeSession", _SignInSession)
    monkeypatch.setattr(api_backend, "_SIGN_IN_POLL_S", 0.001)
    monkeypatch.setattr(_SignInSession, "instances", [])
    monkeypatch.setattr(_SignInSession, "failure", None)
    monkeypatch.setattr(_SignInSession, "site", FakeSite())
    monkeypatch.setattr(_SignInSession, "page_type", FakePage)
    return _SignInSession


def test_sign_in_ready_library_returns_signed_in_and_records_session(
    tmp_path: Path,
    fake_chrome: type[_SignInSession],
) -> None:
    outcome: SignInOutcome = asyncio.run(sign_in(tmp_path))

    assert outcome is SignInOutcome.SIGNED_IN
    record = read_session(tmp_path)
    assert record is not None
    assert record.signed_in
    assert not fake_chrome.instances[0].headless
    assert fake_chrome.instances[0].closed


def test_sign_in_library_appearing_later_returns_signed_in(tmp_path: Path, fake_chrome: type[_SignInSession]) -> None:
    fake_chrome.site = FakeSite(library=LibraryState.SIGNED_OUT)
    fake_chrome.page_type = _ReadyLaterPage

    assert asyncio.run(sign_in(tmp_path, timeout_s=5.0)) is SignInOutcome.SIGNED_IN


def test_sign_in_without_sign_in_before_deadline_returns_signed_out(
    tmp_path: Path,
    fake_chrome: type[_SignInSession],
) -> None:
    fake_chrome.site = FakeSite(library=LibraryState.SIGNED_OUT)

    outcome: SignInOutcome = asyncio.run(sign_in(tmp_path, timeout_s=0.02))

    assert outcome is SignInOutcome.SIGNED_OUT
    record = read_session(tmp_path)
    assert record is not None
    assert not record.signed_in
    assert fake_chrome.instances[0].closed


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (ChromeBusyError("busy"), SignInOutcome.BUSY),
        (ChromeMissingError("missing"), SignInOutcome.NO_CHROME),
        (TtsProviderUnavailableError("down"), SignInOutcome.FAILED),
    ],
)
def test_sign_in_browser_failure_returns_matching_outcome(
    tmp_path: Path,
    fake_chrome: type[_SignInSession],
    failure: TtsError,
    expected: SignInOutcome,
) -> None:
    fake_chrome.failure = failure

    assert asyncio.run(sign_in(tmp_path)) is expected
    assert read_session(tmp_path) is None


def test_session_record_round_trips_without_secrets(tmp_path: Path) -> None:
    write_session(tmp_path, signed_in=True)

    saved: dict[str, object] = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))

    assert set(saved) == {"checked_at", "documents", "restore", "signed_in"}
    assert saved["signed_in"] is True
    assert saved["documents"] == []
    assert saved["restore"] is None


@pytest.mark.parametrize(
    "content",
    [
        "{broken",
        '{"signed_in": true, "checked_at": "2026-10-30T10:00:00+00:00"}',
        '{"signed_in": true, "checked_at": "2026-10-30T10:00:00+00:00", "restore": null, "delete_document": false}',
        '{"signed_in": true, "checked_at": "2026-10-30T10:00:00+00:00", "documents": [{"pressed_at": 1.0}]}',
        '{"signed_in": true, "checked_at": "2026-10-30T10:00:00+00:00", "documents": '
        '[{"pressed_at": 1.0, "listed_by": 2.0, "titles": [], "read_id": 7}]}',
        "[1]",
    ],
)
def test_read_session_corrupt_file_returns_none(tmp_path: Path, content: str) -> None:
    (tmp_path / "session.json").write_text(content, encoding="utf-8")

    assert read_session(tmp_path) is None


def test_save_cleanup_owed_steps_are_saved_with_read_id_without_plain_text(tmp_path: Path) -> None:
    write_session(tmp_path, signed_in=False)
    cleanup = AccountCleanup(restore=PREVIOUS, documents=[document_trace(read_id=READ_ID)])

    assert save_cleanup(tmp_path, cleanup)

    record = read_session(tmp_path)
    assert record is not None
    assert not record.signed_in
    assert record.restore == PREVIOUS
    assert record.delete_document
    assert record.cleanup_pending
    assert record.documents == tuple(cleanup.documents)
    assert "Pierwsza" not in (tmp_path / "session.json").read_text(encoding="utf-8")


def test_write_session_saved_cleanup_is_kept(tmp_path: Path) -> None:
    save_cleanup(tmp_path, AccountCleanup(documents=[document_trace()]))

    write_session(tmp_path, signed_in=True)

    record = read_session(tmp_path)
    assert record is not None
    assert record.signed_in
    assert record.delete_document
    assert record.restore is None


def test_save_cleanup_unwritable_root_returns_false(tmp_path: Path) -> None:
    blocker: Path = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")

    assert not save_cleanup(blocker, AccountCleanup(documents=[document_trace()]))


def test_load_cleanup_saved_documents_keep_their_traces_and_read_ids(tmp_path: Path) -> None:
    known = document_trace(read_id=READ_ID)
    unanswered = document_trace(listed_in_s=100.0)
    save_cleanup(tmp_path, AccountCleanup(restore=PREVIOUS, documents=[known, unanswered]))

    cleanup = load_cleanup(tmp_path)

    assert cleanup.restore == PREVIOUS
    assert cleanup.documents == [known, unanswered]
    assert cleanup.pending == ("restore_settings", "delete_read", "delete_orphan")


def test_load_cleanup_upload_still_in_flight_stays_pending_after_restart(tmp_path: Path) -> None:
    save_cleanup(tmp_path, AccountCleanup(documents=[document_trace(listed_in_s=100.0)]))
    site = FakeSite()
    cleanup = load_cleanup(tmp_path)

    asyncio.run(clean_account(cast("ReaderPage", _signed_in_page(site)), cleanup, restore=True))

    assert cleanup.pending == ("delete_orphan",)
    assert "list_reads" in site.events
    assert site.deleted == []


def test_failed_delete_of_known_read_is_retried_by_id_after_restart(tmp_path: Path) -> None:
    first = FakeSite(reads=[READ_ID], failing={"delete_read"})
    cleanup = AccountCleanup(documents=[document_trace(read_id=READ_ID)])
    asyncio.run(clean_account(cast("ReaderPage", _signed_in_page(first)), cleanup, restore=True))
    save_cleanup(tmp_path, cleanup)
    second = FakeSite(reads=[READ_ID])
    restarted = load_cleanup(tmp_path)

    asyncio.run(clean_account(cast("ReaderPage", _signed_in_page(second)), restarted, restore=True))

    assert restarted.pending == ()
    assert second.deleted == [f"{READS_URL}/{READ_ID}"]
    assert "list_reads" not in second.events


def test_load_cleanup_without_session_returns_nothing_pending(tmp_path: Path) -> None:
    assert load_cleanup(tmp_path).pending == ()


def _signed_in_page(site: FakeSite) -> FakePage:
    page = FakePage(site)
    asyncio.run(page.open_library())
    return page


def test_clean_account_without_token_keeps_steps_and_warns(tmp_path: Path) -> None:
    cleanup = AccountCleanup(restore=PREVIOUS, documents=[document_trace(read_id=READ_ID)])
    captured: list[str] = []
    handler_id: int = loguru_logger.add(lambda message: captured.append(str(message)), level="WARNING")

    try:
        asyncio.run(clean_account(cast("ReaderPage", FakePage(FakeSite())), cleanup, restore=True))
    finally:
        loguru_logger.remove(handler_id)

    assert cleanup.pending == ("restore_settings", "delete_read")
    assert any("no account token" in message for message in captured)


def test_clean_account_without_restore_deletes_documents_and_keeps_owed_settings() -> None:
    site = FakeSite(reads=[READ_ID], account={"default_voice_id": FRONCZEWSKI_ID, "playback_speed_rate": 1.0})
    cleanup = AccountCleanup(restore=PREVIOUS, documents=[document_trace(read_id=READ_ID)])

    asyncio.run(clean_account(cast("ReaderPage", _signed_in_page(site)), cleanup, restore=False))

    assert cleanup.pending == ("restore_settings",)
    assert site.deleted == [f"{READS_URL}/{READ_ID}"]
    assert site.account["default_voice_id"] == FRONCZEWSKI_ID
    assert "restore_account" not in site.events


def test_clean_account_orphan_found_by_window_and_title_is_deleted() -> None:
    site = FakeSite(reads=[READ_ID])
    cleanup = AccountCleanup(documents=[document_trace(listed_in_s=100.0)])

    asyncio.run(clean_account(cast("ReaderPage", _signed_in_page(site)), cleanup, restore=True))

    assert cleanup.pending == ()
    assert site.deleted == [f"{READS_URL}/{READ_ID}"]


def test_clean_account_orphan_missing_before_visible_time_stays_pending() -> None:
    site = FakeSite()
    cleanup = AccountCleanup(documents=[document_trace(listed_in_s=100.0)])

    asyncio.run(clean_account(cast("ReaderPage", _signed_in_page(site)), cleanup, restore=True))

    assert cleanup.pending == ("delete_orphan",)
    assert site.deleted == []


def test_clean_account_orphan_missing_after_visible_time_is_settled() -> None:
    site = FakeSite()
    cleanup = AccountCleanup(documents=[document_trace()])

    asyncio.run(clean_account(cast("ReaderPage", _signed_in_page(site)), cleanup, restore=True))

    assert cleanup.pending == ()
    assert "list_reads" in site.events


class _BrokenAccountPage(FakePage):
    async def get_json(self, url: str, token: str, *, action: str) -> dict[str, object]:
        if action == "read_account":
            message: str = "boom"
            raise RuntimeError(message)
        return await super().get_json(url, token, action=action)


def test_clean_account_step_breaking_unexpectedly_keeps_it_and_runs_next_step() -> None:
    site = FakeSite(reads=[READ_ID])
    page = _BrokenAccountPage(site)
    asyncio.run(page.open_library())
    cleanup = AccountCleanup(restore=PREVIOUS, documents=[document_trace(read_id=READ_ID)])

    asyncio.run(clean_account(cast("ReaderPage", page), cleanup, restore=True))

    assert cleanup.pending == ("restore_settings",)
    assert site.deleted == [f"{READS_URL}/{READ_ID}"]


def test_sign_in_signed_in_runs_saved_cleanup(tmp_path: Path, fake_chrome: type[_SignInSession]) -> None:
    save_cleanup(tmp_path, AccountCleanup(restore=PREVIOUS, documents=[document_trace(read_id=READ_ID)]))
    fake_chrome.site = FakeSite(reads=[READ_ID], account={"default_voice_id": FRONCZEWSKI_ID})

    assert asyncio.run(sign_in(tmp_path)) is SignInOutcome.SIGNED_IN

    record = read_session(tmp_path)
    assert record is not None
    assert not record.cleanup_pending
    assert fake_chrome.site.deleted == [f"{READS_URL}/{READ_ID}"]
    assert fake_chrome.site.account == {"default_voice_id": "previous-voice", "playback_speed_rate": 1.5}


def test_sign_in_cleanup_failing_keeps_it_saved(tmp_path: Path, fake_chrome: type[_SignInSession]) -> None:
    save_cleanup(tmp_path, AccountCleanup(documents=[document_trace(read_id=READ_ID)]))
    fake_chrome.site = FakeSite(reads=[READ_ID], failing={"delete_read"})

    assert asyncio.run(sign_in(tmp_path)) is SignInOutcome.SIGNED_IN

    record = read_session(tmp_path)
    assert record is not None
    assert record.signed_in
    assert record.delete_document


def _reader(page: FakePlaywrightPage) -> ReaderPage:
    return ReaderPage(cast("Page", page))


def _upload(page: FakePlaywrightPage, tmp_path: Path, cleanup: AccountCleanup) -> tuple[UploadedRead, list[str]]:
    clicks_at_save: list[str] = []
    document: Path = tmp_path / "edp.txt"
    document.write_text("Tekst.\n", encoding="utf-8")
    uploaded = asyncio.run(_reader(page).upload(document, cleanup, lambda: clicks_at_save.extend(page.clicks)))
    return uploaded, clicks_at_save


def test_reader_page_upload_reply_returns_read_and_registers_it_after_saving(tmp_path: Path) -> None:
    page = FakePlaywrightPage()
    page.add_reply = FakeResponse(200, {"read_id": READ_ID, "char_count": 42})
    cleanup = AccountCleanup()
    started: float = time.time()

    uploaded, clicks_at_save = _upload(page, tmp_path, cleanup)

    assert (uploaded.read_id, uploaded.char_count, uploaded.token) == (READ_ID, 42, TOKEN)
    [trace] = cleanup.documents
    assert trace.read_id == READ_ID
    assert trace.titles == document_titles("Tekst.\n")
    assert started <= trace.pressed_at <= trace.listed_by <= time.time()
    assert clicks_at_save == ["Import"]
    assert page.clicks == ["Import", "Upload"]
    assert page.files == [tmp_path / "edp.txt"]


def test_reader_page_upload_reply_keeps_earlier_orphan_pending(tmp_path: Path) -> None:
    page = FakePlaywrightPage()
    page.add_reply = FakeResponse(200, {"read_id": READ_ID, "char_count": 42})
    earlier = document_trace(listed_in_s=100.0)
    cleanup = AccountCleanup(documents=[earlier])

    _upload(page, tmp_path, cleanup)

    assert cleanup.documents[0] == earlier
    assert [trace.read_id for trace in cleanup.documents] == [None, READ_ID]
    assert cleanup.pending == ("delete_read", "delete_orphan")


@pytest.mark.parametrize(
    ("body", "authorization"),
    [
        ({"read_id": READ_ID}, TOKEN),
        ({"read_id": READ_ID, "char_count": 0}, TOKEN),
        ({"read_id": READ_ID, "char_count": 5}, ""),
    ],
)
def test_reader_page_upload_invalid_reply_raises_after_registering_read(
    tmp_path: Path,
    body: dict[str, object],
    authorization: str,
) -> None:
    page = FakePlaywrightPage()
    page.add_reply = FakeResponse(200, body, authorization=authorization)
    cleanup = AccountCleanup()

    with pytest.raises(TtsProviderUnavailableError):
        _upload(page, tmp_path, cleanup)

    assert [trace.read_id for trace in cleanup.documents] == [READ_ID]


@pytest.mark.parametrize("reply", [FakeResponse(200, text="{oops"), FakeResponse(200, {"char_count": 5})])
def test_reader_page_upload_reply_without_read_id_raises_and_keeps_orphan(tmp_path: Path, reply: FakeResponse) -> None:
    page = FakePlaywrightPage()
    page.add_reply = reply
    cleanup = AccountCleanup()

    with pytest.raises(TtsProviderUnavailableError) as error:
        _upload(page, tmp_path, cleanup)

    assert error.value.__cause__ is None
    [trace] = cleanup.documents
    assert trace.read_id is None
    assert trace.listed_by <= time.time()
    assert cleanup.pending == ("delete_orphan",)


def test_reader_page_upload_refused_reply_raises_typed_error_without_orphan(tmp_path: Path) -> None:
    page = FakePlaywrightPage()
    page.add_reply = FakeResponse(402, {})
    cleanup = AccountCleanup()

    with pytest.raises(TtsQuotaError):
        _upload(page, tmp_path, cleanup)

    assert cleanup.pending == ()


@pytest.mark.parametrize(
    ("reply", "error_type"),
    [
        (FakeResponse(200, text="not json"), TtsProviderUnavailableError),
        (FakeResponse(200, [1, 2]), TtsProviderUnavailableError),
        (FakeResponse(401, {}), TtsAuthError),
    ],
)
def test_reader_page_get_json_bad_reply_raises_typed_error(reply: FakeResponse, error_type: type[TtsError]) -> None:
    page = FakePlaywrightPage()
    page.replies[("GET", READS_URL)] = reply

    with pytest.raises(error_type) as error:
        asyncio.run(_reader(page).get_json(READS_URL, TOKEN, action="list_reads"))

    assert error.value.__cause__ is None


def test_reader_page_get_json_object_returns_it() -> None:
    page = FakePlaywrightPage()
    page.replies[("GET", READS_URL)] = FakeResponse(200, {"reads": []})

    assert asyncio.run(_reader(page).get_json(READS_URL, TOKEN, action="list_reads")) == {"reads": []}


@pytest.mark.parametrize("status", [200, 404])
def test_reader_page_delete_done_or_gone_succeeds(status: int) -> None:
    page = FakePlaywrightPage()
    page.replies[("DELETE", f"{READS_URL}/{READ_ID}")] = FakeResponse(status, {})

    asyncio.run(_reader(page).delete(f"{READS_URL}/{READ_ID}", TOKEN, action="delete_read"))

    assert page.calls == [("DELETE", f"{READS_URL}/{READ_ID}")]


def test_reader_page_delete_server_error_raises_unavailable() -> None:
    page = FakePlaywrightPage()
    page.replies[("DELETE", f"{READS_URL}/{READ_ID}")] = FakeResponse(503, {})

    with pytest.raises(TtsProviderUnavailableError):
        asyncio.run(_reader(page).delete(f"{READS_URL}/{READ_ID}", TOKEN, action="delete_read"))


def test_reader_page_post_json_sends_data_and_maps_refusal() -> None:
    page = FakePlaywrightPage()
    page.replies[("POST", "https://api.elevenlabs.io/v1/reader/user_config")] = FakeResponse(403, {})

    with pytest.raises(TtsAuthError):
        asyncio.run(
            _reader(page).post_json(
                "https://api.elevenlabs.io/v1/reader/user_config", TOKEN, {"theme": "dark"}, action="set_account"
            )
        )

    assert page.posted == [{"theme": "dark"}]


def test_clean_account_listing_without_reads_keeps_orphan() -> None:
    page = FakePlaywrightPage()
    page.replies[("GET", READS_URL)] = FakeResponse(200, {"items": []})
    reader = _reader(page)
    page.emit("request", FakeRequest(READS_URL, "GET", {"authorization": TOKEN}))
    cleanup = AccountCleanup(documents=[document_trace()])

    asyncio.run(clean_account(reader, cleanup, restore=True))

    assert cleanup.pending == ("delete_orphan",)


def _listed_cleanup(reads: list[object], trace: DocumentTrace) -> tuple[AccountCleanup, list[str], list[str]]:
    page = FakePlaywrightPage()
    page.replies[("GET", READS_URL)] = FakeResponse(200, {"reads": reads, "has_more": True, "next_cursor": "c"})
    reader = _reader(page)
    page.emit("request", FakeRequest(READS_URL, "GET", {"authorization": TOKEN}))
    cleanup = AccountCleanup(documents=[trace])
    warnings: list[str] = []
    handler_id: int = loguru_logger.add(
        lambda message: warnings.append(str(message)), format="{message} {extra}", level="WARNING"
    )
    try:
        asyncio.run(clean_account(reader, cleanup, restore=True))
    finally:
        loguru_logger.remove(handler_id)
    deleted: list[str] = [url for method, url in page.calls if method == "DELETE"]
    return cleanup, deleted, warnings


def test_clean_account_real_listing_deletes_only_upload_in_window_with_its_title() -> None:
    now: float = time.time()
    reads: list[object] = [
        library_read("u:book", "Książka", added_at=now),
        library_read(READ_ID, added_at=now),
        library_read("u:old", added_at=now - 3600.0),
        library_read("u:web", added_at=now, imported=False),
        library_read("u:pdf", added_at=now, file_type="application/pdf"),
        "junk",
    ]

    cleanup, deleted, warnings = _listed_cleanup(reads, document_trace(f"{FIRST_LINE}\n\n…\n\nDruga kwestia.\n"))

    assert cleanup.pending == ()
    assert deleted == [f"{READS_URL}/{READ_ID}"]
    assert warnings == []


def test_clean_account_several_matching_uploads_delete_nothing_and_warn() -> None:
    reads: list[object] = [library_read(READ_ID), library_read("u:twin")]

    cleanup, deleted, warnings = _listed_cleanup(reads, document_trace())

    assert cleanup.pending == ("delete_orphan",)
    assert deleted == []
    assert any("cannot tell its upload" in message for message in warnings)


def test_clean_account_window_import_of_other_title_is_kept_and_settles_with_warning() -> None:
    cleanup, deleted, warnings = _listed_cleanup([library_read("u:book", "Książka")], document_trace())

    assert cleanup.pending == ()
    assert deleted == []
    assert any("may remain there" in message and "'imports': 1" in message for message in warnings)


def test_clean_account_unanswered_upload_missing_after_visible_time_settles_with_warning() -> None:
    old = library_read("u:old", added_at=time.time() - 86_400.0)

    cleanup, deleted, warnings = _listed_cleanup([old], document_trace())

    assert cleanup.pending == ()
    assert deleted == []
    assert any("may remain there" in message and "'imports': 0" in message for message in warnings)
    assert all(FIRST_LINE not in message for message in warnings)


@pytest.mark.parametrize(
    ("title", "deleted"),
    [
        ("Hej!", True),
        ("Hej! Co tam?", True),
        ("Hej!  Co\ntam? …", True),
        ("Co tam?", False),
        ("Hej! Co tam? … Dalej. Więcej", False),
    ],
)
def test_clean_account_title_matches_leading_words_of_document(title: str, *, deleted: bool) -> None:
    trace = document_trace("Hej! Co tam?\n\n…\n\nDalej.\n")

    _, calls, _ = _listed_cleanup([library_read(READ_ID, title)], trace)

    assert (calls == [f"{READS_URL}/{READ_ID}"]) is deleted


def test_reader_page_token_is_taken_only_from_api_requests() -> None:
    page = FakePlaywrightPage()
    reader = _reader(page)

    page.emit("request", FakeRequest("https://elevenreader.io/app.js", "GET", {"authorization": "page"}))
    assert reader.token is None
    page.emit("request", FakeRequest(READS_URL, "GET", {"authorization": TOKEN}))

    assert reader.token == TOKEN
    assert page.timeout_ms == 120_000


def _library_page(scenario: str) -> FakePlaywrightPage:
    page = FakePlaywrightPage(visible=())
    if scenario == "goto_fails":
        page.goto_error = PlaywrightError("net::ERR")
    elif scenario == "server_error":
        page.goto_reply = FakeResponse(503)
    elif scenario == "import":
        page.visible = {"Import"}
    elif scenario == "sign_in_button":
        page.visible = {SIGN_IN_BUTTON}
    elif scenario == "sign_in_address":
        page.url = "https://elevenreader.io/sign-in"
    elif scenario == "sign_up_address":
        page.url = "https://elevenreader.io/reader/sign-up"
    elif scenario == "browser_broke":
        page.wait_error = PlaywrightError("Target closed")
    return page


@pytest.mark.parametrize(
    ("scenario", "state"),
    [
        ("goto_fails", LibraryState.UNAVAILABLE),
        ("server_error", LibraryState.UNAVAILABLE),
        ("import", LibraryState.READY),
        ("sign_in_button", LibraryState.SIGNED_OUT),
        ("sign_in_address", LibraryState.SIGNED_OUT),
        ("sign_up_address", LibraryState.SIGNED_OUT),
        ("nothing", LibraryState.UNAVAILABLE),
        ("browser_broke", LibraryState.UNAVAILABLE),
    ],
)
def test_reader_page_open_library_scenario_returns_state(scenario: str, state: LibraryState) -> None:
    page = _library_page(scenario)

    assert asyncio.run(_reader(page).open_library()) is state


def test_reader_page_check_page_speed_injects_missing_and_retunes_off_speed_frames() -> None:
    missing = FakeFrame(None)
    slow = FakeFrame({"target": 64.0, "rates": [1.0]})
    retargeted = FakeFrame({"target": 1.0, "rates": []})
    steady = FakeFrame({"target": 64.0, "rates": [64.0]})
    broken = FakeFrame(error=PlaywrightError("detached"))
    page = FakePlaywrightPage()
    page.frames = [missing, slow, retargeted, steady, broken]

    asyncio.run(_reader(page).check_page_speed(64.0))

    assert "window.__edpSpeed = 64.0" in missing.scripts[-1]
    assert slow.scripts[-1] == "window.__edpSetSpeed(64.0)"
    assert retargeted.scripts[-1] == "window.__edpSetSpeed(64.0)"
    assert len(steady.scripts) == 1


def test_reader_page_player_state_reads_slider_or_zero() -> None:
    page = FakePlaywrightPage()
    reader = _reader(page)

    page.player = {"value": 10, "max": 20.5}
    assert asyncio.run(reader.player_state()) == PlayerState(value=10.0, length=20.5)
    page.player = None
    assert asyncio.run(reader.player_state()) == PlayerState(value=0.0, length=0.0)


def test_reader_page_watch_stream_feeds_only_read_stream_until_unwatched() -> None:
    page = FakePlaywrightPage()
    reader = _reader(page)
    recorder = StreamRecorder(io.BytesIO())
    urls: list[str] = []
    stream = FakeSocket(f"wss://api.elevenlabs.io/v1/reader/reads/stream/v2/{READ_ID}?voice_id={FRONCZEWSKI_ID}")
    other = FakeSocket("wss://api.elevenlabs.io/v1/other")

    reader.watch_stream(recorder, urls.append)
    page.emit("websocket", other)
    page.emit("websocket", stream)
    reader.unwatch_stream()

    assert urls == [stream.url]
    assert set(stream.handlers) == {"framesent", "framereceived", "close"}
    assert other.handlers == {}
    assert page.listeners["websocket"] == []


def test_reader_page_stream_open_and_close_are_logged_without_address() -> None:
    page = FakePlaywrightPage()
    reader = _reader(page)
    stream = FakeSocket(f"wss://api.elevenlabs.io/v1/reader/reads/stream/v2/{READ_ID}?voice_id={FRONCZEWSKI_ID}")
    captured: list[str] = []
    handler_id: int = loguru_logger.add(
        lambda message: captured.append(str(message)), format="{message} {extra}", level="INFO"
    )

    try:
        reader.watch_stream(StreamRecorder(io.BytesIO()), lambda url: None)
        page.emit("websocket", stream)
        stream.handlers["close"](stream.url)
    finally:
        loguru_logger.remove(handler_id)

    assert any("stream opened" in line for line in captured)
    assert any("stream closed" in line for line in captured)
    assert READ_ID not in "".join(captured)
    assert "wss://" not in "".join(captured)


@pytest.mark.parametrize(("visible", "clicks"), [(("Play",), ["Play"]), ((), [])])
def test_reader_page_press_play_clicks_only_shown_button(visible: tuple[str, ...], clicks: list[str]) -> None:
    page = FakePlaywrightPage(visible=visible)

    asyncio.run(_reader(page).press_play())

    assert page.clicks == clicks


def test_reader_page_open_document_without_play_times_out() -> None:
    page = FakePlaywrightPage(visible=())

    with pytest.raises(TtsTimeoutError):
        asyncio.run(_reader(page).open_document(READ_ID))

    assert page.calls == [("GOTO", f"{LIBRARY_PAGE_URL}/{READ_ID}")]


def test_reader_page_close_tolerates_gone_browser_and_skips_closed_tab() -> None:
    page = FakePlaywrightPage()
    page.close_error = PlaywrightError("Target closed")
    reader = _reader(page)

    asyncio.run(reader.close())
    page.closed = True
    asyncio.run(reader.close())

    assert page.close_calls == 1
