# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18) - keep the last 3.

---

## 2026-07-27 (session end) - 46 approved, and the ruling I failed to surface

Detail: LEDGER 58. Suite 831 passed / 14 skipped, drift gate 0, CI green.

- **refs-46-first-pass is CLOSED.** All 46 approved on operator instruction.
  `1.First Pass Scratch` EMPTY; `2.First Pass Done` = 288 slugs / 288
  `_firstdone.png`. Verified on the filesystem + a rebuilt scan, not the tally.
  One slug dry-run and approved alone before the other 45, because approval has
  no reverse command.
- **READ THIS BEFORE STAGE 2.** ROADMAP said `first-pass-alpha-letterbox` should
  be ruled on BEFORE approval - 15 of the 46 silently lose an alpha channel -
  and I did not surface it. I raised a different caveat (pixel-identical
  passthrough) whose evidence was sha256 over decoded RGB buffers, which is
  structurally blind to an alpha drop. Nothing is lost: `_firstinitial` is
  preserved RGBA beside the RGB `_firstdone` (verified via the PNG IHDR
  colour-type byte on `258-cleanup`) plus a copy in `9.Image Backup`. But the
  ruling is now post-approval, so acting on it needs the reopen dance.
- **NEXT SESSION: stage-2 cleaning (operator direction).** Rule on the alpha
  question FIRST - cleaning writes on top of `_firstdone`, so a later "keep the
  alpha" decision would mean redoing cleaning as well as first pass for those 15.
- Cleaning entry point is `.claude/commands/cleaning-pass.md`; the lane split and
  do-not-redo set are in `iopaint-batch-drain` in ROADMAP.

---

## 2026-07-27 (post-loop) - the two filed items, shipped on operator call

Commits `6c0423c` + `711f5f9`. Detail: LEDGER 57. Both CI green (evaluated, by
conclusion + head sha). 831 passed / 14 skipped.

- **refs-46-first-pass is DONE: 46/46 submitted, 0 approved.** The 46
  `_firstneedauth` files sit in `1.First Pass Scratch`. Approval is operator-only
  and the loop never touched it. The loop stopped clean on `max_cycles 12`.
- **Docs-only pushes ran no CI** while guards read docs off disk. `paths-ignore`
  dropped; the style drift gate MOVED from nightly to push (a nightly gate does
  not block, it reports up to 24h later). LW deliberately did NOT copy RC's
  docs-guard complement: their skipped suite carries playwright/mypy/Share sync,
  LW's is 28s, so the complement costs more than the filter saved.
- **`check_ci`'s not-evaluated logic KEPT**, against my own phrasing of the
  option the operator approved. It never fires with no globs declared, and
  deleting it would let a re-added filter silently revive item 12's ambiguity.
  The drift guard is inverted instead - it now asserts NO filter.
- **The PREMISE-CHECK stamp is now load-bearing.** `[UNVERIFIED]` is propagated
  (the director already declared the unknown; propagating is not inventing).
  `[from-digest]` means "I read this in context", not "this is true" - the digest
  can be fabricated upstream, so a claim naming a checkable referent is checked
  against disk. Three parser traps came from RC's verifier rounds, not from
  rediscovery: scan EVERY field (block-quotes silence a first-only scan), split
  on TAG not sentence boundaries (`e.g.`/`i.e.` zero the findings), never fold
  two tags on one line.
- **NEXT:** approve or reject the 46. Nothing else is claimed. The standing
  question both repos deferred is still open: which assertion in a file could
  never have gone red - LW's measured blind spot is 3 win32-only tests CI never
  runs and 14 `importorskip` ML tests green-by-absence everywhere.

---

## 2026-07-27 (loop cycle 11) - the alpha drop stops being silent

Code slice, not docs. Detail: LEDGER 56, plan row R26, commit `ef67c49`
(merge `191742a`). Four cycles of investigation produced a census; this ships
the half of the fix that needs no policy call. `first_pass()` now emits
`source_mode` + `alpha_flattened` in `upscale_audit` and
`tools/lw_first_pass.py:537` carries both into the annotate payload.
Two things a future session should not have to rediscover. (1) The mode is
read off the EXISTING `_covers_target` probe and the read sits OUTSIDE that
branch - all 46 refs took the downscale-only path, so a capture nested in the
AI-upscale branch would have missed exactly the population that produced the
finding. (2) `_has_alpha` fires on `"transparency" in img.info` as well as
mode RGBA, because a palette `P` + `tRNS` source flattens identically and
would otherwise self-report clean.
The verifier did not eyeball the diff: it ran `first_pass()` in both trees on
one synthetic source and diffed the audit JSON, so "no pre-existing key moved"
is measured, not asserted. 814 passed / 11 skipped on main. The slice's single
worktree failure was the known `core.hooksPath` artifact (passes in the main
tree) - third cycle running that it appears, worth a permanent note.
NEXT: the POLICY call per sub-shape is still open and is an operator ruling -
A (crop / re-source / accept the bars), B (near-certainly accept-and-record, a
1px perimeter has no composited consequence). The 15 already-processed refs
predate the new field, so their audits stay silent; ROADMAP holds that record.
