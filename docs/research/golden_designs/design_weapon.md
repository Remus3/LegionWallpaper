# WEAPON FIX DESIGN - canonical wrist-mounted repeating crossbow
2026-07-11. Strict ASCII. Target: the #1 golden blocker (GOLDEN_DEFINITION.md:38-42, ~15/16
volume-batch fails). Design honors all box constraints and all SETTLED items.

## 0. Ground truth and observed failure modes (full-res review)

Canonical (tools/models/lora_datasets/vayne/vayne_00_default.jpg): a compact dark-silver
REPEATING CROSSBOW RIG mounted on the RIGHT forearm (angular bat-wing limbs, mechanical
stock along the forearm), free left hand gripping a short silver bat-bladed BOLT. Navy +
crimson palette, silver metal.

Observed across the 5 reference candidates (viewed full-res):
- exp3_clean/seed22.png: vague blade prop entering frame lower-right, not attached to a wrist.
- exp3_clean/seed33.png: two-handed rifle-axe hybrid (correct hands, wrong weapon class).
- exp4_volume/seed800.png: dual hand-held bat-wing blades (bat MOTIF leaked into weapon SHAPE).
- vayne-controlnet-proto/cand_01.png: purple energy bat-glaive.
- vayne-controlnet-proto/cand_02.png: energy spear + a shouldered black prop.

Diagnosis: Animagine composes the weapon from the bat/crimson STYLE tokens, not from the
weapon NOUN. "dual wrist crossbows, holding crossbow" is already in the brief
(briefs/vayne_animagine.json:7) and "holding wrist crossbow" in the v2 recipe prompt
(images/_gen_scratch/exp3_clean/index.json:2) - proven insufficient at cn 0.55 with a <77-token
budget. A wrist-mounted repeating crossbow is a rare, mechanically specific object; global
prompt pressure cannot buy it. The fix must be LOCAL (weapon region only) and CONDITIONED
(pixels/structure/concept), exactly as GOLDEN_DEFINITION.md:41-42 predicts.

## 1. Key engine facts (verified, cited)

- lw_gen_run.py:406-413 `_extract_pose` calls `OpenposeDetector(...)(img, hand_and_face=True,
  output_type="pil")` and returns ONLY the drawn skeleton PIL image. KEYPOINTS ARE THROWN AWAY.
- controlnet_aux 0.0.10 exposes `detect_poses(oriImg, include_hand, include_face) ->
  List[PoseResult]` with NORMALIZED (0-1) body keypoints
  (.venv-gen/Lib/site-packages/controlnet_aux/open_pose/__init__.py:160-197) and 21-point
  normalized hand keypoints (__init__.py:119-139). Body index map is the OpenPose-18 order
  (limbSeq is 1-indexed at util.py:86-100, keypoints[k-1] at util.py:99): 0-indexed
  3=RElbow, 4=RWrist, 6=LElbow, 7=LWrist. So wrist/elbow/hand localization is FREE - no
  detection model, satisfying the YOLO dead-end ruling.
- diffusers 0.39 `StableDiffusionXLInpaintPipeline` mixes in `IPAdapterMixin` and
  `StableDiffusionXLLoraLoaderMixin`
  (.venv-gen/.../diffusers/pipelines/stable_diffusion_xl/pipeline_stable_diffusion_xl_inpaint.py:215-222)
  -> IP-Adapter AND per-pass LoRA are both supported ON THE INPAINT PIPE.
- `AutoPipelineForInpainting.from_pipe(pipe)` on the loaded
  StableDiffusionXLControlNetPipeline maps to StableDiffusionXLControlNetInpaintPipeline;
  passing `controlnet=None` maps to plain StableDiffusionXLInpaintPipeline, reusing weights
  with NO reallocation (auto_pipeline.py:242-256, 1141-1188). Zero extra VRAM for the
  inpaint pass.
- `load_ip_adapter(..., weight_name=..., image_encoder_folder=...)` + `set_ip_adapter_scale`
  exist in 0.39 (.venv-gen/.../diffusers/loaders/ip_adapter.py:58-63, 252).
- QA is a stateless two-stage gate with per-candidate sidecars (lw_gen_qa.py:93-119 grade;
  ClipScorer lw_gen_qa.py:209-284); thresholds live in tools/lw_gen_config.json:30-35.
  `resolve_thresholds` already supports manifest `qa_overrides` (lw_gen_qa.py:187-203).
