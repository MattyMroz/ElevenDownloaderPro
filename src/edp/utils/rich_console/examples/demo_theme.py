"""Demo complete Rich theme — auto-highlighting demonstration.

Displays theme styles with AUTO-HIGHLIGHTING enabled.
All numbers, operators, and special characters are automatically colored.
No manual markup tags needed — the console does it automatically.

Usage (via module entry point):

    python -m <pkg>.rich_console.examples --theme

Features demonstrated:
    1. Auto-highlighting (numbers, operators, special chars)
    2. Primary Color Palette (manual styles for headings/emphasis)
    3. Semantic Styles (info, success, warning, error)
    4. Real-world examples (logs, tables, markdown)
"""

from __future__ import annotations

from typing import Final

from rich.table import Table

from ..console import console

__all__ = ["run_all_demos"]

# ── Constants ─────────────────────────────────────────────────────────────────

HEADER_WIDTH: Final[int] = 70
"""Character width of demo section headers."""

SECTION_SEPARATOR: Final[str] = "═" * HEADER_WIDTH
"""Horizontal rule printed above and below each section title."""


# ── Helpers ───────────────────────────────────────────────────────────────────


def print_section(title: str) -> None:
    """Print section header with centered title."""
    console.print(f"\n{SECTION_SEPARATOR}")
    console.print(title.center(HEADER_WIDTH), style="white_bold")
    console.print(f"{SECTION_SEPARATOR}\n")


def demo_primary_colors() -> None:
    """Demonstrate all 39 primary color styles (13 colors × 3 variants)."""
    print_section("PRIMARY COLOR PALETTE (13 colors × 3 variants)")

    table = Table(
        title="Complete Color Palette",
        show_header=True,
        header_style="white_bold",
    )

    table.add_column("Color", justify="left", style="white", width=12)
    table.add_column("Normal", justify="left", width=17)
    table.add_column("Bold", justify="left", width=20)
    table.add_column("Italic", justify="left", width=20)

    colors = [
        ("Purple", "purple"),
        ("Ruby Red", "ruby_red"),
        ("Pink", "pink"),
        ("Red", "red"),
        ("Brown", "brown"),
        ("Orange", "orange"),
        ("Yellow", "yellow"),
        ("Green", "green"),
        ("Blue", "blue"),
        ("White", "white"),
        ("Normal", "normal"),
        ("Gray", "gray"),
        ("Black", "black"),
    ]

    for color_name, style_base in colors:
        table.add_row(
            f"[{style_base}_bold]{color_name}[/{style_base}_bold]",
            f"[{style_base}]{style_base}[/{style_base}]",
            f"[{style_base}_bold]{style_base}_bold[/{style_base}_bold]",
            f"[{style_base}_italic]{style_base}_italic[/{style_base}_italic]",
        )

    console.print(table)


def demo_semantic_styles() -> None:
    """Demonstrate semantic application-level styles."""
    print_section("SEMANTIC STYLES (Application-level)")

    console.print("Basic Semantic Styles:")
    console.print("  INFO - Informational message")
    console.print("  SUCCESS - Operation completed")
    console.print("  WARNING - Warning message")
    console.print("  ERROR - Error occurred")
    console.print("  DEBUG - Debug information")
    console.print("  CRITICAL - Critical failure")


