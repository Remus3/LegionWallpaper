"""Mask-excluded G1 FR for cleaning candidates (tools/lw_clean_fr.py).

Why a mask at all: G1's FR metrics compare a candidate against its
_cleaninitial, which still carries the mark. A successful cleaning legitimately
differs inside the detect mask, so that region is neutralized (reference pixels
composited in) before FR runs, and only the region the candidate was supposed
to preserve is scored.

THE TRAP THIS MODULE EXISTS TO PREVENT (measured on 259f, 2026-08-29): a mask
DERIVED from the candidate's own diff is a tautology. Neutralizing wherever the
candidate differs makes it byte-identical to the reference, and FR returns
ms_ssim 1.0000 / lpips 0.0001 for any candidate whatsoever. The mask must be an
INDEPENDENT artifact - the detect output on disk - never computed from the pair.
The API therefore accepts a mask PATH only, and refuses one large enough to make
the score vacuous.

Honest scope: measured over 41 recorded cleaning masks the median covers 1.257%
of the frame and the max 6.363%, so exclusion moves ms_ssim by roughly +0.003
(259f) to +0.02 (corpus worst case). It is a correctness fix, not a large one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_fr as cf  # noqa: E402

# Measured corpus facts these tests are anchored to (docs/LEDGER.md).
CORPUS_MAX_MASK_PCT = 6.363
CORPUS_MEDIAN_MASK_PCT = 1.257


def _img(h=64, w=96, val=None):
    y, x = np.mgrid[0:h, 0:w]
    a = np.zeros((h, w, 3), np.uint8)
    a[..., 0] = (40 + 80 * ((x // 8) % 2)) if val is None else val
    a[..., 1] = (40 + 80 * ((y // 8) % 2)) if val is None else val
    a[..., 2] = (30 + 60 * (((x + y) // 12) % 2)) if val is None else val
    return a


def _write(path: Path, arr) -> Path:
    from PIL import Image
    Image.fromarray(arr).save(path)
    return path


def _write_mask(path: Path, shape, box) -> Path:
    from PIL import Image
    m = np.zeros(shape[:2], np.uint8)
    y0, y1, x0, x1 = box
    m[y0:y1, x0:x1] = 255
    Image.fromarray(m).save(path)
    return path


def test_source_is_ascii():
    src = Path(__file__).resolve().parent.parent / "tools" / "lw_clean_fr.py"
    assert all(b <= 127 for b in src.read_bytes())


# ------------------------------------------------------- the tautology guard
def test_a_mask_over_the_area_ceiling_is_refused(tmp_path: Path):
    """A mask big enough to swallow the candidate's whole diff makes FR vacuous."""
    ref = _img()
    mp = _write_mask(tmp_path / "m.png", ref.shape, (0, 60, 0, 90))  # ~88%
    with pytest.raises(cf.MaskError) as e:
        cf.load_gate_mask(mp, ref.shape)
    assert "ceiling" in str(e.value).lower()


def test_the_corpus_worst_case_mask_is_accepted(tmp_path: Path):
    """6.363% is the largest mask on record; it must not trip the ceiling."""
    assert CORPUS_MAX_MASK_PCT < cf.MASK_MAX_PCT
    ref = _img(100, 100)
    rows = int(round(CORPUS_MAX_MASK_PCT))            # ~6.36% of a 100x100
    mp = _write_mask(tmp_path / "m.png", ref.shape, (0, rows, 0, 100))
    mask = cf.load_gate_mask(mp, ref.shape)
    assert mask.sum() == rows * 100


def test_a_mask_whose_size_does_not_match_the_frame_is_refused(tmp_path: Path):
    ref = _img(64, 96)
    mp = _write_mask(tmp_path / "m.png", (32, 32), (0, 16, 0, 16))
    with pytest.raises(cf.MaskError):
        cf.load_gate_mask(mp, ref.shape)


def test_an_empty_mask_is_refused(tmp_path: Path):
    """An all-zero mask means the detect step found nothing; scoring against it
    silently degrades to whole-frame while claiming a mask was applied."""
    ref = _img()
    mp = _write_mask(tmp_path / "m.png", ref.shape, (0, 0, 0, 0))
    with pytest.raises(cf.MaskError):
        cf.load_gate_mask(mp, ref.shape)


# ------------------------------------------------------------- neutralization
def test_neutralize_makes_the_masked_region_identical_to_the_reference():
    ref, cand = _img(), _img(val=200)
    mask = np.zeros(ref.shape[:2], bool)
    mask[10:20, 10:20] = True
    out = cf.neutralize(cand, ref, mask)
    assert np.array_equal(out[mask], ref[mask])


def test_neutralize_leaves_everything_outside_the_mask_untouched():
    ref, cand = _img(), _img(val=200)
    mask = np.zeros(ref.shape[:2], bool)
    mask[10:20, 10:20] = True
    out = cf.neutralize(cand, ref, mask)
    assert np.array_equal(out[~mask], cand[~mask])


