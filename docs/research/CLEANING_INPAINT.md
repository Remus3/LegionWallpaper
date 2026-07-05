# LW Stage-2 Research: Watermark Removal + Artifact Inpainting (the scalpel)

Date: 2026-07-03
Scope: masked inpainting tools, automatic watermark/text detection, artifact
repair for illustrations, the uhdpaper corner-watermark case, and a concrete
recommended stage-2 stack for the Legion Wallpaper cleaning pass.
Hardware context: Windows 10 Pro, RTX 5070 12GB (Blackwell sm_120, needs
cu128+ wheels), Python 3.14 system install (ML wheels lag - see section 6).

Verification convention: claims checked against official repos/PyPI/docs are
dated; anything not directly confirmed is marked UNVERIFIED.

---

## 0. Empirical corpus findings (checked on this machine, 2026-07-03)

The corpus lives at `C:\Users\Administrator\Desktop\need up\` with staged
folders `0.Originals` (19 files) through `9.Image Backup`, plus
`Images copied from Pictures - Temp folder` (the 302 processed 2560x1440
PNGs, names like `NNN_cleanup.png` / `NNN.png`).

`2.First Pass Done` holds 58 files, of which 33 are uhdpaper-named JPEGs at
3840x2160 or 7680x4320 (e.g. `braum-victorious-...-uhdpaper.com-470@5@n.jpg`,
progressive JPEG, 7680x4320).

Findings from a high-pass corner/edge scan of all 33 uhdpaper files plus
visual inspection of five of them (braum, akali, caitlyn, gwen, swain
prestige) at native resolution:

1. NO visible uhdpaper corner watermark was found on any of the 33 files.
   The `...@5@x` full downloads in this corpus appear to be the clean
   variants. The remembered "uhdpaper corner watermark" case did not
   reproduce here - it likely applies to preview-tier images or other
   downloads (see section 4). Treat per-file scanning, not a blanket corner
   recipe, as the requirement.
2. CONFIRMED watermark class in the processed 302 corpus: baked-in artist
   credit strips. Example: `170_cleanup.png` carries semi-transparent white
   text across the full bottom edge, roughly 40 px tall at 1440p:
   `artstation.com/perryhan @<CJK chars>PerryHan` (mixed latin + CJK).
   This is exactly the class an OCR-based detector handles well.
3. CONFIRMED artifact class: the swain-prestige 8K file shows dense
   dither/chroma-noise zigzag texture in dark gradient regions - a stage-2/3
   artifact target independent of watermarks.
4. The simple high-pass heuristic (deviation from 9px median) found the
   artist-credit strip (score 3293 vs noise floor ~500) but also fires on
   fine art detail - it is a useful cheap pre-filter, not a decider.

Implication: stage-2 needs BOTH a text/watermark detector (OCR + trained
detector) and an artifact pass (JPEG/banding/chroma), and detection must run
on every file rather than assuming fixed watermark positions.

---

## 1. Masked inpainting tools that run locally

### IOPaint (ex lama-cleaner) - still the reference tool, but ARCHIVED

- Latest release: 1.6.0 on PyPI, 2025-03-18. GitHub repo Sanster/IOPaint was
  archived (read-only) on 2025-08-13. The tool still works; it just will not
  receive fixes. Pin versions.
- Erase models bundled: LaMa (default), MAT, ZITS, MI-GAN, plus Stable
  Diffusion inpaint models. Plugins: RealESRGAN, GFPGAN, RestoreFormer,
  RemoveBG, Anime Segmentation, Segment Anything (interactive masks).
- Batch CLI (the mode LW wants):
  `iopaint run --model=lama --device=cuda --image=IN_DIR --mask=MASK_DIR --output=OUT_DIR`
  Mask files pair with images by filename; a single mask file applies to all
  images. Masks are white-on-black PNGs.
- Web UI (`iopaint start --model=lama --device=cuda --port=8080`) gives
  hand-drawn masks - this is the human-in-the-loop QA fallback for free.
- Docs still recommend torch 2.1.2 (dated); in practice it runs on newer
  torch 2.x, but because the project is archived, expect dependency-pin
  friction with the newest diffusers/transformers. Keep it in its own venv.

### Model choice for illustrations

- LaMa (Fourier convolutions, resolution-robust): consensus best erase model
  for small-to-medium masks over texture/gradient continuation - which is
  exactly the text-watermark case on splash art. Runs fast on GPU, no prompt.
- MAT (transformer): aimed at large masks, but community and IOPaint docs
  note it can produce blur/artifacts; not the default scalpel.
- ZITS: good structural continuation (lines/edges); niche.
- MI-GAN: mobile-sized, lowest quality ceiling; skip on a 5070.
- Verdict: LaMa for the scalpel pass on text/logo watermarks. It does NOT
  hallucinate new content, which keeps the audit story simple.

### simple-lama-inpainting (pip) - the library route

- Thin Python wrapper around big-lama.pt (auto-downloads the model), requires
  torch >= 2.1. Ideal for embedding LaMa directly in `lw_pipeline` without
  IOPaint's web-app dependency tree. GitHub: enesmsahin/simple-lama-inpainting.
- Recommended as the PRIMARY batch engine (we own the loop, IOPaint is
  archived); keep IOPaint for its web UI QA mode.

### Stable-Diffusion inpainting (ComfyUI) - the reconstruction tier

- For LARGE reconstructions (malformed eyes/irises/skin, i.e. AI-generation
  artifacts needing new content), LaMa is insufficient - use SD inpainting
  with an illustration checkpoint (Illustrious- or NoobAI-family models suit
  the LoL splash-art style; both have ControlNet support since early 2025).
- ComfyUI on RTX 50-series: works with torch cu128 builds; the official
  portable build ships an embedded Python 3.12+ and there is a community
  portable preloaded for Blackwell: juspky/ComfyUI-Windows-Portable-cu128.
  Portable install avoids the Python 3.14 problem entirely.
- Keep this tier HUMAN-GATED: diffusion inpainting changes content, so every
  output goes through the milestone audit; never fully autonomous.
- Specific inpaint-checkpoint choice (e.g. which Illustrious inpaint merge)
  is UNVERIFIED - evaluate 2-3 candidates on a 5-image eye-repair benchmark
  during stage-2 bring-up.

---

## 2. Automatic watermark/text detection (mask generation without a human)

### Trained watermark detectors

- fancyfeast/joycaption-watermark-detection (HF Space) ships two models:
  - `yolo11x-train28-best.pt` (115 MB, YOLO11x): localizes watermark regions
    as bounding boxes; the Space runs it at imgsz=1024, IoU 0.5, default
    confidence 0.5.
  - `far5y1y5-8000.pt` (358 MB, OWLv2-based): binary watermarked / not
    watermarked classifier at 960x960 - useful as a cheap pre-gate.
  - License not stated on the Space (UNVERIFIED) - fine for local personal
    use; re-check before the process goes public/shareable.
- Proven pipeline pattern (jferments/watermark_remover, Medium writeup):
  YOLO11 detect -> dilate boxes 15 px with an elliptical kernel -> LaMa via
  simple-lama-inpainting -> write output. Default conf there is 0.1 (very
  permissive; they preferred false positives). For LW, start at 0.35-0.5 and
  gate (below).

### OCR-based text detection

- PaddleOCR 3.x (PP-OCRv5, released May 2025) is the accuracy leader in 2025
  comparisons (avg confidence 0.93 vs EasyOCR 0.85 in one eval); handles
  rotated text and CJK well - relevant since the confirmed corpus watermark
  mixes latin + CJK.
- EasyOCR is simpler to install (pure torch, shares the cu128 venv) and is
  good enough for white credit-strip text; PaddleOCR needs paddlepaddle
  wheels which lag on new Python versions and add a second framework.
- Tesseract: weakest on stylized/semi-transparent overlay text; skip.
- Recommendation: EasyOCR first (one less framework); if recall on faint
  strips disappoints, add PaddleOCR as a second voter.

### Cheap heuristics (pre-filter, not decider)

- High-pass (pixel deviation from local median) over border zones flags
  text-like energy fast with zero ML deps - validated on this corpus (found
  the artstation strip). Use it to rank/queue files, never to auto-approve.
- Frequency/edge templates for KNOWN site watermarks (fixed position + fixed
  text) can be exact: build a per-site template once, match corners.

### How reliable is full-auto in 2026, and sane gating

- Reliable: opaque or semi-transparent TEXT and LOGO overlays in border
  zones - YOLO + OCR union catches these with high recall.
- Unreliable: large diffuse tiled watermarks, marks over busy art, artistic
  signatures that resemble watermarks (policy call: an artist signature IS
  part of some fan art - decide keep/remove per file class before automating).
- Sane gate for autonomous mode (both must hold to auto-inpaint):
  1. detection confidence >= 0.5 (YOLO) or OCR text box with recognized
     string matching URL/handle patterns (contains ".com", "@", "www",
     "artstation", "deviantart", "uhdpaper", etc.);
  2. total mask area <= 2 percent of image AND mask centroid in the outer
     10 percent border band.
  Everything else lands in the human QA queue (IOPaint web UI).

---

## 3. Artifact repair beyond watermarks (illustrations)

- JPEG artifact removal: FBCNN (ICCV 2021, flexible blind QF prediction with
  a manual quality knob) remains the standard tool; available as a ComfyUI
  node (ComfyUI-FBCNN) and standalone PyTorch. Run it BEFORE upscaling on
  jpg sources (blockiness amplifies through any upscaler). SCUNet is the
  blind real-noise alternative and doubles as a chroma-noise cleaner.
  OpenModelDB also hosts 1x restoration models tuned for anime/illustration
  compression cleanup (specific model picks UNVERIFIED - audition during
  bring-up).
- Banding: the robust recipe for flat-color/gradient illustration areas is
  (a) do ALL stage math in 16-bit, (b) masked gradient smoothing on
  low-gradient regions only (ffmpeg `deband`/`gradfun` logic; research-grade
  options exist - AdaDeband, WaveMamba - but are overkill), (c) add
  blue-noise dither on the final 16->8-bit PNG export. Never deband after
  sharpening.
- Chroma noise / dither speckle (confirmed in corpus, section 0): SCUNet
  light pass or chroma-channel median in LAB space; keep luma untouched to
  preserve line art crispness.
- Ordering within the full pipeline: JPEG/deband/denoise repair FIRST (on
  the recovered source), then the single AI upscale, then watermark
  inpainting can run at either scale - prefer inpainting at SOURCE scale
  before upscale so LaMa fills less area and the upscaler unifies texture.

---

## 4. The uhdpaper.com corner watermark case

- Empirical result on THIS corpus (section 0): all 33 uhdpaper-named files
  in `2.First Pass Done` are the `...@5@x` variants and carry NO visible
  corner watermark (heuristic scan + 5 visual spot checks at native res).
- uhdpaper.com serves preview images with a corner site mark while full
  downloads are typically clean; the exact meaning of the `@N@letter`
  filename suffixes is undocumented (UNVERIFIED). The remembered watermark
  case most likely came from saving preview-tier images.
- Recipe if/when a uhdpaper-marked file shows up:
  1. It is a fixed-position corner text mark - detect via OCR restricted to
     the four corner regions (match string "uhdpaper");
  2. build a mask = OCR box dilated 15 px (elliptical);
  3. LaMa inpaint; corner regions are usually sky/texture, LaMa's best case;
  4. verify: re-run OCR on the healed corner (must be empty) and require
     pixels outside the mask to be bit-identical.
- Do not bake a blanket "always inpaint bottom-right corner" rule - the scan
  proved most files are clean, and blind inpainting would degrade them (the
  scalpel-not-sledgehammer lesson).

---

## 5. Recommended LW stage-2 (cleaning pass) stack

Flow per file: detect -> gate -> mask -> inpaint -> verify, with a human QA
queue for everything the gate rejects.

1. DETECT (venv-clean, Python 3.12):
   - YOLO11x watermark detector (ultralytics) at imgsz=1024, conf 0.35;
   - EasyOCR full-frame text pass (latin + CJK models);
   - cheap high-pass border scan as a ranking signal.
   Union the boxes; classify each box (URL/handle regex on OCR string,
   border-zone position).
2. GATE: auto path only if conf >= 0.5 (or OCR regex hit) AND mask <= 2
   percent of area AND in outer 10 percent band. Else -> QA queue.
3. MASK: white-on-black PNG per image; dilate boxes 15 px elliptical
   (cv2.dilate, MORPH_ELLIPSE) - matches the proven public pipeline.
4. INPAINT: simple-lama-inpainting (big-lama) in-process for the batch path;
   IOPaint `run` CLI is the equivalent alternative. SD/ComfyUI tier only for
   content reconstruction (eyes/skin), always human-reviewed.
5. VERIFY (self-audit): (a) re-run detector + OCR over the healed region -
   must be clean; (b) assert pixels outside the dilated mask are unchanged
   (exact compare - LaMa composites only inside the mask); (c) log JSON per
   file (boxes, conf, mask area, verdict) for the milestone audit; (d) SSIM
   on the mask border ring to catch seams (threshold to tune, start 0.92).
6. HUMAN FALLBACK: `iopaint start --model=lama --device=cuda --port=8080` -
   operator draws the mask in the browser for queue files; output drops back
   into the same verify step.

### Install steps (RTX 5070 / cu128; Python 3.14 caveats)

Python 3.14 is NOT viable for this stack today: torch 2.9+ ships only
"preview" 3.14 wheels (torch 2.9 release notes, Oct 2025) and ultralytics,
easyocr, paddleocr, and iopaint dependency pins all lag it. Side-install
Python 3.12 for ML venvs; keep 3.14 for everything else.

```
:: 1. Python 3.12 side-install (does not touch 3.14)
winget install Python.Python.3.12

