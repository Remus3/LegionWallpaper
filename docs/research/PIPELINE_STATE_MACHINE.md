# PIPELINE_STATE_MACHINE - Folder/Naming Workflow QA + Refined Spec

Date: 2026-07-03. Author: QA subagent (adversarial review of the operator's staged
folder scheme). Status: PROPOSAL - the operator's design is kept verbatim wherever
it survives QA; every deviation is tagged FIX (required, concrete failure mode) or
PROPOSED (operator decision needed, scheme is silent).

Scope note: filesystem semantics claims below (NTFS rename atomicity, MAX_PATH,
reserved names) are standard documented Windows behavior; nothing here required
web verification. Anything not derivable from the scheme text is marked PROPOSED.

---

## 1. Verdict

The scheme is SOUND and is kept: 10 numbered stage folders, per-image subfolder,
four co-existing phase files per scratch stage (_initial / _working_## /
_needauth / _done), copy-forward with rename at stage start, backup-at-intake and
backup-at-stage-start, scratch deletion only after verified arrival. None of that
changes. The failure modes found are all at the edges: crash windows in multi-file
transitions, name-grammar ambiguity, and undefined corners (End Review rejection,
duplicate Done sets). All fixes are additive.

### 1.1 Failure modes found (concrete) and minimal fixes

FM-01 Multi-file transitions are not atomic.
  Intake touches 3 locations (backup copy, scratch _firstinitial, delete from
  0.Originals). Approve touches 3+ (rename needauth->done, move 2 files to Done,
  delete scratch folder). A crash or power loss between steps leaves a split
  state. NTFS same-volume rename IS atomic per file, but nothing makes a 3-file
  sequence atomic.
  FIX: every transition is an ordered copy+fsync+hash-verify+delete sequence with
  a deterministic recovery rule per crash point (section 2.4). The scanner can
  always classify a half-done transition from filesystem state alone and either
  resume it or report it - never lose the authoritative copy, because the source
  is deleted only after every destination verifies.

FM-02 Duplicate authority between Done N and Done N+1.
  "Continuing an image COPIES its milestone set" into the next scratch. After
  approval of stage N+1, the set exists in Done N and Done N+1 simultaneously,
  forever, with no rule for which is authoritative. The scheme's own end-state
  description ("each Done folder holds the growing milestone set ... by the end")
  implies one location per image, so the leftover Done N copy is an unintended
  duplicate that will confuse any scanner and double storage.
  FIX: on approve of stage N+1, after the set is hash-verified in Done N+1,
  garbage-collect the Done N folder for that slug (content-verified: every file in
  Done N must equal a file in Done N+1 by hash - _firstdone content equals
  _cleaninitial content by construction). During stage N+1 work, the image
  legitimately exists in both Done N and Scratch N+1; that is the defined state.

FM-03 Basename collisions.
  NTFS is case-insensitive: Ahri.png and ahri.jpg collide. The same filename
  re-downloaded later collides with an existing 9.Image Backup\<name>\ and with
  an image already mid-pipeline. Windows reserved device names (CON, PRN, AUX,
  NUL, COM1-9, LPT1-9) and trailing dots/spaces (silently stripped by Win32) can
  produce folders that cannot be created or that alias each other.
  FIX: slug at intake (section 2.5). The slug is the canonical image ID for all
  folders and milestone filenames; the verbatim original filename is preserved
  inside 9.Image Backup\<slug>\ and recorded in manifest.json. On collision with
  any existing slug anywhere in the pipeline, suffix -2, -3, ...

FM-04 Grammar ambiguity from underscores in source names.
  A source named mf_firstdone.png or splash_final_working_02.jpg would parse as a
  phase token. DeviantArt names routinely contain underscores.
  FIX: reserve "_" exclusively for the phase-token separator. Slugging converts
  every non [a-z0-9] run in the source basename to a single hyphen. Slugs contain
  hyphens only, so the FIRST underscore in a milestone filename always starts the
  token. Parsing becomes a single anchored regex with zero ambiguity.

