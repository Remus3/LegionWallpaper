"""Tests for the pure anatomy-plausibility geometry in tools/lw_anat_metrics.py.

Slice S3. The gate ladder's G1 metrics all compare an output to its OWN source,
so a source-inherent anatomy defect (fiora1_firstdone: head off the spine axis)
scores ms_ssim 0.997 / lpips 0.044 and PASSes. This module is the missing
measurement; these tests pin its INVARIANTS rather than hand-computed values,
because the invariants are the actual product requirement:

  - translation / scale invariance: the metric must not depend on where in the
    frame the figure sits or how big it is (crops and upscales must agree).
  - ROTATION invariance: the metric must measure head-vs-spine, never
    head-vs-image-vertical. An artistically leaning figure is not a defect, and
    a metric that flagged one would be useless on this corpus.
  - mirror antisymmetry: leaning left is the same magnitude as leaning right.

Stdlib + pytest only - no torch / onnx / numpy, which is the point of keeping
the math in its own module: it tests with no pose model present.
"""
from __future__ import annotations

import dataclasses
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_anat_metrics as anat  # noqa: E402


# --------------------------------------------------------------------------
# skeleton fixtures / transforms (all pure dict math)
# --------------------------------------------------------------------------
def _skeleton(head_dx: float = 0.0, head_dy: float = 0.0, conf: float = 0.9) -> dict:
    """Upright, bilaterally symmetric figure with a vertical spine.

    head_dx slides the whole head group laterally, which for this vertical
    spine equals the perpendicular offset in pixels. Shoulder width is 60,
    spine length 120.
    """
    head = {
        "nose": (100.0, 40.0),
        "left_eye": (92.0, 34.0),
        "right_eye": (108.0, 34.0),
        "left_ear": (86.0, 36.0),
        "right_ear": (114.0, 36.0),
    }
    kp = {name: (x + head_dx, y + head_dy, conf) for name, (x, y) in head.items()}
    kp.update({
        "left_shoulder": (70.0, 80.0, conf),
        "right_shoulder": (130.0, 80.0, conf),
        "left_hip": (80.0, 200.0, conf),
        "right_hip": (120.0, 200.0, conf),
    })
    return kp


def _translate(kp: dict, dx: float, dy: float) -> dict:
    return {n: (x + dx, y + dy, c) for n, (x, y, c) in kp.items()}


def _scale(kp: dict, s: float) -> dict:
    return {n: (x * s, y * s, c) for n, (x, y, c) in kp.items()}


def _rotate(kp: dict, deg: float, cx: float, cy: float) -> dict:
    r = math.radians(deg)
    cos_r, sin_r = math.cos(r), math.sin(r)
    out = {}
    for n, (x, y, c) in kp.items():
        px, py = x - cx, y - cy
        out[n] = (cx + px * cos_r - py * sin_r, cy + px * sin_r + py * cos_r, c)
    return out


def _mirror_x(kp: dict) -> dict:
    return {n: (-x, y, c) for n, (x, y, c) in kp.items()}


# --------------------------------------------------------------------------
# head_spine_offset - baseline
# --------------------------------------------------------------------------
def test_upright_symmetric_figure_has_zero_offset():
    res = anat.head_spine_offset(_skeleton())
    assert res is not None
    assert res.offset_norm == pytest.approx(0.0, abs=1e-12)
    assert res.offset_px == pytest.approx(0.0, abs=1e-9)
    assert res.shoulder_width_px == pytest.approx(60.0)
    assert res.spine_len_px == pytest.approx(120.0)
    assert res.sign == 0


def test_all_five_head_points_are_used_when_confident():
    res = anat.head_spine_offset(_skeleton())
    assert res is not None
    assert set(res.head_points_used) == {
        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    }


def test_low_confidence_head_points_are_dropped_from_the_centroid():
    kp = _skeleton()
    for name in ("left_ear", "right_ear", "left_eye", "right_eye"):
        x, y, _ = kp[name]
        kp[name] = (x, y, 0.05)
    res = anat.head_spine_offset(kp, min_conf=0.3)
    assert res is not None
    assert res.head_points_used == ("nose",)


def test_conf_exactly_at_min_conf_is_accepted():
    kp = _skeleton(conf=0.3)
    assert anat.head_spine_offset(kp, min_conf=0.3) is not None


