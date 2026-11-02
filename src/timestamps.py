"""Turn ElevenReader character timings into sentence subtitles (.srt) and word timings (.json).

The recorder stores every audio chunk's alignment as one line of <name>.align.jsonl with the chunk's offset in the
recording. This module joins those lines into one timeline, drops <break .../> tags, splits the text into words and
sentences and writes <name>.srt and <name>.json next to it.

Usage:
    uv run src/timestamps.py workspace/output/book.align.jsonl
"""

import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

# ── Constants ────────────────────────────────────────────────────────────────

BITRATES_KBPS: Final[tuple[int, ...]] = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
"""MPEG-1 Layer III bitrate table indexed by the header's bitrate bits."""

SAMPLE_RATES: Final[tuple[int, ...]] = (44100, 48000, 32000)
"""MPEG-1 sample rate table indexed by the header's sample rate bits."""

SAMPLES_PER_FRAME: Final[int] = 1152
"""Samples in one MPEG-1 Layer III frame."""

ID3_HEADER_SIZE: Final[int] = 10
"""Bytes in an ID3v2 header before the tag body."""

BREAK_TAG: Final[re.Pattern[str]] = re.compile(r"<break[^>]*(?:/>|$)")
"""SSML pause that ElevenReader inserts between paragraphs and after headings; may be cut off at the very end."""

SENTENCE_END: Final[str] = ".!?…"
"""Characters that close a sentence when they end a word."""

CLOSING_MARKS: Final[str] = "\"'”’)]»"
"""Quotes and brackets that may follow the sentence-ending character."""

DASHES: Final[str] = "-–—"
"""Word starts that continue the previous sentence, as in dialogue tags."""

RESUME_MARK: Final[str] = "<break/>"
"""Boundary inserted where an appended recording session begins."""


@dataclass
class Word:
    text: str
    start_ms: float
    end_ms: float


@dataclass
class Sentence:
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def mp3_frames(data: bytes) -> Iterator[tuple[int, int]]:
    """Yield the byte offset and sample rate of every MPEG-1 Layer III frame, skipping ID3 tags and stray bytes."""
    i: int = 0
    while i + 4 <= len(data):
        if data[i] == 0xFF and data[i + 1] & 0xFE == 0xFA:
            bitrate: int = BITRATES_KBPS[data[i + 2] >> 4]
            rate_index: int = (data[i + 2] >> 2) & 3
            if bitrate and rate_index < len(SAMPLE_RATES):
                sample_rate: int = SAMPLE_RATES[rate_index]
                yield i, sample_rate
                i += 144_000 * bitrate // sample_rate + ((data[i + 2] >> 1) & 1)
                continue
        if data[i : i + 3] == b"ID3" and i + ID3_HEADER_SIZE <= len(data):
            size: int = (data[i + 6] << 21) | (data[i + 7] << 14) | (data[i + 8] << 7) | data[i + 9]
            i += ID3_HEADER_SIZE + size
            continue
        i += 1


def mp3_duration_ms(data: bytes) -> float:
    """Return the playing time of MPEG-1 Layer III data."""
    return sum(SAMPLES_PER_FRAME * 1000 / rate for _, rate in mp3_frames(data))


def mp3_cut_ms(data: bytes, cut_ms: float) -> tuple[bytes, float]:
    """Drop the frames that start before cut_ms; return the remaining data and the playing time dropped."""
    dropped: float = 0.0
    for offset, rate in mp3_frames(data):
        if dropped >= cut_ms - 0.5:  # float sums of 26.12 ms frames land a hair short
            return data[offset:], dropped
        dropped += SAMPLES_PER_FRAME * 1000 / rate
    return b"", dropped


