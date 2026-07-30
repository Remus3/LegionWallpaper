"""Tests for tools/lw_usm_halo_probe.py - the USM-vs-upscaler halo probe.

CI constraint (read before editing imports): these run on system python 3.14 and
CI 3.12 with ONLY PIL + numpy + stdlib. No torch, no spandrel, no GPU, no live
corpus. Everything here works on synthetic images built in-process.

The one live-model path (worker_render's spandrel branch) is capability-gated on
the ABSENCE of the upscale venv + model file, never on the thing under test - and
the geometry half of that worker is exercised through the downscale-only branch,
which needs no model at all.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_usm_halo_probe as probe  # noqa: E402
from lw_upscale import TARGET, USM_DEFAULT, _finish  # noqa: E402


# --------------------------------------------------------------------------
# synthetic fixtures
# --------------------------------------------------------------------------
def _step_edge(w, h, period=64):
    """Hard vertical bar pattern - the shape an unsharp mask rings hardest on."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    xs = (np.arange(w) // period) % 2 == 0
    arr[:, xs, :] = 235
    arr[:, ~xs, :] = 20
    return Image.fromarray(arr, mode="RGB")


def _smooth_ramp(w, h):
    """A gentle horizontal ramp - almost no strong edges to ring."""
    xs = np.linspace(0, 255, w, dtype=np.float64)
    arr = np.repeat(xs[None, :], h, axis=0)
    return Image.fromarray(np.stack([arr] * 3, axis=2).astype(np.uint8), "RGB")


# --------------------------------------------------------------------------
# parse_usm_spec / variant_label
# --------------------------------------------------------------------------
def test_parse_usm_spec_triple():
    assert probe.parse_usm_spec("1.2,70,3") == (1.2, 70, 3)


def test_parse_usm_spec_none_is_condition_b():
    assert probe.parse_usm_spec("none") is None
    assert probe.parse_usm_spec("  NONE ") is None


@pytest.mark.parametrize("bad", ["1.2,70", "1.2,70,3,4", ""])
def test_parse_usm_spec_rejects_wrong_arity(bad):
    with pytest.raises(ValueError):
        probe.parse_usm_spec(bad)


def test_parse_usm_spec_rejects_non_numeric():
    with pytest.raises(ValueError):
        probe.parse_usm_spec("a,b,c")


def test_variant_label_is_stable_and_distinct():
    assert probe.variant_label(None) == "no_usm"
    assert probe.variant_label((1.2, 70, 3)) == "usm_1.2_70_3"
    assert probe.variant_label((1.2, 35, 3)) == "usm_1.2_35_3"
    # Same triple must always produce the same key or the census cannot be joined.
    assert probe.variant_label((1.2, 70, 3)) == probe.variant_label((1.2, 70.0, 3.0))


# --------------------------------------------------------------------------
# latest_g1_audit - the top-level-read trap
# --------------------------------------------------------------------------
def _manifest(*audits):
    return {"transitions": [{"audit": a} for a in audits]}


def test_latest_g1_audit_reads_transitions_not_top_level():
    manifest = _manifest({"gate": "G1", "verdict": "FLAG"})
    # A decoy at top level must be ignored: the real audit lives in transitions.
    manifest["audit"] = {"gate": "G1", "verdict": "PASS"}
    assert probe.latest_g1_audit(manifest)["verdict"] == "FLAG"


def test_latest_g1_audit_takes_the_newest():
    manifest = _manifest(
        {"gate": "G1", "verdict": "FAIL"},
        {"hold": "aspect_crop_heavy"},
        {"gate": "G1", "verdict": "PASS"},
    )
    assert probe.latest_g1_audit(manifest)["verdict"] == "PASS"


@pytest.mark.parametrize(
    "manifest",
    [{}, {"transitions": []}, {"transitions": [{"audit": {"hold": "x"}}]}, None, "x"],
)
def test_latest_g1_audit_missing_returns_none(manifest):
    assert probe.latest_g1_audit(manifest) is None


def test_shipped_halo_extracts_metric():
    manifest = _manifest({"gate": "G1", "verdict": "FLAG",
                          "metrics": {"halo_pct": 0.1157}})
    assert probe.shipped_halo(manifest) == pytest.approx(0.1157)


