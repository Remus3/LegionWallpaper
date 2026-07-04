# GOLDEN_SET - First-Pass Golden-Set Regression Protocol (v1)

Design spec. Date: 2026-07-04 (QA Session 2 follow-on). Operationalizes
`docs/RESTORATION_PLAN.md` section 4 and `docs/research/AUDIT_GATES.md` 5.4 for
the CURRENT reality: no finished ground-truth exists (operator ruling
2026-07-04 - every corpus image still needs work; the `reference_pictures/
*_cleanup.png` files are "original-not-found" markers, not approved outputs),
and only the first-pass stage is built. See memory `project-no-finished-ground-truth`.

## 1. Purpose and the reframe

The golden set is the cheap self-audit that catches whether a pipeline change
regresses. The plan assumes frozen (input, APPROVED-output) pairs. No approved
finals exist, so v1 uses a FROZEN-BASELINE reference of record instead:

- The reference is the CURRENT blessed pipeline's own first-pass output, not
  human perfection. A one-time operator "bless" (thumbs-up, or drop a bad case)
  turns the current IllustrationJaNai first-pass outputs into the
  baseline-of-record.
- Future first-pass changes (V3 DAT2, USM/threshold tweaks) regress against that
  frozen baseline: outputs must not drift beyond epsilon, and (once G3 exists)
  must win-or-tie a side-by-side vs the baseline. This is drift + no-regression
  detection with a quality floor, which is exactly what a first-pass change
  needs guarding, and it needs no ground-truth.

Scope: FIRST PASS ONLY. Clean/final/last stages are TBD; each golden case grows
a per-stage baseline as those stages come online (not built now - YAGNI).

## 2. The artifact

`data/golden/golden_set.json` (COMMITTED). One entry per case:

```
{
  "schema": 1,
  "pipeline_version": "<hash of the pinned tuple>",
  "created_ts": "...",
  "cases": [
    {
      "slug": "fiora2",
      "input":    {"path": "data/golden/inputs/fiora2_firstinitial.jpg",  "sha256": "..."},
      "baseline": {"path": "data/golden/baseline/fiora2_ijn.png",         "sha256": "..."},
      "metrics":  {"msssim":..., "lpips":..., "lap_ratio":..., "halo_pct":..., "band_delta":...},
      "verdict":  "PASS|FLAG",
      "blessed":  true,
      "defect_axes": ["soft-source", "high-halo", ...]
    }, ...
  ]
}
```

- `pipeline_version` = sha256 of the pinned tuple: upscaler model basename+sha256,
  backend, torch version, target dims, USM (radius/percent/threshold), and the
  `DEFAULT_G1_THRESHOLDS` config. A model/threshold change changes this hash, so
  regressions across pipeline versions are always attributable.
- PRIVACY BOUNDARY (RESTORATION_PLAN section 10): the JSON manifest + metrics +
  code are committed and shareable; the IMAGE BYTES are NEVER committed. Inputs
  and baseline outputs are copied to `data/golden/{inputs,baseline}/` (a
  gitignored durable location - the frozen IJN outputs currently live only in
  session scratch and must be copied somewhere durable), and pinned by sha256 in
  the manifest. `data/golden/*.json` stays tracked; `data/golden/inputs/**` and
  `data/golden/baseline/**` are gitignored.

## 3. Selection (N = 10)

Ship the 10 already-processed first-pass images (the QA Session 2 set: fiora2 +
9 Found-originals). Rationale: they already have IJN outputs, G1 metrics, and
manifests, and their metrics span the first-pass-relevant failure axes -
source-softness (lap_ratio 1.26-3.22, a 2.5x spread), sharpening/halo
(halo_pct 0.018-0.075, 4x), perceptual distance (lpips 0.008-0.080, 10x).

KNOWN GAP (documented, not silently ignored): whether any of the 10 is a
banding-heavy-glow or heavy-JPEG-artifact case is unconfirmed from metrics
alone. v1 ships the 10; targeted defect-class cases can be added later from the
intake backlog without changing the protocol (append a case, re-freeze that
entry's pipeline_version).

## 4. The bless step (one-time, operator)

Before freezing, the operator does a quick visual pass over the 10 baseline
outputs: keep (thumbs-up) or drop ("this one is actually bad - not a valid
baseline"). Dropped cases leave the set (N may end < 10). This makes the
baseline blessed without requiring perfection. Presented as a contact sheet /
montage for a fast pass. Blessing is the FIRST implementation step (operator
chose bless-now timing).

## 5. The regression harness

`tools/lw_golden.py` with two verbs:

- `freeze` - (re)build `golden_set.json` from the current pipeline: copy inputs +
  baseline outputs to the durable gitignored location, compute metrics + the
  pipeline_version hash, mark blessed cases. Run once now, and again only on a
  deliberate re-baseline.
- `regress` - for each golden case, re-run first_pass on the input with the
  CURRENT pipeline config, recompute G1 metrics, and compare to the frozen
  baseline metrics within epsilon (RESTORATION_PLAN section 4):
  MS-SSIM within 0.01, LPIPS within 0.02, lap_ratio within 5 percent, halo_pct
  within 0.02 (seed). Any case exceeding epsilon FLAGS the change; report is a
  per-case delta table + overall pass/fail + exit code (0 ok, 1 regressions).
  If the current pipeline_version differs from the frozen one, the report says
  so (an intended re-baseline vs an accidental drift are distinguished).

DEFERRED (documented TODO, gated on G3): the Haiku side-by-side new-vs-baseline
"must win or tie" check (AUDIT_GATES 5.4 / 3.3). G3 vision audit is not built
yet; the metric-delta check is the entire harness for v1. When G3 lands,
`regress` gains the batched Haiku pass.

## 6. Determinism and shareability

- The upscale backend must be deterministic for `regress` to be meaningful:
  spandrel eager inference on a pinned model is deterministic; record the model
  sha256. (ncnn backend determinism is a separate check - the golden baseline is
  spandrel/IJN.)
- The committed manifest + `lw_golden.py` + `lw_g1_gate.py` make the protocol
  reproducible and shareable (anyone can run `regress` on their own corpus and
  get comparable, explainable verdicts) - the process is the deliverable, the
  images stay private.

## 7. Out of scope (v1)

Clean/final/last per-stage baselines; the G3 Haiku check; automatic defect-class
curation; source-adaptive USM. Each is a named extension point, not a v1 gap.

## 8. Test plan

- `tools/lw_golden.py` unit tests (pure stdlib + tmp_path): freeze writes a
  well-formed manifest with sha-pinned entries and a stable pipeline_version;
  regress computes deltas and flags a case whose metrics are perturbed beyond
  epsilon; regress passes a case whose metrics are within epsilon; pipeline_version
  mismatch is reported. Heavy upscale/pyiqa paths use importorskip (CI-safe, per
  the QA Session 2 pattern).
- One live `freeze` on the real 10 (in `.venv-upscale`/`.venv-metrics`) after
  the bless, then one `regress` self-check (must pass with zero deltas against
  the just-frozen baseline).
