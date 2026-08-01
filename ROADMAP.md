# Legion Wallpaper - Roadmap

_Now + Next only. Highest priority at the TOP. Full history in `docs/history_notes.md`. Aspirational in `BACKLOG.md`._

---

## Open items - High priority

_Shipped/closed entries move to `docs/LEDGER.md` (append-only). Only open/in-flight work stays below, highest priority first. Sequencing for the next 2-4 weeks: `docs/ATTACK_PLAN.md`. Item grammar: id - title - state - next action - evidence link._

- **gemini-removal - drop Gemini; the loop becomes Claude-only and
  self-adjudicating - OPERATOR-DIRECTED, own slice.**
  Next: flip the reversible part, keep the backend reachable as the rollback
  path, file the rest as a sweep - the same split RC took rather than a
  big-bang removal. RC completed its side 2026-08-01 (`adjudicator: claude`,
  `DEFAULT_BACKEND` flipped, `RC-GeminiAudit` task disabled not deleted).
  LW's shape is DIFFERENT and there is no one-line flip: LW has no adjudicator
  key at all - Gemini is structurally the DIRECTOR and AUDITOR via
  `gemini_model`, `gemini_cmd`, `director_prompt.md`, `auditor_prompt.md`,
  `tools/gemini_audit.ps1`, the `ceiling_usd` accounting, and the mutex hold at
  `loop_controller.py:366`. Removing it means replacing what AUTHORS each
  cycle's directive, not switching a backend behind a flag.
  Supporting evidence from LW's own runs: a read-only Claude verifier refuted a
  Claude slice on a false behavior-identical claim, and a second refuted another
  on a cache-eviction regression a 530-line test file missed - same vendor, both
  caught, because the grader was adversarial and independent rather than
  differently-branded. Vendor diversity was not what was catching errors.
  Do-not-redo: do NOT delete `GEMINI_MUTEX` from `winmutex.py` - it is
  byte-identical-by-contract, deleting it needs a three-way re-pin, and LW still
  has a LIVE consumer at `loop_controller.py:366` today.
  Evidence: `moon_sync_inbox/2026-08-01-0820-from-RC-*` section 7.

- **rundash-instrumentation - the evidence panel shipped; the rest of the
  backlog is open - LATER.**
  DONE 2026-08-01 (`0ee1c9e`): chips render VERIFIED / REFUTED / NOT OBSERVED
  from an append-only per-slice verdict history written only through
  `slice_orchestrator.py`. A REFUTE with no later CONFIRM renders REFUTED even
  when the slice is `committed`; earlier refutations survive as `prior_refutes`.
  ALSO DONE 2026-08-01 (LEDGER 65): the directive-history spine - `run_id`,
  `cost_usd` and `session_id` now reach the file, the reader segments runs on a
  real id with the cycle heuristic kept as the legacy fallback, and
  `read_cycle_history` is wired into `/api/run`, which it never was.
  ALSO DONE 2026-08-01 (LEDGER 66): the P1b Cycle History panel renders it, and
  the cost boundary is enforced - `cost_usd` stays in the file for forensics and
  is projected OUT of `/api/run`, because LEDGER 40 settles that Claude dollar
  figures are notional and the spec rejects a cost panel outright.
  Next, from `docs/RUNDASH_SPEC_2026-08-01.md`: persisted per-slice suite
  observations; map the three run-id
  namespaces to each other (the spine only fixed `directive_history.jsonl`);
  mirror at-risk agent metadata out of the transcript dir before Claude Code's
  cleanup reaps it; `truth_gate.py` is never invoked by the run flow so its
  report has never been written on this machine; P4 and P5 panels unbuilt.
  Do-not-redo: do NOT collapse `lw_httpd.parse_ts` and
  `lw_rundash_state.parse_iso` - naive UTC vs naive LOCAL, 5h apart here, and
  `loop_controller.py:303` writes naive LOCAL so `parse_iso` is correct.
  Evidence: `docs/RUNDASH_SPEC_2026-08-01.md`; dashboard 127.0.0.1:8900.

