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

11. DONE **2026-07-05 (downscale-only G1 gate ADR-006 + the 61 deferred batched; commit 7b11f21 + docs).**
   Closed the downscale-only deferral from LEDGER item 10 (operator launched the
   spawned follow-up). **Premise VERIFIED empirically (non-mutating probe, 3
   downscale-only 4K sources):** the G1 lap_ratio floor is INVALID for a no-upscale
   path - it swung 0.75 / 0.78 / 1.20 across near-identical clean downscales
   (arbitrary pass/fail; the third PASSED as spuriously as the first two FAILED)
   while msssim/lpips (0.996-0.998) + halo/band stayed meaningful. **Decision
   ADR-006 (operator ruling, option a):** for upscale backend "downscale-only" drop
   ONLY the lap_ratio floor from the G1 verdict; keep msssim/lpips + halo/band; the
   lap_ratio value is still recorded for provenance. DEFAULT_G1_THRESHOLDS untouched
   (per-path metric selection, not a recalibration); every other backend unchanged.
   **Built (TDD, inline - small well-scoped change):** a pure `gate_metrics(metrics,
   backend)` filter feeding verdict(), wired into process_slug with backend +
   lap_ratio_gated recorded in the manifest. RED confirmed (5 new tests fail, no
   gate_metrics) -> GREEN (32 passed: drops lap only for downscale-only, keeps the
   full set for spandrel, soft-lap passes, halo still flags, corrupt msssim still
   fails); ruff + ASCII clean; py_compile OK. **Ran:** regenerated the 61-slug list
   (post-crop bucket) + batched -> 14 PASS + 47 FLAG + 0 FAIL + 0 error. **Zero
   lap_ratio fails - the false-soft is gone.** **Verified:** scan anomalies=0, 0
   still-editing, needauth now 110 (49 upscale + 61 downscale-only), verify --all ok
   (131 images), full suite 275 passed / 3 skipped (was 270/3; +5). **OBSERVATION
   (open, NOT fixed):** 47/61 downscale-only FLAGGED on halo_pct (0.052-0.211).
   Flag-only (all submitted for vision audit) so conservative/safe, but the rate is
   high; a quick probe to separate real USM ringing from a common-scale
   back-upscale artifact was inconclusive (confounded by per-slug source selection).
   WATCH during the vision audit - if the flags read spurious, a
   halo-for-downscale-only calibration look (analogous to this lap_ratio fix) is the
   follow-up. **Do NOT redo:** ADR-006, the gate_metrics change, the 61-batch.
   **State:** all 120 originals first-passed - 110 in _firstneedauth (approve/
   reject), 10 crop_heavy HELD.

