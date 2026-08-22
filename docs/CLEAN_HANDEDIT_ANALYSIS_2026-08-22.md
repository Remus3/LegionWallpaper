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
