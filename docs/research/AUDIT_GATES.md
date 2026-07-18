# AUDIT_GATES - Audit Metrics and Autonomy Gates for the LW Pipeline

Research date: 2026-07-03. Author: research subagent (audit metrics + autonomy gates topic).
Scope: how the Legion Wallpaper pipeline self-audits each stage (upscale, inpaint) and how it
earns the right to self-approve outputs without the operator in the loop.

Corpus context: ~302 processed 2560x1440 PNGs (LoL splash-art style ILLUSTRATIONS, mostly
AI-generated DeviantArt fan art) + ~77 original .jpg sources. Defects: upscale softness,
malformed eyes/irises/skin, site watermarks, compression artifacts, banding.

Verification discipline: claims are cited with source + date. Anything not confirmed against
a primary source is marked UNVERIFIED. Published "thresholds" for perceptual metrics are
folklore, not standards - treat every number below as a STARTING POINT to calibrate on the
LW corpus itself (section 6.4).

---

## 1. Full-reference (FR) metrics - "did we degrade the content"

FR metrics compare output against a reference (the original source). They answer exactly one
question: did processing move the image away from the source in ways we did not intend.
They CANNOT say the output is good - a faithful copy of a bad source scores perfectly.

### 1.1 The metrics

| Metric  | What it measures | Direction | Notes for LW |
|---------|------------------|-----------|--------------|
| SSIM    | Local luminance/contrast/structure similarity | higher = closer (1.0 = identical) | Cheap, deterministic, brutal on misalignment. Compute on luma. |
| MS-SSIM | SSIM at multiple scales | higher = closer | Preferred over plain SSIM at wallpaper resolutions - single-scale SSIM over-weights fine texture at 2560x1440. |
| LPIPS   | Deep-feature perceptual distance (AlexNet/VGG) | lower = closer | Best human correlation of the classic FR trio; the workhorse. |
| DISTS   | Structure + texture deep similarity | lower = closer | Texture-tolerant - forgives GAN/SR re-synthesized texture that LPIPS punishes. Good second opinion for upscaler output. |

Findings from the literature sweep:
- LPIPS and DISTS are empirically closer to human judgment than PSNR/SSIM for
  super-resolution output; DISTS is repeatedly called out as the strongest for SR
  (acta IMEKO SR metrics review; CVPR 2023 perception-oriented SR paper).
- LPIPS and DISTS track each other closely in practice - use LPIPS as primary, add DISTS
  only when LPIPS flags and you want a texture-tolerant tiebreak
  (unifiedimagetools.com practical guide, 2025 - WEAK SOURCE, practitioner blog).
- One practitioner guide suggests alert/stop thresholds of LPIPS >= 0.20 or SSIM < 0.92
  for "content drifted" in AI image pipelines (unifiedimagetools.com, 2025 - WEAK SOURCE,
  but consistent with common usage in SR papers where LPIPS < 0.15 reads as "close" and
  > 0.3 as "visibly different"). No peer-reviewed standard thresholds exist. UNVERIFIED
  as universal - calibrate on corpus.

### 1.2 Alignment caveats - compare at COMMON SCALE (critical)

FR metrics require pixel-aligned, same-size inputs. The LW upscale stage changes resolution,
so the comparison protocol matters more than the metric:

1. DOWNSCALE THE OUTPUT to the source resolution using the same high-quality resampler the
   pipeline already uses (Lanczos), then compute SSIM/LPIPS at source scale. This asks
   "is the content still there" without rewarding or punishing invented detail.
2. NEVER upscale the reference with bicubic to meet the output - that manufactures a blurry
   reference and biases every metric toward approving soft output (the exact softness bug
   the old pipeline had).
3. Sub-pixel shifts and 1-px crops destroy SSIM (it can drop 0.05+ from a half-pixel shift).
   The pipeline must guarantee no crop/pad/offset between input and output; assert exact
   integer scale factors and identical aspect ratio before computing metrics, and treat an
   unexplained SSIM cliff as an alignment bug first, quality bug second.
4. Color space: compute SSIM/MS-SSIM on luma (Y of YCbCr); LPIPS/DISTS on RGB as designed.
5. JPEG sources vs PNG outputs: the source's own compression artifacts are part of the
   reference. A GOOD artifact cleanup will lower SSIM vs the artifacted source. Therefore
   FR gates are "drift alarms" with generous bands, not tight approval gates - the tight
   gates live in the targeted checks (section 3) and vision audit (section 4).
