# ADR-007: The FR common-scale pixel budget is 3840x2160

**Date:** 2026-08-02
**Status:** Accepted

## Context

G1's full-reference metrics compare the pipeline OUTPUT against the SOURCE. They
require pixel-aligned, same-size inputs, and `docs/research/AUDIT_GATES.md` 1.2
fixes the direction of that alignment: **downscale the output to meet the source,
never upscale the source to meet the output.** Bicubic-upscaling the reference
manufactures a blurry reference and biases every metric toward approving soft
output - the exact softness bug ADR-002 structurally bans.

So the comparison happens at SOURCE scale, and LW sources are much larger than
the deliverable. The approved output is exactly 2560x1440; the sources behind it
run to 6500x3660, with 26 corpus images sitting natively at 3840x2160. **The
comparison scale is not the output scale, and conflating the two is the first
thing anyone reading this gets wrong.**

That has a cost the corpus actually paid. Measured 2026-07-18: DISTS allocates
~2 GiB of VGG activations at 7680x4320, on top of what the earlier metrics in the
same run still hold. That OOMs the 12GB card AND OOMs system RAM on the CPU
fallback, so DISTS was simply uncomputable for 8K-class sources. **63 of 230
first-pass images had lost DISTS entirely this way** - every single failure was
DISTS, at common scales 5376x3024 and up. The largest common scale that ever
succeeded corpus-wide was 4096x2306 (9.4 MPix).

A budget was shipped 2026-07-30 (LEDGER 32, `b14b688`) as
`lw_g1_gate.MAX_COMMON_PIXELS = 3840 * 2160`, with `common_scale_for()`
Lanczos-resampling BOTH sides down to fit when a pair exceeds it. It was shipped
because the metric was otherwise unavailable, but the VALUE was left unratified:
it changes the G1 measurement basis corpus-wide, which is ADR-006-scale, and a
measurement-basis change is an operator call rather than an implementation
detail.

Alternatives considered: (a) ratify 3840x2160; (b) pick the proven ceiling
4096x2306 instead, buying ~13 percent more comparison detail; (c) no cap, and
accept that 8K-class sources have no DISTS; (d) native-8K DISTS via tiling or a
smaller backbone.

## Decision

**`MAX_COMMON_PIXELS` is ratified at 3840x2160 (8.29 MPix), option (a).**
Operator direction, 2026-08-02.

Rationale for the specific number, in the order it matters:

1. It sits **below a measured ceiling**, not at it. 4096x2306 is the largest
   scale that ever completed corpus-wide; a budget set AT the ceiling has no
   headroom for a future metric, a longer chain, or a busier GPU.
2. It **lands on a scale the corpus already uses** - 26 images are natively
   3840x2160, so for those the cap is a no-op and the comparison is unchanged.
3. It is above every common resolution below it, so the cap only ever engages on
   genuinely oversized sources.

The mechanism is unchanged and stays as shipped: over budget, BOTH sides are
Lanczos-resampled down preserving aspect; under budget the source scale is used
verbatim, so the ordinary case is exactly what AUDIT_GATES 1.2 describes. The cap
only ever DOWNSCALES the reference, so caveat 2 above still holds - the reference
is never blurred upward.

Option (d) is REJECTED and should not be retried: native-8K DISTS was measured
impossible on this box on both devices.

## Consequences

**Good:** DISTS is computable for every source in the corpus, which recovers a
metric that was silently absent for 63 of 230 images. "Silently" is the load
bearing word - a missing metric read as a clean run.

**Trade-off:** A capped comparison **hides high-frequency difference**. A capped
value is therefore NOT interchangeable with a native-scale one, and the two must
never be averaged, thresholded together, or compared across the boundary. This is
already enforced in data rather than by convention: `fr_metrics` reports `capped`
and `native_scale` alongside `common_scale`, so any consumer can tell which
regime a number came from.

**Watch for:** the threshold table `DEFAULT_G1_THRESHOLDS` was calibrated on a mix
of capped and uncapped measurements. If a future recalibration is done, it must
segment on the `capped` flag rather than pooling - pooling would fit one threshold
to two measurement bases. Note this is the same class of error as
`usm-halo-calibration`, where a one-axis threshold pick already got a gate
rejected.

**Pinned:** `tests/test_g1_common_scale_budget.py` asserts the constant equals
this ADR's value. The constant is now a ratified decision, so a silent edit to it
is a CI failure rather than a diff nobody reads.
