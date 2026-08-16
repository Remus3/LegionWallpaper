"""lw-gen MEDIUM yardstick - how far an arm's images sit from the real corpus.

The gate in `lw_gen_qa.py` scores SUBJECT (is this the right champion). It is
measurably blind to MEDIUM: animagine plus-face 0.5 posts a near-best
`subject_cos` while its frames sit 0.11-0.19 below the real corpus's own
self-similarity (LEDGER 110). This module is that second, gate-independent
measure, and nothing here is a gate - it reports numbers.

The measure, recovered and re-derived 2026-08-16:

    ceiling  = mean pairwise cosine of CLIP image embeddings WITHIN the real
               reference set (21 official Ahri splashes -> 0.8373)
    arm mean = mean cosine of every arm image against every real image
    delta    = arm mean - ceiling

The ceiling is what "as much like the real corpus as the real corpus is like
itself" costs. An arm BELOW it is measurably outside the corpus distribution;
at or above it is inside. Same CLIP as the subject gate
(`clip_model`/`clip_pretrained` in `tools/lw_gen_config.json`, ViT-L-14-quickgelu
/openai) so the two numbers are comparable.

CLI (needs .venv-metrics for the encode; the math above is dependency-light):

    .venv-metrics\\Scripts\\python.exe tools/lw_gen_medium.py \\
        --real tools/models/lora_datasets/ahri \\
        --arm images/_gen_scratch/<batch>:animagine [--arm <dir>:<label> ...]

Heavy deps (torch / open_clip / PIL) are imported lazily inside `encode_dir`,
so importing this module in CI stays torch-free.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

# Borrow the gpu_lock helper rather than minting a fifth copy - same reasoning
# as lw_gen_qa.py: this module runs in .venv-metrics alongside lw_g1_gate, which
# is stdlib+numpy at import time (torch/pyiqa lazy inside it), so the import
# keeps this module's own torch-free CI contract intact.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lw_g1_gate import GpuBusy, gpu_lock  # noqa: E402,F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_EXTS = ("*.png", "*.jpg", "*.jpeg", "*.webp")


def _unit_rows(embs):
    """Return `embs` as a float64 array with every row L2-normalised.

    Callers hand in whatever their encoder produced; normalising here is what
    makes the dot products below cosines rather than inner products.
    """
    arr = np.asarray(embs, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"expected a 2-D (n, dim) array, got shape {arr.shape}")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def mean_pairwise_cos(embs):
    """Mean cosine over every DISTINCT pair - the self-similarity ceiling.

    The diagonal is excluded on purpose: a set is trivially 1.0 similar to
    itself, and including it drags the ceiling toward 1 by 1/n.
    """
    arr = _unit_rows(embs)
    n = arr.shape[0]
    if n < 2:
        raise ValueError("a self-similarity ceiling needs at least 2 members")
    mat = arr @ arr.T
    iu = np.triu_indices(n, k=1)
    return float(mat[iu].mean())


def mean_cross_cos(arm_embs, real_embs):
    """Mean cosine of every arm image against every real image."""
    a = _unit_rows(arm_embs)
    b = _unit_rows(real_embs)
    if a.shape[0] == 0 or b.shape[0] == 0:
        raise ValueError("both sets must be non-empty")
    return float((a @ b.T).mean())


def per_image_cross_cos(arm_embs, real_embs):
    """One mean-vs-real cosine per arm image, in input order."""
    a = _unit_rows(arm_embs)
    b = _unit_rows(real_embs)
    return [float(v) for v in (a @ b.T).mean(axis=1)]


def medium_report(arm_embs, real_embs, label="arm", files=None, ceiling=None):
    """The full record for one arm: ceiling, arm mean, delta, per-image rows."""
    ceil = mean_pairwise_cos(real_embs) if ceiling is None else float(ceiling)
    rows = per_image_cross_cos(arm_embs, real_embs)
    names = list(files) if files is not None else [str(i) for i in range(len(rows))]
    arm_mean = mean_cross_cos(arm_embs, real_embs)
    delta = arm_mean - ceil
    return {
        "label": label,
        "n_arm": int(np.asarray(arm_embs).shape[0]),
        "n_real": int(np.asarray(real_embs).shape[0]),
        "ceiling": ceil,
        "arm_mean_cos": arm_mean,
        "delta": delta,
        "verdict": "at_or_above" if delta >= 0 else "below",
        "per_image": [{"file": f, "mean_cos": c} for f, c in zip(names, rows, strict=True)],
    }


# --------------------------------------------------------------------------
# Encoding (heavy deps, lazy).
# --------------------------------------------------------------------------
def list_images(directory):
    """Sorted image paths in `directory` - stable order so runs are comparable."""
    out = []
    for pat in IMAGE_EXTS:
        out.extend(glob.glob(os.path.join(directory, pat)))
    return sorted(out)


def load_clip_config(root=ROOT):
    with open(os.path.join(root, "tools", "lw_gen_config.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    return cfg.get("clip_model", "ViT-L-14"), cfg.get("clip_pretrained", "openai")


def encode_paths(paths, root=ROOT):
    """CLIP image embeddings for `paths` (lazy torch/open_clip/PIL import)."""
    import open_clip  # lazy heavy dep
    import torch  # lazy heavy dep
    from PIL import Image  # lazy heavy dep

    name, pretrained = load_clip_config(root)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    # ONE hold for the load plus every encode - same shape as
    # ClipScorer.load + score_batch. Pure leaf: no subprocess is spawned inside.
    with gpu_lock(device):
        model, _, preprocess = open_clip.create_model_and_transforms(
            name, pretrained=pretrained)
        model = model.to(device).eval()
        embs = []
        for p in paths:
            with Image.open(p) as im:
                tensor = preprocess(im.convert("RGB")).unsqueeze(0).to(device)
            with torch.no_grad():
                emb = model.encode_image(tensor)
                emb = emb / emb.norm(dim=-1, keepdim=True)
            embs.append(emb.squeeze(0).float().cpu().numpy())
    return np.asarray(embs, dtype=np.float64)


def _parse_arm(spec):
    """`<dir>` or `<dir>:<label>` - a bare Windows drive colon is not a label."""
    head, sep, tail = spec.rpartition(":")
    if sep and len(tail) != 1 and tail:
        return head, tail
    return spec, os.path.basename(os.path.normpath(spec))


def main(argv=None):
    ap = argparse.ArgumentParser(description="medium yardstick: arm vs real corpus")
    ap.add_argument("--real", required=True, help="directory of real reference images")
    ap.add_argument("--arm", action="append", default=[],
                    help="<dir> or <dir>:<label> of generated images (repeatable)")
    ap.add_argument("--out", default=None, help="write the JSON report here too")
    args = ap.parse_args(argv)

    real_paths = list_images(args.real)
    if len(real_paths) < 2:
        print(f"need >= 2 real images in {args.real}", file=sys.stderr)
        return 2
    real = encode_paths(real_paths)
    ceiling = mean_pairwise_cos(real)

    report = {"real_dir": args.real, "n_real": len(real_paths), "ceiling": ceiling,
              "arms": []}
    for spec in args.arm:
        directory, label = _parse_arm(spec)
        paths = list_images(directory)
        if not paths:
            print(f"no images in {directory} - arm skipped", file=sys.stderr)
            continue
        embs = encode_paths(paths)
        report["arms"].append(medium_report(
            embs, real, label=label, files=[os.path.basename(p) for p in paths],
            ceiling=ceiling))

    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        tmp = args.out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
