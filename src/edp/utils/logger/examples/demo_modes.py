"""Demo logger modes — DEV, PRODUCTION, SILENT.

Demonstrate how to configure the logger for different environments
and how each mode affects output behavior.

Usage (via module entry point):

    python -m <pkg>.logger.examples --modes
"""

from __future__ import annotations

import time

from loguru import logger

from ...rich_console import console
from .. import LoggerMode, log_duration, setup_mode

__all__ = ["run_all_demos"]


def demo_dev_mode() -> None:
    """Show DEV mode: stderr + file, DEBUG level, colored output."""
    console.rule("[ruby_red_bold]DEV Mode[/ruby_red_bold]")
    setup_mode(LoggerMode.DEV, name="demo")

    log = logger.bind(logger_name="demo.dev")
    log.debug("Debug message — visible in DEV mode")
    log.info("Info message — application started")
    log.success("Success — operation completed")
    log.warning("Warning — something looks off")
    log.error("Error — something failed")
    log.critical("Critical — system is down")

    console.print("[green]DEV mode shows ALL levels with colors.[/green]")


def demo_production_mode() -> None:
    """Show PRODUCTION mode: file-only JSON, INFO+ level."""
    console.rule("[ruby_red_bold]PRODUCTION Mode[/ruby_red_bold]")
    setup_mode(LoggerMode.PRODUCTION, name="demo")

    log = logger.bind(logger_name="demo.prod")
    log.debug("This DEBUG message goes to file only (not console)")
    log.info("Info message — written as JSONL to file")
    log.error("Error message — written to both app.log and errors.log")

    console.print("[green]PRODUCTION mode writes JSONL to files, minimal console output.[/green]")


def demo_silent_mode() -> None:
    """Show SILENT mode: no output at all."""
    console.rule("[ruby_red_bold]SILENT Mode[/ruby_red_bold]")
    setup_mode(LoggerMode.SILENT, name="demo")

    log = logger.bind(logger_name="demo.silent")
    log.info("This message is silenced — nothing appears")
    log.error("Even errors are silenced")

    console.print("[green]SILENT mode suppresses ALL output.[/green]")


def demo_timer_integration() -> None:
    """Show log_duration context manager."""
    console.rule("[ruby_red_bold]Timer Integration (log_duration)[/ruby_red_bold]")
    setup_mode(LoggerMode.DEV, name="demo")

    with log_duration("image_resize"):
        time.sleep(0.05)

    with log_duration("model_inference"):
        time.sleep(0.1)

    console.print("[green]log_duration automatically logs operation timing.[/green]")


def run_all_demos() -> None:
    """Run all modes demos."""
    console.rule("[ruby_red_bold]Logger Modes Demo[/ruby_red_bold]", style="ruby_red")
    console.print()

    demo_dev_mode()
    console.print()

    demo_production_mode()
    console.print()

    demo_silent_mode()
    console.print()

    demo_timer_integration()
    console.print()

    setup_mode(LoggerMode.DEV, name="demo")
