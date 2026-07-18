"""CI-safe tests for tools/lw_gen_weaponfix.py (torch-free, no real detector).

Proves the PURE mask-derivation logic of the M1 weapon pass FIRST slice:
name-keyed keypoint maps -> weapon ROI (union of two wrist discs + a hand
bbox) with a hard face-exclusion subtraction and a full fallback ladder
(no_body / missing_wrist / missing_elbow / short_forearm / area_cap /
face_intersect). NO heuristic box is ever emitted on a fallback. Also proves
the binary/feathered masks are distinct with binary support a subset of the
feathered nonzero support, and the old-weapon coverage fraction helper.

kp maps are built directly as name-keyed dicts - no detector, no torch. The
module MUST import under base python with only numpy + PIL (torch / cv2 /
controlnet_aux / scipy stay unimported).
"""
import math
import os
import sys
from collections import namedtuple

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_gen_weaponfix as lgw  # noqa: E402

from _import_probe import assert_import_free  # noqa: E402

IMG_WH = (1344, 768)

# ---------------------------------------------------------------------------
# Fake OpenPose detection shapes (mirror tests/test_lw_gen_pose.py): a body is
# an index-aligned [Keypoint or None] list + total_score; a Keypoint carries
# x/y/score; a pose bundles the body + the three limb lists. Built directly so
# the slice-2 adapter tests stay torch-free and never touch a real detector.
# ---------------------------------------------------------------------------
FakeKeypoint = namedtuple("FakeKeypoint", ["x", "y", "score"])
FakeBody = namedtuple("FakeBody", ["keypoints", "total_score"])
FakePose = namedtuple("FakePose", ["body", "left_hand", "right_hand", "face"])


def make_body18(coords, total_score=5.0):
    """Build an 18-slot OpenPose body; coords maps index -> (x, y), rest None.

    The None slots are the whole point: a real detector leaves a missing joint
    as None IN PLACE (index-aligned), never dropped. This is the fixture the
    anti-compaction lock relies on.
    """
    kps = [None] * 18
    for idx, (x, y) in coords.items():
        kps[idx] = FakeKeypoint(x, y, 0.9)
    return FakeBody(keypoints=kps, total_score=total_score)


def hot(mask, x, y):
    """True if the binary mask is set at pixel (x, y) (mask is indexed [y, x])."""
    return bool(mask[int(round(y)), int(round(x))])


# ---------------------------------------------------------------------------
# 1. Import safety (numpy + PIL only; no heavy libs).
# ---------------------------------------------------------------------------
def test_import_is_torch_free():
    assert_import_free("tools.lw_gen_weaponfix",
                       ("torch", "cv2", "controlnet_aux", "scipy"))
    assert callable(lgw.weapon_roi_from_keypoints)
    assert callable(lgw.old_weapon_coverage)
    # Slice-2 raw-pose adapter is importable + torch-free too.
    assert callable(lgw.body_to_kp_map)
    assert callable(lgw.pose_to_weapon_inputs)


# ---------------------------------------------------------------------------
# 2. Right-wrist ROI covers the wrist AND extends past the fist; cold far off.
# ---------------------------------------------------------------------------
def test_right_wrist_roi_covers_wrist_and_extends_past_fist():
    kp = {"RElbow": (0.5, 0.5), "RWrist": (0.6, 0.5)}
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res.ok is True
    assert res.fallback is None
    assert res.mask_binary is not None
    # W in px, and the fist-extension point W + 1.1*vhat*L.
    wx, wy = 0.6 * 1344, 0.5 * 768  # (806.4, 384)
    ex = 0.5 * 1344
    L = wx - ex  # 134.4
    fist_x = wx + 1.1 * L  # 954.24
    assert hot(res.mask_binary, wx, wy)          # wrist covered
    assert hot(res.mask_binary, fist_x, wy)      # extends past the fist
    assert not hot(res.mask_binary, 50, 700)     # cold far from the forearm


# ---------------------------------------------------------------------------
# 3. wrist="left" keys off LWrist/LElbow, not the right side.
# ---------------------------------------------------------------------------
def test_left_wrist_selected_when_config_left():
    kp = {"LElbow": (0.5, 0.5), "LWrist": (0.6, 0.5), "RElbow": None, "RWrist": None}
    res = lgw.weapon_roi_from_keypoints(kp, wrist="left", img_wh=IMG_WH)
    assert res.ok is True
    assert hot(res.mask_binary, 0.6 * 1344, 0.5 * 768)  # left wrist covered
    # Same map read as the right side has no right keypoints -> missing_wrist.
    res_r = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res_r.ok is False
    assert res_r.fallback == "no_body"


