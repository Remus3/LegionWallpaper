# Generator Model Provenance + License Tracking (lw-gen)

Durable, tracked record of every model weight the lw-gen sidecar uses. Strict
7-bit ASCII. This file is the shareable proof-of-process; the weight binaries
themselves are gitignored (`tools/models/*`, `.venv-*`) - the PROCESS is tracked,
the multi-GB binaries never are (same discipline as `images/**` and the recovery
corpus).

STATUS 2026-07-10: Phase-0 provisioning IN PROGRESS (operator-authorized 2026-07-10).
.venv-gen built (torch 2.11.0+cu128, torchvision 0.26.0+cu128, diffusers 0.39.0);
open-clip-torch 3.3.0 installed into .venv-metrics (torch pin held at 2.11.0+cu128).
Weight downloads under way - the rows below carry model/version/license/source
recorded BEFORE download per plan section 9; sha256 is filled after each file lands.
The (12,0) live proof + the by-eye style-fidelity spike are HARD-GATED off until
League/RC is closed (League was live at provisioning time - downloads are network/
disk only, so they proceed; GPU work waits).

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
| RealVisXL V5.0 | V5.0 fp16 | huggingface.co/SG161222/RealVisXL_V5.0 | openrail++ | 6a35a7855770ae9820a3c931d4964c3817b6d9e3c6f9c4dabb5b3a94e5643b80 | 2026-07-10 | approach A: photoreal-leaning SDXL finetune; ungated; no personal-use restriction (verified live). 6.94 GB, tools/models/RealVisXL_V5.0/RealVisXL_V5.0_fp16.safetensors |
| SDXL base 1.0 | 1.0 fp16 | huggingface.co/stabilityai/stable-diffusion-xl-base-1.0 | CreativeML OpenRAIL++-M | (not downloaded) | - | approach B anchor - DEFERRED. Staged only if the RealVis by-eye spike is not painterly enough; then pull base SDXL + a splash/key-art LoRA |
| Animagine XL 4.0 | 4.0 fp16 opt | huggingface.co/cagliostrolab/animagine-xl-4.0 | CreativeML OpenRAIL++-M | 6327eca98bfb6538dd7a4edce22484a1bbc57a8cff6b11d075d40da1afb847ac | 2026-07-11 | ANIME base (operator-directed anime-flat direction). 6.94 GB animagine-xl-4.0-opt.safetensors. Booru-tag prompting (style splash-booru). KNOWS LoL champions canonically (Vayne: correct glasses/dual-crossbows/ponytail) + clean anime faces/glasses - fixed the mangled-glasses + odd-expression + too-photoreal complaints RealVis could not |
| ControlNet OpenPose SDXL | xinsir 1.0 | huggingface.co/xinsir/controlnet-openpose-sdxl-1.0 | Apache-2.0 | (diffusers fp16) | 2026-07-11 | 2.5 GB. POSE CONTROL - extract an OpenPose skeleton (with hand keypoints) from a real splash via controlnet_aux OpenposeDetector, condition Animagine on it. Deterministic fix for unnatural posing + mirrored/second-left-hand chirality, while KEEPING sharp txt2img detail (no img2img blur). --controlnet-pose <ref>. Preprocessor annotators from lllyasviel/Annotators. controlnet_aux is pure-pip (no onnxruntime/mediapipe) |

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

### IP-Adapter (reference-image identity/concept transfer - NO training)

Reference-image conditioning: hand the pipe a real splash crop and it carries
identity without a trained LoRA. Adopted as a lane 2026-08-16 after the general
adapter measurably BEAT the no-adapter control where the trained per-champion
LoRA measurably lost (LEDGER 108). Consumed by `tools/lw_gen_run.py`
(`--ip-adapter-image` / `--ip-adapter-scale` / `--ip-adapter-weight-name`) on the
txt2img path and by `tools/lw_gen_weaponpass.py` on the inpaint path.

