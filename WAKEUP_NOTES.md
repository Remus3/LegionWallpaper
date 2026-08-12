# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01), and the 2026-08-01 (earlier) P3/P4/P5 + wiki-swap session and the 2026-08-01 (late) MCP-list/P1 session (both pruned 2026-08-02), and the 2026-08-02 all-five-recommendations/USM-flip/watchdog session (pruned 2026-08-09) - keep the last 3.

---

## 2026-08-11 - clean-retry-degrades HALF 2: detector precision measured, 0 FP

One commit. Suite **1837 passed / 18 skipped** (3.14, full run). LEDGER 91.

- **Answer: the detector is precise. 14 unattended (`auto`) proposals over the
  whole 21-slug gated corpus, ZERO false positives.** New read-only probe
  `tools/lw_clean_detector_probe.py` re-runs detect + the same `gate_decision`
  on each `_cleaninitial`; every `auto` region was then cropped and looked at.
  All 14 are a credit URL, handle, signature or credit strip (ADR-005 REMOVE).
  4 route to `qa` (not a proposal), 3 to `clean`.
- **Both cited cases were stale.** `vayne3` detects nothing at all now (n=0);
  `p08e8`'s fire is the real `@namakxin` signature the operator APPROVED
  removing (65122 changed px in `_cleandone`), same for `nguyen-ky-phuc` (9719).
- **Method lesson worth keeping:** a REJECT note is a WEAK label - it lands on
  one working's pixels, not on the detector's box. The strong label is the
  `APPROVE_CLEAN` sha256 vs `_cleaninitial`. Reading the notes alone would have
  "found" 2 false positives that are not false positives.
- **No rule narrowed** (acceptance branch 2). Shipped the regression net
  instead: `tests/test_lw_clean_detector_precision.py`, 29 tests pinning all 21
  measured rows + a KEEP-set test that no KEEP slug may become `auto`.
- Still open on the parent item: the cross-engine ladder is fired by the
  operator/skill, not by code.

### Then RECALL, same session (LEDGER 92)

