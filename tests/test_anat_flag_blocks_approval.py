"""ADR-008: an anatomy vision reviewer may FLAG, never REJECT - and the flag
BLOCKS a non-operator approval.

Two mechanisms, and they are deliberately separate:

  1. CLAMP - a vision audit can never carry a FAIL/REJECT verdict. It is coerced
     to FLAG at the annotate boundary, so no future reviewer can demote an image
     by writing a verdict, whatever its prompt says.
  2. BLOCK - an unresolved anatomy flag REFUSES an approval by any actor that is
     not the operator. That is the half that gives FLAG-only its safety property:
     nothing ships past an anatomy problem unseen, without ever letting an
     irreproducible judge spend a pass that `clean-retry-degrades` measured is
     NOT neutral.

The operator can always approve - that path already records itself as an
`override` and refusing it would wedge the operator's own workflow.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "lw_pipeline_anat_under_test", ROOT / "tools" / "lw_pipeline.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


lp = _load()


# ---- 1. the clamp: a vision reviewer may FLAG, never REJECT ---------------

def test_a_vision_reject_is_clamped_to_flag():
    out = lp.clamp_vision_audit({"gate": "vision-anat", "verdict": "REJECT",
                                 "reasons": ["anat_head_spine"]})
    assert out["verdict"] == "FLAG"
    assert out["clamped_from"] == "REJECT"


def test_a_vision_fail_is_clamped_too():
    out = lp.clamp_vision_audit({"gate": "vision-anat", "verdict": "FAIL"})
    assert out["verdict"] == "FLAG"
    assert out["clamped_from"] == "FAIL"


def test_a_vision_pass_is_left_alone_and_unmarked():
    out = lp.clamp_vision_audit({"gate": "vision-anat", "verdict": "PASS"})
    assert out["verdict"] == "PASS"
    assert "clamped_from" not in out


def test_a_vision_flag_is_left_alone_and_unmarked():
    out = lp.clamp_vision_audit({"gate": "vision-anat", "verdict": "FLAG"})
    assert out["verdict"] == "FLAG"
    assert "clamped_from" not in out


def test_a_metric_gate_keeps_its_fail():
    """The clamp is scoped to VISION gates. G1 is reproducible to 4dp and its
    FAIL is a real hard floor - clamping that would silently disarm the ladder."""
    out = lp.clamp_vision_audit({"gate": "G1", "verdict": "FAIL",
                                 "reasons": ["lap_ratio"]})
    assert out["verdict"] == "FAIL"
    assert "clamped_from" not in out


def test_the_clamp_does_not_mutate_its_input():
    src = {"gate": "vision-anat", "verdict": "REJECT"}
    lp.clamp_vision_audit(src)
    assert src["verdict"] == "REJECT"


def test_a_non_audit_value_passes_through_untouched():
    """`annotate --metrics` accepts operator JSON. A list or a bare string must
    not crash the clamp on its way through."""
    assert lp.clamp_vision_audit(None) is None
    assert lp.clamp_vision_audit([1, 2]) == [1, 2]
    assert lp.clamp_vision_audit({}) == {}


# ---- 2. blocking flags -----------------------------------------------------

def test_anat_reasons_are_blocking():
    assert lp.blocking_flags(["anat_head_spine"]) == ["anat_head_spine"]


def test_ordinary_metric_reasons_are_not_blocking():
    assert lp.blocking_flags(["halo_pct", "band_delta", "lap_ratio"]) == []


def test_blocking_flags_are_deduped_and_sorted():
    got = lp.blocking_flags(["anat_pose", "halo_pct", "anat_head_spine", "anat_pose"])
    assert got == ["anat_head_spine", "anat_pose"]


def test_blocking_flags_tolerates_junk():
    assert lp.blocking_flags(None) == []
    assert lp.blocking_flags(["", None, 7]) == []


# ---- 3. the approval record carries them ----------------------------------

def _man(reasons, verdict="FLAG"):
    return {"transitions": [
        {"op": "INTAKE"},
        {"op": "ANNOTATE", "audit": {"gate": "vision-anat", "verdict": verdict,
                                     "reasons": reasons}},
    ]}


def test_approval_record_surfaces_the_blocking_flag():
    rec = lp._approval_record(_man(["anat_head_spine"]), "first")
    assert rec["blocking_flags"] == ["anat_head_spine"]
    assert rec["gate_check"] == "override"


def test_approval_record_is_empty_when_nothing_blocks():
    rec = lp._approval_record(_man(["halo_pct"]), "first")
    assert rec["blocking_flags"] == []


def test_a_legacy_no_audit_record_blocks_nothing():
    """12 approved images carry no G1 audit at all. A missing verdict is NOT a
    blocking flag - it is its own outcome, and inventing a block for it would
    strand them."""
    rec = lp._approval_record({"transitions": [{"op": "INTAKE"}]}, "first")
    assert rec["gate_check"] == "no_audit"
    assert rec["blocking_flags"] == []


# ---- 4. the block itself ---------------------------------------------------

def test_a_tool_actor_is_refused_while_a_flag_is_unresolved():
    with pytest.raises(lp.PipelineError) as e:
        lp.assert_approval_allowed("p08e8", {"blocking_flags": ["anat_head_spine"]},
                                   actor="tool:auto-approve")
    assert e.value.code == 3
    assert "anat_head_spine" in str(e.value)


def test_the_operator_is_never_refused():
    """Approving over a flag is an operator judgement and stays allowed; the
    approval record already writes it down as an override."""
    lp.assert_approval_allowed("p08e8", {"blocking_flags": ["anat_head_spine"]},
                               actor="operator")


def test_a_tool_actor_is_allowed_when_nothing_blocks():
    lp.assert_approval_allowed("p08e8", {"blocking_flags": []}, actor="tool:auto-approve")


def test_an_unknown_actor_is_treated_as_not_the_operator():
    """Fail closed. An actor string nobody recognises must not inherit operator
    authority just because it is not on a list."""
    with pytest.raises(lp.PipelineError):
        lp.assert_approval_allowed("x", {"blocking_flags": ["anat_pose"]}, actor="")
