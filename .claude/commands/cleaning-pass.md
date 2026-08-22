---
description: Stage 2 cleaning pass - watermark/artifact removal via the detect -> gate -> mask -> LaMa inpaint -> verify loop with a hard outside-mask identity assertion; gate rejects fall back to the human QA queue (IOPaint web UI). NEVER inpaint without a mask. Use when images sit in 3.Cleaning Scratch or the operator says "cleaning pass".
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent emits the per-image plan (detections found, proposed masks, inpaint engine) BEFORE any pixel changes; verify it vs ground truth (`tools/lw_pipeline.py status`, `ops/runtime/pipeline_state.json`, the actual detection overlays) - never scaffold on assumptions.
> 2. **New session:** confirm intent + acceptance criteria with the operator (or the Gemini director), re-probe live pipeline state, THEN act.
> 3. **Act via subagents:** per-image worker subagents on disjoint slugs (sole merger) + a read-only `verifier` subagent gate before any "done" claim.
> 4. Trivial single-mask reruns may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol".

Contract references: `docs/research/CLEANING_INPAINT.md` (stack + install), `docs/research/AUDIT_GATES.md` (G2 gate, 1.3 + 3.4), `docs/research/PIPELINE_STATE_MACHINE.md` (T2/T3/T4). Stage doctrine: SCALPEL, not sledgehammer - masked inpainting only, no full-image regeneration, ever. **NEVER inpaint without a mask.**

### 0. Preflight (mandatory, before touching any image)

1. Run: `C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/lw_pipeline.py status`
   - If `tools/lw_pipeline.py` is missing or errors, STOP and report (single-writer rule).
2. Read the tail (last ~20 lines) of `PIPELINE_LOG.md` at the project root - prior REJECT notes on target slugs are the retry hints.
3. Targets: slugs in `images\3.Cleaning Scratch\` (EDITING substate). Images still in `images\2.First Pass Done\` enter via `... lw_pipeline.py start-stage <slug>` (dry-run first) which creates `_cleaninitial`.
4. Tooling readiness - each item is an INSTALL TARGET from the `docs/RESTORATION_PLAN.md` install checklist, not an assumption; report exact install steps when absent, never fail mid-image:
   - **Detection + inpaint venv:** `C:\Tools\lw-clean\venv` (torch cu128 + ultralytics + easyocr + simple-lama-inpainting + opencv-python). Missing -> detection degrades to the cheap high-pass corner/edge pre-filter + operator eyeballing; inpainting is unavailable -> queue images for the human QA route instead.
   - **Watermark detector weights:** anti-watermark YOLO weights (e.g. joycaption-watermark-detection yolo11x) downloaded per RESTORATION_PLAN.md. Missing -> OCR-only detection (EasyOCR) + template sweep.
   - **Human QA fallback:** IOPaint 1.6.0 under `%LOCALAPPDATA%\Python\pythoncore-3.11-64\python.exe` (verified live 2026-08-22). The old `C:\Tools\iopaint\venv` path was NEVER created - LEDGER 30 recorded that in 2026-07-16 and the string outlived the correction; do not restore it. Missing -> note the install target; rejects queue as manifest notes until it exists.

### 1. DETECT (per slug, on the current working image)

- Run the watermark detector (YOLO, imgsz=1024) + EasyOCR text detection over the FULL image - never assume fixed watermark positions (the corpus's confirmed class is baked-in artist-credit strips, e.g. bottom-edge text, mixed latin + CJK).
- Corner/center-bottom template sweep against the known wallpaper-site watermark library.
- Cheap high-pass pre-filter (deviation from 9px median) as a hint layer only - it fires on fine art detail; it is a pre-filter, not a decider.
- No detections -> record "clean scan" in the manifest and skip to section 5 (an image can legitimately need zero cleaning).

### 2. GATE the detections

- Confident text/logo detections (detector confidence >= 0.5 AND OCR corroboration or template hit) -> proceed to mask.
- Low-confidence or art-vs-watermark ambiguity -> HUMAN QA QUEUE: do not guess. Queue the image for the operator with detection overlays.

### 3. MASK -> INPAINT -> VERIFY loop (per detection region)

1. **Mask:** build a white-on-black PNG mask from the detection boxes, dilated ~8 px. The mask is saved next to the working file (scratch side-files are protected from GC by FM-13).
2. **Inpaint:** LaMa via simple-lama-inpainting (primary batch engine) - masked region ONLY. LaMa does not hallucinate new content, which keeps the audit story simple. Large reconstructions (missing content) are NOT this stage - defer to /final-pass masked repair.
3. **Verify (G2 gate, hard):**
   - OUTSIDE the dilated mask: SSIM >= 0.995 AND mean abs diff <= 1/255 - the identity assertion. Any violation = pipeline bug (full-image pass slipped through) - HARD FAIL, discard the output.
   - INSIDE the mask: change-happened check (SSIM vs original patch <= 0.90, else the inpaint no-opped - fail); text-residue check (MSER/morphological-gradient text detection inside the old bbox - any text-like components = residual watermark - fail); seam check (boundary-ring SSIM + texture-statistics mismatch inside vs outside = flag).
4. Verify pass -> register: `... lw_pipeline.py save-working <slug> --from <path> --tool lama --params <json-with-mask-bbox>`.
5. Verify fail -> human QA queue (ONE attempt: `max_attempts` defaults to 1, and
   a repeat attempt recomputes bit-identical pixels).
6. **ONE ENGINE PER SUBMISSION (ADR-009).** Do NOT answer a REJECT by climbing
   the lama -> sdxl -> iopaint ladder: measured over the whole cleaning stage, a
   second engine won 0 of the 3 adjudicated slugs, sdxl lost seam to lama in
   14/15, and iopaint's seam wins are bought by repainting 2.66x the area (all 9
   rejected). `save-working` REFUSES a second engine on a slug (exit 3) unless
   `--allow-ladder` is passed; the engines stay available for an explicit,
   operator-chosen swap. Evidence: `docs/CLEAN_LADDER_DECISION_2026-08-12.md`.

Any helper script authored here that spawns subprocesses MUST pass `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` (Legion focus-steal rule).

### 4. Human QA queue fallback (gate rejects + ambiguous detections)

- Start the IOPaint web UI for hand-drawn masks: `& "$env:LOCALAPPDATA\Python\pythoncore-3.11-64\python.exe" -m iopaint start --model=lama --device=cuda --port=8080` and point the operator at `http://127.0.0.1:8080`. (Verified live 2026-08-22; the constant is `IOPAINT_LAUNCH` in `tools/lw_clean_iopaint.py`.)
- Operator saves the hand-fixed result; adopt it via `... lw_pipeline.py save-working <slug> --adopt`. The G2 verify (section 3.3) still runs on adopted files - the outside-mask assertion uses the hand-drawn mask.

### 5. Submit for authorization

- `... lw_pipeline.py submit <slug>` -> `_cleanneedauth.png`. Operator approves (`approve <slug>` -> `_cleandone` + move to `images\4.Cleaning Done\`) or rejects with a note. This command never self-approves.

### 6. Log/state update + banner

1. Confirm `PIPELINE_LOG.md` gained the transition lines and `ops/runtime/pipeline_state.json` is fresh (re-run `... lw_pipeline.py scan` if in doubt).
2. Print the closing banner (one ASCII line):

```
LW CLEANING | scanned=<n> clean=<c> inpainted=<i> qa-queued=<q> gate-fail=<f> | submitted=<k> | next: approve/reject via lw_pipeline
```
