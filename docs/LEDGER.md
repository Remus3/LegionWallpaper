# Legion Wallpaper - Item Ledger

Append-only, newest-first per-item completion record. Kept OUT of `CLAUDE.md`
by design (CLAUDE.md has a hard per-turn auto-load size budget - never append
ledger entries there). Do not rewrite history - append each new item at the TOP
of the body below (newest-first, directly under the `---` rule), matching the
entry format documented here.

**Entry format** (one numbered block per completed item, numbering starts at 1
and only ever increases):

```
N. DONE **YYYY-MM-DD (short title; commit SHAs or "docs-only").** Body: what
   shipped, premise verification, how it was built (TDD RED-first evidence,
   worktree slices, verifier verdict), what was verified (suite counts, health
   checks), doc/roadmap syncs, and any FUTURE / do-not-redo notes.
```

Conventions carried from the format's origin: bold date+title lead; premise
VERIFIED/CORRECTED called out explicitly; verification evidence (test counts,
exit codes, health probes) stated, never implied; scope calls and rejected
alternatives logged so they are not re-litigated.

Pointers: open work -> `ROADMAP.md` + `BACKLOG.md`; recent sessions ->
`WAKEUP_NOTES.md`; pruned ledger items + archived wakeups ->
`docs/history_notes.md`; decisions -> `docs/adr/`.

---

3. DONE **2026-07-04 (QA Session 2 - IllustrationJaNai primary path + frozen G1
   gate + manifest annotate verb; commit dca6071).** Established the IJN
   (4x_IllustrationJaNai_V1_DAT2_190k, spandrel/torch) first-pass upscaler as the
   PRIMARY path and froze the G1 gate on it. **Derisked live before building:**
   downloaded the V1 DAT2 weights from OpenModelDB (Google-Drive large-file
   confirm-token dance; the file is a zip bundle - extracted the .pth + an ESRGAN
   cross-check model to `tools/models/`, gitignored), spandrel loads it as
   arch=DAT scale=4, CUDA forward pass on the RTX 5070 green. **Built (TDD,
   subagent slices, CI-safe: numpy/Pillow/stdlib tests run in CI, torch/pyiqa/
   spandrel use pytest.importorskip):** `tools/lw_upscale.py` (spandrel + ncnn
   backends, mandatory tiling - seam validated exact on real torch, maxdiff 0.0
   incl odd sizes; one 4x + one Lanczos to 2560x1440 + one capped USM; atomic PNG
   + audit dict); `tools/lw_g1_gate.py` (pure-numpy laplacian ratio, the REAL
   overshoot detector - near-edge pixels outside the source local min/max range =
   USM ringing, replacing the crude edge-diff proxy - banding delta, lazy pyiqa
   common-scale FR, pure-stdlib verdict); `tools/lw_pipeline.py` `annotate` verb
   (records source_url + G1 metrics into manifest.json atomically; closes the
   spawned task_fb503c0a gap). **Ran the 10 approved first-pass images through IJN
   and G1-scored IJN vs the realesrgan-anime fallback with identical code:** IJN
   wins EVERY image on MS-SSIM, LPIPS, and halo_pct (10/10 each); the fallback's
   higher laplacian ratio is RINGING (higher halo_pct), not clean detail -
   confirming the Session 1 finding that laplacian is not an over-sharpen ceiling;
   the new overshoot detector is. **Frozen thresholds (AUDIT_GATES 1.4):** msssim
   pass>=0.98, lpips pass<=0.12, lap floor>=1.0 (no ceiling), halo FLAG>0.05, and
   band_delta demoted from a fail>0 HARD FAIL to an ADVISORY FLAG>0.05 - the >0
   rule was a bug that hard-failed the BETTER upscaler 8/10 on ~0.004 noise.
   Verdicts n=10: IJN 8 PASS / 2 FLAG, fallback 1 PASS / 9 FLAG, zero hard fails.
   **Premise CORRECTED (operator ruling 2026-07-04):** the `reference_pictures/
   *_cleanup.png` files are "original-not-found" markers, NOT finished
   ground-truth - so the Session 1 "GT LPIPS vs finished ref" band is VOID
   (removed from AUDIT_GATES 1.4); G1 scores SELF-metrics only (output-vs-source),
   every corpus image still needs work. **Verified:** full suite 183 passed / 2
   skipped (147 baseline + 24 new + 12 annotate), ruff clean on all touched files,
   verifier gate re-run fresh, no weights staged (git check-ignore confirmed).
   requirements.txt gained numpy + Pillow (cheap-check + finish tests run in CI);
   .gitignore ignores `tools/models/`. **Future / do-not-redo:** venvs + the V1
   DAT2 weights are installed/downloaded + gitignored - DO NOT refetch; the 10
   images are done. NEXT: V3detail DAT2 (nicer quality; its OpenModelDB gdrive
   link was not resolved this session), widen n before treating the freeze as
   final, and a real GOLDEN SET of approved outputs (there is no ground-truth
   yet). GT-vs-approved comparison only returns once such a golden set exists.

