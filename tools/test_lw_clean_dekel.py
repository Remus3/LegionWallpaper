"""Unit tests for tools/lw_clean_dekel.py (Dekel multi-image watermark remover).

Runs under the lw-clean venv (numpy / scipy / cv2 / skimage). Lives in tools/
(NOT tests/) on purpose: it needs cv2 + skimage + scipy.sparse which the CI
tests/ dir (system Python314, stdlib+numpy only) cannot import, and it is the
sibling of the module it exercises. Pure-math coverage only - no cluster solve,
no disk I/O of real images.

Run:
  C:\\Tools\\lw-clean\\venv\\Scripts\\python.exe -m pytest tools/test_lw_clean_dekel.py -q
"""
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_dekel as dekel  # noqa: E402


# ---------------------------------------------------------------------------
# 1. poisson_reconstruct2 round-trips a smooth field (grad -> reconstruct).
# ---------------------------------------------------------------------------
def test_poisson_reconstruct2_roundtrips_smooth_field():
    # Smooth low-frequency field (gentle plane + long-period sinusoid). The DST
    # Dirichlet solver pushes its boundary-correction error into a ~2 px frame
    # just inside the edge (documented artifact of this solver), so the honest
    # round-trip check is on the interior.
    h, w = 48, 56
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    z = 0.20 * xx + 0.15 * yy + 2.0 * np.sin(xx / 22.0) + 1.5 * np.cos(yy / 26.0)
    gy, gx = np.gradient(z)
    rec = dekel.poisson_reconstruct2(gx, gy, z.copy())
    b = slice(3, -3)
    a = rec[b, b].ravel() - rec[b, b].mean()
    c = z[b, b].ravel() - z[b, b].mean()
    corr = float(np.dot(a, c) / (np.linalg.norm(a) * np.linalg.norm(c)))
    assert corr > 0.99


# ---------------------------------------------------------------------------
# 2. alignment recovers a known sub-pixel translation within 0.2 px.
# ---------------------------------------------------------------------------
def test_alignment_recovers_subpixel_shift():
    # A structured 'mark' (two Gaussian blobs) - representative of the localised
    # watermark signal and unambiguous for sub-pixel registration.
    h = w = 80
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    base = (np.exp(-(((xx - 40) ** 2 + (yy - 44) ** 2) / 120.0))
            + 0.5 * np.exp(-(((xx - 22) ** 2 + (yy - 28) ** 2) / 40.0)))
    dx0, dy0 = -2.3, 1.7  # translation applied to build the moving image
    m_fwd = np.array([[1, 0, dx0], [0, 1, dy0]], dtype=np.float64)
    moving = cv2.warpAffine(base, m_fwd, (w, h), flags=cv2.INTER_CUBIC,
                            borderMode=cv2.BORDER_REFLECT)
    dy_est, dx_est = dekel.estimate_shift(base, moving, upsample=20)
    # estimate_shift returns the (dy, dx) that registers moving back onto base,
    # i.e. the negation of the forward translation.
    assert abs(dy_est - (-dy0)) < 0.2
    assert abs(dx_est - (-dx0)) < 0.2
    # end-to-end: applying the estimated shift recovers base on the interior.
    m_rec = np.array([[1, 0, dx_est], [0, 1, dy_est]], dtype=np.float64)
    recovered = cv2.warpAffine(moving, m_rec, (w, h), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REFLECT)
    inner = slice(10, 70)
    assert np.abs(recovered[inner, inner] - base[inner, inner]).mean() < 0.02


# ---------------------------------------------------------------------------
# 3. matting-equation inversion recovers I exactly where alpha < 1.
# ---------------------------------------------------------------------------
def test_matting_inversion_recovers_known_I():
    rng = np.random.default_rng(2)
    h, w = 16, 16
    i_true = rng.random((h, w, 3))
    w_mark = rng.random((h, w, 3))
    alpha = rng.random((h, w, 3)) * 0.8  # strictly < 1
    j = alpha * w_mark + (1.0 - alpha) * i_true
    i_rec = dekel.invert_matting(j, alpha, w_mark)
    assert np.max(np.abs(i_rec - i_true)) < 1e-6


# ---------------------------------------------------------------------------
# 4. closed_form_matte on a 2-region scribble -> ~0 one side, ~1 the other.
# ---------------------------------------------------------------------------
def test_closed_form_matte_two_region():
    rng = np.random.default_rng(3)
    h, w = 24, 24
    img = np.empty((h, w, 3), dtype=np.float64)
    img[:, :12, :] = 0.15
    img[:, 12:, :] = 0.85
    img += rng.normal(0.0, 0.01, img.shape)  # avoid degenerate flat windows
    scribble = img.copy()
    scribble[:, 0:2, :] = 0.0    # left constraint alpha=0 (differs from img)
    scribble[:, -2:, :] = 1.0    # right constraint alpha=1 (differs from img)
    alpha = dekel.closed_form_matte(img, scribble, mylambda=100)
    assert alpha[:, :4].mean() < 0.2
    assert alpha[:, -4:].mean() > 0.8


