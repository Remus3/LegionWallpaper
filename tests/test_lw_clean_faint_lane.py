"""Faint-mark REMOVAL lane (ROADMAP `cleaning-detector-recall`, item e).

Gate v4 flags four `clean` images to `qa/faint_mark`. This is the removal half,
and the first thing measuring it established is that the four are NOT one
object the way the 32-slug centre overlay was:

  * `110-cleanup` is a DeviantArt centre overlay whose score (0.121) sits under
    the 0.15 overlay flag. The overlay lane already removes that object - it
    needs routing, not a new recipe.
  * `karthasbasefinal` + `dragon-slayer-pantheon` are the same thin brush
    signature on painted art. A diff-from-median mask separates them cleanly
    once the bright threshold is raised off the banner default.
  * `p2402-kda-evelynn` is a stylised wordmark sitting ON busy art, and no
    threshold separates it - see the constants' notes. It routes to the manual
    IOPaint lane, which is what the coverage rail here exists to force.

So the lane deliberately does two things and refuses a third. It derives its ROI
from the detector's own faint boxes rather than a hand-measured preset (the
whole point of having the boxes), and it self-refuses when its mask is too big
to be a mark - a refusal routes to a human, which is the safe direction.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))
import lw_clean_iopaint as IO  # noqa: E402

_W, _H = 2560, 1440


def _fb(x0, y0, x1, y1, conf=0.12):
    return {"box": [float(x0), float(y0), float(x1), float(y1)], "conf": conf}


def _ob(x0, y0, x1, y1, text="X"):
    return {"box": [float(x0), float(y0), float(x1), float(y1)],
            "text": text, "conf": 0.3}


@pytest.fixture(autouse=True)
def _no_overlay_signal(monkeypatch):
    """Pin the overlay score for every lane test. CI has no template and scores
    0.0, Legion has one and scores a real number off whatever the fixture
    happens to look like - and a synthetic noise frame correlating over the
    defer line would make these tests pass or fail by machine. The deferral
    tests override this deliberately."""
    monkeypatch.setattr(IO.C, "centre_overlay_score", lambda p: 0.0)


# ===========================================================================
# 1. faint_region - the ROI comes from the detector, not from a preset
# ===========================================================================
def test_region_is_the_union_of_the_faint_boxes():
    r = IO.faint_region([_fb(100, 200, 300, 250), _fb(280, 210, 500, 260)],
                        [], _W, _H)
    assert r == (100, 200, 500, 260)


def test_region_is_none_without_faint_boxes():
    assert IO.faint_region([], [_ob(0, 0, 100, 100)], _W, _H) is None


def test_an_overlapping_ocr_box_extends_the_region():
    """p2402: the 0.1228 YOLO box stops at x=2348 but OCR reads the wordmark out
    to x=2482. The faint box under-covers the mark, and the ROI must not."""
    r = IO.faint_region([_fb(1897, 1077, 2348, 1178)],
                        [_ob(1894, 1070, 2482, 1142, "N A M A K X I N"),
                         _ob(2039, 1139, 2337, 1183, "P & M 24 02")],
                        _W, _H)
    assert r == (1894, 1070, 2482, 1183)


def test_a_distant_ocr_box_does_not_extend_the_region():
    """The LEAGUE OF LEGENDS wordmark sits in the opposite corner on both
    alexflores frames. Unioning it in would hand the KEPT logo to LaMa."""
    r = IO.faint_region([_fb(2255, 1351, 2511, 1440)],
                        [_ob(81, 1316, 338, 1366, "TLEAOUEo"),
                         _ob(81, 1354, 354, 1418, "JEGENDS")], _W, _H)
    assert r == (2255, 1351, 2511, 1440)


def test_region_is_clamped_to_the_frame():
    r = IO.faint_region([_fb(-40, 1400, 2600, 1500)], [], _W, _H)
    assert r == (0, 1400, _W, _H)


def test_ocr_extension_needs_real_overlap_not_a_shared_edge():
    """Boxes that merely touch are not the same mark."""
    r = IO.faint_region([_fb(1000, 1000, 1200, 1050)],
                        [_ob(1200, 1000, 1600, 1050)], _W, _H)
    assert r == (1000, 1000, 1200, 1050)


# ===========================================================================
# 2. the coverage rail - the lane must refuse busy art
# ===========================================================================
def test_coverage_rail_accepts_the_measured_signatures():
    """karthasbasefinal 14.3%, dragon-slayer-pantheon 22.0% at the lane's
    threshold - both real marks, both must pass."""
    assert IO.faint_mask_ok(14.3) is True
    assert IO.faint_mask_ok(22.0) is True


def test_coverage_rail_refuses_the_measured_busy_art_case():
    """p2402 is 30.5% at the same threshold: the mask is half art, so the lane
    must hand it to the manual queue rather than repaint the picture."""
    assert IO.faint_mask_ok(30.5) is False


def test_coverage_rail_is_the_calibrated_constant():
    assert IO.FAINT_COVERAGE_MAX == pytest.approx(25.0)
    assert IO.faint_mask_ok(IO.FAINT_COVERAGE_MAX) is True
    assert IO.faint_mask_ok(IO.FAINT_COVERAGE_MAX + 0.01) is False


def test_bright_threshold_is_raised_off_the_banner_default():
    """The 10.0 default was calibrated for an opaque bottom-centre credit strip.
    Painted art reads above +10 from its own local median, so at the default the
    signature mask also swallows the cloud streaks beside it (measured: 32.6%
    coverage on karthasbasefinal, dropping to 14.3% at the lane's value)."""
    assert IO.FAINT_BRIGHT_THR > IO.BRIGHT_THR
    assert IO.FAINT_BRIGHT_THR == pytest.approx(42.0)


# ===========================================================================
# 3. the mask recipe on a synthetic frame with BOTH a mark and art texture
# ===========================================================================
def _synthetic_roi():
    """Dark art with soft bright streaks (+18 over the local median) plus a
    thin hard stroke (+90). The lane must keep the stroke and drop the streaks;
    the banner default keeps both."""
    rng = np.random.default_rng(7)
    roi = np.full((120, 400, 3), 40.0)
    roi += rng.normal(0, 1.5, roi.shape)
    for y in (20, 55, 95):                       # soft art streaks
        roi[y:y + 5, 30:360, :] += 18.0
    roi[58:62, 120:300, :] += 90.0               # the "signature" stroke
    return np.clip(roi, 0, 255).astype(np.uint8)


def test_default_threshold_masks_the_art_too():
    m = IO.build_watermark_mask(_synthetic_roi(), bright_thr=IO.BRIGHT_THR)
    assert (m[20:25, 30:360] > 127).mean() > 0.5, "art streak not masked at 10"


def test_lane_threshold_keeps_the_stroke_and_drops_the_art():
    m = IO.build_watermark_mask(_synthetic_roi(), bright_thr=IO.FAINT_BRIGHT_THR)
    assert (m[58:62, 150:280] > 127).mean() > 0.95, "the mark must stay covered"
    for y in (20, 95):
        assert (m[y:y + 5, 30:360] > 127).mean() < 0.05, "art streak survived"


# ===========================================================================
# 4. lane plumbing - it can never write without a mask, and never auto-applies
# ===========================================================================
def test_faint_lane_refuses_a_slug_with_no_faint_boxes(monkeypatch, tmp_path):
    from PIL import Image
    p = tmp_path / "s.png"
    Image.new("RGB", (400, 300), (20, 20, 20)).save(p)
    monkeypatch.setattr(IO, "_faint_detect", lambda path: ([], []))
    rec = IO.clean_slug("s", image=str(p), faint=True, dry_run=True,
                        out_dir=str(tmp_path), log=lambda *a: None)
    assert rec["status"] == "error"
    assert "faint" in rec["reason"]


def test_faint_lane_refuses_when_the_mask_is_mostly_art(monkeypatch, tmp_path):
    """The rail must fire BEFORE the GPU, and the refusal must name the manual
    lane rather than leave the operator with a silent skip."""
    from PIL import Image
    rng = np.random.default_rng(3)
    noisy = np.clip(rng.normal(128, 70, (300, 400, 3)), 0, 255).astype(np.uint8)
    p = tmp_path / "busy.png"
    Image.fromarray(noisy).save(p)
    monkeypatch.setattr(IO, "_faint_detect",
                        lambda path: ([_fb(60, 60, 340, 240)], []))
    rec = IO.clean_slug("busy", image=str(p), faint=True,
                        out_dir=str(tmp_path), log=lambda *a: None)
    assert rec["status"] == "manual"
    assert rec["mask_coverage_pct"] > IO.FAINT_COVERAGE_MAX
    assert "manual" in rec["reason"].lower()
    assert not os.path.exists(
        os.path.join(str(tmp_path), "busy_clean_cand.png")), \
        "a refused slug must not leave a candidate behind"


# ===========================================================================
# 4b. deferral - a KNOWN object belongs to its own lane
# ===========================================================================
_MEASURED_OVERLAY = [
    # slug, its live centre-overlay score, expected to defer
    ("dbwtlkx-eeb94ce2-166d-4457-abc3-615a5bc07fd4", 0.0480, False),
    ("dragon-slayer-pantheon-by-alexflores-d7fr57n-fullview", 0.0609, False),
    ("karthasbasefinal-by-alexflores-d7q5tbt-fullview", 0.0611, False),
    ("p2402-kda-evelynn-by-namakx-dgykw2q-pre", 0.0641, False),
    ("110-cleanup", 0.1090, True),
]


@pytest.mark.parametrize("slug,score,defers", _MEASURED_OVERLAY,
                         ids=[m[0][:22] for m in _MEASURED_OVERLAY])
def test_deferral_line_matches_the_measured_rows(slug, score, defers):
    assert IO.faint_defers_to_overlay(score) is defers


def test_deferral_line_is_outside_the_clean_population():
    """Measured over the 209 `clean` firstdones: overlay score p50 0.0596,
    p90 0.0770, p99 0.1042, max 0.1213. The line sits above p99, so deferring
    means `this frame's overlay correlation is out of the clean distribution`
    rather than a threshold picked to fit one slug."""
    assert IO.FAINT_OVERLAY_DEFER == pytest.approx(0.10)
    assert IO.faint_defers_to_overlay(0.1042) is True
    assert IO.faint_defers_to_overlay(0.0770) is False


def test_lane_defers_before_touching_the_gpu(monkeypatch, tmp_path):
    """110-cleanup is the centre-overlay object, and the faint lane's RAISED
    bright threshold is structurally wrong for a low-alpha mark - measured, the
    credit line stays legible (coverage 19.0%, 19.9% with chroma) and the
    overlay score goes UP, 0.1090 -> 0.1203. Route it, do not repaint it."""
    from PIL import Image
    Image.fromarray(_synthetic_roi()).resize((400, 300)).save(tmp_path / "s.png")
    monkeypatch.setattr(IO, "_faint_detect",
                        lambda path: ([_fb(100, 100, 300, 200)], []))
    monkeypatch.setattr(IO.C, "centre_overlay_score", lambda p: 0.109)
    monkeypatch.setattr(IO, "_load_lama",
                        lambda dev=None: pytest.fail("the GPU must not be used"))
    rec = IO.clean_slug("s", image=str(tmp_path / "s.png"), faint=True,
                        out_dir=str(tmp_path), log=lambda *a: None)
    assert rec["status"] == "defer_overlay"
    assert "--overlay" in rec["reason"]
    assert rec["overlay_score"] == pytest.approx(0.109)


# ===========================================================================
# 5. the outcome check - coverage is a proxy, the detector is the measurement
# ===========================================================================
def test_residual_check_reads_the_candidate_not_the_input():
    """A box that survives INSIDE the ROI means the mark is still there. One
    outside it is a different mark the lane never touched."""
    roi = (100, 100, 400, 200)
    assert IO.faint_residual([_fb(150, 120, 350, 180)], roi) == [
        _fb(150, 120, 350, 180)]
    assert IO.faint_residual([_fb(900, 900, 1100, 950)], roi) == []
    assert IO.faint_residual([], roi) == []


def test_lane_reports_residual_when_the_mark_survives(monkeypatch, tmp_path):
    """110-cleanup: a low-alpha DA credit line stays legible after the pass, and
    a lane that reported `cleaned` there would be lying to the operator."""
    from PIL import Image
    Image.fromarray(_synthetic_roi()).resize((400, 300)).save(tmp_path / "s.png")
    monkeypatch.setattr(IO, "_faint_detect",
                        lambda path: ([_fb(100, 100, 300, 200)], []))
    monkeypatch.setattr(IO, "_load_lama", lambda dev=None: (object(), "cpu"))
    monkeypatch.setattr(IO, "inpaint_once", lambda roi, m, lama: roi)
    rec = IO.clean_slug("s", image=str(tmp_path / "s.png"), faint=True,
                        out_dir=str(tmp_path), log=lambda *a: None)
    assert rec["status"] == "residual"
    assert rec["faint_residual"], "the surviving box must be reported"
    assert os.path.isfile(rec["cand"]), \
        "a residual is still an improvement - the candidate stays on disk"


def test_lane_reports_cleaned_when_the_mark_is_gone(monkeypatch, tmp_path):
    from PIL import Image
    Image.fromarray(_synthetic_roi()).resize((400, 300)).save(tmp_path / "s.png")
    seen = {"n": 0}

    def detect(path):
        seen["n"] += 1
        return ([_fb(100, 100, 300, 200)], []) if seen["n"] == 1 else ([], [])

    monkeypatch.setattr(IO, "_faint_detect", detect)
    monkeypatch.setattr(IO, "_load_lama", lambda dev=None: (object(), "cpu"))
    monkeypatch.setattr(IO, "inpaint_once", lambda roi, m, lama: roi)
    rec = IO.clean_slug("s", image=str(tmp_path / "s.png"), faint=True,
                        out_dir=str(tmp_path), log=lambda *a: None)
    assert rec["status"] == "cleaned"
    assert rec["faint_residual"] == []
    assert seen["n"] == 2, "the candidate must be re-detected, not assumed clean"


def test_faint_lane_dry_run_writes_the_mask_and_no_candidate(monkeypatch,
                                                             tmp_path):
    from PIL import Image
    Image.fromarray(_synthetic_roi()).resize((400, 300)).save(tmp_path / "s.png")
    monkeypatch.setattr(IO, "_faint_detect",
                        lambda path: ([_fb(100, 100, 300, 200)], []))
    rec = IO.clean_slug("s", image=str(tmp_path / "s.png"), faint=True,
                        dry_run=True, out_dir=str(tmp_path), log=lambda *a: None)
    assert rec["status"] == "dry-run"
    assert rec["mask"] == "faint-diff"
    assert os.path.isfile(rec["mask_png"])
    assert not os.path.exists(os.path.join(str(tmp_path), "s_clean_cand.png"))
