"""CI-safe tests for tools/lw_gen_weaponpass.py (M1 weapon pass, W1 rung).

Torch-free by construction: importing lw_gen_weaponpass must NOT pull
torch / diffusers / cv2 / onnxruntime (every heavy dep is lazy inside a
function). Every test injects a STUB backend (a known keypoint map) and a STUB
inpainter (a solid-color PIL image) so no onnx pose model and no SDXL pipeline
is ever loaded. The pure helpers (select_wrist_inputs / paste_back /
assert_outside_identity) are unit-tested directly; the batch driver is proven
against a temp batch dir + gen_manifest.json built from the real
new_candidate_record contract.

The one real-GPU acceptance test (test_acceptance_seed42_right_e2e) is SKIPPED
unless LW_GEN_E2E=1 - the orchestrator runs it on the box, not CI.
"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_gen_localizer_eval as loc  # noqa: E402
from tools import lw_gen_qa  # noqa: E402
from tools import lw_gen_run as gr  # noqa: E402
from tools import lw_gen_weaponfix as lgw  # noqa: E402
from tools import lw_gen_weaponpass as wp  # noqa: E402
from tools.lw_gen_qa import RawScore, WeaponScore  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Stub factories: a known right-forearm backend + a solid-color inpainter.
# ---------------------------------------------------------------------------
def _right_forearm_backend(**kp_over):
    """A stub pose backend: a clean horizontal right forearm, face joints off.

    kp_over lets a test null out a joint (e.g. RWrist=None) to drive a fallback.
    Mirrors the dwpose_backend(image_path, min_conf=...) call signature.
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


def _solid_inpainter(color=(0, 255, 0), record=None):
    """A stub inpainter: returns a solid-color PIL image sized to the input."""
    from PIL import Image

    def inpainter(image, mask_image, prompt, negative_prompt, strength, seed):
        if record is not None:
            record.append({"seed": seed, "strength": strength, "size": image.size})
        return Image.new("RGB", image.size, color)

    return inpainter


# Weapon-gate stubs: canned WeaponScores so no CLIP model ever loads. A PASS
# score clears any calibrated floor (cos 0.90); a REJECT score fails the
# offclass clause (cos 0.05). weapon_pass grades these via resolve_weapon_
# thresholds, so the injected config carries the floors under test.
W_PASS = WeaponScore(weapon_cos=0.90, weapon_off=0.05, lap_var=500.0)
W_REJECT = WeaponScore(weapon_cos=0.05, weapon_off=0.02, lap_var=500.0)
# gate_mode "clip" drives the auto-accept path (the injected gate stub); the
# shipped default is "operator" (dead CLIP gate -> save-all-rolls review lane).
W_CFG = {"weapon": {"gate_mode": "clip", "T_weapon": 0.22, "T_wmargin": 0.03,
                    "T_wblur": 150.0}}
W_OP_CFG = {"weapon": {"gate_mode": "operator"}}


def _gate_const(score):
    """A stub weapon gate returning the same WeaponScore on every roll."""
    def gate(crop_img):
        return score
    return gate


def _gate_seq(*scores, record=None):
    """A stub weapon gate returning scores in order (last repeats if exhausted)."""
    calls = {"n": 0}

    def gate(crop_img):
        i = calls["n"]
        calls["n"] += 1
        if record is not None:
            record.append(i)
        return scores[i] if i < len(scores) else scores[-1]

    return gate


