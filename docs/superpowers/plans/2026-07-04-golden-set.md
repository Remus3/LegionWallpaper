# First-Pass Golden-Set Regression Protocol - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tools/lw_golden.py` (freeze + regress) so first-pass pipeline changes regress against a frozen, operator-blessed IllustrationJaNai baseline - no ground-truth required.

**Architecture:** A pure stdlib+numpy+PIL orchestrator with heavy deps INJECTED (a `compute_metrics` callable + a `torch_version` string), so the whole tool is CI-testable while the CLI wires the real `lw_g1_gate` metrics under `.venv-metrics`. `freeze` adopts the already-produced blessed IJN outputs, copies bytes to durable gitignored storage, and writes a committed JSON manifest. `regress` scores a candidate-output dir (produced by re-running `lw_upscale` under `.venv-upscale`) against the frozen baseline metrics within epsilon.

**Tech Stack:** Python (stdlib + numpy + Pillow); reuses `tools/lw_g1_gate.py` (metrics/verdict) and `tools/lw_upscale.py` (first_pass) from commit dca6071; `.venv-metrics` (pyiqa) runs freeze/regress, `.venv-upscale` (spandrel) produces regress candidates.

## Global Constraints

- 7-bit ASCII only in all authored text; no em/en dashes, no smart quotes; " - " for clause breaks. Enforced by the precommit hook.
- Atomic writes: write tmp then `os.replace`.
- CI (python 3.12) has only pytest, ruff, numpy, Pillow. `lw_golden.py` must import ONLY stdlib + numpy + PIL at module top level. NEVER import torch/pyiqa/spandrel at top level; inject them. Tests use `pytest.importorskip` for any heavy path.
- System python (tests): `C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`. Metrics venv: `C:\LegionWallpaper\.venv-metrics\Scripts\python.exe`. Upscale venv: `C:\LegionWallpaper\.venv-upscale\Scripts\python.exe`.
- Privacy: `data/golden/golden_set.json` is TRACKED; `data/golden/inputs/**` and `data/golden/baseline/**` are gitignored. Never commit image bytes.
- Spec: `docs/research/GOLDEN_SET.md`. Epsilon (section 5): MS-SSIM 0.01, LPIPS 0.02, lap_ratio 5 percent (relative), halo_pct 0.02.

---

## File Structure

- Create `tools/lw_golden.py` - the golden-set tool (manifest schema, pipeline_version, freeze, regress, CLI). One responsibility: golden-set freeze/regress. ~250 lines.
- Create `tests/test_lw_golden.py` - unit tests (stdlib + numpy + PIL + tmp_path; injected fake metrics; no pyiqa/torch).
- Modify `.gitignore` - add `data/golden/inputs/` and `data/golden/baseline/`.
- Create (live, not committed bytes) `data/golden/golden_set.json` (tracked) + `data/golden/{inputs,baseline}/` (gitignored) via the live freeze.

---

## Task 1: Manifest schema + deterministic pipeline_version

**Files:**
- Create: `tools/lw_golden.py`
- Test: `tests/test_lw_golden.py`

**Interfaces:**
- Produces: `pipeline_version(pinned: dict) -> str` (sha256 hex of canonical-JSON of `pinned`); `new_manifest(pipeline_version: str, created_ts: str) -> dict`; `SCHEMA = 1`.

- [ ] **Step 1: Write the failing test**

```python
import os, sys
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools import lw_golden  # noqa: E402

def test_pipeline_version_is_deterministic_and_order_independent():
    a = {"model": "x.pth", "model_sha256": "ab", "torch": "2.11.0", "usm": {"radius": 1.2, "percent": 70}}
    b = {"usm": {"percent": 70, "radius": 1.2}, "torch": "2.11.0", "model_sha256": "ab", "model": "x.pth"}
    assert lw_golden.pipeline_version(a) == lw_golden.pipeline_version(b)
    assert len(lw_golden.pipeline_version(a)) == 64
    c = dict(a); c["torch"] = "2.12.0"
    assert lw_golden.pipeline_version(c) != lw_golden.pipeline_version(a)

def test_new_manifest_shape():
    m = lw_golden.new_manifest("deadbeef", "2026-07-04T00:00:00Z")
    assert m == {"schema": 1, "pipeline_version": "deadbeef",
                 "created_ts": "2026-07-04T00:00:00Z", "cases": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_lw_golden.py -q`
Expected: FAIL (module/attribute not found).

- [ ] **Step 3: Write minimal implementation**

