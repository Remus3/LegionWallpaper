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