# ---------------------------------------------------------------------------
# 4. Hand negative-sentinel is filtered BEFORE the bbox (no origin drag).
# ---------------------------------------------------------------------------
def test_hand_bbox_filters_negative_sentinel():
    kp = {"RElbow": (0.5, 0.5), "RWrist": (0.6, 0.5)}
    hand = [(-0.0007, 0.5), (0.4, 0.6)]  # first point is the -1/W sentinel
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH, hand=hand)
    assert res.ok is True
    # If the sentinel leaked, the bbox min corner would be dragged to x~0.
    assert res.bbox[0] > 100
    assert not hot(res.mask_binary, 0, 0)             # origin stays cold
    assert hot(res.mask_binary, 0.4 * 1344, 0.6 * 768)  # valid hand point covered


# ---------------------------------------------------------------------------
# 5. Face disc is subtracted from the ROI (small overlap -> proceed).
# ---------------------------------------------------------------------------
def test_face_disc_subtracted_from_roi():
    kp = {
        "RElbow": (0.62, 0.5), "RWrist": (0.72, 0.5),
        "nose": (0.58, 0.45), "neck": (0.58, 0.55),
    }
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res.ok is True
    assert res.fallback is None
    # (835, 384) sits inside BOTH the dilated wrist disc and the face disc ->
    # must be carved out by the subtraction.
    assert not hot(res.mask_binary, 835, 384)
    # (900, 384) is in the ROI but outside the face disc -> stays hot.
    assert hot(res.mask_binary, 900, 384)


# ---------------------------------------------------------------------------
# 6. Substantial face overlap routes to review (face_intersect, no mask).
# ---------------------------------------------------------------------------
def test_roi_intersecting_face_routes_to_review():
    kp = {
        "RElbow": (0.5, 0.6), "RWrist": (0.5, 0.48),
        "nose": (0.5, 0.4), "neck": (0.5, 0.55),
    }
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res.ok is False
    assert res.fallback == "face_intersect"
    assert res.mask_binary is None
    assert res.mask_feathered is None


# ---------------------------------------------------------------------------
# 7. A huge union (garbage keypoints) trips the 35% area cap.
# ---------------------------------------------------------------------------
def test_area_cap_over_35pct_triggers_fallback():
    kp = {"RElbow": (0.1, 0.5), "RWrist": (0.9, 0.5)}  # L ~ 1075px
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res.ok is False
    assert res.fallback == "area_cap"
    assert res.mask_binary is None


# ---------------------------------------------------------------------------
# 8. Sub-20px forearm trips the short_forearm fallback.
# ---------------------------------------------------------------------------
def test_short_forearm_triggers_fallback():
    kp = {"RElbow": (0.5, 0.5), "RWrist": (0.51, 0.5)}  # L ~ 13.4px
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res.ok is False
    assert res.fallback == "short_forearm"
    assert res.mask_binary is None


# ---------------------------------------------------------------------------
# 9. Missing wrist -> missing_wrist, NO heuristic box emitted.
# ---------------------------------------------------------------------------
def test_missing_rwrist_triggers_fallback():
    kp = {"RElbow": (0.5, 0.5), "RWrist": None}
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res.ok is False
    assert res.fallback == "missing_wrist"
    assert res.mask_binary is None
    assert res.mask_feathered is None


# ---------------------------------------------------------------------------
# 10. Missing elbow -> missing_elbow.
# ---------------------------------------------------------------------------
def test_missing_relbow_triggers_fallback():
    kp = {"RElbow": None, "RWrist": (0.6, 0.5)}
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res.ok is False
    assert res.fallback == "missing_elbow"
    assert res.mask_binary is None


# ---------------------------------------------------------------------------
# 11. Empty / all-None kp map -> no_body.
# ---------------------------------------------------------------------------
def test_zero_body_triggers_fallback():
    assert lgw.weapon_roi_from_keypoints({}, wrist="right", img_wh=IMG_WH).fallback == "no_body"
    kp = {"RElbow": None, "RWrist": None}
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res.ok is False
    assert res.fallback == "no_body"
    assert res.mask_binary is None


