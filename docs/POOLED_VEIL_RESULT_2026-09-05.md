# Pooled veil estimate over 62 DA-overlay frames - result

**Verdict: it did not work, and the mechanism is now known.** The hand-clean is
still better than the machine. What follows is the evidence, because the negative
result kills several hypotheses that would otherwise be retried.

Fit: 62 frames from `3.Cleaning Scratch`, **123f held out** as the acceptance
target. Artifacts: `data/reference/pooled_veil_62.npz`,
`data/reference/pooled_logo_matte.npz`.

## What DID work

**Registration is not the problem, and that kills a whole class of hypotheses.**
Every one of 26 sampled frames registers at **scale 1.00, shift within +-3 px**,
with template correlation 0.35-0.58. The overlay sits in the same place at the
same size in every frame. An earlier worry that the mark rides at different
scales per frame (a `scale=1.12` reading on slug 122) does NOT generalise.

**Pooling cancels the art.** The 62-frame median high-pass leaves the DA logo
outline crisp against near-black. Support 29,492 px. The pooled matte reaches
alpha 0.4317 with 9,638 px above 0.08. So the mark IS recoverable as a shared
object - the question is which PART of it.

## What did NOT work, and why

**The pooled matte recovers the mark's EDGES, not its flat FILL.** Applied to
held-out 123f it darkened the logo's outline and left the interior visible - the
opposite of a removal. The cause is structural, not a tuning miss:
`estimate_template` and `estimate_matte` are built on `highpass`, which by
construction sees edges. The logo's flat interior carries almost no
high-frequency signal, so a high-pass pooled estimator is blind to precisely the
part that is visible to the eye.

`estimate_veil` is the one component meant to catch a flat region, and it
returned **693 px of support (0.047% of the band) at alpha 0.021** - barely above
its own "do not manufacture a veil" guard. Pooling 62 frames did not lift that
amplitude clear of the noise floor.

**The credit line cannot be pooled at all.** It is artist-specific. The pooled
matte carried `PEBANO1`'s glyph geometry, because that artist dominates the set,
and subtracting it from a `SMALLTAVERNX` frame produced a dark smeared double
plus new artifacts near the jaw. Pooling only helps an object common to every
frame; the logo qualifies, the credit line never will.

## The number that lied

`overlay_score` fell **0.5492 -> 0.2085, a 62 percent reduction**, on an output
that is visibly WORSE than the input. This is the 2026-08-12 ruling reproduced
live: `overlay_score` is a DETECTION flag and NEVER a removal-quality gate. Any
future attempt that reports success on this metric alone should be disbelieved
until someone looks at the pixels.

## What would actually be needed

The flat fill needs a LOW-frequency estimator, not a high-pass one - the veil is
a ~2 percent luminance step over a large solid region, which is a DC-ish signal
that `highpass` removes on purpose. Pooling helps the SNR but cannot recover a
band the transform discarded before pooling started.

Two consequences for planning:

1. Do NOT retry the existing pooled path with more frames or looser thresholds.
   The blindness is in the transform, not the sample size.
2. The hand-clean lane remains the shipping route for these 63 frames. Its output
   is the acceptance target, not fitting data - a matte fitted from a hand-clean
   encodes the operator's heal/clone reconstruction rather than the watermark
   (measured separately: the hand-finished line fits the alpha model no better
   than the known-invented LaMa layer, 7.00 vs 6.12 median levels of error).

## Follow-up: analysis-by-synthesis (operator's proposal), 2026-09-05

The operator proposed inverting the approach: instead of scraping a residue out
of watermarked frames, SYNTHESISE the mark onto clean art and fit until it
matches. That is the better formulation - DA's overlay is machine-generated, so
the model has ~a dozen parameters, and a dozen parameters cannot absorb a hand
reconstruction the way a free per-pixel alpha does.

**What it needs is a matched pair, and none exists.** Checked and ruled out:

* **No clean/watermarked duplicate in the corpus.** All 63 watermarked frames
  matched against all 517 `4.Cleaning Done` images on the repo's own consensus
  pHash+dHash: closest consensus distance **18**, against an accept threshold of
  8 and a recorded noise floor of 12-14 between DIFFERENT champions. 45 no_match,
  18 review, 0 match.
* **DA watermarks every render size.** `content` 1600x897, `preview` 1194x669 and
  even the 300px thumb all carry it, and it scales with the render, so no size
  comes back clean.
* **Two sizes do not separate it either.** Downscaling `content` onto `preview`
  leaves the logo outline visible in the residual - so the mark's geometry does
  differ between renders - but art edges survive just as strongly because each
  render is independently JPEG'd. Resampling noise dominates.

**What the attempt did produce.** Shape and amplitude can be separated: the
pooled template gives a clean logo SHAPE (one component, 605x365, aspect 1.66,
filled to 81,881 px), and the amplitude can be measured per frame as the
luminance step across that known boundary, `alpha = step / (255 - L_outside)`.
Pooled over 62 frames (123f held out): **alpha = 0.0578 +- 0.0046 (SE)**, a
12.6-sigma result that independently lands on the ~0.06 figure LEDGER already
recorded. Applying it to held-out 123f damaged nothing - no dark edges, no
smearing, unlike every earlier attempt.

**But it cannot be validated per frame, which is the blocker.** The same ring
measurement on a SINGLE frame is noise-dominated: across 62 frames the per-frame
alpha has std 0.036 against mean 0.050, and **6 frames (10 percent) come out
NEGATIVE**, which is physically impossible for a white overlay. 123f's own
pre-correction boundary step is -1.33 levels, so applying the pooled 0.0578 to
it over-corrected to -3.67. Shape is solid; amplitude is a population average we
cannot check against the frame in front of us.

**Standing conclusion.** The hand lane remains the shipping route. Every
automated estimate here is unverifiable per-frame for want of one clean/
watermarked pair, and the search above establishes that no such pair is
obtainable from the corpus or from DeviantArt.
