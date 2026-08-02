# Operator answers - 2026-08-02

Five questions asked at the end of the 2026-08-01 session and deferred. Each
answer states the evidence it rests on and ends with a recommendation, so a
one-word reply is enough to close the item.

---

## 1. anat-vision-review - what changes if the vision reviewer may REJECT, not only FLAG

**The question.** `tools/lw_anat_metrics.py` keypoint offset was built, measured
over all 288 approved firstdones, and rejected as a gate (LEDGER 60,
`docs/ANATOMY_CENSUS_2026-07-29.md`). The right mechanism is the Claude-vision
2AFC path `end-review` already uses. Open: may that reviewer only FLAG, or may
it REJECT.

**What FLAG-only costs.** The reviewer writes a reason into the audit block and
the image continues. Every anatomy call lands in the operator's queue as an
annotation. Throughput is unchanged; the reviewer can never be wrong in a way
that loses an image; and the whole value is advisory - if you do not read the
flag, nothing happened. Precedent in this repo: `lw_anat_metrics` already ships
diagnostic-only, and truth_gate shipped ADVISORY (`truth_gate_blocking: false`)
for exactly this reason - a new control-flow branch that can HALT should not be
its own first measurement.

**What may-REJECT costs.** Three concrete ramifications, in order of how much
they bite:

1. **A demotion is not free.** REJECT at the gate ladder demotes a milestone to
   the previous scratch stage with the reason logged. That is recoverable, but
   it spends a pass, and `clean-retry-degrades` (ROADMAP, 2026-08-02) has just
   established that a further pass on this pipeline is not neutral - later
   cleaning workings are measurably WORSE than `_01`. So a false REJECT does not
   merely cost time here; on the cleaning stage it actively degrades the image
   it was trying to protect.
2. **Anatomy is the least deterministic percept in the ladder.** G1 metrics are
   reproducible to 4dp (the USM census reproduced every recorded `halo_pct`
   exactly). A vision 2AFC is not: same image, same prompt, different session
   can differ. A non-reproducible REJECT cannot be re-derived by the operator
   when they disagree with it, and `truth_gate` exists precisely because
   irreproducible claims are the failure class this project keeps hitting.
3. **Splash art defeats the measurement.** The census already showed most images
   have no confident hips - the art is cropped at the waist. A reviewer that may
   REJECT on anatomy will be adjudicating stylised, deliberately non-anatomical
   proportions (that is the house style of the corpus) with no ground truth to
   check against. There is no finished ground truth here at all - see
   `project-no-finished-ground-truth`.

**There is a third position and it is the one worth taking.** FLAG-only, but the
flag is BLOCKING at the operator queue rather than at the gate: the image cannot
be auto-approved while an anatomy flag is unresolved, and the operator either
clears it or sends it back. That gets the safety property of REJECT (nothing
ships past an anatomy problem unseen) without giving an irreproducible judge the
power to spend a degrading pass on its own.

**Recommendation: FLAG only, and make the flag block auto-approval.** Revisit
REJECT after the Phase A shadow window (`autonomy-phases-bc`) has >= 50
operator-reviewed images and the reviewer's flag precision is a measured number
rather than an assumption. Promoting it later is one config key; un-losing an
image that a bad REJECT sent back through a degrading pass is not.

---

## 2. usm-halo-calibration - the three axes, explained, with a recommendation

**What is actually true, from the census** (`docs/USM_HALO_CENSUS_2026-07-30.md`,
all 17 gated slugs of batch20, nothing inferred):

- Condition A reproduces every recorded manifest `halo_pct` to 4dp, so the probe
  measures the real pipeline, not a model of it.
- Skip the unsharp mask entirely and max `halo_pct` falls to **0.0062**, 0 of 17
  over the line. **Our own USM manufactures every halo flag.** ADR-004
  (IllustrationJaNai V3) is NOT implicated and does not need re-opening.
