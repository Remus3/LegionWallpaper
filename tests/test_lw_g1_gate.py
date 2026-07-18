"""Tests for the G1 upscale-gate metrics in tools/lw_g1_gate.py.

Spec: docs/research/AUDIT_GATES.md sections 1.4 (calibrated seed thresholds),
3.1 (sharpness / laplacian ratio), 3.2 (halo / overshoot detection), 3.3
(banding delta). Written test-first per CLAUDE.md TDD.

CI constraint: this file runs on Python 3.12 with only pytest, ruff, numpy,
Pillow installed. The numpy/stdlib tests below are the real CI coverage and
MUST run. The single pyiqa smoke test starts with importorskip so it SKIPS
cleanly wherever pyiqa/torch are absent (CI and system python both lack them).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_g1_gate as g1  # noqa: E402


# --------------------------------------------------------------------------
# helpers (pure numpy - no PIL/torch needed)
# --------------------------------------------------------------------------
def _box_blur(a: np.ndarray, k: int = 3) -> np.ndarray:
    """Simple odd-window box blur with edge padding (softens an array)."""
    a = a.astype(np.float64)
    r = k // 2
    p = np.pad(a, r, mode="edge")
    out = np.zeros_like(a)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out += p[r + dy : r + dy + a.shape[0], r + dx : r + dx + a.shape[1]]
    return out / (k * k)


def _checkerboard(h: int, w: int, cell: int = 4) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    board = (((yy // cell) + (xx // cell)) % 2).astype(np.float64)
    return board * 255.0


# --------------------------------------------------------------------------
# laplacian_var / laplacian_ratio  (AUDIT_GATES 3.1)
# --------------------------------------------------------------------------
def test_laplacian_var_positive_on_texture():
    src = _checkerboard(64, 64, cell=4)
    assert g1.laplacian_var(src) > 0.0


def test_laplacian_var_zero_on_flat():
    flat = np.full((32, 32), 128.0)
    assert g1.laplacian_var(flat) == pytest.approx(0.0, abs=1e-9)


def test_laplacian_ratio_blur_below_one():
    """Sharp source -> blurred output: output is softer, ratio < 1.0."""
    src = _checkerboard(64, 64, cell=4)
    out = _box_blur(src, 3)
    ratio = g1.laplacian_ratio(src, out)
    assert ratio < 1.0


def test_laplacian_ratio_sharpen_above_one():
    """Blurred source -> sharp output: swapping the pair inverts the ratio."""
    src = _checkerboard(64, 64, cell=4)
    out = _box_blur(src, 3)
    ratio = g1.laplacian_ratio(out, src)  # source=blurred, output=sharp
    assert ratio > 1.0


# --------------------------------------------------------------------------
# overshoot_halo  (AUDIT_GATES 3.2) - the most important validation
# --------------------------------------------------------------------------
def _step_edge(h: int = 64, w: int = 64, lo: float = 60.0, hi: float = 200.0):
    """Vertical step edge: left half=lo, right half=hi."""
    img = np.full((h, w), lo, dtype=np.float64)
    img[:, w // 2 :] = hi
    return img


def test_overshoot_halo_clean_step_is_quiet():
    """output == source on a clean step edge -> no values outside local range."""
    src = _step_edge()
    out = src.copy()
    res = g1.overshoot_halo(src, out)
    assert res["halo_pct"] < 0.01
    assert res["n_edge_px"] > 0


def test_overshoot_halo_fires_on_ringing():
    """USM-style ringing pushes fringe pixels outside the 60/200 local range."""
    src = _step_edge()
    mid = src.shape[1] // 2
    clean = src.copy()
    haloed = src.copy()
    # bright side of the edge overshoots up to ~235 (> local max 200)
    haloed[:, mid : mid + 2] = 235.0
    # dark side of the edge undershoots down to ~30 (< local min 60)
    haloed[:, mid - 2 : mid] = 30.0

    clean_pct = g1.overshoot_halo(src, clean)["halo_pct"]
    haloed_pct = g1.overshoot_halo(src, haloed)["halo_pct"]

    assert haloed_pct > clean_pct
    assert haloed_pct > 0.1  # sane floor: the detector clearly fires


def test_overshoot_halo_splits_over_and_under():
    src = _step_edge()
    mid = src.shape[1] // 2
    haloed = src.copy()
    haloed[:, mid : mid + 2] = 235.0  # overshoot only
    res = g1.overshoot_halo(src, haloed)
    assert res["overshoot_pct"] > 0.0
    assert res["halo_pct"] == pytest.approx(
        res["overshoot_pct"] + res["undershoot_pct"], abs=1e-6
    )


def test_overshoot_halo_accepts_rgb():
    """RGB inputs are reduced to luma internally and still work."""
    src = _step_edge()
    rgb = np.stack([src, src, src], axis=-1)
    res = g1.overshoot_halo(rgb, rgb)
    assert res["halo_pct"] < 0.01


# --------------------------------------------------------------------------
# banding_delta  (AUDIT_GATES 3.3)
# --------------------------------------------------------------------------
def _smooth_gradient(h: int = 64, w: int = 64) -> np.ndarray:
    row = np.linspace(0.0, 255.0, w)
    return np.repeat(row[None, :], h, axis=0)


def _posterize(a: np.ndarray, levels: int = 6) -> np.ndarray:
    step = 255.0 / (levels - 1)
    return np.round(a / step) * step


def test_banding_delta_positive_when_output_posterized():
    src = _smooth_gradient()
    out = _posterize(src, levels=6)
    assert g1.banding_delta(src, out) > 0.0


def test_banding_delta_zero_when_identical():
    src = _smooth_gradient()
    assert g1.banding_delta(src, src) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------
# verdict  (AUDIT_GATES 1.4 seed thresholds) - pure stdlib
# --------------------------------------------------------------------------
def test_verdict_pass():
    m = {"msssim": 0.985, "lpips": 0.10, "lap_ratio": 2.0, "halo_pct": 0.0,
         "band_delta": 0.0}
    r = g1.verdict(m, g1.DEFAULT_G1_THRESHOLDS)
    assert r["verdict"] == "PASS"
    assert r["reasons"] == []


def test_verdict_flag_on_msssim():
    m = {"msssim": 0.97, "lpips": 0.10, "lap_ratio": 2.0, "halo_pct": 0.0,
         "band_delta": 0.0}
    r = g1.verdict(m, g1.DEFAULT_G1_THRESHOLDS)
    assert r["verdict"] == "FLAG"
    assert any("msssim" in reason for reason in r["reasons"])


def test_verdict_fail_on_lap_ratio_softness():
    m = {"msssim": 0.99, "lpips": 0.05, "lap_ratio": 0.8, "halo_pct": 0.0,
         "band_delta": 0.0}
    r = g1.verdict(m, g1.DEFAULT_G1_THRESHOLDS)
    assert r["verdict"] == "FAIL"
    assert any("lap_ratio" in reason for reason in r["reasons"])


def test_verdict_flag_on_band_delta():
    # band_delta is an ADVISORY flag after the QA Session 2 freeze (too noisy at
    # n=10 to hard-fail); a positive delta above the flag threshold routes to
    # vision audit, it does NOT hard-fail.
    m = {"msssim": 0.99, "lpips": 0.05, "lap_ratio": 2.0, "halo_pct": 0.0,
         "band_delta": 0.5}
    r = g1.verdict(m, g1.DEFAULT_G1_THRESHOLDS)
    assert r["verdict"] == "FLAG"
    assert any("band_delta" in reason for reason in r["reasons"])


def test_verdict_flag_on_halo():
    m = {"msssim": 0.99, "lpips": 0.05, "lap_ratio": 2.0, "halo_pct": 0.2,
         "band_delta": 0.0}
    r = g1.verdict(m, g1.DEFAULT_G1_THRESHOLDS)
    assert r["verdict"] == "FLAG"
    assert any("halo_pct" in reason for reason in r["reasons"])


def test_verdict_fail_beats_flag():
    """Worst-of rule: a FAIL metric plus a FLAG metric -> overall FAIL."""
    m = {"msssim": 0.97, "lpips": 0.05, "lap_ratio": 0.8, "halo_pct": 0.0,
         "band_delta": 0.0}
    r = g1.verdict(m, g1.DEFAULT_G1_THRESHOLDS)
    assert r["verdict"] == "FAIL"


def test_verdict_fail_on_lpips():
    m = {"msssim": 0.99, "lpips": 0.25, "lap_ratio": 2.0, "halo_pct": 0.0,
         "band_delta": 0.0}
    r = g1.verdict(m, g1.DEFAULT_G1_THRESHOLDS)
    assert r["verdict"] == "FAIL"
    assert any("lpips" in reason for reason in r["reasons"])


def test_default_thresholds_shape():
    t = g1.DEFAULT_G1_THRESHOLDS
    assert t["msssim"]["pass"] == 0.98
    assert t["msssim"]["fail"] == 0.96
    assert t["lpips"]["pass"] == 0.12
    assert t["lpips"]["fail"] == 0.20
    assert t["lap_ratio"]["fail"] == 1.0
    assert t["halo_pct"]["flag"] == 0.05
    assert t["band_delta"]["flag"] == 0.05


# --------------------------------------------------------------------------
# common-scale pixel budget (pure - real CI coverage, no torch/pyiqa needed)
#
# Regression: DISTS at an uncapped common scale OOMs both a 12GB GPU and
# system RAM. Observed on 63 of 230 first-pass images (2026-07-18): every
# failure was DISTS, at common scales from 5376x3024 (16.3 MPix) up. The
# largest scale that ever succeeded corpus-wide was 4096x2306 (9.4 MPix).
# --------------------------------------------------------------------------
def test_common_scale_under_budget_is_untouched():
    """Below the budget the source scale is used verbatim - no behaviour change."""
    for w, h in [(1280, 720), (1920, 1080), (2560, 1440), (3840, 2160)]:
        cw, ch, capped = g1.common_scale_for(w, h)
        assert (cw, ch) == (w, h)
        assert capped is False


def test_common_scale_caps_gently_just_over_budget():
    """4096x2306 (9.4 MPix) computed natively before, so its cap must be mild.

    The budget sits below this deliberately - it buys OOM headroom and keeps
    every capped value on the same 3840x2160 footing as the 26 corpus images
    already measured natively there. The cost is that scales in this band get
    re-based on a future recompute, so the cap must stay gentle enough that
    almost no resolution is lost.
    """
    cw, ch, capped = g1.common_scale_for(4096, 2306)
    assert capped is True
    assert cw * ch >= 0.85 * (4096 * 2306)  # gentle: keeps most of the pixels


@pytest.mark.parametrize(
    "src",
    [
        (7680, 4320),  # 57 of the 63 observed failures
        (5376, 3024),  # smallest observed failure
        (7000, 3964),
        (7680, 4324),  # off-by-4 height variant
    ],
)
def test_common_scale_caps_every_observed_failing_scale(src):
    """Each scale that OOMed in the corpus must be capped under budget."""
    w, h = src
    cw, ch, capped = g1.common_scale_for(w, h)
    assert capped is True
    assert cw * ch <= g1.MAX_COMMON_PIXELS
    assert cw <= w and ch <= h  # never upscale the reference
    assert abs((cw / ch) - (w / h)) < 0.01  # aspect preserved


def test_common_scale_budget_is_pixel_based_not_side_based():
    """A square 4096x4096 busts the budget even though its sides are small.

    A max-side cap would wave this through; the allocation that OOMs scales
    with pixel count, so the budget must too.
    """
    cw, ch, capped = g1.common_scale_for(4096, 4096)
    assert capped is True
    assert cw * ch <= g1.MAX_COMMON_PIXELS


def test_common_scale_never_returns_zero_dimension():
    """Extreme aspect ratios must not collapse a side to 0 (invalid resize)."""
    for w, h in [(30000, 8), (8, 30000)]:
        cw, ch, _ = g1.common_scale_for(w, h)
        assert cw >= 1 and ch >= 1


def test_max_common_pixels_within_proven_good_range():
    """Budget must sit at or below the largest corpus-proven scale (9.4 MPix)."""
    assert g1.MAX_COMMON_PIXELS <= 4096 * 2306
    assert g1.MAX_COMMON_PIXELS >= 1920 * 1080  # not so tight it destroys signal


# --------------------------------------------------------------------------
# fr_metrics smoke - SKIPS wherever pyiqa is unavailable (CI + system python)
# --------------------------------------------------------------------------
def test_fr_metrics_reports_capped_scale_honestly(tmp_path):
    """A capped run records the scale actually used plus the native one."""
    pytest.importorskip("pyiqa")
    from PIL import Image

    # 4200x2400 = 10.1 MPix, just over the budget -> must cap.
    ref = np.random.default_rng(0).integers(0, 256, (2400, 4200, 3), dtype=np.uint8)
    ref_p = tmp_path / "ref.png"
    dist_p = tmp_path / "dist.png"
    Image.fromarray(ref).save(ref_p)
    Image.fromarray(ref).resize((2560, 1440), Image.LANCZOS).save(dist_p)

    out = g1.fr_metrics(dist_p, ref_p, ref_p, names=("psnr",))
    assert out["capped"] is True
    assert out["native_scale"] == [4200, 2400]
    assert out["common_scale"][0] * out["common_scale"][1] <= g1.MAX_COMMON_PIXELS
    assert not isinstance(out["psnr"], str)  # computed, not an "ERR ..." string


def test_fr_metrics_smoke(tmp_path):
    pytest.importorskip("pyiqa")
    from PIL import Image

    ref = np.random.default_rng(0).integers(0, 256, (48, 64, 3), dtype=np.uint8)
    dist = np.repeat(np.repeat(ref, 2, axis=0), 2, axis=1)  # 2x nearest upscale
    ref_p = tmp_path / "ref.png"
    dist_p = tmp_path / "dist.png"
    Image.fromarray(ref).save(ref_p)
    Image.fromarray(dist).save(dist_p)

    out = g1.fr_metrics(dist_p, ref_p, ref_p, names=("psnr", "ssim"))
    assert "psnr" in out
    assert "common_scale" in out