def load_timeline(align_path: Path) -> tuple[str, list[float], list[float]]:
    """Join all chunks into one text with absolute start and end times per character."""
    chars: list[str] = []
    starts: list[float] = []
    ends: list[float] = []
    for line in align_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        chunk: dict[str, Any] = json.loads(line)
        offset: float = float(chunk["offset_ms"])
        if chunk.get("resume"):
            chars.extend(RESUME_MARK)
            starts.extend([offset] * len(RESUME_MARK))
            ends.extend([offset] * len(RESUME_MARK))
        for ch, start, duration in zip(chunk["chars"], chunk["start_ms"], chunk["dur_ms"], strict=True):
            chars.append(ch)
            starts.append(offset + start)
            ends.append(offset + start + duration)
    return "".join(chars), starts, ends


def ends_sentence(word: Word) -> bool:
    return word.text.rstrip(CLOSING_MARKS)[-1:] in SENTENCE_END


def starts_sentence(word: Word) -> bool:
    """Tell whether a word can open a new sentence; a dash or lowercase start continues the previous one."""
    if word.text[0] in DASHES:
        return False
    letter: str = next((c for c in word.text if c.isalpha()), "")
    return not letter.islower()


def split_words(text: str, starts: list[float], ends: list[float]) -> list[Word | None]:
    """Return the words in order, with None wherever a break tag forces a sentence boundary."""
    in_break: list[bool] = [False] * len(text)
    for match in BREAK_TAG.finditer(text):
        in_break[match.start() : match.end()] = [True] * (match.end() - match.start())

    tokens: list[Word | None] = []
    word_start: int | None = None
    for k, ch in enumerate([*text, " "]):
        boundary: bool = k == len(text) or in_break[k] or ch.isspace()
        if boundary and word_start is not None:
            tokens.append(Word(text[word_start:k], starts[word_start], ends[k - 1]))
            word_start = None
        if k < len(text) and in_break[k] and (not tokens or tokens[-1] is not None):
            tokens.append(None)
        if not boundary and word_start is None:
            word_start = k
    return tokens


def split_sentences(text: str, starts: list[float], ends: list[float]) -> list[Sentence]:
    """Group words into sentences ended by punctuation before a new sentence start, or by a break tag."""
    sentences: list[Sentence] = []
    current: Sentence = Sentence()
    for token in split_words(text, starts, ends):
        new_sentence: bool = token is None or (
            bool(current.words) and ends_sentence(current.words[-1]) and starts_sentence(token)
        )
        if new_sentence and current.words:
            sentences.append(current)
            current = Sentence()
        if token is not None:
            current.words.append(token)
    if current.words:
        sentences.append(current)
    return sentences


def srt_time(ms: float) -> str:
    total: int = round(ms)
    hours, rest = divmod(total, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def write_srt(sentences: list[Sentence], path: Path) -> None:
    blocks: list[str] = [
        f"{n}\n{srt_time(s.words[0].start_ms)} --> {srt_time(s.words[-1].end_ms)}\n{s.text}\n"
        for n, s in enumerate(sentences, start=1)
    ]
    path.write_text("\n".join(blocks), encoding="utf-8")


def write_json(sentences: list[Sentence], path: Path) -> None:
    def seconds(ms: float) -> float:
        return round(ms / 1000, 3)

    data: dict[str, list[dict[str, object]]] = {
        "sentences": [
            {
                "text": s.text,
                "start": seconds(s.words[0].start_ms),
                "end": seconds(s.words[-1].end_ms),
                "words": [{"text": w.text, "start": seconds(w.start_ms), "end": seconds(w.end_ms)} for w in s.words],
            }
            for s in sentences
        ]
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def build_subtitles(align_path: Path) -> int:
    """Write <name>.srt and <name>.json from <name>.align.jsonl and return the number of sentences."""
    sentences: list[Sentence] = split_sentences(*load_timeline(align_path))
    stem: str = align_path.name.removesuffix(".align.jsonl")
    write_srt(sentences, align_path.with_name(f"{stem}.srt"))
    write_json(sentences, align_path.with_name(f"{stem}.json"))
    return len(sentences)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: uv run src/timestamps.py <name>.align.jsonl")
    print(f"{build_subtitles(Path(sys.argv[1]))} sentences written")