2. DONE **2026-07-04 (QA Session 1 - first-pass stack + G1 calibration;
   docs-and-ops, ML state gitignored).** First real end-to-end pipeline runs.
   **Shipped:** ML tooling stack installed clean - py3.12 side-install,
   `.venv-upscale` (torch 2.11.0+cu128 + spandrel 0.4.2, CUDA verified on the
   RTX 5070), `.venv-metrics` (pyiqa 0.1.15, 99 metrics); gallery-dl + imagehash
   on 3.14. Ran 10 images through intake -> first-pass -> operator-approved into
   `2.First Pass Done` (1 hand-driven fiora2 + a 9-image Found-original batch),
   each with a full manifest audit trail (INTAKE/SAVE_WORKING/SUBMIT/APPROVE,
   sha-tracked). **G1 calibrated n=10** on real source->finished-ref pairs
   (upscaler = realesrgan-x4plus-anime fallback, USM70): MS-SSIM self 0.984-0.993,
   LPIPS self 0.047-0.144, GT LPIPS 0.048-0.097, laplacian 1.81-4.43. Tighter
   seed thresholds written to `docs/research/AUDIT_GATES.md` 1.4. **Premise
   CORRECTED twice:** (a) the first-chosen `-pre` source failed the G0 gate
   (sub-720p preview) - re-picked G0-valid mid-res originals; (b) `reference_pictures`
   is a FR ground-truth goldmine - `fiora2` <-> `87_cleanup.png` matched at
   pHash dP=0. **How verified:** live scans (first_done=10, anomalies=0), 10
   `_firstdone` pairs on disk, pyiqa metrics computed this run, manifests read
   back. **Gaps found:** (1) `lw_pipeline` has no verb to write provenance/G1
   metrics into `manifest.json` (source_url null; metrics only in `logs/`) -
   spawned as a background task, now a ROADMAP NOW item; (2) `save-working
   --params` needs argv (not PowerShell) JSON passing. **Findings:** laplacian
   ratio is source-dependent, NOT a usable over-sharpen ceiling - needs a real
   overshoot detector (AUDIT_GATES 3.1) or source-adaptive USM. **Future /
   do-not-redo:** venvs are installed + gitignored (`.venv-*/`); DO NOT re-run
   the installs. IllustrationJaNai primary weights still TODO (this run used the
   ncnn fallback) - recalibrate on the primary path next. Doc syncs: AUDIT_GATES
   1.4 (calibration), ROADMAP (QA Session 2 + manifest-writer NOW items),
   `.gitignore` (`.venv-*/`).

1. DONE **2026-07-03 (restoration pipeline designed + built; commit 1d3631b,
   docs-and-code).** The LW product is now defined and scaffolded: a
   staged, self-auditing image restoration pipeline (drop image ->
   recover source -> single upscale -> masked cleaning -> face/eye polish ->
   gate ladder audit -> approved 2560x1440 PNG to Pictures). Premise VERIFIED
   against the live corpus (2026-07-03 scans: ~302 processed PNGs, ~77
   scattered sources, confirmed artist-credit watermark class, no uhdpaper
   corner marks, DeviantArt token->deviation-ID decode verified live). Built
   from a five-topic research wave - `docs/research/UPSCALE_TOOLCHAIN.md`,
   `CLEANING_INPAINT.md`, `AUDIT_GATES.md`, `SOURCE_RECOVERY.md`,
   `PIPELINE_STATE_MACHINE.md` - plus `LW_MONITOR_SPEC.md`, synthesized into
   `docs/adr/ADR-002-restoration-pipeline-product.md` (product = four-stage
   pipeline + G0-G4 gate ladder + autonomy calibration ladder + toolchain:
   IllustrationJaNai/spandrel primary, ncnn fallback, LaMa inpaint,
   CodeFormer/GFPGAN hard-excluded) and
   `docs/adr/ADR-003-pipeline-folder-scheme.md` (operator's 10-folder/4-phase
   scheme verbatim + 13 additive fixes + five operator rulings incl. root =
   `C:\LegionWallpaper\images`, End Review rejection enabled, Done-N GC,
   LongPathsEnabled deferred). Operational plan rewritten as
   `docs/RESTORATION_PLAN.md` (v2), superseding the operator's v1 Desktop plan
   (archived at `docs/RESTORATION_PLAN_v1.md`). Build wave (TDD, worktree
   slices): `tools/lw_pipeline.py` (state machine, SAFE-MOVE transitions,
   manifests, atomic `ops/runtime/pipeline_state.json`), `tools/lw_monitor.py`
   (127.0.0.1:8901, tolerant reader), stage slash-commands, hygiene suite
   green (counts in each slice's report). Living docs synced: README (product
   section), CLAUDE.md (header + Settled: ADR-003 folder scheme not to be
   re-litigated), ROADMAP (NOW = QA Session 1: venvs + one image end-to-end
   via /first-pass + G1 calibration), ARCHITECTURE (pipeline component map).
   FUTURE / do-not-redo: run the DeviantArt recovery campaign EARLY (2026-03-09
   quota clampdown); artist-signature keep/remove policy is a QUEUED operator
   decision; never re-litigate the folder scheme (ADR-003); never
   double-resample; NR-IQA in delta/percentile mode only. Note: the RC
   operating-system bootstrap (2026-07-03, ADR-001) predates this ledger and
   is recorded by ADR-001 + `WAKEUP_NOTES.md`, not retro-numbered here.