def demo_logging_styles() -> None:
    """Demonstrate logging integration styles with real log examples."""
    print_section("LOGGING INTEGRATION")

    console.print("Logging Level Styles:")
    console.print("  [logging.level.info]INFO[/logging.level.info]: Application started")
    console.print("  [logging.level.success]SUCCESS[/logging.level.success]: Task completed")
    console.print("  [logging.level.warning]WARNING[/logging.level.warning]: Low memory")
    console.print("  [logging.level.error]ERROR[/logging.level.error]: Connection failed")
    console.print("  [logging.level.debug]DEBUG[/logging.level.debug]: Variable state: x=42")
    console.print("  [logging.level.critical]CRITICAL[/logging.level.critical]: System crash")
    console.print()

    console.print("Real Log Examples (with timestamp):")
    console.print(
        "  [log.time]2024-11-06 14:23:15.123[/log.time] | [logging.level.info]INFO    [/logging.level.info] | Starting application...",  # noqa: E501
    )
    console.print(
        "  [log.time]2024-11-06 14:23:16.456[/log.time] | [logging.level.success]SUCCESS [/logging.level.success] | Database connected",  # noqa: E501
    )
    console.print(
        "  [log.time]2024-11-06 14:23:17.789[/log.time] | [logging.level.warning]WARNING [/logging.level.warning] | Cache miss for key='user:123'",  # noqa: E501
    )
    console.print(
        "  [log.time]2024-11-06 14:23:18.012[/log.time] | [logging.level.error]ERROR   [/logging.level.error] | Failed to load config.json",  # noqa: E501
    )
    console.print(
        "  [log.time]2024-11-06 14:23:19.345[/log.time] | [logging.level.debug]DEBUG   [/logging.level.debug] | Request body: {'user_id': 42}",  # noqa: E501
    )
    console.print(
        "  [log.time]2024-11-06 14:23:20.678[/log.time] | [logging.level.critical]CRITICAL[/logging.level.critical] | Out of memory!",  # noqa: E501
    )


def demo_repr_styles() -> None:
    """Demonstrate Python object representation styles with real examples."""
    print_section("REPR STYLES (Python Object Display)")

    console.print("Numbers & Booleans:")
    console.print(
        "  [repr.number]42[/repr.number], [repr.number]3.14[/repr.number], [repr.number_complex]2+3j[/repr.number_complex]",  # noqa: E501
    )
    console.print("  [repr.bool_true]True[/repr.bool_true], [repr.bool_false]False[/repr.bool_false]")
    console.print()

    console.print("Real Python Objects:")
    console.print(
        "  Dict: [repr.brace]{[/repr.brace][repr.str]'name'[/repr.str][repr.comma], [/repr.comma][repr.str]'age'[/repr.str][repr.comma], [/repr.comma][repr.number]30[/repr.number][repr.brace]}[/repr.brace]",  # noqa: E501
    )
    console.print(
        "  List: [repr.brace][[/repr.brace][repr.number]1[/repr.number][repr.comma], [/repr.comma][repr.number]2[/repr.number][repr.comma], [/repr.comma][repr.number]3[/repr.number][repr.brace]][/repr.brace]",  # noqa: E501
    )
    console.print(
        "  Tuple: [repr.brace]([/repr.brace][repr.str]'x'[/repr.str][repr.comma], [/repr.comma][repr.bool_true]True[/repr.bool_true][repr.comma], [/repr.comma][repr.none]None[/repr.none][repr.brace])[/repr.brace]",  # noqa: E501
    )
    console.print()

    console.print("Special Values:")
    console.print("  [repr.none]None[/repr.none]")
    console.print('  [repr.str]"Hello World"[/repr.str]')
    console.print("  [repr.ellipsis]...[/repr.ellipsis]")
    console.print()

    console.print("URLs & UUIDs:")
    console.print("  [repr.url]https://github.com/username/project[/repr.url]")
    console.print("  [repr.uuid]550e8400-e29b-41d4-a716-446655440000[/repr.uuid]")
    console.print()

    console.print("Paths & Files:")
    console.print("  [repr.path]/home/user/projects/myapp/src[/repr.path]")
    console.print("  [repr.filename]config.json[/repr.filename]")
    console.print("  [repr.path]C:\\\\Users\\\\username\\\\Documents\\\\project\\\\[/repr.path]")
    console.print()

    console.print("HTML Attributes:")
    console.print(
        '  [repr.attrib_name]href[/repr.attrib_name][repr.attrib_equal]=[/repr.attrib_equal][repr.attrib_value]"https://example.com"[/repr.attrib_value]',
    )
    console.print(
        '  [repr.attrib_name]class[/repr.attrib_name][repr.attrib_equal]=[/repr.attrib_equal][repr.attrib_value]"btn-primary"[/repr.attrib_value]',  # noqa: E501
    )


