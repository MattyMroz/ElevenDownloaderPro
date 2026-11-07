from __future__ import annotations

import asyncio
import errno
import io
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from fakes import (
    ADAM_ID,
    BREAK,
    FRONCZEWSKI_ID,
    READ_ID,
    READS_URL,
    TOKEN,
    FakePage,
    FakeSession,
    FakeSite,
    audio_frame,
    document_trace,
    engine_config,
    fake_engine,
    read_id_of,
    read_url,
    stream_frames,
)
from loguru import logger as loguru_logger

from edp.cancellation import Cancellation
from edp.engine import (
    CLEANUP_WARNING,
    ElevenReaderTtsEngine,
    hub,
    read_session,
    service,
)
from edp.engine import browser as browser_module
from edp.engine.api_backend import save_cleanup
from edp.engine.recorder import StreamRecorder
from edp.engine.service import document_text, part_spans
from edp.engine.types import (
    AccountCleanup,
    AccountSettings,
    AlignmentChunk,
    DocumentPart,
    DocumentResult,
    DocumentSynthesisRequest,
    LibraryState,
)
from edp.errors import (
    TtsAuthError,
    TtsCancelledError,
    TtsClipValidationError,
    TtsError,
    TtsInputError,
    TtsProviderUnavailableError,
    TtsTimeoutError,
    TtsVoiceError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterator
    from pathlib import Path

    from loguru import Message

pytestmark = pytest.mark.unit

TEXTS = ("Pierwsza kwestia.", "Druga [kwestia].")
UNREADABLE_PARTS = ("", "   ", "…", " … ", 'Raz <break time="1s"/> dwa', "Raz <BREAK/>", "Raz <break dwa")
HUB_THREAD = "edp-elevenreader"

type EngineFor = Callable[..., ElevenReaderTtsEngine]


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "POLL_S", 0.001)
    monkeypatch.setattr(service, "END_IDLE_S", 0.0)
    monkeypatch.setattr(service, "START_TIMEOUT_S", 0.02)
    monkeypatch.setattr(service, "STALL_S", 0.1)
    monkeypatch.setattr(service, "SPEED_CHECK_S", 0.0)


@pytest.fixture
def engine_for(tmp_path: Path) -> Iterator[EngineFor]:
    created: list[ElevenReaderTtsEngine] = []

    def make(site: FakeSite, *, voice_id: str = "fronczewski") -> ElevenReaderTtsEngine:
        engine: ElevenReaderTtsEngine = fake_engine(tmp_path, site, voice_id=voice_id)
        created.append(engine)
        return engine

    yield make
    for engine in created:
        asyncio.run(engine.close())


def _run[T](work: Coroutine[object, object, T]) -> T:
    return asyncio.run(work)


def _request(
    tmp_path: Path,
    *,
    texts: tuple[str, ...] = TEXTS,
    voice_id: str = "fronczewski",
    deadline_s: float = 60.0,
    name: str = "recording",
) -> DocumentSynthesisRequest:
    return DocumentSynthesisRequest(
        request_id="episode:document:0",
        parts=tuple(DocumentPart(request_id=f"line-{index}", text=text) for index, text in enumerate(texts)),
        voice_id=voice_id,
        recording=tmp_path / "rec" / f"{name}.mp3",
        deadline_s=deadline_s,
    )


async def _record(engine: ElevenReaderTtsEngine, request: DocumentSynthesisRequest) -> DocumentResult:
    return await engine.synthesize_document(request, cancel=Cancellation())


def _assert_cleaned(site: FakeSite) -> None:
    assert site.account["default_voice_id"] == "previous-voice"
    assert site.account["playback_speed_rate"] == 1.5
    assert site.account["theme"] == "dark"
    assert site.deleted == [f"https://api.elevenlabs.io/v1/reader/reads/{READ_ID}"]


def _in_thread(
    pool: ThreadPoolExecutor,
    engine: ElevenReaderTtsEngine,
    request: DocumentSynthesisRequest,
    cancel: Cancellation | None = None,
) -> Future[DocumentResult]:
    token: Cancellation = cancel or Cancellation()
    return pool.submit(asyncio.run, engine.synthesize_document(request, cancel=token))


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline: float = time.monotonic() + 5.0
    while not condition():
        assert time.monotonic() < deadline
        time.sleep(0.005)


def _hub_threads() -> int:
    return sum(thread.name == HUB_THREAD for thread in threading.enumerate())


def test_synthesize_document_success_returns_ordered_timings_and_cleans_account(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS)
    request = _request(tmp_path)

    result = _run(_record(engine_for(site), request))

    assert [timing.request_id for timing in result.parts] == ["line-0", "line-1"]
    assert result.parts[0].end_ms <= result.parts[1].start_ms
    assert result.recording == request.recording
    assert request.recording.stat().st_size > 0
    assert result.voice_id == FRONCZEWSKI_ID
    assert "".join(char for chunk in result.chunks for char in chunk.chars).startswith("Pierwsza kwestia.")
    assert site.uploaded == ["Pierwsza kwestia.\n\n…\n\nDruga (kwestia).\n"]
    assert "set_page_speed" in site.events
    _assert_cleaned(site)
    assert site.pages[0].closed
    assert not site.pages[0].watching
    assert site.sessions[0].alive


def test_synthesize_document_sets_voice_and_speed_before_opening_document(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS)

    _run(_record(engine_for(site, voice_id="adam"), _request(tmp_path, voice_id="adam")))

    assert site.events.index("set_account") < site.events.index("open_document")
    assert site.events.index("upload") < site.events.index("set_account")


