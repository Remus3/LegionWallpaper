"""Healing-brush fill - exemplar patch plus gradient-domain (Poisson) blending.

The operator's own description of what the cleaning lane should be doing, given
on 2026-08-22 after rejecting all 87 automated candidates: "like photoshops
healing brush". That is a different instrument from everything tried so far, and
it retro-explains every piece of guidance they gave.

A healing brush does two things and neither of them is generation:

  1. it takes TEXTURE from a source area chosen for matching structure, which is
     the operator's "reach beyond the text into similar-like areas ... to pull
     down into the area to be altered";
  2. it reconciles COLOUR and TONE with the destination by solving in the
     GRADIENT domain, so the source's gradients survive and the boundary is met
     exactly.

Consequences, and they line up with the measured failures:

  - LINES continue. Poisson transports the source's gradients, so a stroke that
    crosses the mark is carried through it instead of being re-imagined. "Lines
    from outside the matte do not re-align" was the rejection reason on 45 of
    45 candidates.
  - the seam vanishes BY CONSTRUCTION - Dirichlet boundary conditions, not a
    model that guessed well. Every lattice variant tried before this signed its
    own tile boundaries into the result.
  - it is DETERMINISTIC and hallucination-free, so the "phantom / incorrect
    context" failure mode cannot occur.
  - where the art is smooth there is no texture worth importing and the solve
    degrades to a membrane fill, which is exactly right for a painted signature
    on a flat panel (209-cleanup, one stroke).

Deliberately pure numpy + Pillow: no torch, no cv2, no scipy. The blobs are
small, which is what makes a classical solver cheap, and it keeps the whole
thing inside the fast CI lane.

This module is the FILL only. Mask generation is the open problem and is not
solved here; the honest way to exercise this is to replay the operator's own
captured masks through it (`tools/lw_clean_replay.py --engine heal`).

  python tools/lw_clean_heal.py --image in.png --mask mask.png --out out.png
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

# ------------------------------------------------------------------ constants
# Width of the valid annulus a source patch is scored against. Four pixels is
# enough to carry a line's direction without dragging in unrelated content.
RING_WIDTH = 4

# How far to look for a source patch. The operator's strokes pull from just
# outside the mark, never from across the frame.
SEARCH_RADIUS = 96
COARSE_STEP = 4                 # coarse grid, then a +/-3 refine around the win
RING_SAMPLE_MAX = 2000          # cap the ring points scored per candidate
MIN_RING_USABLE = 0.5           # candidate needs this much of the ring readable

# Levels of RMSE charged per pixel of offset length: a mild preference for the
# nearest adequate source, never enough to override a real structural match.
DISTANCE_PENALTY = 0.02

# RMSE credit for reusing an offset an adjacent committed tile already chose.
# Keeps a run of tiles over one texture coherent, so no gradient step appears
# along an internal tile boundary.
NEIGHBOUR_BONUS = 1.5

# Texture test. `ring_detail` is the RMS residual of the ring after a plane fit,
# so a smooth ramp reads ~0 however steep it is. Below this there is nothing to
# import and the membrane solution is both cheaper and safer.
SMOOTH_DETAIL = 3.0

# There is deliberately NO "the exemplar must be a good enough match" test.
# The first version of this module had one (accept only if the ring RMSE came
# in under 0.75x the ring's detail) and it rejected every exemplar on
# 105-cleanup - real painted art does not repeat exactly under translation - so
# all 8 tiles fell back to membrane and the result was a smear that lost the
# fabric entirely. Measured on the capture: an imperfect exemplar beats a blur
# on anything textured, because Poisson only imports the source's GRADIENTS and
# the tone is pinned by the destination's boundary either way. The only
# fallback left is the smooth case above, where there is no texture to import.

# Tile target area. The captures put the operator's median stroke at 6.5k px on
# busy art and 16k on soft art; 6k is the conservative end of that range. Tiles
# exist so one translation never has to explain content it cannot.
TARGET_TILE_AREA = 6000

CG_TOL = 1e-7
CG_MAXITER = 3000


# --------------------------------------------------------------- mask helpers
def _dilate(mask, width):
    """Square dilation by `width`, in pure numpy shifts."""
    out = mask.copy()
    for _ in range(int(width)):
        cur = out
        nxt = cur.copy()
        nxt[1:, :] |= cur[:-1, :]
        nxt[:-1, :] |= cur[1:, :]
        nxt[:, 1:] |= cur[:, :-1]
        nxt[:, :-1] |= cur[:, 1:]
        nxt[1:, 1:] |= cur[:-1, :-1]
        nxt[1:, :-1] |= cur[:-1, 1:]
        nxt[:-1, 1:] |= cur[1:, :-1]
        nxt[:-1, :-1] |= cur[1:, 1:]
        out = nxt
    return out


def ring_of(tile, invalid, width=RING_WIDTH):
    """The annulus of usable context around `tile`.

    `invalid` is everything that may not be read as context: the parts of the
    mark not yet healed, plus the tile itself.
    """
    return _dilate(tile, width) & ~invalid & ~tile


def label_blobs(mask):
    """8-connected components, as a list of boolean masks.

    Run-length union-find rather than a flood fill: linear in the number of
    runs, and it keeps this module free of scipy.
    """
    h, w = mask.shape
    parent = []

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    prev, runs = [], []
    for y in range(h):
        row = mask[y]
        if not row.any():
            prev = []
            continue
        d = np.diff(row.astype(np.int8))
        starts = (np.nonzero(d == 1)[0] + 1).tolist()
        ends = (np.nonzero(d == -1)[0] + 1).tolist()
        if row[0]:
            starts.insert(0, 0)
        if row[-1]:
            ends.append(w)
        cur = []
        for x0, x1 in zip(starts, ends, strict=True):
            lab = len(parent)
            parent.append(lab)
            for px0, px1, plab in prev:
                if px0 - 1 < x1 and x0 - 1 < px1:      # 8-connectivity
                    union(lab, plab)
            cur.append((x0, x1, lab))
            runs.append((y, x0, x1, lab))
        prev = cur

    groups = {}
    for y, x0, x1, lab in runs:
        groups.setdefault(find(lab), []).append((y, x0, x1))
    out = []
    for _root, rs in groups.items():
        m = np.zeros_like(mask)
        for y, x0, x1 in rs:
            m[y, x0:x1] = True
        ys, xs = np.nonzero(m)
        out.append((int(ys.min()), int(xs.min()), m))
    out.sort(key=lambda t: (t[0], t[1]))
    return [m for _y, _x, m in out]


def plan_tiles(mask, target_area=TARGET_TILE_AREA):
    """Partition the mask into ordered tiles, exactly and without overlap.

    A single large mask is the one thing four captures agree never works on a
    mark with structure around it. Blobs are split on a grid rather than by
    content: the content decision is made per tile by the source search, and a
    grid keeps the partition provably lossless.
    """
    tiles = []
    for blob in label_blobs(mask):
        area = int(blob.sum())
        ys, xs = np.nonzero(blob)
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        if area <= target_area * 1.5:
            tiles.append(blob)
            continue
        side = max(8, int(round(np.sqrt(float(target_area)))))
        for cy in range(y0, y1, side):
            for cx in range(x0, x1, side):
                cell = np.zeros_like(mask)
                cell[cy:min(cy + side, y1), cx:min(cx + side, x1)] = True
                t = blob & cell
                if t.any():
                    tiles.append(t)
    return tiles


def tile_axis(tile):
    """Unit vector ACROSS the tile - the direction art has to continue in.

    A credit line is long and thin, and the content that explains what is under
    it lies immediately above and below, not along it. This returns the minor
    principal axis of the tile, which is that direction. `None` when the tile is
    round enough that no direction is preferred.
    """
    ys, xs = np.nonzero(tile)
    if ys.size < 16:
        return None
    p = np.stack([ys - ys.mean(), xs - xs.mean()]).astype(np.float64)
    cov = (p @ p.T) / float(ys.size)
    vals, vecs = np.linalg.eigh(cov)
    if vals[1] <= 1e-9 or vals[0] / vals[1] > 0.64:      # within 1.25x: round
        return None
    v = vecs[:, 0]
    if v[0] < 0 or (v[0] == 0 and v[1] < 0):
        v = -v
    return (float(v[0]), float(v[1]))


# ------------------------------------------------------------ Poisson solving
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _shift(a, dy, dx):
    """out[p] = a[p + (dy, dx)], zero outside the array."""
    h, w = a.shape[:2]
    out = np.zeros_like(a)
    dy0, dy1 = max(0, -dy), h - max(0, dy)
    dx0, dx1 = max(0, -dx), w - max(0, dx)
    sy0, sy1 = max(0, dy), h - max(0, -dy)
    sx0, sx1 = max(0, dx), w - max(0, -dx)
    out[dy0:dy1, dx0:dx1, ...] = a[sy0:sy1, sx0:sx1, ...]
    return out


def _neighbour_sum(a):
    """Sum of the 4 axis neighbours, zero outside the array."""
    s = np.zeros_like(a)
    s[1:, ...] += a[:-1, ...]
    s[:-1, ...] += a[1:, ...]
    s[:, 1:, ...] += a[:, :-1, ...]
    s[:, :-1, ...] += a[:, 1:, ...]
    return s


def _divergence(g):
    """The Poisson right-hand side for a single guidance field."""
    return 4.0 * g - _neighbour_sum(g)


def _blended_divergence(ga, gb, w):
    """Crossfade two guidance fields in the GRADIENT domain, not in intensity.

    Blending the images and differencing would smear the two sources into each
    other; blending their gradients edge by edge keeps each side's structure
    sharp and only hands over authority across the mark.
    """
    out = np.zeros_like(ga)
    for dy, dx in NEIGHBOURS:
        wpq = 0.5 * (w + _shift(w, dy, dx))
        out += (wpq * (ga - _shift(ga, dy, dx))
                + (1.0 - wpq) * (gb - _shift(gb, dy, dx)))
    return out


def _cg(hole, b, tol=CG_TOL, maxiter=CG_MAXITER):
    """Conjugate gradients on the masked Laplacian, per channel.

    The operator is the same for all three channels but the scalars are not, so
    the reductions carry a channel axis and alpha/beta broadcast.
    """
    m3 = hole[..., None]

    def apply(u):
        return (4.0 * u - _neighbour_sum(u)) * m3

    x = np.zeros_like(b)
    r = b * m3
    p = r.copy()
    rs = (r * r).sum(axis=(0, 1))
    rs0 = rs.copy()
    if not np.any(rs0 > 0):
        return x
    for _ in range(maxiter):
        ap = apply(p)
        denom = (p * ap).sum(axis=(0, 1))
        denom = np.where(np.abs(denom) < 1e-30, 1e-30, denom)
        alpha = rs / denom
        x += alpha * p
        r -= alpha * ap
        rs_new = (r * r).sum(axis=(0, 1))
        if np.all(rs_new <= tol * tol * np.maximum(rs0, 1e-30)):
            break
        p = r + (rs_new / np.where(rs < 1e-30, 1e-30, rs)) * p
        rs = rs_new
    return x


def _blend_weight(shape, hole, axis, origin):
    """1 at the +axis edge of the hole, 0 at the -axis edge, linear between.

    The weight that decides how much of each side's gradients a pixel gets:
    content pulled from above is trusted near the top edge, from below near the
    bottom, and the two are crossfaded across the mark. That is what keeps a
    line entering one edge and leaving the other from meeting at a step.
    """
    uy, ux = axis
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    t = (yy + origin[0]) * uy + (xx + origin[1]) * ux
    ts = t[hole]
    lo, hi = float(ts.min()), float(ts.max())
    if hi - lo < 1e-9:
        return np.full(shape, 0.5)
    return np.clip((t - lo) / (hi - lo), 0.0, 1.0)


def _window(img, hole, offsets, source):
    """Sub-arrays for the solve: image, hole and one guidance field per offset.

    The pad is edge-replicated so a hole touching the frame border still has a
    Dirichlet boundary on every side.
    """
    h, w = hole.shape
    ys, xs = np.nonzero(hole)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    cy0, cy1 = max(0, y0 - 1), min(h, y1 + 1)
    cx0, cx1 = max(0, x0 - 1), min(w, x1 + 1)
    pad = ((1 if cy0 == y0 else 0, 1 if cy1 == y1 else 0),
           (1 if cx0 == x0 else 0, 1 if cx1 == x1 else 0))

    sub = np.pad(img[cy0:cy1, cx0:cx1].astype(np.float64),
                 (pad[0], pad[1], (0, 0)), mode="edge")
    sub_hole = np.pad(hole[cy0:cy1, cx0:cx1], (pad[0], pad[1]),
                      mode="constant", constant_values=False)

    srcf = source.astype(np.float64)
    guides = []
    for off in offsets:
        if off is None:
            guides.append(None)
            continue
        dy, dx = off
        gy = np.clip(np.arange(cy0 - pad[0][0], cy1 + pad[0][1]) + dy, 0, h - 1)
        gx = np.clip(np.arange(cx0 - pad[1][0], cx1 + pad[1][1]) + dx, 0, w - 1)
        guides.append(srcf[np.ix_(gy, gx)])
    return sub, sub_hole, guides, (cy0 - pad[0][0], cx0 - pad[1][0])


def poisson_fill(img, hole, offset=None, source=None, offset2=None,
                 axis=None):
    """Solve for the hole's contents; nothing outside the hole is touched.

    `offset` None solves the membrane (harmonic) problem - the smoothest field
    that meets the boundary. An offset imports the gradients of `source` shifted
    by it, which is the healing half. Give `offset2` and `axis` as well and the
    two sources are crossfaded across the mark, so structure entering one edge
    and leaving the other is carried by whichever side is nearer.
    """
    img = np.asarray(img)
    hole = np.asarray(hole, dtype=bool)
    out = img.copy()
    if not hole.any():
        return out
    src = img if source is None else np.asarray(source)
    offs = [offset, offset2] if offset2 is not None else [offset]
    sub, sub_hole, guides, (oy, ox) = _window(img, hole, offs, src)

    known = sub * (~sub_hole)[..., None]
    b = _neighbour_sum(known)
    if guides[0] is not None:
        if len(guides) == 2 and guides[1] is not None and axis is not None:
            w = _blend_weight(sub.shape[:2], sub_hole, axis, (oy, ox))[..., None]
            b = b + _blended_divergence(guides[0], guides[1], w)
        else:
            b = b + _divergence(guides[0])
    b = b * sub_hole[..., None]

    x = _cg(sub_hole, b)
    vals = np.clip(np.rint(x[sub_hole]), 0, 255).astype(img.dtype)
    ys, xs = np.nonzero(sub_hole)
    out[ys + oy, xs + ox] = vals
    return out


# ----------------------------------------------------------- exemplar search
def _plane_residual(vals, ys, xs):
    """RMS residual of a least-squares plane fit - texture, with tilt removed."""
    if vals.size < 8:
        return 0.0
    a = np.stack([ys.astype(np.float64), xs.astype(np.float64),
                  np.ones(ys.size)], axis=1)
    coef, *_ = np.linalg.lstsq(a, vals, rcond=None)
    return float(np.sqrt(np.mean((vals - a @ coef) ** 2)))


def _subsample(idx, cap):
    if idx[0].size <= cap:
        return idx
    step = int(np.ceil(idx[0].size / float(cap)))
    return (idx[0][::step], idx[1][::step])


def search_source(img, hole, invalid, radius=SEARCH_RADIUS,
                  ring_width=RING_WIDTH, prefer=(), axis=None, side=0):
    """Pick the translation whose surroundings best explain this hole's ring.

    Scored on the valid annulus only, so the mark itself never votes. A
    candidate is rejected outright if the shifted hole would read any pixel that
    is still marked - a source patch overlapping the mark paints it back in.
    """
    img = np.asarray(img)
    h, w = hole.shape
    ring = ring_of(hole, invalid, ring_width)
    rec = {"ring_px": int(ring.sum()), "ring_detail": 0.0, "ring_rmse": None,
           "offset": None, "candidates": 0}
    if rec["ring_px"] < 16:
        return None, rec

    ry, rx = _subsample(np.nonzero(ring), RING_SAMPLE_MAX)
    imgf = img.astype(np.float64)
    ref = imgf[ry, rx]
    luma = ref.mean(axis=1)
    rec["ring_detail"] = round(_plane_residual(luma, ry, rx), 3)

    prefer = {tuple(p) for p in prefer if p is not None}
    scored = []
    step = max(1, int(COARSE_STEP))
    grid = list(range(-int(radius), int(radius) + 1, step))
    fine = set()
    for dy in grid:
        for dx in grid:
            if dy == 0 and dx == 0:
                continue
            if not _on_side(dy, dx, axis, side):
                continue
            cost, rmse = _score(imgf, invalid, ry, rx, ref, dy, dx, h, w, prefer)
            if cost is None:
                continue
            scored.append((cost, rmse, dy, dx))
    if scored:
        scored.sort(key=lambda t: (t[0], t[2], t[3]))
        by, bx = scored[0][2], scored[0][3]
        for dy in range(by - step + 1, by + step):
            for dx in range(bx - step + 1, bx + step):
                if (dy, dx) == (0, 0) or (dy % step == 0 and dx % step == 0):
                    continue
                fine.add((dy, dx))
    for dy, dx in sorted(fine):
        if not _on_side(dy, dx, axis, side):
            continue
        cost, rmse = _score(imgf, invalid, ry, rx, ref, dy, dx, h, w, prefer)
        if cost is not None:
            scored.append((cost, rmse, dy, dx))
    rec["candidates"] = len(scored)
    if not scored:
        return None, rec

    scored.sort(key=lambda t: (t[0], t[2], t[3]))
    hy, hx = np.nonzero(hole)
    for _cost, rmse, dy, dx in scored:
        yy, xx = hy + dy, hx + dx
        if yy.min() < 0 or yy.max() >= h or xx.min() < 0 or xx.max() >= w:
            continue
        if invalid[yy, xx].any():
            continue
        rec["ring_rmse"] = round(float(rmse), 3)
        rec["offset"] = (int(dy), int(dx))
        return (int(dy), int(dx)), rec
    return None, rec


def _on_side(dy, dx, axis, side):
    """Keep only offsets that reach across the mark in the wanted direction."""
    if axis is None or not side:
        return True
    return (dy * axis[0] + dx * axis[1]) * side > 0


def _score(imgf, invalid, ry, rx, ref, dy, dx, h, w, prefer):
    """Ring RMSE for one candidate offset, or (None, None) if unusable."""
    yy, xx = ry + dy, rx + dx
    ok = (yy >= 0) & (yy < h) & (xx >= 0) & (xx < w)
    if ok.sum() < MIN_RING_USABLE * ry.size:
        return None, None
    yy, xx = yy[ok], xx[ok]
    free = ~invalid[yy, xx]
    if free.sum() < MIN_RING_USABLE * ry.size:
        return None, None
    got = imgf[yy[free], xx[free]]
    want = ref[ok][free]
    rmse = float(np.sqrt(np.mean((got - want) ** 2)))
    cost = rmse + DISTANCE_PENALTY * float(np.hypot(dy, dx))
    if (dy, dx) in prefer:
        cost -= NEIGHBOUR_BONUS
    return cost, rmse


# ------------------------------------------------------------------ the brush
def heal(img, mask, target_area=TARGET_TILE_AREA, radius=SEARCH_RADIUS,
         ring_width=RING_WIDTH, two_sided=True, log=None):
    """Heal every masked pixel, one tile at a time, committing as it goes.

    Sequential commits are not a style choice: the captures show each of the
    operator's strokes landing on the result of the last, and a tile that has
    been healed becomes valid context and a valid source for its neighbours.
    """
    img = np.asarray(img)
    mask = np.asarray(mask, dtype=bool)
    cur = img.copy()
    info = {"tiles": 0, "steps": []}
    if not mask.any():
        return cur, info

    tiles = plan_tiles(mask, target_area=target_area)
    info["tiles"] = len(tiles)
    remaining = mask.copy()
    chosen = []                                   # (tile, offset) already done
    for i, tile in enumerate(tiles):
        prefer = [off for t, off in chosen
                  if off is not None and (_dilate(tile, 1) & t).any()]
        ring = ring_of(tile, remaining, ring_width)
        detail = 0.0
        offset, srec = None, {"ring_px": int(ring.sum())}
        if ring.any():
            ry, rx = _subsample(np.nonzero(ring), RING_SAMPLE_MAX)
            luma = cur[ry, rx].astype(np.float64).mean(axis=1)
            detail = _plane_residual(luma, ry, rx)
        second, axis = None, None
        if detail >= SMOOTH_DETAIL:
            axis = tile_axis(tile) if two_sided else None
            offset, srec = search_source(cur, tile, remaining, radius=radius,
                                         ring_width=ring_width, prefer=prefer,
                                         axis=axis, side=1 if axis else 0)
            if axis is not None:
                second, srec2 = search_source(cur, tile, remaining,
                                              radius=radius,
                                              ring_width=ring_width,
                                              prefer=prefer, axis=axis, side=-1)
                if offset is None:
                    offset, second, srec = second, None, srec2
                elif second is not None:
                    srec["ring_rmse_2"] = srec2.get("ring_rmse")
        cur = poisson_fill(cur, tile, offset=offset, source=cur,
                           offset2=second, axis=axis if second else None)
        remaining &= ~tile
        chosen.append((tile, offset))
        rec = {"i": i, "px": int(tile.sum()),
               "mode": ("two-sided" if second else
                        "exemplar" if offset is not None else "membrane"),
               "offset": list(offset) if offset else None,
               "offset2": list(second) if second else None,
               "ring_detail": round(float(detail), 3),
               "ring_rmse": srec.get("ring_rmse")}
        info["steps"].append(rec)
        if log:
            log(f"[{i + 1}/{len(tiles)}] {rec['mode']} px={rec['px']} "
                f"detail={rec['ring_detail']} rmse={rec['ring_rmse']} "
                f"offset={rec['offset']}")
    return cur, info


# ----------------------------------------------------------------------- CLI
def main(argv=None):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    ap = argparse.ArgumentParser(prog="lw_clean_heal")
    ap.add_argument("--image", required=True)
    ap.add_argument("--mask", required=True, help="white = heal")
    ap.add_argument("--out", required=True)
    ap.add_argument("--target-area", type=int, default=TARGET_TILE_AREA)
    ap.add_argument("--radius", type=int, default=SEARCH_RADIUS)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    with Image.open(args.image) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    with Image.open(args.mask) as im:
        mask = np.asarray(im.convert("L")) > 127
    out, info = heal(rgb, mask, target_area=args.target_area,
                     radius=args.radius, log=None if args.quiet else print)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".part"
    Image.fromarray(out).save(tmp, format="PNG")
    os.replace(tmp, args.out)
    modes = {}
    for s in info["steps"]:
        modes[s["mode"]] = modes.get(s["mode"], 0) + 1
    print(json.dumps({"out": args.out, "mask_px": int(mask.sum()),
                      "tiles": info["tiles"], "modes": modes}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
