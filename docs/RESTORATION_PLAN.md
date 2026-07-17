# RESTORATION_PLAN v2 - The Legion Wallpaper Operational Plan

Date: 2026-07-03. Status: ACTIVE - this is THE operational plan for the LW
product. Supersedes the operator's v1 plan (archived verbatim at
`docs/_archive/RESTORATION_PLAN_v1.md`; originally authored 2026-06-14 on the
Desktop).
Decisions behind this plan: `docs/adr/ADR-002-restoration-pipeline-product.md`
(product + architecture) and `docs/adr/ADR-003-pipeline-folder-scheme.md`
(folder/state scheme). Research substrate: `docs/research/UPSCALE_TOOLCHAIN.md`,
`docs/research/CLEANING_INPAINT.md`, `docs/research/AUDIT_GATES.md`,
`docs/research/SOURCE_RECOVERY.md`, `docs/research/PIPELINE_STATE_MACHINE.md`,
`docs/research/LW_MONITOR_SPEC.md`.

---

## 1. Goal recap (the operator vision)

Drop an image into a folder; an autonomous, self-auditing pipeline recovers the
best source, upscales it once, cleans watermarks and AI-generation artifacts,
repairs illustrated faces/eyes, audits itself at every stage, and delivers an
approved 2560x1440 PNG to `C:\Users\Administrator\Pictures\` with an optional
sequential `###.png` rename. The corpus is ~302 processed League-splash-style
illustrations (mostly AI-generated DeviantArt fan art) plus ~77 recovered
sources.

Two products, cleanly separated:

- PRIVATE: the cleaned wallpapers themselves. Third-party art stays on this
  machine; cleaned images are never published.
- SHAREABLE: the PROCESS - the pipeline code, the gate ladder, the golden-set
  regression protocol, the provenance manifests. Anyone can rerun it on their
  own corpus. The process is the deliverable worth sharing.

The v1 plan's core lesson stands and is baked in everywhere: never
double-resample. One AI upscale, one Lanczos downscale, one light unsharp mask.
The bicubic up-to-8K round trip that softened batch 2 is dead forever.

## 2. The four stages

Images move through the 10-folder scheme in `C:\LegionWallpaper\images\`
(ADR-003): `0.Originals` -> first -> clean -> final -> last -> `8.End Review`
-> `9.Image Backup` (+ optional Pictures delivery). Each stage is
scratch-then-done with the four phase tokens `_<stage>initial`,
`_<stage>working_##`, `_<stage>needauth`, `_<stage>done`. `reference_pictures`
holds the non-pipeline reference corpus.

### 2.1 first = source recovery + the single upscale

Recovery waterfall (stop at the first tier that succeeds; every decision
logged; see `docs/research/SOURCE_RECOVERY.md`):

- Tier 0 - LOCAL PAIR MATCH (offline, free, deterministic). pHash + dHash
  consensus over processed PNGs vs local source JPGs. Brute force at this
  scale; Hamming <= 8 with both hashes agreeing = same image; 9-14 = review.
- Tier 1 - DEVIANTART TOKEN DECODE (offline -> two cheap HTTP calls). The
  filename token IS the deviation ID: strip the leading "d", base36-decode,
  `https://www.deviantart.com/deviation/<id>` redirects to the artwork page
  (verified live). oEmbed for liveness/metadata, then gallery-dl
  (quality=100, intermediary=true) for the best non-quota file; escalate to
  `original=true` only when dimensions demand it (weekly quota - section 8).
- Tier 2 - SAUCENAO API (free key: ~4 searches/30s, ~100/day - a queue, not a
  loop). similarity >= 85 auto-accept, 60-85 review, < 60 fail. Official Riot
  splash art detected here reroutes to clean CDN recovery (League wiki HD
  category, CommunityDragon) instead of inpainting.
- Tier 3 - MANUAL QUEUE. Leftovers get a row in
  `data/recovery/manual_queue.csv` (browser Lens/Yandex suggested); human
  resolves or marks "no source exists - inpaint path".

