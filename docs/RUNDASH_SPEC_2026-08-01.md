# LW Run Dashboard - spec

Authored 2026-08-01 from three parallel read-only design lanes (data census,
`lw_monitor` teardown, information design) plus adjudication. Every claim below
was measured on the live tree, not inferred.

**Scope.** A dashboard for RUNS - headless cycles, worktree agents, slices,
verification. NOT for images: `tools/lw_monitor.py` on 8901 owns image-stage
state and is not touched by this work.

---

## The incident this exists to fix

2026-07-30. A headless run dispatched 4 worktree build agents and 4 verifier
agents. The operator was away. Nothing about that run was visible anywhere but
the chat transcript: not which agents were live, not which slice each owned, not
that one slice was REFUTED and sent back, not that the suite moved 1093 -> 1169,
not that a merge was waiting. The only durable artifact was a Desktop synopsis
the run wrote by hand.

---

## Adjudication - the lanes disagreed, and the disagreement matters

The information-design lane listed "owning agent / worktree" and "dispatch
timestamp" as NEEDS INSTRUMENTATION. The census lane refuted that by
reconstructing the entire 2026-07-30 fleet - all 8 agents, with type, worktree
branch, start time, elapsed and token spend - from files that already exist:

- `~/.claude/projects/C--LegionWallpaper/<session>/subagents/agent-<id>.meta.json`
  carries `agentType`, `worktreePath`, `worktreeBranch`, `description`,
  `toolUseId`, `spawnDepth`. Presence of `worktreePath` IS the
  worktree-agent-vs-verifier discriminator.
- `agent-<id>.jsonl` carries per-event `timestamp` and `message.usage` token
  counts. Its mtime separates running from finished - measured live at 4.6s,
  14.9s and 58.2s for three then-running lanes against ~176,000s for the
  2026-07-30 agents.
- `~/.claude/sessions/<pid>.json` maps a live pid to a session and a `cwd`, so
  LW sessions are filterable from the sibling projects.

**Ruling: the census wins on evidence - but it is available, not durable.** The
same lane found `~/.claude/settings.json` sets no `cleanupPeriodDays`, so agent
history is subject to Claude Code's default reaping with no warning, and the
transcript dir is already 596 MB.

**Synthesis neither lane proposed:** read the transcript dir LIVE for the
running view, and mirror the reaped-at-risk fields into `ops/runtime/` so the
historical view survives cleanup. Fleet visibility therefore ships in v1 with
no new writers; durability is a follow-on, not a blocker.

---

## Decision: separate service, on an extracted shared scaffold

`tools/lw_monitor.py` and this dashboard share zero domain. `build_pipeline_view`
is 187 lines of pipeline-schema tolerance that generalizes to nothing here, and
the thumbnail subsystem is dead weight for a run view. They also have different
lifecycles: the monitor is an operator-launched board expected to sit running
for hours, and editing it to iterate on a run view would restart the operator's
pipeline board.

But naive copy-paste duplicates ~130 lines of Python plumbing and ~120 lines of
CSS/JS, and that plumbing is where the fail-soft posture silently drifts - the
`Host`-header guard, the `_guarded` 500 wrapper, the `log_message` override that
keeps stdout empty under `pythonw`, and the bind-first single-instance guard are
each one line away from being wrong and invisible when wrong.

**Therefore, in order:**

1. Extract `tools/lw_httpd.py` - `LWServer`, `BaseLWHandler` (send helpers, host
   guard, guarded dispatch, logging override), `setup_logging`, the bind-first
   `serve_or_defer` seam, and `read_json_tolerant` (read a JSON path, on parse
   failure serve last-good with `stale` / `stale_since`). Point `lw_monitor` at
   it. The existing 530-line monitor suite is the regression net; this is a
   pure move-and-import that also splits routing from plumbing.
2. Build `tools/lw_rundash.py` + `web/rundash.html` on top.

The extraction is NOT optional. If it is rejected, extending `lw_monitor` is the
safer of the two remaining options - two divergent copies of the security
plumbing is a worse outcome than one crowded file.

**Port: 8900.** `lw_ports.next_free()` returns the block low, since only 8901 is
taken. (I said 8902 earlier in chat - wrong, and the registry is the authority.)
The module must live at `tools/lw_rundash.py` with a literal `DEFAULT_PORT` and
a hand-written pin in `tests/test_lw_ports.py`.

---

