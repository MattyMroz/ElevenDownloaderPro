"""ElevenReader engine: one attempt reads a whole document in Chrome and returns the recording with part timings."""

from __future__ import annotations

import asyncio
import re
import tempfile
import time
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never

from edp.errors import ErrorCode, ErrorContext, TtsClipValidationError, TtsInputError
from edp.utils.logger import get_logger

from .api_backend import prepare_account, unavailable_error, voice_error
from .config import resolve_voice
from .constants import (
    DOCUMENT_NAME,
    END_IDLE_S,
    END_SLACK_CHARS,
    LINE_SEPARATOR,
    MAX_DOCUMENT_CHARS,
    PAGE_SPEED,
    PLAY_ATTEMPTS,
    POLL_S,
    READING_SPEED,
    SPEED_CHECK_S,
    STALL_S,
    START_TIMEOUT_S,
)
from .hub import ReaderHub, cancelled_error, headless_session, timeout_error, unless_cancelled
from .recorder import StreamRecorder
from .types import DocumentResult, PartTiming

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from edp.cancellation import Cancellation

    from .api_backend import ReaderPage
    from .browser import ChromeSession
    from .config import ElevenReaderConfig
    from .hub import ReaderAttempt
    from .types import (
        AlignmentChunk,
        DocumentPart,
        DocumentSynthesisRequest,
        ElevenReaderVoice,
        PlayerState,
        UploadedRead,
    )

