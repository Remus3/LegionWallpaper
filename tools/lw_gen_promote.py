"""lw_gen_promote.py - Phase 3 of the lw-gen sidecar (stdlib + PIL, NO torch).

Reads a post-QA gen_manifest.json in a batch dir, ranks the PASS candidates,
and drops the top_k of them as loose stage-0 inputs in images/0.Originals so
the operator can run the normal pipeline intake.

Hard boundaries encoded here (see the SHARED INTEROP CONTRACT):

  * SIZE ASSERT before any drop: a promoted image MUST be strictly smaller
    than the 2560x1440 first-pass target on BOTH axes. A >=2560 or >=1440
    image is SKIPPED (recorded in promote.review with reason
    "oversize_would_trigger_downscale_path"). This guards a future config
    edit from silently flipping first_pass into the downscale-only path where
    lap_ratio is not a valid gate metric (ADR-006).

  * ATOMIC placement: prefer lw_pipeline Ops.safe_copy (copy + fsync +
    SHA256 verify). If that is unavailable, fall back to a copy-to-.part plus
    a retry-wrapped os.replace (survives transient WinError 5 when the live
    pipeline is concurrently reading 0.Originals). Never a bare no-retry
    os.replace.

  * Promote is a PRODUCER of stage-0 inputs and STOPS at the loose
    0.Originals drop. It does NOT shell intake or annotate inline, because:
      - cmd_intake enforces MIN_AGE_SECONDS, so a freshly written file is
        skipped as "modified too recently (still downloading?)";
      - the post-intake slug is unpredictable (unique_slug suffixing);
      - annotate needs the EXACT final slug + a manifest and only looks up
        scratch/done/backup folders.
    The operator (or the Phase-4 driver) recovers the real slug from intake
    stdout and never reconstructs it.

Only stdlib + PIL here; torch/open_clip/cv2 are never imported. lw_pipeline is
stdlib-only at module top, so importing slugify / Ops from it is CI-safe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

# Path shim so `from tools import lw_pipeline` works both as a script
# (python tools/lw_gen_promote.py) and under pytest (from tools import ...).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_pipeline  # noqa: E402

MANIFEST_NAME = "gen_manifest.json"
ORIGINALS_SUBPATH = ("images", "0.Originals")
TARGET_W = 2560
TARGET_H = 1440
DEFAULT_TOP_K = 3

# Documented operator interpreter (used only in the printed next-step commands).
PY = r"C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe"

REASON_OVERSIZE = "oversize_would_trigger_downscale_path"
REASON_ZERO_PASS = "zero_pass_best_near_miss"


# --------------------------------------------------------------- small helpers

def _repo_root():
    return Path(__file__).resolve().parents[1]


def _default_originals():
    return _repo_root().joinpath(*ORIGINALS_SUBPATH)


def _read_json(path):
    with open(path, encoding="utf-8") as fo:
        return json.load(fo)


def _write_json_atomic(path, data):
    """tmp.write + os.replace, per the project atomic-write rule."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fo:
        for chunk in iter(lambda: fo.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _short_hash(path, seed=None):
    """First 4 hex of sha1(file bytes), falling back to the seed."""
    try:
        with open(path, "rb") as fo:
            return hashlib.sha1(fo.read()).hexdigest()[:4]
    except OSError:
        basis = str(seed if seed is not None else path)
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:4]


def _image_size(path):
    """(width, height) via PIL; PIL imported lazily to keep imports light."""
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def _subject_cos(cand):
    val = cand.get("subject_cos")
    return val if isinstance(val, (int, float)) else float("-inf")


# --------------------------------------------------------------- placement core

def _retry_replace(tmp, dest, tries=3, backoff=0.05):
    """os.replace with a short backoff retry (transient WinError 5 guard)."""
    last = None
    for i in range(tries):
        try:
            os.replace(tmp, dest)
            return
        except OSError as exc:
            last = exc
            time.sleep(backoff * (i + 1))
    raise last


def _get_ops():
    """Return an Ops(dry=False) recorder if lw_pipeline exposes one, else None."""
    ops_cls = getattr(lw_pipeline, "Ops", None)
    if ops_cls is None:
        return None
    try:
        return ops_cls(dry=False)
    except (TypeError, ValueError):
        return None


def atomic_place(src, dest, ops=None):
    """Atomically copy src -> dest.

    Prefers Ops.safe_copy (copy + fsync + SHA256 verify). Falls back to a
    copy-to-.part then retry-wrapped os.replace. Returns the dest sha256.
    """
    src = Path(src)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if ops is not None and hasattr(ops, "safe_copy"):
        ops.safe_copy(src, dest.parent, dest.name)
        return _sha256(dest)
    tmp = dest.with_name(dest.name + ".part")
    shutil.copyfile(src, tmp)
    _retry_replace(tmp, dest)
    return _sha256(dest)


def _unique_dest(originals_dir, slug):
    """Local same-name collision guard in 0.Originals: <slug>, <slug>-2, ..."""
    candidate = slug
    i = 2
    while (originals_dir / f"{candidate}.png").exists():
        candidate = f"{slug}-{i}"
        i += 1
    return candidate, originals_dir / f"{candidate}.png"


# --------------------------------------------------------------- promote driver

