# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12) - keep the last 3.

---

# 2026-07-12 (M2 W2 reference-transplant rung - SHIPPED + e2e-proven; canonical bless DEFERRED)

Shipped + pushed (commit 44cb0f2); CI green; full suite 436 passed / 4 skipped; ruff + hygiene clean.
- **Built (subagent-first, 2 disjoint parallel slices, TDD, first-party verifier gate):**
  forearm_frame(kp_map,wrist,img_wh) extracted in lw_gen_weaponfix (weapon_roi delegates, mask
  byte-identical). NEW tools/lw_gen_weapon_assets.py = AssetMeta + load_assets/pick_asset/
  affine_transplant (pure PIL, torch-free; anchor tracked through PIL y-down expand-rotate).
  lw_gen_weaponpass rung=="w2": forearm_frame -> pick_asset -> ROI mask -> affine-paste crop ->
  masked SDXL inpaint over w2_strength [0.35,0.45,0.5] -> paste-back into the ORIGINAL (outside-mask
  identical) -> operator lane saves every roll; no_forearm/no_asset -> review. +24 tests.
- **Assets (gitignored tools/models/weapon_assets/vayne/):** 5 feathered RGBA crossbow crops +
  meta.json (default/dragonslayer/sentinel/project/aristocrat), geometry spot-checked on previews.
- **E2e (real DWPose+SDXL, seed22/seed33/seed800):** pipeline proven; seed800(default)+seed22 = 3
  rolls each, outside_mask_identical=True; seed33 correct face_intersect skip. Artifacts:
  images/_gen_scratch/w2_e2e/ + w2_e2e_default/ (gitignored).

**OPERATOR-DEFERRED (the M2 exit):** operator reviewed the rolls, "not sure", did NOT bless. Honest
first-party read: the transplant harmonizes (strength 0.35-0.50) into a generic silver MECHANICAL
hand-device - crossbow-adjacent, not an unambiguous bat-wing repeating crossbow - and the original
wrong weapon persists OUTSIDE the wrist-only mask. One operator-directed escalation (force the
canonical default crop on seed22, replacing the weak dragonslayer auto-pick) only marginally changed
the read: the low-strength harmonize plateaus.

**NEXT / do-not-redo:** operator to bless a current roll (M2 exit met) OR authorize a design lever -
W3 IP-Adapter (mechanism C, ~3.2GB one-time downloads; injects the crossbow CONCEPT - the design's
intended fix for exactly this "pasted-on / wrong-read" case) and/or a mask-widen to remove the 2nd
weapon (old_weapon_coverage scaffolding exists in lw_gen_weaponfix). Do NOT rebuild W2 / assets /
rung / forearm_frame; do NOT re-run the force-default-crop experiment (measured plateau); do NOT
retune the dead ViT-L-14 CLIP gate. Still operator-blocked: GOLDEN_DEFINITION.md sec 6 Q1-Q4.

---

# 2026-07-12 (M1 weapon-region CLIP gate - CLIP is DEAD, operator-lane shipped)

M1-finish. Built the weapon-region CLIP gate (design_weapon.md sec 6) + calibrated it.
**The CLIP gate CANNOT separate** canonical-crossbow crops from wrong-weapon crops ->
shipped the pre-authorized operator-lane fallback (GOLDEN_DEFINITION.md:120, T_aes
dead-gate precedent). Full suite 413 passed / 4 skipped; ruff clean.
- **Built (TDD RED-first, 3 coupled slices, main-thread):** lw_gen_qa.py = pure
  weapon_grade (4-clause: offclass -> weak_margin -> mush) + WeaponScore + WeaponClipScorer
  (lazy open-clip, 3 positives / 8 distractors) + resolve_weapon_thresholds + --weapon-crop
  JSON helper (shelled to .venv-metrics). lw_gen_weaponfix.py = pad_bbox. lw_gen_weaponpass.py
  = gated rolls loop (K<=4, first PASS wins) + gate_mode branch. config weapon{} block.
