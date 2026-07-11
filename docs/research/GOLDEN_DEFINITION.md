# lw-gen GOLDEN DEFINITION - seed rubric (2026-07-11)

Seed material for the next session's task: use fable-5 ultraplan + adversarial
full-res review to explore the repo + the accepted "barely okay" images and
DEVELOP the golden definition/rubric. Golden is reached by ITERATIVE passes, not a
single superficial tweak. This file is the starting point, not the finished rubric.

Strict ASCII. The operator is ground truth for "golden".

## Where we are (2026-07-11)
The generation recipe is DIALED and CONSISTENT (canonical, feminine, clean-DoF anime
Vayne every draw - see GEN_RETUNE.md "WINNING RECIPE v2"). But raw 1344x768
single-pass SDXL (Animagine XL 4.0 + ControlNet-OpenPose) plateaus at "good fan
splash", NOT golden. Across a 26-image volume batch the operator accepted only ~2-3
as "barely okay to start". The gap to golden is per-image correctness of specific
canonical elements, plus a real polish/finish pass - not more prompt nudging.

## Operator seed critique (verbatim, exp4_volume 16-seed batch)
This is the raw material for the rubric. Each line = one candidate + why it fails.
- seed 1: mangled hand - weapon isnt a weapon
- seed 2: malformed posture, weapon, face
- seed 3: odd composition for the arrow to be in flight, missing right arm
- seed 5: face, posture, weapon are all malformed
- seed 8: face, posture, weapon are all malformed
- seed 17: odd weapon, face isnt right for clarity of head position / eyes
- seed 29: weapon and head posture, sizing are incorrect
- seed 42: weapon, left hand, head posture are odd and off or malformed
- seed 54: weapon and shoulderpads are scaled and positioned wrong + hand & glasses are janky
- seed 99: weapon position/scale is incorrect, left hand is positioned weird for the pose, off wing/cape effects
- seed 150: weapon choice is wrong, glasses are not glasses, right hand seems malformed but is blurry not sure
- seed 222: glasses, shoulder/body posture, arm, weapon are all incorrect one way or another
- seed 314: weapon, and face are off - posture is okay
- seed 404: weapon is wrong, cape is off, glasses are off, cowl is off
- seed 606: bad posture angle, face is off, weapon is wrong
- seed 800: is okay except for glasses, weapon (closest of the batch)

## Failure taxonomy (ranked by frequency in the critique)
1. WEAPON (dominant, ~15/16): wrong/malformed/miscast. Vayne's canonical weapon is a
   wrist-mounted repeating crossbow firing short silver bolts - the model instead
   renders random blades, longbows, axes, oversized/miscaled props. THE #1 golden
   blocker. Likely needs explicit weapon conditioning (reference/inpaint/LoRA), not a
   prompt token.
2. HANDS: mangled / miscounted / mispositioned for the pose (seed 1, 42, 99, 150).
3. FACE + HEAD: head posture/angle, sizing, eye clarity off (seed 2,5,8,17,29,42,314,606).
4. GLASSES: the signature round red-tinted glasses render as not-glasses / janky /
   deformed (seed 54,150,222,404,800).
5. POSTURE / BODY: malformed or awkward posture, shoulder/body angle (seed 2,5,8,222,606).
6. CANON KIT: cape, cowl, shoulderpads off-model or misscaled (seed 54,99,404).
7. COMPOSITION: incoherent action (arrow-in-flight logic, missing arm) (seed 3).

## Accepted "barely okay" reference set (current bar, for next-session review)
On disk (gitignored scratch - review at FULL RES; not yet promoted anywhere):
- images/_gen_scratch/exp3_clean/seed22.png (sharp subject + clean DoF; gate wrongly
  rejected it as blurry - see the T_blur finding in GEN_RETUNE.md)
- images/_gen_scratch/exp3_clean/seed33.png (both hands cleanly on weapon - Riot hand
  formula; strong)
- images/_gen_scratch/exp4_volume/seed800.png (closest of the volume batch)
- images/_gen_scratch/vayne-controlnet-proto/cand_01.png + cand_02.png (earlier
  "getting kinda close" - cand_02 was a near-empty skeleton = free composition)

## Next-session plan (operator directive)
fable-5 ultraplan + adversarial review over FULL-RES context. Explore the repo +
the accepted images above. Develop the golden rubric from the taxonomy. Then design
the ITERATIVE path to golden - candidate weapon fix (the #1 blocker), face/eye + hand
+ glasses repair passes, and the polish/finish to 2560x1440. Not superficial; expect
multiple passes. The QA gate's sharpness metric needs the subject-region fix
(GEN_RETUNE.md) before it can rank golden candidates honestly.
