# ADR-004: Promote IllustrationJaNai V3 detail DAT2 to primary first-pass upscaler

**Date:** 2026-07-05
**Status:** Accepted

## Context

The first-pass upscaler was IllustrationJaNai V1 DAT2 (`4x_IllustrationJaNai_V1_DAT2_190k.pth`,
spandrel/torch), frozen as PRIMARY in QA Session 2 (LEDGER item 3) with the G1
gate calibrated on it. The newer V3 "detail" variant was a documented trial
target; its download was unresolved in prior sessions. This session resolved it
(the OpenModelDB link is dead - V3 ships only via the MangaJaNai v3.0.0 GitHub
release, a direct HTTPS asset, no Google-Drive token dance) and fetched
`4x_IllustrationJaNai_V3detail_DAT2_28k_bf16.safetensors` (139,793,020 bytes,
sha256 `eb9faf6a37de81406765e0c99e76ad7dafe67e4877f32e186085ac277a0e6181`, no
upstream checksum published so we computed our own). spandrel loads it (arch=DAT,
scale=4). It was A/B'd against V1 through `tools/lw_golden.py regress` on the 10
blessed golden inputs plus the 2 new defect-class cases, same USM70 finish so the
delta isolates the upscaler.

Alternatives: (a) keep V1 primary, V3 as a recorded trial; (b) promote V3.

## Decision

Promote V3 detail DAT2 to the primary first-pass upscaler and re-baseline the
golden set on it. V1 DAT2 remains the spandrel-confirmed fallback. Operator
directive, 2026-07-05, on the A/B evidence below.

## Consequences

**Good:** V3 wins the A/B across every primary axis - golden n=10: MS-SSIM 8/10
(other 2 rounding-tied), LPIPS 9/10, halo_pct 7/10 - and wins both new defect
cases (JPEG-artifact `coven-ashe`, banding `1341679`). It resolves BOTH standing
high-halo flags (fiora2 0.072->0.043, inkshadow 0.075->0.043 - now under the 0.05
flag), so the re-frozen golden set is all-PASS with zero flags. V3 sharpens more
gently (lower lap_ratio) yet never breaches the 1.0 softening floor (min ~1.28).
The G1 thresholds are UNCHANGED and still hold (widening to n=14 golden-comparable
showed no real breaches), so no recalibration was required - the promotion is
purely a better-model swap plus a re-baseline.

**Trade-off:** The golden `pipeline_version` changed (d9ec8125 -> 6d43a6d4), so
pre-promotion regress reports are not directly comparable - intended, and the
harness flags pv changes explicitly. V3 is slightly heavier per inference than V1.
The model is `.safetensors` bf16 (V1 was `.pth`); both are core-spandrel-loadable.

**Watch for:** No code hardcodes the primary model (it is always passed as an
arg), so "primary" now lives in the golden `pipeline_version` pin, this ADR, and
the docs updated alongside it (`RESTORATION_PLAN.md`, `UPSCALE_TOOLCHAIN.md`,
`AUDIT_GATES.md` 1.4). A separate finding surfaced during the widening: first-pass
4x-ing sources already >= the 2560x1440 target is wasteful and scores as
false-soft under the common-scale rule (the output is upscaled back to the native
source resolution to compare) - a G0 source-gate gap tracked in ROADMAP, not
addressed here. V3 "denoise" remains a per-image alternative for halftone-heavy
sources (not adopted as primary; detail is the right default for clean digital
illustration).
