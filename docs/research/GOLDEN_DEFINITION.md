# lw-gen GOLDEN DEFINITION - rubric v1.1 + iterative path (2026-07-11)

Deliverable of the fable-5 ultraplan + adversarial full-res review session (3 workflows,
98 agents, all designs adversarially verified) PLUS the full operator-corpus deep dive
(179 firstdone + 273 reference_pictures = ~452 notations, spot-audited FAITHFUL).
Strict ASCII. The operator is ground truth for "golden"; this doc is DRAFT until the
ratification questions in section 6 are answered.

Source artifacts:
- Corpus premise + anchors: docs/research/corpus/CORPUS_PREMISE.md + CORPUS_ANCHORS.md
- Per-image notations: docs/research/corpus/notes_*.json (+ audits, pHash correlation)
- Full pass designs + adversarial verdicts: docs/research/golden_designs/ (weapon,
  face_hands, finish, qa_fix, rubric + VERDICTS.md)
- Champion-label queue for the operator: docs/research/corpus/CHAMPION_UNKNOWNS.md
- Recipe v2 + QA calibration (unchanged, settled): docs/research/GEN_RETUNE.md

## 1. THE GOLDEN RUBRIC v1.1 (operator-facing)

Grades per element: 2 = golden, 1 = okay/fixable, 0 = fail, X = not visible/NA.
Severity: BLOCKER = auto-reject; MAJOR = must fix before golden; MINOR = polish.
Addressability: which pass can fix a 0/1 (REROLL = only a fresh seed fixes it).

| # | Element | PASS criteria (Vayne) | Severity | Addressable by |
|---|---------|----------------------|----------|----------------|
| W | WEAPON | EITHER (a) repeating crossbow RIG on the RIGHT FOREARM (strapped, bat-wing limbs, silver+navy, forearm-scaled) OR (b) a corpus-sanctioned DODGE: stylized wing-rig behind shoulder, ornate crystal crossbow lowered/folded, blurred-backdrop silhouette, or confidently absent (see sec 3 - 7 of 9 corpus Vayne 5s use a dodge). NOT a longbow/axe/blade, NOT fused into the arm, NOT torso-scaled, NOT a fiddly literal mechanism. | BLOCKER if wrong class / fused / torso-scale. MAJOR if right class but handheld/misscaled. | WEAPON PASS (fix lane) or GENERATION (dodge lane) |
| H | HANDS | Correct count + chirality, GLOVED (all 13 corpus Vaynes are gloved - zero bare-hand risk), plausible at a glance. Riot formula (both on weapon / one occluded / hidden) is a first-class PASS route, never a penalty. | BLOCKER if mangled/extra/fused/second-left-hand. MAJOR if awkward. | REROLL if chirality/missing-wrist (structural); REPAIR PASS otherwise |
| F | FACE | Sharp angular face, high cheekbones, arched brows, determined scowl, dark crimson lips, winged liner; head angle consistent with body; face = crispest region in frame (corpus: focal-face quality is the single highest-leverage axis). | BLOCKER if off-model/malformed/wrong gender read. MAJOR if angle/size/expression drift. | REPAIR PASS |
| E | EYES | Both eyes coherent behind lenses, gaze matches pose, no smear at full res. Opaque lens glare is corpus-accepted. | MAJOR (BLOCKER if smeared to noise). | REPAIR PASS (operator-flag trigger) |
| G | GLASSES | Red-TINTED glasses resting on the nose, both lenses distinct, eyes visible through tint OR clean glare. NOT a visor/half-mask/absent. SHAPE (round vs narrow-angular) = OPEN operator question (sec 6 Q1) - canonical ref reads narrow-angular at full res, not round. | BLOCKER if not-glasses (mask/visor/absent). MAJOR if glasses but wrong shape once Q1 is answered. | REPAIR PASS (visor mode auto-trigger; shape modes operator-flag) |
| R | HAIR | Dark violet-black, HIGH BUN + long ponytail both present, windblown motion consistent with pose. | MAJOR if bun missing. BLOCKER if wrong color (blonde/bright). | GENERATION (prompt) + REPAIR PASS escalation |
| K | KIT | Bat-wing pauldrons at shoulder scale, deep navy bodysuit, crimson cape LINING reading as cape, high collar, thigh boots if legs in frame. | MAJOR if misscaled/miscast; MINOR trim drift. | REROLL (structural) / REPAIR (local) |
| P | PALETTE | Crimson/black/gold OR navy+crimson+silver (both corpus-proven Vayne modes), PALE skin (no lavender drift), unified 2-3 hue grade + accent glow. | MAJOR (skin drift = MAJOR; full palette miss = BLOCKER). | GENERATION (prompt) |
| S | POSE/POSTURE | Anatomically coherent deliberate pose at ANY energy (corpus: stillness and max action both earn 5s; stiff mannequin costs 2 notches), believable line of action, no missing/extra limbs. | BLOCKER if malformed/missing limb. MAJOR if stiff/awkward. | REROLL only (skeleton curation; NOT repairable) |
| C | COMPOSITION | Single focal hierarchy, action logically coherent, no giant blurry prop eating half the frame, negative space works FOR the subject. | MAJOR. | REROLL only |
| B | BACKGROUND | Subordinate clean-DoF gothic environment; mush is fine and corpus-free; never sharper than the face; NO text/watermark/signature EVER (generated text = auto-reject, no cleaning-debt excuse). | MINOR (MAJOR if clutter competes; BLOCKER if generated text/watermark). | GENERATION (v2 negatives) + FINISH deband |
| D | FINISH/DETAIL | Splash-grade micro-detail in the focal zone (armor edges, hair strands, glass specularity), no banding/smear/halos. Corpus bar: finish >= 3 to exist, 4-5 to aspire. | MAJOR pre-finish (every raw gen fails today); BLOCKER at promotion. | FINISH PASS |

