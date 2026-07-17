"""Legion Wallpaper - Dekel et al. (CVPR 2017) multi-image watermark remover.

Stage-2 cleaning R&D worker. A repeated, semi-transparent watermark that appears
over MANY different artworks is separable: it is the structure common to every
frame while the art underneath differs. Dekel's method estimates a single
watermark image W and a continuous matte alpha from the whole CLUSTER, then
recovers each clean art frame by INVERTING the matting equation

    J = alpha * W + (1 - alpha) * I   ->   I = (J - alpha * W) / (1 - alpha)

This is faithful RECOVERY (an algebraic inverse), not inpainting or generation -
where alpha ~ 0 the output equals the input. No halo is chased here; the
operator-facing validation loop owns final tuning. STOP conditions: unit tests
green + one namakx cluster solve that writes debug PNGs (W, alpha, per-slug
reconstruction) + a timing.json.

Ported from the rohitrango/automatic-watermark-detection scaffold (Py2,
matplotlib-coupled). The MATH is reused; every matplotlib call is stripped and
replaced by optional debug-PNG dumps. Two grounded deviations from the scaffold,
both documented at the call site:
  1. The sparse Sobel operators are rebuilt (vectorised) to MATCH cv2.Sobel; the
     scaffold's hand-written kernel is asymmetric + half-scale, which is
     internally inconsistent with the cv2.Sobel calls the solver interleaves.
  2. Per-image sub-pixel ALIGNMENT (phase cross-correlation) is added before the
     median-gradient pool - the genuinely missing piece for a jittered cluster
     like namakx (mark bbox y wanders ~39 px between frames). Unaligned pooling
     smears the shared mark and is the measured plateau cause.

Runtime: lw-clean venv ONLY (numpy 1.26 / scipy 1.17 / cv2 4.11 / skimage 0.24),
pure CPU. Heavy imports are module-top by design - this tool is never imported by
the CI-safe lw_clean_pass. ASCII-only; atomic PNG/JSON writes; any subprocess
would pass CREATE_NO_WINDOW (this tool shells out to nothing).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import cv2
import numpy as np
import scipy.fftpack
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from numpy.lib.stride_tricks import as_strided
from skimage.registration import phase_cross_correlation

# --------------------------------------------------------------------------
# Constants / project paths (Legion machine).
# --------------------------------------------------------------------------
KERNEL_SIZE = 3
MASK_THRESHOLD = 128

ROOT = r"C:\LegionWallpaper"
CLEAN_SCRATCH = os.path.join(ROOT, "images", "3.Cleaning Scratch")

# namakx repeated-watermark cluster (5 slugs); input per slug is <slug>_cleaninitial.png.
NAMAKX_SLUGS = [
    "dfz5w2g-8ba7345b-5776-4d83-b939-4ca7d045f545",
    "dfzlox4-7e2bdc64-36ce-41fa-80b0-c83f97fdf5f5",
    "dfzypoo-482973ff-dfb0-44e4-a90c-386714d27faf",
    "dfzypou-30bef263-c754-4a26-9797-484757b1c4cf",
    "dfzypp1-251c5c37-e25f-496e-a9a6-4900304e6fa5",
]

# Watermark region on the 2560x1440 frame (x0, y0, x1, y1); x1/y1 exclusive.
DEFAULT_REGION = (848, 1122, 1712, 1430)
DEFAULT_PAD = 20

_SCRATCH_DEBUG = os.path.join(
    r"C:\Users\ADMINI~1\AppData\Local\Temp\claude\C--LegionWallpaper",
    "a29d4376-03d2-40f2-85f9-719b5a3dfe9e", "scratchpad", "dekel_debug", "namakx",
)

# Standard 3x3 Sobel kernels expressed as (di, dj, value) correlation taps. These
# reproduce cv2.Sobel(ksize=3) EXACTLY on interior pixels (see the module note).
#   Sobel-x: [[-1,0,+1],[-2,0,+2],[-1,0,+1]]
#   Sobel-y: [[-1,-2,-1],[0,0,0],[+1,+2,+1]]
_XSOBEL_TAPS = ((-1, -1, -1.0), (-1, 1, 1.0), (0, -1, -2.0),
                (0, 1, 2.0), (1, -1, -1.0), (1, 1, 1.0))
_YSOBEL_TAPS = ((-1, -1, -1.0), (-1, 0, -2.0), (-1, 1, -1.0),
                (1, -1, 1.0), (1, 0, 2.0), (1, 1, 1.0))


# ==========================================================================
# Small pure helpers.
# ==========================================================================
def normalize01(image):
    """Map an array to [0, 1] by min-max (matches the scaffold PlotImage)."""
    im = np.asarray(image, dtype=np.float64)
    lo, hi = np.min(im), np.max(im)
    if hi - lo < 1e-12:
        return np.zeros_like(im)
    return (im - lo) / (hi - lo)


def _threshold01(image, threshold=0.5):
    """Binarise a [0,1]-normalised image at threshold*max -> {0, 1}."""
    im = normalize01(image)
    out = np.zeros_like(im)
    out[im >= threshold] = 1.0
    return out


def _as_binary(mask):
    """A boolean 'inside' mask from either a bool array or a uint8 L-mask."""
    m = np.asarray(mask)
    if m.dtype == bool:
        return m
    return m >= MASK_THRESHOLD


# ==========================================================================
# Closed-form matting (Levin et al.) - ported verbatim from the scaffold
# closed_form_matting.py (already Py3-clean).
# ==========================================================================
def _rolling_block(a, block=(3, 3)):
    shape = (a.shape[0] - block[0] + 1, a.shape[1] - block[1] + 1) + block
    strides = (a.strides[0], a.strides[1]) + a.strides
    return as_strided(a, shape=shape, strides=strides)


def compute_laplacian(img, eps=1e-7, win_rad=1):
    """Sparse Levin matting Laplacian for a 3-channel image."""
    win_size = (win_rad * 2 + 1) ** 2
    h, w, d = img.shape
    c_h, c_w = h - 2 * win_rad, w - 2 * win_rad
    win_diam = win_rad * 2 + 1

    inds_m = np.arange(h * w).reshape((h, w))
    ravel_img = img.reshape(h * w, d)
    win_inds = _rolling_block(inds_m, block=(win_diam, win_diam))
    win_inds = win_inds.reshape(c_h, c_w, win_size)
    win_i = ravel_img[win_inds]

    win_mu = np.mean(win_i, axis=2, keepdims=True)
    win_var = (np.einsum("...ji,...jk ->...ik", win_i, win_i) / win_size
               - np.einsum("...ji,...jk ->...ik", win_mu, win_mu))

    inv = np.linalg.inv(win_var + (eps / win_size) * np.eye(3))

    x = np.einsum("...ij,...jk->...ik", win_i - win_mu, inv)
    vals = np.eye(win_size) - (1 / win_size) * (
        1 + np.einsum("...ij,...kj->...ik", x, win_i - win_mu))

    nz_inds_col = np.tile(win_inds, win_size).ravel()
    nz_inds_row = np.repeat(win_inds, win_size).ravel()
    nz_inds_val = vals.ravel()
    return sp.coo_matrix((nz_inds_val, (nz_inds_row, nz_inds_col)),
                         shape=(h * w, h * w))


def closed_form_matte(img, scribbled_img, mylambda=100):
    """Solve for a continuous alpha matte given hard scribble constraints.

    scribbled_img differs from img exactly where a constraint is imposed; the
    scribble's channel-0 value is the target alpha (0 or 1) there.
    """
    h, w, _c = img.shape
    consts_map = (np.sum(np.abs(img - scribbled_img), axis=-1) > 0.001).astype(np.float64)
    consts_vals = scribbled_img[:, :, 0] * consts_map
    d_s = consts_map.ravel()
    b_s = consts_vals.ravel()
    laplacian = compute_laplacian(img)
    s_d_s = sp.diags(d_s)
    x = spla.spsolve(laplacian + mylambda * s_d_s, mylambda * b_s)
    return np.minimum(np.maximum(x.reshape(h, w), 0), 1)


# ==========================================================================
# Sparse Sobel operators (rebuilt to match cv2.Sobel - see module note).
# ==========================================================================
def _sobel_sparse(m, n, p, taps):
    """coo->csr sparse operator applying a 3x3 correlation kernel (zero border).

    Vectorised replacement for the scaffold's per-element Python loop. Rows =
    output index, cols = neighbour index, values = kernel tap. Out-of-range
    neighbours are dropped (zero boundary) - interior pixels then equal
    cv2.Sobel to machine precision.
    """
    size = m * n * p
    idx = np.arange(size)
    i, j, k = np.unravel_index(idx, (m, n, p))
    rows, cols, data = [], [], []
    for di, dj, val in taps:
        ii, jj = i + di, j + dj
        valid = (ii >= 0) & (ii < m) & (jj >= 0) & (jj < n)
        rows.append(idx[valid])
        cols.append(np.ravel_multi_index((ii[valid], jj[valid], k[valid]), (m, n, p)))
        data.append(np.full(int(valid.sum()), val, dtype=np.float64))
    return sp.coo_matrix(
        (np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))),
        shape=(size, size)).tocsr()


def get_xSobel_matrix(m, n, p):  # noqa: N802 - keep scaffold name for continuity
    """Sparse (m*n*p, m*n*p) operator equal to cv2.Sobel(dx=1) on the interior."""
    return _sobel_sparse(m, n, p, _XSOBEL_TAPS)


def get_ySobel_matrix(m, n, p):  # noqa: N802 - keep scaffold name for continuity
    """Sparse (m*n*p, m*n*p) operator equal to cv2.Sobel(dy=1) on the interior."""
    return _sobel_sparse(m, n, p, _YSOBEL_TAPS)


# ==========================================================================
# Poisson reconstruction (DST direct solver) - ported from the scaffold.
# ==========================================================================
def poisson_reconstruct2(gradx, grady, boundarysrc):
    """Reconstruct a 2D scalar field from its gradient with a Dirichlet boundary.

    Direct DST Poisson solve (Raskar). gradx/grady/boundarysrc are 2D. The
    boundary of the result is taken from boundarysrc; the interior is solved.
    """
    gyy = grady[1:, :-1] - grady[:-1, :-1]
    gxx = gradx[:-1, 1:] - gradx[:-1, :-1]
    f = np.zeros(boundarysrc.shape)
    f[:-1, 1:] += gxx
    f[1:, :-1] += gyy

    boundary = boundarysrc.copy().astype(np.float64)
    boundary[1:-1, 1:-1] = 0

    f_bp = (-4 * boundary[1:-1, 1:-1] + boundary[1:-1, 2:] + boundary[1:-1, 0:-2]
            + boundary[2:, 1:-1] + boundary[0:-2, 1:-1])
    f = f[1:-1, 1:-1] - f_bp

    tt = scipy.fftpack.dst(f, norm="ortho")
    fsin = scipy.fftpack.dst(tt.T, norm="ortho").T

    x, y = np.meshgrid(range(1, f.shape[1] + 1), range(1, f.shape[0] + 1), copy=True)
    denom = ((2 * np.cos(math.pi * x / (f.shape[1] + 2)) - 2)
             + (2 * np.cos(math.pi * y / (f.shape[0] + 2)) - 2))

    f = fsin / denom

    tt = scipy.fftpack.idst(f, norm="ortho")
    img_tt = scipy.fftpack.idst(tt.T, norm="ortho").T

    result = boundary
    result[1:-1, 1:-1] = img_tt
    return result


def poisson_reconstruct_multichannel(gradx, grady, boundary):
    """Per-channel poisson_reconstruct2 for a 3-channel gradient field."""
    if gradx.ndim == 2:
        return poisson_reconstruct2(gradx, grady, boundary)
    out = np.zeros_like(gradx, dtype=np.float64)
    for c in range(gradx.shape[2]):
        b = boundary[:, :, c] if boundary.ndim == 3 else boundary
        out[:, :, c] = poisson_reconstruct2(gradx[:, :, c], grady[:, :, c], b)
    return out


# ==========================================================================
# Median-gradient watermark seed + mark localisation.
# ==========================================================================
def estimate_watermark_gradients(images, ksize=KERNEL_SIZE):
    """grad(W) = median over the cluster of per-image Sobel gradients.

    images: list of aligned float ROI crops (identical shape). Returns
    (Wm_x, Wm_y, gradx_list, grady_list).
    """
    gradx = [cv2.Sobel(im, cv2.CV_64F, 1, 0, ksize=ksize) for im in images]
    grady = [cv2.Sobel(im, cv2.CV_64F, 0, 1, ksize=ksize) for im in images]
    wm_x = np.median(np.array(gradx), axis=0)
    wm_y = np.median(np.array(grady), axis=0)
    return wm_x, wm_y, gradx, grady


def mark_bbox_from_gradient(gradx, grady, threshold=0.4, boundary_size=2):
    """Tight (y0, y1, x0, x1) bbox of the mark support from |grad(W)|.

    Thresholds the normalised gradient magnitude and takes the bounding box of
    the surviving pixels, padded by boundary_size. None if nothing survives.
    """
    w_mod = np.sqrt(np.square(gradx) + np.square(grady))
    w_mod = normalize01(w_mod)
    gray = np.average(w_mod, axis=2) if w_mod.ndim == 3 else w_mod
    binm = _threshold01(gray, threshold)
    ys, xs = np.where(binm == 1)
    if ys.size == 0:
        return None
    h, w = gray.shape
    y0 = max(int(np.min(ys)) - boundary_size - 1, 0)
    y1 = min(int(np.max(ys)) + boundary_size + 1, h)
    x0 = max(int(np.min(xs)) - boundary_size - 1, 0)
    x1 = min(int(np.max(xs)) + boundary_size + 1, w)
    return y0, y1, x0, x1


# ==========================================================================
# Alpha + blend-factor initialisation (ported).
# ==========================================================================
def estimate_normalized_alpha(j_stack, w_m, num_images=None, threshold=170,
                              invert=False, adaptive=False,
                              adaptive_threshold=21, c2=10):
    """Per-image closed-form matte against a thresholded W seed, then median."""
    if num_images is None:
        num_images = j_stack.shape[0]
    wm_avg = (255 * normalize01(np.average(w_m, axis=2))).astype(np.uint8)
    if adaptive:
        thr = cv2.adaptiveThreshold(wm_avg, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, adaptive_threshold, c2)
    else:
        _ret, thr = cv2.threshold(wm_avg, threshold, 255, cv2.THRESH_BINARY)
    if invert:
        thr = 255 - thr
    thr = np.stack([thr, thr, thr], axis=2).astype(np.float64)

    _num, m, n, _p = j_stack.shape
    alpha = np.zeros((num_images, m, n))
    for idx in range(num_images):
        alpha[idx] = closed_form_matte(j_stack[idx], thr)
    return np.median(alpha, axis=0)


def estimate_filled_alpha(j_stack, median_blur_k=21, blur_k=3, eps=1.0):
    """FILLED continuous alpha for a bright (near-white) semi-transparent mark.

    The closed-form-matte seed (estimate_normalized_alpha) thresholds a weak
    Poisson W_m and captures only glyph EDGES - the resulting hollow matte makes
    the matting inversion act on edges alone (a chromatic halo). This estimates a
    FILLED matte instead, via cross-image whitening (the validated glyph15
    method): for a white overlay J = a*255 + (1-a)*I, the local excess brightness
    over the background gives a ~ (gray - bg) / (255 - bg). Median across the
    cluster keeps the common mark and cancels per-image art. Returns [0,1].
    """
    mats = []
    for j in j_stack:
        gray = np.average(j, axis=2)
        gray_u8 = np.clip(gray, 0, 255).astype(np.uint8)
        bg = cv2.medianBlur(gray_u8, median_blur_k).astype(np.float64)
        whiten = np.clip((gray - bg) / np.clip(255.0 - bg, eps, None), 0.0, 1.0)
        mats.append(whiten)
    shape = np.median(np.array(mats), axis=0)
    if blur_k and blur_k >= 3:
        shape = cv2.GaussianBlur(shape, (blur_k, blur_k), 0)
    return np.clip(shape, 0.0, 1.0)


def estimate_blend_factor(j_stack, w_m, alph, ksize=KERNEL_SIZE):
    """Per-channel blend factor C matching Dekel's supplementary (ported)."""
    k = j_stack.shape[0]
    jm = j_stack - w_m
    gx_jm = np.zeros(j_stack.shape)
    gy_jm = np.zeros(j_stack.shape)
    for i in range(k):
        gx_jm[i] = cv2.Sobel(jm[i], cv2.CV_64F, 1, 0, ksize)
        gy_jm[i] = cv2.Sobel(jm[i], cv2.CV_64F, 0, 1, ksize)
    jm_grad = np.sqrt(gx_jm ** 2 + gy_jm ** 2)

    est_ik = alph * np.median(j_stack, axis=0)
    gx_est = cv2.Sobel(est_ik, cv2.CV_64F, 1, 0, ksize)
    gy_est = cv2.Sobel(est_ik, cv2.CV_64F, 0, 1, ksize)
    est_grad = np.sqrt(gx_est ** 2 + gy_est ** 2)

    c = []
    for i in range(3):
        num = np.sum(jm_grad[:, :, :, i] * est_grad[:, :, i])
        den = np.sum(np.square(est_grad[:, :, i])) * k
        c.append(num / den if den > 1e-12 else 1.0)
    return c, est_ik


