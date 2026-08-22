"""Template-detected footprint + scheduled fill - the two proven halves joined.

The 2026-08-22 investigation ended with a clean split:

  FILL      solved. Replaying the operator's own masks through simple-lama
            produced frames they accepted on both ground-truth slugs, and the
            generated SCHEDULE (residue -> contiguous run -> context pad ->
            tight crop -> commit) produced a clean 105-cleanup on its own.
  DETECTION unsolved by anything contrast-based. An absolute residue threshold
            fires on genuine brush detail (it damaged 107-cleanup); a threshold
            calibrated against a control band of the same art misses the mark
            entirely, because a semi-transparent credit line is NOT busier than
            the art around it - it is low-amplitude coherent structure.

The one detector in this repo with a proven record is the centre-overlay
TEMPLATE: built by median-stacking the high-pass of frames that carry the mark,
calibrated at zero false positives over the live corpus. It knows where the mark
is because it knows what the mark LOOKS like, which is the property contrast
measures lack.

So this joins them: the template's own pre-pass supplies the footprint, and the
schedule does the filling instead of the single large LaMa call that was
rejected 45 times.

  python tools/lw_clean_overlay_schedule.py <slug> --steps 14
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_iopaint as IO  # noqa: E402
import lw_clean_pass as C  # noqa: E402
import lw_clean_tiled as T  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def resolve_image(slug, image=None):
    """The frame to clean: an explicit path, else the slug's working image."""
    if image:
        return image
    return C.select_working_image(os.path.join(C.CLEAN_SCRATCH, slug), slug)


def build_footprint(bgr, tpl, matte):
    """(pre-pass frame, footprint mask, info) from the overlay template.

    The pre-pass is kept: it inverts the matting equation where it can, which is
    faithful by construction, and the footprint is what it could NOT invert -
    exactly the region a filler should be asked about.
    """
    pre_bgr, mask_full, roi_box, info = IO.overlay_prepass(bgr, matte, tpl)
    foot = np.asarray(mask_full) > 0
    return pre_bgr, foot, roi_box, info


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_overlay_schedule")
    ap.add_argument("slug")
    ap.add_argument("--image")
    ap.add_argument("--out", help="candidate PNG (default: runtime dir)")
    ap.add_argument("--steps", type=int, default=14)
    ap.add_argument("--context-ratio", type=float, default=T.CONTEXT_RATIO)
    ap.add_argument("--dry-run", action="store_true",
                    help="report the footprint the template finds; no GPU")
    args = ap.parse_args(argv)

    tpl, matte = IO.load_overlay_pair()
    if tpl is None or matte is None:
        print(json.dumps({"slug": args.slug, "status": "error",
                          "reason": "no overlay template/matte on this box - "
                                    "the template is gitignored and rebuilt "
                                    "from the verified slugs"}))
        return 3
    path = resolve_image(args.slug, args.image)
    if not path:
        print(json.dumps({"slug": args.slug, "status": "error",
                          "reason": "no clean input image"}))
        return 3

    with Image.open(path) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    pre_bgr, foot, roi_box, info = build_footprint(bgr, tpl, matte)
    pre_rgb = np.ascontiguousarray(np.asarray(pre_bgr)[:, :, ::-1])
    rec = {"slug": args.slug, "image": path, "roi": list(roi_box) if roi_box else None,
           "footprint_px": int(foot.sum()), "overlay": info}

    if args.dry_run or not foot.any():
        rec["status"] = "dry-run" if foot.any() else "nothing-to-mask"
        print(json.dumps(rec, indent=2))
        return 0

    out, plan = T.run_schedule(pre_rgb, foot, T._lama_inpainter(),
                               steps=args.steps,
                               context_ratio=args.context_ratio)
    target = args.out or os.path.join(C.RUNTIME_CLEAN, args.slug,
                                      f"{args.slug}_tiled_cand.png")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".part"
    Image.fromarray(out).save(tmp, format="PNG")
    os.replace(tmp, target)
    rec["status"] = "cleaned"
    rec["candidate"] = target
    rec["schedule"] = {k: v for k, v in plan.items()
                       if k not in ("mask_px_per_step", "residue_px_per_step")}
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