```python
"""lw_golden.py - first-pass golden-set freeze/regress (see docs/research/GOLDEN_SET.md).

Pure stdlib + numpy + PIL at import time. Heavy deps (pyiqa/torch via
lw_g1_gate, spandrel via lw_upscale) are injected or subprocessed so this module
imports cleanly in CI. Atomic writes only.
"""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path

SCHEMA = 1

def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))

def pipeline_version(pinned: dict) -> str:
    return hashlib.sha256(_canonical(pinned).encode("ascii")).hexdigest()

def new_manifest(pv: str, created_ts: str) -> dict:
    return {"schema": SCHEMA, "pipeline_version": pv, "created_ts": created_ts, "cases": []}

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_lw_golden.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/lw_golden.py tests/test_lw_golden.py
git commit -m "feat(golden): manifest schema + deterministic pipeline_version"
```

---

## Task 2: freeze - build the manifest from blessed baselines

**Files:**
- Modify: `tools/lw_golden.py`
- Test: `tests/test_lw_golden.py`

**Interfaces:**
- Consumes: `pipeline_version`, `new_manifest`, `_sha256_file`, `_write_json_atomic`, `iso_now`.
- Produces: `freeze(cases, out_root, pinned, compute_metrics, ts=None) -> dict`. `cases` = list of `{"slug","input_path","baseline_path","defect_axes"}` (only blessed cases passed in). `compute_metrics(input_path, output_path) -> dict` is INJECTED (real one wraps lw_g1_gate; tests pass a fake). Copies each input to `out_root/inputs/<name>` and baseline to `out_root/baseline/<name>`, computes metrics, writes `out_root/golden_set.json`. Returns the manifest.

- [ ] **Step 1: Write the failing test**

```python
from PIL import Image

def _mkimg(path, size=(64, 36), color=(120, 90, 60)):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)

def test_freeze_writes_manifest_and_copies_bytes(tmp_path):
    inp = tmp_path / "src" / "fiora2_firstinitial.jpg"; _mkimg(inp)
    base = tmp_path / "scratch" / "fiora2_ijn.png"; _mkimg(base, (256, 144))
    out_root = tmp_path / "golden"
    fake = lambda i, o: {"msssim": 0.99, "lpips": 0.02, "lap_ratio": 1.5, "halo_pct": 0.03, "band_delta": 0.0}
    man = lw_golden.freeze(
        [{"slug": "fiora2", "input_path": str(inp), "baseline_path": str(base), "defect_axes": ["soft-source"]}],
        out_root, {"model": "v1.pth", "torch": "2.11.0"}, fake, ts="2026-07-04T00:00:00Z")
    assert (out_root / "golden_set.json").is_file()
    assert (out_root / "inputs" / "fiora2_firstinitial.jpg").is_file()
    assert (out_root / "baseline" / "fiora2_ijn.png").is_file()
    case = man["cases"][0]
    assert case["slug"] == "fiora2"
    assert case["metrics"]["msssim"] == 0.99
    assert case["input"]["sha256"] and case["baseline"]["sha256"]
    assert man["pipeline_version"] == lw_golden.pipeline_version({"model": "v1.pth", "torch": "2.11.0"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_lw_golden.py::test_freeze_writes_manifest_and_copies_bytes -q`
Expected: FAIL (`freeze` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
import shutil

def _copy_into(src, dstdir: Path) -> tuple[str, str]:
    dstdir.mkdir(parents=True, exist_ok=True)
    name = os.path.basename(src)
    dst = dstdir / name
    tmp = dstdir / (name + ".part")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)
    return name, _sha256_file(dst)