Then the upscale (see `docs/research/UPSCALE_TOOLCHAIN.md`): ONE AI upscale
with IllustrationJaNai (V3 DAT2 primary; V1 DAT2 confirmed-compatible
fallback) via spandrel/torch, with the existing
`realesrgan-ncnn-vulkan.exe` (x4plus-anime) as the zero-CUDA ncnn fallback
backend; then ONE Lanczos downscale to exactly 2560x1440; then a light
unsharp mask. Tiling is mandatory from day one (12GB VRAM ceiling).

### 2.2 clean = watermark/artifact removal (the scalpel)

Flow per file: detect -> gate -> mask -> inpaint -> verify (see
`docs/research/CLEANING_INPAINT.md`):

- DETECT: YOLO11x watermark detector (imgsz=1024, conf 0.35) + EasyOCR
  full-frame text pass (latin + CJK - the confirmed corpus watermark class is
  mixed-script artist credit strips) + cheap high-pass border scan as a
  ranking signal only. Detection runs on EVERY file - no blanket corner
  recipes (the uhdpaper corner-mark case did not reproduce on this corpus).
- GATE: auto path only if detection confidence >= 0.5 (or OCR regex hit on
  URL/handle patterns) AND mask <= 2 percent of area AND in the outer 10
  percent border band. Everything else -> human QA queue.
- MASK: white-on-black PNG, boxes dilated 15 px elliptical.
- INPAINT: LaMa via simple-lama-inpainting (batch path). LaMa does not
  hallucinate new content, which keeps the audit story simple.
- VERIFY: outside-mask identity (SSIM >= 0.995 hard gate - the single most
  important inpaint check), inside-mask change-happened + text-residue + seam
  checks, per-file JSON log.
- HUMAN QA QUEUE: IOPaint web UI, launched from the operator's local py3.11
  install (`%LOCALAPPDATA%\Python\pythoncore-3.11-64\python.exe -m iopaint
  start --model=lama --device=cuda` - the planned dedicated venv was never
  created; WAKEUP 2026-07-16). Operator draws the mask in the browser; output
  re-enters the same verify step. IOPaint is archived upstream - 1.6.0 pinned
  in that install (verified 2026-07-17).

### 2.3 final = polish (faces, eyes, banding, conformance)

- Masked eye/face repair ONLY: anime-trained YOLO detectors (Anzhc's YOLOs /
  adetailer anime variants) build dilated masks; ComfyUI headless (Impact
  Pack FaceDetailer pattern) inpaints only the mask with an anime-trained
  checkpoint at moderate denoise. Diff-audit proves the change region is
  confined to the mask.
- NEVER CodeFormer or GFPGAN. Both are photo-trained face restorers and harm
  illustrations (documented: photographic noses pasted onto anime faces,
  horror-adjacent distortion). Hard exclusion; the v1 plan's Fix B choice is
  overruled by the research.
- Debanding: 16-bit stage math, masked gradient smoothing on low-gradient
  regions only, blue-noise dither on the final 16->8-bit export. Never deband
  after sharpening.
- ORDERING NOTE: JPEG artifact repair (FBCNN) runs BEFORE upscaling on jpg
  sources - blockiness amplifies through any upscaler. This lives at the
  first-stage boundary but is a final-stage-owned quality concern.
- Exact 2560x1440 conformance check (PNG, sRGB, 8-bit, metadata scrubbed).

### 2.4 last = fresh-eyes regression

No new editing beyond reverts. Regression audit of the candidate against ALL
prior milestones (_firstinitial intent, _cleandone, _finaldone): drift across
stages, watermark recurrence, format check. Then End Review (deep audit of the
full milestone set) and, on pass, archive to `9.Image Backup` + optional
Pictures delivery.

## 3. The gate ladder G0-G4

Cheap -> expensive -> human; any hard fail at G1/G2 short-circuits with zero
API spend. Full detail: `docs/research/AUDIT_GATES.md`.

- G0 SOURCE GATE (free): resolution >= half target, pHash matches the corpus
  item it claims to replace, decodes clean, not a `-pre` preview.
- G1 UPSCALE GATE (free, deterministic): alignment asserts (integer scale,
  same aspect); MS-SSIM/LPIPS at COMMON SCALE; laplacian ratio >= 1.0; median
  edge width + halo detector; banding delta <= 0; NR delta gate
  (MUSIQ/TOPIQ/Q-Align must not regress).
