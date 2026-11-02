from __future__ import annotations

import asyncio
import itertools
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from fakes import READ_ID, FakePage, FakeSession, FakeSite, ScriptedEngine, stream_frames

from edp import reading
from edp.engine import service
from edp.errors import TtsAuthError, TtsInputError, TtsTimeoutError
from edp.reading import read_id_from_url, record, text_lines
from edp.utils.mp3_frames import frames_duration_ms, iter_frames

if TYPE_CHECKING:
    from collections.abc import Callable

    from edp.engine.browser import ChromeSession

pytestmark = pytest.mark.unit

LINES = ("Raz.", "Dwa.", "Trzy.", "Pięć.")


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []

    async def instant(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", instant)
    return slept


def _text(tmp_path: Path, *lines: str, name: str = "rozdzial") -> Path:
    path = tmp_path / f"{name}.txt"
    path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    return path


def _use(monkeypatch: pytest.MonkeyPatch, engine: ScriptedEngine) -> None:
    monkeypatch.setattr(reading, "ElevenReaderTtsEngine", lambda config: engine)


def _fills(data: bytes) -> list[int]:
    return [fill for fill, _ in itertools.groupby(data[frame.offset + 4] for frame in iter_frames(data))]


def _frame_starts(data: bytes) -> dict[int, float]:
    starts: dict[int, float] = {}
    position = 0.0
    for frame in iter_frames(data):
        starts.setdefault(data[frame.offset + 4], position)
        position += frame.duration_ms
    return starts


def test_text_lines_strips_lines_and_skips_empty_ones() -> None:
    assert text_lines("  Raz. \n\n\r\n\tDwa.\r\n   \nTrzy.") == ("Raz.", "Dwa.", "Trzy.")


@pytest.mark.parametrize(
    "url",
    [
        f"https://elevenreader.io/reader/library/{READ_ID}",
        "https://elevenreader.io/reader/library/u%3Areadsecret42?tab=1",
        f"https://www.elevenreader.io/reader/books/{READ_ID}/",
    ],
)
def test_read_id_from_url_document_address_returns_read_id(url: str) -> None:
    assert read_id_from_url(url) == READ_ID


@pytest.mark.parametrize(
    "url", ["https://example.com/reader/library/u:x", "https://elevenreader.io/library/u:x", "u:x", ""]
)
def test_read_id_from_url_other_address_raises_input_error(url: str) -> None:
    with pytest.raises(TtsInputError):
        read_id_from_url(url)


def test_record_writes_mp3_json_and_srt_next_to_the_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = ScriptedEngine(tmp_path)
    _use(monkeypatch, engine)

    result = record(_text(tmp_path, *LINES), home=tmp_path)

    assert (result.mp3, result.json, result.srt) == (
        tmp_path / "rozdzial.mp3",
        tmp_path / "rozdzial.json",
        tmp_path / "rozdzial.srt",
    )
    described = json.loads(result.json.read_text(encoding="utf-8"))
    assert described["audio"] == "rozdzial.mp3"
    assert described["voice"] == "fronczewski"
    assert [part["text"] for part in described["parts"]] == list(LINES)
    assert [word["text"] for word in described["words"]] == list(LINES)
    assert described["silent"] == []
    assert described["duration_ms"] == frames_duration_ms(result.mp3.read_bytes())
    assert result.srt.read_text(encoding="utf-8").count(" --> ") == 4
    assert engine.documents == [("0", "1", "2", "3")]
    assert engine.closed


def test_record_out_dir_receives_the_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, ScriptedEngine(tmp_path))

    result = record(_text(tmp_path, *LINES), out_dir=tmp_path / "out", home=tmp_path)

    assert result.mp3 == tmp_path / "out" / "rozdzial.mp3"
    assert result.json.is_file()
    assert result.srt.is_file()


def test_record_parts_group_into_documents_within_the_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = ScriptedEngine(tmp_path)
    _use(monkeypatch, engine)
    monkeypatch.setattr(reading, "MAX_DOCUMENT_CHARS", len("Trzy.\n\n…\n\nPięć.\n"))

    result = record(_text(tmp_path, *LINES), home=tmp_path)

    assert sorted(engine.documents) == [("0", "1"), ("2", "3")]
    assert [part.request_id for part in result.parts] == ["0", "1", "2", "3"]
    assert _fills(result.mp3.read_bytes()) == [1, 2, 11, 12]


