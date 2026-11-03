from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

import pytest

from edp.engine.recorder import StreamRecorder
from edp.engine.service import part_spans, stream_timeline
from edp.engine.types import AlignmentChunk, DocumentPart
from edp.reading import text_lines
from edp.subtitles import Piece, json_text, split_sentences, split_words, spoken_pieces, srt_text
from edp.utils.mp3_frames import frames_duration_ms

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"


def _stream(name: str) -> tuple[tuple[AlignmentChunk, ...], float]:
    recorder = StreamRecorder(io.BytesIO())
    audio = b""
    for line in (FIXTURES / f"{name}.frames.jsonl").read_text(encoding="utf-8").splitlines():
        audio += base64.b64decode(json.loads(line).get("audio") or "")
        recorder.on_frame(line)
    return recorder.chunks, frames_duration_ms(audio)


def _texts(name: str, pieces: list[Piece], **fields: Any) -> tuple[str, object]:
    return srt_text(pieces), json.loads(json_text(audio=f"{name}.mp3", pieces=pieces, **fields))


def _expected(name: str) -> tuple[str, object]:
    return (
        (FIXTURES / f"{name}.srt").read_bytes().decode("utf-8"),
        json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")),
    )


def test_subtitles_open_document_without_parts_match_fixture() -> None:
    chunks, duration_ms = _stream("open-document")

    written = _texts(
        "open-document", [stream_timeline(chunks)], voice=None, lines=(), timings=(), duration_ms=duration_ms
    )

    assert written == _expected("open-document")


def test_subtitles_pasted_text_with_silent_part_match_fixture() -> None:
    chunks, duration_ms = _stream("pasted-text")
    lines = text_lines((FIXTURES / "pasted-text.txt").read_text(encoding="utf-8"))
    parts = tuple(DocumentPart(request_id=str(index), text=line) for index, line in enumerate(lines))
    timings = part_spans(chunks, parts)

    written = _texts(
        "pasted-text",
        list(spoken_pieces(chunks, timings).values()),
        voice="fronczewski",
        lines=lines,
        timings=timings,
        duration_ms=duration_ms,
    )

    assert written == _expected("pasted-text")


def test_subtitles_srt_bytes_match_fixture_exactly() -> None:
    chunks, _ = _stream("open-document")

    written = srt_text([stream_timeline(chunks)]).encode("utf-8")

    assert written == (FIXTURES / "open-document.srt").read_bytes()


def test_split_words_break_tag_is_no_word_and_ends_sentence() -> None:
    text = 'Ala ma <break time="0.6s"/> kota'
    piece: Piece = (text, [float(index) for index in range(len(text))], [index + 1.0 for index in range(len(text))])

    words = split_words(piece)

    assert [None if word is None else word.text for word in words] == ["Ala", "ma", None, "kota"]
    assert [sentence.text for sentence in split_sentences(piece)] == ["Ala ma", "kota"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Raz. Dwa.", ["Raz.", "Dwa."]),
        ("Raz. — dwa.", ["Raz. — dwa."]),
        ("Raz. dwa.", ["Raz. dwa."]),
        ("„Tak.” Nie.", ["„Tak.”", "Nie."]),
        ("Czekaj… Idę.", ["Czekaj…", "Idę."]),
    ],
)
def test_split_sentences_punctuation_and_next_word_decide_boundary(text: str, expected: list[str]) -> None:
    piece: Piece = (text, [0.0] * len(text), [1.0] * len(text))

    assert [sentence.text for sentence in split_sentences(piece)] == expected
