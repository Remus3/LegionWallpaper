# GOLDEN RUBRIC - lw-gen golden definition (Vayne instantiation, v1)

Status: DRAFT for operator ratification. Operator is ground truth; this rubric encodes
their seed critique (docs/research/GOLDEN_DEFINITION.md) so batches can be graded fast
and trended. Skeleton is champion-generic; VAYNE columns instantiate it. Strict ASCII.

## 0. Ground truth and what I saw (full-res adversarial review)

Canonical ref: tools/models/lora_datasets/vayne/vayne_00_default.jpg. Load-bearing
details of the official splash: the crossbow is a RIG STRAPPED ON THE RIGHT FOREARM
(wrist-mounted repeater, bat-wing limbs, no handheld grip), the LEFT HAND separately
grips a short silver bladed bolt; glasses are small ROUND red-lens spectacles sitting
on the nose; hair is a HIGH BUN with a long ponytail falling from it; palette is navy
indigo + crimson + cold silver + pale (not lavender) skin; pose is a mid-leap kick with
thigh-high heeled boots; background is misty gothic night with drifting bats.

Element-by-element gap of each accepted ref vs golden:

- exp3_clean/seed22.png (accepted): face crisp, scowl + dark lips + winged liner
  correct, palette and clean-DoF arches correct. FAILS golden on: weapon (a large
  handheld silver bladed prop at the hip, not a forearm rig; left hand clipped at frame
  edge gripping an ambiguous red/silver object), glasses (angular double-lens wing
  shape with a janky white rim, not round), hair (ponytail only, no high bun), kit
  (collar reads correct but pauldron underscaled).
- exp3_clean/seed33.png (accepted): both hands cleanly unified on the weapon (Riot
  hand formula works), high bun + ponytail BOTH present (best hair of the set), face
  clean. FAILS golden on: weapon (a giant double-bladed axe-crossbow held like a rifle
  - handheld, wrong class, and it sits blurry in a foreground plane eating the right
  half), skin (lavender/violet drift, not pale), collar (oversized red spikes reading
  as a second pauldron layer), glasses (near-correct red lenses but angular with a
  heavy brow bar).
