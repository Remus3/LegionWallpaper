"""Head-vs-spine ADVISORY DIAGNOSTIC - pure geometry over a keypoint dict (slice S3).

NOTHING IN THE GATE LADDER CONSUMES THIS MODULE, AND NOTHING SHOULD. It is
triage-ordering scaffolding for a human: it says "look at these images first",
never "this image fails". Gating on it was MEASURED AND REJECTED - see THE
CENSUS below before wiring it into G1, G2, or any pass/fail path.

WHY IT WAS BUILT: every G1 metric compares an output image to its OWN source, so
a defect inherent to the source art is invisible to the whole ladder.
`fiora1_firstdone.png` shipped with the head visibly off the model's spine at
ms_ssim 0.997113 / lpips 0.043644, verdict PASS, zero reasons. The idea was that
head-vs-spine lateral offset would catch what a self-referential metric cannot.

THE CENSUS (288 approved firstdones, DWPose in .venv-gen, 0 errors, 0 zero-figure
detections) says it does not:

  - MEASURABLE at min_conf 0.3: 115 of 288, i.e. 39.9 percent. The other 173 fail
    the shoulder/hip confidence floor outright. Anything keyed on this metric is
    SILENT on 60 percent of the corpus.
  - abs(offset_norm) over those 115: min 0.0078, p25 0.0877, median 0.1638,
    p75 0.3036, p90 0.4298, p95 0.5208, max 1.7349, mean 0.2217, stdev 0.2328.
  - THE DECIDING NUMBER: fiora1 - the ONE image a human actually rejected as
    visually bad - measures abs 0.1446 and ranks 66 of 115, the 43.5th
    percentile. It is BELOW the corpus median for badness. The originally
    shipped FLAG threshold of 0.15 sat essentially ON the median (0.1638), so it
    would have flagged roughly half of an ALREADY-APPROVED corpus while still
    passing the one image the operator threw out. There is no threshold on this
    axis that separates the operator's percept, because the metric is not
    measuring the operator's percept.
  - THE TAIL IS NOT ANATOMY, IT IS LOCALIZER FAILURE - confirmed by overlaying
    the detected axis on the two worst images. `silver-fang-akali...` at
    offset_norm -1.7349 has a detected shoulder width of 120.1 px and
    `150-cleanup` at -1.3001 has 59.2 px, both on 2560x1440 images. A correctly
    detected figure (fiora1) measures 357.4 px of shoulder against 610.2 px of
    spine. DWPose collapses the shoulders on twisted and crouched poses; the
    dramatic numbers are bad keypoints, not bad art.

WHY 60 PERCENT IS UNMEASURABLE, AND WHY A BETTER LOCALIZER CANNOT FIX IT - this
is the more damning finding of the two. Per-joint confidence failures among the
173 unmeasurable images: left_hip 157, right_hip 159, left_shoulder 108,
right_shoulder 121, and 80 images have no head point at all above 0.3. The HIPS
dominate: roughly 91 percent of unmeasurable images (157-159 of 173) fail because
the hips are not confidently detected. That is a property of the CORPUS, not a
DWPose defect - wallpaper splash art is routinely cropped at or above the waist,
or the hips are buried under clothing, weapons and effects. A spine axis DEFINED
as hip-mid to shoulder-mid therefore cannot be computed on most of this corpus as
a matter of framing. Swapping in a better pose model does not help: no model can
find hips that are outside the crop. Any future attempt to make this axis gateable
has to change the DEFINITION of the axis, not the localizer.

Per-image figure counts, for context on a module that measures ONE figure: 261
single-figure images, 13 with 2, 5 with 3, 5 with 4, 3 with 5, 1 with 9.

CONCLUSION: head-spine lateral offset from DWPose keypoints does NOT capture the
operator's percept on this stylized-illustration corpus, and it will NOT be wired
into the gate ladder as pass/fail. This module is kept because its REFUSALS are
worth more than its numbers: `head_spine_offset` is now the place that says
out loud when a detected skeleton is not credible.

RETURN CONTRACT (changed in the rework, callers must be updated): this function
NEVER returns None. It returns a `HeadSpineResult` (ok=True) or a
`HeadSpineRefusal` (ok=False, with a machine-readable `reason`). Branch on
`.ok`, never on `is None`. A refusal is not a zero and not a pass - 60 percent of
the corpus is unmeasurable, so that distinction is the entire point.

Deliberately dependency-free (stdlib `math` only). The pose model that produces
the keypoints is expensive and platform-fragile; keeping the math here means the
scoring logic is unit-testable with no model, no torch, and no onnx present.

Keypoint contract: a mapping of COCO-WholeBody-style joint name -> (x, y, conf)
in PIXEL coordinates. Required for the spine: left_shoulder, right_shoulder,
left_hip, right_hip. Head centroid: whichever of nose / left_eye / right_eye /
left_ear / right_ear clear min_conf.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple, Union

# Head points contribute to the centroid; any subset that clears min_conf works,
# so a profile view with one ear occluded still measures.
HEAD_POINT_NAMES: Tuple[str, ...] = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
)
SPINE_POINT_NAMES: Tuple[str, ...] = (
    "left_shoulder", "right_shoulder", "left_hip", "right_hip",
)

DEFAULT_MIN_CONF = 0.3

# Census percentiles of abs(offset_norm) over the 115 measurable images. These are
# DISTRIBUTION MARKERS FOR TRIAGE ORDERING, NOT QUALITY THRESHOLDS: by
# construction 10 percent and 5 percent of an ALREADY-APPROVED corpus sit above
# them, and the one image the operator rejected sits at the 43.5th percentile,
# far below both. Crossing one means "unusual for this corpus, worth a look
# sooner", and it is the extremes that turned out to be localizer failure rather
# than bad art - so a crossing is as likely to indicate a bad skeleton as a bad
# figure. Do not turn either number into a verdict.
HEAD_SPINE_P90_NORM = 0.4298
HEAD_SPINE_P95_NORM = 0.5208

# DETECTION-SANITY FLOOR, NOT AN ANATOMY JUDGEMENT. shoulder_width_px divided by
# spine_len_px, below which the skeleton is not credible enough to normalize by.
# It says "these keypoints are not a body", never "this body is wrong".
#
# Shoulder width is this metric's DENOMINATOR, so once it collapses offset_norm is
# arithmetic on noise and refusing beats reporting a dramatic number. The census
# ratio distribution over the 115 measurable figures: min 0.215, p05 0.424,
# p10 0.461, p25 0.586, median 0.684, p75 0.760, max 1.560. The two detections
# confirmed bad by eye sit at the very bottom - silver-fang-akali at 0.215
# (120.1 px over 558.0 px) is the corpus MINIMUM and 150-cleanup at 0.251
# (59.2 px over 235.5 px) is next. The known-good fiora1 detection is 0.586,
# exactly the p25.
#
# 0.35 is a round value inside the whole band that separates those cases
# (roughly 0.30 to 0.40), deliberately not tuned tighter: the bad cases are n=2
# and the floor's job is to catch a collapsed skeleton, not to be precise. It
# clears both confirmed collapses by ~0.10, leaves fiora1 a wide margin, and sits
# below the p05 of 0.424, so it discards under 5 percent of currently-measurable
# figures. A genuine deep-profile or hard-foreshortened pose projects to a small
# width too and will also be refused - correctly, because a collapsed denominator
# makes the metric meaningless whatever the cause.
MIN_SHOULDER_SPINE_RATIO = 0.35

# Refusal reasons. Callers route on these, so they are stable strings.
REFUSE_SPINE_POINT_MISSING = "spine_point_missing"
REFUSE_SPINE_POINT_LOW_CONF = "spine_point_low_conf"
REFUSE_DEGENERATE_SHOULDERS = "degenerate_shoulders"
REFUSE_DEGENERATE_SPINE = "degenerate_spine"
REFUSE_IMPLAUSIBLE_GEOMETRY = "implausible_geometry"
REFUSE_NO_HEAD_POINTS = "no_head_points"

REFUSAL_REASONS: Tuple[str, ...] = (
    REFUSE_SPINE_POINT_MISSING,
    REFUSE_SPINE_POINT_LOW_CONF,
    REFUSE_DEGENERATE_SHOULDERS,
    REFUSE_DEGENERATE_SPINE,
    REFUSE_IMPLAUSIBLE_GEOMETRY,
    REFUSE_NO_HEAD_POINTS,
)


@dataclass(frozen=True)
class HeadSpineResult:
    """One head-vs-spine measurement that the geometry supported.

    offset_norm is the number; offset_px / shoulder_width_px / spine_len_px are
    retained so a later census can re-derive percentiles without re-running the
    pose model, and so a suspiciously small skeleton stays visible to a caller.
    """

    offset_px: float
    offset_norm: float
    shoulder_width_px: float
    spine_len_px: float
    head_points_used: Tuple[str, ...]
    sign: int
    ok: bool = True


@dataclass(frozen=True)
class HeadSpineRefusal:
    """Why no measurement was possible. NOT a zero and NOT a pass.

    `detail` names the offending joint or carries the measured ratio, purely for
    a human reading a triage log. Geometry that WAS established before the
    refusal is passed through so a caller can see how collapsed the skeleton was.
    """

    reason: str
    detail: str = ""
    shoulder_width_px: float = 0.0
    spine_len_px: float = 0.0
    ok: bool = False

    def __bool__(self) -> bool:
        # The pre-rework contract returned None here, so existing callers guard
        # with a truthiness or `is None` check. A dataclass is truthy by default,
        # which would silently promote a refusal to a measurement - the one
        # failure mode this module exists to prevent. Staying falsey keeps those
        # callers routing unmeasurable images to review instead of past it.
        return False


HeadSpineOutcome = Union[HeadSpineResult, HeadSpineRefusal]


def _point(
    kp: Mapping[str, Sequence[float]], name: str, min_conf: float,
) -> Tuple[bool, float, float]:
    """(present_and_confident, x, y). Absent and low-conf are separate refusals."""
    entry = kp.get(name)
    if entry is None or len(entry) < 3:
        return False, 0.0, 0.0
    if float(entry[2]) < min_conf:
        return False, 0.0, 0.0
    return True, float(entry[0]), float(entry[1])


def _has_key(kp: Mapping[str, Sequence[float]], name: str) -> bool:
    entry = kp.get(name)
    return entry is not None and len(entry) >= 3


def head_spine_offset(
    kp: Mapping[str, Sequence[float]], min_conf: float = DEFAULT_MIN_CONF,
) -> HeadSpineOutcome:
    """Signed perpendicular offset of the head center from the spine axis.

    ADVISORY ONLY - see the module docstring; this is not a gate verdict and the
    census rejected it as one.

    Returns `HeadSpineResult` (ok=True) or `HeadSpineRefusal` (ok=False) with a
    reason drawn from REFUSAL_REASONS. Never returns None.
    """
    spine = {}
    for name in SPINE_POINT_NAMES:
        found, x, y = _point(kp, name, min_conf)
        if not found:
            if _has_key(kp, name):
                return HeadSpineRefusal(REFUSE_SPINE_POINT_LOW_CONF, detail=name)
            return HeadSpineRefusal(REFUSE_SPINE_POINT_MISSING, detail=name)
        spine[name] = (x, y)

    lsx, lsy = spine["left_shoulder"]
    rsx, rsy = spine["right_shoulder"]
    lhx, lhy = spine["left_hip"]
    rhx, rhy = spine["right_hip"]

    shoulder_width_px = math.hypot(rsx - lsx, rsy - lsy)
    if shoulder_width_px <= 0.0:
        return HeadSpineRefusal(REFUSE_DEGENERATE_SHOULDERS)

    shoulder_mid = ((lsx + rsx) / 2.0, (lsy + rsy) / 2.0)
    hip_mid = ((lhx + rhx) / 2.0, (lhy + rhy) / 2.0)

    axis_x = shoulder_mid[0] - hip_mid[0]
    axis_y = shoulder_mid[1] - hip_mid[1]
    spine_len_px = math.hypot(axis_x, axis_y)
    if spine_len_px <= 0.0:
        return HeadSpineRefusal(
            REFUSE_DEGENERATE_SPINE, shoulder_width_px=shoulder_width_px,
        )

    ratio = shoulder_width_px / spine_len_px
    if ratio < MIN_SHOULDER_SPINE_RATIO:
        return HeadSpineRefusal(
            REFUSE_IMPLAUSIBLE_GEOMETRY,
            detail=f"shoulder_spine_ratio={ratio:.4f}",
            shoulder_width_px=shoulder_width_px,
            spine_len_px=spine_len_px,
        )

    head_used = []
    sum_x = 0.0
    sum_y = 0.0
    for name in HEAD_POINT_NAMES:
        found, x, y = _point(kp, name, min_conf)
        if not found:
            continue
        head_used.append(name)
        sum_x += x
        sum_y += y
    if not head_used:
        return HeadSpineRefusal(
            REFUSE_NO_HEAD_POINTS,
            shoulder_width_px=shoulder_width_px,
            spine_len_px=spine_len_px,
        )
    head_center = (sum_x / len(head_used), sum_y / len(head_used))

    # 2D cross product of the spine direction with hip->head, divided by the
    # spine length: the signed distance from the infinite spine LINE. Measuring
    # against the line (not the image vertical) is what makes an artistically
    # leaning figure score the same as an upright one; the sign only says which
    # side of the spine the head sits on, so callers key on abs().
    rel_x = head_center[0] - hip_mid[0]
    rel_y = head_center[1] - hip_mid[1]
    cross = axis_x * rel_y - axis_y * rel_x
    offset_px = cross / spine_len_px

    if offset_px > 0.0:
        sign = 1
    elif offset_px < 0.0:
        sign = -1
    else:
        sign = 0

    return HeadSpineResult(
        offset_px=offset_px,
        offset_norm=offset_px / shoulder_width_px,
        shoulder_width_px=shoulder_width_px,
        spine_len_px=spine_len_px,
        head_points_used=tuple(head_used),
        sign=sign,
    )


# Triage bands. NOT verdicts - the vocabulary is deliberately not PASS/FLAG/FAIL,
# because the rework deleted a classifier that returned exactly those three
# strings and would have been read as a gate result within a release or two.
BAND_TYPICAL = "TYPICAL"
BAND_ABOVE_P90 = "ABOVE_P90"
BAND_ABOVE_P95 = "ABOVE_P95"


def triage_band(
    offset_norm: float,
    p90: float = HEAD_SPINE_P90_NORM,
    p95: float = HEAD_SPINE_P95_NORM,
) -> str:
    """Where abs(offset_norm) sits in the approved-corpus distribution.

    Answers "how unusual is this for the corpus", NOT "is this acceptable" - the
    census found the operator's one rejection at the 43.5th percentile, so a
    TYPICAL band is not evidence of quality and an ABOVE_P95 band is not
    evidence of a defect (it is more often a collapsed skeleton). Use it to
    ORDER a review queue and nothing else.

    Keyed on abs() because a head off the spine reads the same either way.
    """
    if not p90 <= p95:
        raise ValueError("p90 marker must not exceed p95 marker")
    magnitude = abs(offset_norm)
    if magnitude >= p95:
        return BAND_ABOVE_P95
    if magnitude >= p90:
        return BAND_ABOVE_P90
    return BAND_TYPICAL
