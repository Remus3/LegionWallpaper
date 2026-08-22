# How the operator actually cleans: 82 iterations on 105-cleanup, quantified

Ground truth captured 2026-08-22. The operator hand-cleaned one slug in the
IOPaint UI and saved every iteration - the highlighted target, the brush mask,
and the output - 82 of each. This is the measurement that explains why every
automated candidate produced that day was rejected.

## The numbers, per iteration

| quantity | median | min | max |
|---|---|---|---|
| brush mask (px) | 6495 | 382 | 21157 |
| brush mask (% of frame) | 0.176% | 0.010% | 0.574% |
| pixels actually CHANGED | 766 | 279 | 5263 |
| mask bbox w x h | 218 x 56 | - | 549 x 69 |
| mean level delta where changed | 11.8 | - | - |

Cumulative over all 82 steps: **21766 pixels changed, 0.59044% of the frame**, confined to a 549 x 69 strip (the artist credit line).

## Why the automated lane failed, in one comparison

The operator's ENTIRE 82-step edit changed 21,766 pixels. A single mask from
the automated overlay lane on this same slug covered ~36,800 pixels, and the
region lane's masks ran to a median 47.6% of their ROI. **The automated lane's
one shot was larger than the operator's whole cumulative edit** - and it was
applied at once, so LaMa had to invent a large contiguous area instead of
closing a hole it could see around.

IOPaint's own logs name the mechanism: every call reports `Run crop strategy`
at 120-190ms. It crops a small region around the brush mask, so the model only
ever sees local context and returns local texture. Feed it a mask covering half
the ROI and that advantage is gone - which is exactly the blur, the smudging,
and the lines that fail to re-align across the boundary.

The operator put it plainly: it cannot be done in one big step, which is why
the prior outputs failed 100%.

## The automation target this sets

Not a better mask. A DECOMPOSED one: split the mark into small pieces on the
order of 0.18% of frame each, inpaint each with a tight crop, commit, repeat.
The existing `--progressive` mode is NOT this - it erodes rings off a single
large mask, which keeps the large hole on the first pass. What the operator does
is spatial tiling in sequence.

## A caution about scoring this work

The accepted result scores `overlay_score` 0.2756, ABOVE the 0.15 flag, while
the rejected automated candidate scores 0.0496. That is NOT the score inverting
on quality - checked before claiming it. The two edits address DIFFERENT marks:
105-cleanup carries both the centre veil (what the score measures) and the
bottom credit line (what the operator removed in these 82 steps). The veil is
still there in the accepted frame. The lesson stands anyway - a single scalar
over a frame with two marks cannot gate either one.

## Second capture: 107-cleanup, 46 iterations with deliberately broader strokes

The operator cleaned a second slug and named their reason unprompted: broader
strokes "due to the softer color gradient transitions being so prominent". That
turns a stylistic remark into a testable scaling rule, and the numbers agree.

| | 105-cleanup | 107-cleanup |
|---|---|---|
| iterations | 82 | 46 |
| median brush mask | 6,495 px (0.176% of frame) | 16,298 px (0.442%) |
| median changed px | 766 | 1,996 |
| median mask bbox | 218 x 56 | 366 x 105 |
| cumulative changed | 21,766 px (0.590%) | 84,998 px (2.306%) |
| **changed / mask** | **0.118** | **0.122** |
| median local gradient near the stroke | 3.48 | 2.70 |

Two things fall out.

**1. The margin ratio is invariant.** Across a 2.5x change in stroke size, LaMa
changes ~12% of what was brushed in BOTH captures. The operator consistently
brushes about eight times the area that actually needs to change - a generous
margin around the mark is part of the method, not sloppiness. Any automated mask
that hugs the glyph is not reproducing this.

**2. Stroke size tracks the local gradient, inversely, exactly as stated.** The
softer slug (median local gradient 2.70) got 2.5x LARGER strokes than the busier
one (3.48). That is the scaling rule the automation needs: smooth art tolerates
big tiles, high-frequency art demands small ones.

CAUTION on the within-slug correlation (+0.32 on 105, +0.51 on 107): it has the
OPPOSITE sign to the across-slug relation, and it is almost certainly an artifact
- gradient is measured over the mask bbox neighbourhood, so a larger stroke pulls
in more varied art and reads a higher gradient by construction. Do not fit on it.
The across-slug direction is n=2: a direction to build toward and re-measure, not
a law to hard-code.

## What to build, concretely

A tiled decomposition worker: split the mark mask into ordered tiles, inpaint
each with a tight crop around it, commit, repeat - the loop IOPaint's UI performs
by hand. Two calibration anchors from the captures:

- tile target area: ~6.5k px where local gradient is ~3.5, ~16k px where it is
  ~2.7 (inverse, re-measure as more captures land)
- dilate the mark to roughly 8x its own area before tiling, matching the observed
  changed/mask ratio of 0.12

Validation is available and honest: run it on 105-cleanup and 107-cleanup and
compare against the operator's own finals pixel-for-pixel. Anything that cannot
land near those two does not ship.

