"""Face-key correction - put the generated face on the body's light plane.

The operator's complaint on the shipped lw-gen frames was that the face reads
as cropped onto the body. Measured against the 21 real Ahri splashes, face skin
in real splash art sits **+24.3 levels** above body skin and carries **0.83x**
its modelling (luminance std). The shipped generator produces +9.9 / 0.62 - a
flatter, under-keyed face on a more strongly modelled body, which is exactly
that read.

Three levers were measured and failed before this one (see
`docs/GEN_FACE_REALISM_2026-08-16.md`): four lighting-tag arms, two CFG arms,
and a face-region img2img refinement at 3x effective resolution - the last one
moved the key the WRONG way at every strength, which is what ruled out
"the face is flat because it is small".

So the correction is deterministic and works in pixels:

  gain   = 0.83 * body_std / face_std      (clipped)
  target = body_mean + 24.3
  out    = rgb * (target_luminance / luminance)

MULTIPLICATIVE on purpose - an additive lift pushes skin toward grey, and the
whole point is to move light, not colour. Applied through a weight map whose
INTERIOR IS 1.0: blurring a mask directly leaves the interior at a fraction of
one, so only a fraction of the computed shift lands. That bug is why the first
prototype missed its target and moved the key downward.

Pure numpy - the face detector is imported lazily in the CLI only, so importing
this module in CI pulls nothing heavy.
"""
import argparse
import glob
import json
import os
import shutil
import sys

import numpy as np

# Measured on the 21 real Ahri splashes (tools/models/lora_datasets/ahri).
CORPUS_OFFSET = 24.3      # face-skin mean minus body-skin mean, in levels
CORPUS_RATIO = 0.83       # face-skin std over body-skin std
CORPUS_BAND = {           # p10..p90 of the same corpus - the validation band
    "level_offset": (-3.0, 45.0),
    "modelling_ratio": (0.64, 1.26),
}
GAIN_CLIP = (0.85, 1.35)  # tight: 1.8 crushed lash lines to black (see MAX_DARKEN)
MAX_DARKEN = 12.0        # a pixel may never lose more than this many levels
MAX_BRIGHTEN = 70.0      # nor gain more, so speculars cannot be driven to clip
CRUSH_LIMIT = 0.0005     # fraction of frame newly <= 8; above this the pass is refused
BLOWOUT_LIMIT = 0.0005   # fraction newly >= 250
SKIN_CHROMA_TOL = 0.045
LUM_WINDOW = 90.0        # skin must sit within this many levels of the seed median
PASSES = 2               # re-measure and apply the residual once
STEPS = (1.0, 0.6, 0.3)  # damped step search - full strength can overshoot


def key_targets(face_mean, face_std, body_mean, body_std,
                offset=CORPUS_OFFSET, ratio=CORPUS_RATIO, gain_clip=GAIN_CLIP):
    """Return (gain, target_mean) that put the face in the corpus relationship."""
    gain = (ratio * float(body_std)) / max(float(face_std), 1e-6)
    gain = float(np.clip(gain, gain_clip[0], gain_clip[1]))
    return gain, float(body_mean) + float(offset)