def test_neutralize_does_not_mutate_its_inputs():
    ref, cand = _img(), _img(val=200)
    before = cand.copy()
    mask = np.zeros(ref.shape[:2], bool)
    mask[5:9, 5:9] = True
    cf.neutralize(cand, ref, mask)
    assert np.array_equal(cand, before)


def test_a_none_mask_scores_the_whole_frame():
    ref, cand = _img(), _img(val=200)
    out = cf.neutralize(cand, ref, None)
    assert np.array_equal(out, cand)


# -------------------------------------------------------------------- verdict
def _fr(ms, lp, di=0.01):
    return {"ms_ssim": ms, "lpips": lp, "dists": di}


def test_a_clean_candidate_passes():
    a = cf.clean_fr_audit(_fr(0.9872, 0.0197), lap_ratio=1.02, halo_pct=0.03,
                          band_delta=0.0, mask_pct=0.912)
    assert a["verdict"] == "PASS"
    assert a["reasons"] == []


def test_a_globally_filtered_candidate_fails():
    a = cf.clean_fr_audit(_fr(0.9566, 0.1747), lap_ratio=10.244, halo_pct=0.3897,
                          band_delta=0.0, mask_pct=0.912)
    assert a["verdict"] == "FAIL"
    assert any("halo" in r for r in a["reasons"])


def test_the_audit_is_shaped_for_pipeline_annotate():
    a = cf.clean_fr_audit(_fr(0.99, 0.01), lap_ratio=1.0, halo_pct=0.0,
                          band_delta=0.0, mask_pct=1.0)
    assert a["gate"] == "G1-clean"
    assert set(("gate", "verdict", "reasons", "metrics")) <= set(a)
    json.dumps(a)  # must survive --metrics round-tripping


def test_the_audit_records_the_mask_percentage_it_excluded():
    """A reader must be able to judge how much of the frame went unscored."""
    a = cf.clean_fr_audit(_fr(0.99, 0.01), lap_ratio=1.0, halo_pct=0.0,
                          band_delta=0.0, mask_pct=CORPUS_MEDIAN_MASK_PCT)
    assert a["metrics"]["mask_pct"] == pytest.approx(CORPUS_MEDIAN_MASK_PCT)


def test_whole_frame_scoring_is_recorded_as_a_zero_mask():
    a = cf.clean_fr_audit(_fr(0.99, 0.01), lap_ratio=1.0, halo_pct=0.0,
                          band_delta=0.0, mask_pct=None)
    assert a["metrics"]["mask_pct"] is None


def test_lap_ratio_is_recorded_but_never_gated_on_a_cleaning_candidate():
    """ADR-006 logic: cleaning does no upscale, so the lap_ratio softness FLOOR
    reads as arbitrary pass/fail by source content. Recorded, not gated - the
    over-sharpen direction is already owned by halo_pct."""
    a = cf.clean_fr_audit(_fr(0.99, 0.01), lap_ratio=0.4, halo_pct=0.0,
                          band_delta=0.0, mask_pct=1.0)
    assert a["verdict"] == "PASS"
    assert a["metrics"]["lap_ratio"] == pytest.approx(0.4)
    assert not any("lap_ratio" in r for r in a["reasons"])


# --------------------------------------------- the tautology, caught directly
# The derived box that produced ms_ssim 1.0000 on 259f covered 14.787% of the
# frame - comfortably under a 25% ceiling. An area ceiling alone does NOT catch
# this. The real tell is that nothing outside the mask differs at all.
DERIVED_BOX_PCT = 14.787


def test_the_ceiling_refuses_the_derived_box_that_produced_the_tautology(
        tmp_path: Path):
    assert cf.MASK_MAX_PCT < DERIVED_BOX_PCT, (
        "the ceiling must sit below the derived box measured on 259f")
    ref = _img(100, 100)
    mp = _write_mask(tmp_path / "m.png", ref.shape, (0, 15, 0, 100))  # 15%
    with pytest.raises(cf.MaskError):
        cf.load_gate_mask(mp, ref.shape)


def test_the_ceiling_still_clears_the_corpus_worst_case():
    assert CORPUS_MAX_MASK_PCT < cf.MASK_MAX_PCT


def test_a_candidate_differing_only_inside_the_mask_is_reported_as_unscored(
        tmp_path: Path):
    """Tool output is byte-identical outside its mask by construction, so
    neutralizing leaves nothing to compare. That must be VISIBLE in the audit,
    not hidden behind a free 1.0."""
    ref_a = _img()
    cand_a = ref_a.copy()
    cand_a[10:20, 10:20] = 255
    rp = _write(tmp_path / "ref.png", ref_a)
    cp = _write(tmp_path / "cand.png", cand_a)
    mp = _write_mask(tmp_path / "m.png", ref_a.shape, (10, 20, 10, 20))
    out = cf.compute_clean_fr(rp, cp, mask_path=mp,
                              fr_fn=lambda *a, **k: _fr(1.0, 0.0))
    assert out["metrics"]["outside_changed_px"] == 0
    assert out["metrics"]["scored"] is False


