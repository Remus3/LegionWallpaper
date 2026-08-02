# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01), and the 2026-08-01 (earlier) P3/P4/P5 + wiki-swap session and the 2026-08-01 (late) MCP-list/P1 session (both pruned 2026-08-02) - keep the last 3.

---

## 2026-08-02 (latest) - all five recommendations EXECUTED; USM flipped on measurement; watchdog armed

Suite **1760 passed / 16 skipped** (session start 1679), ruff clean, drift_guard 0.
LEDGER 87. Operator answered "do the recommendation" x2 and "yes" x2.

- **usm-halo-calibration RESOLVED - and the measurement changed the answer.**
  Ran the missing axis: fidelity per variant over all 17 gated batch20 slugs at
  70/50/35/none. Expected a trade-off curve. There is none - **every fidelity
  metric improves monotonically as the mask weakens, worst case included.** The
  mask was COSTING fidelity, not buying it. `USM_DEFAULT` is now `(1.2, 35, 3)`;
  halo flags 7/17 -> 0/17, worst gated `lap_ratio` 1.1399 over its 1.0 floor.
  The 0.05 threshold was deliberately NOT moved - at 35 nothing flags, and
  moving a ruler to fit a reading was the one axis ruled out.
  Honest limit, stated in the doc and the code: these are FR SELF-comparisons
  against the conditioned source, so a weaker mask is closer by construction.
  They say the gate's metrics improve, not that the image looks sharper.
  `lap_ratio` is what stops the argument at 35 rather than at 0.
  Gotcha found while flipping: the synthetic step-edge fixture SATURATES - at 35
  its halo reads equal to no-mask - so that test now pins the historical 70.
- **ADR-007** ratifies `MAX_COMMON_PIXELS` 3840x2160, pinned by a test.
- **ADR-008** rules vision reviewers FLAG-only and blocks non-operator approval.
  `clamp_vision_audit()` at the WRITE boundary + `assert_approval_allowed()`
  before the needauth rename; `approve --actor` defaults to `operator`.
- **`tools/ci_watchdog.py` written, `LW-CIWatchdog` ARMED.** My earlier answer
  said "register it" - it could not be registered, the script did not exist.
  Now it does. HALT first (empty file counts), only a SETTLED failure acts, 2
  attempts per sha with a refund on transient vendor errors, merge self-gated on
  the fix branch's OWN green CI at its OWN head sha. `schtasks` rejects `/RI`
  for `/SC ONSTART`, so registration is the tool's own `--install` XML.
  **It has never seen a real red main** - watch its first genuine fire, and read
  `ops/runtime/ci_watchdog/watchdog.log` after any red push.
- **`LW-WeeklyHygiene` armed** too; its `-Model` was a dead id
  (`claude-sonnet-4-6`) and would have failed silently every Sunday.
- Still open and NOT implied: the 288 approved firstdones were made at usm70 and
  are now on a different recipe. Reprocessing is an operator call.

---

## 2026-08-02 - the five owed answers delivered; gemini-removal's reversible half landed

Suite **1695 passed / 16 skipped**, ruff clean, drift_guard 0 breaches. LEDGER 86.

- **The five answers are on disk at `docs/OPERATOR_ANSWERS_2026-08-02.md`**, each
  with evidence + a recommendation so a one-word reply closes the item. Headlines:
  `anat-vision-review` -> FLAG only, but the flag BLOCKS auto-approval (a third
  position; gets REJECT's safety without letting an irreproducible judge spend a
  pass that `clean-retry-degrades` has just measured is NOT neutral).
  `usm-halo-calibration` -> go toward usm35, but measure ms_ssim/lpips/dists per
  variant FIRST; never take the threshold-only axis, the one axis that improves
  the report and not the image. `g1-dists-cap-ratify` -> ratify 3840x2160 as
  ADR-007; **the question's premise needed correcting** - the cap sets the
  SOURCE-vs-OUTPUT COMPARISON scale, not the 1440p deliverable, sources run to
  6500x3660, and it recovered 63 of 230 images whose DISTS was silently absent.
  `arm-scheduled-tasks` -> register WeeklyHygiene + CIWatchdog, DROP GeminiAudit,
  and relabel `LW-Supervisor` BLOCKED-ON-SCRIPT (its gate is a missing file, not
  your approval).