# ==========================================================================
# IRLS alternating solver (ported from solve_images; matplotlib stripped).
# ==========================================================================
def _phi(x, epsilon=1e-3):
    return np.sqrt(x + epsilon ** 2)


def _phi_deriv(x, epsilon=1e-3):
    return 0.5 / _phi(x, epsilon)


def _solve_linear(a, b, solver="spsolve", rtol=1e-4, maxiter=3000):
    """Solve a x = b for a sparse symmetric a. Solver in {spsolve, cg, lsqr}."""
    a = a.tocsr()
    if solver == "spsolve":
        return spla.spsolve(a, b)
    if solver == "cg":
        diag = a.diagonal()
        diag[np.abs(diag) < 1e-12] = 1.0
        m_pre = spla.LinearOperator(a.shape, matvec=lambda v: v / diag)
        x, _info = spla.cg(a, b, rtol=rtol, atol=0.0, maxiter=maxiter, M=m_pre)
        return x
    if solver == "lsqr":
        return spla.lsqr(a, b, atol=rtol, btol=rtol, iter_lim=maxiter)[0]
    raise ValueError(f"unknown solver {solver!r} (expected spsolve|cg|lsqr)")


def solve_images(j_stack, w_m, alpha, w_init, gamma=1, beta=1, lambda_w=0.005,
                 lambda_i=1, lambda_a=0.01, iters=4, solver="spsolve",
                 debug_dir=None, log=print, step_timer=None, clip_alpha=False,
                 clip_w=None):
    """Dekel master solver: alternate (Step1) per-image W_k/I_k decomposition,
    (Step2) W = median(W_k), (Step3) alpha via the matting Laplacian.

    Linear algebra is identical to the scaffold; the only changes are the
    swappable linear solver, optional debug-PNG dumps replacing plt.*, and an
    optional physical projection of the solved matte back to [0, 1] each iter
    (clip_alpha - the unconstrained sparse solve can overshoot, and alpha is an
    opacity so values outside [0, 1] are non-physical and blow up the matting
    inversion 1/(1-alpha); projecting is the standard IRLS-with-box-constraint
    step, not invention).
    """
    k, m, n, p = j_stack.shape
    size = m * n * p

    sobelx = get_xSobel_matrix(m, n, p)
    sobely = get_ySobel_matrix(m, n, p)
    i_k = np.zeros(j_stack.shape)
    w_k = np.zeros(j_stack.shape)
    for i in range(k):
        i_k[i] = j_stack[i] - w_m
        w_k[i] = w_init.copy()
    w = w_init.copy()

    for it in range(iters):
        log(f"[solve] iter {it + 1}/{iters} step1")
        alpha_gx = cv2.Sobel(alpha, cv2.CV_64F, 1, 0, 3)
        alpha_gy = cv2.Sobel(alpha, cv2.CV_64F, 0, 1, 3)
        wm_gx = cv2.Sobel(w_m, cv2.CV_64F, 1, 0, 3)
        wm_gy = cv2.Sobel(w_m, cv2.CV_64F, 0, 1, 3)

        cx = sp.diags(np.abs(alpha_gx).reshape(-1))
        cy = sp.diags(np.abs(alpha_gy).reshape(-1))
        alpha_diag = sp.diags(alpha.reshape(-1))
        alpha_bar_diag = sp.diags((1 - alpha).reshape(-1))

        for i in range(k):
            t0 = time.time()
            wkx = cv2.Sobel(w_k[i], cv2.CV_64F, 1, 0, 3)
            wky = cv2.Sobel(w_k[i], cv2.CV_64F, 0, 1, 3)
            ikx = cv2.Sobel(i_k[i], cv2.CV_64F, 1, 0, 3)
            iky = cv2.Sobel(i_k[i], cv2.CV_64F, 0, 1, 3)

            alpha_wk = alpha * w_k[i]
            alpha_wk_gx = cv2.Sobel(alpha_wk, cv2.CV_64F, 1, 0, 3)
            alpha_wk_gy = cv2.Sobel(alpha_wk, cv2.CV_64F, 0, 1, 3)

            phi_data = sp.diags(_phi_deriv(np.square(
                alpha * w_k[i] + (1 - alpha) * i_k[i] - j_stack[i]).reshape(-1)))
            phi_f = sp.diags(_phi_deriv(
                ((wm_gx - alpha_wk_gx) ** 2 + (wm_gy - alpha_wk_gy) ** 2).reshape(-1)))
            phi_aux = sp.diags(_phi_deriv(np.square(w_k[i] - w).reshape(-1)))
            phi_r_i = sp.diags(_phi_deriv(
                np.abs(alpha_gx) * (ikx ** 2) + np.abs(alpha_gy) * (iky ** 2)).reshape(-1))
            phi_r_w = sp.diags(_phi_deriv(
                np.abs(alpha_gx) * (wkx ** 2) + np.abs(alpha_gy) * (wky ** 2)).reshape(-1))

            l_i = sobelx.T.dot(cx * phi_r_i).dot(sobelx) + sobely.T.dot(cy * phi_r_i).dot(sobely)
            l_w = sobelx.T.dot(cx * phi_r_w).dot(sobelx) + sobely.T.dot(cy * phi_r_w).dot(sobely)
            l_f = sobelx.T.dot(phi_f).dot(sobelx) + sobely.T.dot(phi_f).dot(sobely)
            a_f = alpha_diag.T.dot(l_f).dot(alpha_diag) + gamma * phi_aux

            b_w = (alpha_diag.dot(phi_data).dot(j_stack[i].reshape(-1))
                   + beta * l_f.dot(w_m.reshape(-1))
                   + gamma * phi_aux.dot(w.reshape(-1)))
            b_i = alpha_bar_diag.dot(phi_data).dot(j_stack[i].reshape(-1))

            a = sp.vstack([
                sp.hstack([(alpha_diag ** 2) * phi_data + lambda_w * l_w + beta * a_f,
                           alpha_diag * alpha_bar_diag * phi_data]),
                sp.hstack([alpha_diag * alpha_bar_diag * phi_data,
                           (alpha_bar_diag ** 2) * phi_data + lambda_i * l_i]),
            ]).tocsr()
            b = np.hstack([b_w, b_i])
            x = _solve_linear(a, b, solver=solver)
            w_k[i] = x[:size].reshape(m, n, p)
            i_k[i] = x[size:].reshape(m, n, p)
            if clip_w is not None:
                np.clip(w_k[i], clip_w[0], clip_w[1], out=w_k[i])
            dt = time.time() - t0
            if step_timer is not None:
                step_timer.append(dt)
            log(f"[solve]   step1 image {i} solved in {dt:.1f}s")

        log(f"[solve] iter {it + 1}/{iters} step2 (W = median W_k)")
        w = np.median(w_k, axis=0)

        log(f"[solve] iter {it + 1}/{iters} step3 (alpha)")
        w_diag = sp.diags(w.reshape(-1))
        a1 = b1 = None
        for i in range(k):
            alpha_wk = alpha * w_k[i]
            alpha_wk_gx = cv2.Sobel(alpha_wk, cv2.CV_64F, 1, 0, 3)
            alpha_wk_gy = cv2.Sobel(alpha_wk, cv2.CV_64F, 0, 1, 3)
            phi_f = sp.diags(_phi_deriv(
                ((wm_gx - alpha_wk_gx) ** 2 + (wm_gy - alpha_wk_gy) ** 2).reshape(-1)))
            phi_k_a = sp.diags((
                _phi_deriv((alpha * w_k[i] + (1 - alpha) * i_k[i] - j_stack[i]) ** 2)
                * ((w - i_k[i]) ** 2)).reshape(-1))
            phi_k_b = (
                _phi_deriv((alpha * w_k[i] + (1 - alpha) * i_k[i] - j_stack[i]) ** 2)
                * (w - i_k[i]) * (j_stack[i] - i_k[i])).reshape(-1)
            phi_alpha = sp.diags(_phi_deriv(alpha_gx ** 2 + alpha_gy ** 2).reshape(-1))
            l_alpha = sobelx.T.dot(phi_alpha.dot(sobelx)) + sobely.T.dot(phi_alpha.dot(sobely))
            l_f = sobelx.T.dot(phi_f).dot(sobelx) + sobely.T.dot(phi_f).dot(sobely)
            a_tilde_f = w_diag.T.dot(l_f).dot(w_diag)
            if a1 is None:
                a1 = phi_k_a + lambda_a * l_alpha + beta * a_tilde_f
                b1 = phi_k_b + beta * w_diag.dot(l_f).dot(w_m.reshape(-1))
            else:
                a1 = a1 + (phi_k_a + lambda_a * l_alpha + beta * a_tilde_f)
                b1 = b1 + (phi_k_b + beta * w_diag.T.dot(l_f).dot(w_m.reshape(-1)))
        alpha = _solve_linear(a1, b1, solver=solver).reshape(m, n, p)
        if clip_alpha:
            alpha = np.clip(alpha, 0.0, 1.0)

        if debug_dir is not None:
            _atomic_write_png(os.path.join(debug_dir, f"_solve_iter{it + 1}_W.png"),
                              _to_u8(normalize01(w)))
            _atomic_write_png(os.path.join(debug_dir, f"_solve_iter{it + 1}_alpha.png"),
                              _to_u8(np.clip(alpha, 0, 1)))
    return w_k, i_k, w, alpha