def test_shipped_halo_none_when_metric_missing_or_non_numeric():
    assert probe.shipped_halo(_manifest({"gate": "G1"})) is None
    assert probe.shipped_halo(
        _manifest({"gate": "G1", "metrics": {"halo_pct": "ERR boom"}})
    ) is None
    assert probe.shipped_halo({}) is None


# --------------------------------------------------------------------------
# finish_variant - condition A must BE the shipped path
# --------------------------------------------------------------------------
def test_finish_variant_with_usm_is_byte_identical_to_shipped_finish():
    raw = _step_edge(3200, 1800)
    mine = probe.finish_variant(raw, usm=USM_DEFAULT)
    shipped = _finish(raw, usm=USM_DEFAULT)
    assert mine.size == shipped.size == TARGET
    assert mine.tobytes() == shipped.tobytes()


def test_finish_variant_without_usm_is_the_bare_lanczos_downscale():
    raw = _step_edge(3200, 1800)
    mine = probe.finish_variant(raw, usm=None)
    bare = raw.convert("RGB").resize(TARGET, Image.LANCZOS)
    assert mine.size == TARGET
    assert mine.tobytes() == bare.tobytes()


def test_finish_variant_ab_differ_only_by_the_mask():
    raw = _step_edge(3200, 1800)
    b = probe.finish_variant(raw, usm=None)
    a = probe.finish_variant(raw, usm=USM_DEFAULT)
    radius, percent, threshold = USM_DEFAULT
    masked_b = b.filter(
        ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold)
    )
    assert a.tobytes() == masked_b.tobytes()


def test_finish_variant_passthrough_when_already_at_target():
    # _usm_applies is False at exact target: no resample, so no mask either, and
    # both conditions must collapse to the untouched pixels.
    raw = _step_edge(*TARGET)
    a = probe.finish_variant(raw, usm=USM_DEFAULT)
    b = probe.finish_variant(raw, usm=None)
    assert a.tobytes() == b.tobytes() == raw.convert("RGB").tobytes()


@pytest.mark.parametrize("usm", [USM_DEFAULT, None])
def test_finish_variant_refuses_to_squash_aspect_in_both_conditions(usm):
    # The no-mask branch must not become an aspect escape hatch: if B squashed
    # where A refuses, the A/B delta would be two different pictures.
    raw = _step_edge(1000, 1000)
    with pytest.raises(ValueError):
        probe.finish_variant(raw, usm=usm)


# --------------------------------------------------------------------------
# the measurement itself, on synthetic pixels (no model, no GPU)
# --------------------------------------------------------------------------
def _halo(src_img, out_img):
    """halo_pct at common scale, the way compute_numpy_metrics does it."""
    from lw_g1_gate import overshoot_halo

    common = out_img.convert("RGB").resize(src_img.size, Image.LANCZOS)
    return overshoot_halo(np.asarray(src_img.convert("RGB")), np.asarray(common))[
        "halo_pct"
    ]


def test_resample_alone_already_rings_without_any_unsharp_mask():
    # The load-bearing fact behind the whole census: halo_pct is NOT a USM-only
    # detector. Lanczos has negative lobes, so condition B - a bare downscale
    # with the mask skipped entirely - already pushes near-edge pixels outside
    # the source local range on a hard edge. Any reading of an A/B table that
    # assumes B must be ~0 is wrong, and this test is why.
    src = _step_edge(800, 450)
    raw = src.resize((3200, 1800), Image.LANCZOS)
    assert _halo(src, probe.finish_variant(raw, usm=None)) > 0.0


def test_the_mask_measurably_moves_the_metric():
    # A and B must not be the same number, or the census has no signal to read.
    # The DIRECTION is deliberately not asserted here: it is the open question
    # the corpus measurement exists to answer, and on this degenerate bar
    # pattern the masked variant actually scores LOWER.
    src = _step_edge(800, 450)
    raw = src.resize((3200, 1800), Image.LANCZOS)
    a = _halo(src, probe.finish_variant(raw, usm=USM_DEFAULT))
    b = _halo(src, probe.finish_variant(raw, usm=None))
    assert a != b


def test_smooth_source_does_not_ring():
    # A ramp has no strong edges to overshoot on; a nonzero halo here would mean
    # the detector fires on gradient content and the census would be noise.
    src = _smooth_ramp(800, 450)
    raw = src.resize((3200, 1800), Image.LANCZOS)
    assert _halo(src, probe.finish_variant(raw, usm=USM_DEFAULT)) < 0.01
    assert _halo(src, probe.finish_variant(raw, usm=None)) < 0.01


