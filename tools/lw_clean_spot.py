"""Spot healing, one blob at a time, with rollback.

Track C, and the place tracks A and B stop being interesting and start being
useful. The schedule this replaces commits every step unconditionally: it fills,
and whatever comes out is what you get. Four hand-clean captures say the
operator does not work that way - they treat one spot at a time, look at it, and
undo what made things worse.

Each blob of the mark is its own heal, and each of the three decisions is made
by a piece that was measured on its own first:

  WHERE     the blobs of the detector's own footprint. No residue detector is
            used to start: contrast residue is on the standing do-not-redo list
            as a starting detector, and the footprint is what the detector
            already decided.
  HOW BIG   the stroke size the art BEHIND the mark asks for (track A) sets
            how a blob is CUT UP, not how far it is grown - a distinction that
            cost a whole measured round to learn, see MARGIN_RATIO_SPOT. The
            margin itself stays small, and defaults to none when the mask handed
            in is already a brush mask.
  WORTH IT  the comparison layer (track B), scoped to the chords this blob's
            context actually touches, judged BEFORE against AFTER. A step that
            turns an intact chord into a broken one is undone.

The rollback rule is a comparison, not a threshold, and it is asymmetric on
purpose: a mark that survives is recoverable - the slug simply stays in the hand
queue - while art destroyed under it is not. Where the layer has nothing to say,
the fill stands: abstaining is not failing.

Nothing here approves anything. A run that holds a blob reports `held`, which
means the slug cannot leave the queue on this pass; the operator's eye remains
the acceptance bar (LEDGER 101-103).

  python tools/lw_clean_spot.py --image in.png --mask mark.png --out out.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_behind as BEHIND  # noqa: E402
import lw_clean_heal as HEAL  # noqa: E402
import lw_clean_lines as LINES  # noqa: E402
import lw_clean_tiled as T  # noqa: E402

# The brush stops at the mark's visible edge; its soft skirt is still mark.
HALO = 3

# Radii a scoped revert tries, smallest first. Not a calibration: the band grows
# until the ordinary verdict passes on the candidate, so the schedule only sets
# how finely that search is stepped. The last one is large enough that reaching
# it on a stroke-sized blob means the whole blob, which is the old behaviour.
REVERT_RADII = (4, 8, 16, 32)

# Margin a piece is given, as a multiple of its own area.
#
# The first version of this module grew each blob until its area matched
# `target_tile_area` of the art behind it, and that was a straight
# misreading, caught by running the whole thing on the captures: the target is
# how big a STROKE should be, not how much margin a spot needs. On dgk8f92 -
# soft snow, gradient 0.778, so a 40000px target against ~2300px blobs - it
# repainted 24x the mark and scored 22.59 against the operator's final where the
# one-shot fill scores 2.38. Same misreading in a different costume as the
# CONTEXT_RATIO = 5.0 the four captures falsified.
#
# So the target sets the SPLIT (below) and the margin is its own question. The
# capture that looked like it answered it - 209-cleanup, where the operator's
# single brush bbox was 117x52 against an 86x43 detector box, about 1.6x - is
# answering a DIFFERENT question: brush against DETECTOR BOX. The mask handed to
# this runner is already a brush mask, so adding that margin again repaints art
# nobody asked about. Swept against the operator's finals, in-mask distance,
# LaMa, lower better:
#
#   slug   untouched   one-shot   m=1.0   m=1.6   m=3.0
#   105        15.45       7.87    8.08   15.20   15.38
#   107        23.50      12.45   12.22   36.04   23.50
#   209        27.26       1.28    1.31    3.58    5.50
#   dgk        49.89       2.38    2.23    5.23   21.41
#
# m=1.0 matches or beats the one-shot fill on all four AND keeps per-blob
# rollback; every larger margin is monotonically worse. So the default is no
# margin at all, and the knob stays for the case this runner is handed a
# DERIVED mask rather than a brush mask - where a margin is a real question
# again and this table does not answer it.
MARGIN_RATIO_SPOT = 1.0

# A blob bigger than this multiple of the target is split into strokes; below
# it, one stroke covers the blob.
SPLIT_SLACK = 1.5

# Crop handed to the filler around the context mask.
CROP_MARGIN = 32

# How much of a line's pre-step strength a step has to leave standing.
#
# The obvious rule - "revert when an intact chord becomes broken" - is not
# enough on its own, and the reason is physical: a semi-transparent mark
# ATTENUATES the lines under it, so the pre-step frame is often already below
# the intact bar and no intact->broken transition can occur. Measured on the two
# captures that carry chords, as the fraction of the pre-fill ratio retained:
#
#   operator  0.947 / 0.937      accepted
#   lama      0.922 / 0.921      accepted
#   heal      0.543 / 0.496      rejected at 1:1
#   membrane  0.301 / 0.133      a blur by construction
#
# 0.75 sits in the middle of that gap, about 1.2x below the worst accepted case
# and 1.4x above the best rejected one. It is calibrated on eight observations
# and that is stated rather than hidden - it is tolerable here only because this
# is a ROLLBACK trigger and not an approval gate: firing it leaves the mark in
# place and the slug in the hand queue, which is recoverable, while the damage
# it prevents is not.
KEEP_FRACTION = 0.75


def stroke_size(img, footprint, region):
    """How big a stroke this art wants here, from the picture BEHIND the mark."""
    grad = BEHIND.local_gradient_behind(img, footprint, T.mask_bbox(region))
    return grad, T.target_tile_area(grad)


def _context_for(piece, others, margin=MARGIN_RATIO_SPOT):
    """A piece plus its margin, never reaching into another blob."""
    if margin <= 1.0:
        return piece.copy()
    ctx = T.grow_to_ratio(piece, margin)
    return (ctx & ~others) | piece


def plan_spots(img, mark_mask, footprint=None,
               margin=MARGIN_RATIO_SPOT, split=False):
    """(piece, context) pairs: the mark cut into strokes, each with its margin.

    Track A enters through the SPLIT, which is what the measured stroke area
    actually governs: smooth art is worked in fewer, larger strokes and busy art
    in more, smaller ones. The margin is a separate and much smaller question,
    and no context is ever allowed to reach into another blob - letting two
    steps share pixels would mean one silently re-filling the other's committed
    result.
    """
    mark = np.asarray(mark_mask, dtype=bool)
    if not mark.any():
        return []
    foot = mark if footprint is None else np.asarray(footprint, dtype=bool)
    blobs = HEAL.label_blobs(mark)
    blobs.sort(key=lambda b: (-int(b.sum()), T.mask_bbox(b)))
    out = []
    for b in blobs:
        others = mark & ~b
        _grad, target = stroke_size(img, foot, b)
        if split and int(b.sum()) > target * SPLIT_SLACK:
            pieces = HEAL.plan_tiles(b, target_area=target)
        else:
            pieces = [b]
        for piece in pieces:
            out.append((piece, _context_for(piece, others, margin)))
    return out


def relevant_chords(chords, region):
    """The chords whose predicted path actually enters this step's context."""
    h, w = region.shape
    keep = []
    for c in chords:
        pts = c.path
        yi = np.clip(np.rint(pts[:, 0]).astype(int), 0, h - 1)
        xi = np.clip(np.rint(pts[:, 1]).astype(int), 0, w - 1)
        if region[yi, xi].any():
            keep.append(c)
    return keep