def freeze(cases, out_root, pinned, compute_metrics, ts=None):
    out_root = Path(out_root)
    pv = pipeline_version(pinned)
    man = new_manifest(pv, ts or iso_now())
    for c in cases:
        in_name, in_sha = _copy_into(c["input_path"], out_root / "inputs")
        base_name, base_sha = _copy_into(c["baseline_path"], out_root / "baseline")
        metrics = compute_metrics(c["input_path"], c["baseline_path"])
        man["cases"].append({
            "slug": c["slug"],
            "input": {"path": f"data/golden/inputs/{in_name}", "sha256": in_sha},
            "baseline": {"path": f"data/golden/baseline/{base_name}", "sha256": base_sha},
            "metrics": metrics,
            "defect_axes": c.get("defect_axes", []),
            "blessed": True,
        })
    _write_json_atomic(out_root / "golden_set.json", man)
    return man
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_lw_golden.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/lw_golden.py tests/test_lw_golden.py
git commit -m "feat(golden): freeze verb - manifest + durable byte copy"
```

---

## Task 3: regress - compare candidate metrics to baseline within epsilon

**Files:**
- Modify: `tools/lw_golden.py`
- Test: `tests/test_lw_golden.py`

**Interfaces:**
- Consumes: manifest dict from `freeze`.
- Produces: `EPSILON = {"msssim": 0.01, "lpips": 0.02, "lap_ratio_rel": 0.05, "halo_pct": 0.02}`; `regress(manifest, candidates_dir, compute_metrics, current_pv=None) -> dict` returning `{"ok": bool, "cases": [...], "pipeline_version_changed": bool}`. For each manifest case, find `candidates_dir/<basename-of-baseline>`, compute its metrics, compare to `case["metrics"]`: msssim/lpips/halo_pct use absolute epsilon, lap_ratio uses relative 5 percent. A case is `ok` only if every metric is within epsilon. Missing candidate -> case ok=False, reason "missing candidate".

- [ ] **Step 1: Write the failing test**

```python
def _man_one(metrics):
    return {"schema": 1, "pipeline_version": "pv0", "created_ts": "t", "cases": [
        {"slug": "s", "input": {"path": "i", "sha256": "a"},
         "baseline": {"path": "data/golden/baseline/s_ijn.png", "sha256": "b"},
         "metrics": metrics, "defect_axes": [], "blessed": True}]}

def test_regress_passes_within_epsilon(tmp_path):
    (tmp_path / "s_ijn.png").write_bytes(b"x")
    man = _man_one({"msssim": 0.99, "lpips": 0.02, "lap_ratio": 2.0, "halo_pct": 0.03, "band_delta": 0.0})
    fake = lambda i, o: {"msssim": 0.985, "lpips": 0.035, "lap_ratio": 2.08, "halo_pct": 0.04, "band_delta": 0.0}
    rep = lw_golden.regress(man, tmp_path, fake, current_pv="pv0")
    assert rep["ok"] is True
    assert rep["pipeline_version_changed"] is False

def test_regress_flags_beyond_epsilon(tmp_path):
    (tmp_path / "s_ijn.png").write_bytes(b"x")
    man = _man_one({"msssim": 0.99, "lpips": 0.02, "lap_ratio": 2.0, "halo_pct": 0.03, "band_delta": 0.0})
    fake = lambda i, o: {"msssim": 0.90, "lpips": 0.02, "lap_ratio": 2.0, "halo_pct": 0.03, "band_delta": 0.0}
    rep = lw_golden.regress(man, tmp_path, fake, current_pv="pv1")
    assert rep["ok"] is False
    assert rep["pipeline_version_changed"] is True
    assert any("msssim" in r for r in rep["cases"][0]["reasons"])