10. DONE **2026-07-05 (first-pass driver + recovered-backlog first-pass batch; commit 82aacc2 + docs).**
   Executed task 1 - processed the recovered source backlog through Stage-1 first
   pass. **Premise CORRECTED (ground-truth):** the WAKEUP "67 fullviews quota-capped
   ~1280px" was the DA oEmbed PREVIEW dim, not the fetched file - gallery-dl already
   pulled true fullviews (median 1440w, 19 of 68 >=2560, one 7680x4320). So the
   operator's gate-triggered original=true budget cost 0 this batch (no source
   needed it). **Two operator forks resolved:** (a) budget = gate-triggered (spend
   original=true only on G1 source-res FAILs); (b) non-16:9 conditioning = auto
   center-crop to exact 16:9 when area-loss <= 8 percent, else manual HOLD.
   **Validated the recipe live BEFORE building** (p08e8 manual chain -> G1 PASS):
   intake basename -> upscale the fetched fullview via .venv-upscale spandrel V3 DAT2
   -> save-working -> G1 (.venv-metrics FR + numpy at common scale; fr 'ms_ssim' ->
   'msssim' remap; pyiqa stdout noise -> last-json-line) -> annotate -> submit.
   **Built (subagent-first, TDD, verifier-gated) `tools/lw_first_pass.py`** -
   resumable single/batch driver: best-source selection (fetched fullview else
   _firstinitial), aspect conditioning (crop_ok <=8 percent writes a 16:9 temp
   BEFORE first_pass so _finish never raises; crop_heavy HOLDs), sequential (GPU is
   one device), CREATE_NO_WINDOW, all pipeline mutation through lw_pipeline
   (single-writer). 27 unit tests (aspect thresholds, crop math, source select, FR
   remap, verdict wiring, subprocess argv), ruff + ASCII clean; verifier
   VERIFIED-GREEN independently; live-proven on aatrox via the committed driver (G1
   PASS). **Ran:** intake --all (119 -> scratch, 0 anomalies); real-upscale batch of
   47 -> 38 PASS + 9 FLAG (halo/band, submitted for vision audit) + 0 FAIL + 0 error;
   10 crop_heavy recorded HELD. **49 total in _firstneedauth** (47 batch + p08e8 +
   aatrox) awaiting operator approve/reject. **Verified:** scan anomalies=0, verify
   --all ok (131 images, no hash mismatch), full suite 270 passed / 3 skipped (was
   243/3; +27 driver). **Deferred with cause (NOT done):** 61 downscale-only sources
   (native 8K/4K + over-2560 fullviews + crop_ok-large) - the G1 common-scale
   lap_ratio floor is INVALID for a no-upscale path (the LEDGER-7 false-soft: the
   gate upscales the 1440p output back to source res); they need distinct
   downscale-only G1 handling (skip the upscale-quality floor - a clean Lanczos
   downscale of an already-good source IS the wallpaper) before gating. **Do NOT
   redo:** the driver, the 47-batch, the 10 holds, the 2 pilots. **FUTURE
   (ROADMAP):** (1) downscale-only G1 handling + process the 61; (2) operator crop of
   the 10 held (3 borderline at 0.080-0.081 loss - a hair over the cap); (3)
   approve/reject the 49 needauth; then cleaning-pass downstream.