### Scorecard (one line per candidate, machine-parseable; stage field added in v1.1)

```
VAYNE|<batch>|<seed>|<stage:raw/W/repair/finish>|W:0-2|H:0-2|F:0-2|E:0-2|G:0-2|R:0-2|K:0-2|P:0-2|S:0-2|C:0-2|B:0-2|D:0-2|verdict:REJECT/FIX/HOLD/GOLD|note:<free>
```

REJECT = any BLOCKER 0 whose Addressable column says REROLL. FIX = 0/1 only on
pass-addressable lines. HOLD = operator parks. GOLD = section 2 bar.
Trend metric: count of W:0 per batch per stage = weapon-lane efficacy.

## 2. THE GOLDEN BAR (promotion to 0.Originals)

ALL must hold:
1. W, H, F, G, S all score 2 (weapon via fix lane OR dodge lane).
2. No 0 anywhere; at most TWO 1s, only on B or K-trim.
3. Wallpaper fitness at final 2560x1440: exact fill; face center in upper-third band
   (15-45 pct from top); no BLOCKER element in the bottom 60 px or within 3 pct of
   side edges; silhouette reads as Vayne at 25 pct zoom; left third may stay quiet
   (icon zone).
4. D scores 2 AFTER the finish pass (raw single-pass never promotes - plateau finding).
5. QA gate passes WITH the subject-region sharpness metric (sec 5), not global lap_var.
6. Corpus check: candidate would sit at >= 3 on the corpus scale (CORPUS_ANCHORS.md
   sec 2) - the operative floor is A: stellastria-ahri / B: 32_cleanup tier.
7. Operator signs the card. The rubric ranks; the operator ratifies. No auto-promotion.

Program stop condition (GAP 9): golden reached when >= 3 operator-blessed GOLD
candidates from >= 2 different batches exist. Per-candidate ladder budget: max 2 weapon
attempts + 2 repairs/element (5 total) + 1 finish; a full-ladder candidate costs ~4-6
SDXL loads wall-clock - a REROLL costs the same as ONE repair attempt, so REROLL is the
correct tool for structural fails (S/C/K, chirality).

## 3. WHAT THE CORPUS TAUGHT US (grounding for every criterion above)

- Style band: current anime-flat recipe sits in a 1.6 pct niche (7/451) of the
  operator's demonstrated taste; ALL nine corpus Vayne 5s are painterly-semireal.
  Nearest reachable band for the locked Animagine base = anime-painterly-hybrid
  (24 pct): painted shading, rim/backlight, bloom, material speculars - the v2 recipe
  already half-way there. Sec 6 Q2 puts the steer to the operator.
- Vayne weapon (13 data points): NEVER a literal fiddly mechanism. Proven treatments:
  gold wing-rig behind shoulder, crystal crossbow folded/raised, wrist-mount, energy
  bow, blurred-backdrop silhouette, bolt shards with no weapon, absent. Crisp-and-
  ornate when visible, otherwise dodge boldly. This legitimizes the DODGE LANE as a
  first-class golden route alongside the forearm-rig fix.
