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

Measured lead for whoever picks that up - **the algebraic pre-pass ALONE nearly
clears the flag**, so on most of this family the inpaint may be optional:

| frame | raw | pre-pass only |
| --- | --- | --- |
| mecha-ahri | 0.6958 | 0.1560 |
| 245f | 0.5858 | 0.1208 |
| miss-fortune | 0.5853 | 0.0984 |
| ahri-dmbclo0 | 0.5645 | 0.0840 |
| bayonetta-dm7iirw | 0.4476 | 0.0833 |
| 225f | 0.3967 | 0.1136 |

Five of six are already under 0.15 with ZERO invented pixels. A "skip LaMa when
the pre-pass clears" rule is worth measuring over all 32 - it is NOT shipped
here, because six frames is not the population.

## 6. Do not redo

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