6. COMPUTE BUDGET: the common scale is capped at `MAX_COMMON_PIXELS` (3840x2160 =
   8.29 MPix, `lw_g1_gate.common_scale_for`). Over budget, BOTH sides are Lanczos-
   resampled down to fit, preserving aspect; under budget the source scale is used
   verbatim, so the rule above is unchanged for the common case. Rationale: DISTS
   allocates ~2 GiB of VGG activations at 7680x4320 on top of what the earlier metrics
   still hold, which OOMs a 12GB card - and OOMs system RAM on the CPU fallback, so the
   metric was simply uncomputable for 8K sources. Measured 2026-07-18: 63 of 230
   first-pass images had lost DISTS this way (every failure was DISTS; scales 5376x3024
   and up), while the largest scale that ever succeeded corpus-wide was 4096x2306.
   The budget sits below that proven ceiling for headroom and matches the 26 corpus
   images already measured natively at 3840x2160. The cap only ever DOWNSCALES the
   reference, so caveat 2 still holds. A capped value is NOT interchangeable with a
   native-scale one (capping hides high-frequency difference): `fr_metrics` reports
   `capped` + `native_scale` alongside `common_scale` so the two are never conflated.

### 1.3 Inpainting QA is a split-domain problem

For watermark/artifact inpainting the mask defines two regions with OPPOSITE expectations:

- OUTSIDE the (dilated ~8 px) mask: nothing should change. Gate: SSIM >= 0.995 and
  mean abs diff <= 1/255 on the unmasked area. This catches the "sledgehammer" failure
  (full-image regeneration) mechanically - it is the single most important inpaint gate.
- INSIDE the mask: change is intended, so FR "similarity to original" INVERTS - if the
  inpainted patch is still nearly identical to the watermarked original
  (patch SSIM >= ~0.95), the inpaint silently did nothing. See section 3.4.

### 1.4 LW starting thresholds (to be calibrated, section 6.4)

Upscale stage, computed at source scale per 1.2:
- MS-SSIM >= 0.92 pass; 0.85-0.92 flag for vision audit; < 0.85 hard fail.
- LPIPS (alex) <= 0.20 pass; 0.20-0.30 flag; > 0.30 hard fail.
- DISTS advisory only: log it, alert if DISTS and LPIPS disagree by a large margin
  (LPIPS bad + DISTS fine often = re-synthesized texture, send to vision audit).

**Calibrated seeds (QA Session 1, 2026-07-04, n=10 real source->finished-ref
pairs, upscaler=realesrgan-x4plus-anime, USM70, LoL splash corpus).** Observed
ranges: MS-SSIM self 0.984-0.993 (median 0.991); LPIPS self 0.047-0.144 (median
0.077); GT LPIPS vs finished ref 0.048-0.097; laplacian ratio 1.81-4.43. The
starting gates above are far too loose for this corpus. Recommended tighter:
- MS-SSIM >= 0.98 pass; 0.96-0.98 flag; < 0.96 hard fail.
- LPIPS (alex) <= 0.12 pass; 0.12-0.20 flag; > 0.20 hard fail.
- GT LPIPS <= 0.10 sanity band (how close the upscale lands to the finished ref).
  [VOIDED QA Session 2, 2026-07-04 - no finished ground-truth exists for this
  corpus; the `_cleanup` files are operator "original-not-found" markers, not
  finished references. See the FROZEN block below.]
- Laplacian ratio: keep the >= 1.0 softness floor, but do NOT set an absolute
  ceiling - the 1.81-4.43 spread at fixed USM tracks SOURCE softness, not
  over-sharpen. Over-sharpen must be caught by a real overshoot detector (3.1),
  not a laplacian ceiling; or by source-adaptive USM. The crude edge-diff halo
  proxy used this session (0.41-0.73) is not a gate - build the 3.1 detector.
These are still seeds - widen the n before freezing, and re-calibrate for the
IllustrationJaNai primary path (this run used the ncnn fallback).

**FROZEN (QA Session 2, 2026-07-04, n=10, IllustrationJaNai V1 DAT2 via
spandrel/torch = PRIMARY, vs realesrgan-x4plus-anime = fallback; same 10
images, same USM70 finish so the delta isolates the upscaler).** Implemented in
`tools/lw_g1_gate.py` (`DEFAULT_G1_THRESHOLDS`, `verdict`, `overshoot_halo`);
scored by `tools/lw_upscale.py` outputs. Two structural corrections to the
Session 1 seeds:

1. NO FINISHED GROUND-TRUTH. The `reference_pictures/*_cleanup.png` files are
   operator "original-not-found" markers, NOT finished references (operator
   ruling, 2026-07-04). The Session 1 "GT LPIPS vs finished ref" band is VOID.
   G1 scores SELF-metrics ONLY - output downscaled to source scale vs the
   source ("did we degrade content") - plus the overshoot detector and the
   laplacian floor. Every corpus image still needs work; nothing is a spec.
2. REAL OVERSHOOT DETECTOR replaces the crude edge-diff halo proxy
   (`overshoot_halo`, per 3.1/3.2): fraction of near-edge pixels whose value
   falls OUTSIDE the source local min/max range by > 8/255 (USM ringing). It
   ranks IJN below the fallback on ALL 10 images.

Observed n=10 (self-metrics, output-at-common-scale vs source) [min - max (median)]:

| metric       | IJN V1 DAT2 (PRIMARY)      | realesrgan-anime (fallback) |
|--------------|----------------------------|-----------------------------|
| MS-SSIM      | 0.994 - 0.999 (0.999)      | 0.984 - 0.993 (0.991)       |
| LPIPS (alex) | 0.008 - 0.080 (0.016)      | 0.047 - 0.144 (0.077)       |
| lap_ratio    | 1.26 - 3.22 (1.49)         | 1.81 - 4.48 (2.25)          |
| halo_pct     | 0.018 - 0.075 (0.036)      | 0.049 - 0.145 (0.087)       |
| band_delta   | -0.010 - 0.029 (0.004)     | -0.032 - 0.079 (0.001)      |

IJN wins EVERY image on MS-SSIM, LPIPS, and halo_pct (10/10 each). The
fallback's higher lap_ratio is RINGING (higher halo_pct), not clean detail -
confirming laplacian is not an over-sharpen ceiling; the overshoot detector is.

Frozen G1 thresholds (`DEFAULT_G1_THRESHOLDS`):
- MS-SSIM: pass >= 0.98, flag 0.96-0.98, fail < 0.96.
- LPIPS (alex): pass <= 0.12, flag 0.12-0.20, fail > 0.20.
- laplacian ratio: fail < 1.0 (softness floor), NO upper ceiling.
- halo_pct: FLAG > 0.05 (over-flag is the safe direction), never a hard fail.
- band_delta: ADVISORY FLAG > 0.05, NOT a hard fail - at n=10 the band metric
  noise (up to 0.079) overlaps real-banding signal, so a >0 hard fail wrongly
  rejected the BETTER upscaler 8/10 on ~0.004 noise. Revisit with a proper
  banding metric (BBAND, 3.3) before ever hard-gating on banding.

Resulting verdicts n=10: IJN 8 PASS / 2 FLAG (its 2 sharpest images,
halo-flagged for vision audit); fallback 1 PASS / 9 FLAG; ZERO hard fails on
either path. Still n=10 - widen n before treating these as final - but the
primary path and the real overshoot detector now agree, and the gate no longer
hard-fails clean primary-path output.

**UPDATE (2026-07-05, ADR-004 - V3 detail DAT2 now PRIMARY).** n was widened
past 10 (n=14 golden-comparable) and the golden set re-frozen at n=12 on V3
(added a JPEG-artifact + a banding defect case; pv 6d43a6d4). These thresholds
are UNCHANGED and HOLD under V3 - no real hard-gate breaches, and V3's gentler
sharpening drops the 2 high-halo cases under the 0.05 flag, so all 12 golden
cases are PASS with zero flags. Finding: first-pass 4x on sources already
>= 2560w scores as false-soft (the common-scale rule upscales the 1440p output
back to the native source resolution to compare) - a G0 source-gate gap, not a
threshold problem.

Inpaint stage:
- Outside dilated mask: SSIM >= 0.995 hard gate, else FAIL (pipeline bug).
- Inside mask: no FR pass gate; run section 3.4 residual checks instead.

---

## 2. No-reference (NR) IQA - "is this output good"

### 2.1 The pyiqa toolbox

pyiqa (IQA-PyTorch, github.com/chaofengc/IQA-PyTorch) is the standard one-stop package:
PSNR, SSIM, MS-SSIM, LPIPS, DISTS, FID, NIQE, BRISQUE, MUSIQ, TOPIQ (NR and FR variants),
NIMA, MANIQA, HyperIQA, CLIP-IQA(+), LIQE, QualiCLIP, Q-Align and more, all behind one
`pyiqa.create_metric(name)` API with GPU acceleration. Latest release 0.1.15.post2
(2026-03-18, PyPI). Actively maintained (DMM FR metric added Dec 2025).