# ==========================================================================
# THE ADDED PIECE: sub-pixel per-image alignment.
# ==========================================================================
def mark_signal(roi):
    """Background-invariant mark signal = channel-averaged gradient magnitude.

    The repeated mark is the gradient structure common to every frame; per-image
    art gradients differ and cancel under the median, the mark's do not.
    """
    r = np.asarray(roi, dtype=np.float64)
    gx = cv2.Sobel(r, cv2.CV_64F, 1, 0, ksize=KERNEL_SIZE)
    gy = cv2.Sobel(r, cv2.CV_64F, 0, 1, ksize=KERNEL_SIZE)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    return np.average(mag, axis=2) if mag.ndim == 3 else mag


def estimate_shift(reference, moving, upsample=20, normalization=None):
    """Sub-pixel (dy, dx) that registers `moving` onto `reference`.

    Wraps skimage phase_cross_correlation. The returned (dy, dx) is applied to
    `moving` via cv2.warpAffine translation (tx=dx, ty=dy) to align it.

    normalization=None (plain cross-correlation, the default here) is deliberate:
    the library default 'phase' whitens the spectrum and collapses to a near-zero
    (wrong) peak on smooth, low-frequency content like a mark signal - measured
    this session recovering a known shift to < 0.06 px with None vs total failure
    with 'phase'. Pass normalization='phase' only for broadband inputs.
    """
    shift, _err, _pd = phase_cross_correlation(
        np.asarray(reference, np.float64), np.asarray(moving, np.float64),
        upsample_factor=upsample, normalization=normalization)
    return float(shift[0]), float(shift[1])


