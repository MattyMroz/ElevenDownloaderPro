"""Words and sentences from streamed character timings, as the text of ``<name>.json`` and ``<name>.srt``."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from edp.engine.service import part_bounds, stream_timeline

if TYPE_CHECKING:
    from edp.engine.types import AlignmentChunk, PartTiming

__all__ = [
    "Piece",
    "Sentence",
    "Word",
    "json_text",
    "shifted",
    "split_sentences",
    "split_words",
    "spoken_pieces",
    "srt_text",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_BREAK_TAG: Final[re.Pattern[str]] = re.compile(r"<break[^>]*(?:/>|$)")
"""SSML pause the server inserts between paragraphs and after headings; may be cut off at the very end."""

_SENTENCE_END: Final[str] = ".!?…"
"""Characters that close a sentence when they end a word."""

_CLOSING_MARKS: Final[str] = "\"'”\u2019)]»"
"""Quotes and brackets that may follow the sentence-ending character."""

_DASHES: Final[str] = "-–—"
"""Word starts that continue the previous sentence, as in dialogue tags."""

_MS_PER_HOUR: Final[int] = 3_600_000
"""Milliseconds in one hour."""

_MS_PER_MINUTE: Final[int] = 60_000
"""Milliseconds in one minute."""

_MS_PER_SECOND: Final[int] = 1000
"""Milliseconds in one second."""

type Piece = tuple[str, list[float], list[float]]
"""Text with the start and end of every character in milliseconds; words and sentences never cross pieces."""


@dataclass(frozen=True, slots=True)
class Word:
    """One word with the start of its first and the end of its last character."""

    text: str
    start_ms: float
    end_ms: float


@dataclass(slots=True)
class Sentence:
    """Consecutive words read as one subtitle."""

    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Return the words joined by single spaces."""
        return " ".join(word.text for word in self.words)


def spoken_pieces(chunks: tuple[AlignmentChunk, ...], timings: tuple[PartTiming, ...]) -> dict[str, Piece]:
    """Return the characters of every spoken part of one recording, keyed by the part's request id.

    The part ranges come from the engine's ``part_bounds``, so separators and break tags never become words.
    """
    text, starts, ends = stream_timeline(chunks)
    return {
        timing.request_id: (text[first : last + 1], starts[first : last + 1], ends[first : last + 1])
        for timing, (first, last) in zip(timings, part_bounds(text), strict=True)
        if timing.spoken
    }


def shifted(piece: Piece, shift_ms: float) -> Piece:
    """Return *piece* moved by *shift_ms* on the timeline."""
    text, starts, ends = piece
    return text, [start + shift_ms for start in starts], [end + shift_ms for end in ends]


def split_words(piece: Piece) -> list[Word | None]:
    """Return the words in order, with None wherever a break tag forces a sentence boundary."""
    text, starts, ends = piece
    in_break: list[bool] = [False] * len(text)
    for match in _BREAK_TAG.finditer(text):
        in_break[match.start() : match.end()] = [True] * (match.end() - match.start())
    tokens: list[Word | None] = []
    word_start: int | None = None
    for index, char in enumerate([*text, " "]):
        boundary: bool = index == len(text) or in_break[index] or char.isspace()
        if boundary and word_start is not None:
            tokens.append(Word(text[word_start:index], starts[word_start], ends[index - 1]))
            word_start = None
        if index < len(text) and in_break[index] and (not tokens or tokens[-1] is not None):
            tokens.append(None)
        if not boundary and word_start is None:
            word_start = index
    return tokens


def split_sentences(piece: Piece) -> list[Sentence]:
    """Group words into sentences ended by punctuation before a new sentence start, or by a break tag."""
    sentences: list[Sentence] = []
    current: Sentence = Sentence()
    for token in split_words(piece):
        new_sentence: bool = token is None or (
            bool(current.words) and _ends_sentence(current.words[-1]) and _starts_sentence(token)
        )
        if new_sentence and current.words:
            sentences.append(current)
            current = Sentence()
        if token is not None:
            current.words.append(token)
    if current.words:
        sentences.append(current)
    return sentences


def srt_text(pieces: list[Piece]) -> str:
    """Return the SRT subtitles of the sentences of every piece, numbered from 1."""
    sentences: list[Sentence] = [sentence for piece in pieces for sentence in split_sentences(piece)]
    blocks: list[str] = [
        f"{number}\n{_srt_time(sentence.words[0].start_ms)} --> {_srt_time(sentence.words[-1].end_ms)}\n"
        f"{sentence.text}\n"
        for number, sentence in enumerate(sentences, start=1)
    ]
    return "\n".join(blocks)


def json_text(  # noqa: PLR0913 - the file schema has these independent fields
    *,
    audio: str,
    voice: str | None,
    duration_ms: float,
    lines: tuple[str, ...],
    timings: tuple[PartTiming, ...],
    pieces: list[Piece],
) -> str:
    """Return the recording description shared with the userscript: parts, words and the indexes of silent parts.

    Args:
        audio: File name of the MP3 next to it.
        voice: Voice alias, or None when the account voice read the document.
        duration_ms: Length of the MP3 on the server timeline.
        lines: Source text of every part, in order.
        timings: Timing of every part on the MP3 timeline, in the order of *lines*.
        pieces: Spoken characters on the MP3 timeline, in order.
    """
    data: dict[str, object] = {
        "audio": audio,
        "voice": voice,
        "duration_ms": duration_ms,
        "parts": [
            {
                "index": index,
                "text": line,
                "start_ms": timing.start_ms,
                "end_ms": timing.end_ms,
                "spoken": timing.spoken,
            }
            for index, (line, timing) in enumerate(zip(lines, timings, strict=True))
        ],
        "words": [
            {"text": word.text, "start_ms": word.start_ms, "end_ms": word.end_ms}
            for piece in pieces
            for word in split_words(piece)
            if word is not None
        ],
        "silent": [index for index, timing in enumerate(timings) if not timing.spoken],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _ends_sentence(word: Word) -> bool:
    return word.text.rstrip(_CLOSING_MARKS)[-1:] in _SENTENCE_END


def _starts_sentence(word: Word) -> bool:
    if word.text[0] in _DASHES:
        return False
    letter: str = next((char for char in word.text if char.isalpha()), "")
    return not letter.islower()


def _srt_time(ms: float) -> str:
    total: int = round(ms)
    hours, rest = divmod(total, _MS_PER_HOUR)
    minutes, rest = divmod(rest, _MS_PER_MINUTE)
    seconds, millis = divmod(rest, _MS_PER_SECOND)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