def demo_markdown_styles() -> None:
    """Demonstrate markdown rendering styles with REAL Rich Markdown."""
    from rich.markdown import Markdown

    print_section("MARKDOWN STYLES (8-level hierarchy)")

    console.print("Headings (styled preview):")
    console.print("  [markdown.h1]H1: Purple bold[/markdown.h1]")
    console.print("  [markdown.h2]H2: Ruby Red bold[/markdown.h2]")
    console.print("  [markdown.h3]H3: Red bold[/markdown.h3]")
    console.print("  [markdown.h4]H4: Orange bold[/markdown.h4]")
    console.print("  [markdown.h5]H5: Yellow bold[/markdown.h5]")
    console.print("  [markdown.h6]H6: Green bold[/markdown.h6]")
    console.print()

    console.print("REAL Markdown Rendering:")

    md_content: str = """# H1 Main Title

## H2 Section Title

### H3 Subsection

#### H4 Minor Heading

##### H5 Small Heading

###### H6 Smallest Heading

This is **bold text** and this is *italic text* and this is ***both***.

Normal paragraph text with `inline_code()` example.

- Bullet point 1
- Bullet point 2
  - Nested bullet

1. Numbered item 1
2. Numbered item 2

> Block quote example
> Multi-line quote

[Link Example](https://example.com)

---
"""

    md: Markdown = Markdown(md_content)
    console.print(md)
    console.print()

    console.print("Additional Markdown Styles:")
    console.print("  [markdown.bold]Bold text[/markdown.bold]")
    console.print("  [markdown.italic]Italic text[/markdown.italic]")
    console.print("  [markdown.code]inline_code()[/markdown.code]")
    console.print("  [markdown.list.bullet]•[/markdown.list.bullet] Bullet")
    console.print("  [markdown.list.number]1.[/markdown.list.number] Number")
    console.print("  [markdown.block_quote] Block quote[/markdown.block_quote]")
    console.print("  [markdown.link]Link Text[/markdown.link]")
    console.print("  [markdown.link_url]https://example.com[/markdown.link_url]")
    console.print("  [markdown.hr][/markdown.hr] Horizontal rule")


def demo_json_styles() -> None:
    """Demonstrate JSON syntax highlighting with REAL JSON."""
    from rich.json import JSON

    print_section("JSON STYLES (main palette)")

    console.print("REAL JSON Rendering:")

    json_data: str = """{
  "project": "rich_console",
  "version": "1.0.0",
  "active": true,
  "config": {
    "database": {
      "enabled": true,
      "host": "localhost",
      "port": 5432
    },
    "cache": {
      "enabled": true,
      "ttl": 3600
    }
  },
  "metadata": {
    "created": "2024-11-06",
    "deprecated": false,
    "count": 42,
    "ratio": 3.14,
    "empty": null
  }
}"""

    console.print(JSON(json_data))
    console.print()

    console.print("JSON Value Types (styled preview):")
    console.print('  [json.key]"key"[/json.key]')
    console.print('  [json.str]"string value"[/json.str]')
    console.print("  [json.number]42[/json.number], [json.number]3.14[/json.number]")
    console.print("  [json.bool]true[/json.bool], [json.bool]false[/json.bool]")
    console.print("  [json.null]null[/json.null]")
    console.print("  Braces: [json.brace]{[/json.brace] [json.brace]}[/json.brace]")
    console.print("  Brackets: [json.bracket][[/json.bracket] [json.bracket]][/json.bracket]")


