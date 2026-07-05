# UPSCALE_TOOLCHAIN - Upscaling + Restoration Toolchain Research for Legion Wallpaper

Date: 2026-07-03
Author: LW research subagent (Claude)
Scope: local upscaling and restoration toolchain for splash-art / illustration
content on THIS box (Windows 10 Pro, RTX 5070 12GB Blackwell sm_120, driver
610.62, Python 3.14 system install, existing realesrgan-ncnn-vulkan at
C:\Tools\realesrgan).
Verification discipline: claims checked against official repos / package
indexes where possible. Anything not directly confirmed is marked UNVERIFIED.

---

## 1. Executive summary

- The state of the art for ILLUSTRATION upscaling in 2026 is NOT the stock
  Real-ESRGAN models. It is community-trained models hosted on OpenModelDB,
  and for LW's corpus (color splash-art / digital illustration) the standout
  family is IllustrationJaNai by the-database (author of MangaJaNai) -
  trained specifically on color illustrations to remove JPEG artifacts,
  halftone, and low-res softness. V3 ships variants on HAT-L, DAT2, FDAT,
  and SPAN networks (quality vs speed ladder).
- The RTX 5070 (sm_120) is fully usable from PyTorch: any stable torch
  >= 2.7.0 built against CUDA 12.8 (cu128 wheel index) contains sm_120
  kernels. Verified today: the cu128 index has Windows cp314 wheels up to
  torch 2.11.0, so system Python 3.14 CAN run CUDA torch - no 3.11/3.12
  side-install strictly required for torch itself (but see risks: the wider
  ML dependency ecosystem on 3.14 still lags).
- The ncnn-vulkan route (the existing realesrgan-ncnn-vulkan.exe) sidesteps
  the CUDA/PyTorch question entirely - it uses Vulkan through the NVIDIA
  driver and already works on Blackwell. Its limits: model zoo is frozen
  (2022-era Real-ESRGAN models), no DAT2/HAT/FDAT support, and the upstream
  exe is unmaintained. The maintained fork is upscayl-ncnn (upscayl-bin),
  which accepts custom NCNN .param/.bin models.
