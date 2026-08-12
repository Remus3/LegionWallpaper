"""Centre-overlay detector - the 11-of-14 false-negative class (ROADMAP
`cleaning-detector-recall`).

The missed object is the semi-transparent DeviantArt centre overlay: the DA
logo plus `(C) NAME.DEVIANTART.COM`, alpha-composited at a FIXED position and
scale on every image the site serves. The recall census measured why the
existing stack cannot see it - YOLO scores it 0.11-0.25 against a 0.35 floor,
OCR reads it as garble, and its centroid is mid-frame so the geometry rules
would only ever say `qa` anyway.

So this detector does not chase confidence. It exploits the one property that
census also proved: the mark is the SAME pixels in the SAME place across
images, which makes it recoverable by median-stacking the high-pass of images
that carry it (measured 2026-08-11: the stack of 11 positives renders the logo
and the URL legibly; the stack of 8 negatives renders nothing). Detection is
then a zero-mean normalized correlation of one image's high-pass against that
template over the template's own support.

Two invariants this file exists to hold:
  * the detector FLAGS to `qa`, it never routes to `auto`. Precision over the
    gated corpus is currently 0 false positives in 14 proposals and an
    unattended edit driven by a correlation score would spend that.
  * the flag is checked BEFORE the `lol_logo` KEEP rule, because two of the
    measured misses (seraphine, the-ruined-king-viego) are exactly images where
    the wordmark KEEP fired while a DA overlay sat in the middle of the frame.

Pure numpy - no cv2, no torch, no GPU - so it runs in CI.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))
import lw_clean_overlay as ov  # noqa: E402
import lw_clean_pass as cp  # noqa: E402

H, W = 240, 400


def _art(seed):
    """A busy synthetic 'artwork': smooth gradients plus structured noise."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    base = 90 + 60 * np.sin(xx / 23.0 + seed) + 40 * np.cos(yy / 17.0 - seed)
    base = base + rng.normal(0, 14, size=(H, W))
    rgb = np.stack([base, base * 0.95, base * 1.05], axis=2)
    return np.clip(rgb, 0, 255)


def _mark(h=H, w=W):
    """A fixed 'watermark': a bar, a chevron and a dotted text line."""
    m = np.zeros((h, w), dtype=np.float64)
    y0 = int(h * 0.66)
    m[y0:y0 + 3, int(w * 0.20):int(w * 0.80)] = 1.0      # the URL underline
    for i in range(18):                                   # a chevron
        m[y0 - 40 + i, int(w * 0.45) + i:int(w * 0.45) + i + 3] = 1.0
    for x in range(int(w * 0.22), int(w * 0.78), 7):       # glyph ticks
        m[y0 - 12:y0 - 4, x:x + 3] = 1.0
    return m


def _planted(seed, alpha=0.08):
    """Art with the mark alpha-composited on top, like the real overlay."""
    art = _art(seed)
    m = _mark()[:, :, None]
    return np.clip(art * (1 - alpha * m) + 255.0 * alpha * m, 0, 255)


@pytest.fixture(scope="module")
def tpl():
    """Template estimated from planted images ONLY - never from a test image."""
    return ov.estimate_template([_planted(s) for s in range(20, 32)])


