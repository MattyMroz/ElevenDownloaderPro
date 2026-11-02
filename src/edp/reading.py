"""Text files and library documents to one MP3 with part timings, words and subtitles.

A text file becomes parts (one per non-empty line), the parts become documents of at most ``MAX_DOCUMENT_CHARS``
characters, and the engine records at most ``MAX_PARALLEL_DOCUMENTS`` documents at once. Parts the server did not
speak are read again in smaller documents. The recordings are cut and joined by MP3 frames into one file, and the
part, word and subtitle times are moved onto its timeline.
"""

from __future__ import annotations

import asyncio
import itertools
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never
from urllib.parse import unquote, urlsplit

from edp.cancellation import Cancellation
from edp.engine import (
    DEFAULT_VOICE_ALIAS,
    MAX_DOCUMENT_CHARS,
    MAX_PARALLEL_DOCUMENTS,
    VOICES,
    DocumentPart,
    DocumentSynthesisRequest,
    ElevenReaderConfig,
    ElevenReaderTtsEngine,
    PartTiming,
    SignInOutcome,
    resolve_voice,
)
from edp.engine.api_backend import sign_in as sign_in_async
from edp.engine.service import stream_timeline
from edp.errors import ErrorCode, ErrorContext, TransientError, TtsInputError
from edp.subtitles import Piece, shifted, spoken_pieces, write_json, write_srt
from edp.utils._retry import build_retry
from edp.utils.logger import get_logger
from edp.utils.mp3_frames import cut_before_ms, frames_duration_ms

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tenacity import AsyncRetrying

    from edp.engine.types import DocumentResult, ElevenReaderVoice