FM-05 Rejection-renumber race and overwrite risk.
  "Next _working_##" requires listing the folder and computing a number. Two
  concurrent writers (or a crashed retry) can compute the same number. Python
  os.replace silently OVERWRITES an existing target on Windows; a collision would
  destroy a working version. Also: ## as exactly two digits caps at 99, and
  count-based numbering breaks when the operator deletes a working file (gaps).
  FIX: (a) single-writer rule - only tools/lw_pipeline.py renames pipeline files,
  under a per-image lock file (section 2.7); (b) use os.rename, which fails if the
  target exists - on failure, rescan and retry with the new max; (c) number =
  max(existing)+1, never count+1; (d) grammar accepts 2+ digits (working_100 is
  legal) while the writer always zero-pads to at least 2.

FM-06 Extension drift creates ambiguous twins.
  Sources are .jpg, working files are .png. Nothing forbids ahri_firstdone.jpg
  and ahri_firstdone.png co-existing - two files, one logical milestone.
  FIX: uniqueness key is (slug, stage, phase) regardless of extension; the
  scanner flags a duplicate key as an ERROR. Policy: _firstinitial keeps the
  source extension (jpg/jpeg/png/webp); every later milestone MUST be .png
  (lossless from first-pass output onward - re-encoding to jpg mid-pipeline would
  reintroduce the compression artifacts the pipeline exists to remove).

FM-07 Half-written files in 0.Originals.
  A browser still writing a download (or a .crdownload/.part/.tmp) at session
  start would be intaken truncated - and FM-01's delete step would then destroy
  the only good copy when the download completes into a name that was already
  consumed.
  FIX: intake eligibility gate - skip files matching known partial extensions
  (.crdownload, .part, .tmp, .download), files with an open write handle, and
  files whose size changed between two probes ~2s apart or whose mtime is
  younger than 10s.

FM-08 MAX_PATH overflow.
  The slug appears TWICE in a milestone path (folder + filename) plus a ~45 char
  root prefix and up to ~25 chars of stage folder + token. DeviantArt basenames
  can exceed 120 chars; 2x that blows the 260-char default limit and produces
  files that Explorer and some editors cannot open.
  FIX: cap slug at 64 chars (truncate, then apply collision suffix). Belt and
  braces: enable the LongPathsEnabled registry switch on this box (safe, global):
  Set-ItemProperty "HKLM:SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1

FM-09 Backup collisions on reprocess.
  Re-running an image (better source found, same filename) writes into an
  existing 9.Image Backup\<slug>\ that already holds files from the prior run.
  FIX: backup writes are hash-idempotent - if the target name exists with the
  same SHA-256, skip silently; if it exists with a DIFFERENT hash, write
  <name>.2.<ext> (then .3, ...) and log. Never overwrite in 9.Image Backup.

FM-10 End Review rejection path is undefined.
  The scheme defines pass (send _lastdone to 9 + optional Pictures copy) but not
  fail.
  PROPOSED: fail demotes to 7.Last Scratch - recreate 7.Last Scratch\<slug>\
  from the End Review set with _lastdone renamed to _lastworking_{max+1}, exactly
  mirroring the in-stage rejection rule the operator already designed. The End
  Review folder entry is removed after the scratch set verifies.

FM-11 No content verification anywhere.
  The scheme's motivating fear ("never corrupted") is not actually defended:
  a bit-flip, truncated copy, or editor mis-save is invisible until a human
  looks. FIX: SHA-256 manifest per image folder (section 2.6); every copy is
  verified against the source hash before any delete; scan --verify re-hashes
  the world.

FM-12 Pictures delivery: cross-volume + sequential-rename race.
  Pictures may be on a different volume - the copy degrades to non-atomic
  copy+delete semantics, and a crash leaves a truncated ###.png that the next
  run then skips ("number taken"). Also "next ###" computed against a folder the
  user also writes to is a race by definition.
  FIX: copy to ###.png.part, fsync, hash-verify, then rename to ###.png (rename
  is atomic within the Pictures volume); compute the next free number at rename
  time and retry on collision; record the final assigned name in manifest.json
  and the log. Scanner ignores/GCs stale *.part files older than a day.