def align_rois(rois, upsample=20, use_ecc=False):
    """Align each ROI so the shared mark registers to the cluster reference.

    Returns (aligned_rois, forward_affines, inverse_affines, shifts). Reference =
    median of the per-image mark signals (mark survives, art cancels). Default is
    translation-only (robust + unit-tested); ECC affine refinement is opt-in and
    guarded (falls back to translation on any failure).
    """
    marks = [mark_signal(r) for r in rois]
    ref = np.median(np.array(marks), axis=0)
    aligned, fwd, inv, shifts = [], [], [], []
    for roi, mk in zip(rois, marks):
        dy, dx = estimate_shift(ref, mk, upsample=upsample)
        m_fwd = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy]], dtype=np.float64)
        if use_ecc:
            try:
                crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-5)
                warp = m_fwd.astype(np.float32)
                _cc, warp = cv2.findTransformECC(
                    ref.astype(np.float32), mk.astype(np.float32), warp,
                    cv2.MOTION_AFFINE, crit, None, 5)
                m_fwd = warp.astype(np.float64)
            except cv2.error:
                pass  # keep the translation estimate
        h, w = roi.shape[:2]
        a = cv2.warpAffine(roi, m_fwd, (w, h), flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_REFLECT)
        aligned.append(a)
        fwd.append(m_fwd)
        inv.append(cv2.invertAffineTransform(m_fwd))
        shifts.append((dy, dx))
    return aligned, fwd, inv, shifts