- Batch interlock contract: run/qa/promote interlock ONLY via batch dir + gen_manifest.json
  (lw_gen_run.py:7-10) - the weapon pass must be a 4th stage script, not an import.
- Sampler defaults steps 30 / cfg 5.5 (lw_gen_run.py:426-429); res 1344x768
  (lw_gen_config.json:16-18); recipe v2 = steps 28, cfg 5.5, cn 0.55, skel proto/skel_01
  (images/_gen_scratch/exp3_clean/index.json:4-7).
- 19 official skin splashes on disk for weapon crops (tools/models/lora_datasets/vayne/).
- Cleaning-pass precedent: detect -> mask -> inpaint -> verify with a HARD outside-mask
  identity assertion (cleaning-pass skill; ADR-005 path). The weapon pass reuses that shape.

## 2. Mechanism evaluation (ranked)

| # | Mechanism | P(canonical)/attempt | Effort | Risk | Downloads | Verdict |
|---|-----------|----------------------|--------|------|-----------|---------|
| A | Guided transplant inpaint: paste real crossbow crop affine-fit to wrist, masked SDXL inpaint at strength 0.35-0.5 | HIGH (0.6-0.8; geometry is literally canonical, diffusion only restyles) | M (one-time crop library + affine math) | seam/style mismatch if strength too low; geometry-pose mismatch if crop angle wrong | none | RANK 1 - primary workhorse |
| B | Masked inpaint re-roll, weapon-dense prompt, strength 0.88-0.98 | LOW-MED (0.2-0.35; same UNet that fails globally, but full 77-token budget now spent on the weapon + local canvas) | S (pipe already loaded; from_pipe is free) | can invent yet another prop; needs K rolls + gate | none | RANK 2 - free first rung and the re-roll loop under A |
| C | B + IP-Adapter (h94 ip-adapter_sdxl_vit-h) image-prompting the inpaint with a weapon crop | MED-HIGH (0.4-0.6; strong concept transfer, but IP-A is global-ish even when masked - style bleed) | M (2 downloads + wiring) | ref background/style bleed into region; scale tuning | ip-adapter_sdxl_vit-h.safetensors ~0.7GB + CLIP ViT-H image encoder ~2.5GB (pure-torch safetensors, ungated, gitignored - box-legal) | RANK 3 - escalation when A harmonize drifts |
| D | Weapon-concept LoRA (crossbow crops only), loaded ONLY on the inpaint pipe | HIGH once trained (0.6-0.8) | L (curate 30-60 crops, caption, ~1-2h train, iterate) | small-dataset overfit; earlier failure was whole-character dilution, NOT the method - a single-object concept LoRA scoped to the masked pass avoids both dilution and global style shift | none (training path proven on box) | RANK 4 - durable escalation if A+C acceptance < target |
| E | Structural ControlNet on the inpaint pass (canny/scribble silhouette from the affine-fit crop) | HIGH for SHAPE (0.6+) | L (new controlnet-canny-sdxl ~2.5GB; silhouette compositing; ControlNetInpaint wiring) | duplicate infra with A (same affine code) for less payoff - A already carries texture AND shape | canny CN ~2.5GB | RANK 5 - last resort only |
| F | Global knob/prompt re-sweep | - | - | SETTLED (LEDGER 16) | - | REJECTED by charter |

Why A over C/D first: A needs zero downloads, zero training, reuses the loaded pipe, and is
the digital-painting industry's actual workflow (photobash + paintover). The img2img
face-blur rejection (GEN_RETUNE.md:44-46) DOES NOT APPLY: that rejection was a WHOLE-IMAGE
img2img blending a semi-realistic source into the face; here the mask never touches the
face, and the hard paste-back composite (sec 5) makes out-of-mask pixels bit-identical.

VRAM audit (12GB, offload on - proven envelope): base SDXL bf16 + xinsir CN already runs at
1344x768 with enable_model_cpu_offload (lw_gen_run.py:388-393). from_pipe inpaint adds 0
bytes of weights. IP-Adapter adds ~0.7GB attn procs + ~1.3GB fp16 image encoder, sequenced
by offload - fits. Never co-load two ControlNets (E replaces, not stacks).

## 3. RECOMMENDED pass order (cheapest-first escalation, mirrors the retune plan)

W1 (free rung): keypoint-masked inpaint re-roll (mechanism B). K<=4 rolls per candidate at
strength 0.92, weapon-dense local prompt. Accept via the weapon gate (sec 6). Expected to
salvage a minority; establishes the mask + gate plumbing that every later rung reuses.

