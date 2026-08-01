# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01) - keep the last 3.

---

## 2026-08-01 (latest) - P7: the claim table finally REFUSES something; P8 closed on fit

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

NEXT: **L2's retrospective half** - `tools/claimed_green_gate.py` reads a Stop-hook
payload from stdin and has no CLI and no history mode, so the question the triage
posed (retroactively, how often was a green claim in this repo unbacked?) is still
untouched. Lift red-handed's detector design, do NOT install it. Also open:
`wiki-swap-manifest-hash-residue` (scan --verify HASH_MISMATCH on 21 of 22,
bookkeeping only; plain scan is clean). Loose end unchanged: two stale worktrees
still registered - check for unmerged work before removing.

---

## 2026-08-01 (earlier) - P3/P4/P5 shipped, the wiki turned out to hold real pixels, and 22 sources got swapped

Nine commits `1eaa135`..`6d7efc2`. Suite **1624 passed / 16 skipped**, ruff clean,
drift_guard 0 breaches, CI **green on 6d7efc2 verified with `gh`**.

- **P3 (LEDGER 72):** a MediaWiki wiki serves LW canonical splash art anonymously
  - but the probe ran against the Action API DIRECTLY, which is what both
  candidate MCP servers wrap. **Adopt the source, decline both wrappers.** Fandom
  serves a lossy WEBP transcode under a `.jpg` name unless `?format=original`;
  prefer wiki.gg. No host serves bytes matching the declared sha1.
- **P4 (LEDGER 73):** file-claim table in `slice_orchestrator.py`, 40 tests.
  Nothing calls it yet - the enforcement half is still open (f1-phase6 item 7).
- **P5 (LEDGER 74):** memi **DO NOT ADOPT**. Its one finding fires on the fix it
  recommends, its colour counter reads 0 on a file with 10 hex literals, and the
  same file scores 38 vs 81 depending on subcommand. `npx memi` is a DIFFERENT
  package; the tool is `@memi-design/cli`.
- **The intersection, then the real comparison (LEDGER 75 + 76):** 77 corpus
  images confirmed same-artwork on TWO metrics. But wiki-vs-TARGET is not
  wiki-vs-what-we-hold: 23 held sources are LARGER, and the wiki file is softer
  in 35 of 77. What rescues it is that the held files RING - halo median 0.1032
  against the authentic original vs 0.0089 the other way. Net: **46 of 77 favour
  the wiki, not 77.**
- **The swap (LEDGER 77 + 78):** the 22 clear upgrades swapped in and all 22
  approved (10 clean, 12 operator override). `2.First Pass Done` back to 288.
- **P6 (LEDGER 79) CLOSED as NOT APPLICABLE** - LW replays no credentials
  anywhere; four probes, zero hits.

NEXT: **P7** (task-orchestrator's server-enforced gate, narrowed by P4 to just the
gate) or **P8** (gitwand, gated on one worktree-path probe). Also open: L2's
retrospective half, and `wiki-swap-manifest-hash-residue`.
Do NOT redo: the 22 swaps (done, approved, verified on disk), the P3/P5 probes,
or the intersection sweep. Two stale git worktrees are registered and were left
alone deliberately - check for unmerged work before removing.

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