# ---------------------------------------------------------------------------
# 12. Binary and feathered are distinct; binary support subset of feathered.
# ---------------------------------------------------------------------------
def test_dilation_and_feather_are_separate_masks():
    kp = {"RElbow": (0.5, 0.5), "RWrist": (0.6, 0.5)}
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res.ok is True
    b = res.mask_binary
    f = res.mask_feathered
    assert b.dtype == bool
    assert f.dtype.kind == "f"
    # The feather halo makes them differ: more nonzero pixels than the hard mask.
    assert int((f > 0).sum()) > int(b.sum())
    # Every hard-mask pixel has positive feather weight (subset invariant).
    assert bool((f[b] > 0).all())
    # Feather is a normalized [0, 1] float field.
    assert float(f.max()) <= 1.0 + 1e-6
    assert float(f.min()) >= 0.0


# ---------------------------------------------------------------------------
# 13. old_weapon_coverage: outside prop box low, inside prop box high.
# ---------------------------------------------------------------------------
def test_old_weapon_coverage_below_threshold_flags():
    kp = {"RElbow": (0.5, 0.5), "RWrist": (0.6, 0.5)}
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    b = res.mask_binary
    outside = lgw.old_weapon_coverage(b, (5, 5, 55, 55))       # top-left, off the ROI
    inside = lgw.old_weapon_coverage(b, (790, 375, 815, 393))  # tucked inside disc a
    assert outside < 0.95
    assert inside >= 0.95
    assert 0.0 <= outside <= 1.0 and 0.0 <= inside <= 1.0
    assert not math.isnan(outside)


# ===========================================================================
# SLICE 2 - raw index-aligned OpenPose body -> name-keyed kp_map adapter.
# The adapter reads the RAW body keypoints (index-aligned, None preserved) and
# maps the OpenPose-18 indices to names, the reverse of the M0 compaction path
# (poseresult_to_keypoints), so a persisted-index shift can never mislabel a
# joint. Confirmed indices (controlnet_aux open_pose/body.py format_body_result
# person[:18] + util.py draw_bodypose limbSeq): 0=nose 1=neck 3=RElbow 4=RWrist
# 6=LElbow 7=LWrist. Keypoint.x/.y are already normalized [0,1] -> passed raw.
# ===========================================================================


# ---------------------------------------------------------------------------
# 14. OpenPose-18 indices map to the right joint names at the right coords.
# ---------------------------------------------------------------------------
def test_maps_openpose_indices_to_names():
    coords = {
        0: (0.50, 0.10),  # nose
        1: (0.50, 0.20),  # neck
        3: (0.55, 0.45),  # RElbow
        4: (0.60, 0.50),  # RWrist
        6: (0.45, 0.45),  # LElbow
        7: (0.40, 0.50),  # LWrist
    }
    pose = FakePose(body=make_body18(coords), left_hand=None, right_hand=None, face=None)
    kp = lgw.body_to_kp_map([pose])
    assert kp["nose"] == (0.50, 0.10)
    assert kp["neck"] == (0.50, 0.20)
    assert kp["RElbow"] == (0.55, 0.45)
    assert kp["RWrist"] == (0.60, 0.50)
    assert kp["LElbow"] == (0.45, 0.45)
    assert kp["LWrist"] == (0.40, 0.50)


# ---------------------------------------------------------------------------
# 15. THE anti-compaction lock: a None at the RWrist slot survives as None,
#     and joints AFTER it keep their slots (a compacting map would shift them).
# ---------------------------------------------------------------------------
def test_none_index_preserved_not_compacted():
    coords = {
        1: (0.50, 0.20),  # neck at idx 1
        3: (0.55, 0.45),  # RElbow at idx 3
        # idx 4 (RWrist) intentionally absent -> None IN PLACE
        6: (0.45, 0.45),  # LElbow at idx 6
        7: (0.40, 0.50),  # LWrist at idx 7
    }
    pose = FakePose(body=make_body18(coords), left_hand=None, right_hand=None, face=None)
    kp = lgw.body_to_kp_map([pose])
    # poseresult_to_keypoints would DROP the None and pull LElbow/LWrist down
    # into slots 4/5, mislabeling them. This adapter must NOT: the sentinel
    # stays, and the later joints keep their true names.
    assert kp["RWrist"] is None
    assert kp["RElbow"] == (0.55, 0.45)
    assert kp["LElbow"] == (0.45, 0.45)
    assert kp["LWrist"] == (0.40, 0.50)


# ---------------------------------------------------------------------------
# 16. Multi-body: the max total_score body's joints win (mirror M0 pick).
# ---------------------------------------------------------------------------
def test_picks_max_total_score_body():
    p_low = FakePose(
        body=make_body18({4: (0.10, 0.10)}, total_score=3.0),
        left_hand=None, right_hand=None, face=None,
    )
    p_high = FakePose(
        body=make_body18({4: (0.90, 0.90)}, total_score=8.0),
        left_hand=None, right_hand=None, face=None,
    )
    kp = lgw.body_to_kp_map([p_low, p_high])
    assert kp["RWrist"] == (0.90, 0.90)  # the 8.0 body, not the 3.0 body