def demo_table_styles() -> None:
    """Demonstrate table styling with REAL table (Excel-like)."""
    print_section("TABLE STYLES (Excel-like)")

    console.print("REAL Table Example:")

    table: Table = Table(
        title="[table.title]Service Performance Metrics[/table.title]",
        caption="[table.caption]Data as of 2024-11-06[/table.caption]",
        show_header=True,
        header_style="table.header",
        show_footer=True,
        footer_style="table.footer",
        border_style="white",
    )

    table.add_column("Service", justify="left", footer="[table.footer]Total[/table.footer]")
    table.add_column("Requests", justify="right", footer="[table.footer]12,345[/table.footer]")
    table.add_column("Success Rate", justify="right", footer="[table.footer]98.5%[/table.footer]")
    table.add_column("Avg Time (ms)", justify="right", footer="[table.footer]125[/table.footer]")
    table.add_column("Status", justify="center", footer="[table.footer]—[/table.footer]")

    table.add_row("auth_service", "3,450", "99.2%", "85", "OK")
    table.add_row("api_gateway", "2,890", "98.8%", "120", "OK")
    table.add_row("database", "2,150", "97.5%", "180", "SLOW")
    table.add_row("cache", "1,980", "99.5%", "95", "OK")
    table.add_row("file_storage", "1,125", "96.8%", "240", "ERROR")
    table.add_row("notification", "750", "99.9%", "150", "OK")

    console.print(table)
    console.print()

    console.print("Table Component Styles:")
    console.print("  [table.header]Table Header[/table.header]")
    console.print("  [table.footer]Table Footer[/table.footer]")
    console.print("  [table.cell]Table Cell[/table.cell]")
    console.print("  [table.title]Table Title[/table.title]")
    console.print("  [table.caption]Table Caption[/table.caption]")


def demo_progress_styles() -> None:
    """Demonstrate progress bar related styles."""
    print_section("PROGRESS/BAR STYLES")

    console.print("Bar Components:")
    console.print("  [bar.complete][/bar.complete] Complete bar")
    console.print("  [bar.finished][/bar.finished] Finished bar")
    console.print("  [bar.pulse][/bar.pulse] Pulse animation")
    console.print("  [bar.back][/bar.back] Background")
    console.print()

    console.print("Progress Info:")
    console.print("  [progress.description]Processing...[/progress.description]")
    console.print("  [progress.percentage]75%[/progress.percentage]")
    console.print("  [progress.elapsed]00:05[/progress.elapsed]")
    console.print("  [progress.remaining]00:02[/progress.remaining]")
    console.print("  [progress.filesize]1.5 MB / 10 MB[/progress.filesize]")
    console.print("  [progress.data.speed]5 MB/s[/progress.data.speed]")
    console.print("  [progress.spinner][/progress.spinner]")


def demo_tree_rule_styles() -> None:
    """Demonstrate tree and rule styles."""
    print_section("TREE, RULE, OTHER STYLES")

    console.print("Tree Structure:")
    console.print("  [tree.line] Tree line[/tree.line]")
    console.print()

    console.print("Rule:")
    console.print("  [rule.line][/rule.line]")
    console.print("  [rule.text]Rule Text[/rule.text]")
    console.print()

    console.print("Status:")
    console.print("  [status.spinner][/status.spinner]")
    console.print("  [status.text]Processing...[/status.text]")


def demo_traceback_styles() -> None:
    """Demonstrate error/traceback styles."""
    print_section("TRACEBACK/ERROR STYLES")

    console.print("Traceback Components:")
    console.print("  [traceback.error]Error occurred[/traceback.error]")
    console.print("  [traceback.border][/traceback.border]")
    console.print("  [traceback.title]Exception: ValueError[/traceback.title]")
    console.print(
        "  [traceback.exc_type]ValueError[/traceback.exc_type]: [traceback.exc_value]Invalid input[/traceback.exc_value]",  # noqa: E501
    )