# --------------------------------------------------------------------------
# classify_slugs / crossings / atomic write
# --------------------------------------------------------------------------
def _write_slug(root, slug, audit):
    d = Path(root) / slug
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(_manifest(audit)), encoding="utf-8")


def test_classify_slugs_selects_by_shipped_verdict(tmp_path):
    _write_slug(tmp_path, "aaa", {"gate": "G1", "verdict": "FLAG"})
    _write_slug(tmp_path, "bbb", {"gate": "G1", "verdict": "PASS"})
    _write_slug(tmp_path, "ccc", {"hold": "aspect_crop_heavy"})
    (tmp_path / "ddd").mkdir()  # no manifest at all
    assert probe.classify_slugs(tmp_path, {"FLAG"}) == ["aaa"]
    assert probe.classify_slugs(tmp_path, {"PASS"}) == ["bbb"]
    assert probe.classify_slugs(tmp_path, {"FLAG", "PASS"}) == ["aaa", "bbb"]


def test_classify_slugs_survives_a_corrupt_manifest(tmp_path):
    _write_slug(tmp_path, "aaa", {"gate": "G1", "verdict": "FLAG"})
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text("{not json", encoding="utf-8")
    assert probe.classify_slugs(tmp_path, {"FLAG"}) == ["aaa"]


def test_classify_slugs_missing_root_is_empty(tmp_path):
    assert probe.classify_slugs(tmp_path / "nope", {"FLAG"}) == []


def test_crossings_counts_over_line_per_variant():
    rows = [
        {"variants": {"usm_1.2_70_3": {"halo_pct": 0.07},
                      "no_usm": {"halo_pct": 0.01}}},
        {"variants": {"usm_1.2_70_3": {"halo_pct": 0.04},
                      "no_usm": {"halo_pct": 0.002}}},
        {"status": "error"},
    ]
    got = probe.crossings(rows, threshold=0.05)
    assert got["usm_1.2_70_3"] == {"over": 1, "measured": 2, "max": 0.07, "min": 0.04}
    assert got["no_usm"]["over"] == 0
    assert got["no_usm"]["measured"] == 2


def test_crossings_ignores_non_numeric_halo():
    rows = [{"variants": {"no_usm": {"halo_pct": None}}}]
    assert probe.crossings(rows) == {}


def test_atomic_write_json_leaves_no_part_file(tmp_path):
    out = tmp_path / "sub" / "report.json"
    probe._atomic_write_json(out, {"rows": []})
    assert json.loads(out.read_text(encoding="utf-8")) == {"rows": []}
    assert not list(tmp_path.rglob("*.part"))


# --------------------------------------------------------------------------
# worker geometry via the model-free downscale-only branch
# --------------------------------------------------------------------------
def test_worker_render_downscale_only_needs_no_model(tmp_path):
    # An over-target source takes _covers_target's downscale-only branch, so the
    # worker's variant loop is exercised end to end without touching spandrel.
    src = tmp_path / "src.png"
    _step_edge(3200, 1800).save(src)
    meta = probe.worker_render(str(src), str(tmp_path), ["1.2,70,3", "none"],
                               model_path="/nonexistent/model.safetensors")
    assert meta["backend"] == "downscale-only"
    assert meta["usm_applies"] is True
    assert set(meta["variants"]) == {"usm_1.2_70_3", "no_usm"}
    for info in meta["variants"].values():
        assert Path(info["png"]).is_file()
        assert info["dims"] == list(TARGET)
    assert not list(tmp_path.glob("*.part"))


def test_worker_render_variants_differ(tmp_path):
    src = tmp_path / "src.png"
    _step_edge(3200, 1800).save(src)
    meta = probe.worker_render(str(src), str(tmp_path), ["1.2,70,3", "none"])
    a = Image.open(meta["variants"]["usm_1.2_70_3"]["png"]).tobytes()
    b = Image.open(meta["variants"]["no_usm"]["png"]).tobytes()
    assert a != b


