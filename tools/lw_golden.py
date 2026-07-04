"""lw_golden.py - first-pass golden-set freeze/regress (docs/research/GOLDEN_SET.md).

Pure stdlib + numpy + PIL at import time. Heavy deps (pyiqa/torch via
lw_g1_gate, spandrel via lw_upscale) are INJECTED or lazy-imported so this module
imports cleanly in CI. Atomic writes only.

freeze  - build data/golden/golden_set.json from the blessed IJN baselines,
          copying image bytes to a durable gitignored location.
regress - re-score a candidate-output dir against the frozen baseline metrics
          within epsilon; flag any case that drifted.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

SCHEMA = 1

# Regression tolerances (docs/research/GOLDEN_SET.md section 5). Absolute for
# msssim/lpips/halo_pct; relative for lap_ratio.
EPSILON = {"msssim": 0.01, "lpips": 0.02, "lap_ratio_rel": 0.05, "halo_pct": 0.02}


# --------------------------------------------------------------- helpers
def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def pipeline_version(pinned: dict) -> str:
    """sha256 of the canonical (order-independent) JSON of the pinned tuple."""
    return hashlib.sha256(_canonical(pinned).encode("ascii")).hexdigest()


def new_manifest(pv: str, created_ts: str) -> dict:
    return {"schema": SCHEMA, "pipeline_version": pv,
            "created_ts": created_ts, "cases": []}


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="ascii")
    os.replace(tmp, path)


def _copy_into(src, dstdir: Path):
    dstdir.mkdir(parents=True, exist_ok=True)
    name = os.path.basename(src)
    dst = dstdir / name
    tmp = dstdir / (name + ".part")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)
    return name, _sha256_file(dst)


# --------------------------------------------------------------- freeze
def freeze(cases, out_root, pinned, compute_metrics, ts=None):
    """Build the golden manifest from blessed (input, baseline) pairs.

    cases: list of {slug, input_path, baseline_path, defect_axes} (blessed only).
    compute_metrics(input_path, output_path) -> dict is injected (the CLI wires
    the real lw_g1_gate adapter; tests pass a fake). Copies bytes into
    out_root/{inputs,baseline}/ and writes out_root/golden_set.json atomically.
    """
    out_root = Path(out_root)
    man = new_manifest(pipeline_version(pinned), ts or iso_now())
    for c in cases:
        in_name, in_sha = _copy_into(c["input_path"], out_root / "inputs")
        base_name, base_sha = _copy_into(c["baseline_path"], out_root / "baseline")
        man["cases"].append({
            "slug": c["slug"],
            "input": {"path": f"data/golden/inputs/{in_name}", "sha256": in_sha},
            "baseline": {"path": f"data/golden/baseline/{base_name}", "sha256": base_sha},
            "metrics": compute_metrics(c["input_path"], c["baseline_path"]),
            "defect_axes": c.get("defect_axes", []),
            "blessed": True,
        })
    _write_json_atomic(out_root / "golden_set.json", man)
    return man


# --------------------------------------------------------------- regress
def _compare(base, cur):
    reasons = []
    for k in ("msssim", "lpips", "halo_pct"):
        if k in base and k in cur and abs(float(cur[k]) - float(base[k])) > EPSILON[k]:
            reasons.append(f"{k} {cur[k]:g} vs baseline {base[k]:g} (> {EPSILON[k]})")
    if "lap_ratio" in base and "lap_ratio" in cur and float(base["lap_ratio"]):
        rel = abs(float(cur["lap_ratio"]) - float(base["lap_ratio"])) / float(base["lap_ratio"])
        if rel > EPSILON["lap_ratio_rel"]:
            reasons.append(
                f"lap_ratio {cur['lap_ratio']:g} vs {base['lap_ratio']:g} ({rel:.1%} > 5%)")
    return reasons


def regress(manifest, candidates_dir, compute_metrics, current_pv=None):
    """Score each candidate output vs the frozen baseline metrics within epsilon.

    candidates_dir holds re-upscaled outputs named like each case's baseline
    basename (produced by re-running lw_upscale under .venv-upscale). Returns
    {ok, pipeline_version_changed, cases:[{slug, ok, reasons, current}]}.
    """
    candidates_dir = Path(candidates_dir)
    pv_changed = bool(current_pv) and current_pv != manifest.get("pipeline_version")
    cases_out = []
    all_ok = True
    for case in manifest["cases"]:
        base_name = os.path.basename(case["baseline"]["path"])
        cand = candidates_dir / base_name
        if not cand.is_file():
            cases_out.append({"slug": case["slug"], "ok": False,
                              "reasons": [f"missing candidate {base_name}"]})
            all_ok = False
            continue
        cur = compute_metrics(case["input"]["path"], str(cand))
        reasons = _compare(case["metrics"], cur)
        ok = not reasons
        all_ok = all_ok and ok
        cases_out.append({"slug": case["slug"], "ok": ok,
                          "reasons": reasons, "current": cur})
    return {"ok": all_ok, "pipeline_version_changed": pv_changed, "cases": cases_out}


# --------------------------------------------------------------- real adapters (lazy)
def _real_compute_metrics(input_path, output_path):
    """Real metrics: common-scale self FR (pyiqa) + numpy cheap checks.

    Lazy-imports numpy/PIL/lw_g1_gate so the module stays CI-importable; run
    under .venv-metrics (pyiqa + torch present).
    """
    import numpy as np
    from PIL import Image

    from tools import lw_g1_gate as g1
    src_im = Image.open(input_path).convert("RGB")
    sw, sh = src_im.size
    src_g = np.asarray(src_im.convert("L"), dtype=np.float64)
    out_g = np.asarray(
        Image.open(output_path).convert("RGB").resize((sw, sh), Image.LANCZOS).convert("L"),
        dtype=np.float64)
    fr = g1.fr_metrics(str(output_path), str(input_path), str(input_path),
                       names=("ms_ssim", "lpips"))
    return {
        "msssim": fr.get("ms_ssim"), "lpips": fr.get("lpips"),
        "lap_ratio": g1.laplacian_ratio(src_g, out_g),
        "halo_pct": g1.overshoot_halo(src_g, out_g)["halo_pct"],
        "band_delta": g1.banding_delta(src_g, out_g),
    }


def _pinned_from_config(model_path):
    import torch

    from tools import lw_g1_gate as g1
    return {
        "model": os.path.basename(model_path),
        "model_sha256": _sha256_file(model_path),
        "backend": "spandrel", "torch": torch.__version__,
        "target": [2560, 1440],
        "usm": {"radius": 1.2, "percent": 70, "threshold": 3},
        "thresholds": g1.DEFAULT_G1_THRESHOLDS,
    }


# --------------------------------------------------------------- CLI
def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="lw_golden",
                                description="first-pass golden-set freeze/regress")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze", help="build golden_set.json from blessed baselines")
    f.add_argument("--cases-json", required=True,
                   help="JSON list of blessed {slug,input_path,baseline_path,defect_axes}")
    f.add_argument("--model", required=True, help="upscaler .pth (pins pipeline_version)")
    f.add_argument("--out-root", default="data/golden")
    r = sub.add_parser("regress", help="score a candidate dir vs the frozen baseline")
    r.add_argument("--candidates-dir", required=True)
    r.add_argument("--manifest", default="data/golden/golden_set.json")
    r.add_argument("--model", required=True)
    a = p.parse_args(argv)

    if a.cmd == "freeze":
        cases = json.loads(Path(a.cases_json).read_text(encoding="utf-8"))
        man = freeze(cases, a.out_root, _pinned_from_config(a.model), _real_compute_metrics)
        print(f"froze {len(man['cases'])} cases -> {a.out_root}/golden_set.json "
              f"pv={man['pipeline_version'][:12]}")
        return 0

    man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    rep = regress(man, a.candidates_dir, _real_compute_metrics,
                  current_pv=pipeline_version(_pinned_from_config(a.model)))
    for c in rep["cases"]:
        print(f"  {c['slug']:<42} {'OK' if c['ok'] else 'FLAG'} "
              f"{'; '.join(c.get('reasons', []))}")
    print(f"regress: {'PASS' if rep['ok'] else 'REGRESSIONS'} "
          f"pv_changed={rep['pipeline_version_changed']}")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    import sys
    # Running as a script puts tools/ on sys.path[0], not the repo root, so the
    # lazy `from tools import lw_g1_gate` in the real adapters would fail. Put the
    # repo root (parent of tools/) on the path first.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main())