# ==========================================================================
# Reconstruction (matting inversion) + paste-back.
# ==========================================================================
def invert_matting(j, alpha, w, eps=1e-3):
    """I = (J - alpha*W)/(1 - alpha), alpha clipped to [0, 1-eps].

    Where alpha ~ 0 the result equals J (no change) - faithful recovery, not a
    fill. Exact inverse of J = alpha*W + (1-alpha)*I wherever alpha < 1.
    """
    a = np.clip(np.asarray(alpha, np.float64), 0.0, 1.0 - eps)
    jf = np.asarray(j, np.float64)
    wf = np.asarray(w, np.float64)
    return (jf - a * wf) / (1.0 - a)


# ==========================================================================
# Low-frequency ghost metric + faithful post-correction of the IRLS art.
# ==========================================================================
def _surround_inpaint(luma, template, thr=0.1, dilate_iter=2):
    """Clean local surround: inpaint the glyph region from OUTSIDE the dilated
    mark mask (never from the ghost itself) - a trend-free 'what the art would be
    with no mark' reference for the low-frequency ghost score."""
    mask = cv2.dilate((np.asarray(template) > thr).astype(np.uint8),
                      cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
                      iterations=dilate_iter)
    src = np.clip(np.asarray(luma, np.float64), 0, 255).astype(np.uint8)
    return cv2.inpaint(src, mask, 5, cv2.INPAINT_TELEA).astype(np.float64)