- **14 confirmed false negatives, ~12 percent of the 229 `clean` verdicts.**
  Measured over all 302 unrouted `_firstdone` images (the gated corpus CANNOT
  answer recall - it is the detector's own `auto` output). 27 auto / 46 qa /
  229 clean; strata S1-S3 (17 images) censused in full, S4 (212) sampled n=14.
- **11 of the 14 are ONE object: the semi-transparent DeviantArt centre
  overlay.** Under the 0.35 YOLO floor (scores 0.11-0.25), illegible to OCR, and
  mid-frame so the geometry rules would only ever say `qa`.
- Two traps: `is_lol_logo` looks guilty (fired on all 4 S1 misses) but is NOT
  the binding cause - those marks had no box above the floor either; and the
  conf floor is a good FLAG signal, not an AUTO one (13/17 low-conf clean images
  are real misses).
- No rule changed there. The fix followed in the same session.

### Then BUILT the centre-overlay detector (LEDGER 93)

- **Gate v3: `clean` 229 -> 214 over the live 302-image corpus.**
  `tools/lw_clean_overlay.py` median-stacks the high-pass of marked frames into
  a template (the mark is the same pixels in the same place, so the art cancels)
  and scores by masked normalized correlation with a tight shift search. Pure
  numpy, no GPU, CI-safe.
- **Everything is measured, leave-one-ARTIST-out** (not leave-one-image - the
  template is partly artist-specific): clip at +-8 levels (0.112 -> 0.220),
  shift search +-3.0%h/+-1.6%w (-0.02 -> 0.100), window kept TIGHT (a wide
  search lifts CLEAN frames faster than positives). Threshold 0.15 = 15 clean
  images flip to qa, all 15 real, zero false; 0.12 costs 3 false.
- **The detector found 8 misses the census had not** - it is now 19 verified
  positives, and those 8 went into the template.
- Invariants pinned by tests: FLAG only (`qa`, NEVER `auto`), above the `n==0`
  and `lol_logo` rules, below `watermark_ocr`. One auto was lost on purpose
  (`239f` has a banner AND an overlay).
- Template is a derivative of DA's watermark -> `ops/runtime/` (gitignored),
  rebuilt via `--build-overlay-template`; missing template = flag off = v2.
- Suite 1853/18. Still open: REMOVAL (the alpha problem), thin signatures, and
  `110-cleanup` at 0.121.

## 2026-08-10/11 - intake x4, clean-retry-degrades half 1, venv-destroying test bug

Three commits, all CI green: `2958338` (retry default), `1ea9144` (suite venv
guard), `ee73136` (production venv guard). Suite 1808/18 on 3.14; lw-clean venv
1822/10 with 3 pre-existing failures. LEDGER 90 has the full record.

- **Intake:** 4 DeviantArt previews in, Tier 0 found no local match (hamming
  18-22), Tier 1 decoded + fetched all 4 quota-free. Two real gains (sona,
  orianna -> 1920px); kaisa + amazingeudora are still preview-grade.
- **clean-retry-degrades half 1 is ANSWERED with measured numbers:** retries won
  0 of 3 adjudicated slugs; `_02` lost on seam 14/15; `_03` "wins" only by
  repainting 2.66x the area and was rejected 9/9. `max_attempts` 2 -> 1, because
  `_auto_inpaint` recomputed a bit-identical inpaint on attempt 2.
- **The test suite was deleting Pillow from the lw-clean venv on every full
  run** (ultralytics autoinstall via a patched `PIL.Image.open`). Fixed in both
  the suite and the production tool. Venv then rebuilt clean, 54/54 packages,
  CUDA live.

**Do NOT redo:** the retry default + both autoinstall guards are shipped; the
venv is rebuilt and verified (old backup deleted, pip cache deliberately kept).
**Still open + unexplained:** the 3 venv-only concurrency failures
(`test_loop_concurrency` x2, `test_three_way_concurrency`) - verified
pre-existing at `78d0ad1`, 3.12-only, invisible to CI (3.14). Next up is the
`cleaning-detector-precision` half of the ROADMAP item.

---

## 2026-08-09 - weekly hygiene pass (unattended, LW-WeeklyHygiene scheduled run)

Doc + memory hygiene only, no code changes, no restart. Ground truth gathered
via a read-only investigation subagent, verified independently before any edit.

- **WAKEUP_NOTES trimmed to keep the last 3.** Relocated the 2026-08-02
  "all five recommendations EXECUTED" session (LEDGER 87) verbatim to
  `docs/history_notes.md` (banner pointer updated). CLAUDE.md checked clean
  (no stray per-item ledger content, 25015 bytes, well under the 60KB budget).
- **Two memory files were stale, both corrected (not committed - memory is
  outside the repo):** `project-lw-headless-stack.md` claimed the run
  dashboard was still missing; `tools/lw_rundash.py` shipped 2026-08-01, ~26
  min after that memory was written, and was never refreshed.
  `reference-lw-port-block.md` claimed only port 8901 was taken; `lw_ports.py`
  `ALLOCATIONS` now also has 8900 (`rundash`). Both files + the MEMORY.md
  index lines updated after independently confirming both files/ports on
  disk via Read/Grep (not just trusting the subagent report).
- **Flagged for operator (no action taken):**
  - **ACTIONABLE, code fix, out of scope this pass:** `tools/lw_facts.py`
    prints "5 LW-*" in its header but lists only 3 (matches the live
    `Get-ScheduledTask` count). Root cause: line ~116 counts raw CSV rows
    before the `set()` dedup on the next line, and `schtasks /Query` returns
    a duplicate row per extra trigger (e.g. `LW-Wallpaper` has logon + PT3M).
    One-line fix: count `len(set(rows))` instead. Cosmetic, Tier-0, your call.
  - **MEDIUM confidence, not edited:** `project-restoration-pipeline.md`'s
    "302 processed / ~76 original jpgs" count is 36 days stale (point-in-time
    by design, corpus count churns) - only worth updating if you want it kept
    current. `reference-deviantart-recovery.md`'s quota-state claim is
    inherently time-perishable (weekly reset) and cannot be confirmed without
    a live probe, which was out of scope for a read-only pass.
  - Scheduled tasks: only 3 `LW-*` registered (`LW-Wallpaper`, `LW-CIWatchdog`,
    `LW-WeeklyHygiene` - this run), both non-hygiene tasks last ran with
    `LastTaskResult=0`. No other anomalies.
- **Deferred (per skill contract, not this pass):** `/sync-all-md` full doc
  reconcile, any coverage%/VERSION/data-count prose recompute, `BACKLOG.md`
  edits, any dated-artifact history rewrite.

---

## 2026-08-02 (latest) - repo RENAMED, README made outward-facing, toolchain to 3.14, cv-lane, hand-off guarded

Suite **1800 passed / 17 skipped**, ruff clean, drift_guard 0 breaches / 4 notes.
Nine commits `15844aa`..`3a3f6f7`, CI green on every one.

- **Repo is now `Remus3/LegionWallpaper`** (was `legion-wallpaper`). `origin`
  updated; WAKEUP + LEDGER 88 URLs follow. Old URL redirects, but the old name
  is claimable by anyone - do not rely on the redirect.
- **README rewritten for a stranger** (`7809618`): CI + license badges, mermaid
  stage diagram, a "what is reusable here" table (verifier subagent, gates,
  drift guard, loop, state machine), scope/status section. It had NEVER been
  revised for a public audience - going public only added a License section.
- **Toolchain moved to 3.14** (`b096533`): CI was pinned 3.12 while Legion runs
  3.14, and ruff's `target-version` still claimed `py39`. Runner confirmed on
  CPython 3.14.6. `target-version` = the MINIMUM supported version; do NOT
  raise it above the CI pin.
- **`ruff.toml` `exclude` was INERT** (`f293428`) - it sat under `[lint]`, which
  measurably excludes nothing on ruff 0.15.12. Moved top-level. Only
  `tools/dwpose_onnx` was actually reaching the linter (everything else was
  covered by `.gitignore` by accident). Vendored dwpose now genuinely excluded.
- **UP017 + B905 cleared and un-ignored** (`7453936`, `a15394b`). B905 needed
  OPPOSITE answers per site: `strict=True` in `lw_clean_dekel.align_rois`
  (lengths guaranteed by construction), `strict=False` in the pairwise test
  idiom. A blanket autofix would have broken the test.
- **`align_rois` had ZERO tests** despite a docstring claiming "unit-tested".
  10 tests added (`4184ad2`), mutation-checked (crippling `estimate_shift`
  kills 2 of 3 correctness assertions), and **`cv-lane`** (`e31a91a`,
  `0472a72`) now runs them in CI off `requirements-cv.txt` - with a junit-XML
  guard that FAILS the job if the suite silently skips. Runner: `tests=10
  skipped=0`.
- **Desktop hand-off guarded** (`3a3f6f7`). BACKLOG claimed the file was
  "written each /done" - FALSE, `done.md` never mentioned it. Now
  `tools/lw_next_session.py` resolves + guards the target and `done.md` 10b
  makes the write mandatory. A doctored intent doc naming `RC-NEXT-SESSION.txt`
  falls back to LW's own file.
- **Do NOT redo:** the rename, README, 3.14 bump, exclude fix, UP017/B905, the
  align_rois tests, cv-lane, or the hand-off guard - all shipped and CI-green.