- **Calibrated live** (scratchpad/weapon_calib.py, cross-venv): 19 official skins vs all
  localizable gen candidates (DWPose cropped 9/19 + 30/42). weapon_cos overlaps totally
  (GOOD 0.13-0.22 / BAD 0.11-0.21); margin NEGATIVE on every crop (CLIP ranks generic
  weapon/hand text above "crossbow" on stylized art; the DEFAULT skin fails a floor 6 bad
  candidates clear). 3 configs all fail (1/9, 2/9, 3/9 good-PASS). The sec-6 top-2
  re-measure did NOT rescue it. Root cause = ViT-L-14 can't resolve painted weapon subtype.
- **Shipped fallback:** config weapon.gate_mode="operator" (DEFAULT) -> W1 saves EVERY
  roll to weapon_review/ for operator blessing, no auto-accept. gate_mode="clip" stays
  wired for a future scorer. T_weapon/T_wmargin DORMANT (not calibrated).

**NEXT session:** M2 W2 transplant (design_weapon.md mechanism A: affine crossbow crop +
guided inpaint 0.35-0.50) is now THE path to canonical - acceptance via the operator lane.
Do NOT re-attempt the ViT-L-14 CLIP gate calibration (dead, 3 configs) - a new gate needs a
NEW scorer (weapon LoRA / fine-tune / DINO). Do NOT rebuild gate logic / rolls loop /
localizer / slices 1-2 / weapon pass W1. Still operator-blocked: GOLDEN_DEFINITION.md sec 6.

---

# 2026-07-12 (M1 weapon pass W1 - DWPose-wrist masked SDXL inpaint SHIPPED)

Shipped + pushed (commit 834b74e); full 3-suite 55 passed / 1 skipped; e2e green.
- **Wired** the adopted DWPose localizer into lw_gen_run's real detect -> mask ->
  inpaint. New tools/lw_gen_weaponpass.py (4th gen-sidecar stage): dwpose_backend ->
  operator-picked wrist -> REUSED weapon_roi_from_keypoints (slices 1-2, UNCHANGED)
  -> AutoPipelineForInpainting.from_pipe(base, controlnet=None) W1 re-roll (strength
  0.92) -> hard paste-back + outside-mask identity assert -> cand[file] _wfix -> re-QA.
  Propose mode (no --wrist) = both-wrist overlays; a fallback -> review, never inpaints.
  run.py flags --weapon-fix / --wrist / --weapon-rung / --weapon-only / --weapon-min-conf;
  _shell_stage +extra_args.
- **Built** TDD RED-first (build subagent) + first-party verifier gate (I re-ran the
  suite + read the module/test/diff, NOT the subagent's counts). 10 torch-free tests.
- **E2e acceptance** seed42/right (two-venv chain: real .venv-gen SDXL inpaint +
  .venv-metrics re-QA): cand_00_wfix.png, mask from DWPose RWrist 0.877,
  outside_mask_identical true, re-QA PASS (subj 0.296 / margin 0.073 / lap 449).
  design_weapon.md sec 7's "lw_gen_weaponfix.py" name was already taken by slices 1-2
  -> new stage is lw_gen_weaponpass.py; the doc predates DWPose (sec 4 assumes OpenPose).
- **Pruned** ops/budget_saver/ (operator: no longer relevant).

**Scope:** built to the WAKEUP acceptance (mask-from-DWPose-wrist + identity + existing
full-image re-QA), DEFERRED the weapon-region CLIP gate (design_weapon.md sec 6) - the
existing re-QA proves plumbing + subject non-regression, the deferred gate proves the
weapon is CANONICAL.

**NEXT session:** (1) weapon-region CLIP gate calibrated on ~21 known-bad + 19
official-skin crops; (2) W2 transplant (mechanism A: affine crossbow crop + guided
inpaint 0.35-0.50). Do NOT redo the localizer / slices 1-2 / weapon pass / SDPose or
re-run the e2e. Still operator-blocked: GOLDEN_DEFINITION.md sec 6 Q1-Q4.