- But with no mask, **6 of 16 gated slugs fall through the `lap_ratio` 1.0 HARD
  FAIL floor** - i.e. removing the sharpening trades 7 soft flags for 6 hard
  fails. That is strictly worse.
- `halo_pct` is **monotone in USM percent on every slug**. It reads as a
  strength dial, not a defect detector, and the 0.05 line cuts a continuum with
  no gap at it.
- `usm35` clears every halo flag with the weakest gated `lap_ratio` at
  **1.1399** (comfortably above the 1.0 floor). `usm50` still leaves 2 flagged.
  Current default is `USM_DEFAULT = (1.2, 70, 3)` at `tools/lw_upscale.py:167`.

**The three axes.**

- **Axis A - re-seed the halo threshold.** Raise the 0.05 flag line for the
  IllustrationJaNai path. `tools/lw_g1_gate.py:178-184` says in its own comment
  that 0.05 was seeded from an n=10 realesrgan/USM70 sample and is owed
  recalibration. Cost: zero pixels change, one constant moves, and every already
  approved image keeps its recorded numbers. Risk: you are moving the ruler to
  fit the reading, and since `halo_pct` is monotone with no gap at any value,
  ANY line you pick is arbitrary - you would be replacing one unjustified
  constant with another.
- **Axis B - soften `USM_DEFAULT`.** Drop 70 percent toward 35. Cost: this
  changes OUTPUT PIXELS for every future image, and the census deliberately did
  NOT recompute ms_ssim / lpips / dists per variant - so **the fidelity cost of a
  milder mask is UNMEASURED**. Picking a number on halo evidence alone is the
  exact one-axis mistake that already got one gate rejected in this project.
  Risk: also corpus-splitting - images processed before and after the change are
  no longer directly comparable.
- **Axis C - accept the flags.** Change nothing. The 7 flags are FLAG, not FAIL;
  they never blocked anything; the operator approved 17 of 20 in batch20 anyway.
  Cost: the gate keeps emitting a signal that carries no information, which
  trains everyone to ignore it - and a gate you ignore is worse than no gate,
  because it looks like coverage.

**Recommendation: B, but measured first, and it is a two-step, not a decision.**
Step 1 (no ruling needed, cheap, ~17 slugs): re-run the census variants WITH the
fidelity metrics - ms_ssim / lpips / dists per USM variant - which is the one
thing the first census skipped and the only thing that makes a number defensible.
Step 2: if usm35 holds fidelity within the existing G1 bands, take usm35, and
leave the 0.05 line ALONE - because at usm35 nothing flags, so the threshold
stops mattering and you have not moved a ruler to fit a reading. If usm35 costs
real fidelity, fall back to Axis C (accept) rather than Axis A - an arbitrary
threshold move buys a clean dashboard and nothing else.

Do not take A on its own under any outcome: it is the only axis that improves the
report without improving the image.

---

## 3. g1-dists-cap-ratify - why a 4K cap when the deliverable is 1440p

**The premise of the question is the thing to correct.** `MAX_COMMON_PIXELS`
(3840x2160, `tools/lw_g1_gate.py:520`) does **not** cap the OUTPUT. The
deliverable is unchanged: an approved image is exactly 2560x1440. The cap governs
the **common comparison scale** - the resolution at which the full-reference
metrics compare the SOURCE against the OUTPUT.

**Why that is bigger than 1440p.** `docs/research/AUDIT_GATES.md` 1.2 rules that
FR metrics are computed at SOURCE scale: the output is downscaled to meet the
source, never the reverse, because bicubic-upscaling the reference manufactures a
blurry reference and biases every metric toward approving soft output - which is
the exact softness bug ADR-002 structurally bans. So the comparison scale is set
by the SOURCE, and LW sources run well past 1440p: up to 6500x3660 in this
corpus, with 26 images sitting natively at 3840x2160.

