# lw-gen per-element repair pass - FACE/EYES + GLASSES + HANDS (verify-then-repair)

Design for the golden-definition ultraplan. Strict ASCII. Pattern: hand-rolled
ADetailer in diffusers 0.39 - keypoint-localized crop -> upscale -> masked
low-strength inpaint -> feathered paste-back - executed ONLY on elements a cheap
check (or the operator) flags as flawed. Recipe v2 (Animagine + CN-OpenPose skel_01,
1344x768, steps 28, cfg 5.5, cn 0.55) already renders face/glasses/hands mostly
well; an unconditional pass would degrade good candidates and waste GPU.

## 0. Ground-truth engine facts (verified, cited)

- `_extract_pose` (tools/lw_gen_run.py:406-413) calls
  `OpenposeDetector(img, hand_and_face=True, output_type="pil")` and returns ONLY
  the drawn skeleton canvas. Keypoint coordinates are computed internally then
  THROWN AWAY: `__call__` runs `detect_poses(...)` at line 220 of
  .venv-gen/Lib/site-packages/controlnet_aux/open_pose/__init__.py and uses the
  poses only to `draw_poses` (line 221).
- `detect_poses(oriImg, include_hand, include_face)` is a PUBLIC method
  (open_pose/__init__.py:160-197) returning `List[PoseResult]` with
  `body.keypoints` (COCO-18: 0 nose, 1 neck, 3/6 elbows, 4/7 wrists, 14/15 eyes,
  16/17 ears), `left_hand`/`right_hand` (21 kps each), `face` (70 kps). All
  coordinates NORMALIZED 0-1 (x/W, y/H at lines 188-189, 126-127, 151-152) - so
  they are resolution-independent and valid at any working size.
- controlnet_aux's own hand localization (`util.handDetect(body, oriImg)`,
  open_pose/__init__.py:123) derives hand boxes GEOMETRICALLY from body
  wrist/elbow keypoints - no learned hand detector. This sanctions wrist-anchored
  box math as the localization method (no YOLO, no mediapipe).
- `detect_poses` can be run on ANY image, including a GENERATED CANDIDATE - the
  same painterly domain it already extracts skeletons from successfully
  (GEN_RETUNE.md WINNING RECIPE). This is critical: at cn 0.55 (loose) the
  candidate drifts from the ref skeleton, so ref keypoints are only a prior;
  candidate-side keypoints are the actual localization.
- Skeleton is extracted ONCE per batch from the REF image
  (tools/lw_gen_run.py:592-593); per-candidate keypoints do not exist today.
- `AutoPipelineForImage2Image.from_pipe(pipe)` weight-sharing precedent is live at
  tools/lw_gen_run.py:603-606; `AutoPipelineForInpainting.from_pipe` is the same
  mechanism (already asserted viable in GEN_RETUNE.md PRIORITY PLAN item 5).
- Multi-venv subprocess chain pattern: `_shell_stage` (tools/lw_gen_run.py:491-501)
  shells QA into .venv-metrics. Repair verify reuses this pattern (CLIP lives in
  .venv-metrics only; diffusers lives in .venv-gen only).
- QA blur metric is WHOLE-IMAGE lap_var (tools/lw_gen_qa.py:152-162) - the known
  DoF confound (GEN_RETUNE.md QA GATE FINDING). Face-crop lap_var built here doubles
  as the deferred subject-region sharpness fix.
- CLIP aesthetic softmax is a DEAD GATE (0.500-0.504 on everything,
  lw_gen_config.json:37 note; scorer at tools/lw_gen_qa.py:273-284) - do NOT reuse
  it for repair decisions. Element checks below use 2AFC/3AFC over element-specific
  texts on CROPS, which is a different, calibratable discrimination task.
- Config model_path is still RealVis (tools/lw_gen_config.json:2); Animagine runs
  via --model-path override. The repair tool must accept the same override and use
  the SAME checkpoint that generated the candidate (mixing bases restyles the patch).

