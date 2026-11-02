from __future__ import annotations

from rich.theme import Theme

from ..theme import (
    RICH_THEME,
    Colors,
    get_all_style_names,
    get_style_categories,
)


class TestColors:
    def test_all_constants_are_strings(self) -> None:
        for attr in dir(Colors):
            if attr.isupper() and not attr.startswith("_"):
                assert isinstance(getattr(Colors, attr), str)

    def test_ruby_red_is_rgb(self) -> None:
        assert Colors.RUBY_RED.startswith("rgb(")

    def test_known_colors_exist(self) -> None:
        assert Colors.PURPLE
        assert Colors.RUBY_RED
        assert Colors.GREEN
        assert Colors.BLUE
        assert Colors.WHITE


class TestRichTheme:
    def test_is_theme_instance(self) -> None:
        assert isinstance(RICH_THEME, Theme)

    def test_has_semantic_styles(self) -> None:
        style_names = set(RICH_THEME.styles.keys())
        for name in ("info", "success", "warning", "error", "debug", "critical"):
            assert name in style_names

    def test_has_primary_color_styles(self) -> None:
        style_names = set(RICH_THEME.styles.keys())
        for base in ("purple", "ruby_red", "red", "green", "blue"):
            assert base in style_names
            assert f"{base}_bold" in style_names
            assert f"{base}_italic" in style_names

    def test_has_repr_styles(self) -> None:
        style_names = set(RICH_THEME.styles.keys())
        assert "repr.number" in style_names
        assert "repr.bool_true" in style_names
        assert "repr.url" in style_names

    def test_has_logging_styles(self) -> None:
        style_names = set(RICH_THEME.styles.keys())
        assert "logging.level.info" in style_names
        assert "logging.level.error" in style_names

    def test_style_count_over_100(self) -> None:
        assert len(RICH_THEME.styles) > 100


class TestGetAllStyleNames:
    def test_returns_list(self) -> None:
        result = get_all_style_names()
        assert isinstance(result, list)

    def test_sorted(self) -> None:
        result = get_all_style_names()
        assert result == sorted(result)

    def test_contains_known_styles(self) -> None:
        result = get_all_style_names()
        assert "info" in result
        assert "error" in result
        assert "ruby_red" in result

    def test_matches_theme_count(self) -> None:
        result = get_all_style_names()
        assert len(result) == len(RICH_THEME.styles)


class TestGetStyleCategories:
    def test_returns_dict(self) -> None:
        result = get_style_categories()
        assert isinstance(result, dict)

    def test_has_primary_colors(self) -> None:
        result = get_style_categories()
        assert "primary_colors" in result
        assert len(result["primary_colors"]) > 0

    def test_has_semantic(self) -> None:
        result = get_style_categories()
        assert "semantic" in result
        assert "info" in result["semantic"]

    def test_has_expected_categories(self) -> None:
        result = get_style_categories()
        expected = {"primary_colors", "semantic", "logging", "repr", "markdown", "json", "table", "other"}
        assert expected.issubset(set(result.keys()))

    def test_other_catches_uncategorized_styles(self) -> None:
        result = get_style_categories()
        assert "other" in result
        assert "operator" in result["other"]
        assert "special" in result["other"]

    def test_all_styles_categorized(self) -> None:
        result = get_style_categories()
        total = sum(len(v) for v in result.values())
        assert total == len(RICH_THEME.styles)

    def test_all_values_are_lists(self) -> None:
        result = get_style_categories()
        for category, styles in result.items():
            assert isinstance(styles, list), f"{category} is not a list"