## Panels, ranked

### P1 - Run Ledger (BUILD FIRST)

**Answers:** is anything running, which agent owns which slice, which is stuck?

Header: run id, state chip (LIVE / DEAD / STOPPED / FINISHED), controller pid
with a CORROBORATED liveness verdict, age of the newest write across run-state
files, HEAD at run start vs now, commits ahead of origin, cycle N of cap, STOP
reason.

Board, one row per slice: id, title, file set, ladder status
(`pending / in_progress / verified / committed / failed`), **time in current
status**, commit sha, worktree path and branch, the owning agent with its type
and token spend, an evidence chip (P2), and a disjointness warning when two
non-committed slices name the same path.

Sources: `ops/runtime/slice_manifest.json` (atomic, crash-durable);
`git worktree list` + per-worktree `git status`; `ops/loop/control/*`; the
transcript dir per the adjudication above.

**Liveness must be corroborated, never read from the lock.** Measured
2026-08-01: `RUNNING.lock` named pid 8532 from a run that ended five days
earlier, and the OS had reissued that pid to an unrelated conhost. That defect
is fixed in `e63a50d` for the controller, and the dashboard must apply the same
rule - lock age against `slots.DEFAULT_STALE_AFTER`, corroborated by newest
write across `controller.log` / `cycle.txt` / `slice_manifest.json`, plus STOP
presence.

### P2 - Evidence Ledger

**Answers:** was that green claim backed by a run, or did somebody just say it?

Three states, never two: **VERIFIED / REFUTED / NOT OBSERVED**. Per row: claim
text, claimed counts, OBSERVED counts, observer (self / verifier / truth_gate),
timestamp, output file, exit code, ruff result, cited-files present-or-missing
with the exact missing path, CI conclusion for the merged sha, discrepancy lines
verbatim.

Two derived tripwires, both cheap, both aimed at LW's most documented failure
class:

- **Carry-forward detector** - a claimed count exactly equal to the previous
  observed count with no new observation for this sha.
- **Observation older than the commit it certifies** - not evidence. This is the
  stale-pipe replay case as a timestamp comparison.

Sources: `ops/loop/control/directive_history.jsonl` (exists; carries `tests`,
`regress`, `sha_before`, `sha_after`, `verdict` per cycle),
`ops/runtime/truth_gate_report.json`, `gh` for CI.

**Blank is a lie.** Before any instrumentation lands, every row renders amber
NOT OBSERVED. That is the truth, it is immediately useful, and the panel
indicting itself is the strongest available argument for the instrumentation
that upgrades it.

### P3 - Resume Decision

**Answers:** it died - resume or restart, and is any work stranded?

Non-committed slices; per worktree path, branch, ahead/behind, dirty file list;
orphan worktrees no slice claims; unpushed commits; STOP reason; last 5 lines of
`controller.log` pinned ONLY when state is DEAD. Computed verdict: RESUME SAFE
vs SALVAGE FIRST.

Sources: all existing. Zero instrumentation. On 2026-07-29 a session limit
killed five agents at once; one agent's uncommitted files were salvaged from its
worktree and one slice's work was lost. The difference was somebody knowing to
look. Best value per line on the list.

### P4 - Operator Queue - BUILT 2026-08-01 (`/api/queue`)

**Answers:** what is waiting on ME, and for how long?

Two columns. *Blocked on you:* NEEDAUTH slugs with gate verdict and flag reason
(17 today), HELD slugs with reason (3 today on `aspect_crop_heavy`),
OPERATOR-GATED roadmap items with their `Next:` line, age of each. Plus one
run-attributed line: **"this run added N to your queue, M flagged, all M on the
same reason"**. *Blocked on the machine:* slices in progress, cycles remaining.

The ROADMAP half is a prose grep on `OPERATOR-GATED` - it works today and will
rot. Label it as fragile on the panel rather than pretending it is structured.

**As built.** 29 NEEDAUTH slugs live, oldest first because AGE is the question;
capped at 25 rows with the full count and the cap STATED, never silently
truncated. HELD is not built: no HELD substate exists in `pipeline_state.json`
on this machine, and inventing a source for it would have been worse than the
gap. The run-attributed line ("this run added N") is likewise NOT built - no
source attributes an image to a run - and the clustering pointer that survives
the rejected gate-flag census IS built: one stage holding the whole queue reads
structural, scattered reads as quality. The ROADMAP grep resolves a marker on a
WRAPPED line back to the bullet above it (3 of the 6 live items wrap), which is
the difference between the id `m1-gate-fund-or-close` and the useless fragment
`OPERATOR-GATED on product direction`.

