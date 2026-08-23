# Credit-line lane, run end to end on the queue - 2026-08-22

The chain from the mask-generation session (`docs/CLEAN_MASKGEN_2026-08-22.md`)
had been measured piece by piece and looked at on two frames. This is the first
time it has been pointed at the whole queue and the first time the output has
been put in front of an eye. Nothing here approves anything: acceptance is the
operator on a 1:1 crop and the bar is ZERO residue, so ghost, banding and faint
all fail.

## What ran

`tools/lw_clean_creditline_run.py`, new. Per slug in `3.Cleaning Scratch`:

    read the line (easyocr, band + two enhancements, self-verifying on DEVIANTART)
      -> glyph mask inside the verified box (p88, grow 4)
      -> per-blob heal with rollback (LaMa, tracks A/B/C)
      -> re-read the OUTPUT
      -> 1:1 sheet: untouched above, cleaned below, cropped to the read box + 80px

Artifacts in `ops/runtime/clean/creditline/run/`: `<slug>_creditline.png` (the
cleaned frame), `<slug>_sheet.png` (the review crop), `<slug>_plan.json` (every
blob, its verdict and its reason), `run_summary.json`, and `REVIEW.md`, which
lists the sheets worst-first.

`still_reads` is diagnostic and NOT a gate. A read after the fill proves failure;
silence proves nothing, because the reader needs contrast and a faint ghost that
fails the operator's bar sits well under it.

## Result

39 of the 80 queued slugs carry a readable credit line. All 39 ran.

- 16 slugs held at least one blob, so they cannot leave the queue on this pass.
- 13 slugs still read a credit line in the OUTPUT: a proven failure, before the
  eye has looked at anything.

The lane REDUCES. It does not finish. That is the same conclusion the single-slug
measurement gave (105 reaches 11.56 against 15.45 untouched and the operator's
own 8.08) and it now holds across the queue.

## Three findings

### 1. On 266f the lane destroyed artwork

`266f` carries the poster's own gold typography, `PRECISION IS PERFECTION`, on
the same row as the `VEXXSOUL.DEVIANTART` credit. The reader joins a row before
verifying - it has to, because 107's line only spells the host once its two
halves are joined - and the joined box handed the filler 1228px of frame. The
tagline was erased and the rollback stayed silent, because flat text over flat
ground breaks no chord for the comparison layer to catch.

Evidence: `ops/runtime/clean/creditline/266f_sheet_BEFORE_GAPFIX.png`.

Two narrower masking rules were tried and BOTH MEASURED WORSE:

- Splitting the parts wherever a horizontal gap opened wider than the row is
  tall, keeping the run that reads closest to DEVIANTART. It does not touch
  266f - easyocr returns `P E R F E C T I g WExXsou_DEVIANT}` as ONE read
  spanning the tagline and the credit, so no partition of the parts separates
  them - and it broke three slugs that had been working, because the credit line
  itself arrives in gapped pieces: 261f `SLIMSNAD=` 87px left of `APERDEVIAN`,
  286f `PEBANOL` 67px left of `MIANTART COM`, dark-cosmic-ahri `EFIANOIDEV` 76px
  left of `MART ART OM OM`. Masks halved (261f 14209 -> 6435, 286f 25236 ->
  13126, dark-cosmic 18467 -> 11291) and the mark stayed on the frame.
- Unioning the part boxes instead of taking the line's bounding box. Milder, same
  mistake: it withholds only the gaps between reads, which on 105 is 79 pixels of
  22075, and that was enough to flip a blob from commit to revert and leave a
  readable line on a slug that had been clean of reads.

Both are reverted. The line's whole box is the mark, and `_credit_span` carries
the record so neither gets retried. **266f wants a discriminator INSIDE the box** -
the credit overlay is achromatic where the tagline is saturated gold - not a
better way of cutting up reads. Untested; it is a direction, not a result.

### 2. The 259f class: the mask is too thin for a bright ground

On `259f` the line is still plainly legible at 1:1 after 9 committed blobs. The
glyph threshold takes the top 12 percent of |high-pass| inside the box, which is
tuned on 105 - one slug picking one of nine cells - and on a light overlay over
bright, busy art it lands on a fraction of the strokes. This is the sweep the
mask-generation session said to widen once more slugs had been reviewed. It now
has 39 slugs and 13 failures to widen it against.

### 3. The negative census was reading the wrong frame

The open question was whether `230-cleanup`, sitting in `4.Cleaning Done` marked
APPROVED CLEAN, really carries `SMALLTANERNXDEVIANTART`. It does not. The census
asked `initial_of` for its negatives, which returns `<slug>_cleaninitial.png` -
the frame handed INTO cleaning, mark and all - so the one slug that fired was
reading a mark that was still there, and the 118 quiet frames were not evidence
of precision either. Re-read against `230-cleanup_cleandone.png`: zero hits.

Fixed: `approved_of()` reads `_cleandone` only, and skips-and-counts a slug that
has none rather than silently downgrading to the input. The precision claim from
the first census should be treated as unmeasured until the negatives are re-run.

## Also worth knowing

The rollback is knife-edge. A 0.36 percent change in mask area (105, 79px) moved
a blob from commit to revert and changed whether the mark survived. Any future
tuning of the glyph constants will move rollback verdicts as a side effect, so
the two have to be swept together rather than one at a time.

## Round two, on operator instruction (2026-08-23)

The operator looked at the round-one sheets and asked for another round. Round
two works round one's OUTPUT and re-opens the box round one recorded, so a line
that has gone quiet is still attacked - the reader only finds what still READS,
and a ghost sits under its floor, so a re-detecting second round would walk past
exactly the frames a first round half-cleaned.

`--input-dir` + `--plans-from`, output in `ops/runtime/clean/creditline/run2/`.
Sheets carry three rows: untouched, previous round, cleaned.

By the diagnostic it improves. 13 slugs still reading becomes 10; 3 go quiet
(276f, evelynn-by-pebano1, queen-of-the-saltwind); none that were quiet start
reading again; held blobs 16 -> 14.

**At 1:1 it trades text for smear, and it degrades frames that were already
done.** Four looked at:

- `evelynn-by-pebano1-dmc9764-pre` - one of the three that went quiet. The text
  is gone and a visible wash band stands where it was; the magenta filigree that
  crossed the line is destroyed. The read went away because the art did.
- `105-cleanup` - had nothing left to read after round one. Round two ran anyway,
  on the re-opened box, and the frame comes back softer: washed edges on the
  green shapes and the tan strokes below.
- `266f` - the leftover glyph stubs are gone, and the ornamental divider under
  the tagline and the diagonal gold lines to the right have lost more of
  themselves.
- `259f` - unchanged. Still fully legible. Another pass of the same mask picks up
  nothing, which is what a mask that is too thin does twice.

So a blanket second round is not the answer, and the two failures want different
things. The 259f class wants a THICKER mask, not another pass - `--glyph-pct` is
now a flag so that can be swept without a code change. The smear class wants the
fill to stop being re-applied over its own output at all. Neither reaches the
zero bar.

## Where to look

`ops/runtime/clean/creditline/run/REVIEW.md` - sheets, worst first.