**Why a cap exists at all.** Measured 2026-07-18: DISTS allocates ~2 GiB of VGG
activations at 7680x4320 on top of what the earlier metrics still hold. That OOMs
the 12GB card AND OOMs system RAM on the CPU fallback, so the metric was simply
uncomputable for 8K sources - **63 of 230 first-pass images had lost DISTS
entirely** this way, every single failure being DISTS, at scales 5376x3024 and
up. The largest common scale that ever succeeded corpus-wide was 4096x2306
(9.4 MPix). 3840x2160 (8.29 MPix) sits just under that proven ceiling for
headroom and lands exactly on the scale 26 corpus images already use natively.

Over budget, BOTH sides are Lanczos-resampled down to fit, preserving aspect;
under budget the source scale is used verbatim, so the ordinary case is
unchanged. The cap only ever DOWNSCALES the reference, so caveat 2 above still
holds. A capped value is not interchangeable with a native one (capping hides
high-frequency difference), which is why `fr_metrics` reports `capped` and
`native_scale` alongside `common_scale` - the two can never be silently
conflated.

**Why it needs ratifying rather than just shipping** (it is already shipped,
LEDGER 32 / `b14b688`): it changes the G1 measurement basis corpus-wide, which is
ADR-006-scale, so the VALUE is an operator call even though the mechanism is
settled.

**Recommendation: ratify 3840x2160 as ADR-007 as-is.** It is empirically derived
(below a measured ceiling, above the corpus mode), it recovers 63 images' worth
of a metric that was silently absent, and the alternative - native-8K DISTS - is
measured impossible on this box on both devices. Do not re-open native-8K.

---

## 4. arm-scheduled-tasks - roster review, Gemini going

Registered today: `LW-Wallpaper` only (2026-07-18, Ready). Roster and
registration commands live in `docs/OPERATIONS.md`.

| Task | Verdict now | Why |
|---|---|---|
| `LW-Wallpaper` | KEEP - already registered | Desktop deck rotator, working. |
| `LW-GeminiAudit` | **DROP from the roster** | Its entire job is a Gemini read-only auditor pass over the repo via `tools/gemini_audit.ps1`. With `gemini-removal` executing, registering it would arm a vendor we are removing. It was never registered, so there is nothing to disable - it just comes off the list. |
| `LW-Supervisor` | **CANNOT register yet** | Its target `ops/lw_supervisor.py` does not exist - the supervisor is TBD until the product has a long-running process. Registering it arms a task that fails on every logon. Blocked on the script, not on your approval. |
| `LW-WeeklyHygiene` | REGISTER | `tools/weekly_hygiene_run.ps1` exists; the pass is relocate-only and defers `/sync-all-md`. Low blast radius, weekly. |
| `LW-CIWatchdog` | REGISTER, with the kill switch understood | Self-gates its merge on the ci-fix PR's OWN green CI and works in an isolated worktree. Kill switch: create `ops\runtime\ci_watchdog\HALT`, or `Disable-ScheduledTask LW-CIWatchdog`. This is the highest-authority task on the list - it can push - so it is the one to arm knowing the switch. |

**Recommendation: register `LW-WeeklyHygiene` + `LW-CIWatchdog` now, drop
`LW-GeminiAudit` from the roster permanently, and leave `LW-Supervisor` on the
list marked BLOCKED-ON-SCRIPT rather than NOT-YET-REGISTERED**, so it is clear
the gate is a missing file and not a missing approval. The deep-audit program
stays DORMANT - it is a separate gate and nothing here implies it.

---

## 5. gemini-removal - executed this session

See `docs/LEDGER.md` and the ROADMAP entry. Shape of the landing: the reversible
half flips now (backends behind a config key, Claude default), the Gemini backend
stays reachable as the rollback path, and the physical deletions file as a sweep.
`GEMINI_MUTEX` is NOT deleted from `ops/loop/winmutex.py` - it is
byte-identical-by-contract with Riot Commander and still has a live consumer.
