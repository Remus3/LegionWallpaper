"""Global-filter tripwire on submissions to save-working.

Why this exists (measured on slug 259f, 2026-08-29): every image check the
cleaning stage owns is masked or local - outside_ssim, mad_outside, seam_ssim,
change_ssim - so a submission carrying a GLOBAL filter on top of the intended
local edit is invisible to all of them. cmd_save_working ran no image check at
all, and an operator PNG measuring halo_pct 0.3897 / lap_ratio 10.244 against
its own _cleaninitial was accepted with rc=0.

ADR-008 house rule: a reviewer may FLAG, never REJECT. This records the
measurement and flags it; it never refuses the operator's file.

Spec anchors:
  - halo flag 0.05 = lw_g1_gate.DEFAULT_G1_THRESHOLDS["halo_pct"]["flag"]
  - lap ceiling: legitimate cleaning measures ~1.0; the settled USM census
    (CLAUDE.md, USM_DEFAULT ruling) put the worst gated lap_ratio at 1.1399.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_pipeline as lw  # noqa: E402

STAGE_FOLDERS = [
    "0.Originals",
    "1.First Pass Scratch",
    "2.First Pass Done",
    "3.Cleaning Scratch",
    "4.Cleaning Done",
    "5.Final Scratch",
    "6.Final Done",
    "7.Last Scratch",
    "8.End Review",
    "9.Image Backup",
]

# Measured on 259f: the clean rebuild vs the operator's sharpened submission.
CLEAN_HALO, CLEAN_LAP = 0.0206, 0.9356
SHARPENED_HALO, SHARPENED_LAP = 0.3897, 10.244


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "images"
    for name in STAGE_FOLDERS + ["reference_pictures"]:
        d = r / name
        d.mkdir(parents=True)
        (d / ".gitkeep").write_text("")
    return r


@pytest.fixture(autouse=True)
def _fast_gate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lw, "PROBE_SECONDS", 0.0)


def run(root: Path, *args: str) -> int:
    return lw.main(["--root", str(root), *args])


def test_source_is_ascii():
    src = Path(__file__).resolve().parent.parent / "tools" / "lw_pipeline.py"
    assert all(b <= 127 for b in src.read_bytes())


# ---------------------------------------------------------------- pure verdict
def test_a_clean_rebuild_is_not_flagged():
    v = lw.global_filter_verdict(CLEAN_HALO, CLEAN_LAP)
    assert v["flagged"] is False
    assert v["reasons"] == []


def test_a_globally_sharpened_submission_is_flagged():
    v = lw.global_filter_verdict(SHARPENED_HALO, SHARPENED_LAP)
    assert v["flagged"] is True
    assert len(v["reasons"]) == 2


def test_halo_over_the_flag_alone_is_enough():
    v = lw.global_filter_verdict(SHARPENED_HALO, 1.0)
    assert v["flagged"] is True
    assert any("halo_pct" in r for r in v["reasons"])
    assert not any("lap_ratio" in r for r in v["reasons"])


def test_lap_ratio_over_the_ceiling_alone_is_enough():
    v = lw.global_filter_verdict(0.01, 5.0)
    assert v["flagged"] is True
    assert any("lap_ratio" in r for r in v["reasons"])
    assert not any("halo_pct" in r for r in v["reasons"])


def test_halo_exactly_at_the_flag_is_not_flagged():
    assert lw.global_filter_verdict(lw.GLOBAL_FILTER_HALO_FLAG, 1.0)["flagged"] is False


def test_lap_ratio_exactly_at_the_ceiling_is_not_flagged():
    assert lw.global_filter_verdict(0.01, lw.GLOBAL_FILTER_LAP_CEIL)["flagged"] is False


def test_the_settled_usm_census_worst_case_is_not_flagged():
    """USM_DEFAULT (1.2, 35, 3) put the worst gated lap_ratio at 1.1399.

    A legitimate light USM must never trip this tripwire, or the settled
    default would flag every image it was chosen to fix.
    """
    assert lw.global_filter_verdict(0.0, 1.1399)["flagged"] is False


def test_a_softening_filter_is_not_caught_by_the_lap_ceiling():
    """The ceiling catches over-sharpen only; lap_ratio's FLOOR (G1, fail 1.0)
    owns the soft direction. Asserted so nobody later widens this into a band
    and silently double-gates softness."""
    v = lw.global_filter_verdict(0.0, 0.2)
    assert v["flagged"] is False


def test_an_unmeasurable_metric_is_skipped_not_treated_as_a_pass_or_a_fail():
    v = lw.global_filter_verdict(None, None)
    assert v["flagged"] is False
    assert v["reasons"] == []


def test_one_unmeasurable_metric_does_not_suppress_the_other():
    v = lw.global_filter_verdict(None, 5.0)
    assert v["flagged"] is True
    assert any("lap_ratio" in r for r in v["reasons"])


def test_a_reason_names_the_measurement_and_the_threshold():
    reason = lw.global_filter_verdict(SHARPENED_HALO, 1.0)["reasons"][0]
    assert "0.3897" in reason and "0.05" in reason


# ------------------------------------------------------------------ measurement
def _write_png(path: Path, arr: np.ndarray) -> None:
    from PIL import Image
    Image.fromarray(arr.astype(np.uint8)).save(path)


def _structured_base(h: int = 96, w: int = 128) -> np.ndarray:
    """Deterministic image with real edges - a flat filter must show up on it."""
    y, x = np.mgrid[0:h, 0:w]
    a = np.zeros((h, w, 3), np.float64)
    a[..., 0] = 40 + 80 * ((x // 8) % 2)
    a[..., 1] = 40 + 80 * ((y // 8) % 2)
    a[..., 2] = 30 + 60 * (((x + y) // 12) % 2)
    return a


def test_measure_reports_near_unity_for_an_untouched_copy(tmp_path: Path):
    ref = tmp_path / "ref.png"
    sub = tmp_path / "sub.png"
    base = _structured_base()
    _write_png(ref, base)
    _write_png(sub, base)
    m = lw.measure_global_filter(ref, sub)
    assert m["halo_pct"] == pytest.approx(0.0, abs=1e-6)
    assert m["lap_ratio"] == pytest.approx(1.0, abs=1e-6)
    assert lw.global_filter_verdict(m["halo_pct"], m["lap_ratio"])["flagged"] is False


def test_measure_catches_a_heavy_global_sharpen(tmp_path: Path):
    from PIL import Image, ImageFilter
    ref = tmp_path / "ref.png"
    sub = tmp_path / "sub.png"
    base = _structured_base()
    _write_png(ref, base)
    sharp = Image.fromarray(base.astype(np.uint8)).filter(
        ImageFilter.UnsharpMask(radius=1.5, percent=300, threshold=0))
    sharp.save(sub)
    m = lw.measure_global_filter(ref, sub)
    assert m["lap_ratio"] > lw.GLOBAL_FILTER_LAP_CEIL
    assert lw.global_filter_verdict(m["halo_pct"], m["lap_ratio"])["flagged"] is True


def test_measure_returns_none_for_undecodable_bytes(tmp_path: Path):
    """save-working must stay usable on a non-image payload - several existing
    suites submit b"edited-first" as the working file."""
    ref = tmp_path / "ref.png"
    sub = tmp_path / "sub.png"
    _write_png(ref, _structured_base())
    sub.write_bytes(b"not-an-image")
    m = lw.measure_global_filter(ref, sub)
    assert m["halo_pct"] is None and m["lap_ratio"] is None


def test_measure_returns_none_when_the_reference_is_missing(tmp_path: Path):
    sub = tmp_path / "sub.png"
    _write_png(sub, _structured_base())
    m = lw.measure_global_filter(tmp_path / "nope.png", sub)
    assert m["halo_pct"] is None and m["lap_ratio"] is None


def test_measure_returns_none_on_a_size_mismatch(tmp_path: Path):
    ref = tmp_path / "ref.png"
    sub = tmp_path / "sub.png"
    _write_png(ref, _structured_base(96, 128))
    _write_png(sub, _structured_base(64, 64))
    m = lw.measure_global_filter(ref, sub)
    assert m["halo_pct"] is None and m["lap_ratio"] is None


# --------------------------------------------------------------------- wiring
def _stage_a_clean_slug(root: Path, slug: str = "ahri") -> Path:
    folder = root / "3.Cleaning Scratch" / slug
    folder.mkdir(parents=True)
    _write_png(folder / f"{slug}_cleaninitial.png", _structured_base())
    (folder / "manifest.json").write_text(json.dumps({
        "schema": 1, "slug": slug, "original_filename": f"{slug}.png",
        "original_sha256": "0" * 64, "source_url": None,
        "created_ts": "2026-08-29T00:00:00Z", "delivered_as": None,
        "transitions": [],
    }))
    return folder


def _last_transition(folder: Path) -> dict:
    return json.loads((folder / "manifest.json").read_text())["transitions"][-1]


def test_save_working_records_the_measurement_in_the_manifest(root: Path,
                                                              tmp_path: Path):
    folder = _stage_a_clean_slug(root)
    sub = tmp_path / "sub.png"
    _write_png(sub, _structured_base())
    assert run(root, "save-working", "ahri", "--from", str(sub),
               "--tool", "operator-select") == 0
    gf = _last_transition(folder)["audit"]["global_filter"]
    assert gf["lap_ratio"] == pytest.approx(1.0, abs=1e-6)
    assert gf["flagged"] is False


def test_save_working_flags_a_globally_sharpened_submission(root: Path,
                                                            tmp_path: Path):
    from PIL import Image, ImageFilter
    folder = _stage_a_clean_slug(root)
    sub = tmp_path / "sub.png"
    Image.fromarray(_structured_base().astype(np.uint8)).filter(
        ImageFilter.UnsharpMask(radius=1.5, percent=300, threshold=0)).save(sub)
    assert run(root, "save-working", "ahri", "--from", str(sub),
               "--tool", "operator-select") == 0
    gf = _last_transition(folder)["audit"]["global_filter"]
    assert gf["flagged"] is True
    assert gf["reasons"]


def test_a_flagged_submission_is_still_accepted(root: Path, tmp_path: Path,
                                                capsys: pytest.CaptureFixture):
    """ADR-008: FLAG, never REJECT. The operator is never refused."""
    from PIL import Image, ImageFilter
    folder = _stage_a_clean_slug(root)
    sub = tmp_path / "sub.png"
    Image.fromarray(_structured_base().astype(np.uint8)).filter(
        ImageFilter.UnsharpMask(radius=1.5, percent=300, threshold=0)).save(sub)
    rc = run(root, "save-working", "ahri", "--from", str(sub),
             "--tool", "operator-select")
    assert rc == 0
    assert (folder / "ahri_cleanworking_01.png").is_file()
    assert "global_filter" in capsys.readouterr().out.lower()


def test_save_working_still_accepts_a_non_image_payload(root: Path,
                                                        tmp_path: Path):
    """Regression guard: existing suites submit b"edited-first" as the file."""
    folder = _stage_a_clean_slug(root)
    sub = tmp_path / "sub.png"
    sub.write_bytes(b"edited-clean")
    assert run(root, "save-working", "ahri", "--from", str(sub),
               "--tool", "operator-select") == 0
    gf = _last_transition(folder)["audit"]["global_filter"]
    assert gf["halo_pct"] is None and gf["flagged"] is False


def test_the_recorded_audit_does_not_disturb_the_vision_flag_machinery(
        root: Path, tmp_path: Path):
    """_latest_gate_audit keys on an audit dict carrying "verdict". The
    global_filter audit carries no "verdict", so it must leave the approval
    record reading "no_audit" - NOT be mistaken for a gate result."""
    folder = _stage_a_clean_slug(root)
    sub = tmp_path / "sub.png"
    _write_png(sub, _structured_base())
    assert run(root, "save-working", "ahri", "--from", str(sub),
               "--tool", "operator-select") == 0
    man = json.loads((folder / "manifest.json").read_text())
    rec = lw._approval_record(man, "clean")
    assert rec["gate_check"] == "no_audit"
    assert rec["verdict"] is None