:: 2. Detection + inpaint venv
C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe -m venv C:\Tools\lw-clean\venv
C:\Tools\lw-clean\venv\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
C:\Tools\lw-clean\venv\Scripts\pip install ultralytics easyocr simple-lama-inpainting opencv-python pillow

:: 3. Watermark detector weights (115 MB)
curl -L -o C:\Tools\lw-clean\yolo11x-train28-best.pt https://huggingface.co/spaces/fancyfeast/joycaption-watermark-detection/resolve/main/yolo11x-train28-best.pt

:: 4. IOPaint in its OWN venv (archived project, old pins - isolate it)
C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe -m venv C:\Tools\iopaint\venv
C:\Tools\iopaint\venv\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
C:\Tools\iopaint\venv\Scripts\pip install iopaint==1.6.0

:: 5. Optional reconstruction tier: ComfyUI portable for Blackwell
::    (embedded Python 3.12+, torch cu128 - no system Python involvement)
::    https://github.com/juspky/ComfyUI-Windows-Portable-cu128 or the
::    official ComfyUI portable + pip torch cu128 swap per discussion #6643.
```

Blackwell wheel note: torch cu128 wheels (stable 2.7.0+, April 2025 onward)
include Blackwell kernels and are the community-verified path for RTX
50-series on Windows (ComfyUI discussion #6643). A GitHub issue
(pytorch#164342) notes sm_120 is still not formally listed as "officially
supported" in stable release notes as of 2.9 - functionally it works via
cu128/cu129 wheels; if a "no kernel image" error ever appears, move to the
matching nightly cu128 build.

### Risks / open items

- IOPaint archived 2025-08-13: pin 1.6.0; long-term the batch path already
  avoids it (simple-lama-inpainting), only the QA web UI depends on it.
- Artist-signature policy - RULED 2026-07-05 (ADR-005): REMOVE. Flagged
  signatures are inpainted out at the cleaning scratch stage like any other mark
  (standard detect -> mask -> inpaint -> verify, gate + QA fallback); not kept,
  not routed to a keep-queue.
- fancyfeast model licensing unstated (UNVERIFIED) - re-check before the
  "shareable public process" milestone; same for big-lama weights
  redistribution if the pipeline ships weights.
- Removing artist credit text for personal wallpapers is fine as personal
  use; the SHAREABLE deliverable must be the process/pipeline, never the
  cleaned third-party images.
- SD inpaint checkpoint choice and OpenModelDB 1x artifact-model picks are
  UNVERIFIED - schedule a 5-image benchmark for each during bring-up.

---

## Sources (checked 2026-07-03)

- IOPaint: github.com/Sanster/IOPaint (archived 2025-08-13); pypi.org/project/IOPaint (1.6.0, 2025-03-18); iopaint.com/models (LaMa/MAT/MI-GAN pages)
- simple-lama-inpainting: pypi.org/project/simple-lama-inpainting; github.com/enesmsahin/simple-lama-inpainting
- Batch YOLO+LaMa pipeline: jferments.medium.com "Large-scale batch removal of watermarks"; github.com/jferments/watermark_remover
- Detector weights: huggingface.co/spaces/fancyfeast/joycaption-watermark-detection (app.py inspected: YOLO11x imgsz=1024 + OWLv2 classifier)
- OCR comparisons: codesota.com PaddleOCR vs EasyOCR (2025); PaddleOCR 3.0 / PP-OCRv5 release (May 2025)
- FBCNN: github.com/jiaxi-jiang/FBCNN (ICCV 2021); github.com/Miosp/ComfyUI-FBCNN
- Debanding: ffmpeg deband/gradfun docs; AdaDeband (IEEE SPL 2020); WaveMamba debanding (arxiv 2508.11331)
- PyTorch Blackwell: pytorch.org/blog/pytorch-2-7 (cu128 + Blackwell, Apr 2025); pytorch.org/blog/pytorch-2-9 (Python 3.14 preview wheels, Oct 2025); github.com/pytorch/pytorch/issues/164342 (sm_120 official-support status); github.com/Comfy-Org/ComfyUI/discussions/6643 (50-series setup)
- ComfyUI portable for Blackwell: github.com/juspky/ComfyUI-Windows-Portable-cu128
- Local corpus inspection: C:\Users\Administrator\Desktop\need up\ (scans and crops run 2026-07-03 on this machine)