FM-13 Scratch deletion can eat operator side-files.
  Photoshop/Krita drop .psd/.kra/autosave files next to the image being edited.
  "Delete the scratch folder" would destroy them.
  FIX: scratch GC deletes only files matching the milestone grammar plus known
  temp patterns (*.part, *.tmp, .lw.lock, manifest.json after relocation); if
  unknown files remain, the folder is NOT deleted - it is reported as anomaly
  SCRATCH_RESIDUE and requires --force or manual cleanup. Approval still
  completes; only the GC step defers.

Verdict summary: keep the scheme; land FM-01..FM-09 + FM-11..FM-13 as required
fixes inside tools/lw_pipeline.py; FM-10 needs an operator yes/no.

---

## 2. State machine specification

### 2.1 Canonical layout

Pipeline root (PROPOSED default, configurable): C:\LegionWallpaper\pipeline\

```
<ROOT>\
  0.Originals\                 raw drops, any filename        (files, no subfolders)
  1.First Pass Scratch\<slug>\ stage=first, active work
  2.First Pass Done\<slug>\    stage=first, approved set
  3.Cleaning Scratch\<slug>\   stage=clean, active work
  4.Cleaning Done\<slug>\      stage=clean, approved set
  5.Final Scratch\<slug>\      stage=final, active work
  6.Final Done\<slug>\         stage=final, approved set
  7.Last Scratch\<slug>\       stage=last, active work
  8.End Review\<slug>\         full 5-milestone set, deep audit queue + archive
  9.Image Backup\<slug>\       original (verbatim name) + every _initial +
                               _lastdone + manifest snapshots. Append-only,
                               never overwrite (FM-09).
```

Keep 9.Image Backup on the SAME volume as the rest of the pipeline (preserves
atomic renames and cheap moves); true disaster-redundancy belongs to a separate
mirror job to another disk later - do not conflate the two (noted, out of scope).

### 2.2 Naming grammar (exact)

```
SLUG      := [a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?          # 1-64 chars, no "_"
STAGE     := first|clean|final|last
MILESTONE := ^(?P<slug>[a-z0-9][a-z0-9-]{0,63})
             _(?P<stage>first|clean|final|last)
             (?:(?P<phase>initial|needauth|done)
               |working_(?P<ver>[0-9]{2,}))
             \.(?P<ext>png|jpg|jpeg|webp)$                  # case-insensitive ext
```

Rules:
- The uniqueness key is (slug, stage, phase[, ver]) - extension excluded (FM-06).
- _firstinitial may be jpg/jpeg/png/webp; ALL other milestones must be png.
- Writer always zero-pads ver to >= 2 digits; parser accepts any length >= 2.
- A stage-N folder may contain milestones of stage <= N (carried-forward set);
  active-phase files (working/needauth) are legal only for stage == N.
  Anything else in a stage folder that does not parse is anomaly UNPARSED_FILE
  (except manifest.json, .lw.lock, *.part, known editor sidecars - see FM-13).

### 2.3 States (per image, derivable from filesystem alone)

The log and state file are advisory; a full rescan of the tree reconstructs every
state. Precedence: an image's state is defined by the HIGHEST-numbered folder
containing its slug, with the pairwise-coexistence rules below.

```
S0  PENDING_INTAKE   file in 0.Originals (presence = pending; intake removes it)
S1  FIRST_SCRATCH    1.\<slug>\ exists         substates: EDITING | NEEDAUTH | APPROVED_PENDING_MOVE
S2  FIRST_DONE       2.\<slug>\ exists, no higher folder
S3  CLEAN_SCRATCH    3.\<slug>\ exists (2.\<slug>\ also present = normal)
S4  CLEAN_DONE       4.\<slug>\ exists, no higher folder
S5  FINAL_SCRATCH    5.\<slug>\ exists (4. also present = normal)
S6  FINAL_DONE       6.\<slug>\ exists, no higher folder
S7  LAST_SCRATCH     7.\<slug>\ exists (6. also present = normal)
S8  END_REVIEW       8.\<slug>\ exists; PASSED iff 9.\<slug>\ contains a file
                     hash-equal to 8.\<slug>\<slug>_lastdone.png
S9  (terminal)       9.\<slug>\ only - archive entries for passed images
                     (plus, per verbatim scheme, the set remains in 8.End Review)
```

Scratch substates: EDITING = initial + zero or more workings; NEEDAUTH =
_needauth present; APPROVED_PENDING_MOVE = _done present in a SCRATCH folder
(only occurs mid-approve; scanner resumes the move - FM-01 recovery).

