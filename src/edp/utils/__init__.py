"""Provide shared utilities — portable across projects.

Subpackages: logger/, timer/, rich_console/.
Standalone: device.py, safe_path.py, safe_fs.py.

Heavy deps (torch via device.py) are NOT eagerly imported.
Use ``from <pkg>.utils.device import get_device`` explicitly.
"""

from __future__ import annotations

from .safe_fs import safe_move, safe_rmtree
from .safe_path import PathTraversalError, safe_resolve

__all__ = [
    "PathTraversalError",
    "safe_move",
    "safe_resolve",
    "safe_rmtree",
]
