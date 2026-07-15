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

# 2026-07-15 (first-pass throughput - reprocess 5 + intake 47 + contamination-strip 4 + Pictures export)

Operational session; NO code changes (all pipeline data ops, gitignored). First Pass Done 179 -> 228; First Pass Scratch now EMPTY.
- **Reprocessed 5** (vayne3/morgana1/hwei1/shyvana1/soraka1): operator dropped corrected `_firstinitial` (Jul-12 re-crops removing a composite top-strip contamination); regenerated 2560x1440 firstdones. No reverse command exists -> reopen dance (stage scratch + move stale Done to a backup + lw_first_pass + approve). Backup deleted (operator eyeballed). See memory `project-reprocess-done-slug`.
- **Intake 47** new originals -> first-pass: 34 PASS + 11 FLAG (borderline halo, spot-checked clean) = 45 approved; 2 HELD dropped (seasonal-key-art/viktor: low-res + off-aspect; DA originals quota-blocked) to `data/dropped_20260715/`.
- **4 remaining** (camille1/fiora1/kaisa1/xayah1): SAME top-strip contamination (seam row 242, batch-consistent), operator-rejected pending re-crop but never re-cropped. Auto-stripped + subject-aware 16:9 + processed + approved.
- **Pictures export:** copied all 228 firstdones to Pictures (operator moved them flat to root).

**NEXT / do-not-redo:** lw-gen M2 bless remains the top ROADMAP item (unchanged - this session did not touch lw-gen). Downstream stages (cleaning/final) still empty. Recovery campaign for the ~82 sub-1280px sources deferred until the DeviantArt weekly download quota resets. Do NOT re-fetch the 2 dropped (DA has nothing better quota-free). New memories: `project-reprocess-done-slug`, `reference-deviantart-recovery`.

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
