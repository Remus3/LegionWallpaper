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

## The replay: our fill is NOT the problem

The operator proposed the decisive experiment - replay their captured masks in
order, each waiting on the committed result of the last, and see what can be
inferred. `tools/lw_clean_replay.py` does exactly that: mask 1..82 through
simple-lama, cropped around each mask the way IOPaint's crop strategy does.

**The replayed frame is clean.** Text gone, art intact, the brush handle that
crosses the credit line survives, no seams, no speckles - visually equivalent to
the operator's own result.

| variant | in-mask mean distance to the operator's final |
|---|---|
| untouched original | 15.22 |
| best derived-mask attempt (contours + gated subdivision) | 11.12 |
| **replay of the operator's own masks** | **7.74** (72.9% within 8 levels) |

Per-step divergence stayed BOUNDED across all 82 steps (median 8.59, max 13.04)
rather than growing, which rules out drift from sequential commits.

Two conclusions, and they redirect the whole effort:

1. **The fill engine is adequate.** Given the right mask, our pipeline produces
   an acceptable clean. Every rejected candidate was a MASK failure wearing a
   fill failure's clothes.
2. **The residual 7.74 is engine difference, not method** - IOPaint's LaMa
   serving versus simple-lama. It is not worth closing; the frame is acceptable
   at that distance.

So mask GENERATION is the entire remaining problem, and the captures say what it
has to produce.

## What the stroke pattern actually is (forward and backward)

Reading the 82 steps in both directions - each step against the one before, and
each step against the finished frame - contradicts the obvious model:

- **median NEW area per stroke: 3.0%.** 97% of every stroke re-covers ground
  already brushed. This is not a sweep with small strokes.
- **direction is not monotonic:** 52 of 81 steps move right, the rest backtrack;
  the x centroid wanders 1237 -> 1376 and ends back at 1273.
- **no coarse-to-fine phase:** new area is 3.1% in the first half, 2.8% in the
  second.
- **the work is back-loaded:** after 40 of 82 steps the frame is still at 12.97
  of its starting 15.06 distance from the final. **86% of the convergence
  happens in the last 30 steps**, as the mask grows past ~10k px.
- **the mask grows 55x** from first stroke (382 px) to last (21,157 px) over one
  small area.

So the method is: park on a spot, re-brush it repeatedly with a mask that keeps
GROWING, move on, come back. The generator has to reproduce that schedule, not a
one-shot mask and not a fixed-size multi-pass.

## 107-cleanup: the fill holds, the residue detector does not

The operator asked for the harder slug to get the same treatment, noting it was
trickier despite fewer strokes. The captures say why, and the two runs split the
remaining problem cleanly.

| | 105-cleanup | 107-cleanup |
|---|---|---|
| footprint | 21,766 px | 84,998 px |
| shape | 549 x 69, a line | 674 x 290, an AREA |
| residue as share of footprint | 41.8% | 13.0% |
| luma spread across the band | 27.0 | 31.9 |

**Replay of their 46 masks: GOOD.** Hair, shoulder and pendant intact; in-mask
distance 12.35 against 23.39 untouched. The fill holds on the harder case too,
which matches the 105 replay the operator passed.

**Schedule on derived masks: FAILS, worse than doing nothing** - 27.95 against
23.39 untouched, with the character's hair and shoulder smeared where 105 came
out clean.

The cause is the detector, not the fill, and the same fill given the operator's
masks proves it. On 107 the footprint covers real ART rather than a text line,
so the residue detector fires on genuine detail and the generator repaints it.

**The blunt confirming measurement: the operator's OWN accepted frames still
read 3,986 px (105) and 5,761 px (107) as residue by this detector.** Absolute
residue is therefore neither a valid target nor a valid stop rule. "Blended out"
has to mean INDISTINGUISHABLE FROM THE SURROUNDING ART - measured against a
control region of the same image - not a fixed pixel count.

NEXT, and it is a measurement change rather than another fill pass: define
residue relative to a control band of untouched art in the same frame, and stop
when the footprint's residue density reaches the control's. Do not run more fill
variants until that lands - the 105 success and the 107 damage came from the
same code, so the difference is entirely in what the detector called residue.

## The relative residue measure: built, calibrated, and it cannot start the work

Implemented as `control_band` + `calibrate_threshold` + `relative_residue`: take
a ring of untouched art just outside the footprint, calibrate the deviation
threshold on it so "residue" means busier than THIS picture's own detail, and
stop when the footprint's density matches the control's.

Calibrated against frames whose answer is known:

| frame | excess ratio | footprint density | control | would |
|---|---|---|---|---|
| 105 untouched, MARK PRESENT | 1.01 | 5.1% | 5.0% | stop |
| 105 operator accepted | 0.64 | 3.2% | 5.0% | stop |
| 107 untouched, MARK PRESENT | 0.36 | 1.8% | 5.0% | stop |
| 107 operator accepted | 0.17 | 0.8% | 5.0% | stop |

**It reports no excess on frames that still carry the watermark.** The measure
is not buggy - it answers "is this region busier than the art beside it", and a
semi-transparent credit line honestly is not. That is the whole lesson: these
marks are low-amplitude COHERENT STRUCTURE, and every detector tried so far
keys on local contrast, which fires on brush detail (the absolute version,
which damaged 107) and misses text (this relative version).

What it IS good for: an accepted frame scores lower than an untouched one on
both slugs (0.64 vs 1.01, 0.17 vs 0.36), so the shape works as a STOP rule once
work is underway. It cannot decide where to start.

WHAT A DETECTOR ACTUALLY NEEDS, stated so the next attempt does not repeat this
family: a feature that sees COHERENCE rather than amplitude. Three candidates,
none tried yet - template correlation against the known overlay (already exists
for the centre mark and is the one proven detector in this repo), an OCR-driven
legibility measure (the ROADMAP already records that a ship gate needs one), and
supervised learning from the 128 captured hand-clean steps, which are labelled
by construction.

