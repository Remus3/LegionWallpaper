# FINISH PASS DESIGN - 1344x768 draw -> golden 2560x1440 (lw-gen ultraplan)

Date: 2026-07-11. Strict ASCII. Scope: the polish/finish stage that runs AFTER
element correction (weapon/hands/glasses fixes are upstream designs) and delivers
an approved-quality 2560x1440 PNG through the existing pipeline.

## 0. Observed gap (full-res review)

Reviewed at full res: exp3_clean/seed22 + seed33, exp4_volume/seed800,
vayne-controlnet-proto/cand_01 + cand_02, vs official vayne_00_default.jpg.
The accepted candidates are compositionally strong (clean DoF, canonical palette,
correct chirality on seed33) but read as SMOOTH SDXL RENDERS: broad gradient
shading, no painted micro-texture in armor/cloth/hair, soft edge transitions.
The official splash has dense brushwork, hard specular accents, layered FX
(bat swarm, bolt trails), and crisp silhouette edges. A faithful upscaler alone
CANNOT close this gap - it preserves what is there; the missing micro-detail must
be SYNTHESIZED. Hence the finish pass is two-stage: a low-strength SDXL hi-res
img2img refine (adds painted detail) followed by the PROVEN Stage-1 upscale chain
(delivers crisp 2560x1440 with full G1 gating).

## 1. ASPECT strategy: center-crop height, 1344x768 -> 1344x756 (exact 16:9)

Chosen: crop 12 rows (6 top / 6 bottom, 1.6 percent of height) inside lw-gen,
immediately after element correction, before the refine. 1344x756 is exactly
16:9 (756 * 16/9 = 1344) and both axes stay /4 (VAE-safe /8 after the refine
resize below).

Why crop and not the alternatives:
- Generate at a 16:9 bucket (1536x864): REJECTED. (i) It re-opens the shipped
  recipe - resolution is a generation knob; the winning recipe v2 and the QA
  floors were calibrated at 1344x768 (tools/lw_gen_config.json:17 resolution
  [1344,768]; qa floors lines 30-35 calibrated on that batch), and lap_var is
  resolution-dependent (lw_gen_qa.py:152-162 computes whole-image Laplacian
  variance), so floors would need recalibration - explicitly settled/no-redo.
  (ii) 1536x864 is +29 percent pixels over SDXL's ~1MP training buckets and
  1344x768 IS a native SDXL bucket; off-bucket gen risks anatomy/duplication
  regressions in exactly the elements we just fixed. (iii) The gain over a crop
  is 1.6 percent of frame - not worth any model-behavior risk.
- Outpaint width to ~1365: REJECTED. Non-integer/off-grid target, adds an
  inpaint model invocation and a seam risk for a 21-pixel strip.
- Letterbox-extend: REJECTED. Visible bars or synthetic fill on a wallpaper.

Crop placement: symmetric 6/6 default. A content-aware bias is unnecessary at
12 rows; none of the reviewed candidates carry edge-critical content in the
outer 6 rows. (Optional follow-up: bias the crop using OpenPose keypoints -
see section 6 - but NOT required for MVP.)

HARD REQUIREMENT this satisfies: Stage-1 first-pass REFUSES the raw 7:4 frame.
lw_upscale._finish enforces ASPECT_TOL = 0.02 (tools/lw_upscale.py:43) and
raises on mismatch (tools/lw_upscale.py:104-109); |1.750 - 1.778| = 0.028 >
0.02, so an uncropped candidate can never pass Stage 1. The crop is therefore
not cosmetic - it is a pipeline-compatibility requirement and MUST happen
pre-promotion.

## 2. FINISH recipe (exact steps, venv per step)

Evaluated options:
(1) Proven chain alone (JaNai V3 DAT2 x4 -> Lanczos 2560x1440 -> USM): crisp
    but faithful - keeps the smooth-render look. Insufficient alone.
(2) SDXL hi-res img2img refine to final res (~2560x1440 or 2688x1512) then
    downscale: adds detail, but (a) promote SIZE ASSERT blocks any pre-promotion
    file >= 2560x1440 on either axis (tools/lw_gen_promote.py:54-55 TARGET
    consts, 221-227 skip-with-reason oversize_would_trigger_downscale_path),
    (b) it would route Stage 1 onto the ADR-006 downscale-only path, losing the
    lap_ratio softness guard for generated content where it IS meaningful, and
    (c) full-res SDXL denoise at 2560x1440 is the slowest, riskiest VRAM point.
(3) BOTH IN SEQUENCE, refine at an intermediate sub-target resolution, then the
    proven chain: CHOSEN. Gets detail synthesis AND supersampled crispness AND
    keeps every existing contract intact.

