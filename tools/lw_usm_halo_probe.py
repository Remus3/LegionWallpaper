"""USM-vs-upscaler halo attribution probe (S6) - a MEASUREMENT, not a gate.

WHY this exists: the 2026-07-30 first-pass batch flagged 7 of 14 gated slugs and
every single flag was the same reason - halo_pct over the 0.05 line
(tools/lw_g1_gate.py:51). The previous 46-slug batch flagged nothing, but those
46 sources were already exactly 2560x1440 and so took the no-resample-no-sharpen
passthrough (tools/lw_upscale.py:108 _usm_applies), which runs no unsharp mask at
all. The two batches therefore differ on TWO axes at once - resampled vs not, and
USM vs no USM - and nobody has separated them. This probe separates them.

The measurement holds everything constant except the finishing unsharp mask:

  A  the shipped path - one 4x upscale (or the downscale-only branch), one
     Lanczos downscale to 2560x1440, one UnsharpMask at USM_DEFAULT.
  B  identical up to the mask, with the UnsharpMask SKIPPED.

Both variants are derived from the SAME raw upscale inside one worker process, so
the A-vs-B delta carries no upscaler nondeterminism. If B collapses under the
0.05 line the flags are manufactured by our own mask; if B stays high the
upscaler is producing the overshoot and the mask is at most an amplifier.

NOTHING here writes into images\\ and nothing re-runs the pipeline. The probe
re-derives each slug's conditioned source with the shipped selector + conditioner
(lw_first_pass.select_source:202, condition_source:433) into a caller-supplied
work directory, and scores every variant with the shipped metric function
(lw_first_pass.compute_numpy_metrics:355) so no metric is reimplemented here.

Process split, mirroring the shipped pipeline exactly: the upscale + finish run
in .venv-upscale (torch/spandrel live only there) and write one PNG per variant;
the numpy metrics run in SYSTEM python, in-process, against those PNGs. Measuring
the metric in the same interpreter the pipeline uses is what makes variant A
comparable to the manifest number it is being checked against.

Exit codes (CLI): 0 report written; 2 usage / no slug resolved.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_first_pass as fp  # noqa: E402
from lw_g1_gate import DEFAULT_G1_THRESHOLDS  # noqa: E402
from lw_upscale import (  # noqa: E402
    ASPECT_TOL,
    TARGET,
    USM_DEFAULT,
    _covers_target,
    _finish,
    _usm_applies,
)

# CREATE_NO_WINDOW: Legion focus-steal rule - a bare spawn flashes a console and
# steals focus. getattr guard so the module still imports off Windows.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

HALO_FLAG = DEFAULT_G1_THRESHOLDS["halo_pct"]["flag"]

# The literal spelling of "no unsharp mask" on the CLI and in the report.
NO_USM = "none"


# ==========================================================================
# Pure logic
# ==========================================================================
def parse_usm_spec(spec):
    """Parse one --usm value into a (radius, percent, threshold) tuple or None.

    "none" (any case) means condition B - skip the mask entirely - and maps to
    None, which is what finish_variant reads as "no mask". Anything else must be
    three comma-separated numbers in lw_upscale's own parameter order.
    """
    text = str(spec).strip()
    if text.lower() == NO_USM:
        return None
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        raise ValueError(
            f"bad --usm {spec!r}: expected 'radius,percent,threshold' or '{NO_USM}'"
        )
    return (float(parts[0]), int(parts[1]), int(parts[2]))


def variant_label(usm):
    """Stable report key for a usm triple (or None). Deterministic across runs."""
    if usm is None:
        return "no_usm"
    radius, percent, threshold = usm
    return f"usm_{radius:g}_{int(percent)}_{int(threshold)}"


def latest_g1_audit(manifest):
    """Return the newest G1 audit block from a manifest dict, or None.

    The audit is NOT at manifest top level - it lives at transitions[i]["audit"]
    for the ANNOTATE transition (tools/lw_first_pass.py:578 writes it through
    pipeline_annotate). A top-level read silently returns empty for every field,
    which is exactly how a census ends up reporting zeros as measurements, so
    this walks the transitions newest-first and never consults the top level.
    """
    if not isinstance(manifest, dict):
        return None
    for transition in reversed(manifest.get("transitions", []) or []):
        audit = transition.get("audit")
        if isinstance(audit, dict) and audit.get("gate") == "G1":
            return audit
    return None


def shipped_halo(manifest):
    """The halo_pct this slug actually shipped with, or None if never gated."""
    audit = latest_g1_audit(manifest)
    if not audit:
        return None
    value = (audit.get("metrics") or {}).get("halo_pct")
    return float(value) if isinstance(value, (int, float)) else None


def finish_variant(raw_img, target=TARGET, usm=USM_DEFAULT):
    """Finish a raw upscale, with usm=None meaning 'skip the unsharp mask'.

    The usm-carrying branch DELEGATES to lw_upscale._finish rather than
    re-deriving it, so condition A is the shipped code path and not a lookalike
    that could drift from it. The usm=None branch reproduces the same geometry -
    same aspect guard, same single Lanczos resize, same already-at-target
    passthrough (_usm_applies) - and stops before the mask.

    The aspect guard is repeated rather than dropped: a measurement branch that
    silently squashes aspect where the shipped branch refuses would compare two
    different pictures and call the difference a halo.
    """
    if usm is not None:
        return _finish(raw_img, target=target, usm=usm)
    from PIL import Image

    src_w, src_h = raw_img.size
    if abs(src_w / src_h - target[0] / target[1]) > ASPECT_TOL:
        raise ValueError(
            f"aspect mismatch: source {src_w}x{src_h} vs target "
            f"{target[0]}x{target[1]} exceeds tolerance {ASPECT_TOL:.4f}"
        )
    img = raw_img.convert("RGB")
    if not _usm_applies(raw_img.size, target):
        return img
    return img.resize(target, Image.LANCZOS)


def classify_slugs(scratch_root, wanted):
    """Slugs under scratch_root whose newest G1 verdict is in `wanted`.

    wanted is a set of verdict strings ("FLAG", "PASS", ...). A slug with no G1
    audit - held, or never gated - is never returned, because there is no
    shipped halo number to reproduce for it.
    """
    base = Path(scratch_root)
    if not base.is_dir():
        return []
    out = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        audit = latest_g1_audit(manifest)
        if audit and audit.get("verdict") in wanted:
            out.append(child.name)
    return out


def crossings(rows, threshold=HALO_FLAG):
    """Summarize an A/B census: how many slugs each variant puts over the line.

    rows is the report's per-slug list. Returns {variant: {"over": n,
    "measured": n, "max": x, "min": x}} - a distribution, not a verdict. Any
    threshold proposal has to be read off this, never picked ahead of it.
    """
    summary = {}
    for row in rows:
        for label, result in (row.get("variants") or {}).items():
            halo = result.get("halo_pct")
            if not isinstance(halo, (int, float)):
                continue
            bucket = summary.setdefault(
                label, {"over": 0, "measured": 0, "max": None, "min": None}
            )
            bucket["measured"] += 1
            if halo > threshold:
                bucket["over"] += 1
            if bucket["max"] is None or halo > bucket["max"]:
                bucket["max"] = halo
            if bucket["min"] is None or halo < bucket["min"]:
                bucket["min"] = halo
    return summary


def _atomic_write_json(path, payload):
    """Write JSON via tmp + os.replace (project hard rule: consumers may poll)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, target)


