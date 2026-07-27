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


def glb_skin_id(champion_id: int, skin_index: int) -> int:
    """Riot's skinId encoding: the champion owns a 1000-wide block of ids.

    Base skin is index 0, so Vayne (championId 67) is 67000 and her 5th skin is
    67005. The CDN keys every model directory by this id, which is why the asset
    layer needs the arithmetic rather than a hand-maintained id table. Ground
    truth: docs/LEDGER.md item 37 (verified live against 5 Vayne skins - distinct
    Content-Lengths, bogus ids 404) and ROADMAP.md glb-render-pipeline.
    """
    return int(champion_id) * 1000 + int(skin_index)


def glb_model_url(champion: str, champion_id: int, skin_index: int) -> str:
    """Build the CDN URL of one skin's textured .glb (named joints included).

    This is the capability that unblocks the whole render path: the CDN serves a
    .glb whose joint hierarchy is FULLY NAMED, superseding the blocker recorded in
    docs/research/crossbow_render_poc.md ("the .skl skeleton is NOT exported by
    CDragon (404) -> bone NAMES are unavailable"), which had forced base-skin-only
    isolation plus manual curation. The POC's separate "modelviewer.lol is not
    scrapeable" note was true of the WEBSITE (Cloudflare + in-app blobs) and does
    NOT apply to this CDN - do not re-litigate either half.

    The champion slug is lowercased because the CDN path is case-sensitive while
    callers carry display-cased names ("Vayne"). Pure string work: no request is
    made here, and the module stays import-time network-free by construction.
    Ground truth: docs/LEDGER.md item 37, ROADMAP.md glb-render-pipeline.
    """
    slug = str(champion).lower()
    skin_id = glb_skin_id(champion_id, skin_index)
    return f"https://cdn.modelviewer.lol/lol/models/{slug}/{skin_id}/model.glb"


def is_weapon_joint(name: str) -> bool:
    """Decide whether a joint name belongs to the HELD weapon geometry.

    Name matching is mandatory, not a convenience: two rig conventions coexist in
    the corpus (lowercase `r_weapon` on older skins, CamelCase `R_Weapon` on
    newer), so the same logical joint sits at different indices per skin and no
    fixed bone-INDEX set can ever port across skins. Everything here is therefore
    case-insensitive.

    The exclusions are each a measured failure mode from docs/LEDGER.md item 37:
    `buffbone` joints are VFX attachment points that drag unrelated geometry in;
    a name STARTING with `b_weapon` is the back-mounted bolt rather than the held
    crossbow; `wings` and `ult` joints belong to skin-specific and ultimate-state
    props. With this rule name-based isolation renders a clean crossbow on 4/5
    Vayne skins including aristocrat, the POC's documented wine-bottle failure
    (project legitimately has no crossbow geometry - its weapon is VFX).
    """
    low = str(name or "").lower()
    if "weapon" not in low:
        return False
    if "buffbone" in low or "wings" in low or "ult" in low:
        return False
    return not low.startswith("b_weapon")


def weapon_joint_indices(gltf: dict) -> list[int]:
    """Node indices of the held-weapon joints in an already-parsed glTF dict.

    Returns indices (not names) because every downstream glTF lookup - skin joint
    lists, inverse bind matrices, JOINTS_0 vertex weights - is index-keyed. The
    indices are derived per file from is_weapon_joint rather than hardcoded,
    since the two rig conventions make any fixed index set unportable
    (docs/LEDGER.md item 37, ROADMAP.md glb-render-pipeline).

    A node without a "name" key is skipped, never a crash: real files carry
    unnamed helper nodes and one of them must not take down a batch render.
    Missing "nodes" returns [] for the same reason.
    """
    nodes = (gltf or {}).get("nodes") or []
    return [i for i, node in enumerate(nodes)
            if is_weapon_joint((node or {}).get("name", ""))]


def weapon_joint_names(gltf: dict) -> list[str]:
    """The surviving weapon-joint names, in node order, for logging and audit.

    Kept separate from weapon_joint_indices because the two audiences differ: the
    renderer consumes indices, while a human confirming WHY a skin isolated the
    way it did needs to see whether this file used `r_weapon` or `R_Weapon` - the
    exact convention split that makes index sets unportable (docs/LEDGER.md item
    37). Same node order as weapon_joint_indices so the two zip together.
    """
    nodes = (gltf or {}).get("nodes") or []
    return [str((nodes[i] or {}).get("name", "")) for i in weapon_joint_indices(gltf)]


def mesh_primitives(gltf: dict, mesh_index: int) -> list[dict]:
    """ALL primitives of one mesh - the fix for a measured silent-truncation trap.

    Newer skins split mesh 0 into 9-10 primitives that share ONE POSITION
    accessor, so reading `primitives[0]` alone drops most of the triangles with no
    error and no visible parse failure - the render just comes out partial. This
    function exists so that trap cannot be re-introduced by a caller reaching into
    the dict itself (docs/LEDGER.md item 37, ROADMAP.md glb-render-pipeline
    do-not-redo list).

    A missing mesh, a missing "meshes" key, or an out-of-range index returns []
    rather than raising: skin coverage across the corpus is uneven and a batch
    render must degrade per-skin, not abort.
    """
    meshes = (gltf or {}).get("meshes") or []
    if not isinstance(mesh_index, int) or mesh_index < 0 or mesh_index >= len(meshes):
        return []
    return list((meshes[mesh_index] or {}).get("primitives") or [])


def mesh_primitive_index_accessors(gltf: dict, mesh_index: int) -> list[int]:
    """Every primitive's triangle-index accessor id, in primitive order.

    The shared-POSITION-accessor split (docs/LEDGER.md item 37) means the geometry
    of a multi-primitive mesh is distinguished ONLY by these per-primitive index
    accessors - the vertex buffer is identical across them. Collecting all of them
    is what makes the isolated weapon mesh whole; taking the first is exactly the
    truncation this port removes.

    A primitive with no "indices" is non-indexed (draw-array) geometry and simply
    contributes no accessor id, which keeps the return list aligned with what the
    caller can actually dereference.
    """
    return [int(p["indices"]) for p in mesh_primitives(gltf, mesh_index)
            if isinstance(p, dict) and "indices" in p]