def test_record_line_longer_than_a_document_raises_input_error_with_line_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = ScriptedEngine(tmp_path)
    _use(monkeypatch, engine)
    monkeypatch.setattr(reading, "MAX_DOCUMENT_CHARS", 10)

    with pytest.raises(TtsInputError) as error:
        record(_text(tmp_path, "Raz.", "To jest za długa linia."), home=tmp_path)

    assert error.value.context.details == {"line": 3}
    assert engine.documents == []


@pytest.mark.parametrize("text", ["", "\n  \n", "…"])
def test_record_text_without_readable_lines_raises_input_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    _use(monkeypatch, ScriptedEngine(tmp_path))
    path = tmp_path / "pusty.txt"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(TtsInputError):
        record(path, home=tmp_path)


def test_record_missing_file_raises_input_error(tmp_path: Path) -> None:
    with pytest.raises(TtsInputError):
        record(tmp_path / "brak.txt", home=tmp_path)


def test_record_parts_silent_in_large_document_are_spoken_after_reading_them_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = ScriptedEngine(tmp_path, speaks_up_to={"Dwa.": 2, "Pięć.": 2})
    _use(monkeypatch, engine)

    result = record(_text(tmp_path, *LINES), home=tmp_path)

    assert engine.documents == [("0", "1", "2", "3"), ("1", "3")]
    assert result.silent == ()


def test_record_parts_silent_with_other_parts_are_spoken_when_read_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = ScriptedEngine(tmp_path, speaks_up_to={"Dwa.": 1, "Pięć.": 1})
    _use(monkeypatch, engine)

    result = record(_text(tmp_path, *LINES), home=tmp_path)

    assert engine.documents == [("0", "1", "2", "3"), ("1", "3"), ("1",), ("3",)]
    assert result.silent == ()


def test_record_part_silent_even_alone_stays_silent_after_bounded_rereads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = ScriptedEngine(tmp_path, speaks_up_to={"Dwa.": 0, "Pięć.": 1})
    _use(monkeypatch, engine)

    result = record(_text(tmp_path, *LINES), home=tmp_path)

    assert engine.documents == [("0", "1", "2", "3"), ("1", "3"), ("1",), ("3",)]
    assert result.silent == (1,)
    described = json.loads(result.json.read_text(encoding="utf-8"))
    assert described["silent"] == [1]
    assert [part["spoken"] for part in described["parts"]] == [True, False, True, True]
    assert [word["text"] for word in described["words"]] == ["Raz.", "Trzy.", "Pięć."]


def test_record_every_part_silent_reads_each_alone_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = ScriptedEngine(tmp_path, speaks_up_to={"Raz.": 0, "Dwa.": 0})
    _use(monkeypatch, engine)

    result = record(_text(tmp_path, "Raz.", "Dwa."), home=tmp_path)

    assert engine.documents == [("0", "1"), ("0",), ("1",)]
    assert result.silent == (0, 1)
    assert result.mp3.read_bytes() == b""


def test_record_reread_parts_are_joined_in_text_order_with_their_own_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, ScriptedEngine(tmp_path, speaks_up_to={"Dwa.": 2, "Pięć.": 2}))

    result = record(_text(tmp_path, *LINES), home=tmp_path)

    data = result.mp3.read_bytes()
    assert _fills(data) == [1, 2, 11, 3, 4, 12]
    starts = _frame_starts(data)
    assert [part.start_ms for part in result.parts] == pytest.approx([starts[1], starts[11], starts[3], starts[12]])
    assert all(part.spoken for part in result.parts)
    assert result.duration_ms == frames_duration_ms(data)
    words = json.loads(result.json.read_text(encoding="utf-8"))["words"]
    assert [word["text"] for word in words] == list(LINES)
    assert [word["start_ms"] for word in words] == pytest.approx([part.start_ms for part in result.parts])
    assert [word["end_ms"] for word in words] == pytest.approx([part.end_ms for part in result.parts])


