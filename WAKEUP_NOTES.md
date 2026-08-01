# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01) - keep the last 3.

---

## 2026-08-01 (late) - the MCP list finally got READ, and P1 shipped off the back of it

Three commits: `cf9dfcc` (stage-4 dive), `9d38fa0` (the off-list sources), `278792e`
(P1). Suite **1563 passed / 16 skipped**. Ruff clean, drift_guard 0 breaches, CI
**green on 278792e verified with `gh`**.

- **All 63 LW-list entries read at source.** The triage had 5 VERIFIED-LIVE and
  58 INHERITED-RC, so 58 scores came from a summary written for another project.
  Measured: 31 of 63 need a key/account/hosted service, and only 13 state Windows
  support at all. `mockd` 5 -> **8** (offline Windows binary, record-and-replay -
  the DeviantArt stub answer). viznoir 6 -> 3 and picdefenseio 6 -> 2, both dead.
- **The off-list posts are bot-generated summaries of OTHER posts.** CCR-146, LW's
  top off-list score at 9, rests on `--append-subagent-system-prompt`, which does
  not exist on 2.1.220 - the post's own limitations say the source was "Claude
  itself told me". 9 -> 1. `--agent <name>` DOES exist and is salvaged separately.
- **My own retrieval failure is the lesson**: I measured a 403 on the `.json`
  endpoint and generalized it to the host, filing a live source as a dead end. RM
  caught it. `curl -sSL` on old.reddit HTML works, 200 at ~55 KB.
- **P1 (LEDGER 71) is the real prize.** The Stop slot was empty since the file was
  written; it now runs `tools/claimed_green_gate.py`. TDD went green on synthetic
  fixtures that were WRONG about the data - a live probe found 2 pytest runs and
  classified both `unknown`. Results join by `tool_use_id` onto a LATER entry, a
  Bash result has NO `code` field, and `interrupted` is the STRING "False".

NEXT: **P2 - mockd for the recovery waterfall** (BACKLOG `mcp-lift-phases`). One
offline Windows binary, Apache-2.0; record the real DeviantArt oEmbed + gallery-dl
exchanges once including a quota block, then delete the hand-written stubs.
Do NOT redo: the 63 dives (go upstream, not to the marketplace page), the Reddit
retrieval (recipe is in the dive), or P1.

---

## 2026-08-01 (night) - the dashboard spec is fully built out; all four remaining items landed

Four commits: 3e8ce6a (item 3), 1d3c2c5 (item 5), 621e8d1 (item 6), 27b22c3
(P4 + P5). Suite 1458 -> **1524 passed / 16 skipped**. Ruff clean. CI
**CONFIRMED green on 27b22c3 with `gh`** - not assumed, which was last
session's stated process miss. Full detail in LEDGER 69.

- **truth_gate now persists what it observed onto the slice ladder.** A global
  refusal quarantines no individual slice, so red-suite discrepancies are
  carried onto every row prefixed `global:`; `--skip-suite` writes
  `counts: null`, never zeros. `build_verdict_record` is now the ONE owner of
  the record shape.
- **The three run-id namespaces are joined, on evidence only.** Two ids sitting
  side by side is not a join - the header renders `=` only when a cycle record
  carried both, `/` plus an amber `unjoined` tag otherwise.
- **136 agents across 35 sessions are now durable**, back to 2026-07-03,
  including all 18 of the 2026-07-30 fleet. `tools/lw_agent_mirror.py`, called
  per cycle by the controller.
- **P4 and P5 shipped.** P5's first live render is 30 commits / 5 observed /
  25 gaps, every observed row "chain broken". That is the panel working, and it
  indicts the tree it runs on - which is the point.
- **Two things I deliberately did NOT build**: P4's HELD column (no HELD
  substate exists in `pipeline_state.json`) and its run-attributed "this run
  added N" line (nothing attributes an image to a run). Inventing a source for
  either would have been worse than the gap. Do not "fix" these without a real
  producer.

**P6 Fleet History followed in `71baedd`** (LEDGER 70), on your ask. It reads
the mirror nothing was reading: per-session token spend (3,439,867 total,
2026-07-03 to 2026-08-01) and, more usefully, whether each session's source
transcripts still exist. All 136 are still on disk today, so the mirror is
AHEAD of the reaper - the panel says so rather than leaving a blank. Suite
1537 passed / 16 skipped, CI green on `71baedd`, confirmed with `gh`.

NEXT: the dashboard spec has NO open items. Two numbers on it read zero for a
reason and are NOT bugs - do not "fix" either in code. `truth_gate_blocking`
stays false until a live run has been observed. P6's `joined_sessions` is 0
because no controller cycle has run since the `session_id` field was wired; the
next live cycle populates it. Product work is Stage 2's remaining 3 namakx
ghosts (triage improvement 1) and the 29-slug NEEDAUTH queue, which P4 now
shows you (oldest 2d, spread across stages).

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