# ===========================================================================
# 1. template estimation
# ===========================================================================
def test_estimate_template_recovers_the_common_mark(tpl):
    """The median high-pass of many marked frames must reveal the mark itself."""
    truth = _mark()
    band = tpl["band"]
    t = tpl["template"]
    truth_band = truth[int(H * band[0]):int(H * band[1]), :]
    assert t.shape == truth_band.shape
    # the recovered template must correlate strongly with the planted mark
    a = t - t.mean()
    b = truth_band - truth_band.mean()
    corr = float((a * b).sum() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
    # The template is a HIGH-PASS of the mark - stroke edges and their ringing -
    # so its correlation with the filled mask caps well below 1. Measured 0.43
    # for this fixture; the bound guards the recovery, not the exact number.
    assert corr > 0.40
    assert tpl["support"].sum() > 0


def test_estimate_template_of_unmarked_art_has_no_structure():
    """Stacking clean art must NOT manufacture a template out of noise."""
    clean = ov.estimate_template([_art(s) for s in range(60, 72)])
    marked = ov.estimate_template([_planted(s) for s in range(20, 32)])
    assert np.abs(clean["template"]).max() < np.abs(marked["template"]).max()


# ===========================================================================
# 2. scoring
# ===========================================================================
def test_score_separates_planted_overlay_from_clean_art(tpl):
    """The whole point: marked frames score high, unmarked art scores ~0."""
    pos = [ov.overlay_score(_planted(s), tpl) for s in range(100, 106)]
    neg = [ov.overlay_score(_art(s), tpl) for s in range(200, 206)]
    # Measured on this fixture: positives 0.27-0.51, clean art 0.07-0.09.
    assert min(pos) > 0.25
    assert max(neg) < 0.15
    assert min(pos) > max(neg)


def test_score_falls_with_alpha_but_stays_clear_of_art(tpl):
    """A fainter mark scores lower - and must still beat clean art."""
    strong = ov.overlay_score(_planted(7, alpha=0.10), tpl)
    faint = ov.overlay_score(_planted(7, alpha=0.03), tpl)
    # The score is NOT alpha-invariant: correlation is normalised by the band's
    # own energy, which is mostly art, so a fainter mark scores lower (measured
    # 0.43 at alpha 0.10, 0.19 at 0.03). It must stay well clear of clean art
    # (< 0.09 on this fixture), which is what makes a calibrated threshold work.
    assert faint > 0.15
    assert strong > faint


def test_score_is_zero_on_a_flat_frame(tpl):
    """A frame with no high-pass energy must not divide by zero or score."""
    flat = np.full((H, W, 3), 128.0)
    assert ov.overlay_score(flat, tpl) == 0.0


def test_score_resizes_a_template_from_a_different_frame_size(tpl):
    """The corpus is 2560x1440 but the template must not hard-code that."""
    big = np.repeat(np.repeat(_planted(11), 2, axis=0), 2, axis=1)
    assert ov.overlay_score(big, tpl) > 0.15


# ===========================================================================
# 3. round-trip
# ===========================================================================
def test_template_round_trips_through_disk(tmp_path, tpl):
    p = os.path.join(str(tmp_path), "t.npz")
    ov.save_template(p, tpl)
    back = ov.load_template(p)
    assert back["template"].shape == tpl["template"].shape
    assert back["band"] == tpl["band"]
    s1 = ov.overlay_score(_planted(3), tpl)
    s2 = ov.overlay_score(_planted(3), back)
    assert s1 == pytest.approx(s2, abs=1e-9)


def test_load_template_missing_file_returns_none():
    assert ov.load_template(r"C:\no\such\template.npz") is None


# ===========================================================================
# 4. the gate wiring - FLAG only, and ahead of the wordmark KEEP
# ===========================================================================
_W, _H = 2560, 1440
_MID = (1280.0, 720.0)
_BOTTOM = (1280.0, 1300.0)


def test_overlay_flag_routes_to_qa_not_auto():
    v, reason = cp.gate_decision(1, 0.2, False, 0.5, _MID, _W, _H, [],
                                 overlay_score=0.9)
    assert (v, reason) == ("qa", "centre_overlay")


def test_overlay_flag_fires_with_no_boxes_at_all():
    """Two measured misses carry no YOLO box at ANY conf; n=0 must still flag."""
    v, reason = cp.gate_decision(0, 0.0, False, 0.0, None, _W, _H, [],
                                 overlay_score=0.9)
    assert (v, reason) == ("qa", "centre_overlay")


def test_overlay_flag_beats_the_lol_logo_keep():
    """seraphine + the-ruined-king-viego: wordmark KEPT while a DA overlay sat
    in the middle of the frame. The flag must win over rule 2."""
    lol = ["LEAGUE OF LEGENDS"]
    assert cp.is_lol_logo(lol) is True
    v, reason = cp.gate_decision(1, 0.76, False, 0.45, _BOTTOM, _W, _H, lol,
                                 overlay_score=0.9)
    assert (v, reason) == ("qa", "centre_overlay")
    # below threshold the KEEP rule is untouched
    v2, reason2 = cp.gate_decision(1, 0.76, False, 0.45, _BOTTOM, _W, _H, lol,
                                   overlay_score=0.0)
    assert (v2, reason2) == ("clean", "lol_logo")


def test_overlay_flag_never_overrides_an_ocr_watermark_auto():
    """A read watermark is a stronger signal than a correlation - auto stands."""
    v, reason = cp.gate_decision(1, 0.9, True, 1.0, _BOTTOM, _W, _H,
                                 ["patreon.com/x"], overlay_score=0.9)
    assert (v, reason) == ("auto", "watermark_ocr")


def test_gate_default_is_unchanged_without_a_score():
    """Every existing caller passes no score; behaviour must be identical."""
    assert cp.gate_decision(0, 0.0, False, 0.0, None, _W, _H, []) == (
        "clean", "no_detections")
    assert cp.gate_decision(1, 0.9, False, 0.5, _BOTTOM, _W, _H, []) == (
        "auto", "bottom_banner")


def test_threshold_is_the_calibrated_constant():
    """The threshold is a measured value, not a guess - see the module docstring
    and docs/CLEAN_OVERLAY_DETECTOR_2026-08-11.md."""
    assert cp.OVERLAY_SCORE_MIN == pytest.approx(0.15)
    v, _ = cp.gate_decision(0, 0.0, False, 0.0, None, _W, _H, [],
                            overlay_score=cp.OVERLAY_SCORE_MIN)
    assert v == "qa"
    v2, r2 = cp.gate_decision(0, 0.0, False, 0.0, None, _W, _H, [],
                              overlay_score=cp.OVERLAY_SCORE_MIN - 0.01)
    assert (v2, r2) == ("clean", "no_detections")


# ===========================================================================
# 5. the flag is OFF unless a template has been built
# ===========================================================================
_MISSING = os.path.join("C:", os.sep, "no", "such", "image.png")
def test_centre_overlay_score_is_zero_without_a_template(monkeypatch):
    """CI has no template. A missing one must mean `flag off`, not a crash."""
    monkeypatch.setattr(cp, "_OVERLAY_TEMPLATE", ("unloaded", None))
    monkeypatch.setattr(ov, "load_template", lambda *a, **k: None)
    assert cp.centre_overlay_score(_MISSING) == 0.0


def test_centre_overlay_score_swallows_a_bad_image(monkeypatch):
    """A slug the loader cannot read must not take the whole run down."""
    monkeypatch.setattr(cp, "_OVERLAY_TEMPLATE",
                        ("loaded", {"template": np.zeros((4, 4)),
                                    "support": np.ones((4, 4), dtype=bool),
                                    "band": (0.55, 0.85), "n": 1}))
    assert cp.centre_overlay_score(_MISSING) == 0.0
