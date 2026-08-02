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

## 2026-08-01 (latest) - THE REPO IS PUBLIC; history purged, Apache-2.0, every sha rewritten

Suite **1760 passed / 16 skipped**, ruff clean, drift_guard 0 breaches / 25 notes
(the notes are the 43 intentionally-dead shas in the new map doc - expected, not drift).
LEDGER 88. Commits `4e3b617` + `f9cd7a1`.

- **<https://github.com/Remus3/legion-wallpaper> is PUBLIC.** Audited first: all
  306 commits scanned as full diffs for keys / tokens / PEM headers / the
  operator email - zero hits, and no secret-named file was ever tracked.
- **`style.jpg` + `style2.jpg` purged from all history** (`git filter-repo`),
  untracked, gitignored; both files restored to disk from a pre-purge bundle.
  They were the only tracked image bytes and contradicted the README's own
  process-not-pixels boundary.
- **The trap worth remembering:** a force-push does NOT GC unreachable objects.
  GitHub still served the dead sha and `style.jpg` at 122630 bytes afterwards,
  so going public would have republished exactly what was purged. Fixed by
  delete-and-recreate (repo had 0 issues / PRs / forks / stars / secrets, all
  API-verified). Needed a `delete_repo` scope the token lacked; operator granted it.
- **Apache-2.0 LICENSE** (canonical text, `Copyright 2026 Moonbeam`) + a README
  License section stating the grant covers the PROCESS and cannot cover the
  third-party image corpus.
- **The permanent cost:** every sha from `152d84f` onward changed. 43 shas cited
  across LEDGER / history_notes / WAKEUP no longer resolve. Doc text was NOT
  edited (append-only ledger); the old -> new table is
  `docs/_archive/2026-08-01-sha-rewrite-map.md`. `.git/filter-repo/commit-map`
  is untracked local plumbing and will be clobbered by any future rewrite.
- Gap noticed, not fixed: `drift_guard.check_cited_shas` only reads STAGED docs,
  so it cannot catch a rewrite invalidating shas already committed.

---

## 2026-08-02 - all five recommendations EXECUTED; USM flipped on measurement; watchdog armed

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