def ghost_lf(clean_bgr, template, thr=0.2):
    """Low-FREQUENCY ghost score (the metric a high-pass edge check misses).

    Correlates the glyph template with the cleaned luma-drop over template>thr,
    where the drop is measured against an inpaint-from-outside surround (never the
    ghost). Returns (corr, slope, mag):
      corr  ~0 => no glyph-shaped low-freq residual; +ve = residual brighter than
            surround (white/under-subtract), -ve = darker (dark ghost/over-sub).
      slope luma units per unit alpha (same sign convention).
      mag   mean|luma - surround| at glyph cores (template>0.35), luma units.
    Validated on a synthetic: corr, slope and the true recovery bias all null
    together at the correct alpha, with a monotonic sign flip around it. A clean
    low-freq result needs corr~0 AND slope~0; note a residual HIGH-freq stroke
    ghost can still be eye-legible at corr~0 (always eyeball too)."""
    template = np.asarray(template, np.float64)
    g = np.asarray(clean_bgr, np.float64).mean(axis=2)
    resid = g - _surround_inpaint(g, template)
    core = template > thr
    if int(core.sum()) < 20:
        return 0.0, 0.0, 0.0
    t = template[core] - template[core].mean()
    r = resid[core] - resid[core].mean()
    den = float(np.linalg.norm(t) * np.linalg.norm(r))
    corr = float(np.dot(t, r) / den) if den > 1e-9 else 0.0
    slope = float(np.dot(t, r) / max(float(np.dot(t, t)), 1e-9))
    body = template > 0.35
    mag = float(np.abs(resid[body]).mean()) if int(body.sum()) > 10 else 0.0
    return corr, slope, mag


def derainbow_deghost(j, i_recon, template, k_max=60.0):
    """Faithful post-correction of the IRLS per-image art estimate i_recon.

    Two non-generative corrections (no fill, no invention):
      1. DE-RAINBOW: the mark is achromatic, so per-channel divergence baked into
         i_recon (the IRLS solves W_k / i_k per channel) is an artifact. Recolour
         J to i_recon's luma - chroma comes from J, so no per-channel rainbow can
         survive by construction; the only colour change is faithful desaturation
         under the (white) mark, never invented colour.
      2. DE-GHOST: i_recon over-subtracts the mark by a glyph-proportional low-freq
         luma bias. Estimate it by regressing (clean surround - i_recon luma) on
         the template and add back k*template - an algebraic level correction that
         restores the over-removed level while carrying i_recon's high-frequency
         detail through untouched. Self-calibrating (k per cluster), clamped.

    Nulls the low-frequency ghost_lf and removes the rainbow; it does NOT erase a
    residual high-frequency stroke ghost (that is entangled with real art detail
    and cannot be separated without inpainting - see the module R&D verdict).
    Where template ~ 0 the output equals J (identity outside the mark support)."""
    j = np.asarray(j, np.float64)
    tmpl = np.clip(np.asarray(template, np.float64), 0.0, 1.0)
    l_ik = np.asarray(i_recon, np.float64).mean(axis=2)
    surround = _surround_inpaint(l_ik, tmpl)
    core = tmpl > 0.2
    if int(core.sum()) > 20:
        t = tmpl[core] - tmpl[core].mean()
        d = (surround - l_ik)[core]
        d = d - d.mean()
        k = float(np.dot(t, d) / max(float(np.dot(t, t)), 1e-9))
        k = float(np.clip(k, 0.0, k_max))
    else:
        k = 0.0
    l_target = l_ik + k * tmpl
    l_j = np.clip(j.mean(axis=2), 1e-3, None)
    ratio = np.clip(l_target / l_j, 0.0, 4.0)[:, :, None]
    return np.clip(j * ratio, 0.0, 255.0)


def paste_back(inp_arr, result_arr, mask):
    """out = where(inside-mask, result, inp); OUTSIDE stays byte-identical."""
    inp = np.asarray(inp_arr)
    result = np.asarray(result_arr)
    binary = _as_binary(mask)
    if inp.ndim == 3 and binary.ndim == 2:
        binary = binary[:, :, None]
    return np.where(binary, result, inp).astype(inp.dtype)


def assert_outside_identity(inp_arr, final_arr, mask):
    """Raise unless final == inp on every pixel OUTSIDE the mask (tripwire)."""
    inp = np.asarray(inp_arr)
    final = np.asarray(final_arr)
    binary = _as_binary(mask)
    if inp.ndim == 3 and binary.ndim == 2:
        binary = binary[:, :, None]
    outside = ~np.broadcast_to(binary, inp.shape)
    if not np.array_equal(final[outside], inp[outside]):
        raise AssertionError(
            "Dekel clean pass mutated pixels OUTSIDE the mask "
            "(paste-back identity violated)")


