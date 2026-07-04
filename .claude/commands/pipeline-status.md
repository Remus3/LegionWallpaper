---
description: Pipeline status board - run lw_pipeline scan + status, show per-stage counts, the needs-attention list (anomalies, needauth queue, manual source-recovery queue), new-originals detection, tooling readiness, and the LW Monitor pointer. Read-only except the pipeline_state.json refresh. Use when the operator asks "status", "where are we", or "pipeline status".
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** status reporting is read-only, so the spec step collapses to grounding - every number in the board comes from a live probe (`tools/lw_pipeline.py scan`/`status`, `ops/runtime/pipeline_state.json`, directory listings), never from memory or a stale doc.
> 2. **New session:** re-probe live state before summarizing; never carry counts forward from a prior session or another agent's report.
> 3. **Act via subagents:** a single read-only probe subagent may gather the board in parallel slices; anything MUTATING that this board surfaces (anomaly fixes, intakes) is spun off to the owning stage command, not done inline here.
> 4. This command inlines freely - it is trivial-read territory (refines R9). See `CLAUDE.md` "Subagent-First Protocol".

Contract references: `docs/research/PIPELINE_STATE_MACHINE.md` (scan/status CLI, anomaly classes, state file 4.2), `docs/research/LW_MONITOR_SPEC.md` (monitor). This command is READ-ONLY on pipeline folders: the only write is lw_pipeline's atomic refresh of `ops/runtime/pipeline_state.json`. It never fixes anomalies itself - it routes them.

### 0. Preflight

1. Run: `C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/lw_pipeline.py status`
   - If `tools/lw_pipeline.py` is missing or errors, report that the pipeline CLI is not built/installed yet and fall back to a plain directory census of `images\` (counts only, clearly labeled "unmanaged census").
2. Read the tail (last ~20 lines) of `PIPELINE_LOG.md` at the project root - the recent-activity strip for the board. Missing log = fresh pipeline; say so.
3. Run `... lw_pipeline.py scan` to refresh `ops/runtime/pipeline_state.json` (tmp+replace; extra fields tolerated by readers). Add `--verify` only when the operator asks for a deep integrity check (it re-hashes the world - slow).

### 1. Stage counts

From `pipeline_state.json` counts: pending_intake, first_scratch, first_done, clean_scratch, clean_done, final_scratch, final_done, last_scratch, end_review, passed, anomalies. Render as a compact one-line-per-stage table with the stage folder names (`0.Originals` ... `9.Image Backup`).

### 2. Needs-attention list

- **Anomalies** (from scan): DUPLICATE_KEY, UNPARSED_FILE, SPLIT_STATE, STALE_DONE, MISSING_INITIAL, HASH_MISMATCH, SCRATCH_RESIDUE, STALE_LOCK, STALE_PART - one line each with slug + suggested action (`scan --fix-resumable` handles the provably-safe ones; the rest name the owning command).
- **Awaiting authorization:** every slug in a `_*needauth` substate, oldest first - these block their stage until the operator runs `approve`/`reject`.
- **Manual source-recovery queue:** slugs whose intake provenance says "manual" (Tier 0-2 exhausted).
- **Human QA queue:** slugs parked for the IOPaint hand-mask route by /cleaning-pass.

### 3. New-originals detection

- List `images\0.Originals`: count eligible files vs ineligible (stability gate reasons per FM-07: partial extensions, size still changing, mtime < 10s). Eligible > 0 -> suggest `/intake`.

### 4. Tooling readiness (install targets, not assumptions)

One line per tool with INSTALLED/MISSING - each MISSING line points at the `docs/RESTORATION_PLAN.md` install checklist entry (these paths are the plan's install targets):

- `.venv-upscale` (torch cu128 + spandrel + IllustrationJaNai) - /first-pass primary
- `C:\Tools\realesrgan\realesrgan-ncnn-vulkan.exe` - /first-pass fallback
- `C:\Tools\lw-clean\venv` (ultralytics + easyocr + simple-lama-inpainting) - /cleaning-pass
- `C:\Tools\iopaint\venv` (iopaint 1.6.0) - /cleaning-pass human QA
- ComfyUI portable cu128 + illustration checkpoint - /final-pass
- metrics venv (pyiqa) - G1/G2 numbers everywhere
- `gallery-dl`, `imagehash`, `API-Key-SauceNAO.txt` - /intake recovery tiers

### 5. Monitor pointer

- LW Monitor serves the live board at `http://127.0.0.1:8901` (launch via the Desktop "LW Monitor" shortcut, which runs `pythonw.exe tools/lw_monitor.py --open`). If the port does not answer, say so and point at the shortcut - do not start daemons from this command unless the operator asks.

### 6. Log/state update + banner

1. This command appends nothing to `PIPELINE_LOG.md` (no transitions happened); confirm `ops/runtime/pipeline_state.json` carries a fresh `generated_ts` from the section 0 scan.
2. Print the closing banner (one ASCII line):

```
LW STATUS | intake=<n> scratch=<s> done=<d> needauth=<q> review=<r> passed=<p> | anomalies=<a> | monitor: http://127.0.0.1:8901 | next: <most-urgent-command>
```