- Hands: gloved always; hiding is a sanctioned strategy used by 5s; visible fused
  fingers cap at 3-4; a wrong hero hand thrust at camera is the riskiest composition.
- Face: the non-negotiable; melt/watermark ON the focal face = corpus floor (2).
- Palette: crimson/black/gold is the modal Vayne mode; navy+crimson+silver canonical
  default; icy crystal, white-gold high-key, violet spirit-flame all proven alternates.
- Scale anchors: 5 = bo-chen-firecracker / 100f.png; 3 = minimum promotion bar;
  2 = reject (seams, focal melt); 1 = outside corpus entirely.

## 4. ITERATIVE PATH TO GOLDEN (orchestrator spec; closes VERDICTS GAPs 1-10)

M0 - FOUNDATIONS (one session, BEFORE any pass code; GAPs 1,2,3,6):
  a. Config flip (Tier-1 + test): lw_gen_config.json model_path -> Animagine, steps 28
     (flagged by ALL FIVE verdicts); rule: every pass reads checkpoint from
     manifest[model], never config.
  b. Shared tools/lw_gen_pose.py: detect_poses on each CANDIDATE (not the batch ref -
     cn 0.55 candidates drift from the shared skeleton), mirroring __call__
     preprocessing (HWC3 + resize_image 512), sentinel handling (None body kps,
     negative hand/face coords), persisted per-candidate keypoint JSON.
     ONE recall gate: contact-sheet overlay on the 5 refs + 1 reject; operator confirms
     boxes land on the element in >= 5/6. TDD list per repo rule.
  c. Plan B if the recall gate FAILS (OpenPose-on-anime unproven): QA keeps the
     keypoint-free center-upper crop; weapon/repair fall back to operator-drawn masks
     (IOPaint lane, mirrors cleaning-pass); everything else = REROLL.
  d. Rubric v1.1 ratification: operator answers sec 6; scorecard adopted on next batch.
  e. Manifest contract (GAP 4): every pass rewrites cand[file] to its latest artifact
     (raw -> _wfix -> _repair -> _finish), keeps a provenance list + stage field; QA
     and promote key off cand[file] (lw_gen_qa.py:327-332, lw_gen_promote.py:205-235).