def _box_blur(a, k, pad_mode="edge"):
    """Separable box blur.

    `pad_mode` is load-bearing and defaults to EDGE. Zero padding depresses the
    result near the frame border, which biases the shading/detail split - the
    detail term inherits the deficit and the correction then double-counts it
    (measured: a synthetic frame overshot its target by +22 levels). The mask
    feathering is the one caller that WANTS zero padding, so that the weight
    tapers to nothing at the image edge; it asks for it explicitly.
    """
    k = max(3, int(k) | 1)
    out = np.asarray(a, dtype=np.float64)
    for axis in (0, 1):
        pad = np.pad(out, k // 2, mode=pad_mode)
        acc = np.zeros_like(out)
        for d in range(k):
            if axis == 0:
                acc += pad[d:d + out.shape[0], k // 2:k // 2 + out.shape[1]]
            else:
                acc += pad[k // 2:k // 2 + out.shape[0], d:d + out.shape[1]]
        out = acc / k
    return out


def feathered_weight(mask, feather_px=15):
    """Soft weights that are 1.0 across the mask INTERIOR and taper outside.

    A plain blur of the mask is what broke the first attempt: it drops the
    interior well below 1.0, silently scaling the correction down. Here the
    blur is renormalised against a blur of the same shape so the interior
    saturates, and the result is clipped back to the [0, 1] range.
    """
    m = np.asarray(mask, dtype=np.float64)
    if not m.any():
        return np.zeros_like(m)
    # CLOSE first. A skin mask is speckled - eyes, brows, lips and highlights
    # punch holes in it - so blurring it directly never reaches 1.0 anywhere,
    # which is precisely how the first prototype scaled its own correction
    # away. Closing fills those holes so the region reads as solid.
    solid = (_box_blur(m, feather_px, pad_mode="constant") > 0.15).astype(np.float64)
    solid = np.maximum(solid, m)
    # Then a plain blur gives interior 1.0 with the taper on the boundary; the
    # 0.9 divisor makes the saturation robust to a ragged edge.
    return np.clip(_box_blur(solid, feather_px, pad_mode="constant") / 0.9, 0.0, 1.0)


def luminance(rgb):
    a = np.asarray(rgb, dtype=np.float64)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def shading_split(lum, face_width):
    """Split luminance into low-frequency shading and high-frequency detail.

    THE CORRECTION MUST ONLY TOUCH THE SHADING. Scaling raw luminance about its
    mean amplifies every deviation, including the fine dark strokes that draw
    lashes, lash lines, nostrils and lip lines - which is exactly the "mascara
    like black line" the operator reported, and why a gain of 1.8 darkened
    Katarina by up to 113 levels. Detail is carried through untouched.
    """
    k = max(9, int(face_width // 3) | 1)
    low = _box_blur(np.asarray(lum, dtype=np.float64), k)
    return low, np.asarray(lum, dtype=np.float64) - low


def apply_face_key(rgb, mask, weight, gain, target_mean, face_width=None):
    """Return `rgb` with the masked region's SHADING keyed to (gain, target_mean).

    Outside the weight map the output is byte-identical to the input. Inside it,
    per-pixel movement is bounded by MAX_DARKEN / MAX_BRIGHTEN so the correction
    can never manufacture black strokes or blow highlights out.
    """
    a = np.asarray(rgb, dtype=np.float64)
    lum = luminance(a)
    sel = np.asarray(mask, dtype=bool)
    if not sel.any():
        return a.astype(np.uint8)
    if face_width is None:
        cols = np.where(sel.any(axis=0))[0]
        face_width = max(9, int(cols.max() - cols.min()) if cols.size else 9)
    low, detail = shading_split(lum, face_width)
    face_low_mean = float(low[sel].mean())
    new_low = (low - face_low_mean) * float(gain) + float(target_mean)
    new_lum = new_low + detail
    # Bound the movement BEFORE it becomes a scale factor.
    new_lum = np.maximum(new_lum, lum - MAX_DARKEN)
    new_lum = np.minimum(new_lum, lum + MAX_BRIGHTEN)
    new_lum = np.clip(new_lum, 2.0, 250.0)
    scale = np.divide(new_lum, np.maximum(lum, 1e-6))
    w = np.asarray(weight, dtype=np.float64)
    scale = 1.0 + (scale - 1.0) * w
    return np.clip(a * scale[..., None], 0, 255).astype(np.uint8)


def harm(before_rgb, after_rgb):
    """(crush, blowout) - fractions of the frame newly crushed or blown out."""
    x = luminance(np.asarray(before_rgb, dtype=np.float64))
    y = luminance(np.asarray(after_rgb, dtype=np.float64))
    crush = float(((y <= 8) & (x > 8)).mean())
    blow = float(((y >= 250) & (x < 250)).mean())
    return crush, blow


def skin_mask(rgb, seed_box, tol=SKIN_CHROMA_TOL, lum_window=LUM_WINDOW):
    """Boolean skin mask from the chroma of the pixels inside `seed_box`.

    The luminance window is not cosmetic: without it, blown highlights and deep
    shadows that merely share skin CHROMA join the set and drag both statistics.
    It is the stricter of the two definitions measured on 2026-08-16, and it is
    the one the corpus band was calibrated with, so the tool and the yardstick
    must agree on it or the tool grades its own homework on an easier scale.
    """
    a = np.asarray(rgb, dtype=np.float64)
    x0, y0, x1, y1 = [int(v) for v in seed_box]
    seed = a[y0:y1, x0:x1].reshape(-1, 3)
    if seed.size < 30:
        return np.zeros(a.shape[:2], dtype=bool)
    seed_chroma = np.median(seed / (seed.sum(axis=1, keepdims=True) + 1e-6), axis=0)
    chroma = a / (a.sum(axis=2, keepdims=True) + 1e-6)
    close = np.sqrt(((chroma - seed_chroma) ** 2).sum(axis=2)) < tol
    lum_ok = np.abs(luminance(a) - float(np.median(seed))) < lum_window
    return close & lum_ok


def measure(rgb, face_box):
    """(level_offset, modelling_ratio) for a frame, or None when skin is scarce."""
    a = np.asarray(rgb, dtype=np.float64)
    lum = luminance(a)
    x0, y0, x1, y1 = [int(v) for v in face_box]
    fw, fh = x1 - x0, y1 - y0
    seed = (x0 + fw // 3, y0 + fh // 3, x1 - fw // 3, y1 - fh // 3)
    skin = skin_mask(a, seed)
    box = np.zeros(skin.shape, dtype=bool)
    box[y0:y1, x0:x1] = True
    fs, bs = skin & box, skin & (~box)
    if fs.sum() < 200 or bs.sum() < 200:
        return None
    return (float(lum[fs].mean() - lum[bs].mean()),
            float(lum[fs].std() / max(lum[bs].std(), 1e-6)))


def _distance(m, offset=CORPUS_OFFSET, ratio=CORPUS_RATIO):
    """How far a (level_offset, modelling_ratio) pair sits from the corpus.

    Level is in 0..255 levels and ratio is dimensionless, so the ratio term is
    scaled to put the two on a comparable footing - 0.1 of ratio is treated as
    worth about 3 levels, which is the corpus band's own relative width.
    """
    if m is None:
        return float("inf")
    return abs(m[0] - offset) + 30.0 * abs(m[1] - ratio)


def in_band(level_offset, modelling_ratio, band=CORPUS_BAND):
    lo, hi = band["level_offset"]
    rlo, rhi = band["modelling_ratio"]
    return bool(lo <= level_offset <= hi and rlo <= modelling_ratio <= rhi)


def correct_frame(rgb, face_box, feather_px=15, offset=CORPUS_OFFSET,
                  ratio=CORPUS_RATIO, band=CORPUS_BAND):
    """Key one frame. Returns (out_rgb, before, after) measurement tuples."""
    a = np.asarray(rgb, dtype=np.float64)
    lum = luminance(a)
    x0, y0, x1, y1 = [int(v) for v in face_box]
    fw, fh = x1 - x0, y1 - y0
    seed = (x0 + fw // 3, y0 + fh // 3, x1 - fw // 3, y1 - fh // 3)
    skin = skin_mask(a, seed)
    box = np.zeros(skin.shape, dtype=bool)
    box[y0:y1, x0:x1] = True
    fs, bs = skin & box, skin & (~box)
    before = measure(a, face_box)
    if before is None or fs.sum() < 200 or bs.sum() < 200:
        return a.astype(np.uint8), before, before
    # GUARDED iteration. A plain "apply, then apply the residual" loop is NOT
    # convergent here: each pass shifts which pixels the skin mask selects, so
    # pass two can push a frame back past the target (measured - one frame went
    # +13.5 -> -2.7 that way). Each pass is therefore kept only if it moves the
    # frame CLOSER to the corpus relationship, and the best pass wins.
    best = a
    best_score = _distance(before, offset, ratio)
    before_in_band = in_band(*before, band=band)
    cur = a
    for _ in range(PASSES):
        lum_i = luminance(cur)
        skin_i = skin_mask(cur, seed)
        fs_i, bs_i = skin_i & box, skin_i & (~box)
        if fs_i.sum() < 200 or bs_i.sum() < 200:
            break
        gain, target_mean = key_targets(lum_i[fs_i].mean(), lum_i[fs_i].std(),
                                        lum_i[bs_i].mean(), lum_i[bs_i].std(),
                                        offset=offset, ratio=ratio)
        w = feathered_weight(fs_i, feather_px)
        # Damped step search: a full-strength correction fixes the modelling
        # ratio but can carry the level past the target, and the guard then
        # (correctly) throws the whole pass away. Trying fractional steps means
        # such a frame gets a smaller correction rather than none.
        improved = False
        for step in STEPS:
            cand = apply_face_key(cur, fs_i, w * step, gain, target_mean,
                                  face_width=x1 - x0).astype(np.float64)
            crush, blow = harm(a, cand)
            if crush > CRUSH_LIMIT or blow > BLOWOUT_LIMIT:
                continue          # this step manufactures black strokes or clipping
            m_cand = measure(cand, face_box)
            score = _distance(m_cand, offset, ratio)
            # Never trade a frame that is already inside the corpus band for a
            # nominally shorter distance outside it. Measured over 57 frames,
            # distance-only acceptance pushed 3 in-band frames OUT.
            if before_in_band and not (m_cand and in_band(*m_cand, band=band)):
                continue
            if score < best_score:
                best, best_score, cur, improved = cand, score, cand, True
                break
        if not improved:
            break
    return best.astype(np.uint8), before, measure(best, face_box)


# --------------------------------------------------------------------------
# CLI (lazy heavy deps).
# --------------------------------------------------------------------------
def _detect_face(path, weights):
    from ultralytics import YOLO  # lazy heavy dep

    model = _detect_face.model = getattr(_detect_face, "model", None) or YOLO(weights)
    res = model.predict(source=path, conf=0.30, verbose=False, device=0)
    boxes = [b for r in res for b in r.boxes.xyxy.cpu().numpy()]
    if not boxes:
        return None
    boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    return [int(round(v)) for v in boxes[0][:4]]


BANDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "lw_gen_facekey_bands.json")
MIN_BAND_N = 5           # fewer real images than this cannot support a band


def load_bands(path=BANDS_PATH):
    """Per-champion targets, or {} when the file is absent."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def targets_for(champion, bands=None):
    """(offset, ratio, band, source) for a champion.

    Per-champion when the corpus carries enough real art for that champion,
    otherwise the corpus-wide default - never silently the Ahri numbers, which
    is what the single global target actually was.
    """
    bands = load_bands() if bands is None else bands
    key = (champion or "").strip().lower().replace(" ", "-")
    entry = bands.get(key)
    if entry and entry.get("n", 0) >= MIN_BAND_N:
        src = f"champion:{key} (n={entry['n']})"
    else:
        entry = bands.get("_default")
        src = f"corpus-default (n={entry['n']})" if entry else "built-in"
    if not entry:
        return CORPUS_OFFSET, CORPUS_RATIO, CORPUS_BAND, src
    return (entry["level_median"], entry["ratio_median"],
            {"level_offset": tuple(entry["level_band"]),
             "modelling_ratio": tuple(entry["ratio_band"])}, src)


def main(argv=None):
    ap = argparse.ArgumentParser(description="key generated faces to the corpus")
    ap.add_argument("src", help="image file or directory of PNGs")
    ap.add_argument("out", help="output directory")
    ap.add_argument("--weights", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "models", "yolo", "face_yolov8m.pt"))
    ap.add_argument("--feather", type=int, default=15)
    ap.add_argument("--champion", default=None,
                    help="use this champion's measured band when one exists")
    args = ap.parse_args(argv)

    from PIL import Image  # lazy heavy dep

    offset, ratio, band, src_label = targets_for(args.champion)
    print(f"targets: level {offset:+.1f}, ratio {ratio:.2f}  [{src_label}]")
    paths = ([args.src] if os.path.isfile(args.src)
             else sorted(glob.glob(os.path.join(args.src, "*.png"))))
    os.makedirs(args.out, exist_ok=True)
    report = []
    for p in paths:
        dst = os.path.join(args.out, os.path.basename(p))
        box = _detect_face(p, args.weights)
        if box is None:
            # PASS IT THROUGH, do not drop it. A batch tool whose output folder
            # is missing frames is worse than one that declines to correct them
            # - the loss is silent and the frame is gone from the set.
            shutil.copyfile(p, dst)
            report.append({"file": os.path.basename(p), "skipped": "no_face"})
            print(f"{os.path.basename(p)}: no face - copied through unchanged")
            continue
        with Image.open(p) as im:
            rgb = np.asarray(im.convert("RGB"), dtype=np.float64)
        out, before, after = correct_frame(rgb, box, args.feather,
                                           offset=offset, ratio=ratio, band=band)
        if before is None or after is None:
            shutil.copyfile(p, dst)
            report.append({"file": os.path.basename(p), "skipped": "insufficient_skin"})
            print(f"{os.path.basename(p)}: too little skin - copied through unchanged")
            continue
        Image.fromarray(out).save(dst)
        row = {"file": os.path.basename(p),
               "targets": src_label,
               "before": {"level_offset": round(before[0], 1),
                          "modelling_ratio": round(before[1], 3),
                          "in_band": in_band(*before, band=band)},
               "after": {"level_offset": round(after[0], 1),
                         "modelling_ratio": round(after[1], 3),
                         "in_band": in_band(*after, band=band),
                         "crush": round(harm(rgb, out)[0], 5),
                         "blowout": round(harm(rgb, out)[1], 5)}}
        report.append(row)
        print(f"{row['file']}: level {row['before']['level_offset']:+.1f} -> "
              f"{row['after']['level_offset']:+.1f} | ratio "
              f"{row['before']['modelling_ratio']:.2f} -> "
              f"{row['after']['modelling_ratio']:.2f} | in_band "
              f"{row['before']['in_band']} -> {row['after']['in_band']}")
    if report:
        scored = [r for r in report if "after" in r]
        n_in = sum(1 for r in scored if r["after"]["in_band"])
        skipped = len(report) - len(scored)
        print(f"in corpus band: {n_in}/{len(scored)}"
              + (f" ({skipped} passed through unscored)" if skipped else ""))
        tmp = os.path.join(args.out, "facekey_report.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
        os.replace(tmp, os.path.join(args.out, "facekey_report.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