- **usm-halo-calibration - our own unsharp mask manufactures every halo flag,
  and turning it down trades 7 soft flags for 6 hard fails - OPERATOR-GATED.**
  Next: operator picks the axis - re-seed the halo threshold for the
  IllustrationJaNai path (its own comment at `tools/lw_g1_gate.py:31-34` says
  the 0.05 seed is an n=10 realesrgan/USM70 number owed recalibration), or
  soften `USM_DEFAULT` percent, or accept the flags. Measured over all 17 gated
  slugs of batch20 (7 flagged + 10 controls, nothing inferred): condition A
  reproduces every recorded manifest `halo_pct` to 4dp, so the probe measures
  the real pipeline. Skip the USM and max `halo_pct` falls to 0.0062 with 0 of
  17 over the line - the upscaler contributes almost none of it, so ADR-004 is
  NOT implicated. But with no mask 6 of the 16 gated slugs fall through
  `lap_ratio`'s 1.0 HARD FAIL floor. usm35 clears all halo flags with the
  weakest gated `lap_ratio` at 1.1399; usm50 leaves 2 flagged.
  Do-not-redo: proposing a final number on halo evidence alone - the census
  deliberately did NOT recompute ms_ssim/lpips/dists per variant, so a milder
  mask's fidelity cost is UNMEASURED, and a one-axis threshold pick is the
  mistake that already got one gate rejected here. Measure fidelity per variant
  first. Also settled by the census: `halo_pct` is monotone in USM percent on
  every slug, so it reads as a strength dial, not a defect detector, and the
  0.05 line cuts a continuum with no gap at it.
  Evidence: `docs/USM_HALO_CENSUS_2026-07-30.md`; `tools/lw_usm_halo_probe.py`.

- **g1-source-adequacy - G1 is blind to an inadequate SOURCE; 105 of 276 approved
  images came from one - OPERATOR-GATED on policy.**
  Next: operator answers two questions, then it is a small deterministic slice -
  (1) is a 2.5x upscale from 1024x576 acceptable? (2) inadequate source = FLAG or
  FAIL? Deliberately NOT guessed; guessing repeats the mistake `anat-vision-review`
  caught the same day. Cheap once decided - `src_dims` is already in every
  manifest, so no model and no pixels needed.
  Do-not-redo: do NOT retune the G1 fidelity metrics - they are correct at their
  job; the gap is a MISSING ABSOLUTE precondition, not a miscalibrated relative one.
  Evidence: LEDGER 60; `docs/SOURCE_ADEQUACY_CENSUS_2026-07-29.md`.

- **legacy-audit-backfill - 12 approved images carry no G1 audit; 10 of them were
  built with the FALLBACK upscaler - NEXT (backfill, not a code fix).**
  Next: backfill or mark the 12 as pre-audit legacy, then decide the 10 reprocesses.
  Verified NOT a live bug (all 12 predate ADR-004; the current code path always
  writes the audit). NOT reprocessed unattended - `APPROVE_FIRST` is an operator
  judgement by design, so regenerating would park 10 images in your approval queue.
  The CODE half is DONE 2026-07-30 (`94bea85`): approve and finalize now record
  `gate_check` as `pass` / `override` / `no_audit`, so an override is greppable
  and a legacy no-audit approval is its own outcome rather than passing for a
  clean one. Only the DATA decision is still owed.
  Evidence: LEDGER 60 + 61; `docs/SOURCE_ADEQUACY_CENSUS_2026-07-29.md` (slugs listed).

- **anat-vision-review - the anatomy percept needs a VISION reviewer, not keypoints
  - OPERATOR-GATED on product direction.**
  Next: operator decides whether a vision reviewer may FLAG only, or may REJECT.
  Keypoint head-spine offset was built, measured over all 288 approved firstdones,
  and REJECTED as a gate on the evidence; it ships as a diagnostic only
  (`tools/lw_anat_metrics.py` + `tools/lw_anat_probe.py`). The right mechanism is
  the Claude-vision 2AFC path `end-review` already uses.
  Do-not-redo: keypoint head-spine offset as a gate metric; swapping the localizer
  to rescue it (splash art is cropped at the waist, so most images have no confident
  hips - a better pose model cannot find hips outside the crop); reading a DWPose
  figure count as a detection count (35 percent yield zero person boxes and
  `tools/dwpose_onnx/onnxpose.py:26` silently substitutes the whole frame).
  Evidence: LEDGER 60; `docs/ANATOMY_CENSUS_2026-07-29.md`.

- **m1-gate-fund-or-close - decide attempt #4 on the weapon-canonicity gate - OPERATOR-GATED.**
  Next: operator decides FUND or CLOSE. Three measured negatives landed
  2026-07-26 (LEDGER 37) and the binding constraint is now known and cheap to
  fix: canonical n=5 gives AUC granularity 1/65, so no result can be
  significant. FUND = hand-crop wrists from the 19 official Vayne splashes
  already local at `tools/models/lora_datasets/vayne/` (the existing 5
  `weapon_assets` crops came from that same pool) to reach n~19 canonical vs
  ~13 non-canonical, all real Riot art, matched on pixel count AND provenance.
  CLOSE = accept `gate_mode="operator"` permanently, which is already the
  shipped default and works.
  Evidence: LEDGER 37; `scratchpad/probe_results.md` +
  `scratchpad/render_exemplar_results.md`.
  Do-not-redo: img2img weapon-swap (structure-locked, 0/12); any probe trained
  across a provenance boundary (AUC 1.0 = generator fingerprint); the 36 staged
  DreamUp step4 prompts (superseded by the render path). Match on EVERY axis -
  provenance and resolution both slipped in while palette was being tuned.