def test_regress_missing_candidate(tmp_path):
    man = _man_one({"msssim": 0.99, "lpips": 0.02, "lap_ratio": 2.0, "halo_pct": 0.03, "band_delta": 0.0})
    fake = lambda i, o: {}
    rep = lw_golden.regress(man, tmp_path, fake)
    assert rep["ok"] is False
    assert "missing candidate" in rep["cases"][0]["reasons"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_lw_golden.py -q`
Expected: FAIL (`regress`/`EPSILON` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
EPSILON = {"msssim": 0.01, "lpips": 0.02, "lap_ratio_rel": 0.05, "halo_pct": 0.02}

def _compare(base, cur):
    reasons = []
    for k in ("msssim", "lpips", "halo_pct"):
        if k in base and k in cur and abs(float(cur[k]) - float(base[k])) > EPSILON[k]:
            reasons.append(f"{k} {cur[k]:g} vs baseline {base[k]:g} (> {EPSILON[k]})")
    if "lap_ratio" in base and "lap_ratio" in cur and float(base["lap_ratio"]):
        rel = abs(float(cur["lap_ratio"]) - float(base["lap_ratio"])) / float(base["lap_ratio"])
        if rel > EPSILON["lap_ratio_rel"]:
            reasons.append(f"lap_ratio {cur['lap_ratio']:g} vs {base['lap_ratio']:g} ({rel:.1%} > 5%)")
    return reasons

def regress(manifest, candidates_dir, compute_metrics, current_pv=None):
    candidates_dir = Path(candidates_dir)
    pv_changed = bool(current_pv) and current_pv != manifest.get("pipeline_version")
    cases_out = []
    all_ok = True
    for case in manifest["cases"]:
        base_name = os.path.basename(case["baseline"]["path"])
        cand = candidates_dir / base_name
        if not cand.is_file():
            cases_out.append({"slug": case["slug"], "ok": False, "reasons": ["missing candidate " + base_name]})
            all_ok = False
            continue
        cur = compute_metrics(case["input"]["path"], str(cand))
        reasons = _compare(case["metrics"], cur)
        ok = not reasons
        all_ok = all_ok and ok
        cases_out.append({"slug": case["slug"], "ok": ok, "reasons": reasons, "current": cur})
    return {"ok": all_ok, "pipeline_version_changed": pv_changed, "cases": cases_out}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_lw_golden.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/lw_golden.py tests/test_lw_golden.py
git commit -m "feat(golden): regress verb - epsilon compare + pipeline_version guard"
```

---

## Task 4: CLI + real metrics adapter + .gitignore

**Files:**
- Modify: `tools/lw_golden.py` (add `_real_compute_metrics`, `_pinned_from_config`, `main`)
- Modify: `.gitignore`
- Test: `tests/test_lw_golden.py` (CLI arg-parse smoke; real metrics under importorskip)

**Interfaces:**
- Consumes: `freeze`, `regress`, `pipeline_version`.
- Produces: `_real_compute_metrics(input_path, output_path) -> dict` (lazy-imports lw_g1_gate; common-scale self FR msssim/lpips + numpy cheap checks lap_ratio/halo_pct/band_delta); `main(argv=None) -> int` with subcommands `freeze` (reads a candidates JSON of blessed cases) and `regress` (`--candidates-dir`, `--manifest`).

- [ ] **Step 1: Write the failing test**

```python
def test_gitignore_has_golden_rules():
    gi = Path(__file__).resolve().parents[1] / ".gitignore"
    text = gi.read_text(encoding="ascii", errors="replace")
    assert "data/golden/inputs/" in text
    assert "data/golden/baseline/" in text

def test_real_compute_metrics_smoke():
    pytest.importorskip("pyiqa")  # skips in CI and on system python
    # exercised live in .venv-metrics; here we only assert it is importable-shaped
    assert callable(lw_golden._real_compute_metrics)
```

- [ ] **Step 2: Run to verify it fails**

Run: `& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_lw_golden.py -q`
Expected: FAIL (`.gitignore` lacks rules; `_real_compute_metrics` missing).

- [ ] **Step 3: Implement**

Add to `.gitignore` (after the existing `data/.*.png` block):

```
# Golden-set image bytes (privacy - the manifest data/golden/*.json IS tracked,
# the input/baseline image bytes are not; sha-pinned in the manifest).
data/golden/inputs/
data/golden/baseline/
```

Add to `tools/lw_golden.py`:

```python
def _real_compute_metrics(input_path, output_path):
    import numpy as np
    from PIL import Image
    from tools import lw_g1_gate as g1
    src_im = Image.open(input_path).convert("RGB")
    sw, sh = src_im.size
    src_g = np.asarray(src_im.convert("L"), dtype=np.float64)
    out_g = np.asarray(Image.open(output_path).convert("RGB").resize((sw, sh), Image.LANCZOS).convert("L"), dtype=np.float64)
    fr = g1.fr_metrics(str(output_path), str(input_path), str(input_path), names=("ms_ssim", "lpips"))
    return {
        "msssim": fr.get("ms_ssim"), "lpips": fr.get("lpips"),
        "lap_ratio": g1.laplacian_ratio(src_g, out_g),
        "halo_pct": g1.overshoot_halo(src_g, out_g)["halo_pct"],
        "band_delta": g1.banding_delta(src_g, out_g),
    }

def _pinned_from_config(model_path):
    import torch
    return {"model": os.path.basename(model_path), "model_sha256": _sha256_file(model_path),
            "backend": "spandrel", "torch": torch.__version__, "target": [2560, 1440],
            "usm": {"radius": 1.2, "percent": 70, "threshold": 3},
            "thresholds": __import__("tools.lw_g1_gate", fromlist=["DEFAULT_G1_THRESHOLDS"]).DEFAULT_G1_THRESHOLDS}

def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="lw_golden")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze"); f.add_argument("--cases-json", required=True); f.add_argument("--model", required=True); f.add_argument("--out-root", default="data/golden")
    r = sub.add_parser("regress"); r.add_argument("--candidates-dir", required=True); r.add_argument("--manifest", default="data/golden/golden_set.json"); r.add_argument("--model", required=True)
    a = p.parse_args(argv)
    if a.cmd == "freeze":
        cases = json.loads(Path(a.cases_json).read_text(encoding="utf-8"))
        man = freeze(cases, a.out_root, _pinned_from_config(a.model), _real_compute_metrics)
        print(f"froze {len(man['cases'])} cases -> {a.out_root}/golden_set.json pv={man['pipeline_version'][:12]}")
        return 0
    man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    rep = regress(man, a.candidates_dir, _real_compute_metrics, current_pv=pipeline_version(_pinned_from_config(a.model)))
    for c in rep["cases"]:
        print(f"  {c['slug']:<40} {'OK' if c['ok'] else 'FLAG'} {'; '.join(c.get('reasons', []))}")
    print(f"regress: {'PASS' if rep['ok'] else 'REGRESSIONS'} pv_changed={rep['pipeline_version_changed']}")
    return 0 if rep["ok"] else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
```

- [ ] **Step 4: Run to verify it passes + ruff + full suite**

Run: `& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_lw_golden.py -q`
Expected: PASS (8 tests; the pyiqa smoke SKIPS).
Run: `& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m ruff check tools/lw_golden.py tests/test_lw_golden.py`
Expected: All checks passed.
Run: `& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/ -q`
Expected: full suite green (no regression).

- [ ] **Step 5: Commit**

```bash
git add tools/lw_golden.py tests/test_lw_golden.py .gitignore
git commit -m "feat(golden): CLI + real metrics adapter + gitignore golden bytes"
```

---

## Task 5 (LIVE, this session): bless -> freeze the real 10 -> regress self-check

**Files:** none committed except `data/golden/golden_set.json` (the manifest).

This task operates on real data; no unit test. The 10 blessed IJN outputs live in the session scratchpad from QA Session 2 Phase A.

- [ ] **Step 1: Build a contact sheet** of the 10 IJN outputs for the operator bless. Under `.venv-metrics` (PIL), tile the 10 `*_ijn.png` (downscaled thumbs, labeled by slug) into one PNG in the scratchpad. Show it to the operator.

- [ ] **Step 2: Operator bless.** Operator names any case to DROP (bad baseline). Build `cases.json` = the kept cases: `[{"slug","input_path" (the 2.First Pass Done/<slug>/<slug>_firstinitial.*),"baseline_path" (scratchpad <slug>_ijn.png),"defect_axes"}]`. Wait for the operator's keep/drop list before proceeding.

- [ ] **Step 3: Live freeze.** Run under `.venv-metrics`:
`& "C:\LegionWallpaper\.venv-metrics\Scripts\python.exe" tools/lw_golden.py freeze --cases-json <scratch>/cases.json --model tools/models/4x_IllustrationJaNai_V1_DAT2_190k.pth`
Verify: `data/golden/golden_set.json` written (tracked), `data/golden/{inputs,baseline}/` populated (gitignored), N == blessed count, pipeline_version present.

- [ ] **Step 4: Regress self-check.** Produce candidates by re-running first_pass on the golden inputs under `.venv-upscale` into a temp dir (reuse the QA Phase A pattern: `lw_upscale.first_pass(input, tmp/<slug>_ijn.png, backend="spandrel", model_path=...)`), then run `lw_golden.py regress --candidates-dir <tmp> --model tools/models/4x_IllustrationJaNai_V1_DAT2_190k.pth` under `.venv-metrics`. Expected: PASS (deltas within epsilon vs the just-frozen baseline; pv_changed=False). This validates freeze+regress end-to-end and upscale determinism.

- [ ] **Step 5: Commit** the manifest (bytes stay gitignored):

```bash
git add data/golden/golden_set.json
git commit -m "chore(golden): freeze first-pass golden set (N blessed IJN baselines)"
```

---

## Self-Review

- **Spec coverage:** section 1 reframe -> Task 1/2 (frozen-baseline manifest); section 2 artifact + privacy -> Task 2 (copy) + Task 4 (gitignore); section 3 selection (the 10) -> Task 5 Step 2; section 4 bless -> Task 5 Steps 1-2; section 5 harness freeze/regress + epsilon + G3 TODO -> Tasks 2/3/4 (G3 Haiku remains a documented TODO, not implemented - matches spec); section 6 pipeline_version/determinism -> Task 1 + Task 5 Step 4; section 8 test plan -> Tasks 1-4 unit tests + Task 5 live checks. No gaps.
- **Placeholder scan:** none - every code step is complete; the only "deferred" item (G3 Haiku) is an explicit spec-level out-of-scope, not a plan placeholder.
- **Type consistency:** `compute_metrics(input_path, output_path) -> dict` with keys msssim/lpips/lap_ratio/halo_pct/band_delta is used identically in freeze (Task 2), regress (Task 3), and `_real_compute_metrics` (Task 4). `pipeline_version(pinned)` and manifest `cases[].metrics`/`baseline.path` shapes are consistent across freeze and regress.
