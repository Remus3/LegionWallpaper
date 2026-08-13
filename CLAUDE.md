# Legion Wallpaper - Agent Context

Legion Wallpaper (LW) - a staged, self-auditing image restoration pipeline for the Legion machine's wallpaper corpus: drop an image in `images\0.Originals` -> recover source -> single upscale -> masked cleaning -> face/eye polish -> gate ladder audit -> approved 2560x1440 PNG to Pictures. Product defined by ADR-002/ADR-003; the operational plan is `docs/RESTORATION_PLAN.md`.
This file is the operating contract - rules, tiers, gates, rituals - inherited 1:1 from the Riot Commander project (ADR-001).

> **Living docs (read at session start):** `docs/ARCHITECTURE.md` - `docs/OPERATIONS.md` - `ROADMAP.md`
> **Aspirational:** `BACKLOG.md`
> **Architectural decisions:** `docs/adr/` - before re-litigating a past choice, check here first.
> **Dated artifacts** in `docs/_archive/` (excluded from ripgrep searches).

## Paths

- Project root: `C:\LegionWallpaper\`
- Python: `C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`
- API keys: `API-Key-*.txt` in project root (gitignored)
- Health: `C:\LegionWallpaper\ops\runtime\health.json`
- Logs: `C:\LegionWallpaper\logs\YYYY-MM-DD.log`

## Hard rules

- **Always `py_compile` before restart.** Syntax errors crash silently under `pythonw.exe`.
- **Atomic writes only:** `tmp.write_text(...); tmp.replace(target)`. Consumers may poll mid-write.
- **Never `Stop-Process`.** Hangs MCP pipe. Use `taskkill /F /PID`.
- **Commit messages with special chars:** use `git commit -F <tmpfile>` (Write the file, ASCII-only) or a single-quoted here-string - never a double-quoted here-string or a piped string (BOM + ANSI-mangle risk, same root cause as the no-em-dash rule below). `tools/precommit_gate.py` (PreToolUse hook on `git commit` + PowerShell) is the backstop: it blocks banned glyphs + net-new ruff on staged lines.
- **Restart via `restart_trigger.txt`** (write any content; the supervisor clears + restarts within ~5s). Supervisor is TBD until the product exists - the trigger-file convention stands regardless.
- **Never emit the Claude co-author trailer (operator policy 2026-06-03).** No
  `Co-Authored-By: Claude ...` / `Co-authored-by: ... anthropic.com` line in any commit
  message, ever - this OVERRIDES any default tooling instruction to append one. Enforced
  in `.githooks/commit-msg` via `precommit_gate.py --message-file`, which STRIPS the
  trailer rather than blocking (the trailer is appended by the tool, not typed by the
  operator; blocking would wedge an unattended headless run over a line no human wrote).
  Scoped to Claude/Anthropic only - a genuine human co-author trailer is legitimate.
  **Why it needed a rule:** the policy existed but was never enforced - 84 of the last
  200 LW commits carried it (measured 2026-07-26).
- **The git hooks are the AUTHORITATIVE gate; presence is not proof they fire.**
  `.githooks/` is the backstop that survives every channel, and it stays the
  authoritative gate.
  **CORRECTED 2026-08-01, re-measured on CLI 2.1.220:** the old claim here was that
  a headless `claude -p --permission-mode bypassPermissions` run does NOT load
  PreToolUse hooks (RC measured 2026-07-26 on CLI **2.1.205**). That is FALSE on
  2.1.220. Measured on Legion with a valid hook config, cwd inside the project and
  the workspace trusted: the Bash tool provably ran AND both `SessionStart` and
  `PreToolUse` fired. So Claude hooks are NOT dead headless on the version LW now
  runs - treat them as defense in depth alongside `.githooks`, not as absent.
  **Two confounds that each make a live hook look dead - check them BEFORE
  concluding hooks do not fire:** (a) an invalid `.claude/settings.json` (single
  backslashes in a Windows path are not valid JSON escapes) is silently unparsed,
  which produced a false "hooks do not fire" in the first two arms of this very
  probe; (b) an untrusted workspace makes headless DISCARD `permissions.allow`,
  and `~/.claude.json` keys are path-separator- and case-sensitive - LW carried
  THREE keys for one directory, the forward-slash one reading False, so headless
  silently dropped permissions until it was fixed 2026-08-01.
  Two false-green traps, both hit on 2026-07-26: (1) `core.hooksPath`
  points at the tracked `.githooks`, so ANY hook written into `.git/hooks` is dead;
  (2) `.githooks/pre-commit` invoked `precommit_gate.py` with no args from 2026-07-03,
  and with no args the gate self-gates to a silent no-op - it ran on every commit and
  gated nothing. Verify with `python tools/install_git_hooks.py --check` (wired into
  `tools/drift_guard.py`, every session), never by looking at whether a hook file exists.
- **State assumptions explicitly before coding.**
- **No em-dashes or en-dashes - ever (7-bit ASCII authored content).** Hard rule in *all* authored text: code, comments, docstrings, `.md`, writeups, commit messages, WAKEUP/ROADMAP/CLAUDE, chat output. Use ` - ` (spaced hyphen) for a clause break, `-` otherwise. Also avoid smart quotes (U+201C U+201D U+2018 U+2019) and en/em dashes (U+2013 U+2014); stay ASCII. **Why:** Windows PowerShell 5.1 `ParseFile` ANSI-decodes a no-BOM `.ps1`, turning a UTF-8 em-dash inside a double-quoted string into a U+201D smart-quote that the tokenizer treats as a string terminator -> cascading parse failure (2026-05-18 boot-script incident, inherited from RC); also a standing operator style rule. LW starts ASCII-clean - keep it that way; a strip-em-dashes style sweep tool (RC pattern: `tools/strip_em_dashes.py`) is reusable for drift checks. **Standing sweep exclusions** (immutable history / non-source): `*.log` + rotated `*.log.N`, `docs/_archive/**` + dated artifacts, `.jsonl` ledgers, binaries, `.pyc`/`.git`.
- **Frozen files** (do not modify without explicit user approval):
  none yet - files get frozen as core stabilizes; requires explicit operator approval to modify once listed.

## Restart workflow

```
echo restart > restart_trigger.txt
```
Verify: read `ops/runtime/health.json`, confirm new `pid`, `alive=true`, `last_reload_ok=true`.
Hard fallback: `taskkill /F /PID <pid>` then the restart script.
(Supervisor + restart script are TBD until the product exists; this workflow is the contract they must satisfy.)

## Session workflow

Scoped sessions - each focused task is one session.
- **End:** commit + update `WAKEUP_NOTES.md` (keep last 2-3 sessions at full fidelity; archive older to `docs/history_notes.md`) + push.
- **Start:** `/clear`, bootstrap from CLAUDE.md + MEMORY.md + git log + WAKEUP_NOTES + `docs/ARCHITECTURE.md` + `ROADMAP.md`.
- `/clear` between Tier items, between coding/reviewing modes, between focus-area switches.

## Session-End Ritual

When user says 'wrap', '/done', or 'end session': run tests, commit with descriptive message, push, sync living docs (append the per-item ledger entry to `docs/LEDGER.md`, NOT CLAUDE.md), and confirm CI green before declaring done.

## Output Constraints

Keep individual responses under 500 output tokens to avoid API errors. Break long work into multiple turns or use file writes for verbose output.

## Style Rules

- No em-dashes anywhere (repo-wide hard rule, enforced).
- Watch for em-dashes in PowerShell double-quoted strings - they cause mojibake parse failures.

## Execution Efficiency & Tooling Rules

Operator-agreed (inherited from RC, 2026-06-13) to cut per-edit + audit wall-clock. Default to fast, direct, text-based tools; scale verification to blast radius. SCOPES "Testing Discipline" + "Verification Discipline" below (those apply at Tier-2). Memory: `feedback_execution_efficiency_rules`.

Text-first (R1-R4) - never default to visual / computer-use for text, code, or state:
- **R1** Files = Read / Edit / Write / Grep / Glob ONLY. NEVER computer-use / Windows-MCP to read or change a file.
- **R2** Runtime / dashboard state via the project health endpoint or Read `ops/runtime/health.json` (endpoints TBD). NEVER screenshot to read a number, version, or STATE.
- **R3** Visual tools (screenshot / computer-use / Windows-MCP / preview / capture_monitor) ONLY for rendered-pixel / CSS / layout checks with no text equivalent. The UI-audit ritual is the sanctioned visual use (`feedback_screenshot_after_ui_changes`).
- **R4** Prefer built-in tools over Bash / PowerShell. When shell is needed: absolute paths (no `cd`), one compound command over many round-trips.

Tiered verification (R5-R7) - Tier-0/1 do NOT pay the Tier-2 tax (operator-accepted tradeoff):
- **Tier-0** cosmetic (doc / comment / string / non-runtime constant): Edit + `py_compile` if .py. No suite, no restart.
- **Tier-1** local logic (one module): `py_compile` + that module's tests only.
- **Tier-2** schema / engine / core-contract change (product-specific triggers TBD - when in doubt, classify up): full suite (`tests/`) + service restart.
- **R5** Classify every change into a tier; run only that tier's verification.
- **R6** Run the relevant suite ONCE; trust exit code + result file. Re-run only if I edited since, or the pipe demonstrably glitched - not prophylactically.
- **R7** `verifier` subagent ONLY for parallel-slice / subagent claims or a real stale-pipe event - not my own single-thread edits.

Overhead (R8-R11):
- **R8** Never re-Read a file I just Edited to confirm (Edit fails loudly).
- **R9** No subagents / worktrees under ~3 files. Inline.
- **R10** Batch independent reads / greps in one message.
- **R11** Skip the screenshot ritual for backend / version / doc changes (scoped to UI visual changes).

Enforcement (hooks in `.claude/settings.json`): PostToolUse `tools/pytest_guard.py` is py_compile-only by default (no auto full-suite per edit); `LW_FULL_SUITE=1` restores auto-suite for a Tier-2 batch. PreToolUse `tools/text_first_guard.py` denies pure screen-text/state readers (Windows-MCP Scrape, computer-use read_clipboard) with a text-path pointer; escape hatch `ops/runtime/allow_visual.flag`.

## Scheduled tasks (Legion)

Naming convention: `LW-*` (e.g. `LW-Supervisor`). Registered: `LW-Wallpaper` (desktop deck rotator, 2026-07-18), `LW-WeeklyHygiene` (Sunday 04:17, 2026-08-02) and `LW-CIWatchdog` (boot + PT2M, 2026-08-02; kill switch `ops\runtime\ci_watchdog\HALT`). `LW-GeminiAudit` is retired; `LW-Supervisor` is blocked on a missing script. Full list + registration commands live in `docs/OPERATIONS.md`.

## Where to find current state

- Live PID + health: `ops/runtime/health.json`
- Recent activity: `logs/YYYY-MM-DD.log`
- Architecture / module map: `docs/ARCHITECTURE.md`
- Ops commands + restart: `docs/OPERATIONS.md`
- Open work: `ROADMAP.md` - Aspirational: `BACKLOG.md` - History: `docs/history_notes.md`

## Useful commands

Full reference: `docs/OPERATIONS.md`. Quick-start:
```
python -c "import json; print(json.dumps(json.loads(open(r'ops/runtime/health.json').read()), indent=2))"
echo restart > restart_trigger.txt
```
(Product-specific health/API probes TBD - add them here + `docs/OPERATIONS.md` when endpoints exist.)

## TDD First

All feature work and bug fixes follow TDD: write failing characterization/regression test first, then implement, then verify the full suite before committing.

## Subagent Code Quality

When spawning subagents to generate files (especially tests), require them to run ruff/lint before reporting done. Subagent-generated test files have broken CI in the past.

## Subagent-First Protocol

Standing operator directive (inherited from RC, 2026-06-20): ALWAYS use subagents for substantive design / build / research work - do not build solo in the main thread. Refines R9 (truly trivial one-line cosmetic edits may still inline).
- **Spec first, then act:** a Plan/design subagent (or the Gemini director) emits the spec/plan BEFORE any code; verify it against ground truth (grep cited file:line, live health state via `ops/runtime/health.json`, git) - never scaffold on assumptions.
- **New session:** interview the Gemini director (or the operator if Gemini is down) for intent + acceptance criteria, re-probe live state, THEN build. Verify before building.
- **Act via subagents:** worktree-isolated build agents on disjoint files (sole merger) + a read-only `verifier` subagent gate before any merge or "done" claim.
- Every `.claude/commands/*.md` carries the SUBAGENT-FIRST block (tracked in git - unlike RC, this repo tracks `.claude/`; only `settings.local.json`, `local/`, and `worktrees/` stay local). See memory `feedback-subagent-first`.

## Testing Discipline

Always run the full test suite after schema changes or core-contract version bumps. Avoid data-fragile cross-item comparison assertions; prefer assertions on computed quantities. When stubbing methods accessed via class, wrap with `@staticmethod` correctly. Before writing any probe or test, grep the codebase to confirm every method, field, and data shape it will use actually exists - cite file:line for each; never scaffold against an assumed API surface. **Tier scope (R5):** "full suite" = Tier-2 (schema / engine / core-contract); Tier-0 cosmetic + Tier-1 local-logic edits are exempt - see "Execution Efficiency & Tooling Rules".

## Error Handling

Never surface raw API error strings (credit/balance exhaustion, 400, rate-limit, thinking-block) in any user-facing UI or panel. Catch and render a friendly degraded-mode message (e.g. "paused - retrying") and log the raw error to `logs/`. Applies to every user-facing surface.

## Verification

Before asserting external state - API key validity, account IDs, process/PID metrics, "X is dead/missing/broken" - verify it live against the source of truth; never rely on a stale doc or another agent's unverified output. Re-probe first, then assert. See memories `feedback_verify_generated_reports` / `feedback_verify_before_declare_broken` / `feedback_audit_proposals_are_intent`.

## Verification Discipline

Re-verify against ground truth before claiming any task green; the tool pipe can replay stale or out-of-order results (a past RC session hit severe stale-tool-result replay - a fabricated "1 failed", a non-existent value, a pre-bump health read, invented filenames). Ground truth when the pipe wedges = `git status` + Edit success/fail + pytest written to a file + a DONE-exit sentinel, NOT raw stdout. Before reporting complete: re-run the relevant suite fresh, confirm every cited test file actually exists on disk (`ls` it), and report the exact pass/fail counts you observed THIS run - never carry a prior or subagent-reported count forward. NEVER trust a subagent's claim about test counts, green CI, or file existence without an independent probe; subagents have cited non-existent test files and used broken commands (wmic, pre-restart cumulative measurements). The `verifier` subagent (`.claude/agents/verifier.md`) exists for exactly this re-check. See `feedback_verify_generated_reports` / `feedback_verify_before_declare_broken`. **Tier scope (R6-R7):** this re-verify-fresh + verifier mandate applies at Tier-2; Tier-0/1 follow tiered verification (run once, trust exit code unless edited-since or the pipe glitched) - see "Execution Efficiency & Tooling Rules".

## UI Fixture Ritual

Any UI page change runs the visual-hierarchy / fixture audit subagent BEFORE the commit + push, not after. Do not commit a page until the 5-phase audit (STRUCTURE / TYPOGRAPHY / HIT-TARGETS / ASCII / HIERARCHY) completes and every MUST-FIX is resolved in the same slice. Shipping a page ahead of its audit was a process miss the operator called out explicitly in RC. See `feedback_phase3_fixture_ritual`.

## Python Conventions

When adding a required field to a dataclass, append it at the END with a default; do not insert mid-class. A mid-class required field breaks every existing positional construction + test (an RC item inserted a field mid-class and broke 41 manual constructions; the fix was to default it at the end).

## Data Fixes

A data-corruption or pollution fix is not done until already-corrupted rows are backfilled + recovered, not just future occurrences prevented. A race-condition guard that only stops future races leaves the existing bad rows wrong (an RC item needed two extra backfill + recovery rounds AFTER the guard landed). Plan the recovery pass in the SAME fix and verify the historical rows are corrected live.

## Feature / Engine Conventions

Root-cause-first: fix the cause, not the symptom (see the `root-cause-fix` skill). Case-specific fixes are validated per case, not with one generic shape; expect to patch multiple sibling cases. A narrow first fix that misses siblings forces a second comprehensive cleanup. Before shipping any fix in a family of similar cases: grep for sibling cases (other variants, other modes, duplicate code paths) and add a test covering each. When narrowing a matching/fold rule: start with the tightest matching set and add a test asserting unrelated types are excluded BEFORE widening; widen only on test evidence (an RC fold over-counted on its first pass and took two narrowing iterations).

## Windows Environment Notes

Claude Desktop on Windows may be installed via the Microsoft Store (check `%LOCALAPPDATA%\Packages`) in addition to standard install paths. Use `pythonw.exe` (not `python.exe`) for background daemons to avoid flashing console windows.

## Session Wrap-up

When invoked with `/done` or asked to wrap a session: (1) audit pending changes, (2) commit and push, (3) update ROADMAP/README + append the per-item completion entry to `docs/LEDGER.md` (NEVER to CLAUDE.md; it is CI size-budgeted < 60KB - touch CLAUDE.md only for rule/frozen-list/Settled changes), (4) process lessons/WAKEUP_NOTES, (5) print final banner. Run independent steps in parallel.

## Active priorities

Per-item completion ledger lives in `docs/LEDGER.md` (append-only, newest-first, starting at item 1) to keep CLAUDE.md out of the per-turn auto-load budget. CLAUDE.md is CI size-budgeted (< 60KB) - NEVER append item-ledger entries here; append them to `docs/LEDGER.md`.

- Open work + NEXT: `ROADMAP.md` + `BACKLOG.md`
- Recent session fidelity (last 2-3): `WAKEUP_NOTES.md`
- Per-item completion ledger (item 1 and newer): `docs/LEDGER.md`
- Deep archive (pruned wakeups + relocated settled items): `docs/history_notes.md`

### Settled - do not re-litigate

Settled decisions accumulate here as one-line entries; long-tail entries relocate verbatim to `docs/history_notes.md` when this section grows. Read the archive for full context before re-opening any line below.

- **LW inherits the Riot Commander operating system 1:1 (ADR-001):** rules, tiers, gates, rituals, TDD, verification, subagent delegation, memory conventions. Process questions are settled by this file + `docs/adr/`; only product questions are open.
- **The repo is PUBLIC under Apache-2.0 since 2026-08-01 (LEDGER 88) - do not re-litigate.** Every push is world-readable: never track image bytes (`images/**`, root style refs and `data/recovery/fetched/` are gitignored for this reason), never commit a key, and treat any new tracked binary as a release decision. The license covers the PROCESS only - it neither does nor can grant rights to the third-party corpus. History was rewritten to purge two stray jpgs, so shas before `4e3b617` that predate the rewrite may not resolve; the map is `docs/_archive/2026-08-01-sha-rewrite-map.md`. A force-push does NOT purge GitHub-side unreachable objects - delete-and-recreate or a Support request is the only real purge.
- **Pipeline folder scheme is operator-designed, settled by ADR-003 - do not re-litigate** (10 stage folders under `images\`, 4-phase tokens, slug grammar, GC + End Review rulings).
- **Primary first-pass upscaler = IllustrationJaNai V3 detail DAT2 (ADR-004, 2026-07-05) - do not re-litigate.** Promoted from V1 DAT2 on a golden A/B sweep (V3 wins MS-SSIM/LPIPS/halo, clears all halo flags); golden re-frozen at n=12 on V3 (pv 6d43a6d4); G1 thresholds unchanged. V1 DAT2 = spandrel-confirmed fallback; V3denoise = per-image halftone alternative.
- **Artist signatures are REMOVED, not kept (ADR-005, 2026-07-05) - do not re-litigate.** Inpainted out at the cleaning scratch stage via the standard detect -> mask -> inpaint -> verify path (gate + QA fallback); not routed to a keep-queue. Justified only by the private-use / process-is-the-deliverable boundary (RESTORATION_PLAN section 10).
- **Loop executor channel = headless `claude -p` (`channel: sdk`), phase-6 deletions HELD (LEDGER 40, 2026-07-26) - do not re-litigate.** The AHK GUI bridge was a machine-wide singleton keyed on a window title and was the sole reason two loops could not run at once; LW+RC now run CONCURRENTLY, proven by a 4-condition acceptance run. Rollback is ONE config key. `done_sentinel.py`, `meter()`, `claude_gui_bridge.ahk` and `claude_window_title` all STAY until the operator lifts the hold. NO Claude dollar cap or accounting: on a Max plan `total_cost_usd` is notional API-equivalent pricing, and `meter()` bills the wrong session entirely. Gemini's `ceiling_usd` is unaffected - that vendor is genuinely metered. Shared files `ops/loop/slots.py` + `ops/loop/winmutex.py` are BYTE-IDENTICAL-by-contract with RC; changing either needs a re-sync, and LW's suite is the only coverage they have on either side.
- **Canonical splash art comes from the LoL wiki's Action API DIRECTLY, not from a MediaWiki MCP server (LEDGER 72, 2026-08-01) - do not re-litigate.** Both candidate servers wrap the same anonymous API, which answers in ~40 lines of stdlib `urllib` - the transport `lw_recover.py` already uses - so neither wrapper buys a capability. Prefer wiki.gg; Fandom serves a lossy WEBP transcode under a `.jpg` name unless `?format=original`. No host serves bytes matching the API-declared sha1, so provenance records the sha256 of what was FETCHED. Detail + the corpus intersection in `docs/MCP_LIFT_P3_2026-08-01.md` + `docs/WIKI_VS_FIRSTINITIAL_2026-08-01.md`.
- **`USM_DEFAULT` = `(1.2, 35, 3)` since 2026-08-02 (was percent 70) - do not re-litigate on halo evidence alone.** Measured over all 17 gated batch20 slugs at 70/50/35/none WITH fidelity per variant (`docs/USM_FIDELITY_CENSUS_2026-08-02.md`): halo flags 7/17 -> 0/17, worst gated `lap_ratio` 1.1399 (floor 1.0), and every fidelity metric IMPROVES as the mask weakens - the mask was costing fidelity, not buying it. The 0.05 halo threshold was deliberately NOT moved. Do not drop the mask entirely (6 of 16 gated slugs fall through the `lap_ratio` floor) and do not read the synthetic step-edge fixture as evidence about mask strength (it saturates).
- **A vision reviewer may FLAG, never REJECT; the flag blocks a NON-operator approval (ADR-008, 2026-08-02) - do not re-litigate.** `clamp_vision_audit()` coerces a vision audit's REJECT/FAIL to FLAG at the ANNOTATE write boundary; `assert_approval_allowed()` refuses a non-operator approval (exit 3) while an `anat_`-prefixed flag is open; `approve --actor` defaults to `operator` and the operator is never refused. Reasons: a REJECT demotes and a further pass measurably DEGRADES (`clean-retry-degrades`); a vision 2AFC is not reproducible; splash art has no anatomical ground truth. Revisit REJECT only at >= 50 shadow-window reviews.
- **G1 FR common-scale pixel budget = 3840x2160 (ADR-007, 2026-08-02) - do not re-litigate.** It caps the SOURCE-vs-OUTPUT COMPARISON scale, NOT the 2560x1440 deliverable (sources run to 6500x3660; FR metrics compare at source scale because upscaling the reference manufactures a blurry one). Below the proven ceiling 4096x2306, on the scale 26 corpus images already use natively; recovers DISTS for the 63 of 230 images that had silently lost it. Native-8K DISTS is measured impossible on this box. Pinned by `tests/test_g1_common_scale_budget.py` - moving it needs a new ADR.
- **Lint/CI toolchain pins, settled 2026-08-02 (LEDGER 89) - do not re-litigate.** Repo is `Remus3/LegionWallpaper` (renamed; the old name is claimable, so the redirect is not a boundary). CI and Legion both run **Python 3.14**; ruff `target-version` = the MINIMUM supported version = the CI pin, so it must NEVER be raised above it. `exclude` in `ruff.toml` MUST stay top-level - under `[lint]` it is silently INERT (measured, ruff 0.15.12), which is how vendored `tools/dwpose_onnx` was being linted for months. `cv-lane` runs the cv2/skimage tests in CI off `requirements-cv.txt` with a junit guard that fails the job if they silently skip.
- **Cleaning runs ONE engine per submission; the cross-engine ladder is never automatic (ADR-009, 2026-08-12) - do not re-litigate.** Measured over the whole cleaning stage (21 slugs / 50 rejected workings / 24 scored retries): a second engine won 0 of the 3 adjudicated slugs, sdxl-animagine lost seam to lama in 14/15, and iopaint's 6-of-9 seam wins are bought by repainting 2.66x the area (all 9 rejected). No measured-improvement gate is possible - seam gain tracks edit area (r=+0.46), so gating on it selects for the biggest repaint. `lw_pipeline save-working` refuses a second engine (exit 3) unless `--allow-ladder`; `operator-select` and friends are exempt so the operator is never refused. Engines are KEPT, just not chained. Evidence: `docs/CLEAN_LADDER_DECISION_2026-08-12.md`, LEDGER 105.
- **`overlay_score` is a DETECTION flag and NEVER a removal-QUALITY gate (2026-08-12, LEDGER 101-103) - do not re-litigate.** It was calibrated on untouched frames; the algebraic pre-pass drives it to 0.076 while keeping **103 percent** of the credit line's local stroke contrast, so a frame can sit deep inside the clean distribution and still show its artist credit line at 1:1. A candidate ship gate needs a legibility measure. Same family of rulings: the centre-overlay veil correction is FEATHERED (`VEIL_FEATHER` 16px) and its boundary is never inpainted - the old LaMa ring existed only to hide a 12.7-27.4 level cliff the hard-edged correction created itself; and the veil amplitude's ring-pair estimator is sound (proven by a clean-frame control) but has SNR ~1, so do not re-open it on a single frame set - it moves 40 percent when the set changes.
- **M1 weapon-pass localizer = DWPose onnx-CPU (LEDGER 19, 2026-07-11, commit 7e21c9d) - do not re-litigate.** Adopted at 5/6 wrist-on-weapon vs OpenPose 1/6 on the recall_gate samples. SDPose-Wholebody REJECTED: it hard-imports mmpose + pins mmcv==2.2.0 (the Blackwell / torch-2.11 wall) + torch 2.8 / transformers 4.57 / xformers; do NOT retry. Reusable: tools/lw_gen_localizer_eval.py (dwpose_backend + cocowb_to_kp_map) + tools/dwpose_onnx/ (vendored, no mmcv); models gitignored (tools/models/dwpose, fashn-ai HF mirror).

Full open work + future: `ROADMAP.md` + `BACKLOG.md`. Per-item ledger: `docs/LEDGER.md`. Deep archive: `docs/history_notes.md`.
