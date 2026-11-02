"""Select best available compute device — CUDA > CPU, torch-free.

Never imports torch itself — importing torch puts it in ``sys.modules``,
which makes a later ``onnxruntime.InferenceSession`` reuse torch's cuDNN
instead of its own, slowing dynamic-shape ONNX model loading. Detection
only reads torch if some other module already imported it first.

Detection order:
    1. torch already in ``sys.modules`` -> use it (no penalty).
    2. ``nvidia-smi`` on PATH -> query name + VRAM.
    3. ``onnxruntime`` reports CUDAExecutionProvider -> CUDA, unknown VRAM.
    4. Otherwise -> CPU.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Final, Literal

__all__ = ["DeviceInfo", "get_device"]

_BYTES_PER_MB: Final[int] = 1024 * 1024
"""Bytes per megabyte, for VRAM byte→MB conversion."""

_NVIDIA_SMI_TIMEOUT_S: Final[float] = 2.0
"""Timeout for the nvidia-smi subprocess probe."""

_NO_WINDOW: Final[int] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
"""Windows flag keeping a console child from opening its own window when the parent has none."""


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Immutable snapshot of device selection."""

    device: Literal["cuda", "mps", "cpu"]
    name: str
    has_cuda: bool
    has_mps: bool
    vram_mb: int


def _query_cuda_via_torch() -> tuple[str, int] | None:
    """Use torch only if it is already loaded; never import it ourselves."""
    torch = sys.modules.get("torch")
    if torch is None:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        vram_mb = torch.cuda.get_device_properties(0).total_memory // _BYTES_PER_MB
        return torch.cuda.get_device_name(0), int(vram_mb)
    except Exception:
        return None


def _query_cuda_via_nvidia_smi() -> tuple[str, int] | None:
    """Production-safe probe — runs ``nvidia-smi`` as a subprocess."""
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=_NVIDIA_SMI_TIMEOUT_S,
            check=True,
            creationflags=_NO_WINDOW,
        )
    except subprocess.SubprocessError, OSError:
        return None
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    if not lines or "," not in lines[0]:
        return None
    name_part, vram_part = (p.strip() for p in lines[0].split(",", 1))
    try:
        vram_mb = int(vram_part)
    except ValueError:
        return None
    return name_part, vram_mb


def _ort_reports_cuda() -> bool:
    """Cheap check: does onnxruntime advertise CUDAExecutionProvider?"""
    ort = sys.modules.get("onnxruntime")
    if ort is None:
        try:
            import onnxruntime
        except ImportError:
            return False
        ort = onnxruntime
    try:
        return "CUDAExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def get_device(
    *,
    force_cpu: bool = False,
    min_vram_mb: int = 0,
) -> DeviceInfo:
    """Select best available device without forcing a torch import."""
    if force_cpu:
        return DeviceInfo(device="cpu", name="CPU", has_cuda=False, has_mps=False, vram_mb=0)

    gpu = _query_cuda_via_torch() or _query_cuda_via_nvidia_smi()

    if gpu is None:
        if _ort_reports_cuda():
            return DeviceInfo(device="cuda", name="CUDA GPU", has_cuda=True, has_mps=False, vram_mb=0)
        return DeviceInfo(device="cpu", name="CPU", has_cuda=False, has_mps=False, vram_mb=0)

    name, vram_mb = gpu
    if min_vram_mb > 0 and vram_mb < min_vram_mb:
        return DeviceInfo(device="cpu", name="CPU", has_cuda=True, has_mps=False, vram_mb=0)
    return DeviceInfo(device="cuda", name=name, has_cuda=True, has_mps=False, vram_mb=vram_mb)