# --------------------------------------------------------------------------
# head_spine_offset - invariances (the product requirement)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("dx,dy", [(0.0, 0.0), (37.0, -12.0), (-1000.0, 2500.0), (0.5, 0.5)])
@pytest.mark.parametrize("head_dx", [0.0, 9.0, -21.0])
def test_translation_leaves_offset_norm_unchanged(dx, dy, head_dx):
    base = anat.head_spine_offset(_skeleton(head_dx=head_dx))
    moved = anat.head_spine_offset(_translate(_skeleton(head_dx=head_dx), dx, dy))
    assert base is not None and moved is not None
    assert moved.offset_norm == pytest.approx(base.offset_norm, abs=1e-9)
    assert moved.offset_px == pytest.approx(base.offset_px, abs=1e-6)


@pytest.mark.parametrize("s", [0.25, 0.5, 2.0, 7.5])
@pytest.mark.parametrize("head_dx", [0.0, 9.0, -21.0])
def test_uniform_scale_leaves_norm_but_scales_px(s, head_dx):
    base = anat.head_spine_offset(_skeleton(head_dx=head_dx))
    scaled = anat.head_spine_offset(_scale(_skeleton(head_dx=head_dx), s))
    assert base is not None and scaled is not None
    assert scaled.offset_norm == pytest.approx(base.offset_norm, abs=1e-9)
    assert scaled.offset_px == pytest.approx(base.offset_px * s, abs=1e-6)
    assert scaled.shoulder_width_px == pytest.approx(base.shoulder_width_px * s)
    assert scaled.spine_len_px == pytest.approx(base.spine_len_px * s)


@pytest.mark.parametrize("deg", [-170.0, -90.0, -33.0, 0.0, 15.0, 90.0, 180.0, 359.0])
@pytest.mark.parametrize("cx,cy", [(0.0, 0.0), (100.0, 140.0), (-500.0, 900.0)])
@pytest.mark.parametrize("head_dx", [0.0, 9.0, -21.0])
def test_rotation_about_any_point_leaves_offset_norm_unchanged(deg, cx, cy, head_dx):
    """A figure leaning artistically must not be flagged - this is the crux."""
    base = anat.head_spine_offset(_skeleton(head_dx=head_dx))
    turned = anat.head_spine_offset(_rotate(_skeleton(head_dx=head_dx), deg, cx, cy))
    assert base is not None and turned is not None
    assert turned.offset_norm == pytest.approx(base.offset_norm, abs=1e-9)
    # Which side of the spine the head sits on must survive rotation too - but
    # only where there IS a side. A perfectly aligned head rotates into float
    # noise around zero, and the sign of that noise is not meaningful.
    if abs(base.offset_norm) > 1e-6:
        assert turned.sign == base.sign


def test_a_steeply_leaning_but_aligned_figure_still_passes():
    leaning = _rotate(_skeleton(), 40.0, 100.0, 200.0)
    res = anat.head_spine_offset(leaning)
    assert res is not None
    assert res.offset_norm == pytest.approx(0.0, abs=1e-9)
    assert anat.classify_head_spine(res.offset_norm) == "PASS"


@pytest.mark.parametrize("head_dx", [3.0, 9.0, 30.0, -9.0])
def test_mirroring_flips_the_sign_and_preserves_the_magnitude(head_dx):
    base = anat.head_spine_offset(_skeleton(head_dx=head_dx))
    flipped = anat.head_spine_offset(_mirror_x(_skeleton(head_dx=head_dx)))
    assert base is not None and flipped is not None
    assert flipped.offset_norm == pytest.approx(-base.offset_norm, abs=1e-9)
    assert abs(flipped.offset_norm) == pytest.approx(abs(base.offset_norm), abs=1e-9)
    assert flipped.sign == -base.sign


def test_lateral_head_displacement_increases_offset_monotonically():
    seen = []
    for head_dx in (0.0, 1.0, 3.0, 6.0, 12.0, 24.0, 48.0):
        res = anat.head_spine_offset(_skeleton(head_dx=head_dx))
        assert res is not None
        seen.append(abs(res.offset_norm))
    assert seen == sorted(seen)
    assert all(b > a for a, b in zip(seen, seen[1:]))


def test_head_displacement_along_the_spine_does_not_register():
    """Only the PERPENDICULAR component is the defect - a low head is not a lean."""
    res = anat.head_spine_offset(_skeleton(head_dy=55.0))
    assert res is not None
    assert res.offset_norm == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------
# head_spine_offset - every unmeasurable path returns None, asserted separately
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "missing", ["left_shoulder", "right_shoulder", "left_hip", "right_hip"],
)
def test_none_when_a_required_spine_point_is_absent(missing):
    kp = _skeleton()
    del kp[missing]
    assert anat.head_spine_offset(kp) is None


