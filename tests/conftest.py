from __future__ import annotations

import pytest
from fakes import _no_browser

from edp import reading


@pytest.fixture(autouse=True)
def _no_real_chrome(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reading, "_window", _no_browser)
