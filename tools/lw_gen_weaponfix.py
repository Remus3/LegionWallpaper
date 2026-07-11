"""Pure mask-derivation logic for the M1 weapon pass (FIRST slice).

Torch-free by construction: numpy + PIL only, no I/O. This module owns the
geometry that turns name-keyed OpenPose keypoints into a weapon-repair ROI
(two wrist discs + an optional hand bbox), a hard face-exclusion subtraction,
and the full fallback ladder. The diffusion inpaint engine, the W1-W4 rungs,
the CLIP weapon gate, config wiring, and lw_gen_run/qa/promote integration are
LATER slices and deliberately live elsewhere.

Geometry is the shipped design of record (docs/research/golden_designs/
design_weapon.md, section 4 "Mask geometry spec"):
- normalized (x, y) in [0, 1] -> px via (x*img_wh[0], y*img_wh[1]).
- forearm vector v = W - E, L = |v| px; v_hat = v / L.
- ROI = union of disc(W, 0.9*L) + disc(W + 1.1*v_hat*L, 1.2*L) + bbox(hand kps
  dilated 0.5*L). Binary = the primitives expanded +24px; feathered = a 16px
  Gaussian on the binary, in [0, 1]. Binary support is a subset of the
  feathered nonzero support.
- Face exclusion: subtract disc(nose, 1.1*dist(nose, neck)); a substantial
  pre-subtraction overlap routes to review instead of inpainting near a face.

Every fallback returns ok=False with NO mask - a missing/garbage keypoint set
never emits a heuristic box.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

# --- geometry constants (design_weapon.md section 4) ------------------------
WRIST_DISC_R = 0.9      # disc a radius, in forearm-lengths, centered on W
FIST_DISC_R = 1.2       # disc b radius, in forearm-lengths
FIST_OFFSET = 1.1       # disc b center offset along v_hat, in forearm-lengths
HAND_DILATE = 0.5       # hand bbox dilation, in forearm-lengths
DILATE_PX = 24          # binary primitive expansion (px)
FEATHER_PX = 16         # Gaussian feather radius for the inpaint mask (px)
MIN_FOREARM_PX = 20.0   # forearms shorter than this -> short_forearm fallback
AREA_CAP_FRAC = 0.35    # final mask above this fraction of frame -> area_cap
FACE_R_MULT = 1.1       # face disc radius = FACE_R_MULT * dist(nose, neck)
FACE_INTERSECT_FRAC = 0.25  # raw-ROI/face overlap at/above this -> face_intersect


@dataclass
class RoiResult:
    """Outcome of weapon_roi_from_keypoints.

    ok=True  -> mask_binary (bool HxW), mask_feathered (float [0,1] HxW), bbox.
    ok=False -> fallback names the reason and NO mask is emitted.
    """

    ok: bool
    fallback: Optional[str] = None
    mask_binary: Optional[np.ndarray] = None
    mask_feathered: Optional[np.ndarray] = None
    bbox: Optional[Tuple[int, int, int, int]] = None


def _to_px(pt, img_wh):
    return (pt[0] * img_wh[0], pt[1] * img_wh[1])


def _disc(xx, yy, cx, cy, r):
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r


def _valid_hand_px(hand, img_wh):
    """Filter the negative missing-peak sentinel BEFORE the bbox, then to px.

    A missing hand peak arrives as a negative coord (~ -0.0007); taking a bbox
    over it would drag the min corner to the origin, so drop any point with
    x < 0 or y < 0 first.
    """
    out = []
    for pt in hand or []:
        if pt is None:
            continue
        x, y = pt[0], pt[1]
        if x < 0 or y < 0:
            continue
        out.append(_to_px((x, y), img_wh))
    return out


def weapon_roi_from_keypoints(
    kp_map: dict,
    wrist: str = "right",
    img_wh: Tuple[int, int] = (1344, 768),
    hand: Optional[List] = None,
) -> RoiResult:
    """Derive the weapon-repair ROI from a NAME-KEYED keypoint map.

    kp_map keys ("RElbow"/"RWrist"/"LElbow"/"LWrist"/"nose"/"neck") each hold a
    normalized (x, y) in [0, 1] or None. `hand` is an optional list of
    normalized hand keypoints (may carry the -1/W negative sentinel). Returns a
    RoiResult: ok=True with a dilated binary mask + a feathered [0,1] mask +
    bbox, or ok=False with a fallback reason and no mask. See the fallback
    ladder in the module docstring; a fallback NEVER emits a heuristic box.
    """
    w_px = img_wh[0]
    h_px = img_wh[1]

    if wrist == "left":
        w_key, e_key = "LWrist", "LElbow"
    else:
        w_key, e_key = "RWrist", "RElbow"

    w_norm = kp_map.get(w_key)
    e_norm = kp_map.get(e_key)

    # Fallback ladder (order matters): both-missing first, then each joint.
    if w_norm is None and e_norm is None:
        return RoiResult(ok=False, fallback="no_body")
    if w_norm is None:
        return RoiResult(ok=False, fallback="missing_wrist")
    if e_norm is None:
        return RoiResult(ok=False, fallback="missing_elbow")

    wx, wy = _to_px(w_norm, img_wh)
    ex, ey = _to_px(e_norm, img_wh)
    vx, vy = wx - ex, wy - ey
    L = math.hypot(vx, vy)
    if L < MIN_FOREARM_PX:
        return RoiResult(ok=False, fallback="short_forearm")

    vhx, vhy = vx / L, vy / L
    bx = wx + FIST_OFFSET * vhx * L
    by = wy + FIST_OFFSET * vhy * L

    yy, xx = np.ogrid[0:h_px, 0:w_px]

    # Raw ROI (pre-dilation core) drives the area-cap gate + the face check.
    roi_core = _disc(xx, yy, wx, wy, WRIST_DISC_R * L)
    roi_core = roi_core | _disc(xx, yy, bx, by, FIST_DISC_R * L)

    hand_pts = _valid_hand_px(hand, img_wh)
    hbox = None  # (x0, y0, x1, y1) in px, pre +24 expansion
    if hand_pts:
        hxs = [p[0] for p in hand_pts]
        hys = [p[1] for p in hand_pts]
        d = HAND_DILATE * L
        hbox = (min(hxs) - d, min(hys) - d, max(hxs) + d, max(hys) + d)
        hb = (
            (xx >= hbox[0]) & (xx <= hbox[2]) & (yy >= hbox[1]) & (yy <= hbox[3])
        )
        roi_core = roi_core | hb

    # Face disc (nose + neck present) -> subtract; a substantial pre-subtraction
    # overlap means never inpaint a face-adjacent region.
    face = None
    nose = kp_map.get("nose")
    neck = kp_map.get("neck")
    if nose is not None and neck is not None:
        nx, ny = _to_px(nose, img_wh)
        kx, ky = _to_px(neck, img_wh)
        r_face = FACE_R_MULT * math.hypot(nx - kx, ny - ky)
        if r_face > 0:
            face = _disc(xx, yy, nx, ny, r_face)
            face_area = float(face.sum())
            if face_area > 0:
                overlap = float((roi_core & face).sum()) / face_area
                if overlap >= FACE_INTERSECT_FRAC:
                    return RoiResult(ok=False, fallback="face_intersect")

    # Binary mask = primitives expanded +24px, then face carved out.
    binary = _disc(xx, yy, wx, wy, WRIST_DISC_R * L + DILATE_PX)
    binary = binary | _disc(xx, yy, bx, by, FIST_DISC_R * L + DILATE_PX)
    if hbox is not None:
        hb2 = (
            (xx >= hbox[0] - DILATE_PX)
            & (xx <= hbox[2] + DILATE_PX)
            & (yy >= hbox[1] - DILATE_PX)
            & (yy <= hbox[3] + DILATE_PX)
        )
        binary = binary | hb2
    binary = np.asarray(binary, dtype=bool)
    if face is not None:
        binary = binary & ~face

    if int(binary.sum()) > AREA_CAP_FRAC * w_px * h_px:
        return RoiResult(ok=False, fallback="area_cap")

    feathered = _feather(binary, FEATHER_PX)
    if face is not None:
        feathered = feathered * (~face)

    ys, xs = np.where(binary)
    if xs.size == 0:
        # ROI fully consumed by the face carve -> treat as face-adjacent.
        return RoiResult(ok=False, fallback="face_intersect")
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

    return RoiResult(
        ok=True,
        fallback=None,
        mask_binary=binary,
        mask_feathered=feathered,
        bbox=bbox,
    )


def _feather(binary, radius):
    """16px Gaussian feather of a bool mask -> float32 field in [0, 1].

    Uses PIL (deferred import) so the module stays torch/scipy-free. Blurring a
    0/255 'L' image only grows support, so every True binary pixel keeps a
    positive weight - the binary support is a subset of the feathered nonzero
    support by construction.
    """
    from PIL import Image, ImageFilter  # deferred; PIL pulls no torch/scipy

    src = Image.fromarray((binary.astype(np.uint8) * 255), mode="L")
    blurred = src.filter(ImageFilter.GaussianBlur(radius=radius))
    return (np.asarray(blurred, dtype=np.float32) / 255.0)


def old_weapon_coverage(mask_binary, prop_box) -> float:
    """Fraction of prop_box's area covered by mask_binary, in [0, 1].

    prop_box = (x0, y0, x1, y1) px of the wrong/old weapon prop. Returns
    intersection / prop_box_area; a later rung requires >= ~0.95 before a W2
    transplant (the new rig must actually blanket the old one).
    """
    x0, y0, x1, y1 = prop_box
    bx0, bx1 = (x0, x1) if x0 <= x1 else (x1, x0)
    by0, by1 = (y0, y1) if y0 <= y1 else (y1, y0)
    area = (bx1 - bx0) * (by1 - by0)
    if area <= 0:
        return 0.0
    h_px, w_px = mask_binary.shape
    ix0 = max(0, int(math.floor(bx0)))
    iy0 = max(0, int(math.floor(by0)))
    ix1 = min(w_px, int(math.ceil(bx1)))
    iy1 = min(h_px, int(math.ceil(by1)))
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = int(np.asarray(mask_binary[iy0:iy1, ix0:ix1], dtype=bool).sum())
    cov = inter / float(area)
    return float(min(1.0, max(0.0, cov)))
