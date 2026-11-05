"""Command line ``edp``: one JSON object on stdout, logs on stderr and fixed exit codes."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never

from edp.engine import DEFAULT_VOICE_ALIAS, VOICES, SignInOutcome, find_chrome, read_session
from edp.errors import EdpError, TransientError, TtsCancelledError, TtsInputError
from edp.reading import RecordResult, default_home, download, read_id_from_url, record, sign_in
from edp.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from loguru import Record

    from edp.engine import SessionRecord

__all__ = ["EXIT_CANCELLED", "EXIT_INCOMPLETE", "EXIT_REFUSED", "EXIT_SUCCESS", "EXIT_USAGE", "main"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

EXIT_SUCCESS: Final[int] = 0
"""The command did everything it was asked to."""

EXIT_REFUSED: Final[int] = 1
"""Refused: configuration, sign-in, voice, credits, missing Chrome, unwritable output or an unexpected error."""

EXIT_USAGE: Final[int] = 2
"""Unusable arguments or input: bad option, unreadable text, long line, bad address or output, resumed document."""

EXIT_INCOMPLETE: Final[int] = 3
"""Finished without everything: a part stayed silent after every reread, or a transient failure outlived retries."""

EXIT_CANCELLED: Final[int] = 4
"""Cancelled with Ctrl+C after the browser and the account were cleaned up."""

_DESCRIPTION: Final[str] = """\
examples:
  edp login                                         sign in once in a Chrome window
  edp record chapter.txt --voice fronczewski        write chapter.mp3, chapter.json, chapter.srt
  edp download https://elevenreader.io/reader/library/<read_id> --out book.mp3

Record ElevenReader speech as MP3 with part timings, word timings and SRT subtitles.
Every command prints one JSON value on stdout and logs on stderr; a failure prints
{"error": {"code", "message", "suggestion", "details"}}.

exit codes:
  0  success
  1  refused: configuration, sign-in, voice, credits, missing Chrome, unwritable output
     or an unexpected error (traceback on stderr)
  2  usage: bad arguments, unreadable text, a line too long, not a document address,
     --out without .mp3, a library document that resumes from the middle
  3  incomplete: a part stayed silent after rereads, or a transient failure outlived retries
  4  cancelled with Ctrl+C
"""
"""Help text shown under the usage line, starting with examples."""

_UNSAFE_NAME: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9_-]+")
"""Characters replaced in a read id used as a file name."""

_LOG_FORMAT: Final[str] = "{time:HH:mm:ss} {level: <7} {message}"
"""Start of every stderr log line; context fields follow it."""

type _Command = Callable[[argparse.Namespace], tuple[object, int]]
"""Handler of one subcommand returning the JSON value and the exit code."""


class _Parser(argparse.ArgumentParser):
    """Argument parser that reports a usage error as JSON on stdout before exiting with code 2."""

    def error(self, message: str) -> Never:
        """Print the error as JSON, the usage on stderr, and exit with ``EXIT_USAGE``."""
        _print({"error": {"code": "USAGE", "message": message, "suggestion": "Run edp --help.", "details": {}}})
        self.print_usage(sys.stderr)
        raise SystemExit(EXIT_USAGE)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one ``edp`` command and return its exit code."""
    _use_utf8()
    arguments: argparse.Namespace = _parser().parse_args(argv)
    root = get_logger()
    root.remove()
    sink: int = root.add(sys.stderr, level="INFO", format=_log_line, diagnose=False, backtrace=False)
    command: _Command = arguments.command
    try:
        value, code = command(arguments)
    except (KeyboardInterrupt, Exception) as error:  # noqa: BLE001 - the process boundary reports every failure as JSON
        value, code = _outcome(error)
    finally:
        root.remove(sink)
    _print(value)
    return code