__all__ = ["ElevenReaderTtsEngine", "document_text", "part_bounds", "part_spans", "stream_timeline"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_BRACKETS: Final[dict[int, str]] = str.maketrans({"[": "(", "]": ")"})
"""Square brackets, which ElevenReader reads as audio tags, mapped to round ones."""

_PART_GLUE: Final[str] = f"\n\n{LINE_SEPARATOR}\n\n"
"""Text between parts: a separator paragraph, so the server pauses and marks breaks around it."""

_BREAK_TAG: Final[str] = "<break"
"""Start of the SSML pause the server places between paragraphs; a part may not contain one."""

_BREAK_RUN: Final[re.Pattern[str]] = re.compile(r"<break[^>]*(?:>|$)(?:\s*<break[^>]*(?:>|$))*")
"""Adjacent SSML pauses forming one boundary; the final tag may be cut off at the end of the text."""

_ACCOUNT_VOICE: Final[str] = ""
"""Voice-gate key of a download reading with the account's voice: it waits for, and holds off, every chosen voice."""

_DOWNLOAD_REQUEST_ID: Final[str] = "download"
"""Request id of a downloaded document; the read id stays out of results."""


class ElevenReaderTtsEngine:
    """One-attempt adapter recording ElevenReader documents in a tab of the profile's shared Chrome."""

    def __init__(
        self,
        config: ElevenReaderConfig,
        *,
        browser_factory: Callable[[Path], ChromeSession] | None = None,
    ) -> None:
        """Join the profile's host without starting a browser."""
        self._config: ElevenReaderConfig = config
        self._hub: ReaderHub = ReaderHub.acquire(self._config.profile_root, browser_factory or headless_session)
        self._closed: bool = False

    def document_chars(self, parts: tuple[DocumentPart, ...]) -> int:
        """Return the length of the uploaded document text for *parts*."""
        return len(document_text(parts))

    def validate_part(self, part: DocumentPart) -> None:
        """Raise TtsInputError when *part* cannot be read as its own paragraph."""
        text: str = _neutralize(part.text)
        if not text or text == LINE_SEPARATOR or _BREAK_TAG in text.casefold():
            _raise_unreadable_part(part.request_id)

    async def synthesize_document(
        self,
        request: DocumentSynthesisRequest,
        *,
        cancel: Cancellation,
    ) -> DocumentResult:
        """Record one document once in its own tab, always deleting it from the library afterwards."""
        voice: ElevenReaderVoice = self._validate(request)
        if cancel.is_cancelled:
            raise cancelled_error()
        if self._closed:
            message: str = "ElevenReader engine is closed"
            raise unavailable_error(message)
        return await self._hub.record(
            partial(self._read, _reported_here(request), voice),
            voice_id=voice.voice_id,
            deadline_s=request.deadline_s,
            cancel=cancel,
        )

    async def download_document(
        self,
        read_id: str,
        recording: Path,
        *,
        voice_id: str | None,
        deadline_s: float,
        cancel: Cancellation,
    ) -> DocumentResult:
        """Record an existing library document from its start in its own tab; the document stays in the library.

        Args:
            read_id: Library id of the document.
            recording: MP3 file to write.
            voice_id: Voice alias or id to set on the account, or None to read with the account's voice.
            deadline_s: Upper limit of the whole attempt.
            cancel: Cancellation of the caller.

        Returns:
            The recording and its stream chunks, without part timings.
        """
        voice: ElevenReaderVoice | None = None if voice_id is None else resolve_voice(voice_id)
        if cancel.is_cancelled:
            raise cancelled_error()
        if self._closed:
            message: str = "ElevenReader engine is closed"
            raise unavailable_error(message)
        return await self._hub.record(
            partial(self._download, read_id, recording, voice),
            voice_id=_ACCOUNT_VOICE if voice is None else voice.voice_id,
            deadline_s=deadline_s,
            cancel=cancel,
        )

    async def close(self) -> None:
        """Leave the profile's host; the last engine to leave cleans the account and stops Chrome."""
        if self._closed:
            return
        self._closed = True
        await self._hub.release()

    def _validate(self, request: DocumentSynthesisRequest) -> ElevenReaderVoice:
        voice: ElevenReaderVoice = resolve_voice(request.voice_id)
        if voice != self._config.voice:
            _raise_input("ElevenReader request voice differs from engine configuration")
        if self.document_chars(request.parts) > MAX_DOCUMENT_CHARS:
            _raise_input(f"ElevenReader document exceeds {MAX_DOCUMENT_CHARS} characters")
        for part in request.parts:
            self.validate_part(part)
        return voice

    async def _read(
        self,
        request: DocumentSynthesisRequest,
        voice: ElevenReaderVoice,
        attempt: ReaderAttempt,
    ) -> DocumentResult:
        page: ReaderPage = attempt.page
        cancel: Cancellation = attempt.cancel
        text: str = document_text(request.parts, tags=request.tags)
        with tempfile.TemporaryDirectory(prefix="edp-elevenreader-") as folder:
            document: Path = Path(folder) / DOCUMENT_NAME
            document.write_text(text, encoding="utf-8")
            uploaded: UploadedRead = await unless_cancelled(
                page.upload(document, attempt.uploads, attempt.save),
                cancel,
            )
        logger.info("ElevenReader document uploaded", parts=len(request.parts), chars=uploaded.char_count)
        await unless_cancelled(
            prepare_account(page, uploaded.token, voice.voice_id, attempt.account, attempt.save),
            cancel,
        )
        recorder: StreamRecorder = await self._stream(
            attempt,
            uploaded.read_id,
            request.recording,
            voice,
            char_count=uploaded.char_count,
            progress=request.progress,
        )
        elapsed_ms: float = (time.monotonic() - attempt.entered_at) * 1000
        return self._result(request, voice, recorder, uploaded.char_count, elapsed_ms)

    async def _download(
        self,
        read_id: str,
        recording: Path,
        voice: ElevenReaderVoice | None,
        attempt: ReaderAttempt,
    ) -> DocumentResult:
        token: str | None = attempt.page.token
        if not token:
            message: str = "ElevenReader library gave no account token"
            raise unavailable_error(message)
        await unless_cancelled(
            prepare_account(
                attempt.page, token, None if voice is None else voice.voice_id, attempt.account, attempt.save
            ),
            attempt.cancel,
        )
        recorder: StreamRecorder = await self._stream(
            attempt, read_id, recording, voice, char_count=None, progress=None
        )
        elapsed_ms: float = (time.monotonic() - attempt.entered_at) * 1000
        logger.info("ElevenReader document downloaded", chars=recorder.chars, elapsed_ms=elapsed_ms)
        return DocumentResult(
            request_id=_DOWNLOAD_REQUEST_ID,
            recording=recording,
            voice_id=None if voice is None else voice.voice_id,
            request_time_ms=elapsed_ms,
            parts=(),
            chunks=recorder.chunks,
        )

    async def _stream(  # noqa: PLR0913 - one stream needs its tab, document, file, voice, length and progress
        self,
        attempt: ReaderAttempt,
        read_id: str,
        recording: Path,
        voice: ElevenReaderVoice | None,
        *,
        char_count: int | None,
        progress: Callable[[int, int], Awaitable[None]] | None,
    ) -> StreamRecorder:
        page: ReaderPage = attempt.page
        cancel: Cancellation = attempt.cancel
        recording.parent.mkdir(parents=True, exist_ok=True)
        stream_voices: list[bool] = []
        with recording.open("wb") as output:
            recorder: StreamRecorder = StreamRecorder(output)
            page.watch_stream(recorder, lambda url: stream_voices.append(voice is None or voice.voice_id in url))
            try:
                await unless_cancelled(page.open_document(read_id), cancel)
                await unless_cancelled(page.set_page_speed(PAGE_SPEED), cancel)
                await unless_cancelled(page.press_play(), cancel)
                played_at: float = time.monotonic()
                await _stream_opened(recorder, stream_voices, played_at, cancel)
                attempt.started()
                await self._record(page, recorder, char_count, progress, cancel, played_at=played_at)
            finally:
                page.unwatch_stream()
                recorder.stop()
        if voice is not None and not any(stream_voices):
            message: str = "ElevenReader stream address did not carry the selected voice"
            raise voice_error(message)
        return recorder

    async def _record(  # noqa: PLR0913 - one recording loop needs its tab, stream, length, progress and Play moment
        self,
        page: ReaderPage,
        recorder: StreamRecorder,
        char_count: int | None,
        progress: Callable[[int, int], Awaitable[None]] | None,
        cancel: Cancellation,
        *,
        played_at: float,
    ) -> None:
        now: float = time.monotonic()
        last_progress: float = now
        last_speed_check: float = now
        last_bytes: int = 0
        plays: int = 1
        while True:
            await unless_cancelled(asyncio.sleep(POLL_S), cancel)
            if recorder.write_error is not None:
                raise _write_error(recorder.write_error)
            if recorder.listening_speed not in (None, READING_SPEED):
                message: str = "ElevenReader streamed with Eleven v2 instead of v4"
                raise unavailable_error(message)
            now = time.monotonic()
            if now - last_speed_check >= SPEED_CHECK_S:
                last_speed_check = now
                await unless_cancelled(page.check_page_speed(PAGE_SPEED), cancel)
            if not recorder.audio_bytes:
                if now - played_at < START_TIMEOUT_S:
                    continue
                if plays >= PLAY_ATTEMPTS:
                    reason: str = "ElevenReader sent no audio after Play"
                    raise timeout_error(reason)
                await unless_cancelled(page.press_play(), cancel)
                plays, played_at = plays + 1, now
                continue
            if recorder.audio_bytes != last_bytes:
                last_bytes, last_progress = recorder.audio_bytes, now
                if progress is not None and char_count is not None:
                    await progress(min(recorder.chars, char_count), char_count)
            if await self._finished(page, recorder, char_count, cancel) and now - last_progress >= END_IDLE_S:
                return
            if now - last_progress >= STALL_S:
                reason = "ElevenReader recording stalled"
                raise timeout_error(reason)

    async def _finished(
        self, page: ReaderPage, recorder: StreamRecorder, char_count: int | None, cancel: Cancellation
    ) -> bool:
        if char_count is not None and recorder.chars >= char_count:
            return True
        state: PlayerState = await unless_cancelled(page.player_state(), cancel)
        return state.length > 0 and state.length - state.value <= END_SLACK_CHARS

    def _result(
        self,
        request: DocumentSynthesisRequest,
        voice: ElevenReaderVoice,
        recorder: StreamRecorder,
        char_count: int,
        elapsed_ms: float,
    ) -> DocumentResult:
        if recorder.chars < char_count:
            _raise_clip("ElevenReader recording is incomplete", received=recorder.chars, expected=char_count)
        if recorder.chars > char_count:
            logger.warning(
                "ElevenReader received more text than uploaded", received=recorder.chars, expected=char_count
            )
        timings: tuple[PartTiming, ...] = part_spans(recorder.chunks, request.parts, tags=request.tags)
        logger.info(
            "ElevenReader document recorded",
            parts=len(timings),
            unspoken=sum(not timing.spoken for timing in timings),
            chars=recorder.chars,
            elapsed_ms=elapsed_ms,
        )
        return DocumentResult(
            request_id=request.request_id,
            recording=request.recording,
            voice_id=voice.voice_id,
            request_time_ms=elapsed_ms,
            parts=timings,
            chunks=recorder.chunks,
        )


def document_text(parts: tuple[DocumentPart, ...], *, tags: bool = False) -> str:
    """Return the uploaded document: parts as paragraphs split by separator paragraphs, newline-ended.

    Args:
        parts: Parts in reading order.
        tags: Keep square brackets so the server reads them as audio tags; otherwise they become round brackets.

    Returns:
        The document text with single spaces inside each part.
    """
    return _PART_GLUE.join(_neutralize(part.text, tags=tags) for part in parts) + "\n"


def part_spans(
    chunks: tuple[AlignmentChunk, ...], parts: tuple[DocumentPart, ...], *, tags: bool = False
) -> tuple[PartTiming, ...]:
    """Return the server timing of every part between break tags; a part touching a silent chunk gets an empty span.

    Args:
        chunks: Stream chunks with character timings, in arrival order.
        parts: Parts of the uploaded document, in reading order.
        tags: The document was uploaded with square brackets kept, as by ``document_text(..., tags=True)``.

    Returns:
        One timing per part.

    Raises:
        TtsClipValidationError: The streamed text does not split into the parts or a part's timing is reversed.
    """
    text, starts, ends = stream_timeline(chunks)
    silent: list[bool] = [chunk.silent for chunk in chunks for _ in chunk.chars]
    bounds: tuple[tuple[int, int], ...] = part_bounds(text)
    if len(bounds) != len(parts):
        _raise_clip("ElevenReader line count mismatch", received=len(bounds), expected=len(parts))
    timings: list[PartTiming] = []
    for index, (part, (first, last)) in enumerate(zip(parts, bounds, strict=True)):
        if text[first : last + 1] != _neutralize(part.text, tags=tags):
            _raise_clip("ElevenReader line text mismatch", line=index)
        if ends[last] < starts[first]:
            _raise_clip("ElevenReader part timing is reversed", line=index)
        end_ms: float = starts[first] if any(silent[first : last + 1]) else ends[last]
        timings.append(PartTiming(request_id=part.request_id, start_ms=starts[first], end_ms=end_ms))
    return tuple(timings)


def stream_timeline(chunks: tuple[AlignmentChunk, ...]) -> tuple[str, list[float], list[float]]:
    """Return the streamed text with the start and end of every character on the recording timeline."""
    text: str = "".join(char for chunk in chunks for char in chunk.chars)
    starts: list[float] = [chunk.offset_ms + start for chunk in chunks for start in chunk.starts_ms]
    ends: list[float] = [
        chunk.offset_ms + start + duration
        for chunk in chunks
        for start, duration in zip(chunk.starts_ms, chunk.durations_ms, strict=True)
    ]
    return text, starts, ends


def part_bounds(text: str) -> tuple[tuple[int, int], ...]:
    """Return the first and last character index of every part in the streamed *text*.

    Parts are the runs between break tags, trimmed of whitespace; a run holding only the separator paragraph is not a
    part.
    """
    bounds: list[tuple[int, int]] = []
    cursor: int = 0
    for match in (*_BREAK_RUN.finditer(text), None):
        stop: int = len(text) if match is None else match.start()
        bound: tuple[int, int] | None = _segment(text, cursor, stop)
        if bound is not None:
            bounds.append(bound)
        cursor = len(text) if match is None else match.end()
    return tuple(bounds)


def _neutralize(text: str, *, tags: bool = False) -> str:
    return " ".join((text if tags else text.translate(_BRACKETS)).split())


def _segment(text: str, first: int, stop: int) -> tuple[int, int] | None:
    last: int = stop - 1
    while first <= last and text[first].isspace():
        first += 1
    while last >= first and text[last].isspace():
        last -= 1
    if first > last or text[first : last + 1] == LINE_SEPARATOR:
        return None
    return first, last


def _reported_here(request: DocumentSynthesisRequest) -> DocumentSynthesisRequest:
    progress: Callable[[int, int], Awaitable[None]] | None = request.progress
    if progress is None:
        return request
    loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

    async def notify(received: int, total: int) -> None:
        await progress(received, total)

    async def report(received: int, total: int) -> None:
        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(notify(received, total), loop))

    return replace(request, progress=report)


