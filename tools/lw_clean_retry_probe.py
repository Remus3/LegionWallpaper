"""lw_clean_retry_probe.py - measure whether cleaning retries ever beat _01.

ROADMAP item `clean-retry-degrades`: "for every slug with 2+ workings, compare
each working against `_cleaninitial` on the existing metrics and count how often
`_02+` beats `_01` - if it never does, the loop is pure loss and the fix is a
one-line default."

Two independent censuses, both reported as measured counts:

  VERDICT census (stdlib only) - reads every cleaning manifest and replays its
  SAVE_WORKING / SUBMIT / REJECT / APPROVE_CLEAN transitions to record which
  working version each slug actually settled on. This is the operator's own
  adjudication, so it is the strongest available evidence.

  METRIC census (needs numpy + the lw_clean_pass metrics) - for each working,
  derives the edit region by diffing the working against `_cleaninitial`, then
  scores it on the SAME functions the cleaning gate already uses:
  masked_identity (outside-region identity), patch_change_ssim (how much the
  edit region moved) and seam_ring_ssim (seam quality on the edit boundary).
  No mask files are persisted per working, so the changed-pixel set IS the
  mask - which is exact, because inpaint_lama composites outside the mask.

Read-only: this probe never writes into a pipeline stage folder.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = r"C:\LegionWallpaper"
STAGES = (
    os.path.join(ROOT, "images", "3.Cleaning Scratch"),
    os.path.join(ROOT, "images", "4.Cleaning Done"),
)
_WORKING_RE = re.compile(r"_cleanworking_(\d+)\.", re.IGNORECASE)


def working_version(path_or_name):
    """Extract the NN of a _cleanworking_NN filename, else None."""
    if not path_or_name:
        return None
    m = _WORKING_RE.search(str(path_or_name))
    return int(m.group(1)) if m else None


def load_manifests(stages=STAGES):
    """Yield (slug, stage_dir, manifest_dict) for every cleaning-stage slug."""
    for stage in stages:
        if not os.path.isdir(stage):
            continue
        for slug in sorted(os.listdir(stage)):
            d = os.path.join(stage, slug)
            mpath = os.path.join(d, "manifest.json")
            if not os.path.isfile(mpath):
                continue
            try:
                with open(mpath, encoding="utf-8") as f:
                    yield slug, d, json.load(f)
            except (OSError, ValueError):
                continue


def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verdict_census(stages=STAGES):
    """Replay cleaning transitions per slug -> which working CONTENT won.

    Resolution is by sha256, not by filename, for two reasons measured on the
    real corpus: (a) an approved slug's workings are GC'd off disk, so version
    must be traced through the SAVE_WORKING hashes; (b) the winning working is
    routinely an `operator-select` COPY of an earlier working (or of
    `_cleaninitial`), so the approving VERSION number overstates which attempt
    actually produced the accepted pixels. `origin_version` is the LOWEST
    version carrying the approved sha - i.e. the attempt that really won.
    """
    rows = []
    for slug, d, man in load_manifests(stages):
        saved, rejected = {}, []
        sha_to_versions = {}
        for t in man.get("transitions") or []:
            op = t.get("op")
            v = working_version(t.get("dst")) or working_version(t.get("src"))
            sha = t.get("sha256_out")
            if op == "SAVE_WORKING" and v is not None:
                saved[v] = {"tool": t.get("tool"), "sha": sha}
                if sha:
                    sha_to_versions.setdefault(sha, set()).add(v)
            elif op == "REJECT" and v is not None:
                rejected.append(v)

        initial = os.path.join(d, f"{slug}_cleaninitial.png")
        initial_sha = _sha256_file(initial) if os.path.isfile(initial) else None

        approved_sha = None
        for t in man.get("transitions") or []:
            if t.get("op") == "APPROVE_CLEAN":
                approved_sha = t.get("sha256_out") or approved_sha
        origin_version = None
        approved_is_initial = False
        if approved_sha:
            versions = sha_to_versions.get(approved_sha)
            if versions:
                origin_version = min(versions)
            if initial_sha and approved_sha == initial_sha:
                approved_is_initial = True

        on_disk = sorted(
            working_version(n) for n in os.listdir(d) if _WORKING_RE.search(n)
        )
        rows.append({
            "slug": slug,
            "workings_on_disk": on_disk,
            "saved": {v: saved[v]["tool"] for v in sorted(saved)},
            "rejected": sorted(set(rejected)),
            "approved_sha12": (approved_sha or "")[:12] or None,
            "origin_version": origin_version,
            "approved_is_cleaninitial": approved_is_initial,
        })

    multi = [r for r in rows if len(r["saved"]) >= 2 or len(r["workings_on_disk"]) >= 2]
    decided = [r for r in multi if r["approved_sha12"]]
    retry_won = [r for r in decided
                 if r["origin_version"] and r["origin_version"] > 1
                 and not r["approved_is_cleaninitial"]]
    first_won = [r for r in decided
                 if r["origin_version"] == 1 and not r["approved_is_cleaninitial"]]
    initial_won = [r for r in decided if r["approved_is_cleaninitial"]]
    return {
        "rows": rows,
        "totals": {
            "slugs": len(rows),
            "slugs_with_2plus_workings": len(multi),
            "decided": len(decided),
            "settled_on_01": len(first_won),
            "settled_above_01": len(retry_won),
            "settled_on_cleaninitial": len(initial_won),
            "undecided": len(multi) - len(decided),
            "rejected_workings_total": sum(len(r["rejected"]) for r in rows),
        },
    }


# ---------------------------------------------------------------------------
# METRIC census - needs numpy + PIL; imports lazily so the verdict census runs
# on bare stdlib Python.
# ---------------------------------------------------------------------------
def _load_gray_rgb(path):
    import numpy as np
    from PIL import Image
    img = Image.open(path).convert("RGB")
    return np.asarray(img).astype("float64")


def metric_row(initial_path, working_path, clean_pass):
    """Score ONE working against _cleaninitial using the cleaning gate's own
    metric functions. The changed-pixel set is the mask (exact: the inpaint
    composites outside it), so `outside` here is provably untouched region.
    """
    import numpy as np
    a = _load_gray_rgb(initial_path)
    b = _load_gray_rgb(working_path)
    if a.shape != b.shape:
        return {"error": f"shape {a.shape} vs {b.shape}"}
    diff = np.abs(a - b).max(axis=2)
    mask = diff > 1.0                      # >1 level = a real edit, not codec noise
    edit_pct = float(mask.mean() * 100.0)
    if not mask.any():
        return {"edit_pct": 0.0, "no_op": True}
    outside_ssim, mad_outside = clean_pass.masked_identity(a, b, mask)
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    change_ssim = clean_pass.patch_change_ssim(a[y0:y1, x0:x1], b[y0:y1, x0:x1])
    ring = clean_pass._ring_mask(mask)
    seam_ssim = clean_pass.seam_ring_ssim(b, ring)
    return {
        "edit_pct": edit_pct,
        "no_op": False,
        "outside_ssim": float(outside_ssim),
        "mad_outside": float(mad_outside),
        "change_ssim": float(change_ssim),
        "seam_ssim": float(seam_ssim),
    }


def metric_census(stages=STAGES):
    """Score every working of every 2+-working slug. Higher seam_ssim is better;
    a LOWER change_ssim means the edit region moved further from the initial.
    """
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import lw_clean_pass as clean_pass

    out = []
    for slug, d, _man in load_manifests(stages):
        initial = os.path.join(d, f"{slug}_cleaninitial.png")
        if not os.path.isfile(initial):
            continue
        workings = sorted(
            (working_version(n), os.path.join(d, n))
            for n in os.listdir(d) if _WORKING_RE.search(n)
        )
        if len(workings) < 2:
            continue
        scored = []
        for v, path in workings:
            row = metric_row(initial, path, clean_pass)
            row["version"] = v
            scored.append(row)
        out.append({"slug": slug, "workings": scored})
    return out


def _fmt_metric_table(census):
    lines = []
    seam_wins = seam_losses = ties = 0
    for entry in census:
        lines.append(entry["slug"])
        base = next((w for w in entry["workings"] if w["version"] == 1), None)
        for w in entry["workings"]:
            if w.get("error"):
                lines.append(f"  _{w['version']:02d} ERROR {w['error']}")
                continue
            if w.get("no_op"):
                lines.append(f"  _{w['version']:02d} NO-OP (identical to initial)")
                continue
            lines.append(
                f"  _{w['version']:02d} edit={w['edit_pct']:6.3f}%"
                f" outside_ssim={w['outside_ssim']:.5f}"
                f" mad={w['mad_outside']:.3f}"
                f" change_ssim={w['change_ssim']:.4f}"
                f" seam_ssim={w['seam_ssim']:.4f}"
            )
            if base and w["version"] > 1 and not base.get("no_op"):
                if w["seam_ssim"] > base["seam_ssim"]:
                    seam_wins += 1
                elif w["seam_ssim"] < base["seam_ssim"]:
                    seam_losses += 1
                else:
                    ties += 1
    lines.append("")
    lines.append(
        f"seam_ssim vs _01 (all retries pooled):"
        f" BETTER={seam_wins} WORSE={seam_losses} TIE={ties}"
    )

    # Pooling hides the real shape: _02 and _03 are DIFFERENT ENGINES, not two
    # attempts by one. Break the comparison out per version, and carry the edit
    # area with it - a retry that "wins" on seam by repainting 3x more of the
    # image is not a better clean, it is a bigger one.
    per_version = {}
    for entry in census:
        base = next((w for w in entry["workings"] if w["version"] == 1), None)
        if not base or base.get("no_op") or base.get("error"):
            continue
        for w in entry["workings"]:
            if w["version"] == 1 or w.get("no_op") or w.get("error"):
                continue
            d = per_version.setdefault(w["version"], {
                "n": 0, "seam_better": 0, "seam_worse": 0,
                "area_ratio": [], "change_lower": 0,
            })
            d["n"] += 1
            if w["seam_ssim"] > base["seam_ssim"]:
                d["seam_better"] += 1
            elif w["seam_ssim"] < base["seam_ssim"]:
                d["seam_worse"] += 1
            if base["edit_pct"] > 0:
                d["area_ratio"].append(w["edit_pct"] / base["edit_pct"])
            if w["change_ssim"] < base["change_ssim"]:
                d["change_lower"] += 1
    lines.append("")
    lines.append("per-version vs _01:")
    for v in sorted(per_version):
        d = per_version[v]
        avg_area = sum(d["area_ratio"]) / len(d["area_ratio"]) if d["area_ratio"] else 0
        lines.append(
            f"  _{v:02d}  n={d['n']:2d}  seam better={d['seam_better']:2d}"
            f" worse={d['seam_worse']:2d} | mean edit-area vs _01 = {avg_area:.2f}x"
            f" | moved further from initial in {d['change_lower']}/{d['n']}"
        )
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_retry_probe")
    ap.add_argument("--metrics", action="store_true",
                    help="also run the metric census (needs numpy + PIL)")
    ap.add_argument("--json", action="store_true", help="dump raw JSON")
    args = ap.parse_args(argv)

    vc = verdict_census()
    if args.json:
        payload = {"verdict": vc}
        if args.metrics:
            payload["metric"] = metric_census()
        print(json.dumps(payload, indent=1))
        return 0

    t = vc["totals"]
    print("VERDICT CENSUS (operator adjudication, from manifests)")
    for r in vc["rows"]:
        if len(r["saved"]) < 2 and len(r["workings_on_disk"]) < 2:
            continue
        won = "-"
        if r["approved_sha12"]:
            won = ("_cleaninitial (no clean)" if r["approved_is_cleaninitial"]
                   else f"_{r['origin_version']:02d}")
        tools = ",".join(f"{v}:{t or '?'}" for v, t in r["saved"].items())
        print(f"  {r['slug'][:52]:52} rejected={str(r['rejected']):12}"
              f" won={won:24} [{tools}]")
    print()
    print(f"  slugs total                  : {t['slugs']}")
    print(f"  slugs with 2+ workings       : {t['slugs_with_2plus_workings']}")
    print(f"  ...of those, decided         : {t['decided']}")
    print(f"  ...won by _01                : {t['settled_on_01']}")
    print(f"  ...won by a retry (_02+)     : {t['settled_above_01']}")
    print(f"  ...won by _cleaninitial      : {t['settled_on_cleaninitial']}")
    print(f"  ...still undecided           : {t['undecided']}")
    print(f"  rejected workings (all slugs) : {t['rejected_workings_total']}")

    if args.metrics:
        print()
        print("METRIC CENSUS (cleaning gate's own functions, vs _cleaninitial)")
        print(_fmt_metric_table(metric_census()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