- **gemini-removal: the seam is built and Claude is the default.** LW had no key
  to flip - Gemini structurally AUTHORED the directive and SCORED the diff - so
  the slice built `oracle_backend()` / `claude_oracle()` / `oracle()` and routed
  `director()` + `auditor()` through it. TDD RED first (14 of 16 failed; the 2
  that passed were the deliberate do-not-delete guards).
- **Rollback is TWO config keys** (`director_backend` / `auditor_backend` back to
  `gemini`). Nothing deleted - same posture as the `channel` flip (LEDGER 40).
  The Claude oracle is `--permission-mode plan`, NOT the executor's
  `bypassPermissions`: an adjudicator that can write is not an adjudicator. An
  unknown backend value resolves to `claude` - a typo must neither wedge an
  unattended run nor silently bill the vendor being removed.
- **Do NOT** delete `GEMINI_MUTEX` (byte-identical-by-contract with RC, and the
  rollback path consumes it) and do NOT rename `gemini.ready` (AHK handshake
  filename, not a vendor reference).
- NEXT on this item: the physical deletion sweep, but only AFTER the Claude
  oracle has authored directives on a live multi-cycle run. A backend that has
  never run is not one you delete the fallback for.

---

## 2026-08-01 - P7: the claim table finally REFUSES something; P8 closed on fit

Commits `b7814b3` (the gate), `a26e690` (docs sync, CI **green, confirmed with
`gh`** on the full sha), plus the P8 decision commit. Suite **1640 passed /
16 skipped** (baseline 1624 + 16 new), ruff clean, drift_guard 0 breaches.

- **P7 shipped as `start_gate()` (LEDGER 80).** `set --status in_progress` is now
  REFUSED unless the named `--agent` holds a claim on every file the slice
  declares. P4 built the table; this is the half that makes a CALL fail, which is
  the only property task-orchestrator had that LW wanted. Nothing installed.
- **Consequence for every future run:** `add` every slice with its real
  `--files`, then `claim --agent <id> --files <same>`, THEN
  `set --status in_progress --agent <id>`. A slice with no declared files cannot
  start at all - that was the trivial bypass. Both run commands document this now.
- **Not gated:** `verified` / `committed` / `failed`. A crashed agent's claims may
  be gone by then and gating those would strand a finished slice.
- **No `--force` bypass and no `start` subcommand**, both on purpose: a second
  door or an escape hatch would be the bypass.
- Found while implementing: three existing tests moved a slice to `in_progress`
  without asserting the exit code, so they would have passed vacuously under the
  gate. Each now claims first and asserts the 0.

**P8 followed, same session (LEDGER 81) - probe answered YES, adoption DECLINED
on fit, nothing installed.** Read at source via `gh api`, not the marketplace
page: all 7 gitwand MCP tools take a per-call `cwd`, every git access is
`execFileSync("git", args, {cwd})` with no `.git`-as-directory assumption, so a
worktree path works. The gate is cleared and the tool is still not worth taking -
P7 shipped hours earlier makes LW's merge conflicts rare BY ENFORCEMENT, so an
auto-resolver has ~nothing to resolve. REOPEN only if the orchestrator is widened
past disjointness, and do NOT re-run the probe. Gotcha if it ever is adopted:
every explain/trace string is hardcoded FRENCH with em-dashes - it must never
reach a commit message or a tracked doc.

**L2's retrospective half followed, same session (LEDGER 82,
`docs/CLAIMED_GREEN_RETRO_2026-08-01.md`).** `claimed_green_gate.py` gained
`--history` / `--audit` / `--json`. THE ANSWER: 387 transcripts, 269 green
claims, 25 flagged, **6 genuinely unbacked** after hand-reading every one, and
**ZERO** claims of green over a red suite. All 6 are the same shape - a count a
SUBAGENT or a previous session observed, restated as this turn's fact. So
Verification Discipline is right and its emphasis is wrong: the danger is
inheriting a green, not lying about one. Quote the reviewed 6, NEVER the raw
sweep - the number moved 206 -> 67 -> 31 -> 25 on three measurement bugs, the
biggest being that subagent transcripts carry NO entry-level `toolUseResult`
(output is on the tool_result PART as `content` + `is_error`). Two of the fixes
improved the LIVE gate: it would have blocked this very session twice for
reporting TDD RED honestly. Do NOT tune the two residual false-positive classes
against those 25 samples - that is fitting the detector to its own sweep.