@pytest.mark.parametrize(
    "weak", ["left_shoulder", "right_shoulder", "left_hip", "right_hip"],
)
def test_none_when_a_required_spine_point_is_below_min_conf(weak):
    kp = _skeleton()
    x, y, _ = kp[weak]
    kp[weak] = (x, y, 0.29)
    assert anat.head_spine_offset(kp, min_conf=0.3) is None


def test_none_when_no_head_point_is_present():
    kp = _skeleton()
    for name in ("nose", "left_eye", "right_eye", "left_ear", "right_ear"):
        del kp[name]
    assert anat.head_spine_offset(kp) is None


def test_none_when_every_head_point_is_below_min_conf():
    kp = _skeleton()
    for name in ("nose", "left_eye", "right_eye", "left_ear", "right_ear"):
        x, y, _ = kp[name]
        kp[name] = (x, y, 0.1)
    assert anat.head_spine_offset(kp, min_conf=0.3) is None


def test_none_on_a_degenerate_zero_length_spine():
    kp = _skeleton()
    kp["left_hip"] = (70.0, 80.0, 0.9)
    kp["right_hip"] = (130.0, 80.0, 0.9)
    assert anat.head_spine_offset(kp) is None


def test_none_on_zero_shoulder_width():
    kp = _skeleton()
    kp["left_shoulder"] = (100.0, 80.0, 0.9)
    kp["right_shoulder"] = (100.0, 80.0, 0.9)
    assert anat.head_spine_offset(kp) is None


def test_none_on_an_empty_keypoint_mapping():
    assert anat.head_spine_offset({}) is None


def test_unmeasurable_is_distinguishable_from_a_measured_zero():
    """An unmeasurable image must route to review, never silently PASS."""
    measured = anat.head_spine_offset(_skeleton())
    assert measured is not None and measured.offset_norm == pytest.approx(0.0, abs=1e-12)
    assert anat.head_spine_offset({}) is None


def test_result_is_frozen():
    res = anat.head_spine_offset(_skeleton())
    assert res is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.offset_norm = 1.0


# --------------------------------------------------------------------------
# classify_head_spine
# --------------------------------------------------------------------------
def test_module_thresholds_are_ordered():
    assert 0.0 < anat.HEAD_SPINE_FLAG_NORM < anat.HEAD_SPINE_FAIL_NORM


@pytest.mark.parametrize(
    "offset_norm,expected",
    [
        (0.0, "PASS"),
        (0.01, "PASS"),
        (-0.01, "PASS"),
        (anat.HEAD_SPINE_FLAG_NORM - 1e-9, "PASS"),
        (anat.HEAD_SPINE_FLAG_NORM, "FLAG"),
        (-anat.HEAD_SPINE_FLAG_NORM, "FLAG"),
        (anat.HEAD_SPINE_FAIL_NORM - 1e-9, "FLAG"),
        (anat.HEAD_SPINE_FAIL_NORM, "FAIL"),
        (-anat.HEAD_SPINE_FAIL_NORM, "FAIL"),
        (10.0, "FAIL"),
        (-10.0, "FAIL"),
    ],
)
def test_classify_boundaries_and_negatives(offset_norm, expected):
    assert anat.classify_head_spine(offset_norm) == expected


@pytest.mark.parametrize("offset_norm", [0.0, 0.11, -0.11, 0.4, -0.4, 3.0, -3.0])
def test_classify_is_symmetric_in_sign(offset_norm):
    assert anat.classify_head_spine(offset_norm) == anat.classify_head_spine(-offset_norm)


@pytest.mark.parametrize("offset_norm", [0.0, 0.2, -0.9, 5.0])
def test_classify_only_ever_returns_the_three_verdicts(offset_norm):
    assert anat.classify_head_spine(offset_norm) in ("PASS", "FLAG", "FAIL")


def test_classify_honours_injected_thresholds():
    assert anat.classify_head_spine(0.05, flag=0.02, fail=0.5) == "FLAG"
    assert anat.classify_head_spine(0.05, flag=0.5, fail=0.9) == "PASS"
    assert anat.classify_head_spine(-0.95, flag=0.5, fail=0.9) == "FAIL"


def test_classify_rejects_inverted_thresholds():
    with pytest.raises(ValueError):
        anat.classify_head_spine(0.1, flag=0.5, fail=0.2)
