# Legion Wallpaper - Roadmap

_Now + Next only. Highest priority at the TOP. Full history in `docs/history_notes.md`. Aspirational in `BACKLOG.md`._

---

## Open items - High priority

_Shipped/closed entries move to `docs/LEDGER.md` (append-only). Only open/in-flight work stays below, highest priority first. Sequencing for the next 2-4 weeks: `docs/ATTACK_PLAN.md`. Item grammar: id - title - state - next action - evidence link._

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

- **f1-phase6-queue - 12 follow-ups from the sdk-channel migration - NEXT (joint with RC).**
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
  Next: land 5a + 9 jointly with RC (byte-identical shared files, needs re-sync).
  Evidence: LEDGER 40; `docs/specs/2026-07-26-f1-sdk-executor-channel.md`.

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

- **refs-46-first-pass - process the 46 intaken reference_pictures - NEXT.**
  Next: first pass the 46 slugs now staged in `1.First Pass Scratch` (intaken
  2026-07-18, LEDGER 36), then route them to stage-2 cleaning - 35 were
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

- **iopaint-batch-drain - Stage-2 watermark batch reprocess - IN PROGRESS.**
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
