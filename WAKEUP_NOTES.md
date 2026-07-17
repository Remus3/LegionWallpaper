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

# 2026-07-16 (Stage-2 watermark cleaning SOLVED via IOPaint-emulation; Dekel built + CAPPED; gate FPs fixed)

Long session; 3 commits (bd7521e gate FPs, bad25c8 Dekel engine, bc5fc19 lw_clean_iopaint) + living-docs. All 3 CI green. The semi-transparent-watermark blocker is SOLVED - by emulating the operator's OWN manual IOPaint method, not by Dekel.

- **Dekel (bad25c8, LEDGER 29):** built proper Dekel (fork rohitrango; Py3; Levin matting-Laplacian + IRLS + the genuinely-missing sub-pixel alignment + filled cross-image alpha). Corrected the R&D doc (its claim that the IRLS/matte core was absent was WRONG - verified vs source). Root-cause-fixed a rainbow-explosion collapse (W_init DC scale). VERDICT = CAP: leaves a legible dark-stroke ghost (the white-fill + dark-outline mark is inseparable by single-achromatic-W algebra; residual entangled with art). Parked as R&D; NOT wired.
- **Pivot (operator insight):** operator had cleaned it manually in a LOCAL IOPaint (LaMa) piece-by-piece. Recovered their launch code from PS history: `& "$env:LOCALAPPDATA\Python\pythoncore-3.11-64\python.exe" -m iopaint start --model=lama|Sanster/PowerPaint-V1-stable-diffusion-inpainting --device=cuda --port=8080` (the doc's C:\Tools\iopaint\venv is stale/never-created). Proved emulation: the trick is MASK COMPLETENESS - cover the dark OUTLINE, not just the white fill.
- **lw_clean_iopaint (bc5fc19, LEDGER 30):** masked simple-lama cleaner (complete fill+dark-edge mask, optional chroma/cross-image matte). namakx auto-cleans near-clean + faithful (cov 31.7%). Busy-art (pebano one-off) smears -> manual lane. TDD 17 pure + 1 ML; 52 passed both clean suites.
- **Gate FPs (bd7521e, LEDGER 28):** bare '@' (caitlyn/vayne3) + diluted LoL wordmark (the-ruined-king-viego) now KEEP, not auto-clean. +2 TDD tests on the exact captured OCR.

**NEXT / do-not-redo:** batch-triage the ~18 staged non-FP slugs in images\3.Cleaning Scratch (auto-clean calm-bg -> save-working --tool iopaint + submit for needauth; busy-art -> operator manual IOPaint), improve the passes per the triage, then clean-scan the 190 clean firstdones. A batch-triage subagent was running at wrap - read its triage table (scratchpad/iopaint_triage/) for the auto/partial/manual buckets. Do NOT re-try Dekel / pure-algebraic (measured cap) or a white-only mask (ghosts). The 3 FP slugs (caitlyn / vayne3 / the-ruined-king-viego) = KEEP.

---

# 2026-07-16 (Stage-2 cleaning pipeline built: harness + gate-v2 + SDXL engine; watermark-removal R&D -> glyph15 interim, Dekel deferred)

Very long session; 2 commits (bf94629 cleaning harness, 07b7e30 SDXL worker) + living-docs. Cleaning stack provisioned (C:\Tools\lw-clean\venv, gitignored) - was ABSENT at start (verified live). Cleaning-suite green (500 collected; 33 pure + 5 integration for lw_clean_pass, 17 pure for lw_clean_sdxl); ruff + ASCII clean; independent re-verify each subagent merge. Operator drove the fill-engine decision via framed forks + rejected two engines before landing the current-best interim.

- **Shipped:** tools/lw_clean_pass.py (detect YOLO11x+EasyOCR -> gate v2 -> mask -> LaMa -> G2 verify -> PRINT lw_pipeline save-working/submit; single-writer, lazy ML imports CI-safe; bf94629). Gate v2 (build subagent, TDD): bottom-edge banners -> auto, LEAGUE OF LEGENDS wordmark excluded (is_lol_logo), OCR URL/handle match (is_watermark_text), reduction-based residue. tools/lw_clean_sdxl.py (SDXL reconstruction, .venv-gen, dual-format loader [single-file Animagine XL 4.0 + folder DreamShaper/RealVis], --checkpoint, paste-back outside-identity, VAE tiling; 07b7e30). DreamShaper XL downloaded (gitignored).
- **Triage of 228 firstdones (read-only):** 190 clean / 17 QA / 21 auto (watermark). LaMa batch: 21 -> 17 submitted, 0 discards, outside_ssim=1.0. Operator REJECTED LaMa (dark-blurs content). Reprocessed 21 via SDXL (Animagine beat DreamShaper on a sample). Operator REJECTED block-SDXL (dilated-box mask hallucinates + hard seam).
- **Watermark R&D, 9 methods (docs/research/WATERMARK_REMOVAL_RND.md):** the halo ghost is an ALPHA-ESTIMATION problem (precise masks -> faint edge halo; block -> hallucinate). glyph15+SDXL (accurate cross-image glyph matte dilated 15px + SDXL) = current-best interim (text gone, faithful, minor dense-line smudge). Research subagent verdict: proper Dekel (Levin matting-Laplacian alpha + sub-pixel alignment + IRLS + matting-equation inversion) is the only zero-halo FAITHFUL path (~1-2 sessions, pure numpy, no cu128 risk); SLBR/WDNet out-of-distribution (256px logos).

**NEXT / do-not-redo (operator: Dekel is a FRESH session):** build proper Dekel per WATERMARK_REMOVAL_RND.md section 3 (fork rohitrango scaffold; add matting-Laplacian + sub-pixel alignment + IRLS; pool ALL same-artist images). Reprocess the 21 (staged in 3.Cleaning Scratch, block-SDXL needauth already rejected) + pebano1/vexxsoul/namakx clusters. Tighten gate false-positives (caitlyn `@`-only, vayne3 carved-stone, the-ruined-king-viego LoL logo). Then clean-scan the 190. Do NOT re-try LaMa erase / block-SDXL / tight-glyph fill / pragmatic joint-opt / SLBR-WDNet. Session R&D scripts are scratchpad-temp (logic captured in the doc). Committed code green + pushed.

---

# 2026-07-16 (W4 M3 rung==w4 SHIPPED; LoRA trained; weapon-quality investigation -> CEILING, PARKED)

Long session; 1 commit (0c255d8 M3) + docs. Full suite 458 passed / 4 skipped (+5 W4); CI green; ruff + ASCII clean; pushed. Ran the queued handoff to completion, then an operator-driven investigation into weapon quality that concluded NEGATIVE (a measured ceiling).

- **W4 M3 (LEDGER 26, 0c255d8):** ran the full ~15-min LoRA train (93MB, loss 0.03, peak 7.33GB) FIRST, then wired rung=="w4" in weapon_pass (build subagent, TDD RED-first, first-party full-suite verify + full-diff read). _build_real_inpainter gains weapon_lora (load_lora_weights adapter_name=vayne_weapon + set_adapters 0.8 + offload re-apply + pass-scoped .unload_lora handle); rung==w4 block = W1-style masked rolls + "vaynecrossbow" prompt prepend + no_lora fallback; unload after the loop. config weapon_lora_path/scale/trigger + _note_w4. +5 tests. CLI needed zero change. E2e seed22/33/800 clean (LoRA loads/guides/unloads, outside_mask_identical, seed33 face_intersect).
- **Weapon-quality investigation (all NEGATIVE):** (a) v1 e2e = plateau (dark-bat-wing/silver-shard, best seed800). (b) LoRA-scale 0.8->1.1 = no change. (c) splash pool EXHAUSTED for clean crossbow crops (re-checked all 19 + auto-crops; even demoncursed = a blade). (d) research + POC: modelviewer.lol is Cloudflare/blob-blocked; CommunityDragon serves the raw .skn -> built + PROVED a 3D crossbow-render pipeline (pyritofile parse + bone-set isolation + moderngl headless render on the 5070, pip-only; docs/research/crossbow_render_poc.md) -> 4 clean base crossbow renders (themed skins isolate poorly). (e) v2 LoRA on 10 crops (6+4 renders) = v2 == v1, no improvement.
- **Verdict:** the crossbow-adjacent read is a CEILING of masked-inpaint + thin-LoRA on stylized art, not a data gap. Operator PARKED the weapon-quality quest; rung=="w4" stays wired + available.

**NEXT / do-not-redo:** weapon-pass quest is PARKED - do NOT re-run any rung/scale (plateau measured 5x), re-mine splashes (exhausted), or build the full 20-skin render pipeline (base geometry proven not to help). rung=="w4" is available for hand-picked per-wallpaper use. LOCAL-only (gitignored, not in repo): tools/models/lora_datasets/vayne_weapon_train now holds 10 crops (6 + render_base_*.png); vayne_weapon (v1) + vayne_weapon_v2 LoRAs; .venv-poc; images/_gen_scratch/w4_* batches. The 3D-render pipeline is reusable for OTHER champions/purposes only (per docs/research/crossbow_render_poc.md). Stray untracked style.jpg/style2.jpg at repo root are pre-existing, NOT from this session.
