# LW session history archive

Deep archive for content pruned from the living docs. Nothing here is ever
rewritten - relocations are verbatim, newest batch first.

**Archival contract:**

- `WAKEUP_NOTES.md` keeps only the last 2-3 sessions at full fidelity. When it
  is pruned, the older session blocks move HERE verbatim under a
  `## Relocated YYYY-MM-DD (reason - keep last N sessions: ...)` header, and the
  WAKEUP_NOTES banner gains a pointer line naming what was archived.
- `docs/LEDGER.md` stays append-only; if it is ever pruned for size, the oldest
  item range relocates here verbatim (e.g. "items 1-N") and the LEDGER pointer
  line is updated to say so.
- `ROADMAP.md` shipped/closed entries do not accumulate - they live in the
  ledger; anything roadmap-shaped that must be preserved verbatim on prune
  lands here.

---

## Relocated 2026-07-16 (keep last 2 sessions: md-hygiene R3 pruned the 2026-07-16 W4-M3 weapon-parked session - quest PARKED, mirrored in docs/LEDGER.md item 26)

# 2026-07-16 (W4 M3 rung==w4 SHIPPED; LoRA trained; weapon-quality investigation -> CEILING, PARKED)

Long session; 1 commit (0c255d8 M3) + docs. Full suite 458 passed / 4 skipped (+5 W4); CI green; ruff + ASCII clean; pushed. Ran the queued handoff to completion, then an operator-driven investigation into weapon quality that concluded NEGATIVE (a measured ceiling).

- **W4 M3 (LEDGER 26, 0c255d8):** ran the full ~15-min LoRA train (93MB, loss 0.03, peak 7.33GB) FIRST, then wired rung=="w4" in weapon_pass (build subagent, TDD RED-first, first-party full-suite verify + full-diff read). _build_real_inpainter gains weapon_lora (load_lora_weights adapter_name=vayne_weapon + set_adapters 0.8 + offload re-apply + pass-scoped .unload_lora handle); rung==w4 block = W1-style masked rolls + "vaynecrossbow" prompt prepend + no_lora fallback; unload after the loop. config weapon_lora_path/scale/trigger + _note_w4. +5 tests. CLI needed zero change. E2e seed22/33/800 clean (LoRA loads/guides/unloads, outside_mask_identical, seed33 face_intersect).
- **Weapon-quality investigation (all NEGATIVE):** (a) v1 e2e = plateau (dark-bat-wing/silver-shard, best seed800). (b) LoRA-scale 0.8->1.1 = no change. (c) splash pool EXHAUSTED for clean crossbow crops (re-checked all 19 + auto-crops; even demoncursed = a blade). (d) research + POC: modelviewer.lol is Cloudflare/blob-blocked; CommunityDragon serves the raw .skn -> built + PROVED a 3D crossbow-render pipeline (pyritofile parse + bone-set isolation + moderngl headless render on the 5070, pip-only; docs/research/crossbow_render_poc.md) -> 4 clean base crossbow renders (themed skins isolate poorly). (e) v2 LoRA on 10 crops (6+4 renders) = v2 == v1, no improvement.
- **Verdict:** the crossbow-adjacent read is a CEILING of masked-inpaint + thin-LoRA on stylized art, not a data gap. Operator PARKED the weapon-quality quest; rung=="w4" stays wired + available.

**NEXT / do-not-redo:** weapon-pass quest is PARKED - do NOT re-run any rung/scale (plateau measured 5x), re-mine splashes (exhausted), or build the full 20-skin render pipeline (base geometry proven not to help). rung=="w4" is available for hand-picked per-wallpaper use. LOCAL-only (gitignored, not in repo): tools/models/lora_datasets/vayne_weapon_train now holds 10 crops (6 + render_base_*.png); vayne_weapon (v1) + vayne_weapon_v2 LoRAs; .venv-poc; images/_gen_scratch/w4_* batches. The 3D-render pipeline is reusable for OTHER champions/purposes only (per docs/research/crossbow_render_poc.md). Stray untracked style.jpg/style2.jpg at repo root are pre-existing, NOT from this session.

## Relocated 2026-07-16 (md-hygiene night run cycle 1: ROADMAP shipped/parked entry -> LEDGER 26 holds the record; prose preserved verbatim below)