- exp4_volume/seed800.png (closest of volume batch, operator: "okay except glasses,
  weapon"): confirmed - pose, cape flow, palette, face, ponytail all read golden-
  adjacent. FAILS on: weapon (right hand plunged into a two-winged bladed contraption,
  handheld not forearm-mounted), glasses (angular red cat-eye, off-model shape), plus
  no visible bun and a soft left hand at the hip.
- vayne-controlnet-proto/cand_01.png: great energy, bats + cathedral present. FAILS
  on: weapon (purple glowing bladed thing gripped in one hand), busy pre-v2 background
  and effect spam, fishnet-textured bust off-model, left-hand grip mushy.
- vayne-controlnet-proto/cand_02.png: strong free composition and face size. FAILS
  on: glasses rendered as a red HALF-MASK over the nose (not-glasses), right arm FUSED
  into an armored blade limb (weapon-arm, worst weapon failure mode), effect spam.

The shared residue across all five: (a) no candidate has ever rendered the forearm-
mounted repeater + separate bolt-in-left-hand combination; (b) glasses drift to
angular/visor/mask; (c) single-pass 1344x768 micro-detail is soft next to the official
splash's dense finish. That is exactly the operator taxonomy: weapon dominant, then
glasses/hands/face, then finish.

## 1. Element checklist - PASS criteria + severity

Severity tiers: BLOCKER = auto-reject the candidate; MAJOR = cannot promote to golden
until fixed by a pass; MINOR = polish, fix opportunistically. Severities mirror the
critique frequencies (weapon ~15/16, then hands/face, glasses 5, posture 5, kit 3,
composition 1).

| # | Element | PASS criteria (Vayne instantiation) | Severity |
|---|---------|--------------------------------------|----------|
| W | WEAPON | A repeating crossbow RIG mounted on the RIGHT FOREARM (strapped, bat-wing limbs, silver+navy). NOT handheld, NOT a longbow/axe/blade, NOT fused into the arm, scaled to forearm length (roughly elbow-to-knuckle, never torso-sized). Bonus: left hand holding a short silver bladed bolt. | BLOCKER if wrong class / fused / absent / torso-scale. MAJOR if correct class but handheld or misscaled. |
| H | HANDS | Correct count, five fingers each where visible, correct chirality, natural grip or pose-consistent placement. Riot formula (both on weapon / one occluded / gloved) is an accepted PASS route. | BLOCKER if mangled / extra / fused / second-left-hand. MAJOR if awkward placement for the pose. |
| F | FACE | Sharp angular face, high cheekbones, thin arched brows, determined scowl, dark crimson lips, winged liner. Head angle consistent with the body posture; face is the sharpest region in frame. | BLOCKER if off-model / malformed / wrong gender read. MAJOR if angle/sizing off or expression drifts sweet. |
| E | EYES | Both eyes coherent behind the lenses, gaze direction matches head/pose, no smearing at full res. | MAJOR (BLOCKER if smeared into noise). |
| G | GLASSES | Small ROUND red-tinted spectacles resting on the nose, thin silver frame, both lenses distinct, eyes visible through the tint. NOT angular / cat-eye / visor / half-mask. | BLOCKER if not-glasses (mask/visor/absent). MAJOR if glasses but wrong shape (the seed800 failure). |
| R | HAIR | Dark violet-black. HIGH BUN present with the long ponytail falling from it (both, like seed33; ponytail-only fails this line). Windblown motion consistent with pose. | MAJOR (bun missing = MAJOR; wrong color/blonde = BLOCKER). |
| K | KIT | Bat-wing spiked pauldrons at shoulder scale (not torso scale), deep navy bodysuit, crimson cape LINING (cape reads as cape, not as collar spikes), high collar, thigh-high heeled boots if legs in frame, bat motif accents. | MAJOR if a piece is misscaled/miscast; MINOR for small trim/detail drift. |
| P | PALETTE | Navy indigo + crimson + cold silver, PALE skin (no lavender drift), dark moody ground, red-vs-blue complementary pop. No gold/bronze takeover. | MAJOR (skin-color drift = MAJOR; full palette miss = BLOCKER). |
| S | POSE / POSTURE | Anatomically coherent dynamic pose (lunge / over-shoulder fire / mid-leap), believable line of action, shoulder/hip counter-twist, no missing or extra limbs, low-camera heroic angle. | BLOCKER if malformed/missing limb. MAJOR if stiff or angle awkward. |
| C | COMPOSITION | Single hero, action logically coherent (no arrow-in-flight with no shooter logic), weapon and limbs fully inside frame or intentionally cropped, negative space works FOR the subject (no giant blurry prop eating a half, the seed33 failure). | MAJOR. |
| B | BACKGROUND | Clean-DoF gothic environment (cathedral/arches/night), optional drifting bats/embers, no clutter, no effect spam, background never sharper than the face. | MINOR (MAJOR if clutter competes with subject). |
| D | FINISH / DETAIL | Dense splash-grade micro-detail on subject (armor edges, hair strands, glass specularity) after the finish pass; no banding, no smearing, no upscale halos; face crispest region. | MAJOR pre-finish (every raw gen fails this today); BLOCKER at promotion time. |

## 2. Wallpaper-fitness criteria (2560x1440 target)

- FILL: final image exactly 2560x1440, 16:9 native composition (raw 1344x768 scales
  1.905x - the finish pass must survive that without halos; use the proven
  .venv-upscale IllustrationJaNai chain, not naive resample).
- SUBJECT PLACEMENT: face center in the upper-third band, vertically 15-45 percent
  from top; never within 5 percent of any edge. Subject occupies roughly 40-70 percent
  of frame height (cowboy-shot or wider).
- CROP SAFETY: no BLOCKER-tier element (weapon rig, face, glasses, hands) within the
  bottom 60px (taskbar zone) or within 3 percent of left/right edges; intentional
  limb crops allowed only for non-signature elements.
- READABILITY AT DISTANCE: at 25 percent zoom the silhouette must still read as Vayne
  - ponytail+bun silhouette, red glasses dot, crimson-on-navy split. If the thumbnail
  reads generic-dark-hero, composition fails.
- DESKTOP TOLERANCE: left third may carry quieter negative space (icon zone); highest
  detail density stays center-right or center.

## 3. Per-candidate SCORECARD (operator fills one line in seconds)

Grades per element: 2 = golden, 1 = okay/fixable, 0 = fail. X = not visible/NA.
One pipe-delimited line per candidate, machine-parseable, mirrors the seed-critique
style:

```
VAYNE|<batch>|<seed>|W:0-2|H:0-2|F:0-2|E:0-2|G:0-2|R:0-2|K:0-2|P:0-2|S:0-2|C:0-2|B:0-2|D:0-2|verdict:REJECT/HOLD/FIX/GOLD|note:<free text>
```

Examples (the three accepted refs as I graded them at full res):
```
VAYNE|exp3_clean|22|W:0|H:1|F:2|E:2|G:1|R:1|K:1|P:2|S:2|C:2|B:2|D:1|verdict:FIX|note:handheld blade prop; wing glasses; no bun
VAYNE|exp3_clean|33|W:0|H:2|F:2|E:2|G:1|R:2|K:1|P:1|S:2|C:1|B:2|D:1|verdict:FIX|note:rifle-grip axe-bow; lavender skin; blurry fg prop
VAYNE|exp4_volume|800|W:0|H:1|F:2|E:2|G:1|R:1|K:2|P:2|S:2|C:2|B:2|D:1|verdict:FIX|note:closest; cat-eye glasses; winged blade contraption
```
Verdicts: REJECT (any BLOCKER-severity 0 that a pass cannot address), FIX (0/1 only on
pass-addressable elements), HOLD (operator unsure, park), GOLD (see section 4).
Trending: grep the ledger for `W:0` count per batch = weapon-pass efficacy metric.

## 4. THE GOLDEN BAR (promotion to 0.Originals)

A candidate is GOLDEN and may be promoted only when ALL of the following hold:
1. Every BLOCKER-capable element (W, H, F, G, S) scores 2 - no exceptions, no
   "barely okay". The weapon line specifically: forearm-mounted repeater, correct
   scale, correct side.
2. No element scores 0 anywhere on the card; at most TWO elements score 1, and only
   in MINOR-tier lines (B) or kit trim (K).
3. All five wallpaper-fitness criteria in section 2 pass at final 2560x1440.
4. D (finish) scores 2 AFTER the finish pass - raw single-pass output never promotes
   directly (the plateau finding: raw SDXL tops out at good-fan-splash).
5. The QA gate passes with the SUBJECT-REGION sharpness measure, not whole-image
   lap_var (see section 5 - the current metric false-rejects clean-DoF golds).
6. Operator eyeballs the card and signs the line. The rubric ranks; the operator
   ratifies. No auto-promotion.

## 5. Rubric element -> fix-pass mapping (the rubric drives iteration)

| Element | Owning pass | Mechanism |
|---------|-------------|-----------|
| W WEAPON | WEAPON PASS (new, pass 1, the #1 blocker) | Region-localized conditioning/inpaint at the right wrist. KEY ENGINE FACT: the OpenPose skeleton is already extracted per batch via OpenposeDetector(hand_and_face=True) in _extract_pose (tools/lw_gen_run.py:406-413), but with output_type="pil" the keypoint COORDINATES are rendered into the control image and DISCARDED - only the PIL skeleton survives. Fix: also call the detector's keypoint path (detect_poses) and persist wrist/hand/face coords to the batch manifest; then the weapon pass masks a box around the right-wrist keypoint with NO detection model (YOLO dead end stays dead). Conditioning source: a weapon-crop reference of the rig from vayne_00_default.jpg (inpaint re-roll or weapon-region img2img - full-image img2img stays rejected). Note _extract_pose runs ONCE per batch (tools/lw_gen_run.py:593), so one coord set covers all candidates of a batch. |
| H HANDS, E EYES, G GLASSES, F FACE | REPAIR PASS (pass 2) | Same keypoint-localized masks: face box from face keypoints (glasses + eyes + expression re-roll with a round-red-glasses-weighted prompt), hand boxes from hand keypoints (re-roll toward Riot formula). Masked inpaint mirrors the proven cleaning-pass loop; verify with outside-mask identity assertion. |
| R HAIR, K KIT, P PALETTE | REPAIR PASS (prompt-side) + scorecard trend | Bun and skin-tone drift respond to prompt weight within the locked recipe v2 (1344x768, steps 28, cfg 5.5, cn 0.55, skel proto/skel_01 - images/_gen_scratch/exp3_clean/index.json:4-7); persistent 0s escalate to a masked region re-roll in the repair pass. |
| S POSTURE, C COMPOSITION | GENERATION (skeleton curation) | Pose source is the lever, not scale: curate single-figure skeletons; per-candidate skeleton cycling is the deferred variety feature. A posture 0 is not repairable - reject and redraw. |
| B BACKGROUND | GENERATION (clean-DoF v2 recipe) + FINISH PASS deband | Already mostly solved by v2 negatives. |
| D FINISH + section 2 fitness | FINISH PASS (pass 3) | IllustrationJaNai V3 DAT2 upscale (.venv-upscale) -> 2560x1440 conformance -> deband -> face/eye polish. Prereq QA fix: replace whole-image laplacian_variance (tools/lw_gen_qa.py:152; gate logic lw_gen_qa.py:93-116; floors tools/lw_gen_config.json:30-35, T_blur 150) with a subject/face-region sharpness measure - the face keypoints from the weapon-pass persistence give the crop for free. |

Iteration loop: generate -> scorecard -> weapon pass on FIX verdicts -> re-scorecard ->
repair pass -> re-scorecard -> finish pass -> golden-bar check -> operator ratifies ->
promote to images/0.Originals. Every re-scorecard line appends to the batch ledger so
element-level pass efficacy is trendable across batches.
