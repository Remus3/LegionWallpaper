# The healing brush, built and measured: track E does NOT beat the fill we have

Track E was the operator's named PRIMARY track for the zero-residue cleaning
work: "like photoshops healing brush", i.e. exemplar texture plus
gradient-domain (Poisson) blending rather than learned inpainting. It was built,
tested, and measured against all four hand-clean captures. It loses, on every
capture, on both the numbers and at 1:1.

This document is the evidence, so the track is closed with a reason instead of a
hunch, and so nobody rebuilds it.

## What was built

`tools/lw_clean_heal.py` - pure numpy + Pillow, no torch / cv2 / scipy, so it
runs in the fast CI lane:

- 8-connected blob labelling (run-length union-find), then a lossless grid
  decomposition into tiles near the operator's measured median stroke area;
- an exemplar search that scores candidate translations on the VALID annulus
  around each tile only, so the mark never votes on its own replacement, and
  that refuses any offset whose shifted patch would read a still-marked pixel;
- a Poisson solve (conjugate gradients on the masked Laplacian, Dirichlet on the
  hole boundary) that imports the source's gradients while pinning tone to the
  destination - the seam is matched by construction, not guessed;
- TWO-SIDED guidance: for a thin mark, one source from each side of it,
  crossfaded in the gradient domain across the mark, so structure entering one
  edge and leaving the other is carried by whichever side is nearer;
- a membrane (harmonic) fallback for the smooth case, where there is no texture
  worth importing.

18 tests in `tests/test_lw_clean_heal.py`, including the hard outside-mask
identity assertion, determinism, seam continuity against a deliberately
mismatched source, and a line-continuity test that encodes the exact defect that
got 45 candidates rejected.

## How it was measured

Two harnesses, both anchored on the operator's own captures:

1. `tools/lw_clean_replay.py --engine heal` - their masks, in order, each on the
   committed result of the last, diffed against their output at every step.
2. `tools/lw_clean_fill_bakeoff.py` - the fair engine comparison. The UNION of
   every mask they brushed, filled ONCE by each engine, scored against the frame
   they accepted. This exists because the replay is not an engine comparison: a
   heal is a one-shot instrument and re-solving one region 82 times compounds
   its own output, while a learned inpainter re-imagines it from a cleaner
   context each pass. The heal scores 14.0 through the 82-step replay on
   105-cleanup and 14.5 in one shot; LaMa goes the other way.

Mean in-mask distance to the operator's accepted final, one-shot, lower better:

| capture | mark | untouched | heal (2-sided) | heal (1-sided) | **lama** |
|---|---|---|---|---|---|
| 105-cleanup | credit line, folded fabric | 15.45 | 16.45 | 14.51 | **7.87** |
| 107-cleanup | area, soft gradients | 23.50 | 26.68 | 26.53 | **12.45** |
| 209-cleanup | signature, smooth panel | 27.26 | 5.90 | 13.97 | **1.28** |
| dgk8f92 | block, busy mid-frame | 49.89 | 5.61 | 5.28 | **2.38** |

Sheets at 1:1 in `ops/runtime/clean/heal/sheet_*.png` (gitignored): original,
operator, heal, lama, same crop, no resampling.

## Why it loses, which is the part worth keeping

**League splash art is painted, not textured.** There is no translation under
which its content repeats, so the exemplar search has nothing to lock onto. On
105-cleanup the best available source scores a ring RMSE of 26 to 38 against a
ring detail of 6 to 38 - the best patch in a 96px radius explains essentially
none of the surrounding structure. That is not a tuning failure, it is the
corpus.

With no usable exemplar, both remaining answers are bad:

- **membrane** (the first version's fallback, taken when the exemplar looked
  poor) is a blur. All 8 tiles on 105 fell back to it and the fabric was lost.
  That fallback rule was removed: on textured art an imperfect exemplar beats a
  smear, because Poisson imports only GRADIENTS and the tone is pinned either
  way. The constant is gone and the reason is recorded in the module.
- **forced exemplar** imports foreign structure. On 105 it invents crisp
  diagonal streaks that are not in the art; on 107 it drags whole ghost shapes
  across the orb. Deterministic, yes - but "deterministic" only rules out
  hallucination from a learned prior, not wrong content from a wrong patch.

The premise behind track E was that gradient-domain blending would preserve
lines where LaMa re-imagines them. The premise is sound in general and false
here: it preserves the SOURCE's lines, and on this corpus the source is wrong.

## What this settles

1. **The fill stays LaMa.** Given the operator's own masks, LaMa lands 7.87 /
   12.45 / 1.28 / 2.38 against their accepted finals and reads clean at 1:1 on
   all four. The earlier finding holds at the new zero-residue bar, and it is
   now backed by an engine comparison rather than a single-engine replay.
2. **Mask generation remains the entire open problem.** Nothing measured today
   moves that, and the four remaining tracks (A analyse behind the mark, B
   overlap-muxed comparison layer, C per-blob heal with rollback, D tone
   conditioning) are all mask-side. They are unaffected by this result.
3. **Do NOT rebuild the healing brush as a fill.** The code stays in the tree as
   a measured negative result and as a working Poisson solver; the bake-off
   harness stays because it is the honest way to compare any future fill.

## Caveat, stated rather than buried

Distance to the operator's final flatters LaMa: their finals came out of
IOPaint, which serves LaMa, so it is scored against its own family. Two things
make the conclusion hold anyway. On 105 and 107 the heal scores WORSE than
leaving the watermark in place, which no family bias explains - it moved the art
further from the target than the mark itself did. And the 1:1 sheets show the
smears and invented streaks directly, which is the standard the operator set.
