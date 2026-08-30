"""Find the DeviantArt credit line: it is TEXT, so read it.

Mask generation has been the open problem since the automated lane closed, and
the investigation on 2026-08-22 found that the question had been mis-posed. The
centre-overlay template does work - it locates the DA LOGO on these frames at a
correlation of 0.75, and rendering its mask over the frame shows it sitting
exactly on the logo. What it does not find is the CREDIT LINE, and the credit
line is what the operator actually cleans.

The reason is structural. The template is a median over 19 frames from mixed
uploaders, and the credit line carries the uploader's name - 105-cleanup reads
SLIMSHADYWALLPAPER, 107-cleanup reads SMALLTAVERNWALLPAPER - so the text
averages away in the stack while the logo, identical everywhere, survives. No
amount of thresholding a template that does not contain the text will find it.

But the credit line is text, and text can be read:

  - both gold captures put it in the same place, horizontally centred at about
    0.69 of frame height, so OCR is shown a BAND rather than a 2560x1440 frame;
  - a semi-transparent line is invisible to OCR at native contrast, so the band
    is enhanced two ways - a high-pass boost and a percentile stretch - and the
    hits are unioned, because the two captures are read best by different ones;
  - the hit is SELF-VERIFYING: the string contains DEVIANTART. That is a
    property no contrast measure has, and it is why this is not the residue
    detector wearing a new hat.

Measured against the operator's own brush masks, the boxes land at 94.8 percent
(105) and 98.4 percent (107) precision - almost every pixel OCR claims is inside
the region the operator themselves decided to work.

The reader is injected and lazily imported, so this module and its tests stay in
the fast CI lane; easyocr lives in the lw-clean venv.

  python tools/lw_clean_creditline.py --image in.png --mask-out mask.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Where the credit line sits, as a fraction of frame height. Measured on the two
# gold captures: 105 puts its line at 0.668-0.716 and 107 at about 0.688, both
# horizontally centred. That is TWO observations - the band is deliberately
# wider than they need, and a frame whose line falls outside it will simply not
# be found rather than mis-found.
BAND = (0.62, 0.76)

# Enhancements. Neither wins on both captures - 105 reads best off the high-pass
# (conf 0.725 against 0.184 stretched) and 107 off the stretch (0.745 against
# 0.378) - so both are run and the hits unioned.
HP_WIN = 15
HP_GAIN = 6.0
STRETCH_PCT = (2.0, 98.0)

# The string the mark always carries, and how far OCR may garble it. Observed
# reads include DEVIANTAR, DEVIANFART and DEMIANTAR, so an exact match would
# reject the very hits this exists to catch.
NEEDLE = "DEVIANTART"
MAX_EDITS = 3
MIN_TEXT = 8

# Refining the read box down to the GLYPHS.
#
# A solid box is the right PLACE and the wrong SHAPE: on 105 it covers 99.95
# percent of the operator's brush, but handing the filler a 589x72 slab to
# invent breaks a line and the rollback reverts the whole step. The operator's
# own mask is stroke-shaped and covers the same region in 21184 px, not 42328.
#
# Thresholding the high-pass INSIDE a verified box is not the global contrast
# residue this repo falsified. That measure had to decide whether a mark was
# there; this one already knows - the string said DEVIANTART - and only has to
# decide which pixels it lands on.
#
# Swept end to end on 105 (percentile x growth, 9 cells, in-mask distance to the
# operator's final): the best cell is p88 grow 4, at 11.56 against 15.45
# untouched and their own 8.08, with the rollback committing every spot. That is
# ONE slug choosing one of nine cells, so these two numbers are a starting point
# and not a calibration.
GLYPH_PCT = 88.0
GLYPH_GROW = 4

# Pad around the read box, in pixels. Derived from 105, where the operator's
# brush runs 21px above and 15px below the OCR box and 21px to its left: they
# brush a little wider than the glyphs, and the measured brush is 1.05 to 1.65x
# the pixels that actually change.
PAD = 20

# Ink that stands out from its OWN neighbourhood.
#
# MEASURED 2026-08-29 over all 39 queue slugs. `percentile(hp[box], 88)` is set
# by whatever is brightest anywhere inside the box, so one bright art highlight
# raises the bar over the overlay's own strokes and the whole line survives -
# soraka-...-givemenine keeps 9 percent of its ring ink with the box fully
# covering the ring, akali-godly-deer 1 percent, bayonetta-...-dm7iirw 1
# percent. A robust ceiling on the same distribution (median + k*MAD) does NOT
# fix it and was tried first: those three slugs have BROAD box distributions
# (k = (p88-med)/MAD of 3.26, 3.70, 3.43) while the healthy controls have
# NARROW ones (105 4.51, 107 6.38, 123f 9.20), so the ceiling bites on exactly
# the wrong slugs.
#
# What works is asking a LOCAL question - does this pixel stand out from the
# |hp| level around it - which no single feature elsewhere in the box can
# move. Swept over the 39 slugs at win 31/65/101 x beta 1.6/2.0/2.4/2.8:
# win 65 beta 2.4 lifts median ring-ink keep from 0.48 to 0.77 for a median
# mask growth of 1.07x (p90 1.17x, worst 1.46x). The floor is the noise guard -
# the ratio test alone fires on sensor noise in a flat region - and 4.0 is free
# (keep 0.77, identical walk coverage), where 6.0 already costs keep 0.59.
LOCAL_WIN = 65
LOCAL_BETA = 2.4
LOCAL_FLOOR = 4.0

# Walking left to where the mark actually starts.
#
# The mask's left edge used to be `box_x0 - PAD` and nothing else, and the
# mark's true left extent is not a constant: 20-21px on small type (ring 17px
# wide, 3-4px gap), 35px on large type (ring 28px, 8px gap), 43-44px at scale
# 1.2 (akali, 281-cleanup), and 96px or more where easyocr drops leading
# letters - 124f reads TAVERIUM DEVIANTART COM for SMALLTAVERN..., which no pad
# rule can predict. Ring ink lay outside the mask on 22 of the 39 slugs.
#
# LEFT_GAP must clear the space between the logo and the first letter, measured
# at 12 empty columns on 270f - hence 14, and 16 already walks a control 93px
# into artwork. LEFT_MINROWS 4 is the smallest column ink count that keeps the
# controls at 22px or less; 3 lets one of them run to 94px. LEFT_MAX 120 has
# headroom over the largest credibly-located mark start in the queue (96px,
# blood-moon-...-dmhckey) without being reachable by any control.
LEFT_GAP = 14
LEFT_MINROWS = 4
LEFT_MAX = 120

# How many mark components the walk may take, and what is too narrow to count
# as one. LEFT_MAX bounds a single run and does NOT bound a CHAIN of them, and
# the chain is the real failure: on 270f the walk took the ring, crossed a
# 4-column gap onto a 5-column speck at 972..976, and kept stepping - 90px of
# extension where the mark starts at 36px, i.e. 55px of artwork inside the mask
# on a frame already flagged for collateral damage.
#
# MEASURED 2026-08-30 over all 39 slugs, over-reach past the NCC-registered
# ring left edge (walk only, pad excluded):
#   unlimited  median 2  p90 25  max 67   5 slugs past 20px   coverage 20/21
#   hop <= 3   median 2  p90 19  max 55   4 slugs past 20px   coverage 20/21
#   hop <= 2   median 2  p90 18  max 55   2 slugs past 20px   coverage 20/21
#   hop <= 1   median 0  p90  5  max 15   0 slugs past 20px   coverage 17/21
# Hop 1 alone costs four slugs their logo (286f, 221-cleanup,
# queen-of-the-saltwind, 281-cleanup) because on those the FIRST run out of the
# read box is a 5-7px speck and the logo is the second. A speck is not a mark
# component - the logo measured 17-34px wide on every slug where it registered
# - so a run narrower than LEFT_STUB is taken without spending the budget.
# That recovers coverage to 20/21 at over-reach median 1 / p90 8 / max 39 with
# 2 slugs past 20px, which beats the unbounded walk on every axis. Setting
# LEFT_STUB to 0 buys the strictest column (hop 1 alone) if over-reach ever
# needs to go to zero at the cost of those four logos.
LEFT_HOPS = 1
LEFT_STUB = 10

# Artwork that only PASSES THROUGH the region.
#
# MEASURED 2026-08-30 over all 39 queue slugs, rebuilding every mask from the
# recorded box (the rebuild reproduces each recorded mask_px exactly): the fill
# destroys 75.2 percent of every strong source edge that falls inside a mask,
# and 75.7 percent of the flattened pixels belong to source structures with a
# limb 6px or more OUTSIDE the mask. That is artwork crossing the band, not
# credit-line stroke. The selection is a threshold, so on busy art the art's
# own sharpest pixels ARE the selected ink: the mask recruits them, hands them
# to the fill and the fill flattens them.
#
# The credit line's strokes are bounded by the text line and sit at least PAD
# px inside the region; art crossing the band has limbs running out of it. So
# ink further than LIMB_GAP outside the region is seeded and followed back
# along the selection for LIMB_REACH steps, and what it reaches is refused.
#
# LIMB_REACH is the whole trade, and it is PAD + LIMB_GAP on purpose: the pad
# is slack this module added around the read, while the read box itself is
# EVIDENCE - OCR spelled DEVIANTART off it - so the escape may consume the
# slack and must stop at the evidence. Measured over the queue against the
# NCC-registered mark objects (20 slugs registering at ncc >= 0.60), strong
# source edges inside the masks against the operator's own brush ink on the
# two hand-cleaned captures:
#   reach   strong px   cut   ridge px   cut   operator ink   logos losing ink
#      0      144102     0%     34458     0%      100.0%             0
#     20      124957    13%     29958    13%       97.6%             0
#     24      119587    17%     28705    17%       96.6%             0
#     32      110153    24%     26508    23%       94.1%             0
#     36      106168    26%     25656    26%       93.3%             1
#     40      102381    29%     24784    28%       92.3%             2
#     96       82714    43%     20256    41%       81.2%             2
# So there is measured headroom to 32 and the first mark loss is at 36; 24
# keeps the promise that verified pixels are never dropped, which no larger
# value can make. Raising it is this number and the test that pins it, and it
# buys damage cut for mark risk.
#
# The promise has one exception and it is the BAND, not the reach: where the
# band clips the pad the escape enters from the clipped side. Measured, that
# is 2 of the 39 slugs - akali-godly-deer (line at the band's first row, so no
# pad above it, 615 px of box-interior ink dropped) and 281-cleanup (3 px of
# pad short at the bottom, 107 px) - and on both the dropped ink is artwork on
# inspection: akali keeps 442 of 442 registered logo px and has the queue's
# lowest in-box ink retention at 93.4 percent.
#
# Dropping the whole STRUCTURE instead - the first mechanism measured - cuts
# 41 percent at ratio 0.10, but it takes the copyright glyph on
# bayonetta-...-dm7iiug outright (0 of 159 px kept: the glyph sits ON a dark
# art edge and merges with it into one structure) and costs 10 percent of the
# operator's own brush ink. A ratio does not fix that - that structure is 337
# px in and 340 px out - so the reach is what bounds the damage instead.
LIMB_GAP = 4
LIMB_REACH = 24


def band_slice(height, band=BAND):
    return int(height * band[0]), int(height * band[1])


def _highpass(lum, win=HP_WIN):
    """Local-mean subtraction - the same estimator the overlay lane uses."""
    k = int(win) | 1
    pad = k // 2
    a = np.pad(lum, pad, mode="edge")
    cs = np.cumsum(np.cumsum(a, axis=0), axis=1)
    cs = np.pad(cs, ((1, 0), (1, 0)), mode="constant")
    h, w = lum.shape
    box = (cs[k:k + h, k:k + w] - cs[0:h, k:k + w]
           - cs[k:k + h, 0:w] + cs[0:h, 0:w]) / float(k * k)
    return lum - box


def _boxmean(a, win):
    """Local mean of `a` - the complement of the high-pass, so no new estimator."""
    return a - _highpass(a, win=win)


def local_ink(img, win=LOCAL_WIN, beta=LOCAL_BETA, floor=LOCAL_FLOOR):
    """Pixels that stand out from THEIR OWN neighbourhood.

    Deliberately not a percentile of anything: a percentile over a region is
    decided by the region's brightest feature, which is the whole reason a
    bright art highlight was dropping the credit line's strokes.
    """
    lum = np.asarray(img, dtype=np.float64).mean(axis=2)
    ah = np.abs(_highpass(lum, win=HP_WIN))
    loc = np.maximum(_boxmean(ah, win), 1e-6)
    return (ah >= beta * loc) & (ah >= floor)


def left_extent(img, box, gap=LEFT_GAP, minrows=LEFT_MINROWS, cap=LEFT_MAX,
                ink=None, band=BAND, hops=LEFT_HOPS, stub=LEFT_STUB):
    """Where the mark really starts, walking left from the read box.

    Going left, cross up to `gap` columns carrying no mark-like ink to reach
    the next run of columns that do, then take that whole run - but only if the
    run ENDS before the cap. The mark is a bounded object; a run still going at
    the cap is artwork, and it is refused outright rather than truncated there.
    That distinction is one half of the fix: 270f's ring is 26 columns and then
    nothing, while 105-cleanup's mountain ridge lines run unbroken past 90px,
    and a walk that truncated at the cap would drag that control's mask 120px
    across the artwork.

    The other half is `hops`. Taking one run is finding the logo; taking run
    after run is walking into the artwork one legal-looking step at a time, and
    the cap cannot see it because the cap bounds a single run and not the
    chain. The budget is spent only on runs at least `stub` wide, because the
    speck that sits between the read box and the logo on several slugs is not a
    mark component and must not cost the logo its hop.

    An achromatic gate was measured here first, because the overlay is grey
    where 266f's own tagline is gold, and it does NOT separate these two: the
    105-cleanup ridge ink sits at saturation 5-8 while the 270f ring runs 9-21,
    so gating on it removes the mark before the artwork. At satmax 30 the
    queue's ring coverage falls from 14/15 to 11/15 and one control's
    extension drops to nothing, with the control extensions otherwise
    unchanged. It buys nothing and is not applied. Keying the ink on the
    strength of the glyph ink inside the box was measured too - a floor at 0.3x
    the in-box median is a no-op, 0.5x costs a slug, 0.7x costs four.
    """
    if ink is None:
        ink = local_ink(img)
    ink = np.asarray(ink, dtype=bool)
    h, w = ink.shape[:2]
    by0, by1 = band_slice(h, band)
    y0 = max(by0, min(h, int(box[1])))
    y1 = min(by1, max(y0, int(box[3])))
    x0 = max(0, min(w, int(box[0])))
    if y1 <= y0 or x0 <= 0:
        return x0
    lo = max(0, x0 - int(cap) - int(gap))
    counts = ink[y0:y1, lo:x0].sum(axis=0)
    left, taken = x0, 0
    while hops <= 0 or taken < hops:
        j, seen = left - 1, 0
        while j >= lo and seen < gap and counts[j - lo] < minrows:
            j -= 1
            seen += 1
        if j < lo or counts[j - lo] < minrows:
            return left
        k = j
        while k - 1 >= lo and counts[k - 1 - lo] >= minrows:
            k -= 1
        if x0 - k > cap:
            return left
        if (j - k + 1) >= stub:
            taken += 1
        left = k
    return left


def enhancements(band_rgb):
    """The band, twice: high-pass boosted and percentile stretched."""
    lum = np.asarray(band_rgb, dtype=np.float64).mean(axis=2)
    hp = np.clip(128.0 + HP_GAIN * _highpass(lum), 0, 255).astype(np.uint8)
    lo, hi = np.percentile(lum, STRETCH_PCT[0]), np.percentile(lum,
                                                              STRETCH_PCT[1])
    st = np.clip((lum - lo) / max(1e-6, hi - lo) * 255.0, 0, 255).astype(np.uint8)
    return [("highpass", np.stack([hp] * 3, axis=2)),
            ("stretch", np.stack([st] * 3, axis=2))]


def _norm(text):
    return "".join(c for c in str(text).upper() if c.isalnum())


def _edits(a, b):
    """Levenshtein distance. The strings are short; clarity beats cleverness."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def substring_edits(needle, haystack):
    """Fewest edits turning `needle` into SOME substring of `haystack`.

    Free start and end - row zero is all zeros and the answer is the minimum of
    the last row - because the read is a run-on of the uploader's name and the
    host, so the host has to be found inside it rather than matched whole.
    """
    if not needle:
        return 0
    prev = [0] * (len(haystack) + 1)
    for ca in needle:
        cur = [prev[0] + 1]
        for j, cb in enumerate(haystack, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return min(prev)


def looks_like_credit(text, needle=NEEDLE, max_edits=MAX_EDITS):
    """True when the read is a garbled DEVIANTART credit line."""
    s = _norm(text)
    if len(s) < MIN_TEXT:
        return False
    return substring_edits(needle, s) <= max_edits


def group_lines(reads, overlap=0.5):
    """Join reads that share a row into one LINE, ordered left to right.

    easyocr splits a credit line: 107-cleanup comes back as
    "SMALLTAVERNWALLPAPERDEVIAN" plus "ARTGOM", and neither half carries the
    host on its own. Joining them before matching is what lets the verification
    stay strict, and the union of their boxes is also the better mask - the
    ".COM" tail on 105 is a separate read worth another 6 percent of the
    operator's own brush.
    """
    lines = []
    for box, text, conf in sorted(reads, key=lambda r: (r[0][1], r[0][0])):
        placed = False
        for ln in lines:
            a0, a1 = box[1], box[3]
            b0, b1 = ln["box"][1], ln["box"][3]
            inter = max(0, min(a1, b1) - max(a0, b0))
            if inter >= overlap * min(a1 - a0, b1 - b0):
                ln["parts"].append((box, text, conf))
                ln["box"] = [min(ln["box"][0], box[0]), min(b0, a0),
                             max(ln["box"][2], box[2]), max(b1, a1)]
                placed = True
                break
        if not placed:
            lines.append({"box": list(box), "parts": [(box, text, conf)]})
    out = []
    for ln in lines:
        parts = sorted(ln["parts"], key=lambda r: r[0][0])
        out.append({"box": [int(v) for v in ln["box"]],
                    "text": " ".join(str(t) for _b, t, _c in parts),
                    "conf": round(float(max(c for _b, _t, c in parts)), 4),
                    "parts": len(parts),
                    "boxes": [[int(v) for v in b] for b, _t, _c in parts],
                    "texts": [str(t) for _b, t, _c in parts]})
    out.sort(key=lambda r: (r["box"][1], r["box"][0]))
    return out


def _credit_span(line):
    """The pixels of a verified line: its whole bounding box, gaps included.

    Two narrower rules were tried on 2026-08-22 and both MEASURED WORSE, so the
    whole span stands and this records why.

    Splitting the parts wherever a gap opened wider than the row is tall was
    written for 266f, where the poster's own gold tagline `PRECISION IS
    PERFECTION` shares a row with `VEXXSOUL.DEVIANTART` and the fill erased the
    artwork. It did not touch that case - easyocr returns
    `P E R F E C T I g WExXsou_DEVIANT}` as ONE read spanning both, so no
    partition of the parts can separate them - and it broke three slugs that had
    been working, because the credit line itself arrives in gapped pieces (261f
    `SLIMSNAD=` + 87px + `APERDEVIAN`; 286f `PEBANOL` + 67px + `MIANTART COM`;
    dark-cosmic `EFIANOIDEV` + 76px + `MART ART OM OM`). Dropping the piece that
    does not itself spell the host halves the mask and leaves the mark.

    Unioning the PARTS instead of taking the line's bounding box is the milder
    version of the same mistake: it withholds the gaps between reads. On 105 that
    is 79 mask pixels out of 22075, and it was enough to flip a blob from commit
    to revert and leave a readable line on the frame.

    266f needs a discriminator INSIDE the box - the credit overlay is achromatic
    where the tagline is saturated gold - not a different way of cutting up reads.
    """
    return [list(line["box"])]


def detect(img, reader, band=BAND, min_conf=0.0):
    """Read the credit line. `reader` is anything with easyocr's readtext API."""
    img = np.asarray(img)
    h = img.shape[0]
    y0, y1 = band_slice(h, band)
    sub = img[y0:y1]
    reads = []
    for _name, view in enhancements(sub):
        for box, text, conf in reader.readtext(view, detail=1):
            if float(conf) < min_conf:
                continue
            p = np.asarray(box, dtype=float)
            reads.append(((int(p[:, 0].min()), int(p[:, 1].min()) + y0,
                           int(p[:, 0].max()) + 1, int(p[:, 1].max()) + 1 + y0),
                          text, float(conf)))
    return [ln for ln in group_lines(reads) if looks_like_credit(ln["text"])]


def mask_from_hits(shape, hits, pad=PAD, band=BAND, img=None):
    """Solid boxes around every read, padded, and clipped to the band.

    Given `img`, the LEFT edge is measured instead of assumed - see
    `left_extent`. The measurement can only move that edge further left, never
    right, so a frame whose mark starts inside the pad is untouched and every
    caller with no pixels to hand keeps the old behaviour exactly.
    """
    h, w = int(shape[0]), int(shape[1])
    mask = np.zeros((h, w), dtype=bool)
    by0, by1 = band_slice(h, band)
    ink = None if img is None else local_ink(img)
    for rec in hits:
        for x0, y0, x1, y1 in _credit_span(rec):
            left = x0 if ink is None else left_extent(
                img, [x0, y0, x1, y1], ink=ink, band=band)
            mask[max(by0, y0 - pad):min(by1, y1 + pad),
                 max(0, left - pad):min(w, x1 + pad)] = True
    return mask


def _grow1(m):
    """One 8-connected dilation step, in numpy shifts."""
    out = m.copy()
    out[1:, :] |= m[:-1, :]
    out[:-1, :] |= m[1:, :]
    out[:, 1:] |= m[:, :-1]
    out[:, :-1] |= m[:, 1:]
    out[1:, 1:] |= m[:-1, :-1]
    out[1:, :-1] |= m[:-1, 1:]
    out[:-1, 1:] |= m[1:, :-1]
    out[:-1, :-1] |= m[1:, 1:]
    return out


def escaped_ink(sel, box_mask, gap=LIMB_GAP, reach=LIMB_REACH):
    """Selected ink a structure carries IN from outside the credit-line region.

    Seeded on the selection more than `gap` px outside the region and followed
    back along the selection for `reach` steps. A structure that continues
    well outside the region is artwork passing through it - see LIMB_REACH for
    what that is measured to be worth - and the mark's own strokes sit behind
    PAD px of slack that the default reach is sized never to cross, so on 37
    of the 39 queue slugs not one pixel INSIDE the read box can be reached at
    all. The other two are the ones whose band clips that slack.

    Followed per PIXEL rather than per structure on purpose. The overlay's
    strokes TOUCH art edges and merge with them into one component - measured
    on bayonetta-...-dm7iiug, where the copyright glyph and a dark diagonal
    edge are a single 700 px structure, 337 px of it inside the region and 340
    outside - so a verdict on the whole structure takes the glyph with the
    limb. A bounded reach takes the limb and stops before the glyph.

    The work is done on a window around the region, which is exact: a path
    that reaches the region within `reach` steps cannot leave it further than
    that.
    """
    sel = np.asarray(sel, dtype=bool)
    box_mask = np.asarray(box_mask, dtype=bool)
    out = np.zeros_like(sel)
    if int(reach) <= 0 or not box_mask.any():
        return out
    ys, xs = np.nonzero(box_mask)
    pad = int(reach) + int(gap) + 2
    y0 = max(0, int(ys.min()) - pad)
    y1 = min(sel.shape[0], int(ys.max()) + 1 + pad)
    x0 = max(0, int(xs.min()) - pad)
    x1 = min(sel.shape[1], int(xs.max()) + 1 + pad)
    s = sel[y0:y1, x0:x1]
    near = box_mask[y0:y1, x0:x1]
    for _ in range(int(gap)):
        near = _grow1(near)
    seeds = s & ~near
    for _ in range(int(reach)):
        nxt = _grow1(seeds) & s
        if int(nxt.sum()) == int(seeds.sum()):
            break
        seeds = nxt
    out[y0:y1, x0:x1] = seeds
    return out


def glyph_mask(img, box_mask, pct=GLYPH_PCT, grow=GLYPH_GROW, gap=LIMB_GAP,
               reach=LIMB_REACH):
    """Narrow a verified box down to the pixels the text actually lands on.

    The box percentile stays, unioned with the local ink test: the percentile
    is the better estimator wherever the box is mostly credit line, and the
    local test is what survives a bright art highlight sitting in the same box.
    A union also means no currently-kept pixel is ever lost, so the slugs that
    already clean correctly keep the mask they had.

    What the union cannot tell apart is the art's own sharpest pixels, and
    those are 75.7 percent of the damage the fill does, so the selection is
    then asked one more question per structure: does this ink come in from
    OUTSIDE the region - see `escaped_ink`. That is a narrowing WITHIN the
    verified box, which is what this function has always done; it is not a
    narrower read box, which was measured worse twice - see `_credit_span`.
    """
    box_mask = np.asarray(box_mask, dtype=bool)
    if not box_mask.any():
        return box_mask.copy()
    lum = np.asarray(img, dtype=np.float64).mean(axis=2)
    hp = np.abs(_highpass(lum, win=HP_WIN))
    thr = float(np.percentile(hp[box_mask], pct))
    sel = (hp >= thr) | local_ink(img)
    g = box_mask & sel & ~escaped_ink(sel, box_mask, gap=gap, reach=reach)
    for _ in range(int(grow)):
        g[1:, :] |= g[:-1, :]
        g[:-1, :] |= g[1:, :]
        g[:, 1:] |= g[:, :-1]
        g[:, :-1] |= g[:, 1:]
    return g & box_mask


# ----------------------------------------------------------------------- CLI
def _reader(gpu=True):
    import easyocr
    return easyocr.Reader(["en"], gpu=gpu, verbose=False)


def main(argv=None):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    ap = argparse.ArgumentParser(prog="lw_clean_creditline")
    ap.add_argument("--image", required=True)
    ap.add_argument("--mask-out")
    ap.add_argument("--json-out")
    ap.add_argument("--pad", type=int, default=PAD)
    ap.add_argument("--box", action="store_true",
                    help="keep the solid read box instead of narrowing it to "
                         "the glyphs (measured worse: the slab breaks lines)")
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args(argv)

    with Image.open(args.image) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    hits = detect(rgb, _reader(gpu=not args.cpu))
    rec = {"image": args.image, "hits": hits}
    if hits and args.mask_out:
        mask = mask_from_hits(rgb.shape, hits, pad=args.pad, img=rgb)
        if not args.box:
            mask = glyph_mask(rgb, mask)
        rec["shape"] = "box" if args.box else "glyphs"
        rec["mask_px"] = int(mask.sum())
        os.makedirs(os.path.dirname(os.path.abspath(args.mask_out)),
                    exist_ok=True)
        tmp = args.mask_out + ".part"
        Image.fromarray((mask * 255).astype(np.uint8)).save(tmp, format="PNG")
        os.replace(tmp, args.mask_out)
        rec["mask"] = args.mask_out
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)),
                    exist_ok=True)
        tmp = args.json_out + ".part"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rec, fh, indent=2)
        os.replace(tmp, args.json_out)
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
