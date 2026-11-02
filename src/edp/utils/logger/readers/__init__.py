"""Readers package - chain-able LogReader and aggregations."""

from __future__ import annotations

from .aggregator import LogAggregator
from .reader import LogReader

__all__ = [
    "LogAggregator",
    "LogReader",
]