# --------------------------------------------------------------------------
# driver wiring (subprocess monkeypatched - never spawns a real venv)
# --------------------------------------------------------------------------
def test_spawn_worker_passes_create_no_window_and_argv(monkeypatch):
    seen = {}

    class _Proc:
        returncode = 0
        stdout = 'noise\n{"backend": "spandrel", "variants": {}}\n'
        stderr = ""

    def _fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return _Proc()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    out = probe._spawn_worker("py.exe", "src.png", "outdir", ["1.2,70,3", "none"],
                              model_path="m.safetensors")
    assert out["backend"] == "spandrel"
    # Legion focus-steal rule: the flag must be present on every spawn.
    assert seen["kwargs"]["creationflags"] == getattr(
        subprocess, "CREATE_NO_WINDOW", 0
    )
    argv = seen["argv"]
    assert argv[0] == "py.exe"
    assert "--worker" in argv
    assert argv[argv.index("--worker-src") + 1] == "src.png"
    assert argv.count("--usm") == 2
    assert argv[argv.index("--model") + 1] == "m.safetensors"


def test_spawn_worker_raises_on_nonzero_rc(monkeypatch):
    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(RuntimeError, match="rc=1"):
        probe._spawn_worker("py.exe", "s", "o", ["none"])


def test_run_census_isolates_a_failing_slug(monkeypatch):
    def _fake(slug, *a, **k):
        if slug == "bad":
            raise RuntimeError("nope")
        return {"slug": slug, "status": "ok"}

    monkeypatch.setattr(probe, "measure_slug", _fake)
    rows = probe.run_census(["good", "bad", "also-good"], "w", ["none"], "py")
    assert [r["status"] for r in rows] == ["ok", "error", "ok"]
    assert "RuntimeError" in rows[1]["reason"]


def test_main_without_slugs_exits_2(capsys):
    assert probe.main(["--scratch-root", "/nonexistent-root"]) == 2


def test_main_batch_resolves_and_writes_report(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    _write_slug(scratch, "aaa", {"gate": "G1", "verdict": "FLAG",
                                 "metrics": {"halo_pct": 0.07}})
    _write_slug(scratch, "bbb", {"gate": "G1", "verdict": "PASS",
                                 "metrics": {"halo_pct": 0.01}})
    monkeypatch.setattr(
        probe, "measure_slug",
        lambda slug, *a, **k: {"slug": slug, "status": "ok",
                               "variants": {"no_usm": {"halo_pct": 0.01}}},
    )
    out = tmp_path / "report.json"
    rc = probe.main(["--batch", "flagged", "--scratch-root", str(scratch),
                     "--out", str(out), "--work-dir", str(tmp_path / "w")])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [r["slug"] for r in report["rows"]] == ["aaa"]
    assert report["halo_flag_threshold"] == 0.05
    assert report["crossings"]["no_usm"]["measured"] == 1


def test_main_default_usm_specs_are_the_shipped_recipe_plus_none(tmp_path, monkeypatch):
    captured = {}

    def _fake_census(slugs, work_root, usm_specs, python_exe, model_path=None):
        captured["specs"] = usm_specs
        return []

    monkeypatch.setattr(probe, "run_census", _fake_census)
    probe.main(["--slug", "x", "--work-dir", str(tmp_path)])
    assert captured["specs"] == ["1.2,70,3", "none"]
    assert probe.parse_usm_spec(captured["specs"][0]) == USM_DEFAULT


# --------------------------------------------------------------------------
# live-model path - gated on the CAPABILITY, not on the thing under test
# --------------------------------------------------------------------------
_HAVE_UPSCALER = os.path.isfile(probe.fp.UP_PY) and os.path.isfile(probe.fp.MODEL_PATH)


@pytest.mark.skipif(not _HAVE_UPSCALER,
                    reason="upscale venv or IJN model absent (CI / non-Legion box)")
def test_worker_spandrel_branch_produces_both_variants(tmp_path):
    # 700x394 is inside ASPECT_TOL of 16:9 and 4x lands at 2800x1576, so the
    # finish really does resample - a 640x360 source would hit the exact-target
    # passthrough and measure nothing.
    src = tmp_path / "src.png"
    _step_edge(700, 394).save(src)
    argv = [probe.fp.UP_PY, probe.__file__, "--worker",
            "--worker-src", str(src), "--worker-out-dir", str(tmp_path),
            "--usm", "1.2,70,3", "--usm", "none"]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert proc.returncode == 0, proc.stderr[-800:]
    meta = probe.fp._last_json_line(proc.stdout)
    assert meta["backend"] == "spandrel"
    assert meta["up_dims"] == [2800, 1576]
    assert meta["usm_applies"] is True
    assert set(meta["variants"]) == {"usm_1.2_70_3", "no_usm"}
