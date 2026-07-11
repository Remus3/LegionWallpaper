# Generator Model Provenance + License Tracking (lw-gen)

Durable, tracked record of every model weight the lw-gen sidecar uses. Strict
7-bit ASCII. This file is the shareable proof-of-process; the weight binaries
themselves are gitignored (`tools/models/*`, `.venv-*`) - the PROCESS is tracked,
the multi-GB binaries never are (same discipline as `images/**` and the recovery
corpus).

STATUS 2026-07-10: NO WEIGHTS DOWNLOADED YET. The rows below are EMPTY templates
to fill in on download. Every download is operator-run and permission-gated (see
Phase-0 setup). Record the model/version/license/sha256 line BEFORE the download,
not "confirmed later" (plan section 9, Licensing/IP).

---

## Why this file exists (license/IP guardrails)

- Output is personal, solo, non-distributed fan-art. Riot's Legal Jibber Jabber
  permits non-commercial fan creations but PROHIBITS distribution/sale and any
  implied Riot endorsement.
- SDXL finetunes ship under varied terms (CreativeML-OpenRAIL-M, Fair-AI-Public-
  License, or custom). Confirm the specific checkpoint permits personal-use image
  generation BEFORE downloading it, and record the exact license here.
- Concrete guarantees baked into the design:
  (a) this file carries model/version/license/date before any Phase-0 download;
  (b) generated-origin images are personal-use ONLY - never uploaded to the
      DeviantArt recovery corpus, sold, or redistributed;
  (c) the `gen://lw-gen/<batch-id>` source_url is ALWAYS set so any future publish
      path can filter generated images out.

---

## Model provenance table

Fill one row per weight actually downloaded. `source_url` = the exact download
page/repo. `sha256` = the on-disk hash of the downloaded file (compute after
download; it is what the promote/QA sidecars can pin against). `date` = download
date (YYYY-MM-DD).

### Base checkpoint (the painterly/semi-realistic SDXL finetune - picked BY EYE in Phase 0)

| model | version | source_url | license | sha256 | date | notes |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  | (empty - fill on download) |

Placeholder path in `tools/lw_gen_config.json`:
`tools/models/<PLACEHOLDER checkpoint>.safetensors`. No weight is downloaded yet;
the config path is a documented placeholder, not a live file. Candidate classes to
try in the Phase-0 spike (plan section 2.2): a Juggernaut-XL / RealVisXL-class
photoreal-leaning SDXL finetune; base SDXL 1.0 + a splash-art / concept-art / key-
art LoRA; or a dedicated digital-painting / concept-art SDXL finetune. Pick ONE by
eye against real 0.Originals - do NOT default to anime (an anime finetune renders
flat cel-shaded art that still falsely passes the CLIP subject gate).

### Style LoRA (OPTIONAL - only if the Phase-0 spike shows anime/style leakage)

| model | version | source_url | license | sha256 | date | notes |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  | (empty - fill only if a LoRA is adopted) |

Config key `lora_path` is `null` until a LoRA is adopted.

### Subject-QA CLIP (open-clip ViT-L-14, openai pretrained - into .venv-metrics)

| model | version | source_url | license | sha256 | date | notes |
|---|---|---|---|---|---|---|
| ViT-L-14 | openai | (open_clip pretrained tag) | (per open-clip / OpenAI CLIP terms) |  |  | ~1.7GB weight; the existing pyiqa/clipiqa import is BROKEN, so this is a fresh install |

---

## Phase-0 setup (OPERATOR-RUN, PERMISSION-GATED)

Multi-GB downloads and a new venv. These commands are for the OPERATOR to run;
Claude does NOT execute them (they pull large third-party binaries and are gated on
explicit operator go-ahead). Transcribed from GENERATOR_SIDECAR_PLAN.md section 7.
Hardware is already probe-confirmed (torch 2.11.0+cu128, CUDA 12.8,
get_device_capability()==(12,0) on the RTX 5070) - no CUDA/PyTorch upgrade needed.

```
# 1. create the new side-venv (gitignored, like .venv-upscale / .venv-metrics)
C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe -m venv C:\LegionWallpaper\.venv-gen

# 2. install the SAME cu128 torch channel the box already runs
#    (do NOT let pip pull a CPU/cu12x wheel)
C:\LegionWallpaper\.venv-gen\Scripts\python.exe -m pip install torch==2.11.0+cu128 torchvision==0.26.0+cu128 --index-url https://download.pytorch.org/whl/cu128

# 3. add the generation stack (pure-python / torch-dependent; no new CUDA toolkit; NO xformers)
C:\LegionWallpaper\.venv-gen\Scripts\python.exe -m pip install diffusers transformers accelerate safetensors

# 4. add a working CLIP into .venv-metrics (the existing pyiqa/clip import is BROKEN)
C:\LegionWallpaper\.venv-metrics\Scripts\python.exe -m pip install open-clip-torch

# 5. download ONE painterly/semi-realistic SDXL finetune (safetensors) into
#    tools\models\ (gitignored); plus, if the spike shows anime leakage, one
#    splash-art/key-art LoRA. RECORD the model/version/license/sha256 row ABOVE
#    BEFORE downloading.

# 6. LIVE PROOF (retire the runtime + attention risks before building on top):
C:\LegionWallpaper\.venv-gen\Scripts\python.exe -c "import torch; print(torch.cuda.get_device_capability())"
   # MUST print (12, 0)  -> confirms sm_120 kernels load on the 5070
```

### Blackwell launcher env (set by lw_gen_run, documented here for the setup proof)

- `TORCH_CUDA_ARCH_LIST=12.0` and `CUDA_MODULE_LOADING=LAZY` (sm_120 is not always
  auto-detected).
- `CUDA_VISIBLE_DEVICES` must NOT be `-1` (a stray `-1` silently disables the GPU).
- Pin attention to torch SDPA; do NOT install xformers (no guaranteed sm_120 wheel).
- `enable_model_cpu_offload()` + tiled VAE decode ON by default (~9.5GB real free
  VRAM on this shared box, not 12GB).

### Phase-0 acceptance (from plan section 8)

- `torch.cuda.get_device_capability()` returns `(12,0)` live; SDPA active; GPU
  visible (no `CUDA_VISIBLE_DEVICES=-1`).
- A 1344x768 SDXL gen completes; peak VRAM measured WITH the real desktop resident
  stays within ~9.5GB free (offload + tiled decode ON).
- STYLE-FIDELITY: output looks like a painterly LoL splash judged BY EYE against
  real 0.Originals - NOT flat anime. This is the gating acceptance; swap model/LoRA
  before proceeding if it fails.
- open-clip ViT-L loads and scores an image in .venv-metrics (proves the QA
  foundation is un-broken).

Discipline: heavy ML NEVER enters `requirements.txt` (CI stays pytest/ruff/numpy/
Pillow, torch-free). Avoid `uvx` on this box (dies under Vanguard's .data lock); use
the persistent venv.
