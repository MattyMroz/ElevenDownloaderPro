"""Complete Rich theme definition with 150+ styles.

Color Palette:
- 13 base colors × 3 variants (normal, bold, italic) = 39 primary styles
- 6 semantic styles (info, success, warning, error, debug, critical)
- 100+ specialized styles for Rich features

Usage:
    >>> from rich.console import Console
    >>> from rich_console.theme import RICH_THEME
    >>> console = Console(theme=RICH_THEME)
"""

from __future__ import annotations

from typing import Final

from rich.theme import Theme

__all__ = [
    "RICH_THEME",
    "Colors",
    "get_all_style_names",
    "get_style_categories",
]

# ── Color Constants ───────────────────────────────────────────────────────────


class Colors:
    """Named color constants for the Rich theme palette.

    Attributes:
        PURPLE: Purple accent.
        RUBY_RED: Primary brand red (RGB).
        PINK: Light pink variant.
        RED: Bright red for errors.
        BROWN: Warm brown accent.
        ORANGE: Orange for debug/warnings.
        YELLOW: Bright yellow for caution.
        GREEN: Green for success states.
        BLUE: Dodger blue for info/links.
        WHITE: Default white text.
        NORMAL: Terminal default color.
        GRAY: Dark gray for muted elements.
        BLACK_ON_WHITE: Inverted text for critical.
    """

    PURPLE: Final[str] = "purple"
    RUBY_RED: Final[str] = "rgb(224,34,103)"
    PINK: Final[str] = "pale_violet_red1"
    RED: Final[str] = "bright_red"
    BROWN: Final[str] = "rgb(180,82,45)"
    ORANGE: Final[str] = "rgb(255,135,70)"
    YELLOW: Final[str] = "bright_yellow"
    GREEN: Final[str] = "green"
    BLUE: Final[str] = "dodger_blue2"
    WHITE: Final[str] = "white"
    NORMAL: Final[str] = "default"
    GRAY: Final[str] = "rgb(58,58,58)"
    BLACK_ON_WHITE: Final[str] = "rgb(0,0,0) on white"


# ── Rich Theme ────────────────────────────────────────────────────────────────

