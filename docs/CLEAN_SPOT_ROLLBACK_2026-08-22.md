# Track C: one spot at a time, and undo what breaks a line

The schedule this replaces commits every step unconditionally - it fills, and
whatever comes out is what you get. The four hand-clean captures say the
operator does not work that way: they treat one spot at a time, look at it, and
undo what made things worse. `tools/lw_clean_spot.py` does that, and it is where
tracks A and B stop being interesting and start being load-bearing.

## The three decisions, each made by a piece measured on its own first

**WHERE** - the blobs of the detector's own footprint. No residue detector is
used to start: contrast residue is on the standing do-not-redo list as a
starting detector, and the footprint is what the detector already decided.

**HOW BIG** - the stroke size the art BEHIND the mark asks for (track A) governs
how a blob is CUT UP, not how far it is grown. That distinction cost two
measured rounds to learn and both are recorded below.

**WORTH IT** - the comparison layer (track B), scoped to the chords this spot's
context actually touches, judged BEFORE against AFTER. A step that breaks a line
is undone.

The rollback rule is asymmetric on purpose: a mark that survives is recoverable,
because the slug simply stays in the hand queue. Art destroyed under it is not.
Where the layer has nothing to say the fill stands - abstaining is not failing.

## Two mistakes of mine, both caught by running it on the captures

**One.** The first version grew each blob until its area matched
`target_tile_area` of the art behind it. That is a straight misreading: the
target is how big a STROKE should be, not how much margin a spot needs. On
dgk8f92 - soft snow, gradient 0.778, so a 40000px target against ~2300px blobs -
it repainted 24x the mark and scored 22.59 against the operator's final where a
one-shot fill scores 2.38. The same misreading in a different costume as the
`CONTEXT_RATIO = 5.0` the four captures already falsified.

**Two.** With the target moved to the split, a 1.6x margin remained, taken from
209-cleanup where the operator's brush bbox was 117x52 against an 86x43 detector
box. That capture answers a DIFFERENT question - brush against DETECTOR BOX -
and the mask handed to this runner is already a brush mask, so the margin
repaints art nobody asked about. Swept against the operator's finals (in-mask
distance, LaMa, lower better):

| slug | untouched | one-shot | m=1.0 | m=1.6 | m=3.0 |
|---|---|---|---|---|---|
| 105 | 15.45 | 7.87 | **8.08** | 15.20 | 15.38 |
| 107 | 23.50 | 12.45 | **12.22** | 36.04 | 23.50 |
| 209 | 27.26 | 1.28 | **1.31** | 3.58 | 5.50 |
| dgk | 49.89 | 2.38 | **2.23** | 5.23 | 21.41 |

`m=1.0` matches or beats the one-shot fill on all four and every larger margin is
monotonically worse. The default is now no margin at all; the knob stays for the
case where this runner is handed a DERIVED mask, where a margin is a real
question again and this table does not answer it.

**Splitting is off by default for the same reason.** Cutting a blob into
disjoint stroke-sized pieces starves the filler of context: on 107 it produced
34 spots, all committed, and moved the frame from 23.50 to 23.08 - it barely
cleaned at all. That is consistent with what the captures actually show, which
is not a partition: the operator's strokes overlap 30x, the median stroke
re-covers 97% of ground already brushed, and each one lands on a neighbourhood
that has ALREADY been partly cleaned. A disjoint partition is a different
process wearing the same clothes.

## What it does now

Same four captures, in-mask distance to the operator's accepted final:

| slug | untouched | one-shot lama | **spot-lama** | spot-heal | rollback |
|---|---|---|---|---|---|
| 105 | 15.45 | 7.87 | **8.08** clean | 15.87 | **held 1 of 2** |
| 107 | 23.50 | 12.45 | **12.22** clean | 23.50 | **held 1 of 1** |
| 209 | 27.26 | 1.28 | **1.31** clean | 1.95 | abstains, 0 chords |
| dgk | 49.89 | 2.38 | **2.23** clean | 5.05 | abstains, 0 chords |

Per-blob healing costs nothing against the one-shot fill and buys rollback. And
the rollback fires on exactly the engine that was independently shown to damage
art at 1:1 (track E's healing brush), on exactly the two slugs where lines cross
the mark, while never firing on the fills the operator accepted.

## The rollback rule, and the number in it

Two triggers, either fires:

1. a chord that was intact before the step is broken after it;
2. the median chord ratio retains less than `KEEP_FRACTION` of its pre-step value.

The second exists because the first is not enough on its own, for a physical
reason: a semi-transparent mark ATTENUATES the lines under it, so the pre-step
frame is often already below the intact bar and no intact-to-broken transition
can occur. Retention measured on the two captures that carry chords:

| fill | retained | label |
|---|---|---|
| operator | 0.947 / 0.937 | accepted |
| lama | 0.922 / 0.921 | accepted |
| heal | 0.543 / 0.496 | rejected at 1:1 |
| membrane | 0.301 / 0.133 | a blur by construction |

`KEEP_FRACTION = 0.75` sits mid-gap, about 1.2x below the worst accepted case
and 1.4x above the best rejected one. **It is calibrated on eight observations
and that is stated, not hidden.** It is tolerable only because this is a
ROLLBACK trigger and not an approval gate: firing it leaves the mark in place
and the slug in the queue, which is recoverable, while the damage it prevents is
not.

## Honest limits

- **Rollback protects LINES, not everything.** On 209 and dgk there are no
  chords, so it abstains and commits whatever the engine produced - including
  the healing brush. Damage to smooth art is invisible to it.
- **With one chord it protects very little.** At margin 1.6 on 107 the result
  was 36.04 - worse than leaving the watermark in place - and rollback did not
  catch it, because the single chord held.
- **Nothing here approves anything.** A run that holds a blob reports `held`,
  which means the slug cannot leave the queue on this pass. The operator's eye
  remains the acceptance bar (LEDGER 101-103).

16 tests in `tests/test_lw_clean_spot.py`, written first (RED confirmed). Full
suite 2227 passed / 18 skipped. Artifacts in `ops/runtime/clean/spot/`
(gitignored).
