# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18) - keep the last 3.

---

# 2026-07-18 (wallpaper deck rotator shipped - Windows slideshow replaced; LW-Wallpaper task live)

Three commits: b93ddc7 (spec), d220e6e (feat), 17693cb (time-trigger fix).
Operator asked why the Windows slideshow repeats constantly. It is not a
perception problem - the algorithm has no memory.

- **Root cause (probed live, not assumed):** `HKCU\Control Panel\Personalization\Desktop Slideshow`
  has `Shuffle=1`, `Interval=60000`, `LastTickLow=LastTickHigh=0`. Zeroed
  LastTick = no deck, no cursor, no shown-set: sampling WITH replacement,
  re-seeded on wake/logon. At 242 images the expected first repeat is ~19
  picks (~19 min). Verifier corroborated by catching the wallpaper registry
  value change between two probes while LastTick stayed 0.
- **Shipped:** `tools/lw_wallpaper_rotate.py` - persisted permutation +
  cursor in `ops/runtime/wallpaper_deck.json`. Deck logic is pure so the
  once-per-cycle guarantee is testable; win32 SPI call is an isolated shim.
  Mid-cycle corpus churn handled (new pipeline deliveries join the current
  cycle; deletions are never set). Cycle-seam swap stops the last pick of
  cycle N opening cycle N+1.
- **Two defects caught, both worth remembering.** (1) My spec's step-2
  reconcile ran unconditionally, splicing everything into an empty deck on
  fresh state, so `cursor >= len(deck)` never fired and the seam swap was
  dead code - found by the build agent. (2) The task registered `Ready` with
  `Next Run Time: N/A`: a LogonTrigger's Repetition only starts when the
  trigger FIRES, so it would have idled until the next logon. Found by LIVE
  probe after install, NOT by the suite - the task XML had no trigger-level
  test. Both fixed, both now covered.
- **Live state:** task `LW-Wallpaper` Ready, NextRun populated, both triggers
  PT3M, `Shuffle=0` (built-in disarmed), `WallpaperStyle=10` preserved, deck
  242 entries / 242 unique. Interval 3 min = ~12.1h per full cycle.
- Suite 575 passed / 11 skipped, ruff clean. Detail: `docs/LEDGER.md` item 34.

**Second half - corpus expansion (LEDGER 35 + 36).** Operator asked for the
missing "properly sized and QA'd" images from `9.Image Backup` and
`reference_pictures`. Premise was wrong on both and the wrong half mattered.

- `9.Image Backup` REJECTED: raw intake inputs. The 183 absent slugs are 8K
  sources or sub-720p DeviantArt previews, not outputs.
- `reference_pictures`: 272 of 292 genuinely novel (slug matching is useless
  here - dedupe ran on sha256-vs-manifest + pHash; 20 were already restored).
  All 2560x1440, no internal dupes. But NOT QA'd - `AUDIT_GATES.md:126` and
  `CLEANING_INPAINT.md:37` document baked-in artist credit strips.
- Triaged all 272 through the PRODUCTION gate (`detect_image` :660 +
  `gate_decision` :352, clean venv, 105s, 0 errors) -> 237 clean / 22 qa /
  13 auto. Gate validated against ground truth: it correctly caught
  `170_cleanup.png`, the one file the repo proves is watermarked.
- Held 11 more that the gate called clean but whose OCR could not be cleared.
  A fuzzy threshold flagged only 2 and MISSED `124f.png` (reads as
  DEVIANTART.COM) - evidence the threshold was the wrong instrument, so all 12
  long-OCR files got bounded manual review instead. Only `278f.png` cleared
  (in-art splash lore typography).
- Delivered 226 as `ref_<name>.png`, sha256-verified. Pictures 242 -> 468.
  Rotator reconciled live: deck 242 -> 468, all unique, new files joined the
  CURRENT cycle (`ref_302f.png` picked on that very tick).
- The 46 held were then intaken (operator directive): `first_scratch=0 -> 46`,
  anomalies=0, verifier CONFIRMED 9/9 + 4/4 harm checks. Queue + per-file
  reasons in `docs/refs_cleaning_queue.md`.
- **NEXT SESSION:** first pass the 46, then cleaning. Their manifests carry
  `source_url: null` - the recovery waterfall is still OWED for that set.

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
