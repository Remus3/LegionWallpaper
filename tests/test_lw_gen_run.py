"""CI-safe tests for tools/lw_gen_run.py (torch-free, no real subprocess).

Proves: the module imports under base python (lazy torch/diffusers), the RC-live
hard gate refuses on a flag file and on a League process, the aspect guard
refuses non-16:9, and brief/CLI precedence resolves correctly. NO torch is
imported and NO real subprocess runs - generation is never reached.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_gen_run as gr  # noqa: E402

from _import_probe import assert_import_free  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers.
# ---------------------------------------------------------------------------
def _config():
    return {
        "model_path": "tools/models/PLACEHOLDER.safetensors",
        "clip_model": "ViT-L-14",
        "sampler": {"name": "dpmpp_2m_sde", "scheduler": "karras", "steps": 30, "cfg": 5.5},
        "resolution": {"16:9": [1344, 768]},
        "gen": {"offload": True, "tiled_vae": True, "attention": "sdpa", "fast_path": False},
        "env": {"TORCH_CUDA_ARCH_LIST": "12.0", "CUDA_MODULE_LOADING": "LAZY"},
        "top_k": 3,
        "venvs": {"gen": ".venv-gen", "metrics": ".venv-metrics"},
        "rc_live": {
            "mode": "refuse",
            "flag_path": "ops/runtime/rc_live.flag",
            "processes": ["LeagueClient.exe", "LeagueClientUx.exe",
                          "League of Legends.exe", "RiotClientServices.exe"],
        },
    }


def _styles():
    return {
        "splash": {
            "positive": "splash art of {subject}, painterly, {prompt_extra}",
            "negative": "anime, blurry, {negative_extra}",
            "sampler": {"name": "dpmpp_2m_sde", "scheduler": "karras", "steps": 30, "cfg": 5.5},
        },
        "portrait": {
            "positive": "portrait of {subject}, {prompt_extra}",
            "negative": "anime, {negative_extra}",
            "sampler": {"name": "dpmpp_2m_sde", "scheduler": "karras", "steps": 32, "cfg": 5.5},
        },
    }


def _cli(**over):
    base = {
        "subject": None, "style": None, "n": None, "aspect": None,
        "prompt_extra": None, "negative_extra": None, "seed": None,
        "max_regen_rounds": None, "top_k": None,
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Import safety (lazy torch proof).
# ---------------------------------------------------------------------------
def test_import_is_torch_free():
    # Importing the module must not pull torch/diffusers into sys.modules.
    assert_import_free("tools.lw_gen_run", ("torch", "diffusers"))
    # The lazy loader references them only inside the function body.
    assert callable(gr._load_pipeline)


# ---------------------------------------------------------------------------
# RC-live hard gate.
# ---------------------------------------------------------------------------
def test_rc_live_refuses_on_flag_file(tmp_path):
    flag = tmp_path / "rc_live.flag"
    flag.write_text("live\n", encoding="utf-8")
    status = gr.rc_live_check(_config(), process_lister=lambda: [], flag_path=str(flag))
    assert status.state == gr.RC_LIVE
    ok, msg = gr.rc_live_gate(status)
    assert ok is False
    assert "live" in msg.lower()


def test_rc_live_refuses_on_league_process():
    lister = lambda: ["explorer.exe", "LeagueClient.exe", "chrome.exe"]  # noqa: E731
    status = gr.rc_live_check(_config(), process_lister=lister, flag_path=None)
    assert status.state == gr.RC_LIVE
    ok, _ = gr.rc_live_gate(status)
    assert ok is False


def test_rc_live_clear_when_no_signal():
    status = gr.rc_live_check(_config(), process_lister=lambda: ["explorer.exe"], flag_path=None)
    assert status.state == gr.RC_CLEAR
    ok, msg = gr.rc_live_gate(status)
    assert ok is True
    assert msg == ""


def test_rc_live_unknown_refuses_then_allow_when_unsure():
    status = gr.rc_live_check(_config(), process_lister=lambda: None, flag_path=None)
    assert status.state == gr.RC_UNKNOWN
    ok_default, _ = gr.rc_live_gate(status)
    assert ok_default is False
    ok_allow, _ = gr.rc_live_gate(status, allow_when_unsure=True)
    assert ok_allow is True
    ok_force, msg_force = gr.rc_live_gate(status, force=True)
    assert ok_force is True


def test_rc_live_force_overrides_live():
    status = gr.rc_live_check(_config(), process_lister=lambda: ["LeagueClient.exe"])
    ok, msg = gr.rc_live_gate(status, force=True)
    assert ok is True
    assert "force" in msg.lower()


def test_rc_live_broken_lister_is_unknown_not_crash():
    def boom():
        raise OSError("tasklist exploded")
    status = gr.rc_live_check(_config(), process_lister=boom, flag_path=None)
    assert status.state == gr.RC_UNKNOWN


# ---------------------------------------------------------------------------
# Aspect guard.
# ---------------------------------------------------------------------------
def test_aspect_guard_accepts_16_9():
    assert gr.resolve_resolution("16:9", _config()) == (1344, 768)


def test_aspect_guard_refuses_ultrawide():
    with pytest.raises(gr.GenError) as ei:
        gr.resolve_resolution("21:9", _config())
    assert ei.value.code == 2


# ---------------------------------------------------------------------------
# Plan resolution: CLI overrides brief overrides defaults.
# ---------------------------------------------------------------------------
def test_plan_defaults_from_subject_only():
    plan = gr.resolve_plan(_cli(subject="Ambessa"), _config(), _styles())
    assert plan["subject"] == "Ambessa"
    assert plan["style"] == "splash"
    assert plan["n"] == 4
    assert plan["aspect"] == "16:9"
    assert plan["top_k"] == 3
    assert plan["max_regen_rounds"] == 1
    assert plan["subject_aliases"] == ["Ambessa"]


def test_plan_brief_supplies_defaults():
    brief = {"subject": "Ambessa", "style": "portrait", "n": 6,
             "subject_aliases": ["Ambessa", "Noxus general"], "prompt_extra": "storm sky"}
    plan = gr.resolve_plan(_cli(), _config(), _styles(), brief)
    assert plan["subject"] == "Ambessa"
    assert plan["style"] == "portrait"
    assert plan["n"] == 6
    assert plan["prompt_extra"] == "storm sky"
    assert plan["subject_aliases"] == ["Ambessa", "Noxus general"]


def test_plan_cli_overrides_brief():
    brief = {"subject": "Ambessa", "style": "portrait", "n": 6}
    plan = gr.resolve_plan(_cli(subject="Darius", style="splash", n=2),
                           _config(), _styles(), brief)
    assert plan["subject"] == "Darius"
    assert plan["style"] == "splash"
    assert plan["n"] == 2


def test_plan_missing_subject_raises():
    with pytest.raises(gr.GenError) as ei:
        gr.resolve_plan(_cli(), _config(), _styles())
    assert ei.value.code == 2


def test_plan_unknown_style_raises():
    with pytest.raises(gr.GenError):
        gr.resolve_plan(_cli(subject="X", style="nope"), _config(), _styles())


# ---------------------------------------------------------------------------
# Prompt build.
# ---------------------------------------------------------------------------
def test_build_prompts_fills_slots():
    pos, neg = gr.build_prompts(_styles()["splash"], "Ambessa", "storm sky", "no text")
    assert "Ambessa" in pos
    assert "storm sky" in pos
    assert "no text" in neg
    assert "{" not in pos and "{" not in neg


# ---------------------------------------------------------------------------
# Provisioning + brief loading.
# ---------------------------------------------------------------------------
def test_check_provisioned_refuses_when_absent(tmp_path):
    ok, msg = gr.check_provisioned(_config(), root=str(tmp_path))
    assert ok is False
    assert "not provisioned" in msg


def test_load_brief_reads_json(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"subject": "Ambessa", "n": 3}), encoding="utf-8")
    brief = gr.load_brief(str(p))
    assert brief["subject"] == "Ambessa"
    assert brief["n"] == 3


def test_load_brief_empty_path_is_empty_dict():
    assert gr.load_brief(None) == {}


# ---------------------------------------------------------------------------
# End-to-end run stops at RC-live / provisioning without ever running gen.
# ---------------------------------------------------------------------------
def test_run_refuses_when_rc_live_via_flag(tmp_path, monkeypatch):
    cfg = _config()
    # Root ROOT at tmp_path so the resolved flag path lands under our temp dir.
    monkeypatch.setattr(gr, "ROOT", str(tmp_path))
    os.makedirs(tmp_path / "ops" / "runtime", exist_ok=True)
    (tmp_path / "ops" / "runtime" / "rc_live.flag").write_text("live", encoding="utf-8")

    args = gr.build_parser().parse_args(["--subject", "Ambessa"])
    # Guard: if generation were reached, this would fail the test loudly.
    monkeypatch.setattr(gr, "_load_pipeline", lambda *a, **k: pytest.fail("gen reached"))
    with pytest.raises(gr.GenError) as ei:
        gr.run(args, config=cfg, styles=_styles())
    assert ei.value.code == 3


def test_run_refuses_when_not_provisioned(tmp_path, monkeypatch):
    cfg = _config()
    monkeypatch.setattr(gr, "ROOT", str(tmp_path))  # no venv/model under tmp
    args = gr.build_parser().parse_args(["--subject", "Ambessa"])
    monkeypatch.setattr(gr, "rc_live_check",
                        lambda *a, **k: gr.RcStatus(gr.RC_CLEAR, "test", "clear"))
    monkeypatch.setattr(gr, "_load_pipeline", lambda *a, **k: pytest.fail("gen reached"))
    with pytest.raises(gr.GenError) as ei:
        gr.run(args, config=cfg, styles=_styles())
    assert ei.value.code == 4


def test_run_aspect_guard_refuses(monkeypatch):
    args = gr.build_parser().parse_args(["--subject", "Ambessa", "--aspect", "21:9"])
    monkeypatch.setattr(gr, "_load_pipeline", lambda *a, **k: pytest.fail("gen reached"))
    with pytest.raises(gr.GenError) as ei:
        gr.run(args, config=_config(), styles=_styles())
    assert ei.value.code == 2


def test_main_returns_gen_error_code(monkeypatch):
    # main() catches GenError and returns the exit code (never a raw traceback).
    monkeypatch.setattr(gr, "run", lambda *a, **k: (_ for _ in ()).throw(gr.GenError("x", code=3)))
    assert gr.main(["--subject", "Ambessa"]) == 3


# ---------------------------------------------------------------------------
# M0 (e): manifest cand[file] contract - stage helpers (pure, torch-free).
# ---------------------------------------------------------------------------
def test_new_candidate_record_has_stage_and_provenance():
    rec = gr.new_candidate_record("cand_00.png", 1234, 0)
    # Existing candidate shape is preserved verbatim.
    assert rec["file"] == "cand_00.png"
    assert rec["seed"] == 1234
    assert rec["round"] == 0
    assert rec["verdict"] == "PENDING"
    assert rec["subject_cos"] is None
    # New (e) fields, appended at the END.
    assert rec["stage"] == "raw"
    assert rec["provenance"] == ["cand_00.png"]


def test_advance_cand_file_rewrites_and_records():
    cand = {"file": "cand_00.png", "stage": "raw", "provenance": ["cand_00.png"]}
    gr.advance_cand_file(cand, "cand_00_wfix.png", "weapon")
    assert cand["file"] == "cand_00_wfix.png"
    assert cand["stage"] == "weapon"
    assert "cand_00.png" in cand["provenance"]


def test_advance_cand_file_tolerates_legacy_record():
    # Records predating (e) have no stage/provenance; advance must not KeyError.
    cand = {"file": "cand_00.png"}
    gr.advance_cand_file(cand, "cand_00_wfix.png", "weapon")
    assert cand["file"] == "cand_00_wfix.png"
    assert cand["stage"] == "weapon"
    assert "cand_00.png" in cand["provenance"]


def test_stage_filename_chain():
    assert gr.stage_filename("cand_00.png", "wfix") == "cand_00_wfix.png"
    assert gr.stage_filename("cand_00.png", "repair") == "cand_00_repair.png"
    assert gr.stage_filename("cand_00.png", "finish") == "cand_00_finish.png"
    # No accretion: a rewrite from an already-staged file derives from the RAW
    # stem, never cand_00_wfix_repair.png.
    assert gr.stage_filename("cand_00_wfix.png", "repair") == "cand_00_repair.png"
    assert gr.stage_filename("cand_00_repair.png", "finish") == "cand_00_finish.png"
