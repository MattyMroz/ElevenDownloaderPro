"""Recording of ElevenReader stream frames into one MP3 file and in-memory character timings."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from typing import TYPE_CHECKING, Final

from edp.utils.logger import get_logger
from edp.utils.mp3_frames import cut_before_ms, frames_duration_ms

from .constants import (
    MIN_DEDUP_BYTES,
    MIN_PROBE_CHARS,
    SILENT_CHUNK_MIN_LETTERS,
    SILENT_CHUNK_MS_PER_LETTER,
    TAIL_CHARS,
)
from .types import AlignmentChunk

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import BinaryIO

__all__ = ["StreamRecorder"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TAG: Final[re.Pattern[str]] = re.compile(r"<[^>]*>")
"""Markup the server sends with the text, such as SSML pauses; it holds no spoken letters."""

_LETTER: Final[re.Pattern[str]] = re.compile(r"\w")
"""One letter or digit of the chunk text counted against its audio."""


class StreamRecorder:
    """Append audio chunks of the stream to *output*, skipping duplicates and text repeated after a reconnect."""

    def __init__(self, output: BinaryIO) -> None:
        """Record into the open binary *output*, starting at time zero."""
        self._output: BinaryIO = output
        self._offset_ms: float = 0.0
        self._audio_bytes: int = 0
        self._chars: int = 0
        self._chunks: list[AlignmentChunk] = []
        self._seen: set[bytes] = set()
        self._tail: str = ""
        self._expect: str | None = None
        self._expect_anchored: bool = False
        self._listening_speed: float | None = None
        self._stopped: bool = False
        self._write_error: OSError | None = None

    @property
    def audio_bytes(self) -> int:
        """Return the number of audio bytes written."""
        return self._audio_bytes

    @property
    def chars(self) -> int:
        """Return the number of characters received with the written audio."""
        return self._chars

    @property
    def listening_speed(self) -> float | None:
        """Return the reading speed the page last streamed at, or None before the first frame sent."""
        return self._listening_speed

    @property
    def write_error(self) -> OSError | None:
        """Return the error that stopped writing the recording, or None while writing works."""
        return self._write_error

    @property
    def chunks(self) -> tuple[AlignmentChunk, ...]:
        """Return the character timings of every written chunk in recording order."""
        return tuple(self._chunks)

    def stop(self) -> None:
        """Ignore every later frame, so nothing writes after the output closes."""
        self._stopped = True

    def on_sent(self, payload: str | bytes) -> None:
        """Track the reading speed carried by a frame the page sends; the server picks the voice model from it."""
        data: dict[str, object] | None = None if self._stopped else _json_object(payload)
        speed: object = None if data is None else data.get("listening_speed")
        if isinstance(speed, bool) or not isinstance(speed, int | float):
            return
        self._listening_speed = float(speed)

    def on_frame(self, payload: str | bytes) -> None:
        """Record the audio and character timings of one frame the server sends."""
        data: dict[str, object] | None = None if self._stopped else _json_object(payload)
        if data is None:
            return
        if data.get("type") == "config" and self._chars:
            self._expect, self._expect_anchored = self._tail, False
        audio: object = data.get("audio")
        if not isinstance(audio, str) or not audio:
            return
        try:
            chunk: bytes = base64.b64decode(audio, validate=True)
        except binascii.Error:
            logger.warning("ElevenReader frame carried undecodable audio")
            return
        self._write_chunk(chunk, _alignment(data))

    def _write_chunk(self, chunk: bytes, alignment: AlignmentChunk | None) -> None:
        chars: tuple[str, ...] = () if alignment is None else alignment.chars
        if len(chunk) >= MIN_DEDUP_BYTES:
            digest: bytes = hashlib.sha1(chunk + json.dumps(chars).encode(), usedforsecurity=False).digest()
            if digest in self._seen:
                logger.debug("ElevenReader duplicate chunk skipped", size=len(chunk))
                return
            self._seen.add(digest)
        if alignment is not None:
            repeated: int = self._repeated_prefix("".join(chars))
            if repeated == len(chars):
                logger.debug("ElevenReader chunk repeated after reconnect skipped", chars=repeated)
                return
            if repeated:
                chunk, alignment = _trim_chunk(chunk, alignment, repeated)
                logger.debug("ElevenReader chunk trimmed after reconnect", chars=repeated)
        try:
            self._output.write(chunk)
            self._output.flush()
        except OSError as error:
            self._write_error, self._stopped = error, True
            logger.warning("ElevenReader recording could not be written", error_class=type(error).__name__)
            return
        self._audio_bytes += len(chunk)
        audio_ms: float = frames_duration_ms(chunk)
        if alignment is not None:
            self._keep_alignment(alignment, audio_ms)
        self._offset_ms += audio_ms

    def _keep_alignment(self, alignment: AlignmentChunk, audio_ms: float) -> None:
        text: str = "".join(alignment.chars)
        letters: int = len(_LETTER.findall(_TAG.sub("", text)))
        silent: bool = letters >= SILENT_CHUNK_MIN_LETTERS and audio_ms < SILENT_CHUNK_MS_PER_LETTER * letters
        if silent:
            logger.warning(
                "ElevenReader chunk carried text without speech",
                chunk=len(self._chunks),
                letters=letters,
                audio_ms=round(audio_ms, 1),
            )
        self._chunks.append(
            AlignmentChunk(
                offset_ms=self._offset_ms,
                chars=alignment.chars,
                starts_ms=alignment.starts_ms,
                durations_ms=alignment.durations_ms,
                silent=silent,
            ),
        )
        self._chars += len(text)
        self._tail = (self._tail + text)[-TAIL_CHARS:]

    def _repeated_prefix(self, text: str) -> int:
        expect: str | None = self._expect
        if expect is None:
            return 0
        if not self._expect_anchored and len(text) < MIN_PROBE_CHARS:
            return 0
        starts: Iterator[int] = iter((0,)) if self._expect_anchored else _rfind_all(expect, text[:MIN_PROBE_CHARS])
        for at in starts:
            if expect.startswith(text, at):
                self._expect, self._expect_anchored = expect[at + len(text) :] or None, True
                return len(text)
            if len(expect) - at <= len(text) and text.startswith(expect[at:]):
                self._expect = None
                return len(expect) - at
        self._expect = None
        return 0


def _json_object(payload: str | bytes) -> dict[str, object] | None:
    if isinstance(payload, bytes):
        return None
    try:
        data: object = json.loads(payload)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _alignment(data: dict[str, object]) -> AlignmentChunk | None:
    raw: object = data.get("alignment") or data.get("normalizedAlignment")
    if not isinstance(raw, dict):
        return None
    chars: object = raw.get("chars")
    starts: object = raw.get("charStartTimesMs")
    durations: object = raw.get("charDurationsMs")
    if not isinstance(chars, list) or not chars or not isinstance(starts, list) or not isinstance(durations, list):
        return None
    if not len(chars) == len(starts) == len(durations):
        return None
    try:
        return AlignmentChunk(
            offset_ms=0.0,
            chars=tuple(str(char) for char in chars),
            starts_ms=tuple(float(value) for value in starts),
            durations_ms=tuple(float(value) for value in durations),
        )
    except TypeError, ValueError:
        return None


def _rfind_all(text: str, sub: str) -> Iterator[int]:
    at: int = text.rfind(sub)
    while at >= 0:
        yield at
        at = text.rfind(sub, 0, at + len(sub) - 1)


def _trim_chunk(chunk: bytes, alignment: AlignmentChunk, drop: int) -> tuple[bytes, AlignmentChunk]:
    remaining: bytes
    cut_ms: float
    remaining, cut_ms = cut_before_ms(chunk, alignment.starts_ms[drop])
    trimmed: AlignmentChunk = AlignmentChunk(
        offset_ms=0.0,
        chars=alignment.chars[drop:],
        starts_ms=tuple(max(0.0, start - cut_ms) for start in alignment.starts_ms[drop:]),
        durations_ms=alignment.durations_ms[drop:],
    )
    return remaining, trimmed