- G2 INPAINT GATE (free, deterministic): outside-mask SSIM >= 0.995 hard
  gate; inside-mask change-happened + text-residue + seam checks; corner
  watermark template sweep; face/eye crop checks logged.
- G3 VISION AUDIT (Claude): side-by-side 2AFC rubric, Haiku 4.5 workhorse via
  Batch API (~$0.004/image; full-corpus sweep ~$1.20); escalate flagged
  images to Sonnet/Opus at high-res tier. Randomized A/B order, forced JSON
  rubric, temperature 0, model ID + prompt hash pinned in the ledger.
- G4 OPERATOR: approve/reject in a dead-simple triage flow; 100 percent
  during calibration, sampled after (section 5).

### 3.1 The FR-at-common-scale protocol (critical)

Full-reference metrics compare at the SOURCE resolution: downscale the output
to source size with the same Lanczos resampler, then compute MS-SSIM/LPIPS.
NEVER bicubic-upscale the reference to meet the output - that manufactures a
blurry reference and auto-approves soft output (the exact v1 softness bug).
Assert integer scale factors and identical aspect before any metric; treat an
unexplained SSIM cliff as an alignment bug first.

### 3.2 Delta-mode NR metrics

All no-reference IQA is photo-trained and untrustworthy in absolute terms on
illustrations (NIQE/BRISQUE are documented invalid on cartoons - log only,
never gate). Use the deep trio (MUSIQ, TOPIQ, Q-Align) two safe ways only:
DELTA mode (output minus input on the same content - photo bias cancels;
regression = flag) and CORPUS PERCENTILE bands (score all 302 once, flag new
outputs below the corpus 5th percentile).

### 3.3 The Claude-vision 2AFC rubric

LMMs are reliable at coarse pairwise comparison, weak at absolute scoring - so
the audit is side-by-side forced choice, never "rate 1-10". Send full A + full
B + native-res crops (eyes, old watermark bbox); do not reveal which is the
processed image; randomize order and record the mapping. Fixed JSON schema
with 10 scored categories (0-3). Pass rule: no category at 0, at most one at
1, eyes_and_irises >= 2, watermark_or_text_residue == 3, and the processed
image must win or tie overall.

## 4. Golden-set regression protocol

A frozen golden set of 10-15 representative (input, approved-output) pairs
spanning the defect classes (soft upscale, watermark corner, bad eyes,
banding-heavy glow). Every pipeline change re-runs the golden inputs:

- metric deltas vs stored approved outputs stay within epsilon (start:
  MS-SSIM within 0.01, LPIPS within 0.02, laplacian ratio within 5 percent);
- one batched Haiku side-by-side per golden image - new output must win or
  tie vs the stored approved output.

This is the cheap self-audit against prior milestones and doubles as the
shareable proof-of-process artifact.

## 5. Autonomy calibration ladder

False APPROVE (defective wallpaper ships) and false REJECT (one wasted rerun)
are not symmetric - tune every threshold to over-flag, and define autonomy in
terms of false approves:

- PHASE A - SHADOW (start here): operator reviews 100 percent; the auto
  verdict is computed and recorded but decides nothing. Minimum 50 images
  before any promotion.
- PHASE B - SPOT-CHECK: promote when agreement (auto vs operator) >= 95
  percent over the trailing 50 reviewed images AND zero false approves over
  the trailing 30. Operator then reviews only auto-REVISE/REJECT items plus a
  10 percent random sample of auto-APPROVEs.
- PHASE C - FULL AUTO: promote at zero false approves over 100 consecutive
  operator-checked samples since entering Phase B. Approved outputs land in
  Pictures untouched; a perpetual 5 percent random sample still goes to a
  review folder.
- DEMOTION: ANY false approve at any phase drops one phase and restarts that
  phase's window. Any pipeline_version change (new model, threshold, prompt)
  drops C -> B automatically.