def test_a_candidate_changed_outside_the_mask_is_reported_as_scored(
        tmp_path: Path):
    ref_a = _img()
    cand_a = ref_a.copy()
    cand_a[10:20, 10:20] = 255      # inside the mask
    cand_a[40:44, 40:44] = 7        # outside it - real collateral
    rp = _write(tmp_path / "ref.png", ref_a)
    cp = _write(tmp_path / "cand.png", cand_a)
    mp = _write_mask(tmp_path / "m.png", ref_a.shape, (10, 20, 10, 20))
    out = cf.compute_clean_fr(rp, cp, mask_path=mp,
                              fr_fn=lambda *a, **k: _fr(0.97, 0.05))
    assert out["metrics"]["outside_changed_px"] == 16
    assert out["metrics"]["outside_max_delta"] > 0
    assert out["metrics"]["scored"] is True


def test_whole_frame_scoring_counts_every_changed_pixel_as_outside(
        tmp_path: Path):
    ref_a = _img()
    cand_a = ref_a.copy()
    cand_a[10:20, 10:20] = 255
    rp = _write(tmp_path / "ref.png", ref_a)
    cp = _write(tmp_path / "cand.png", cand_a)
    out = cf.compute_clean_fr(rp, cp, mask_path=None,
                              fr_fn=lambda *a, **k: _fr(0.97, 0.05))
    assert out["metrics"]["outside_changed_px"] == 100
    assert out["metrics"]["scored"] is True


# ------------------------------------------------------------------ end to end
def test_compute_uses_the_mask_and_reports_it(tmp_path: Path):
    ref_a = _img()
    cand_a = ref_a.copy()
    cand_a[10:20, 10:20] = 255                       # the "cleaned" region
    rp = _write(tmp_path / "ref.png", ref_a)
    cp = _write(tmp_path / "cand.png", cand_a)
    mp = _write_mask(tmp_path / "m.png", ref_a.shape, (10, 20, 10, 20))
    seen = {}

    def fake_fr(cand_path, ref_path, src_path, names=()):
        seen["cand"] = np.asarray(__import__("PIL.Image", fromlist=["Image"])
                                  .open(cand_path).convert("RGB"))
        return _fr(0.999, 0.001)

    out = cf.compute_clean_fr(rp, cp, mask_path=mp, fr_fn=fake_fr)
    # the neutralized candidate handed to FR must equal the reference exactly
    assert np.array_equal(seen["cand"], ref_a)
    assert out["metrics"]["mask_pct"] == pytest.approx(100 * 100 / (64 * 96), abs=1e-6)


def test_compute_without_a_mask_scores_the_whole_frame(tmp_path: Path):
    ref_a = _img()
    cand_a = ref_a.copy()
    cand_a[10:20, 10:20] = 255
    rp = _write(tmp_path / "ref.png", ref_a)
    cp = _write(tmp_path / "cand.png", cand_a)
    seen = {}

    def fake_fr(cand_path, ref_path, src_path, names=()):
        seen["cand"] = np.asarray(__import__("PIL.Image", fromlist=["Image"])
                                  .open(cand_path).convert("RGB"))
        return _fr(0.98, 0.05)

    out = cf.compute_clean_fr(rp, cp, mask_path=None, fr_fn=fake_fr)
    assert np.array_equal(seen["cand"], cand_a)
    assert out["metrics"]["mask_pct"] is None


def test_the_cli_exits_2_on_a_missing_file_instead_of_tracebacking(
        tmp_path: Path, capsys: pytest.CaptureFixture):
    rp = _write(tmp_path / "ref.png", _img())
    rc = cf.main(["--reference", str(rp),
                  "--candidate", str(tmp_path / "nope.png")])
    assert rc == 2
    assert "lw_clean_fr" in capsys.readouterr().err


def test_the_cli_exits_2_on_an_undecodable_candidate(tmp_path: Path):
    rp = _write(tmp_path / "ref.png", _img())
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not-an-image")
    assert cf.main(["--reference", str(rp), "--candidate", str(bad)]) == 2


def test_compute_refuses_a_candidate_that_is_not_the_reference_size(tmp_path: Path):
    rp = _write(tmp_path / "ref.png", _img(64, 96))
    cp = _write(tmp_path / "cand.png", _img(32, 32))
    with pytest.raises(cf.MaskError):
        cf.compute_clean_fr(rp, cp, mask_path=None, fr_fn=lambda *a, **k: _fr(1.0, 0.0))