def band_around(chords, shape, radius):
    """Everything within `radius` of these chords' predicted paths."""
    h, w = int(shape[0]), int(shape[1])
    m = np.zeros((h, w), dtype=bool)
    for c in chords:
        pts = np.asarray(c.path, dtype=float)
        yi = np.clip(np.rint(pts[:, 0]).astype(int), 0, h - 1)
        xi = np.clip(np.rint(pts[:, 1]).astype(int), 0, w - 1)
        m[yi, xi] = True
    return HEAL._dilate(m, int(radius)) if radius > 0 else m


def _damaged(before, after, chords, layer_mask, region):
    """The chords this step cost something, by either rule the verdict uses.

    Not just intact -> broken. Measured over the queue's own reverts, the two
    rules fire in the same order of magnitude - 9 broke a line and 12 lost
    strength - so scoping only the first would leave most reverts whole.
    """
    mine = relevant_chords(chords, region)
    if not mine:
        return []
    b = LINES.score(before, layer_mask, mine)
    a = LINES.score(after, layer_mask, mine)
    if b["n_chords"] == 0 or a["n_chords"] == 0:
        return []
    was = {tuple(r["p0"] + r["p1"]): r["ratio"] for r in b["chords"]}
    worse = {tuple(r["p0"] + r["p1"]) for r in a["chords"]
             if r["ratio"] < was.get(tuple(r["p0"] + r["p1"]), r["ratio"])}
    return [c for c in mine if tuple(list(c.p0) + list(c.p1)) in worse]


