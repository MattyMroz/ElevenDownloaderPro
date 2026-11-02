from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rich.text import Text

from ..console import (
    _has_rich_markup,
    _highlight_outside_rich_markup,
    _patched_console_print,
    auto_highlight_text,
    normalize_numbers,
)


def styled(text: Text, style: str) -> list[str]:
    return [text.plain[span.start : span.end] for span in text.spans if str(span.style) == style]


class TestNormalizeNumbers:
    def test_comma_to_dot(self) -> None:
        assert normalize_numbers("1,5") == "1.5"

    def test_multiple_commas(self) -> None:
        assert normalize_numbers("1,5 and 2,3") == "1.5 and 2.3"

    def test_no_numbers(self) -> None:
        assert normalize_numbers("hello world") == "hello world"

    def test_already_dot(self) -> None:
        assert normalize_numbers("1.5") == "1.5"

    def test_comma_not_between_digits(self) -> None:
        assert normalize_numbers("a,b") == "a,b"

    def test_empty_string(self) -> None:
        assert normalize_numbers("") == ""

    def test_mixed(self) -> None:
        assert normalize_numbers("values: 1,5 and 2.3") == "values: 1.5 and 2.3"


class TestHasRichMarkup:
    def test_plain_text(self) -> None:
        assert _has_rich_markup("hello world") is False

    def test_known_prefix_bold(self) -> None:
        assert _has_rich_markup("[bold]text[/bold]") is True

    def test_known_prefix_closing(self) -> None:
        assert _has_rich_markup("[/bold]") is True

    def test_known_prefix_color(self) -> None:
        assert _has_rich_markup("[red]text here[/red]") is True

    def test_known_prefix_color_variant(self) -> None:
        assert _has_rich_markup("[red_bold]text[/red_bold]") is True

    def test_false_positive_redis_rejected(self) -> None:
        assert _has_rich_markup("[redis_connection]") is False

    def test_false_positive_blacklist_rejected(self) -> None:
        assert _has_rich_markup("[blacklist]") is False

    def test_false_positive_redirect_rejected(self) -> None:
        assert _has_rich_markup("[redirect]") is False

    def test_known_prefix_repr(self) -> None:
        assert _has_rich_markup("[repr.number]42[/repr.number]") is True

    def test_generic_tag_pair(self) -> None:
        assert _has_rich_markup("[custom_style]text[/custom_style]") is True

    def test_unmatched_brackets(self) -> None:
        assert _has_rich_markup("[not a tag") is False

    def test_empty_string(self) -> None:
        assert _has_rich_markup("") is False