async def _stream_opened(
    recorder: StreamRecorder, addresses: list[bool], played_at: float, cancel: Cancellation
) -> None:
    while not addresses and not recorder.audio_bytes and time.monotonic() - played_at < START_TIMEOUT_S:
        await unless_cancelled(asyncio.sleep(POLL_S), cancel)


def _write_error(error: OSError) -> TtsClipValidationError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CLIP_INVALID,
        message="ElevenReader recording could not be written",
        suggestion="Check free space and write permissions of the output directory.",
        details={"error_class": type(error).__name__, "errno": error.errno},
    )
    return TtsClipValidationError(context=context)


def _raise_input(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_INPUT_INVALID,
        message=message,
        suggestion="Use the voice the engine was created with and keep the document within the size limit.",
    )
    raise TtsInputError(context=context)


def _raise_unreadable_part(request_id: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_INPUT_INVALID,
        message="ElevenReader part cannot be read as its own paragraph",
        suggestion="A part must not be empty, only „…” or contain a <break> tag.",
        details={"request_id": request_id},
    )
    raise TtsInputError(context=context)


def _raise_clip(message: str, **details: int) -> Never:
    context: ErrorContext = ErrorContext(code=ErrorCode.TTS_CLIP_INVALID, message=message, details=details)
    raise TtsClipValidationError(context=context)