def test_record_keeps_audio_streamed_before_the_first_part(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, ScriptedEngine(tmp_path, lead_frames=3))

    result = record(_text(tmp_path, *LINES), home=tmp_path)

    data = result.mp3.read_bytes()
    assert _fills(data) == [99, 1, 2, 3, 4]
    assert result.parts[0].start_ms == pytest.approx(_frame_starts(data)[1])
    assert result.parts[0].start_ms > 0


def test_record_transient_failure_is_retried_after_a_pause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    engine = ScriptedEngine(tmp_path, failures=[TtsTimeoutError("stalled")])
    _use(monkeypatch, engine)

    result = record(_text(tmp_path, *LINES), home=tmp_path)

    assert engine.calls == 2
    assert sleeps == [60.0]
    assert result.silent == ()


def test_record_transient_failure_after_every_retry_is_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    engine = ScriptedEngine(tmp_path, failures=[TtsTimeoutError("stalled") for _ in range(4)])
    _use(monkeypatch, engine)

    with pytest.raises(TtsTimeoutError):
        record(_text(tmp_path, *LINES), home=tmp_path)

    assert engine.calls == 4
    assert sleeps == [60.0, 120.0, 240.0]
    assert engine.closed
    assert not (tmp_path / "rozdzial.mp3").exists()


def test_record_fatal_failure_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = ScriptedEngine(tmp_path, failures=[TtsAuthError("signed out")])
    _use(monkeypatch, engine)

    with pytest.raises(TtsAuthError):
        record(_text(tmp_path, *LINES), home=tmp_path)

    assert engine.calls == 1


class _PlayedBeforePlay(FakePage):
    async def open_document(self, read_id: str) -> None:
        await super().open_document(read_id)
        assert self._recorder is not None
        self._recorder.on_frame(self.site.stream()[0])

    async def press_play(self) -> None:
        frames = self.site.frames
        self.site.frames = self.site.stream()[1:]
        try:
            await super().press_play()
        finally:
            self.site.frames = frames


def _fake_browser(site: FakeSite) -> Callable[[Path], ChromeSession]:
    def factory(profile_root: Path) -> ChromeSession:
        session = FakeSession(site)
        site.sessions.append(session)
        return cast("ChromeSession", session)

    return factory


@pytest.fixture
def fast_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "POLL_S", 0.001)
    monkeypatch.setattr(service, "END_IDLE_S", 0.0)
    monkeypatch.setattr(service, "START_TIMEOUT_S", 0.02)
    monkeypatch.setattr(service, "STALL_S", 0.1)
    monkeypatch.setattr(service, "SPEED_CHECK_S", 0.0)


@pytest.mark.usefixtures("fast_engine")
def test_record_chunk_streamed_before_play_is_in_mp3_and_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    texts = ("Pierwsza kwestia.", "Druga kwestia.")
    site = FakeSite(texts=texts, page_type=_PlayedBeforePlay)
    site.frames = stream_frames(texts)
    monkeypatch.setattr(service, "headless_session", _fake_browser(site))

    result = record(_text(tmp_path, *texts), home=tmp_path)

    assert site.events.index("open_document") < site.events.index("press_play")
    assert _fills(result.mp3.read_bytes()) == [1, 2]
    words = json.loads(result.json.read_text(encoding="utf-8"))["words"]
    assert [word["text"] for word in words] == ["Pierwsza", "kwestia.", "Druga", "kwestia."]
    assert words[0]["start_ms"] == 0.0


@pytest.mark.usefixtures("fast_engine")
def test_download_writes_three_files_without_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    site = FakeSite(texts=("Pierwsza kwestia. Druga kwestia.",), player_done=True)
    monkeypatch.setattr(service, "headless_session", _fake_browser(site))
    out = tmp_path / "ksiazka.mp3"

    result = reading.download(f"https://elevenreader.io/reader/library/{READ_ID}", out=out, home=tmp_path)

    assert (result.mp3, result.json, result.srt) == (out, tmp_path / "ksiazka.json", tmp_path / "ksiazka.srt")
    described = json.loads(result.json.read_text(encoding="utf-8"))
    assert described["parts"] == []
    assert described["silent"] == []
    assert described["voice"] is None
    assert [word["text"] for word in described["words"]] == ["Pierwsza", "kwestia.", "Druga", "kwestia."]
    assert site.uploaded == []
    assert site.deleted == []