## 1. Architecture

New stateless tool `tools/lw_gen_repair.py` (.venv-gen), operating on a batch dir +
gen_manifest.json, same interlock contract as qa/promote (files + manifest only,
no cross-import). Runs AFTER the weapon pass, BEFORE final polish/upscale.

Flow per PASS-verdict candidate:
1. `detect_poses(candidate, include_hand=True, include_face=True)` once ->
   `cand_NN.pose.json` (normalized kps, atomic write). Pick the single PoseResult
   with max total_score; if >1 body detected, flag `multi_body` for operator (the
   duplicate-figure glitch class).
2. Compute element regions (section 2). Emit crops to `repair/cand_NN_<elem>.png`
   for the verify step and the operator contact sheet.
3. VERIFY: shell `tools/lw_gen_crops_verify.py <batch_dir>` into .venv-metrics
   (reuses ClipScorer loading pattern) -> per-crop scores into
   `repair/verify.json`. Merge with optional operator `repair/flags.json`
   (operator overrides automation BOTH directions).
4. REPAIR flagged elements in fixed order (section 5) via
   `AutoPipelineForInpainting.from_pipe(base_pipe)` - one base checkpoint load per
   batch, zero extra weight VRAM, 1024x1024 crop inpaint fits 12GB trivially.
5. Re-verify the repaired crop (re-shell verify on changed crops only). Accept ->
   write `cand_NN_r<k>.png` (NEVER overwrite the original; milestone convention),
   update manifest `candidates[].repairs[]`. Reject after retry budget -> give-up
   policy (section 6).
6. After all elements: re-run lw_gen_qa on the repaired file so the global
   subject/identity gate re-certifies it (a repair must never silently break
   Stage A identity).

Manifest schema addition (Tier-2 change -> full suite per CLAUDE.md):
`candidates[].repairs = [{element, box_px, attempts, strength, seed, verdict,
metric_before, metric_after, file_after}]` appended at END with defaults.

## 2. Region localization spec (keypoints only - no detection model)

All boxes from candidate-side `detect_poses` normalized kps, converted to px at
1344x768. Scale unit S = face scale = dist(eye_l, eye_r) px; fallback
dist(nose, neck)*0.6 if an eye is missing.

- FACE box: center = centroid(nose, eye_l, eye_r); square side = 4.2*S (covers
  hairline to chin on the observed candidates, ~180-280 px); clamp to image.
  If face 70-kps present, tighten to their bbox * 1.35 padding.
- EYES box: if face kps present use kps 36-47 bbox padded 0.6*S vertical / 0.9*S
  horizontal; else horizontal span ear-to-ear (16,17), vertical = eye centroid
  +/- 0.55*S. Typically ~200x90 px.
- GLASSES box: EYES box grown 25 percent horizontally (frames + temple arms) and
  down 0.4*S (lenses droop below the eye line in the failure cases - seed22,
  seed800 both droop).
- HAND boxes (one per detected side): center = mean(hand 21-kps) when present with
  >= 12 kps above score floor; else wrist-anchored: center = wrist kp displaced
  0.35 * dist(elbow, wrist) along the elbow->wrist direction (exactly the
  controlnet_aux handDetect geometry); side = 1.4 * dist(elbow, wrist) capped at
  [96, 384] px.
- Every crop expands 1.6x around its box for inpaint CONTEXT (the unmasked ring is
  what pins style, lighting, and chirality), then Lanczos-upscales so the box's
  long edge maps to ~768 px inside a 1024x1024 canvas (cap upscale factor at 4x -
  beyond that the pasted texture visibly mismatches the surround).

## 3. Failure signatures + repair-needed checks (per element)

Observed across seed22/seed33/seed800/cand_01/cand_02 vs vayne_00_default.jpg
(canonical: SMALL ROUND red-tinted glasses flat to the eyes, high bun + ponytail,
right-forearm wrist-crossbow rig, left hand holding a silver bolt).

