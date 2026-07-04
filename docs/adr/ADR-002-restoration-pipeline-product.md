# ADR-002: The LW product is a staged, self-auditing image restoration pipeline

**Date:** 2026-07-03
**Status:** Accepted

## Context

Legion Wallpaper needed its product defined (the ROADMAP's gating item since
bootstrap). The real, existing problem: a ~302-image corpus of 2560x1440
League-splash-style wallpapers (mostly AI-generated DeviantArt fan art) in
`C:\Users\Administrator\Pictures\`, carrying two defect classes - upscale
softness introduced by the operator's old double-resample pipeline, and
source-baked defects (malformed eyes/irises/skin, site watermarks, compression
artifacts, banding). The operator's v1 plan (2026-06-14, archived at
`docs/RESTORATION_PLAN_v1.md`) diagnosed the softness root cause correctly
(bicubic up-to-8K round trip) but predated the research wave and named
photo-trained face restorers (CodeFormer/GFPGAN) that demonstrably harm
illustrations. A five-topic research wave (2026-07-03, `docs/research/`)
verified toolchain, cleaning, audit, source-recovery, and state-machine
choices against primary sources and this box's hardware (RTX 5070, Blackwell
sm_120). Alternatives considered: (a) a conventional wallpaper
rotation/rendering app (no real problem to solve; the corpus IS the problem),
(b) a one-shot batch fix script (no self-audit, no reuse, repeats the v1
failure mode of unverified output), (c) the chosen staged pipeline.

## Decision

LW is a staged, self-auditing image restoration pipeline: drop an image in a
folder -> autonomous processing -> approved output delivered to Pictures
(optional sequential `###.png` rename). Concretely:

- FOUR-STAGE ARCHITECTURE (first/clean/final/last) over the operator's
  10-folder scheme (ADR-003), each stage scratch-then-done with the four
  phase tokens. first = source recovery (Tier0 pHash pair-match -> Tier1
  DeviantArt token base36 decode -> Tier2 SauceNAO -> manual queue) + ONE AI
  upscale + ONE Lanczos down + light USM; clean = detect->gate->mask->LaMa
  inpaint->verify with a human QA queue; final = masked anime-YOLO + ComfyUI
  face/eye repair, debanding, conformance; last = fresh-eyes regression vs
  all milestones.
- GATE LADDER G0-G4: free deterministic metric gates (FR at common scale, NR
  in delta mode only), then a Claude-vision 2AFC rubric (Haiku Batch API
  workhorse, ~$0.004/image), then the operator.
- AUTONOMY LADDER: Phase A shadow -> B spot-check (>= 95 percent agreement,
  zero false approves) -> C full auto with a perpetual 5 percent audit; any
  false approve demotes one phase.
- TOOLCHAIN: IllustrationJaNai (illustration-trained transformer SR) via
  spandrel as the primary upscaler with the existing realesrgan-ncnn-vulkan
  as the CUDA-free fallback; LaMa (non-hallucinating) for watermark
  inpainting; ComfyUI headless for content reconstruction; CodeFormer/GFPGAN
  HARD-EXCLUDED (photo-trained, documented to ruin illustrated faces).
  Python 3.14 orchestration, Python 3.12 side-venvs for ML, torch always
  from the cu128 index (sm_120 requirement).

Full operational detail: `docs/RESTORATION_PLAN.md` (v2).

## Consequences

**Good:** The product finally exists and is grounded in a verified corpus
problem, not speculation. Every stage is auditable and reversible (milestone
sets + hash manifests); the softness bug class is structurally prevented
(single-resample rule + laplacian ratio gate); the process - not the images -
is shareable, sidestepping third-party-art licensing. The gate ladder makes
API spend proportional to uncertainty.

**Trade-off:** Heavy toolchain surface (two side-venvs, model downloads,
ComfyUI later) on a 12GB-VRAM box; autonomy arrives only after a deliberate
calibration campaign, so early throughput is operator-bound. The wallpaper
"app" (rotation/rendering) is explicitly NOT this product; if ever wanted, it
is a separate ADR.

**Watch for:** DeviantArt tightening API/fullview access beyond the 2026-03-09
download clampdown (run the recovery campaign early); IOPaint is archived
upstream (pinned 1.6.0, QA-UI-only dependency); NR-IQA absolute scores are
photo-biased on illustrations (delta/percentile mode only - never absolute
gates); artist-signature keep/remove policy is a queued operator decision;
licensing re-check on detector/LaMa weights before the shareable milestone.