def demo_inspect_styles() -> None:
    """Demonstrate inspect/introspection styles."""
    print_section("INSPECT STYLES")

    console.print("Inspect Components:")
    console.print("  [inspect.attr]attribute[/inspect.attr]")
    console.print("  [inspect.attr.dunder]__init__[/inspect.attr.dunder]")
    console.print("  [inspect.callable]function()[/inspect.callable]")
    console.print("  [inspect.def]def[/inspect.def]")
    console.print("  [inspect.equals]=[/inspect.equals]")
    console.print('  [inspect.doc]"Docstring text"[/inspect.doc]')


def demo_datetime_styles() -> None:
    """Demonstrate ISO8601 datetime styles."""
    print_section("ISO8601 DATETIME")

    console.print("Datetime Components:")
    console.print(
        "  [iso8601.date]2024-01-01[/iso8601.date][iso8601.time]T12:30:45[/iso8601.time][iso8601.timezone]+00:00[/iso8601.timezone]",  # noqa: E501
    )


def demo_scope_styles() -> None:
    """Demonstrate scope/variable display styles."""
    print_section("SCOPE STYLES")

    console.print("Scope Components:")
    console.print("  [scope.border][/scope.border]")
    console.print("  [scope.key]variable[/scope.key] [scope.equals]=[/scope.equals] value")
    console.print("  [scope.key.special]__special__[/scope.key.special]")


def demo_prompt_styles() -> None:
    """Demonstrate prompt/input styles."""
    print_section("PROMPT STYLES")

    console.print("Prompt Components:")
    console.print("  Enter value:")
    console.print("  [prompt.choices]Yes/No[/prompt.choices]")
    console.print("  [prompt.default](default)[/prompt.default]")
    console.print("  [prompt.invalid]Invalid input![/prompt.invalid]")


def demo_number_normalization() -> None:
    """Demonstrate automatic number normalization."""
    print_section("NUMBER NORMALIZATION & BRACKET ESCAPING")

    console.print("Number Normalization:")
    console.print("  Decimal with dot:   [repr.number]1.234[/repr.number] and [repr.number]5.67[/repr.number]")
    console.print("  Decimal with comma: [repr.number]1,234[/repr.number] and [repr.number]5,67[/repr.number]")
    console.print("  Arrays with dots:   [1.5, 2.3, 3.8]")
    console.print("  Arrays with commas: [1,5, 2,3, 3,8]")
    console.print("Both notations display identically!")
    console.print()

    console.print("Bracket Escaping:")
    console.print("  Literal brackets: [this, is, array]")
    console.print("  With numbers: [1.23, 4.56, 7,89]")
    console.print("  With markup: This is bold")
    console.print("console.print() automatically handles escaping!")


def run_all_demos() -> None:
    """Run all visual demos."""
    console.print(f"\n{SECTION_SEPARATOR}")
    console.print("RICH THEME VISUAL DEMO - All 150+ Styles".center(HEADER_WIDTH), style="white_bold")
    console.print(f"{SECTION_SEPARATOR}\n")

    demo_primary_colors()
    demo_semantic_styles()
    demo_logging_styles()
    demo_repr_styles()
    demo_markdown_styles()
    demo_json_styles()
    demo_table_styles()
    demo_progress_styles()
    demo_tree_rule_styles()
    demo_traceback_styles()
    demo_inspect_styles()
    demo_datetime_styles()
    demo_scope_styles()
    demo_prompt_styles()
    demo_number_normalization()

    console.print(f"\n{SECTION_SEPARATOR}")
    console.print("All theme styles demonstrated!".center(HEADER_WIDTH), style="white_bold")
    console.print(f"{SECTION_SEPARATOR}\n")

    console.print("Summary:")
    console.print("  • 39 primary color styles (13 colors × 3 variants)")
    console.print("  • 6 semantic styles (info, success, warning, error, debug, critical)")
    console.print("  • 100+ specialized styles for Rich features")
    console.print("  • Automatic number normalization (1.5 = 1,5)")
    console.print("  • Automatic bracket escaping")
    console.print()


if __name__ == "__main__":
    run_all_demos()