# ==========================================================================
# Worker (runs under .venv-upscale - torch/spandrel live only there)
# ==========================================================================
def worker_render(src_path, out_dir, usm_specs, model_path=None, target=TARGET):
    """Produce one finished PNG per variant from ONE raw upscale. Returns meta.

    Both the AI-upscale branch and the over-target downscale-only branch are
    reproduced from lw_upscale.first_pass:364-395 so a downscale-only slug is
    measured on its real path instead of being silently pushed through the model.

    The raw upscale happens exactly once and every variant is finished from that
    same in-memory image - that is what makes the A-vs-B delta attributable to
    the mask alone rather than to two separate GPU runs.
    """
    from PIL import Image

    from lw_upscale import upscale_spandrel

    model_path = model_path or fp.MODEL_PATH
    with Image.open(src_path) as probe:
        src_w, src_h = probe.size
        if _covers_target(src_w, src_h, target):
            raw = probe.convert("RGB")
            backend = "downscale-only"
        else:
            raw = None
            backend = "spandrel"

    t0 = time.time()
    if raw is None:
        raw, _meta = upscale_spandrel(src_path, model_path)

    variants = {}
    for spec in usm_specs:
        usm = parse_usm_spec(spec)
        label = variant_label(usm)
        finished = finish_variant(raw, target=target, usm=usm)
        out_path = os.path.join(str(out_dir), f"{label}.png")
        tmp_path = out_path + ".part"
        finished.save(tmp_path, format="PNG")
        os.replace(tmp_path, out_path)
        variants[label] = {
            "usm": list(usm) if usm else None,
            "png": out_path,
            "dims": list(finished.size),
        }

    return {
        "backend": backend,
        "src_dims": [src_w, src_h],
        "up_dims": list(raw.size),
        "usm_applies": _usm_applies(raw.size, target),
        "variants": variants,
        "seconds": round(time.time() - t0, 3),
    }