def scoped_revert(before, after, chords, layer_mask, region,
                  radii=REVERT_RADII):
    """Undo only the neighbourhood of the lines this step broke.

    A revert is all-or-nothing today, and that is what makes a thicker mask
    clean LESS rather than more: thickening merges the strokes into one blob,
    one chord across it breaks, and the whole fill dies with it - measured on
    akali-godly-deer, aatrox and miss-fortune, which come back UNTOUCHED at
    p40 (0 healed, 1 held). The stretch of mark with no line near it was never
    the problem and does not need to be given back.

    The radius is not a constant to guess at: the band GROWS until the existing
    verdict passes on the candidate, and if it takes the whole region then this
    was a whole revert all along. Returns (frame, band, reason), or three Nones
    when no radius saves the lines - a strength-loss revert has no broken chord
    to scope to and always lands there.
    """
    hurt = _damaged(before, after, chords, layer_mask, region)
    if not hurt:
        return None, None, None
    region = np.asarray(region, dtype=bool)
    for r in radii:
        band = band_around(hurt, region.shape, r) & region
        if not band.any() or int(band.sum()) >= int(region.sum()):
            continue
        cand = after.copy()
        cand[band] = before[band]
        action, _reason, _mb, _ma, _n = _verdict(before, cand, chords,
                                                 layer_mask, region)
        if action == "commit":
            return cand, band, f"scoped to {r}px around the damaged line"
    return None, None, None


def _pool_verdict(before, after, layer_mask, mine, label=""):
    """The verdict ONE kind of evidence gives, or None when it has none."""
    if not mine:
        return None
    b = LINES.score(before, layer_mask, mine)
    a = LINES.score(after, layer_mask, mine)
    if b["n_chords"] == 0 or a["n_chords"] == 0:
        return None
    was = {tuple(r["p0"] + r["p1"]): r["intact"] for r in b["chords"]}
    broke = [k for k, r in
             ((tuple(r["p0"] + r["p1"]), r) for r in a["chords"])
             if was.get(k) and not r["intact"]]
    if broke:
        return ("revert", f"{label}broke {len(broke)} of {b['n_chords']} lines",
                b["median_ratio"], a["median_ratio"], b["n_chords"])
    lost = 1.0 - a["median_ratio"] / max(b["median_ratio"], 1e-9)
    if a["median_ratio"] < b["median_ratio"] * KEEP_FRACTION:
        return ("revert",
                f"{label}lines lost {round(100 * lost)} percent of their "
                f"strength",
                b["median_ratio"], a["median_ratio"], b["n_chords"])
    return ("commit", f"{label}lines held", b["median_ratio"],
            a["median_ratio"], b["n_chords"])


def _verdict(before, after, chords, layer_mask, region):
    """Did this step turn an intact line into a broken one?

    Chords and stubs are judged SEPARATELY, and a revert from either stands.
    Pooling them into one median was measured to be wrong: over the 39-slug
    queue, 825 stubs entering the same median silenced NINE reverts the chords
    alone had fired - including both of 259f's, the slug scoped_revert was
    proven on, and one that had read "lines lost 73 percent of their strength".
    The broken-line rule is an any-rule and cannot be diluted; the strength rule
    is a median and can be, by weaker evidence that simply outnumbers it.

    So a stub may only ADD a verdict of its own. It never softens a chord's.
    """
    mine = relevant_chords(chords, region)
    weak = [c for c in mine if getattr(c, "kind", "chord") == "stub"]
    strong = [c for c in mine if getattr(c, "kind", "chord") != "stub"]
    v_strong = _pool_verdict(before, after, layer_mask, strong)
    v_weak = _pool_verdict(before, after, layer_mask, weak,
                           label="a stub says ")
    for v in (v_strong, v_weak):
        if v is not None and v[0] == "revert":
            return v
    for v in (v_strong, v_weak):
        if v is not None:
            return v
    return "commit", "no-evidence", None, None, 0


