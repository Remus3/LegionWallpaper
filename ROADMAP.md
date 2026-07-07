# Legion Wallpaper - Roadmap

_Now + Next only. Highest priority at the TOP. Full history in `docs/history_notes.md`. Aspirational in `BACKLOG.md`._

---

## Open items - High priority

_Shipped/closed entries move to `docs/LEDGER.md` (append-only). Only open/in-flight work stays below, highest priority first._

- **Bucket C source recovery (NOW).** 8 held first-pass slugs are sub-resolution -
  even a perfect 16:9 crop lands < 2560w, so cropping cannot deliver; route each to
  the source-recovery waterfall, reject only if recovery fails (operator ruling
  2026-07-07). Splits by source shape: (C1) 4 DeviantArt `-pre`
  (`darius-...-vexxsoul`, `fantasy-design-...-aivio`, `fury-tempest-sona-...`,
  `victorious-syndra-...`) - lever is the deferred per-image `original=true` 4K
  gallery-dl escalation (quota-costed); (C2) 2 already-`-fullview`
  (`inkshadow-yone-...` 1024w, `ashe-...-nortonki` 900w) - DeviantArt already maxed,
  only SauceNAO/other-source or reject; (C3) 2 manual-named (`mfortune1` 1920x887,
  `wp11960522-...-vayne` 2560x1920 4:3) - Tier-0 pHash vs Pictures + Desktop/Found.

- **Re-source the 4 ingest messups (NOW).** `xayah1`, `camille1`, `kaisa1`,
  `fiora1` REJECTED out of needauth 2026-07-07 - composite source has a second
  image strip bleeding behind the intended image (top edge); NOT a process fail.
  Re-crop the source top-off + re-intake (converges with the bucket-C crop/recovery
  refactor).

- **Cleaning pass downstream (LATER).** dark-cosmic-ahri + the approved first-pass
  set flow to Stage-2 cleaning (`/cleaning-pass`). The G3 Haiku side-by-side "win
  or tie" check + the V3denoise per-image halftone alternative stay documented
  TODOs gated on the vision-audit stage.

## Open items - Medium priority

- **Autonomy phases B/C (LATER).** After the Phase A shadow window
  accumulates >= 50 operator-reviewed images: promote per the calibration
  ladder (`docs/RESTORATION_PLAN.md` section 5). Never skip the ladder.

- **Shareability packaging (LATER).** The process is the public deliverable
  (pipeline code, gate ladder, rubric, golden-set protocol, manifests) -
  never the cleaned third-party images. Prereq: licensing re-check on
  detector/LaMa weights (queued in `docs/RESTORATION_PLAN.md` section 9).
- **Arm the audit/hygiene scheduled tasks (operator-gated).** The standard
  roster (`LW-Supervisor`, `LW-GeminiAudit`, `LW-WeeklyHygiene`,
  `LW-CIWatchdog`) stays documented in `docs/OPERATIONS.md`, NOT YET
  REGISTERED, until the operator explicitly directs it. Same gate for the
  deep-audit program (`docs/DEEP_AUDIT_CHARTER.md` - DORMANT).

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