class TestAutoHighlightText:
    def test_plain_text_unchanged(self) -> None:
        result = auto_highlight_text("hello")
        assert result.plain == "hello"
        assert not result.spans

    def test_number_highlighted(self) -> None:
        result = auto_highlight_text("value 123")
        assert styled(result, "repr.number") == ["123"]

    def test_float_highlighted(self) -> None:
        result = auto_highlight_text("pi is 3.14")
        assert styled(result, "repr.number") == ["3.14"]

    def test_url_highlighted_blue(self) -> None:
        result = auto_highlight_text("visit https://example.com")
        assert styled(result, "repr.url") == ["https://example.com"]

    def test_true_highlighted(self) -> None:
        result = auto_highlight_text("value is True")
        assert styled(result, "repr.bool_true") == ["True"]

    def test_false_highlighted(self) -> None:
        result = auto_highlight_text("value is False")
        assert styled(result, "repr.bool_false") == ["False"]

    def test_none_highlighted(self) -> None:
        result = auto_highlight_text("value is None")
        assert styled(result, "repr.none") == ["None"]

    def test_already_marked_text_keeps_markup_styling(self) -> None:
        result = auto_highlight_text("[bold]already marked[/bold]")
        assert result.plain == "already marked"
        assert styled(result, "bold") == ["already marked"]

    def test_empty_string(self) -> None:
        result = auto_highlight_text("")
        assert result.plain == ""

    def test_absolute_path(self) -> None:
        result = auto_highlight_text("Loading /home/user/.cache/models/v2.1.0")
        assert styled(result, "repr.path") == ["/home/user/.cache/models/v2.1.0"]

    def test_relative_path_3_segments(self) -> None:
        result = auto_highlight_text("saved to output/dir_01/sub_03/")
        assert styled(result, "repr.path") == ["output/dir_01/sub_03/"]

    def test_relative_path_with_extension(self) -> None:
        result = auto_highlight_text("Processing: dir_01/file_01.dat")
        assert styled(result, "repr.path") == ["dir_01/file_01.dat"]

    def test_relative_path_with_long_extension(self) -> None:
        result = auto_highlight_text("hashing vae/flux2-vae.safetensors")
        assert styled(result, "repr.path") == ["vae/flux2-vae.safetensors"]

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param(r"C:\Users\me\output\[draft] Report Final - v2 (2024).pdf", id="single-bracket"),
            pytest.param(r"C:\data\output\[backup] Data Set - 03 (1080p) [checksum].zip", id="two-brackets-parens"),
            pytest.param(
                r"C:\proj\workspace\TASK [module.core] Build - 01 [stage-2] run - 2.00s.log",
                id="space-prefixed-brackets",
            ),
            pytest.param(r"C:\Users\me\output\[Draft] Report Final - v2 (2024).pdf", id="uppercase-bracket"),
            pytest.param(r"/home/user/[a] file (x) [b].txt", id="posix-brackets"),
            pytest.param(r"output\dir\[X] plain.ass", id="relative-bracket"),
            pytest.param(r"C:\ws\[label] Sample Show II - 01.displayed.ass", id="multi-dot-extension"),
        ],
    )
    def test_bracketed_path_preserved_and_colored(self, path: str) -> None:
        result = auto_highlight_text(path)

        assert result.plain == path
        assert styled(result, "repr.path") == [path]

    def test_path_does_not_match_fraction(self) -> None:
        result = auto_highlight_text("24/24 items")
        assert styled(result, "repr.path") == []
        assert styled(result, "repr.number") == ["24/24"]

    @pytest.mark.parametrize("text", ["a, b, c", "Done 5 - Failed 0"])
    def test_path_does_not_match_status_text(self, text: str) -> None:
        assert styled(auto_highlight_text(text), "repr.path") == []

    def test_posix_path_stops_before_trailing_words(self) -> None:
        result = auto_highlight_text("path /home/user/file done extra words here")
        assert result.plain == "path /home/user/file done extra words here"
        assert styled(result, "repr.path") == ["/home/user/file"]

    def test_slashed_words_in_sentence_are_not_a_path(self) -> None:
        result = auto_highlight_text("24/24 done but a/b/c is path")
        assert styled(result, "repr.path") == []
        assert "24/24" in styled(result, "repr.number")

    def test_fraction_with_words_is_not_a_path(self) -> None:
        result = auto_highlight_text("progress 5/10 items remaining")
        assert styled(result, "repr.path") == []
        assert styled(result, "repr.number") == ["5/10"]

    def test_slash_separated_number_sequence_is_one_highlighted_span(self) -> None:
        result = auto_highlight_text("tokens 20189/20255/40444")
        assert styled(result, "repr.number") == ["20189/20255/40444"]

    def test_status_summary_with_middle_dot_is_not_a_path(self) -> None:
        result = auto_highlight_text("Done 5 · Failed 0")
        assert styled(result, "repr.path") == []

    def test_drive_path_stops_before_trailing_words(self) -> None:
        result = auto_highlight_text(r"Saved C:\out\[draft] final.ass in 1.33s")
        assert result.plain == r"Saved C:\out\[draft] final.ass in 1.33s"
        assert styled(result, "repr.path") == [r"C:\out\[draft] final.ass"]
        assert styled(result, "repr.number") == ["1.33s"]

    def test_drive_path_stops_at_first_extension(self) -> None:
        result = auto_highlight_text(r"C:\out\file.ass then see readme.txt")
        assert styled(result, "repr.path") == [r"C:\out\file.ass"]

    def test_posix_path_at_end_of_sentence(self) -> None:
        result = auto_highlight_text("wrote /var/log/app/output.log")
        assert styled(result, "repr.path") == ["/var/log/app/output.log"]

    def test_posix_dir_with_trailing_slash_in_sentence(self) -> None:
        result = auto_highlight_text("saved to /tmp/out/ then continued work")
        assert styled(result, "repr.path") == ["/tmp/out/"]  # noqa: S108 — regex input text, not a real path

    def test_relative_multi_segment_file_path(self) -> None:
        result = auto_highlight_text("compiled src/pkg/module_a/main.py ok")
        assert styled(result, "repr.path") == ["src/pkg/module_a/main.py"]

    def test_drive_dir_without_extension(self) -> None:
        result = auto_highlight_text(r"scan C:\Users\me\output now")
        assert styled(result, "repr.path") == [r"C:\Users\me\output"]

    def test_fraction_with_unit_is_not_a_path(self) -> None:
        result = auto_highlight_text("speed 3/4.5s done")
        assert styled(result, "repr.path") == []

    def test_digit_first_extension_still_a_path(self) -> None:
        result = auto_highlight_text("stored in data/backup.7z ok")
        assert styled(result, "repr.path") == ["data/backup.7z"]

    def test_numeric_segment_with_letter_extension_still_a_path(self) -> None:
        result = auto_highlight_text("archived 2024/report.pdf ok")
        assert styled(result, "repr.path") == ["2024/report.pdf"]

    def test_posix_path_inside_parens(self) -> None:
        result = auto_highlight_text("(see /var/log/x.log)")
        assert result.plain == "(see /var/log/x.log)"
        assert styled(result, "repr.path") == ["/var/log/x.log"]

    def test_quoted_drive_path_stops_at_quote(self) -> None:
        result = auto_highlight_text(r'"C:\out\file.ass" saved')
        assert styled(result, "repr.path") == [r"C:\out\file.ass"]

    def test_sentence_period_not_part_of_path(self) -> None:
        result = auto_highlight_text("see /home/user/file. Next line")
        assert styled(result, "repr.path") == ["/home/user/file"]

    def test_single_posix_dir_with_trailing_slash_is_a_path(self) -> None:
        result = auto_highlight_text("GET /users/ 200")
        assert styled(result, "repr.path") == ["/users/"]
        assert styled(result, "repr.number") == ["200"]

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param(r"C:\My Documents\report.pdf", id="spaced-dir"),
            pytest.param(r"C:\Program Files\app\data.bin", id="spaced-dir-nested"),
            pytest.param(r"C:\Users\John Smith\output\file.txt", id="spaced-user-dir"),
            pytest.param("/home/user/My Documents/report.pdf", id="posix-spaced-dir"),
        ],
    )
    def test_spaced_intermediate_segments_match_fully(self, path: str) -> None:
        result = auto_highlight_text(path)
        assert result.plain == path
        assert styled(result, "repr.path") == [path]

    def test_spaced_dir_path_in_sentence(self) -> None:
        result = auto_highlight_text(r"Saved C:\My Documents\report.pdf in 1.33s")
        assert styled(result, "repr.path") == [r"C:\My Documents\report.pdf"]
        assert styled(result, "repr.number") == ["1.33s"]

    def test_spaced_dir_without_extension_stays_bounded(self) -> None:
        result = auto_highlight_text(r"open C:\My Documents now")
        assert styled(result, "repr.path") == [r"C:\My"]

    def test_version_v_prefixed(self) -> None:
        result = auto_highlight_text("MyApp v2.1.0 starting")
        assert styled(result, "repr.number") == ["v2.1.0"]

    def test_version_dotted_3_segments(self) -> None:
        result = auto_highlight_text("Python 3.13.11")
        assert styled(result, "repr.number") == ["3.13.11"]

    def test_version_with_build_metadata(self) -> None:
        result = auto_highlight_text("torch 2.6.0+cu128")
        assert styled(result, "repr.number") == ["2.6.0+cu128"]

    def test_version_with_prerelease_and_build_suffixes(self) -> None:
        result = auto_highlight_text("release v2.0.0-rc1+build.5 ready")
        assert result.plain == "release v2.0.0-rc1+build.5 ready"
        assert styled(result, "repr.number") == ["v2.0.0-rc1+build.5"]

    def test_bare_version_with_multiple_suffixes(self) -> None:
        result = auto_highlight_text("pkg 1.4.0-beta.2+exp.sha.5114f85 installed")
        assert styled(result, "repr.number") == ["1.4.0-beta.2+exp.sha.5114f85"]

    def test_multiple_versions_in_sentence(self) -> None:
        result = auto_highlight_text("upgrade v1.2.3 to v2.0.0-rc1+build.5 now")
        assert styled(result, "repr.number") == ["v1.2.3", "v2.0.0-rc1+build.5"]

    def test_version_suffix_stops_before_detached_dash(self) -> None:
        result = auto_highlight_text("built v2.1.0 - done in 3s")
        assert styled(result, "repr.number") == ["v2.1.0", "3s"]

    def test_v_number_without_dots_is_not_a_version(self) -> None:
        result = auto_highlight_text("rev v1 deployed")
        assert styled(result, "repr.number") == []

    def test_number_unit_seconds(self) -> None:
        result = auto_highlight_text("loaded in 1.33s")
        assert styled(result, "repr.number") == ["1.33s"]

    def test_number_unit_with_space(self) -> None:
        result = auto_highlight_text("size is 8.04 GB")
        assert styled(result, "repr.number") == ["8.04 GB"]

    def test_number_unit_megabytes(self) -> None:
        result = auto_highlight_text("file size 245MB")
        assert styled(result, "repr.number") == ["245MB"]

    def test_number_unit_milliseconds(self) -> None:
        result = auto_highlight_text("latency 42ms")
        assert styled(result, "repr.number") == ["42ms"]

    def test_fraction(self) -> None:
        result = auto_highlight_text("Batch 3/5 done")
        assert styled(result, "repr.number") == ["3/5"]

    def test_fraction_larger(self) -> None:
        result = auto_highlight_text("Detection 156/156 regions")
        assert styled(result, "repr.number") == ["156/156"]

    def test_colon_not_colored(self) -> None:
        result = auto_highlight_text("key: value")
        assert styled(result, "special") == []

    def test_comma_not_colored(self) -> None:
        result = auto_highlight_text("24 files, 12MB")
        assert result.plain == "24 files, 12MB"

    def test_parens_not_colored(self) -> None:
        result = auto_highlight_text("(avg 27ms/item)")
        assert result.plain == "(avg 27ms/item)"

    def test_em_dash_not_colored(self) -> None:
        result = auto_highlight_text("loaded — 3 profiles")
        assert styled(result, "special") == []

    def test_literal_brackets_preserved(self) -> None:
        result = auto_highlight_text("result[0] = 42")
        assert result.plain == "result[0] = 42"
        assert styled(result, "repr.number") == ["0", "42"]

    def test_literal_brackets_never_parsed_as_markup(self) -> None:
        result = auto_highlight_text("array[1:3]")
        assert result.plain == "array[1:3]"

    @pytest.mark.parametrize(
        ("text", "style", "plain"),
        [
            ("[repr.number]42[/repr.number]", "repr.number", "42"),
            ("[bold]text[/bold]", "bold", "text"),
            ("[info]msg[/info]", "info", "msg"),
        ],
    )
    def test_existing_markup_not_double_highlighted(self, text: str, style: str, plain: str) -> None:
        result = auto_highlight_text(text)
        assert result.plain == plain
        assert styled(result, style) == [plain]