def _parser() -> argparse.ArgumentParser:
    common: argparse.ArgumentParser = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--home",
        type=Path,
        default=None,
        help="directory with the Chrome profile and session.json (default: $EDP_HOME or ~/.edp)",
    )
    parser: argparse.ArgumentParser = _Parser(
        prog="edp", description=_DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(title="commands", required=True, metavar="COMMAND")
    login = commands.add_parser("login", parents=[common], help="sign in in a Chrome window and clean up the account")
    login.set_defaults(command=_login)
    doctor = commands.add_parser("doctor", parents=[common], help="check Chrome, the session and owed cleanup")
    doctor.set_defaults(command=_doctor)
    voices = commands.add_parser("voices", parents=[common], help="list the voices")
    voices.set_defaults(command=_voices)
    recorder = commands.add_parser("record", parents=[common], help="record text files, one paragraph per line")
    recorder.add_argument("texts", nargs="+", type=Path, metavar="FILE.txt")
    recorder.add_argument("--voice", choices=tuple(VOICES), default=DEFAULT_VOICE_ALIAS)
    recorder.add_argument("--out", type=Path, default=None, metavar="DIR", help="directory for the files")
    recorder.add_argument("--tags", action="store_true", help="send [square brackets] as Eleven v4 audio tags")
    recorder.set_defaults(command=_record)
    downloader = commands.add_parser("download", parents=[common], help="record a document of the library")
    downloader.add_argument("url", metavar="URL")
    downloader.add_argument("--out", type=Path, default=None, metavar="FILE.mp3")
    downloader.add_argument("--voice", choices=tuple(VOICES), default=None, help="default: the account voice")
    downloader.set_defaults(command=_download)
    return parser


def _login(arguments: argparse.Namespace) -> tuple[object, int]:
    outcome: SignInOutcome = sign_in(arguments.home)
    return {"outcome": outcome.value}, EXIT_SUCCESS if outcome is SignInOutcome.SIGNED_IN else EXIT_REFUSED


def _doctor(arguments: argparse.Namespace) -> tuple[object, int]:
    chrome: Path | None = find_chrome()
    session: SessionRecord | None = read_session(arguments.home or default_home())
    value: dict[str, object] = {
        "chrome": None if chrome is None else str(chrome),
        "signed_in": None if session is None else session.signed_in,
        "cleanup_pending": session is not None and session.cleanup_pending,
    }
    return value, EXIT_REFUSED if chrome is None else EXIT_SUCCESS


def _voices(arguments: argparse.Namespace) -> tuple[object, int]:
    del arguments
    return [{"alias": voice.alias, "label": voice.label, "voice_id": voice.voice_id} for voice in VOICES.values()], 0


def _record(arguments: argparse.Namespace) -> tuple[object, int]:
    done: list[dict[str, object]] = []
    try:
        recorded: tuple[RecordResult, ...] = record(
            *arguments.texts,
            voice=arguments.voice,
            out_dir=arguments.out,
            tags=arguments.tags,
            home=arguments.home,
            on_done=lambda text, result: done.append({"text": str(text), **_result_value(result)}),
        )
    except (KeyboardInterrupt, EdpError, OSError) as error:
        failure, code = _outcome(error)
        return {"results": done, **failure}, code
    results: list[dict[str, object]] = [
        {"text": str(text), **_result_value(result)} for text, result in zip(arguments.texts, recorded, strict=True)
    ]
    silent: bool = any(entry["silent"] for entry in results)
    return {"results": results}, EXIT_INCOMPLETE if silent else EXIT_SUCCESS


def _download(arguments: argparse.Namespace) -> tuple[object, int]:
    out: Path = arguments.out or Path.cwd() / f"{_UNSAFE_NAME.sub('-', read_id_from_url(arguments.url))}.mp3"
    result: RecordResult = download(arguments.url, out=out, voice=arguments.voice, home=arguments.home)
    return {"results": [{"url": arguments.url, **_result_value(result)}]}, EXIT_SUCCESS


def _result_value(result: RecordResult) -> dict[str, object]:
    return {
        "mp3": str(result.mp3),
        "json": str(result.json),
        "srt": str(result.srt),
        "duration_ms": result.duration_ms,
        "silent": list(result.silent),
    }


def _outcome(error: BaseException) -> tuple[dict[str, object], int]:
    if isinstance(error, KeyboardInterrupt):
        return _failure("CANCELLED", "Cancelled with Ctrl+C", ""), EXIT_CANCELLED
    if isinstance(error, EdpError):
        return _error_value(error), _exit_code(error)
    if isinstance(error, OSError):
        details: dict[str, object] = {} if error.filename is None else {"path": str(error.filename)}
        message: str = error.strerror or type(error).__name__
        return _failure(
            "IO_ERROR", message, "Check the paths, their permissions and free disk space.", details
        ), EXIT_REFUSED
    logger.opt(exception=error).error("edp failed unexpectedly")
    return _failure(
        "INTERNAL", f"Unexpected {type(error).__name__}", "Report the traceback logged above.", {}
    ), EXIT_REFUSED


def _error_value(error: EdpError) -> dict[str, object]:
    return _failure(error.context.code.value, str(error), error.context.suggestion, error.context.details)


def _failure(code: str, message: str, suggestion: str, details: dict[str, object] | None = None) -> dict[str, object]:
    sys.stderr.write(f"edp: {message}\n")
    if suggestion:
        sys.stderr.write(f"edp: {suggestion}\n")
    return {"error": {"code": code, "message": message, "suggestion": suggestion, "details": details or {}}}


def _exit_code(error: EdpError) -> int:
    if isinstance(error, TtsCancelledError):
        return EXIT_CANCELLED
    if isinstance(error, TtsInputError):
        return EXIT_USAGE
    if isinstance(error, TransientError):
        return EXIT_INCOMPLETE
    return EXIT_REFUSED


def _log_line(record: Record) -> str:
    details: str = " ".join(f"{key}={value}" for key, value in record["extra"].items() if key != "logger_name")
    escaped: str = details.replace("{", "{{").replace("}", "}}")
    return f"{_LOG_FORMAT} {escaped}\n{{exception}}" if escaped else f"{_LOG_FORMAT}\n{{exception}}"


def _print(value: object) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def _use_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and stream.encoding.casefold() != "utf-8":
            stream.reconfigure(encoding="utf-8")