Environment caveats for THIS box (RTX 5070 12GB, Blackwell sm_120, Python 3.14):
- pyiqa depends on torch + torchvision. sm_120 needs torch built against CUDA 12.8+
  (cu128/cu129 wheels); anything older fails with "no kernel image" or CPU fallback
  (pytorch/pytorch issue #164342; PyTorch forums Blackwell threads).
- torch 2.12.1 (2026-06-17, PyPI) supports Python 3.10-3.14 and ships cp314 wheels on
  PyPI - but PyPI Windows wheels are CPU-only by convention; CUDA wheels come from
  download.pytorch.org. As of torch 2.9.x there were NO CUDA wheels for cp314
  (pytorch issue #169929). Whether cu128 cp314 Windows wheels exist for 2.12.x is
  UNVERIFIED - check `https://download.pytorch.org/whl/cu128` at install time.
- PRAGMATIC ROUTE: side-install Python 3.12 and build a dedicated metrics venv
  (torch cu128 + pyiqa + opencv). Keep 3.14 for orchestration only. This also dodges the
  long tail of ML deps (timm, transformers, openai-clip) that lag on 3.14.
- GPU is a nice-to-have, not a requirement: for a 302-image corpus, NIQE/BRISQUE/SSIM run
  fine on CPU; transformer metrics (MUSIQ, TOPIQ, Q-Align) are the ones that want the GPU.
  12GB VRAM is ample for inference-only IQA at 2560x1440 (most metrics resize internally).

### 2.2 Which NR metrics to trust on ILLUSTRATIONS

This is the key trap: almost all NR-IQA is trained on PHOTOS.

- NIQE and BRISQUE are natural-scene-statistics (NSS) models. Documented to be invalid for
  computer graphics and cartoons - "the metric is really not applicable to cartoons"
  (videoprocessing.ai NIQE criticism page; arXiv 1907.03842 NIQE barriers paper). Flat
  cel-shaded regions and clean line art violate NSS priors, so clean splash art can score
  WORSE than a noisy photo. Never use their absolute values on the LW corpus.
- MUSIQ (trained KonIQ-10k/PaQ-2-PiQ/SPAQ/AVA), TOPIQ, MANIQA, HyperIQA: deep photo-trained
  metrics. Distribution shift on illustrations is real; their absolute scores on splash art
  are UNVERIFIED against human judgment. No published study of NR-IQA correlation
  specifically on anime/splash-art illustrations was found in this sweep.
- CLIP-IQA judges quality through CLIP prompt pairs ("Good photo." vs "Bad photo.") and
  supports CUSTOM prompt pairs - the one metric that can be adapted to the domain, e.g.
  ("a sharp, clean digital painting", "a blurry, artifact-ridden digital painting").
  Treat as an experiment to validate against operator verdicts, not a trusted gate.
- AIGC-specific line of work is the closest match to LW's mostly-AI corpus: AGIQA-3K
  database (IEEE TCSVT 2023, 2982 AI-generated images with human MOS), Q-Align (LMM-based
  scorer, available in pyiqa), ImageReward/PickScore (CLIP-based, but text-prompt
  conditioned - less useful since LW has no prompts). Q-Align is the best candidate
  "modern NR metric" to trial on splash art.

### 2.3 How LW should actually use NR metrics: DELTA mode + corpus percentiles

Because absolute scores are untrustworthy on illustrations, use NR metrics two safer ways:

1. DELTA GATE: score(output) - score(input) on the SAME content. Photo bias mostly cancels
   because both sides are the same illustration. Gate: output must not regress
   (delta >= -epsilon) on MUSIQ/TOPIQ/Q-Align; a regression is a strong "flag" signal even
   when the absolute number is meaningless.
2. CORPUS BANDS: score all 302 processed images once, take the 5th/25th percentile per
   metric as the "this corpus" floor. New outputs below the corpus 5th percentile get
   flagged. This self-calibrates the photo bias away.

Recommended NR set for LW: MUSIQ + TOPIQ (topiq_nr) + Q-Align as the deep trio (delta +
percentile mode), CLIP-IQA with custom illustration prompts as an experiment, NIQE/BRISQUE
logged for the ledger but NEVER gating.

---

## 3. Targeted cheap checks (OpenCV-level, no ML weights)

These are deterministic, fast (ms per image), run on Python 3.14 with opencv-python alone,
and target LW's exact known defects. They are the first rung of the gate ladder.

### 3.1 Sharpness / acutance

- Variance of Laplacian (cv2.Laplacian(gray, CV_64F).var()): the standard blur detector.
  Absolute values are content-dependent (a sharp image ~17k vs its blurred copy ~1.9k in
  one published example - the RATIO is meaningful, the number is not). LW gate: compute at
  common scale (downscale output to source size), require
  laplacian_var(output_ds) / laplacian_var(source) >= 1.0 (upscale+USM should never soften;
  ratio < 0.9 = the old double-resample softness bug resurfacing - hard fail).
- Edge width / rise distance (acutance): sample strong edges (Canny), measure 10-90%
  luminance rise distance perpendicular to the edge; median edge width in px. Softness
  shows as median width creeping up; oversharpening as width < 1 px plus overshoot.
  This is the Imatest-style measure, easy to reimplement (~50 lines numpy).
- Gradient percentile: 99th percentile of Sobel magnitude, as a second opinion.

### 3.2 Halo / oversharpen detection

Unsharp-mask halos = overshoot (bright fringe) and undershoot (dark fringe) flanking strong
edges (Imatest artifacts page; US patent 8090214 detects halos by comparing gradient
direction original vs processed). Cheap LW detector:
- For each strong edge pixel, sample a short profile perpendicular to the edge; halo if
  profile max exceeds the bright-side plateau by > T (start T = 8/255) or min undershoots
  the dark side by > T, on more than P% of edges (start P = 5%).
- Extra tripwires: fraction of pixels at 255/0 within 3 px of edges (clipping from USM),
  and the FR path catches it too - oversharpened output vs source shows LPIPS rising while
  laplacian ratio also rises (sharp AND drifted = halo suspect -> vision audit).
- Guard at the source: cap USM amount/radius in the pipeline config; the detector is the
  audit, the cap is the prevention.

### 3.3 Banding detection

Banding = false contours in smooth gradients (skies, glows - splash art is FULL of glows).
Literature: BBAND index (ICASSP 2020, no-reference banding predictor), Deep Banding Index
(ICASSP 2021, github akshay-kap/Meng-699-Image-Banding-detection, TensorFlow), FS-BAND
(arXiv 2311.18216), BAND-2k dataset (arXiv 2311.17752). The deep ones are photo/video
oriented and heavy; a cheap structural detector is enough for LW:
- Find smooth regions (local variance below threshold after 3x3 blur), compute per-channel
  gradient there; banding shows as connected iso-value plateaus separated by 1-2 level
  steps - count plateau boundary pixels per smooth-area pixel (band edge density).
- Gate in DELTA mode: band edge density of output must be <= input (processing must not add
  banding; upscaling 8-bit gradients then sharpening is a classic banding amplifier).
- If banding becomes a real fight, port the BBAND algorithm (it is described fully in the
  ICASSP 2020 paper and is pure signal processing, no weights).

### 3.4 Residual-watermark detection (post-inpaint)

The watermark bbox is KNOWN at inpaint time (the mask). Three stacked checks inside it:
1. CHANGE-HAPPENED check: SSIM(inpainted patch, original watermarked patch) <= 0.90.
   If ~1.0 the inpaint silently no-opped - fail. (This is the "SSIM patch map vs original
   in the watermark region" idea - inverted logic, similarity here means failure.)
2. TEXT-RESIDUE check: the usual site watermarks are text/logo. Run MSER or
   morphological-gradient text detection inside the old bbox on the OUTPUT; any text-like
   connected components = residual watermark - fail.
3. SEAM check: SSIM map along the dilated mask boundary ring between output and its own
   blurred version - a visible inpaint seam shows as a structured ring; plus compare local
   texture statistics (variance, edge density) inside vs immediately outside the mask -
   large mismatch = patch does not blend - flag for vision audit.
Also keep a small template library of known wallpaper-site watermarks (wallpaperscraft
etc.) and template-match the four corners + center-bottom of EVERY output as a corpus-wide
tripwire, not just inpainted ones.

### 3.5 Eye/face-region checks on illustrations

Photo face detectors (dlib, mediapipe, retinaface) fail on anime-style faces - use
anime-specific detectors:
- lbpcascade_animeface (github nagadomi/lbpcascade_animeface): OpenCV LBP cascade XML,
  zero heavy deps, works on near-frontal anime faces. Runs on the 3.14 interpreter today.
  Weakness: misses profiles/tilted faces; splash art poses will evade it sometimes.
- anime-face-detector (github hysts/anime-face-detector, PyPI): mmdet+mmpose based,
  face bbox + 28 landmarks (eyes individually locatable). Much better recall, but the
  mmcv/mmdet dependency chain is notoriously version-locked against new torch -
  compatibility with torch 2.12/cu128 is UNVERIFIED; if it fights back, fall back to
  the cascade + generous crop.
- animeface-2009 (nagadomi): older but does landmarks; niche build. Backup option.

LW use of face/eye regions:
- Detect face bbox -> derive eye crops (landmarks if available, else upper-central face
  heuristic) -> cheap checks: left/right iris similarity (mirror one eye, SSIM/LPIPS vs
  the other - grossly malformed or mismatched eyes score low), specular highlight count
  per eye (connected bright blobs; 0 or > 4 is suspicious in splash style), edge coherence.
  These heuristics are UNVALIDATED - log-only until calibrated against operator verdicts.
- The HIGH-VALUE use: face and eye crops at native resolution are exactly what the
  vision-LLM auditor needs (section 4.3) - a 2560x1440 global view downscales too far to
  judge irises; a 512x512 native-res eye crop does not.

---

## 4. Vision-LLM as auditor (Claude vision)

This is the path to full autonomy: metrics catch regressions mechanically; only a vision
model can judge "the left iris is deformed" or "there is a ghost of the watermark text".

### 4.1 What the evidence says about VLM-as-IQA-judge

- MLLMs (GPT/Claude class) beat handcrafted NSS metrics at NR-IQA but still trail
  specialized deep IQA models on photo benchmarks (MDPI Big Data Cogn. Comput. 2025,
  "Comparative Evaluation of Multimodal LLMs for NR-IQA... OpenAI and Claude.AI models").
- LMMs are RELIABLE at coarse-grained pairwise quality comparison and weaker at
  fine-grained absolute scoring - 2AFC (two-alternative forced choice) prompting is the
  gold-standard protocol (IEEE TCSVT 2024, arXiv 2402.01162 "2AFC Prompting of Large
  Multimodal Models for IQA"). Design implication: frame the audit as SIDE-BY-SIDE
  before/after with forced-choice questions plus a defect checklist, not "rate 1-10".
- Including the image in the judging prompt improves judge-human correlation (VLM-judge
  literature 2024-2025). Rubrics with explicit criteria + forced numeric scale + required
  rationale are the standard pattern.
- For LW specifically: none of this is validated on splash-art illustrations - which is
  exactly why the ledger calibration phase (section 5) exists.

### 4.2 Cost per image (VERIFIED against platform.claude.com/docs pricing + vision pages, 2026-07)

Token math: image tokens = ceil(w/28) x ceil(h/28).
- High-res tier models (Opus 4.8/4.7, Sonnet 5, Fable 5): max long edge 2576 px, cap 4784
  visual tokens. A full 2560x1440 wallpaper = 92 x 52 = 4784 tokens (exactly at cap).
- Standard tier (Haiku 4.5, Sonnet 4.6/4.5): long edge > 1568 px is downscaled; cap 1568
  tokens, so a wallpaper costs ~1560 tokens (at 61% linear resolution - fine detail lost).
- A 512x512 crop = 19 x 19 = 361 tokens on any tier.

Audit call shape (side-by-side): 2 full images + 4 crops (2 eye crops, watermark region
before/after) + ~800 prompt tokens, ~500 output tokens.

| Model, mode | Input tokens | Cost per audit | 302-image sweep |
|---|---|---|---|
| Haiku 4.5 ($1/$5), standard res | ~5.4k | ~$0.008 | ~$2.40 |
| Haiku 4.5, Batch API (-50%) | ~5.4k | ~$0.004 | ~$1.20 |
| Sonnet 5 intro ($2/$10, thru 2026-08-31), high res | ~11.5k | ~$0.028 | ~$8.50 |
| Sonnet 4.6 ($3/$15), standard res | ~5.4k | ~$0.021 | ~$6.40 |
| Opus 4.8 ($5/$25), high res | ~11.5k | ~$0.062 | ~$18.70 |

Notes: Batch API gives 50% off and fits the autonomous pipeline perfectly (audits are not
latency-sensitive). Newest models (Opus 4.7+, Sonnet 5) tokenize text ~30% heavier but
image token math is as above. Up to 100 images/request on 200k-context models; 10 MB max
per image; 8000x8000 max dimensions; >20 images per request triggers a stricter 2000 px
per-image limit.

Model choice: Haiku 4.5 for the per-image audit workhorse (cheap enough to run at every
stage), escalate to Sonnet/Opus at high-res tier only for images Haiku flags or for the
final approval pass. High-res tier matters: it sees the wallpaper at native-ish resolution
instead of 61%.

### 4.3 Prompt pattern (the LW audit rubric - v1, to iterate)

Mechanics that matter (from 4.1 evidence + Claude vision docs):
- Images BEFORE text in the message; label them "Image 1:", "Image 2:", ...
- Side-by-side framing, and DO NOT reveal which image is the processed one. Randomize A/B
  order per call and record the mapping; sycophancy toward "the improved version" is real.
- Send: full A, full B, then native-res crops (eyes, old watermark bbox) labeled per image.
- Force JSON output with a fixed schema; temperature 0; pin model ID + prompt hash in the
  ledger. For borderline verdicts, self-consistency: 3 calls, majority vote.
- Position-bias check on high-stakes calls: swap A/B and re-ask; disagreement = flag.

Rubric schema (each category 0-3: 0 fail, 1 poor, 2 acceptable, 3 good; rationale required
for anything below 3):

```json
{
  "which_is_better_overall": "A|B|tie",
  "categories": {
    "global_sharpness":        {"A": 0, "B": 0, "note": ""},
    "halo_or_ringing":         {"A": 0, "B": 0, "note": ""},
    "eyes_and_irises":         {"A": 0, "B": 0, "note": ""},
    "hands_and_anatomy":       {"A": 0, "B": 0, "note": ""},
    "skin_and_faces":          {"A": 0, "B": 0, "note": ""},
    "watermark_or_text_residue": {"A": 0, "B": 0, "note": ""},
    "banding_and_gradients":   {"A": 0, "B": 0, "note": ""},
    "color_fidelity":          {"A": 0, "B": 0, "note": ""},
    "composition_intact":      {"A": 0, "B": 0, "note": ""},
    "other_artifacts":         {"A": 0, "B": 0, "note": ""}
  },
  "verdict_for_processed": "APPROVE|REVISE|REJECT",
  "revise_stage_hint": "upscale|inpaint|none",
  "one_line_reason": ""
}
```

Pass rule for the processed image (auto-computable from the JSON): no category at 0;
at most one category at 1; eyes_and_irises >= 2; watermark_or_text_residue == 3; and
which_is_better_overall must not be the ORIGINAL (processed must win or tie).

When to trust the VLM alone vs paired with metrics:
- Never alone at first. Metrics are deterministic, repeatable, free, and catch regressions
  (softness, drift, no-op inpaint) that a VLM might wave through; the VLM catches semantic
  defects (deformed iris, ghost text, extra fingers) no metric sees.
- Pair them: metrics are the hard pre-gate (fail fast, no API cost), the VLM is the
  semantic gate, and the operator is the calibration reference until the ledger proves
  the auto stack (section 5). After calibration the VLM + metrics run alone with a small
  perpetual random audit.

---

## 5. The LW gate ladder - per-stage checks and the road to autonomy

### 5.1 Ladder shape (cheap -> expensive -> human)

```
G0 SOURCE GATE (per recovered source, free)
   - resolution >= half of target (else upscale factor too aggressive - flag)
   - perceptual hash (pHash) matches the corpus item it claims to replace
   - decodes clean, sane aspect ratio, not a thumbnail/preview (-pre) file
G1 UPSCALE GATE (free, deterministic)
   - alignment asserts (integer scale, same aspect)
   - MS-SSIM / LPIPS at common scale (1.4 thresholds)
   - laplacian ratio >= 1.0, median edge width, halo detector (3.1, 3.2)
   - banding delta <= 0 (3.3)
   - NR delta gate: MUSIQ/TOPIQ/Q-Align no regression (2.3)
G2 INPAINT GATE (free, deterministic)
   - outside-mask identity: SSIM >= 0.995 (1.3) - hard gate
   - inside-mask: change-happened + text-residue + seam checks (3.4)
   - corner watermark template sweep (3.4)
   - face/eye crops extracted and cheap eye checks logged (3.5)
G3 VISION AUDIT (Claude, ~$0.004-0.03/image batched)
   - side-by-side rubric (4.3), Haiku 4.5 workhorse
   - escalation: any category <= 1 or pass-rule failure -> re-audit on Sonnet/Opus
     high-res tier before declaring REVISE/REJECT
G4 OPERATOR (during calibration; sampled after)
   - approve / reject (+ optional defect tag) in a dead-simple triage flow
     (approved -> Pictures, rejected -> rework queue)
```

Any hard fail at G1/G2 short-circuits (no API spend). G3 verdict REVISE routes back to the
named stage with the rubric notes attached as the retry hint. Everything is appended to
the ledger regardless of outcome.

### 5.2 The ledger (calibration substrate)

One row per (image, pipeline_version, stage attempt) in docs/audit/ledger (SQLite or
append-only JSONL - JSONL is greppable and git-friendly, start there):

```
image_id, timestamp, pipeline_version, stage,
metrics: {msssim, lpips, dists, lap_ratio, edge_width, halo_pct, band_delta,
          musiq_delta, topiq_delta, qalign_delta, wm_change_ssim, wm_text_residue},
auto_verdict (G1+G2+G3 composite: APPROVE|REVISE|REJECT),
llm: {model_id, prompt_hash, ab_order, rubric_json, cost_usd},
operator_verdict (APPROVE|REJECT|null), operator_tag,
agreement (auto == operator), false_approve (auto APPROVE + operator REJECT)
```

### 5.3 Removing the operator - explicit criteria

The two error types are NOT symmetric: a false APPROVE ships a defective wallpaper (the
thing the whole pipeline exists to prevent); a false REJECT wastes one rerun. Tune every
threshold conservative (over-flag), and define autonomy in terms of false approves.

- PHASE A - SHADOW (start here): operator reviews 100% of outputs; auto-verdict is
  computed and recorded but decides nothing. Minimum 50 images before any promotion.
- PHASE B - SPOT-CHECK: promote when, over the trailing 50 operator-reviewed images:
  agreement (auto vs operator) >= 95% AND false approves == 0 over the trailing 30.
  Operator now reviews only: auto-REVISE/REJECT items, plus a 10% random sample of
  auto-APPROVEs.
- PHASE C - FULL AUTO: promote when false approves == 0 over 100 consecutive
  operator-checked samples since entering Phase B. Approved outputs land in Pictures
  untouched by the operator. A perpetual 5% random sample still goes to a review folder.
- DEMOTION: any false approve discovered at ANY phase drops the pipeline one phase and
  restarts that phase's window. Any pipeline_version change (new model, new threshold,
  new prompt) drops Phase C -> B automatically (the calibration was for the old pipeline).

### 5.4 Milestone regression (audit every output against prior milestones)

Keep a frozen GOLDEN SET: 10-15 representative (input, approved-output) pairs spanning the
defect classes (soft upscale, watermark corner, bad eyes, banding-heavy glow). Every
pipeline change re-runs the golden inputs and:
- metric deltas vs the stored approved outputs must stay within epsilon
  (start: MS-SSIM within 0.01, LPIPS within 0.02, lap_ratio within 5%);
- one batched Haiku side-by-side of new-vs-stored-approved output per golden image -
  new output must win or tie.
This is the cheap self-audit "against prior milestones" and doubles as the shareable
public proof-of-process artifact.

### 5.5 Determinism and shareability

- Pin and record: pyiqa version + metric model weight checksums, torch version, Claude
  model ID, prompt template hash, threshold config hash - all in every ledger row
  (pipeline_version is the hash of that tuple).
- The ledger + golden set + rubric make the process publishable: anyone can rerun the
  gates on their own corpus and get comparable, explainable verdicts.

---

## 6. Recommendations and open items

### 6.1 Build order
1. G1/G2 cheap checks in pure OpenCV/numpy (runs on the existing 3.14 interpreter if
   opencv-python has cp314 wheels - UNVERIFIED; otherwise this too goes in the 3.12 venv).
2. Python 3.12 metrics venv: torch cu128 + pyiqa; wire MS-SSIM/LPIPS/DISTS + MUSIQ/TOPIQ/
   Q-Align delta gates. Verify torch sees the 5070 (`torch.cuda.get_device_capability()`
   -> (12, 0)) before trusting GPU numbers.
3. Claude G3 auditor with the 4.3 rubric on Haiku 4.5 via Batch API; ledger JSONL.
4. Corpus calibration run (6.4), then Phase A shadow mode.

### 6.2 Risks
- All NR-IQA absolute scores are photo-biased on illustrations - anyone (including the
  vision LLM literature) quoting absolute-score thresholds for this corpus is guessing.
  Delta + percentile mode (2.3) is the mitigation.
- anime-face-detector's mmcv/mmdet chain vs torch 2.12/cu128 is UNVERIFIED and historically
  brittle - budget for the lbpcascade fallback.
- cp314 CUDA wheels: UNVERIFIED; the 3.12 venv sidesteps it entirely.
- VLM verdict drift across model updates - pinned model IDs + Phase C -> B demotion on any
  pipeline_version change covers it.
- Sonnet 5 intro pricing ends 2026-08-31 ($2/$10 -> $3/$15); cost table shifts then.

### 6.3 Explicitly out of scope here
Upscaler/inpainter selection and the source-recovery workflow are sibling research topics;
this doc only defines how their outputs get judged.

### 6.4 Calibration run (do this before trusting ANY threshold in this doc)
Score the full 302-image corpus + the 77 originals once with every gate metric. Derive:
per-metric corpus percentile bands, the actual MS-SSIM/LPIPS distribution of KNOWN-good
prior outputs vs sources, and 20 operator-labeled worst/best examples. Set the v1
thresholds from that data; the numbers in sections 1.4 and 3 are literature-informed
seeds, nothing more.

---

## Sources

- pyiqa / IQA-PyTorch: https://github.com/chaofengc/IQA-PyTorch ; https://pypi.org/project/pyiqa/ (v0.1.15.post2, 2026-03-18)
- SR metrics review: https://acta.imeko.org/index.php/acta-imeko/article/view/1679/2939
- LPIPS/SSIM practitioner thresholds (WEAK): https://unifiedimagetools.com/en/articles/ai-image-quality-metrics-lpips-ssim-2025
- NIQE not applicable to cartoons: https://videoprocessing.ai/metrics/ways-of-cheating-on-popular-objective-metrics.html ; https://arxiv.org/pdf/1907.03842
- AGIQA-3K: https://arxiv.org/abs/2306.04717 (IEEE TCSVT 2023)
- 2AFC prompting of LMMs for IQA: https://arxiv.org/pdf/2402.01162 (IEEE TCSVT 2024)
- MLLMs (OpenAI/Claude) for NR-IQA: https://www.mdpi.com/2504-2289/9/5/132 (2025)
- Banding: BBAND https://live.ece.utexas.edu/publications/2020/ICASSP2020_BBAND.pdf ; BAND-2k https://arxiv.org/pdf/2311.17752 ; FS-BAND https://arxiv.org/pdf/2311.18216 ; Deep Banding Index https://github.com/akshay-kap/Meng-699-Image-Banding-detection
- Halo detection patent: https://patents.google.com/patent/US8090214B2/en ; Imatest artifacts: https://www.imatest.com/imaging/artifacts/
- Laplacian variance blur detection: https://theailearner.com/2021/10/30/blur-detection-using-the-variance-of-the-laplacian-method/
- Anime face detection: https://github.com/hysts/anime-face-detector ; https://github.com/nagadomi/lbpcascade_animeface ; https://github.com/nagadomi/animeface-2009
- Claude vision + pricing (VERIFIED 2026-07-03): https://platform.claude.com/docs/en/build-with-claude/vision ; https://platform.claude.com/docs/en/about-claude/pricing
- PyTorch Blackwell/sm_120: https://github.com/pytorch/pytorch/issues/164342 ; cp314 CUDA wheels gap: https://github.com/pytorch/pytorch/issues/169929 ; torch 2.12.1: https://pypi.org/project/torch/
