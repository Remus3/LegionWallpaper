# Centre-overlay removal, part 2: the matte SEEDS the LaMa mask

2026-08-11. Follows `docs/CLEAN_OVERLAY_DETECTOR_2026-08-11.md` (LEDGER 93, the
detector) and the algebraic removal (LEDGER 94), which measured itself to a
detector score of 0.112 and then stopped at a legible ghost.

## The premise this session inherited

The ghost is an INPAINTING problem, not more matting. Two independent solves have
now hit the same wall from opposite ends:

* `lw_clean_dekel.py` (LEDGER 29, `bad25c8`) has Levin's closed-form matte, IRLS
  and sub-pixel alignment. It capped with a dark-stroke ghost.
* `lw_clean_overlay.estimate_matte` (LEDGER 94) recovers a cross-image alpha over
  19 registered frames. It capped with the same ghost.

Both cap for one reason: the DeviantArt mark is a white FILL plus a dark OUTLINE,
and a single achromatic `W` cannot both add white and darken an edge. The shipped
answer for that shape of mark is LEDGER 30 - masked LaMa over a mask that covers
the outline too - so this session wired the matte into that mask builder.

## What was built

`tools/lw_clean_iopaint.py --overlay`, one lane, four steps:

1. **Register** the frame against the overlay template (`best_shift`).
2. **Algebraic pre-pass** - `remove_overlay` inverts `J = (I - aW)/(1-a)` over the
   whole matte. This is deliberately FIRST: the logo is a 310x240px flat veil over
   a face on `mecha-ahri`, and no filler should be asked to invent that much.
3. **Mask** what the inversion could not fix: threshold the matte (`alpha >=
   0.08`), open, drop specks by local DENSITY, dilate, take the bbox as the ROI,
   then complete the mask with THIS frame's own residual (the validated
   diff-from-median rule) inside a gate around the seed - 7px ACROSS the strokes,
   40px ALONG the credit line, and the sideways reach accepts only BRIGHT residual
   because the nearest art it can touch is the dark lip line one band below.
4. **One LaMa pass** over that ROI, then the standard outside-ROI identity
   tripwire.

Three measurements decided the knobs:

| knob | value | why |
| --- | --- | --- |
| removal band | `REMOVAL_BAND = (0.45, 0.85)` | the detector's band starts at 0.55h, but the logo's top edge sits at y/h ~ 0.506 (row 728 of 1440). Detection never cared; removal does - the clipped 64 rows are a flat veil the inversion never touched. The detector's calibrated `BAND` was NOT moved: the removal pair is cached separately (`*_wide.npz`). |
| `alpha >= 0.08` | seed | 0.03 stretches the ROI from the mark's own 550x290 to 1229x624 by dragging in estimator speckle; 0.12 keeps the same bbox with 30 percent less seed. |
| horizontal reach | +-40px, bright-only | the seed stopped ~40px short of the leading "(C)", which survived the first run while every glyph the seed reached cleared. A round gate that far also reaches the lips directly below. |
| density filter | 25 px in a 31x31 box | the opening leaves ~8 round specks; erosion cannot drop them without dropping real 4-6px strokes, but density can (a stroke fills ~124 of that box, a speck 9). |

## Measured result

Over all **32** `centre_overlay`-flagged slugs in
`ops/runtime/clean_recall_census_gatev3b.json`, one pass each:

| | before | after |
| --- | --- | --- |
| median detector score | 0.310 | **0.069** |
| worst frame | 0.696 | **0.115** |
| under the 0.15 flag | 0 of 32 | **32 of 32** |

Median mask coverage 14.1 percent of the ROI. Outside-ROI byte identity held on
every slug (`assert_region_identity`, and the pre-pass baseline is the frame it
compares against). Candidates + per-slug JSON: `ops/runtime/clean/overlay_lane/`.

BY EYE, at 1:1, the two halves of the mark behave differently:

* the **credit line clears** - `bayonetta-dm7iirw`, `239f`, `khanzaaiart-dmbzcmq`
  and the rest of the busy/dark frames come back with no visible trace and no
  visible smear;
* the **logo's flat veil survives on smooth art** - clearly on
  `miss-fortune-dmcdsno` (a lighter polygon over the neck) and `mecha-ahri`
  (over the cheek). On busy art it is invisible.

So the score bar is met everywhere and the eye bar is met only where the art
hides the veil. These stay QA proposals - the lane never auto-approves.

## What is still NOT solved, and exactly why

The credit line clears. The LOGO's flat interior does not, and the cause is now
pinned rather than guessed: **the template's support is the top 2 percent of the
median HIGH-PASS, so a flat region contributes nothing to it.** Measured on
`mecha-ahri`, matte alpha inside the logo is exactly `0.0` while its edges carry
alpha up to 0.25 - the veil interior is invisible to the detector AND to the
matte, so the inversion leaves the step and LaMa is only ever handed the outline.

That is a different estimator, not a tuning pass. Do NOT approach it by lowering
the alpha threshold or widening the mask - masking the interior hands LaMa
310x240px of face to hallucinate, which is worse than the veil.

**A probe of the next estimator was run, and it half-works - start from here.**
Same whitening `lw_clean_dekel.estimate_filled_alpha` uses, `a ~ (gray - bg) /
(255 - bg)`, but with a background window WIDER THAN THE VEIL, median-combined
over the registered collection (14 frames):

| background window | logo interior alpha | art far from the mark |
| --- | --- | --- |
| 201px median | 0.028 | 0.003 |
| ~408px (median 51 on a 1/8 downscale) | **0.060** | 0.005 |

The silhouette comes out FILLED and legible - the logo reads as a solid shape,
which the high-pass template never sees. Two things still block it:

* it UNDERREADS. The step measured across the logo's own boundary on `mecha-ahri`
  is ~20 levels over `J ~ 110`, i.e. `a ~ 0.14`, against the estimator's 0.060 -
  the background window still partly follows the veil, so the interior is damped.
  Calibrating against the boundary step (`a = step / (W - J)`) is the obvious fix.
* its support SPRAWLS. At 0.05, art residue that 14 frames did not cancel spans
  x 643-2290 of the band, so the veil needs a support gate at least as strict as
  the density filter used for the strokes before it can drive a removal.

`cv2.medianBlur` cannot be used at that width (it asserts `k < 16` above 8-bit
ksize 5); the downscale-median-upscale path is also the one that keeps this
CI-safe.

## Reproduce

```
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_detector_probe.py --wide --build-overlay-template <the 19 confirmed slugs>
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_detector_probe.py --wide --build-overlay-matte <the same 19>
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_iopaint.py <slug> --overlay
```

The template and matte are derivatives of a third party's watermark: both live
under `ops/runtime/clean/` (gitignored) and are never tracked in this public repo.