# ==========================================================================
# Driver (system python)
# ==========================================================================
def _spawn_worker(python_exe, src_path, out_dir, usm_specs, model_path=None):
    """Run this module's --worker mode under `python_exe`, return its JSON dict.

    CREATE_NO_WINDOW is mandatory here (Legion focus-steal rule).
    """
    argv = [
        python_exe, os.path.abspath(__file__), "--worker",
        "--worker-src", str(src_path),
        "--worker-out-dir", str(out_dir),
    ]
    for spec in usm_specs:
        argv += ["--usm", str(spec)]
    if model_path:
        argv += ["--model", str(model_path)]
    proc = subprocess.run(
        argv, capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"worker rc={proc.returncode}: {(proc.stderr or '')[-600:]}"
        )
    return fp._last_json_line(proc.stdout)


def measure_slug(slug, work_root, usm_specs, python_exe, model_path=None):
    """Measure every USM variant for one slug. Returns a report row dict.

    The source is re-derived, never re-used from the pipeline run: select_source
    then condition_source, both the shipped functions, writing any 16:9 crop into
    work_root. The slug's own folder under images\\ is only ever READ.
    """
    scratch = fp.scratch_dir_for(slug)
    src, kind = fp.select_source(slug, scratch)
    if src is None:
        return {"slug": slug, "status": "error", "reason": "no decodable source"}

    manifest_path = Path(scratch) / "manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
    audit = latest_g1_audit(manifest) or {}

    slug_dir = Path(work_root) / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    conditioned, cplan = fp.condition_source(src, str(slug_dir))
    if conditioned is None:
        return {"slug": slug, "status": "held",
                "reason": cplan.get("aspect_class"), "plan": cplan}

    meta = _spawn_worker(python_exe, conditioned, slug_dir, usm_specs, model_path)

    variants = {}
    for label, info in meta["variants"].items():
        lap, halo, band = fp.compute_numpy_metrics(conditioned, info["png"])
        variants[label] = {
            "usm": info["usm"],
            "halo_pct": halo,
            "lap_ratio": round(float(lap), 4),
            "band_delta": round(float(band), 6),
            "over_flag": halo > HALO_FLAG,
        }

    row = {
        "slug": slug,
        "status": "ok",
        "source_choice": kind,
        "source_path": src,
        "conditioned_dims": meta["src_dims"],
        "cropped": cplan.get("cropped"),
        "backend": meta["backend"],
        "up_dims": meta["up_dims"],
        "usm_applies": meta["usm_applies"],
        "shipped_verdict": audit.get("verdict"),
        "shipped_halo_pct": shipped_halo(manifest),
        "variants": variants,
        "worker_seconds": meta["seconds"],
    }
    baseline = variants.get(variant_label(USM_DEFAULT))
    no_mask = variants.get("no_usm")
    if baseline and no_mask:
        row["delta_a_minus_b"] = round(
            baseline["halo_pct"] - no_mask["halo_pct"], 4
        )
    return row


