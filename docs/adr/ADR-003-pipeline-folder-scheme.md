# ADR-003: Pipeline folder scheme - operator's 10-folder/4-phase design, adopted verbatim plus 13 additive fixes

**Date:** 2026-07-03
**Status:** Accepted

## Context

The restoration pipeline (ADR-002) needs a filesystem state machine: where
images live at each stage, how phases are named, what survives a crash. The
operator designed a 10-folder staged scheme with per-image subfolders, four
co-existing phase files per scratch stage, copy-forward milestone sets, and
backup-at-intake. An adversarial QA review
(`docs/research/PIPELINE_STATE_MACHINE.md`) judged the scheme SOUND and found
13 edge failure modes (FM-01..FM-13): non-atomic multi-file transitions,
duplicate Done-set authority, basename collisions, underscore grammar
ambiguity, rejection-renumber races, extension twins, half-written intake
files, MAX_PATH overflow, backup collisions, an undefined End Review
rejection path, no content verification, Pictures delivery races, and scratch
GC eating operator side-files. Alternatives (database-backed state, flat
folder + sidecar index) were rejected: the operator's scheme is
human-inspectable, and every state is derivable from the filesystem alone.

## Decision

Adopt the operator's scheme VERBATIM - 10 numbered stage folders, per-image
slug subfolders, phase tokens `_<stage>initial | _<stage>working_## |
_<stage>needauth | _<stage>done` (stage in first/clean/final/last), underscore
reserved exclusively for phase tokens, image IDs as lowercase hyphen slugs -
plus ALL 13 additive fixes from PIPELINE_STATE_MACHINE.md (SAFE-MOVE
copy+fsync+hash-verify+delete transitions, Done-N GC, intake slugging with
collision suffixes, anchored grammar, single-writer lock + fail-if-exists
renames, png-after-first policy, intake eligibility gate, 64-char slug cap,
hash-idempotent backups, End Review rejection, SHA-256 manifests, .part+rename
Pictures delivery, grammar-scoped scratch GC). Implemented solely by
`tools/lw_pipeline.py`; state published atomically to
`ops/runtime/pipeline_state.json`; transitions appended to `PIPELINE_LOG.md`
at project root (pipe-delimited, append-only, gitignored personal state).

Five operator rulings (the QA doc's open decisions, now settled):

1. END REVIEW REJECTION: ENABLED. Fail demotes to `7.Last Scratch` -
   recreate `7.Last Scratch\<slug>\` from the End Review set with `_lastdone`
   renamed to `_lastworking_{max+1}`; remove the `8.End Review` entry after
   the scratch set verifies (T7r).
2. DONE-N GC: CONFIRMED. After the milestone set hash-verifies in Done N+1,
   the Done N copy for that slug is garbage-collected - one authoritative
   location per image.
3. STAGE SEMANTICS: CONFIRMED as in ADR-002 / `docs/RESTORATION_PLAN.md`
   section 2 (first = recovery + single upscale; clean = masked watermark/
   artifact inpaint; final = face/eye repair + debanding + conformance;
   last = fresh-eyes regression).
4. PIPELINE ROOT: `C:\LegionWallpaper\images\` (not the QA doc's proposed
   `pipeline\` default). Stage folders exactly: `0.Originals`,
   `1.First Pass Scratch`, `2.First Pass Done`, `3.Cleaning Scratch`,
   `4.Cleaning Done`, `5.Final Scratch`, `6.Final Done`, `7.Last Scratch`,
   `8.End Review`, `9.Image Backup`, plus `reference_pictures` (non-pipeline
   reference corpus). `images/**` stays gitignored except the .gitkeep
   skeleton.
5. LONGPATHSENABLED: DEFERRED. The 64-char slug cap suffices; do not touch
   the machine-wide registry switch. Revisit on the first observed MAX_PATH
   error.

Additional ruling beyond the QA doc's T7: on End Review PASS, `8.End Review\
<slug>\` is DELETED after the `_lastdone` copy to `9.Image Backup` verifies -
the full milestone chain lives in `9.Image Backup`, not duplicated in 8.

## Consequences

**Good:** Every image state is reconstructable from the filesystem alone
(logs and state JSON are advisory); crashes at any point are resumable
because sources are deleted only after every destination hash-verifies; the
scheme stays exactly as the operator designed it, so human inspection and
manual editing keep working; provenance manifests make each image's chain
reproducible and the process shareable.

**Trade-off:** Copy-forward milestone sets cost disk (bounded by Done-N GC
and the End-Review-pass deletion); SAFE-MOVE hashing adds per-transition
latency (negligible at corpus scale); single-writer locking serializes
concurrent pipeline mutations by design.

**Watch for:** MAX_PATH errors (ruling 5's revisit trigger); scratch folders
reported as SCRATCH_RESIDUE when editors drop sidecar files (deferred GC, by
design - not a bug); `9.Image Backup` growth (append-only, never overwrite;
disaster mirroring to another disk is a separate future job, out of scope
here). This scheme is operator-designed and settled - do not re-litigate
folder names, token grammar, or stage flow without a superseding ADR.