Anomaly classes (scan output): DUPLICATE_KEY (FM-06), UNPARSED_FILE,
SPLIT_STATE (slug in two scratch folders, or done+scratch of the same stage with
non-matching hashes), STALE_DONE (Done N still present after Done N+1 verified -
resumable GC, FM-02), MISSING_INITIAL, HASH_MISMATCH (manifest vs disk),
SCRATCH_RESIDUE (FM-13), STALE_LOCK, STALE_PART.

### 2.4 Transitions - exact file operations + crash recovery

Primitive SAFE-MOVE(src, dstdir, dstname):
  1. copy src -> dstdir\dstname.part (stream, then flush + os.fsync)
  2. re-read dstdir\dstname.part, SHA-256 must equal src hash, else delete .part and fail
  3. os.rename .part -> dstname  (fails if dstname exists; on hash-equal existing
     target, treat as already-done and delete .part; on hash-diff, anomaly)
  4. delete src (only step that removes the source)
Crash at any point: src still exists until step 4 completes -> rerun is
idempotent. A bare *.part is garbage-collected on scan.
Same-volume note: NTFS rename within a volume is atomic per file; SAFE-MOVE is
used anyway because (a) it verifies content, (b) it survives cross-volume moves,
(c) recovery is uniform. Pure renames (submit/reject/approve step 1) use plain
os.rename - single-file, atomic, nothing to verify.

T1 INTAKE (S0 -> S1)   [command: intake]
  pre: eligibility gate (FM-07); compute slug (2.5); acquire lock
  1. mkdir 9.Image Backup\<slug>\ ; SAFE-COPY original -> backup, VERBATIM
     original filename (copy, not move: source deleted last)
  2. mkdir 1.First Pass Scratch\<slug>\ ; SAFE-COPY original ->
     <slug>_firstinitial.<ext>
  3. write manifest.json into scratch folder (tmp + os.replace, per CLAUDE.md)
  4. delete file from 0.Originals ; append log line ; release lock
  recovery: file still in 0.Originals -> rerun intake; existing hash-equal
  backup/scratch copies are skipped; hash-diff -> anomaly, halt this image.