def run_census(slugs, work_root, usm_specs, python_exe, model_path=None):
    """Measure every slug in order; a per-slug failure never kills the census."""
    rows = []
    for slug in slugs:
        try:
            rows.append(
                measure_slug(slug, work_root, usm_specs, python_exe, model_path)
            )
        except Exception as exc:  # noqa: BLE001 - one bad slug != a dead census
            rows.append({"slug": slug, "status": "error",
                         "reason": f"{type(exc).__name__}: {exc}"})
        print(f"[{len(rows)}/{len(slugs)}] {slug} -> {rows[-1].get('status')}",
              flush=True)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Measure G1 halo_pct with and without the finishing unsharp "
                    "mask. Read-only against images - writes nothing there."
    )
    ap.add_argument("--slug", action="append", default=[],
                    help="slug to measure (repeatable)")
    ap.add_argument("--batch", choices=("flagged", "passed", "all"),
                    help="resolve slugs from the scratch tree by shipped G1 verdict")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap the number of --batch slugs (0 = no cap)")
    ap.add_argument("--usm", action="append", default=[],
                    help="usm variant 'radius,percent,threshold' or 'none' "
                         "(repeatable; default: the shipped recipe plus 'none')")
    ap.add_argument("--out", help="JSON report path (atomic write)")
    ap.add_argument("--work-dir", help="scratch dir for conditioned + finished PNGs")
    ap.add_argument("--python", default=fp.UP_PY,
                    help="python that owns torch/spandrel (.venv-upscale)")
    ap.add_argument("--model", default=fp.MODEL_PATH, help="upscaler .safetensors")
    ap.add_argument("--scratch-root", default=fp.FIRST_SCRATCH,
                    help="the 1.First Pass Scratch tree to resolve --batch against")
    # Worker mode: internal, spawned by _spawn_worker under the upscale venv.
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--worker-src", help=argparse.SUPPRESS)
    ap.add_argument("--worker-out-dir", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    usm_specs = args.usm or [
        f"{USM_DEFAULT[0]:g},{USM_DEFAULT[1]},{USM_DEFAULT[2]}", NO_USM
    ]

    if args.worker:
        if not args.worker_src or not args.worker_out_dir:
            ap.error("--worker needs --worker-src and --worker-out-dir")
        meta = worker_render(args.worker_src, args.worker_out_dir, usm_specs,
                             model_path=args.model)
        print(json.dumps(meta))
        return 0

    slugs = list(args.slug)
    if args.batch:
        wanted = {"flagged": {"FLAG"}, "passed": {"PASS"},
                  "all": {"FLAG", "PASS", "FAIL"}}[args.batch]
        found = classify_slugs(args.scratch_root, wanted)
        if args.limit > 0:
            found = found[: args.limit]
        slugs += [s for s in found if s not in slugs]
    if not slugs:
        print("no slugs resolved - pass --slug or --batch", file=sys.stderr)
        return 2

    work_root = args.work_dir or tempfile.mkdtemp(prefix="lw_usm_halo_")
    Path(work_root).mkdir(parents=True, exist_ok=True)
    rows = run_census(slugs, work_root, usm_specs, args.python, args.model)
    report = {
        "probe": "lw_usm_halo_probe",
        "halo_flag_threshold": HALO_FLAG,
        "usm_default": list(USM_DEFAULT),
        "usm_specs": usm_specs,
        "work_dir": str(work_root),
        "rows": rows,
        "crossings": crossings(rows),
    }
    if args.out:
        _atomic_write_json(args.out, report)
        print(f"report -> {args.out}")
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
