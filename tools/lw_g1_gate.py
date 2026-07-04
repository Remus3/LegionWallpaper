"""G1 upscale-gate metrics for the Legion Wallpaper pipeline.

Spec: docs/research/AUDIT_GATES.md - section 1.4 (calibrated seed thresholds,
QA Session 1 2026-07-04), section 3.1 (sharpness / laplacian ratio), section
3.2 (halo / overshoot-undershoot detection), section 3.3 (banding delta).

This module is the free, deterministic first rung of the G1 gate (ladder step
G1 in AUDIT_GATES section 5.1). It answers "did the single upscale + light USM
soften, ring, or band the image relative to its source" using pure-numpy
signal processing - no ML weights, no cv2.

CI constraint (read before editing imports): committed tests import this module
on Python 3.12 with only numpy + Pillow available as third-party deps. Therefore
numpy is a top-level import and PIL is imported lazily. cv2, torch, and pyiqa are
NOT available in CI and must never be imported at module top level - the only FR
function (fr_metrics) lazy-imports pyiqa/torch inside its body.

All arrays are float64. Convolutions are hand-rolled 3x3 kernels over
edge-padded slices (no scipy, no cv2). Any file this module writes uses an
atomic write (tmp then os.replace) per the project hard rules.
"""
from __future__ import annotations

import os
import tempfile
from typing import Any, Dict

import numpy as np

# --------------------------------------------------------------------------
# Calibrated seed thresholds (AUDIT_GATES.md section 1.4, QA Session 1,
# 2026-07-04, n=10, upscaler=realesrgan-x4plus-anime, USM70, LoL splash corpus).
# These are SEEDS to be calibrated - widen n before freezing, and re-calibrate
# for the IllustrationJaNai primary path (Session 1 used the ncnn fallback).
# --------------------------------------------------------------------------
DEFAULT_G1_THRESHOLDS: Dict[str, Dict[str, float]] = {
    # MS-SSIM: pass >= 0.98, flag 0.96-0.98, fail < 0.96 (higher = closer).
    "msssim": {"pass": 0.98, "fail": 0.96},
    # LPIPS (alex): pass <= 0.12, flag 0.12-0.20, fail > 0.20 (lower = closer).
    "lpips": {"pass": 0.12, "fail": 0.20},
    # Laplacian ratio: softness floor. fail if < 1.0. No upper ceiling - the
    # 1.81-4.43 spread at fixed USM tracks SOURCE softness, not over-sharpen;
    # over-sharpen is caught by overshoot_halo (3.1/3.2), not a lap ceiling.
    "lap_ratio": {"fail": 1.0},
    # halo_pct: fraction of near-edge pixels that ring (the real overshoot
    # detector, AUDIT_GATES 3.2). flag if > 0.05 - over-flag is the safe
    # direction. QA Session 2 n=10: the detector ranks IJN below fallback on
    # ALL 10 images (IJN 0.018-0.075 median 0.036; fallback 0.049-0.145 median
    # 0.087). Flag-only, never a hard fail - over-sharpen is a quality flag for
    # vision audit, not a content-integrity failure.
    "halo_pct": {"flag": 0.05},
    # band_delta: output banding density minus source (DELTA mode). ADVISORY
    # FLAG after the QA Session 2 freeze, NOT a hard fail - at n=10 the metric
    # noise (IJN up to 0.029, fallback up to 0.079) overlaps real-banding
    # signal, so a >0 hard fail wrongly rejected the BETTER upscaler 8/10 on
    # ~0.004 noise. flag if > 0.05; real banding still routes to vision audit.
    # Revisit with a proper banding metric (BBAND, AUDIT_GATES 3.3) before hard-gating.
    "band_delta": {"flag": 0.05},
}