9. DONE **2026-07-05 (monitor polish - verified live + Desktop shortcut; docs-only).**
   Polished lw_monitor now that real pipeline_state.json exists (ROADMAP NEXT).
   **Verified live (running instance):** /api/pipeline renders the real state
   (stage 0=120 pending + stage 2=11 First-Pass-Done, 0 attention, not stale),
   /api/log tails PIPELINE_LOG, GET / serves the 9KB page - all HTTP 200; Pillow
   12.3.0 present for thumbs; the 432-line tests/test_lw_monitor.py rides in the
   243-pass suite. **Created the "LW Monitor" Desktop shortcut** per
   LW_MONITOR_SPEC section 8 (pythonw.exe tools/lw_monitor.py --open, WorkingDir
   C:\LegionWallpaper, imageres.dll,109 icon) - a machine artifact, not committed.
   **Finding (verified, not assumed):** thumbnail generation is DORMANT - no
   pipeline item carries a `thumb` field, `ops/runtime/thumbs` is absent, and
   lw_pipeline references no thumbs, so the spec's guessed thumbs-root RISK
   (`data\` / `ops\runtime\thumbs\`) is moot. Resolved it in LW_MONITOR_SPEC
   section 10: the root settled on `images/` + `--images-root`, thumb-root tuning
   deferred until a producer exists (BACKLOG). web/monitor.html confirmed 7-bit
   ASCII clean (repo hard rule). No lw_monitor.py / monitor.html change was
   warranted (the code is complete + tested + working), so the UI Fixture Ritual
   was not triggered - there was no page change to audit. **Do NOT redo:** the
   shortcut, the live verification. **FUTURE:** a thumbnail producer (writes
   `thumb` fields + populates a thumbs root) if the monitor thumbnail lane is
   wanted; then confirm/extend the thumb root + run the fixture ritual on any
   page change.

8. DONE **2026-07-05 (source-recovery campaign activated + run on 170; commit 5c2cf42).**
   Activated + ran the Tier 0/1/2 recovery waterfall against the full pending
   backlog, racing DeviantArt's 2026-03-09 download clampdown (RESTORATION_PLAN
   section 8). **Premise VERIFIED live before building:** DA OAuth resolves
   (`gallery-dl -g` on deviation 1309974594 -> EXIT 0, wixmp fullview URL); keys
   present (SauceNAO 40ch, DA 65ch); gallery-dl 1.32.5 + %APPDATA% config
   (original=false, quality=100, intermediary=true). **Built (subagent-first,
   TDD, verifier-gated fresh):** (slice A) `saucenao_search` real
   multipart/form-data image POST replacing the GET stub - params in query, file
   part, live short_remaining/long_remaining surfaced for self-throttle, public
   signature unchanged (+3 tests); (slice B) new `tools/lw_recover_campaign.py`
   driver - enumerate_targets (170 pending: 69 in 0.Originals + 101 Found
   -pre-only folders), build_corpus_hashes ((mtime,size) cache over 424
   Pictures+Found candidates), run_campaign (per-target waterfall -> tier-1
   quota-free fullview fetch -> guarded provenance annotate), annotate_via_pipeline,
   CLI run/report, all side effects injected (11 tests). **FIX (root-cause, live
   clampdown regression):** DeviantArt oEmbed now 404s on the /deviation/<id>
   redirect form (the SOURCE_RECOVERY-predicted risk landed) and requires the
   canonical /<artist>/art/x-<id> URL - title slug ignored, artist required.
   Added `parse_artist()` (from the *_by_<artist>_* filename) and rebuilt the
   oEmbed query URL; provenance URL stays the resolvable /deviation/<id> form;
   the fetch stays on authoritative gallery-dl OAuth (+3 tests). Proven live:
   oembed_liveness + run_waterfall resolve a real target to tier 1. **Verified:**
   suite 243 passed / 3 skipped (was 226/3; +3 saucenao +3 artist/oembed +11
   campaign, all CI-runnable, network injected), ruff clean, direct + `-m` CLI
   both run. **Full run (170/170, 0 errors):** 102 Tier-0 local pHash matches,
   67 real DeviantArt fullview fetches (quota-free, verified real JPEGs ~1280px),
   1 SauceNAO (Pixiv source, dead deviation), 0 manual-queued; a live SauceNAO
   probe confirmed the parsed shape + quota (long_remaining=94). Provenance
   annotated via `lw_pipeline annotate` on the two manifest-bearing slugs
   (dark-cosmic-...-pre + inkshadow-kai-sa-...-fullview); loose targets record
   provenance in data/recovery/matches.json (their record of authority - no
   manifest exists pre-intake). **.gitignore:** recovery runtime outputs now
   ignored - fetched third-party art (nested fetched/) + the hash/match/saucenao
   caches (they embed personal-corpus abspaths); supersedes the earlier "caches
   stay tracked" note. **Cached everything:** hashes.json (424), matches.json
   (170), saucenao_cache.json, fetched/ (68 fullviews incl dark-cosmic). **Do
   NOT redo:** the POST, the oEmbed artist-URL fix, the driver, this run's
   caches. **FUTURE (BACKLOG):** per-image original=true escalation (10/week
   budget) for the ~67 fullviews quota-capped at ~1280px that need true 4K; a
   gallery-dl `-g` liveness fallback would harden Tier-1 against a full oEmbed
   shutdown.

7. DONE **2026-07-05 (G0 over-target source-gate; TDD).** Closed the G0 gap
   surfaced during the V3 widening (LEDGER item 5): first-pass was 4x-ing sources
   that already cover the 2560x1440 target - pathological compute (an 8K source
   -> a ~531-megapixel tensor, minutes) AND false-soft G1 scoring (the
   common-scale rule upscales the 1440p output back to native source res to
   compare). **Built (TDD via a subagent slice + independent merger probe):**
   `tools/lw_upscale.py` gains `_covers_target(w, h, target)` and a gate at the
   top of `first_pass` - when the source covers the target on both axes it takes
   a DOWNSCALE-ONLY path (raw = the source, one Lanczos to target + light USM, no
   model needed), recorded as backend "downscale-only" (scale 1, no
   model_sha256); below-target sources keep the unchanged AI 4x path. ADR-002
   never-double-resample doctrine honored. The `_finish` aspect guard is
   preserved (over-target non-16:9 still raises). **Verified (merger's own
   probe):** RED-then-GREEN confirmed; full suite 226 passed / 3 skipped (was
   223/3; +3 new CI-runnable tests, no torch); ruff clean; module still imports
   on stdlib+PIL+numpy. **Do NOT redo:** the gate + tests. **Design note:**
   downscale-only (not low-factor AI or flag-for-operator) chosen per the
   operator's "shouldn't 4x" phrasing + never-double-resample; AI enhancement of
   over-target sources, if ever wanted, belongs to the Stage-2 cleaning stage.

6. DONE **2026-07-05 (source-recovery waterfall scaffolding + artist-signature
   ruling ADR-005).** Operator directive: scaffold the recovery campaign so it is
   ready the moment API keys land. **Premise VERIFIED:** no recovery tool existed
   (grep) - built to the complete existing spec `docs/research/SOURCE_RECOVERY.md`,
   not from scratch. **Shipped `tools/lw_recover.py`** (TDD via a subagent slice,
   then an INDEPENDENT verifier probe by the merger): the 4-tier waterfall - Tier
   0 local pHash+dHash consensus match (both hashes must agree, accept<=8 /
   review<=14; usable NOW, no keys), Tier 1 DeviantArt token-decode (strip "d",
   base36 -> deviation id; the `dlnxav6 -> 1309974594` vector is a test) + public
   oEmbed liveness + gallery-dl fetch (decode/oEmbed work now; fetch gated on
   OAuth config), Tier 2 SauceNAO (gated on `API-Key-SauceNAO.txt`;
   accept>=85/review 60-85; the multipart-POST body is a flagged TODO for when the
   key lands), Tier 3 manual-queue CSV. CI-safe (stdlib at import, imagehash/PIL
   lazy, every network call injected so no test touches the wire),
   friendly-degraded (no raw API errors, never crashes the waterfall), atomic
   writes, CREATE_NO_WINDOW on gallery-dl. **Verified (merger's own probe, not the
   subagent's word):** full suite 223 passed / 3 skipped (was 190/3; +33 new),
   ruff clean, module imports on stdlib, token vector correct, `.gitignore`
   ignores fetched image bytes (privacy) while keeping recovery metadata
   trackable, `data/recovery/` holds only `.gitkeep`. **ADR-005 (artist
   signatures):** operator RULED remove-not-keep, inpainted at the cleaning
   scratch stage - closes the last queued ADR-002 operator decision; synced
   RESTORATION_PLAN, CLEANING_INPAINT, ROADMAP, CLAUDE Settled. **Do NOT redo:**
   the recovery tool + tests. **Future:** finish the SauceNAO multipart POST when
   the key lands; run the Tier 0 campaign on the 149 pending (no keys needed); G0
   over-target source-gate + monitor polish are next.

5. DONE **2026-07-05 (V3 detail DAT2 promoted to primary; golden re-frozen n=12
   on V3; dark-cosmic-ahri reprocessed; ADR-004).** Closed the top NOW item
   (widen G1 + V3 trial + defect-class cases) and the operator's dark-cosmic ask.
   **Premise VERIFIED:** V3's OpenModelDB link is dead - V3 ships only via the
   MangaJaNai v3.0.0 GitHub release (direct HTTPS, no gdrive token); fetched
   `4x_IllustrationJaNai_V3detail_DAT2_28k_bf16.safetensors` (139,793,020 bytes,
   sha eb9faf6a, self-computed - no upstream checksum), spandrel-loaded
   (arch=DAT/4x). **A/B (`lw_golden regress`, same USM70 finish so the delta
   isolates the upscaler):** V3 beats V1 on golden n=10 - MS-SSIM 8/10, LPIPS
   9/10, halo 7/10 - and on both new defect cases; clears BOTH high-halo flags
   (fiora2 0.072->0.043, inkshadow 0.075->0.043). **Widened** to n=14
   golden-comparable: frozen G1 thresholds HOLD (no real breaches; 3 apparent
   lap<1.0 "fails" were big-4K-source common-scale-upscale artifacts, not gate
   failures - logged as a G0 source-gate gap in ROADMAP). **Promoted (operator
   directive, ADR-004):** re-froze `data/golden/golden_set.json` at n=12 on V3
   (pv d9ec8125 -> 6d43a6d4; added `coven-ashe-lol-df49jt0-pre` jpeg-artifact +
   `1341679-banding`), all 12 blessed + PASS with ZERO flags; regress self-check
   PASS 12/12 pv_changed=False (V3 determinism confirmed). **dark-cosmic-ahri:**
   recovered its Tier-0 source (`Pictures/288.png`, 2560x1440, pHash dP=4 vs the
   1192x670 G0-fail preview), V3 first-passed it (PASS), and
   save-working -> annotate -> submit put it in `_firstneedauth` awaiting
   operator approve. **Verified:** full suite 190 passed / 3 skipped; only
   `data/golden/golden_set.json` tracked-dirty (image bytes + pipeline state
   gitignored). **Process note:** killed a pathological 8K source (caitlyn
   7680x4320) mid-widening that pinned the 12GB card at 11.5GB - PID verified by
   working-set/CPU/GPU correlation, NOT blind nvidia-smi. **Do NOT redo:** the V3
   weight (gitignored `tools/models/`); the n=12 V3 freeze; the A/B. **Future:**
   G0 over-target source-gate; V3denoise as a per-image halftone alternative; G3
   Haiku win-or-tie (vision stage).

4. DONE **2026-07-04 (first-pass golden-set regression protocol; commits
   8e8b9a0 + 936d99b).** Built the drift-detection harness the pipeline lacked,
   adapted for the no-ground-truth reality (operator ruling - no finished
   references exist; LEDGER item 3). Flow: brainstorm -> spec
   (`docs/research/GOLDEN_SET.md`) -> plan (`docs/superpowers/plans/`) -> TDD
   build. **Shipped:** `tools/lw_golden.py` with `freeze` (manifest from the
   blessed IJN baselines, copy bytes to durable gitignored storage, real G1
   metrics + a deterministic pipeline_version hash) and `regress` (re-score a
   candidate dir vs the frozen baseline within epsilon: MS-SSIM 0.01 / LPIPS
   0.02 / lap 5 percent / halo 0.02). Heavy deps INJECTED so the whole tool is
   CI-testable (CI 3.12 / system 3.14 have no pyiqa/torch). **Reference of
   record (operator decision):** the current blessed IJN first-pass output, not
   human perfection - drift + no-regression detection with a quality floor, no
   ground-truth needed; first-pass scope, per-stage baselines deferred.
   **Live:** operator blessed all 10 (kept all), froze
   `data/golden/golden_set.json` (TRACKED; pv d9ec8125be99; 10 cases; image
   bytes gitignored + sha-pinned so the privacy boundary held), and the regress
   self-check PASSED 10/10 within epsilon (pv_changed=False) - which also
   confirms spandrel/IJN upscale DETERMINISM. **Verified:** full suite 190
   passed / 3 skipped; ruff clean; CI green (8e8b9a0, 936d99b); `git
   check-ignore` confirmed no image bytes staged. **Process notes:** fixed a
   real CLI bug (`from tools import ...` failed when run as a script - added the
   `__main__` sys.path insert); a stray `&` inside a background launch spawned a
   duplicate torch job that exhausted the pagefile (WinError 1455), fixed by
   taskkill of command-line-verified torch PIDs - and NEARLY killed
   dwm/explorer/claude by trusting `nvidia-smi` compute-apps blindly (ALWAYS
   verify a PID's name/command line before taskkill). **Future:** G3 Haiku
   side-by-side "win or tie" is a documented TODO gated on the vision stage;
   widen n past 10; add banding/JPEG-artifact defect-class cases (the 10 span
   source-softness/halo, that gap unconfirmed); per-stage baselines as
   clean/final/last come online.

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