def _dilate_mask(mask_bool, iterations=3):
    """Dilate a boolean mask by a few px (bounds where pixels may change)."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    d = cv2.dilate(mask_bool.astype(np.uint8), k, iterations=iterations)
    return d.astype(bool)


# ==========================================================================
# I/O (atomic writes per the project hard rule).
# ==========================================================================
def _to_u8(arr01):
    return np.clip(np.asarray(arr01, np.float64) * 255.0, 0, 255).astype(np.uint8)


def _atomic_write_png(path, bgr_or_gray):
    tmp = path + ".tmp.png"
    ok = cv2.imwrite(tmp, bgr_or_gray)
    if not ok:
        raise OSError(f"cv2.imwrite failed for {tmp}")
    os.replace(tmp, path)


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fo:
        fo.write(json.dumps(data, indent=2) + "\n")
        fo.flush()
        os.fsync(fo.fileno())
    os.replace(tmp, path)


# ==========================================================================
# Cluster orchestration.
# ==========================================================================
def solve_cluster(images, region=DEFAULT_REGION, pad=DEFAULT_PAD, iters=4,
                  solver="spsolve", debug_dir=None, slugs=None,
                  bbox_threshold=0.4, alpha_threshold=170, apply_blend=False,
                  use_ecc=False, alpha_init="filled", post_correct=True,
                  log=print):
    """Full Dekel solve for one cluster; writes debug PNGs + timing when asked.

    images: list of full-frame BGR uint8 arrays (same size). Returns a dict of
    results (W, alpha, per-image reconstruction + roi crops + geometry + timing).
    """
    np.random.seed(0)
    timing = {"solver": solver, "iters": iters, "n_images": len(images)}
    t_all = time.time()
    if slugs is None:
        slugs = [f"img{i}" for i in range(len(images))]
    if debug_dir is not None:
        os.makedirs(debug_dir, exist_ok=True)

    h_img, w_img = images[0].shape[:2]
    x0, y0, x1, y1 = region
    rx0, ry0 = max(x0 - pad, 0), max(y0 - pad, 0)
    rx1, ry1 = min(x1 + pad, w_img), min(y1 + pad, h_img)
    rois = [im[ry0:ry1, rx0:rx1, :].astype(np.float64) for im in images]
    log(f"[cluster] ROI x[{rx0}:{rx1}] y[{ry0}:{ry1}] size {rois[0].shape}")

    t0 = time.time()
    aligned, _fwd, inv, shifts = align_rois(rois, use_ecc=use_ecc)
    timing["align_s"] = time.time() - t0
    log("[cluster] alignment shifts (dy,dx): "
        + ", ".join(f"({dy:+.2f},{dx:+.2f})" for dy, dx in shifts))

    t0 = time.time()
    wm_x, wm_y, _gx, _gy = estimate_watermark_gradients(aligned)
    bbox = mark_bbox_from_gradient(wm_x, wm_y, threshold=bbox_threshold)
    if bbox is None:
        raise RuntimeError("mark bbox empty - lower bbox_threshold")
    by0, by1, bx0, bx1 = bbox
    timing["mark_bbox"] = [by0, by1, bx0, bx1]
    timing["mark_bbox_hw"] = [by1 - by0, bx1 - bx0]
    log(f"[cluster] tight mark bbox y[{by0}:{by1}] x[{bx0}:{bx1}] "
        f"-> {by1 - by0}x{bx1 - bx0}")

    j_stack = np.array([a[by0:by1, bx0:bx1, :] for a in aligned])
    wm_x_t = wm_x[by0:by1, bx0:bx1, :]
    wm_y_t = wm_y[by0:by1, bx0:bx1, :]
    w_m = poisson_reconstruct_multichannel(wm_x_t, wm_y_t, np.zeros_like(wm_x_t))
    timing["gradseed_s"] = time.time() - t0

    t0 = time.time()
    if alpha_init == "filled":
        alpha_n = estimate_filled_alpha(j_stack)
    else:
        alpha_n = estimate_normalized_alpha(j_stack, w_m, threshold=alpha_threshold)
    timing["alpha_init"] = alpha_init
    alpha = np.stack([alpha_n, alpha_n, alpha_n], axis=2)
    if apply_blend:
        try:
            c, _est = estimate_blend_factor(j_stack, w_m, alpha)
            for ci in range(3):
                alpha[:, :, ci] = np.clip(c[ci] * alpha[:, :, ci], 0, 1)
            timing["blend_C"] = [float(v) for v in c]
        except Exception as exc:  # noqa: BLE001 - blend is a refinement; degrade to C=1
            log(f"[cluster] blend factor skipped: {exc}")
    timing["alpha_init_s"] = time.time() - t0

    # W_init MUST be a full-watermark-scale estimate (~the mark's own colour,
    # near-white here), NOT the matted watermark w_m. The scaffold builds it as
    # (w_m - w_m.min() + alpha*median(J)) / C (main.py L24/35/37) - the port had
    # regressed to passing raw w_m (min ~ -900, DC-less Poisson output), which
    # made the data term alpha*W_k + (1-alpha)*I_k = J and the Step-3 update
    # alpha=(J-I)/(W-I) ill-conditioned: W-I ~ 0 drove alpha to [-20, 6] and the
    # reconstruction 1/(1-alpha) exploded (the rainbow). Restore the scaffold
    # init (DC-shifted, image-contribution added, blend-normalised), clipped to a
    # physical [0, 255] colour range.
    w_m_shift = w_m - w_m.min()
    med_j = np.median(j_stack, axis=0)
    c_proxy = max(float(np.average(alpha, axis=2).mean()) * 3.0, 0.3)
    w_init = np.clip((w_m_shift + alpha * med_j) / c_proxy, 0.0, 255.0)
    timing["w_init_mean"] = float(w_init.mean())

    step_timer = []
    t0 = time.time()
    w_k, i_k, w_solved, alpha_solved = solve_images(
        j_stack, w_m, alpha, w_init, iters=iters, solver=solver,
        debug_dir=debug_dir, log=log, step_timer=step_timer, clip_alpha=True)
    timing["solve_s"] = time.time() - t0
    timing["step1_solve_times_s"] = [round(v, 2) for v in step_timer]

    # Alpha-support mask (aligned frame): where the matte actually acts.
    alpha_gray = np.clip(np.average(alpha_solved, axis=2), 0, 1)
    support_aligned = _dilate_mask(alpha_gray > 0.05)

    results = {"slugs": list(slugs), "shifts": shifts, "timing": timing,
               "reconstructions": {}}
    hroi, wroi = rois[0].shape[:2]
    for i, slug in enumerate(slugs):
        # The clean frame is the solver's own I_k (scaffold-faithful: main.py
        # displays Ik as the result). The port previously re-derived it as
        # invert_matting(J, alpha_solved, w_solved) - but the unconstrained
        # solved alpha reaches ~1 and 1/(1-alpha) blew up to +/-1e6 (the rainbow
        # speckle). I_k is the regularised decomposition output and stays bounded.
        # A direct matting inversion was re-checked in push-2 and left a WORSE
        # bright-outline residual (the stylised mark has a dark outline a single
        # achromatic W cannot invert), so I_k remains the base. post_correct then
        # applies the faithful de-rainbow + low-freq de-ghost on top (see
        # derainbow_deghost): it nulls the low-freq ghost_lf and kills the rainbow
        # without any fill. Embed into a full-ROI aligned canvas, inverse-warp to
        # this image's geometry, composite under the (inverse-warped) support mask.
        i_recon = i_k[i]
        if post_correct:
            i_recon = derainbow_deghost(j_stack[i], i_recon, alpha_n)
        recon_aligned = aligned[i].copy()
        recon_aligned[by0:by1, bx0:bx1, :] = i_recon

        support_roi_aligned = np.zeros((hroi, wroi), dtype=np.uint8)
        support_roi_aligned[by0:by1, bx0:bx1] = support_aligned.astype(np.uint8) * 255

        recon_roi = cv2.warpAffine(recon_aligned, inv[i], (wroi, hroi),
                                   flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        support_roi = cv2.warpAffine(support_roi_aligned, inv[i], (wroi, hroi),
                                     flags=cv2.INTER_NEAREST) > 127

        recon_roi_u8 = np.clip(recon_roi, 0, 255).astype(np.uint8)
        full_out = images[i].copy()
        region_in = full_out[ry0:ry1, rx0:rx1, :]
        region_out = paste_back(region_in, recon_roi_u8, support_roi)
        full_out[ry0:ry1, rx0:rx1, :] = region_out

        full_mask = np.zeros((h_img, w_img), dtype=bool)
        full_mask[ry0:ry1, rx0:rx1] = support_roi
        assert_outside_identity(images[i], full_out, full_mask)

        # Low-freq ghost_lf before/after, measured in the aligned tight-bbox space
        # where the glyph template (alpha_n) is defined (the warp-back is geometry
        # only and does not create or remove the ghost).
        gc_b, gs_b, gm_b = ghost_lf(j_stack[i], alpha_n)
        gc_a, gs_a, gm_a = ghost_lf(i_recon, alpha_n)
        results.setdefault("metrics", {})[slug] = {
            "ghost_lf_corr_before": round(gc_b, 4),
            "ghost_lf_corr_after": round(gc_a, 4),
            "ghost_lf_slope_before": round(gs_b, 2),
            "ghost_lf_slope_after": round(gs_a, 2),
            "ghost_lf_mag_before": round(gm_b, 2),
            "ghost_lf_mag_after": round(gm_a, 2),
        }

        results["reconstructions"][slug] = {
            "full": full_out,
            "roi_before": images[i][ry0:ry1, rx0:rx1, :].copy(),
            "roi_after": region_out,
            "solver_ik": i_k[i],
        }

    results["W"] = w_solved
    results["alpha"] = alpha_solved
    timing["total_s"] = time.time() - t_all

    if debug_dir is not None:
        _write_cluster_debug(results, debug_dir, w_solved, alpha_solved, j_stack, i_k)
    return results


def _write_cluster_debug(results, debug_dir, w_solved, alpha_solved, j_stack, i_k):
    """Write W / alpha / per-slug recon + roi before/after + timing.json."""
    _atomic_write_png(os.path.join(debug_dir, "W.png"), _to_u8(normalize01(w_solved)))
    _atomic_write_png(os.path.join(debug_dir, "alpha.png"),
                      _to_u8(np.clip(np.average(alpha_solved, axis=2), 0, 1)))
    for i, slug in enumerate(results["slugs"]):
        r = results["reconstructions"][slug]
        _atomic_write_png(os.path.join(debug_dir, f"{slug}_recon.png"), r["full"])
        _atomic_write_png(os.path.join(debug_dir, f"{slug}_roi_before.png"), r["roi_before"])
        _atomic_write_png(os.path.join(debug_dir, f"{slug}_roi_after.png"), r["roi_after"])
        _atomic_write_png(os.path.join(debug_dir, f"{slug}_solver_ik.png"),
                          _to_u8(normalize01(i_k[i])))
    _atomic_write_json(os.path.join(debug_dir, "timing.json"), results["timing"])
    if "metrics" in results:
        _atomic_write_json(os.path.join(debug_dir, "metrics.json"), results["metrics"])


def load_namakx():
    """Load the 5 namakx <slug>_cleaninitial.png inputs (BGR uint8)."""
    images, slugs = [], []
    for slug in NAMAKX_SLUGS:
        path = os.path.join(CLEAN_SCRATCH, slug, f"{slug}_cleaninitial.png")
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(f"namakx input missing: {path}")
        images.append(img)
        slugs.append(slug)
    return images, slugs


# ==========================================================================
# CLI.
# ==========================================================================
def _parse_region(text):
    parts = [int(v) for v in text.split(",")]
    if len(parts) != 4:
        raise ValueError("region must be x0,y0,x1,y1")
    return tuple(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Dekel multi-image watermark remover (Stage-2 cleaning R&D).")
    ap.add_argument("--cluster", choices=["namakx"],
                    help="named cluster to solve (loads its 5 slugs)")
    ap.add_argument("--images", help="comma-separated image paths (generic mode)")
    ap.add_argument("--region", type=_parse_region, default=None,
                    help="watermark region x0,y0,x1,y1 (default namakx region)")
    ap.add_argument("--pad", type=int, default=DEFAULT_PAD)
    ap.add_argument("--iters", type=int, default=3,
                    help="alternating IRLS iterations (3 = validated namakx "
                         "config; more iters flatten the glyph-band art)")
    ap.add_argument("--solver", choices=["spsolve", "cg", "lsqr"], default="cg",
                    help="cg = validated fast default; spsolve = exact reference")
    ap.add_argument("--bbox-threshold", type=float, default=0.4)
    ap.add_argument("--alpha-threshold", type=int, default=170)
    ap.add_argument("--blend", action="store_true",
                    help="enable Dekel blend-factor alpha scaling (default OFF; "
                         "it over-amplified the matte on namakx)")
    ap.add_argument("--alpha-init", choices=["filled", "matte"], default="filled",
                    help="filled = cross-image whitening seed (default, fills "
                         "glyph bodies); matte = closed-form-matte edge seed")
    ap.add_argument("--no-post-correct", dest="post_correct", action="store_false",
                    help="disable the faithful de-rainbow + low-freq de-ghost post "
                         "-correction of I_k (default ON; nulls low-freq ghost_lf "
                         "+ kills the rainbow without any fill)")
    ap.add_argument("--ecc", action="store_true", help="opt-in ECC affine refine")
    ap.add_argument("--debug-dir", default=None,
                    help="output dir (default the namakx scratchpad dir)")
    args = ap.parse_args(argv)

    if args.cluster == "namakx":
        images, slugs = load_namakx()
        region = args.region or DEFAULT_REGION
        debug_dir = args.debug_dir or _SCRATCH_DEBUG
    elif args.images:
        paths = [p for p in args.images.split(",") if p]
        images, slugs = [], []
        for p in paths:
            img = cv2.imread(p, cv2.IMREAD_COLOR)
            if img is None:
                raise FileNotFoundError(f"image missing: {p}")
            images.append(img)
            slugs.append(os.path.splitext(os.path.basename(p))[0])
        region = args.region or DEFAULT_REGION
        debug_dir = args.debug_dir or _SCRATCH_DEBUG
    else:
        ap.error("provide --cluster namakx or --images a.png,b.png,...")

    res = solve_cluster(
        images, region=region, pad=args.pad, iters=args.iters, solver=args.solver,
        debug_dir=debug_dir, slugs=slugs, bbox_threshold=args.bbox_threshold,
        alpha_threshold=args.alpha_threshold, apply_blend=args.blend,
        use_ecc=args.ecc, alpha_init=args.alpha_init, post_correct=args.post_correct)
    print(json.dumps({"done": True, "debug_dir": debug_dir,
                      "timing": res["timing"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