Calibration substrate: an append-only JSONL ledger, one row per (image,
pipeline_version, stage attempt) with all metric values, the auto verdict,
the LLM rubric JSON + cost, and the operator verdict. pipeline_version is the
hash of the pinned tuple (metric versions, torch, model IDs, prompt hash,
threshold config).

## 6. Environment strategy

- Python 3.14 (system, `C:\...\Python314\python.exe`): orchestration only -
  lw_pipeline.py, lw_monitor.py, gallery-dl (supports 3.14), imagehash
  (PyWavelets 1.9.0+ has cp314 wheels), Pillow, opencv cheap checks.
- Python 3.12 side-venvs for every torch/ML stack: the wider ML ecosystem
  (ultralytics, easyocr, iopaint, pyiqa deps) lags cp314. One venv per tool
  family; never fight a 3.14 wheel gap.
- RTX 5070 is Blackwell sm_120: every torch install MUST come from the cu128
  (or newer) wheel index - `--index-url https://download.pytorch.org/whl/cu128`.
  Older wheels fail with "no kernel image". The ncnn-vulkan fallback needs no
  CUDA/torch at all and works today.
- Do not depend on torch.compile/Triton (Windows + sm_120 issues); eager
  inference is all spandrel needs.

## 7. Install status (checklist complete except ComfyUI; verified on disk 2026-07-17)

The original 8-item install checklist is archived verbatim in
`docs/history_notes.md` (2026-07-17 entry). Live environment map:
`docs/ARCHITECTURE.md` "ML environments". Status:

- DONE: py 3.12 side-install; `.venv-upscale` (torch 2.11.0+cu128 + spandrel,
  CUDA verified on the 5070); models in `tools/models/` (V3detail DAT2 primary
  per ADR-004 + V1 DAT2 spandrel-confirmed fallback); `C:\Tools\lw-clean\venv`
  (ultralytics + easyocr + simple-lama + yolo11x watermark weights); py 3.14
  orchestration deps (gallery-dl, imagehash); API keys
  (`API-Key-SauceNAO.txt`, `API-Key-DeviantArt.txt`).
- CHANGED: the planned dedicated IOPaint venv (`C:\Tools\iopaint\venv`) was
  never created; the manual QA lane runs the operator's local py3.11 install
  (`%LOCALAPPDATA%\Python\pythoncore-3.11-64\python.exe -m iopaint start
  --model=lama --device=cuda`, iopaint 1.6.0 pinned there; WAKEUP 2026-07-16).
- PENDING: ComfyUI portable for Blackwell (embedded py 3.12 + torch cu128) +
  Impact Pack + anime YOLO detectors + FBCNN node (final-stage bring-up).

## 8. DeviantArt quota urgency (run the recovery campaign EARLY)

DeviantArt clamped downloads on 2026-03-09: the download button (and
gallery-dl `original: true`) is now 10/week free / 150/week Core. The March
2026 change shows appetite for further anti-scraping moves - API fullview
content could be next. Therefore: run the Tier 0/1 recovery campaign soon and
cache everything. Fullview/quality-100 API fetches do not consume the download
quota; reserve `original` pulls for images that truly need them, and consider
one month of Core to burst 150/week during the initial campaign. gallery-dl
refresh tokens go stale after ~3 months - intake must surface a friendly
re-auth message, not a silent failure.

## 9. Open operator decisions (queued, not blockers)

- ARTIST-SIGNATURE POLICY - RULED 2026-07-05 (ADR-005): REMOVE, do not keep.
  Artist signatures are treated as removable marks and inpainted out during the
  cleaning scratch stage (Stage 2), through the standard
  detect -> mask -> inpaint -> verify cleaning path with the usual gate + human
  QA fallback. No longer routed to a keep-queue.
- Licensing re-check before the shareable milestone: fancyfeast detector
  weights license unstated; big-lama weight redistribution terms if the
  shipped process bundles weights.

## 10. Privacy / shareability boundary

Cleaned third-party images STAY PRIVATE (personal use). The shareable
artifact is the process: pipeline code, gate ladder, rubric, golden-set
protocol, provenance manifests (every tool, parameter, and hash per image).
Never git-add image content; `images/**` is gitignored except the .gitkeep
skeleton.
