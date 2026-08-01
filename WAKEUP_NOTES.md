# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29) - keep the last 3.

---

## 2026-08-01 (evening) - Stage 2 finally drained; L1 closed; dashboard spine + panel; concurrency measured; truth_gate wired

Six commits: d460e95 (stage-2 drain), c526c8b (MCP L1), 3cc0d92 (GpuBusy),
0c57899 (rundash spine), cd2a996 (P1b panel), 55033cf (concurrency), a14ab3f
(truth_gate + two fixes). Suite 1401 -> 1458 passed / 16 skipped. CI GREEN on
a14ab3f (verified with gh, not assumed).

- **Stage 2 flowed for the first time.** 12 slugs cleaned and submitted; the
  needauth queue is yours to approve. 9 stay in scratch by design: 3 gate-FP
  KEEPs, 3 namakx dark-outline ghosts (need triage improvement 1), 3 manual lane.
  Coverage differed from the 2026-07-16 triage table (aatrox 47.9 vs 76.1), so
  those by-eye verdicts did NOT carry over - re-checked on a contact sheet.
- **L2 is CLOSED, not deferred:** `--append-subagent-system-prompt` does not
  exist on CLI 2.1.220. Its premise had already failed (hooks DO fire headless).
- **skylos is not CI material here** - it flagged `lw_httpd:122
  allow_reuse_address = False`, which IS the single-instance bind guard. Use
  `uvx skylos==3.0.0 <onedir>` as a one-shot hint only.
- **GpuBusy was forked 4 ways** so `except GpuBusy` only caught its own module's
  raise. One shared zero-import class; the package-style `tools.lw_gen_run` path
  was the trap that would have made two class objects.
- **Three-way concurrency MEASURED** with real processes: slots peak exactly 3,
  4th queues, dead-holder reap works under contention, mutex serializes to 1.
  Production slot pickup latency is 0-4s (backoff/jitter 2.0), not instant.
- **truth_gate wired and it earned it on run one:** its own
  `DEFAULT_SUITE_CMD` swept the whole tree and manufactured a REFUSE on a green
  tree; and it caught a CI red I had reported as green.

MY PROCESS MISS, do not repeat: I declared 55033cf done on a local Windows pass
without confirming CI. It was red - `winmutex.hold` is a no-op off Windows, so
the mutex serialization assertion is FALSE on Linux, not vacuous. Fixed with
skipif. Confirm CI before saying done.

NEXT: dashboard has 4 items left (per-slice suite observations, join the three
run-id namespaces, mirror agent metadata before cleanup reaps it, P4/P5 panels).
truth_gate is ADVISORY - flip `truth_gate_blocking` once a live run has been
observed. Stage 2's remaining 3 namakx ghosts need triage improvement 1.

---

## 2026-08-01 (late) - three-repo N=3 landed; the hook rule was stale and is corrected

Continues the entry below. HEAD `e436128`. Suite **1401 passed / 16 skipped /
0 failed**, ruff clean, drift guard 0 breaches, CI green.

**THIS ENTRY SUPERSEDES TWO THINGS IN THE ENTRY BELOW:** its "ALSO OWED"
B5/B6 block (both are merged - nothing owed) and its "the shared lane cap stays
at 2" (it is 3 on all three repos now). Its DRAIN STAGE 2 priority still stands
and is still the product work.

- **B5 and B6 are MERGED and verifier-CONFIRMED.** Nothing owed from them. The
  dashboard's evidence chips now render real verdicts (B1 shows
  `prior_refutes=1`), and NO CUDA consumer in the tree is left unwired - a
  verifier swept all 55 files under `tools/` itself: 9 CUDA, 9 acquire, 16 sites.
- **N=3 is live across all three repos.** LW 3 / RC 3 / RM 3, `slots.py`
  byte-identical at `5297f2d041030398` (7154 bytes) on all three disks, each
  re-hashed locally rather than trusted from a note. LW flipped first and
  carried a deliberate red for ~20 minutes; RC and RM followed the same session.
  A cross-repo equality guard makes an atomic change impossible by construction -
  whoever moves first is red. RM is immune only because its guard pins
  self-contained constants rather than a sibling's disk; that is the shape to
  steal if we ever revisit.
- **CLAUDE.md's hook hard rule was STALE and is corrected (`e436128`).**
  PreToolUse hooks DO fire under headless `claude -p --permission-mode
  bypassPermissions` on CLI **2.1.220** - measured here, Bash provably ran and
  both SessionStart and PreToolUse fired. The old claim was measured on 2.1.205.
  `.githooks` stays authoritative; Claude hooks are defense in depth, not absent.
  **The probe returned a FALSE NEGATIVE twice before it was right** - an
  invalid `settings.json` (heredoc collapsed the double backslashes; single
  backslashes are not valid JSON escapes, so it silently never parsed), and the
  trust bug below. Both make a live hook look dead. Both are now named in the rule.
- **Trust bug found by RM, reproduced and FIXED on LW.** `~/.claude.json` held
  THREE keys for one directory - `C:\LegionWallpaper` True, `C:/LegionWallpaper`
  **False** (what headless reads), `C:/legionwallpaper` True - so headless was
  silently discarding `permissions.allow`. Fixed LW's key only; backup at
  `.claude.json.lwbak-2026-08-01`; RC and RM keys verified untouched.
- **NOT fixed, and it is RC's call:** `"model": "rc-main"` is set machine-wide in
  `C:\Users\Administrator\.claude\settings.json:17` and does not resolve. LW is
  insulated only because its executor passes `--model` explicitly
  (`executor.py:431-433`). Any LW call that does not would break. LW did not
  touch it.
