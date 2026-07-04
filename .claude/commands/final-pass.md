---
description: Stage 3 final pass - masked anime-face/eye repair (ComfyUI headless with an illustration checkpoint; NEVER CodeFormer/GFPGAN on illustrations), debanding, and exact 2560x1440 conformance, gated by G1+G2 style checks. Use when images sit in 5.Final Scratch or the operator says "final pass".
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent emits the per-image plan (detected faces/eyes, proposed repair masks, deband regions, resize op) BEFORE any pixel changes; verify it vs ground truth (`tools/lw_pipeline.py status`, `ops/runtime/pipeline_state.json`, actual detection crops) - never scaffold on assumptions.
> 2. **New session:** confirm intent + acceptance criteria with the operator (or the Gemini director), re-probe live pipeline state, THEN act.
> 3. **Act via subagents:** per-image worker subagents on disjoint slugs (sole merger) + a read-only `verifier` subagent gate before any "done" claim.
> 4. Trivial single-image reruns may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol".

Contract references: `docs/research/PIPELINE_STATE_MACHINE.md` (stage semantics 2.8), `docs/research/UPSCALE_TOOLCHAIN.md` (face-repair doctrine), `docs/research/CLEANING_INPAINT.md` (SD inpaint tier), `docs/research/AUDIT_GATES.md` (G1/G2 + 3.5 eye checks). Stage doctrine: polish only - eyes/irises/skin, banding/color, exact-dimension conformance. Diffusion inpainting CHANGES content, so this stage is always human-gated.

**HARD RULE: NEVER run CodeFormer or GFPGAN on illustrations.** They are photo-trained face restorers and harm illustrated faces (realistic noses pasted onto anime faces, horror-adjacent distortion). The correct approach is anime-trained detection + masked diffusion inpainting.

### 0. Preflight (mandatory, before touching any image)

1. Run: `C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/lw_pipeline.py status`
   - If `tools/lw_pipeline.py` is missing or errors, STOP and report (single-writer rule).
2. Read the tail (last ~20 lines) of `PIPELINE_LOG.md` at the project root - prior REJECT notes on target slugs are the retry hints.
3. Targets: slugs in `images\5.Final Scratch\` (EDITING substate). Images in `images\4.Cleaning Done\` enter via `... lw_pipeline.py start-stage <slug>` (dry-run first) which creates `_finalinitial`.
4. Tooling readiness - each item is an INSTALL TARGET from the `docs/RESTORATION_PLAN.md` install checklist, not an assumption; report exact install steps when absent, never fail mid-image:
   - **Face/eye detection:** anime-face-detector (mmdet/mmpose, 28 landmarks) in its venv, else the zero-dep fallback `lbpcascade_animeface` (OpenCV LBP cascade XML) with generous crops. Neither -> operator marks face regions by hand; log the install target.
   - **ComfyUI headless:** portable cu128 build (e.g. juspky/ComfyUI-Windows-Portable-cu128) reachable via the HTTP `/prompt` API on localhost, with an illustration inpaint checkpoint (Illustrious/NoobAI family). Missing -> SKIP face/eye repair entirely (do the deband + conformance steps only) and report the install target - do NOT substitute a photo face restorer.
   - **Metrics venv** (G1/G2 numbers) per RESTORATION_PLAN.md. Missing -> OpenCV-only checks + operator review flag.

### 1. Masked face/eye repair (per slug, human-gated)

1. Detect anime faces; derive eye crops (landmarks if available, else upper-central face heuristic). Run the cheap eye checks (iris mirror-similarity, specular-highlight count 1-4, edge coherence) - log-only heuristics that PRIORITIZE which faces need repair.
2. For each region needing repair: build a tight mask (face or eye bbox, dilated ~8 px). **Never inpaint without a mask; never run a full-image diffusion pass.**
3. Inpaint the masked region via ComfyUI headless (illustration checkpoint, inpaint workflow, fixed seed recorded in params).
4. G2-style verification per masked edit: OUTSIDE the dilated mask SSIM >= 0.995 + mean abs diff <= 1/255 (hard); INSIDE the mask change-happened + the eye checks re-run (the repaired eye must not score worse than before).
5. Register each accepted repair: `... lw_pipeline.py save-working <slug> --from <path> --tool comfyui --params <json-with-checkpoint-seed-mask>`.

### 2. Debanding

- Detect banding in smooth regions (band edge density per AUDIT_GATES.md 3.3). Apply targeted debanding to affected regions only; verify DELTA mode: output band edge density <= input, and the fix must not blur detail elsewhere (outside-region identity like any masked edit).

### 3. Conformance to exactly 2560x1440

- Final geometry: exactly 2560x1440. If the working image is larger, ONE Lanczos downscale (this is the sanctioned second resample of the whole pipeline; there is no third). Never upscale here - if the image is smaller than 2560x1440, the first pass failed: reject back with a note instead of stretching.
- Format checks: PNG, sRGB, 8-bit.

### 4. G1 + G2 style gates

- G1 FR drift vs `_finalinitial` at common scale: MS-SSIM/LPIPS within the flag bands, laplacian ratio sane, halo detector clean, banding delta <= 0.
- G2 masked-edit identity: every masked repair already verified in-line (section 1.4); re-assert the composite (all-edits-combined outside-union-of-masks identity).
- Log every metric to the manifest. Hard fail -> do not submit; loop or queue for the operator.

Any helper script authored here that spawns subprocesses MUST pass `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` (Legion focus-steal rule).

### 5. Submit for authorization

- `... lw_pipeline.py submit <slug>` -> `_finalneedauth.png`. Operator approves (-> `_finaldone` + move to `images\6.Final Done\`) or rejects with a note. This command never self-approves - diffusion output is always human-gated.

### 6. Log/state update + banner

1. Confirm `PIPELINE_LOG.md` gained the transition lines and `ops/runtime/pipeline_state.json` is fresh (re-run `... lw_pipeline.py scan` if in doubt).
2. Print the closing banner (one ASCII line):

```
LW FINAL PASS | processed=<n> faces-repaired=<r> debanded=<d> conformed=<c> | submitted=<k> gate-fail=<f> | next: approve/reject via lw_pipeline
```