- **f1-phase6-queue - 12 follow-ups from the sdk-channel migration - RC-SIDE REMAINDER (LW's share is DONE).**
  Phase 6 DELETIONS remain HELD by operator call (flip yes, delete no); both repos
  default to `channel: sdk` and rollback is one config key. The gate for revisiting
  deletion is satisfied on both sides (LW 24-min / RC 71-min full-length cycles).
  Queue, agreed with RC and unstarted: (1) `chmod +x .githooks/*` - DONE on LW,
  open on RC. (2) `gate_inactive_reason` must check the exec bit on POSIX, not just
  presence. (3) log `sid` on EVERY `SdkExecutor` path incl. success - a cycle's
  transcript is currently unfindable once the process exits. (4) `ENGINE-IMPACT:
  BUMP` must require a numbered step naming every anchor site (RC found a FIFTH
  anchor: two changelogs, `agents/daemon_slayer/CHANGELOG.md` != `Share/CHANGELOG.md`).
  (5) `skipif` audit - skip when the CAPABILITY is absent, never when the thing under
  test is. (5a) pin the shared-file sha256s as constants so each repo's CI enforces
  parity alone. (6) CI arms the gate then asserts it - DONE on LW. (7) directives
  naming N parallel agents must assert disjoint files; executor serializes AND
  RECORDS the deviation. (9) POSIX `winmutex` branch must emit `UNSERIALIZED` -
  today it is unserialized AND untraced, so every guard we built passes vacuously
  off-Windows; joint edit + re-sync. (10) enumerate every instance of a defect class
  IN THE FILE before committing the fix, then across the codebase - CLAUDE.md:171
  says this but points outward, and it was missed twice in one function. (11) a
  claim heavy enough to justify a schema change ships as a TEST, not a transcript.
  (12) when asserting CI state, distinguish `not evaluated` (docs-only path filter)
  from `queued` - they are indistinguishable in `gh run list`.
  (5a) and (9) are DONE and VERIFIED IN SYNC on both sides: LW `3bd9a8b`, RC
  `fbf744f5`, both trees re-hashed clean to `slots.py 95077a62...` and
  `winmutex.py f1b4b011...` (the latter supersedes `c21bfe4f...`). (1) is done
  on both sides too - RC's exec bits landed as `19b680cc`.
  (3) is DONE on LW (`549f52c`): `build_argv` now retains the session id it
  mints or resumes, so all five `SdkExecutor` paths log it - including timeout
  and unparseable stdout, which never parse a payload and so previously had no
  id to log at all. Same commit repairs the CI red that `202cef3` introduced
  (the `directive_suffix` guard keyworded `done_sentinel`, which the phase-6
  DO-NOT-REDO line legitimately names).
  (12) is DONE on LW (`07ed5bc`): `check_ci` split the single `no-runs` outcome
  into `not-evaluated` and `queued`. The `paths-ignore` globs are PARSED from
  `.github/workflows/ci.yml` rather than hardcoded, so the check cannot drift
  from the workflow, and every unknown - unreadable workflow, no `paths-ignore`
  key, failed `git show`, merge commit - falls to `queued`. `not-evaluated`
  requires positive evidence. `reconcile()` still REFUSEs only on `failure`:
  making `queued` refuse would wedge an unattended run on GitHub API lag.
  Residual, adjacent and NOT item 12: `check_ci` only rev-parses when
  `sha == "HEAD"`, so an abbreviated sha reaches `gh run list --commit` and
  returns `[]`. The conservative fallback answers `queued`, so it is not a false
  green, but the abbreviation gap is real - `check_ci("549f52c")` -> `queued`
  while the full sha -> `success`.
  LW's share of the queue is now empty; RC keeps (2), (4), (5), (7), (10), (11).
  Cross-repo channel is the gitignored `moon_sync_inbox/` in each repo.
  Evidence: LEDGER 41 + 40; `docs/specs/2026-07-26-f1-sdk-executor-channel.md`.

- **glb-render-fetch - acquire the .glb bytes the ported resolver now addresses - NEXT.**
  Next: the addressing + filtering half shipped 2026-07-26 (LEDGER 38, 1dbfc2d) -
  `glb_model_url` / `glb_skin_id` / `is_weapon_joint` / `weapon_joint_indices` /
  `mesh_primitives` live in `tools/lw_gen_weapon_assets.py` and are pure, so the
  module stays torch-free AND network-free. What is still OWED is the I/O half:
  fetch the URL, parse the GLB container, skin the mesh against the surviving
  joints, and render the crop that `load_assets` consumes. That half needs a
  network dependency and a render backend, so it is a separate slice by design.
  Evidence: LEDGER 38 (1dbfc2d); LEDGER 37 for the live CDN verification.
  Do-not-redo: scraping the modelviewer.lol WEBSITE (Cloudflare + in-app blobs,
  POC-measured); any fixed bone-INDEX set (two rig conventions exist, so indices
  cannot port); reading `primitives[0]` alone (newer skins split mesh 0 into
  9-10 primitives sharing one POSITION accessor - drops most triangles); the
  `.skl` skeleton from CDragon (404) - the named-joint path replaces it.

- **refs-46-first-pass - process the 46 intaken reference_pictures - DONE
  2026-07-27. 46 of 46 APPROVED by the operator; `1.First Pass Scratch` is
  empty and `2.First Pass Done` holds 288 slugs (242 prior + these 46).**
  **A PROCESS MISS ON APPROVAL, recorded because the ruling it skipped is still
  open:** this entry said `first-pass-alpha-letterbox` should be ruled on BEFORE
  approval, and the session did not surface that to the operator - it raised the
  pixel-identity caveat instead. The pixel-identity evidence was itself blind to
  the issue: identity was measured as sha256 over decoded RGB buffers, which
  cannot see an alpha plane being dropped. NOTHING IS LOST - `approve`
  safe-copies `_firstinitial` next to `_firstdone`, verified on `258-cleanup`
  (`_firstinitial` RGBA, `_firstdone` RGB), and `9.Image Backup` holds a third
  copy - so the 15 affected slugs remain reprocessable via the reopen dance once
  the policy call lands. What was actually spent is the operator's chance to
  decide before staging, not the data.
  Next: stage-2 cleaning on the 46 (operator direction 2026-07-27).
  Cycle 10 (LEDGER 55, plan row R25) ran the last 5,
  `280f` `281-cleanup` `286f` `32-cleanup` `84f`,
  cycle 9 (LEDGER 54, plan row R24) ran
  `270f` `272-cleanup` `274f` `276f` `277f`,
  cycle 8 (LEDGER 53, plan row R23) ran
  `261f` `262f` `264-cleanup` `266f` `269f`,
  cycle 7 (LEDGER 52, plan row R22) ran
  `239f` `245f` `254f` `258-cleanup` `259f`,
  cycle 6 (LEDGER 51, plan row R21) ran
  `219-cleanup` `221-cleanup` `225f` `229f` `230-cleanup`,
  cycle 5 (LEDGER 50, plan row R20) ran
  `186-cleanup` `190-cleanup` `193-cleanup` `196f` `209-cleanup`,
  cycle 4 (LEDGER 49, plan row R19) ran
  `150-cleanup` `153-cleanup` `170-cleanup` `177-cleanup` `180-cleanup`,
  cycle 3 (LEDGER 48, plan row R18) ran
  `123f` `124f` `127-cleanup` `134-cleanup` `14-cleanup`, cycle 2 (LEDGER 47,
  plan row R17) ran `105-cleanup` `106-cleanup` `107-cleanup` `110-cleanup`
  `122`, and all five took 5/5 G1 PASS with an empty reasons list. That is the
  R16 fix measured in production over 45 consecutive slugs: cycle 1 FLAGGED on
  halo, cycles 2-10 flag nothing. Cycles 3-10 also MEASURED the pixel-identity
  claim (sha256 over the decoded RGB buffers per pair) instead of inferring it
  from equal dimensions; the PNG bytes otherwise differ only because SUBMIT
  re-encodes, and cycle 5's `186-cleanup` is the only RGB output so far to
  SHRINK on that re-encode rather than grow. Cycle 7's two big shrinks are a
  different mechanism entirely - see `first-pass-alpha-letterbox` below.
  Probe notes for the next cycle: the audit block
  is NOT at manifest top level - it is `transitions[i].audit` for the
  `ANNOTATE` transition, and a top-level read silently returns empty for every
  field. `manifest.json` carries no `state` key at all; state/substate is
  derived from the filesystem by `scan_tree`, and `lw_pipeline.Ctx()` takes the
  IMAGES dir, not the project root - passing the project root scans 0 images
  and returns a silent all-zero result rather than an error.
  All 46 processed slugs sit at
  `FIRST_SCRATCH/NEEDAUTH` - approval is operator-only and is the real queue.
  Cycle 1 proved the chain on slug `0`
  (`_firstneedauth`, G1 FLAG on halo only, LEDGER 45) and corrected the premise:
  all 46 `_firstinitial` files are EXACTLY 2560x1440, so every slug takes the
  `downscale-only` branch at scale=1, no resample happens, and the unsharp mask
  was the ONLY operation first pass applied to this batch. The AI upscaler is
  not exercised by these 46 at all (model load verified separately: spandrel DAT
  scale 4, torch 2.11.0+cu128, RTX 5070). Director decision B (LEDGER 46, plan
  row R16) fixed it at the cause: no resample, no unsharp mask. First pass is now
  a provenance-only passthrough for an already-at-target source - measured live
  on slugs `0` and `105-cleanup`, halo_pct 0.0711 -> 0.0 and lap_ratio 1.965 ->
  1.0, output pixel-identical to the source. A genuine over-target downscale
  (e.g. 4K -> 1440p) still gets its USM; the skip is keyed on the exact-target
  size, NOT on `scale == 1`. The 47/61 downscale-only halo flags in
  `project-first-pass-recipe-validated` stay an open watch - those DID resample.
  Then route them to stage-2 cleaning - 35 were
  gate-flagged (13 auto / 22 qa) and 11 were held on manual OCR review, so
  the watermark work happens at `3.Cleaning Scratch`, NOT before first pass.
  Recovery waterfall is still OWED for this set: every manifest carries
  `source_url: null` (Tier 0/1/2 deliberately skipped at operator direction),
  and 112 of the novel refs are still source-recoverable.
  Evidence: LEDGER 35 + 36 (63cc35b, 3b8e0f1); per-file verdict + reason
  table in `docs/refs_cleaning_queue.md`.
  Do-not-redo: the 226 clean refs are already delivered to Pictures as
  `ref_*.png` (sha-verified) - do not re-triage or re-copy them. If any of
  the 112 recoverable ones later gets restored, REMOVE its raw `ref_*` copy
  from Pictures or rotation gains a near-duplicate.

- **batch20-first-pass - FIRST PASS DONE 2026-07-30; 17 slugs sit at NEEDAUTH
  awaiting operator approval, 3 are HELD.**
  Next: operator approves or rejects the 17 (`lw_pipeline.py approve|reject`);
  approval is operator-only by design. Result: 10 PASS, 7 FLAG, 0 FAIL, 3 HELD.
  All 7 flags are the SAME reason - `halo_pct` over the 0.05 line, 0.0567 to
  0.1196 - and that is now measured and explained, see `usm-halo-calibration`
  at the top of this file. This batch DID exercise the AI upscaler (16 of 17
  took `upscale-4x`), unlike the 46 refs which were all exactly 2560x1440 and
  took the passthrough branch - which is exactly why this batch flags and that
  one did not.
  The 3 HELD are `puppet-master-syndra` and both `spirit-blossom-vayne` slugs,
  all on `aspect_crop_heavy` (area loss ~0.156 vs the 0.08 `AREA_LOSS_MAX`
  cap). They are annotated, never upscaled, and still EDITING. Crop policy is
  product direction and was NOT decided unattended - that ruling is owed.
  Intake + recovery ran 2026-07-29: Tier 0 `no_match` for all 20 (every one
  novel), Tier 1 decoded a DeviantArt token for all 20 and gallery-dl fetched
  all 20 at the quota-free setting. 8 of 20 gained real pixels, best
  `blood-moon-priestess-mel` 1159x689 -> 1920x1142 (2.75x); the other 12 held
  pixel count but shed 6-7x of JPEG compression.
  Do-not-redo: `original: true` on DeviantArt (weekly quota; the intermediary
  path already measured a gain and costs none); re-intaking a fetched fullview
  through `0.Originals` (re-slugging diverges the slug - `lw_first_pass`
  selects by convention path instead).
  Evidence: `PIPELINE_LOG.md` 2026-07-30T12:0x-12:17Z block; per-slug audit at
  `transitions[i].audit` for the ANNOTATE transition; LEDGER 61.

- **first-pass-alpha-letterbox - first pass silently drops the alpha channel,
  and G1 is blind to it - OPEN (found cycle 7, LEDGER 52, plan row R22;
  widened by cycle 8, LEDGER 53, plan row R23; sub-shape B identified by
  cycle 9, LEDGER 54, plan row R24; CENSUS CLOSED by cycle 10, LEDGER 55, plan
  row R25; audit hygiene SHIPPED by cycle 11, LEDGER 56, plan row R26;
  SUB-SHAPE B RULED by the operator 2026-07-29 - ACCEPT AND RECORD, change no
  pixels; SUB-SHAPE A's policy call is still open).**
  **STILL OPEN AND NOW POST-APPROVAL.** All 46 were approved on 2026-07-27
  without this ruling - see the miss recorded under `refs-46-first-pass`. That
  does not close it and does not lose anything: every `_firstinitial` is
  preserved RGBA beside its RGB `_firstdone` in `2.First Pass Done` and again in
  `9.Image Backup`. It does change the shape of acting on it - a ruling that
  says "keep the alpha" now needs the reopen dance for the affected slugs
  instead of a re-run before staging. Rule on it BEFORE stage-2 cleaning, since
  cleaning writes on top of `_firstdone`.
  The census is now complete over all 46 refs, so the numbers below are final
  rather than a running tally: FIFTEEN of the 46 are RGBA with a genuinely
  non-opaque alpha, 31 are RGB, none is any other mode. Cycles 8 and 9 both
  came back 5-for-5 RGBA, which read as "most of the corpus"; cycle 10 came
  back 3 of 5 and the full sweep settles it at 15 of 46, so this is a common
  shape but a minority one. Final shape histogram over the 15: sub-shape B 1px
  rim x8, sub-shape A hairline letterbox x4, the B left/right-column variant
  x2, and `258-cleanup`'s 160-row letterbox alone x1. The alpha PLANES collapse
  to only five distinct bitmaps (sha256-16 `2d01a0afce742e26` x8,
  `4be64a25a2e1d11c` x4, `f47a60870653b036` x1, `8d42f440f08f26d0` x1,
  `03a55dd42770d45d` x1), so three of them account for 14 of the 15 files -
  export-toolchain provenance, not per-image chance. That matters for the
  policy call: ONE ruling on sub-shape B disposes of 10 of the 15 files, and a
  second on sub-shape A disposes of 4 more. Two DISTINCT sub-shapes:
  Sub-shape A - a fully transparent (alpha=0) full-width top/bottom letterbox
  whose underlying RGB is already pure black: `258-cleanup` rows 0-79 +
  1360-1439 (160 rows, 11.11 percent of the frame - the actual artwork is
  2560x1280, an exact 2:1 plate letterboxed into a 16:9 canvas), and a 3px
  hairline `[0-2]` + `[1437-1439]` (6 rows, 0.4167 percent) on `259f`, `261f`,
  `262f` and `264-cleanup` - four slugs with byte-identical bar geometry, so
  the hairline is a shared authoring or export artifact, not per-image chance.
  Sub-shape B (found cycle 8, IDENTIFIED cycle 9) - PARTIAL translucency with
  no transparent row at all, and it is a 1-PIXEL OUTER BORDER RIM, not the
  scattered anti-aliased band cycle 8 read it as. Cycle 9's five slugs plus
  cycle 8's `269f` each measure alpha min=220 max=255, ZERO fully transparent
  pixels, and exactly 7996 non-opaque pixels = `2*2560 + 2*1440 - 4`, the frame
  perimeter, with a 100 percent opaque interior. Cycle 8's `266f` measures
  2880 = `2*1440`, the same rim with only the left/right columns. Cycle 9's
  five alpha planes are `np.array_equal` BIT-IDENTICAL to one another (plane
  sha256-16 `2d01a0afce742e26`), so this is one export-toolchain artifact
  stamped across many files rather than per-image chance - cycle 10's `280f`
  and `286f` carry that same plane hash, making it 8 files on one bitmap.
  One dent in the taxonomy, from cycle 10: `281-cleanup` is a 2880
  left/right-column rim like `266f`, but its alpha min is 218, not the 220
  every other rim carries, and its plane hash (`03a55dd42770d45d`) matches
  nothing else. Its plane's value histogram is exactly `{218: 1440, 222: 1440}`
  - one column at 218, the other at 222, no 220 anywhere in the file, so its
  two columns are not even equal to each other. "alpha min 220" is a strong
  regularity, NOT an invariant - any detector written for this must not
  hard-code it. Nothing is
  letterboxed here; the alpha is simply discarded. The item name understates it
  - the general defect is an unannounced RGBA -> RGB flatten.
  First pass writes RGB, so sub-shape A bars bake to pure black (verified max
  AND min channel value 0) and the file shrinks ~40 percent on the alpha drop -
  the only reason this was noticed at all. Every cycle-8 output shrank
  (-39.7 to -42.1 percent) and every cycle-9 output shrank (-40.6 to -43.3
  percent) for exactly this reason, which is a different mechanism from cycle
  5's `186-cleanup` RGB re-encode shrink.
  The gap: G1 compares RGB only, so black-vs-black under alpha=0 scores a
  perfect 1.0 and a letterboxed source is structurally invisible to the gate.
  `aspect_class=ok` on `258-cleanup` is satisfied by the transparent bars, not
  by the artwork, so it would approve as a 2560x1440 wallpaper with an 80px
  black bar top and bottom. Sub-shape B is invisible to the gate for the same
  reason and has no aspect consequence at all - the composite over an opaque
  background is unchanged, so it may well be acceptable as-is.
  Decide the POLICY before writing any detector, and decide it PER SUB-SHAPE.
  **SUB-SHAPE B IS RULED (operator, 2026-07-29): ACCEPT AND RECORD.** The
  flatten is recorded in the audit and NO pixels change - a 1px perimeter rim
  (or a left/right-column variant) has no consequence composited over any
  background, which is what the cycle-9 rim measurement established. That
  disposes of TEN of the fifteen files (the 8 full-perimeter rims on plane hash
  `2d01a0afce742e26` plus the 2 left/right-column variants, `266f` and
  `281-cleanup`), and it needs no reopen dance: their already-approved
  `_firstdone` files stand as-is and go straight to stage-2 cleaning. Recording
  for the ten is the `alpha_flattened` + `source_mode` field shipped in cycle 11
  (`ef67c49`), which those ten predate - so their record lives in this ROADMAP
  entry and the LEDGER, not in their own manifests, and that is the accepted
  cost of ruling post-approval rather than a reason to re-run them.
  **SUB-SHAPE A IS STILL OPEN** and still blocks its five slugs: for A, crop to
  the content box and re-run the aspect logic against that, re-source a
  full-bleed original, or accept the bars as authored intent. A wrong automatic
  answer is worse than the current queue, so those five (`258-cleanup` with the
  160-row letterbox, plus the 3px-hairline four `259f` / `261f` / `262f` /
  `264-cleanup`) stay held ahead of cleaning. Nothing downstream is blocked for
  the other ten; this is a correctness hole in the audit, not a gate.
  Cheapest first step, and it needs no policy call: DONE cycle 11 (LEDGER 56,
  plan row R26, commit `ef67c49`). `first_pass` now reads the source PIL mode
  off the existing probe BEFORE any `convert("RGB")` and records `source_mode`
  + `alpha_flattened` in `upscale_audit`, so every future run self-reports the
  drop instead of leaving a file-size anomaly as the only tell.
  `alpha_flattened` is True for palette-with-transparency sources too, not
  just mode RGBA - a `P` + `tRNS` source flattens identically and would
  otherwise read clean. NOTE the 15 already-processed refs predate the field
  and carry no such key; their flatten is documented here, not in their
  audits. The "scan the remaining unprocessed refs" step is DONE (cycle 10
  swept all 46); what is still owed is the POLICY call itself (per sub-shape),
  and the note that the same blindness applies to any future letterbox in a
  solid non-black colour, where the RGB metrics would ALSO score clean.

- **iopaint-batch-drain - Stage-2 watermark batch reprocess - IN PROGRESS, and
  the NEXT SESSION'S focus (operator direction 2026-07-27).** The 46 refs
  approved this session join this queue. `first-pass-alpha-letterbox` is now
  PARTLY ruled: sub-shape B (10 slugs) is ACCEPT-AND-RECORD as of 2026-07-29 and
  is CLEARED for cleaning; sub-shape A (5 slugs - `258-cleanup` `259f` `261f`
  `262f` `264-cleanup`) is STILL HELD, because cleaning writes on top of
  `_firstdone` and a later "crop to the content box" ruling would mean redoing
  cleaning as well as first pass for those five. Clean the other 41 freely.
  Next: land the 3 pass-improvements from the triage (full-width banner band;
  chroma-thr ~12 default; namakx template-mask / adaptive dark_thr) -> re-run
  the worker over the 9 CLEAN-AUTO + cleared PARTIALs -> `save-working --tool
  iopaint` + submit needauth -> route fantasy-design + prestige-coven-xayah
  (+ fury-sona if fidelity demands) to the manual IOPaint lane -> clean-scan
  the 190 clean firstdones + dark-cosmic-ahri + the 14 uhdpaper firstdones
  landed 2026-07-18 (LEDGER 32 session) (G3 Haiku 2AFC + V3denoise
  halftone alt stay gated on the vision stage).
  Evidence: LEDGER 30 (bc5fc19) + `docs/research/IOPAINT_TRIAGE.md` (9 auto /
  7 partial / 2 manual); manual-lane launch cmd in
  `docs/research/CLEANING_INPAINT.md` + `.claude/commands/cleaning-pass.md`.
  Do-not-redo: Dekel / pure algebraic (LEDGER 29 measured cap); white-only
  masks (mask MUST cover the dark edge).

- **g1-dists-cap-ratify - ratify the FR common-scale pixel budget - OPERATOR-GATED.**
  Next: ratify `MAX_COMMON_PIXELS` (3840x2160) as ADR-007, or set a different
  value. Shipped and documented, but it changes the G1 measurement basis
  corpus-wide (ADR-006-scale), so the value itself is an operator call.
  Evidence: LEDGER 32 (b14b688); `docs/research/AUDIT_GATES.md` 1.2 point 6
  (budget, rationale, proven-good ceiling 4096x2306 = 9.4 MPix).
  Do-not-redo: native-8K DISTS (measured impossible on this box, both devices).

- **golden-sec6-ratify - GOLDEN_DEFINITION sec 6 Q1-Q4 - OPERATOR-BLOCKED.**
  Next: operator ratifies glasses shape / style-band steer / dodge lane /
  scorecard. Champion labels already DONE.
  Evidence: LEDGER 17 (open questions) + LEDGER 18 (labels done).

- **resource-4-messups - re-source 4 ingest messups - MANUAL (NOW).**
  Next: drop clean 1920x1080+ Battle Academia splashes for `xayah1` /
  `camille1` / `kaisa1` / `fiora1` into `0.Originals` + re-intake (originals
  are 1920x1173 with a ~210px foreign strip pasted on top). Fallback only if
  the manual grab is skipped: bottom-anchored crop -> ~1712x960 -> ~1.5x
  upscale (lossy; not preferred).
  Evidence: operator ruling 2026-07-07 (LEDGER 13); Tier-0 pHash found no
  local twin (423-file corpus), no source token for auto-fetch.

- **corpus-crop-redo - 3 slugs crop + reprocess - LATER.**
  Next: #115 Hwei / #247 Shyvana / #253 Soraka - champion label correct,
  crop the leftover top artifact, then reprocess.
  Evidence: `docs/research/corpus/CROP_REDO_QUEUE.md`.

- **g1-lpips-downscale-watch - downscale-only lpips threshold - LATER (watch).**
  Next: only if more synthetic-8K downscales trip a spurious `lpips > 0.2`
  FAIL, calibrate a downscale-only lpips threshold (ADR-006-style ruling).
  One datapoint so far - not actionable.
  Evidence: `elise-8k` operator force-submit + approve 2026-07-07 (LEDGER 12
  session).

## Open items - Medium priority

- **autonomy-phases-bc - promote autonomy per calibration ladder - LATER.**
  Next: after the Phase A shadow window accumulates >= 50 operator-reviewed
  images, promote per the ladder. Never skip the ladder.
  Evidence: `docs/RESTORATION_PLAN.md` section 5.

- **shareability-packaging - package the process as the deliverable - LATER.**
  Next: package pipeline code, gate ladder, rubric, golden-set protocol,
  manifests - never the cleaned third-party images. Prereq: licensing
  re-check on detector/LaMa weights.
  Evidence: `docs/RESTORATION_PLAN.md` section 9.

- **arm-scheduled-tasks - register the LW-* roster - OPERATOR-GATED.**
  Next: register `LW-Supervisor` / `LW-GeminiAudit` / `LW-WeeklyHygiene` /
  `LW-CIWatchdog` ONLY on explicit operator direction; same gate for the
  deep-audit program (DORMANT).
  Evidence: `docs/OPERATIONS.md` + `docs/DEEP_AUDIT_CHARTER.md`.

## Status at a glance

Live status is intentionally NOT duplicated here - a static table goes stale.
Sources of truth:

- Pipeline state: `ops/runtime/pipeline_state.json` (written by
  `tools/lw_pipeline.py`; viewed via lw_monitor at `127.0.0.1:8901`)
- Transition history: `PIPELINE_LOG.md` (project root, append-only, gitignored)
- Process, pid, alive flag: `ops/runtime/health.json` (producer still TBD)
- Daily log: `logs/YYYY-MM-DD.log`
- Scheduled tasks: `Get-ScheduledTask -TaskName "LW-*" | Select TaskName, State`
  (expected result today: none - nothing is registered yet)

---

## Cross-cutting principles (never violate)

- **Frozen files** - see CLAUDE.md. Explicit operator sign-off required for any
  change. (The frozen list is currently EMPTY - files earn freeze status as the
  product stabilizes.)
- **Atomic writes only** - `tmp.write_text(...); tmp.replace(target)`.
- **`py_compile` before restart** - syntax errors crash silently under `pythonw.exe`.
- **Restart via `restart_trigger.txt`** - never `Stop-Process`; `taskkill /F /PID`
  for hard kills.
- **7-bit ASCII only** in authored content - no em/en dashes, no smart quotes.
- **Do not build blind** - product-shaping choices need an ADR or an explicit
  operator directive first.
- **Never double-resample** - one AI upscale, one Lanczos down, one light USM
  (the v1 softness bug, structurally banned by ADR-002).
- **Never touch `images/` content in tests or git** - tests use tmp_path;
  `images/**` gitignored except the .gitkeep skeleton.
