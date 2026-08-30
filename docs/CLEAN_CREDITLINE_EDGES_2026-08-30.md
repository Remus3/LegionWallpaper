# Credit line: the right edge, and what the mid-line holes actually are

2026-08-30. Follows `47903a2` (left edge) and `88e1ac7` (art in the mask). The
hand-off asked for two things: mirror `left_extent` to the RIGHT edge of the
credit-line mask, and close the mid-line holes. Both were measured. Neither is
what the hand-off assumed, and one of them is falsified.

Every number here is rebuilt from the recorded boxes in
`ops/runtime/clean/creditline/run_ringfix/*_plan.json` against the source frames
they name. The rebuild is exact: at `reach=0` it reproduces the recorded
`mask_px` on **39 of 39** slugs, which is the pre-`escaped_ink` lane those
outputs were made with. Measurements below use HEAD (`reach=24`) unless said
otherwise.

## 1. Scope: the right edge truncates on 4 of 39, not 2

All 39 right ends were rendered at 1:1 with the mask edge drawn and read by eye.
The mark runs past the mask on:

| slug | box x1 | mark ends | must reach (px past x1) |
|---|---|---|---|
| `viego-the-ruined-king-...-dgemoim` | 1500 | 1552 | 52 |
| `261f` | 1429 | 1546 | 117 |
| `aidraw-...-watercolornessie-dma7o8j` | 1464 | 1520 | 56 |
| `266f` | 1428 | ~1580 | 152 |