### P5 - Suite Trajectory - BUILT 2026-08-01 (`/api/trajectory`)

Observed passed / failed / skipped by sha, delta per commit, source of each
datapoint, and **commits with no datapoint rendered as gaps, never
interpolated**. A count that drops is deleted tests or a collection error; a
commit with no datapoint is the unbacked-green failure at repo scale.
Interpolating would manufacture the false continuity this project keeps getting
burned by. Shares a data spine with P2.

**As built.** Datapoints are harvested from two producers - the controller's
resolved-cycle chain (`tests` against `sha_after`) and the per-slice verdict
counts item 3 now persists - and a count with NO commit is dropped rather than
kept with a blank sha, since a number that certifies no commit is unbacked green
in its purest form. Sha widths differ by producer (8 / 7 / 40) and are matched at
the shorter width. First live render, 30 commits: 5 observed, 25 gaps, and every
observed row reads `chain broken` because no two observations are adjacent. That
is the panel working, and it is the most honest picture of this repo's evidence
coverage that has ever been on a screen.

---

### P6 - Fleet History - BUILT 2026-08-01 (`/api/fleet`)

**Not in the original ranking.** It exists because item 6 made the fleet durable
and then nothing read it: 136 agents across 35 sessions sat in
`ops/runtime/agent_fleet_mirror.json` with no consumer.

**Answers two things the live fleet view cannot.** *Where the tokens went* -
per-session output spend, newest first, so an expensive run reads as one row
rather than twenty agent rows (3,439,867 output tokens total on first render).
*What is already lost* - every session is labelled by whether its source
transcripts still exist. `mirror only` means reaping has been and gone and this
file is the only remaining copy, which is the single fact that says whether the
mirror is earning its keep or quietly failing to run. Reaping is per-FILE, so
the half-reaped case reports `N of M on disk` rather than collapsing to a
boolean. First live render: all 136 still on disk, so the mirror is currently
ahead of the reaper - the good case, and it is stated as such rather than left
as a blank.

**Rules inherited rather than re-argued.** A session whose agents carry no
timestamps has span `None`, rendered unknown - zero would read as "ran
instantly" (P5's rule). A session is labelled with a controller run ONLY when
`join.by_session_id` pairs them; today no cycle record on this machine carries a
session id, so every row renders `unjoined`, which is the truth and makes the
remaining half of the join visible. 20 of 35 sessions render and the header says
so (no silent caps). Each row names its top 3 spenders with the full count
beside them - 136 agents were never the unit of the question.

## Rejected, with reasons

**Gate flag census ("7 of 17").** `docs/USM_HALO_CENSUS_2026-07-30.md`
established that `halo_pct` is monotone in USM percent on every slug - it reads
as a strength dial, not a defect detector, and the 0.05 line cuts a continuum
with no gap at it. Putting that number on a dashboard implies a target, a target
invites tuning, and tuning on one axis is the exact mistake `usm-halo-calibration`
is gated against. The run-relevant residue is ONE line inside P4: whether the
flags cluster on a single reason. Single reason means structural, look at the
pipeline; scattered means quality, look at the images.

**Cost / budget panel.** One header field only (`gemini_usd` vs ceiling, 0.48 of
200). LEDGER 40 settles that there is no Claude dollar accounting - on a Max plan
`total_cost_usd` is notional and the old meter billed the wrong session. Present
token counts, never dollars.

**Live log tail as its own panel.** Only inside P3, only when DEAD.

**Per-agent percent-complete.** No durable source, and no action follows.

---

## Instrumentation backlog (v1 does NOT block on any of it)

1. **A REFUTED state on the slice ladder.** Today a refuted slice is set back to
   `in_progress` and the refutation leaves no trace - the one REFUTE on
   2026-07-30 exists only as prose in LEDGER 61. Highest-value single addition.
2. **Persisted verifier verdicts.** Currently chat-only.
3. ~~**Per-slice suite observations** as append-only events - the datum the whole
   evidence ledger is made of.~~ DONE 2026-08-01. `truth_gate.py` now appends one
   `observer: truth_gate` record per reconciled slice to the manifest verdict
   history, carrying the OBSERVED counts. A global refusal (red suite, CI
   failure) quarantines no individual slice, so it is carried down onto every
   row prefixed `global:` - otherwise a slice reconciled during a red suite
   renders as "checked, and fine". `--skip-suite` records `counts: null`, never
   zeros. The record shape has ONE owner
   (`slice_orchestrator.build_verdict_record`); truth_gate does not hand-roll it.
