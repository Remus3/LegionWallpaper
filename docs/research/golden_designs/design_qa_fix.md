# QA Gate Fix - subject-region sharpness + golden-ranking readiness

Design for the lw-gen QA sharpness fix (GEN_RETUNE.md "QA GATE FINDING") plus
advisory per-element probes for golden-candidate ranking. Strict ASCII.

## 1. Ground truth verified (file:line)

- `laplacian_variance` is WHOLE-IMAGE: tools/lw_gen_qa.py:152-162 opens the full
  PNG, converts to luma, and returns the variance of the 4-neighbour Laplacian
  over every pixel. The gate compares it to T_blur at lw_gen_qa.py:116-117
  (Stage B, reason "blurry"). Clean-DoF hero shots (the operator-preferred
  aesthetic per GEN_RETUNE.md v2) have a majority-blurred background by DESIGN,
  so the global metric is structurally confounded - seed22 (accepted) scored 111
  < 150 and was falsely rejected.
- Keypoints are currently THROWN AWAY at gen time: tools/lw_gen_run.py:406-413 -
  `_extract_pose` calls `detector(img, hand_and_face=True, output_type="pil")`
  and returns only the rendered skeleton PIL image. Inside controlnet_aux,
  `OpenposeDetector.__call__` computes full `PoseResult` keypoints then discards
  them after drawing the canvas (.venv-gen/Lib/site-packages/controlnet_aux/
  open_pose/__init__.py:220-221). The public `detect_poses` API returns
  normalized 0-1 keypoints for body + left/right hand + face, with -1 sentinels
  for missing points (__init__.py:160-197; hand/face normalization at 119-156).
  So programmatic localization IS available - but note the coordinates describe
  the POSE REFERENCE, and `_extract_pose` runs once per batch
  (tools/lw_gen_run.py:593). At the working controlnet_scale 0.55 ("Animagine
  composes freely, not pose-locked" - GEN_RETUNE.md v2), the generated subject
  can drift from the reference skeleton position. A ref-derived bbox is
  therefore an APPROXIMATION for the candidate, not a guarantee.
- Sidecar/candidate schema today: subject_cos, off_cos, margin, aesthetic,
  lap_var, stage_a_pass, stage_b_pass, verdict, reason, thresholds
  (tools/lw_gen_qa.py:335-364). Candidate dicts born PENDING in run:
  tools/lw_gen_run.py:473-479. build_manifest writes no qa_overrides
  (tools/lw_gen_run.py:320-345) - resolve_thresholds' manifest override path
  (tools/lw_gen_qa.py:187-203) is live code but currently unfed, as GEN_RETUNE
  notes.
- Promote ranks PASS candidates by subject_cos only (tools/lw_gen_promote.py:196).
- Full-res image review: in ALL five candidate images (seed22, seed33, seed800,
  cand_01, cand_02) the face + sharp torso sit inside the proven fixed crop
  x 25-75 pct, y 5-65 pct; seed33's intentionally DoF-blurred weapon (right
  side) is largely excluded by it. The official vayne_00_default.jpg has the
  face at roughly x 78-87 pct - OUTSIDE the fixed crop - but officials are
  calibration anchors, never gated candidates, and the ControlNet recipe with
  curated single-figure skeletons + cowboy-shot prompt reliably centers the
  hero. Limitation accepted and recorded.

## 2. Options evaluated

### Option 1 - fixed center-upper crop lap_var (CHOSEN as the gate)
Crop luma to x [0.25, 0.75], y [0.05, 0.65] and compute the existing numpy
Laplacian variance on the crop. Zero new deps (numpy+PIL already required),
runs in .venv-metrics unchanged, proven proxy (ranked the DoF hero shots
correctly in the throwaway pool_judge.py per GEN_RETUNE.md), and verified above
to cover the subject in every accepted/near-miss image. Backward compatible by
construction. This is the gate.

### Option 2 - gen-time bbox handoff (ADOPT the plumbing, ADVISORY only for now)
Verified feasible: keypoints exist but are discarded (citations above). Two
flavors:
- (2a) Ref-skeleton bbox: free (already computed once per batch) but describes
  the reference, not the candidate; at cn 0.55 drift makes it unsafe to GATE on.
- (2b) Candidate self-extraction: after saving each candidate PNG, run
  `detector.detect_poses(np.array(image))` on the CANDIDATE itself (detector
  already resident in .venv-gen when the ControlNet path is active; one extra
  body+hand+face inference per candidate, seconds). This yields the candidate's
  OWN face bbox + wrist coordinates - exactly the localization the upcoming
  weapon/glasses/face repair passes and golden-ranking probes need, with no
  detection model beyond what is already installed.