__all__ = ["RecordResult", "default_home", "download", "read_id_from_url", "record", "sign_in", "text_lines"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

HOME_VARIABLE: Final[str] = "EDP_HOME"
"""Environment variable naming the home directory with the Chrome profile and the session file."""

HOME_DIR_NAME: Final[str] = ".edp"
"""Home directory under the user's home when ``EDP_HOME`` is unset."""

DOCUMENT_DEADLINE_S: Final[float] = 3600.0
"""Upper limit of one document attempt; a full document plays in about 12 minutes at the measured speed."""

DOWNLOAD_DEADLINE_S: Final[float] = 12 * 3600.0
"""Upper limit of one download attempt; a library book can be many hours long."""

RETRIES: Final[int] = 3
"""Repeats of a document after a transient failure."""

RETRY_BASE_S: Final[float] = 60.0
"""First pause before repeating a document; later pauses double."""

RETRY_CAP_S: Final[float] = 300.0
"""Longest pause before repeating a document."""

_READER_HOST: Final[str] = "elevenreader.io"
"""Host of document addresses."""

_READER_PATH: Final[str] = "reader"
"""First path segment of document addresses; the read id is the last one."""


@dataclass(frozen=True, slots=True)
class RecordResult:
    """Files written for one recording and what the JSON file describes."""

    mp3: Path
    json: Path
    srt: Path
    duration_ms: float
    parts: tuple[PartTiming, ...]
    silent: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _Take:
    """One recorded document: its bytes, the spoken parts in order and their characters."""

    data: bytes
    spoken: tuple[str, ...]
    timings: dict[str, PartTiming]
    pieces: dict[str, Piece]


def default_home() -> Path:
    """Return ``EDP_HOME`` when set, else ``~/.edp``."""
    named: str = os.environ.get(HOME_VARIABLE, "")
    return Path(named) if named else Path.home() / HOME_DIR_NAME


def text_lines(text: str) -> tuple[str, ...]:
    """Return the parts of *text*: every line stripped, empty ones left out."""
    return tuple(line for _, line in _numbered_lines(text))


def read_id_from_url(url: str) -> str:
    """Return the read id of a document address ``https://elevenreader.io/reader/.../<read_id>``."""
    address = urlsplit(url.strip())
    segments: list[str] = [segment for segment in address.path.split("/") if segment]
    host: str = (address.hostname or "").casefold()
    is_reader: bool = host == _READER_HOST or host.endswith(f".{_READER_HOST}")
    if not is_reader or len(segments) < 2 or segments[0] != _READER_PATH:  # noqa: PLR2004 - "reader" and the id
        _raise_input(
            "Not an ElevenReader document address", "Copy the address of a document opened on elevenreader.io."
        )
    return unquote(segments[-1])


def record(
    text: Path,
    *,
    voice: str = DEFAULT_VOICE_ALIAS,
    out_dir: Path | None = None,
    tags: bool = False,
    home: Path | None = None,
) -> RecordResult:
    """Record the text file and write ``<stem>.mp3``, ``<stem>.json`` and ``<stem>.srt`` next to it or in *out_dir*."""
    try:
        source: str = text.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        _raise_input_from(error, "The text file cannot be read as UTF-8", "Pass an existing UTF-8 .txt file.")
    folder: Path = text.parent if out_dir is None else out_dir
    return asyncio.run(_record(source, folder / text.stem, voice=voice, tags=tags, home=home or default_home()))


def download(url: str, *, out: Path, voice: str | None = None, home: Path | None = None) -> RecordResult:
    """Record an existing library document from its start into *out* and the ``.json`` and ``.srt`` next to it."""
    read_id: str = read_id_from_url(url)
    return asyncio.run(_download(read_id, out, voice=voice, home=home or default_home()))


def sign_in(home: Path | None = None) -> SignInOutcome:
    """Open a Chrome window on the library until the owner signs in, then clean up the account."""
    return asyncio.run(sign_in_async(home or default_home()))


async def _record(source: str, stem: Path, *, voice: str, tags: bool, home: Path) -> RecordResult:
    chosen: ElevenReaderVoice = resolve_voice(voice)
    engine: ElevenReaderTtsEngine = ElevenReaderTtsEngine(ElevenReaderConfig(voice=chosen, profile_root=home))
    try:
        parts: tuple[DocumentPart, ...] = _parts(source, engine)
        with tempfile.TemporaryDirectory(prefix="edp-") as folder:
            reader: _Reader = _Reader(engine, chosen.voice_id, tags=tags, folder=Path(folder))
            takes: list[DocumentResult] = await reader.read(_documents(parts, engine))
            return _write_record(stem, chosen.alias, parts, takes)
    finally:
        await engine.close()


async def _download(read_id: str, out: Path, *, voice: str | None, home: Path) -> RecordResult:
    chosen: ElevenReaderVoice | None = None if voice is None else resolve_voice(voice)
    config: ElevenReaderConfig = ElevenReaderConfig(voice=chosen or VOICES[DEFAULT_VOICE_ALIAS], profile_root=home)
    engine: ElevenReaderTtsEngine = ElevenReaderTtsEngine(config)
    cancel: Cancellation = Cancellation()
    try:
        with tempfile.TemporaryDirectory(prefix="edp-") as folder:
            recording: Path = Path(folder) / "download.mp3"
            result: DocumentResult = await _retrying()(
                engine.download_document,
                read_id,
                recording,
                voice_id=None if chosen is None else chosen.voice_id,
                deadline_s=DOWNLOAD_DEADLINE_S,
                cancel=cancel,
            )
            data: bytes = recording.read_bytes()
    finally:
        await engine.close()
    _write_atomic(out, data)
    paths: tuple[Path, Path] = out.with_suffix(".json"), out.with_suffix(".srt")
    pieces: list[Piece] = [stream_timeline(result.chunks)]
    duration_ms: float = frames_duration_ms(data)
    voice_alias: str | None = None if chosen is None else chosen.alias
    write_json(
        paths[0], audio=out.name, voice=voice_alias, duration_ms=duration_ms, lines=(), timings=(), pieces=pieces
    )
    write_srt(paths[1], pieces)
    logger.info("Document downloaded", duration_ms=duration_ms)
    return RecordResult(mp3=out, json=paths[0], srt=paths[1], duration_ms=duration_ms, parts=(), silent=())


class _Reader:
    """Records documents with one engine, at most ``MAX_PARALLEL_DOCUMENTS`` at once, repeating transient failures."""

    def __init__(self, engine: ElevenReaderTtsEngine, voice_id: str, *, tags: bool, folder: Path) -> None:
        self._engine: ElevenReaderTtsEngine = engine
        self._voice_id: str = voice_id
        self._tags: bool = tags
        self._folder: Path = folder
        self._cancel: Cancellation = Cancellation()
        self._slots: asyncio.Semaphore = asyncio.Semaphore(MAX_PARALLEL_DOCUMENTS)
        self._numbers: Iterator[int] = itertools.count()

    async def read(self, documents: list[tuple[DocumentPart, ...]]) -> list[DocumentResult]:
        """Read every document with its rereads; return the recordings in document order, rereads after their own."""
        try:
            async with asyncio.TaskGroup() as group:
                tasks: list[asyncio.Task[list[DocumentResult]]] = [
                    group.create_task(self._read_again(parts)) for parts in documents
                ]
        except ExceptionGroup as failure:
            raise failure.exceptions[0] from None
        return [take for task in tasks for take in task.result()]

    async def _read_again(self, parts: tuple[DocumentPart, ...]) -> list[DocumentResult]:
        """Read *parts*, then the unspoken ones together, then each still unspoken one alone."""
        takes: list[DocumentResult] = []
        read: tuple[DocumentPart, ...] = parts
        silent: tuple[DocumentPart, ...] = await self._take(read, takes)
        if 1 < len(silent) < len(read):
            logger.info("Unspoken parts are read again together", parts=len(silent))
            read = silent
            silent = await self._take(read, takes)
        if len(read) > 1 and silent:
            logger.info("Unspoken parts are read again one by one", parts=len(silent))
            alone: list[DocumentPart] = []
            for part in silent:
                alone.extend(await self._take((part,), takes))
            silent = tuple(alone)
        if silent:
            logger.warning("Parts stayed unspoken when read alone", parts=len(silent))
        return takes

    async def _take(self, parts: tuple[DocumentPart, ...], takes: list[DocumentResult]) -> tuple[DocumentPart, ...]:
        result: DocumentResult = await _retrying()(self._attempt, parts)
        takes.append(result)
        return tuple(part for part, timing in zip(parts, result.parts, strict=True) if not timing.spoken)

    async def _attempt(self, parts: tuple[DocumentPart, ...]) -> DocumentResult:
        async with self._slots:
            number: int = next(self._numbers)
            request: DocumentSynthesisRequest = DocumentSynthesisRequest(
                request_id=f"document-{number}",
                parts=parts,
                voice_id=self._voice_id,
                recording=self._folder / f"{number}.mp3",
                deadline_s=DOCUMENT_DEADLINE_S,
                tags=self._tags,
            )
            return await self._engine.synthesize_document(request, cancel=self._cancel)


def _retrying() -> AsyncRetrying:
    return build_retry(
        max_attempts=RETRIES + 1,
        backoff="exponential",
        base_s=RETRY_BASE_S,
        cap_s=RETRY_CAP_S,
        retry_on=TransientError,
    )


def _numbered_lines(text: str) -> Iterator[tuple[int, str]]:
    for number, line in enumerate(text.splitlines(), start=1):
        stripped: str = line.strip()
        if stripped:
            yield number, stripped


def _parts(source: str, engine: ElevenReaderTtsEngine) -> tuple[DocumentPart, ...]:
    parts: list[DocumentPart] = []
    for number, line in _numbered_lines(source):
        part: DocumentPart = DocumentPart(request_id=str(len(parts)), text=line)
        try:
            engine.validate_part(part)
        except TtsInputError as error:
            _raise_line(number, error.context.message, error.context.suggestion, cause=error)
        if engine.document_chars((part,)) > MAX_DOCUMENT_CHARS:
            _raise_line(
                number,
                f"The line is longer than one ElevenReader document of {MAX_DOCUMENT_CHARS} characters",
                "Split the line into shorter paragraphs.",
            )
        parts.append(part)
    if not parts:
        _raise_input("The text file has no line to read", "Write the text to read, one paragraph per line.")
    return tuple(parts)


def _documents(parts: tuple[DocumentPart, ...], engine: ElevenReaderTtsEngine) -> list[tuple[DocumentPart, ...]]:
    documents: list[tuple[DocumentPart, ...]] = []
    current: list[DocumentPart] = []
    for part in parts:
        if current and engine.document_chars((*current, part)) > MAX_DOCUMENT_CHARS:
            documents.append(tuple(current))
            current = []
        current.append(part)
    documents.append(tuple(current))
    logger.info("Text split into documents", parts=len(parts), documents=len(documents))
    return documents


def _write_record(
    stem: Path, voice_alias: str, parts: tuple[DocumentPart, ...], results: list[DocumentResult]
) -> RecordResult:
    """Join, in part order, the stretch of the recording that spoke each part; an unspoken part gets an empty span."""
    takes: list[_Take] = [_take_of(result) for result in results]
    source: dict[str, int] = {}
    for number, recorded in enumerate(takes):
        for request_id in recorded.spoken:
            source.setdefault(request_id, number)
    output: bytearray = bytearray()
    output_ms: float = 0.0
    timings: list[PartTiming] = []
    pieces: list[Piece] = []
    for part in parts:
        index: int | None = source.get(part.request_id)
        if index is None:
            timings.append(PartTiming(request_id=part.request_id, start_ms=output_ms, end_ms=output_ms))
            continue
        take: _Take = takes[index]
        segment, start_ms, length_ms = _stretch(take, part.request_id)
        shift_ms: float = output_ms - start_ms
        timing: PartTiming = take.timings[part.request_id]
        timings.append(
            PartTiming(request_id=part.request_id, start_ms=timing.start_ms + shift_ms, end_ms=timing.end_ms + shift_ms)
        )
        pieces.append(shifted(take.pieces[part.request_id], shift_ms))
        output += segment
        output_ms += length_ms
    data: bytes = bytes(output)
    mp3, described, subtitles = stem.with_suffix(".mp3"), stem.with_suffix(".json"), stem.with_suffix(".srt")
    _write_atomic(mp3, data)
    duration_ms: float = frames_duration_ms(data)
    final: tuple[PartTiming, ...] = tuple(timings)
    lines: tuple[str, ...] = tuple(part.text for part in parts)
    write_json(
        described, audio=mp3.name, voice=voice_alias, duration_ms=duration_ms, lines=lines, timings=final, pieces=pieces
    )
    write_srt(subtitles, pieces)
    silent: tuple[int, ...] = tuple(index for index, timing in enumerate(final) if not timing.spoken)
    logger.info("Text recorded", parts=len(final), silent=len(silent), recordings=len(takes), duration_ms=duration_ms)
    return RecordResult(mp3=mp3, json=described, srt=subtitles, duration_ms=duration_ms, parts=final, silent=silent)


def _take_of(result: DocumentResult) -> _Take:
    timings: dict[str, PartTiming] = {timing.request_id: timing for timing in result.parts}
    return _Take(
        data=result.recording.read_bytes(),
        spoken=tuple(timing.request_id for timing in result.parts if timing.spoken),
        timings=timings,
        pieces=spoken_pieces(result.chunks, result.parts),
    )


def _stretch(take: _Take, request_id: str) -> tuple[bytes, float, float]:
    """Return the frames from the part's start (0 for the first spoken part) to the next spoken part or the end.

    Returns:
        The frames, their start on the recording timeline and their length.
    """
    order: int = take.spoken.index(request_id)
    start_ms: float = 0.0 if order == 0 else take.timings[request_id].start_ms
    rest, cut_ms = cut_before_ms(take.data, start_ms)
    if order + 1 == len(take.spoken):
        return rest, cut_ms, frames_duration_ms(rest)
    following: PartTiming = take.timings[take.spoken[order + 1]]
    tail, length_ms = cut_before_ms(rest, following.start_ms - cut_ms)
    return rest[: len(rest) - len(tail)], cut_ms, length_ms


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _raise_input(message: str, suggestion: str) -> Never:
    raise TtsInputError(context=ErrorContext(code=ErrorCode.TTS_INPUT_INVALID, message=message, suggestion=suggestion))


def _raise_input_from(error: Exception, message: str, suggestion: str) -> Never:
    context: ErrorContext = ErrorContext(code=ErrorCode.TTS_INPUT_INVALID, message=message, suggestion=suggestion)
    raise TtsInputError(context=context) from error


def _raise_line(number: int, message: str, suggestion: str, *, cause: Exception | None = None) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_INPUT_INVALID, message=message, suggestion=suggestion, details={"line": number}
    )
    raise TtsInputError(context=context) from cause