def test_synthesize_document_signed_in_records_session(tmp_path: Path, engine_for: EngineFor) -> None:
    _run(_record(engine_for(FakeSite(texts=TEXTS)), _request(tmp_path)))

    record = read_session(tmp_path)
    assert record is not None
    assert record.signed_in


def test_synthesize_document_signed_out_raises_auth_error_and_records_session(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(library=LibraryState.SIGNED_OUT)

    with pytest.raises(TtsAuthError) as error:
        _run(_record(engine_for(site), _request(tmp_path)))

    assert "edp login" in error.value.context.suggestion
    assert "upload" not in site.events
    record = read_session(tmp_path)
    assert record is not None
    assert not record.signed_in


def test_synthesize_document_default_browser_starts_chrome_headless(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = FakeSite(library=LibraryState.SIGNED_OUT)
    modes: list[bool] = []

    def session(root: Path, *, headless: bool) -> FakeSession:
        modes.append(headless)
        created: FakeSession = FakeSession(site)
        site.sessions.append(created)
        return created

    monkeypatch.setattr(browser_module, "ChromeSession", session)
    engine = ElevenReaderTtsEngine(engine_config(tmp_path))

    try:
        with pytest.raises(TtsAuthError):
            _run(_record(engine, _request(tmp_path)))
    finally:
        _run(engine.close())

    assert modes == [True]


def test_synthesize_document_unavailable_library_closes_tab_and_next_attempt_restarts_browser(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, library=LibraryState.UNAVAILABLE)
    engine = engine_for(site)

    with pytest.raises(TtsProviderUnavailableError) as error:
        _run(_record(engine, _request(tmp_path)))

    assert error.value.retry_after_s == 60.0
    assert site.pages[0].closed
    assert site.sessions[0].alive
    site.library = LibraryState.READY

    _run(_record(engine, _request(tmp_path)))

    assert site.sessions[0].closed
    assert site.sessions[1].alive


def test_synthesize_document_account_ignoring_voice_raises_voice_error_and_cleans(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, ignore_voice=True)

    with pytest.raises(TtsVoiceError):
        _run(_record(engine_for(site), _request(tmp_path)))

    _assert_cleaned(site)
    assert "open_document" not in site.events


def test_synthesize_document_stream_without_voice_raises_voice_error(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite(texts=TEXTS, voice_in_url=False)

    with pytest.raises(TtsVoiceError):
        _run(_record(engine_for(site), _request(tmp_path)))

    _assert_cleaned(site)


def test_synthesize_document_v2_stream_raises_transient_error_and_closes_only_its_tab(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, listening_speed=3.0)

    with pytest.raises(TtsProviderUnavailableError, match="Eleven v2"):
        _run(_record(engine_for(site), _request(tmp_path)))

    _assert_cleaned(site)
    assert site.pages[0].closed
    assert site.sessions[0].alive


def test_synthesize_document_incomplete_recording_raises_clip_error(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite(texts=TEXTS, char_count=10_000, player_done=True)

    with pytest.raises(TtsClipValidationError, match="incomplete"):
        _run(_record(engine_for(site), _request(tmp_path)))

    _assert_cleaned(site)


def test_synthesize_document_silent_chunk_leaves_only_its_lines_unspoken(tmp_path: Path, engine_for: EngineFor) -> None:
    texts = ("Pierwsza kwestia.", "Druga kwestia, która ma sporo liter.", "Trzecia kwestia.")
    frames: list[str] = [
        audio_frame(f"{texts[0]} {BREAK} … {BREAK} ", frames=22, fill=1),
        audio_frame(f"{texts[1]} {BREAK} … {BREAK} ", frames=1, fill=2, step_ms=1.0),
        audio_frame(f'{texts[2]} <break time="2s"/>', frames=22, fill=3),
    ]
    site = FakeSite(texts=texts, frames=frames)

    result = _run(_record(engine_for(site), _request(tmp_path, texts=texts)))

    assert [timing.spoken for timing in result.parts] == [True, False, True]
    _assert_cleaned(site)


def test_synthesize_document_line_count_mismatch_raises_clip_error(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite(texts=TEXTS, frames=stream_frames(("Pierwsza kwestia. Druga (kwestia).",)))

    with pytest.raises(TtsClipValidationError, match="line count mismatch"):
        _run(_record(engine_for(site), _request(tmp_path)))


def test_synthesize_document_without_audio_opens_the_document_again_then_times_out(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, send_audio=False)

    with pytest.raises(TtsTimeoutError, match="no audio"):
        _run(_record(engine_for(site), _request(tmp_path)))

    assert site.plays == 3
    assert site.events.count("open_document") == 3
    _assert_cleaned(site)
    assert site.pages[0].closed


def test_synthesize_document_app_check_refusal_fails_at_once_without_play(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, refusal="AppCheck: 403 error. Attempts allowed again after 01d:00m:00s")

    with pytest.raises(TtsAuthError, match="App Check") as error:
        _run(_record(engine_for(site), _request(tmp_path)))

    assert error.value.context.details == {"console": site.refusal}
    assert site.plays == 0
    _assert_cleaned(site)


def test_synthesize_document_stalled_stream_times_out(tmp_path: Path, engine_for: EngineFor) -> None:
    frames: list[str] = [audio_frame("Pierwsza kwestia. " + BREAK, frames=3)]
    site = FakeSite(texts=TEXTS, frames=frames, char_count=10_000)

    with pytest.raises(TtsTimeoutError, match="stalled"):
        _run(_record(engine_for(site), _request(tmp_path)))


def test_synthesize_document_progress_reports_received_characters_on_engine_thread(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS)
    seen: list[tuple[int, int, int]] = []

    async def observe(received: int, total: int) -> None:
        seen.append((received, total, threading.get_ident()))

    base = _request(tmp_path)
    request = DocumentSynthesisRequest(
        request_id=base.request_id,
        parts=base.parts,
        voice_id=base.voice_id,
        recording=base.recording,
        deadline_s=base.deadline_s,
        progress=observe,
    )

    _run(_record(engine_for(site), request))

    assert seen
    assert seen[-1][:2] == (site.count(), site.count())
    assert {thread for _, _, thread in seen} == {threading.get_ident()}


def test_synthesize_document_cancel_while_waiting_stops_quickly_and_cleans(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, hang_on="open_document")
    engine = engine_for(site)
    cancel = Cancellation()

    async def scenario() -> float:
        started: float = time.monotonic()
        task = asyncio.create_task(engine.synthesize_document(_request(tmp_path), cancel=cancel))
        await asyncio.to_thread(site.hung.wait)
        cancel.cancel()
        with pytest.raises(TtsCancelledError):
            await task
        return time.monotonic() - started

    elapsed: float = _run(scenario())

    assert elapsed < 2.0
    _assert_cleaned(site)
    assert site.pages[0].closed


@pytest.mark.parametrize("hung", ["set_page_speed", "press_play", "check_page_speed", "player_state"])
def test_synthesize_document_cancel_while_page_hangs_stops_quickly_and_cleans(
    tmp_path: Path, engine_for: EngineFor, hung: str
) -> None:
    site = FakeSite(texts=TEXTS, char_count=10_000, hang_on=hung)
    engine = engine_for(site)
    cancel = Cancellation()

    async def scenario() -> None:
        async with asyncio.timeout(5.0):
            task = asyncio.create_task(engine.synthesize_document(_request(tmp_path), cancel=cancel))
            await asyncio.to_thread(site.hung.wait)
            cancel.cancel()
            with pytest.raises(TtsCancelledError):
                await task

    _run(scenario())

    _assert_cleaned(site)
    assert site.pages[0].closed


def test_synthesize_document_hung_page_times_out_at_deadline_and_cleans(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite(texts=TEXTS, char_count=10_000, hang_on="player_state")
    engine = engine_for(site)

    async def scenario() -> None:
        async with asyncio.timeout(5.0):
            await _record(engine, _request(tmp_path, deadline_s=0.2))

    with pytest.raises(TtsTimeoutError, match="deadline"):
        _run(scenario())

    _assert_cleaned(site)
    assert site.pages[0].closed


def test_synthesize_document_task_cancelled_still_cleans_and_closes_tab(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite(texts=TEXTS, hang_on="open_document")
    engine = engine_for(site)

    async def scenario() -> None:
        task = asyncio.create_task(_record(engine, _request(tmp_path)))
        await asyncio.to_thread(site.hung.wait)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    _run(scenario())

    _assert_cleaned(site)
    assert site.pages[0].closed


def test_synthesize_document_cancel_during_upload_deletes_document_found_by_title(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, hang_on="upload")
    engine = engine_for(site)
    cancel = Cancellation()

    async def scenario() -> None:
        task = asyncio.create_task(engine.synthesize_document(_request(tmp_path), cancel=cancel))
        await asyncio.to_thread(site.hung.wait)
        cancel.cancel()
        with pytest.raises(TtsCancelledError):
            await task

    _run(scenario())

    assert site.deleted == [f"{READS_URL}/{READ_ID}"]
    assert site.reads == []
    record = read_session(tmp_path)
    assert record is not None
    assert not record.cleanup_pending
    assert site.pages[0].closed


def test_synthesize_document_task_cancelled_during_upload_deletes_document_found_by_title(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, hang_on="upload")
    engine = engine_for(site)

    async def scenario() -> None:
        task = asyncio.create_task(_record(engine, _request(tmp_path)))
        await asyncio.to_thread(site.hung.wait)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    _run(scenario())

    assert site.deleted == [f"{READS_URL}/{READ_ID}"]
    assert site.pages[0].closed


def test_synthesize_document_cancel_during_upload_before_document_appears_keeps_saved_trace(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, hang_on="upload")
    engine = engine_for(site)
    cancel = Cancellation()

    async def scenario() -> None:
        task = asyncio.create_task(engine.synthesize_document(_request(tmp_path), cancel=cancel))
        await asyncio.to_thread(site.hung.wait)
        site.reads.clear()
        cancel.cancel()
        with pytest.raises(TtsCancelledError):
            await task
        await engine.close()

    _run(scenario())

    record = read_session(tmp_path)
    assert record is not None
    assert record.delete_document
    assert READ_ID not in (tmp_path / "session.json").read_text(encoding="utf-8")


def test_saved_document_trace_is_cleaned_by_next_engine_before_upload(tmp_path: Path, engine_for: EngineFor) -> None:
    first = FakeSite(texts=TEXTS, hang_on="upload", failing={"list_reads"})
    engine = engine_for(first)
    cancel = Cancellation()

    async def interrupted() -> None:
        task = asyncio.create_task(engine.synthesize_document(_request(tmp_path), cancel=cancel))
        await asyncio.to_thread(first.hung.wait)
        cancel.cancel()
        with pytest.raises(TtsCancelledError):
            await task
        await engine.close()

    _run(interrupted())
    saved = read_session(tmp_path)
    assert saved is not None
    assert saved.delete_document
    second = FakeSite(texts=TEXTS, reads=[READ_ID])

    _run(_record(engine_for(second), _request(tmp_path)))

    assert second.events.index("list_reads") < second.events.index("upload")
    assert second.deleted == [f"{READS_URL}/{READ_ID}", f"{READS_URL}/{READ_ID}"]
    record = read_session(tmp_path)
    assert record is not None
    assert not record.cleanup_pending


def test_failed_restore_is_saved_and_run_by_next_engine_after_its_recording(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    first = FakeSite(texts=TEXTS, failing={"restore_account"})
    engine = engine_for(first)
    _run(_record(engine, _request(tmp_path)))
    _run(engine.close())
    saved = read_session(tmp_path)
    assert saved is not None
    assert saved.restore == AccountSettings(voice_id="previous-voice", speed=1.5)
    assert not saved.delete_document
    second = FakeSite(texts=TEXTS, account={"default_voice_id": FRONCZEWSKI_ID, "playback_speed_rate": 1.0})

    _run(_record(engine_for(second), _request(tmp_path)))

    assert second.events.index("upload") < second.events.index("restore_account")
    assert second.account["default_voice_id"] == "previous-voice"
    assert second.account["playback_speed_rate"] == 1.5
    record = read_session(tmp_path)
    assert record is not None
    assert not record.cleanup_pending


def test_synthesize_document_unwritable_recording_raises_clip_error_without_waiting_for_stall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine_for: EngineFor,
) -> None:
    monkeypatch.setattr(service, "STALL_S", 300.0)
    monkeypatch.setattr(service, "StreamRecorder", lambda output: StreamRecorder(_FullDisk()))
    site = FakeSite(texts=TEXTS)
    started: float = time.monotonic()

    with pytest.raises(TtsClipValidationError) as error:
        _run(_record(engine_for(site), _request(tmp_path)))

    assert time.monotonic() - started < 2.0
    assert error.value.context.details == {"error_class": "OSError", "errno": errno.ENOSPC}
    _assert_cleaned(site)


class _FullDisk(io.BytesIO):
    def write(self, data: object) -> int:
        raise OSError(errno.ENOSPC, "No space left on device")


@pytest.mark.parametrize("text", UNREADABLE_PARTS)
def test_synthesize_document_part_unreadable_as_paragraph_is_refused_without_browser(
    tmp_path: Path, engine_for: EngineFor, text: str
) -> None:
    site = FakeSite()

    with pytest.raises(TtsInputError) as error:
        _run(_record(engine_for(site), _request(tmp_path, texts=("Dobrze.", text))))

    assert error.value.context.details == {"request_id": "line-1"}
    assert site.sessions == []
    assert site.uploaded == []


def test_synthesize_document_tags_part_with_break_is_refused_without_browser(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite()

    with pytest.raises(TtsInputError):
        _run(_record(engine_for(site), replace(_request(tmp_path, texts=("[śmiech] Raz <break/> dwa",)), tags=True)))

    assert site.sessions == []


def test_synthesize_document_tags_uploads_square_brackets_and_times_parts(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    texts = ("[śmiech] Pierwsza kwestia.", "Druga [kwestia].")
    frames: list[str] = [
        audio_frame(f"{texts[0]} {BREAK} … {BREAK} ", frames=22, fill=1),
        audio_frame(f'{texts[1]} <break time="2s"/>', frames=22, fill=2),
    ]
    site = FakeSite(texts=texts, frames=frames)

    result = _run(_record(engine_for(site), replace(_request(tmp_path, texts=texts), tags=True)))

    assert site.uploaded == ["[śmiech] Pierwsza kwestia.\n\n…\n\nDruga [kwestia].\n"]
    assert [timing.spoken for timing in result.parts] == [True, True]


@pytest.mark.parametrize("text", UNREADABLE_PARTS)
def test_validate_part_unreadable_as_paragraph_raises_input_error(engine_for: EngineFor, text: str) -> None:
    site = FakeSite()

    with pytest.raises(TtsInputError) as error:
        engine_for(site).validate_part(DocumentPart(request_id="line-7", text=text))

    assert error.value.context.details == {"request_id": "line-7"}
    assert site.sessions == []


@pytest.mark.parametrize("text", ["Zobacz filmik…", "Raz [dwa].", "  Trzy\ncztery.  "])
def test_validate_part_readable_paragraph_accepts_part(engine_for: EngineFor, text: str) -> None:
    engine_for(FakeSite()).validate_part(DocumentPart(request_id="line-0", text=text))


def test_synthesize_document_cancelled_before_start_opens_no_browser(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite()
    cancel = Cancellation()
    cancel.cancel()

    with pytest.raises(TtsCancelledError):
        _run(engine_for(site).synthesize_document(_request(tmp_path), cancel=cancel))

    assert site.sessions == []


def test_synthesize_document_after_close_is_refused_without_browser(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite()
    engine = engine_for(site)
    _run(engine.close())

    with pytest.raises(TtsProviderUnavailableError, match="closed"):
        _run(_record(engine, _request(tmp_path)))

    assert site.sessions == []


def test_failed_delete_stays_pending_and_runs_before_next_upload(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite(texts=TEXTS, failing={"delete_read"})
    engine = engine_for(site)

    async def scenario() -> None:
        await _record(engine, _request(tmp_path))
        site.failing.clear()
        site.events.clear()
        await _record(engine, _request(tmp_path))

    _run(scenario())

    assert site.events.index("delete_read") < site.events.index("upload")
    assert site.deleted == [read_url(0), read_url(1)]


def test_close_runs_pending_cleanup_while_browser_lives(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite(texts=TEXTS, failing={"delete_read"})
    engine = engine_for(site)

    async def scenario() -> None:
        await _record(engine, _request(tmp_path))
        site.failing.clear()
        await engine.close()

    _run(scenario())

    assert len(site.deleted) == 1
    assert site.sessions[0].closed


def test_close_with_cleanup_failing_for_good_warns_owner(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite(texts=TEXTS, failing={"delete_read", "restore_account"})
    engine = engine_for(site)
    captured: list[Message] = []
    handler_id: int = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")

    async def scenario() -> None:
        await _record(engine, _request(tmp_path))
        await engine.close()

    try:
        _run(scenario())
    finally:
        loguru_logger.remove(handler_id)

    warnings: list[str] = [str(message) for message in captured if CLEANUP_WARNING in str(message)]
    assert len(warnings) == 1
    assert "restore_settings" in warnings[0]
    assert "delete_read" in warnings[0]
    assert site.sessions[0].closed
    record = read_session(tmp_path)
    assert record is not None
    assert record.restore == AccountSettings(voice_id="previous-voice", speed=1.5)
    assert record.delete_document


class _BrokenTabPage(FakePage):
    async def close(self) -> None:
        await super().close()
        message: str = "tab gone"
        raise RuntimeError(message)


def test_synthesize_document_tab_close_breaking_still_frees_the_recording_slot(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, listening_speed=3.0, page_type=_BrokenTabPage)
    engine = engine_for(site)

    with pytest.raises(RuntimeError, match="tab gone"):
        _run(_record(engine, _request(tmp_path)))

    _assert_cleaned(site)
    assert site.sessions[0].alive
    site.page_type = FakePage
    site.listening_speed = 1.0

    async def other_voice() -> DocumentResult:
        async with asyncio.timeout(5.0):
            return await _record(engine_for(site, voice_id="adam"), _request(tmp_path, voice_id="adam"))

    assert _run(other_voice()).voice_id == ADAM_ID


def test_synthesize_document_cleanup_breaking_unexpectedly_still_closes_tab(
    tmp_path: Path,
    engine_for: EngineFor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken(page: object, cleanup: object, *, restore: bool) -> None:
        message: str = "cleanup bug"
        raise RuntimeError(message)

    site = FakeSite(texts=TEXTS, listening_speed=3.0)
    engine = engine_for(site)

    with monkeypatch.context() as patch:
        patch.setattr(hub, "clean_account", broken)
        with pytest.raises(RuntimeError, match="cleanup bug"):
            _run(_record(engine, _request(tmp_path)))

    assert site.pages[0].closed
    assert site.sessions[0].alive


def test_logs_never_contain_token_read_id_or_stream_address(tmp_path: Path) -> None:
    captured: list[Message] = []
    handler_id: int = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")

    async def scenario() -> None:
        engine = fake_engine(tmp_path, FakeSite(texts=TEXTS))
        await _record(engine, _request(tmp_path))
        await engine.close()
        failing = fake_engine(tmp_path, FakeSite(texts=TEXTS, failing={"delete_read", "restore_account"}))
        await _record(failing, _request(tmp_path))
        await failing.close()

    try:
        _run(scenario())
    finally:
        loguru_logger.remove(handler_id)

    text: str = "\n".join(str(message) for message in captured)
    assert captured
    assert TOKEN not in text
    assert READ_ID not in text
    assert "wss://" not in text
    assert str(tmp_path) not in text


def test_two_engines_on_two_threads_record_together_in_tabs_of_one_browser(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, held={0, 1})
    first, second = engine_for(site), engine_for(site)

    with ThreadPoolExecutor(max_workers=2) as pool:
        recordings = [
            _in_thread(pool, engine, _request(tmp_path, name=name))
            for engine, name in ((first, "first"), (second, "second"))
        ]
        _wait_until(lambda: site.streams == 2)
        site.held.clear()
        results = [recording.result(timeout=5.0) for recording in recordings]

    assert len(site.sessions) == 1
    assert len(site.pages) == 2
    assert all([timing.request_id for timing in result.parts] == ["line-0", "line-1"] for result in results)
    uploads: list[int] = [index for index, event in enumerate(site.events) if event == "upload"]
    streams: list[int] = [index for index, event in enumerate(site.events) if event.startswith("stream_")]
    assert streams[0] < uploads[1]
    assert sorted(site.deleted) == sorted([read_url(0), read_url(1)])
    assert site.events.count("restore_account") == 1


def test_first_recording_ending_deletes_only_its_document_and_last_one_restores_account(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    stale: str = "u:stale"
    save_cleanup(tmp_path, AccountCleanup(documents=[document_trace(read_id=stale)]))
    site = FakeSite(texts=TEXTS, held={0, 1})
    first, second = engine_for(site), engine_for(site)

    with ThreadPoolExecutor(max_workers=2) as pool:
        earlier = _in_thread(pool, first, _request(tmp_path, name="first"))
        _wait_until(lambda: site.streams == 1)
        later = _in_thread(pool, second, _request(tmp_path, name="second"))
        _wait_until(lambda: site.streams == 2)
        assert site.deleted == [f"{READS_URL}/{stale}"]
        site.held.discard(0)
        earlier.result(timeout=5.0)
        assert site.deleted == [f"{READS_URL}/{stale}", read_url(0)]
        assert site.account["default_voice_id"] == FRONCZEWSKI_ID
        midway = read_session(tmp_path)
        assert midway is not None
        assert midway.restore == AccountSettings(voice_id="previous-voice", speed=1.5)
        assert [trace.read_id for trace in midway.documents] == [read_id_of(1)]
        site.held.clear()
        later.result(timeout=5.0)

    assert site.deleted == [f"{READS_URL}/{stale}", read_url(0), read_url(1)]
    assert site.account["default_voice_id"] == "previous-voice"
    record = read_session(tmp_path)
    assert record is not None
    assert not record.cleanup_pending


class _YieldingPage(FakePage):
    async def delete(self, url: str, token: str, *, action: str) -> None:
        await asyncio.sleep(0.05)
        await super().delete(url, token, action=action)

    async def close(self) -> None:
        await asyncio.sleep(0.05)
        await super().close()


def _end_together(site: FakeSite, tokens: list[Cancellation], ending: str) -> None:
    if ending == "finish":
        site.held.clear()
        return
    for token in tokens:
        token.cancel()


@pytest.mark.parametrize("ending", ["finish", "cancel"])
def test_recordings_ending_together_restore_account_once_both_left(
    tmp_path: Path, engine_for: EngineFor, ending: str
) -> None:
    site = FakeSite(texts=TEXTS, held={0, 1}, page_type=_YieldingPage)
    tokens: list[Cancellation] = [Cancellation(), Cancellation()]

    with ThreadPoolExecutor(max_workers=2) as pool:
        recordings = [
            _in_thread(pool, engine_for(site), _request(tmp_path, name=name), token)
            for name, token in zip(("first", "second"), tokens, strict=True)
        ]
        _wait_until(lambda: site.streams == 2)
        _end_together(site, tokens, ending)
        for recording in recordings:
            recording.exception(timeout=5.0)

    assert site.account["default_voice_id"] == "previous-voice"
    assert site.account["playback_speed_rate"] == 1.5
    record = read_session(tmp_path)
    assert record is not None
    assert not record.cleanup_pending


class _SlowRestorePage(FakePage):
    async def post_json(self, url: str, token: str, data: dict[str, object], *, action: str) -> None:
        if action == "restore_account":
            self.site.events.append("restore_begin")
            self.site.hung.set()
            await asyncio.sleep(0.2)
        await super().post_json(url, token, data, action=action)


def test_recording_starting_while_last_one_restores_account_waits_for_the_restore(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, page_type=_SlowRestorePage)
    first, second = engine_for(site), engine_for(site)

    with ThreadPoolExecutor(max_workers=2) as pool:
        earlier = _in_thread(pool, first, _request(tmp_path, name="first"))
        assert site.hung.wait(timeout=5.0)
        later = _in_thread(pool, second, _request(tmp_path, name="second"))
        earlier.result(timeout=5.0)
        later.result(timeout=5.0)

    restored: int = site.events.index("restore_account")
    uploads: list[int] = [index for index, event in enumerate(site.events) if event == "upload"]
    assert site.events.index("restore_begin") < restored < uploads[1]
    assert site.events.count("restore_account") == 2
    assert site.account["default_voice_id"] == "previous-voice"


def test_recording_in_another_voice_waits_until_active_recordings_finish(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite(texts=TEXTS, held={0})
    fronczewski, adam = engine_for(site), engine_for(site, voice_id="adam")

    with ThreadPoolExecutor(max_workers=2) as pool:
        earlier = _in_thread(pool, fronczewski, _request(tmp_path, name="first"))
        _wait_until(lambda: site.streams == 1)
        later = _in_thread(pool, adam, _request(tmp_path, voice_id="adam", name="second"))
        time.sleep(0.2)
        assert len(site.uploaded) == 1
        site.held.clear()
        results = [earlier.result(timeout=5.0), later.result(timeout=5.0)]

    assert [result.voice_id for result in results] == [FRONCZEWSKI_ID, ADAM_ID]
    sets: list[int] = [index for index, event in enumerate(site.events) if event == "set_account"]
    assert site.events.index("restore_account") < sets[1]
    assert site.account["default_voice_id"] == "previous-voice"


def test_cancelling_one_recording_closes_only_its_tab_and_keeps_the_other(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, held={0, 1})
    first, second = engine_for(site), engine_for(site)
    cancel = Cancellation()

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancelled = _in_thread(pool, first, _request(tmp_path, name="first"), cancel)
        _wait_until(lambda: site.streams == 1)
        kept = _in_thread(pool, second, _request(tmp_path, name="second"))
        _wait_until(lambda: site.streams == 2)
        cancel.cancel()
        with pytest.raises(TtsCancelledError):
            cancelled.result(timeout=5.0)
        assert site.deleted == [read_url(0)]
        assert [page.closed for page in site.pages] == [True, False]
        assert site.sessions[0].alive
        assert site.account["default_voice_id"] == FRONCZEWSKI_ID
        site.held.clear()
        kept.result(timeout=5.0)

    assert len(site.sessions) == 1
    assert site.deleted == [read_url(0), read_url(1)]
    assert site.account["default_voice_id"] == "previous-voice"


def test_timed_out_recording_keeps_shared_browser_until_the_others_finish(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, held={0, 1})
    first, second = engine_for(site), engine_for(site)

    with ThreadPoolExecutor(max_workers=2) as pool:
        expiring = _in_thread(pool, first, _request(tmp_path, deadline_s=1.0, name="first"))
        _wait_until(lambda: site.streams == 1)
        kept = _in_thread(pool, second, _request(tmp_path, name="second"))
        _wait_until(lambda: site.streams == 2)
        with pytest.raises(TtsTimeoutError, match="deadline"):
            expiring.result(timeout=5.0)
        assert site.sessions[0].alive
        site.held.clear()
        kept.result(timeout=5.0)

    _run(_record(first, _request(tmp_path, name="third")))

    assert len(site.sessions) == 2
    assert site.sessions[0].closed
    assert site.sessions[1].alive


def _download(engine: ElevenReaderTtsEngine, tmp_path: Path, *, voice_id: str | None = None) -> DocumentResult:
    return _run(
        engine.download_document(
            READ_ID, tmp_path / "rec" / "book.mp3", voice_id=voice_id, deadline_s=60.0, cancel=Cancellation()
        )
    )


def test_download_document_records_library_document_without_upload_or_delete(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, player_done=True)

    result = _download(engine_for(site), tmp_path)

    assert result.parts == ()
    assert result.voice_id is None
    assert "".join(char for chunk in result.chunks for char in chunk.chars).startswith("Pierwsza kwestia.")
    assert result.recording.stat().st_size > 0
    assert site.uploaded == []
    assert site.deleted == []
    assert site.account["default_voice_id"] == "previous-voice"
    assert site.account["playback_speed_rate"] == 1.5
    assert site.pages[0].closed


def test_download_document_without_voice_keeps_account_voice_while_reading(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, player_done=True)
    voices: list[object] = []

    class _Watched(FakePage):
        async def press_play(self) -> None:
            voices.append((self.site.account["default_voice_id"], self.site.account["playback_speed_rate"]))
            await super().press_play()

    site.page_type = _Watched

    _download(engine_for(site), tmp_path)

    assert voices == [("previous-voice", 1.0)]


def test_download_document_with_voice_sets_it_and_restores_account(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite(texts=TEXTS, player_done=True)

    result = _download(engine_for(site), tmp_path, voice_id="adam")

    assert result.voice_id == ADAM_ID
    assert site.account["default_voice_id"] == "previous-voice"
    assert site.deleted == []


def test_download_document_resumed_in_the_middle_is_refused_and_cleans_account(
    tmp_path: Path, engine_for: EngineFor
) -> None:
    site = FakeSite(texts=TEXTS, player_done=True, start_position=120)

    with pytest.raises(TtsInputError) as error:
        _download(engine_for(site), tmp_path)

    assert error.value.context.details == {"position": 120.0}
    assert "Rewind" in error.value.context.suggestion
    assert site.plays == 1
    assert site.account["default_voice_id"] == "previous-voice"
    assert site.account["playback_speed_rate"] == 1.5
    assert site.pages[0].closed


def test_download_document_cancelled_before_start_opens_no_browser(tmp_path: Path, engine_for: EngineFor) -> None:
    site = FakeSite()
    cancel = Cancellation()
    cancel.cancel()

    with pytest.raises(TtsCancelledError):
        _run(
            engine_for(site).download_document(
                READ_ID, tmp_path / "book.mp3", voice_id=None, deadline_s=60.0, cancel=cancel
            )
        )

    assert site.sessions == []


def test_last_engine_closing_stops_browser_and_host_thread(tmp_path: Path) -> None:
    threads: int = _hub_threads()
    site = FakeSite(texts=TEXTS)
    first, second = fake_engine(tmp_path, site), fake_engine(tmp_path, site)
    _run(_record(first, _request(tmp_path)))

    _run(first.close())

    assert site.sessions[0].alive
    assert _hub_threads() == threads + 1

    _run(second.close())

    assert site.sessions[0].closed
    assert _hub_threads() == threads


@pytest.mark.parametrize(
    ("change", "error_type"),
    [
        ({"voice_id": ADAM_ID}, TtsInputError),
        ({"voice_id": "dallin"}, TtsVoiceError),
    ],
)
def test_synthesize_document_invalid_request_is_refused_without_browser(
    tmp_path: Path,
    engine_for: EngineFor,
    change: dict[str, object],
    error_type: type[TtsError],
) -> None:
    site = FakeSite()
    base = _request(tmp_path)
    values: dict[str, object] = {
        "request_id": base.request_id,
        "parts": base.parts,
        "voice_id": base.voice_id,
        "recording": base.recording,
        "deadline_s": base.deadline_s,
    }
    values.update(change)
    request = DocumentSynthesisRequest(**values)  # type: ignore[arg-type]

    with pytest.raises(error_type):
        _run(_record(engine_for(site), request))

    assert site.sessions == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[śmiech] No [tak]", "(śmiech) No (tak)"),
        ("Dwie\n linie\t i  spacje ", "Dwie linie i spacje"),
        ("Bez zmian: „cudzysłów”…", "Bez zmian: „cudzysłów”…"),
    ],
)
def test_document_text_part_returns_round_brackets_and_single_spaces(text: str, expected: str) -> None:
    assert document_text((DocumentPart(request_id="a", text=text),)) == expected + "\n"


def test_document_text_parts_returns_separator_paragraph_between_parts() -> None:
    parts = (DocumentPart(request_id="a", text="Raz [dwa]."), DocumentPart(request_id="b", text="Trzy\ncztery."))

    assert document_text(parts) == "Raz (dwa).\n\n…\n\nTrzy cztery.\n"


def test_document_chars_parts_returns_uploaded_text_length(engine_for: EngineFor) -> None:
    parts = (DocumentPart(request_id="a", text="Raz."), DocumentPart(request_id="b", text="Dwa."))

    assert engine_for(FakeSite()).document_chars(parts) == len("Raz.\n\n…\n\nDwa.\n")


def test_document_text_single_part_returns_one_paragraph() -> None:
    assert document_text((DocumentPart(request_id="a", text="Tylko."),)) == "Tylko.\n"


def test_document_text_tags_keeps_square_brackets_and_single_spaces() -> None:
    parts = (DocumentPart(request_id="a", text="[śmiech]  No [tak]"), DocumentPart(request_id="b", text="Dwa."))

    assert document_text(parts, tags=True) == "[śmiech] No [tak]\n\n…\n\nDwa.\n"


def _chunk(text: str, *, offset_ms: float = 0.0, step_ms: float = 10.0, silent: bool = False) -> AlignmentChunk:
    return AlignmentChunk(
        offset_ms=offset_ms,
        chars=tuple(text),
        starts_ms=tuple(index * step_ms for index in range(len(text))),
        durations_ms=(step_ms,) * len(text),
        silent=silent,
    )


def _parts(*texts: str) -> tuple[DocumentPart, ...]:
    return tuple(DocumentPart(request_id=f"line-{index}", text=text) for index, text in enumerate(texts))


def _spans(chunks: tuple[AlignmentChunk, ...], *texts: str) -> list[tuple[float, float]]:
    return [(timing.start_ms, timing.end_ms) for timing in part_spans(chunks, _parts(*texts))]


def test_part_spans_break_tags_split_parts_in_server_time() -> None:
    chunks = (_chunk('Ab. <break time="0.6s"/> Cd.'),)

    assert _spans(chunks, "Ab.", "Cd.") == [(0.0, 30.0), (250.0, 280.0)]


def test_part_spans_separator_paragraph_is_not_a_part() -> None:
    chunks = (_chunk('Ab. <break time="0.6s"/> … <break time="0.6s"/> Cd.'),)

    assert _spans(chunks, "Ab.", "Cd.") == [(0.0, 30.0), (480.0, 510.0)]


def test_part_spans_adjacent_break_tags_form_one_boundary() -> None:
    chunks = (_chunk('Ab.<break time="0.6s"/> <break time="0.6s"/>Cd.'),)

    assert _spans(chunks, "Ab.", "Cd.") == [(0.0, 30.0), (440.0, 470.0)]


def test_part_spans_part_the_server_did_not_speak_returns_empty_span() -> None:
    silent = AlignmentChunk(
        offset_ms=250.0, chars=tuple("j g"), starts_ms=(0.0, 0.0, 0.0), durations_ms=(0.0, 0.0, 0.0)
    )
    chunks = (_chunk('Ab. <break time="0.6s"/> '), silent, _chunk(' <break time="0.6s"/> Cd.', offset_ms=300.0))

    assert _spans(chunks, "Ab.", "j g", "Cd.") == [(0.0, 30.0), (250.0, 250.0), (520.0, 550.0)]


def test_part_spans_parts_touching_a_silent_chunk_return_empty_spans() -> None:
    chunks = (
        _chunk('Ab. <break time="0.6s"/> C'),
        _chunk('d. <break time="0.6s"/> Ef.', offset_ms=300.0, step_ms=1.0, silent=True),
        _chunk(' <break time="0.6s"/> Gh.', offset_ms=330.0),
    )

    timings = part_spans(chunks, _parts("Ab.", "Cd.", "Ef.", "Gh."))

    assert [timing.spoken for timing in timings] == [True, False, False, True]
    assert _spans(chunks, "Ab.", "Cd.", "Ef.", "Gh.")[3] == (550.0, 580.0)


def test_part_spans_ellipsis_ending_a_part_stays_in_its_text() -> None:
    chunks = (_chunk('Zobacz filmik… <break time="0.6s"/> … <break time="0.6s"/> Cd.'),)

    timings = part_spans(chunks, _parts("Zobacz filmik…", "Cd."))

    assert [(timing.start_ms, timing.end_ms) for timing in timings] == [(0.0, 140.0), (590.0, 620.0)]


def test_part_spans_final_break_adds_no_empty_part() -> None:
    chunks = (_chunk('Ab. <break time="0.6s"/> Cd. <break time="2s"/>'),)

    assert len(_spans(chunks, "Ab.", "Cd.")) == 2


def test_part_spans_tag_cut_between_chunks_still_splits() -> None:
    chunks = (_chunk("Ab. <break ti"), _chunk('me="0.6s"/> Cd.', offset_ms=1000.0))

    assert _spans(chunks, "Ab.", "Cd.") == [(0.0, 30.0), (1120.0, 1150.0)]


def test_part_spans_unclosed_tag_at_end_is_dropped() -> None:
    chunks = (_chunk('Ab. <break time="2'),)

    assert _spans(chunks, "Ab.") == [(0.0, 30.0)]


def test_part_spans_part_ending_before_it_starts_raises_clip_error() -> None:
    reversed_chunk = AlignmentChunk(
        offset_ms=0.0, chars=tuple("Ab."), starts_ms=(100.0, 50.0, 0.0), durations_ms=(10.0, 10.0, 10.0)
    )

    with pytest.raises(TtsClipValidationError, match="timing is reversed") as error:
        part_spans((reversed_chunk,), _parts("Ab."))

    assert error.value.context.code.value == "TTS_CLIP_INVALID"
    assert error.value.context.details == {"line": 0}


def test_part_spans_surrounding_whitespace_is_trimmed() -> None:
    chunks = (_chunk("  Ab  "),)

    assert _spans(chunks, "Ab") == [(20.0, 40.0)]


def test_part_spans_bracketed_part_matches_round_brackets_in_server_text() -> None:
    chunks = (_chunk("(Ab)"),)

    assert _spans(chunks, "[Ab]") == [(0.0, 40.0)]


def test_part_spans_tags_bracketed_part_matches_square_brackets_in_server_text() -> None:
    chunks = (_chunk("[Ab]"),)

    timings = part_spans(chunks, _parts("[Ab]"), tags=True)

    assert [(timing.start_ms, timing.end_ms) for timing in timings] == [(0.0, 40.0)]


def test_part_spans_count_mismatch_raises_clip_error() -> None:
    chunks = (_chunk('Ab. <break time="0.6s"/> Cd.'),)

    with pytest.raises(TtsClipValidationError, match="line count mismatch"):
        part_spans(chunks, _parts("Ab. Cd."))


def test_part_spans_text_mismatch_raises_clip_error() -> None:
    chunks = (_chunk('Ab. <break time="0.6s"/> Cd.'),)

    with pytest.raises(TtsClipValidationError, match="line text mismatch"):
        part_spans(chunks, _parts("Ab.", "Ef."))


def test_part_spans_no_chunks_and_no_parts_returns_nothing() -> None:
    assert part_spans((), ()) == ()