Decision: implement 2b as manifest plumbing in lw_gen_run (Tier-1, run-side).
QA consumes the face bbox for ADVISORY metrics only (face_lap_var, probes).
The blur GATE stays on the fixed crop until a validation pass over archived
batches shows bbox-crop ranking is at least as good - do not gate on an
unvalidated localizer (that is how T_aes became a dead gate). Cross-venv
transport is plain JSON in gen_manifest.json candidates[] - no new deps.
Failure mode handled: detect_poses can return zero poses on a stylized
candidate -> fields stay null -> QA falls back to the fixed crop silently.

### Option 3 - CLIP-based subject localization in .venv-metrics (REJECTED)
ViT-L-14 has no native pixel-space localization; attention-rollout/gradient
hacks are unreliable on painterly content, add compute in the metrics venv, and
options 1+2 already cover the need with zero new dependencies. Reject.

## 3. Chosen design - dual metric, subject crop gates, global goes advisory

- NEW `lap_var_subject` = Laplacian variance over the subject crop. It is the
  Stage-B blur GATE, compared against a new floor `T_blur_subject`.
- `lap_var` (global) keeps being computed and recorded in sidecar + manifest as
  an ADVISORY/rank/debug signal - it is no longer consulted by grade() when
  lap_var_subject is present.
- Legacy fallback: if a RawScore has lap_var_subject=None (old stub scorers,
  re-graded historical sidecars), grade() falls back to the old
  lap_var-vs-T_blur check. No existing behavior silently changes for old data.

### Exact code changes (tools/lw_gen_qa.py)

1. `RawScore`: append `lap_var_subject: Optional[float] = None` at the END with
   a default (repo dataclass rule - never mid-class). Existing keyword
   constructions in tests/test_lw_gen_qa.py:31 etc. stay valid.
2. `grade()` Stage B blur clause (currently lw_gen_qa.py:116-117) becomes:
   - if `scores.lap_var_subject is not None`: reject "blurry" when
     `lap_var_subject < thresholds["T_blur_subject"]`
   - else: reject "blurry" when `lap_var < thresholds["T_blur"]` (legacy path).
   Reason code stays "blurry" (contract-locked with promote).
3. `DEFAULT_THRESHOLDS` gains `"T_blur_subject": 150.0` (placeholder; replaced
   by the calibrated value - see section 4). resolve_thresholds needs no logic
   change (it iterates DEFAULT_THRESHOLDS keys), and per-batch
   manifest qa_overrides automatically supports the new key.
4. Refactor the Laplacian core so the image loads ONCE:
   - `_lap_var_of_gray(gray: np.ndarray) -> float` (extracted from
     laplacian_variance lines 152-162).
   - `laplacian_variance(path)` keeps its exact signature/behavior (public,
     test-covered).
   - NEW `sharpness_pair(path, crop_frac) -> tuple[float, float]` returning
     (lap_var_global, lap_var_subject) from a single PIL load; crop_frac is
     `(x0, y0, x1, y1)` fractions, slice indices rounded and clamped, degenerate
     crops (<8px a side) fall back to the full frame.
   - Module constant `DEFAULT_SUBJECT_CROP = (0.25, 0.05, 0.75, 0.65)`.
5. Crop is config-tunable, not hard-coded at call sites: config key
   `qa.subject_crop_frac` (list of 4 floats). score_batch resolves it
   (config -> DEFAULT_SUBJECT_CROP) and passes it to the scorer.
6. `ClipScorer`: accept the crop in `__init__`; `__call__` (lw_gen_qa.py:273-284)
   replaces its `laplacian_variance(path)` call with `sharpness_pair` and
   returns `RawScore(..., lap_var_subject=lap_subject)`.
7. Sidecar + manifest candidate fields added (score_batch, lw_gen_qa.py:335-364):
   `lap_var_subject`, `subject_crop_frac` (the rect actually used - provenance
   for future recalibration), and `face_lap_var` (advisory; null unless a
   candidate face bbox exists - see below). `thresholds` in the sidecar now
   carries T_blur_subject automatically.

### Config changes (tools/lw_gen_config.json qa{})

- add `"T_blur_subject": <calibrated>` (see section 4)
- add `"subject_crop_frac": [0.25, 0.05, 0.75, 0.65]`
- KEEP `"T_blur": 150.0` (legacy fallback path + advisory context) with an
  updated `_note_qa_calibration` stating T_blur no longer gates when the
  subject metric is present and citing the seed22 false-reject.