- **Still unmeasured, by anyone:** three-way concurrency; a contended acquire
  reaping a stale lock in a live run; recent two-way concurrency (LW contributed
  zero for a week).

---

## 2026-08-01 - the loop was wedged for five days; run dashboard shipped

Detail: LEDGER 62. Suite 1178 -> **1346 passed / 16 skipped / 0 failed**, ruff
clean, drift 0 breaches, CI green. HEAD `7879af2`, 14 commits. Six worktree
slices, all verifier-gated; two REFUTED and reworked rather than merged.

- **THE PRIORITY NEXT SESSION, operator-directed 2026-08-01: DRAIN STAGE 2.**
  Merge B5/B6 first (below) since they are cheap and already committed, then
  spend the session on the product rather than more infrastructure.
  **Nothing has EVER flowed past Stage 2** - `clean_scratch: 21, clean_done: 0`,
  unchanged since the attack plan was written 2026-07-16. Everything shipped on
  2026-08-01 was infrastructure.
  The work is already triaged in `docs/research/IOPAINT_TRIAGE.md`:
  **CLEAN-AUTO 9 | PARTIAL 7 | MANUAL 2** (+3 gate-FP KEEPs = the 21). Three
  PARTIAL fixes are already CONFIRMED in that doc and just need landing:
  `--chroma-thr 12` clears `spirit-blossom-ahri-mono-01`; a full-width banner
  band `(860,958,1720,1035)` + chroma clears `viego-...slimshadywallpaper`;
  widen region right + chroma clears `aidraw-...watercolornessie`. That takes
  PARTIAL 7 -> 4.
  Route to the manual IOPaint lane, do not fight them: `fantasy-design-...aivio`
  (ornate filigree smeared) and `prestige-coven-xayah-...pebano1` (busy feathers,
  a KNOWN LaMa failure) - plus `fury-tempest-sona` if fidelity demands, since it
  has no residue but softens folds and gold trim.
  Then re-run the worker over CLEAN-AUTO 9 + the cleared PARTIALs ->
  `save-working --tool iopaint` -> `submit`. Acceptance: `3.Cleaning Scratch`
  holds ONLY manual-lane slugs and the needauth queue holds the auto-cleaned set.
  Tooling: `tools/lw_clean_iopaint.py`, venv `C:\Tools\lw-clean\venv`, ritual
  `.claude/commands/cleaning-pass.md`. HARD RULE: never inpaint without a mask,
  and every auto-clean must pass the outside-mask identity assertion.
  **Note this will be the FIRST real exercise of the GPU mutex** - B4 wired
  `lw_clean_iopaint` and `lw_clean_pass`, so a cleaning run now acquires
  `Global\LW_GPU` and will wait up to 1800s then raise `GpuBusy` if a sibling
  repo holds the card. If that fires, it is the guard working, not a bug.

- **ALSO OWED.** Two slices were IN FLIGHT when the session ended, both recorded
  `in_progress` in `ops/runtime/slice_manifest.json`:
  - **B5** persist verifier verdicts - **COMMITTED `d570d42` on branch
    `worktree-agent-a902870319ee6443d`, NOT verified and NOT merged.** Nothing
    to salvage; run the `verifier` subagent against it, then merge. It reports
    1340 passed / 16 skipped and a backfill of the live manifest. Note it also
    fixed the same flaky `status_age_s` bound that `7879af2` fixed on main, so
    expect a conflict in `tests/test_lw_rundash.py` and keep main's version.
    ROADMAP `rundash-instrumentation`.
  - **B6** wire the 3 remaining CUDA consumers - branch
    **COMMITTED `a76a05d` on branch `slice-b6-gpu-mutex-remaining`** - note that
    is NOT a `worktree-agent-*` name. Nothing to redo; verify then merge.
    It reports 1367 passed / 16 skipped and, critically, that **NO CUDA consumer
    in the tree is left unwired** - which is the answer RC and RM are waiting on.
    ROADMAP `gpu-mutex-inert` carries the constraints; read them first.
    It also CORRECTED a premise I gave it: `winmutex.hold`'s timeout bounds the
    WAIT TO ACQUIRE, not the hold duration (`winmutex.py:96-101`), so a long
    training run cannot time itself out and needs no bespoke constant.
- **Your headless loop could not start and had not been able to for five days.**
  `RUNNING.lock` named a pid recycled to an unrelated conhost. Fixed `e63a50d`.
  Do NOT re-investigate.
- **The shared lane cap stays at 2.** RC proposed 3 and Red Moon has already
  WRITTEN 3, so the bucket is 3 wide whenever RM acquires first - RM was asked to
  set it back today. LW cannot agree until B6 lands; 6 of 9 CUDA consumers are
  wired. Both siblings are waiting on that answer.
- **The run dashboard is live** at 127.0.0.1:8900 (`tools/lw_rundash.py`,
  `pythonw`, read-only). Every evidence chip reads NOT OBSERVED until B5 lands.
- **Do NOT collapse `lw_httpd.parse_ts` and `lw_rundash_state.parse_iso`.** First
  reads a naive stamp as UTC, second as LOCAL - 5 hours apart on this machine.
  `loop_controller.py:303` writes naive LOCAL, so `parse_iso` is correct.
- Inbox is clear: RC and RM both answered today. Port blocks settled three ways,
  `slots.py` confirmed byte-identical at `95077a62...5054f9`.

**Do-not-redo:** the recycled-pid fix; the `null`-evicts-cache fix; the DWPose
correction (it is onnx-CPU, not a GPU consumer); the port registry AST widening;
the flaky `time.time()` bound in `test_lw_rundash.py`.
