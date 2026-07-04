---
description: Stage 0 intake - scan images/0.Originals for new files (stability gate), run lw_pipeline intake per image (dry-run first, then execute), kick off the source-recovery waterfall (Tier 0 local pHash, Tier 1 DeviantArt token decode + gallery-dl, Tier 2 SauceNAO, else manual queue), and record provenance in each image manifest. Use when new wallpaper sources have been dropped and the operator says "intake" or "start intake".
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent emits the batch plan (which files, which slugs, which recovery tier per file) BEFORE any mutation; verify it vs ground truth (`tools/lw_pipeline.py status`, `ops/runtime/pipeline_state.json`, a directory listing of `images\0.Originals`) - never scaffold on assumptions.
> 2. **New session:** confirm intent + acceptance criteria with the operator (or the Gemini director), re-probe live pipeline state, THEN act.
> 3. **Act via subagents:** per-image or per-tier worker subagents on disjoint slugs (sole merger) + a read-only `verifier` subagent gate before any "done" claim.
> 4. Trivial single-file intakes may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol".

Contract references: `docs/research/PIPELINE_STATE_MACHINE.md` (T1 INTAKE, slugging 2.5, eligibility gate FM-07), `docs/research/SOURCE_RECOVERY.md` (recovery tiers). All mutations go through `tools/lw_pipeline.py` (single-writer rule) - this command NEVER renames, copies, or deletes pipeline files by hand.

### 0. Preflight (mandatory, before touching any image)

1. Run: `C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/lw_pipeline.py status`
   - If `tools/lw_pipeline.py` is missing or errors, STOP and report - the CLI is the only sanctioned writer.
2. Read the tail (last ~20 lines) of `PIPELINE_LOG.md` at the project root for recent transitions, failures, and half-done intakes. Missing log = fresh pipeline; note it and continue.
3. Run `... lw_pipeline.py scan` and check `ops/runtime/pipeline_state.json` for anomalies (STALE_LOCK, half-done T1 recovery states). Resolve or report anomalies BEFORE new intakes.
4. Tooling readiness (report, never fail mid-image). Each item below is an INSTALL TARGET from the `docs/RESTORATION_PLAN.md` install checklist, not an assumption - if absent, say exactly what to install and degrade to the next tier:
   - `imagehash` importable on Python 3.14 (Tier 0 pHash). Missing -> skip Tier 0, note it.
   - `gallery-dl --version` succeeds (Tier 1 fetch). Missing -> Tier 1 resolves URLs only, no fetch.
   - `API-Key-SauceNAO.txt` present at project root (Tier 2). Missing -> Tier 2 disabled, queue manual.

### 1. Scan 0.Originals with the stability gate (FM-07)

- List `images\0.Originals` (files only, no subfolders expected).
- Exclude ineligible files and report each with a reason: partial extensions (`.crdownload`, `.part`, `.tmp`, `.download`), open write handles, size changed between two probes ~2s apart, or mtime younger than 10s (browser may still be writing).
- Zero eligible files -> skip to section 4 with `new=0`.

### 2. Intake each eligible file (dry-run first)

Per image, in order:

1. `... lw_pipeline.py intake <file> --dry-run` - show the exact op plan (slug chosen per grammar 2.5, backup copy to `images\9.Image Backup\<slug>\` with verbatim name, scratch copy to `images\1.First Pass Scratch\<slug>\<slug>_firstinitial.<ext>`, delete from 0.Originals last).
2. Sanity-check the plan: slug is a lowercase hyphen ID (underscore is reserved for phase tokens), no collision surprises, duplicate re-intake of a hash-equal file is refused.
3. Execute: `... lw_pipeline.py intake <file>`. On failure, the file stays in 0.Originals (T1 recovery is idempotent) - report and continue with the next file.

`--all` batch mode is acceptable once the per-file dry-run plans have been reviewed.

### 3. Source-recovery waterfall kickoff (per intaken image)

Goal: find the best full-resolution original BEFORE first-pass upscaling. Work the tiers cheapest-first; stop at the first confident hit; record the outcome either way.

- **Tier 0 - local pHash match (free, offline):** compute 64-bit pHash + dHash of `<slug>_firstinitial` and compare against `images\reference_pictures` (the non-pipeline reference corpus). Accept Hamming <= 8 on both hashes; 9-14 = flag for operator review; > 14 = no match. A hit means a known better/cleaner source already exists locally.
- **Tier 1 - DeviantArt token decode (deterministic, no search quota):** if the original filename carries a DeviantArt token (`<title>_by_<artist>_<token>-fullview.jpg` or `<token>-<uuid>.jpg` shapes), strip the leading `d`, base36-decode the rest, and resolve `https://www.deviantart.com/deviation/<id>`. If gallery-dl is installed, fetch the fullview/original into a staging temp dir (NOT into pipeline folders directly; re-enter via 0.Originals + intake, or record for the first-pass best-source step). Mind the 2026 download clamp: reserve `"original": true` pulls for images that truly need them.
- **Tier 2 - SauceNAO (quota-bound queue, key required):** POST the image with `output_type=2&db=999`. Free tier is ~4 searches/30s and ~100/day - this is an overnight QUEUE, never a loop. Accept similarity >= 85; 60-85 = operator review; < 60 = discard.
- **Else - manual queue:** append the slug + reason to the needs-attention list (manifest note) for manual Lens/Yandex browsing by the operator.

Any helper script authored here that spawns subprocesses MUST pass `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` (Legion focus-steal rule) and NEVER writes into pipeline stage folders by hand.

### 4. Record provenance

For every image: record in its `manifest.json` (via the lw_pipeline manifest path, tmp+replace) the recovery tier attempted, `source_url` (or null), match similarity/Hamming distance, and fetch outcome. Provenance is the substrate for the shareable per-image chain - no silent recoveries.

### 5. Log/state update + banner

1. Confirm `PIPELINE_LOG.md` gained one pipe-delimited INTAKE line per image (format per PIPELINE_STATE_MACHINE.md section 4.1) and `ops/runtime/pipeline_state.json` was rewritten atomically (re-run `... lw_pipeline.py scan` if in doubt).
2. Print the closing banner (one ASCII line):

```
LW INTAKE | new=<n> intaken=<k> skipped=<s> | src: t0=<a> t1=<b> t2=<c> manual=<d> | anomalies=<x> | next: /first-pass
```