**wiki-swap-manifest-hash-residue CLOSED too (LEDGER 83).** Decided on principle,
not patched: a swapped source gets an APPENDED `REPLACE_SOURCE` transition; the
INTAKE hash is never rewritten, because the manifest is the provenance record and
every other ledger here is append-only. Fixing it exposed a latent bug that was
not the swap's fault - `verify` picked a file's expected hash by dict-insertion
order, so **9 of the original 32 mismatches were that alone** (measured three
ways: 32 file-order / 23 latest-ts / 2 latest-ts+backfill). 21 slugs backfilled,
all 21 cross-checked against the swap manifest's recorded wiki hash before
writing (0 disagreements), idempotent on re-run. `scan --verify` 32 -> 2, plain
`scan` anomalies 0. The backfill tool REFUSES to run unscoped and that earned
itself immediately - the 2 leftovers are `vayne3`, never part of the 22 and
unexplained; an unscoped sweep would have recorded the drift as intentional.
**vayne3 then got explained, and it was hiding something (LEDGER 84).** The
2026-07-15 aspect-correction pass swapped operator-corrected 16:9 crops over
non-16:9 initials; vayne3 was the documented PILOT for that flow (original intact
in `9.Image Backup` at ar 1.725, on disk 1.781). Not corruption - the same class
as the wiki swaps, predating the convention. The real finding: its **8 siblings
from that same pass reported nothing**, because their crops were saved `.png`
over a `.jpg` intake and `_expected_hashes` keyed by FILENAME, so verify checked
NOTHING for them. 9 of 726 milestone files were unverifiable that way - including
`1341679`, which LEDGER 83 wrote off as "no comparable hash": it was UNCHECKED,
not fine. Root-cause fix: `_milestone_key()` identifies a milestone by slug +
stage + phase + version, never by extension. All 9 backfilled after checking each
went non-16:9 -> 16:9 with its original preserved.
FINAL: `scan --verify` **0**, `scan` anomalies **0**, **0** unchecked files.
The lesson worth keeping: clearing the one noisy row early would have recorded a
file and left the hole open - investigating it is what surfaced the 8 silent
ones. NOTE: `images/**` is gitignored, so those 32 manifest edits are on disk
only, not in any commit.

**Then the operator queue drain (LEDGER 85, 2026-08-02).** Both stale worktrees
removed (each 0 ahead of main, clean tree) and all 10 merged agent branches
pruned - `git branch` is just `main`. First pass: 17 of 20 approved (Done
267 -> 284); the other 3 are HELD at 3:2 (ar 1.500) because 16:9 costs ~15.6
percent of height against an 8 percent tolerance - `lw_first_pass` returns
`skipped/held` and the crop is an operator call, NOT forced. Cleaning: all 12
needauths rejected on review, then 3 passed through - `nguyen` (`_01`), `vayne3`
(initial unchanged; team logos are design), `p08e8` (`_01`, remnant accepted).
Cleaning Done 0 -> 3, scratch 18, anomalies 0. A targeted LaMa pass on p08e8's
remnant was built and REJECTED - it traded the fragment for a smudge plus patch
seams; do not retry that region blind.
**Two records corrected - both were blocking the right work.** New ROADMAP item
`clean-retry-degrades`: workings after `_01` are measurably worse, so the retry
loop is harmful past attempt 1, and the detector proposes edits on clean images.
And the BACKLOG's "modelviewer.lol: NO, do not retry" rested on ONE 2026-07-16
line measuring only asset-scraping; operator re-measured 2026-08-02 - Cloudflare
is no longer the blocker and the route is CAPTURE (seed each champion + skin
once, many perspectives/rotations). That also undoes the provenance objection
raised against a render library for m1: it applies to MIXING renders with real
art, not to an all-render design where both classes share a renderer - which
matches provenance by construction and kills the n=5 ceiling. Filed as a THIRD
m1 option; do NOT re-close m1 on provenance alone.

NEXT: **five operator answers are owed** - `anat-vision-review` FLAG-vs-REJECT
ramifications, `usm-halo-calibration` explain + recommend, `g1-dists-cap-ratify`
why a 4K cap when output is 1440p, `arm-scheduled-tasks` register + roster review
now that Gemini is going, and **`gemini-removal` to be executed** (operator said
proceed). Those were asked this session and deferred to the next one. Also open:
`wiki-swap-manifest-hash-residue` (scan --verify HASH_MISMATCH on 21 of 22,
bookkeeping only; plain scan is clean). Loose end unchanged: two stale worktrees
still registered - check for unmerged work before removing.
