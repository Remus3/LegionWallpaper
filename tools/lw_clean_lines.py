"""The overlap-muxed comparison layer: does the fill carry the art's lines?

Track B. Forty-five of forty-five automated candidates were rejected for one
stated reason - lines from outside the matte do not re-align - and nothing in
the stack could see it. Every scalar gate in the repo measures how much a region
changed or how loud it is; none of them knows that a blade edge entering the top
of a credit line has to come out of the bottom, in the right place, at the right
angle.

This builds that knowledge BEFORE any fill, from readable art only:

  1. find where strong oriented structure meets the mark's boundary. The
     gradient is computed mask-aware, so not one pixel of the mark contributes -
     the same trap track A found in the busyness measure.
  2. pair each crossing with the one on the far side that agrees with it in
     direction and lies on its ray, and whose connecting segment actually
     crosses the mark. Each pair is a CHORD: a prediction about a line that has
     to exist inside the filled region.
  3. carry the chords through the stepped processing. After a step, probe across
     the predicted path and compare with what the same probe reads on readable
     art at the same line.

The probe answers both shapes real art uses - a step (region boundary) and a
ridge (a thin stroke) - and takes the larger, so one operator covers both and
the expected/measured comparison is like for like.

It tells three outcomes apart, and the third is the one that matters:

  intact      the line is on the predicted path, with the expected contrast
  erased      the fill smoothed it away, as a membrane fill does
  misaligned  a line exists but not where the art says it goes. Contrast alone
              calls this a pass, which is how the rejected candidates got through

A small alignment tolerance is allowed because real art curves; it is far below
the misalignment the eye objects to, so "nearly right" still passes and "a line,
somewhere" does not.

A chord needs a crossing on BOTH sides of the mark, and the credit-line corpus
mostly does not supply one: over 39 queued slugs, 1,566 crossings become 102
chords and 269 of 357 fill steps end up with no evidence at all. So a lone
crossing is spent too, as a STUB - a ray rather than a path. It is weaker on
purpose (one anchor, so erased only, never misaligned) and it is proven against
the frame it was built from before it is allowed to say anything.

This module REPORTS. It is not a gate: no candidate is approved or rejected on a
scalar here (LEDGER 101-103), and the operator's eye remains the acceptance bar.

Pure numpy + Pillow: no torch, cv2 or scipy.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_heal as HEAL  # noqa: E402

# ------------------------------------------------------------------ constants
# Ring of readable art just outside the mark that crossings are found in.
BAND_WIDTH = 2

# A boundary pixel below this gradient magnitude carries no line worth tracking.
GRAD_MIN = 6.0

# Crossings within this distance of each other are one line, not two: a stroke
# has two edges and a soft edge has several peaks, and both should yield ONE
# crossing at their weighted centre.
CLUSTER_DILATE = 2

# Pairing tolerances. A pair must agree in direction and lie on each other's
# ray, and the segment joining them must actually cross the mark.
ANGLE_MAX_DEG = 30.0
# Lateral offset allowed from the partner's ray. Measured over the two captures
# that carry chords: at 6.0 this was the BINDING constraint and inconsistent
# with the angle tolerance beside it (30 degrees over a ~70px span already
# admits far more lateral offset than 6px). Raising it to 10 doubles the chords
# found on 105 and leaves the ordering unchanged - operator and lama above heal
# and behind on every one of the twelve (angle, ray) combinations tried.
RAY_TOL = 10.0
MIN_INSIDE_FRACTION = 0.6

# Probing.
PROBE_OFFSET = 2.0          # px across the path
SAMPLES = 24                # points along a chord before the inside-mask filter
MIN_SAMPLES = 3
ALIGN_TOL = 1.5             # px of drift allowed before a line counts as moved
ALIGN_STEP = 0.5

# A chord this weak is broken. Reported, never used to approve anything.
PASS_RATIO = 0.5
INTACT_FRACTION = 0.8

# Cap on crossings considered, strongest first: pairing is quadratic and a busy
# boundary can offer thousands.
MAX_CROSSINGS = 200

# How far a STUB follows its crossing's ray into the mark, and at what spacing.
# 12px is what the coverage measurement was taken at: it crosses a credit-line
# glyph (20-40px on this corpus) without running the length of the whole band,
# and it is far enough that a fill which flattens the letter cannot hide inside
# it. It has NOT been swept - it is one value that produced a measured result,
# and it is labelled as such.
STUB_LEN = 12.0
STUB_STEP = 1.0


@dataclass
class Chord:
    """A predicted line through the mark, made from readable art only.

    `kind` is "chord" when both ends are anchored and "stub" when only one is.
    A stub cannot see MISALIGNED - it has no far side to be wrong about - so a
    caller that cares about the difference has to be able to ask.
    """
    p0: tuple
    d0: tuple
    p1: tuple
    d1: tuple
    expected: float
    path: np.ndarray = field(repr=False, default=None)
    kind: str = "chord"


# --------------------------------------------------------------- the gradient
def _luma(img):
    a = np.asarray(img, dtype=np.float64)
    return a.mean(axis=2) if a.ndim == 3 else a


def masked_gradient(lum, valid):
    """Central differences that never read an invalid pixel.

    One-sided where only one neighbour is readable, zero where neither is. This
    is what keeps the mark out of its own prediction.
    """
    gy = np.zeros_like(lum)
    gx = np.zeros_like(lum)
    for axis in (0, 1):
        up = HEAL._shift(lum, -1 if axis == 0 else 0, 0 if axis == 0 else -1)
        dn = HEAL._shift(lum, 1 if axis == 0 else 0, 0 if axis == 0 else 1)
        vu = HEAL._shift(valid.astype(np.float64),
                         -1 if axis == 0 else 0, 0 if axis == 0 else -1) > 0.5
        vd = HEAL._shift(valid.astype(np.float64),
                         1 if axis == 0 else 0, 0 if axis == 0 else 1) > 0.5
        both = vu & vd
        g = np.where(both, (dn - up) / 2.0,
                     np.where(vd, dn - lum,
                              np.where(vu, lum - up, 0.0)))
        g = np.where(valid, g, 0.0)
        if axis == 0:
            gy = g
        else:
            gx = g
    return gy, gx


# ------------------------------------------------------------------ crossings
def _orient_into(p, d, mask, steps=(2.0, 4.0, 6.0)):
    """Flip an edge direction so it points into the mark, or None if neither."""
    h, w = mask.shape
    for sign in (1.0, -1.0):
        for s in steps:
            y = int(round(p[0] + sign * d[0] * s))
            x = int(round(p[1] + sign * d[1] * s))
            if 0 <= y < h and 0 <= x < w and mask[y, x]:
                return (sign * d[0], sign * d[1])
    return None


def boundary_crossings(img, mask, band_width=BAND_WIDTH, grad_min=GRAD_MIN):
    """Where oriented structure meets the mark, as (point, direction, strength)."""
    mask = np.asarray(mask, dtype=bool)
    lum = _luma(img)
    valid = ~mask
    gy, gx = masked_gradient(lum, valid)
    mag = np.hypot(gy, gx)

    band = HEAL._dilate(mask, band_width) & valid
    hot = band & (mag >= grad_min)
    if not hot.any():
        return []

    out = []
    for blob in HEAL.label_blobs(HEAL._dilate(hot, CLUSTER_DILATE) & band):
        sel = blob & hot
        if not sel.any():
            continue
        ys, xs = np.nonzero(sel)
        w = mag[ys, xs]
        tot = float(w.sum())
        if tot <= 0:
            continue
        py = float((ys * w).sum() / tot)
        px = float((xs * w).sum() / tot)
        # Structure tensor over the cluster: handles the sign ambiguity that
        # averaging raw gradient directions cannot.
        vy, vx = gy[ys, xs], gx[ys, xs]
        j = np.array([[float((w * vy * vy).sum()), float((w * vy * vx).sum())],
                      [float((w * vy * vx).sum()), float((w * vx * vx).sum())]])
        vals, vecs = np.linalg.eigh(j)
        gdir = vecs[:, int(np.argmax(vals))]
        edge = (-float(gdir[1]), float(gdir[0]))
        n = float(np.hypot(*edge))
        if n < 1e-9:
            continue
        edge = (edge[0] / n, edge[1] / n)
        d = _orient_into((py, px), edge, mask)
        if d is None:
            continue
        out.append(((py, px), d, float(w.max())))
    out.sort(key=lambda c: (-c[2], c[0][0], c[0][1]))
    return out[:MAX_CROSSINGS]


# -------------------------------------------------------------------- pairing
def _fraction_inside(p0, p1, mask, n=16):
    ys = np.linspace(p0[0], p1[0], n)
    xs = np.linspace(p0[1], p1[1], n)
    h, w = mask.shape
    yi = np.clip(np.rint(ys).astype(int), 0, h - 1)
    xi = np.clip(np.rint(xs).astype(int), 0, w - 1)
    return float(mask[yi, xi].mean())


def _pair_cost(a, b, mask):
    (p0, d0, _s0), (p1, d1, _s1) = a, b
    v = np.array([p1[0] - p0[0], p1[1] - p0[1]], dtype=np.float64)
    length = float(np.hypot(*v))
    if length < 2.0:
        return None
    da = np.array(d0)
    db = np.array(d1)
    if float(v @ da) <= 0 or float((-v) @ db) <= 0:
        return None                       # they must face each other
    cos = float(np.clip(-(da @ db), -1.0, 1.0))
    angle = float(np.degrees(np.arccos(cos)))
    if angle > ANGLE_MAX_DEG:
        return None
    off = max(float(np.hypot(*(v - (v @ da) * da))),
              float(np.hypot(*(-v - ((-v) @ db) * db))))
    if off > RAY_TOL:
        return None
    if _fraction_inside(p0, p1, mask) < MIN_INSIDE_FRACTION:
        return None
    return angle / ANGLE_MAX_DEG + off / RAY_TOL


def _hermite(p0, d0, p1, d1, n=SAMPLES):
    """Cubic through both crossings, leaving each along its own direction."""
    p0 = np.array(p0, dtype=np.float64)
    p1 = np.array(p1, dtype=np.float64)
    length = float(np.hypot(*(p1 - p0)))
    m0 = np.array(d0, dtype=np.float64) * length
    m1 = -np.array(d1, dtype=np.float64) * length
    s = np.linspace(0.0, 1.0, n)[:, None]
    h00 = 2 * s ** 3 - 3 * s ** 2 + 1
    h10 = s ** 3 - 2 * s ** 2 + s
    h01 = -2 * s ** 3 + 3 * s ** 2
    h11 = s ** 3 - s ** 2
    return h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1


# --------------------------------------------------------------- the probe
def _sample(lum, y, x):
    h, w = lum.shape
    y = min(max(float(y), 0.0), h - 1.0001)
    x = min(max(float(x), 0.0), w - 1.0001)
    y0, x0 = int(y), int(x)
    fy, fx = y - y0, x - x0
    a = lum[y0, x0] * (1 - fy) * (1 - fx) + lum[y0 + 1, x0] * fy * (1 - fx)
    return a + lum[y0, x0 + 1] * (1 - fy) * fx + lum[y0 + 1, x0 + 1] * fy * fx


def _response(lum, p, normal, offset=PROBE_OFFSET):
    """The larger of the step and ridge answers across `normal` at `p`."""
    c = _sample(lum, p[0], p[1])
    a = _sample(lum, p[0] + offset * normal[0], p[1] + offset * normal[1])
    b = _sample(lum, p[0] - offset * normal[0], p[1] - offset * normal[1])
    return max(abs(a - b), abs(2 * c - a - b))


def _aligned_response(lum, p, tangent, offset=PROBE_OFFSET, tol=ALIGN_TOL):
    """Best response within `tol` px across the path - art curves a little."""
    normal = (-tangent[1], tangent[0])
    best = 0.0
    k = int(round(tol / ALIGN_STEP))
    for i in range(-k, k + 1):
        d = i * ALIGN_STEP
        q = (p[0] + d * normal[0], p[1] + d * normal[1])
        best = max(best, _response(lum, q, normal, offset))
    return best


def _readable(mask, p, tangent, offset=PROBE_OFFSET, tol=ALIGN_TOL):
    """True when every pixel that probe would touch lies outside the mark."""
    h, w = mask.shape
    normal = (-tangent[1], tangent[0])
    k = int(round(tol / ALIGN_STEP))
    for i in range(-k, k + 1):
        d = i * ALIGN_STEP
        for o in (-offset - 1.0, 0.0, offset + 1.0):
            y = int(round(p[0] + (d + o) * normal[0]))
            x = int(round(p[1] + (d + o) * normal[1]))
            if not (0 <= y < h and 0 <= x < w) or mask[y, x]:
                return False
    return True


def _expected_at(lum, mask, p, d):
    """The same probe, taken on readable art at this line, just outside it."""
    for s in (2.0, 3.0, 4.0, 5.0, 6.0):
        q = (p[0] - s * d[0], p[1] - s * d[1])
        if _readable(mask, q, d):
            return _aligned_response(lum, q, d)
    return None


# ------------------------------------------------------------------- the layer
def _layer(img, mask, band_width=BAND_WIDTH, grad_min=GRAD_MIN):
    """The pairing pass. Returns (chords, crossings, indices spent, luma)."""
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return [], [], set(), None
    lum = _luma(img)
    crossings = boundary_crossings(img, mask, band_width, grad_min)

    cands = []
    for i in range(len(crossings)):
        for j in range(i + 1, len(crossings)):
            cost = _pair_cost(crossings[i], crossings[j], mask)
            if cost is not None:
                cands.append((cost, i, j))
    cands.sort(key=lambda t: (t[0], t[1], t[2]))

    used, chords = set(), []
    for _cost, i, j in cands:
        if i in used or j in used:
            continue
        (p0, d0, _), (p1, d1, _) = crossings[i], crossings[j]
        e0 = _expected_at(lum, mask, p0, d0)
        e1 = _expected_at(lum, mask, p1, d1)
        if e0 is None or e1 is None:
            continue
        used.add(i)
        used.add(j)
        chords.append(Chord(p0=(round(p0[0], 3), round(p0[1], 3)), d0=d0,
                            p1=(round(p1[0], 3), round(p1[1], 3)), d1=d1,
                            expected=0.5 * (e0 + e1),
                            path=_hermite(p0, d0, p1, d1)))
    chords.sort(key=lambda c: (c.p0, c.p1))
    return chords, crossings, used, lum


def build_layer(img, mask, band_width=BAND_WIDTH, grad_min=GRAD_MIN):
    """Chords predicted from the art around the mark. Reads no masked pixel."""
    return _layer(img, mask, band_width, grad_min)[0]


def build_stubs(img, mask, band_width=BAND_WIDTH, grad_min=GRAD_MIN,
                length=STUB_LEN, step=STUB_STEP):
    """Rays from the crossings no chord could claim - and each one is checked.

    A chord needs two crossings on the same piece of mark. Over the 39-slug
    credit-line queue the corpus supplies about ONE per glyph blob, so the
    pairing pass turns 1,566 crossings into 102 chords and 269 of 357 fill
    steps commit with no evidence at all. Solving both of the pairing's own
    filter losses perfectly recovers 34 of those steps; spending the lone
    crossings instead reaches 153. That is the whole reason this exists.

    A stub is strictly weaker than a chord. With no far-side anchor it cannot
    tell a line that MOVED from a line that is where it should be, so it
    answers only the erased question - which is the failure the rollback was
    already built to catch.

    It also assumes the line runs STRAIGHT, and art curves. So every stub is
    scored against the frame it was built from, where the only correct answer
    is intact, and one that cannot predict its own source is dropped. A stub
    that fails there would do nothing but manufacture reverts on fills that did
    no harm; this is the same shape as the credit-line reader verifying itself
    on the string DEVIANTART - the evidence carries its own check.
    """
    mask = np.asarray(mask, dtype=bool)
    _chords, crossings, used, lum = _layer(img, mask, band_width, grad_min)
    if lum is None:
        return []
    n = max(int(round(length / step)) + 1, 3)
    out = []
    for i, (p, d, _s) in enumerate(crossings):
        if i in used:
            continue
        expected = _expected_at(lum, mask, p, d)
        if expected is None:
            continue
        path = np.array([[p[0] + k * step * d[0], p[1] + k * step * d[1]]
                         for k in range(n)], dtype=np.float64)
        out.append(Chord(p0=(round(p[0], 3), round(p[1], 3)), d0=d,
                         p1=(round(float(path[-1][0]), 3),
                             round(float(path[-1][1]), 3)), d1=d,
                         expected=expected, path=path, kind="stub"))
    if not out:
        return []
    proven = {tuple(r["p0"] + r["p1"])
              for r in score(img, mask, out)["chords"] if r["intact"]}
    out = [c for c in out if tuple(list(c.p0) + list(c.p1)) in proven]
    out.sort(key=lambda c: (c.p0, c.p1))
    return out


def measure_chord(img, mask, chord):
    """Median probe response along the predicted path, inside the mark only."""
    lum = _luma(img)
    pts = chord.path
    h, w = mask.shape
    vals = []
    for k in range(1, len(pts) - 1):
        p = pts[k]
        yi = int(np.clip(round(p[0]), 0, h - 1))
        xi = int(np.clip(round(p[1]), 0, w - 1))
        if not mask[yi, xi]:
            continue
        t = pts[k + 1] - pts[k - 1]
        n = float(np.hypot(*t))
        if n < 1e-9:
            continue
        vals.append(_aligned_response(lum, p, (t[0] / n, t[1] / n)))
    if len(vals) < MIN_SAMPLES:
        return None
    return float(np.median(vals))


def score(img, mask, chords):
    """Per-chord ratios plus a summary. Reports; never approves."""
    mask = np.asarray(mask, dtype=bool)
    rows = []
    for c in chords:
        measured = measure_chord(img, mask, c)
        if measured is None or c.expected <= 1e-6:
            continue
        ratio = float(min(2.0, measured / c.expected))
        rows.append({"p0": list(c.p0), "p1": list(c.p1),
                     "expected": round(c.expected, 3),
                     "measured": round(measured, 3),
                     "ratio": round(ratio, 4),
                     "kind": getattr(c, "kind", "chord"),
                     "intact": bool(ratio >= PASS_RATIO)})
    if not rows:
        return {"n_chords": 0, "median_ratio": None, "intact_fraction": None,
                "verdict": "no-evidence", "chords": []}
    ratios = [r["ratio"] for r in rows]
    frac = sum(1 for r in rows if r["intact"]) / float(len(rows))
    return {"n_chords": len(rows),
            "median_ratio": round(float(np.median(ratios)), 4),
            "intact_fraction": round(frac, 4),
            "verdict": "intact" if frac >= INTACT_FRACTION else "broken",
            "chords": rows}


# ----------------------------------------------------------------------- CLI
def main(argv=None):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    ap = argparse.ArgumentParser(prog="lw_clean_lines")
    ap.add_argument("--before", required=True, help="frame the layer is built from")
    ap.add_argument("--mask", required=True)
    ap.add_argument("--after", help="filled frame to score (default: --before)")
    ap.add_argument("--grad-min", type=float, default=GRAD_MIN)
    ap.add_argument("--json-out")
    args = ap.parse_args(argv)

    def _load(path):
        with Image.open(path) as im:
            return np.asarray(im.convert("RGB"), dtype=np.uint8)

    before = _load(args.before)
    with Image.open(args.mask) as im:
        mask = np.asarray(im.convert("L")) > 127
    after = _load(args.after) if args.after else before

    chords = build_layer(before, mask, grad_min=args.grad_min)
    rec = score(after, mask, chords)
    rec["before"] = args.before
    rec["after"] = args.after or args.before
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)),
                    exist_ok=True)
        tmp = args.json_out + ".part"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rec, fh, indent=2)
        os.replace(tmp, args.json_out)
    summary = {k: v for k, v in rec.items() if k != "chords"}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