RICH_THEME: Final[Theme] = Theme(
    {
        # ──────────────────────────────────────────────────────────────────────
        # PRIMARY COLOR PALETTE (13 colors × 3 variants = 39 styles)
        # ──────────────────────────────────────────────────────────────────────
        "purple": Colors.PURPLE,
        "purple_bold": f"{Colors.PURPLE} bold",
        "purple_italic": f"{Colors.PURPLE} italic",
        "ruby_red": Colors.RUBY_RED,
        "ruby_red_bold": f"{Colors.RUBY_RED} bold",
        "ruby_red_italic": f"{Colors.RUBY_RED} italic",
        "pink": Colors.PINK,
        "pink_bold": f"{Colors.PINK} bold",
        "pink_italic": f"{Colors.PINK} italic",
        "red": Colors.RED,
        "red_bold": f"{Colors.RED} bold",
        "red_italic": f"{Colors.RED} italic",
        "brown": Colors.BROWN,
        "brown_bold": f"{Colors.BROWN} bold",
        "brown_italic": f"{Colors.BROWN} italic",
        "orange": Colors.ORANGE,
        "orange_bold": f"{Colors.ORANGE} bold",
        "orange_italic": f"{Colors.ORANGE} italic",
        "yellow": Colors.YELLOW,
        "yellow_bold": f"{Colors.YELLOW} bold",
        "yellow_italic": f"{Colors.YELLOW} italic",
        "green": Colors.GREEN,
        "green_bold": f"{Colors.GREEN} bold",
        "green_italic": f"{Colors.GREEN} italic",
        "blue": Colors.BLUE,
        "blue_bold": f"{Colors.BLUE} bold",
        "blue_italic": f"{Colors.BLUE} italic",
        "white": Colors.WHITE,
        "white_bold": f"{Colors.WHITE} bold",
        "white_italic": f"{Colors.WHITE} italic",
        "normal": Colors.NORMAL,
        "normal_bold": "bold",
        "normal_italic": "italic",
        "gray": Colors.GRAY,
        "gray_bold": f"{Colors.GRAY} bold",
        "gray_italic": f"{Colors.GRAY} italic",
        "black": Colors.BLACK_ON_WHITE,
        "black_bold": f"{Colors.BLACK_ON_WHITE} bold",
        "black_italic": f"{Colors.BLACK_ON_WHITE} italic",
        # ──────────────────────────────────────────────────────────────────────
        # SEMANTIC STYLES (Application-level)
        # ──────────────────────────────────────────────────────────────────────
        "info": f"{Colors.BLUE} bold",
        "success": f"{Colors.GREEN} bold",
        "warning": f"{Colors.YELLOW} bold",
        "error": f"{Colors.RED} bold",
        "debug": f"{Colors.ORANGE} bold",
        "critical": f"rgb(0,0,0) on {Colors.RED} bold",
        # ──────────────────────────────────────────────────────────────────────
        # LOGGING INTEGRATION
        # ──────────────────────────────────────────────────────────────────────
        "logging.level.info": f"{Colors.BLUE} bold",
        "logging.level.success": f"{Colors.GREEN} bold",
        "logging.level.warning": f"{Colors.YELLOW} bold",
        "logging.level.error": f"{Colors.RED} bold",
        "logging.level.debug": f"{Colors.ORANGE} bold",
        "logging.level.critical": f"rgb(0,0,0) on {Colors.RED} bold",
        "logging.level": "red",
        "logging.time": "red",
        "logging.message": "red",
        "log.time": f"{Colors.RUBY_RED} italic",
        "log.level": f"{Colors.RUBY_RED} bold",
        # ──────────────────────────────────────────────────────────────────────
        # REPR STYLES - Python object representation
        # ──────────────────────────────────────────────────────────────────────
        "repr.number": f"{Colors.RUBY_RED} bold",
        "repr.number_complex": f"{Colors.RUBY_RED} bold",
        "repr.bool_true": f"{Colors.GREEN} bold",
        "repr.bool_false": f"{Colors.RED} bold",
        "repr.none": f"{Colors.RED} italic",
        "repr.str": Colors.ORANGE,
        "repr.brace": f"{Colors.RUBY_RED} bold",
        "repr.comma": Colors.RUBY_RED,
        "repr.ellipsis": f"{Colors.RED} italic",
        "repr.indent": "default",
        "repr.error": f"{Colors.RED} bold",
        "repr.url": f"{Colors.BLUE} underline",
        "repr.uuid": Colors.PURPLE,
        "repr.call": f"{Colors.YELLOW} bold",
        "repr.path": Colors.RUBY_RED,
        "repr.filename": f"{Colors.RUBY_RED} bold",
        "repr.tag_start": f"{Colors.RUBY_RED} bold",
        "repr.tag_name": f"{Colors.YELLOW} bold",
        "repr.tag_contents": "default",
        "repr.tag_end": f"{Colors.RUBY_RED} bold",
        "repr.attrib_name": Colors.PURPLE,
        "repr.attrib_equal": Colors.RUBY_RED,
        "repr.attrib_value": Colors.ORANGE,
        # ──────────────────────────────────────────────────────────────────────
        # OPERATORS & SPECIAL CHARACTERS
        # ──────────────────────────────────────────────────────────────────────
        "operator": Colors.RUBY_RED,
        "punctuation": Colors.RUBY_RED,
        "special": Colors.RUBY_RED,
        # ──────────────────────────────────────────────────────────────────────
        # MARKDOWN STYLES (8-color hierarchical palette)
        # ──────────────────────────────────────────────────────────────────────
        "markdown.paragraph": "default",
        "markdown.text": "default",
        "markdown.bold": "bold",
        "markdown.italic": "italic",
        "markdown.code": f"{Colors.RUBY_RED} on rgb(30,30,30)",
        "markdown.code_block": f"{Colors.RUBY_RED} on rgb(30,30,30)",
        "markdown.block_quote": f"{Colors.RUBY_RED} italic",
        "markdown.list.bullet": f"{Colors.RUBY_RED} bold",
        "markdown.list.number": f"{Colors.RUBY_RED} bold",
        "markdown.hr": Colors.RUBY_RED,
        # Hierarchical headings (8 levels)
        "markdown.h1": f"{Colors.PURPLE} bold",
        "markdown.h2": f"{Colors.RUBY_RED} bold",
        "markdown.h3": f"{Colors.RED} bold",
        "markdown.h4": f"{Colors.ORANGE} bold",
        "markdown.h5": f"{Colors.YELLOW} bold",
        "markdown.h6": f"{Colors.GREEN} bold",
        "markdown.h1.border": "",
        "markdown.h2.border": Colors.RUBY_RED,
        "markdown.link": f"{Colors.BLUE} bold",
        "markdown.link_url": f"{Colors.BLUE} underline",
        "markdown.item.bullet": f"{Colors.RUBY_RED} bold",
        "markdown.item.number": f"{Colors.RUBY_RED} bold",
        # ──────────────────────────────────────────────────────────────────────
        # JSON STYLES (main palette: purple, ruby_red, red, orange, yellow, green, blue, white)
        # ──────────────────────────────────────────────────────────────────────
        "json.key": f"{Colors.PURPLE} bold",
        "json.str": Colors.ORANGE,
        "json.number": f"{Colors.RUBY_RED} bold",
        "json.bool": f"{Colors.YELLOW} bold",
        "json.null": f"{Colors.RED} italic",
        "json.brace": f"{Colors.RUBY_RED} bold",
        "json.bracket": f"{Colors.RUBY_RED} bold",
        # ──────────────────────────────────────────────────────────────────────
        # TABLE STYLES
        # ──────────────────────────────────────────────────────────────────────
        "table.header": f"{Colors.WHITE} bold",
        "table.footer": Colors.GRAY,
        "table.cell": "default",
        "table.title": f"{Colors.RUBY_RED} bold",
        "table.caption": f"{Colors.RUBY_RED} bold",
        # ──────────────────────────────────────────────────────────────────────
        # PROGRESS/BAR STYLES
        # ──────────────────────────────────────────────────────────────────────
        "bar.back": Colors.GRAY,
        "bar.complete": "green",
        "bar.finished": "green",
        "bar.pulse": f"{Colors.RUBY_RED} bold",
        "progress.description": "default",
        "progress.filesize": "default",
        "progress.filesize.total": "default bold",
        "progress.download": "default bold",
        "progress.elapsed": "default",
        "progress.percentage": "default bold",
        "progress.remaining": "default",
        "progress.data.speed": "default bold",
        "progress.spinner": f"{Colors.RUBY_RED} bold",
        # ──────────────────────────────────────────────────────────────────────
        # TREE, RULE, OTHER STYLES
        # ──────────────────────────────────────────────────────────────────────
        "tree.line": Colors.WHITE,
        "rule.line": Colors.RUBY_RED,
        "rule.text": f"{Colors.RUBY_RED} bold",
        "status.spinner": f"{Colors.RUBY_RED} bold",
        "status.text": "default",
        # ──────────────────────────────────────────────────────────────────────
        # TRACEBACK/ERROR STYLES
        # ──────────────────────────────────────────────────────────────────────
        "traceback.error": f"{Colors.RED} bold",
        "traceback.border": Colors.RED,
        "traceback.title": f"{Colors.RED} bold",
        "traceback.text": "default",
        "traceback.exc_type": f"{Colors.RED} bold",
        "traceback.exc_value": Colors.RED,
        # ──────────────────────────────────────────────────────────────────────
        # INSPECT STYLES (using main palette: purple, ruby_red, red, orange, yellow, green, blue, white)
        # ──────────────────────────────────────────────────────────────────────
        "inspect.attr": Colors.PURPLE,
        "inspect.attr.dunder": f"{Colors.ORANGE} italic",
        "inspect.callable": f"{Colors.YELLOW} bold",
        "inspect.def": f"{Colors.RUBY_RED} bold",
        "inspect.error": f"{Colors.RED} bold",
        "inspect.equals": Colors.RUBY_RED,
        "inspect.doc": f"{Colors.GREEN} italic",
        # ──────────────────────────────────────────────────────────────────────
        # ISO8601 DATETIME (unified ruby_red)
        # ──────────────────────────────────────────────────────────────────────
        "iso8601.date": f"{Colors.RUBY_RED} bold",
        "iso8601.time": f"{Colors.RUBY_RED} bold",
        "iso8601.timezone": f"{Colors.RUBY_RED}",
        # ──────────────────────────────────────────────────────────────────────
        # SCOPE STYLES
        # ──────────────────────────────────────────────────────────────────────
        "scope.border": Colors.WHITE,
        "scope.key": f"{Colors.PURPLE} bold",
        "scope.key.special": f"{Colors.RUBY_RED} bold",
        "scope.equals": Colors.RUBY_RED,
        # ──────────────────────────────────────────────────────────────────────
        # PROMPT STYLES (unified ruby_red)
        # ──────────────────────────────────────────────────────────────────────
        "prompt": f"{Colors.RUBY_RED} bold",
        "prompt.choices": f"{Colors.RUBY_RED} bold",
        "prompt.default": f"{Colors.RUBY_RED} italic",
        "prompt.invalid": f"{Colors.RUBY_RED} bold",
    },
)
"""Complete Rich theme with 150+ styles for the console."""


