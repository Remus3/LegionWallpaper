"""Opacity / hue / tone conditioning inside the mark region.

Track D. The premise is that a mark is a semi-transparent layer over the art,

    observed = alpha * colour + (1 - alpha) * content

so alpha and colour can be estimated from the readable ring around the mark and
the region pushed back toward the content before any filler is asked for
anything: the mark's remaining amplitude drops and the region's tone matches its
surroundings.

The estimator here is exact for that model and is proved so on synthetic art
where the model is true by construction. What it also does, and this is the
point of keeping it, is let the model be TESTED on the real marks instead of
assumed. `fit_veil` regresses the marked frame against the operator's accepted
final inside the mask, which is the direct ground-truth measurement of alpha and
colour, and `tools/lw_clean_condition_census.py` reports it per capture.

Measured on the four captures, R-squared of that fit:

    105-cleanup (credit line)    0.49 - 0.59
    107-cleanup (area)           0.32 - 0.81, inconsistent across channels
    209-cleanup (signature)      0.002          slopes NEGATIVE, alpha > 1
    dgk8f92     (block)          0.04

So the model does not describe three of these four marks, and on 209 it is not
merely inaccurate - the observed pixels carry essentially no information about
what is under them, because a painted signature is opaque. There is nothing to
weaken. The estimator is not what is failing; the assumption is.

Where a genuine veil DOES exist - the DeviantArt centre overlay, which is a real
semi-transparent layer and covers 45 of the 80 queued slugs - the repo already
inverts it with a template and matte in `lw_clean_iopaint.overlay_prepass`, and
LEDGER 101-103 records that even there the pre-pass alone leaves the credit line
legible at 1:1. Conditioning was never going to be a removal.

Nothing here approves anything, and conditioning writes only inside the mask.

  python tools/lw_clean_condition.py --image in.png --mask mark.png --out out.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_heal as HEAL  # noqa: E402

# The ring the region is compared against. The inner gap skips the mark's soft
# skirt, which is still mark; the outer bound keeps the comparison local.
RING_INNER = 4
RING_OUTER = 24
MIN_RING_PX = 256

# Below this there is no veil worth inverting, and above it the inverse gain
# 1/(1-alpha) amplifies whatever noise the region has more than it recovers.
MIN_ALPHA = 0.02
MAX_ALPHA = 0.85

# How far the region's contrast loss must exceed the loss between two annuli of
# the SAME art before it counts as a veil.
#
# Without this the estimator fires on ordinary art: a region and the ring around
# it differ in contrast for perfectly innocent reasons, and calling that a veil
# would apply a correction to a frame that has no mark in it - the failure mode
# this repo has already logged for absolute contrast residue. The null is
# measured per image from the ring's own inner and outer halves rather than
# assumed, so it costs no constant.
NULL_MARGIN = 2.0


def ring_of(mark, inner=RING_INNER, outer=RING_OUTER, others=None):
    """The readable annulus around a mark, skipping its own soft skirt."""
    ring = HEAL._dilate(mark, outer) & ~HEAL._dilate(mark, inner)
    if others is not None:
        ring = ring & ~others
    return ring


def _moments(img, sel):
    a = np.asarray(img, dtype=np.float64)[sel]
    return a.mean(axis=0), a.std(axis=0)


def estimate_veil(img, mark, ring=None):
    """Alpha and colour from the ring alone - no pixel of truth is read.

    A veil is an affine contraction toward its own colour: it scales contrast by
    (1 - alpha) and pulls the mean toward the colour. Matching the region's first
    two moments to the ring's therefore inverts it exactly, and reporting the
    result as (alpha, colour) rather than as gain and offset is what makes it
    checkable by eye.
    """
    mark = np.asarray(mark, dtype=bool)
    rec = {"alpha": 0.0, "colour": [0.0, 0.0, 0.0], "applies": False,
           "reason": "", "px": int(mark.sum()), "null": 0.0,
           "alpha_per_channel": [0.0, 0.0, 0.0]}
    if not mark.any():
        rec["reason"] = "empty mark"
        return rec
    band = ring_of(mark) if ring is None else np.asarray(ring, dtype=bool)
    if int(band.sum()) < MIN_RING_PX:
        rec["reason"] = "no readable ring"
        return rec

    m_in, s_in = _moments(img, mark)
    m_ring, s_ring = _moments(img, band)
    with np.errstate(divide="ignore", invalid="ignore"):
        keep = np.where(s_ring > 1e-6, s_in / s_ring, 1.0)

    # Opacity is ONE number. The veil's colour differs per channel; how much of
    # it there is does not, and estimating three alphas invites three different
    # answers to a question with one.
    alpha = float(np.clip(1.0 - float(np.mean(keep)), 0.0, MAX_ALPHA))
    rec["alpha"] = round(alpha, 4)
    rec["alpha_per_channel"] = [round(float(1.0 - k), 4) for k in keep]
    rec["null"] = round(_null_scale(img, mark), 4)
    if alpha < MIN_ALPHA:
        rec["reason"] = "no contrast loss - not a veil"
        return rec
    if alpha < NULL_MARGIN * rec["null"]:
        rec["reason"] = (f"contrast loss {alpha:.3f} is within the art's own "
                         f"variation ({rec['null']:.3f})")
        return rec

    colour = (m_in - (1.0 - alpha) * m_ring) / max(alpha, 1e-6)
    rec["colour"] = [round(float(c), 2) for c in np.clip(colour, -1e4, 1e4)]
    rec["applies"] = True
    rec["reason"] = "veil estimated from the ring"
    return rec


def _null_scale(img, mark):
    """Contrast difference between two annuli of the same art - the null.

    If the region's contrast loss does not beat this, it is indistinguishable
    from the art simply varying from place to place.
    """
    mid = (RING_INNER + RING_OUTER) // 2
    inner = ring_of(mark, RING_INNER, mid)
    outer = ring_of(mark, mid, RING_OUTER)
    if int(inner.sum()) < MIN_RING_PX or int(outer.sum()) < MIN_RING_PX:
        return 0.0
    _mi, si = _moments(img, inner)
    _mo, so = _moments(img, outer)
    with np.errstate(divide="ignore", invalid="ignore"):
        keep = np.where(so > 1e-6, si / so, 1.0)
    return float(abs(1.0 - float(np.mean(keep))))


def apply_veil_inverse(img, mark, alpha, colour):
    """Undo the layer inside the mark; nothing outside it is touched."""
    img = np.asarray(img)
    mark = np.asarray(mark, dtype=bool)
    out = img.copy()
    if not mark.any():
        return out
    a = np.clip(np.asarray(alpha, dtype=np.float64), 0.0, MAX_ALPHA)
    c = np.asarray(colour, dtype=np.float64)
    keep = np.maximum(1.0 - a, 1.0 - MAX_ALPHA)
    vals = (img[mark].astype(np.float64) - a * c) / keep
    out[mark] = np.clip(np.rint(vals), 0, 255).astype(img.dtype)
    return out


def auto_condition(img, mark, per_blob=True):
    """Estimate and apply, per blob by default so one veil does not set another."""
    img = np.asarray(img)
    mark = np.asarray(mark, dtype=bool)
    rec = {"steps": [], "conditioned_px": 0, "per_blob": bool(per_blob)}
    if not mark.any():
        return img.copy(), rec

    regions = HEAL.label_blobs(mark) if per_blob else [mark]
    regions.sort(key=lambda b: (-int(b.sum()),
                                int(np.nonzero(b)[0].min()),
                                int(np.nonzero(b)[1].min())))
    cur = img.copy()
    for region in regions:
        others = mark & ~region
        band = ring_of(region, others=others)
        step = estimate_veil(cur, region, ring=band)
        if step["applies"]:
            cur = apply_veil_inverse(cur, region, step["alpha"], step["colour"])
            rec["conditioned_px"] += int(region.sum())
        rec["steps"].append(step)
    return cur, rec


# --------------------------------------------------- ground-truth validation
def fit_veil(observed, truth, mask):
    """Regress observed against the true content inside the mask.

    This is the only honest test of the MODEL, as opposed to the estimator: with
    the content known, `observed = (1 - alpha) * content + alpha * colour` is a
    straight line per channel, and its R-squared says whether the mark is a veil
    at all. It needs ground truth, so it belongs to the census and never to a
    lane.
    """
    observed = np.asarray(observed, dtype=np.float64)
    truth = np.asarray(truth, dtype=np.float64)
    mask = np.asarray(mask, dtype=bool)
    out = {"alpha": [], "colour": [], "r2": []}
    for ch in range(3):
        x = truth[:, :, ch][mask]
        y = observed[:, :, ch][mask]
        a = np.stack([x, np.ones_like(x)], axis=1)
        coef, *_ = np.linalg.lstsq(a, y, rcond=None)
        slope, offset = float(coef[0]), float(coef[1])
        alpha = 1.0 - slope
        denom = ((y - y.mean()) ** 2).sum()
        r2 = 1.0 - ((y - a @ coef) ** 2).sum() / denom if denom > 0 else 0.0
        out["alpha"].append(round(alpha, 4))
        out["colour"].append(round(offset / alpha, 2) if abs(alpha) > 1e-6
                             else None)
        out["r2"].append(round(float(r2), 4))
    return out


# ----------------------------------------------------------------------- CLI
def main(argv=None):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    ap = argparse.ArgumentParser(prog="lw_clean_condition")
    ap.add_argument("--image", required=True)
    ap.add_argument("--mask", required=True, help="white = the mark")
    ap.add_argument("--out", required=True)
    ap.add_argument("--whole-region", action="store_true",
                    help="one estimate for the whole mark instead of per blob")
    args = ap.parse_args(argv)

    with Image.open(args.image) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    with Image.open(args.mask) as im:
        mark = np.asarray(im.convert("L")) > 127

    out, rec = auto_condition(rgb, mark, per_blob=not args.whole_region)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".part"
    Image.fromarray(out).save(tmp, format="PNG")
    os.replace(tmp, args.out)
    rec["out"] = args.out
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