FACE
- Signatures: blotchy/soft face at small scale; melted or doubled features; wrong
  head ANGLE/size (structural - NOT inpaint-fixable); off-canon face (round/soft
  vs sharp angular + high cheekbones).
- Check (auto): face-crop lap_var (numpy path already exists,
  tools/lw_gen_qa.py:152-162, applied to the crop). Floor calibrated on the
  accepted set (seed22/seed33/seed800 face crops = PASS anchors; exp4 rejects
  seeds 2/5/8 = FAIL anchors) BEFORE shipping - do not guess a number. Head-angle
  wrongness is operator-only (structural).
- Repair-needed default: lap_var(face crop) < calibrated floor OR operator flag.

EYES
- Signatures: muddy/undefined iris; asymmetric eye shapes; eyes rendered ABOVE the
  lens line (cand_01 - one eye peeks over the red lens); dead gaze.
- Check: operator flag primary. Auto assist: lap_var on the EYES crop vs FACE
  crop ratio (crisp face + mushy eyes = ratio dip); soft signal only, never gates
  alone.

GLASSES (signature element - three distinct failure modes, all observed)
- (a) VISOR-MASK: one continuous red plate over both eyes, no bridge/rims/temples
  (cand_02 fully; cand_01 partially). Semantically far from "glasses" - CLIP-
  detectable.
- (b) DEFORMED FRAMES: asymmetric/floating/drooping lenses, broken bridge
  (seed22 - front frame slides off nose; seed800 - diagonal mismatched lenses;
  operator: seeds 54/150/222/404).
- (c) WRONG SHAPE: angular/cat-eye instead of canonical small ROUND (seed22,
  seed800; seed33 is closest to acceptable).
- Check (auto): 3AFC CLIP on the GLASSES crop over texts
  ["small round red-tinted glasses with thin frames",
   "a red visor mask covering the eyes",
   "a face with no eyewear"].
  Repair-needed if argmax != glasses OR margin < floor. CALIBRATION SET EXISTS:
  operator critique labels glasses-bad (54,150,222,404,800 + cand_01/02) vs
  glasses-ok (seed33); measure both clusters, set the floor at the midpoint, and
  if the clusters do not separate, demote the check to operator-flag-only (the
  T_aes lesson: never ship an uncalibrated CLIP floor).
- Shape-wrongness (c) auto-detection is unreliable (round vs cat-eye is subtle for
  CLIP at crop scale) - operator flag; but the REPAIR prompt always specifies
  round, so any triggered repair also corrects shape.

HANDS
- Signatures: clawed/extra/fused/missing fingers; hand melted into weapon or prop;
  CHIRALITY error (second left hand - seed42 class); hand floating unattached.
- Check (auto - weak by design): candidate-side hand keypoint quality - if
  detect_poses returns a hand with >= 15/21 kps and coherent geometry (monotonic
  finger chains), weakly-OK; missing/low hands are SUSPICIOUS not FAILED (openpose
  hand model shares YOLO's painted-hand unreliability; GEN_RETUNE dead-end
  warning). NEVER auto-repair on this signal alone.
- Repair-needed default: OPERATOR FLAG ONLY. The contact sheet gives per-hand
  crops; the operator marks repair/ok/reject in flags.json. Rationale: an
  automatic hand pass with an unreliable trigger both misses real failures and
  re-rolls good hands - the worst of both.

## 4. Repair recipes (crop-level masked inpaint, from_pipe, same checkpoint)

All: Animagine XL 4.0 via --model-path (same base that generated the candidate),
bfloat16, SDPA, cpu-offload as in `_load_pipeline` (tools/lw_gen_run.py:387-393).
Mask = element box interior ellipse/rect at 0.72 of crop box, Gaussian feather.
Paste-back: Lanczos down to region size, alpha-blend with the feathered mask.
Negative base = recipe v2 negatives (exp3_clean/index.json) minus the global
composition terms, plus per-element additions below.