# --------------------------------------------------------------------------
# small pure-numpy convolution primitives
# --------------------------------------------------------------------------
def _to_gray(a: np.ndarray) -> np.ndarray:
    """Return a 2D float64 luma array. Accepts 2D gray or HxWx3/HxWx4 RGB(A).

    Luma uses the Rec.601 coefficients (Y of YCbCr) per AUDIT_GATES 1.2 item 4.
    """
    arr = np.asarray(a, dtype=np.float64)
    if arr.ndim == 2:
        return arr
    if arr.ndim == 3 and arr.shape[2] >= 3:
        r = arr[:, :, 0]
        g = arr[:, :, 1]
        b = arr[:, :, 2]
        return 0.299 * r + 0.587 * g + 0.114 * b
    raise ValueError(f"expected 2D gray or HxWx3 RGB array, got shape {arr.shape}")


def _conv3(a: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Convolve a 2D float64 array with a 3x3 kernel using edge padding.

    Implemented as a sum of shifted, edge-padded slices - no scipy/cv2. Returns
    an array the same shape as the input (mode='same', border replicate, which
    matches cv2's default BORDER_REFLECT_101 closely enough for a variance /
    percentile statistic on the interior-dominated wallpaper corpus).
    """
    a = np.asarray(a, dtype=np.float64)
    k = np.asarray(kernel, dtype=np.float64)
    p = np.pad(a, 1, mode="edge")
    out = np.zeros_like(a)
    h, w = a.shape
    for dy in range(3):
        for dx in range(3):
            coef = k[dy, dx]
            if coef == 0.0:
                continue
            out += coef * p[dy : dy + h, dx : dx + w]
    return out


# 4-neighbour Laplacian, matching cv2.Laplacian's default kernel.
_LAPLACIAN_4 = np.array([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]])
# Sobel gradient kernels.
_SOBEL_X = np.array([[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]])
_SOBEL_Y = np.array([[-1.0, -2.0, -1.0], [0.0, 0.0, 0.0], [1.0, 2.0, 1.0]])


def _window_reduce(a: np.ndarray, radius: int, op: str) -> np.ndarray:
    """Local max / min over a (2r+1)x(2r+1) window via edge-padded shifted slices.

    op is 'max' or 'min'. Pure numpy, no scipy.ndimage.
    """
    a = np.asarray(a, dtype=np.float64)
    if radius <= 0:
        return a.copy()
    p = np.pad(a, radius, mode="edge")
    h, w = a.shape
    acc = None
    span = 2 * radius + 1
    for dy in range(span):
        for dx in range(span):
            sl = p[dy : dy + h, dx : dx + w]
            if acc is None:
                acc = sl.copy()
            elif op == "max":
                acc = np.maximum(acc, sl)
            else:
                acc = np.minimum(acc, sl)
    return acc


def _local_variance(a: np.ndarray, radius: int = 1) -> np.ndarray:
    """Local variance over a (2r+1) window: E[x^2] - E[x]^2, edge padded."""
    a = np.asarray(a, dtype=np.float64)
    k = 2 * radius + 1
    ones = np.ones((k, k), dtype=np.float64) / (k * k)
    mean = _conv_box(a, ones)
    mean_sq = _conv_box(a * a, ones)
    var = mean_sq - mean * mean
    return np.clip(var, 0.0, None)


def _conv_box(a: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Convolve with an arbitrary odd square kernel via edge-padded slices."""
    a = np.asarray(a, dtype=np.float64)
    k = np.asarray(kernel, dtype=np.float64)
    r = k.shape[0] // 2
    p = np.pad(a, r, mode="edge")
    h, w = a.shape
    out = np.zeros_like(a)
    for dy in range(k.shape[0]):
        for dx in range(k.shape[1]):
            coef = k[dy, dx]
            if coef == 0.0:
                continue
            out += coef * p[dy : dy + h, dx : dx + w]
    return out


# --------------------------------------------------------------------------
# 3.1 sharpness / laplacian ratio
# --------------------------------------------------------------------------
def laplacian_var(gray: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian - the standard blur metric.

    gray is a 2D array (or RGB, reduced to luma). Mirrors
    cv2.Laplacian(gray, CV_64F).var(). Absolute value is content-dependent; the
    meaningful quantity is the ratio between two images (laplacian_ratio).
    """
    g = _to_gray(gray)
    lap = _conv3(g, _LAPLACIAN_4)
    return float(np.var(lap))


def laplacian_ratio(source_gray: np.ndarray, output_common_gray: np.ndarray) -> float:
    """laplacian_var(output) / laplacian_var(source): the softness floor metric.

    AUDIT_GATES G1: ratio >= 1.0 means the upscale + USM did not soften the
    image. ratio < 0.9 is the old double-resample softness bug resurfacing.
    Both inputs must already be at COMMON SCALE (same H x W). Returns +inf if
    the source is perfectly flat (zero Laplacian variance) and the output is
    not, which correctly reads as "output is sharper than a flat source".
    """
    src_var = laplacian_var(source_gray)
    out_var = laplacian_var(output_common_gray)
    if src_var == 0.0:
        return float("inf") if out_var > 0.0 else 1.0
    return float(out_var / src_var)


# --------------------------------------------------------------------------
# 3.2 halo / overshoot-undershoot detection (the real detector)
# --------------------------------------------------------------------------
def overshoot_halo(
    source_rgb_or_gray: np.ndarray,
    output_common_gray_or_rgb: np.ndarray,
    edge_pctile: float = 95.0,
    T: float = 8.0,
    near_edge_radius: int = 2,
) -> Dict[str, Any]:
    """Detect unsharp-mask ringing (halos) near strong source edges.

    AUDIT_GATES sections 3.1/3.2. Both inputs are the SAME H x W (already at
    common scale), uint8/float in 0..255, gray or RGB. Work is done on luma.

    Principle: USM ringing pushes output pixel values OUTSIDE the original local
    dynamic range near strong edges - a bright overshoot fringe (output above
    the source local max) and/or a dark undershoot fringe (output below the
    source local min). A clean upscale keeps every near-edge pixel inside the
    source local range, so halo_pct ~ 0; a haloed edge lights up.

    Algorithm (pure numpy):
      a. gradient magnitude of the SOURCE via Sobel (Gx, Gy 3x3).
         strong-edge mask = grad >= percentile(grad, edge_pctile).
      b. dilate that mask by near_edge_radius (window max) -> near-edge band.
      c. source local max / local min over a (2*near_edge_radius+1) window.
      d. overshoot px = output > src_localmax + T; undershoot px = output <
         src_localmin - T. Both restricted to the near-edge band.
      e. return the fractions and counts (see keys below).

    Returns dict with keys:
      halo_pct       - frac of near-edge-band px that overshoot OR undershoot
      overshoot_pct  - frac that overshoot
      undershoot_pct - frac that undershoot
      n_edge_px      - int count of near-edge-band px (the denominator)
      T, edge_pctile - the parameters used
    All fractions are in 0..1 rounded to 4dp.
    """
    src = _to_gray(source_rgb_or_gray)
    out = _to_gray(output_common_gray_or_rgb)
    if src.shape != out.shape:
        raise ValueError(
            f"source {src.shape} and output {out.shape} must be the same size "
            "(common scale) before halo detection"
        )

    # (a) source gradient magnitude via Sobel, strong-edge mask by percentile.
    gx = _conv3(src, _SOBEL_X)
    gy = _conv3(src, _SOBEL_Y)
    grad = np.hypot(gx, gy)
    thresh = float(np.percentile(grad, edge_pctile))
    grad_max = float(grad.max())
    if grad_max <= 0.0:
        # Perfectly flat image: no edges at all. Empty band -> halo_pct 0.
        strong = np.zeros_like(src, dtype=bool)
    else:
        # Strong-edge mask = gradient at or above the percentile threshold, but
        # ALWAYS strictly positive. On an image with sparse but sharp edges (a
        # clean step edge is >95 percent flat) the p95 gradient is 0; a bare
        # `>= 0` test would then select the entire flat frame. Floor the
        # threshold just above zero so only real edge pixels are selected.
        eff_thresh = max(thresh, 1e-6)
        strong = grad >= eff_thresh

    # (b) dilate to a near-edge band.
    band = _window_reduce(strong.astype(np.float64), near_edge_radius, "max") > 0.5

    n_edge = int(np.count_nonzero(band))
    if n_edge == 0:
        return {
            "halo_pct": 0.0,
            "overshoot_pct": 0.0,
            "undershoot_pct": 0.0,
            "n_edge_px": 0,
            "T": float(T),
            "edge_pctile": float(edge_pctile),
        }

    # (c) source local max / min over the small window.
    win = near_edge_radius  # window radius = near_edge_radius -> (2r+1) span
    src_max = _window_reduce(src, win, "max")
    src_min = _window_reduce(src, win, "min")

    # (d) overshoot / undershoot pixels, restricted to the near-edge band.
    overshoot = (out > (src_max + T)) & band
    undershoot = (out < (src_min - T)) & band

    n_over = int(np.count_nonzero(overshoot))
    n_under = int(np.count_nonzero(undershoot))
    # A pixel could in principle be neither; over and under are disjoint (a
    # value cannot exceed the local max and fall below the local min at once).
    n_ring = n_over + n_under

    return {
        "halo_pct": round(n_ring / n_edge, 4),
        "overshoot_pct": round(n_over / n_edge, 4),
        "undershoot_pct": round(n_under / n_edge, 4),
        "n_edge_px": n_edge,
        "T": float(T),
        "edge_pctile": float(edge_pctile),
    }


# --------------------------------------------------------------------------
# 3.3 banding delta
# --------------------------------------------------------------------------
def banding_delta(source_gray: np.ndarray, output_common_gray: np.ndarray) -> float:
    """Cheap banding metric in DELTA mode (AUDIT_GATES 3.3).

    Definition: PLATEAU-BOUNDARY density in SMOOTH regions, output minus source.
    Banding = "connected iso-value plateaus separated by 1-2 level steps"; the
    structural signature is a flat run (a plateau) that ends in a step. A true
    continuous gradient has no flat runs - every pixel differs slightly from its
    neighbour - so it scores ~0; a posterized/quantized gradient is all flat
    plateaus meeting at steps, so it scores high. That difference, not the raw
    step size, is what separates banding from a clean ramp.
      - Smooth region = pixels whose local variance (3x3) is below a small
        threshold (SMOOTH_VAR_THRESH). Textured regions are excluded so genuine
        detail is never mistaken for a false contour; a flat plateau has near
        zero local variance, so quantized gradients still qualify as smooth.
      - A BAND-EDGE pixel is a step (non-zero first difference) whose two
        neighbours ALONG THE SAME AXIS are both flat - an isolated plateau
        boundary. This is direction-aware: along a ramp's gradient axis a step
        is flanked by more steps (not a band edge); along its constant axis
        there are no steps at all; only genuine flat-plateau-meets-step
        transitions count, in either axis.
      - density = band-edge px / smooth px, computed for each image on ITS OWN
        smooth mask; the metric returned is out_density - src_density.

    Return value <= 0 means processing did not add banding (the gate: band
    delta must be <= 0). A positive value means the output introduced banding.
    Both inputs must be at common scale (same H x W).
    """
    src = _to_gray(source_gray)
    out = _to_gray(output_common_gray)
    if src.shape != out.shape:
        raise ValueError(
            f"source {src.shape} and output {out.shape} must be the same size"
        )

    SMOOTH_VAR_THRESH = 4.0  # local variance below this = smooth region

    def _axis_band_edges(a: np.ndarray, axis: int) -> np.ndarray:
        """Band-edge pixels along one axis: a step whose two neighbours along
        that SAME axis are both flat (a plateau boundary), direction-aware so an
        axis-aligned smooth ramp is not mistaken for banding.

        Along the gradient axis a true ramp is a run of equal small steps, so a
        step is flanked by MORE steps (not flat) -> not a band edge. A posterized
        ramp is flat plateaus meeting at isolated steps, so each step is flanked
        by flats -> band edge. Along the constant axis of a ramp everything is
        flat (no steps at all), so it contributes nothing.
        """
        d = np.abs(np.diff(a, axis=axis, append=np.take(a, [-1], axis=axis)))
        is_step = d > 1e-9
        # neighbour diffs shifted one pixel forward/back along the axis.
        prev_flat = np.roll(d, 1, axis=axis) <= 1e-9
        next_flat = np.roll(d, -1, axis=axis) <= 1e-9
        return is_step & prev_flat & next_flat

    def _density(a: np.ndarray) -> float:
        var = _local_variance(a, radius=1)
        smooth = var < SMOOTH_VAR_THRESH
        n_smooth = int(np.count_nonzero(smooth))
        if n_smooth == 0:
            return 0.0
        # A band-edge pixel is itself a step (high local variance), so it fails
        # the smooth test - but it BORDERS smooth plateaus. Qualify it by the
        # dilated smooth mask so a plateau boundary next to a smooth region
        # counts, while band edges in genuinely textured areas do not.
        smooth_near = _window_reduce(smooth.astype(np.float64), 1, "max") > 0.5
        band = (
            _axis_band_edges(a, axis=1) | _axis_band_edges(a, axis=0)
        ) & smooth_near
        return float(np.count_nonzero(band)) / float(n_smooth)

    return float(_density(out) - _density(src))


# --------------------------------------------------------------------------
# 1.x full-reference metrics (LAZY pyiqa/torch - not importable in CI)
# --------------------------------------------------------------------------
def fr_metrics(
    dist_path,
    ref_path,
    source_path,
    names=("psnr", "ssim", "ms_ssim", "lpips", "dists"),
    device=None,
) -> Dict[str, Any]:
    """Full-reference metrics at COMMON SCALE (AUDIT_GATES 1.2).

    Common-scale rule: the OUTPUT (dist_path, the 2560x1440 result) is
    DOWNSCALED to the SOURCE resolution with PIL Image.LANCZOS, written to a
    temp file, and each FR metric is computed of (downscaled-output vs source).
    The reference is NEVER upscaled (item 2 of 1.2) - upscaling the reference
    manufactures a blurry reference and biases every metric toward approving
    soft output. source_path defines the common scale; ref_path is the metric
    reference (usually the same file as source_path for the self-comparison).

    pyiqa and torch are imported HERE (lazily) so this module stays importable
    in CI where neither is installed. Verified pyiqa call pattern for this
    project:
        m = pyiqa.create_metric(name, device=dev)
        val = float(m(str(dist), str(ref)))
    for names in psnr/ssim/ms_ssim/lpips/dists.

    Each metric is wrapped in try/except so one bad metric records an
    "ERR ..." string instead of killing the whole batch. Returns
    {name: rounded float or "ERR ..."} plus "common_scale": [w, h].
    """
    import pyiqa  # lazy: absent in CI and on system python
    import torch  # lazy: same
    from PIL import Image

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    # Downscale the OUTPUT to the SOURCE resolution (never upscale the ref).
    with Image.open(source_path) as src_img:
        common_w, common_h = src_img.size
    out_img = Image.open(dist_path).convert("RGB")
    if out_img.size != (common_w, common_h):
        out_ds = out_img.resize((common_w, common_h), Image.LANCZOS)
    else:
        out_ds = out_img

    results: Dict[str, Any] = {"common_scale": [int(common_w), int(common_h)]}

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".png", prefix="lw_g1_ds_")
    os.close(tmp_fd)
    try:
        # Atomic-ish: write to a sibling temp then replace the target path.
        tmp_write = tmp_name + ".part"
        out_ds.save(tmp_write, format="PNG")
        os.replace(tmp_write, tmp_name)
        out_img.close()

        for name in names:
            try:
                metric = pyiqa.create_metric(name, device=device)
                val = float(metric(str(tmp_name), str(ref_path)))
                results[name] = round(val, 6)
            except Exception as exc:  # noqa: BLE001 - one bad metric != batch death
                results[name] = f"ERR {type(exc).__name__}: {exc}"
    finally:
        for leftover in (tmp_name, tmp_name + ".part"):
            try:
                os.remove(leftover)
            except OSError:
                pass

    return results


# --------------------------------------------------------------------------
# verdict (pure stdlib)
# --------------------------------------------------------------------------
def _tri(kind: str, value, th: Dict[str, float]):
    """Return ('PASS'|'FLAG'|'FAIL', reason_or_empty) for one metric.

    kind selects the comparison direction:
      'higher_better' - msssim: pass if >= th['pass'], fail if < th['fail'],
                        else flag.
      'lower_better'  - lpips:  pass if <= th['pass'], fail if > th['fail'],
                        else flag.
      'floor'         - lap_ratio: fail if < th['fail'], else pass (no ceiling).
      'flag_over'     - halo_pct, band_delta: flag if > th['flag'], else pass.
      'fail_over'     - available (fail if > th['fail']); unused after the QA
                        Session 2 freeze demoted band_delta to flag-only.
    """
    if value is None:
        return "PASS", ""
    v = float(value)
    if kind == "higher_better":
        if v >= th["pass"]:
            return "PASS", ""
        if v < th["fail"]:
            return "FAIL", f"{{name}} {v:g} < fail {th['fail']:g}"
        return "FLAG", f"{{name}} {v:g} in flag band [{th['fail']:g}, {th['pass']:g})"
    if kind == "lower_better":
        if v <= th["pass"]:
            return "PASS", ""
        if v > th["fail"]:
            return "FAIL", f"{{name}} {v:g} > fail {th['fail']:g}"
        return "FLAG", f"{{name}} {v:g} in flag band ({th['pass']:g}, {th['fail']:g}]"
    if kind == "floor":
        if v < th["fail"]:
            return "FAIL", f"{{name}} {v:g} < floor {th['fail']:g} (softening)"
        return "PASS", ""
    if kind == "flag_over":
        if v > th["flag"]:
            return "FLAG", f"{{name}} {v:g} > flag {th['flag']:g}"
        return "PASS", ""
    if kind == "fail_over":
        if v > th["fail"]:
            return "FAIL", f"{{name}} {v:g} > {th['fail']:g} (added banding)"
        return "PASS", ""
    raise ValueError(f"unknown comparison kind {kind!r}")


# metric key -> (comparison kind, threshold key in the thresholds dict)
_METRIC_RULES = (
    ("msssim", "higher_better", "msssim"),
    ("lpips", "lower_better", "lpips"),
    ("lap_ratio", "floor", "lap_ratio"),
    ("halo_pct", "flag_over", "halo_pct"),
    ("band_delta", "flag_over", "band_delta"),
)

_RANK = {"PASS": 0, "FLAG": 1, "FAIL": 2}


def verdict(metrics: Dict[str, Any], thresholds: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    """Combine per-metric checks into an overall G1 verdict (pure stdlib).

    metrics: a dict that may contain msssim, lpips, lap_ratio, halo_pct,
             band_delta (missing keys are skipped, not failed).
    thresholds: same shape as DEFAULT_G1_THRESHOLDS.

    Returns {"verdict": "PASS"|"FLAG"|"FAIL", "reasons": [...]}. The overall
    verdict is the WORST of the per-metric verdicts (AUDIT_GATES: any hard fail
    short-circuits; a flag routes to the vision audit). reasons lists the
    human-readable cause for every metric that flagged or failed.
    """
    worst = "PASS"
    reasons = []
    for name, kind, th_key in _METRIC_RULES:
        if name not in metrics or th_key not in thresholds:
            continue
        state, reason = _tri(kind, metrics[name], thresholds[th_key])
        if state != "PASS":
            reasons.append(reason.replace("{name}", name))
        if _RANK[state] > _RANK[worst]:
            worst = state
    return {"verdict": worst, "reasons": reasons}