- GFPGAN and CodeFormer are photo-trained face restorers and HARM
  illustrated faces: documented behavior is realistic-looking noses pasted
  onto anime faces (GFPGAN) and horror-adjacent distortion (CodeFormer).
  Do not put them in the LW pipeline. The correct illustrated-face repair
  approach is detection + masked diffusion inpainting: anime-trained YOLO
  detectors (face / eye models, e.g. Anzhc's YOLOs) to build masks, then
  inpaint only the masked region with an anime-trained SD checkpoint -
  which is exactly LW's "scalpel not sledgehammer" doctrine.
- Recommended orchestration: plain Python driving spandrel (the chaiNNer
  team's pip-installable model-loading library) for the upscale pass, and a
  headless ComfyUI server (HTTP /prompt API) for the later inpainting /
  face-repair stage. chaiNNer itself has a real CLI (chainner.exe run
  chain.chn) and is a fine prototyping surface, but its override mechanism
  is too limited for a self-auditing pipeline.

---

## 2. Topic 1 - Best local upscalers for splash-art / illustration

### 2.1 Where models live: OpenModelDB

OpenModelDB (https://openmodeldb.info) is the successor to the old Upscale
Wiki model database and is THE hub for community super-resolution models in
2026 - hundreds of models tagged by content type (anime, manga, photo,
game textures, text), architecture, and scale. Models are typically .pth
(PyTorch) or .safetensors, loadable by spandrel / chaiNNer / ComfyUI.

### 2.2 Architectures, quality ladder (2026)

- ESRGAN (RRDBNet) - the 2018-era classic; still the most widely trained
  community arch. Fast, well supported everywhere (including ncnn).
- Real-ESRGAN - ESRGAN retrained with a synthetic degradation pipeline;
  the stock realesrgan-x4plus-anime / animevideov3 models are what the
  existing exe ships. Decent but superseded for stills.
- SwinIR / HAT / DAT (transformer SR) - measurably better texture and
  pattern coherence than ESRGAN; DAT2 and HAT-L are the quality end of the
  community ladder. Slow relative to ESRGAN, but on a 5070 a 1440p-target
  upscale is still seconds-per-image, not minutes.
- SPAN / RealPLKSR / Compact (and FDAT-M) - the modern speed end; used for
  video and bulk work.
- FDAT - a newer transformer arch used by the-database for IllustrationJaNai
  V2/V3 (XL = balanced, M = fast). NOTE: FDAT is NOT supported by chaiNNer
  as of v0.25.1 per the release notes; it runs via the author's tooling
  (MangaJaNaiConverterGui) and, expected, recent spandrel versions
  (UNVERIFIED which spandrel version added FDAT - check spandrel changelog
  during implementation).

### 2.3 Model shortlist for LW's corpus (color splash art, AI-gen fan art)

Primary candidates, in recommended trial order:

1. 4x IllustrationJaNai V3 (the-database) - trained FOR color illustration:
   detail/texture generation, line de-aliasing, color/contrast accuracy.
   Two flavors (V3detail, V3denoise) x 4 networks each (HAT-L / DAT2 /
   FDAT / SPAN grades). V3denoise is interesting for LW's compression
   artifact + banding defects. Released via the-database/MangaJaNai GitHub
   releases (same repo hosts MangaJaNai = B/W manga line; IllustrationJaNai
   = color line). Release dates on the fetched page were ambiguous
   (UNVERIFIED exact dates; V1 listed 2024 on OpenModelDB, V2/V3 2025).
2. 4x IllustrationJaNai V1 DAT2 (OpenModelDB:
   4x-IllustrationJaNai-V1-DAT2) - proven, chaiNNer/spandrel-compatible
   today, explicitly recommended as a general digital-art upscaler.
3. 4x AnimeSharp (Kim2091) - classic ESRGAN anime model, sharp lines;
   AnimeSharpV2 variants exist on MoSR arch (Sharp/Soft). Good cross-check
   model, cheap to run.
4. Ani4K v2 (Sirosky/Upscale-Hub) - detail retention + depth-of-field
   preservation, targeted at modern anime to 2K/4K. Trained for video
   frames but community-reported fine on stills. Sirosky's AniScale 2 also
   ships a 1x "AS2R" refiner (Compact) for line fixing - relevant as a
   post-pass instead of unsharp mask (worth an A/B).
5. 4x UltraSharpV2 (Kim2091) - the 2025 successor to 4x-UltraSharp;
   general/photo-leaning. Keep as a control model for the audit harness,
   not as the primary (LW content is illustration, not photo).

Stock realesrgan-x4plus-anime (already on box) is the baseline to beat and
the zero-install fallback.

Upscayl (the Electron GUI) uses the same ncnn Real-ESRGAN backend
(upscayl-ncnn fork, binary name upscayl-bin) - as a GUI it adds nothing for
an automated pipeline, but upscayl-bin the CLI is the maintained successor
to realesrgan-ncnn-vulkan and loads custom NCNN models (.param/.bin, scale
parsed from filename). Custom models repo: upscayl/custom-models.

### 2.4 Which family is state of the art for anime/illustration in 2026?

For stills at maximum quality: transformer models trained on illustration
data - concretely IllustrationJaNai V3 on HAT-L or DAT2. Independent 2026
comparisons agree transformer archs (SwinIR/HAT/DAT) hold pattern coherence
better than ESRGAN, and content-specific training matters more than the
arch itself. For bulk/speed: SPAN / Compact / FDAT-M grade models. ESRGAN
models remain relevant only because the ncnn path and older tools support
them universally.

---

## 3. Topic 2 - RTX 5070 (Blackwell sm_120) PyTorch compatibility

Verified facts:

- Blackwell consumer GPUs report CUDA compute capability sm_120. Torch
  wheels built before CUDA 12.8 (cu118/cu121/cu124/cu126) do NOT include
  sm_120 kernels and fail with the classic "no kernel image" / sm_120
  not-supported errors (multiple PyTorch forum threads and pytorch/pytorch
  issue #164342 document this).
- The fix is simply to install from the cu128 (or newer cu13x) wheel index:
  pip install torch torchvision --index-url
  https://download.pytorch.org/whl/cu128
  Stable torch >= 2.7.0 built with CUDA 12.8 includes Blackwell support;
  community guides for the 5070 specifically confirm 2.9.1+cu128 working.
- Python 3.14 status - VERIFIED today by fetching the cu128 index directly:
  https://download.pytorch.org/whl/cu128/torch/ contains win_amd64 wheels
  for cp310..cp314 (including cp314t free-threaded), newest torch 2.11.0.
  So the system Python 3.14 can run CUDA torch on this box. (There are
  older GitHub issues from late 2025 complaining cp314 had CPU-only wheels;
  that is now stale for cu128.)
- Caveat: torch is not the whole ecosystem. Packages like onnxruntime-gpu,
  ultralytics (YOLO), and some ComfyUI custom nodes may still lack cp314
  wheels or pin older torch. If any stage-2 dependency fails on 3.14, the
  pragmatic move remains a py311/py312 venv just for that tool - flag it,
  do not fight it.
- Triton / torch.compile on Windows + sm_120 had lingering issues in
  nightly threads ("sm_120 is not defined for option gpu-name") - do not
  build the pipeline to depend on torch.compile. Plain eager inference is
  all spandrel needs.
- The ncnn-vulkan route sidesteps ALL of this: it is Vulkan via the NVIDIA
  driver, no CUDA, no torch, no Python version constraint. The existing
  realesrgan-ncnn-vulkan.exe works on Blackwell today. This is the LW
  safety net.

---

## 4. Topic 3 - Face/eye repair for ILLUSTRATED faces

### 4.1 GFPGAN / CodeFormer: verified unsuitable

Both are blind face restoration models trained on photographic face priors
(GFPGAN leans on a pretrained StyleGAN2 photo-face prior; CodeFormer on a
codebook learned from photos). On anime/illustrated faces the documented
failure modes are:

- CodeFormer: distorts stylized faces, can produce "horror-like" results;
  community guidance is to not use it on anime-style images.
- GFPGAN: blurs the surrounding art and renders noses/skin with
  photographic realism inside a stylized face - style-breaking even when
  not grotesque.
- Consensus recommendation found in comparisons: for anime styles, refrain
  from photo face restoration entirely.

Verdict for LW: HARD EXCLUDE from the illustration path. At most they stay
relevant if LW ever ingests photographic wallpapers (separate content
route, detected at audit time).

### 4.2 What works for illustrations: detect + masked diffusion inpaint

The 2026 standard for fixing malformed eyes/irises/faces in illustrations
is the ADetailer / FaceDetailer pattern:

1. Detect faces/eyes with YOLO models trained on ANIME data - e.g. the
   adetailer face_yolo anime variants and Anzhc's YOLOs (HuggingFace:
   Anzhc/Anzhcs_YOLOs; eye models trained on 5k+ annotated anime/
   illustration images, sclera-level masks). deepghs (HuggingFace org) also
   publishes anime face/eye/head detectors (UNVERIFIED current model list -
   check at implementation).
2. Build a dilated mask from detections.
3. Inpaint ONLY the mask with an anime-trained diffusion checkpoint
   (2026 lineage: Illustrious-XL / NoobAI-XL family - UNVERIFIED which
   checkpoint is current best; pick during stage-2 design) at moderate
   denoise (0.3-0.5), matching the splash-art style.
4. Composite back and diff-audit against the pre-inpaint image so the
   change region is provably confined to the mask (this is the LW
   self-audit hook).

Runners for this pattern:
- ComfyUI Impact Pack "FaceDetailer" node - the standard implementation,
  fully drivable through headless ComfyUI API.
- Bing-su/adetailer - the original A1111 extension (A1111 itself is in
  decline; prefer the ComfyUI equivalent).

This is stage 2/3 territory for LW (watermark removal shares the same
masked-inpaint machinery with a different detector: manual boxes or a
watermark detector). Not needed for the stage-1 upscale pass, but the
toolchain choice (ComfyUI headless) should anticipate it.

---

## 5. Topic 4 - Orchestration: chaiNNer CLI vs ComfyUI headless vs plain Python

### 5.1 chaiNNer

- Node GUI, alpha v0.25.1 (Oct 2025), actively developed.
- Real CLI, VERIFIED from the project wiki:
  chainner.exe run "path\to\chain.chn"
  chainner.exe run "path\to\chain.chn" --override "overrides.json"
  Exit code 0 on success. Overrides support text/number/file/directory
  inputs only - dropdowns/checkboxes are NOT overridable from CLI.
- Backends: PyTorch, NCNN, ONNX, TensorRT; loads anything on OpenModelDB
  (except newest archs like FDAT).
- Fit for LW: excellent for interactive experimentation and for converting
  models between PyTorch/ONNX/NCNN. Weak as the automation backbone: chains
  are opaque .chn blobs, CLI overrides are limited, and per-image audit
  hooks would live outside the tool anyway.

### 5.2 ComfyUI headless

- The ComfyUI server is headless by default; the browser UI is just a
  client. POST a workflow JSON to /prompt, poll /history/<prompt_id> or
  subscribe to the ws://host/ws websocket, fetch outputs via /view.
  Official script_examples exist in the repo; the pattern is widely
  documented for batch pipelines.
- Fit for LW: overkill for stage 1 (a plain upscale), but the right host
  for stage 2/3 (FaceDetailer, masked inpaint, watermark removal) since
  Impact Pack and every detector/inpaint node already live there. Running
  it as a local service that the LW pipeline calls over HTTP keeps the
  pipeline code in plain Python and the diffusion mess contained.
- Blackwell note: ComfyUI bundles/requires torch; on this box it must be
  installed with the cu128 build. ComfyUI portable builds for Windows
  exist with cu128 torch (UNVERIFIED whether the current portable zip
  defaults to cu128 - check at install time; safe path is manual install
  into a venv with the cu128 index URL).

### 5.3 Plain Python + spandrel (+ ncnn exe fallback)

- spandrel (chaiNNer-org/spandrel, pip install spandrel) is the chaiNNer
  team's extraction of their model-loading layer: auto-detects architecture
  and hyperparams from a .pth/.safetensors file, returns a callable torch
  model. Supports ESRGAN/SwinIR/HAT/DAT/SPAN/Compact and more. This is what
  A1111 itself migrated to for its upscalers.
- A ~100-line Python module gives LW: load model once, tile if needed,
  batch a folder, write PNG, emit per-image JSON audit records (timings,
  input/output hashes, model id, settings). Fully deterministic, fully
  testable under pytest - matches the repo's TDD discipline.
- The ncnn exe path (subprocess to realesrgan-ncnn-vulkan.exe or
  upscayl-bin) is the same module with a different backend enum - zero
  Python-ML dependencies, immune to CUDA/Python-version churn.

### 5.4 Verdict

For an AUTOMATED, SELF-AUDITING, SHAREABLE pipeline: plain Python
orchestrator, two pluggable upscale backends (spandrel/torch primary, ncnn
exe fallback), ComfyUI headless added later as the stage-2/3 inpaint
service. chaiNNer stays as a desk tool for experiments and NCNN conversion,
not in the pipeline path. Shareability favors this too: "pip install -r
requirements.txt + download 2 model files" beats "install my GUI and load
my chain file".

---

## 6. Topic 5 - Concrete recommended stack for LW stage 1 (upscale pass)

### 6.1 Primary stack (GPU torch, best quality)

Pipeline shape per image (locks in the no-double-resample rule):
source -> ONE AI upscale (4x model) -> ONE Lanczos downscale to exactly
2560x1440 (or 4K target) -> light unsharp mask -> PNG.

Components:
- Python: system 3.14 (cp314 cu128 torch wheels verified). If any dep
  breaks on 3.14, fall back to a py312 venv - decision point, not blocker.
- torch 2.11.0+cu128 (newest on the cu128 index as of 2026-07-03).
- spandrel (latest; PyPI page fetch failed today - version UNVERIFIED,
  check pip).
- Pillow (Lanczos + UnsharpMask) or OpenCV; Pillow is lighter and enough.
- Models (download to C:\LegionWallpaper\tools\models\):
  - 4x_IllustrationJaNai_V3detail (DAT2 variant) - primary quality model.
  - 4x_IllustrationJaNai_V3denoise (DAT2) - for the compression/banding
    subset.
  - 4x_AnimeSharp - cheap cross-check model for the audit A/B.
  From: github.com/the-database/MangaJaNai/releases and openmodeldb.info.
  V3detail DAT2 is spandrel-loaded and PROMOTED to primary as of ADR-004
  (2026-07-05); V1 DAT2 (4x_IllustrationJaNai_V1_DAT2_190k.pth) is the
  spandrel-confirmed fallback.

Install steps (new venv, PowerShell):

    cd C:\LegionWallpaper
    & "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m venv .venv-upscale
    .\.venv-upscale\Scripts\python.exe -m pip install --upgrade pip
    .\.venv-upscale\Scripts\pip.exe install torch torchvision --index-url https://download.pytorch.org/whl/cu128
    .\.venv-upscale\Scripts\pip.exe install spandrel pillow numpy
    # smoke test
    .\.venv-upscale\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"

Acceptance gate: cuda.is_available() True and device name contains 5070;
then a spandrel load + 64x64 tensor forward pass on each downloaded model.

VRAM note: 12GB is comfortable for 4x DAT2 on ~1024-1500px inputs with
tiling (tile 512, overlap 32) - implement tiling from day one; HAT-L may
need smaller tiles.

### 6.2 Fallback stack (zero-CUDA, works today)

- Existing C:\Tools\realesrgan\realesrgan-ncnn-vulkan.exe with
  realesrgan-x4plus-anime, driven by subprocess. Already Blackwell-safe.
- Upgrade option: upscayl-bin from github.com/upscayl/upscayl-ncnn
  (maintained fork, custom NCNN model support). Community NCNN conversions
  of many OpenModelDB ESRGAN models exist (and chaiNNer can convert
  PyTorch -> NCNN for ESRGAN-arch models). Transformer models (DAT2/HAT)
  generally do NOT convert to NCNN - the fallback tops out at ESRGAN-class
  quality.
- Same Lanczos + unsharp finishing in Pillow either way, so the pipeline
  code above the backend enum is identical.

### 6.3 Stage-2 preview (not stage 1, informs design)

- ComfyUI in headless mode as a localhost service; Impact Pack FaceDetailer
  with anime YOLO detectors (Anzhc's YOLOs / adetailer anime face models);
  anime SDXL-lineage checkpoint for masked inpainting of eyes/faces and
  watermark regions. All drivable from the same Python orchestrator via
  HTTP. Requires the same cu128 torch rule.

---

## 7. Risks and open items

1. Python 3.14 ecosystem lag - torch is fine (verified) but onnxruntime /
   ultralytics / ComfyUI deps may not be. Mitigation: py312 venv per tool.
2. FDAT / newest IllustrationJaNai variants may not load in spandrel or
   chaiNNer yet (chaiNNer v0.25.1 release notes say FDAT unsupported).
   Mitigation: use DAT2/HAT variants, or the author's
   MangaJaNaiConverterGui tooling.
3. Fetched pytorch.org get-started page rendered a stale "stable 2.7.0"
   snapshot; the live cu128 wheel index (fetched directly) shows 2.11.0 as
   newest - trust the index. Exact current stable version number as of
   mid-2026: UNVERIFIED beyond ">= 2.11.0 exists on cu128 index".
4. IllustrationJaNai release dates from the GitHub releases fetch were
   internally inconsistent (a "2022" V1 date is almost certainly a
   misparse). Model QUALITY claims come from the author's release notes -
   LW's own A/B audit (milestone diffing) is the real gate, per doctrine.
5. 12GB VRAM ceiling with HAT-L on large inputs - tiling is mandatory in
   the pipeline module, never optional.
6. realesrgan-ncnn-vulkan upstream is unmaintained; keep as-is (it works)
   but treat upscayl-bin as the maintained replacement when NCNN custom
   models are wanted.

---

## 8. Sources

- OpenModelDB: https://openmodeldb.info (anime tag: /?t=anime)
- IllustrationJaNai V1 DAT2: https://openmodeldb.info/models/4x-IllustrationJaNai-V1-DAT2
- MangaJaNai / IllustrationJaNai releases: https://github.com/the-database/MangaJaNai/releases
- 4x AnimeSharp: https://openmodeldb.info/models/4x-AnimeSharp
- 4x UltraSharpV2: https://openmodeldb.info/models/4x-UltraSharpV2
- Sirosky Upscale-Hub (Ani4K v2, AniScale 2): https://github.com/Sirosky/Upscale-Hub/releases
- Kim2091 models: https://github.com/Kim2091/Kim2091-Models/releases
- spandrel: https://github.com/chaiNNer-org/spandrel ; https://pypi.org/project/spandrel/
- chaiNNer: https://github.com/chaiNNer-org/chaiNNer (v0.25.1, 2025-10-23)
- chaiNNer CLI wiki: https://github.com/chaiNNer-org/chaiNNer/wiki/05--CLI
- PyTorch cu128 wheel index (cp314 win wheels, torch 2.11.0):
  https://download.pytorch.org/whl/cu128/torch/
- PyTorch sm_120 issue: https://github.com/pytorch/pytorch/issues/164342
- RTX 5070 + PyTorch guide: https://github.com/Stephensmetana/nvidia-rtx5070-pytorch-guide
- Blackwell + Real-ESRGAN benchmark: https://allenkuo.medium.com/upgrading-to-blackwell-gpu-pytorch-compatibility-cuda-support-and-real-esrgan-benchmark-0ebb363e4e9c
- PyTorch forums sm_120 threads: https://discuss.pytorch.org/t/nvidia-geforce-rtx-5070-ti-with-cuda-capability-sm-120/221509
- cp314 CUDA wheel issue (stale): https://github.com/pytorch/pytorch/issues/169929
- GFPGAN: https://github.com/TencentARC/GFPGAN
- Face-restore-on-anime comparison (CodeFormer distortion, GFPGAN realism
  bleed): https://note.com/levelma/n/na9c3d83fb8cc
- ADetailer: https://github.com/Bing-su/adetailer
- Anzhc's anime YOLO detectors: https://huggingface.co/Anzhc/Anzhcs_YOLOs
- ComfyUI API guide: https://www.runflow.io/blog/comfyui-api-developer-guide ;
  https://medium.com/@yushantripleseven/comfyui-using-the-api-261293aa055a
- ComfyUI workflows as scripts: https://www.timlrx.com/blog/executing-comfyui-workflows-as-standalone-scripts/
- Upscayl NCNN backend: https://github.com/upscayl/upscayl-ncnn
- Upscayl custom models: https://github.com/upscayl/custom-models
- 2026 upscaler comparison (arch-level claims): https://zsky.ai/blog/ai-upscaling-comparison
