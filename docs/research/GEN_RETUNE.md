# lw-gen Retune - Archetype Rubric + Priority Plan (2026-07-11)

Durable output of the deep-research workflow (wf_05edf4d1-2ed). Strict ASCII. This
is BOTH the generation-steering rubric AND the similarity/acceptance rubric. The
operator rejected the first results: non-canonical faces, broken hands/fingers, too
photoreal (RealVis wrong feel), uncanny valley. Fix with DEPTH, cheapest lever first.

## LIVE FINDINGS (2026-07-11) - the winning recipe
- STEP 1 (painterly prompt rewrite + cfg 5.0): FIXED "too photoreal" + uncanny. Vayne
  became painterly + canonically recognizable (round tinted glasses cue landed). But
  palette drifted (gold/silver instead of navy+crimson) and un-occluded HANDS stayed
  broken (cand_05 clawed fingers).
- HAND DETECTION IS A DEAD END on painterly art: ultralytics hand_yolov8s detected 0
  hands on the worst broken-hand image and only 1 low-conf box elsewhere. A
  detect->inpaint loop cannot repair hands it cannot see. Detection-repair DEPRIORITIZED
  (matches the critique's warning). YOLO models are downloaded (tools/models/yolo/) if a
  future occluded-hand pass wants them.
- STEP 2 (img2img from a REAL reference splash, StableDiffusionXLImg2ImgPipeline via
  AutoPipelineForImage2Image.from_pipe, strength 0.55) = THE WIN. Seeding from
  tools/models/lora_datasets/vayne/vayne_00_default.jpg simultaneously: locks the
  canonical navy+CRIMSON palette, inherits a canonical dynamic pose, keeps the painterly
  style, AND materially improves hands (inherits real anatomy - no detection needed).
  Output (batch vayne-splash-20260711014930) reads like an actual Vayne splash. This is
  the base recipe: PAINTERLY PROMPT + IMG2IMG-FROM-REAL-REFERENCE.
- REMAINING POLISH (not blockers): all candidates in a run share ONE init image (add
  per-candidate init cycling across the champion's skins for variety); a few hands still
  imperfect on close zoom (optional occluded-region touch-up); the similarity/QA gate is
  not built yet. Face-LoRA likely UNNECESSARY now (img2img already nails identity).
- ANIME-FLAT DIRECTION (operator 2026-07-11: "more anime flat aspect, less photorealism,
  careful of mangled glasses + odd expression"). Anime ban OVERRIDDEN by operator. RealVis +
  anime prompts only goes PARTWAY + still mangles glasses. The WIN is a real ANIME BASE:
  Animagine XL 4.0 (tools/models/animagine-xl-4.0, style splash-booru, booru tags via
  briefs/vayne_animagine.json, --model-path override). It KNOWS LoL champions from booru data
  (Vayne = correct clean RED TINTED GLASSES, dual crossbows, violet ponytail, navy+red cape)
  AND renders clean anime-flat faces - fixing glasses + odd-expression + too-photoreal in ONE
  shot, no img2img needed for identity. Batch vayne-splash-booru-20260711062307 = canonical
  clean anime Vayne. Booru prompt: "<champ>, league of legends, 1girl, solo, <features>,
  masterpiece, high score, great score, absurdres".
- TWO VIABLE RECIPES: (A) RealVis + img2img-from-real = semi-realistic canonical; (B) Animagine
  + booru tags = anime-flat canonical (operator's current preference). Same run/qa/promote
  plumbing; only base + style + prompt-vocab differ.
- POSE + HANDS + CLARITY (operator 2026-07-11: "right hand = 2nd left hand; body positioning
  unnatural; keep detail HIGH, champion is the centerpiece; faces went blotchy/blurry"). Deep
  ArtStation posing research -> the DURABLE FIX = ControlNet-OpenPose. Findings:
  * img2img fixes pose but BLURS faces (blends a semi-realistic source) - rejected for the
    clarity-critical face. Hand DETECTION (YOLO) is unreliable on painterly hands - dead end.
  * Hand chirality (mirrored/second-left-hand) is NOT fixable by negatives - only by STRUCTURE.
    Riot hand formula: hands unified on one weapon / one occluded / gloved (composes ambiguity
    away). Encoded in the prompt.
  * WINNING RECIPE = Animagine + ControlNet-OpenPose (xinsir SDXL) skeleton extracted from a
    real splash (controlnet_aux OpenposeDetector hand_and_face=True) + cowboy-shot detail-tag
    booru prompt. This is TXT2IMG (keeps Animagine's SHARP high detail - no blur) conditioned
    on the skeleton -> natural pro pose + correct hand chirality + large crisp detailed face.
    Batch vayne-controlnet-tuned (cand_05 etc.) = production quality, hits the operator bar.
  * Prompt now carries ArtStation posing vocab (line-of-action/twist/contrapposto/from-below/
    cowboy-shot) + detail tags (detailed face/eyes/skin, sharp focus); negatives kept LEAN.
  * Integrated into lw_gen_run: --controlnet-pose <ref> / --controlnet-scale (config
    controlnet_openpose_path). Skeleton with >1 body -> duplicate-figure glitch; curate
    single-figure refs (skip multi-body). FOLLOW-UP: per-candidate skeleton cycling across a
    champion's skins for pose variety in one batch.

## Root causes of the rejects
1. RealVisXL photoreal base pulls output toward photography / plastic-SSS skin, not
   painterly key art. 2. No champion-identity conditioning -> generic/wrong faces
   (Ambessa rendered a bearded man). 3. SDXL hand weakness x dynamic poses + weapons
   -> broken/extra fingers nearly every frame. 4. The one LoRA run overfit (washed
   out, muddy bg, wrong hair). Photoreal skin + slightly-off face geometry = the
   uncanny-valley read.

## STYLE archetype (general LoL splash = painterly semi-realistic key art)
A NARROW band: a PAINTING of the subject, never a photo, never flat anime.
STEER TOWARD: painterly digital illustration, concept-art / cover-illustration
finish, visible confident brushstrokes, fully volumetric form, smooth idealized
painted skin (no pores, matte), idealized canonically-correct face, dramatic
cinematic chiaroscuro, strong colored rim/back light, warm-key vs cool-shadow
complementary grade, rich deep blacks + luminous glow FX, atmospheric painterly
bokeh bg, flowing hair/cloth motion, dynamic heroic low-angle pose, single hero.
STEER AWAY: photorealistic skin/pores/texture, DSLR photo, cosplay, film grain,
lens bokeh, uncanny 3D render / Unreal / Daz3D / plastic / waxy skin, flat cel
shading, banded 2-tone shadow, black lineart, coloring-book, chibi/anime
proportions, flat even lighting, muted documentary palette, gray washed-out low
contrast, mangled/extra/fused fingers, off-model face, stiff frontal mugshot.

## VAYNE archetype (next focus champion)
IDENTITY ANCHORS (the "same woman across skins" cues): sharp angular face, high
cheekbones, thin high-arched brows, determined/predatory scowl, dark crimson lips,
winged eyeliner; SIGNATURE ROUND RED-TINTED GLASSES (default/Heartseeker/Sentinel);
dark violet-black hair in a HIGH BUN (or long windblown ponytail per skin).
KIT: bat-wing angular spiked shoulder pauldrons, deep navy/indigo bodysuit, crimson
cape lining, thigh-high heeled boots; WRIST-MOUNTED REPEATING CROSSBOW (Final Hour)
- NOT a longbow; grips short bladed silver bolts, glowing bolt-of-light trail; bat
motif everywhere. PALETTE: navy indigo + crimson red + cold silver + pale skin on a
dark moody ground (red-vs-blue complementary pop). BG: gothic ruined cathedral,
stained glass, misty night, drifting bats/embers, atmospheric DoF. POSE: dynamic
lunge / over-shoulder fire / mid-leap, low camera. HANDS: canonically often two on
the crossbow (the hard case); keep clean.
VAYNE NEGATIVES: big longbow, medieval bow, blonde bright hair, sweet smile,
muscular male.

## PRIORITY PLAN (adversarial-critique revised; cheapest lever first, escalate only as needed)
Operator is ground truth for "canonical" + "painterly"; in their absence, evaluate
each result against the real refs (tools/models/lora_datasets/vayne/ official skins
+ the 6 vayne*_firstdone.png in images/2.First Pass Done) and the cues above.
1. FREE LEVER (Tier-0, DONE-ish): rewrite lw_gen_styles.json splash - strip
   photoreal tokens, front-load painterly + archetype tokens, strengthen negatives;
   drop cfg 5.5->5.0. Vayne specifics via briefs/vayne.json prompt_extra. Regen n=8
   PURE txt2img. Does prompt+CFG alone move photoreal->painterly on RealVis?
2. IMG2IMG off a real Vayne splash (StableDiffusionXLImg2ImgPipeline, strength ~0.55,
   NO ControlNet, no new downloads). Inherit Riot painterly value structure + pose.
3. IP-ADAPTER plus-face_sdxl (h94, scale ~0.5) fed a base-skin face crop - identity,
   NO training, NO insightface (insightface fails on painted refs + has no py wheel).
4. depth-ControlNet (diffusers/controlnet-depth-sdxl-1.0) ONLY if img2img pose drifts;
   verify VRAM with plus-face co-resident; do not stack two controlnets.
5. HAND-REPAIR loop: ultralytics YOLO hand-detect (Bingsu hand_yolov8s.pt) -> dilated
   mask -> AutoPipelineForInpainting.from_pipe re-roll -> verify; IOPaint fallback.
   Mirrors the proven cleaning-pass loop. #1 rejection but downstream of a good base.
6. MINIMAL QA: keep the existing CLIP subject gate; add ONE style score (CSD painterly
   -vs-photoreal, or a paint/photo discriminator) as a SOFT rank. Nothing else gates.
7. FACE LoRA only if plus-face insufficient; train on ONE canonical skin (vayne_00),
   NOT all 19 heterogeneous skins (skin dilution caused the Ahri overfit). adamw,
   rank ~24, ~1000-1500 steps; the DreamBooth-LoRA path is already proven on this box.

## DEFERRED (rank-only nudges or wheel risks; NOT on the critical path)
DINOv3 (HF-gated; use DINOv2 fallback), facenet identity veto (photo-trained, noisy
on paintings; torch-pin risk), .venv-detect mediapipe hand-geometry gate (no py3.13/14
wheel, unreliable on painted hands), aesthetic-predictor-v2, bad-anatomy classifier,
CMMD, LPIPS dedup, ComfyUI MeshGraphormer (MANO license, not pip-clean).

## Box constraints (immutable)
sm_120 / torch 2.11 cu128 / diffusers 0.39 / SDPA only. NO xformers, triton,
bitsandbytes/8-bit, insightface, mediapipe-on-py3.14. Every model = pure-torch
safetensors. LoRA training: adamw (never adamw8bit). Keep heavy ML out of
requirements.txt; weights gitignored under tools/models/*.
