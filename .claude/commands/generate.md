---
description: lw-gen generator sidecar entry - generate League-champion splash-art-style wallpapers from a brief (subject + style + count) with free local SDXL on the RTX 5070, subject-matter CLIP QA gate FIRST, then promote QA-passed candidates as loose files into images/0.Originals. HARD-GATED off when RC/League/vision is live; refuses gracefully if .venv-gen/model are not provisioned. Promotion STOPS at 0.Originals - the operator runs intake --all. Use when the operator says "generate", "gen a wallpaper", or names a champion + style to synthesize.
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent emits the per-batch plan (subject, style, resolution, QA thresholds, regen budget) BEFORE any generation; verify it vs ground truth (`tools/lw_pipeline.py status`, `docs/GENERATOR_SIDECAR_PLAN.md`, the actual brief JSON, `tools/lw_gen_config.json`) - never scaffold on assumptions.
> 2. **New session:** confirm intent + acceptance criteria with the operator (or the Gemini director), re-probe live pipeline + GPU state, THEN act.
> 3. **Act via subagents:** per-batch worker subagents on disjoint batch dirs (sole merger) + a read-only `verifier` subagent gate before any "done" claim.
> 4. Trivial single-brief reruns may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol".

This is a THIN dispatcher for the lw-gen sidecar. The durable spec is
`docs/GENERATOR_SIDECAR_PLAN.md` (OPERATOR DECISIONS section 9 are LOCKED); model
provenance/licensing + the operator-run Phase-0 setup live in `docs/GEN_MODELS.md`.
Graceful degrade: if any step is unclear or a tool is missing, STOP and point at
`docs/RESTORATION_PLAN.md` + `docs/GENERATOR_SIDECAR_PLAN.md` rather than improvising.
Doctrine: the sidecar is a PRODUCER of stage-0 inputs only; it does NOT add or modify
any numbered stage, and the human 8.End Review stays the final arbiter.

### 0. Preflight (mandatory, before any generation)

1. Run: `C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/lw_pipeline.py status`
   - If `tools/lw_pipeline.py` is missing or errors, STOP and report (single-writer rule).
2. Read the tail (last ~20 lines) of `PIPELINE_LOG.md` at the project root - confirm no
   in-flight intake churn on 0.Originals before you drop new loose files.
3. RC-LIVE HARD GATE (operator decision 3, LOCKED - auto-refuse). lw_gen_run enforces
   this itself before importing torch, but confirm the intent here: if
   `ops/runtime/rc_live.flag` exists OR any of `LeagueClient.exe` / `LeagueClientUx.exe` /
   `League of Legends.exe` / `RiotClientServices.exe` is running, the generator REFUSES
   (VRAM contention on the shared 12GB card). Do not `--force` past this without an
   explicit operator instruction.
4. Phase-0 readiness (refuse gracefully if not provisioned): the generator needs
   `.venv-gen` (torch/diffusers) AND a downloaded painterly SDXL checkpoint in
   `tools/models/` AND `open-clip-torch` in `.venv-metrics`. NONE are downloaded yet as of
   2026-07-10. If they are absent, lw_gen_run prints a friendly "generator not provisioned
   yet - run the Phase-0 setup (see docs/GEN_MODELS.md)" message and exits nonzero. Do NOT
   attempt to auto-download weights - Phase-0 is operator-run and permission-gated.

### 1. Resolve the brief (inline or file)

- Inline (quick): a subject + style + count. Style defaults to `splash`; count defaults
  to 4; aspect is `16:9` ONLY at MVP (any other aspect is refused - ultrawide is a
  deferred multi-target refactor).
- Brief file (repeatable, git-diffable): `briefs/<champion>.json` supplies defaults;
  explicit flags override the brief. Example: `briefs/ambessa.json`.
- Thresholds (`qa_subject_floor`, `qa_margin_floor`, ...) come from the brief, then
  `tools/lw_gen_config.json` `qa{}`. The operator never tunes a sampler per wallpaper.

### 2. Run the generator (chains QA + promote automatically)

```
C:\LegionWallpaper\.venv-gen\Scripts\python.exe tools\lw_gen_run.py --subject "<Champion>" --style splash --n 4
# or, from a brief:
C:\LegionWallpaper\.venv-gen\Scripts\python.exe tools\lw_gen_run.py --brief briefs\<champion>.json
```

- lw_gen_run generates N candidates into `images/_gen_scratch/<batch-id>/` (gitignored,
  pipeline-invisible), then shells `lw_gen_qa.py` (.venv-metrics: CLIP Stage-A subject
  gate FIRST, Stage-B quality second) and `lw_gen_promote.py` (stdlib) unless `--no-chain`.
- Any helper subprocess passes `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)`
  (Legion focus-steal rule).
- Default `--max-regen-rounds 1` means NO auto-regen; regen is opt-in.

### 3. Promotion result + intake handoff (promotion STOPS at 0.Originals)

- Promote writes each QA-passed, slugified, size-asserted (`< 2560x1440`) PNG as a LOOSE
  file into `images/0.Originals/` with a `<slug>.slice.json` metrics sidecar, and updates
  `gen_manifest.json` `promote{}`. It does NOT shell `intake` or `annotate` inline
  (cmd_intake would SKIP a fresh file as "modified too recently"; the post-intake slug is
  unpredictable via `unique_slug` suffixing; annotate needs the EXACT final slug).
- Zero PASS: the best near-miss is copied to `<batch-dir>/review/` (human eyeball, never
  auto-deleted) and recorded in `promote.review`.
- Operator handoff (the exact next commands lw_gen_run prints):
  1. `C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/lw_pipeline.py intake --all`
  2. Then annotate the RECOVERED slug (from intake stdout `intake <file> -> <slug>`, never
     reconstructed): `... lw_pipeline.py annotate <recovered-slug> --source-url gen://lw-gen/<batch-id> --tool lw-gen --metrics @<slug>.slice.json`
- From intake onward a generated image rides the EXACT existing chain (1.First Pass ->
  ... -> 8.End Review) with NO stage-code change; the human 8.End Review is the only
  manual gate. Generated images are personal-use only (gen:// provenance), never uploaded
  to the recovery corpus.

### 4. Log/state update + banner

1. Confirm `images/_gen_scratch/<batch-id>/gen_manifest.json` records per-candidate scores
   + the promote decisions, and (after a manual `intake --all`) that
   `... lw_pipeline.py scan` reports ZERO UNPARSED_FILE anomalies.
2. Print the closing banner (one ASCII line):

```
LW GENERATE | subject=<name> style=<splash|portrait|landscape-ambient> gen=<n> pass=<k> promoted=<p> review=<r> | rc-live-gate=<ok|refused> | next: lw_pipeline intake --all
```
