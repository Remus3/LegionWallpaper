"""usm-halo-calibration step 1: measure FIDELITY per USM variant.

The 2026-07-30 census (`docs/USM_HALO_CENSUS_2026-07-30.md`) established that our
own unsharp mask manufactures every halo flag, and that usm35 clears them all
while keeping `lap_ratio` above its 1.0 hard floor. What it deliberately did NOT
do is recompute ms_ssim / lpips / dists per variant - so the FIDELITY cost of a
milder mask was unmeasured, and picking a number on halo evidence alone is the
one-axis mistake that already got one gate rejected in this project.

These tests pin the fidelity plumbing. The expensive part (spawning
.venv-metrics per variant) is INJECTED, so the merge logic is testable without a
GPU, a venv, or a corpus.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    sys.path.insert(0, str(ROOT / "tools"))
    spec = importlib.util.spec_from_file_location(
        "lw_usm_halo_probe_fid_under_test", ROOT / "tools" / "lw_usm_halo_probe.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


probe = _load()


def _variants():
    return {
        "usm1.2,70,3": {"usm": [1.2, 70, 3], "halo_pct": 0.0711, "png": "a.png"},
        "usm1.2,35,3": {"usm": [1.2, 35, 3], "halo_pct": 0.0301, "png": "b.png"},
        "no_usm": {"usm": None, "halo_pct": 0.0041, "png": "c.png"},
    }


def _runner(calls):
    def run(out_png, source_png):
        calls.append((out_png, source_png))
        return {"ssim": 0.99, "ms_ssim": 0.998, "lpips": 0.031, "dists": 0.024,
                "common_scale": [3840, 2160], "capped": True,
                "native_scale": [6500, 3660]}
    return run


def test_every_variant_gets_its_own_fidelity_measurement():
    calls = []
    out = probe.attach_fidelity(_variants(), "src.png", _runner(calls))
    assert len(calls) == 3
    assert {c[1] for c in calls} == {"src.png"}
    assert {c[0] for c in calls} == {"a.png", "b.png", "c.png"}
    for v in out.values():
        assert v["fidelity"]["ms_ssim"] == 0.998


def test_fidelity_keeps_only_the_fields_a_verdict_can_use():
    """Deliberately narrow. `capped` + `common_scale` ride along because ADR-007
    says a capped value is NOT interchangeable with a native one - conflating
    the two regimes across variants would be the same error a second time."""
    out = probe.attach_fidelity(_variants(), "src.png", _runner([]))
    got = set(out["no_usm"]["fidelity"])
    assert got == {"ssim", "ms_ssim", "lpips", "dists", "common_scale",
                   "capped", "native_scale"}


def test_the_halo_numbers_survive_the_merge():
    out = probe.attach_fidelity(_variants(), "src.png", _runner([]))
    assert out["usm1.2,70,3"]["halo_pct"] == 0.0711
    assert out["no_usm"]["usm"] is None


def test_a_failed_measurement_is_recorded_not_swallowed():
    """A missing number must never read as a good one. One variant failing must
    not kill the census either - that is 16 slugs of GPU time."""
    def boom(out_png, source_png):
        if out_png == "b.png":
            raise RuntimeError("fr_metrics died")
        return {"ms_ssim": 0.9}
    out = probe.attach_fidelity(_variants(), "src.png", boom)
    assert out["usm1.2,35,3"]["fidelity"] is None
    assert "fr_metrics died" in out["usm1.2,35,3"]["fidelity_error"]
    assert out["no_usm"]["fidelity"]["ms_ssim"] == 0.9


def test_attach_fidelity_does_not_mutate_its_input():
    src = _variants()
    probe.attach_fidelity(src, "s.png", _runner([]))
    assert "fidelity" not in src["no_usm"]


# ---- fidelity_summary: what the decision is actually read off -------------

def _rows():
    return [
        {"slug": "a", "status": "ok", "variants": {
            "usm1.2,70,3": {"fidelity": {"ms_ssim": 0.990, "lpips": 0.040,
                                         "dists": 0.030}},
            "usm1.2,35,3": {"fidelity": {"ms_ssim": 0.995, "lpips": 0.030,
                                         "dists": 0.020}}}},
        {"slug": "b", "status": "ok", "variants": {
            "usm1.2,70,3": {"fidelity": {"ms_ssim": 0.980, "lpips": 0.060,
                                         "dists": 0.050}},
            "usm1.2,35,3": {"fidelity": {"ms_ssim": 0.985, "lpips": 0.050,
                                         "dists": 0.040}}}},
        {"slug": "c", "status": "error"},
    ]


def test_fidelity_summary_reports_worst_case_not_just_the_mean():
    """A mean hides the one slug a milder mask ruins. The gate is per-image, so
    the decision has to be readable off the worst case."""
    s = probe.fidelity_summary(_rows())
    assert s["usm1.2,35,3"]["measured"] == 2
    assert s["usm1.2,35,3"]["ms_ssim"]["min"] == 0.985
    assert s["usm1.2,35,3"]["lpips"]["max"] == 0.050
    assert s["usm1.2,35,3"]["dists"]["max"] == 0.040


def test_fidelity_summary_skips_rows_with_no_measurement():
    s = probe.fidelity_summary(_rows())
    assert all(v["measured"] == 2 for v in s.values())


def test_fidelity_summary_is_empty_when_nothing_was_measured():
    assert probe.fidelity_summary([{"slug": "a", "status": "ok",
                                    "variants": {"x": {"fidelity": None}}}]) == {}
