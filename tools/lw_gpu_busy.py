"""The ONE GpuBusy shared by every GPU consumer in this repo.

This module imports NOTHING, and that is the whole design. The four tools that
own a `gpu_lock` - lw_g1_gate, lw_upscale, lw_gen_run, lw_clean_sdxl - run under
four different venvs (.venv-metrics, .venv-upscale, .venv-gen, C:\\Tools\\lw-clean).
They each forked their own `class GpuBusy(RuntimeError)` to avoid dragging one
venv's dependencies into another, which was the right instinct and the wrong fix:
Python matches exceptions by class IDENTITY, so a forked class means
`except GpuBusy` in one module silently fails to catch what another module's
`gpu_lock` raises. A module with zero imports is safe in every venv and gives all
four the same class object.

Do NOT add an import here, and do NOT move this into ops/loop/winmutex.py -
that file is byte-identical-by-contract with the sibling repos and moving it
would need a three-way re-pin.

See docs/MCP_LIFT_L1_2026-08-01.md section 3 and the ROADMAP item
gpu-busy-fork-unification.
"""
from __future__ import annotations


class GpuBusy(RuntimeError):
    """GPU_MUTEX did not free within the holder's GPU_MUTEX_TIMEOUT_S.

    A tool-native type so a caller can report "the GPU is busy elsewhere"
    instead of leaking a winmutex traceback; the MutexTimeout stays on
    __cause__ for anyone who needs the raw reason.
    """
