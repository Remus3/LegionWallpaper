"""ADR-007: the FR common-scale pixel budget is a ratified decision.

`MAX_COMMON_PIXELS` sets the G1 measurement BASIS corpus-wide - it decides the
resolution at which every source-vs-output comparison happens. It was shipped
unratified (LEDGER 32) and ratified by the operator 2026-08-02.

These tests exist so the constant cannot move without someone noticing. A
threshold can be retuned on evidence; a measurement basis cannot be retuned
quietly, because every recorded number in the corpus was taken against it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR = ROOT / "docs" / "adr" / "ADR-007-fr-common-scale-pixel-budget.md"


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "lw_g1_gate_budget_under_test", ROOT / "tools" / "lw_g1_gate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


g1 = _load_gate()


def test_budget_is_the_ratified_value():
    assert g1.MAX_COMMON_PIXELS == 3840 * 2160


def test_the_adr_exists_and_is_accepted():
    """A ratified constant with no ADR behind it is just a constant again."""
    txt = ADR.read_text(encoding="utf-8")
    assert "**Status:** Accepted" in txt
    assert "3840x2160" in txt


def test_budget_stays_under_the_proven_ceiling():
    """4096x2306 (9.4 MPix) is the largest common scale that ever completed
    corpus-wide. A budget set AT the ceiling has no headroom; ADR-007 takes it
    below deliberately."""
    assert g1.MAX_COMMON_PIXELS < 4096 * 2306


def test_a_1440p_pair_is_never_capped():
    """The cap governs the SOURCE-vs-OUTPUT comparison scale, NOT the 2560x1440
    deliverable. Conflating the two is the misreading ADR-007 was written to
    correct, so pin it: the output size passes through untouched."""
    assert g1.common_scale_for(2560, 1440) == (2560, 1440, False)


def test_a_native_4k_source_is_never_capped():
    """26 corpus images are natively 3840x2160. The budget lands exactly there so
    the cap is a no-op for them and their measurements stay comparable."""
    assert g1.common_scale_for(3840, 2160) == (3840, 2160, False)


def test_the_largest_real_source_is_capped_and_keeps_its_aspect():
    """6500x3660 is the largest source in this corpus."""
    w, h, capped = g1.common_scale_for(6500, 3660)
    assert capped is True
    assert w * h <= g1.MAX_COMMON_PIXELS
    assert abs((w / h) - (6500 / 3660)) < 0.01


def test_the_cap_only_ever_downscales_the_reference():
    """AUDIT_GATES 1.2 caveat 2: upscaling the reference manufactures a blurry
    reference and biases every metric toward approving soft output. The cap must
    never do that, at any input size."""
    for src in [(2560, 1440), (3840, 2160), (4096, 2306), (6500, 3660),
                (7680, 4320), (4096, 4096), (1024, 576)]:
        w, h, _ = g1.common_scale_for(*src)
        assert w <= src[0] and h <= src[1]


def test_the_budget_is_on_area_not_side_length():
    """A square 4096x4096 is 16.8 MPix and must be capped even though a max-side
    rule would wave it through - the allocation that OOMs scales with area."""
    assert g1.common_scale_for(4096, 4096)[2] is True
