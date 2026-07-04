---
description: Stage 4 last pass - fresh-eyes regression against ALL prior milestones (_firstinitial through _finalinitial), full gate-ladder re-run, and the format/dimension audit. No new editing beyond reverts. Use when images sit in 7.Last Scratch or the operator says "last pass".
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent emits the regression plan (which milestones exist per slug, which comparisons run) BEFORE any verdicts; verify it vs ground truth (`tools/lw_pipeline.py status`, `ops/runtime/pipeline_state.json`, the actual milestone files on disk) - never scaffold on assumptions.
> 2. **New session:** confirm intent + acceptance criteria with the operator (or the Gemini director), re-probe live pipeline state, THEN act.
> 3. **Act via subagents:** per-image regression subagents on disjoint slugs (sole merger) + a read-only `verifier` subagent gate before any "done" claim.
> 4. Trivial single-comparison reruns may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol".

Contract references: `docs/research/PIPELINE_STATE_MACHINE.md` (stage semantics 2.8: fresh-eyes regression, no new editing beyond reverts), `docs/research/AUDIT_GATES.md` (gate ladder 5.1, milestone regression 5.4). This stage is an AUDIT with revert authority, not an editing stage - if something regressed, revert to the milestone that had it right; do not craft new fixes here.

### 0. Preflight (mandatory, before touching any image)

1. Run: `C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/lw_pipeline.py status`
   - If `tools/lw_pipeline.py` is missing or errors, STOP and report (single-writer rule).
2. Read the tail (last ~20 lines) of `PIPELINE_LOG.md` at the project root - the slug's full transition history is the audit context.
3. Targets: slugs in `images\7.Last Scratch\` (EDITING substate). Images in `images\6.Final Done\` enter via `... lw_pipeline.py start-stage <slug>` (dry-run first) which creates `_lastinitial`.
4. Tooling readiness - INSTALL TARGETS from the `docs/RESTORATION_PLAN.md` install checklist, not assumptions; never fail mid-image:
   - **Metrics venv** (pyiqa: MS-SSIM/LPIPS/DISTS + NR deltas). Missing -> OpenCV-only subset (sharpness/halo/banding/format) + mandatory operator eyeball pass; say exactly what to install.
   - **Vision audit (optional):** Claude API key configured. Missing -> metrics-only regression; note that G3 runs at /end-review.

### 1. Milestone inventory (per slug)

- The scratch folder carries the growing milestone set. Enumerate and hash-verify (`... lw_pipeline.py verify <slug>`) ALL milestones: `_firstinitial`, `_cleaninitial`, `_finalinitial`, `_lastinitial` (plus the current working file if any). A missing milestone = MISSING_INITIAL anomaly - report, do not proceed on a partial set.

### 2. Fresh-eyes regression vs ALL milestones

Compare the candidate (latest working, else `_lastinitial`) against EVERY prior milestone, not just the immediate parent - cross-stage drift hides in pairwise-only comparisons:

- vs `_firstinitial` (the intent anchor): composition intact, color fidelity, no content drift beyond the intended cleanups. FR metrics at common scale (downscale candidate to source resolution; never upscale the reference).
- vs `_cleaninitial`: watermark regions STILL clean (re-run the residual-watermark checks + corner template sweep on the candidate - watermark recurrence is a known End Review failure class).
- vs `_finalinitial`: face/eye repairs still present and not degraded (re-run the cheap eye checks; compare crops).
- Sharpness ladder: laplacian variance must not have decayed across the chain (softness creeping back in = regression).

Any regression found -> REVERT to the milestone that had it right (via `... lw_pipeline.py save-working <slug> --from <milestone-file> --tool revert --params <json-naming-source-milestone>`), and log the reason. No new creative edits in this stage.

### 3. Full gate ladder re-run

- G0 sanity, G1 FR/sharpness/halo/banding, G2 residual-watermark + outside-mask spot checks - the full deterministic ladder per AUDIT_GATES.md 5.1, results to the manifest. Any hard fail -> revert or reject back to the owning stage with the metric report as the note (`... lw_pipeline.py reject <slug> --note ...` after submit, operator-driven).

### 4. Format/dimension audit

- Exactly 2560x1440. PNG, sRGB, 8-bit, no alpha surprises, metadata scrubbed. Extension/format twins (jpg+png of the same milestone) = DUPLICATE_KEY anomaly - report.
- Any format miss is a mechanical fix (re-encode losslessly, dimensions must already be right from /final-pass); register via save-working.

Any helper script authored here that spawns subprocesses MUST pass `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` (Legion focus-steal rule).

### 5. Submit for authorization

- All green: `... lw_pipeline.py submit <slug>` -> `_lastneedauth.png`. Operator approve (`approve <slug>`) executes T6: `_lastdone` + the full 5-milestone set moves to `images\8.End Review\<slug>\`. This command never self-approves.

### 6. Log/state update + banner

1. Confirm `PIPELINE_LOG.md` gained the transition lines and `ops/runtime/pipeline_state.json` is fresh (re-run `... lw_pipeline.py scan` if in doubt).
2. Print the closing banner (one ASCII line):

```
LW LAST PASS | audited=<n> reverts=<r> format-fixes=<x> | submitted=<k> regressions=<f> | next: approve via lw_pipeline, then /end-review
```
