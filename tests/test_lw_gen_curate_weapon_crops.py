"""CI-safe tests for tools/lw_gen_curate_weapon_crops.py (W4 dataset curation).

Torch-free by construction: importing lw_gen_curate_weapon_crops must NOT pull
torch / diffusers / cv2 / onnxruntime (every heavy dep is lazy inside a
function, exactly like lw_gen_weaponpass). Every crop-path test injects a STUB
pose backend (a known keypoint map) so no onnx pose model is ever loaded; the
pure helpers (letterbox_to_square / build_caption) are unit-tested directly.

Mirrors the stub-backend fixture pattern in tests/test_lw_gen_weaponpass.py.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_gen_localizer_eval as loc  # noqa: E402
from tools import lw_gen_curate_weapon_crops as cur  # noqa: E402


# ---------------------------------------------------------------------------
# Stub factories: a known right-forearm backend + tiny splash / asset writers.
# Mirrors _right_forearm_backend in tests/test_lw_gen_weaponpass.py.
# ---------------------------------------------------------------------------
def _right_forearm_backend(**kp_over):
    """A stub pose backend: a clean horizontal right forearm, face joints off.

    kp_over lets a test null out a joint (RWrist=None -> no_forearm) or move one
    (a far-apart elbow/wrist -> an area_cap ROI fallback). Mirrors the
    dwpose_backend(image_path, min_conf=...) call signature.
    """
    kp_map = {
        "nose": None, "neck": None,
        "RElbow": (0.5, 0.5), "RWrist": (0.6, 0.5),
        "LElbow": None, "LWrist": None,
    }
    kp_map.update(kp_over)

    def backend(image_path, min_conf=0.3):
        return loc.BackendOutput(kp_map=dict(kp_map), left_hand=[], right_hand=[])

    return backend


def _write_splash(d, name, w=672, h=384, color=(40, 60, 80)):
    from PIL import Image

    Image.new("RGB", (w, h), color).save(os.path.join(d, name))


def _write_asset_dir(adir, file="cb_right.png"):
    """A synthetic right-hand crossbow crop (RGBA) + meta.json.

    Mirrors _write_weapon_asset in tests/test_lw_gen_weaponpass.py.
    """
    from PIL import Image

    os.makedirs(adir, exist_ok=True)
    Image.new("RGBA", (120, 60), (0, 0, 200, 255)).save(os.path.join(adir, file))
    meta = {"assets": [{
        "file": file, "anchor_px": [30, 30], "axis": [1.0, 0.0],
        "forearm_len_px": 40.0, "handedness": "right", "view": "side",
    }]}
    with open(os.path.join(adir, "meta.json"), "w", encoding="utf-8") as fo:
        json.dump(meta, fo)


# ---------------------------------------------------------------------------
# 0. Import safety: the heavy backend stays lazy (torch/cv2/onnx/diffusers-free).
# ---------------------------------------------------------------------------
def test_import_is_lazy_and_torch_free():
    for banned in ("torch", "diffusers", "cv2", "onnxruntime"):
        assert banned not in sys.modules
    assert callable(cur.curate)
    assert callable(cur.letterbox_to_square)
    assert callable(cur.build_caption)


# ---------------------------------------------------------------------------
# 1. letterbox_to_square: a WIDE image -> exactly 1024x1024, aspect preserved,
#    padded with the neutral field top/bottom.
# ---------------------------------------------------------------------------
def test_letterbox_wide_preserves_aspect_and_pads():
    from PIL import Image

    src = Image.new("RGB", (200, 100), (200, 10, 10))  # 2:1 wide, red
    out = cur.letterbox_to_square(src, 1024)
    assert out.size == (1024, 1024)
    arr = np.asarray(out)
    assert tuple(int(c) for c in arr[512, 512]) == (200, 10, 10)   # center = content
    assert tuple(int(c) for c in arr[10, 512]) == (128, 128, 128)  # top pad = neutral
    # 1024-wide content at 2:1 -> 512 tall band, centered (rows 256..767).
    content_rows = np.where(np.any(arr != 128, axis=(1, 2)))[0]
    assert content_rows.min() >= 250 and content_rows.max() <= 773
    assert 500 <= (content_rows.max() - content_rows.min() + 1) <= 524


# ---------------------------------------------------------------------------
# 2. letterbox_to_square: a TALL image -> exactly 1024x1024, aspect preserved,
#    padded with the neutral field left/right.
# ---------------------------------------------------------------------------
def test_letterbox_tall_preserves_aspect_and_pads():
    from PIL import Image

    src = Image.new("RGB", (100, 200), (10, 200, 10))  # 1:2 tall, green
    out = cur.letterbox_to_square(src, 1024)
    assert out.size == (1024, 1024)
    arr = np.asarray(out)
    assert tuple(int(c) for c in arr[512, 512]) == (10, 200, 10)   # center = content
    assert tuple(int(c) for c in arr[512, 10]) == (128, 128, 128)  # left pad = neutral
    content_cols = np.where(np.any(arr != 128, axis=(0, 2)))[0]
    assert content_cols.min() >= 250 and content_cols.max() <= 773
    assert 500 <= (content_cols.max() - content_cols.min() + 1) <= 524


# ---------------------------------------------------------------------------
# 3. build_caption is OBJECT-ONLY: starts with the concept token, pure ASCII,
#    and never leaks the character name ("vayne " as a word) or a skin name.
# ---------------------------------------------------------------------------
def test_build_caption_object_only_ascii_no_identity():
    names = ("vayne_00_default", "vayne_03_dragonslayer-vayne",
             "vayne_25_sentinel-vayne", "project_right", "aristocrat_right")
    skins = ("default", "dragonslayer", "sentinel", "project", "aristocrat",
             "heartseeker", "firecracker", "soulstealer", "arclight")
    for name in names:
        cap = cur.build_caption(name)
        assert cap.startswith("vaynecrossbow")
        cap.encode("ascii")             # raises on any non-ASCII (dashes, smart quotes)
        assert "vayne " not in cap      # no character token (vayne followed by a space)
        for skin in skins:
            assert skin not in cap      # no skin name leaks


# ---------------------------------------------------------------------------
# 4. The crop+save path with an injected localizing stub backend: a raw 1024
#    PNG + a paired caption + an eyeball overlay are written; counts add up.
# ---------------------------------------------------------------------------
def test_curate_crop_path_writes_png_and_caption(tmp_path):
    from PIL import Image

    splash_dir = tmp_path / "splashes"
    splash_dir.mkdir()
    _write_splash(str(splash_dir), "vayne_00_test.jpg")
    out_dir = tmp_path / "out"

    summary = cur.curate(
        str(splash_dir), str(tmp_path / "noassets"), str(out_dir),
        backend=_right_forearm_backend(), min_conf=0.3, pad=0.1,
    )

    raw = out_dir / "raw" / "vayne_00_test.png"
    cap = out_dir / "raw" / "vayne_00_test.txt"
    ov = out_dir / "overlays" / "vayne_00_test.png"
    assert raw.exists() and cap.exists() and ov.exists()
    assert Image.open(raw).size == (1024, 1024)
    assert Image.open(raw).mode == "RGB"
    assert cap.read_text(encoding="ascii").startswith("vaynecrossbow")
    assert summary["localized"] == 1
    assert summary["skipped"] == []
    assert summary["total"] == 1


# ---------------------------------------------------------------------------
# 5. A no-forearm backend (RWrist None -> forearm_frame None) skips the splash,
#    counts it as no_forearm, writes NO raw crop, but writes the overlay anyway.
# ---------------------------------------------------------------------------
def test_curate_no_forearm_skips_counted_no_crop(tmp_path):
    splash_dir = tmp_path / "splashes"
    splash_dir.mkdir()
    _write_splash(str(splash_dir), "vayne_01_test.jpg")
    out_dir = tmp_path / "out"

    summary = cur.curate(
        str(splash_dir), str(tmp_path / "noassets"), str(out_dir),
        backend=_right_forearm_backend(RWrist=None),
    )

    assert summary["localized"] == 0
    assert summary["skipped"] == [("vayne_01_test", "no_forearm")]
    assert not (out_dir / "raw" / "vayne_01_test.png").exists()
    assert not (out_dir / "raw" / "vayne_01_test.txt").exists()
    assert (out_dir / "overlays" / "vayne_01_test.png").exists()  # operator sees why


# ---------------------------------------------------------------------------
# 6. A valid forearm but an unusable ROI (huge forearm -> area_cap fallback)
#    skips with roi.fallback, writes NO raw crop, still writes the overlay.
# ---------------------------------------------------------------------------
def test_curate_bad_roi_skips_counted_no_crop(tmp_path):
    splash_dir = tmp_path / "splashes"
    splash_dir.mkdir()
    _write_splash(str(splash_dir), "vayne_02_test.jpg")
    out_dir = tmp_path / "out"

    # Elbow far-left, wrist far-right -> forearm ~0.8*W -> ROI blows the area cap.
    summary = cur.curate(
        str(splash_dir), str(tmp_path / "noassets"), str(out_dir),
        backend=_right_forearm_backend(RElbow=(0.1, 0.5), RWrist=(0.9, 0.5)),
    )

    assert summary["localized"] == 0
    assert len(summary["skipped"]) == 1
    name, reason = summary["skipped"][0]
    assert name == "vayne_02_test"
    assert reason == "area_cap"
    assert not (out_dir / "raw" / "vayne_02_test.png").exists()
    assert (out_dir / "overlays" / "vayne_02_test.png").exists()


# ---------------------------------------------------------------------------
# 7. The 5-asset-crop path: each RGBA crop composites onto the neutral field,
#    letterboxes to 1024, and gets a paired object-only caption.
# ---------------------------------------------------------------------------
def test_curate_composites_asset_crops(tmp_path):
    from PIL import Image

    splash_dir = tmp_path / "splashes"
    splash_dir.mkdir()  # empty -> 0 splashes localized
    asset_dir = tmp_path / "assets"
    _write_asset_dir(str(asset_dir), file="cb_right.png")
    out_dir = tmp_path / "out"

    summary = cur.curate(
        str(splash_dir), str(asset_dir), str(out_dir),
        backend=_right_forearm_backend(),
    )

    raw = out_dir / "raw" / "asset_cb_right.png"
    cap = out_dir / "raw" / "asset_cb_right.txt"
    assert raw.exists() and cap.exists()
    assert Image.open(raw).size == (1024, 1024)
    assert Image.open(raw).mode == "RGB"
    assert cap.read_text(encoding="ascii").startswith("vaynecrossbow")
    assert summary["assets"] == 1
    assert summary["localized"] == 0
    assert summary["total"] == 1