- **lw-gen: weapon pass - SHIPPED end to end + PARKED at a quality ceiling (2026-07-16, LEDGER 26).**
  Full rung ladder is wired + shipped: W1 (LEDGER 20) + W2 transplant (22) + W3 IP-Adapter (23) +
  **W4 weapon-concept LoRA (26, commit 0c255d8: real train + rung=="w4" wired/tested/e2e'd)**.
  DONE-not-open. Weapon QUALITY plateaus at a crossbow-ADJACENT mechanical device (never a
  textbook repeating crossbow) - a measured CEILING of masked-inpaint + thin-LoRA on stylized
  splash art, confirmed 5x (W2, W3, W4-v1, W4-v2, LoRA-scale sweep). Data levers are exhausted:
  the splash pool has no more clean crossbow crops, and a proven 3D geometry-render pipeline
  (docs/research/crossbow_render_poc.md) added 4 clean base renders that did NOT move the needle
  (v2 == v1). Operator PARKED it here; rung=="w4" stays available. **Do NOT re-litigate:** no
  re-run of any rung/scale, no re-mining splashes, no full 20-skin render build (all measured
  dead ends). If ever revisited, the open lever is a non-inpaint mechanism or a separating weapon
  scorer to revive `gate_mode="clip"` - NOT more crop data.

## Relocated 2026-07-16 (keep last 3 sessions: WAKEUP added the 2026-07-16 W3-IP-Adapter / W4-LoRA session)

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

## Relocated 2026-07-11 (keep last 3 sessions: WAKEUP added the 2026-07-11 golden-definition session)

# 2026-07-07 (first-pass queue fully worked: needauth + crop-held + bucket-C recovery + 9 working triaged)

Operator-driven review pass. Commits 6c6006a + d441993 + 0c9b1f5 (last is
docs-only, CI path-ignored; first two CI green). `2.First Pass Done` 121 -> 179.

**Needauth (53 live):** 49 APPROVED, 4 REJECTED (xayah1/camille1/kaisa1/fiora1 -
source ingest artifact, a foreign strip on top; NOT a process fail).
**Crop-held (12):** A+B 4 hand-cropped to 16:9 + re-run + approved
(chengwei-pan-1/2, rey-jinn-up-2, tina-wei). Bucket-C 4 recovered + approved
(darius/fantasy-aivio/fury-sona via gallery-dl original=true; mfortune1 via local
2560x1440 twin Pictures/145_cleanup.png); 4 discarded (inkshadow, ashe, syndra,
wp-vayne). **9 working triaged:** image1/2/4/5 (800x450 alphacoders thumbs)
DISCARDED; elise-8k (clean 8K, spurious lpips-only downscale-only FAIL)
force-submitted + approved; 4 messups PARKED for manual re-source.

**NEXT:** (1) manual re-source the 4 messups (Battle Academia splashes; drop a
clean 1920x1080+ into 0.Originals + re-intake; Tier-0 found no local twin, no
token) OR (2) start the cleaning pass (Stage 2, /cleaning-pass) on the 179 Done.
**Do NOT redo:** the 57 approvals, the crop+recovery flow, the discards, elise
force-submit - all shipped. select_source prefers data/recovery/fetched/<slug>
fullviews over scratch _firstinitial (the crop-wrong-file trap; see LEDGER 12).

## Relocated 2026-07-05 (keep last 3 sessions: WAKEUP added the 2026-07-05 V3-promotion session)

# 2026-07-04 (QA Session 1 - first-pass stack live + G1 calibrated n=10)

First real pipeline runs. Installed the first-pass ML stack (py3.12,
`.venv-upscale` = torch 2.11+cu128 + spandrel on RTX 5070, `.venv-metrics` =
pyiqa 99 metrics); gallery-dl + imagehash on 3.14. Ran 10 images intake ->
first-pass -> operator-approved into `2.First Pass Done` (fiora2 + a 9-image
Found-original batch), full manifest audit trails. G1 calibrated n=10
(realesrgan-x4plus-anime fallback, USM70): MS-SSIM 0.984-0.993, LPIPS
0.047-0.144, GT LPIPS <= 0.097; tighter seeds in `AUDIT_GATES.md` 1.4 (pass
msssim >= 0.98, lpips <= 0.12).

Key: `reference_pictures` is a FR ground-truth goldmine (pHash dP=0 matches).
Found corpus (`Desktop\Found`, 121 folders) = 21 real originals + 97 still
`-pre`. Laplacian ratio is source-dependent, NOT an over-sharpen ceiling - need
a real overshoot detector.

**Do NOT redo:** the ML venv installs (done + gitignored `.venv-*/`); the 10
approved first-pass images. **Gaps:** no manifest verb for provenance/metrics
(ROADMAP NOW + spawned task); IllustrationJaNai primary weights still TODO (this
run used the ncnn fallback). **Next:** QA Session 2 - IJN primary path +
recalibrate; then the recovery campaign (149 pending, 75 `niphrimit` `-pre`).
**Queued:** artist-signature policy (watermarks on all Found originals);
LongPathsEnabled (deferred).

---

# 2026-07-18 (14-image first-pass batch delivered; G1 DISTS OOM root-caused + 63-manifest backfill; suite green again)

Two commits, both CI green: b14b688 (G1 common-scale cap + backfill), 7d1796b
(torch-free test isolation). Started as a routine batch, turned up two real
defects.

- **Batch (no code):** 14 uhdpaper originals intaken -> first pass -> approved
  -> copied to `C:\Users\Administrator\Pictures\` (sha256-verified, all
  2560x1440). Pictures 228 -> 242. All downscale-only (sources >= target, one
  Lanczos, no AI upscale). G1: 4 PASS / 10 FLAG (halo only) / 0 fail. Approved
  on evidence that flag-then-approve is the norm: 86 of 215 prior approvals
  carried FLAG, 83 over the halo line, max 0.2112 vs this batch's max 0.1291.
  Recovery: Tier 0 no match (nearest Hamming 15), Tier 1 n/a (no DA tokens),
  Tier 2 skipped (uhdpaper direct is already best-grade).
- **G1 DISTS OOM (b14b688, LEDGER 32):** DISTS was UNCOMPUTABLE at 8K, not
  slow - OOMs 12GB VRAM and system RAM both. 63 of 230 first-pass images had
  silently lost the metric. Fixed at the chokepoint both consumers share:
  `MAX_COMMON_PIXELS` (3840x2160) + `common_scale_for()` in lw_g1_gate, budget
  on pixel COUNT not side length, plus empty_cache between metrics. Backfilled
  all 63; coverage now 244/244, zero LPIPS-bad/DISTS-fine divergences.
- **Test isolation (7d1796b, LEDGER 33):** the 7 permanently-red
  `test_import_is_torch_free` failures were ambient-`sys.modules` reads, not
  real. `tests/_import_probe.py` probes a clean interpreter. Suite 529+7 ->
  536 passed / 11 skipped / 0 failed - first fully green suite in a while.

**NEXT / do-not-redo:** `iopaint-batch-drain` is still the top item, unchanged.
The 14 new firstdones need a clean-scan pass like the other 190. OPEN QUESTION
for the operator: ratify the 3840x2160 cap as ADR-007 or pick a different value
(rationale is in AUDIT_GATES 1.2 point 6 + the code comment). Do NOT re-run
DISTS at native 8K (measured impossible on this box, both devices). Do NOT
"fix" lap_ratio reading 0.14-0.39 on 8K downscale-only slugs - that is geometry,
already ungated per ADR-006. 4 slugs (3 gothic + coven-ashe) use
`source_choice=fullview`: their gate source is the fetched fullview under
`data/recovery/fetched/`, NOT the `_firstinitial` preview - any future metric
recompute must reproduce that or it silently compares against a zero-padded
image (cost me a wrong 0.78 DISTS before the MS-SSIM cross-check caught it).

---

# 2026-07-16 (Stage-2 watermark cleaning SOLVED via IOPaint-emulation; Dekel built + CAPPED; gate FPs fixed)

Long session; 3 commits (bd7521e gate FPs, bad25c8 Dekel engine, bc5fc19 lw_clean_iopaint) + living-docs. All 3 CI green. The semi-transparent-watermark blocker is SOLVED - by emulating the operator's OWN manual IOPaint method, not by Dekel.

- **Dekel (bad25c8, LEDGER 29):** built proper Dekel (fork rohitrango; Py3; Levin matting-Laplacian + IRLS + the genuinely-missing sub-pixel alignment + filled cross-image alpha). Corrected the R&D doc (its claim that the IRLS/matte core was absent was WRONG - verified vs source). Root-cause-fixed a rainbow-explosion collapse (W_init DC scale). VERDICT = CAP: leaves a legible dark-stroke ghost (the white-fill + dark-outline mark is inseparable by single-achromatic-W algebra; residual entangled with art). Parked as R&D; NOT wired.
- **Pivot (operator insight):** operator had cleaned it manually in a LOCAL IOPaint (LaMa) piece-by-piece. Recovered their launch code from PS history: `& "$env:LOCALAPPDATA\Python\pythoncore-3.11-64\python.exe" -m iopaint start --model=lama|Sanster/PowerPaint-V1-stable-diffusion-inpainting --device=cuda --port=8080` (the doc's C:\Tools\iopaint\venv is stale/never-created). Proved emulation: the trick is MASK COMPLETENESS - cover the dark OUTLINE, not just the white fill.
- **lw_clean_iopaint (bc5fc19, LEDGER 30):** masked simple-lama cleaner (complete fill+dark-edge mask, optional chroma/cross-image matte). namakx auto-cleans near-clean + faithful (cov 31.7%). Busy-art (pebano one-off) smears -> manual lane. TDD 17 pure + 1 ML; 52 passed both clean suites.
- **Gate FPs (bd7521e, LEDGER 28):** bare '@' (caitlyn/vayne3) + diluted LoL wordmark (the-ruined-king-viego) now KEEP, not auto-clean. +2 TDD tests on the exact captured OCR.

**NEXT / do-not-redo:** batch triage DONE - see `docs/research/IOPAINT_TRIAGE.md` (18 staged non-FP slugs eyeballed: **9 CLEAN-AUTO / 7 PARTIAL / 2 MANUAL**; the doc has the per-slug table + the 6 concrete pass-improvements + the next-session plan). Next: land improvements 3+4 (full-width banner band + chroma-on default; clears 3 PARTIALs) and improvement 1 (namakx template-mask / adaptive dark_thr; clears the 3 namakx dark-outline ghosts), re-run the worker over the CLEAN-AUTO 9 + cleared PARTIALs -> save-working --tool iopaint + submit for needauth, route fantasy-design + prestige-coven-xayah to the MANUAL IOPaint lane, then clean-scan the 190. Do NOT re-try Dekel / pure-algebraic (measured cap), a white-only mask (dark-edge ghost), or `--progressive` for the namakx ghost (verified no help). The cross-image matte path is BROKEN (4.5% cov - debug align_rois + MATTE_ALPHA_THR). The 3 FP slugs (caitlyn / vayne3 / the-ruined-king-viego) = KEEP. NOTE: this session's scratchpad candidates do NOT persist - re-run the worker to regenerate.

---

# 2026-07-16 (Stage-2 cleaning pipeline built: harness + gate-v2 + SDXL engine; watermark-removal R&D -> glyph15 interim, Dekel deferred)

Very long session; 2 commits (bf94629 cleaning harness, 07b7e30 SDXL worker) + living-docs. Cleaning stack provisioned (C:\Tools\lw-clean\venv, gitignored) - was ABSENT at start (verified live). Cleaning-suite green (500 collected; 33 pure + 5 integration for lw_clean_pass, 17 pure for lw_clean_sdxl); ruff + ASCII clean; independent re-verify each subagent merge. Operator drove the fill-engine decision via framed forks + rejected two engines before landing the current-best interim.

- **Shipped:** tools/lw_clean_pass.py (detect YOLO11x+EasyOCR -> gate v2 -> mask -> LaMa -> G2 verify -> PRINT lw_pipeline save-working/submit; single-writer, lazy ML imports CI-safe; bf94629). Gate v2 (build subagent, TDD): bottom-edge banners -> auto, LEAGUE OF LEGENDS wordmark excluded (is_lol_logo), OCR URL/handle match (is_watermark_text), reduction-based residue. tools/lw_clean_sdxl.py (SDXL reconstruction, .venv-gen, dual-format loader [single-file Animagine XL 4.0 + folder DreamShaper/RealVis], --checkpoint, paste-back outside-identity, VAE tiling; 07b7e30). DreamShaper XL downloaded (gitignored).
- **Triage of 228 firstdones (read-only):** 190 clean / 17 QA / 21 auto (watermark). LaMa batch: 21 -> 17 submitted, 0 discards, outside_ssim=1.0. Operator REJECTED LaMa (dark-blurs content). Reprocessed 21 via SDXL (Animagine beat DreamShaper on a sample). Operator REJECTED block-SDXL (dilated-box mask hallucinates + hard seam).
- **Watermark R&D, 9 methods (docs/research/WATERMARK_REMOVAL_RND.md):** the halo ghost is an ALPHA-ESTIMATION problem (precise masks -> faint edge halo; block -> hallucinate). glyph15+SDXL (accurate cross-image glyph matte dilated 15px + SDXL) = current-best interim (text gone, faithful, minor dense-line smudge). Research subagent verdict: proper Dekel (Levin matting-Laplacian alpha + sub-pixel alignment + IRLS + matting-equation inversion) is the only zero-halo FAITHFUL path (~1-2 sessions, pure numpy, no cu128 risk); SLBR/WDNet out-of-distribution (256px logos).

**NEXT / do-not-redo (operator: Dekel is a FRESH session):** build proper Dekel per WATERMARK_REMOVAL_RND.md section 3 (fork rohitrango scaffold; add matting-Laplacian + sub-pixel alignment + IRLS; pool ALL same-artist images). Reprocess the 21 (staged in 3.Cleaning Scratch, block-SDXL needauth already rejected) + pebano1/vexxsoul/namakx clusters. Tighten gate false-positives (caitlyn `@`-only, vayne3 carved-stone, the-ruined-king-viego LoL logo). Then clean-scan the 190. Do NOT re-try LaMa erase / block-SDXL / tight-glyph fill / pragmatic joint-opt / SLBR-WDNet. Session R&D scripts are scratchpad-temp (logic captured in the doc). Committed code green + pushed.

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

---

# 2026-07-11 (M1 localizer decision - DWPose onnx-CPU adopted, 5/6)

Shipped + pushed (commit 7e21c9d), full suite 387 passed / 3 skipped:
- **Spike outcome:** DWPose onnx-CPU ADOPTED as the M1 auto-suggestion localizer -
  5/6 wrist-on-weapon on the 6 recall_gate samples (seed22 / seed33 / seed800 /
  cand_01 / seed42 hit; cand_02 miss) vs OpenPose 1/6. Cleared the operator's >= 4/6 bar.
- **SDPose-Wholebody REJECTED (do NOT retry):** its pipeline hard-imports mmpose +
  pins mmcv==2.2.0 = the Blackwell / torch-2.11 wall (also torch 2.8 / transformers
  4.57 / xformers; 5.32GB). NOT drop-in as the handoff assumed. Operator approved the
  DWPose onnx download (351MB, fashn-ai HF mirror) instead.
- **Built:** tools/lw_gen_localizer_eval.py (detector-agnostic harness + cocowb_to_kp_map
  COCO-WholeBody-133 adapter + openpose/dwpose backends) feeding the REUSED
  weapon_roi_from_keypoints; tools/dwpose_onnx/ vendored onnx helpers (no mmcv). +7
  tests. Models gitignored (tools/models/dwpose). min_conf=0.3 (scores clean [0,1]).

**NEXT session:** wire dwpose_backend into lw_gen_run's real detect -> mask -> inpaint
path (operator-in-the-loop picks the weapon-side wrist -> kp_map -> weapon_roi_from_keypoints
-> inpaint + hard outside-mask identity assert + re-QA via cand[file]). Do NOT redo the
localizer spike, slices 1-2, or re-attempt SDPose. Still operator-blocked:
GOLDEN_DEFINITION.md sec 6 Q1-Q4.

---

# 2026-07-11 (M0 foundations + M1 weapon slices 1-2 + upstream-localizer exploration)

Shipped + pushed, all green (full suite 380 passed / 3 skipped):
- **M0 (a934243):** config Animagine flip (model_path -> the single-file
  animagine-xl-4.0-opt.safetensors; steps 28); tools/lw_gen_pose.py OpenPose helper;
  cand[file] contract (stage_filename / new_candidate_record / advance_cand_file +
  stage + provenance). Recall gate PASSED 6/6 (operator).
- **Corpus (7826b22 / e27054f / ba308ff):** all 122 champion labels applied
  (#32 -> Qiyana, #102 -> Zaahen); CHAMPION_ATTRIBUTED_330.md generated; operator's
  32 corrections backfilled into notes_*.json champion + is_vayne. CROP_REDO_QUEUE.md
  = #115 Hwei / #247 Shyvana / #253 Soraka.
- **M1 slices (693920f, e5bcdc5):** tools/lw_gen_weaponfix.py = pure
  weapon_roi_from_keypoints geometry + first-class fallbacks (+13) and the raw-pose
  -> COCO-18 kp_map adapter with anti-compaction lock (+7).

KEY PIVOT (empirical): weapon-mask contact sheet showed the geometry is SOUND but
OpenPose WRIST is unreliable on stylized art (1/4 auto-masks hit the weapon). CLIP
mask-validator DEAD; ControlNet skeleton-reuse NOT viable (drift, settled
VERDICTS.md); DWPose blocked (mmcv/Blackwell). Operator: in-the-loop regardless.

**NEXT session (operator-directed order):** M1 localizer - try **SDPose-Wholebody
FIRST** (github T-S-Liang/SDPose-OOD, HF teemosliang/SDPose-Wholebody) as the
auto-suggestion; acceptance = beat OpenPose 1/6, target >= 4/6 wrist-on-weapon on the
6 images/_gen_scratch/recall_gate/ samples. If it misses -> **DWPose onnxruntime-CPU
spike** same session (pip install onnxruntime + ~343MB: yolox_l.onnx +
dw-ll_ucoco_384.onnx; operator approves the download). If BOTH miss -> a SEPARATE
later session builds the **manual IOPaint lane**. REUSE tools/lw_gen_weaponfix.py -
do NOT rebuild slices 1-2. Do NOT redo: M0, corpus labeling, the CLIP + skeleton-reuse
dead-ends. Still operator-blocked: GOLDEN_DEFINITION.md sec 6 Q1-Q4.

---

# 2026-07-11 (GOLDEN DEFINITION shipped: rubric v1.1 + full corpus deep dive + iterative path)

Fable-5 ultraplan session (4 workflows, ~100 agents, all adversarially verified /
spot-audited FAITHFUL). Deliverables all committed:

**docs/research/GOLDEN_DEFINITION.md REWRITTEN** = rubric v1.1 (12-element table w/
severity + addressability + stage-field scorecard), golden bar (7 conditions + stop
condition n>=3 GOLD from 2 batches), M0-M4 orchestrator spec, QA fix plan. Full pass
designs + 10 adversarial verdicts: docs/research/golden_designs/ (weapon, face_hands,
finish, qa_fix, rubric + VERDICTS.md).

**Corpus deep dive (operator-directed):** ALL 179 firstdone + 273 reference_pictures
reviewed at full res (6 imgs/agent); pHash correlation 19 exact pairs (Tier-0 rule,
scratch correlate via tools/lw_recover). Artifacts: docs/research/corpus/ (notes JSONs,
audits, CORPUS_PREMISE.md, CORPUS_ANCHORS.md, ref_correlation.json).
Key findings: anime-flat = 1.6 pct niche of operator taste (all 9 Vayne 5s are
painterly-semireal; nearest reachable band = anime-painterly-hybrid); corpus-sanctioned
WEAPON DODGE LANE (wing-rig/folded/blur/absent - 7 of 9 Vayne 5s dodge); focal-face
quality = highest-leverage axis; hands always gloved/hidden; generated text/watermark =
auto-reject; scale anchored 1-5 (min promotion bar = 3).
Engine fact verified: _extract_pose discards keypoints (lw_gen_run.py:413); M0 fixes.

**BLOCKING on operator:** (1) GOLDEN_DEFINITION.md sec 6 Q1-Q4 (glasses shape, style
band steer, dodge-lane ratify, scorecard adopt); (2) champion labels -
docs/research/corpus/CHAMPION_UNKNOWNS.md (78 true unknowns + 44 hedged, numbered,
reply "N = champ"; backfill into notes JSONs on receipt).
**NEXT session:** M0 foundations (config Animagine flip + tests, tools/lw_gen_pose.py
+ recall gate, manifest cand[file] contract, plan B), then M1 weapon pass.
ops/budget_saver/ = operator lean-config experiment, left untracked.

---

# 2026-07-11 (lw-gen QA-floor CALIBRATION + recipe v2 sweep; golden-definition seeded)

Shipped commit 2894e0b (QA floors calibrated on a real Vayne sweep) + a docs sync
(this /done). See LEDGER 16.

**QA floors calibrated (DONE - do not redo):** measured real ClipScorer scores;
set T_subj 0.26 / T_margin 0.05->0.045 / T_blur 100->150 / T_aes 0.45 (kept, but
T_aes is a NON-DISCRIMINATIVE no-op - everything scores 0.500-0.504). 6/6 good PASS,
misses REJECT. gen suite 67/67 green.

**Recipe v2 (operator-in-the-loop sweep, DONE - do not redo the sweep):**
controlnet_scale tight (1.10) OUT, loose-mid (0.35-0.55) wins; POSE SOURCE is the
lever (curated skel_01 leap >> default crouch; `_extract_pose` shares ONE skeleton
per batch - pose variety still needs the deferred cycling feature); fixed a
156-vs-77-token prompt truncation (Animagine quality tags were being cut); feminine
cues + male/androgynous negatives fixed a male-read; clean-DoF prompt killed FX
chaos. Recipe v2 strings: `images/_gen_scratch/exp3_clean/index.json`.

**Plateau + gate finding:** raw single-pass SDXL tops out at "good fan splash", not
golden. Operator accepted seed22 which the gate WRONGLY rejected as blurry - global
lap_var is confounded by DoF; needs a subject/face-region sharpness fix in
`tools/lw_gen_qa.py` (deferred).

**NEXT (operator directive):** fable-5 ultraplan + adversarial FULL-RES review ->
develop the golden rubric from `docs/research/GOLDEN_DEFINITION.md` (operator seed
critique + failure taxonomy; WEAPON is the #1 blocker). Iterative passes, not
superficial. Accepted refs: exp3_clean/seed22+seed33, exp4_volume/seed800,
proto/cand_01+cand_02 (all in `images/_gen_scratch/`, full-res).

---

# 2026-07-11 (lw-gen GENERATOR SIDECAR built + provisioned + Phase-0 proven; then DEEP-RESEARCH RETUNE pivot - HEADLESS)

New sidecar `lw-gen` (generate LoL-champion splash wallpapers -> subject-QA gate
-> feed 0.Originals). Commits: b2fc3a2 (sidecar run/qa/promote + /generate +
67 CI-safe tests), 7d6a3ca (Phase-0 provision + live proof), 5aec00d (subject-LoRA
loading hook + --lora-path/--no-lora).

**Proven live - DO NOT REDO:** `.venv-gen` (torch 2.11 cu128 + diffusers 0.39 +
peft 0.19 + tensorboard); open-clip `ViT-L-14-quickgelu` QA in `.venv-metrics`
(plain ViT-L-14 mismatches - MUST be quickgelu); RealVisXL V5.0 fp16 base
(`tools/models/RealVisXL_V5.0/`, sha in docs/GEN_MODELS.md) + its diffusers-format
copy `tools/models/realvisxl5_diffusers/`; sm_120 (12,0) gen ~3.4 it/s; the ddragon
splash-fetcher (chroma-filter + pHash-dedupe, scratchpad `fetch_splashes.py`);
SDXL LoRA training runs (diffusers `train_dreambooth_lora_sdxl.py` v0.39.0-matched,
UNet-only rank16 1500 steps ~23 min, fits 1024px in 11GB) - but rank16/1500
OVERFIT+blurred. rc_live gate lists ONLY the game/client (NOT RiotClientServices/
Vanguard - those are idle non-GPU). Loader uses `StableDiffusionXLPipeline.from_single_file`
(AutoPipeline has no from_single_file).

**PIVOT (operator, headless):** first gen results REJECTED - non-canonical faces,
broken fingers/hands, too photoreal (RealVis wrong feel), uncanny valley. New
mandate: UNLIMITED DEEP-RESEARCH ULTRA. Mine ALL `2.First Pass Done` (179 imgs,
70 champs; `firstdone_by_champ.json`) + official ddragon skins to build per-champion
+ general-style ARCHETYPES, retune against them. Acceptance = SIMILARITY to real
first-pass-done + official base/extra skins AND artifact/uncanny-free (detect bad
hands/faces). **Next champion = VAYNE** (6 curated firstdone + 19 official splashes
in `tools/models/lora_datasets/vayne/`). Baseline RealVis already recognizes KNOWN
champs well (Ahri baseline QA 4/4) - subject gap is for NEW champs (Ambessa).

**RETUNE - WINNING RECIPE LOCKED (full journey + rubric in docs/research/GEN_RETUNE.md):**
Deep-research workflow wbnpch0uo (archetypes) + posing research -> iterated through
RealVis-painterly (fixed too-photoreal), img2img-from-real (fixed palette/pose but BLURRED
faces - rejected), to the FINAL recipe. Commits this session: cc2875a e35ea14 f67c8f4
065679b e7f98ea d77dbe2 8e30892 f0ac578.
- **WINNING RECIPE = Animagine XL 4.0 (anime base) + ControlNet-OpenPose (skeleton from a
  real splash) + cowboy-shot detail-tag booru prompt.** Operator directed anime-flat
  (overriding the anime ban) + flagged mangled glasses / odd faces / blotchy-blur / bad hands.
  Animagine KNOWS champions from booru data (Vayne: clean red glasses, dual crossbows,
  ponytail, navy+red) + clean anime faces. ControlNet-OpenPose (xinsir SDXL, controlnet_aux
  OpenposeDetector hand_and_face) transplants a real natural pose + pins hand chirality (kills
  the mirrored 2nd-left-hand) while keeping SHARP txt2img detail (no img2img blur).
  Batch vayne-controlnet-tuned = production quality, hits the operator bar.
- Integrated first-class in lw_gen_run: `--model-path` (base override), `--controlnet-pose
  <ref>` / `--controlnet-scale` (config controlnet_openpose_path), `--lora-path`/`--no-lora`,
  `--init-image`/`--img2img-strength`. Style `splash-booru` (posing+detail vocab, lean
  negatives). Brief briefs/vayne_animagine.json. 67 gen tests green, CI-safe (lazy imports).
- Provisioned + gitignored (tools/models/): RealVisXL_V5.0, animagine-xl-4.0-opt.safetensors,
  controlnet-openpose-sdxl (xinsir), lora_datasets/{vayne,ahri} (ddragon fetch), yolo/ (unused
  - hand DETECTION is a dead end on painted hands, do NOT build detect-repair). .venv-gen has
  torch2.11cu128 + diffusers0.39 + peft + controlnet_aux + ultralytics + tensorboard.
- DO NOT REDO: the base/model choices, ControlNet integration, the img2img/anime exploration (settled),
  hand-detection repair (dead end). Full recipe + rejected paths in docs/research/GEN_RETUNE.md.
- **NEXT = THRESHOLD ITERATION (operator, new session):** dial in the knobs on the winning
  recipe - controlnet_scale (0.75), img2img_strength, cfg/steps, and the QA floors in
  lw_gen_config.json qa{} (T_subj .26 / T_margin .05 / T_aes .45 / T_blur 100.0). Also
  per-candidate skeleton cycling (pose variety in one batch), then a full QA+promote pass.

**Continuity/headless:** full authority, commit+push on green. Self-continue across
sessions via Gemini + AHK (`gemini-headless-upgrade` skill) targeting THIS window
(named **"Image"**). State lives on disk (git + this file + docs/LEDGER.md + memory
`project-lw-gen-deep-research`).

---

# 2026-07-05 (V3 promoted to primary + golden n=12 + dark-cosmic; recovery scaffolding; G0 gate; ADR-004/005)

Resolved + promoted IllustrationJaNai V3 detail DAT2 to the PRIMARY first-pass
upscaler (ADR-004; LEDGER item 5). V3's OpenModelDB link is dead - it ships only
via the MangaJaNai v3.0.0 GitHub release (direct HTTPS, no gdrive dance); fetched
the DAT2 detail weight (sha eb9faf6a, 139,793,020 bytes, self-computed checksum),
spandrel-loaded (arch=DAT/4x). A/B'd V1 vs V3 through `lw_golden regress`: V3 wins
golden n=10 (MS-SSIM 8/10, LPIPS 9/10, halo 7/10) + both new defect cases, and
clears BOTH high-halo flags (fiora2 0.072->0.043, inkshadow 0.075->0.043). Widened
calibration to n=14 golden-comparable - thresholds HOLD (the 3 lap<1.0 'fails'
were big-4K-source common-scale-upscale artifacts, a G0 source-gate gap now in
ROADMAP). Re-froze the golden set at n=12 on V3 (pv d9ec8125 -> 6d43a6d4; added
`coven-ashe-lol-df49jt0-pre` jpeg-artifact + `1341679-banding`); all 12 PASS with
ZERO flags; regress self-check PASS 12/12 pv_changed=False. Reprocessed
`dark-cosmic-ahri-by-pebano1-dlnxav6-pre` from its recovered Tier-0 source
(`Pictures/288.png`, 2560x1440, pHash dP=4 vs the 1192x670 G0-fail preview) -> V3
first-pass (PASS) -> submitted to `_firstneedauth`.

**Do NOT redo:** the V3 weight (gitignored `tools/models/`); the n=12 V3 freeze;
the A/B. Suite 190 passed / 3 skipped; only `data/golden/golden_set.json`
tracked-dirty. **Process scar:** killed a pathological 8K source (caitlyn
7680x4320) mid-widening that pinned the 12GB card at 11.5GB - verified the PID by
working-set/CPU/GPU correlation, NOT blind nvidia-smi. **Also shipped this session (2026-07-05, continuous):** (a) source-recovery
waterfall scaffolding `tools/lw_recover.py` (LEDGER item 6, commit b61c1a5) -
Tier 0 local pHash/dHash match usable NOW, Tier 1 token-decode + oEmbed work now,
Tier 1 gallery-dl + Tier 2 SauceNAO gated on keys, the SauceNAO multipart-POST a
flagged TODO; (b) the G0 over-target source-gate (LEDGER item 7, commit 6cffc3d) -
first-pass routes sources already covering 2560x1440 to a downscale-only path
(closes the widening gap); (c) artist-signature ruling ADR-005 (REMOVE at the
cleaning scratch stage - closes the last queued ADR-002 decision). Full suite now
226 passed / 3 skipped; commits 37741ea, b61c1a5, 6cffc3d all pushed.

**STATE update (later 2026-07-05):** dark-cosmic APPROVED -> `2.First Pass Done`
(_firstdone). Recovery keys IN - `API-Key-SauceNAO.txt` (40 chars) +
`API-Key-DeviantArt.txt` (client-id/secret); `%APPDATA%/gallery-dl/config.json`
written with the app creds + quota-friendly (original=false, quality=100,
intermediary=true). **DeviantArt AUTHORIZED** (operator ran `gallery-dl oauth:deviantart`
2026-07-05; refresh-token cached) - all recovery keys live. **NEXT (active -
recovery activation):** (1) finish the
SauceNAO image-upload POST in `lw_recover.saucenao_search` (flagged TODO; TDD);
(2) build + run a campaign driver - enumerate the 149 pending, Tier-0 corpus =
`Pictures/` + `Desktop/Found`, run `run_waterfall`, record provenance via
`lw_pipeline annotate`. **Then:** monitor polish (lw_monitor 127.0.0.1:8901,
`docs/research/LW_MONITOR_SPEC.md` section 8, UI Fixture Ritual); G3 Haiku
win-or-tie; V3denoise per-image halftone alternative.

**STATE update 2 (recovery activated + monitor polished, 2026-07-05):** the
"NEXT (active)" above is DONE. (1) SauceNAO multipart POST wired (real image
upload; live-verified parsed shape + quota long_remaining=94). (2) Campaign
driver `tools/lw_recover_campaign.py` built (TDD, 11 tests) + RAN on the live
170 pending previews (backlog grew past the noted 149): 102 Tier-0 local pHash,
67 real DeviantArt fullview fetches, 1 SauceNAO (Pixiv, dead deviation), 0
manual, 0 errors. **Root-caused + fixed a live DeviantArt clampdown regression:**
oEmbed now 404s on `/deviation/<id>` and needs the canonical
`/<artist>/art/x-<id>` URL (rebuilt from the `_by_<artist>_` filename); the fetch
stays on authoritative gallery-dl OAuth. Provenance annotated via `lw_pipeline
annotate` on the two manifest-bearing slugs; loose targets record provenance in
`data/recovery/matches.json`. `.gitignore` now ignores all recovery runtime
outputs (fetched art + personal-path caches). Suite 243 passed / 3 skipped.
Commits 5c2cf42 (code) + ea74508 (docs); LEDGER item 8. **Monitor polish (LEDGER
item 9):** verified lw_monitor live against real state (renders 11
First-Pass-Done + 120 pending; log tail + page all HTTP 200), created the "LW
Monitor" Desktop shortcut (section 8), confirmed the page ASCII-clean; thumbnail
generation found DORMANT (no producer writes `thumb` fields) so the spec
thumbs-root RISK is RESOLVED/deferred. **Do NOT redo:** the POST, the oEmbed
artist-URL fix, the driver + this run, the shortcut. **NEXT:** dark-cosmic
downstream stages (cleaning pass); a thumbnail producer if monitor thumbs are
wanted; per-image `original=true` 4K escalation for quota-capped fullviews; G3
Haiku win-or-tie; V3denoise halftone alternative.

**STATE update 3 (recovered backlog first-passed, 2026-07-05):** Task 1 executed.
Ground-truth CORRECTED the "1280px cap" (that was the oEmbed PREVIEW dim; fetched
fullviews are median 1440w, 19/68 >=2560). Operator forks: budget = gate-triggered
original=true (cost 0 this batch); non-16:9 = auto-crop when area-loss <=8 percent
else HOLD. Validated the full chain live (p08e8 PASS) THEN built + committed
`tools/lw_first_pass.py` (resumable first-pass driver, 27 tests, verifier-green,
live-proven on aatrox; commit 82aacc2). `intake --all` (119 -> scratch, 0
anomalies) -> real-upscale batch of 47 = 38 PASS + 9 FLAG + 0 FAIL; 10 crop_heavy
HELD. **49 in _firstneedauth** (approve/reject queue). Suite 270 passed / 3
skipped. **Deferred (cause):** 61 downscale-only need distinct G1 handling
(lap_ratio floor invalid for a no-upscale path; the LEDGER-7 false-soft) - now the
top ROADMAP NEXT. **Do NOT redo:** the driver, the 47-batch, the 10 holds, the 2
pilots. LEDGER item 10.

---

# 2026-07-04 (golden set - first-pass drift-regression harness shipped)

Commits 8e8b9a0 + 936d99b + e0a1250. Built `tools/lw_golden.py` (freeze +
regress) - the drift-detection harness, adapted for no-ground-truth (operator
ruling: no finished refs; reference of record = the current blessed IJN
first-pass output, not perfection). Flow: brainstorm -> spec
(`docs/research/GOLDEN_SET.md`) -> plan
(`docs/superpowers/plans/2026-07-04-golden-set.md`) -> TDD build; heavy deps
INJECTED so the tool is CI-testable. Operator blessed all 10, froze
`data/golden/golden_set.json` (TRACKED, pv d9ec8125, 10 cases; image bytes
gitignored + sha-pinned). Regress self-check PASSED 10/10 within epsilon (also
proves IJN upscale determinism). Suite 190 passed / 3 skipped; CI green.

Do NOT redo: the golden freeze (done); the 10 baselines. Two process scars in
LEDGER item 4: a stray `&` spawned a duplicate torch job -> pagefile OOM
(WinError 1455); nearly taskkill'd dwm/explorer/claude by trusting `nvidia-smi`
compute-apps blindly - ALWAYS verify a PID name before taskkill. Next: widen n
past 10; trial V3 DAT2 via `lw_golden regress`; add banding/JPEG-artifact
defect-class cases to the golden set.

---

# 2026-07-04 (QA Session 2 - IJN primary path live + G1 gate frozen n=10)

Commit dca6071. IllustrationJaNai V1 DAT2 (spandrel/torch) is now the PRIMARY
first-pass upscaler and the G1 gate is frozen on it. Downloaded + extracted the
V1 DAT2 weights to `tools/models/` (gitignored; OpenModelDB -> Google-Drive zip
bundle, confirm-token dance), spandrel loads DAT/4x on the RTX 5070. Built 3
committed modules (TDD, subagent slices, CI-safe via importorskip):
`lw_upscale.py` (spandrel + ncnn backends, seam-exact tiling), `lw_g1_gate.py`
(the REAL overshoot detector replacing the crude edge-diff proxy, plus
laplacian/banding/common-scale-FR/verdict), and a `lw_pipeline annotate` verb
(provenance + G1 metrics into manifests; closes task_fb503c0a). Ran the 10
approved images through IJN and G1-scored IJN vs the realesrgan-anime fallback
with identical code: **IJN wins 10/10 on MS-SSIM, LPIPS, AND halo_pct.** Froze
AUDIT_GATES 1.4; fixed a band_delta hard-fail bug (was fail>0 - it wrongly
hard-failed the BETTER upscaler 8/10 on ~0.004 noise; demoted to advisory
flag). Suite 183 passed / 2 skipped, ruff clean, pushed.

**Premise CORRECTED (operator ruling):** `reference_pictures/*_cleanup.png` are
"original-not-found" MARKERS, NOT finished ground-truth. The Session 1 "GT vs
finished ref" band is VOID - G1 scores self-metrics only; every image still
needs work. Saved to memory (`project-no-finished-ground-truth`).

**Do NOT redo:** venvs + V1 DAT2 weights (downloaded, gitignored under
`tools/models/` + `.venv-*/`); the 10 first-pass images. **Next:** golden set of
approved (input, output) pairs - the prereq for any GT-vs-approved regression,
since none exists yet; widen n past 10; trial V3detail DAT2 (its OpenModelDB
gdrive link was unresolved this session). **Queued (unchanged):** recovery
campaign (149 pending, 75 `niphrimit` `-pre`); artist-signature policy; API
keys (SauceNAO + DeviantArt).

---

# 2026-07-03 (session 2 - PRODUCT DEFINED: restoration pipeline v1 shipped)

Commit `1d3631b` (44 files, +7946): the staged self-auditing image restoration
pipeline. Operator's 10-folder / 4-phase scheme adopted VERBATIM (ADR-003)
plus 13 additive safety fixes; product recorded in ADR-002; operational plan
is `docs/RESTORATION_PLAN.md` (v2 - v1 archived as RESTORATION_PLAN_v1.md).

**Shipped:** `tools/lw_pipeline.py` (state machine, SAFE-MOVE, slug grammar,
manifests, 49 tests) - `tools/lw_monitor.py` + `web/monitor.html` (:8901,
Desktop "LW Monitor" shortcut, UI fixture audit PASSED, 26 tests) - 7 stage
commands (/intake /first-pass /cleaning-pass /final-pass /last-pass
/end-review /pipeline-status) - 5 research docs + state-machine spec +
monitor spec - migration: 76 intake sources + 302 reference PNGs copied+
SHA256-verified into `images/` (Desktop `need up` untouched, MIGRATED.md
marker left; operator deletes at leisure). First real scan green:
pending_intake=76, anomalies=0. Suite 147/0; verifier CONFIRM.

**Do NOT redo:** migration (done, verified); the design research (docs/
research/ is the source of truth); the DeviantArt token base36 decode is
VERIFIED working. **Next:** QA Session 1 - install .venv-upscale + lw-clean
venvs per RESTORATION_PLAN.md install checklist, run ONE image end-to-end
through /intake + /first-pass, calibrate G1 thresholds. **Queued operator
decisions:** artist-signature keep/remove policy; LongPathsEnabled (deferred).

---

# 2026-07-03 (GENESIS - operating system inherited from Riot Commander; docs-only, no product code)

Legion Wallpaper bootstrapped by cloning HOW the Riot Commander (RC) project
operates - 1:1 process port, ZERO product content. The product (some kind of
wallpaper app for the Legion machine) is deliberately NOT defined yet; the
first real work item is the scope decision (ROADMAP.md, top item).

**What was ported (process, not product):**
- `CLAUDE.md` operating rules + `.claude/` (settings, hooks, agents, commands)
  - the tier system, gates, TDD/RED-first discipline, subagent-first
  delegation, verification rituals, ASCII-only hard rule, CLAUDE.md size
  budget (under 60KB, never append ledger entries to it).
- Living-doc skeletons: `ROADMAP.md` (highest priority at TOP), `BACKLOG.md`
  (aspirational lanes), this file (newest-first hand-off), `docs/LEDGER.md`
  (append-only newest-first per-item ledger, numbering starts at 1),
  `docs/history_notes.md` (deep archive), `docs/adr/` (TEMPLATE + ADR-001).
- Runtime conventions (documented, not yet running): supervisor pattern,
  `restart_trigger.txt`, `ops/runtime/health.json`, `logs/YYYY-MM-DD.log`,
  atomic writes, py_compile-before-restart, taskkill-not-Stop-Process.
- `docs/OPERATIONS.md`: restart workflow + the LW-* scheduled-task convention
  with the standard roster (LW-Supervisor / LW-GeminiAudit / LW-WeeklyHygiene /
  LW-CIWatchdog) - example commands only, NOT YET REGISTERED.
- `docs/AGENTS.md`: the two-supervisor + 8-agent-roster PATTERN as a role
  template (gatekeeper/scheduler/ingest/testing/analyzer/ui-fallback/auditor/
  nl-parser), gate policy pattern, `agents/state/` file conventions - wiring TBD.
- `docs/DEEP_AUDIT_CHARTER.md`: RC's three-lens audit charter as a DORMANT
  template, authorization slots UNSET.

**Where things live:** repo root `C:\LegionWallpaper\`; rules in `CLAUDE.md`;
docs in `docs/`; harness in `.claude/`; canonical Python
`C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`
(`pythonw.exe` for hooks/daemons; bare `py` is BANNED - pytest-less launcher
runtime). Do NOT touch `C:\LegionWallpaper\Claude\` - that is Claude Desktop
app data, not project content.

**What is TBD (do not invent):** the product itself (engine, rendering,
architecture, endpoints, ports); the module map; the test suite; every
scheduled task (none registered); the agent-framework wiring; the deep-audit
program (arms only by explicit operator directive once code exists).

**Decision record:** `docs/adr/ADR-001-inherit-rc-operating-system.md`
(Accepted, 2026-07-03).

**Process notes:** (1) RC product references (Daemon Slayer, dashboards,
Riot API, match DB, tailnet topology, etc.) were dropped or replaced with
explicit "TBD - product not yet defined" placeholders - if a ported rule reads
oddly abstract, that is why; the rule itself is intact. (2) The frozen-file
list starts EMPTY; files earn freeze status as the product stabilizes.

---

## 2026-07-17 - RESTORATION_PLAN section 7 install checklist (relocated on completion, R8 hygiene)

Relocated verbatim from `docs/RESTORATION_PLAN.md` section 7 after on-disk
verification 2026-07-17: every item DONE except 7 (ComfyUI, still pending) and
5 (superseded - the dedicated IOPaint venv was never created; the manual QA
lane runs the operator's local py3.11 iopaint 1.6.0 install, WAKEUP
2026-07-16). Original text:

> ## 7. Install checklist (next QA session)
>
> Consolidated from the research docs' install-now lists. Order matters.
>
> 1. `winget install Python.Python.3.12` (side-install; does not touch 3.14).
> 2. Upscale venv (`C:\LegionWallpaper\.venv-upscale`, py 3.12 preferred; 3.14
>    acceptable for torch itself if cp314 cu128 wheels resolve):
>    - `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128`
>    - `pip install spandrel pillow numpy`
>    - smoke test: `torch.cuda.is_available()` True + device name contains 5070;
>      spandrel load + 64x64 forward pass per downloaded model.
> 3. Models to `C:\LegionWallpaper\tools\models\`: 4x IllustrationJaNai V3detail
>    (DAT2), V3denoise (DAT2), 4x AnimeSharp (cross-check). V3detail DAT2 is the
>    PRIMARY first-pass upscaler as of ADR-004 (spandrel-loaded, sha eb9faf6a);
>    4x_IllustrationJaNai_V1_DAT2_190k.pth is the spandrel-confirmed fallback.
> 4. Cleaning venv (`C:\Tools\lw-clean\venv`, py 3.12): torch cu128, then
>    `ultralytics easyocr simple-lama-inpainting opencv-python pillow`; download
>    `yolo11x-train28-best.pt` watermark weights (115 MB, HuggingFace
>    fancyfeast space).
> 5. IOPaint in its OWN venv (`C:\Tools\iopaint\venv`, py 3.12): torch cu128 +
>    `iopaint==1.6.0` (archived project - pin and isolate).
> 6. Orchestration deps on 3.14: `pip install gallery-dl imagehash pillow`.
> 7. Later (final stage bring-up): ComfyUI portable for Blackwell (embedded py
>    3.12 + torch cu128) + Impact Pack + anime YOLO detectors + FBCNN node.
> 8. API keys to project root (gitignored `API-Key-*.txt` convention):
>    `API-Key-SauceNAO.txt`, `API-Key-DeviantArt.txt` (client-id/secret +
>    refresh-token via `gallery-dl oauth:deviantart`).
