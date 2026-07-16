"""Legion Wallpaper - W4 in-house UNet-only SDXL LoRA trainer (weapon concept).

Path (b) of the approved W4 spec: a self-contained DreamBooth-style LoRA
trainer built on the diffusers 0.39 + peft 0.19 + accelerate stack already
resident in .venv-gen. Zero external downloads - the base model is the single
6.9GB Animagine XL 4.0 opt checkpoint loaded with
`StableDiffusionXLPipeline.from_single_file` (the proven load path,
lw_gen_run.py:431-433), and the training crops ship in the repo.

Design of record: docs/research/golden_designs/design_weapon.md sec 5 (W4).
The saved artifact round-trips through the runtime contract at
design_weapon.md:177-184:
    inpipe.load_lora_weights(out_dir, adapter_name="vayne_weapon")
    inpipe.set_adapters(["vayne_weapon"], adapter_weights=[0.8])
so the trainer writes pytorch_lora_weights.safetensors via the diffusers SDXL
LoRA save path (get_peft_model_state_dict -> convert_state_dict_to_diffusers ->
StableDiffusionXLPipeline.save_lora_weights).

Only the UNet gets a LoRA adapter (r=alpha=rank, gaussian init, attention
projections). The VAE and BOTH text encoders are frozen; the text encoders are
run ONCE to precompute the (near-identical) caption embeds, then freed to keep
the run inside the RTX 5070 12GB budget. Six base crops -> on-the-fly geometric
+ mild color augmentation per step to avoid memorization.

CI constraint (torch-free): this module imports ONLY stdlib at top level. Every
heavy dependency (torch / diffusers / peft / PIL / numpy) is imported lazily
inside the training path, which the unit tests never reach. The pure helpers
(list_pairs / read_caption / sample_aug) are unit-tested without torch.
"""
from __future__ import annotations

import argparse
import glob
import os
import random
import sys
import time

# Allow both `python tools/lw_gen_train_weapon_lora.py` (script mode) and
# `from tools import lw_gen_train_weapon_lora` to resolve. Mirror the repo shim.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# --- defaults (design_weapon.md sec 5: UNet-only, 1024px, adamw, rank 16, 1e-4) -
_DEFAULT_MODEL = os.path.join(
    "tools", "models", "animagine-xl-4.0", "animagine-xl-4.0-opt.safetensors"
)
_DEFAULT_DATA = os.path.join("tools", "models", "lora_datasets", "vayne_weapon_train")
_DEFAULT_OUT = os.path.join("tools", "models", "loras", "vayne_weapon")

# LoRA targets the UNet attention projections (spec sec 5).
_TARGET_MODULES = ["to_k", "to_q", "to_v", "to_out.0"]
# Neutral gray fill for rotation-expand + letterbox padding (mid of [-1, 1]).
_NEUTRAL_FILL = (128, 128, 128)


# --------------------------------------------------------------------------
# Pure helpers (torch-free; unit-tested directly).
# --------------------------------------------------------------------------
def list_pairs(data_dir):
    """Return sorted [(png, txt), ...] for every PNG that has a paired caption.

    A PNG with no same-stem .txt (an orphan) is skipped. Sorted by PNG path so
    the training order is deterministic.
    """
    pairs = []
    for png in sorted(glob.glob(os.path.join(data_dir, "*.png"))):
        txt = os.path.splitext(png)[0] + ".txt"
        if os.path.isfile(txt):
            pairs.append((png, txt))
    return pairs


def read_caption(txt):
    """Return the caption text, stripped of surrounding whitespace/newlines."""
    with open(txt, encoding="utf-8") as fo:
        return fo.read().strip()


def sample_aug(rng):
    """Sample the geometric augmentation params for one step.

    Deterministic given a seeded random.Random. Returns exactly the keys the
    heavy loader consumes:
      angle - degrees in [-10, 10]
      scale - factor in [0.9, 1.1]
      flip  - bool (horizontal flip)
    """
    return {
        "angle": rng.uniform(-10.0, 10.0),
        "scale": rng.uniform(0.9, 1.1),
        "flip": rng.random() < 0.5,
    }


