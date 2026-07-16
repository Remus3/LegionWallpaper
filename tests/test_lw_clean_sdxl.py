"""CI-safe pure tests for tools/lw_clean_sdxl.py (SDXL cleaning inpaint worker).

Torch-free by construction: importing lw_clean_sdxl must NOT pull torch or
diffusers (both are lazy inside build_inpaint_pipe / _run_pipe). Every pure
helper (resolve_checkpoint / paste_back / assert_outside_identity / mask_bbox /
parse_worklist / build_params / the atomic writers) is unit-tested with numpy +
PIL only. The real pipe load + inpaint are proven by the .venv-gen --selfcheck
and a 1-item smoke the orchestrator runs on the box (not in CI).
"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_clean_sdxl as cs  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 0. Import safety: torch / diffusers stay lazy; the pure surface is callable.
# ---------------------------------------------------------------------------
def test_import_is_lazy_and_torch_free():
    for banned in ("torch", "diffusers"):
        assert banned not in sys.modules
    assert callable(cs.resolve_checkpoint)
    assert callable(cs.paste_back)
    assert callable(cs.assert_outside_identity)
    assert callable(cs.mask_bbox)
    assert callable(cs.parse_worklist)
    assert callable(cs.build_params)


# ---------------------------------------------------------------------------
# 1. resolve_checkpoint: registry names map to the right (abs_path, kind).
# ---------------------------------------------------------------------------
def test_resolve_registry_animagine_single_file():
    abs_path, kind = cs.resolve_checkpoint("animagine")
    assert kind == "single_file"
    assert abs_path.endswith("animagine-xl-4.0-opt.safetensors")
    assert os.path.isabs(abs_path)


def test_resolve_registry_folder_names():
    # Inject probes so no real diffusers folder is needed on disk.
    for name in ("dreamshaper", "realvis"):
        abs_path, kind = cs.resolve_checkpoint(
            name, isdir=lambda p: True, isfile=lambda p: True)
        assert kind == "folder"
        assert os.path.isabs(abs_path)


# ---------------------------------------------------------------------------
# 2. resolve_checkpoint: extension detection (.safetensors / .ckpt -> single).
# ---------------------------------------------------------------------------
def test_resolve_safetensors_path_single_file():
    raw = os.path.join(ROOT, "some", "custom", "model.safetensors")
    abs_path, kind = cs.resolve_checkpoint(raw)
    assert kind == "single_file"
    assert abs_path == raw  # raw path passes through unchanged


def test_resolve_ckpt_path_single_file():
    raw = os.path.join(ROOT, "a", "b.ckpt")
    _, kind = cs.resolve_checkpoint(raw)
    assert kind == "single_file"


# ---------------------------------------------------------------------------
# 3. resolve_checkpoint: a raw dir holding model_index.json -> folder.
# ---------------------------------------------------------------------------
def test_resolve_raw_dir_with_model_index_folder():
    raw = os.path.join(ROOT, "some", "diffusers_dir")
    abs_path, kind = cs.resolve_checkpoint(
        raw,
        isdir=lambda p: p == raw,
        isfile=lambda p: p == os.path.join(raw, "model_index.json"))
    assert kind == "folder"
    assert abs_path == raw


def test_resolve_unclassifiable_raises():
    raw = os.path.join(ROOT, "nope", "not_a_model")
    with pytest.raises(ValueError):
        cs.resolve_checkpoint(raw, isdir=lambda p: False, isfile=lambda p: False)


# ---------------------------------------------------------------------------
# 4. paste_back: inside == result, outside == input (byte-identical) on 8x8.
# ---------------------------------------------------------------------------
def test_paste_back_outside_identity_8x8():
    inp = np.zeros((8, 8, 3), dtype=np.uint8)
    result = np.full((8, 8, 3), 200, dtype=np.uint8)
    mask = np.zeros((8, 8), dtype=np.uint8)
    mask[2:5, 2:5] = 255

    out = cs.paste_back(inp, result, mask)
    inside = mask == 255
    assert out.dtype == np.uint8
    assert (out[inside] == 200).all()          # inside -> result
    assert (out[~inside] == 0).all()           # outside -> input value
    assert np.array_equal(out[~inside], inp[~inside])  # byte-identical outside


def test_assert_outside_identity_passes_and_raises():
    inp = np.zeros((8, 8, 3), dtype=np.uint8)
    result = np.full((8, 8, 3), 255, dtype=np.uint8)
    mask = np.zeros((8, 8), dtype=np.uint8)
    mask[2:5, 2:5] = 255
    final = cs.paste_back(inp, result, mask)

    cs.assert_outside_identity(inp, final, mask)  # composite -> no raise

    bad = final.copy()
    bad[0, 0, 0] = 123  # mutate a pixel OUTSIDE the mask
    with pytest.raises(AssertionError):
        cs.assert_outside_identity(inp, bad, mask)


# ---------------------------------------------------------------------------
# 5. mask_bbox: exclusive [x0, y0, x1, y1] of the white region; None if empty.
# ---------------------------------------------------------------------------
def test_mask_bbox_of_white_region():
    mask = np.zeros((10, 12), dtype=np.uint8)
    mask[3:6, 4:8] = 255
    assert cs.mask_bbox(mask) == [4, 3, 8, 6]


def test_mask_bbox_empty_is_none():
    assert cs.mask_bbox(np.zeros((5, 5), dtype=np.uint8)) is None


# ---------------------------------------------------------------------------
# 6. parse_worklist: valid round-trip; missing key raises.
# ---------------------------------------------------------------------------
def test_parse_worklist_valid(tmp_path):
    items = [{"slug": "a", "image": "i.png", "mask": "m.png", "out": "o"}]
    p = tmp_path / "wl.json"
    p.write_text(json.dumps(items), encoding="utf-8")
    assert cs.parse_worklist(str(p)) == items


def test_parse_worklist_missing_key_raises(tmp_path):
    bad = [{"slug": "a", "image": "i.png"}]  # missing mask + out
    p = tmp_path / "wl.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        cs.parse_worklist(str(p))


def test_parse_worklist_not_a_list_raises(tmp_path):
    p = tmp_path / "wl.json"
    p.write_text(json.dumps({"slug": "a"}), encoding="utf-8")
    with pytest.raises(ValueError):
        cs.parse_worklist(str(p))


# ---------------------------------------------------------------------------
# 7. build_params: exact schema + JSON round-trip stability.
# ---------------------------------------------------------------------------
def test_build_params_schema_round_trip():
    params = cs.build_params(
        checkpoint="animagine", strength=0.99, steps=30, guidance=6.0,
        seed=22, mask_bbox=[4, 3, 8, 6])
    assert set(params) == {
        "checkpoint", "strength", "steps", "guidance", "seed", "mask_bbox"}
    rt = json.loads(json.dumps(params))
    assert rt == params
    assert rt["checkpoint"] == "animagine"
    assert rt["steps"] == 30 and isinstance(rt["steps"], int)
    assert rt["strength"] == 0.99
    assert rt["mask_bbox"] == [4, 3, 8, 6]


# ---------------------------------------------------------------------------
# 8. Atomic writers: final file present, no .tmp left, content readable.
# ---------------------------------------------------------------------------
def test_atomic_write_json(tmp_path):
    p = tmp_path / "params.json"
    cs._atomic_write_json(str(p), {"a": 1, "b": [2, 3]})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": [2, 3]}
    assert not (tmp_path / "params.json.tmp").exists()


def test_atomic_write_png(tmp_path):
    from PIL import Image

    img = Image.new("RGB", (6, 4), (10, 20, 30))
    p = tmp_path / "cand.png"
    cs._atomic_write_png(str(p), img)
    assert p.exists()
    assert not (tmp_path / "cand.png.tmp").exists()
    got = Image.open(str(p)).convert("RGB")
    assert got.size == (6, 4)
    assert got.getpixel((0, 0)) == (10, 20, 30)