W2 (workhorse): reference transplant + guided inpaint (mechanism A). Affine-fit a real
crossbow crop to the wrist, alpha-paste, then the SAME masked inpaint call at strength
0.35-0.50 (2-3 strength/seed rolls). Gate each roll. This is where golden is expected.

W3 (escalation): add IP-Adapter to the W1/W2 inpaint pass (mechanism C), scale 0.5-0.8,
ip_adapter_image = clean weapon crop on neutral background. Use when W2 harmonize either
erases the transplant (strength too high) or leaves a pasted-on look (too low).

W4 (durable asset): train the weapon-concept LoRA (mechanism D), trigger "vaynecrossbow",
load ONLY inside the weapon pass (adapter on the inpaint pipe, unload after). Escalate only
if W2+W3 acceptance stays under target after calibration; once trained it upgrades W1 into
a near-free high-probability rung for ALL future Vayne batches.

W5 (last resort): canny-ControlNet inpaint with the silhouette render (mechanism E).

STOP rule per candidate: first gated PASS wins; after exhausting a rung's roll budget,
escalate to the next rung; after W3 (pre-LoRA era) route to review/ for operator eyeball,
exactly like promote's near-miss lane.

## 4. Mask geometry spec (from OpenPose keypoints, no detection model)

Source of keypoints, in priority order:
1. Re-run `detector.detect_poses(np.array(candidate_img)[:, :, ::-1] is handled internally;
   pass RGB np array, include_hand=True)` ON THE GENERATED CANDIDATE (OpenPose already proved
   reliable on painted splash art - the gen-time skeleton source IS painted art). At cn 0.55
   the generated pose drifts from the batch skeleton, so per-candidate keypoints are correct.
2. Fallback: the batch skeleton's keypoints (extract once in _extract_pose, sec 7).
3. Fallback: fixed heuristic box (right third, vertical middle band) + WARN in the sidecar.

Definitions (all normalized coords -> pixel via (x*1344, y*768)):
- weapon wrist W = body kp index 4 (RWrist) when config weapon.wrist=="right" (canonical
  default rig side), kp 7 (LWrist) when "left". Elbow E = kp 3 (resp. 6).
- forearm vector v = W - E, L = |v| (px). If L < 20px or either kp missing -> fallback chain.
- Weapon ROI = union of:
  a. disc(center=W, r=0.9*L)
  b. disc(center=W + 1.1*v_hat*L, r=1.2*L)   (the rig extends beyond the fist)
  c. bbox of the matching HandResult 21 kps (if present) dilated by 0.5*L
- Rasterize union -> binary mask; morphological dilate 24px; Gaussian feather 16px for the
  inpaint mask_image (keep the BINARY dilated mask separately for paste-back + the identity
  assert). Clamp to image; cap mask area at 35% of frame (a bigger mask means keypoints are
  garbage -> fallback chain).
- FACE EXCLUSION HARD RULE: subtract disc(center=body kp 0 (nose), r=2.2 * dist(kp0, kp1
  neck)/2) from the mask. If the weapon ROI intersects the face disc after subtraction ->
  skip inpaint, route to review (never risk the face).
- Optional second region (later iteration, same code): left-hand bolt pass = disc around the
  free hand, r=0.8*L, for the "holding a silver bolt" canonical read.