class TestHighlightOutsideRichMarkup:
    def test_plain_text_highlighted(self) -> None:
        result = _highlight_outside_rich_markup("value 42")
        assert styled(result, "repr.number") == ["42"]

    def test_preserves_existing_markup(self) -> None:
        result = _highlight_outside_rich_markup("[bold]hello[/bold] world 42")
        assert result.plain == "hello world 42"
        assert styled(result, "bold") == ["hello"]
        assert styled(result, "repr.number") == ["42"]

    def test_only_markup_returned_as_is(self) -> None:
        result = _highlight_outside_rich_markup("[bold]test[/bold]")
        assert result.plain == "test"
        assert styled(result, "bold") == ["test"]

    def test_empty_string(self) -> None:
        assert _highlight_outside_rich_markup("").plain == ""

    def test_no_double_highlight(self) -> None:
        result = _highlight_outside_rich_markup("[repr.number]42[/repr.number]")
        assert styled(result, "repr.number") == ["42"]

    def test_container_markup_highlights_inner_numbers(self) -> None:
        text = "[dim]Hashing text_encoders/qwen-3-4b.safetensors (8.04 GB)…[/dim]"
        result = _highlight_outside_rich_markup(text)

        assert result.plain == "Hashing text_encoders/qwen-3-4b.safetensors (8.04 GB)…"
        assert styled(result, "dim") == [result.plain]
        assert styled(result, "repr.number") == ["8.04 GB"]

    def test_container_markup_keeps_bracketed_path_intact(self) -> None:
        path = r"C:\data\output\[backup] Data Set - 03 (1080p) [checksum].zip"
        result = _highlight_outside_rich_markup(f"[gray]-> {path}[/gray]")

        assert result.plain == f"-> {path}"
        assert styled(result, "gray") == [result.plain]
        assert styled(result, "repr.path") == [path]