M1 - WEAPON PASS (tools/lw_gen_weaponfix.py; the #1 blocker; design_weapon.md):
  Rungs, cheapest first: W1 keypoint-masked inpaint re-roll (<= 4 rolls, weapon-dense
  local prompt) -> W2 reference transplant + harmonize inpaint (affine-fit official-
  skin crossbow crop to wrist, strength 0.35-0.5; face never in mask; hard paste-back
  keeps outside-mask pixels bit-identical) -> W3 IP-Adapter image-prompt (verified
  available on the 0.39 SDXL inpaint pipe) -> W4 weapon-concept LoRA (default-rig
  crops only, avoid skin dilution). PLUS the free DODGE LANE from sec 3: a prompt
  variant per batch steering to wing-rig/absent-weapon compositions.
  Verdict fixes baked in: mask must also cover the OLD wrong prop (extends along the
  prop axis; measured >= 95 pct old-weapon coverage on the 21 known-bads before W2),
  pipe loads from_single_file in its own process (no from_pipe from gen), weapon-region
  CLIP gate needs a numeric separation target on official-crop vs known-bad crops with
  an operator-lane fallback if CLIP cannot separate (T_aes dead-gate precedent),
  per-rung acceptance numbers (W1 salvage >= 20 pct; W2 >= 50 pct operator-pass on the
  3 accepted refs), M2 exit >= 3 operator-blessed weapon fixes.

M2 - REPAIR PASS (tools/lw_gen_repair.py; design_face_hands.md): verify-then-repair
  crop-upscale-inpaint (ADetailer pattern in raw diffusers). Auto-triggers ONLY where
  calibratable: face-crop lap_var (fixed 256px crop before scoring) + glasses 3AFC
  (round-vs-visor-vs-none; covers visor mode only - shape modes stay operator-flag).
  Hands = operator-flag only; NEVER inpaint chirality/missing-wrist (structural ->
  REROLL). Order: weapon -> hands -> face -> glasses -> eyes (weapon inpaint often
  fixes hands free; face boxes nest). Outside-mask identity assertion on every repair;
  before/after contact sheet; retry caps 2/element, 5/candidate.

M3 - FINISH PASS (tools/lw_gen_finish.py; design_finish.md): crop 1344x768 -> 1344x756
  exact 16:9 (12 rows; all keypoint consumers operate PRE-crop, -6 px y contract) ->
  optional Animagine img2img refine at 2048x1152 strength 0.30 (adopt ONLY after an
  operator 2AFC of refine-vs-raw at 2560x1440 on seed22/33/800 - unproven that it adds
  painted texture; keep-raw fallback on subject-region sharpness loss) -> proven
  Stage-1 chain post-intake (JaNai V3 DAT2 x4, single Lanczos to 2560x1440, USM, G1).
  Promotion boundary unchanged: lw-gen stops at 0.Originals (ADR-003).

M4 - LOOP (GAP 5): gen (recipe v2 + dodge-lane variant) -> QA -> scorecard (operator,
  one contact-sheet session per iteration) -> REROLL structural fails / WEAPON pass on
  W:0 FIX cards -> re-scorecard -> REPAIR -> re-scorecard -> FINISH -> golden bar ->
  promote. Residual policy (GAP 7): S/C/K fails REROLL against a per-batch draw budget;
  glasses shape modes + eyes stay operator-flag; per-candidate skeleton cycling is the
  only lever that raises the S/C base rate (deferred feature, now priority-tagged).

## 5. QA FIX PLAN (subject-region sharpness; design_qa_fix.md)

Ship: dual metric - lap_var_subject on the fixed center-upper crop (x 25-75 pct,
y 5-65 pct, pure numpy, keypoint-free so it survives a Plan-B world) becomes the
Stage-B gate with its OWN floor T_blur_subject; global lap_var demoted to advisory.
Calibrate offline from already-graded batches + the synthetic blur sweep (NO new
operator sweep): acceptance = seed22/33/800 + cand_01/02 + 6 tuned candidates PASS,
every blurred variant REJECTS, plus at least one natural soft-face negative or the
gate scope is recorded as catastrophic-blur-only. Keypoint face-crop lap_var stays a
repair-pass trigger + QA ADVISORY (GAP 8 precedence). TDD: update
tests/test_lw_gen_qa.py:21 (4-key THRESH dict) + :119 (exact threshold-set assert);
grade() reads T_blur_subject via .get(). Backfill: re-grade flips seed22's historical
false-reject to PASS. T_blur=150 stays for the global advisory only.

## 6. OPERATOR RATIFICATION QUESTIONS (blocking rubric v1.1 -> v1.2)

Q1 GLASSES SHAPE: rubric said "small ROUND spectacles" but vayne_00_default at full
   res reads narrow-angular red-tint (seed800's cat-eye may be closer to canon than
   graded). Which shape is golden: round, narrow-angular, or either-if-crisp?
Q2 STYLE BAND: corpus mass is painterly-semireal (64 pct, all Vayne 5s); locked recipe
   is anime-flat (1.6 pct niche). Steer prompts toward anime-painterly-hybrid within
   the Animagine base (painted shading/rim light/bloom - recommended), stay pure
   anime-flat, or re-open the base choice (currently SETTLED)?
Q3 WEAPON DODGE LANE: confirm that a corpus-style dodge (wing-rig / folded crystal /
   blurred silhouette / absent) counts W:2 golden, or must every golden Vayne carry
   the literal forearm rig?
Q4 SCORECARD: adopt the pipe format + severity/addressability table as-is?

## 7. Operator seed critique + failure taxonomy (historical input, unchanged)

Preserved verbatim from the 2026-07-11 seed - the raw material the rubric encodes.

### Seed critique (exp4_volume 16-seed batch)
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

### Failure taxonomy (ranked by frequency)
1. WEAPON (~15/16) 2. HANDS 3. FACE+HEAD 4. GLASSES 5. POSTURE/BODY 6. CANON KIT
7. COMPOSITION. (Weapon = #1 golden blocker; hands/face/glasses/posture follow.)

### Accepted "barely okay" reference set (current bar)
images/_gen_scratch/: exp3_clean/seed22.png, exp3_clean/seed33.png,
exp4_volume/seed800.png, vayne-controlnet-proto/cand_01.png + cand_02.png.
