# Legion Wallpaper - Roadmap

_Now + Next only. Highest priority at the TOP. Full history in `docs/history_notes.md`. Aspirational in `BACKLOG.md`._

---

## Open items - High priority

_Shipped/closed entries move to `docs/LEDGER.md` (append-only). Only open/in-flight work stays below, highest priority first._

- **First-pass needauth queue - approve/reject (NOW).** 110 images sit in
  `_firstneedauth` (54 PASS + 56 FLAG) from the 2026-07-05 recovered-backlog first
  pass (LEDGER items 10 + 11): 49 upscale (40 PASS / 9 FLAG) + 61 downscale-only
  (14 PASS / 47 FLAG). Operator gate: `lw_pipeline approve <slug>` / `reject <slug>
  --note "<reason>"`; the LW Monitor (127.0.0.1:8901) lists them. **WATCH:** 47/61
  downscale-only flagged on halo_pct - if these read spurious in the vision audit,
  a halo-for-downscale-only calibration look is the follow-up (analogous to the
  ADR-006 lap_ratio fix). (dark-cosmic-ahri already APPROVED -> 2.First Pass Done.)

- **Crop the 10 held (NEXT).** 10 crop_heavy sources HELD (center-crop to 16:9
  loses > 8 percent): manual per-image crop, then re-run. 3 are borderline
  (`chengwei-pan-1/2`, `rey-jinn-up-2` at 0.080-0.081 loss - a hair over the cap;
  nudging `AREA_LOSS_MAX` or hand-cropping recovers them).

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
