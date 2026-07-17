# Legion Wallpaper - Roadmap

_Now + Next only. Highest priority at the TOP. Full history in `docs/history_notes.md`. Aspirational in `BACKLOG.md`._

---

## Open items - High priority

_Shipped/closed entries move to `docs/LEDGER.md` (append-only). Only open/in-flight work stays below, highest priority first._

- **Stage-2 watermark cleaning: IOPaint-emulation cleaner SHIPPED; batch reprocess IN PROGRESS (2026-07-16, LEDGER 30, commit bc5fc19).**
  `tools/lw_clean_iopaint.py` auto-cleans calm-background marks faithfully (masked
  simple-lama with a COMPLETE fill + dark-edge mask; namakx proven near-clean). Busy-art
  marks (pebano-like) smear -> operator's MANUAL IOPaint lane (recovered launch:
  `& "$env:LOCALAPPDATA\Python\pythoncore-3.11-64\python.exe" -m iopaint start --model=lama --device=cuda --port=8080`,
  or `--model=Sanster/PowerPaint-V1-stable-diffusion-inpainting` for the heavier removals;
  http://127.0.0.1:8080). Dekel algebraic approach PARKED (LEDGER 29, bad25c8 - proven cap,
  dark ghost). Gate false-positives fixed (LEDGER 28, bd7521e: caitlyn / vayne3 /
  the-ruined-king-viego now KEEP, not auto-clean). **NEXT:** run the batch triage across the
  ~18 staged non-FP slugs in `images\3.Cleaning Scratch` (auto-clean the calm-bg ones ->
  save-working --tool iopaint + submit for needauth; flag busy-art for the manual lane),
  improve the passes per the triage, then clean-scan the 190 clean firstdones. **Do-not-redo:**
  Dekel / pure algebraic (measured cap); the mask MUST cover the dark edge (a white-only mask
  ghosts).

- **lw-gen: weapon pass - SHIPPED end to end + PARKED at a quality ceiling (2026-07-16, LEDGER 26).**
  Full rung ladder is wired + shipped: W1 (LEDGER 20) + W2 transplant (22) + W3 IP-Adapter (23) +
  **W4 weapon-concept LoRA (26, commit 0c255d8: real train + rung=="w4" wired/tested/e2e'd)**.
  DONE-not-open. Weapon QUALITY plateaus at a crossbow-ADJACENT mechanical device (never a
  textbook repeating crossbow) - a measured CEILING of masked-inpaint + thin-LoRA on stylized
  splash art, confirmed 5x (W2, W3, W4-v1, W4-v2, LoRA-scale sweep). Data levers are exhausted:
  the splash pool has no more clean crossbow crops, and a proven 3D geometry-render pipeline
  (docs/research/crossbow_render_poc.md) added 4 clean base renders that did NOT move the needle
  (v2 == v1). Operator PARKED it here; rung=="w4" stays available. **Do NOT re-litigate:** no
  re-run of any rung/scale, no re-mining splashes, no full 20-skin render build (all measured
  dead ends). If ever revisited, the open lever is a non-inpaint mechanism or a separating weapon
  scorer to revive `gate_mode="clip"` - NOT more crop data.

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

- **Stage-2 cleaning - PIPELINE BUILT, watermark engine IN PROGRESS (2026-07-16, LEDGER 27).**
  Harness (`tools/lw_clean_pass.py`: detect -> gate v2 -> mask -> verify) + SDXL
  reconstruction worker (`tools/lw_clean_sdxl.py`) SHIPPED (bf94629, 07b7e30);
  dedicated `C:\Tools\lw-clean\venv` provisioned. Triage of the 228: 190 clean /
  17 QA / 21 auto (watermark) slugs. BLOCKER on finishing the watermarks:
  semi-transparent watermark removal is hard - LaMa blurs content, block-SDXL
  hallucinates, glyph15+SDXL is a faithful interim with a minor dense-line smudge.
  **NEXT (fresh session): build proper Dekel** (Levin matting-Laplacian alpha +
  sub-pixel alignment + IRLS + matting-equation inversion) for zero-halo faithful
  recovery - full plan + methods-tried + do-not-redo in
  `docs/research/WATERMARK_REMOVAL_RND.md`. Then reprocess the 21 (staged in
  `3.Cleaning Scratch`) + the pebano1/vexxsoul/namakx clusters; tighten gate
  false-positives (caitlyn `@`-only, vayne3 carved-stone, the-ruined-king-viego
  LoL logo). The 190 clean + dark-cosmic-ahri still need clean-scan flow-through;
  the G3 Haiku side-by-side + V3denoise halftone alt stay gated on the vision stage.

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
