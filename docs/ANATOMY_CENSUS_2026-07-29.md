# Anatomy census - 2026-07-29

Measured artifact backing a NEGATIVE result: keypoint-based head-vs-spine
alignment is NOT a viable gate for this corpus. Recorded so the idea is not
re-proposed from first principles in six months.

Origin: the operator flagged `fiora1_firstdone.png` - "the head is off center =
bad. it is not in line with the models spine visually as it is."

## What made this a gate question and not a one-image fix

`fiora1`'s manifest (`images/2.First Pass Done/fiora1/manifest.json`) shows the
image was APPROVED with G1 verdict PASS, `ms_ssim 0.997113`, `lpips 0.043644`,
`dists 0.062058`, and zero gate reasons.

That is not a gate malfunction. G1 is a FIDELITY gate - `ms_ssim`, `lpips`,
`dists`, `lap_ratio`, `halo_pct`, `band_delta` all compare the output against its
own source. `fiora1_firstinitial.png` (1650x928) is an operator hand-crop swapped
in on 2026-07-15, `aspect_class: ok`, `crop_box: null`, `area_loss: 0.0`. The
head-off-spine geometry is INHERENT TO THE SOURCE ART, so a faithful upscale
reproduces it faithfully and scores near 1.0.

Nothing in the ladder asks whether the depicted body is plausible. 288 approved
firstdones sit behind that blind spot. Hence a census rather than a re-crop.

## Method

DWPose onnx-CPU (the ADR-settled localizer, LEDGER 19) under `.venv-gen`
(onnxruntime 1.27.0, cv2 5.0.0 - the only venv with onnxruntime). Weights:
`tools/models/dwpose/yolox_l.onnx` + `dw-ll_ucoco_384.onnx`.

Per figure, from the RAW 133-keypoint COCO-WholeBody array in PIXEL coords:
spine axis = hip midpoint to shoulder midpoint; head center = centroid of the
head points clearing `min_conf` 0.3 (nose, eyes, ears); metric = signed
perpendicular offset of head center from that axis, normalized by shoulder width.

Pixels matter here. The repo's existing `cocowb_to_kp_map`
(`tools/lw_gen_localizer_eval.py:98`) returns ANISOTROPICALLY normalized coords
(`x / w, y / h`), which on a 2560x1440 frame scales the axes differently and
shears the figure. A perpendicular-offset measurement is not shear-invariant, so
that helper cannot be used for this and the census maps indices directly.

Ran over all 288 `*_firstdone.png` in `images/2.First Pass Done`.

## Results

288 slugs, 0 errors, 0 zero-figure detections. Figures per image: 261 single,
13 with 2, 5 with 3, 5 with 4, 3 with 5, 1 with 9.

**CORRECTION - read "0 zero-figure detections" carefully, it does not mean what it
sounds like.** That number is what the code reports, and it is misleading. The
`yolox_l` person detector frequently finds NO person box at all, and
`tools/dwpose_onnx/onnxpose.py:26` then silently substitutes the WHOLE FRAME as the
pose ROI. So a "detected figure" can be the pose model run over an entire
2560x1440 canvas with no person localization at any point.

Measured on a 60-image even-stride sample of the same corpus: **21 of 60 (35
percent) return ZERO person boxes.** Box-count histogram: 0 boxes 21, 1 box 32,
2 boxes 5, 5 boxes 2.

`fiora1` itself is one of the zero-box images. Its keypoints - the ones that produce
the -0.1446 headline number - come from a whole-frame fallback, not from a
localized person. That is also the direct explanation for its uniformly marginal
confidences (0.30 to 0.41 across all nine joints).

This makes Finding 2 below stronger rather than weaker: the corpus never had a
figure-detection rate near 100 percent, it had a fallback that made failure look
like success. Any future work here MUST treat the box count as a first-class
outcome and refuse to report a whole-frame fallback as a detected figure.

Measurable at `min_conf` 0.3: **115 of 288 (39.9 percent)**. The other 173 fail
the shoulder/hip confidence floor.

`abs(offset_norm)` over the 115:

| stat | value |
|------|-------|
| min | 0.0078 |
| p25 | 0.0877 |
| median | 0.1638 |
| p75 | 0.3036 |
| p90 | 0.4298 |
| p95 | 0.5208 |
| max | 1.7349 |
| mean | 0.2217 |
| stdev | 0.2328 |