def promote(batch_dir, originals_dir=None, ops=None):
    """Promote the ranked PASS candidates from one batch dir.

    Returns the updated manifest dict (also written back to disk).
    """
    batch_dir = Path(batch_dir)
    originals_dir = Path(originals_dir) if originals_dir else _default_originals()
    if ops is None:
        ops = _get_ops()

    manifest = _read_json(batch_dir / MANIFEST_NAME)
    subject = manifest.get("subject", "gen")
    style = manifest.get("style", "splash")
    batch_id = manifest.get("batch_id", "unknown")
    candidates = manifest.get("candidates", []) or []

    top_k = manifest.get("top_k")
    if not isinstance(top_k, int) or top_k < 1:
        top_k = DEFAULT_TOP_K

    passes = [c for c in candidates if c.get("verdict") == "PASS"]
    passes.sort(key=_subject_cos, reverse=True)

    promoted = []
    review = []

    if not passes:
        # Zero PASS: copy the best-scoring candidate into review/ for eyeballs.
        if candidates:
            best = max(candidates, key=_subject_cos)
            best_file = best.get("file")
            if best_file and (batch_dir / best_file).exists():
                review_dir = batch_dir / "review"
                review_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(batch_dir / best_file, review_dir / best_file)
                review.append({"file": best_file, "reason": REASON_ZERO_PASS})
    else:
        for cand in passes[:top_k]:
            fname = cand.get("file")
            if not fname:
                continue
            src = batch_dir / fname
            if not src.exists():
                review.append({"file": fname, "reason": "missing_candidate_file"})
                continue

            # SIZE ASSERT: must be strictly under the 2560x1440 target on BOTH
            # axes, else it would trip the downscale-only path where lap_ratio
            # is not a valid gate metric.
            width, height = _image_size(src)
            if width >= TARGET_W or height >= TARGET_H:
                review.append({"file": fname, "reason": REASON_OVERSIZE})
                continue

            short = _short_hash(src, cand.get("seed"))
            base_slug = lw_pipeline.slugify(f"{subject}-{style}-{short}")
            slug, dest = _unique_dest(originals_dir, base_slug)

            sha = atomic_place(src, dest, ops=ops)
            promoted.append({
                "file": fname,
                "slug": slug,
                "dest": str(dest),
                "sha256": sha,
            })

            # Per-promoted metrics slice for a later `annotate --metrics @`.
            slice_obj = {
                "slug": slug,
                "batch_id": batch_id,
                "source_url": f"gen://lw-gen/{batch_id}",
                "tool": "lw-gen",
                "subject": subject,
                "style": style,
                "seed": cand.get("seed"),
                "round": cand.get("round"),
                "model": manifest.get("model"),
                "clip_model": manifest.get("clip_model"),
                "gen_metrics": {
                    "subject_cos": cand.get("subject_cos"),
                    "off_cos": cand.get("off_cos"),
                    "margin": cand.get("margin"),
                    "aesthetic": cand.get("aesthetic"),
                    "lap_var": cand.get("lap_var"),
                },
            }
            _write_json_atomic(batch_dir / f"{slug}.slice.json", slice_obj)

    manifest["promote"] = {
        "top_k": top_k,
        "promoted": promoted,
        "review": review,
    }
    _write_json_atomic(batch_dir / MANIFEST_NAME, manifest)
    return manifest


# --------------------------------------------------------------- CLI / output

def _print_report(manifest, batch_dir):
    batch_id = manifest.get("batch_id", "unknown")
    promo = manifest.get("promote", {})
    promoted = promo.get("promoted", [])
    review = promo.get("review", [])

    print(f"lw-gen promote: batch {batch_id}")
    print(f"scratch dir: {batch_dir}")
    if promoted:
        print(f"promoted {len(promoted)} candidate(s) to 0.Originals:")
        for p in promoted:
            print(f"  {p['file']} -> {p['dest']}")
    else:
        print("promoted 0 candidates (no PASS survived promotion).")
    if review:
        print("review / near-miss (never auto-deleted):")
        for r in review:
            print(f"  {r['file']}: {r['reason']}")

    print("")
    print("next operator commands:")
    print(f"  1) {PY} tools/lw_pipeline.py intake --all")
    print("  2) annotate TEMPLATE (recover the REAL slug from intake stdout;")
    print("     never reconstruct it - unique_slug may have suffixed it):")
    for p in promoted:
        print(
            f"     {PY} tools/lw_pipeline.py annotate <SLUG> "
            f"--source-url gen://lw-gen/{batch_id} --tool lw-gen "
            f"--metrics @{p['slug']}.slice.json"
        )
    if not promoted:
        print(
            f"     {PY} tools/lw_pipeline.py annotate <SLUG> "
            f"--source-url gen://lw-gen/{batch_id} --tool lw-gen "
            "--metrics @<slug>.slice.json"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Promote PASS candidates from a lw-gen batch to 0.Originals.")
    parser.add_argument("batch_dir", help="path to the gen batch dir")
    parser.add_argument(
        "--originals", default=None,
        help="override the 0.Originals destination (default: repo images/0.Originals)")
    args = parser.parse_args(argv)

    batch_dir = Path(args.batch_dir)
    manifest_path = batch_dir / MANIFEST_NAME
    if not manifest_path.exists():
        print(f"lw-gen promote: no {MANIFEST_NAME} in {batch_dir} - run generation first")
        return 2

    manifest = promote(batch_dir, originals_dir=args.originals)
    _print_report(manifest, batch_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