Transplant fit (W2): each crop asset ships metadata {anchor_px: wrist attach point in crop,
axis: unit vector of the rig's long axis in crop coords, forearm_len_px, handedness, view}.
Pick asset by handedness + coarse view (side/front from the sign and magnitude of v_hat.x).
Affine: scale s = L / forearm_len_px, rotate by angle(v_hat) - angle(axis), translate
anchor -> W. PIL: crop.rotate(deg, expand=True, resample=BICUBIC) -> resize by s ->
alpha-composite at the computed offset. One-time asset build: 6-10 crossbow crops with
alpha mattes from the official skins (default, dragonslayer, aristocrat, project, sentinel
carry the clearest rigs), stored gitignored under tools/models/weapon_assets/vayne/.

## 5. Concrete diffusers-0.39 API shapes (all verified against installed source)

Derive the inpaint pipe (zero extra VRAM, drop the ControlNet):
```python
from diffusers import AutoPipelineForInpainting
inpipe = AutoPipelineForInpainting.from_pipe(base_pipe, controlnet=None)
# auto_pipeline.py:1176-1188 -> StableDiffusionXLInpaintPipeline, weights shared
```
W1 masked re-roll:
```python
out = inpipe(
    prompt=("vayne, league of legends, wrist-mounted repeating crossbow, mechanical "
            "crossbow gauntlet on forearm, bat wing crossbow limbs, silver metal, "
            "loaded silver bolt, intricate mechanical detail, masterpiece, absurdres"),
    negative_prompt=("sword, blade, longbow, rifle, gun, axe, spear, staff, empty hand, "
                     "extra fingers, deformed weapon, worst quality"),
    image=cand_img, mask_image=feathered_mask,       # both PIL, 1344x768
    strength=0.92, num_inference_steps=32, guidance_scale=6.0,
    width=1344, height=768,
    generator=torch.Generator("cuda").manual_seed(seed),
).images[0]
final = Image.composite(out, cand_img, binary_dilated_mask)  # hard paste-back
```
W2 guided transplant: identical call with `image=pasted_img` and `strength=0.35..0.50`.
W3 IP-Adapter (weights pre-downloaded to tools/models/ip-adapter/, gitignored):
```python
inpipe.load_ip_adapter("tools/models/ip-adapter", subfolder="sdxl_models",
    weight_name="ip-adapter_sdxl_vit-h.safetensors",
    image_encoder_folder="models/image_encoder")     # ip_adapter.py:58-63
inpipe.set_ip_adapter_scale(0.7)                     # ip_adapter.py:252
out = inpipe(..., ip_adapter_image=weapon_crop_rgb, ...)
```
W4 pass-scoped LoRA (StableDiffusionXLLoraLoaderMixin on the inpaint pipe,
pipeline_stable_diffusion_xl_inpaint.py:219):
```python
inpipe.load_lora_weights(weapon_lora_dir, adapter_name="vayne_weapon")
inpipe.set_adapters(["vayne_weapon"], adapter_weights=[0.8])
# ... rolls with trigger token "vaynecrossbow" prepended ...
inpipe.unload_lora_weights()   # never leaks into the base gen
```
LoRA training (proven box path): DreamBooth-LoRA SDXL, UNet-only, 1024px, adamw, rank 16,
lr 1e-4, 800-1200 steps, 30-60 captioned crossbow crops ("vaynecrossbow, wrist-mounted
repeating crossbow, ...").
Keypoints (in .venv-gen, controlnet_aux/open_pose/__init__.py:160):
```python
poses = detector.detect_poses(np.asarray(img_rgb), include_hand=True, include_face=True)
body = poses[0].body.keypoints          # normalized; [4]=RWrist [3]=RElbow [7]=LWrist [6]=LElbow
rhand = poses[0].right_hand             # 21 normalized kps or None
```

## 6. Acceptance check - how we KNOW the weapon is canonical

> **CALIBRATION OUTCOME 2026-07-12 (LEDGER 21, GEN_RETUNE.md): this CLIP gate is DEAD.**
> Built + calibrated exactly as specified below; the ViT-L-14 region gate CANNOT
> separate canonical-crossbow crops from wrong-weapon crops (margin negative on every
> crop; 3 configs 1/9, 2/9, 3/9 good-PASS; the top-2 fallback below did NOT rescue it).
> Shipped the operator-lane fallback (config weapon.gate_mode="operator", default). The
> spec below stays as the gate_mode="clip" path for a FUTURE SEPARATING scorer (weapon
> LoRA / fine-tune / DINO). Do NOT re-tune prompts/crops on ViT-L-14. The rest of sec 6
> (identity assert, full-image re-QA, operator = final judge) still holds.

Weapon-region CLIP gate (new, in .venv-metrics, same open-clip stack as lw_gen_qa.py):
- Crop the weapon ROI bbox (padded 10%) from the candidate.
- weapon_cos = mean cosine vs positives ["a wrist-mounted mechanical repeating crossbow",
  "a crossbow mounted on an armored forearm", "a small mechanical crossbow"].
- weapon_off = max cosine vs distractors ["a longbow", "a sword blade", "a rifle", "an axe",
  "a spear", "bat wings", "an empty gloved hand", "a blurry dark shape"].
- PASS iff weapon_cos >= T_weapon AND weapon_cos > weapon_off AND margin >= T_wmargin AND
  region lap_var >= T_wblur (anti-mush; region-local, immune to the DoF confound noted in
  GEN_RETUNE.md:116-123).
CALIBRATION (mirror the proven QA method, GEN_RETUNE.md:62-89): score (a) weapon crops from
the 19 official skins = must PASS, (b) the same-geometry crops from the ~21 known-bad
candidates = must REJECT; set T_weapon/T_wmargin at the midpoint with the T_margin-style
borderline allowance. If separation is weak, shrink to top-2 positives and re-measure
before shipping the floor - never ship an uncalibrated gate.
HARD non-regression (every accepted fix):
- outside-mask identity: np.array equality outside the dilated binary mask (guaranteed by
  the paste-back composite; assert anyway, cleaning-pass style).
- full-image Stage-A re-run (lw_gen_qa grade): subject_cos/margin must not drop below floors
  (weapon fix must never cost identity).
- Operator remains final judge of "canonical" (memory: operator = ground truth); the gate
  ranks and filters, the operator blesses the first golden exemplars, then those exemplar
  crops join the positive calibration set.

## 7. Integration points in lw_gen_run + new files

Respect the interlock contract (lw_gen_run.py:7-10): the weapon pass is a 4th stage script
sharing only the batch dir + manifest.
1. tools/lw_gen_weaponfix.py (NEW, runs in .venv-gen - it needs torch + controlnet_aux):
   `python tools/lw_gen_weaponfix.py <batch_dir> [--rung w1|w2|w3|w4] [--rolls 4]
   [--strength ...] [--only cand_02.png]`. For each manifest candidate (or QA-PASS-only via
   --passed-only): keypoints -> mask -> rung rolls -> best gated result written as
   cand_XX_wfix.png + cand_XX.weapon.json sidecar {roi_bbox, rung, rolls, weapon_cos,
   weapon_off, chosen_seed, outside_mask_identical: true}; manifest candidates[] gains
   weapon{verdict, rung, file}. Atomic writes throughout. Region CLIP scoring is shelled to
   the metrics venv (small helper mode in lw_gen_qa.py: `--weapon-crop <png>` prints scores
   as JSON) so torch/open-clip stay in their venvs.
2. lw_gen_run.py changes (small):
   - _extract_pose returns (control_image, poses_normalized) and run() writes
     manifest["pose_keypoints"] = {body, left_hand, right_hand} (the fallback source;
     fixes the keypoints-thrown-away gap at lw_gen_run.py:406-413).
   - new flag --weapon-fix: after the gen/QA round loop, shell weaponfix on the batch dir
     (gen venv python), then re-shell QA so verdicts reflect fixed files, then promote.
     Promote prefers cand_XX_wfix.png when weapon.verdict==PASS.
3. tools/lw_gen_config.json new block:
   `"weapon": {"wrist": "right", "T_weapon": TBD-calibrated, "T_wmargin": TBD,
   "T_wblur": 150.0, "rolls": 4, "w2_strength": [0.35, 0.45, 0.5], "assets":
   "tools/models/weapon_assets/vayne", "ip_adapter_path": null, "weapon_lora_path": null}`
   plus per-brief override `weapon{}` (wire through manifest like qa_overrides -
   lw_gen_qa.py:187-203 pattern; note the existing inert-brief-QA-fields follow-up,
   GEN_RETUNE.md:84-86).
4. Assets (all gitignored under tools/models/): weapon_assets/vayne/*.png + meta.json (W2);
   ip-adapter/ (W3, 2 files ~3.2GB); loras/vayne_weapon/ (W4).
5. Tests (TDD, CI torch-free like the existing suite): mask geometry from synthetic
   keypoints (rotated-rect/disc union, face exclusion, area cap, fallback chain), affine fit
   math, gate logic with stubbed scorer, manifest schema round-trip, paste-back identity.

## 8. Milestones + risks

M1 (one session): keypoint plumbing + mask spec + W1 + weapon gate calibration on the 21
known-bads + official crops. Exit: gate separates good/bad crops; W1 measured salvage rate.
M2: crop asset library + W2 transplant. Exit: >=1 operator-blessed canonical-weapon
candidate from the existing accepted set (seed22/seed33/seed800 re-processed).
M3 (only if needed): W3 IP-Adapter downloads + wiring. M4 (only if needed): W4 LoRA.
Risks: OpenPose misses wrists on extreme poses (fallback chain + review lane); CLIP may
score painted crossbows weakly vs distractors (calibrate FIRST, M1 gates M2 effort);
transplant view-angle mismatch (start with side-view crops matching skel_01's profile
composition; add views as needed); W2 strength window too narrow (W3 exists for exactly
this).