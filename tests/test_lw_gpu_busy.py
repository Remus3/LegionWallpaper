"""Tests for tools/lw_gpu_busy.py - the ONE GpuBusy every GPU consumer shares.

Why this file exists (2026-08-01, docs/MCP_LIFT_L1_2026-08-01.md section 3):
`GpuBusy` was declared FOUR times - lw_g1_gate, lw_upscale, lw_gen_run and
lw_clean_sdxl each carried their own `class GpuBusy(RuntimeError)`. Python
exception matching is by class IDENTITY, so `except GpuBusy` in one module does
NOT catch a GpuBusy raised by another module's `gpu_lock`. The pairings happened
to line up; nothing enforced it, and under N=3 concurrent repos GPU contention
is the expected case rather than the edge case.

The canonical module imports NOTHING - not even stdlib. That is load-bearing:
these four tools run under four different venvs (.venv-gen, .venv-metrics,
.venv-upscale, lw-clean) and the fork existed precisely to avoid dragging one
venv's dependencies into another. A shared module with zero imports is safe
everywhere; a shared module that imports numpy would re-create the problem.

CI constraint: stdlib only, no GPU, no torch. Nothing here acquires a mutex.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import lw_gpu_busy  # noqa: E402

# Every module that owns a `gpu_lock` and must raise the shared type.
GPU_CONSUMERS = ["lw_g1_gate", "lw_upscale", "lw_gen_run", "lw_clean_sdxl"]


@pytest.fixture(scope="module")
def consumers():
    """Import the four GPU-owning modules. Skips any the venv cannot load."""
    mods = {}
    for name in GPU_CONSUMERS:
        try:
            mods[name] = __import__(name)
        except Exception as exc:  # noqa: BLE001 - a missing venv dep is a skip
            pytest.skip(f"{name} not importable here: {type(exc).__name__}: {exc}")
    return mods


# ---------------------------------------------------------------------------
# identity - the actual defect
# ---------------------------------------------------------------------------
def test_every_consumer_exposes_the_same_class_object(consumers):
    for name, mod in consumers.items():
        assert mod.GpuBusy is lw_gpu_busy.GpuBusy, (
            f"{name}.GpuBusy is a FORK, not the shared class - an except in "
            f"another module will not catch what its gpu_lock raises")


def test_one_except_catches_a_raise_from_every_consumer(consumers):
    """The regression this file is named for, exercised the way callers hit it."""
    for name, mod in consumers.items():
        try:
            raise mod.GpuBusy(f"GPU busy elsewhere ({name})")
        except lw_gpu_busy.GpuBusy as exc:
            assert name in str(exc)
        else:  # pragma: no cover - defensive
            pytest.fail(f"a {name} GpuBusy escaped the shared except")


def test_gpu_busy_is_a_runtime_error():
    """Callers with a broad `except RuntimeError` must keep working."""
    assert issubclass(lw_gpu_busy.GpuBusy, RuntimeError)


def test_cause_survives_so_the_raw_reason_is_never_lost():
    """The MutexTimeout stays on __cause__ - that is the contract gpu_lock uses."""
    root = TimeoutError("winmutex: MutexTimeout")
    try:
        try:
            raise root
        except TimeoutError as exc:
            raise lw_gpu_busy.GpuBusy("GPU busy elsewhere") from exc
    except lw_gpu_busy.GpuBusy as exc:
        assert exc.__cause__ is root


# ---------------------------------------------------------------------------
# structural - stop the fork coming back
# ---------------------------------------------------------------------------
def test_only_the_canonical_module_declares_gpu_busy():
    """A fifth fork must fail CI rather than be discovered a month later."""
    offenders = []
    for path in sorted(TOOLS.rglob("*.py")):
        if path.name == "lw_gpu_busy.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "GpuBusy":
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], (
        f"GpuBusy re-declared outside lw_gpu_busy.py: {offenders}. Import the "
        f"shared class instead - a forked class breaks every cross-module except")


def test_the_canonical_module_imports_nothing():
    """Zero imports is what makes it safe in all four venvs. Keep it that way."""
    tree = ast.parse((TOOLS / "lw_gpu_busy.py").read_text(encoding="utf-8"))
    imports = [n for n in ast.walk(tree)
               if isinstance(n, (ast.Import, ast.ImportFrom))
               and not (isinstance(n, ast.ImportFrom) and n.module == "__future__")]
    assert imports == [], (
        "lw_gpu_busy.py must import nothing but __future__ - it is loaded by "
        "tools running under four different venvs")
