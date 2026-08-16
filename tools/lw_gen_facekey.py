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
import sys

import numpy as np

# Measured on the 21 real Ahri splashes (tools/models/lora_datasets/ahri).
CORPUS_OFFSET = 24.3      # face-skin mean minus body-skin mean, in levels
CORPUS_RATIO = 0.83       # face-skin std over body-skin std
CORPUS_BAND = {           # p10..p90 of the same corpus - the validation band
    "level_offset": (-3.0, 45.0),
    "modelling_ratio": (0.64, 1.26),
}
GAIN_CLIP = (0.8, 1.8)
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


def _box_blur(a, k):
    k = max(3, int(k) | 1)
    out = np.asarray(a, dtype=np.float64)
    for axis in (0, 1):
        pad = np.pad(out, k // 2, mode="constant")
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
    solid = (_box_blur(m, feather_px) > 0.15).astype(np.float64)
    solid = np.maximum(solid, m)
    # Then a plain blur gives interior 1.0 with the taper on the boundary; the
    # 0.9 divisor makes the saturation robust to a ragged edge.
    return np.clip(_box_blur(solid, feather_px) / 0.9, 0.0, 1.0)


def luminance(rgb):
    a = np.asarray(rgb, dtype=np.float64)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def apply_face_key(rgb, mask, weight, gain, target_mean):
    """Return `rgb` with the masked region keyed to (gain, target_mean).

    Outside the weight map the output is byte-identical to the input.
    """
    a = np.asarray(rgb, dtype=np.float64)
    lum = luminance(a)
    sel = np.asarray(mask, dtype=bool)
    if not sel.any():
        return a.astype(np.uint8)
    face_mean = float(lum[sel].mean())
    target = (lum - face_mean) * float(gain) + float(target_mean)
    scale = np.divide(target, np.maximum(lum, 1e-6))
    w = np.asarray(weight, dtype=np.float64)
    scale = 1.0 + (scale - 1.0) * w
    out = np.clip(a * scale[..., None], 0, 255)
    return out.astype(np.uint8)


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


def correct_frame(rgb, face_box, feather_px=15):
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
    best_score = _distance(before)
    before_in_band = in_band(*before)
    cur = a
    for _ in range(PASSES):
        lum_i = luminance(cur)
        skin_i = skin_mask(cur, seed)
        fs_i, bs_i = skin_i & box, skin_i & (~box)
        if fs_i.sum() < 200 or bs_i.sum() < 200:
            break
        gain, target_mean = key_targets(lum_i[fs_i].mean(), lum_i[fs_i].std(),
                                        lum_i[bs_i].mean(), lum_i[bs_i].std())
        w = feathered_weight(fs_i, feather_px)
        # Damped step search: a full-strength correction fixes the modelling
        # ratio but can carry the level past the target, and the guard then
        # (correctly) throws the whole pass away. Trying fractional steps means
        # such a frame gets a smaller correction rather than none.
        improved = False
        for step in STEPS:
            cand = apply_face_key(cur, fs_i, w * step, gain, target_mean).astype(np.float64)
            m_cand = measure(cand, face_box)
            score = _distance(m_cand)
            # Never trade a frame that is already inside the corpus band for a
            # nominally shorter distance outside it. Measured over 57 frames,
            # distance-only acceptance pushed 3 in-band frames OUT.
            if before_in_band and not (m_cand and in_band(*m_cand)):
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="key generated faces to the corpus")
    ap.add_argument("src", help="image file or directory of PNGs")
    ap.add_argument("out", help="output directory")
    ap.add_argument("--weights", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "models", "yolo", "face_yolov8m.pt"))
    ap.add_argument("--feather", type=int, default=15)
    args = ap.parse_args(argv)

    from PIL import Image  # lazy heavy dep

    paths = ([args.src] if os.path.isfile(args.src)
             else sorted(glob.glob(os.path.join(args.src, "*.png"))))
    os.makedirs(args.out, exist_ok=True)
    report = []
    for p in paths:
        box = _detect_face(p, args.weights)
        if box is None:
            print(f"{os.path.basename(p)}: no face - skipped", file=sys.stderr)
            continue
        with Image.open(p) as im:
            rgb = np.asarray(im.convert("RGB"), dtype=np.float64)
        out, before, after = correct_frame(rgb, box, args.feather)
        dst = os.path.join(args.out, os.path.basename(p))
        Image.fromarray(out).save(dst)
        row = {"file": os.path.basename(p),
               "before": {"level_offset": round(before[0], 1),
                          "modelling_ratio": round(before[1], 3),
                          "in_band": in_band(*before)},
               "after": {"level_offset": round(after[0], 1),
                         "modelling_ratio": round(after[1], 3),
                         "in_band": in_band(*after)}}
        report.append(row)
        print(f"{row['file']}: level {row['before']['level_offset']:+.1f} -> "
              f"{row['after']['level_offset']:+.1f} | ratio "
              f"{row['before']['modelling_ratio']:.2f} -> "
              f"{row['after']['modelling_ratio']:.2f} | in_band "
              f"{row['before']['in_band']} -> {row['after']['in_band']}")
    if report:
        n_in = sum(1 for r in report if r["after"]["in_band"])
        print(f"in corpus band: {n_in}/{len(report)}")
        tmp = os.path.join(args.out, "facekey_report.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
        os.replace(tmp, os.path.join(args.out, "facekey_report.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
