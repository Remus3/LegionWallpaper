# The overlay lane's softening on pale flat art - ruling and fix (2026-08-12)

ROADMAP `cleaning-detector-recall` item **(a)**. The open question was whether
LaMa's softening along the masked strokes on pale flat art (`mecha-ahri`) is
acceptable at 1:1, needs a narrower mask, or needs a different fill.

**Ruling, in one line: it is NOT acceptable, the mask WAS too wide, and the
excess was not the strokes - it was a ring the pipeline added to hide a cliff it
had created itself.** The ring is gone; `mecha-ahri` still goes to the manual
lane.

## 1. The candidate fails by eye at 1:1

The lane's ROI on this slug is 666x442 at the 2560x1440 deliverable scale, so
the side-files ARE 1:1 - no zoom was needed to judge it. Viewed:
`_overlay_raw.png` (original), `_iopaint_before.png` (the algebraic pre-pass,
i.e. what LaMa is handed) and `_iopaint_after.png`.

- The nose loses its nostril edge and gains a horizontal seam.
- The upper lip is a pale wash where the credit line crossed it.
- Rectangular blocks are visible where the mask's stair-stepped boundary was.

That is not "a blur, not a legible mark" (the LEDGER 96 characterisation). It is
structural damage to a face, and the frame must not be approved.

## 2. What the mask was actually made of

Decomposed on `mecha-ahri` (ROI 294372 px):

| component | px | % of ROI |
| --- | --- | --- |
| strokes (matte alpha >= 0.08) | 17778 | 6.04 |
| **veil boundary ring** | **21205** | **7.20** |
| completion from this frame's residual | 24838 | 8.44 |
| TOTAL handed to LaMa | 63821 | 21.68 |

A third of the mask was the veil ring: a ~25px band (`VEIL_EDGE_R` 9 -> a 19px
ring, plus `DILATE_K` 7) that traces the logo's boundary wherever the logo sits.
On this frame it runs diagonally across the nose and the nostril.

## 3. The ring was hiding a cliff the pipeline made

The veil support is deliberately eroded to stop inside the veil's true edge
(`lw_clean_overlay._veil_support`), and the ring existed because "the correction
leaves a hard step there". Both halves of that were measured on the corpus, and
the second one is much worse than the docstring's "~10px" implied.

Signed-distance profile across the recorded support boundary, means over the
whole boundary, strokes excluded, six frames:

| frame | step in the ORIGINAL | step after the inversion |
| --- | --- | --- |
| mecha-ahri | +0.7 | 20.8 |
| miss-fortune-dmcdsno | +0.3 | 27.3 |
| 245f | 0.0 | 24.8 |
| ahri-dmbclo0 | +0.4 | 26.8 |
| bayonetta-dm7iirw | +0.9 | 27.4 |
| 225f | -0.7 | 12.7 |

**The original carries no step at that line (6 of 6, |step| <= 0.9 levels) -
both sides are veiled alike, which is exactly what an eroded support implies.**
A hard-edged correction there therefore MANUFACTURES a 12.7-27.4 level edge that
was never in the art. Per pixel it reads as a p99 jump of 11.8-16.1 levels
against an art-only control of ~1.

So the lane was creating an artifact and then paying for a filler to paint over
it, on real art, in the middle of the frame.

## 4. Fix at the cause: feather the correction, drop the ring

`veil_alpha_map` now ramps the veil alpha linearly to zero over
`VEIL_FEATHER = 16` px outside the support (successive 3x3 dilations - the module
stays on numpy + PIL for CI). `overlay_mask` no longer ORs the ring into the LaMa
mask at all, and `VEIL_EDGE_R` is retired.

The extension was swept, not guessed. Introduced discontinuity = max over the
profile of |delta(corrected) - delta(original)| between adjacent distance bins:

| extension | introduced (mean) | introduced (max) | cliff at the support |
| --- | --- | --- | --- |
| 0px (was) | 23.30 | 27.36 | 23.30 |
| 8px | 3.37 | 4.07 | 3.30 |
| **16px** | **2.12** | **2.52** | **1.67** |
| 24px | 1.72 | 2.05 | 1.12 |
| 32px | 1.52 | 1.83 | 0.85 |
| 56px | 1.28 | 1.55 | 0.49 |

16px is the knee, and the SMALLEST extension that clears the cliff is the safest
one, because a ramp that reaches past the veil darkens real art. Per-pixel, the
p99 gradient of the correction field on the boundary band goes 11.8/16.1/14.9 ->
3.4/2.2/2.2 on mecha-ahri / miss-fortune / 245f.

Live result on three frames, feather vs the shipped ring:

| frame | mask px | coverage | detector score |
| --- | --- | --- | --- |
| mecha-ahri | 63821 -> **42326** | 21.68% -> **14.38%** | 0.0737 -> 0.0915 |
| 245f | 52833 -> **33188** | 17.95% -> **11.27%** | 0.0903 -> **0.0721** |
| miss-fortune | 50243 -> **29990** | 17.07% -> **10.19%** | 0.0578 -> 0.0692 |

Re-run over **the whole flagged family, 33 slugs** (the 32 of LEDGER 95/96 plus
`110-cleanup`, all registered by the LEDGER 99 scale search):

| | ring-era | feathered |
| --- | --- | --- |
| median mask px | 63821 | **41349** (35% less) |
| median coverage | 18.84% | 14.08% |
| median detector score | 0.0680 | 0.0664 |
| worst detector score | 0.0941 | 0.0955 |
| under the 0.15 flag | 33 of 33 | **33 of 33** |