### Steps (per QA-PASS, element-corrected candidate)

Step F1 - CROP (venv: .venv-gen, PIL only)
  1344x768 -> center-crop to 1344x756 (rows 6..762). Deterministic, lossless
  aside from 12 rows.

Step F2 - PRE-REFINE RESIZE (venv: .venv-gen, PIL)
  Lanczos upscale 1344x756 -> 2048x1152 (exact 16:9, both axes /64, 1.52x).
  This is the hires-fix canvas; the refine re-synthesizes detail so a plain
  Lanczos here is fine and adds no chain-resample debt (the ADR-002
  never-double-resample rule governs the RESTORATION chain; here the resize is
  input conditioning for a generative step, and Stage 1 downstream still
  performs exactly one AI upscale + one Lanczos + one USM).

Step F3 - DETAIL REFINE, SDXL img2img (venv: .venv-gen, torch/diffusers 0.39)
  - Pipeline: AutoPipelineForImage2Image.from_pipe on the SAME loaded Animagine
    XL 4.0 base (pattern already proven in-repo: tools/lw_gen_run.py:602-606).
    NO ControlNet at this stage - strength <= 0.35 preserves structure by
    itself, and low-strength img2img does not blur the face the way
    img2img-from-a-DIFFERENT-real-image did (that rejection was about blending
    a foreign semi-realistic source, GEN_RETUNE.md; here init == the candidate
    itself, so identity is preserved by construction).
  - Params: resolution 2048x1152, strength 0.30 (sweep 0.25-0.35 once, by eye),
    steps 30 (effective denoise ~9 steps at strength 0.30), cfg 5.0,
    prompt = the batch's recipe-v2 positive (exp3_clean/index.json) with the
    detail tail re-affirmed: "intricate details, detailed armor texture,
    detailed hair, sharp focus, masterpiece, best quality, absurdres"
    front-loaded enough to stay inside the 77-token budget (the truncation
    lesson, GEN_RETUNE.md); negative unchanged. Seed = candidate seed (repro).
  - Guardrail: strength > 0.40 starts re-rolling the very elements the
    correction pass fixed (weapon, glasses, hands). Cap at 0.35 hard.
  - VRAM: Animagine bf16 (~5 GB UNet + ~1.7 GB TEs + VAE) under the default
    enable_model_cpu_offload + VAE tiling (config gen.offload/tiled_vae,
    tools/lw_gen_config.json:20-25; offload path lw_gen_run.py:390-398).
    2048x1152 = 2.36 MP; peak attention seq ~9.2k tokens at the 2x-down block
    under SDPA - comfortably < 9 GB peak on the 12 GB card. Runtime ~40-70 s
    per image with offload on the RTX 5070.
  - Output: <slug>_finish_2048x1152.png written into the batch dir; manifest
    candidate gains {"finish": {"file": ..., "strength": ..., "steps": ...}}.

Step F4 - SANITY RE-SCORE (venv: .venv-metrics, existing lw_gen_qa scorer)
  Re-run ONLY Stage A (subject_cos / margin) on the finished file as a
  regression tripwire - the refine must not drift identity. Do NOT gate on
  T_blur here: lap_var floors are calibrated at 1344x768 (config note line 36)
  and are not transferable to 2048x1152; the primary QA verdict remains the one
  taken on the RAW candidate (unchanged ordering: qa chains per round at
  lw_gen_run.py:629-631). A Stage-A regression > 0.02 cos drop -> keep the
  pre-refine file and flag for review.

Step F5 - PROMOTE (venv: base python, existing tools/lw_gen_promote.py, UNCHANGED)
  Promote the FINISHED 2048x1152 file. 2048 < 2560 and 1152 < 1440, so the
  SIZE ASSERT passes by design (lw_gen_promote.py:224-227) and Stage 1 stays on
  the full-metric upscale path (ADR-006 downscale-only carve-out never
  triggers). Only change: promote copies cand["finish"]["file"] when present,
  else the raw candidate (backward compatible).

Step F6 - STAGE-1 FIRST PASS (venv: .venv-upscale + .venv-metrics, UNCHANGED, post-intake)
  Operator runs intake --all as today; first-pass then does the PROVEN chain:
  IllustrationJaNai V3 detail DAT2 x4 (ADR-004; spandrel tiled backend,
  tools/lw_upscale.py:1-14) 2048x1152 -> 8192x4608, ONE Lanczos downscale to
  2560x1440, ONE light USM (1.2/70/3, lw_upscale.py:29-30), G1 gate with the
  FULL metric set including the valid lap_ratio floor, auto-submit to
  _firstneedauth for operator approval. Downscaling from 8192x4608 (3.2x
  supersampling) is what finally yields the crisp painted edge quality.
  VRAM: tile-bounded (~2-4 GB); runtime ~1-2 min for the x4 on 2048x1152.

