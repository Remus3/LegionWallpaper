"""Mask-excluded G1 FR for a cleaning candidate.

G1's FR metrics compare a candidate against its `_cleaninitial`, which still
carries the mark. A successful cleaning legitimately differs inside the detect
mask, so that region is neutralized (reference pixels composited into the
candidate) before FR runs, and only the region the candidate was supposed to
PRESERVE is scored.

THE TRAP THIS MODULE GUARDS (measured on slug 259f, 2026-08-29): a mask DERIVED
from the candidate's own diff is a tautology. Neutralizing wherever a candidate
differs makes it byte-identical to the reference, and FR then returns ms_ssim
1.0000 / lpips 0.0001 for ANY candidate, including one that was globally
filtered. The mask must be an INDEPENDENT artifact - the detect output already
on disk. This module therefore accepts a mask PATH only; it never computes one
from the pair, and it refuses a mask large enough to make the score vacuous.

Honest scope, so nobody expects more of it than it gives: over the 41 recorded
cleaning masks the median covers 1.257 percent of the frame and the largest
6.363 percent, so the exclusion moves ms_ssim by roughly +0.003 (259f) up to
about +0.02 at the corpus worst case. It is a correctness fix, not a large one.
The dominant failure term on a hand-edited submission is a global filter, which
halo_pct catches whether or not a mask is applied.

lap_ratio is RECORDED but never gated here. Cleaning performs no upscale, so by
the ADR-006 argument the softness FLOOR reads as arbitrary pass/fail by source
content; the over-sharpen direction is already owned by halo_pct.

CI constraint: numpy + Pillow only at import time. pyiqa/torch live behind
fr_fn, which defaults to lw_g1_gate.fr_metrics (itself lazy) and is injected as
a stub by the tests so no model is ever loaded.

Exit codes: 0 ok, 2 precondition/argument error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# A mask past this fraction of the frame makes the surviving region too small to
# be a meaningful score. Calibrated against BOTH ends: the largest real mask on
# record covers 6.363 percent, and the derived box that produced the 1.0000
# tautology on 259f covered 14.787 percent. 10 percent sits between them - it
# clears every real detection with ~1.6x headroom while refusing that box.
# An area ceiling alone is NOT sufficient, which is what `scored` is for.
MASK_MAX_PCT = 10.0

GATE_NAME = "G1-clean"


class MaskError(ValueError):
    """The pair or its mask cannot be scored as given."""


def load_gate_mask(mask_path, frame_shape):
    """Read an INDEPENDENT detect mask from disk as a boolean array.

    Refuses a mask that does not match the frame, is empty (the detect step
    found nothing, and scoring against it would silently degrade to whole-frame
    while claiming a mask was applied), or exceeds MASK_MAX_PCT.
    """
    from PIL import Image

    path = Path(mask_path)
    if not path.is_file():
        raise MaskError(f"mask not found: {path}")
    with Image.open(path) as im:
        mask = np.asarray(im.convert("L")) > 127
    if mask.shape != tuple(frame_shape[:2]):
        raise MaskError(
            f"mask {mask.shape} does not match frame {tuple(frame_shape[:2])}")
    covered = float(mask.mean()) * 100.0
    if covered <= 0.0:
        raise MaskError(f"mask {path.name} is empty; nothing was detected")
    if covered > MASK_MAX_PCT:
        raise MaskError(
            f"mask {path.name} covers {covered:.3f}% of the frame, over the "
            f"{MASK_MAX_PCT:g}% ceiling; a mask that large makes the score "
            "vacuous (a mask derived from the candidate's own diff scores "
            "1.0000 for any candidate)")
    return mask


def neutralize(candidate, reference, mask):
    """Composite reference pixels into the candidate inside the mask.

    Returns a new array; inputs are not mutated. A None mask means whole-frame
    scoring and the candidate is returned unchanged (as a copy).
    """
    out = np.array(candidate, copy=True)
    if mask is None:
        return out
    out[mask] = reference[mask]
    return out


def clean_fr_audit(fr, lap_ratio, halo_pct, band_delta, mask_pct):
    """Assemble the annotate-shaped audit dict and its verdict.

    Gated: msssim, lpips, halo_pct, band_delta. Recorded but NOT gated:
    lap_ratio (see the module docstring), mask_pct.
    """
    from lw_g1_gate import DEFAULT_G1_THRESHOLDS, verdict

    gated = {}
    for src_key, key in (("ms_ssim", "msssim"), ("msssim", "msssim"),
                         ("lpips", "lpips")):
        val = (fr or {}).get(src_key)
        if isinstance(val, (int, float)):
            gated[key] = float(val)
    for key, val in (("halo_pct", halo_pct), ("band_delta", band_delta)):
        if isinstance(val, (int, float)):
            gated[key] = float(val)
    v = verdict(gated, DEFAULT_G1_THRESHOLDS)
    metrics = dict(gated)
    metrics["lap_ratio"] = (float(lap_ratio)
                            if isinstance(lap_ratio, (int, float)) else None)
    metrics["mask_pct"] = (float(mask_pct)
                           if isinstance(mask_pct, (int, float)) else None)
    for key in ("dists", "ssim"):
        val = (fr or {}).get(key)
        if isinstance(val, (int, float)):
            metrics[key] = float(val)
    return {
        "gate": GATE_NAME,
        "verdict": v.get("verdict"),
        "reasons": list(v.get("reasons") or []),
        "metrics": metrics,
    }


def compute_clean_fr(reference_path, candidate_path, mask_path=None, fr_fn=None):
    """Score a cleaning candidate against its reference, mask region excluded.

    fr_fn(candidate_path, reference_path, source_path, names=...) -> dict is
    injectable so the tests can stub it; it defaults to lw_g1_gate.fr_metrics.
    """
    from PIL import Image

    from lw_g1_gate import banding_delta, laplacian_ratio, overshoot_halo

    with Image.open(reference_path) as im:
        reference = np.asarray(im.convert("RGB"))
    with Image.open(candidate_path) as im:
        candidate = np.asarray(im.convert("RGB"))
    if reference.shape != candidate.shape:
        raise MaskError(
            f"candidate {candidate.shape} does not match reference "
            f"{reference.shape}; nothing to score")

    mask = None
    mask_pct = None
    if mask_path is not None:
        mask = load_gate_mask(mask_path, reference.shape)
        mask_pct = float(mask.mean()) * 100.0

    scored = neutralize(candidate, reference, mask)

    # The area ceiling cannot catch every vacuous mask, so measure the thing
    # that actually matters: how much of what FR will score differs at all.
    # Tool output is byte-identical outside its mask by construction, so this
    # is legitimately 0 there - the audit must SAY so rather than report a
    # free 1.0 as if it had been earned.
    diff = np.abs(scored.astype(np.int16) - reference.astype(np.int16))
    outside_changed_px = int((diff.max(axis=2) > 0).sum())
    outside_max_delta = int(diff.max()) if diff.size else 0

    if fr_fn is None:
        from lw_g1_gate import fr_metrics as fr_fn  # noqa: N813

    tmp_dir = tempfile.mkdtemp(prefix="lw_clean_fr_")
    tmp_png = Path(tmp_dir) / "scored.png"
    try:
        Image.fromarray(scored).save(tmp_png)
        fr = fr_fn(str(tmp_png), str(reference_path), str(reference_path),
                   names=("ssim", "ms_ssim", "lpips", "dists"))
        lap = laplacian_ratio(reference, scored)
        halo = overshoot_halo(reference, scored)["halo_pct"]
        band = banding_delta(reference, scored)
    finally:
        if tmp_png.exists():
            os.unlink(tmp_png)
        os.rmdir(tmp_dir)
    audit = clean_fr_audit(fr, lap, halo, band, mask_pct)
    audit["metrics"]["outside_changed_px"] = outside_changed_px
    audit["metrics"]["outside_max_delta"] = outside_max_delta
    audit["metrics"]["scored"] = outside_changed_px > 0
    return audit


# ------------------------------------------------------------------------ CLI
def resolve_paths(root, slug, runtime):
    """(reference, candidate, mask_or_None) for a slug in 3.Cleaning Scratch."""
    folder = Path(root) / "3.Cleaning Scratch" / slug
    reference = folder / f"{slug}_cleaninitial.png"
    if not reference.is_file():
        raise MaskError(f"no {reference.name} in {folder}")
    workings = sorted(folder.glob(f"{slug}_cleanworking_*.png"))
    candidate = workings[-1] if workings else None
    if candidate is None:
        raise MaskError(f"no {slug}_cleanworking_NN.png in {folder}")
    mask = Path(runtime) / slug / f"{slug}_mask.png"
    return reference, candidate, (mask if mask.is_file() else None)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Mask-excluded G1 FR for a cleaning candidate.")
    ap.add_argument("slug", nargs="?", help="slug in 3.Cleaning Scratch")
    ap.add_argument("--reference", help="explicit reference PNG")
    ap.add_argument("--candidate", help="explicit candidate PNG")
    ap.add_argument("--mask", help="explicit detect-mask PNG")
    ap.add_argument("--no-mask", action="store_true",
                    help="score the whole frame (records mask_pct null)")
    ap.add_argument("--root", default=r"C:\LegionWallpaper\images")
    ap.add_argument("--runtime", default=r"C:\LegionWallpaper\ops\runtime\clean")
    ap.add_argument("--out", help="write the audit JSON here (atomic)")
    args = ap.parse_args(argv)

    try:
        if args.reference and args.candidate:
            reference = Path(args.reference)
            candidate = Path(args.candidate)
            mask = Path(args.mask) if args.mask else None
        elif args.slug:
            reference, candidate, mask = resolve_paths(
                args.root, args.slug, args.runtime)
            if args.mask:
                mask = Path(args.mask)
        else:
            ap.error("give a slug, or --reference with --candidate")
        if args.no_mask:
            mask = None
        audit = compute_clean_fr(reference, candidate, mask_path=mask)
    except (MaskError, OSError, ValueError) as exc:
        # OSError covers a missing file and PIL's UnidentifiedImageError; a bad
        # path is an argument error (exit 2), never a traceback at the operator.
        print(f"lw_clean_fr: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(audit, indent=2)
    if args.out:
        out = Path(args.out)
        tmp = out.with_suffix(out.suffix + ".tmp")
        tmp.write_text(text, encoding="ascii")
        tmp.replace(out)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
