# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16) - keep the last 3.

---

# 2026-07-16 (W4 M3 rung==w4 SHIPPED; LoRA trained; weapon-quality investigation -> CEILING, PARKED)

Long session; 1 commit (0c255d8 M3) + docs. Full suite 458 passed / 4 skipped (+5 W4); CI green; ruff + ASCII clean; pushed. Ran the queued handoff to completion, then an operator-driven investigation into weapon quality that concluded NEGATIVE (a measured ceiling).

- **W4 M3 (LEDGER 26, 0c255d8):** ran the full ~15-min LoRA train (93MB, loss 0.03, peak 7.33GB) FIRST, then wired rung=="w4" in weapon_pass (build subagent, TDD RED-first, first-party full-suite verify + full-diff read). _build_real_inpainter gains weapon_lora (load_lora_weights adapter_name=vayne_weapon + set_adapters 0.8 + offload re-apply + pass-scoped .unload_lora handle); rung==w4 block = W1-style masked rolls + "vaynecrossbow" prompt prepend + no_lora fallback; unload after the loop. config weapon_lora_path/scale/trigger + _note_w4. +5 tests. CLI needed zero change. E2e seed22/33/800 clean (LoRA loads/guides/unloads, outside_mask_identical, seed33 face_intersect).
- **Weapon-quality investigation (all NEGATIVE):** (a) v1 e2e = plateau (dark-bat-wing/silver-shard, best seed800). (b) LoRA-scale 0.8->1.1 = no change. (c) splash pool EXHAUSTED for clean crossbow crops (re-checked all 19 + auto-crops; even demoncursed = a blade). (d) research + POC: modelviewer.lol is Cloudflare/blob-blocked; CommunityDragon serves the raw .skn -> built + PROVED a 3D crossbow-render pipeline (pyritofile parse + bone-set isolation + moderngl headless render on the 5070, pip-only; docs/research/crossbow_render_poc.md) -> 4 clean base crossbow renders (themed skins isolate poorly). (e) v2 LoRA on 10 crops (6+4 renders) = v2 == v1, no improvement.
- **Verdict:** the crossbow-adjacent read is a CEILING of masked-inpaint + thin-LoRA on stylized art, not a data gap. Operator PARKED the weapon-quality quest; rung=="w4" stays wired + available.

**NEXT / do-not-redo:** weapon-pass quest is PARKED - do NOT re-run any rung/scale (plateau measured 5x), re-mine splashes (exhausted), or build the full 20-skin render pipeline (base geometry proven not to help). rung=="w4" is available for hand-picked per-wallpaper use. LOCAL-only (gitignored, not in repo): tools/models/lora_datasets/vayne_weapon_train now holds 10 crops (6 + render_base_*.png); vayne_weapon (v1) + vayne_weapon_v2 LoRAs; .venv-poc; images/_gen_scratch/w4_* batches. The 3D-render pipeline is reusable for OTHER champions/purposes only (per docs/research/crossbow_render_poc.md). Stray untracked style.jpg/style2.jpg at repo root are pre-existing, NOT from this session.

---

# 2026-07-16 (M2 weapon pass - W3 IP-Adapter SHIPPED + swept, escalated to W4 LoRA; W4 M1 curation + M2 trainer built + smoke-proven)

Big session; 3 commits (0204cfa W3, 7657356 curation tool, 70838da LoRA trainer); full suite 453 passed / 4 skipped (+17); ruff + ASCII clean; all pushed. Operator drove the weapon-pass decision ladder via framed forks; I built + FIRST-PARTY-verified each rung (re-ran suites + read diffs + ran my own smoke, never trusting subagent counts).

- **W3 IP-Adapter (LEDGER 23, 0204cfa):** operator picked W3 at the M2 bless fork. Built the rung (mirrors W2 + an ip_adapter_image concept image) after grounding load_ip_adapter/set_ip_adapter_scale against installed diffusers 0.39. Downloaded h94 vit-h (~3.2GB, gitignored). Found + fixed a real OFFLOAD BUG at e2e: the base pipe gets enable_model_cpu_offload BEFORE load_ip_adapter registers the image_encoder -> encoder stuck on CPU -> re-run offload after load (idempotent). E2e-proven. HONEST: default scale-0.7 PLATEAUS like W2 (ornate mechanical props); an operator-directed sweep (default crop + scale 0.9 + str 0.6) is the best-yet on seed22 (reads as a mechanical weapon rig) but still not a textbook repeating crossbow, and meh on seed800.
- **Escalation to W4 LoRA:** operator chose W4 (mechanism D) over bless / mask-widen / skip. Plan subagent spec'd it; I re-verified: NO trainer exists in-repo (the "proven path" was RC-inherited) -> build it; peft 0.19.1 present, bitsandbytes absent -> adamw; single-file model -> from_single_file path b (zero downloads).
- **W4 M1 curation (LEDGER 24, 7657356):** built tools/lw_gen_curate_weapon_crops.py (DWPose auto-crop + asset composite + object-only captions). E2e over 19 splashes yielded 8 localized (mostly junk on stylized art - faces/Poros/wrong-hands/blades) + 5 assets; truly-clean = 6 (5 hand-made assets + dragonslayer). Operator chose "probe-train the clean core + augment". Assembled tools/models/lora_datasets/vayne_weapon_train/ (6 crops).
- **W4 M2 trainer (LEDGER 25, 70838da):** built tools/lw_gen_train_weapon_lora.py (in-house UNet-only SDXL LoRA, path b). SMOKE proven twice (subagent + my independent re-run, matching numbers): 2 steps no OOM/NaN, 93MB pytorch_lora_weights.safetensors, round-trip load+set_adapters+unload. Peak 7.33/12GB, ~1.0s/step -> full 1000-step run ~17 min.

**NEXT / do-not-redo (operator: the real train is a FRESH session):** (1) run the ~17-min full train: `.venv-gen python tools/lw_gen_train_weapon_lora.py` -> tools/models/loras/vayne_weapon. (2) M3 = wire rung=="w4" in weapon_pass (W1-style masked reroll + LoRA on the inpaint pipe + "vaynecrossbow" trigger prepend + unload after; mirror the W3 _build_real_inpainter seam; config weapon_lora_path/scale/trigger; no_lora review fallback) + TDD (mirror the W3 tests) + e2e on seed22/33/800 -> operator bless. If the thin-data probe LoRA underperforms: hand-crop ~10-15 clean crossbows + retrain. Do NOT rebuild the trainer / curation tool / dataset; do NOT re-run W2/W3 (plateau measured), retune ViT-L-14 (dead), or re-attempt SDPose (mmcv/Blackwell-blocked). Stray untracked at repo root (style.jpg, style2.jpg, data/dropped_20260715/) are pre-existing, NOT from this session.

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