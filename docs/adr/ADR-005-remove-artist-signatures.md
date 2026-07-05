# ADR-005: Remove artist signatures (at the cleaning-scratch stage)

**Date:** 2026-07-05
**Status:** Accepted

## Context

The watermark/mark detector flags legitimate in-art artist signatures alongside
site watermarks (uhdpaper, deviantart handles, etc.). Keep-vs-remove was a queued
operator decision (ADR-002; `RESTORATION_PLAN.md` section 9; `CLEANING_INPAINT.md`);
until ruled, signature-flagged files routed to the human-QA keep-queue and were
never auto-inpainted. The corpus is a private personal-wallpaper restoration set -
the shareable deliverable is the PROCESS (pipeline, gates, rubric), never the
cleaned third-party images (`RESTORATION_PLAN.md` section 10).

Alternatives: (a) keep signatures (route to a preserve-queue); (b) remove them.

## Decision

Remove artist signatures - do not keep. Signatures are treated as removable marks
and inpainted out during the cleaning scratch stage (Stage 2), through the
standard cleaning path (detect -> mask -> inpaint -> verify) with the usual gate +
human-QA fallback. Operator directive, 2026-07-05.

## Consequences

**Good:** Unblocks the cleaning-stage design - no separate keep-queue branch;
signatures follow the same masked-cleaning path as any other mark, one consistent
removal policy. Closes the last queued open operator decision from ADR-002.

**Trade-off:** Removes artist attribution marks from the artwork. Acceptable only
because the output is private personal use and is never redistributed (the
process, not the images, is the deliverable - `RESTORATION_PLAN.md` section 10).
If the shareable-milestone scope ever changes to include images, this must be
revisited (licensing / attribution).

**Watch for:** The cleaning stage is not built yet - this ruling is the spec it
must honor (`CLEANING_INPAINT.md` updated alongside this ADR). The detector must
still distinguish signatures from genuine art content to avoid over-masking; the
standard cleaning gate (outside-mask identity assertion, mask-area <= 2 percent
and border-band limits) remains the safety net.
