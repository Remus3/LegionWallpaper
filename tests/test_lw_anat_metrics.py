"""Tests for the head-vs-spine advisory diagnostic in tools/lw_anat_metrics.py.

Slice S3, reworked after the corpus census. Two things are pinned here:

1. THE GEOMETRY INVARIANTS, which are the actual product requirement and which
   survived the census unchanged:
     - translation / scale invariance: the metric must not depend on where in the
       frame the figure sits or how big it is (crops and upscales must agree).
     - ROTATION invariance: it must measure head-vs-spine, never
       head-vs-image-vertical. An artistically leaning figure is not a defect.
     - mirror antisymmetry: leaning left is the same magnitude as leaning right.

2. THE NEGATIVE RESULT. The census over 288 approved firstdones found only 115
   measurable, and found fiora1 - the one image the operator rejected - at the
   43.5th percentile of abs(offset_norm), below the corpus median. So the tests
   below assert that the module exposes NO pass/fail verdict, that the real
   fiora1 geometry lands in the TYPICAL triage band (the metric does not see what
   the human saw), and that a collapsed skeleton is REFUSED with a reason rather
   than reported as a dramatic number.

Stdlib + pytest only - no torch / onnx / numpy, which is the point of keeping the
math in its own module: it tests with no pose model present.
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
    spine length 120, so the shoulder/spine ratio is 0.5 - comfortably clear of
    the detection-sanity floor.
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


def _figure(
    shoulder_mid: tuple,
    hip_mid: tuple,
    shoulder_width: float,
    head_offset_px: float = 0.0,
    conf: float = 0.9,
) -> dict:
    """Skeleton built from the quantities the census actually reported.

    Lets a real measured case (shoulder mid, hip mid, detected shoulder width) be
    reproduced exactly, so the calibration tests below run on the same numbers
    that were confirmed by eye against the images.

    Shoulders and hips straddle the spine axis perpendicularly, so the detected
    shoulder width is exactly `shoulder_width`. The head sits above the shoulders
    at exactly `head_offset_px` of perpendicular offset from the axis.
    """
    axis_x = shoulder_mid[0] - hip_mid[0]
    axis_y = shoulder_mid[1] - hip_mid[1]
    length = math.hypot(axis_x, axis_y)
    ux, uy = axis_x / length, axis_y / length
    px, py = -uy, ux  # unit perpendicular to the spine axis
    half = shoulder_width / 2.0
    head_x = hip_mid[0] + 1.3 * length * ux + head_offset_px * px
    head_y = hip_mid[1] + 1.3 * length * uy + head_offset_px * py
    return {
        "nose": (head_x, head_y, conf),
        "left_shoulder": (shoulder_mid[0] - half * px, shoulder_mid[1] - half * py, conf),
        "right_shoulder": (shoulder_mid[0] + half * px, shoulder_mid[1] + half * py, conf),
        "left_hip": (hip_mid[0] - half * px, hip_mid[1] - half * py, conf),
        "right_hip": (hip_mid[0] + half * px, hip_mid[1] + half * py, conf),
    }


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
    assert res.ok
    assert res.offset_norm == pytest.approx(0.0, abs=1e-12)
    assert res.offset_px == pytest.approx(0.0, abs=1e-9)
    assert res.shoulder_width_px == pytest.approx(60.0)
    assert res.spine_len_px == pytest.approx(120.0)
    assert res.sign == 0


def test_all_five_head_points_are_used_when_confident():
    res = anat.head_spine_offset(_skeleton())
    assert res.ok
    assert set(res.head_points_used) == {
        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    }


def test_low_confidence_head_points_are_dropped_from_the_centroid():
    kp = _skeleton()
    for name in ("left_ear", "right_ear", "left_eye", "right_eye"):
        x, y, _ = kp[name]
        kp[name] = (x, y, 0.05)
    res = anat.head_spine_offset(kp, min_conf=0.3)
    assert res.ok
    assert res.head_points_used == ("nose",)


def test_conf_exactly_at_min_conf_is_accepted():
    assert anat.head_spine_offset(_skeleton(conf=0.3), min_conf=0.3).ok


# --------------------------------------------------------------------------
# head_spine_offset - invariances (the product requirement)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("dx,dy", [(0.0, 0.0), (37.0, -12.0), (-1000.0, 2500.0), (0.5, 0.5)])
@pytest.mark.parametrize("head_dx", [0.0, 9.0, -21.0])
def test_translation_leaves_offset_norm_unchanged(dx, dy, head_dx):
    base = anat.head_spine_offset(_skeleton(head_dx=head_dx))
    moved = anat.head_spine_offset(_translate(_skeleton(head_dx=head_dx), dx, dy))
    assert base.ok and moved.ok
    assert moved.offset_norm == pytest.approx(base.offset_norm, abs=1e-9)
    assert moved.offset_px == pytest.approx(base.offset_px, abs=1e-6)


@pytest.mark.parametrize("s", [0.25, 0.5, 2.0, 7.5])
@pytest.mark.parametrize("head_dx", [0.0, 9.0, -21.0])
def test_uniform_scale_leaves_norm_but_scales_px(s, head_dx):
    base = anat.head_spine_offset(_skeleton(head_dx=head_dx))
    scaled = anat.head_spine_offset(_scale(_skeleton(head_dx=head_dx), s))
    assert base.ok and scaled.ok
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
    assert base.ok and turned.ok
    assert turned.offset_norm == pytest.approx(base.offset_norm, abs=1e-9)
    # Which side of the spine the head sits on must survive rotation too - but
    # only where there IS a side. A perfectly aligned head rotates into float
    # noise around zero, and the sign of that noise is not meaningful.
    if abs(base.offset_norm) > 1e-6:
        assert turned.sign == base.sign


def test_a_steeply_leaning_but_aligned_figure_reads_as_typical():
    res = anat.head_spine_offset(_rotate(_skeleton(), 40.0, 100.0, 200.0))
    assert res.ok
    assert res.offset_norm == pytest.approx(0.0, abs=1e-9)
    assert anat.triage_band(res.offset_norm) == anat.BAND_TYPICAL


@pytest.mark.parametrize("head_dx", [3.0, 9.0, 30.0, -9.0])
def test_mirroring_flips_the_sign_and_preserves_the_magnitude(head_dx):
    base = anat.head_spine_offset(_skeleton(head_dx=head_dx))
    flipped = anat.head_spine_offset(_mirror_x(_skeleton(head_dx=head_dx)))
    assert base.ok and flipped.ok
    assert flipped.offset_norm == pytest.approx(-base.offset_norm, abs=1e-9)
    assert abs(flipped.offset_norm) == pytest.approx(abs(base.offset_norm), abs=1e-9)
    assert flipped.sign == -base.sign


def test_lateral_head_displacement_increases_offset_monotonically():
    seen = []
    for head_dx in (0.0, 1.0, 3.0, 6.0, 12.0, 24.0, 48.0):
        res = anat.head_spine_offset(_skeleton(head_dx=head_dx))
        assert res.ok
        seen.append(abs(res.offset_norm))
    assert seen == sorted(seen)
    # strict=False is deliberate: seen[1:] is one shorter BY DESIGN - this is the
    # pairwise idiom, not a length bug. strict=True would raise on every call.
    assert all(b > a for a, b in zip(seen, seen[1:], strict=False))


def test_head_displacement_along_the_spine_does_not_register():
    """Only the PERPENDICULAR component is the defect - a low head is not a lean."""
    res = anat.head_spine_offset(_skeleton(head_dy=55.0))
    assert res.ok
    assert res.offset_norm == pytest.approx(0.0, abs=1e-9)


def test_the_figure_helper_reproduces_the_quantities_it_was_given():
    """Guards the calibration fixtures below - a wrong helper would fake a pass."""
    res = anat.head_spine_offset(_figure((100.0, 100.0), (100.0, 500.0), 300.0, 45.0))
    assert res.ok
    assert res.shoulder_width_px == pytest.approx(300.0)
    assert res.spine_len_px == pytest.approx(400.0)
    assert abs(res.offset_px) == pytest.approx(45.0)


# --------------------------------------------------------------------------
# the census result: this metric does not see what the operator saw
# --------------------------------------------------------------------------
def test_fiora1_the_one_rejected_image_reads_as_TYPICAL():
    """The negative result, pinned.

    fiora1 is the only image the operator flagged as visually bad. Its measured
    abs(offset_norm) is 0.1446, rank 66 of 115, the 43.5th percentile - below the
    corpus median of 0.1638. If this ever starts reporting an alarming band, the
    constants have been quietly re-tuned into a gate and the census that rejected
    that idea needs re-reading.
    """
    offset_px = 0.1446 * 357.4
    res = anat.head_spine_offset(_figure((100.0, 200.0), (100.0, 810.2), 357.4, offset_px))
    assert res.ok
    assert abs(res.offset_norm) == pytest.approx(0.1446, abs=1e-4)
    assert anat.triage_band(res.offset_norm) == anat.BAND_TYPICAL
    assert abs(res.offset_norm) < anat.HEAD_SPINE_P90_NORM


def test_fiora1_geometry_clears_the_detection_sanity_floor():
    """A correctly detected stylized figure must still be measurable."""
    res = anat.head_spine_offset(_figure((100.0, 200.0), (100.0, 810.2), 357.4, 20.0))
    assert res.ok
    assert res.shoulder_width_px / res.spine_len_px == pytest.approx(0.5857, abs=1e-3)


def test_silver_fang_akali_collapsed_shoulders_are_refused_not_measured():
    """offset_norm -1.7349 was the corpus maximum and it was a bad skeleton.

    Confirmed by overlaying the detected axis on the image: 120.1 px of shoulder
    on a 2560x1440 canvas is DWPose collapsing a twisted pose, not a slim figure.
    """
    out = anat.head_spine_offset(_figure((1679.2, 386.2), (1803.6, 930.2), 120.1, 400.0))
    assert not out.ok
    assert out.reason == anat.REFUSE_IMPLAUSIBLE_GEOMETRY


def test_150_cleanup_collapsed_shoulders_are_refused_not_measured():
    """The second-worst case, 59.2 px of shoulder - same localizer failure."""
    out = anat.head_spine_offset(_figure((2010.2, 837.6), (1918.5, 1054.5), 59.2, 70.0))
    assert not out.ok
    assert out.reason == anat.REFUSE_IMPLAUSIBLE_GEOMETRY


def test_the_sanity_floor_sits_loosely_between_the_confirmed_cases():
    """Not fitted to n=2 - margin on both sides is the point.

    Census ratio distribution over the 115 measurable figures: min 0.215,
    p05 0.424, p25 0.586, median 0.684, max 1.560.
    """
    akali_ratio = 120.1 / math.hypot(1803.6 - 1679.2, 930.2 - 386.2)
    cleanup_ratio = 59.2 / math.hypot(2010.2 - 1918.5, 837.6 - 1054.5)
    fiora_ratio = 357.4 / 610.2
    assert akali_ratio == pytest.approx(0.215, abs=1e-3)
    assert cleanup_ratio == pytest.approx(0.251, abs=1e-3)
    assert fiora_ratio == pytest.approx(0.586, abs=1e-3)
    assert max(akali_ratio, cleanup_ratio) + 0.08 < anat.MIN_SHOULDER_SPINE_RATIO
    assert anat.MIN_SHOULDER_SPINE_RATIO + 0.15 < fiora_ratio


def test_the_sanity_floor_stays_below_the_census_p05():
    """It must discard under 5 percent of currently-measurable figures.

    A floor above the p05 of 0.424 would start throwing away real detections to
    chase two known-bad ones, which is how a sanity check turns into a bad gate.
    """
    census_p05 = 0.424
    assert 0.30 <= anat.MIN_SHOULDER_SPINE_RATIO <= 0.40
    assert anat.MIN_SHOULDER_SPINE_RATIO < census_p05


@pytest.mark.parametrize("ratio,measurable", [(0.34, False), (0.35, True), (0.36, True)])
def test_the_sanity_floor_is_inclusive_at_its_own_value(ratio, measurable):
    out = anat.head_spine_offset(_figure((0.0, -100.0), (0.0, 0.0), ratio * 100.0, 5.0))
    assert out.ok is measurable


def test_implausible_geometry_refusal_reports_the_geometry_it_rejected():
    """A triage log has to show WHY the skeleton was judged not credible."""
    out = anat.head_spine_offset(_figure((0.0, -400.0), (0.0, 0.0), 40.0, 10.0))
    assert out.reason == anat.REFUSE_IMPLAUSIBLE_GEOMETRY
    assert out.shoulder_width_px == pytest.approx(40.0)
    assert out.spine_len_px == pytest.approx(400.0)
    assert "0.1" in out.detail


# --------------------------------------------------------------------------
# every refusal path, asserted separately, with its own reason
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "missing", ["left_shoulder", "right_shoulder", "left_hip", "right_hip"],
)
def test_refuses_when_a_required_spine_point_is_absent(missing):
    kp = _skeleton()
    del kp[missing]
    out = anat.head_spine_offset(kp)
    assert not out.ok
    assert out.reason == anat.REFUSE_SPINE_POINT_MISSING
    assert out.detail == missing


@pytest.mark.parametrize(
    "weak", ["left_shoulder", "right_shoulder", "left_hip", "right_hip"],
)
def test_refuses_with_a_distinct_reason_when_a_spine_point_is_below_min_conf(weak):
    """Low confidence is a different problem from a joint the model never emitted.

    173 of 288 approved images refuse on exactly this path, so it is the one a
    caller reports on most and it must not be lumped in with missing keys.
    """
    kp = _skeleton()
    x, y, _ = kp[weak]
    kp[weak] = (x, y, 0.29)
    out = anat.head_spine_offset(kp, min_conf=0.3)
    assert not out.ok
    assert out.reason == anat.REFUSE_SPINE_POINT_LOW_CONF
    assert out.detail == weak


def test_refuses_when_no_head_point_is_present():
    kp = _skeleton()
    for name in anat.HEAD_POINT_NAMES:
        del kp[name]
    out = anat.head_spine_offset(kp)
    assert not out.ok
    assert out.reason == anat.REFUSE_NO_HEAD_POINTS


def test_refuses_when_every_head_point_is_below_min_conf():
    kp = _skeleton()
    for name in anat.HEAD_POINT_NAMES:
        x, y, _ = kp[name]
        kp[name] = (x, y, 0.1)
    out = anat.head_spine_offset(kp, min_conf=0.3)
    assert not out.ok
    assert out.reason == anat.REFUSE_NO_HEAD_POINTS


def test_refuses_on_a_degenerate_zero_length_spine():
    kp = _skeleton()
    kp["left_hip"] = (70.0, 80.0, 0.9)
    kp["right_hip"] = (130.0, 80.0, 0.9)
    out = anat.head_spine_offset(kp)
    assert not out.ok
    assert out.reason == anat.REFUSE_DEGENERATE_SPINE


def test_refuses_on_zero_shoulder_width():
    kp = _skeleton()
    kp["left_shoulder"] = (100.0, 80.0, 0.9)
    kp["right_shoulder"] = (100.0, 80.0, 0.9)
    out = anat.head_spine_offset(kp)
    assert not out.ok
    assert out.reason == anat.REFUSE_DEGENERATE_SHOULDERS


def test_refuses_on_an_empty_keypoint_mapping():
    out = anat.head_spine_offset({})
    assert not out.ok
    assert out.reason == anat.REFUSE_SPINE_POINT_MISSING


def test_a_malformed_keypoint_entry_counts_as_missing():
    kp = _skeleton()
    kp["left_hip"] = (80.0, 200.0)
    out = anat.head_spine_offset(kp)
    assert out.reason == anat.REFUSE_SPINE_POINT_MISSING


def test_every_declared_refusal_reason_is_actually_reachable():
    """A reason a caller can never observe is a lie in the public API."""
    low_conf = _skeleton()
    low_conf["left_hip"] = (80.0, 200.0, 0.01)
    headless = {n: v for n, v in _skeleton().items() if n not in anat.HEAD_POINT_NAMES}
    flat_spine = _skeleton()
    flat_spine["left_hip"] = (70.0, 80.0, 0.9)
    flat_spine["right_hip"] = (130.0, 80.0, 0.9)
    no_shoulders = _skeleton()
    no_shoulders["left_shoulder"] = (100.0, 80.0, 0.9)
    no_shoulders["right_shoulder"] = (100.0, 80.0, 0.9)
    cases = [
        {}, low_conf, headless, flat_spine, no_shoulders,
        _figure((0.0, -400.0), (0.0, 0.0), 40.0),
    ]
    observed = set()
    for kp in cases:
        out = anat.head_spine_offset(kp)
        assert not out.ok
        observed.add(out.reason)
    assert observed == set(anat.REFUSAL_REASONS)


# --------------------------------------------------------------------------
# the contract: unmeasurable can never be read as a measurement or a pass
# --------------------------------------------------------------------------
def test_unmeasurable_is_distinguishable_from_a_measured_zero():
    """An unmeasurable image must route to review, never silently PASS."""
    measured = anat.head_spine_offset(_skeleton())
    assert measured.ok and measured.offset_norm == pytest.approx(0.0, abs=1e-12)
    refused = anat.head_spine_offset({})
    assert not refused.ok
    assert not hasattr(refused, "offset_norm")


def test_head_spine_offset_never_returns_none():
    """The reworked contract: an outcome object always, so a reason always exists."""
    for kp in ({}, _skeleton(), _figure((0.0, -400.0), (0.0, 0.0), 40.0)):
        assert anat.head_spine_offset(kp) is not None


def test_a_refusal_is_falsey_so_a_legacy_truthiness_guard_still_routes_to_review():
    """The old contract returned None; a truthy refusal would silently pass it."""
    assert not bool(anat.head_spine_offset({}))
    assert bool(anat.head_spine_offset(_skeleton()))


def test_both_outcome_types_are_frozen():
    res = anat.head_spine_offset(_skeleton())
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.offset_norm = 1.0
    out = anat.head_spine_offset({})
    with pytest.raises(dataclasses.FrozenInstanceError):
        out.reason = "nope"


def test_outcome_types_are_the_two_documented_ones():
    assert isinstance(anat.head_spine_offset(_skeleton()), anat.HeadSpineResult)
    assert isinstance(anat.head_spine_offset({}), anat.HeadSpineRefusal)


# --------------------------------------------------------------------------
# triage_band - ordering only, and provably not a verdict
# --------------------------------------------------------------------------
def test_the_module_exposes_no_pass_fail_verdict_api():
    """The census rejected gating on this metric; the API must not offer it.

    classify_head_spine returned PASS / FLAG / FAIL off a-priori thresholds whose
    FLAG value (0.15) sat on the corpus median while still passing the operator's
    one rejection. It was deleted rather than retuned, because those three strings
    are the gate ladder's own vocabulary and would be read as a gate result no
    matter what the docstring said.
    """
    for gone in ("classify_head_spine", "HEAD_SPINE_FLAG_NORM", "HEAD_SPINE_FAIL_NORM"):
        assert not hasattr(anat, gone)


def test_band_names_are_not_gate_verdicts():
    bands = {anat.BAND_TYPICAL, anat.BAND_ABOVE_P90, anat.BAND_ABOVE_P95}
    assert bands.isdisjoint({"PASS", "FLAG", "FAIL", "WARN", "OK"})


def test_census_markers_are_ordered_and_match_the_measured_percentiles():
    assert 0.0 < anat.HEAD_SPINE_P90_NORM < anat.HEAD_SPINE_P95_NORM
    assert anat.HEAD_SPINE_P90_NORM == pytest.approx(0.4298)
    assert anat.HEAD_SPINE_P95_NORM == pytest.approx(0.5208)


def test_the_markers_sit_above_the_corpus_median_not_on_it():
    """The shipped 0.15 FLAG sat on the median (0.1638); that is what went wrong."""
    corpus_median = 0.1638
    assert anat.HEAD_SPINE_P90_NORM > corpus_median * 2


@pytest.mark.parametrize(
    "offset_norm,expected",
    [
        (0.0, anat.BAND_TYPICAL),
        (0.1446, anat.BAND_TYPICAL),
        (0.1638, anat.BAND_TYPICAL),
        (0.3036, anat.BAND_TYPICAL),
        (anat.HEAD_SPINE_P90_NORM - 1e-9, anat.BAND_TYPICAL),
        (anat.HEAD_SPINE_P90_NORM, anat.BAND_ABOVE_P90),
        (-anat.HEAD_SPINE_P90_NORM, anat.BAND_ABOVE_P90),
        (anat.HEAD_SPINE_P95_NORM - 1e-9, anat.BAND_ABOVE_P90),
        (anat.HEAD_SPINE_P95_NORM, anat.BAND_ABOVE_P95),
        (-anat.HEAD_SPINE_P95_NORM, anat.BAND_ABOVE_P95),
        (1.7349, anat.BAND_ABOVE_P95),
        (-1.7349, anat.BAND_ABOVE_P95),
    ],
)
def test_band_boundaries_and_negatives(offset_norm, expected):
    assert anat.triage_band(offset_norm) == expected


@pytest.mark.parametrize("offset_norm", [0.0, 0.11, -0.11, 0.45, -0.45, 3.0, -3.0])
def test_band_is_symmetric_in_sign(offset_norm):
    assert anat.triage_band(offset_norm) == anat.triage_band(-offset_norm)


@pytest.mark.parametrize("offset_norm", [0.0, 0.2, -0.9, 5.0])
def test_band_only_ever_returns_a_declared_band(offset_norm):
    assert anat.triage_band(offset_norm) in (
        anat.BAND_TYPICAL, anat.BAND_ABOVE_P90, anat.BAND_ABOVE_P95,
    )


def test_band_honours_injected_markers():
    assert anat.triage_band(0.05, p90=0.02, p95=0.5) == anat.BAND_ABOVE_P90
    assert anat.triage_band(0.05, p90=0.5, p95=0.9) == anat.BAND_TYPICAL
    assert anat.triage_band(-0.95, p90=0.5, p95=0.9) == anat.BAND_ABOVE_P95


def test_band_rejects_inverted_markers():
    with pytest.raises(ValueError):
        anat.triage_band(0.1, p90=0.5, p95=0.2)


def test_bands_order_a_review_queue_by_magnitude():
    """The only sanctioned use: sort the queue, do not judge the images."""
    measured = []
    for head_dx in (0.0, 6.0, 18.0, 30.0, 45.0):
        res = anat.head_spine_offset(_skeleton(head_dx=head_dx))
        assert res.ok
        measured.append((abs(res.offset_norm), anat.triage_band(res.offset_norm)))
    ranks = {anat.BAND_TYPICAL: 0, anat.BAND_ABOVE_P90: 1, anat.BAND_ABOVE_P95: 2}
    band_ranks = [ranks[band] for _, band in measured]
    assert band_ranks == sorted(band_ranks)
    assert band_ranks[0] == 0 and band_ranks[-1] == 2