# ---------------------------------------------------------------------------
# 17. No body (empty list or body=None) -> all six joints None (fallback bait).
# ---------------------------------------------------------------------------
def test_no_body_returns_all_none_map():
    names = ("nose", "neck", "RElbow", "RWrist", "LElbow", "LWrist")
    empty = lgw.body_to_kp_map([])
    assert all(empty[n] is None for n in names)
    pose = FakePose(body=None, left_hand=None, right_hand=None, face=None)
    kp = lgw.body_to_kp_map([pose])
    assert all(kp[n] is None for n in names)
    # Fed to slice 1, an all-None map yields the no_body fallback (no mask).
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH)
    assert res.ok is False
    assert res.fallback == "no_body"
    assert res.mask_binary is None


# ---------------------------------------------------------------------------
# 18. wrist="right" selects the right_hand list (raw, sentinels intact).
# ---------------------------------------------------------------------------
def test_right_hand_selected_for_right_wrist():
    rh = [FakeKeypoint(0.70, 0.50, 0.9), FakeKeypoint(0.72, 0.52, 0.8)]
    lh = [FakeKeypoint(0.30, 0.50, 0.9)]
    body = make_body18({3: (0.60, 0.50), 4: (0.68, 0.50)})
    pose = FakePose(body=body, left_hand=lh, right_hand=rh, face=None)
    kp, hand = lgw.pose_to_weapon_inputs([pose], wrist="right")
    assert hand == [(0.70, 0.50), (0.72, 0.52)]  # right hand chosen
    assert kp["RWrist"] == (0.68, 0.50)


# ---------------------------------------------------------------------------
# 19. wrist="left" selects the left_hand list.
# ---------------------------------------------------------------------------
def test_left_hand_for_left():
    rh = [FakeKeypoint(0.70, 0.50, 0.9)]
    lh = [FakeKeypoint(0.30, 0.50, 0.9), FakeKeypoint(0.28, 0.52, 0.8)]
    body = make_body18({6: (0.40, 0.50), 7: (0.32, 0.50)})
    pose = FakePose(body=body, left_hand=lh, right_hand=rh, face=None)
    kp, hand = lgw.pose_to_weapon_inputs([pose], wrist="left")
    assert hand == [(0.30, 0.50), (0.28, 0.52)]  # left hand chosen
    assert kp["LWrist"] == (0.32, 0.50)


# ---------------------------------------------------------------------------
# 20. End-to-end: adapter -> weapon_roi_from_keypoints. Good pose -> ok=True;
#     a body missing the RWrist slot -> missing_wrist fallback (no mask).
# ---------------------------------------------------------------------------
def test_end_to_end_adapter_into_weapon_roi():
    good = make_body18({
        0: (0.10, 0.10), 1: (0.10, 0.15),  # nose/neck far off -> harmless face disc
        3: (0.50, 0.60), 4: (0.60, 0.60),  # horizontal forearm ~134px wide
    })
    rh = [FakeKeypoint(0.62, 0.60, 0.9)]
    pose = FakePose(body=good, left_hand=None, right_hand=rh, face=None)
    kp, hand = lgw.pose_to_weapon_inputs([pose], wrist="right", img_wh=IMG_WH)
    res = lgw.weapon_roi_from_keypoints(kp, wrist="right", img_wh=IMG_WH, hand=hand)
    assert res.ok is True
    assert res.fallback is None
    assert res.mask_binary is not None

    miss = make_body18({0: (0.10, 0.10), 1: (0.10, 0.15), 3: (0.50, 0.60)})  # no idx 4
    pose2 = FakePose(body=miss, left_hand=None, right_hand=None, face=None)
    kp2, hand2 = lgw.pose_to_weapon_inputs([pose2], wrist="right", img_wh=IMG_WH)
    res2 = lgw.weapon_roi_from_keypoints(kp2, wrist="right", img_wh=IMG_WH, hand=hand2)
    assert res2.ok is False
    assert res2.fallback == "missing_wrist"
    assert res2.mask_binary is None