### Run-side plumbing (tools/lw_gen_run.py, phase 2 of the same slice)

- `_extract_pose` additionally returns the batch skeleton's PoseResult list via
  `detector.detect_poses` (kept for provenance as manifest
  `pose_ref_keypoints_frac`, normalized floats, -1 = missing).
- NEW `_locate_subject(detector, pil_image)` run per candidate right after
  `image.save(fpath)` in `_generate_candidates` (lw_gen_run.py:468): calls
  `detect_poses(np.asarray(image), include_hand=True, include_face=True)`,
  takes the highest-total_score pose, and derives:
  - `subject_bbox_frac` = min/max over all valid keypoints, dilated 8 pct,
    clamped to [0,1]
  - `face_bbox_frac` = same over face keypoints, dilated 50 pct of its own size
  - `wrist_points_frac` = body keypoints 4 (RWrist) and 7 (LWrist) when valid
  All null when detection returns nothing. Fields go into the candidate dict
  (extending lw_gen_run.py:473-479). Wrapped in try/except - localization
  failure must never fail generation.
- QA consumption: when a candidate carries `face_bbox_frac`, score_batch
  computes advisory `face_lap_var` on that crop (numpy-only). The GATE is
  unchanged. Promotion of any bbox to gating status requires the validation
  comparison in section 4 step 5.

## 4. Threshold calibration - reuse existing graded batches, no operator sweep

T_blur 150 was calibrated on GLOBAL lap; it does NOT transfer to a crop metric.
Procedure (offline, CPU, .venv-metrics, no generation, no operator):

1. Corpus already on disk: exp3_clean (10 seeds; accepted seed22 + seed33),
   exp4_volume (16 seeds with operator critique labels), vayne-controlnet-tuned
   (6 good, global lap 232-663), proto cand_01/cand_02, official skins +
   non-vayne firstdone anchors (Stage-A context only).
2. One-off script in the session scratchpad (imports lw_gen_qa.sharpness_pair;
   pattern of the retired pool_judge.py): emit a table of
   (image, lap_var_global, lap_var_subject) for every corpus image.
3. Synthetic negatives - reuse the PROVEN blur-sweep procedure from the T_blur
   calibration: PIL GaussianBlur r=1 and r=2 applied to seed22 and the sharpest
   tuned candidate; record their lap_var_subject (global r=1 blur crashed lap to
   ~52 previously; expect a comparable collapse on the crop).
4. Set `T_blur_subject` between max(blurred-set lap_var_subject) and
   min(operator-accepted-set lap_var_subject), biased toward the blurred side
   (protect accepted images first - the failure being fixed is a FALSE REJECT).
   Acceptance criteria, all mandatory: seed22, seed33, seed800, cand_01,
   cand_02, and all 6 tuned candidates clear the floor; every r>=1 blurred
   variant rejects "blurry"; no previously-passing sharp candidate flips.
   Record the measured numbers in GEN_RETUNE.md and _note_qa_calibration.
   Do NOT invent the number in code review - it comes from the measurement.
5. Golden-ranking validation (gates any future bbox promotion + probe trust):
   rank the exp3+exp4 corpus by lap_var_subject and check ordering against the
   operator critique (accepted > "blurry not sure" cases like seed150). Repeat
   with face_lap_var where bboxes exist; bbox-crop may replace the fixed crop
   only if its ordering is at least as consistent.

## 5. Backward compatibility

- Old batches / sidecars without the new fields: promote reads only
  subject_cos (lw_gen_promote.py:196) - unaffected. Re-running QA on an old
  batch dir adds the new fields (score_batch is stateless by design).
- Stub scorers returning 4-field RawScore: lap_var_subject defaults to None ->
  legacy global gate path -> every existing test scenario preserved.
- Config without T_blur_subject / subject_crop_frac: DEFAULT_THRESHOLDS +
  DEFAULT_SUBJECT_CROP fallbacks (same pattern as today, lw_gen_qa.py:172-203).
- Candidates without face_bbox_frac (all txt2img/img2img batches, or failed
  detection): face_lap_var stays null; no code path requires it.

## 6. Per-element QA probes for golden ranking (advisory, honesty section)

Context: T_aes proved that a generic CLIP text-pair softmax can be totally
non-discriminative (everything 0.500-0.504); but the subject-identity margin
DID discriminate (good 0.051-0.071 vs non-vayne <= 0.003). Lesson: probes get
sidecar advisory fields and a labeled-data validation, NEVER a gate slot, until
they demonstrate separation.