def run_spot_heal(img, mark_mask, inpaint, rollback=True,
                  margin=MARGIN_RATIO_SPOT, split=False,
                  crop_margin=CROP_MARGIN, log=None, scoped=False,
                  stubs=False):
    """Heal each blob of the mark on its own, undoing what breaks a line.

    `scoped` is opt-in and off by default, so nothing already measured moves
    until it is asked for. With it on, a step that breaks a line gives back only
    the band around that line instead of the whole blob - see scoped_revert.

    `stubs` is opt-in for the same reason and answers a different question:
    whether the step can see anything AT ALL. Measured over the 39-slug queue,
    269 of 357 steps carry no chord and commit whatever the filler returns; a
    stub reaches 153 of them. It is weaker evidence - one anchor, so erasure
    only - and it is proven against its own source frame before use. See
    lw_clean_lines.build_stubs.
    """
    img = np.asarray(img, dtype=np.uint8)
    mark = np.asarray(mark_mask, dtype=bool)
    cur = img.copy()
    plan = {"blobs": 0, "committed": 0, "held": 0, "partial": 0, "n_chords": 0,
            "n_stubs": 0, "steps": [], "status": "clean"}
    if not mark.any():
        return cur, plan

    layer_mask = HEAL._dilate(mark, HALO)
    chords = LINES.build_layer(img, layer_mask)
    plan["n_chords"] = len(chords)
    if stubs:
        extra = LINES.build_stubs(img, layer_mask)
        plan["n_stubs"] = len(extra)
        chords = chords + extra
    spots = plan_spots(img, mark, margin=margin, split=split)
    plan["blobs"] = len(spots)
    h, w = cur.shape[:2]

    for i, (blob, ctx) in enumerate(spots):
        bb = T.mask_bbox(ctx)
        x0, y0, x1, y1 = T.crop_box(bb[0], bb[1], bb[2], bb[3], crop_margin,
                                    w, h)
        before = cur.copy()
        crop = cur[y0:y1, x0:x1]
        cmask = (ctx[y0:y1, x0:x1].astype(np.uint8) * 255)
        filled = np.asarray(inpaint(crop, cmask), dtype=np.uint8)
        sel = cmask > 0
        region = cur[y0:y1, x0:x1]
        region[sel] = filled[sel]
        cur[y0:y1, x0:x1] = region

        grad, target = stroke_size(img, mark, blob)
        if rollback:
            action, reason, mb, ma, n = _verdict(before, cur, chords,
                                                 layer_mask, ctx)
        else:
            action, reason, mb, ma, n = "commit", "rollback off", None, None, 0
        reverted_px = 0
        if action == "revert" and scoped:
            cand, band, why = scoped_revert(before, cur, chords, layer_mask,
                                            ctx)
            if cand is not None:
                cur = cand
                reverted_px = int(band.sum())
                action, reason = "partial", why
        if action == "revert":
            cur = before
            plan["held"] += 1
            reverted_px = int(ctx.sum())
        elif action == "partial":
            plan["partial"] += 1
        else:
            plan["committed"] += 1
        rec = {"i": i, "blob_px": int(blob.sum()), "mask_px": int(ctx.sum()),
               "reverted_px": reverted_px,
               "blob_bbox": list(T.mask_bbox(blob)),
               "gradient_behind": round(float(grad), 4),
               "target_area": round(float(target), 1),
               "chords": int(n), "median_before": mb, "median_after": ma,
               "action": action, "reason": reason}
        plan["steps"].append(rec)
        if log:
            log(f"[{i + 1}/{len(spots)}] {action} ({reason}) blob="
                f"{rec['blob_px']} mask={rec['mask_px']} "
                f"grad={rec['gradient_behind']} chords={n} "
                f"{mb} -> {ma}")
    # A partial leaves mark on the frame on purpose, so it is no more "clean"
    # than a hold is: the slug stays in the queue either way.
    plan["status"] = "held" if plan["held"] or plan["partial"] else "clean"
    return cur, plan


# ----------------------------------------------------------------------- CLI
def _lama():
    from simple_lama_inpainting import SimpleLama
    from PIL import Image
    lama = SimpleLama()

    def _fn(crop_rgb, crop_mask_u8):
        out = lama(Image.fromarray(crop_rgb), Image.fromarray(crop_mask_u8))
        return np.asarray(out.convert("RGB"), dtype=np.uint8)[
            :crop_rgb.shape[0], :crop_rgb.shape[1]]
    return _fn


def main(argv=None):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    ap = argparse.ArgumentParser(prog="lw_clean_spot")
    ap.add_argument("--image", required=True)
    ap.add_argument("--mask", required=True, help="white = the mark")
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan-out")
    ap.add_argument("--no-rollback", action="store_true")
    ap.add_argument("--margin", type=float, default=MARGIN_RATIO_SPOT)
    ap.add_argument("--split", action="store_true",
                    help="cut a blob into stroke-sized pieces (measured worse "
                         "on large-area marks - see the module notes)")
    ap.add_argument("--engine", choices=("lama", "heal", "membrane"),
                    default="lama")
    args = ap.parse_args(argv)

    with Image.open(args.image) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    with Image.open(args.mask) as im:
        mark = np.asarray(im.convert("L")) > 127

    if args.engine == "lama":
        fn = _lama()
    elif args.engine == "heal":
        def fn(crop_rgb, crop_mask_u8):
            out, _info = HEAL.heal(crop_rgb, crop_mask_u8 > 127)
            return out
    else:
        def fn(crop_rgb, crop_mask_u8):
            return HEAL.poisson_fill(crop_rgb, crop_mask_u8 > 127, offset=None)

    out, plan = run_spot_heal(rgb, mark, fn, rollback=not args.no_rollback,
                              margin=args.margin, split=args.split, log=print)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".part"
    Image.fromarray(out).save(tmp, format="PNG")
    os.replace(tmp, args.out)
    plan["out"] = args.out
    if args.plan_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.plan_out)),
                    exist_ok=True)
        tmp = args.plan_out + ".part"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(plan, fh, indent=2)
        os.replace(tmp, args.plan_out)
    print(json.dumps({k: v for k, v in plan.items() if k != "steps"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