class TestPatchedConsolePrint:
    @patch(f"{_patched_console_print.__module__}._original_console_print")
    def test_plain_text_auto_highlighted(self, mock_print: MagicMock) -> None:
        _patched_console_print("value 42")
        mock_print.assert_called_once()
        arg = mock_print.call_args[0][0]
        assert isinstance(arg, Text)
        assert styled(arg, "repr.number") == ["42"]

    @patch(f"{_patched_console_print.__module__}._original_console_print")
    def test_markup_text_highlights_unstyled_tail(self, mock_print: MagicMock) -> None:
        _patched_console_print("[bold]hello[/bold]")
        arg = mock_print.call_args[0][0]
        assert styled(arg, "bold") == ["hello"]

        _patched_console_print("[green]done[/green] (0.0s)")
        arg = mock_print.call_args[0][0]
        assert styled(arg, "green") == ["done"]
        assert styled(arg, "repr.number") == ["0.0s"]

        _patched_console_print("[dim]Hashing text_encoders/qwen-3-4b.safetensors (8.04 GB)…[/dim]")
        arg = mock_print.call_args[0][0]
        assert styled(arg, "repr.number") == ["8.04 GB"]

    @patch(f"{_patched_console_print.__module__}._original_console_print")
    def test_explicit_highlight_true_with_markup(self, mock_print: MagicMock) -> None:
        _patched_console_print("[bold]hi[/bold] 42", highlight=True)
        arg = mock_print.call_args[0][0]
        assert styled(arg, "bold") == ["hi"]
        assert styled(arg, "repr.number") == ["42"]

    @patch(f"{_patched_console_print.__module__}._original_console_print")
    def test_explicit_highlight_true_plain(self, mock_print: MagicMock) -> None:
        _patched_console_print("value 99", highlight=True)
        arg = mock_print.call_args[0][0]
        assert styled(arg, "repr.number") == ["99"]

    @patch(f"{_patched_console_print.__module__}._original_console_print")
    def test_highlight_false_no_highlighting(self, mock_print: MagicMock) -> None:
        _patched_console_print("value 42", highlight=False)
        arg = mock_print.call_args[0][0]
        assert isinstance(arg, Text)
        assert not arg.spans

    @patch(f"{_patched_console_print.__module__}._original_console_print")
    def test_highlight_false_plain_brackets_stay_literal(self, mock_print: MagicMock) -> None:
        _patched_console_print("config [section]", highlight=False)
        arg = mock_print.call_args[0][0]
        assert isinstance(arg, Text)
        assert arg.plain == "config [section]"

    @patch(f"{_patched_console_print.__module__}._original_console_print")
    def test_highlight_false_markup_passed_through(self, mock_print: MagicMock) -> None:
        _patched_console_print("[bold]hi[/bold]", highlight=False)
        arg = mock_print.call_args[0][0]
        assert arg == "[bold]hi[/bold]"

    @patch(f"{_patched_console_print.__module__}._original_console_print")
    def test_non_string_passthrough(self, mock_print: MagicMock) -> None:
        obj = {"key": "value"}
        _patched_console_print(obj)
        mock_print.assert_called_once()
        assert mock_print.call_args[0][0] is obj

    @patch(f"{_patched_console_print.__module__}._original_console_print")
    def test_comma_normalization(self, mock_print: MagicMock) -> None:
        _patched_console_print("value 1,5", highlight=False)
        arg = mock_print.call_args[0][0]
        assert arg.plain == "value 1.5"