# ---------------------------------------------------------------------------
# 5. sparse Sobel operators: correct shape + match cv2.Sobel on the interior.
# ---------------------------------------------------------------------------
def test_sobel_matrices_shape_and_match_cv2():
    m, n, p = 12, 14, 1
    sx = dekel.get_xSobel_matrix(m, n, p)
    sy = dekel.get_ySobel_matrix(m, n, p)
    assert sx.shape == (m * n * p, m * n * p)
    assert sy.shape == (m * n * p, m * n * p)
    rng = np.random.default_rng(4)
    img = rng.random((m, n)).astype(np.float64)
    gx_cv = cv2.Sobel(img, cv2.CV_64F, 1, 0, ksize=3)
    gy_cv = cv2.Sobel(img, cv2.CV_64F, 0, 1, ksize=3)
    gx_sp = (sx @ img.reshape(-1)).reshape(m, n)
    gy_sp = (sy @ img.reshape(-1)).reshape(m, n)
    assert np.max(np.abs(gx_sp[1:-1, 1:-1] - gx_cv[1:-1, 1:-1])) < 1e-9
    assert np.max(np.abs(gy_sp[1:-1, 1:-1] - gy_cv[1:-1, 1:-1])) < 1e-9


# ---------------------------------------------------------------------------
# 6. paste-back outside-identity: inside may change, outside is byte-identical;
#    a forced outside change raises.
# ---------------------------------------------------------------------------
def test_paste_back_outside_identity():
    rng = np.random.default_rng(5)
    inp = (rng.random((20, 20, 3)) * 255).astype(np.uint8)
    result = (rng.random((20, 20, 3)) * 255).astype(np.uint8)
    mask = np.zeros((20, 20), dtype=bool)
    mask[5:10, 5:10] = True
    out = dekel.paste_back(inp, result, mask)
    dekel.assert_outside_identity(inp, out, mask)  # must not raise
    assert np.array_equal(out[~mask], inp[~mask])
    assert np.array_equal(out[mask], result[mask])
    bad = out.copy()
    bad[0, 0] = 255 - bad[0, 0]
    with pytest.raises(AssertionError):
        dekel.assert_outside_identity(inp, bad, mask)


# ---------------------------------------------------------------------------
# 7. ghost_lf: ~0 on clean art, strongly non-zero on a glyph-shaped mark.
# ---------------------------------------------------------------------------
def _blob_template(h, w):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    t = np.exp(-(((xx - w / 2) ** 2) / 60.0 + ((yy - h / 2) ** 2) / 60.0))
    return np.clip(t, 0.0, 1.0)


def test_ghost_lf_clean_vs_marked():
    rng = np.random.default_rng(7)
    h, w = 64, 128
    art = 110.0 + 25.0 * np.sin(np.linspace(0, 6, w))[None, :] + rng.normal(0, 3, (h, w))
    art3 = np.clip(np.stack([art] * 3, axis=-1), 0, 255)
    tmpl = _blob_template(h, w)
    marked = np.clip(art3 + (tmpl * 90.0)[:, :, None], 0, 255)   # additive white mark
    c_clean, s_clean, _ = dekel.ghost_lf(art3, tmpl)
    c_mark, s_mark, _ = dekel.ghost_lf(marked, tmpl)
    # clean art has no glyph-shaped low-freq residual; the mark does (and brighter).
    assert abs(c_clean) < 0.3
    assert c_mark > 0.5 and s_mark > 0
    assert abs(c_mark) > abs(c_clean)


# ---------------------------------------------------------------------------
# 8. derainbow_deghost: reduces a dark low-freq ghost, balances channels, and is
#    identity where the template ~ 0 (chroma from J, no lift off the mark).
# ---------------------------------------------------------------------------
def test_derainbow_deghost_reduces_ghost_and_preserves_offmask():
    rng = np.random.default_rng(8)
    h, w = 64, 128
    art = 100.0 + rng.normal(0, 4, (h, w))
    art3 = np.clip(np.stack([art] * 3, axis=-1), 0, 255)
    tmpl = _blob_template(h, w)
    j = np.clip(art3 + (tmpl * 80.0)[:, :, None], 0, 255)        # white mark added
    # i_recon: an over-subtracted (dark) estimate with a per-channel tint (rainbow).
    dark = np.clip(art3 - (tmpl * 22.0)[:, :, None], 0, 255)
    dark[:, :, 0] = np.clip(dark[:, :, 0] + tmpl * 12.0, 0, 255)  # blue cast at glyph
    out = dekel.derainbow_deghost(j, dark, tmpl)
    # off-mask (template ~ 0) output equals J (identity outside the mark support).
    off = tmpl < 0.02
    assert np.abs(out[off] - j[off]).mean() < 2.0
    # the low-freq dark ghost shrinks in magnitude.
    _, s_before, _ = dekel.ghost_lf(dark, tmpl)
    _, s_after, _ = dekel.ghost_lf(out, tmpl)
    assert abs(s_after) < abs(s_before)
    # channel spread of the removed mark (J - out) is more balanced than for the
    # rainbowed input (J - dark): the blue-cast divergence is reduced.
    core = tmpl > 0.2
    before_spread = np.std([(j - dark)[:, :, c][core].mean() for c in range(3)])
    after_spread = np.std([(j - out)[:, :, c][core].mean() for c in range(3)])
    assert after_spread <= before_spread + 1e-6
