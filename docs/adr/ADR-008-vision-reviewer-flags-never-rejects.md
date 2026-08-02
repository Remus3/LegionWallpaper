# ADR-008: A vision reviewer may FLAG, never REJECT - and the flag blocks a non-operator approval

**Date:** 2026-08-02
**Status:** Accepted

## Context

The anatomy percept has no working metric. A keypoint head-spine offset was
built, measured over all 288 approved firstdones, and REJECTED as a gate on the
evidence (LEDGER 60, `docs/ANATOMY_CENSUS_2026-07-29.md`); it ships as a
diagnostic only (`tools/lw_anat_metrics.py`, `tools/lw_anat_probe.py`). The
census also closed off the obvious rescue: splash art is cropped at the waist, so
most images have no confident hips, and a better pose model cannot find hips
outside the crop.

The right mechanism is the Claude-vision 2AFC path `end-review` already uses. The
open question was its AUTHORITY: may such a reviewer only FLAG, or may it REJECT?

Three facts bear on it, all measured rather than assumed:

1. **A demotion is not free here.** `clean-retry-degrades` (ROADMAP, 2026-08-02,
   two witnesses) established that cleaning workings after `_01` are measurably
   WORSE than `_01`. So a false REJECT does not merely cost a pass - on the
   cleaning stage it actively degrades the image it was trying to protect.
2. **Anatomy is the least deterministic percept in the ladder.** G1 reproduces
   every recorded `halo_pct` to 4dp. A vision 2AFC does not: same image, same
   prompt, different session can differ. An operator cannot re-derive a verdict
   they disagree with, and `truth_gate` exists precisely because irreproducible
   claims are this project's recurring failure class.
3. **There is no ground truth to check against.** The corpus has no finished
   reference by construction, and the art is deliberately stylised and
   non-anatomical - that is the house style, not a defect.

Alternatives considered: (a) may REJECT, like a metric gate; (b) FLAG only,
purely advisory; (c) FLAG only, but the flag BLOCKS approval by anything that is
not the operator.

## Decision

**Option (c). Operator direction, 2026-08-02.**

A vision reviewer may emit PASS or FLAG. It may never REJECT, and an unresolved
flag refuses an approval by any actor other than the operator.

Two mechanisms, deliberately separate, both in `tools/lw_pipeline.py`:

- **CLAMP** - `clamp_vision_audit()` coerces a `VISION_GATES` audit's
  `REJECT`/`FAIL` down to `FLAG` and records `clamped_from`. It runs at the
  ANNOTATE write boundary, not in a prompt: a rule that lives only in a
  reviewer's instructions is a request, whereas enforced where the audit is
  recorded no future reviewer can demote an image whatever it emits. Scoped to
  vision gates - G1's FAIL is a reproducible hard floor and clamping it would
  silently disarm the ladder.
- **BLOCK** - `_approval_record()` now reports `blocking_flags` (any reason
  matching `BLOCKING_FLAG_PREFIXES`, today `anat_`), and
  `assert_approval_allowed()` raises `PipelineError(code=3)` when a non-operator
  actor tries to approve while one is open. `approve` gained `--actor`, default
  `operator`. The check runs BEFORE the needauth -> done rename, so a refused
  promotion cannot strand a slug in the `APPROVED_PENDING_MOVE` shape.

The operator is never refused. Approving over a flag is their judgement, the
approval record already writes it down distinctly as an `override`, and refusing
it would wedge the operator's own workflow - the same principle ADR-006-era
`_approval_record` was built on.

The rail lands BEFORE auto-approval exists (the autonomy ladder is still at Phase
A, `autonomy-phases-bc`). That ordering is the point: a gate written after the
thing it gates is a gate that was once open.

## Consequences

**Good:** The safety property of REJECT is preserved - nothing ships past an
anatomy problem unseen - without giving an irreproducible judge the power to
spend a pass that has been measured to degrade the image. Unattended callers fail
CLOSED: an unrecognised actor string does not inherit operator authority just
because it is not on a list.

**Trade-off:** Every anatomy call lands in the operator's queue. If the reviewer
over-flags, that queue is the cost, and it is paid in operator attention rather
than in pixels. That is the intended direction of the trade.

**Watch for:** `BLOCKING_FLAG_PREFIXES` is a PREFIX match. A future reason name
that happens to start with `anat_` becomes blocking silently. If the reason
namespace grows, move to an explicit set.

**Revisit when:** the Phase A shadow window has >= 50 operator-reviewed images
and the reviewer's flag precision is a measured number rather than an assumption.
Promoting FLAG to REJECT is then a one-line change. Un-losing an image that a bad
REJECT sent back through a degrading pass is not.

**Not built here:** the vision reviewer itself. This ADR fixes its authority and
lands the rails; the reviewer is a separate slice and must arrive already unable
to exceed them.