### End-to-end cost per accepted candidate
~40-70 s refine + ~5 s crop/resize/score + ~1-2 min Stage-1 upscale
= roughly 2.5-3.5 min GPU time, all stages sequential, never co-resident
(each step is its own subprocess/venv, matching the existing interlock:
batch dir + gen_manifest.json only, lw_gen_run.py docstring lines 8-11).

## 3. INTEGRATION recommendation: split at the promote boundary

RECOMMENDED: F1-F4 live INSIDE lw-gen as a new pre-promotion phase
(tools/lw_gen_finish.py, invoked by lw_gen_run between QA and promote, flag
--finish / config finish{} block, runs only on QA-PASS candidates to save
compute). F5 promote and F6 Stage-1 stay EXACTLY as shipped.

Rationale, in contract order:
- The crop is mandatory pre-promotion (section 1: ASPECT_TOL refuse). A 7:4
  file in 0.Originals is a guaranteed Stage-1 error.
- The refine needs the diffusion stack, the batch prompt, and the candidate
  seed - all of which exist only inside lw-gen's .venv-gen context. Stage 1 is
  deliberately torch-light (spandrel upscaler only) and must not grow an SDXL
  dependency.
- Promote remains a pure producer of stage-0 inputs that STOPS at 0.Originals
  (lw_gen_promote.py docstring lines 22-31); the operator intake boundary and
  ADR-003 folder scheme are untouched.
- Stage-1 first-pass remains the single owner of the upscale-to-target step
  (ADR-004 primary upscaler; one-AI-upscale structural rule lw_upscale.py:7-9),
  and the G1 ladder keeps auditing generated images with the same rigor as
  restored ones - the self-auditing property ADR-002 defines.

## 4. Contracts respected (checklist)
- promote SIZE ASSERT: 2048x1152 strictly under target both axes. PASS.
- lw_upscale aspect guard: promoted file is exact 16:9. PASS.
- ADR-006: never triggered (upscale path, lap_ratio valid and kept). PASS.
- ADR-003 / promote-stops-at-Originals: unchanged. PASS.
- ADR-004: JaNai V3 DAT2 remains the only AI upscaler. PASS.
- Box constraints: only existing .venv-gen deps (torch 2.11 cu128, diffusers
  0.39, SDPA); no new models, no xformers/triton/8-bit/insightface/mediapipe.
  PASS.
- Settled list: no knob re-sweep (refine strength is a NEW knob with one
  bounded 0.25/0.30/0.35 eyeball pick, not a recalibration of the shipped gen
  recipe); base model unchanged; no img2img-from-real (init is the candidate
  itself). PASS.

## 5. Risks + fallbacks
- Refine mutates a corrected element (weapon/glasses): mitigated by strength
  cap 0.35 + Step F4 Stage-A tripwire + operator approval at _firstneedauth.
  Fallback: per-candidate --finish-strength 0.25.
- OOM at 2048x1152 (unexpected): drop to 1792x1008 (exact 16:9, /8-safe);
  offload is already the default path.
- Refine softens instead of detailing (strength too low): the JaNai + 3.2x
  supersample still delivers a strictly better output than today's raw path;
  worst case equals option (1).
- QA blur floor at new sizes: explicitly NOT applied to finished files (F4);
  the known DoF confound in lap_var (GEN_RETUNE.md lines 116-123) remains a
  deferred subject-region fix and is unaffected by this design.

## 6. Engine follow-ups surfaced by this design (not blockers)
- KEYPOINTS ARE CURRENTLY DISCARDED: _extract_pose returns only the rendered
  skeleton image (tools/lw_gen_run.py:406-413, output_type="pil"); wrist/hand/
  face coordinates never persist. Capture and store them in the batch manifest
  (detector supports JSON/array output) - free region localization for the
  upstream weapon/hand/face correction passes AND for the deferred
  subject-region sharpness QA, with zero new models.
- Wire manifest qa_overrides: brief qa floors are inert today (GEN_RETUNE.md
  lines 84-86; resolve_thresholds already reads manifest qa_overrides at
  lw_gen_qa.py:187-203, but lw_gen_run never writes them).
- Promote finish-file selection (F5) is the only promote edit: one field
  lookup with a fallback; TDD it (root-cause-fix skill, Tier-1).