FACE  - res 1024x1024, strength 0.35 (attempt 2: 0.45), steps 28, cfg 5.5,
        feather 24 px.
        Prompt: "vayne, league of legends, 1girl, beautiful feminine face, sharp
        angular face, high cheekbones, thin arched eyebrows, determined
        expression, dark crimson lips, winged eyeliner, small round red tinted
        glasses, detailed face, detailed eyes, masterpiece, best quality"
        Neg add: "deformed glasses, visor, mask, asymmetric eyes"
        NOTE: face prompt INCLUDES the glasses tokens - a face repair re-renders
        the glasses region, so it must describe them correctly or it reintroduces
        failure mode (a)/(c).
EYES  - res 1024 (from ~200px crop, respect 4x cap -> may run at 768), strength
        0.28 (attempt 2: 0.35), steps 24, cfg 5.5, feather 12 px.
        Prompt fragment: "sharp detailed eyes behind round red-tinted lenses,
        crisp winged eyeliner, focused gaze, detailed iris"
        Neg add: "cross-eyed, asymmetric eyes, blank stare"
GLASSES - res 1024, strength 0.45 for deformed-frame (b)/(c); 0.58 + FULL eye-band
        mask for visor-mask (a) (geometry must be replaced, not refined), steps
        28, cfg 6.0 (slight bump - prompt adherence matters more than variety
        here), feather 16 px.
        Prompt fragment: "small round red-tinted glasses, thin dark frames
        resting on the nose, two separate circular lenses, visible bridge,
        temple arms over the ears, see-through red lenses, eyes visible behind
        lenses"
        Neg add: "visor, mask, goggles, monolens, sunglasses covering the face,
        opaque lenses"
        Always re-verify EYES after a glasses repair (the inpaint re-renders them).
HANDS - res 1024, strength 0.42 (attempt 2: 0.5), steps 28, cfg 5.5, feather
        16 px. Mask covers the HAND ONLY - wrist and forearm stay UNMASKED inside
        the crop; the visible forearm continuation is what pins chirality (the
        structural principle from GEN_RETUNE: chirality is fixed by structure,
        not tokens).
        Prompt fragment (side-specific, from keypoints): "detailed gloved
        <left/right> hand, dark glove, natural fingers, five fingers" plus
        context: "gripping the crossbow" when the weapon pass placed a weapon in
        contact, or "holding a silver crossbow bolt" for the canonical left hand.
        Neg add: "extra fingers, fused fingers, missing fingers, mutated hands,
        six fingers" (recipe v2 already carries most of these).

Hand re-roll SAFETY policy (when repair helps vs makes chirality worse):
- SAFE: fingers-only mangling on a hand whose wrist+elbow are detected and whose
  forearm is visible in the unmasked context ring; hand in contact with a weapon
  or prop (contact pins orientation); gloved fist.
- UNSAFE - DO NOT INPAINT: chirality error itself (a second left hand is an
  ARM-level structure error - the masked re-roll continues the same wrong forearm
  and can only render a better-drawn wrong hand, and a free re-roll at higher
  strength un-pins orientation entirely and can flip a correct hand); hand whose
  wrist keypoint is missing (no anchor - mask placement is a guess); open
  free-space hand with foreshortened palm toward camera (orientation genuinely
  ambiguous even for the model). These cases -> structural give-up (section 6).

## 5. Ordering (relative to the weapon pass)

WEAPON -> HANDS -> FACE -> GLASSES -> EYES -> global QA re-run -> polish/upscale.

- Weapon FIRST (it is the #1 blocker, GOLDEN_DEFINITION.md taxonomy line 1, and
  its inpaint region - right forearm rig + gripped bolt - OVERLAPS both hand
  boxes; any hand repair done before it would be overwritten). Re-run hand VERIFY
  after the weapon pass: it frequently fixes hands for free (hands grip the
  weapon; contact resolves ambiguity - the seed33 both-hands-on-weapon effect).
