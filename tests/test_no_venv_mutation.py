"""The suite must never install into, or otherwise mutate, the toolchain venv.

Regression test for the 2026-08-11 finding: a full-suite run under the lw-clean
venv replaced Pillow mid-run via ultralytics' `check_requirements("pi-heif")`
autoinstall path, leaving the venv unusable (see tests/conftest.py for the
mechanism and the measured file counts).
"""
from __future__ import annotations

import os

import pytest


def test_autoinstall_env_guard_is_set():
    """conftest.py pins the ultralytics autoinstall gate off for the suite."""
    assert os.environ.get("YOLO_AUTOINSTALL") == "false"


def test_ultralytics_autoinstall_is_disabled_when_importable():
    """If ultralytics is present, its AUTOINSTALL must resolve False.

    Skips wherever ultralytics is absent (system python 3.14 + CI), so this
    only bites in the venv that can actually be damaged.
    """
    u = pytest.importorskip("ultralytics.utils")
    assert u.AUTOINSTALL is False, (
        "ultralytics AUTOINSTALL is on - a failed PIL.Image.open will shell "
        "out to `uv pip install pi-heif` and replace Pillow in this venv"
    )


def test_lw_clean_pass_sets_the_guard_itself(monkeypatch):
    """The cleaning tool pins the gate at import, independent of pytest.

    conftest.py only protects the SUITE. A production run
    (`python tools/lw_clean_pass.py <slug>`) imports ultralytics lazily inside
    load_models(), so without this the same corrupt-image path would shell out
    to `uv pip install pi-heif` and replace Pillow in the venv. The env var must
    therefore be set by the module itself, before that lazy import can run.

    Deletes the var and reloads, otherwise conftest's setdefault would make this
    pass no matter what the module does.
    """
    import importlib
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "tools"))
    monkeypatch.delenv("YOLO_AUTOINSTALL", raising=False)
    import lw_clean_pass

    importlib.reload(lw_clean_pass)
    assert os.environ.get("YOLO_AUTOINSTALL") == "false"


def test_pil_image_open_failure_does_not_trigger_an_install(monkeypatch, tmp_path):
    """A corrupt image must raise, not send the suite shopping for a codec.

    Guards the exact trip wire: any subprocess spawned while opening
    undecodable bytes fails this test.
    """
    pytest.importorskip("PIL")
    import subprocess

    from PIL import Image

    spawned = []

    def boom(*a, **k):
        spawned.append(a[0] if a else None)
        raise AssertionError(f"test spawned a subprocess: {a[0] if a else None}")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)

    bad = tmp_path / "corrupt.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\xff" * 64)

    # PIL raises UnidentifiedImageError (an OSError subclass) on a header it
    # cannot parse; the tuple keeps the assertion honest without going broad.
    with pytest.raises((OSError, SyntaxError, ValueError)):
        Image.open(bad).load()
    assert spawned == []
