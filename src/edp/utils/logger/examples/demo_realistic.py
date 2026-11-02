"""Realistic app simulation — logger in production-like scenario.

Simulates a <pkg>-like pipeline: config → services → processing → cleanup.
Shows how the logger output looks during actual multi-step workflows.

Run:
    python -m <pkg>.logger.examples --realistic
"""

from __future__ import annotations

import time

from loguru import logger

from ...rich_console import console
from .. import LoggerMode, log_duration, setup_mode

__all__ = ["run_all_demos"]


def _simulate_startup() -> None:
    """Simulate application startup."""
    log = logger.bind(logger_name="app")
    log.info("MyApp v2.1.0 starting")
    log.debug("Python 3.13.11 | CUDA 12.4 | torch 2.7.0")

    with log_duration("config_load"):
        time.sleep(0.01)

    log.info("Config loaded: mode=PRODUCTION, device=cuda:0")


def _simulate_model_loading() -> None:
    """Simulate model loading phase."""
    log = logger.bind(logger_name="models")

    models = ["detector", "parser", "transformer", "renderer"]
    for model_name in models:
        with log_duration(f"load_{model_name}"):
            time.sleep(0.02)
        log.debug("Loaded {model}", model=model_name)

    log.success("All 4 models loaded")


def _simulate_processing() -> None:
    """Simulate data processing pipeline."""
    log = logger.bind(logger_name="pipeline")
    items = ["item_001.dat", "item_002.dat", "item_003.dat"]

    for i, item in enumerate(items, 1):
        log.info("Processing {item} ({i}/{total})", item=item, i=i, total=len(items))

        det_log = logger.bind(logger_name="detection")
        with log_duration(f"detect_{item}"):
            time.sleep(0.015)
        det_log.debug("Found {n} regions, {b} records", n=4 + i, b=2 + i)

        parse_log = logger.bind(logger_name="parse")
        with log_duration(f"parse_{item}"):
            time.sleep(0.01)

        if i == 2:
            parse_log.warning("Low confidence on record #3 (0.42)")

        with log_duration(f"transform_{item}"):
            time.sleep(0.01)

        with log_duration(f"render_{item}"):
            time.sleep(0.01)

    log.success("Batch complete: {n} items processed", n=len(items))


def _simulate_error_scenario() -> None:
    """Simulate an error during processing."""
    log = logger.bind(logger_name="pipeline")
    log.info("Processing item_004.dat (extra batch)")

    det_log = logger.bind(logger_name="detection")
    det_log.debug("Running region detection")

    try:
        msg = "CUDA out of memory. Tried to allocate 2.10 GiB"
        raise RuntimeError(msg)
    except RuntimeError:
        det_log.error("Detection failed — falling back to CPU")
        det_log.warning("CPU fallback is 5-10x slower")

        with log_duration("detect_cpu_fallback"):
            time.sleep(0.05)
        det_log.info("CPU detection complete (slower but OK)")


def _simulate_shutdown() -> None:
    """Simulate graceful shutdown."""
    log = logger.bind(logger_name="app")
    log.info("Shutdown requested")
    log.debug("Flushing 3 pending writes")
    log.debug("Closing model handles")
    log.info("MyApp stopped gracefully")


def demo_realistic_dev() -> None:
    """Show realistic DEV mode output."""
    console.rule("[ruby_red_bold]Realistic DEV Mode[/ruby_red_bold]")
    setup_mode(LoggerMode.DEV, name="<pkg>")

    _simulate_startup()
    _simulate_model_loading()
    _simulate_processing()
    _simulate_error_scenario()
    _simulate_shutdown()


def demo_realistic_production() -> None:
    """Show realistic PRODUCTION mode output (INFO+ only)."""
    console.rule("[ruby_red_bold]Realistic PRODUCTION Mode[/ruby_red_bold]")
    setup_mode(LoggerMode.PRODUCTION, name="<pkg>")

    _simulate_startup()
    _simulate_model_loading()
    _simulate_processing()
    _simulate_error_scenario()
    _simulate_shutdown()


def run_all_demos() -> None:
    """Run realistic scenario demos."""
    console.rule("[ruby_red_bold]Realistic App Simulation[/ruby_red_bold]", style="ruby_red")
    console.print()

    demo_realistic_dev()
    console.print()

    demo_realistic_production()
    console.print()

    setup_mode(LoggerMode.DEV, name="demo")
