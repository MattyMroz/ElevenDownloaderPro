from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fakes import ADAM_ID, FRONCZEWSKI_ID, ScriptedEngine

from edp import cli, reading
from edp.cli import EXIT_CANCELLED, EXIT_INCOMPLETE, EXIT_REFUSED, EXIT_SUCCESS, EXIT_USAGE, main
from edp.engine.api_backend import save_cleanup, write_session
from edp.engine.types import AccountCleanup, AccountSettings

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[object, int]:
    code = main(list(argv))
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    return json.loads(out), code


def _text(tmp_path: Path, name: str, *lines: str) -> Path:
    path = tmp_path / f"{name}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_help_starts_with_usage_examples(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["--help"])

    help_text = capsys.readouterr().out
    assert stopped.value.code == 0
    assert help_text.splitlines()[2] == "examples:"
    assert "edp record chapter.txt --voice fronczewski" in help_text.split("\n\n")[1]
    assert "exit codes:" in help_text


def test_voices_prints_offered_voices(capsys: pytest.CaptureFixture[str]) -> None:
    value, code = _run(capsys, "voices")

    assert code == EXIT_SUCCESS
    assert value == [
        {"alias": "fronczewski", "label": "Piotr Fronczewski", "voice_id": FRONCZEWSKI_ID},
        {"alias": "adam", "label": "Adam", "voice_id": ADAM_ID},
    ]


def test_doctor_reports_chrome_session_and_owed_cleanup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "find_chrome", lambda: tmp_path / "chrome.exe")
    write_session(tmp_path, signed_in=True)
    save_cleanup(tmp_path, AccountCleanup(restore=AccountSettings(voice_id="previous-voice", speed=1.5)))

    value, code = _run(capsys, "doctor", "--home", str(tmp_path))

    assert code == EXIT_SUCCESS
    assert value == {"chrome": str(tmp_path / "chrome.exe"), "signed_in": True, "cleanup_pending": True}


def test_doctor_without_session_reports_unknown_sign_in(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "find_chrome", lambda: tmp_path / "chrome.exe")
    monkeypatch.setenv("EDP_HOME", str(tmp_path / "home"))

    value, code = _run(capsys, "doctor")

    assert code == EXIT_SUCCESS
    assert value == {"chrome": str(tmp_path / "chrome.exe"), "signed_in": None, "cleanup_pending": False}


def test_doctor_without_chrome_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "find_chrome", lambda: None)

    value, code = _run(capsys, "doctor", "--home", str(tmp_path))

    assert code == EXIT_REFUSED
    assert value == {"chrome": None, "signed_in": None, "cleanup_pending": False}


@pytest.mark.parametrize(
    "argv", [(), ("record",), ("record", "a.txt", "--voice", "dallin"), ("voices", "--unknown"), ("speak",)]
)
def test_bad_arguments_exit_with_usage_error_as_json(capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(list(argv))

    out = capsys.readouterr().out
    assert stopped.value.code == EXIT_USAGE
    assert json.loads(out)["error"]["code"] == "USAGE"


def test_record_writes_three_files_per_text_and_prints_results(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reading, "ElevenReaderTtsEngine", lambda config: ScriptedEngine(tmp_path))
    first, second = _text(tmp_path, "jeden", "Raz.", "Dwa."), _text(tmp_path, "dwa", "Trzy.")

    value, code = _run(capsys, "record", str(first), str(second), "--home", str(tmp_path), "--out", str(tmp_path / "o"))

    assert code == EXIT_SUCCESS
    assert isinstance(value, dict)
    results = value["results"]
    assert [result["mp3"] for result in results] == [str(tmp_path / "o" / "jeden.mp3"), str(tmp_path / "o" / "dwa.mp3")]
    for result in results:
        for key in ("mp3", "json", "srt"):
            assert (tmp_path / "o" / result[key]).is_file()
        assert result["silent"] == []
        assert result["duration_ms"] > 0


def test_record_with_part_silent_after_rereads_exits_incomplete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = ScriptedEngine(tmp_path, speaks_up_to={"Dwa.": 0})
    monkeypatch.setattr(reading, "ElevenReaderTtsEngine", lambda config: engine)

    value, code = _run(capsys, "record", str(_text(tmp_path, "jeden", "Raz.", "Dwa.")), "--home", str(tmp_path))

    assert code == EXIT_INCOMPLETE
    assert isinstance(value, dict)
    assert value["results"][0]["silent"] == [1]


def test_record_line_too_long_exits_with_usage_error_and_line_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reading, "ElevenReaderTtsEngine", lambda config: ScriptedEngine(tmp_path))
    monkeypatch.setattr(reading, "MAX_DOCUMENT_CHARS", 5)
    text = _text(tmp_path, "jeden", "Raz.", "Za długa linia.")

    value, code = _run(capsys, "record", str(text), "--home", str(tmp_path))

    assert code == EXIT_USAGE
    assert isinstance(value, dict)
    assert value["results"] == []
    assert value["error"]["details"] == {"line": 2}


def test_download_other_address_exits_with_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    value, code = _run(capsys, "download", "https://example.com/reader/library/u:x")

    assert code == EXIT_USAGE
    assert isinstance(value, dict)
    assert value["error"]["code"] == "TTS_INPUT_INVALID"


def test_ctrl_c_exits_cancelled_with_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "record", interrupted)

    value, code = _run(capsys, "record", str(_text(tmp_path, "jeden", "Raz.")))

    assert code == EXIT_CANCELLED
    assert isinstance(value, dict)
    assert value["error"]["code"] == "CANCELLED"
