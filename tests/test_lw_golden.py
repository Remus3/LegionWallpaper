"""Tests for tools/lw_golden.py - the first-pass golden-set freeze/regress tool.

Pure stdlib + numpy + PIL (CI-safe); heavy metrics are INJECTED as a fake
callable so no pyiqa/torch is needed. The one real-adapter test uses
pytest.importorskip("pyiqa") and SKIPS where absent (CI, system python).
"""

import os
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_golden  # noqa: E402


# --------------------------------------------------------------- helpers
def _mkimg(path, size=(64, 36), color=(120, 90, 60)):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def _man_one(metrics):
    return {"schema": 1, "pipeline_version": "pv0", "created_ts": "t", "cases": [
        {"slug": "s", "input": {"path": "i", "sha256": "a"},
         "baseline": {"path": "data/golden/baseline/s_ijn.png", "sha256": "b"},
         "metrics": metrics, "defect_axes": [], "blessed": True}]}


# --------------------------------------------------------------- Task 1
def test_pipeline_version_is_deterministic_and_order_independent():
    a = {"model": "x.pth", "model_sha256": "ab", "torch": "2.11.0",
         "usm": {"radius": 1.2, "percent": 70}}
    b = {"usm": {"percent": 70, "radius": 1.2}, "torch": "2.11.0",
         "model_sha256": "ab", "model": "x.pth"}
    assert lw_golden.pipeline_version(a) == lw_golden.pipeline_version(b)
    assert len(lw_golden.pipeline_version(a)) == 64
    c = dict(a)
    c["torch"] = "2.12.0"
    assert lw_golden.pipeline_version(c) != lw_golden.pipeline_version(a)


def test_new_manifest_shape():
    m = lw_golden.new_manifest("deadbeef", "2026-07-04T00:00:00Z")
    assert m == {"schema": 1, "pipeline_version": "deadbeef",
                 "created_ts": "2026-07-04T00:00:00Z", "cases": []}


# --------------------------------------------------------------- Task 2
def test_freeze_writes_manifest_and_copies_bytes(tmp_path):
    inp = tmp_path / "src" / "fiora2_firstinitial.jpg"
    _mkimg(inp)
    base = tmp_path / "scratch" / "fiora2_ijn.png"
    _mkimg(base, (256, 144))
    out_root = tmp_path / "golden"
    fake = lambda i, o: {"msssim": 0.99, "lpips": 0.02, "lap_ratio": 1.5,  # noqa: E731
                         "halo_pct": 0.03, "band_delta": 0.0}
    man = lw_golden.freeze(
        [{"slug": "fiora2", "input_path": str(inp), "baseline_path": str(base),
          "defect_axes": ["soft-source"]}],
        out_root, {"model": "v1.pth", "torch": "2.11.0"}, fake,
        ts="2026-07-04T00:00:00Z")
    assert (out_root / "golden_set.json").is_file()
    assert (out_root / "inputs" / "fiora2_firstinitial.jpg").is_file()
    assert (out_root / "baseline" / "fiora2_ijn.png").is_file()
    case = man["cases"][0]
    assert case["slug"] == "fiora2"
    assert case["metrics"]["msssim"] == 0.99
    assert case["input"]["sha256"] and case["baseline"]["sha256"]
    assert man["pipeline_version"] == lw_golden.pipeline_version(
        {"model": "v1.pth", "torch": "2.11.0"})


# --------------------------------------------------------------- Task 3
def test_regress_passes_within_epsilon(tmp_path):
    (tmp_path / "s_ijn.png").write_bytes(b"x")
    man = _man_one({"msssim": 0.99, "lpips": 0.02, "lap_ratio": 2.0,
                    "halo_pct": 0.03, "band_delta": 0.0})
    fake = lambda i, o: {"msssim": 0.985, "lpips": 0.035, "lap_ratio": 2.08,  # noqa: E731
                         "halo_pct": 0.04, "band_delta": 0.0}
    rep = lw_golden.regress(man, tmp_path, fake, current_pv="pv0")
    assert rep["ok"] is True
    assert rep["pipeline_version_changed"] is False


def test_regress_flags_beyond_epsilon(tmp_path):
    (tmp_path / "s_ijn.png").write_bytes(b"x")
    man = _man_one({"msssim": 0.99, "lpips": 0.02, "lap_ratio": 2.0,
                    "halo_pct": 0.03, "band_delta": 0.0})
    fake = lambda i, o: {"msssim": 0.90, "lpips": 0.02, "lap_ratio": 2.0,  # noqa: E731
                         "halo_pct": 0.03, "band_delta": 0.0}
    rep = lw_golden.regress(man, tmp_path, fake, current_pv="pv1")
    assert rep["ok"] is False
    assert rep["pipeline_version_changed"] is True
    assert any("msssim" in r for r in rep["cases"][0]["reasons"])


def test_regress_missing_candidate(tmp_path):
    man = _man_one({"msssim": 0.99, "lpips": 0.02, "lap_ratio": 2.0,
                    "halo_pct": 0.03, "band_delta": 0.0})
    fake = lambda i, o: {}  # noqa: E731
    rep = lw_golden.regress(man, tmp_path, fake)
    assert rep["ok"] is False
    assert "missing candidate" in rep["cases"][0]["reasons"][0]


# --------------------------------------------------------------- Task 4
def test_gitignore_has_golden_rules():
    gi = Path(__file__).resolve().parents[1] / ".gitignore"
    text = gi.read_text(encoding="ascii", errors="replace")
    assert "data/golden/inputs/" in text
    assert "data/golden/baseline/" in text


def test_real_compute_metrics_smoke():
    pytest.importorskip("pyiqa")  # skips in CI and on system python
    assert callable(lw_golden._real_compute_metrics)
