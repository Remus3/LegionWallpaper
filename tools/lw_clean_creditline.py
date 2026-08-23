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


def mask_from_hits(shape, hits, pad=PAD, band=BAND):
    """Solid boxes around every read, padded, and clipped to the band."""
    h, w = int(shape[0]), int(shape[1])
    mask = np.zeros((h, w), dtype=bool)
    by0, by1 = band_slice(h, band)
    for rec in hits:
        for x0, y0, x1, y1 in _credit_span(rec):
            mask[max(by0, y0 - pad):min(by1, y1 + pad),
                 max(0, x0 - pad):min(w, x1 + pad)] = True
    return mask


def glyph_mask(img, box_mask, pct=GLYPH_PCT, grow=GLYPH_GROW):
    """Narrow a verified box down to the pixels the text actually lands on."""
    box_mask = np.asarray(box_mask, dtype=bool)
    if not box_mask.any():
        return box_mask.copy()
    lum = np.asarray(img, dtype=np.float64).mean(axis=2)
    hp = np.abs(_highpass(lum, win=HP_WIN))
    thr = float(np.percentile(hp[box_mask], pct))
    g = box_mask & (hp >= thr)
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
        mask = mask_from_hits(rgb.shape, hits, pad=args.pad)
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
