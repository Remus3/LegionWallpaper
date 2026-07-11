# Legion Wallpaper - Roadmap

_Now + Next only. Highest priority at the TOP. Full history in `docs/history_notes.md`. Aspirational in `BACKLOG.md`._

---

## Open items - High priority

_Shipped/closed entries move to `docs/LEDGER.md` (append-only). Only open/in-flight work stays below, highest priority first._

- **lw-gen: M1 weapon pass - localizer decision (NOW - next session).** M0
  foundations + M1 slices 1-2 SHIPPED (LEDGER 18: config Animagine flip a934243;
  pure mask geometry 693920f; raw-pose->kp_map adapter e5bcdc5; recall gate PASSED
  6/6). Localizer exploration done + settled: OpenPose wrist = 1/4 on stylized art,
  CLIP mask-validator DEAD, ControlNet skeleton-reuse NOT viable (drift) - so
  operator-in-the-loop is the accepted design (no unattended auto-inpaint). NEXT,
  in order, same session: (1) try **SDPose-Wholebody** as the auto-suggestion
  localizer (github T-S-Liang/SDPose-OOD, HF teemosliang/SDPose-Wholebody; SD v2
  prior, 71 AP HumanArt); acceptance = clearly beat OpenPose's 1/6 wrist-on-weapon
  (target >= 4/6) on the 6 `images/_gen_scratch/recall_gate/` samples. (2) if it
  misses, a **DWPose onnxruntime-CPU spike** (pip install onnxruntime + ~343MB:
  yolox_l.onnx + dw-ll_ucoco_384.onnx - operator approval needed for the download).
  (3) if BOTH miss, a SEPARATE later session builds the **manual IOPaint lane**
  (keypoints suggest ROI -> operator confirms/redraws -> SDXL diffusion inpaint on
  the confirmed mask + hard outside-mask identity assert + re-QA via the cand[file]
  contract). REUSE `tools/lw_gen_weaponfix.py` (mask geometry + adapter) - do NOT
  rebuild slices 1-2.

- **OPERATOR-BLOCKED: ratify `GOLDEN_DEFINITION.md` sec 6 Q1-Q4** (glasses shape /
  style-band steer / dodge lane / scorecard). Champion labels are DONE this session
  (LEDGER 18) - only the sec-6 ratifications remain.

- **Corpus crop-redo (LATER).** `docs/research/corpus/CROP_REDO_QUEUE.md` - #115
  Hwei / #247 Shyvana / #253 Soraka: champion label correct, image has a leftover
  top artifact to crop + reprocess.

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
