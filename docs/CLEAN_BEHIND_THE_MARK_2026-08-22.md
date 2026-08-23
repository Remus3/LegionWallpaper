# Track A: the mark stops voting on how it should be treated

Track A of the zero-residue cleaning work: analyse the content BEHIND the mark,
not the frame that still carries it. Built, wired into the consumer, and
measured against the only ground truth that exists - the operator's four
accepted hand-clean finals, which ARE the art behind those marks.

## The bug, re-measured live rather than taken from the doc

`lw_clean_tiled.local_gradient` measures busyness on the marked frame, and
`target_tile_area` turns that into a stroke size, inversely. So a loud mark
inflates its own busyness and buys itself the smallest possible strokes.

| capture | art | marked | true | error | tile area marked -> true |
|---|---|---|---|---|---|
| 105-cleanup | credit line, folded fabric | 3.684 | 2.878 | +28% | 5102 -> 13211 |
| 107-cleanup | area, soft gradients | 3.179 | 2.907 | +9% | 9263 -> 12764 |
| 209-cleanup | signature, smooth panel | 7.754 | 2.247 | **+245%** | **2000** -> 27805 |
| dgk8f92 | block, soft snow | 5.467 | 0.778 | **+603%** | **2000** -> 40000 |

The two SMOOTHEST images in the set are the two slammed into the 2000px tile
floor, because their marks are the loudest thing in frame. 209 is the case that
makes it undeniable: the operator cleaned it in ONE stroke, and the rule would
have prescribed the minimum tile. This is not mis-tuning, it is reading the
wrong picture - which is exactly what the four-capture analysis predicted when
it flagged `local_gradient` as measuring the mark it was measuring.

## Two things were needed, and conflating them was the trap

**The STATISTIC** decides stroke size. `lw_clean_tiled.local_gradient` now takes
`exclude=`: a first difference is counted only when BOTH its endpoints are
readable, so no masked value reaches the result through either end of a
gradient. It invents nothing and assumes only that the art under the mark
resembles the art beside it. With `exclude` unset it is bit-identical to the
version the tile-size anchors were fitted with, which is asserted in the suite -
otherwise every anchor in the repo would quietly change meaning.

**The ESTIMATE** gives stroke placement something to look at.
`lw_clean_behind.behind_image` solves the membrane (harmonic) problem inside the
mark: the smoothest field meeting the surrounding art exactly. It recovers tone
and low-frequency structure and invents no texture.

The estimate must NOT be what the statistic is taken on. A harmonic fill is
smooth by construction and biases busyness DOWN as surely as the mark biases it
up. That was predicted in the module before it was measured, and the census
confirms it: the membrane measure reads low on all four captures (-3.6% to
-20.6%), never high.

## Census, against the operator's finals

`python tools/lw_clean_behind_census.py`

| estimator | mean abs error | worst |
|---|---|---|
| marked (incumbent) | **221.3%** | 603.0% |
| excluded (track A) | **14.6%** | 27.8% |
| membrane (shown to be rejected) | 13.8% | 20.6% |

A 15x reduction in mean error. `excluded` is the one adopted: it is principled
rather than merely close, it carries a hard "cannot read a masked pixel"
guarantee, and its errors are signed both ways rather than systematically low.
The membrane column's slightly better average is a systematic bias that a
one-parameter fit on four points would flatter - four points is not enough to
fit anything, and this repo has a standing rule about exactly that.

The one case where `excluded` loses to the incumbent is 107 (+25.9% against
+9.3%): its mask is 84k px and the readable ring around it is the busy mechanical
armour, so the art beside the mark is genuinely not the art under it. That is
the estimator's stated assumption failing, and it is the honest limit of it.

## A second, unlooked-for result: when the estimate can be trusted

In-mask distance between an estimate and the operator's final - how much it
actually knows about what is under the mark:

| capture | true busyness | marked | **behind estimate** |
|---|---|---|---|
| dgk8f92 | 0.778 | 49.89 | **5.09** |
| 209-cleanup | 2.247 | 27.26 | **1.95** |
| 105-cleanup | 2.878 | 15.45 | 14.67 |
| 107-cleanup | 2.907 | 23.50 | 35.71 |

The membrane estimate is an excellent picture of what is behind the mark on the
two smooth captures and useless to harmful on the two structured ones, and the
ordering against true busyness is perfect: the estimate is trustworthy exactly
where the art is smooth. Physics says so too - a harmonic solve recovers
low-frequency content and cannot recover texture.

So the statistic gates the estimate: the unbiased busyness measure is what tells
you whether the picture behind the mark is worth looking at. **No threshold is
set here.** Four captures order correctly but cannot calibrate a cut, and
inventing one from them would repeat a mistake this repo has already logged
twice.

Worth noting in passing: on dgk8f92 the membrane estimate alone - pure numpy, no
model, deterministic - lands at 5.09 against LaMa's 2.38, from an untouched
49.89, and is visually indistinguishable from the operator's frame at 1:1.

## What is wired

- `lw_clean_tiled.local_gradient(img, box, pad, exclude=None)` - the primitive.
- `lw_clean_tiled.build_plan` now excludes the mark BY DEFAULT (it was already
  holding the mask; it just was not using it), and takes a `gradient=` override
  so a caller can supply a policy-computed value.
- `lw_clean_tiled.subdivide_labels(..., exclude=)` - the sibling case, found by
  grepping for the same root cause. That gate reads a region OF the footprint,
  so without the exclusion it was measuring the mark almost exclusively and
  subdividing flat art it was written to leave whole. The `--contours` path in
  the CLI passes the mark through both.
- `lw_clean_behind` holds the POLICY: halo dilation (3px - a brush mask stops at
  the mark's visible edge and a semi-transparent mark has a soft skirt beyond
  it), and widening the window when the mark fills it, because a mark covering
  everything the probe can see is not evidence of smooth art and a confident 0.0
  there hands it the maximum tile - the same failure in the other direction.

14 tests in `tests/test_lw_clean_behind.py`, written first (RED confirmed), plus
the calibration-cannot-drift assertion and a property test that wrecks the
pixels under the mask and requires the measure not to move at all. Full suite
2196 passed / 18 skipped.

Artifacts (gitignored): `ops/runtime/clean/behind/behind_census.json` and
`sheet_*_behind.png` - original, estimate, operator truth, at 1:1.

## Do not redo

- Do not take busyness on the marked frame anywhere in the cleaning stack. Both
  remaining call sites were fixed; a new one needs `exclude=`.
- Do not measure busyness on the behind-the-mark estimate. It is smooth by
  construction and the census shows the resulting bias.
- Do not fit a trust threshold for the estimate on these four captures.
