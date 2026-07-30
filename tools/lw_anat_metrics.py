"""Anatomy-plausibility metrics - pure geometry over a keypoint dict (slice S3).

WHY THIS EXISTS: every G1 gate metric compares an output image to its OWN
source, so a defect that is inherent to the source art is invisible to the
whole ladder. `fiora1_firstdone.png` shipped with the head visibly off the
model's spine at ms_ssim 0.997113 / lpips 0.043644, verdict PASS, zero reasons.
288 approved images sit behind that blind spot. These functions measure whether
the DEPICTED BODY is geometrically plausible - a question no self-referential
metric can answer.

Deliberately dependency-free (stdlib `math` only). The pose model that produces
the keypoints is expensive and platform-fragile; keeping the math here means the
scoring logic is unit-testable with no model, no torch, and no onnx present.
The S4 probe imports these two functions and supplies the keypoints.

Keypoint contract: a mapping of COCO-WholeBody-style joint name -> (x, y, conf)
in PIXEL coordinates. Required for the spine: left_shoulder, right_shoulder,
left_hip, right_hip. Head centroid: whichever of nose / left_eye / right_eye /
left_ear / right_ear clear min_conf.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

# Head points contribute to the centroid; any subset that clears min_conf works,
# so a profile view with one ear occluded still measures.
HEAD_POINT_NAMES: Tuple[str, ...] = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
)
SPINE_POINT_NAMES: Tuple[str, ...] = (
    "left_shoulder", "right_shoulder", "left_hip", "right_hip",
)

DEFAULT_MIN_CONF = 0.3

# PROVISIONAL PLACEHOLDERS - NOT TUNED. These two numbers have never been
# measured against the corpus; they are a starting bracket so the plumbing has
# something to return, and a later slice MUST replace them with a census over
# all 288 approved images (the observed offset_norm distribution, plus the
# operator's own verdict on the tails). Do not read them as calibrated.
#
# Shipping a tuned-looking threshold before that census is precisely the trap
# this project has already been burned by: a separation score near 1.0 on a
# small corpus is a confound, not success. Anything derived from these values
# before the census (a pass rate, a flagged-image count, an ROC) is arithmetic,
# not evidence.
#
# Where the bracket came from, for the record: a head is roughly a third of a
# shoulder width across, so ~0.17 shoulder-widths of lateral head-center travel
# already puts the head column off the torso column, and ~0.33 displaces it by
# about a full head width. FLAG sits just inside the first, FAIL at the second.
HEAD_SPINE_FLAG_NORM = 0.15
HEAD_SPINE_FAIL_NORM = 0.30


@dataclass(frozen=True)
class HeadSpineResult:
    """One head-vs-spine measurement.

    offset_norm is the metric; offset_px / shoulder_width_px / spine_len_px are
    retained so the census slice can retune thresholds without re-running the
    pose model, and so a suspiciously small skeleton can be spotted.
    """

    offset_px: float
    offset_norm: float
    shoulder_width_px: float
    spine_len_px: float
    head_points_used: Tuple[str, ...]
    sign: int


def _point(
    kp: Mapping[str, Sequence[float]], name: str, min_conf: float,
) -> Optional[Tuple[float, float]]:
    entry = kp.get(name)
    if entry is None or len(entry) < 3:
        return None
    if float(entry[2]) < min_conf:
        return None
    return float(entry[0]), float(entry[1])


def head_spine_offset(
    kp: Mapping[str, Sequence[float]], min_conf: float = DEFAULT_MIN_CONF,
) -> Optional[HeadSpineResult]:
    """Signed perpendicular offset of the head center from the spine axis.

    Returns None whenever the inputs cannot support the measurement. None is NOT
    a zero: an unmeasurable image has to route to human review, and collapsing
    the two would hand it a silent PASS, which is the exact failure mode this
    module was built to close.
    """
    spine = {}
    for name in SPINE_POINT_NAMES:
        pt = _point(kp, name, min_conf)
        if pt is None:
            return None
        spine[name] = pt

    lsx, lsy = spine["left_shoulder"]
    rsx, rsy = spine["right_shoulder"]
    lhx, lhy = spine["left_hip"]
    rhx, rhy = spine["right_hip"]

    shoulder_width_px = math.hypot(rsx - lsx, rsy - lsy)
    if shoulder_width_px <= 0.0:
        return None

    shoulder_mid = ((lsx + rsx) / 2.0, (lsy + rsy) / 2.0)
    hip_mid = ((lhx + rhx) / 2.0, (lhy + rhy) / 2.0)

    axis_x = shoulder_mid[0] - hip_mid[0]
    axis_y = shoulder_mid[1] - hip_mid[1]
    spine_len_px = math.hypot(axis_x, axis_y)
    if spine_len_px <= 0.0:
        return None

    head_used = []
    sum_x = 0.0
    sum_y = 0.0
    for name in HEAD_POINT_NAMES:
        pt = _point(kp, name, min_conf)
        if pt is None:
            continue
        head_used.append(name)
        sum_x += pt[0]
        sum_y += pt[1]
    if not head_used:
        return None
    head_center = (sum_x / len(head_used), sum_y / len(head_used))

    # 2D cross product of the spine direction with hip->head, divided by the
    # spine length: the signed distance from the infinite spine LINE. Measuring
    # against the line (not the image vertical) is what makes an artistically
    # leaning figure score the same as an upright one; the sign only says which
    # side of the spine the head sits on, so callers key verdicts on abs().
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


def classify_head_spine(
    offset_norm: float,
    flag: float = HEAD_SPINE_FLAG_NORM,
    fail: float = HEAD_SPINE_FAIL_NORM,
) -> str:
    """Bucket a normalized offset into PASS / FLAG / FAIL on its magnitude.

    Keyed on abs(offset_norm) because a head leaning off the spine is equally
    wrong in either direction.
    """
    if not flag <= fail:
        raise ValueError("flag threshold must not exceed fail threshold")
    magnitude = abs(offset_norm)
    if magnitude >= fail:
        return "FAIL"
    if magnitude >= flag:
        return "FLAG"
    return "PASS"