- Hands before face: coarse-to-fine, and hand crops never overlap the face box.
- Face before glasses before eyes: strictly nested regions, largest scope first;
  each inner pass refines what the outer pass just rendered, and nothing after
  the eyes micro-pass touches the face again. After ANY overlapping repair,
  re-verify the nested elements (face repair -> re-verify glasses + eyes;
  glasses repair -> re-verify eyes).
- Global lw_gen_qa re-run LAST: repaired file must still clear Stage A identity
  (tools/lw_gen_qa.py:106-111); a repair that drops subject_cos below floor is
  reverted to the pre-repair file.

## 6. Retry / give-up policy

- Per element: max 2 inpaint attempts (attempt 2 = new seed + the escalated
  strength listed above). Verify after each; first PASS wins.
- Per candidate: max 5 total inpaint attempts across all elements (budget: one
  1024 crop inpaint at 28 steps is far cheaper than a full 1344x768 gen; 5
  attempts keeps total repair cost under ~1 full generation).
- STRUCTURAL failures never consume attempts - they are not inpaint-fixable:
  wrong head angle/size, chirality error, missing arm, multi-body. Verdict
  `REJECT_STRUCTURAL` in manifest repairs[]; the candidate goes back to the
  seed pool (a fresh full-image roll is cheaper and more likely than fighting
  structure with patches).
- Element still failing after budget: verdict `REPAIR_GAVE_UP`, candidate parked
  in `repair/review/` for the operator eyeball queue (mirrors the promote
  near-miss review convention).

## 7. Repair-needed decision surface (operator + cheap checks)

- The tool ALWAYS emits a contact sheet `repair/contact_sheet.png` (grid: per
  candidate x per element crop, before/after when repaired) plus editable
  `repair/flags.json` seeded with the automated verdicts
  ({cand: {face: "ok|repair|reject", eyes: ..., glasses: ..., hands_l/r: ...}}).
- Operator edit of flags.json overrides automation both directions; re-running
  the tool consumes the edited flags (verify-step results are only DEFAULTS).
- Automated floors ship only after calibration on the labeled corpus we already
  own (operator critique in GOLDEN_DEFINITION.md + accepted set). Two checks are
  calibratable now: face-crop lap_var and glasses 3AFC. Hands stay operator-only.
- Side benefit shipped with this pass: face-crop lap_var IS the deferred
  subject-region sharpness fix for the global T_blur DoF confound
  (GEN_RETUNE.md QA GATE FINDING) - wire the same crop metric into lw_gen_qa as a
  follow-up so the global gate stops false-rejecting clean-DoF heroes like seed22.

## 8. Engine changes (scoped)

1. tools/lw_gen_run.py `_extract_pose`: switch to detect_poses + draw_poses so
   the REF skeleton keypoints are captured in the same detection and persisted to
   the batch dir (`pose_ref.json`) as a localization PRIOR + provenance. Rendered
   canvas output unchanged (Tier-1).
2. NEW tools/lw_gen_repair.py (.venv-gen): keypoints-on-candidate, region math,
   inpaint loop, contact sheet, manifest repairs[] updates. All writes atomic.
3. NEW tools/lw_gen_crops_verify.py (.venv-metrics): crop lap_var + element
   3AFC scores -> repair/verify.json. Shelled via the `_shell_stage` pattern.
4. Manifest schema addition repairs[] (Tier-2: full suite + restart discipline).
5. Calibration script (scratch, not shipped): score labeled crops from the
   existing exp3/exp4/proto batches; record clusters + chosen floors in
   docs/research/ before enabling any auto-repair trigger.

TDD: pure-logic units (region math from synthetic keypoints, flag merge,
retry/give-up state machine, manifest schema) are torch-free and CI-testable with
the same stub-scorer pattern lw_gen_qa tests use (tools/lw_gen_qa.py:19-23).