### Finding 1 - the metric does not reproduce the operator's judgement

`fiora1`, the one image a human actually rejected, measures `abs(offset_norm)`
**0.1446** - rank **66 of 115**, the **43.5th percentile**. It is BELOW the corpus
median for badness.

Any threshold low enough to flag it flags more than half of an already-approved
corpus. A first-pass a-priori threshold of 0.15, derived from head-width-versus-
shoulder-width reasoning, landed essentially ON the median of 0.1638 - it would
have flagged about half the corpus while still PASSING the one known positive.

### Finding 2 - the extreme tail is localizer failure, not bad art

Verified by rendering the detected axis over the image, not inferred:

| slug | offset_norm | shoulder width | spine length | ratio |
|------|-------------|----------------|--------------|-------|
| silver-fang-akali-...-dlnolnu-pre | -1.7349 | 120.1 px | 558.0 px | 0.215 |
| 150-cleanup | -1.3001 | 59.2 px | 235.5 px | 0.251 |
| fiora1 (correct detection) | -0.1446 | 357.4 px | 610.2 px | 0.586 |

A 59 px shoulder width on a 2560x1440 illustration is a collapsed skeleton, not a
slim figure. DWPose collapses shoulders on twisted and crouched poses. The
dramatic numbers are bad keypoints.

Shoulder-width-to-spine-length ratio over the 115 measurable: min 0.215,
p05 0.424, p10 0.461, p25 0.586, median 0.684, p75 0.760, max 1.560. The two
confirmed-garbage detections are the two lowest values in the corpus, so a loose
detection-sanity floor in the 0.30-0.40 band separates them from every credible
detection while discarding under 5 percent of currently-measurable figures.

### Finding 3 - hips are the structural blocker, and no better model fixes it

Among the 173 unmeasurable images, joints below the 0.3 confidence floor:

| joint | count |
|-------|-------|
| right_hip | 159 |
| left_hip | 157 |
| right_shoulder | 121 |
| left_shoulder | 108 |
| (no head point at all) | 80 |

Roughly **91 percent** of unmeasurable images fail on the HIPS. That is a property
of the corpus, not a model defect: wallpaper splash art is routinely cropped at or
above the waist, or the hips are occluded by clothing, weapons and effects.

A spine axis DEFINED as hip-mid-to-shoulder-mid therefore cannot be computed on
most of this corpus as a matter of framing. This rules out the obvious follow-up -
a better pose model cannot find hips that are outside the crop.

## Rulings

1. **Head-spine offset is NOT gated.** It ships as an advisory diagnostic only.
   Nothing in the gate ladder consumes it. Findings 1 and 3 are the evidence.
2. **The salvageable value is the detection-sanity refusal.** The census's most
   useful product is the ability to say "this skeleton is not credible" explicitly,
   turning a silent localizer failure into an explicit unmeasurable verdict.
   Unmeasurable must never collapse into PASS - it is 60 percent of the corpus.
3. **`fiora1` is not reprocessed.** A crop cannot fix anatomy and the upscale did
   not cause it, so a re-run reproduces the defect byte-for-byte. Its disposition
   is an operator call about the source, not a pipeline action.
4. **FUTURE, needs operator intent:** the operator's complaint is a perceptual
   judgement, so the right mechanism is the Claude-vision 2AFC path the
   `end-review` skill already uses - not a keypoint metric. Deciding what is
   allowed to REJECT an image is a product-direction call and was not made blind
   during an unattended run.

## Do-not-redo

- Do not re-propose keypoint head-spine offset as a G1/G2 gate metric. Measured
  and rejected here, with the corpus distribution above.
- Do not attempt to fix it by swapping the localizer. Finding 3 is a framing
  constraint, not a model-accuracy constraint.
- Do not read a DWPose "figure count" as a detection count anywhere in this repo.
  35 percent of the corpus yields zero person boxes and silently falls back to the
  whole frame (`tools/dwpose_onnx/onnxpose.py:26`). `tools/lw_anat_probe.py` labels
  this per figure as `whole_frame_fallback` and counts it separately - preserve
  that distinction in any consumer.
- Do not route pixel-geometry metrics through `cocowb_to_kp_map` - it normalizes
  anisotropically and drops confidence.
