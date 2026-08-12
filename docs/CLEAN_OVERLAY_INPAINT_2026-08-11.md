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

## Measured result: strokes only (part 1)

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

So part 1 met the score bar everywhere and the eye bar only where the art hid the
veil. Part 2 below closes that gap; these numbers are kept because they are what
isolates the veil's contribution.

## Part 2: the flat veil, calibrated against its own boundary step

The logo's interior is invisible to a high-pass template - matte alpha there is
exactly 0.0 - so it gets its own estimator, `lw_clean_overlay.estimate_veil`:

1. **Whiten** each registered frame, `a ~ (gray - bg) / (255 - bg)`, with `bg`
   over a window WIDER than the veil (~408px, built by downscale -> median ->
   upscale; `cv2.medianBlur` asserts `k < 16` at that width).
2. **Consensus, not median**, across the collection: art structure the median
   cannot cancel is high in a FEW frames, the veil is high in ALL of them, so the
   25th percentile separates them. Measured on the fixture: the median leaves 19
   percent of the art above threshold, the low quartile leaves 0.4 percent.
3. **Support** = smooth -> threshold 0.015 -> open (thin art residue) -> close
   (a solid region still thresholds ragged). It deliberately stops ~10px INSIDE
   the veil's true edge: over-reaching would darken real art by the full veil
   alpha.
4. **Calibrate** the amplitude against the veil's own boundary step - pick the
   gain whose removal leaves no level difference between a ring inside and a ring
   outside. Both rings stand off the support by the same 2-3 ring widths; a ring
   flush against it was measured to be only 56 percent veil, which halved the
   step and so halved the alpha.

Recovered on the corpus: **alpha 0.133** (raw 0.027 x gain 5.0, an interior
optimum - a grid to 10.5 still picks 5.0), support 38375 px whose bbox is
285x282, i.e. the logo silhouette. That matches the ~0.14 read directly off the
boundary step on `mecha-ahri`, which is the number this was built to hit.

The veil is stored beside the stroke alpha in the matte, never merged into it:
the inversion applies to both (`remove_overlay` maxes them), while the LaMa mask
takes the strokes plus a 9px ring around the veil's boundary ONLY. That ring is
there because the support is a median and each frame's own edge sits a few pixels
off it, which leaves a hard step the filler blends away. The 310x240px interior
is never inpainted.

Re-run over the same 32 slugs with the veil in the matte:

| | before | strokes only | + veil |
| --- | --- | --- | --- |
| median detector score | 0.310 | 0.069 | **0.068** |
| worst frame | 0.696 | 0.115 | **0.125** |
| under the 0.15 flag | 0 of 32 | 32 of 32 | **32 of 32** |
| median mask coverage | - | 14.1% | 18.9% |

The score barely moves, and that is the expected result, not a disappointment:
the detector is a HIGH-PASS correlator, so a flat veil was never part of what it
measured. The change is entirely in what the frame looks like. `245f` now comes
back with both the veil polygon and the credit line gone and the art intact;
`miss-fortune-dmcdsno`, whose lighter polygon over the neck was the clearest
part-1 failure, is clean; `mecha-ahri` - pale flat skin, the worst case in the
corpus - is down to a soft blur where LaMa worked, with no legible mark.

## What is still NOT solved, and exactly why

The credit line clears and the veil is now removed algebraically. What remains on
the hardest frames (pale, flat art like `mecha-ahri`) is LaMa's own softening
along the masked strokes - a blur, not a legible mark - plus a faint seam where
the veil ring was blended. Do NOT chase it by masking the veil interior: handing
a filler 310x240px of face is worse than anything it would replace.

The other open items are unchanged from the detector census: thin painted
signatures and an off-band wordmark need their own detector, and whether the 46
`qa` images carry real marks was never labelled.


## Reproduce

```
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_detector_probe.py --wide --build-overlay-template <the 19 confirmed slugs>
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_detector_probe.py --wide --build-overlay-matte <the same 19>
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_iopaint.py <slug> --overlay
```

The template and matte are derivatives of a third party's watermark: both live
under `ops/runtime/clean/` (gitignored) and are never tracked in this public repo.
