# Stage-2 IOPaint auto-clean triage (2026-07-16)

Batch triage of the 18 staged non-FP watermark slugs through `tools/lw_clean_iopaint.py`
(one-pass diff-mask, region auto-detected or namakx-fixed, eyeballed - NOT metric-only:
the `dev_after` high-pass metric dropped to 0.8-3.1 on EVERY slug including the visible
ghosts, so verdicts are by eye). Candidates were written to scratchpad only; NO pipeline
state was mutated. Next session RE-RUNS the worker to regenerate candidates (scratchpad
does not persist), applies the confirmed fixes, and submits for needauth.

3 gate false-positives are EXCLUDED (KEEP, do not clean): caitlyn-love-confession,
vayne3, the-ruined-king-viego (LEDGER 28).

## Buckets: CLEAN-AUTO 9 | PARTIAL 7 | MANUAL 2

| slug | mask cov% | verdict | note |
|---|---|---|---|
| aatrox-...vexxsoul-dm6j4xi | 76.1 | CLEAN-AUTO | (c)VEXXSOUL over flames fully gone (spot-verified) |
| syndra-...kintanki1 | 62.7 | CLEAN-AUTO | dark band clean, minor blade-highlight softening |
| dgk8f8n (namakx) | 28.4 | CLEAN-AUTO | misty bg, mark gone |
| image3 (namakx) | 46.3 | CLEAN-AUTO | thin dark bottom strip, clean |
| nguyen-ky-phuc-...-f1 | 34.8 | CLEAN-AUTO | dark-corner FB logo gone |
| p08e8-...namakx | 36.3 | CLEAN-AUTO | @namakxin over dark drapery, clean |
| dfzlox4 (namakx) | 44.7 | CLEAN-AUTO | no ghost |
| dfzypoo (namakx) | 43.2 | CLEAN-AUTO | no ghost |
| dfzypp1 (namakx) | 35.6 | CLEAN-AUTO | near-clean, faint belt smudge |
| spirit-blossom-...hriful | 48.2 | PARTIAL | 1 blue speck; `--chroma-thr 12` CLEARS (confirmed) |
| viego-...slimshadywallpaper | 61.7 | PARTIAL | flank "(c)SLI/.DEVIANTART"; full-width band (860,958,1720,1035)+chroma CLEARS (confirmed) |
| aidraw-...watercolornessie | 57.2 | PARTIAL | right-flank ".COM" outside ROI; widen region right + chroma |
| dfz5w2g (namakx) | 31.7 | PARTIAL | dark "N CO" outline ghost over black cloth |
| dfzypou (namakx) | 45.5 | PARTIAL | dark "AMAK" outline ghost over black cloth |
| kayle-...su-ke | 28.0 | PARTIAL | faint cyan signature ghost |
| fury-tempest-sona-...ryoairtist | 62.7 | PARTIAL | no residue but folds/gold-trim softened; hand-mask for fidelity |
| fantasy-design-...aivio | 74.1 | MANUAL | ornate armour filigree smeared |
| prestige-coven-xayah-...pebano1 | 76.9 | MANUAL | busy feathers smeared (known LaMa failure) |

## Improvements for the passes (ground-truthed this run)

1. **Namakx dark-outline ghost** (dfz5w2g, dfzypou, kayle): the diff `dark_thr=-14`
   never fires where the semi-transparent DARK glyph sits over near-black art -> a
   ghost survives. `--progressive` reuses the SAME mask, does NOT fix it, and adds
   smear on busy ROIs. Best fix = a static TEMPLATE mask stamp for the fixed namakx
   credit (identical font/size/position across the 5 dfz frames); or a local-contrast-
   normalized / lower adaptive dark_thr.
2. **Cross-image matte is BROKEN**: `--cluster namakx --matte` gave 4.5% coverage and
   left the whole watermark. Debug `lw_clean_dekel.align_rois` + retune `MATTE_ALPHA_THR`
   0.12 -> ~0.03-0.05 before trusting the matte path.
3. **Narrow-region flank residue** (viego confirmed, aidraw): YOLO+OCR envelope under-
   covers long/low-contrast credit strings (stylized text reads low-conf). For the
   bottom-center banner class, expand to a FULL-WIDTH band with generous x-pad.
4. **Low-contrast coloured marks** (spirit-blossom blue, viego/kayle cyan): default the
   CHROMA term ON (`--chroma-thr ~12`) for the banner detect path. Confirmed clears them.
5. **Residue-check blind spot**: `dev_after` high-pass energy misses low-freq ghosts.
   Add an OCR / template re-read INSIDE the mark band on the after image.
6. **Hard MANUAL guard**: cov > ~65% AND high pre-clean detail-energy -> force MANUAL
   (the gate's `not_border -> qa` already partly predicts these).

## Next-session plan

1. Land improvements 3+4 (full-width banner band + chroma-on default) - clears 3
   confirmed PARTIALs (spirit-blossom, viego, aidraw) to CLEAN.
2. Land improvement 1 (namakx template-mask or adaptive dark_thr) - clears the 3
   namakx dark-outline ghosts (dfz5w2g, dfzypou, kayle).
3. Re-run the worker over the CLEAN-AUTO 9 + the now-cleared PARTIALs -> save-working
   --tool iopaint + submit for operator needauth.
4. Route fantasy-design + prestige-coven-xayah (+ fury-sona if fidelity matters) to the
   MANUAL IOPaint lane (launch in ROADMAP / WAKEUP).
5. Then clean-scan the 190 clean firstdones.
