"""gemini-removal: the director + auditor roles behind a backend seam.

Gemini was never a config flag in LW - it was structurally the DIRECTOR (it
AUTHORS each cycle's directive) and the AUDITOR (it scores the cycle's diff).
Removing it therefore means replacing what authors the directive, not switching
a backend behind a key that already exists.

These tests pin the reversible half: a `*_backend` seam whose default is
`claude`, with the Gemini call path left intact and reachable as the rollback.
The rollback is two config keys, exactly as `channel` is one for the executor.

Nothing here spawns a real model call - `oracle()` is exercised against injected
fakes, because the point of the seam is that the dispatch is testable without a
vendor.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_controller():
    spec = importlib.util.spec_from_file_location(
        "lw_loop_controller_under_test", ROOT / "ops" / "loop" / "loop_controller.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


lc = _load_controller()


# ---- the seam itself -------------------------------------------------------

def test_backend_defaults_to_claude_when_unconfigured():
    """The DEFAULT is the whole point: an un-keyed config must not reach Gemini."""
    assert lc.oracle_backend({}, "director") == "claude"
    assert lc.oracle_backend({}, "auditor") == "claude"


def test_per_role_key_wins_over_the_shared_key():
    cfg = {"oracle_backend": "claude", "auditor_backend": "gemini"}
    assert lc.oracle_backend(cfg, "director") == "claude"
    assert lc.oracle_backend(cfg, "auditor") == "gemini"


def test_shared_key_sets_both_roles():
    cfg = {"oracle_backend": "gemini"}
    assert lc.oracle_backend(cfg, "director") == "gemini"
    assert lc.oracle_backend(cfg, "auditor") == "gemini"


def test_backend_is_case_and_whitespace_tolerant():
    assert lc.oracle_backend({"director_backend": " Gemini "}, "director") == "gemini"


def test_unknown_backend_falls_back_to_claude_rather_than_crashing():
    """An unattended run must not die on a typo, and must not silently bill the
    vendor being removed. Unknown -> claude, the safe default."""
    assert lc.oracle_backend({"director_backend": "grok"}, "director") == "claude"


# ---- the live config is flipped -------------------------------------------

def test_shipped_config_routes_both_roles_to_claude():
    import json
    cfg = json.loads((ROOT / "ops" / "loop" / "config.json").read_text(encoding="utf-8"))
    assert lc.oracle_backend(cfg, "director") == "claude"
    assert lc.oracle_backend(cfg, "auditor") == "claude"


# ---- the claude oracle argv ------------------------------------------------

def test_claude_oracle_argv_is_read_only():
    """The director and auditor READ the tree and emit text. They must never get
    the executor's bypassPermissions - that channel exists to let the executor
    COMMIT, and an adjudicator that can write is not an adjudicator."""
    argv = lc.claude_oracle_argv("Audit.", {"repo_root": "C:\\LegionWallpaper"})
    assert "bypassPermissions" not in argv
    assert argv[argv.index("--permission-mode") + 1] == "plan"
    assert "-p" in argv
    assert argv[argv.index("--add-dir") + 1] == "C:\\LegionWallpaper"


def test_claude_oracle_argv_carries_the_instruction_and_model():
    argv = lc.claude_oracle_argv("Output ONLY the directive.",
                                 {"oracle_model": "claude-opus-5"})
    assert argv[argv.index("--model") + 1] == "claude-opus-5"
    assert any("Output ONLY the directive." in a for a in argv)


def test_claude_oracle_argv_accepts_a_list_command_for_test_shims():
    argv = lc.claude_oracle_argv("x", {"claude_cmd": ["python", "shim.py"]})
    assert argv[:2] == ["python", "shim.py"]


# ---- dispatch --------------------------------------------------------------

def test_oracle_routes_to_gemini_when_the_backend_says_so(monkeypatch):
    seen = {}
    monkeypatch.setattr(lc, "CFG", {"director_backend": "gemini"})
    monkeypatch.setattr(lc, "gemini", lambda b, i: (seen.update(gemini=(b, i)), "G")[1])
    monkeypatch.setattr(lc, "claude_oracle", lambda b, i: (seen.update(claude=(b, i)), "C")[1])
    assert lc.oracle("body", "inst", role="director") == "G"
    assert "claude" not in seen


def test_oracle_routes_to_claude_by_default(monkeypatch):
    seen = {}
    monkeypatch.setattr(lc, "CFG", {})
    monkeypatch.setattr(lc, "gemini", lambda b, i: (seen.update(gemini=1), "G")[1])
    monkeypatch.setattr(lc, "claude_oracle", lambda b, i: (seen.update(claude=1), "C")[1])
    assert lc.oracle("body", "inst", role="director") == "C"
    assert "gemini" not in seen


def test_claude_path_never_accrues_gemini_spend(monkeypatch):
    """ceiling_usd is a REAL rail for a metered vendor. Once the claude backend is
    the default it must stay at zero, or the loop stops itself on a phantom bill."""
    monkeypatch.setattr(lc, "CFG", {})
    monkeypatch.setattr(lc, "GEMINI_USD", 0.0)
    monkeypatch.setattr(lc, "claude_oracle", lambda b, i: "ok")
    lc.oracle("body", "inst", role="auditor")
    assert lc.GEMINI_USD == 0.0


def test_director_and_auditor_go_through_the_oracle_seam():
    """Regression guard: the two roles must not call gemini() directly again."""
    src = (ROOT / "ops" / "loop" / "loop_controller.py").read_text(encoding="utf-8")
    body = src[src.index("def director("):src.index("# ---- budget meter")]
    assert "gemini(" not in body, "director/auditor must dispatch via oracle()"
    assert "oracle(" in body


# ---- the rollback path stays reachable ------------------------------------

def test_gemini_backend_is_not_deleted():
    """The removal is reversible ON PURPOSE: flip two keys and the vendor is back.
    A big-bang deletion is the version that cannot be undone at 3am."""
    assert callable(getattr(lc, "gemini", None))
    assert callable(getattr(lc, "_gemini_call", None))


def test_gemini_mutex_still_exists_for_the_cross_repo_contract():
    """ops/loop/winmutex.py is byte-identical-by-contract with Riot Commander and
    GEMINI_MUTEX still has a live consumer there. Deleting it needs a three-way
    re-pin, not a sweep."""
    assert lc.winmutex.GEMINI_MUTEX == "Global\\LWRC_GEMINI"


def test_oracle_role_must_be_known():
    with pytest.raises(ValueError):
        lc.oracle("body", "inst", role="nonsense")