The other 35 end their `.COM` inside the mask. `syndra-...-dlsfckr`, named in the
hand-off as a right-edge case, is NOT one: its `.COM` is fully covered and its
mask extends past it. `266f` is the known detection failure (its read box starts
at x=200, spanning the poster's own gold tagline), so it is a right-edge case
only incidentally.

## 2. The right-edge walk is FALSIFIED. Do not retry it.

Five rule families, 60+ configurations, all over the same 39 slugs. `cov` is how
many of the 4 truncated slugs the mask would reach (extension + `PAD`); `ctrl` is
what the same rule does to the 35 that were already correct.

| rule | best cov | ctrl median | ctrl p90 | ctrl max | ctrl slugs moved |
|---|---|---|---|---|---|
| mirror of `left_extent`, `LEFT_*` constants | 1/4 | 7 | 34 | 58 | 19/35 |
| banded (count only the mark's own text rows) | 2/4 | 0 | 38 | 117 | 17/35 |
| walk-only ink at `beta` 1.2-1.8 | 3/4 | 11 | 68 | 107 | 19/35 |
| leading guard (blank rows above and below) | 3/4 | 4 | 57 | 116 | 18/35 |
| geodesic strip (`escaped_ink` on the line band) | 3/4 | 8 | 61 | 115 | 19/35 |
| edge-adjacency GATE (fire only where ink touches x1) | 4/4 | fires on 16 slugs, 12 of them controls | | | |

No cell reaches 4 of 4 without moving more than half the controls, and no cell
reaches even 3 of 4 for less than a p90 of 57px of mask growth into artwork, on a
lane whose other named open defect is that the fill destroys artwork. Reverting
that trade: **the best rule buys 3 truncated tails and pays with 19 controls.**

Two further facts close it:

- **The reader has nothing to recover.** `easyocr` was re-run on all four
  truncated frames with both enhancements, before `looks_like_credit` filters
  anything. It returns exactly ONE line on each, and **not a single read** lands
  right of `box_x0 - 40`. There is no discarded `COM` read to re-attach; the
  tail is not read at all.
- **`local_ink` cannot see the tails.** On `261f` the tail is plainly visible in
  `|hp|` and in `|hp|/local` (rendered), and dies on the AND of the two: the
  column ink counts past x1 fall to 0-2 across 60 columns where the in-box
  columns run 100-137. The tails are faint precisely BECAUSE that is what made
  OCR drop them, so the walk is blind exactly where it is needed.

**Why the two ends are not mirror images, and this is the load-bearing point.**
On the LEFT, the read box's neighbour is the `(c)` ring: one compact object,
measured 17-34px wide, sitting alone in the line's own leading. "Cross a gap,
take one run that ENDS before the cap" describes that object and nothing else,
which is why `LEFT_HOPS = 1` works. On the RIGHT, the neighbour is more of the
SAME TEXT at the same faintness, arriving as several glyphs with inter-letter
gaps. Reaching it needs repeated hops, and that freedom is exactly what lets the
walk step into artwork. No constant separates the two uses of the same freedom.

**Do NOT redo:** any of the five families above; a `.COM` suffix predicate on the
read text (the OCR is too garbled - `105-cleanup` reads `...EOM OM`, `245f`
`...AT.COP`, `281-cleanup` `...CTM`, `aatrox` `...cpM`, all with correct right
edges, while `122`/`123f` read a clean `COM`); or a glyph-pitch extrapolation
from the read text length (on `261f` the read normalises to 18 characters for 25
true glyphs, so the pitch is 23 percent high before it starts).

**What is left, if it is ever worth it:** the tails are visible in `|hp|`. A rule
that reads them needs a text-specific measure - stroke periodicity along the
baseline, or a glyph model - not another threshold on the same ink map. That is a
larger piece of work than this lever was scoped as, and it serves 4 slugs.

## 3. The mid-line holes are NOT a mask failure. Root cause corrected.

The hand-off's reading was that `glyph_mask` leaves holes and `syndra-...-dlsfckr`
"keeps `R`, `X`, partial `D`" because those glyphs are outside the mask. Measured,
that is false in both halves:

- **The mask covers them.** Inside the mark's own row band (rows 987-1007,
  measured from the in-box ink profile), the shipped mask's horizontal gaps on
  `syndra-...-dlsfckr` are median 2px, **max 3px** over 29 runs. There is nothing
  to close.
- **`escaped_ink` is not eating them either.** The LEDGER 139 promise re-verified
  on HEAD across all 39: escape inside the OCR-verified read box is **0 px on 37
  of 39**, and the two exceptions are the documented band-clipped pair
  (`281-cleanup` 107px, `akali-godly-deer` 615px). `syndra-...-dlsfckr` is 0.

**What actually happens:** the SCOPED REVERT hands them back. Step 0 is
`partial ... scoped to 4px around the damaged line`, and comparing the recorded
output to the source shows **1048 mask pixels ending byte-identical**. Rendered
against the frame, those pixels sit exactly on the `R` and the `X` - the two
letters the output still reads - because the corridor follows a bright diagonal
art edge that crosses the credit line right there.

This is not a bug in `scoped_revert`. It is the measured, operator-ratified cost
of the 2026-08-29 default: a corridor restores SOURCE pixels inside the credit
mask, and every such pixel is mark by construction. The queue-wide number was
known (17,508 px, 1.80 percent) and accepted as the best of four lanes. What was
never asked is WHERE those pixels land, and on `syndra-...-dlsfckr` they land on
glyphs.

### Measured over the recorded 39 outputs

Mask pixels handed back, total **18,835**. Worst: `105-cleanup` 1657,
`259f` 1493, `blood-moon` 1480, `akali-godly-deer` 1389, `miss-fortune` 1304,
`aatrox` 1129, `280f` 1097, `syndra-...-dlsfckr` 1048. Six slugs hand back fewer
than 50.

### A legibility proxy that does NOT work, recorded so it is not retried

Local stroke contrast at the handed-back pixels, source against output
(`|hp|` median, window 15), looked promising: it splits the 39 into a group
keeping 72-104 percent and a group keeping 3-60 percent. It does **not** measure
what it looks like it measures. `259f` keeps 84.6 percent and its output is
CLEAN at 1:1 - there the corridor restored a bright art streak, which is the
corridor doing its job. The measure says "the returned pixels still stand out",
which is equally true of returned art. Overlap with the glyph selection does not
separate them either (`syndra` 19.8 percent, `259f` 26.7, `akali` 48.7).

So the ROADMAP's standing point holds unchanged: **a ship gate here needs a
legibility measure, and nothing in the module has one yet.**

## 4. What shipped

Nothing that moves a pixel. The lane's output is byte-identical.

`handed_back_px` per step and `handed_back` per plan, per lane record, in the
run summary and in `REVIEW.md`, sorted on: mask pixels a step left BYTE-IDENTICAL
to the frame it started from. That is the mark returned to the frame, which is
what the zero-residue bar is about, and no consumer of the plan could see it. It
is deliberately NOT `reverted_px`:

- a COMMIT hands back whatever the filler returned unchanged, and `reverted_px`
  is 0 on every committed step by definition;
- a PARTIAL hands back the corridor and anything else the fill did not move -
  `syndra-...-dlsfckr` reported `partial ... reverted_px=967` and looked fine.

In `review_order` it sorts above the repaint width and below `held`, because it
is measured while `still_reads` is near-blind (it fired on 2 of 39 slugs where
the eye read a line on 28) and `held` counts whole reverts only, so a `partial`
that gave two letters back reads as a clean frame.

## 5. Open, and whose call it is

The corridor that saves an art line by handing a legible letter back is an
operator trade: art line against zero residue. The operator's own bar says the
mark must go, but refusing the corridor today falls through to a WHOLE revert,
which hands back 28.13 percent instead of 1.80. Making "refuse" mean COMMIT
instead is a one-line policy change and a full lane re-run to validate.

Note also that the 39 recorded outputs predate `88e1ac7`, so the queue has never
been run under the shipping default. `handed_back` will only appear in plans
written after this change.