def sample_jitter(rng):
    """Sample mild color-jitter factors (torch-free, deterministic given rng)."""
    return {
        "color": rng.uniform(0.9, 1.1),
        "brightness": rng.uniform(0.95, 1.05),
        "contrast": rng.uniform(0.95, 1.05),
    }


def _abs(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


# --------------------------------------------------------------------------
# Heavy path (lazy imports; never reached by CI).
# --------------------------------------------------------------------------
def _center_square(img, resolution):
    """Aspect-preserving fit of a PIL image onto a neutral square canvas."""
    from PIL import Image

    w, h = img.size
    scale = resolution / max(w, h)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    img = img.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (resolution, resolution), _NEUTRAL_FILL)
    canvas.paste(img, ((resolution - nw) // 2, (resolution - nh) // 2))
    return canvas


def _load_augmented(png, aug, jitter, resolution):
    """Load one crop, apply flip/rotate/scale + mild color jitter, return a
    CHW float tensor in [-1, 1] at resolution x resolution."""
    import numpy as np
    import torch
    from PIL import Image, ImageEnhance

    img = Image.open(png).convert("RGB")
    if aug["flip"]:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if abs(aug["angle"]) > 1e-6:
        img = img.rotate(
            aug["angle"], resample=Image.BILINEAR, expand=True, fillcolor=_NEUTRAL_FILL
        )
    w, h = img.size
    img = img.resize(
        (max(1, int(round(w * aug["scale"]))), max(1, int(round(h * aug["scale"])))),
        Image.BILINEAR,
    )
    img = ImageEnhance.Color(img).enhance(jitter["color"])
    img = ImageEnhance.Brightness(img).enhance(jitter["brightness"])
    img = ImageEnhance.Contrast(img).enhance(jitter["contrast"])
    img = _center_square(img, resolution)
    arr = np.asarray(img, dtype=np.float32) / 127.5 - 1.0
    return torch.from_numpy(arr).permute(2, 0, 1).contiguous()


def _time_ids(resolution):
    """SDXL micro-conditioning time-ids: (orig_h, orig_w, crop_top, crop_left,
    target_h, target_w) - square, no crop."""
    import torch

    return torch.tensor(
        [[resolution, resolution, 0, 0, resolution, resolution]], dtype=torch.float32
    )


def _atomic_save_lora(unet, out_dir, get_sd, convert_sd, pipe_cls):
    """Save the UNet LoRA as pytorch_lora_weights.safetensors, atomically.

    Writes into a sibling .tmp_save dir, then os.replace()s the file into place
    so a mid-write consumer never sees a partial artifact.
    """
    import shutil

    unet_lora = convert_sd(get_sd(unet))
    parent = os.path.dirname(os.path.abspath(out_dir)) or "."
    os.makedirs(parent, exist_ok=True)
    tmp_dir = out_dir + ".tmp_save"
    if os.path.isdir(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir, exist_ok=True)
    pipe_cls.save_lora_weights(save_directory=tmp_dir, unet_lora_layers=unet_lora)
    os.makedirs(out_dir, exist_ok=True)
    src = os.path.join(tmp_dir, "pytorch_lora_weights.safetensors")
    dst = os.path.join(out_dir, "pytorch_lora_weights.safetensors")
    os.replace(src, dst)
    shutil.rmtree(tmp_dir, ignore_errors=True)


def train(args):
    """Run the UNet-only SDXL LoRA training loop and save the adapter."""
    import torch
    import torch.nn.functional as F
    from diffusers import DDPMScheduler, StableDiffusionXLPipeline
    from diffusers.training_utils import cast_training_params, compute_snr, free_memory
    from diffusers.utils import convert_state_dict_to_diffusers
    from peft import LoraConfig
    from peft.utils import get_peft_model_state_dict

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for LoRA training (no GPU visible).")
    device = torch.device("cuda")
    weight_dtype = torch.bfloat16

    model_abs = _abs(args.model)
    data_abs = _abs(args.data)
    out_abs = _abs(args.out)

    pairs = list_pairs(data_abs)
    if not pairs:
        raise RuntimeError(f"no (png,txt) training pairs under {data_abs}")

    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)

    # 1. Load the base pipe on the proven single-file path (bf16), CPU-resident.
    pipe = StableDiffusionXLPipeline.from_single_file(model_abs, torch_dtype=weight_dtype)

    # 2. Precompute caption embeds ONCE per unique caption, then free the text
    #    encoders (the big VRAM lever - captions here are identical).
    pipe.text_encoder.to(device)
    pipe.text_encoder_2.to(device)
    embed_cache = {}
    captions = [read_caption(txt) for _png, txt in pairs]
    with torch.no_grad():
        for cap in captions:
            if cap in embed_cache:
                continue
            pe, _neg, ppe, _negp = pipe.encode_prompt(
                prompt=cap,
                prompt_2=cap,
                device=device,
                num_images_per_prompt=1,
                do_classifier_free_guidance=False,
            )
            embed_cache[cap] = (pe.to(weight_dtype), ppe.to(weight_dtype))
    pipe.text_encoder = None
    pipe.text_encoder_2 = None
    free_memory()

    # 3. UNet + VAE resident on GPU; both frozen (LoRA rides on the UNet).
    unet = pipe.unet
    vae = pipe.vae
    vae.to(device)
    unet.to(device)
    vae.requires_grad_(False)
    unet.requires_grad_(False)
    scaling = vae.config.scaling_factor

    # DDPM forward process from the checkpoint's scheduler config (respects its
    # prediction_type - epsilon vs v_prediction - never hardcoded).
    noise_scheduler = DDPMScheduler.from_config(pipe.scheduler.config)
    num_train_ts = noise_scheduler.config.num_train_timesteps
    pred_type = noise_scheduler.config.prediction_type

    # 4. Attach the LoRA adapter; keep its params in fp32; grad-checkpoint on.
    lora_config = LoraConfig(
        r=args.rank,
        lora_alpha=args.rank,
        init_lora_weights="gaussian",
        target_modules=_TARGET_MODULES,
    )
    unet.add_adapter(lora_config)
    cast_training_params(unet, dtype=torch.float32)
    unet.enable_gradient_checkpointing()
    unet.train()

    lora_params = [p for p in unet.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(lora_params, lr=args.lr)

    add_time_ids = _time_ids(args.resolution).to(device, dtype=weight_dtype)

    torch.cuda.reset_peak_memory_stats()
    step_times = []
    n = len(pairs)

    # 5. Train loop: augment -> VAE encode -> noise -> UNet eps/v MSE (+min-SNR).
    for step in range(args.max_steps):
        t0 = time.perf_counter()
        png, _txt = pairs[step % n]
        cap = captions[step % n]
        aug = sample_aug(rng)
        jitter = sample_jitter(rng)
        pixel = (
            _load_augmented(png, aug, jitter, args.resolution)
            .unsqueeze(0)
            .to(device, dtype=weight_dtype)
        )

        with torch.no_grad():
            latents = vae.encode(pixel).latent_dist.sample() * scaling
        latents = latents.to(weight_dtype)

        noise = torch.randn_like(latents)
        bsz = latents.shape[0]
        timesteps = torch.randint(0, num_train_ts, (bsz,), device=device).long()
        noisy = noise_scheduler.add_noise(latents, noise, timesteps)

        pe, ppe = embed_cache[cap]
        added = {"text_embeds": ppe, "time_ids": add_time_ids}

        with torch.autocast("cuda", dtype=weight_dtype):
            model_pred = unet(
                noisy,
                timesteps,
                encoder_hidden_states=pe,
                added_cond_kwargs=added,
                return_dict=False,
            )[0]

        if pred_type == "epsilon":
            target = noise
        elif pred_type == "v_prediction":
            target = noise_scheduler.get_velocity(latents, noise, timesteps)
        else:
            raise ValueError(f"unsupported prediction_type: {pred_type}")

        if args.snr_gamma and args.snr_gamma > 0:
            snr = compute_snr(noise_scheduler, timesteps)
            gamma_t = torch.full_like(snr, float(args.snr_gamma))
            base_wt = torch.stack([snr, gamma_t], dim=1).min(dim=1)[0]
            mse_wt = base_wt / snr if pred_type == "epsilon" else base_wt / (snr + 1)
            loss = F.mse_loss(model_pred.float(), target.float(), reduction="none")
            loss = loss.mean(dim=list(range(1, len(loss.shape)))) * mse_wt
            loss = loss.mean()
        else:
            loss = F.mse_loss(model_pred.float(), target.float(), reduction="mean")

        loss.backward()
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)

        step_times.append(time.perf_counter() - t0)
        if step == 0 or (step + 1) % 10 == 0 or step == args.max_steps - 1:
            print(f"[train] step {step + 1}/{args.max_steps} loss={loss.item():.4f}")

        if (
            args.save_every
            and (step + 1) % args.save_every == 0
            and (step + 1) < args.max_steps
        ):
            ckpt = os.path.join(out_abs, f"checkpoint-{step + 1}")
            _atomic_save_lora(
                unet, ckpt, get_peft_model_state_dict,
                convert_state_dict_to_diffusers, StableDiffusionXLPipeline,
            )

    # 6. Final save via the diffusers SDXL LoRA path (round-trips at runtime).
    _atomic_save_lora(
        unet, out_abs, get_peft_model_state_dict,
        convert_state_dict_to_diffusers, StableDiffusionXLPipeline,
    )

    peak = torch.cuda.max_memory_allocated() / 1e9
    avg = sum(step_times) / max(1, len(step_times))
    print(
        f"[train] done - {args.max_steps} steps, pred={pred_type}, "
        f"peak VRAM {peak:.2f} GB, avg {avg:.2f}s/step, saved -> {out_abs}"
    )
    return {
        "peak_vram_gb": peak,
        "avg_step_s": avg,
        "out": out_abs,
        "steps": args.max_steps,
        "prediction_type": pred_type,
    }


def _log_error(exc):
    """Append the raw error to logs/ - never surface it to the user."""
    try:
        import datetime

        logs = os.path.join(ROOT, "logs")
        os.makedirs(logs, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(logs, f"{stamp}.log"), "a", encoding="utf-8") as fo:
            fo.write(f"[lw_gen_train_weapon_lora] {type(exc).__name__}: {exc}\n")
    except OSError:
        pass


def build_parser():
    p = argparse.ArgumentParser(
        description="UNet-only SDXL LoRA trainer (W4 Vayne weapon concept)."
    )
    p.add_argument("--model", default=_DEFAULT_MODEL)
    p.add_argument("--data", default=_DEFAULT_DATA)
    p.add_argument("--out", default=_DEFAULT_OUT)
    p.add_argument("--rank", type=int, default=16)
    p.add_argument("--resolution", type=int, default=1024)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--max-steps", dest="max_steps", type=int, default=1000)
    p.add_argument("--save-every", dest="save_every", type=int, default=250)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--snr-gamma", dest="snr_gamma", type=float, default=5.0)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        train(args)
    except Exception as exc:  # noqa: BLE001 - never surface a raw torch/diffusers trace
        print(
            "weapon LoRA training failed - generator not provisioned or a "
            "backend/VRAM error (see logs). Run the Phase-0 setup "
            "(docs/GEN_MODELS.md).",
            file=sys.stderr,
        )
        _log_error(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
