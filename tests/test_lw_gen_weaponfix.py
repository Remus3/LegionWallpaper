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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_gen_weaponfix as lgw  # noqa: E402

IMG_WH = (1344, 768)


def hot(mask, x, y):
    """True if the binary mask is set at pixel (x, y) (mask is indexed [y, x])."""
    return bool(mask[int(round(y)), int(round(x))])


# ---------------------------------------------------------------------------
# 1. Import safety (numpy + PIL only; no heavy libs).
# ---------------------------------------------------------------------------
def test_import_is_torch_free():
    assert "torch" not in sys.modules
    assert "cv2" not in sys.modules
    assert "controlnet_aux" not in sys.modules
    assert "scipy" not in sys.modules
    assert callable(lgw.weapon_roi_from_keypoints)
    assert callable(lgw.old_weapon_coverage)


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
