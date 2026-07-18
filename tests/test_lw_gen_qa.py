"""CI-safe tests for tools/lw_gen_qa.py (Phase 2 QA scorer).

Torch-free: importing lw_gen_qa must NOT pull open_clip/torch/cv2 (they are lazy).
Every test injects a STUB scorer so no model is ever loaded. Covers:
  (a) HARD Stage-A-before-Stage-B ordering (B not consulted when A fails),
  (b) argmax-over-distractors rejects a high-off_cos wrong-subject candidate,
  (c) reason-code mapping (weak_margin / wrong_subject / degenerate / blurry),
  (d) a clean PASS,
plus threshold resolution and the batch driver writing sidecars + updating the
manifest via score_batch with an injected stub.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from tools import lw_gen_qa  # noqa: E402

from _import_probe import assert_import_free  # noqa: E402
from tools.lw_gen_qa import RawScore, grade  # noqa: E402

THRESH = {"T_subj": 0.26, "T_margin": 0.05, "T_aes": 0.45, "T_blur": 100.0}


def test_module_imports_without_torch():
    """Proves the heavy deps are lazy - importing must not pull torch/open_clip/cv2."""
    assert_import_free("tools.lw_gen_qa", ("torch", "open_clip", "cv2"))


def test_clean_pass():
    s = RawScore(subject_cos=0.35, off_cos=0.10, aesthetic=0.60, lap_var=500.0)
    g = grade(s, THRESH)
    assert g.verdict == "PASS"
    assert g.reason is None
    assert g.stage_a_pass is True
    assert g.stage_b_pass is True
    assert abs(g.margin - 0.25) < 1e-9


def test_wrong_subject_below_floor():
    # subject_cos below T_subj -> wrong_subject regardless of margin/argmax.
    s = RawScore(subject_cos=0.20, off_cos=0.05, aesthetic=0.60, lap_var=500.0)
    g = grade(s, THRESH)
    assert g.verdict == "REJECT"
    assert g.reason == "wrong_subject"
    assert g.stage_a_pass is False
    assert g.stage_b_pass is None  # Stage B never consulted


def test_argmax_over_distractors_rejects_high_off_cos():
    # subject_cos clears the floor (0.30 >= 0.26) but a distractor scores higher
    # (off_cos 0.40) -> subject is NOT the argmax -> wrong_subject, not weak_margin.
    s = RawScore(subject_cos=0.30, off_cos=0.40, aesthetic=0.60, lap_var=500.0)
    g = grade(s, THRESH)
    assert g.verdict == "REJECT"
    assert g.reason == "wrong_subject"
    assert g.stage_a_pass is False
    assert g.stage_b_pass is None
    assert g.margin < 0


def test_weak_margin():
    # clears floor + is argmax, but margin (0.03) < T_margin (0.05) -> weak_margin.
    s = RawScore(subject_cos=0.30, off_cos=0.27, aesthetic=0.60, lap_var=500.0)
    g = grade(s, THRESH)
    assert g.verdict == "REJECT"
    assert g.reason == "weak_margin"
    assert g.stage_a_pass is False
    assert g.stage_b_pass is None


def test_stage_a_gates_stage_b_ordering():
    # Candidate FAILS A (below floor) AND would FAIL B (low aesthetic + low blur).
    # The HARD ordering means it must report an A reason and never consult B.
    s = RawScore(subject_cos=0.10, off_cos=0.05, aesthetic=0.01, lap_var=1.0)
    g = grade(s, THRESH)
    assert g.reason == "wrong_subject"      # A reason, NOT "degenerate"/"blurry"
    assert g.reason not in ("degenerate", "blurry")
    assert g.stage_b_pass is None            # proves B was skipped


def test_stage_b_degenerate_when_a_passes():
    # A passes; aesthetic below T_aes -> degenerate (checked before blur).
    s = RawScore(subject_cos=0.35, off_cos=0.10, aesthetic=0.20, lap_var=500.0)
    g = grade(s, THRESH)
    assert g.verdict == "REJECT"
    assert g.reason == "degenerate"
    assert g.stage_a_pass is True
    assert g.stage_b_pass is False


def test_stage_b_blurry_when_aesthetic_ok():
    # A passes, aesthetic ok, but lap_var below T_blur -> blurry.
    s = RawScore(subject_cos=0.35, off_cos=0.10, aesthetic=0.60, lap_var=50.0)
    g = grade(s, THRESH)
    assert g.verdict == "REJECT"
    assert g.reason == "blurry"
    assert g.stage_a_pass is True
    assert g.stage_b_pass is False


def test_degenerate_takes_precedence_over_blurry():
    # Both B sub-checks fail; aesthetic is checked first -> degenerate.
    s = RawScore(subject_cos=0.35, off_cos=0.10, aesthetic=0.10, lap_var=1.0)
    g = grade(s, THRESH)
    assert g.reason == "degenerate"


def test_resolve_thresholds_config_and_overrides():
    config = {"qa": {"T_subj": 0.30, "T_margin": 0.05, "T_aes": 0.45, "T_blur": 100.0}}
    # config qa applies
    resolved = lw_gen_qa.resolve_thresholds(config, {})
    assert resolved["T_subj"] == 0.30
    # manifest qa_overrides win over config
    resolved2 = lw_gen_qa.resolve_thresholds(config, {"qa_overrides": {"T_subj": 0.40}})
    assert resolved2["T_subj"] == 0.40
    # missing config still yields a fully-populated dict from defaults
    resolved3 = lw_gen_qa.resolve_thresholds({}, {})
    assert set(resolved3) == {"T_subj", "T_margin", "T_aes", "T_blur"}
    assert resolved3["T_blur"] == 100.0


def _write_manifest(batch_dir, files):
    manifest = {
        "batch_id": "ambessa-splash-20260710000000",
        "subject": "Ambessa",
        "subject_aliases": ["Ambessa"],
        "style": "splash",
        "model": "placeholder.safetensors",
        "clip_model": "ViT-L-14",
        "prompt": "splash art of Ambessa",
        "negative": "text, watermark",
        "candidates": [
            {"file": f, "seed": 1000 + i, "round": 1, "verdict": "PENDING"}
            for i, f in enumerate(files)
        ],
        "promote": {},
    }
    path = os.path.join(batch_dir, "gen_manifest.json")
    with open(path, "w", encoding="utf-8") as fo:
        json.dump(manifest, fo)
    return path


def test_score_batch_writes_sidecars_and_updates_manifest(tmp_path):
    batch = tmp_path / "batch"
    batch.mkdir()
    files = ["cand_00.png", "cand_01.png"]
    for f in files:
        (batch / f).write_bytes(b"not-a-real-png")  # stub scorer never opens them
    manifest_path = _write_manifest(str(batch), files)

    # Injected stub: cand_00 is a clean PASS, cand_01 is a wrong_subject REJECT.
    scores = {
        os.path.join(str(batch), "cand_00.png"):
            RawScore(subject_cos=0.35, off_cos=0.10, aesthetic=0.60, lap_var=500.0),
        os.path.join(str(batch), "cand_01.png"):
            RawScore(subject_cos=0.10, off_cos=0.05, aesthetic=0.01, lap_var=1.0),
    }

    def stub(path):
        return scores[path]

    updated = lw_gen_qa.score_batch(str(batch), scorer=stub, config={})

    verdicts = {c["file"]: c["verdict"] for c in updated["candidates"]}
    reasons = {c["file"]: c["reason"] for c in updated["candidates"]}
    assert verdicts["cand_00.png"] == "PASS"
    assert verdicts["cand_01.png"] == "REJECT"
    assert reasons["cand_01.png"] == "wrong_subject"

    # manifest persisted to disk
    with open(manifest_path, encoding="utf-8") as fo:
        on_disk = json.load(fo)
    assert on_disk["candidates"][0]["verdict"] == "PASS"

    # per-candidate sidecars written
    for f in files:
        sidecar = os.path.join(str(batch), f.replace(".png", ".qa.json"))
        assert os.path.isfile(sidecar)
        with open(sidecar, encoding="utf-8") as fo:
            sc = json.load(fo)
        assert sc["file"] == f
        assert "thresholds" in sc
        assert sc["clip_model"] == "ViT-L-14"


def test_laplacian_variance_numpy_only(tmp_path):
    # A flat image has zero laplacian variance; noise has positive variance.
    from PIL import Image
    import numpy as np

    flat = tmp_path / "flat.png"
    Image.fromarray(np.full((32, 32, 3), 128, dtype=np.uint8)).save(flat)
    assert lw_gen_qa.laplacian_variance(str(flat)) == 0.0

    rng = np.random.default_rng(0)
    noisy = tmp_path / "noisy.png"
    Image.fromarray(rng.integers(0, 256, (32, 32, 3), dtype=np.uint8)).save(noisy)
    assert lw_gen_qa.laplacian_variance(str(noisy)) > 0.0
    # Stronger than import-time: CALLING it must not reach for cv2 either, so
    # the probe runs the call in the clean interpreter before checking.
    assert_import_free(
        "tools.lw_gen_qa", ("cv2",),
        after=f"tools.lw_gen_qa.laplacian_variance({str(noisy)!r})",
    )


# --- M0 (a)/(e): sidecar model + rewritten cand[file] regression locks -----

def _write_manifest_model(batch_dir, candidates, model):
    manifest = {
        "batch_id": "vayne-splash-20260711000000",
        "subject": "Vayne",
        "subject_aliases": ["Vayne"],
        "style": "splash",
        "model": model,
        "clip_model": "ViT-L-14",
        "prompt": "splash art of Vayne",
        "negative": "text, watermark",
        "candidates": candidates,
        "promote": {},
    }
    path = os.path.join(batch_dir, "gen_manifest.json")
    with open(path, "w", encoding="utf-8") as fo:
        json.dump(manifest, fo)
    return path


def test_qa_sidecar_model_from_manifest_not_config(tmp_path):
    # The QA sidecar records the model the batch was GENERATED with (manifest),
    # never whatever model_path the CURRENT config happens to hold. GREEN today;
    # this locks the provenance source so a refactor cannot regress it.
    batch = tmp_path / "batch"
    batch.mkdir()
    (batch / "cand_00.png").write_bytes(b"not-a-real-png")
    _write_manifest_model(
        str(batch),
        [{"file": "cand_00.png", "seed": 1000, "round": 1, "verdict": "PENDING"}],
        model="MANIFEST_MODEL.safetensors")

    scores = {os.path.join(str(batch), "cand_00.png"):
              RawScore(subject_cos=0.35, off_cos=0.10, aesthetic=0.60, lap_var=500.0)}

    def stub(path):
        return scores[path]

    lw_gen_qa.score_batch(str(batch), scorer=stub,
                          config={"model_path": "CONFIG_OTHER.safetensors"})

    with open(os.path.join(str(batch), "cand_00.qa.json"), encoding="utf-8") as fo:
        sc = json.load(fo)
    assert sc["model"] == "MANIFEST_MODEL.safetensors"
    assert sc["model"] != "CONFIG_OTHER.safetensors"


def test_score_batch_scores_rewritten_cand_file(tmp_path):
    # (e) contract: QA scores whatever cand["file"] currently points at (a
    # stage-rewritten name like cand_00_wfix.png), NOT the raw cand_00.png.
    batch = tmp_path / "batch"
    batch.mkdir()
    (batch / "cand_00_wfix.png").write_bytes(b"not-a-real-png")
    _write_manifest_model(
        str(batch),
        [{"file": "cand_00_wfix.png", "seed": 1000, "round": 1,
          "verdict": "PENDING", "stage": "weapon", "provenance": ["cand_00.png"]}],
        model="MANIFEST_MODEL.safetensors")

    seen = []
    # Keyed ONLY on the wfix path: a call on the raw path would KeyError loudly.
    scores = {os.path.join(str(batch), "cand_00_wfix.png"):
              RawScore(subject_cos=0.35, off_cos=0.10, aesthetic=0.60, lap_var=500.0)}

    def stub(path):
        seen.append(os.path.basename(path))
        return scores[path]

    lw_gen_qa.score_batch(str(batch), scorer=stub, config={})

    assert "cand_00_wfix.png" in seen
    assert "cand_00.png" not in seen
    # sidecar is named from the rewritten file, not the raw stem.
    assert os.path.isfile(os.path.join(str(batch), "cand_00_wfix.qa.json"))
    assert not os.path.isfile(os.path.join(str(batch), "cand_00.qa.json"))


def test_score_batch_preserves_stage_and_provenance(tmp_path):
    # (e) contract: scoring updates score fields only; it must leave the
    # stage/provenance bookkeeping untouched.
    batch = tmp_path / "batch"
    batch.mkdir()
    (batch / "cand_00_wfix.png").write_bytes(b"not-a-real-png")
    _write_manifest_model(
        str(batch),
        [{"file": "cand_00_wfix.png", "seed": 1000, "round": 1,
          "verdict": "PENDING", "stage": "weapon", "provenance": ["cand_00.png"]}],
        model="MANIFEST_MODEL.safetensors")

    scores = {os.path.join(str(batch), "cand_00_wfix.png"):
              RawScore(subject_cos=0.35, off_cos=0.10, aesthetic=0.60, lap_var=500.0)}

    def stub(path):
        return scores[path]

    updated = lw_gen_qa.score_batch(str(batch), scorer=stub, config={})
    cand = updated["candidates"][0]
    assert cand["stage"] == "weapon"
    assert cand["provenance"] == ["cand_00.png"]


# --- M1 weapon-region CLIP gate (design_weapon.md sec 6) -------------------
# Mirrors the Stage-A/B QA grade tests: a 4-clause conjunction with a HARD
# reason ordering (offclass -> weak_margin -> mush). weapon_cos is the MEAN
# cosine vs the crossbow positives; weapon_off is the MAX cosine vs distractors
# (so the crossbow is the argmax iff weapon_cos > weapon_off). lap_var here is
# the REGION-local sharpness of the ROI crop (anti-mush; immune to the DoF
# confound that plagues the whole-image blur gate, GEN_RETUNE.md:116-123).
WTHRESH = {"T_weapon": 0.22, "T_wmargin": 0.03, "T_wblur": 150.0}


def test_weapon_clean_pass():
    from tools.lw_gen_qa import WeaponScore, weapon_grade
    s = WeaponScore(weapon_cos=0.30, weapon_off=0.15, lap_var=400.0)
    g = weapon_grade(s, WTHRESH)
    assert g.verdict == "PASS"
    assert g.reason is None
    assert abs(g.margin - 0.15) < 1e-9


def test_weapon_offclass_below_floor():
    # weapon_cos below T_weapon -> offclass even with a positive margin.
    from tools.lw_gen_qa import WeaponScore, weapon_grade
    s = WeaponScore(weapon_cos=0.18, weapon_off=0.10, lap_var=400.0)
    g = weapon_grade(s, WTHRESH)
    assert g.verdict == "REJECT"
    assert g.reason == "weapon_offclass"


def test_weapon_offclass_not_argmax():
    # clears the floor (0.30 >= 0.22) but a distractor scores higher -> offclass,
    # NOT weak_margin (mirrors the QA argmax-over-distractors rule).
    from tools.lw_gen_qa import WeaponScore, weapon_grade
    s = WeaponScore(weapon_cos=0.30, weapon_off=0.42, lap_var=400.0)
    g = weapon_grade(s, WTHRESH)
    assert g.verdict == "REJECT"
    assert g.reason == "weapon_offclass"
    assert g.margin < 0


def test_weapon_weak_margin():
    # argmax + above floor, but margin (0.02) < T_wmargin (0.03) -> weak_margin.
    from tools.lw_gen_qa import WeaponScore, weapon_grade
    s = WeaponScore(weapon_cos=0.30, weapon_off=0.28, lap_var=400.0)
    g = weapon_grade(s, WTHRESH)
    assert g.verdict == "REJECT"
    assert g.reason == "weapon_weak_margin"


def test_weapon_mush_when_clip_ok():
    # CLIP clauses pass; region lap_var below T_wblur -> mush (anti-mush gate).
    from tools.lw_gen_qa import WeaponScore, weapon_grade
    s = WeaponScore(weapon_cos=0.30, weapon_off=0.15, lap_var=80.0)
    g = weapon_grade(s, WTHRESH)
    assert g.verdict == "REJECT"
    assert g.reason == "weapon_mush"


def test_weapon_offclass_precedence_over_mush():
    # fails BOTH the floor and the blur; the CLIP clause is checked first.
    from tools.lw_gen_qa import WeaponScore, weapon_grade
    s = WeaponScore(weapon_cos=0.05, weapon_off=0.02, lap_var=1.0)
    g = weapon_grade(s, WTHRESH)
    assert g.reason == "weapon_offclass"


def test_resolve_weapon_thresholds_config_and_overrides():
    from tools.lw_gen_qa import resolve_weapon_thresholds
    config = {"weapon": {"T_weapon": 0.25, "T_wmargin": 0.04, "T_wblur": 150.0}}
    resolved = resolve_weapon_thresholds(config, {})
    assert resolved["T_weapon"] == 0.25
    # per-batch manifest weapon_overrides win over config (qa_overrides pattern)
    resolved2 = resolve_weapon_thresholds(config, {"weapon_overrides": {"T_weapon": 0.33}})
    assert resolved2["T_weapon"] == 0.33
    # empty config still yields a fully-populated dict from defaults
    resolved3 = resolve_weapon_thresholds({}, {})
    assert set(resolved3) == {"T_weapon", "T_wmargin", "T_wblur"}


def test_weapon_crop_report_shape():
    # The --weapon-crop helper body: score a crop via an injected scorer, emit
    # a flat JSON-able dict (torch stays in the metrics venv; CI uses a stub).
    from tools.lw_gen_qa import WeaponScore, weapon_crop_report

    def stub(path):
        return WeaponScore(weapon_cos=0.31, weapon_off=0.12, lap_var=333.0)

    rep = weapon_crop_report("ignored.png", stub)
    assert rep == {"weapon_cos": 0.31, "weapon_off": 0.12, "lap_var": 333.0}
