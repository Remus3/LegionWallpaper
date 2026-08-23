# Track D: the veil model does not describe these marks, and conditioning hurts

Track D was to weaken the mark's remaining amplitude and match the region's tone
to its surroundings before asking the filler for anything - opacity, hue and
tone conditioning inside the watermark region. It rests on a model,

    observed = alpha * colour + (1 - alpha) * content

and the four captures can test that model directly, because the operator's
accepted final IS the content behind the mark. So it was tested first, then
built anyway so the negative would be proved rather than asserted.

## The model, measured against ground truth

With the content known, the relation above is a straight line per channel and
its R-squared says whether the mark is a veil at all.

| capture | mark | R-squared (R/G/B) | fitted alpha | veil? |
|---|---|---|---|---|
| 105-cleanup | credit line | 0.49 / 0.59 / 0.52 | 0.26 / 0.27 / 0.31 | NO |
| 107-cleanup | area | 0.61 / 0.32 / 0.81 | 0.26 / 0.58 / 0.03 | NO |
| 209-cleanup | painted signature | **0.00 / 0.00 / 0.00** | **2.23 / 1.91 / 1.71** | NO |
| dgk8f92 | block logo | 0.04 / 0.04 / 0.04 | 0.45 / 0.43 / 0.47 | NO |

None of the four fit. Two details matter more than the headline:

- **209 is not a poor fit, it is no fit at all.** R-squared 0.00 and a fitted
  alpha above 1, which is not a physical opacity. A painted signature is opaque:
  its pixels carry no information about what is under them. There is nothing to
  weaken, and no amount of conditioning can invent it.
- **107 disagrees with itself across channels** - alpha 0.26, 0.58 and 0.03 for
  one supposedly single opacity. A real veil has one alpha.

## Conditioning, applied

The estimator abstains where the model obviously fails and fires where it looks
plausible, which is the correct behaviour and still not enough:

| capture | untouched | conditioned | fill | condition then fill |
|---|---|---|---|---|
| 105 | 15.45 | **22.46** | **8.08** | **20.01** |
| 107 | 23.50 | **39.65** | **12.22** | 12.22 |
| 209 | 27.26 | 27.26 (abstained) | 1.31 | 1.31 |
| dgk | 49.89 | 49.89 (abstained) | 2.23 | 2.23 |

In-mask distance to the operator's accepted final, lower better.

Where conditioning fires it makes the frame **worse** - 15.45 to 22.46 and 23.50
to 39.65 - and where a fill follows it either damages the result (105: 8.08 to
20.01) or is simply overwritten by the fill and changes nothing (107). Where the
estimator is honest it does nothing at all. There is no cell in that table where
conditioning helps.

## The design lesson, which outlives the track

On 105 the conditioned run held 1 of 2 blobs where the plain fill held none.
That is the rollback doing its job - the conditioned region broke a line, so the
fill on top of it was reverted - but **the conditioned damage stayed, because
the pre-pass wrote into the region outside the rollback's envelope.**

So: any pre-pass that writes into the mark region must sit INSIDE the rollback,
or it can damage a frame in a way the rollback cannot undo. Track C's snapshot
covers the fill only.

## What was built and kept

`tools/lw_clean_condition.py` - pure numpy:

- `estimate_veil` - alpha and colour from the readable ring alone. Opacity is
  estimated as ONE number, because it is one: the veil's colour differs per
  channel, how much of it there is does not, and estimating three alphas invites
  three answers to a question with one.
- a **null measured from the ring's own two annuli**. Without it the estimator
  fires on ordinary art, where a region and its ring differ in contrast for
  innocent reasons - the same failure this repo already logged for absolute
  contrast residue. The contrast loss has to beat that null by 2x, and the null
  is measured per image rather than assumed, so it costs no constant.
- `apply_veil_inverse` - writes only inside the mark, gain clamped.
- `fit_veil` - the ground-truth regression above. It needs the answer, so it
  belongs to the census and never to a lane.

16 tests, written first, holding the estimator to the model on synthetic art
where the model is true by construction. That separation is the point: it proves
the failure on the captures is the corpus, not a broken estimator.

## What is NOT wired

Conditioning is not in any cleaning path and should not be. It is measured
harmful on the two captures where it applies and inert on the other two.

Where a genuine veil does exist - the DeviantArt centre overlay, a real
semi-transparent layer covering 45 of the 80 queued slugs - the repo already
inverts it with a TEMPLATE and matte in `lw_clean_iopaint.overlay_prepass`.
This census supports keeping that: a template knows what the mark looks like,
while a ring-based estimate has to infer it from statistics, and the statistics
of these marks do not support the inference. LEDGER 101-103 also records that
even the template pre-pass leaves the credit line legible at 1:1, so conditioning
was never going to be a removal in the first place.

## Do not redo

- Do not condition, tone-match or un-blend a mark region from ring statistics.
  Measured worse on both captures where it applies.
- Do not read a high fitted alpha as evidence of a veil without its R-squared:
  209 returns alpha 2.23 at R-squared 0.00.
- Do not add a pre-pass that writes into the region outside the rollback
  envelope.