def _make_batch(tmp_path, name="batch", w=672, h=384, base=(40, 0, 0),
                fname="cand_00.png", seed=4242):
    """Write a batch dir with one real PNG candidate + a gen_manifest.json."""
    from PIL import Image

    batch = tmp_path / name
    batch.mkdir()
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, :, 0], arr[:, :, 1], arr[:, :, 2] = base
    Image.fromarray(arr).save(batch / fname)

    rec = gr.new_candidate_record(fname, seed, 1)
    manifest = {
        "batch_id": "vayne-splash-20260711000000",
        "subject": "Vayne", "subject_aliases": ["Vayne"], "style": "splash",
        "model": "MODEL.safetensors", "clip_model": "ViT-L-14",
        "prompt": "splash art of Vayne", "negative": "text, watermark",
        "candidates": [rec], "promote": {},
    }
    (batch / "gen_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return batch


# ---------------------------------------------------------------------------
# 0. Import safety: the heavy backends stay lazy (torch/cv2/onnx/diffusers-free).
# ---------------------------------------------------------------------------
def test_import_is_lazy_and_torch_free():
    for banned in ("torch", "diffusers", "cv2", "onnxruntime"):
        assert banned not in sys.modules
    assert callable(wp.weapon_pass)
    assert callable(wp.paste_back)
    assert callable(wp.select_wrist_inputs)
    assert callable(wp.assert_outside_identity)


# ---------------------------------------------------------------------------
# 1. select_wrist_inputs picks the matching side hand, passes kp_map whole.
# ---------------------------------------------------------------------------
def test_select_wrist_inputs_picks_side_hand():
    out = loc.BackendOutput(
        kp_map={"RWrist": (0.6, 0.5), "RElbow": (0.5, 0.5)},
        left_hand=[(0.30, 0.50)],
        right_hand=[(0.70, 0.50), (0.72, 0.52)],
    )
    kp_r, hand_r = wp.select_wrist_inputs(out, "right")
    assert kp_r is out.kp_map
    assert hand_r == [(0.70, 0.50), (0.72, 0.52)]

    kp_l, hand_l = wp.select_wrist_inputs(out, "left")
    assert kp_l is out.kp_map
    assert hand_l == [(0.30, 0.50)]


# ---------------------------------------------------------------------------
# 2. The localizer's COCO-WholeBody adapter feeds weaponfix (no onnx).
#    A synthetic 133-kp PIXEL array with a clean right forearm -> ok mask.
# ---------------------------------------------------------------------------
def test_cocowb_kp_map_feeds_weapon_roi():
    w, h = 1344, 768
    kps = [(0.0, 0.0, 0.0) for _ in range(133)]
    kps[loc.CWB["RElbow"]] = (600.0, 400.0, 0.9)   # RElbow px
    kps[loc.CWB["RWrist"]] = (760.0, 400.0, 0.9)   # RWrist px (forearm 160px)

    kp_map, left_hand, right_hand = loc.cocowb_to_kp_map(kps, (w, h), min_conf=0.3)
    assert kp_map["RWrist"] is not None
    assert kp_map["nose"] is None  # low-conf -> None -> no face disc

    res = lgw.weapon_roi_from_keypoints(kp_map, "right", (w, h), right_hand)
    assert res.ok is True
    assert res.mask_binary is not None
    assert bool(res.mask_binary[400, 760])  # hot at the RWrist pixel [y, x]


# ---------------------------------------------------------------------------
# 3. paste_back composites: inside the mask == inpainted, outside == candidate.
# ---------------------------------------------------------------------------
def test_paste_back_changes_only_inside_mask():
    cand = np.zeros((10, 12, 3), dtype=np.uint8)
    inpainted = np.full((10, 12, 3), 200, dtype=np.uint8)
    mask = np.zeros((10, 12), dtype=bool)
    mask[3:6, 4:8] = True

    out = wp.paste_back(cand, inpainted, mask)
    assert out.dtype == cand.dtype
    assert (out[mask] == 200).all()       # inside -> inpainted
    assert (out[~mask] == 0).all()        # outside -> candidate (byte-identical)


# ---------------------------------------------------------------------------
# 4. assert_outside_identity passes on a real composite, raises on any leak.
# ---------------------------------------------------------------------------
def test_outside_identity_assert_passes_and_raises():
    cand = np.zeros((8, 8, 3), dtype=np.uint8)
    inpainted = np.full((8, 8, 3), 255, dtype=np.uint8)
    mask = np.zeros((8, 8), dtype=bool)
    mask[2:5, 2:5] = True
    final = wp.paste_back(cand, inpainted, mask)

    wp.assert_outside_identity(cand, final, mask)  # composite -> no raise

    bad = final.copy()
    bad[0, 0, 0] = 123  # mutate a pixel OUTSIDE the mask
    with pytest.raises(AssertionError):
        wp.assert_outside_identity(cand, bad, mask)


# ---------------------------------------------------------------------------
# 5. weapon_pass advances cand[file] -> _wfix, records provenance, writes a
#    PNG that differs from the raw ONLY inside the binary mask, + a sidecar.
# ---------------------------------------------------------------------------
def test_weapon_pass_advances_cand_file_and_provenance(tmp_path):
    from PIL import Image

    batch = _make_batch(tmp_path)
    record = []
    manifest = wp.weapon_pass(
        str(batch), wrist="right",
        backend=_right_forearm_backend(),
        inpainter=_solid_inpainter(color=(0, 255, 0), record=record),
        gate=_gate_const(W_PASS), config=W_CFG,
    )

    cand = manifest["candidates"][0]
    assert cand["file"] == "cand_00_wfix.png"
    assert cand["stage"] == "wfix"
    assert "cand_00.png" in cand["provenance"]
    assert len(record) == 1  # first roll gated PASS -> stop

    assert (batch / "cand_00_wfix.png").exists()

    # Recompute the mask the pass used (deterministic stub backend).
    out = _right_forearm_backend()(str(batch / "cand_00.png"))
    W, H = Image.open(batch / "cand_00.png").size
    roi = lgw.weapon_roi_from_keypoints(out.kp_map, "right", (W, H), out.right_hand)
    mask = roi.mask_binary

    raw = np.asarray(Image.open(batch / "cand_00.png").convert("RGB"))
    fixed = np.asarray(Image.open(batch / "cand_00_wfix.png").convert("RGB"))
    assert (fixed[mask] == (0, 255, 0)).all()          # inside -> inpainted green
    assert np.array_equal(fixed[~mask], raw[~mask])    # outside -> raw, identical

    sidecar = json.loads((batch / "cand_00.weapon.json").read_text(encoding="utf-8"))
    assert sidecar["outside_mask_identical"] is True
    assert sidecar["fallback"] is None
    assert sidecar["wrist"] == "right"
    assert sidecar["rung"] == "w1"
    assert sidecar["verdict"] == "PASS"
    assert sidecar["weapon_cos"] == 0.90
    assert sidecar["weapon_off"] == 0.05
    assert sidecar["chosen_roll"] == 0      # first roll passed the gate
    assert sidecar["rolls_tried"] == 1


# ---------------------------------------------------------------------------
# 6. A fallback (missing wrist) routes to review: no inpaint, cand[file] intact.
# ---------------------------------------------------------------------------
def test_fallback_routes_to_review_no_inpaint(tmp_path):
    batch = _make_batch(tmp_path)
    record = []
    manifest = wp.weapon_pass(
        str(batch), wrist="right",
        backend=_right_forearm_backend(RWrist=None),  # -> missing_wrist
        inpainter=_solid_inpainter(record=record),
    )

    assert record == []  # inpainter NEVER called
    cand = manifest["candidates"][0]
    assert cand["file"] == "cand_00.png"          # unchanged
    assert cand.get("stage", "raw") == "raw"
    assert not (batch / "cand_00_wfix.png").exists()

    sidecar = json.loads((batch / "cand_00.weapon.json").read_text(encoding="utf-8"))
    assert sidecar["fallback"] == "missing_wrist"


# ---------------------------------------------------------------------------
# 7. Propose mode (wrist=None) emits both-wrist overlays, mutates nothing.
# ---------------------------------------------------------------------------
def test_propose_emits_both_overlays_no_mutation(tmp_path):
    batch = _make_batch(tmp_path)
    record = []
    manifest = wp.weapon_pass(
        str(batch), wrist=None,
        backend=_right_forearm_backend(),
        inpainter=_solid_inpainter(record=record),
    )

    assert record == []  # propose never inpaints
    assert (batch / "weapon_review" / "cand_00_overlay.png").exists()
    cand = manifest["candidates"][0]
    assert cand["file"] == "cand_00.png"          # untouched
    assert not (batch / "cand_00_wfix.png").exists()


# ---------------------------------------------------------------------------
# 8. Re-QA consumes the advanced file: score_batch keys on cand[file] (_wfix).
# ---------------------------------------------------------------------------
def test_reqa_consumes_advanced_file(tmp_path):
    batch = _make_batch(tmp_path)
    wp.weapon_pass(
        str(batch), wrist="right",
        backend=_right_forearm_backend(),
        inpainter=_solid_inpainter(),
        gate=_gate_const(W_PASS), config=W_CFG,
    )

    def qa_stub(path):
        if os.path.basename(path) == "cand_00_wfix.png":
            return RawScore(subject_cos=0.35, off_cos=0.10, aesthetic=0.60, lap_var=500.0)
        return RawScore(subject_cos=0.10, off_cos=0.05, aesthetic=0.01, lap_var=1.0)

    updated = lw_gen_qa.score_batch(str(batch), scorer=qa_stub, config={})
    cand = updated["candidates"][0]
    assert cand["file"] == "cand_00_wfix.png"
    assert cand["verdict"] == "PASS"  # flips on the wfix file, keyed by cand[file]


# ---------------------------------------------------------------------------
# 8b. Gated rolls: gate REJECTs roll 0, PASSes roll 1 -> 2 inpaint calls, the
#     accepted roll's seed = base+1, sidecar records the winning roll + scores.
# ---------------------------------------------------------------------------
def test_gated_rolls_accept_first_pass(tmp_path):
    batch = _make_batch(tmp_path, seed=100)
    record = []
    manifest = wp.weapon_pass(
        str(batch), wrist="right", rolls=4,
        backend=_right_forearm_backend(),
        inpainter=_solid_inpainter(record=record),
        gate=_gate_seq(W_REJECT, W_PASS), config=W_CFG,
    )
    assert len(record) == 2                       # stopped at the first PASS
    assert record[0]["seed"] == 100               # roll 0 seed = base
    assert record[1]["seed"] == 101               # roll 1 seed = base + 1
    cand = manifest["candidates"][0]
    assert cand["file"] == "cand_00_wfix.png"     # advanced on the PASS

    sidecar = json.loads((batch / "cand_00.weapon.json").read_text(encoding="utf-8"))
    assert sidecar["verdict"] == "PASS"
    assert sidecar["chosen_roll"] == 1
    assert sidecar["chosen_seed"] == 101
    assert sidecar["rolls_tried"] == 2


# ---------------------------------------------------------------------------
# 8c. All rolls REJECT -> STOP-rule review lane: no _wfix advance, cand[file]
#     stays raw, the best near-miss lands in weapon_review/, sidecar is REJECT.
# ---------------------------------------------------------------------------
def test_gated_all_reject_routes_to_review(tmp_path):
    batch = _make_batch(tmp_path)
    record = []
    # Ascending cos so the LAST roll is the best near-miss (still a REJECT).
    manifest = wp.weapon_pass(
        str(batch), wrist="right", rolls=3,
        backend=_right_forearm_backend(),
        inpainter=_solid_inpainter(record=record),
        gate=_gate_seq(
            WeaponScore(0.05, 0.02, 500.0),
            WeaponScore(0.10, 0.02, 500.0),
            WeaponScore(0.15, 0.02, 500.0),
        ),
        config=W_CFG,
    )
    assert len(record) == 3                        # exhausted the roll budget
    cand = manifest["candidates"][0]
    assert cand["file"] == "cand_00.png"           # NOT advanced
    assert cand.get("stage", "raw") == "raw"
    assert not (batch / "cand_00_wfix.png").exists()

    sidecar = json.loads((batch / "cand_00.weapon.json").read_text(encoding="utf-8"))
    assert sidecar["verdict"] == "REJECT"
    assert sidecar["rolls_tried"] == 3
    assert sidecar["weapon_cos"] == 0.15           # kept the best near-miss
    assert (batch / "weapon_review" / "cand_00_wbest.png").exists()


# ---------------------------------------------------------------------------
# 8d. First roll PASS -> exactly one inpaint call (no wasted rolls).
# ---------------------------------------------------------------------------
def test_gated_first_roll_pass_stops_early(tmp_path):
    batch = _make_batch(tmp_path)
    record = []
    wp.weapon_pass(
        str(batch), wrist="right", rolls=4,
        backend=_right_forearm_backend(),
        inpainter=_solid_inpainter(record=record),
        gate=_gate_const(W_PASS), config=W_CFG,
    )
    assert len(record) == 1


# ---------------------------------------------------------------------------
# 8e. Operator lane (dead-gate DEFAULT): run EVERY roll, save each to
#     weapon_review/, sidecar verdict REVIEW, cand[file] never advanced, and the
#     CLIP gate is never consulted (no gate injected, none built).
# ---------------------------------------------------------------------------
def test_operator_mode_saves_all_rolls_no_advance(tmp_path):
    batch = _make_batch(tmp_path, seed=50)
    record = []
    manifest = wp.weapon_pass(
        str(batch), wrist="right", rolls=3,
        backend=_right_forearm_backend(),
        inpainter=_solid_inpainter(record=record),
        config=W_OP_CFG,  # gate omitted: operator lane never reaches the gate
    )
    assert len(record) == 3                        # every roll ran (no early stop)
    assert [r["seed"] for r in record] == [50, 51, 52]
    cand = manifest["candidates"][0]
    assert cand["file"] == "cand_00.png"           # NOT advanced
    assert cand.get("stage", "raw") == "raw"
    assert not (batch / "cand_00_wfix.png").exists()
    for roll in range(3):
        assert (batch / "weapon_review" / f"cand_00_wroll{roll}.png").exists()

    sidecar = json.loads((batch / "cand_00.weapon.json").read_text(encoding="utf-8"))
    assert sidecar["verdict"] == "REVIEW"
    assert sidecar["reason"] == "clip_gate_dead"
    assert sidecar["gate_mode"] == "operator"
    assert len(sidecar["review_files"]) == 3
    assert sidecar["outside_mask_identical"] is True


# ---------------------------------------------------------------------------
# 8f. Operator lane is the DEFAULT when config omits weapon.gate_mode entirely.
# ---------------------------------------------------------------------------
def test_operator_mode_is_default(tmp_path):
    batch = _make_batch(tmp_path)
    manifest = wp.weapon_pass(
        str(batch), wrist="right", rolls=1,
        backend=_right_forearm_backend(),
        inpainter=_solid_inpainter(),
        config={"weapon": {}},  # no gate_mode key -> defaults to operator
    )
    assert manifest["candidates"][0]["file"] == "cand_00.png"  # not advanced
    sidecar = json.loads((batch / "cand_00.weapon.json").read_text(encoding="utf-8"))
    assert sidecar["verdict"] == "REVIEW"


# ---------------------------------------------------------------------------
# W2 reference-transplant rung: a recording inpainter (captures the exact image
# it is handed) + a synthetic crossbow-crop asset dir. Proves the transplant is
# applied before the inpaint, the w2_strength ladder is used in order, every roll
# lands in weapon_review/ as _w2roll{i}.png, cand[file] never advances, and the
# sidecar is a REVIEW verdict. Design: design_weapon.md sec 3 (W2) + sec 4.
# ---------------------------------------------------------------------------
def _recording_inpainter(color=(0, 255, 0), record=None):
    """Stub inpainter that records the RGB array of the image handed to it."""
    from PIL import Image

    def inpainter(image, mask_image, prompt, negative_prompt, strength, seed):
        if record is not None:
            record.append({
                "seed": seed, "strength": strength,
                "image": np.asarray(image.convert("RGB")).copy(),
            })
        return Image.new("RGB", image.size, color)

    return inpainter


def _write_weapon_asset(adir, file="cb.png"):
    """A synthetic right-hand side-view crossbow crop + meta.json (opaque, blue
    body with a magenta anchor block at (30, 30); forearm_len_px 40)."""
    from PIL import Image

    os.makedirs(adir, exist_ok=True)
    img = Image.new("RGBA", (120, 60), (0, 0, 200, 255))
    px = img.load()
    for yy in range(23, 38):
        for xx in range(23, 38):
            px[xx, yy] = (255, 0, 255, 255)
    img.save(os.path.join(adir, file))
    meta = {"assets": [{
        "file": file, "anchor_px": [30, 30], "axis": [1.0, 0.0],
        "forearm_len_px": 40.0, "handedness": "right", "view": "side",
    }]}
    with open(os.path.join(adir, "meta.json"), "w", encoding="utf-8") as fo:
        json.dump(meta, fo)


def test_w2_operator_lane_transplants_and_saves_rolls(tmp_path):
    from PIL import Image

    batch = _make_batch(tmp_path, seed=700)
    adir = tmp_path / "assets"
    _write_weapon_asset(str(adir))
    record = []
    cfg = {"weapon": {"gate_mode": "operator", "assets": str(adir),
                      "w2_strength": [0.35, 0.45, 0.5]}}
    manifest = wp.weapon_pass(
        str(batch), wrist="right", rung="w2",
        backend=_right_forearm_backend(),
        inpainter=_recording_inpainter(record=record),
        config=cfg,
    )

    # (b) the w2_strength ladder is used, in order, with base+i seeds.
    assert [round(r["strength"], 2) for r in record] == [0.35, 0.45, 0.5]
    assert [r["seed"] for r in record] == [700, 701, 702]

    # (a) transplant applied: the image handed to the inpainter differs from the
    #     raw candidate (the crossbow crop was pasted onto the forearm).
    raw = np.asarray(Image.open(batch / "cand_00.png").convert("RGB"))
    assert not np.array_equal(record[0]["image"], raw)

    # (c) N review rolls saved as _w2roll{i}.png.
    for i in range(3):
        assert (batch / "weapon_review" / f"cand_00_w2roll{i}.png").exists()

    # (d) cand[file] not advanced (operator lane never auto-promotes).
    cand = manifest["candidates"][0]
    assert cand["file"] == "cand_00.png"
    assert cand.get("stage", "raw") == "raw"
    assert not (batch / "cand_00_wfix.png").exists()

    # (e) + (f) sidecar: REVIEW verdict, rung w2, asset + strengths recorded,
    #     out-of-mask identity held.
    sidecar = json.loads((batch / "cand_00.weapon.json").read_text(encoding="utf-8"))
    assert sidecar["rung"] == "w2"
    assert sidecar["verdict"] == "REVIEW"
    assert sidecar["reason"] == "clip_gate_dead"
    assert sidecar["outside_mask_identical"] is True
    assert sidecar["asset"] == "cb.png"
    assert sidecar["strengths"] == [0.35, 0.45, 0.5]
    assert len(sidecar["review_files"]) == 3


def test_w2_default_strengths_when_config_omits(tmp_path):
    batch = _make_batch(tmp_path, seed=10)
    adir = tmp_path / "assets"
    _write_weapon_asset(str(adir))
    record = []
    wp.weapon_pass(
        str(batch), wrist="right", rung="w2",
        backend=_right_forearm_backend(),
        inpainter=_recording_inpainter(record=record),
        config={"weapon": {"assets": str(adir)}},  # no w2_strength -> default ladder
    )
    assert [round(r["strength"], 2) for r in record] == [0.35, 0.45, 0.5]


def test_w2_no_asset_routes_to_review(tmp_path):
    batch = _make_batch(tmp_path)
    empty = tmp_path / "empty_assets"
    empty.mkdir()
    record = []
    manifest = wp.weapon_pass(
        str(batch), wrist="right", rung="w2",
        backend=_right_forearm_backend(),
        inpainter=_recording_inpainter(record=record),
        config={"weapon": {"assets": str(empty)}},  # meta.json absent -> []
    )
    assert record == []  # nothing inpainted
    assert manifest["candidates"][0]["file"] == "cand_00.png"
    assert not (batch / "cand_00_wfix.png").exists()
    sidecar = json.loads((batch / "cand_00.weapon.json").read_text(encoding="utf-8"))
    assert sidecar["fallback"] == "no_asset"
    assert sidecar["rung"] == "w2"


def test_w2_no_forearm_routes_to_review(tmp_path):
    batch = _make_batch(tmp_path)
    record = []
    manifest = wp.weapon_pass(
        str(batch), wrist="right", rung="w2",
        backend=_right_forearm_backend(RWrist=None),  # forearm_frame -> None
        inpainter=_recording_inpainter(record=record),
        config={"weapon": {"assets": "tools/models/weapon_assets/vayne"}},
    )
    assert record == []
    assert manifest["candidates"][0]["file"] == "cand_00.png"
    sidecar = json.loads((batch / "cand_00.weapon.json").read_text(encoding="utf-8"))
    assert sidecar["fallback"] == "no_forearm"
    assert sidecar["rung"] == "w2"


def test_w2_accepts_injected_assets_param(tmp_path):
    # assets= injected directly (bypassing config load) still transplants + rolls.
    batch = _make_batch(tmp_path, seed=5)
    adir = tmp_path / "assets"
    _write_weapon_asset(str(adir))
    assets = wp.load_assets(str(adir))
    record = []
    wp.weapon_pass(
        str(batch), wrist="right", rung="w2", assets=assets,
        backend=_right_forearm_backend(),
        inpainter=_recording_inpainter(record=record),
        config={"weapon": {"w2_strength": [0.4]}},
    )
    assert [round(r["strength"], 2) for r in record] == [0.4]
    assert (batch / "weapon_review" / "cand_00_w2roll0.png").exists()


# ---------------------------------------------------------------------------
# 9. GPU acceptance (real DWPose + real SDXL inpaint) - SKIPPED unless LW_GEN_E2E=1.
#    The orchestrator runs this on the box; CI never loads onnx/torch.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    os.environ.get("LW_GEN_E2E") != "1",
    reason="real DWPose + SDXL inpaint; GPU-only, run by the orchestrator",
)
def test_acceptance_seed42_right_e2e(tmp_path):
    from PIL import Image

    src = os.path.join(ROOT, "images", "_gen_scratch", "exp4_volume", "seed42.png")
    assert os.path.exists(src), f"acceptance source missing: {src}"

    batch = tmp_path / "e2e"
    batch.mkdir()
    Image.open(src).convert("RGB").save(batch / "cand_00.png")
    rec = gr.new_candidate_record("cand_00.png", 42, 1)
    manifest = {
        "batch_id": "vayne-e2e", "subject": "Vayne", "subject_aliases": ["Vayne"],
        "style": "splash", "model": "MODEL.safetensors", "clip_model": "ViT-L-14",
        "prompt": "splash art of Vayne", "negative": "text, watermark",
        "candidates": [rec], "promote": {},
    }
    (batch / "gen_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # Real backend + real inpainter (config-driven), no stubs. Shipped config
    # defaults to the operator lane (the CLIP gate is dead), so this proves the
    # DWPose -> mask -> SDXL-inpaint -> paste-back -> review chain end to end.
    out = wp.weapon_pass(str(batch), wrist="right")
    cand = out["candidates"][0]
    sidecar = json.loads((batch / "cand_00.weapon.json").read_text(encoding="utf-8"))

    assert sidecar["verdict"] == "REVIEW"
    assert cand["file"] == "cand_00.png"              # operator lane never advances
    assert sidecar["outside_mask_identical"] is True  # out-of-mask pixels identical
    assert len(sidecar["review_files"]) >= 1
    for rf in sidecar["review_files"]:
        assert (batch / "weapon_review" / rf).exists()
