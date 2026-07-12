"""CI-safe tests for tools/lw_gen_weapon_assets.py (torch-free, PIL + stdlib).

Proves the W2 reference-transplant asset layer in isolation: meta.json load,
handedness/view asset selection, and the affine transplant math that fits a real
crossbow crop onto the wrist. No torch / diffusers / cv2 / onnxruntime is ever
imported (the design-of-record CI constraint); PIL is the only heavy dep and it
stays lazy inside affine_transplant. Design of record:
docs/research/golden_designs/design_weapon.md sec 3 (W2) + sec 4 (Transplant fit).
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_gen_weapon_assets as lwa  # noqa: E402

# The magenta marker is the unique anchor color; the blue field is the opaque
# crop body. A flat 15x15 marker block keeps the anchor pixel exact under BICUBIC.
MARKER = (255, 0, 255, 255)
FIELD = (0, 0, 200, 255)


def _write_asset(adir, file="cb.png", size=(120, 60), anchor=(30, 30),
                 axis=(1.0, 0.0), forearm_len_px=40.0, handedness="right",
                 view="side"):
    """Write one synthetic crossbow-crop PNG + its meta.json into adir."""
    from PIL import Image

    os.makedirs(adir, exist_ok=True)
    img = Image.new("RGBA", size, FIELD)
    px = img.load()
    ax, ay = anchor
    for yy in range(ay - 7, ay + 8):
        for xx in range(ax - 7, ax + 8):
            if 0 <= xx < size[0] and 0 <= yy < size[1]:
                px[xx, yy] = MARKER
    img.save(os.path.join(adir, file))
    meta = {"assets": [{
        "file": file, "anchor_px": list(anchor), "axis": list(axis),
        "forearm_len_px": forearm_len_px, "handedness": handedness, "view": view,
    }]}
    with open(os.path.join(adir, "meta.json"), "w", encoding="utf-8") as fo:
        json.dump(meta, fo)


def _asset(handedness="right", view="side", file="a.png"):
    return lwa.AssetMeta(
        file=file, anchor_px=(10, 10), axis=(1.0, 0.0), forearm_len_px=40.0,
        handedness=handedness, view=view, png_path="/tmp/" + file,
    )


def _is_magenta(p):
    return p[0] > 200 and p[1] < 80 and p[2] > 200


# ---------------------------------------------------------------------------
# 0. Import safety: torch-free (PIL lazy).
# ---------------------------------------------------------------------------
def test_import_is_torch_free():
    for banned in ("torch", "diffusers", "cv2", "onnxruntime"):
        assert banned not in sys.modules
    assert callable(lwa.load_assets)
    assert callable(lwa.pick_asset)
    assert callable(lwa.affine_transplant)


# ---------------------------------------------------------------------------
# 1. load_assets: round-trip a written meta.json; png_path joined to the dir.
# ---------------------------------------------------------------------------
def test_load_assets_roundtrip(tmp_path):
    _write_asset(str(tmp_path))
    assets = lwa.load_assets(str(tmp_path))
    assert len(assets) == 1
    a = assets[0]
    assert a.file == "cb.png"
    assert tuple(a.anchor_px) == (30, 30)
    assert tuple(a.axis) == (1.0, 0.0)
    assert a.forearm_len_px == 40.0
    assert a.handedness == "right"
    assert a.view == "side"
    assert a.png_path == os.path.join(str(tmp_path), "cb.png")
    assert os.path.exists(a.png_path)


def test_load_assets_missing_dir_returns_empty(tmp_path):
    assert lwa.load_assets(str(tmp_path / "does_not_exist")) == []


def test_load_assets_dir_without_meta_returns_empty(tmp_path):
    (tmp_path / "empty").mkdir()
    assert lwa.load_assets(str(tmp_path / "empty")) == []


# ---------------------------------------------------------------------------
# 2. pick_asset: handedness filter, coarse view preference, deterministic
#    fallback, None when nothing matches.
# ---------------------------------------------------------------------------
def test_pick_asset_handedness_filters():
    assets = [_asset("left", "side", "l.png"), _asset("right", "front", "r.png")]
    a = lwa.pick_asset(assets, "right", (0.2, 0.9))  # abs(x)<0.5 -> prefer front
    assert a.file == "r.png"


def test_pick_asset_prefers_side_for_horizontal_forearm():
    assets = [_asset("right", "front", "f.png"), _asset("right", "side", "s.png")]
    a = lwa.pick_asset(assets, "right", (0.95, 0.05))  # abs(x)>=0.5 -> prefer side
    assert a.view == "side"


def test_pick_asset_prefers_front_for_vertical_forearm():
    assets = [_asset("right", "side", "s.png"), _asset("right", "threequarter", "t.png")]
    a = lwa.pick_asset(assets, "right", (0.1, 0.99))  # abs(x)<0.5 -> prefer front/tq
    assert a.view == "threequarter"


def test_pick_asset_deterministic_fallback_to_first_match():
    # No view matches the preference -> the FIRST handedness-match wins.
    assets = [_asset("right", "back", "b.png"), _asset("right", "overhead", "o.png")]
    a = lwa.pick_asset(assets, "right", (0.95, 0.05))
    assert a.file == "b.png"


def test_pick_asset_none_when_no_handedness_match():
    assert lwa.pick_asset([], "right", (1.0, 0.0)) is None
    assert lwa.pick_asset([_asset("left")], "right", (1.0, 0.0)) is None


# ---------------------------------------------------------------------------
# 3. affine_transplant: the tracked anchor lands within 3px of w_px (no rotate).
# ---------------------------------------------------------------------------
def test_affine_transplant_anchor_lands_at_wpx(tmp_path):
    from PIL import Image

    _write_asset(str(tmp_path))
    asset = lwa.load_assets(str(tmp_path))[0]
    cand = Image.new("RGB", (400, 300), (0, 0, 0))
    out = lwa.affine_transplant(cand, asset, (200, 150), (1.0, 0.0), 80.0)  # s=2, no rot
    assert out.mode == "RGB"
    assert out.size == (400, 300)
    arr = np.asarray(out)
    win = arr[150 - 3:150 + 4, 200 - 3:200 + 4].reshape(-1, 3)
    assert any(_is_magenta(p) for p in win)


# ---------------------------------------------------------------------------
# 4. affine_transplant: the anchor still lands at w_px through a 90deg rotate
#    (v_hat perpendicular to the asset axis) - the y-down tracking is correct.
# ---------------------------------------------------------------------------
def test_affine_transplant_anchor_lands_through_rotation(tmp_path):
    from PIL import Image

    _write_asset(str(tmp_path), axis=(1.0, 0.0))
    asset = lwa.load_assets(str(tmp_path))[0]
    cand = Image.new("RGB", (500, 500), (0, 0, 0))
    out = np.asarray(lwa.affine_transplant(cand, asset, (250, 250), (0.0, 1.0), 80.0))
    win = out[250 - 3:250 + 4, 250 - 3:250 + 4].reshape(-1, 3)
    assert any(_is_magenta(p) for p in win)


# ---------------------------------------------------------------------------
# 5. affine_transplant: a larger forearm length paints a strictly larger footprint.
# ---------------------------------------------------------------------------
def test_affine_transplant_larger_L_larger_footprint(tmp_path):
    from PIL import Image

    _write_asset(str(tmp_path))
    asset = lwa.load_assets(str(tmp_path))[0]
    cand = Image.new("RGB", (600, 400), (0, 0, 0))
    cand_arr = np.asarray(cand)
    out_small = np.asarray(lwa.affine_transplant(cand, asset, (300, 200), (1.0, 0.0), 60.0))
    out_big = np.asarray(lwa.affine_transplant(cand, asset, (300, 200), (1.0, 0.0), 120.0))
    foot_small = int(np.any(out_small != cand_arr, axis=2).sum())
    foot_big = int(np.any(out_big != cand_arr, axis=2).sum())
    assert foot_big > foot_small > 0
