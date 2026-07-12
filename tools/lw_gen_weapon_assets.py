"""W2 reference-transplant asset layer for the M1 weapon pass.

Torch-free by construction (numpy is not even needed here): json + os + math +
stdlib at module top; PIL is imported LAZILY inside affine_transplant so the CI
import-safety guard (no torch / diffusers / cv2 / onnxruntime) holds. This module
owns the small, pure, deterministic pieces the W2 rung (mechanism A) needs and
nothing else - the diffusion inpaint, the mask geometry, the rung driver, and the
lw_gen_run/qa wiring live in their own modules.

Design of record: docs/research/golden_designs/design_weapon.md
- sec 3 (W2 = affine-fit a real crossbow crop to the wrist, alpha-paste, then the
  SAME masked inpaint at strength 0.35-0.50).
- sec 4 "Transplant fit (W2)": each crop asset ships metadata {anchor_px, axis,
  forearm_len_px, handedness, view}; pick by handedness + coarse view; affine =
  scale s = L / forearm_len_px, rotate by angle(v_hat) - angle(axis), translate
  anchor -> W; PIL crop.rotate(expand=True, BICUBIC) -> resize by s ->
  alpha-composite at the computed offset.

Assets live gitignored under tools/models/weapon_assets/vayne/ (a meta.json plus
the crop PNGs); load_assets tolerates a missing dir/file by returning [].
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class AssetMeta:
    """One crossbow-crop asset + the metadata that fits it to a wrist.

    file          crop PNG basename (RGBA, alpha matte inside the dir)
    anchor_px     (x, y) wrist-attach point in the crop's pixel coords
    axis          (ux, uy) unit vector of the rig's long axis in crop coords
    forearm_len_px length (px) of the forearm the crop was authored against
    handedness    "right" | "left" (the rig side)
    view          "side" | "front" | "threequarter" | ... (coarse camera view)
    png_path      absolute/dir-joined path to the crop PNG (derived at load)
    """

    file: str
    anchor_px: Tuple[float, float]
    axis: Tuple[float, float]
    forearm_len_px: float
    handedness: str
    view: str
    png_path: str


def load_assets(assets_dir: str) -> List[AssetMeta]:
    """Read <assets_dir>/meta.json into AssetMeta list; [] on any miss.

    meta.json shape: {"assets": [{"file", "anchor_px":[x,y], "axis":[ux,uy],
    "forearm_len_px":N, "handedness":"right", "view":"side"}, ...]}. png_path is
    join(assets_dir, file). A missing directory, a missing meta.json, or invalid
    JSON returns [] (the W2 rung then routes the candidate to review with a
    no_asset fallback - never crashes the batch). A single malformed asset entry
    is skipped, not fatal.
    """
    meta_path = os.path.join(assets_dir, "meta.json")
    try:
        with open(meta_path, encoding="utf-8") as fo:
            data = json.load(fo)
    except (OSError, ValueError):
        return []

    out: List[AssetMeta] = []
    for entry in (data or {}).get("assets", []) or []:
        try:
            out.append(AssetMeta(
                file=entry["file"],
                anchor_px=(float(entry["anchor_px"][0]), float(entry["anchor_px"][1])),
                axis=(float(entry["axis"][0]), float(entry["axis"][1])),
                forearm_len_px=float(entry["forearm_len_px"]),
                handedness=str(entry["handedness"]),
                view=str(entry["view"]),
                png_path=os.path.join(assets_dir, entry["file"]),
            ))
        except (KeyError, TypeError, IndexError, ValueError):
            continue
    return out


def pick_asset(
    assets: List[AssetMeta],
    handedness: str,
    v_hat: Tuple[float, float],
) -> Optional[AssetMeta]:
    """Choose the best-matching asset for a wrist by handedness + coarse view.

    Keep only assets whose handedness matches. Coarse view rule (design_weapon.md
    sec 4 - "coarse view (side/front) from the sign and magnitude of v_hat.x"): a
    strongly horizontal forearm (abs(v_hat[0]) >= 0.5) prefers a "side" crop; an
    upright/foreshortened forearm prefers "front"/"threequarter". Returns the
    first handedness-match whose view is in the preferred set; else a deterministic
    fallback to the first handedness-match; None if nothing matches handedness.
    """
    matches = [a for a in assets if a.handedness == handedness]
    if not matches:
        return None
    if abs(float(v_hat[0])) >= 0.5:
        preferred = ("side",)
    else:
        preferred = ("front", "threequarter")
    for a in matches:
        if a.view in preferred:
            return a
    return matches[0]


def affine_transplant(cand_img, asset: AssetMeta, w_px, v_hat, L):
    """Affine-fit the asset crop onto cand_img so its anchor lands on w_px.

    Pure + deterministic. cand_img is a PIL RGB image; the crop is opened RGBA.
    Steps (design_weapon.md sec 4): scale s = L / asset.forearm_len_px; rotate so
    the asset axis aligns onto v_hat; translate the (rotated, scaled) anchor to
    w_px; alpha-composite onto a COPY of cand_img. Returns a new RGB image.

    Anchor tracking (the load-bearing bit): PIL Image.rotate(angle, expand=True)
    is a VISUAL counter-clockwise rotation. In image (y-down) pixel coords its
    forward point map about the center is
        p_out = R_ccw(theta) @ (p_in - c_in) + c_out,
        R_ccw(theta) = [[cos, sin], [-sin, cos]],
    which DECREASES the atan2 angle by theta. So aligning the asset axis onto
    v_hat needs theta = angle(axis) - angle(v_hat) (the y-down flip of the sec-4
    "angle(v_hat) - angle(axis)"). We apply that exact map to the anchor, then the
    resize scale, then a translate - never trusting a sign we did not derive.
    """
    from PIL import Image

    base = cand_img.convert("RGB").copy()
    crop = Image.open(asset.png_path).convert("RGBA")
    w0, h0 = crop.size
    ax, ay = float(asset.anchor_px[0]), float(asset.anchor_px[1])

    ang_axis = math.atan2(float(asset.axis[1]), float(asset.axis[0]))
    ang_v = math.atan2(float(v_hat[1]), float(v_hat[0]))
    theta = ang_axis - ang_v  # radians; PIL wants degrees, y-down convention above
    rotated = crop.rotate(math.degrees(theta), resample=Image.BICUBIC, expand=True)
    w1, h1 = rotated.size

    cos_t, sin_t = math.cos(theta), math.sin(theta)
    dx, dy = ax - w0 / 2.0, ay - h0 / 2.0
    rx = cos_t * dx + sin_t * dy + w1 / 2.0
    ry = -sin_t * dx + cos_t * dy + h1 / 2.0

    s = float(L) / float(asset.forearm_len_px)
    new_w = max(1, int(round(w1 * s)))
    new_h = max(1, int(round(h1 * s)))
    scaled = rotated.resize((new_w, new_h), resample=Image.BICUBIC)
    sax = rx * (new_w / float(w1))
    say = ry * (new_h / float(h1))

    ox = int(round(float(w_px[0]) - sax))
    oy = int(round(float(w_px[1]) - say))
    base.paste(scaled, (ox, oy), scaled)  # alpha matte = the crop's own alpha
    return base