# ── Utility ───────────────────────────────────────────────────────────────────


def get_all_style_names() -> list[str]:
    """Return all style names defined in RICH_THEME.

    Returns:
        Sorted list of style names.
    """
    return sorted(RICH_THEME.styles.keys())


def get_style_categories() -> dict[str, list[str]]:
    """Return styles organized by category.

    Returns:
        Mapping of category names to lists of style names.
    """
    primary_color_prefixes: tuple[str, ...] = (
        "purple",
        "ruby_red",
        "pink",
        "red",
        "brown",
        "orange",
        "yellow",
        "green",
        "blue",
        "white",
        "normal",
        "gray",
        "black",
    )

    semantic_styles: set[str] = {"info", "success", "warning", "error", "debug", "critical"}

    category_mapping: dict[str, list[str]] = {
        "logging": ["logging.", "log."],
        "repr": ["repr."],
        "markdown": ["markdown."],
        "json": ["json."],
        "table": ["table."],
        "progress": ["progress.", "bar."],
        "tree_rule": ["tree.", "rule.", "status."],
        "traceback": ["traceback."],
        "inspect": ["inspect."],
        "datetime": ["iso8601."],
        "scope": ["scope."],
        "prompt": ["prompt."],
    }

    categories: dict[str, list[str]] = {
        "primary_colors": [],
        "semantic": [],
        **{cat: [] for cat in category_mapping},
        "other": [],
    }

    for style_name in RICH_THEME.styles:
        if any(style_name.startswith(prefix) for prefix in primary_color_prefixes):
            categories["primary_colors"].append(style_name)
        elif style_name in semantic_styles:
            categories["semantic"].append(style_name)
        else:
            matched = False
            for category, prefixes in category_mapping.items():
                if any(style_name.startswith(prefix) for prefix in prefixes):
                    categories[category].append(style_name)
                    matched = True
                    break
            if not matched:
                categories["other"].append(style_name)

    return categories