# ---------------------------------------------------------------------------
# 21. pad_bbox: expand a ROI bbox by a fraction of its own size, clamp to frame.
#     Crops the weapon ROI (padded 10%) for the CLIP gate (design_weapon.md
#     sec 6) so the crossbow has margin without swallowing the whole figure.
# ---------------------------------------------------------------------------
def test_pad_bbox_expands_by_fraction():
    # bbox 100x200; 10% pad -> +/-10 in x, +/-20 in y.
    assert lgw.pad_bbox((100, 100, 200, 300), 0.10, IMG_WH) == (90, 80, 210, 320)


def test_pad_bbox_clamps_to_frame():
    # A large pad runs past every edge -> clamp to [0, W] x [0, H].
    assert lgw.pad_bbox((5, 5, 25, 25), 0.5, (30, 30)) == (0, 0, 30, 30)


def test_pad_bbox_zero_pad_is_clamped_identity():
    assert lgw.pad_bbox((10, 10, 20, 20), 0.0, IMG_WH) == (10, 10, 20, 20)


def test_pad_bbox_returns_ints():
    out = lgw.pad_bbox((100, 100, 201, 301), 0.10, IMG_WH)
    assert all(isinstance(v, int) for v in out)


# ===========================================================================
# SLICE W2 - forearm_frame: the pixel-space (W, v_hat, L) the W2 transplant
# needs, factored out of weapon_roi_from_keypoints. weapon_roi now CALLS it for
# that math, so both must agree exactly (non-regression) and forearm_frame must
# return None on the SAME missing-wrist / missing-elbow / short-forearm cases.
# ===========================================================================


def test_forearm_frame_clean_kp_exact_values():
    # RElbow (0.5,0.5) -> RWrist (0.6,0.5) on 1344x768: W=(806.4,384),
    # v=(134.4,0), L=134.4, v_hat=(1,0).
    fr = lgw.forearm_frame({"RElbow": (0.5, 0.5), "RWrist": (0.6, 0.5)}, "right", IMG_WH)
    assert fr is not None
    wx, wy, vhx, vhy, length = fr
    assert abs(wx - 806.4) < 1e-6
    assert abs(wy - 384.0) < 1e-6
    assert abs(vhx - 1.0) < 1e-9
    assert abs(vhy - 0.0) < 1e-9
    assert abs(length - 134.4) < 1e-6


def test_forearm_frame_left_side_reads_left_joints():
    fr = lgw.forearm_frame({"LElbow": (0.4, 0.5), "LWrist": (0.5, 0.5)}, "left", IMG_WH)
    assert fr is not None
    wx, wy, vhx, vhy, length = fr
    assert abs(wx - 0.5 * 1344) < 1e-6
    assert abs(vhx - 1.0) < 1e-9


def test_forearm_frame_missing_wrist_is_none():
    assert lgw.forearm_frame({"RElbow": (0.5, 0.5), "RWrist": None}, "right", IMG_WH) is None


def test_forearm_frame_missing_elbow_is_none():
    assert lgw.forearm_frame({"RElbow": None, "RWrist": (0.6, 0.5)}, "right", IMG_WH) is None


def test_forearm_frame_short_forearm_is_none():
    # L ~ 13.4px < MIN_FOREARM_PX -> None (mirrors weapon_roi short_forearm).
    assert lgw.forearm_frame({"RElbow": (0.5, 0.5), "RWrist": (0.51, 0.5)}, "right", IMG_WH) is None


def test_weapon_roi_mask_unchanged_after_forearm_frame_refactor():
    """weapon_roi (now delegating the frame math to forearm_frame) must still emit
    the exact documented dilated-disc union - byte-identical, no regression."""
    kp = {"RElbow": (0.5, 0.5), "RWrist": (0.6, 0.5)}
    res = lgw.weapon_roi_from_keypoints(kp, "right", IMG_WH)
    assert res.ok is True

    # Independently rebuild the expected binary from the section-4 geometry.
    w, h = IMG_WH
    wx, wy = 0.6 * w, 0.5 * h
    length = wx - 0.5 * w
    bx = wx + lgw.FIST_OFFSET * length  # v_hat=(1,0) so the fist offset is +x only
    by = wy
    yy, xx = np.ogrid[0:h, 0:w]
    exp = (xx - wx) ** 2 + (yy - wy) ** 2 <= (lgw.WRIST_DISC_R * length + lgw.DILATE_PX) ** 2
    exp = exp | ((xx - bx) ** 2 + (yy - by) ** 2 <= (lgw.FIST_DISC_R * length + lgw.DILATE_PX) ** 2)
    assert np.array_equal(res.mask_binary, np.asarray(exp, dtype=bool))