Read mask PIXELS, not coverage percent: the ROI shrinks with the mask, so a few
slugs (`261f`, `riven`, `the-ruined-king-viego`) show a nearly flat percentage
while their mask drops by 20-30 percent in pixels.

All stay far under the 0.15 flag, and the pre-pass frame - what LaMa is
handed - no longer carries the stepped polygon at all. Off disk, the difference
between the ring-era and feathered pre-pass on `mecha-ahri` is exactly the ramp
and nothing else: 17447 px inside one annulus (bbox 258-575 x 24-322 of the ROI),
max 28 levels, falling off smoothly. Outside-ROI changed pixels
re-measured OFF DISK against the source `_firstdone` are unchanged at
6383 / 6679 / 6696 px (median delta 4 levels, 57 px >= 20 on mecha-ahri), i.e.
the established inversion-across-the-band baseline, not a new leak.

## 5. mecha-ahri still goes to the manual lane

The feather fixes the lane. It does not save this frame: the logo's stroke
outline and the credit line genuinely lie across the nose and the upper lip, so
even the narrowed mask asks a filler to invent facial structure, and at 1:1 it
still shows. This slug joins `p2402-kda-evelynn` in the MANUAL IOPaint queue.

A first six-frame sample suggested the algebraic pre-pass alone nearly clears the
flag (5 of 6 under 0.15), which would have made the inpaint optional on most of
the family. Measured over all 33 it does not hold - see section 6.

## 6. "Skip LaMa when the pre-pass clears" - measured over all 33, REJECTED

The six-frame sample in section 5 was optimistic twice over.

**By score it is 21 of 33, not 5 of 6.** Pre-pass-only detector score: median
**0.1331**, p90 0.1683, max 0.2009, **21 of 33 under the 0.15 flag** (64%). The
population sits ON the threshold, where the LaMa candidates sit at median 0.0664
/ max 0.0955 - a different distribution, not a slightly worse one. The inversion
also RAISES the score on some frames (`110-cleanup` 0.1090 -> 0.1229, `270f`
0.1548 -> 0.1921, `dark-cosmic-ahri` 0.1508 -> 0.1580), which LEDGER 98 had
already recorded for `110-cleanup`.

**By eye it fails even where the score is best.** Credit-line strips cut at 1:1
from the three LOWEST pre-pass scores - `239f` 0.0760, `ahri-dmbclo0` 0.0840,
`bayonetta-dm7iirw` 0.0833, all at or under the clean population's own p50 of
0.0596-0.15 range - and viewed: **3 of 3 still read the credit line**
("STELLASTRIA.D" is plainly legible on `ahri-dmbclo0`). The LaMa candidate clears
all three.

**Why, measured.** Mean |gray - median21| over the lane's own mask pixels in the
credit-line band (the bottom 30% of the ROI), the same pixel set in all three
versions:

| | median stroke contrast | kept vs original |
| --- | --- | --- |
| original | 14.32 | - |
| pre-pass only | 15.97 | **103%** |
| pre-pass + LaMa | 7.00 | **48%** |

The algebraic pre-pass does not reduce the credit line's LOCAL contrast at all -
28 of 33 frames sit at or above 85%, and several exceed 100% because the
inversion lightens the background under the strokes. It suppresses the
whole-band high-pass CORRELATION (it removes the big flat logo, which is most of
the template's support), and that is a different quantity.

**The standing lesson is bigger than the rule:** `overlay_score` is a DETECTION
flag calibrated on untouched frames. It must never be used as a removal-QUALITY
gate. A frame can sit at 0.076 - deep inside the clean distribution - and still
show its artist credit line at 1:1. Any future "is this candidate good enough"
gate needs a legibility measure like the stroke-contrast one above, not the
detector score.

## 7. Do not redo

- Do NOT re-add the veil ring "to blend the edge". There is no edge to blend
  once the correction is feathered; the ring's only job was a cliff of the
  pipeline's own making. Pinned by
  `tests/test_lw_clean_overlay_veil.py::test_the_veil_is_never_handed_to_the_inpainter_at_all`.
- Do NOT read `hf_keep` (high-frequency retention inside the mask) as the
  damage signal. Measured across all 34 lane candidates it runs 0.27-0.76 and
  `mecha-ahri` sits at 0.452, RANK 9 - mid-pack. Every frame loses about half
  its high-frequency energy inside the mask; what makes this one visible is that
  the mask covers a nose on flat pale skin, not that LaMa blurred it harder.
- Do NOT chase the outside-ROI changed-pixel count. Unchanged from the
  established baseline; the inversion legitimately edits sub-threshold alpha
  across the whole band.
- Do NOT re-propose "skip LaMa when the pre-pass clears". Measured over all 33
  in section 6: 21 of 33 by score, and 3 of 3 of the BEST-scoring frames still
  show a legible credit line at 1:1.
- Do NOT gate removal quality on `overlay_score` in any form. It is a detection
  flag; the pre-pass keeps 103% of the credit line's stroke contrast while
  driving that score to 0.076.
- The veil AMPLITUDE is untouched and is NOT verified by this work.
  `_fit_veil_gain` calibrates alpha by matching a ring 16-24px inside the support
  against one 16-24px outside it, and section 3 shows the outer ring is itself
  still veiled. That is a separate open question; feathering is correct either
  way, because it only changes how the correction ENDS, not how strong it is.

## Reproduce

```
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_iopaint.py <slug> --overlay --image <firstdone> --out-dir ops\runtime\clean\overlay_feather\<slug>
```

Candidates and side-files live under `ops/runtime/clean/overlay_feather/`
(gitignored - they are derivatives of a third party's watermark). The
ring-era candidates in `ops/runtime/clean/overlay_lane/` are now STALE.
