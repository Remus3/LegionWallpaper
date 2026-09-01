"""Legion Wallpaper - measure the DA overlay matte from a hand-cleaned pair.

WHY THIS EXISTS. The DeviantArt preview overlay is two objects - a
`(c) ARTIST.DEVIANTART.COM` credit line and a large faint logo veil - and both
sit mid-frame across the subject. Every automated lane failed on them (see
`docs/CLEAN_SCRATCH_CENSUS_2026-09-01.md`), and blind matte estimation sits at
SNR ~1 because it must separate mark from art with NEITHER known - the reason
the settled ruling says not to refit that estimator on a small frame set.

A hand-cleaned frame removes exactly that obstacle. With the artwork known, the
overlay follows in closed form from the compositing model:

    obs = orig * (1 - alpha) + W * alpha        ->     alpha = (obs - orig) / (W - orig)

So one good pair MEASURES the matte where the mark is, instead of inferring it.
That is the whole point: hand work is not just cleaning one image, it is
producing the ground truth the automation was missing.

WHAT IT DOES NOT DO. It does not clean anything and it never touches pipeline
state. It reads two images and reports a matte plus the numbers that say whether
to trust it. Turning a measured matte back into a remover is the next step, and
it should be judged on frames this matte was NOT fitted on.

Import discipline mirrors the rest of the cleaning tools: numpy + PIL + stdlib
only at module level, so CI can exercise every line without torch, cv2 or a GPU.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

# Alpha below this is indistinguishable from JPEG noise in the pairs we have,
# so it is treated as "no mark here" rather than a very faint one. Measured
# against the residual floor of a hand-clean that changed nothing.
ALPHA_FLOOR = 0.02

# The mark is achromatic in every DA frame inspected so far, so the colour is
# searched as a single scalar. The grid stays coarse-to-fine rather than solving
# analytically because the objective is flat near the optimum and a closed form
# would be more precise than the data deserves.
_W_COARSE = np.arange(150.0, 256.0, 5.0)
_W_FINE_SPAN = 6.0
_W_FINE_STEP = 0.5


def _as_float(img):
    a = np.asarray(img, dtype=np.float64)
    if a.ndim == 2:
        a = a[..., None]
    return a


def composite(orig, alpha, mark_colour):
    """The forward model: lay a mark of `mark_colour` at `alpha` over `orig`.

    Kept here rather than in a test so the estimator and the model it inverts
    cannot drift apart.
    """
    orig = _as_float(orig)
    a = np.asarray(alpha, dtype=np.float64)
    if a.ndim == 2:
        a = a[..., None]
    return orig * (1.0 - a) + float(mark_colour) * a


def alpha_from_pair(before, after, mark_colour, eps: float = 8.0):
    """Per-pixel alpha from a (watermarked, hand-cleaned) pair.

    Solves the compositing model per channel and combines the channels weighted
    by |W - orig|. That weighting is the point: where the artwork already sits
    at the mark colour the channel carries no information about alpha and its
    estimate explodes, so it must count for nothing instead of being averaged in
    naively. `eps` is the denominator floor guarding exactly that case.

    Returns a float array in [0, 1] with the image's height and width.
    """
    obs = _as_float(before)
    orig = _as_float(after)
    if obs.shape != orig.shape:
        raise ValueError(f"pair shape mismatch: {obs.shape} vs {orig.shape}")
    w = float(mark_colour)

    denom = w - orig
    weight = np.abs(denom)
    safe = np.where(weight < eps, np.nan, denom)
    per_channel = (obs - orig) / safe

    weight = np.where(np.isnan(per_channel), 0.0, weight)
    per_channel = np.nan_to_num(per_channel, nan=0.0, posinf=0.0, neginf=0.0)

    total = weight.sum(axis=-1)
    alpha = np.divide(
        (per_channel * weight).sum(axis=-1), total,
        out=np.zeros(total.shape, dtype=np.float64), where=total > 0,
    )
    return np.clip(alpha, 0.0, 1.0)


def _residual(before, after, alpha, w):
    return float(np.abs(composite(after, alpha, w) - _as_float(before)).mean())


def fit_mark_colour(before, after):
    """Measure the mark's colour from the pair rather than assuming white.

    Scores a candidate W by round-tripping: derive alpha under that W, composite
    it back over the clean frame, and compare to the watermarked frame. Only
    pixels the hand-clean actually changed are scored - untouched art is
    reproduced perfectly by every candidate and would otherwise flatten the
    objective and drag the answer toward whatever the art happens to be.
    """
    obs = _as_float(before)
    orig = _as_float(after)
    if obs.shape != orig.shape:
        raise ValueError(f"pair shape mismatch: {obs.shape} vs {orig.shape}")

    touched = np.abs(obs - orig).max(axis=-1) > 1.0
    if not touched.any():
        return float(_W_COARSE[-1])
    # Scored pixels are gathered into a Nx1 column so the estimator runs on the
    # same (H, W, C) code path as a whole frame - no separate flat-array branch
    # to keep in step with it.
    obs_s = obs[touched][:, None, :]
    orig_s = orig[touched][:, None, :]

    def score(w):
        a = alpha_from_pair(obs_s, orig_s, w)
        return float(np.abs(composite(orig_s, a, w) - obs_s).mean())

    best = min(_W_COARSE, key=score)
    fine = np.arange(max(0.0, best - _W_FINE_SPAN),
                     min(255.0, best + _W_FINE_SPAN) + _W_FINE_STEP, _W_FINE_STEP)
    return float(min(fine, key=score))


def extract(before, after, mark_colour=None):
    """Measure the overlay from a pair. Returns the matte plus its diagnostics.

    `residual_mae` is the honest one: it is how far the measured matte is from
    reproducing the watermarked frame when composited back over the clean one.
    A large residual means the model does not fit - the hand-clean changed art
    as well as mark, or the mark is not a simple alpha composite - and the matte
    should not be trusted no matter how plausible it looks.
    """
    obs = _as_float(before)
    orig = _as_float(after)
    if obs.shape != orig.shape:
        raise ValueError(f"pair shape mismatch: {obs.shape} vs {orig.shape}")
    w = fit_mark_colour(obs, orig) if mark_colour is None else float(mark_colour)
    alpha = alpha_from_pair(obs, orig, w)
    alpha = np.where(alpha < ALPHA_FLOOR, 0.0, alpha)
    ys, xs = np.nonzero(alpha > ALPHA_FLOOR)
    bbox = ([int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
            if xs.size else None)
    return {
        "alpha": alpha,
        "mark_colour": w,
        "support_px": int((alpha > ALPHA_FLOOR).sum()),
        "alpha_max": float(alpha.max()),
        "alpha_mean_in_support": (float(alpha[alpha > ALPHA_FLOOR].mean())
                                  if (alpha > ALPHA_FLOOR).any() else 0.0),
        "bbox": bbox,
        "residual_mae": _residual(obs, orig, alpha, w),
    }


def _load(path):
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float64)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="lw_overlay_from_pair",
        description="Measure the overlay matte from a watermarked/hand-cleaned pair")
    p.add_argument("before", help="the watermarked frame")
    p.add_argument("after", help="the hand-cleaned frame")
    p.add_argument("--mark-colour", type=float, default=None,
                   help="override the fitted mark colour")
    p.add_argument("--save-alpha", help="write the matte as a 16-bit PNG")
    p.add_argument("--save-npz", help="write the matte as an npz for reuse")
    a = p.parse_args(argv)

    out = extract(_load(a.before), _load(a.after), a.mark_colour)
    alpha = out.pop("alpha")
    if a.save_alpha:
        from PIL import Image
        img = Image.fromarray((np.clip(alpha, 0, 1) * 65535).astype(np.uint16))
        tmp = a.save_alpha + ".tmp.png"
        img.save(tmp)
        os.replace(tmp, a.save_alpha)
        out["alpha_png"] = a.save_alpha
    if a.save_npz:
        tmp = a.save_npz + ".tmp.npz"
        np.savez_compressed(tmp, alpha=alpha, mark_colour=out["mark_colour"])
        os.replace(tmp, a.save_npz)
        out["alpha_npz"] = a.save_npz
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
