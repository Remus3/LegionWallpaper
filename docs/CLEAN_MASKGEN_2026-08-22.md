# Mask generation: the question was mis-posed, and half of it is now solved

Mask generation has been the open problem since the automated cleaning lane
closed. This is what the investigation found, in the order it found it, because
the order is the argument.

## The template was never failing at what it does

The centre-overlay template is the one detector in the repo with a proven
record, and against the operator's brush masks it looked terrible: recall 0.405
on 105-cleanup and **0.086** on 107-cleanup, precision 0.36 and 0.39. Every
attempt to fix it by tuning made things worse - a sweep of four alpha thresholds
by three dilations landed at or below "do nothing" on both slugs, and a coherence
pass (close, then fill each blob's box) was worse still, with bigger masks
scoring worse than smaller ones.

Bigger being worse is the tell: a mask that is merely too small cannot be made
worse by growing it toward the mark. So the mask had to be in the wrong place.
Rendering it over the frame settled it in one look:

**The template finds the DA LOGO. The operator cleans the CREDIT LINE.** They
are different marks, in different places, and every recall number above was
scoring a logo detector against a credit-line gold standard.

The hand-clean captures are therefore PARTIAL gold: 105's capture cleans the
credit line and leaves a real, correctly-detected DA logo untouched.

## Why the template cannot find the credit line

It is a median over 19 frames from mixed uploaders, and the credit line carries
the uploader's name - `SLIMSHADYWALLPAPER` on 105, `SMALLTAVERNWALLPAPER` on 107.
The variable text averages out of the stack while the logo, identical
everywhere, survives. No threshold applied to a template that does not contain
the text will ever find it.

Grouping was tried first, since frames do group by uploader - the top-ranked
pairs by high-pass correlation are exactly same-uploader pairs, and 37 of 81
slugs carry `-by-<uploader>-` in the filename. A leave-one-out template built
from each frame's nearest neighbours did NOT help (recall 0.43-0.54 on 105
against the global 0.405): the groups run 1 to 7 frames, and a median over three
or five frames does not cancel the art.

## The credit line is text, so read it

`tools/lw_clean_creditline.py`. easyocr is already in the stack and found
nothing on these frames, which is unsurprising at full-frame scale on a
semi-transparent line. Shown the layout band, enhanced, it reads them:

| capture | read | confidence |
|---|---|---|
| 105 | `SLMSHADYWAALPAPERDEVIANTAR` | 0.725 |
| 107 | `SMALLTAVERNWALLPAPERDEVIAN` + `ARTGOM` | 0.745 |
| 209 (painted signature) | nothing | correct |

Four things make it work, and each was forced by a measurement:

- **A band, not a frame.** Both captures put the line at the same place -
  y 0.668-0.716 on 105, about 0.688 on 107, both horizontally centred.
- **Two enhancements, unioned.** Neither wins on both: 105 reads best off the
  high-pass boost (0.725 against 0.184 stretched), 107 off the stretch (0.745
  against 0.378).
- **Reads joined into LINES before verification.** easyocr splits 107's line
  and neither half carries the host on its own.
- **Approximate substring matching**, free at both ends. Observed reads include
  `DEVIANTAR`, `DEVIANFART` and `DEMIANTAR`; an exact match rejects every hit
  this exists to catch.

**The hit verifies itself.** The string contains DEVIANTART. That is a property
no contrast measure has, and it is why this is not the falsified residue
detector wearing a new hat.

## Measured

| question | result |
|---|---|
| covers the operator's own brush (105) | **0.9995** |
| box precision against the brush (105 / 107) | 0.50 / 0.79 |
| coverage of the queue | **39 of 80 slugs** carry a readable credit line |
| fires on operator-approved-clean frames | **1 of 119 sampled** |

The single fire on the negative set is `230-cleanup`, reading
`SMALLTANERNXDEVIANTART CAM` twice over. That reads like a real smalltavernx
credit line on a frame that was approved as clean, so it is a question for the
operator's eye rather than a proven false positive - and it is exactly the kind
of claim this repo has been burned by before, which is why the negative set was
sampled rather than assumed.

## The box is the right place and the wrong shape

Handed the solid read box, the proven fill BROKE A LINE and track C's rollback
reverted the whole step: the frame came out at 15.454 against 15.454 untouched.
The box covers 99.95% of the operator's brush but is 42328 px where their
stroke-shaped mask is 21184.

So the box is narrowed to the glyphs - the high-pass thresholded INSIDE a
verified box. That is not the global contrast residue this repo falsified: that
measure had to decide whether a mark was present, while this one already knows,
because the string said DEVIANTART, and only has to decide which pixels it lands
on.

End to end on 105, in-mask distance to the operator's accepted final:

| mask | frame | rollback |
|---|---|---|
| untouched | 15.45 | - |
| solid read box | 15.45 | held, step reverted |
| **glyphs (p88, grow 4)** | **11.56** | committed, 0 of 7 held |
| the operator's own brush | 8.08 | committed |

The first derived mask that meaningfully cleans 105 without breaking a line, and
it closes 55% of the gap between doing nothing and the operator's hand result.

**The two glyph constants are one slug picking one of nine cells.** They are a
starting point, not a calibration, and they are labelled as such in the module.

## What is and is not solved

- **Solved:** locating the DA credit line, on 39 of the 80 queued slugs, with a
  self-verifying detector and a mask the proven fill can use.
- **Not solved:** 107-class marks, where the operator brushed a large AREA and
  the credit line is only part of it (best 22.3 against untouched 23.5); the
  logo, which is detected but which no capture shows the operator removing; and
  the 41 slugs with no readable line - the painted signatures and block logos of
  the `not_border` bucket, which need a different instrument again.
- **A corrected anchor, worth more than any constant it replaces:** the
  operator's brush is only **1.05 to 1.65x** the pixels their clean actually
  changed. Measured on all four captures. This replaces the falsified "8x
  margin" and the `CONTEXT_RATIO = 5.0` derived from it.

## Do not redo

- Do not score a logo detector against a credit-line gold mask, or read the
  hand-clean captures as complete masks for their frames. They are partial.
- Do not tune the centre-overlay matte to find the credit line. The text is not
  in it and cannot be.
- Do not build per-uploader templates from groups of three to seven frames.
  Measured: no better than the global one.