- PROPOSE (experiment): `probe_weapon_margin` - crop a square (~35 pct of image
  height) centered on each valid wrist point (from phase-2 candidate
  self-extraction), CLIP margin of "a wrist-mounted repeating crossbow" vs max
  over ["a longbow", "a sword", "an axe", "a blade", "an empty hand"]. Honest
  odds: MODERATE-LOW - a small painterly prop at CLIP's 224px input is exactly
  the regime where CLIP gets vague. Validation is free: the exp4 critique labels
  weapon-wrong on ~15/16 and seed33/tuned as weapon-plausible; require clean
  separation (all-good above all-bad) on that set or DROP the probe. Worth one
  cheap experiment because WEAPON is the #1 golden blocker and the wrist crops
  are free byproducts of phase 2.
- PROPOSE (experiment): `probe_glasses_margin` - face-bbox crop, margin of
  "wearing round red tinted glasses" vs ["no glasses", "a blindfold",
  "a red mask over the eyes"]. Better odds than the weapon probe (faces crop
  larger and CLIP is strong on faces/eyewear); same validation set (glasses-bad
  labels: seeds 54, 150, 222, 404, 800).
- PROPOSE (keep): `face_lap_var` advisory - directly addresses the
  "faces blotchy/blurry" critique; rank tiebreaker among PASS candidates.
- REJECT: any global aesthetic probe (proven dead - config _note_T_aes);
  hand-count/geometry probes (no mediapipe wheel, YOLO detection proven dead on
  painted hands - settled); DINO/LPIPS similarity ranks (already on the
  DEFERRED list); promoting ANY probe to a gate before it separates the labeled
  critique set.
- Promote ranking itself stays subject_cos (contract) - golden review sessions
  sort the enriched sidecars offline; a read-only rank report is a possible
  later follow-up, out of scope here.

## 7. TDD test list (failing test first, tests/test_lw_gen_qa.py + test_lw_gen_run.py)

Phase 1 (QA, .venv-metrics-safe, no torch imports - CI constraint at
lw_gen_qa.py:16-22 holds):
1. test_rawscore_lap_var_subject_defaults_none - 4-arg construction still valid.
2. test_blur_gate_uses_subject_crop_when_present - THE seed22 regression:
   RawScore(lap_var=111, lap_var_subject=400, A-passing) with
   T_blur=150/T_blur_subject=150 -> PASS.
3. test_blur_gate_rejects_soft_subject_despite_sharp_global - lap_var=500,
   lap_var_subject=60 -> REJECT "blurry" (the inverse confound).
4. test_blur_gate_legacy_fallback_global - lap_var_subject=None -> old
   lap_var/T_blur behavior byte-identical.
5. test_resolve_thresholds_T_blur_subject - default, config qa{}, and manifest
   qa_overrides all resolve.
6. test_sharpness_pair_crop_vs_global_synthetic - tmp PNG: sharp checkerboard
   center inside the crop, flat border outside -> lap_var_subject >> lap_var;
   asserts numpy-only import surface.
7. test_sharpness_pair_degenerate_crop_falls_back_full_frame.
8. test_score_batch_sidecar_new_fields - stub scorer; sidecar carries
   lap_var_subject, subject_crop_frac, thresholds.T_blur_subject; manifest
   candidates mirror them.
9. test_qa_face_advisory_from_candidate_bbox - candidate with face_bbox_frac
   gets face_lap_var; candidate without it gets null and no error.
10. test_module_imports_without_torch stays green (existing, lw_gen_qa CI rule).

Phase 2 (run-side; detector stubbed - never load models in CI, per existing
test_lw_gen_run.py conventions):
11. test_locate_subject_bbox_from_stub_poses - normalized keypoints (with -1
    sentinels) -> correct dilated/clamped subject_bbox_frac, face_bbox_frac,
    wrist_points_frac.
12. test_locate_subject_no_pose_yields_nulls_and_never_raises.
13. test_candidate_dict_carries_bbox_fields - _generate_candidates output
    schema extension, null-safe when localization disabled.

Ruff on all new/edited test files before done (repo subagent code-quality rule).

## 8. Tier + rollout

Tier-2 (QA gate = core contract: schema fields + gate semantics change): full
suite + the calibration script run before commit. Order: failing tests ->
lw_gen_qa changes -> calibration run -> set T_blur_subject from measurement ->
lw_gen_run plumbing (+ its tests) -> re-grade archived exp3/exp4 copies as the
live backfill check (data-fix rule: seed22's historical false-reject must flip
to PASS on re-grade) -> docs (GEN_RETUNE QA section update + config notes).
