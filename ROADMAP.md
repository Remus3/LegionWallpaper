# Legion Wallpaper - Roadmap

_Now + Next only. Highest priority at the TOP. Full history in `docs/history_notes.md`. Aspirational in `BACKLOG.md`._

---

## Open items - High priority

_Shipped/closed entries move to `docs/LEDGER.md` (append-only). Only open/in-flight work stays below, highest priority first._

- **lw-gen: M0 FOUNDATIONS then M1 weapon pass (NOW - next session).** Golden
  rubric v1.1 + M0-M4 path SHIPPED (LEDGER 17, commit b12ef46) - do NOT redesign;
  build per `docs/research/GOLDEN_DEFINITION.md` sec 4 + `golden_designs/VERDICTS.md`.
  M0 (TDD): (a) config flip model_path -> animagine-xl-4.0 + steps 28 + the
  manifest[model] rule; (b) shared `tools/lw_gen_pose.py` (candidate-side
  detect_poses, 512-resize preprocessing, None/negative-coord sentinels) + the ONE
  operator recall gate (contact sheet, >= 5/6); (c) plan-B lanes if the gate fails;
  (e) manifest cand[file] contract (raw -> _wfix -> _repair -> _finish + stage
  field). Then M1 weapon pass (W1-W4 escalation + corpus dodge lane).
  OPERATOR-BLOCKED in parallel (do not wait on it for M0): ratify sec 6 Q1-Q4
  (glasses shape / style-band steer / dodge lane / scorecard) + champion labels in
  `docs/research/corpus/CHAMPION_UNKNOWNS.md` (78 unknowns + 44 hedged).

- **Re-source the 4 ingest messups - MANUAL (NOW).** `xayah1`, `camille1`,
  `kaisa1`, `fiora1` (1920x1173, a ~210px strip of a different image pasted on
  top; the clean Battle Academia splash below is ~1920x960). Operator ruling
  2026-07-07: re-source a clean full 16:9 splash, crop only if that fails.
  Tier-0 pHash found NO local twin (423-file corpus) and there is no source
  token for an auto-fetch, so PARKED for a manual grab (these are identifiable
  Battle Academia splashes - drop a clean 1920x1080+ into `0.Originals` and
  re-intake). Fallback if you skip the manual grab: bottom-anchored crop off the
  strip -> ~1712x960 -> upscale ~1.5x (lossy; not preferred).

- **Possible G1 downscale-only lpips calibration (LATER, watch).** `elise-8k`
  FAILed on `lpips 0.224 > 0.2` for a visually-clean 8K downscale; operator
  force-submitted + approved it 2026-07-07. If more synthetic-8K downscales trip
  the same spurious lpips fail, calibrate the downscale-only lpips threshold
  (analogous to the ADR-006 lap_ratio ruling). One data point so far - not yet
  actionable.

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
