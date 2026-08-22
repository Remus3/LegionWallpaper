# Cleaning: the standard, and the four tracks to run in parallel next session

## The acceptance standard (operator, 2026-08-22)

**ZERO watermark. Ghost, banding and faint residue are NOT acceptable outputs.**

This is stricter than any measure used so far and it settles several arguments:
a detector score near zero does not pass, "much reduced" does not pass, and the
template+schedule result on `105-cleanup` - logo gone, credit line down to a
faint ghost - does NOT pass. There is no partial credit.

## Where the problem actually stands

Settled by measurement on 2026-08-22 (`docs/CLEAN_HANDEDIT_ANALYSIS_2026-08-22.md`):

- **FILL is solved.** Replaying the operator's own masks through simple-lama
  produced a frame they accepted (105), and held up on the harder slug (107).
- **The mask SCHEDULE is built** and cleaned 105 from a derived footprint:
  residue -> contiguous run -> pad to 5x for context -> tight crop -> commit.
- **DETECTION is the open problem.** Contrast-based measures fail in BOTH
  directions - absolute fires on genuine art detail (damaged 107), relative
  misses the mark entirely (a semi-transparent line is not busier than the art).
  Only the centre-overlay TEMPLATE works, because it keys on what the mark looks
  like rather than how loud it is, and it covers only 45 of the 80 slugs.

## The four tracks, to run in parallel and work out next session

Operator's direction: this is SPOT HEALING, not whole-image generation. The
earlier art-generation training informs technique but not approach.

### Track E - a HEALING BRUSH fill, and this is probably the primary track

The operator's own words for what they are describing: "like photoshops healing
brush". That is not what any lane here has been doing, and it retro-explains
every piece of guidance they gave.

Photoshop's healing brush is exemplar + GRADIENT-DOMAIN blending: it takes
TEXTURE from a source area and reconciles COLOUR and TONE with the destination's
surroundings by solving in the gradient domain (Poisson), rather than inventing
content from a learned prior the way LaMa does. Consequences that match the
evidence exactly:

- gradient-domain blending preserves the SOURCE's gradients, so lines stay crisp
  and continue correctly - the operator's "keeping art content lines crisp to
  its design", and the precise defect ("lines from outside the matte do not
  re-align") that got all 45 candidates rejected;
- the seam vanishes because the boundary condition is matched by construction,
  not because a model guessed well - which is why their result has no seams and
  every lattice variant of mine did;
- "beyond the text into similar-like areas ... to pull down into the area to be
  altered" IS source-patch selection;
- tone/opacity/hue conditioning (track D) is what the colour half of the heal
  does;
- it is deterministic and hallucination-free, so "phantom/incorrect context"
  cannot appear - which is the operator's stated failure mode.

Implementation is classical and needs no model: pick a source patch for each
residue blob (nearest region of matching structure, along the contour the mark
crosses), then solve a Poisson blend of that patch into the destination.
Pure-numpy is feasible (Jacobi/multigrid relaxation, or a DCT solve); the blobs
are small, which is what makes it cheap.

This should be tried BEFORE more LaMa variants. LaMa was validated as adequate
when handed the operator's masks, but "adequate" was measured against frames the
operator accepted at the old bar - and the bar is now ZERO residue.

### Track A - analyse the content BEHIND the mark
Estimate the underlying picture inside the mark region (the algebraic matting
inversion already recovers part of it) and analyse THAT, cropped, to drive where
strokes go and how big they are. The current schedule reads the marked frame, so
it is partly measuring the mark when deciding how to treat the mark.

### Track B - an overlap-muxed comparison layer
Build a reference layer from overlapping/neighbouring content and carry it
through the stepped processing as a comparison, so art LINES stay crisp and true
to their design. Concretely: a per-step accept/reject on whether a stroke broke
a line that the comparison layer says continues. This attacks the exact defect
the operator rejected 45 times - lines that fail to re-align across the boundary.

### Track C - spot healing, per blob, with rollback
Treat each residue blob as its own heal with its own context, and roll a step
back when the comparison layer says it made things worse. The current schedule
commits every step unconditionally.

### Track D - opacity / hue / tone conditioning inside the region
Adjust opacity, hue and tone within the watermark region between passes so the
iterative fills converge - weaken the mark's remaining amplitude and match the
region's tone to its surroundings before asking the filler for anything.

## Rules carried into that work

- The operator's eye is the gate; no scalar is a verdict (LEDGER 101-103, and
  re-proven twice today at both ends of the scale).
- Nothing is approved and nothing leaves `3.Cleaning Scratch` on a metric.
- Ground truth for validation is the two captures - 128 labelled steps, plus two
  accepted final frames - in `ops/runtime/clean/handedits/` (gitignored).
