# ADR-011: lw-gen base stays Animagine XL 4.0; corpus similarity never picks a base alone

**Date:** 2026-08-16
**Status:** Accepted (supersedes ADR-010)

## Context

ADR-010, earlier the same day, flipped the base to RealVisXL V5.0 on a
matched-seed three-base A/B. The measure it rested on was corpus similarity:
mean CLIP ViT-L-14-quickgelu cosine against the 21 real Ahri splashes, read
against those splashes' own self-similarity ceiling of 0.8373. On that measure
animagine sat 0.153 BELOW the ceiling and RealVisXL 0.024 above, with RealVisXL
also taking subject_cos, margin and pass rate.

The operator then inspected every candidate frame from all three arms. The
by-eye verdict inverts the ranking completely:

- **Animagine holds League and corpus conventions on ALL candidate frames.**
- **RealVisXL violates hand conventions, weapon/tool canon, and facial
  design/likeness.** These are the same complaints that drove the 2026-07-11
  move away from it, and the Ahri A/B did not retire them - it failed to test
  them.
- **DreamShaper XL violates the corpus look and feel outright.**

So the measure ranked FIRST the two bases that break the product, and LAST the
one that holds it. That is not a close call to be split - it means the measure
does not measure what a base must be selected on.

**Why it goes wrong is now clear and worth writing down.** CLIP-embedding
cosine to the corpus is a GLOBAL image-statistics similarity. It carries
palette, lighting, rendering softness and photographic texture, and it is blind
to exactly the properties a splash-art base has to get right: hand anatomy and
finger count, weapon and tool canon, and facial likeness to a specific champion.
A photoreal base scores well by looking photographically plausible while
rendering six-fingered hands and a wrong-shaped weapon; an anime base scores
badly for its rendering register while keeping every convention intact.

The evidence table stands as measured - `docs/GEN_BASE_DECISION_2026-08-16.md`
is corrected in place rather than deleted, because the numbers are real and the
conclusion drawn from them was not.

## Decision

The lw-gen base **stays Animagine XL 4.0** with the `splash-booru` register.
**RealVisXL V5.0 and DreamShaper XL are DROPPED as base candidates** - not
parked, not per-brief overrides. The 0.8373 corpus-similarity yardstick is
retained as a MEASURE and is **never a base-selection criterion on its own**;
any future base change requires operator inspection of candidate frames for
hands, weapon canon and likeness.

## Consequences

**Good:** The shipped base is the one that holds the corpus conventions, and
the reason a similarity score cannot arbitrate that is now recorded rather than
rediscovered. `tools/lw_gen_medium.py` remains useful for what it does measure
(rendering-register distance from the corpus), with its blind spots stated.

**Trade-off:** The lane keeps a base that sits measurably outside the corpus
distribution on rendering register, and the subject gate still cannot see that.
The gap is real; it is simply not decisive against the conventions.

**Watch for:**
- **Facial realism is the open tuning direction** (operator, 2026-08-16): push
  animagine's faces somewhat more real WITHOUT reaching the uncanny register
  the two dropped bases produced. That is a prompt/adapter/sampler question on
  THIS base, verified by generation and operator eye - not a base swap.
- Do not re-run a base A/B scored on corpus similarity and re-derive ADR-010.
  Any base experiment must score hands, weapon canon and likeness, and those
  have no validated automatic measure today.
- The dropped arms' frames were deleted at operator instruction; the animagine
  arm is kept at `images/_gen_scratch/basedecide/animagine/`.