| model | version | source_url | license | sha256 | date | notes |
|---|---|---|---|---|---|---|
| IP-Adapter SDXL ViT-H | h94/IP-Adapter, sdxl_models | huggingface.co/h94/IP-Adapter | Apache-2.0 | ebf05d918348aec7abb02a5e9ecef77e0aaea6914a5c4ea13f50d45eb1681831 | 2026-07-16 | 0.698 GB, `tools/models/ip-adapter/sdxl_models/ip-adapter_sdxl_vit-h.safetensors`. GENERAL adapter - conditions on ONE global CLIP ViT-H embedding, so it transfers palette/costume/eye-colour but NOT facial structure or fine markings (measured 2026-08-16). Row written retroactively: the weight was downloaded 2026-07-16 for the W3 weapon pass and went unrecorded until the txt2img lane made it load-bearing. Date is the file mtime, not a fetch this session |
| CLIP ViT-H image encoder | h94/IP-Adapter, models/image_encoder | huggingface.co/h94/IP-Adapter | Apache-2.0 | 6ca9667da1ca9e0b0f75e46bb030f7e011f44f86cbfb8d5a36590fcd7507b030 | 2026-07-16 | 2.528 GB, `tools/models/ip-adapter/models/image_encoder/model.safetensors`. REQUIRED by both adapter variants below - do not re-download per variant. Must be registered on the pipe BEFORE `enable_model_cpu_offload`, or it stays unhooked on CPU and the run dies on a device mismatch (`lw_gen_run.py` `_load_pipeline_locked`, `lw_gen_weaponpass.py:262-274`) |
| IP-Adapter plus-face SDXL ViT-H | h94/IP-Adapter, sdxl_models | huggingface.co/h94/IP-Adapter | Apache-2.0 | 677ad8860204f7d0bfba12d29e6c31ded9beefdf3e4bbd102518357d31a292c1 | 2026-08-16 | 847517512 bytes (0.848 GB) at `tools/models/ip-adapter/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors`; on-disk size matches the HF file tree EXACTLY, so the transfer is complete. A `.bin` of the same weights also exists upstream (1013454761 bytes) - take the safetensors. Face-tuned: fine-grained PATCH embeddings from face crops rather than the general adapter's ONE global embedding, so it is the expected fix for what the general adapter dropped (whisker markings, bone structure) AND for its two measured costs (sharpness `lap_var` 416-492 -> 138-231; a second fox familiar hallucinating in at scale >= 0.5). Reuses the image encoder above - do NOT re-download it. Select with `--ip-adapter-weight-name ip-adapter-plus-face_sdxl_vit-h.safetensors`; WITHOUT that flag the default silently falls back to the general adapter (`tools/lw_gen_run.py` `resolve_ip_adapter`). Operator-approved 2026-08-16; the row was written BEFORE the fetch per the rule at the top of this file, and sha256 + date filled after. A first fetch attempt failed before transferring (left `refs/main` with an empty `blobs`); the retry succeeded with no error and the failure was never reproduced |

Multi-GB fetches are OPERATOR-RUN by the policy in "Phase-0 setup" below - Claude
does not execute them. Command for the pending row:

```
C:\LegionWallpaper\.venv-gen\Scripts\python.exe -c "from huggingface_hub import hf_hub_download; print(hf_hub_download('h94/IP-Adapter', 'sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors', local_dir=r'C:\LegionWallpaper\tools\models\ip-adapter'))"
```

### Subject-QA CLIP (open-clip ViT-L-14, openai pretrained - into .venv-metrics)

| model | version | source_url | license | sha256 | date | notes |
|---|---|---|---|---|---|---|
| ViT-L-14-quickgelu | openai (open-clip-torch 3.3.0) | open-clip-torch pretrained "openai" | MIT (open-clip-torch); OpenAI CLIP weight terms | (cached ~1.7GB) | 2026-07-10 | INSTALLED + weight prefetched into .venv-metrics (427.6M params load clean); torch pin held at 2.11.0+cu128. MUST be the -quickgelu variant: plain ViT-L-14 warns QuickGELU-mismatch and degrades subject-QA. Replaces the BROKEN pyiqa/clipiqa import |

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
