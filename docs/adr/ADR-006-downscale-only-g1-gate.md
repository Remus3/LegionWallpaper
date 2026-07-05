# ADR-006: Downscale-only sources drop the G1 lap_ratio floor

**Date:** 2026-07-05
**Status:** Accepted

## Context

First-pass routes a source that already covers 2560x1440 on both axes to a
DOWNSCALE-ONLY path (`lw_upscale._covers_target` -> one Lanczos to target, no AI
4x; ADR-002 never-double-resample, shipped LEDGER item 7). But the G1 gate
(`lw_g1_gate`) was calibrated for the UPSCALE path. Its `lap_ratio` metric is a
softness FLOOR - `laplacian_var(output) / laplacian_var(source)` at common scale,
failing below 1.0 - built to catch an upscale that softened the image. For a
downscale-only output there was no upscale to soften: the common-scale rule
downscales the 1440p output back UP to the native source resolution to compare, so
`lap_ratio` reads as arbitrary pass/fail driven by source content, not quality.

Empirical probe (2026-07-05, 3 of the 61 deferred downscale-only sources, all
~4096x2304 natives):

| source | lap_ratio | msssim | lpips | halo | raw verdict |
|---|---|---|---|---|---|
| 1332614 | 0.75 | 0.998 | 0.027 | 0.011 | FAIL (lap) |
| 1337738 | 0.78 | 0.996 | 0.052 | 0.056 | FAIL (lap + halo flag) |
| 1341679 | 1.20 | 0.998 | 0.015 | 0.036 | PASS |

`lap_ratio` swings 0.75 -> 1.20 across near-identical clean downscales - the third
PASSES as spuriously as the first two FAIL. Meanwhile `msssim`/`lpips` are healthy
and meaningful (0.996-0.998 / 0.014-0.052 = the Lanczos downscale preserved
structure), and `halo`/`band` behave normally. Only the `lap_ratio` FLOOR is
invalid for this path; the other metrics are not.

Without a policy, all 61 downscale-only sources (native 8K/4K + over-2560
DeviantArt fullviews + large crop_ok sources) are gated by an invalid floor and
mostly false-FAIL, so their clean 2560x1440 outputs never reach the operator
approve queue.

Alternatives considered: (a) drop only the `lap_ratio` floor, keep msssim/lpips +
halo/band; (b) drop `lap_ratio` AND the FR msssim/lpips comparison, gate only on
halo/band; (c) auto-submit all downscale-only with no G1.

## Decision

For a downscale-only upscale (audit `backend == "downscale-only"`), the G1 verdict
DROPS the `lap_ratio` floor and KEEPS msssim, lpips, halo_pct, band_delta. The
`lap_ratio` value is still computed and recorded in the manifest for provenance,
just not gated on. PASS/FLAG auto-submits to `_firstneedauth` as usual; a genuine
FAIL (corrupt downscale -> msssim/lpips out of band) still holds. Every other
backend gates on the full metric set unchanged. Operator directive, 2026-07-05
(option (a) - keep the meaningful checks, drop only the invalid one).

## Consequences

**Good:** The 61 deferred downscale-only sources can first-pass and reach the
approve queue. msssim/lpips still catch a corrupt/mis-scaled downscale, and
halo/band still flag added artifacts, so real defects are not waved through - only
the meaningless sharpness floor is removed for the one path where it cannot apply.

**Trade-off:** A second, backend-conditional verdict path in `lw_first_pass`. Kept
minimal: a pure `gate_metrics(metrics, backend)` filter feeds `verdict()`; the
threshold table `DEFAULT_G1_THRESHOLDS` is untouched (this is a per-path metric
selection, not a recalibration).

**Watch for:** If a future backend produces a genuine no-op or near-1x output that
should still be sharpness-checked, revisit the `backend == "downscale-only"`
predicate. The upscale (spandrel/ncnn) path is unaffected - `lap_ratio` remains a
hard floor there (the real double-resample softness guard, ADR-002).