T2 START-STAGE (S2->S3, S4->S5, S6->S7)   [command: start-stage]
  pre: image in Done N, not in any scratch; acquire lock
  1. mkdir Scratch(N+1)\<slug>\
  2. SAFE-COPY every milestone from Done N (keep names), EXCEPT _<N>done which
     copies as <slug>_<N+1>initial.png
  3. SAFE-COPY <slug>_<N+1>initial.png -> 9.Image Backup\<slug>\ (hash-idempotent, FM-09)
  4. SAFE-COPY manifest.json forward; append started_stage transition (tmp+replace)
  5. append log line; PRUNE Done N\<slug>\; release lock.
     Operator ruling 2026-08-17 (supersedes the old "Done N is retained until
     T5" half of FM-02): step 2 already carried every milestone forward, so
     <slug>_<N+1>initial.png IS the fallback and the stage-N folder has no
     further job. The prune is verified, not assumed - the new _initial must
     match the _<N>done byte-for-byte and every other Done-N file must have a
     same-named twin in Scratch N+1, else the folder is KEPT and the skip is
     printed. FM-02's hash-verified GC still governs the Done N -> Done N+1 hop.
  recovery: partial scratch set -> rerun completes missing copies (hash-equal
  skips); the prune runs last, after the full set verifies, so an interrupted
  transition leaves Done N in place and is simply re-runnable.

T3 SAVE-WORKING (within scratch)   [command: save-working]
  input: an edited file (--from <path>) or --adopt (newest unparsed image file
  already saved into the scratch folder by the operator's editor)
  1. n = max(existing ver)+1 (FM-05); SAFE-COPY/rename to <slug>_<stage>working_NN.png
  2. manifest transition (tool+params if machine-produced); log line.

T4 SUBMIT (EDITING -> NEEDAUTH)   [command: submit]
  1. os.rename <slug>_<stage>working_MAX.png -> <slug>_<stage>needauth.png
     (atomic; fails if needauth exists -> error "already submitted")
  requires >= 1 working file; manifest + log.

T4r REJECT (NEEDAUTH -> EDITING)   [command: reject]
  1. os.rename needauth -> working_{max+1} (atomic, fail-if-exists + retry, FM-05)
  2. manifest transition with --note; log line.

T5 APPROVE (NEEDAUTH -> Done N, S(2k-1) -> S(2k))   [command: approve]
  1. os.rename needauth -> <slug>_<stage>done.png   (atomic commit point)
  2. SAFE-MOVE the milestone set (all _initial-lineage files + _<stage>done;
     working files are intentionally discarded per scheme) -> Done N\<slug>\
  3. SAFE-MOVE manifest.json -> Done N\<slug>\ (append approved transition first)
  4. GC scratch folder per FM-13 rules
  5. if N > first: GC Done(N-1)\<slug>\ after content verification (FM-02)
  6. log line; release lock
  recovery: _done present in scratch = APPROVED_PENDING_MOVE -> resume at 2;
  set fully in Done + scratch remnants hash-equal -> resume at 4; Done N and
  Done N-1 both present -> resume at 5 (STALE_DONE).

T6 LAST-APPROVE (S7 -> S8): identical to T5 with Done := 8.End Review\<slug>\
  (End Review acts as the last stage's Done folder, per the scheme).

T7 FINALIZE (End Review pass)   [command: finalize]
  pre: deep audit of all five milestones (audit scores -> manifest)
  1. SAFE-COPY <slug>_lastdone.png -> 9.Image Backup\<slug>\ (hash-idempotent)
  2. optional --to-pictures: copy per FM-12 (.part + atomic rename, next free
     ### computed at rename time; assigned name -> manifest + log)
  3. manifest transition finalized; snapshot manifest.json -> 9.Image Backup\<slug>\
  4. log line. The set REMAINS in 8.End Review (verbatim scheme). PASSED is
     derivable: backup contains a file hash-equal to the set's _lastdone.
  recovery: every step idempotent (hash-equal skips).

T7r END-REVIEW-REJECT (PROPOSED, FM-10)   [command: reject --stage last <slug>]
  recreate 7.Last Scratch\<slug>\ from the End Review set with _lastdone renamed
  to _lastworking_{max+1}; SAFE-MOVE back; remove 8.\<slug>\ after verify.

### 2.5 Collision policy (slugging, FM-03/04/08)

slug(source_basename):
  1. strip extension; Unicode NFKD -> drop non-ASCII; lowercase
  2. every run of chars outside [a-z0-9] becomes a single "-" (kills underscores,
     spaces, dots, illegal chars <>:"/\|?*, smart punctuation)
  3. trim leading/trailing "-"; collapse "--" -> "-"
  4. truncate to 64 chars; trim trailing "-" again
  5. if empty -> "img"
  6. if result is a reserved device name (con, prn, aux, nul, com1-9, lpt1-9)
     -> append "-x"
  7. while slug exists anywhere in the pipeline (any stage folder or 9.Image
     Backup, case-insensitive) AND is not this same source (hash-equal original
     in backup = re-intake of the identical file, which is refused as duplicate):
     append -2, -3, ... (re-truncating to keep <= 64)
  original_filename is recorded verbatim in manifest.json and preserved as the
  backup copy's filename.

### 2.6 Hash policy

- Algorithm: SHA-256, full file, lowercase hex. Stored in manifest.json for every
  milestone at creation and after every transition (sha256_in / sha256_out).
- Every SAFE-MOVE/SAFE-COPY verifies dest hash == src hash BEFORE any delete.
- Log lines carry the first 12 hex chars (sha12) for human greppability.
- verify command / scan --verify: re-hash every file, diff against manifests,
  report HASH_MISMATCH. Never auto-repair; corruption is an operator decision
  (the backup folder holds the recovery material).

### 2.7 Locking + single-writer

- Only tools/lw_pipeline.py mutates pipeline names (operator image EDITS are
  saves via the editor; naming mutations go through save-working/--adopt).
- Per-image lock: <folder>\.lw.lock created O_CREAT|O_EXCL containing pid + ts.
  Held for the duration of a transition. Stale if pid dead or age > 1h ->
  scan reports STALE_LOCK; --break-locks clears after confirmation.
- All renames use os.rename (fail-if-exists), never os.replace, except the
  documented tmp->target replace for manifest/state JSON writes.

### 2.8 Stage semantics (PROPOSED - the scheme defines flow, not content)

- first  = source recovery (reverse-image-search / DeviantArt fullview) + ONE AI
  upscale (realesrgan) + ONE Lanczos downscale to 2560x1440 + light unsharp mask.
  Never double-resample (the old pipeline's softness bug).
- clean  = watermark removal + AI-generation artifact repair via MASKED
  inpainting only (scalpel rule; no full-image passes).
- final  = polish: eyes/irises/skin detail, banding/color fixes, exact
  2560x1440 conformance check.
- last   = fresh-eyes regression vs all prior milestones + format check
  (PNG, sRGB, 8-bit, correct dimensions, metadata scrubbed) - no new editing
  beyond reverts.
- End Review = deep audit of all five milestones together (drift across stages,
  regression vs _firstinitial intent, watermark recurrence).

---

## 3. CLI surface - tools/lw_pipeline.py

Global flags: --root <path> (default from config), --json (machine output),
--dry-run on EVERY mutating subcommand (prints the exact op list - copies,
renames, deletes, hash checks - and exits 0 without touching disk). Every move
is SAFE-MOVE (copy+fsync+hash-verify+delete). Exit codes: 0 ok, 1 anomalies
found, 2 precondition/argument error, 3 verification failure.

```
scan        [--verify] [--fix-resumable]
            Rebuild world state from the filesystem (log/state advisory only).
            Lists per-stage counts, pending intakes, anomalies. --verify
            re-hashes everything. --fix-resumable resumes APPROVED_PENDING_MOVE,
            STALE_DONE GC, *.part GC - only provably-safe recoveries.
            Writes ops/runtime/pipeline_state.json (tmp+replace). Read-only
            on pipeline folders unless --fix-resumable.

status      [<slug>] [--stage <name>]
            Human view: one line per image (slug, state, substate, ver count,
            last transition ts) or full detail + manifest tail for one slug.

intake      [<file>...] [--all] [--dry-run]
            T1 for named files or every eligible file in 0.Originals.
            Skips ineligible files (FM-07) with a reason line.

start-stage <slug> | --next   [--dry-run]
            T2. --next picks the oldest image sitting in a Done stage.
            Refuses if the slug is already in any scratch.

save-working <slug> (--from <path> | --adopt)   [--tool <name> --params <json>] [--dry-run]
            T3. Registers the next _working_##. --tool/--params recorded in
            manifest for machine-produced versions (upscaler, inpainter).

submit      <slug>   [--dry-run]
            T4. Latest working -> _needauth.

approve     <slug>   [--dry-run] [--force]
            T5/T6. needauth -> done, set -> Done folder, GC scratch + prior
            Done. --force overrides SCRATCH_RESIDUE deferral (FM-13).

reject      <slug> [--note <text>] [--stage last]   [--dry-run]
            T4r. needauth -> next _working_##. --stage last = T7r END-REVIEW
            demotion (PROPOSED; disabled until operator approves FM-10).

finalize    <slug> [--to-pictures [--seq]] [--audit-json <path>]   [--dry-run]
            T7. Requires audit scores (from --audit-json or interactive
            confirmation) recorded to manifest before the copies run.

verify      [<slug>] [--all]
            Re-hash and diff vs manifests; report only, never mutate.
```

Idempotence contract: any command may be re-run after a crash; it re-derives
state from disk, skips hash-equal completed steps, and resumes the remainder.

---

## 4. Logging and machine state

### 4.1 PIPELINE_LOG.md (repo: PIPELINE_LOG.md at project root - append-only, human-readable; the build-wave contract superseded this section's original logs/ placement)

One line per transition, pipe-delimited, ASCII, newest at bottom:

```
<iso8601Z> | <slug> | <OP> | <from> -> <to> | actor=<operator|tool:name> | sha12=<hex12> | <ok|fail:reason> | note=<text or ->
```

OP in: INTAKE, START_CLEAN, START_FINAL, START_LAST, SAVE_WORKING, SUBMIT,
REJECT, APPROVE_FIRST, APPROVE_CLEAN, APPROVE_FINAL, APPROVE_LAST, FINALIZE,
DELIVER_PICTURES, GC_DONE, RECOVER. Example:

```
2026-07-03T21:14:09Z | ahri-star-guardian | APPROVE_CLEAN | 3.Cleaning Scratch -> 4.Cleaning Done | actor=operator | sha12=ab12cd34ef56 | ok | note=-
```

Append via open-append + single write of one line; the log is advisory (scan
never needs it), so append is not required to be transactional.

### 4.2 ops/runtime/pipeline_state.json (machine twin, tmp+replace atomic)

```json
{
  "schema": 1,
  "generated_ts": "2026-07-03T21:14:10Z",
  "scan_verify": false,
  "root": "C:\\LegionWallpaper\\pipeline",
  "counts": {"pending_intake": 3, "first_scratch": 1, "first_done": 0,
             "clean_scratch": 2, "clean_done": 5, "final_scratch": 0,
             "final_done": 1, "last_scratch": 0, "end_review": 4,
             "passed": 290, "anomalies": 1},
  "images": {
    "ahri-star-guardian": {
      "state": "CLEAN_SCRATCH", "substate": "EDITING",
      "stage_folder": "3.Cleaning Scratch",
      "working_max": 4, "last_op_ts": "2026-07-03T21:14:09Z",
      "files": [{"name": "ahri-star-guardian_cleaninitial.png",
                 "sha256": "...", "bytes": 8123456,
                 "mtime": "2026-07-03T20:01:00Z"}],
      "anomalies": []
    }
  },
  "anomalies": [{"slug": "jinx-arcane", "class": "STALE_DONE",
                 "detail": "2.First Pass Done superseded by 4.Cleaning Done; resumable GC",
                 "resumable": true}]
}
```

### 4.3 manifest.json (sidecar per image folder; travels with the set; snapshot
to 9.Image Backup at intake and finalize; written tmp+replace)

```json
{
  "schema": 1,
  "slug": "ahri-star-guardian",
  "original_filename": "Ahri_Star Guardian_fullview.jpg",
  "original_sha256": "...",
  "source_url": null,
  "created_ts": "2026-07-01T10:00:00Z",
  "delivered_as": null,
  "transitions": [
    {"ts": "2026-07-01T10:00:01Z", "op": "INTAKE", "actor": "operator",
     "tool": null, "params": null,
     "src": "0.Originals/Ahri_Star Guardian_fullview.jpg",
     "dst": "1.First Pass Scratch/ahri-star-guardian/ahri-star-guardian_firstinitial.jpg",
     "sha256_in": "...", "sha256_out": "...", "audit": null},
    {"ts": "2026-07-01T11:30:00Z", "op": "SAVE_WORKING", "actor": "tool:realesrgan",
     "tool": "realesrgan-ncnn-vulkan", "params": {"model": "realesrgan-x4plus-anime", "scale": 4},
     "src": "...firstinitial.jpg", "dst": "...firstworking_01.png",
     "sha256_in": "...", "sha256_out": "...", "audit": null},
    {"ts": "2026-07-02T09:00:00Z", "op": "FINALIZE", "actor": "operator",
     "tool": null, "params": null, "src": "...", "dst": "...",
     "sha256_in": "...", "sha256_out": "...",
     "audit": {"softness": 0.92, "watermark": 1.0, "faces": 0.88, "format": "pass"}}
  ]
}
```

This manifest is the substrate for the eventual self-audit (audit scores per
transition) and for shareability (a complete, reproducible provenance chain per
image: every tool, every parameter, every hash).

---

## 5. Operator decisions needed (everything else is required-fix, not opinion)

1. FM-10 / T7r: approve the End Review rejection path (demote to 7.Last Scratch)?
2. FM-02 GC rule: confirm deleting the Done N copy after Done N+1 verifies
   (keeps one authoritative location; the alternative is documented duplication).
3. Section 2.8 stage semantics: confirm first/clean/final/last content definitions.
4. Pipeline root location (default C:\LegionWallpaper\pipeline\) and whether
   Pictures delivery uses the sequential ###.png rename by default.
5. FM-08: OK to set LongPathsEnabled=1 machine-wide (safe, reversible)?
