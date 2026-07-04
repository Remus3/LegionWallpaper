---
description: Stage 5 end review - deep audit of the 5-milestone set in 8.End Review (metrics + Claude-vision 2AFC when configured). PASS finalizes (copy _lastdone to 9.Image Backup, clear the 8.End Review entry, optional operator-gated --deliver); FAIL demotes to 7.Last Scratch with the reason logged. Use when images sit in 8.End Review or the operator says "end review".
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent emits the audit plan (slugs queued, milestone completeness, which checks run, vision-audit budget) BEFORE any verdicts; verify it vs ground truth (`tools/lw_pipeline.py status`, `ops/runtime/pipeline_state.json`, the actual 8.End Review sets on disk) - never scaffold on assumptions.
> 2. **New session:** confirm intent + acceptance criteria with the operator (or the Gemini director), re-probe live pipeline state, THEN act.
> 3. **Act via subagents:** per-slug audit subagents on disjoint slugs (sole merger) + a read-only `verifier` subagent gate before any PASS/FAIL is recorded.
> 4. Trivial single-slug re-audits may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol".

Contract references: `docs/research/PIPELINE_STATE_MACHINE.md` (T7 FINALIZE, T7r demotion, FM-10/FM-12), `docs/research/AUDIT_GATES.md` (G3 vision audit section 4, ladder 5.1, ledger 5.2). This is the deep audit of all five milestones TOGETHER: drift across stages, regression vs `_firstinitial` intent, watermark recurrence.

### 0. Preflight (mandatory, before touching any image)

1. Run: `C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/lw_pipeline.py status`
   - If `tools/lw_pipeline.py` is missing or errors, STOP and report (single-writer rule).
2. Read the tail (last ~20 lines) of `PIPELINE_LOG.md` at the project root - confirm each queued slug's APPROVE_LAST landed clean.
3. Targets: slugs in `images\8.End Review\` not yet finalized (no hash-equal `_lastdone` in `images\9.Image Backup\<slug>\`).
4. Hash-verify each set first: `... lw_pipeline.py verify <slug>` - a HASH_MISMATCH disqualifies the set from review (recover from backup, report).
5. Tooling readiness - INSTALL TARGETS from the `docs/RESTORATION_PLAN.md` install checklist, not assumptions; never fail mid-image:
   - **Metrics venv** (pyiqa). Missing -> OpenCV-only metric subset; the audit still runs but is flagged "metrics-degraded" in the manifest.
   - **Claude vision (G3):** Anthropic API key configured (`API-Key-*.txt` at project root). Missing -> metrics + operator eyeball only; record "vision-audit skipped: no key" - do NOT fabricate rubric scores.

### 1. Deep metric audit (per slug, all five milestones together)

- Cross-stage drift: FR metrics (common scale) between every adjacent milestone pair AND candidate-vs-`_firstinitial`; flag monotonic decay (sharpness ladder, color shift accumulating stage over stage).
- Watermark recurrence: residual-watermark checks + corner/center-bottom template sweep on the FINAL image regardless of cleaning history.
- Format: exactly 2560x1440, PNG, sRGB, 8-bit, metadata scrubbed.
- All numbers -> manifest audit record + the audit ledger (JSONL) per AUDIT_GATES.md 5.2.

### 2. Claude-vision 2AFC audit (when configured)

Per AUDIT_GATES.md section 4 - LMMs are reliable at pairwise comparison, weak at absolute scoring, so:

- Side-by-side 2AFC: full A + full B (candidate vs `_firstinitial`) + native-res crops (eyes, prior watermark bboxes), images before text, labeled "Image 1:/Image 2:", A/B order RANDOMIZED per call and the mapping recorded. Never reveal which is processed.
- Forced-JSON rubric (10 categories, 0-3 each + verdict), temperature 0, model ID + prompt hash pinned to the ledger. Haiku is the workhorse; escalate to a high-res-tier model only for flagged categories. Borderline -> 3-call self-consistency majority + A/B-swap position-bias check.
- Pass rule (auto-computable): no category 0; at most one category 1; eyes_and_irises >= 2; watermark_or_text_residue == 3; candidate must win or tie vs the original.

### 3. Verdict: PASS -> finalize

1. `... lw_pipeline.py finalize <slug> --audit-json <path>` (dry-run first) - copies `_lastdone` to `images\9.Image Backup\<slug>\` (hash-idempotent, never overwrite), snapshots the manifest to backup, logs FINALIZE.
2. After the backup copy hash-verifies, clear the `images\8.End Review\<slug>\` entry (the milestone set's authoritative archive is the backup + manifests; a lingering 8-entry re-queues forever).
3. Optional delivery: `--to-pictures` / `--deliver` is OPERATOR-GATED - `C:\Users\Administrator\Pictures\` is in use and owned by the operator; agents never write there. When the operator invokes it, delivery follows FM-12 (.part + fsync + hash-verify + atomic rename, next free ### computed at rename time, assigned name recorded in manifest + log).

### 4. Verdict: FAIL -> demote

1. `... lw_pipeline.py reject <slug> --stage last --note "<one-line reason + failing check>"` (dry-run first) - T7r: recreate `images\7.Last Scratch\<slug>\` from the End Review set with `_lastdone` renamed to `_lastworking_{max+1}`; the 8.End Review entry is removed only after the scratch set hash-verifies.
2. The rejection reason MUST name the failing gate/category - it is the retry hint for the next /last-pass.

Any helper script authored here that spawns subprocesses MUST pass `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` (Legion focus-steal rule).

### 5. Log/state update + banner

1. Confirm `PIPELINE_LOG.md` gained FINALIZE (or REJECT) lines per slug and `ops/runtime/pipeline_state.json` is fresh (re-run `... lw_pipeline.py scan` if in doubt); confirm the audit ledger rows landed.
2. Print the closing banner (one ASCII line):

```
LW END REVIEW | reviewed=<n> pass=<p> fail=<f> vision-audited=<v> | delivered=<d> demoted=<f> | next: /pipeline-status
```