4. ~~**Cost and session id into `directive_history.jsonl`.**~~ DONE 2026-08-01
   (LEDGER 65). `record_directive_outcome` now takes the `DoneRecord` alongside
   `done` (which stays `rec.raw`, carried through untouched because the director
   prompt is built from it) and writes `cost_usd` + `session_id`.
5. ~~**One authoritative run id.**~~ DONE 2026-08-01 (LEDGER 65) for
   `directive_history.jsonl`: records now carry the controller `run_id`, and the
   reader segments on it when present. The cycle-number heuristic survives as
   the fallback for records already on disk, which can never gain an id
   retroactively; `run_id_backed` is False unless EVERY record has one, so a
   half-instrumented file never renders as authoritative.
   The harder half - mapping the three id spaces to each other - is DONE too,
   2026-08-01. Cycle records now carry `manifest_run_id` beside the controller
   `run_id` and `session_id`, so one record pairs all three namespaces at once;
   `build_run_id_join` gathers them and `resolve_run_identity` names a run across
   all three or says plainly that it cannot. The pairing is EVIDENCE ONLY - two
   ids sitting side by side, matching dates, being the only run that day are not
   a join, and the header renders `=` only when a record carried both, `/` plus
   an amber `unjoined` tag otherwise. Records predating the field are counted in
   `unjoined_cycles`, never bucketed under a neighbouring run, and a caller whose
   two ids disagree with the recorded pairing gets `conflict` with BOTH reported
   rather than a picked winner.
6. ~~**Mirror at-risk agent metadata into `ops/runtime/`** before Claude Code's
   cleanup reaps it.~~ DONE 2026-08-01. `tools/lw_agent_mirror.py` folds every
   session's fleet into `ops/runtime/agent_fleet_mirror.json`; first run captured
   136 agents across 36 sessions back to 2026-07-03, including all 18 of the
   2026-07-30 fleet this spec exists for. A separate tool rather than a hook in
   the dashboard, invoked once per cycle by the controller, because the reaping
   window is exactly the window in which nobody has the board open. Counts move
   ONE WAY - a poll that catches a truncated transcript is information lost, not
   news - and no volatile verdict is stored, since a mirrored `running: true`
   from four days ago paints a live agent that does not exist. The board unions
   mirrored rows scoped to the resolved session and STATES the full mirror total
   rather than dropping it silently.
7. **`truth_gate.py` is never invoked by the run flow** - its report has never
   been written on this machine. The atomic writer already exists; only the call
   is missing.

## Adjacent findings, handed on

- `ops/runtime/health.json` is cited by `CLAUDE.md` and by `.claude/agents/verifier.md`
  as the live-state probe and DOES NOT EXIST. Nothing writes it. Do not hang any
  panel on it.
- `logs/lw_monitor.log` is 3.9 MB and unrotated despite `.gitignore` describing a
  daily-rotation convention; `controller.log` and `PIPELINE_LOG.md` are also
  unrotated.
- Non-atomic and torn-read-prone, must be parsed per line with a failing tail
  line discarded: `controller.log`, `directive_history.jsonl`, `PIPELINE_LOG.md`,
  `logs/*.log`, and every subagent `.jsonl`. Atomic and safe to poll:
  `slice_manifest.json`, everything in `ops/loop/control/` written via `awrite`,
  `pipeline_state.json`, `truth_gate_report.json`.

## Inherited constraints (non-negotiable)

Stdlib only, no framework, no build step. Atomic writes. `CREATE_NO_WINDOW` on
every subprocess - enforced by `tools/lw_window_guard.py` and by
`tests/test_no_console_flash.py`, which resolves AST values so a typo'd constant
fails. 7-bit ASCII in all authored text including CSS and JS. Read-only over run
state - `slice_orchestrator.py`, `truth_gate.py` and `loop_controller.py` own
their files. `pythonw` launch means no stdout ever. Never surface a raw error
string in the UI. The UI fixture ritual runs before commit. TDD first. Tests bind
port 0 and inject every path, so they cannot collide with a live instance.
