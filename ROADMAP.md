# Legion Wallpaper - Roadmap

_Now + Next only. Highest priority at the TOP. Full history in `docs/history_notes.md`. Aspirational in `BACKLOG.md`._

---

## Open items - High priority

_Shipped/closed entries move to `docs/LEDGER.md` (append-only). Only open/in-flight work stays below, highest priority first._

- **dark-cosmic approve + G0 over-target source-gate (NOW).** V3 detail DAT2 is
  now the PRIMARY first-pass upscaler (ADR-004; LEDGER item 5): the golden set
  was re-frozen at n=12 on V3 (pv 6d43a6d4; added a JPEG-artifact + a banding
  defect case), thresholds unchanged and holding, all 12 cases PASS with zero
  flags. `dark-cosmic-ahri-by-pebano1-dlnxav6-pre` was reprocessed from its
  recovered Tier-0 source (`Pictures/288.png`, 2560x1440, pHash dP=4) and now
  sits in `_firstneedauth` awaiting `lw_pipeline approve`. New gap surfaced while
  widening: first-pass 4x-ing sources already >= 2560w is wasteful and scores as
  false-soft (the common-scale rule upscales the 1440p output back to native res
  to compare) - add a G0 source-gate that routes over-target sources onto a
  downscale-only path instead of the AI upscale. The G3 Haiku side-by-side "win
  or tie" check stays a documented TODO gated on the vision-audit stage.

- **API keys + recovery campaign (NEXT, time-sensitive).** Register the
  SauceNAO API key and the DeviantArt OAuth app (`API-Key-*.txt` convention),
  then run the Tier 0/1 source-recovery campaign EARLY - DeviantArt's
  2026-03-09 download clampdown signals more anti-scraping moves coming
  (`docs/RESTORATION_PLAN.md` section 8). Cache everything. Backlog is real
  now: 149 pending intake incl a ~75-file `niphrimit` `-pre` batch dropped
  2026-07-04, all previews needing Tier-1 fullview recovery; plus the parked
  `dark-cosmic-ahri-...-pre` (Tier0 -> 288.png 1440p, Tier1 -> deviation
  1309974594). The Found corpus (Desktop\Found, 121 folders) already supplies
  21 real originals - 97 entries there are still `-pre` and need true originals.

- **Monitor polish (NEXT).** lw_monitor (127.0.0.1:8901) tracks the pipeline
  via `ops/runtime/pipeline_state.json`; polish pass once real pipeline runs
  produce state: thumbs roots, stuck thresholds, Desktop shortcut per
  `docs/research/LW_MONITOR_SPEC.md` section 8.

## Open items - Medium priority

- **Autonomy phases B/C (LATER).** After the Phase A shadow window
  accumulates >= 50 operator-reviewed images: promote per the calibration
  ladder (`docs/RESTORATION_PLAN.md` section 5). Never skip the ladder.

- **Shareability packaging (LATER).** The process is the public deliverable
  (pipeline code, gate ladder, rubric, golden-set protocol, manifests) -
  never the cleaned third-party images. Prereq: licensing re-check on
  detector/LaMa weights (queued in `docs/RESTORATION_PLAN.md` section 9).

- **Artist-signature keep/remove policy (operator decision, queued).** Until
  ruled, signature-flagged files route to the human QA queue - never
  auto-inpainted.

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
