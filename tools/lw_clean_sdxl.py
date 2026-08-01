"""Legion Wallpaper - SDXL reconstruction inpaint worker (Stage-2 cleaning).

Replaces the LaMa erase for CONTENT-BEARING watermarks: LaMa erases a mark to a
dark blur over clothing / skin, while SDXL masked inpainting reconstructs
plausible content in the hole. A proof (Animagine XL 4.0) confirmed SDXL
reconstructs where LaMa blurs; this is that proof productionized as a batched,
SELECTABLE-checkpoint worker.

Interlock: this worker owns NOTHING but its own worklist. It is a standalone
sidecar the cleaning-pass orchestrator shells (mirrors the lw-gen sidecar
contract). It never imports the cleaning pass and touches no images/** paths of
its own choosing - every input + output path comes from the worklist.

Two-layer imports (CI / GPU-free pure tests import this module cleanly):
  top level  -> stdlib + numpy + PIL ONLY.
  ML fns     -> torch / diffusers imported LAZILY inside build_inpaint_pipe and
                _run_pipe, which the pure test suite never reaches.
The pure helpers (resolve_checkpoint / paste_back / mask_bbox / parse_worklist /
build_params / the atomic writers) are unit-tested with numpy + PIL only.

Checkpoint loader mirrors:
  lw_gen_run._load_pipeline    (single-file from_single_file, bfloat16, offload)
  lw_gen_weaponpass._build_real_inpainter (AutoPipelineForInpainting.from_pipe
                                           + the offload re-apply idiom)
Paste-back mirrors lw_clean_pass.inpaint_lama: outside-mask pixels stay
byte-identical to the input by construction (the identity assert is a tripwire).
"""
from __future__ import annotations

import argparse
import contextlib as _contextlib
import datetime as _datetime
import importlib.util as _importlib_util
import json
import os
import sys
from pathlib import Path as _Path

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------------
# Machine-wide GPU serialization (ops/loop/winmutex.py GPU_MUTEX)
# --------------------------------------------------------------------------
# One RTX 5070, shared by every headless loop on this machine. winmutex NAMES
# the mutex; the tool that touches CUDA is what ACQUIRES it - that placement is
# the only one under which a hand-run of this module is protected too, which is
# what the winmutex docstring promises.
#
# LEAF ONLY. A Windows named mutex is re-entrant per THREAD, not per process
# tree, so a child that waits on a mutex its parent holds blocks FOREVER. No
# orchestrator in this repo may acquire.
#
# This is one of four copies (lw_upscale / lw_clean_sdxl / lw_g1_gate /
# lw_gen_run). A shared tools/ helper is not importable from all four venvs;
# this module runs under C:\Tools\lw-clean\venv.
#
# 1800s: the longest legitimate single hold is a full SDXL worklist, minutes
# not hours, so half an hour is generous for a healthy holder and still only a
# third of the 5400s headless cycle deadline - leaving the cycle room to LOG
# the failure and finish. timeout=None would instead turn a wedged holder in
# another repo into an invisible hang.
GPU_MUTEX_TIMEOUT_S = 1800.0
_WINMUTEX_MOD = "lw_loop_winmutex"
_GPU_TAG = "lw_clean_sdxl"


def _bind_gpu_busy():
    """Bind tools/lw_gpu_busy.py BY PATH. See lw_g1_gate._bind_gpu_busy for why.

    Short version: one shared class object, cached under a fixed sys.modules key,
    because `except GpuBusy` matches by identity and a fork breaks every
    cross-module catch. The raise still happens before any candidate PNG is
    written, so a timeout never leaves a half-written output behind.
    """
    mod = sys.modules.get("lw_gpu_busy")
    if mod is None:
        path = _Path(__file__).resolve().parent / "lw_gpu_busy.py"
        spec = _importlib_util.spec_from_file_location("lw_gpu_busy", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load lw_gpu_busy from {path}")
        mod = _importlib_util.module_from_spec(spec)
        sys.modules["lw_gpu_busy"] = mod
        spec.loader.exec_module(mod)
    return mod


# The ONE GpuBusy. Never re-declare it here - see tools/lw_gpu_busy.py.
GpuBusy = _bind_gpu_busy().GpuBusy


def _gpu_log(msg):
    """Append one line to logs/YYYY-MM-DD.log. Never raises.

    Not print(): under pythonw.exe there is no stdout at all. The daily log is
    what the operator already reads, and it is what makes a hold window
    measurable after a concurrent run.
    """
    try:
        stamp = _datetime.datetime.now()
        log_dir = _Path(__file__).resolve().parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / f"{stamp:%Y-%m-%d}.log", "a", encoding="utf-8") as fo:
            fo.write(f"{stamp:%H:%M:%S} [{_GPU_TAG}] {msg}\n")
    except OSError:
        pass


def _winmutex():
    """Bind ops/loop/winmutex.py BY PATH (the loop_controller._bind pattern).

    ops/loop has no __init__.py, and the lw-clean venv does not have the repo
    root on sys.path, so a package-style import would fail everywhere the code
    actually executes while passing in CI.
    """
    mod = sys.modules.get(_WINMUTEX_MOD)
    if mod is not None:
        return mod
    path = _Path(__file__).resolve().parent.parent / "ops" / "loop" / "winmutex.py"
    spec = _importlib_util.spec_from_file_location(_WINMUTEX_MOD, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load winmutex from {path}")
    mod = _importlib_util.module_from_spec(spec)
    sys.modules[_WINMUTEX_MOD] = mod
    spec.loader.exec_module(mod)
    return mod


@_contextlib.contextmanager
def gpu_lock(device="cuda", log=None):
    """Hold GPU_MUTEX around real CUDA work. A no-op when device is not cuda.

    The CPU fallback must NOT take it: serializing CPU work across repos buys
    nothing and costs throughput. A winmutex import failure DEGRADES to unheld
    with the same UNSERIALIZED marker winmutex itself emits - the mutex is a
    cross-repo governor, not a dependency of this tool, and a venv that cannot
    see it must still be able to clean.
    """
    if str(device) != "cuda":
        yield None
        return

    def sink(msg):
        _gpu_log(msg)
        if log is not None:
            log(msg)

    try:
        wm = _winmutex()
    except Exception as exc:  # noqa: BLE001 - a governor must never be fatal
        sink(f"winmutex: UNSERIALIZED GPU - cannot bind ops/loop/winmutex.py "
             f"({type(exc).__name__}: {exc}); proceeding WITHOUT the lock")
        yield None
        return

    try:
        with wm.hold(wm.GPU_MUTEX, timeout=GPU_MUTEX_TIMEOUT_S, log=sink) as handle:
            yield handle
    except wm.MutexTimeout as exc:
        sink(f"winmutex: TIMEOUT on {wm.GPU_MUTEX} after {GPU_MUTEX_TIMEOUT_S}s "
             f"- another process still holds the GPU; abandoning this step")
        raise GpuBusy(
            f"GPU busy elsewhere for more than {GPU_MUTEX_TIMEOUT_S}s") from exc


# Checkpoint registry: name -> path relative to the repo root (C:/LegionWallpaper).
#   animagine   = the anime SDXL finetune the reconstruction proof used (single
#                 opt .safetensors; from_single_file).
#   dreamshaper = general SDXL diffusers folder (from_pretrained).
#   realvis     = RealVisXL V5.0 diffusers folder (from_pretrained).
CHECKPOINT_REGISTRY = {
    "animagine": "tools/models/animagine-xl-4.0/animagine-xl-4.0-opt.safetensors",
    "dreamshaper": "tools/models/dreamshaper-xl",
    "realvis": "tools/models/realvisxl5_diffusers",
}

# Reconstruction defaults (design intent: rebuild plausible content, not erase).
DEFAULT_PROMPT = (
    "league of legends splash art, highly detailed digital painting, seamless "
    "continuation of character and background, clothing skin scenery, dramatic "
    "cinematic lighting, clean"
)
DEFAULT_NEG = (
    "text, watermark, signature, url, website, letters, words, logo, caption, "
    "blurry, smudge, dark blur, low quality, artifacts"
)

DEFAULT_STRENGTH = 0.99
DEFAULT_STEPS = 30
DEFAULT_GUIDANCE = 6.0
DEFAULT_SEED = 22

# Mask threshold: >= this L-value counts as "inpaint here" (white=inpaint).
MASK_THRESHOLD = 128


# --------------------------------------------------------------------------
# Pure helpers (torch-free; unit-tested directly).
# --------------------------------------------------------------------------
def resolve_checkpoint(name_or_path, isdir=None, isfile=None):
    """Resolve a registry NAME or a raw path to (abs_path, kind).

    kind is "single_file" or "folder". Pure + injectable probes (isdir / isfile
    default to os.path.*) so it is unit-testable with no torch and no real files
    on disk. Detection order:
      - a registry name  -> substitute its relative path, then re-resolve.
      - a .safetensors / .ckpt path -> single_file (existence NOT required here;
        the loader reports a missing file with a friendly error).
      - an existing directory holding model_index.json -> folder (diffusers).
      - anything else -> ValueError (cannot classify).
    """
    isdir = os.path.isdir if isdir is None else isdir
    isfile = os.path.isfile if isfile is None else isfile
    key = str(name_or_path)
    if key in CHECKPOINT_REGISTRY:
        key = CHECKPOINT_REGISTRY[key]
    abs_path = key if os.path.isabs(key) else os.path.join(ROOT, key)
    low = abs_path.lower()
    if low.endswith(".safetensors") or low.endswith(".ckpt"):
        return abs_path, "single_file"
    if isdir(abs_path) and isfile(os.path.join(abs_path, "model_index.json")):
        return abs_path, "folder"
    raise ValueError(
        f"cannot classify checkpoint {name_or_path!r} ({abs_path}): expected a "
        "registry name, a .safetensors / .ckpt file, or a diffusers folder "
        "containing model_index.json"
    )


def paste_back(inp_arr, result_arr, mask_arr):
    """Composite result INSIDE the mask onto inp, leaving OUTSIDE byte-identical.

    out = where(mask>=threshold, result, inp). np.where copies the input value
    verbatim outside the mask (design_weapon.md / lw_clean_pass.inpaint_lama
    identity rule), so no out-of-mask pixel can drift. mask WHITE (>=128) =
    inpaint. Result carries the input's dtype.
    """
    inp = np.asarray(inp_arr)
    result = np.asarray(result_arr)
    binary = np.asarray(mask_arr) >= MASK_THRESHOLD
    if inp.ndim == 3 and binary.ndim == 2:
        binary = binary[:, :, None]
    return np.where(binary, result, inp).astype(inp.dtype)


def assert_outside_identity(inp_arr, final_arr, mask_arr):
    """Raise AssertionError unless final == inp on every pixel OUTSIDE the mask.

    The cleaning-pass non-regression tripwire: an SDXL inpaint must never touch a
    pixel the mask did not cover (mirrors lw_gen_weaponpass.assert_outside_
    identity + lw_clean_pass's G2 outside check).
    """
    inp = np.asarray(inp_arr)
    final = np.asarray(final_arr)
    binary = np.asarray(mask_arr) >= MASK_THRESHOLD
    if not np.array_equal(final[~binary], inp[~binary]):
        raise AssertionError(
            "SDXL clean pass mutated pixels OUTSIDE the mask "
            "(paste-back identity violated)"
        )


def mask_bbox(mask_arr):
    """Bounding box [x0, y0, x1, y1] (x1/y1 EXCLUSIVE) of the white region.

    None when the mask has no white (>=128) pixel. Pure numpy; recorded in the
    params sidecar so the orchestrator can audit what region was reconstructed.
    """
    binary = np.asarray(mask_arr) >= MASK_THRESHOLD
    if binary.ndim == 3:
        binary = binary.any(axis=2)
    ys, xs = np.where(binary)
    if ys.size == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def parse_worklist(path):
    """Load + validate a worklist JSON: a list of {slug, image, mask, out} dicts.

    Raises ValueError on any structural problem (not a list, an item is not an
    object, or an item is missing a required key). Pure (json only).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"worklist must be a JSON list of items: {path}")
    required = ("slug", "image", "mask", "out")
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"worklist item {i} is not a JSON object")
        missing = [k for k in required if k not in item]
        if missing:
            raise ValueError(f"worklist item {i} missing keys: {missing}")
    return data


def build_params(checkpoint, strength, steps, guidance, seed, mask_bbox):
    """The params sidecar dict (JSON-serializable) recorded next to each output."""
    return {
        "checkpoint": checkpoint,
        "strength": float(strength),
        "steps": int(steps),
        "guidance": float(guidance),
        "seed": int(seed),
        "mask_bbox": mask_bbox,
    }


# --------------------------------------------------------------------------
# I/O helpers (atomic writes per project hard rule: tmp + os.replace).
# --------------------------------------------------------------------------
def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fo:
        fo.write(json.dumps(data, indent=2) + "\n")
        fo.flush()
        os.fsync(fo.fileno())
    os.replace(tmp, path)


def _atomic_write_png(path, image):
    tmp = path + ".tmp"
    image.save(tmp, format="PNG")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# ML layer (LAZY torch / diffusers - never reached by the pure test suite).
# --------------------------------------------------------------------------
_PIPE_CACHE = {}


def build_inpaint_pipe(abs_path, kind, offload=True):
    """Build (and cache) the SDXL inpaint pipe for a resolved checkpoint.

    Loads the base per kind (from_single_file for single_file; from_pretrained
    with variant fp16 for a diffusers folder, torch_dtype bfloat16), then
    AutoPipelineForInpainting.from_pipe(base, controlnet=None) - a plain SDXL
    inpaint pipe sharing the base weights (zero extra VRAM; mirrors
    lw_gen_weaponpass._build_real_inpainter). Cached on (abs_path, kind, offload)
    so a sequential worklist loads the model ONCE (the GPU is one device).
    """
    key = (abs_path, kind, bool(offload))
    if key in _PIPE_CACHE:
        return _PIPE_CACHE[key]
    import torch
    from diffusers import AutoPipelineForInpainting, StableDiffusionXLPipeline

    if kind == "single_file":
        base = StableDiffusionXLPipeline.from_single_file(
            abs_path, torch_dtype=torch.bfloat16)
    elif kind == "folder":
        try:
            base = StableDiffusionXLPipeline.from_pretrained(
                abs_path, torch_dtype=torch.bfloat16, variant="fp16")
        except Exception:  # noqa: BLE001 - some diffusers folders ship no fp16 shards
            base = StableDiffusionXLPipeline.from_pretrained(
                abs_path, torch_dtype=torch.bfloat16)
    else:
        raise ValueError(f"unknown checkpoint kind: {kind!r}")

    inpipe = AutoPipelineForInpainting.from_pipe(base, controlnet=None)
    # cpu-offload manages device placement itself; only .to(cuda) on the
    # all-resident path (mirrors lw_gen_run._load_pipeline).
    if offload:
        inpipe.enable_model_cpu_offload()
    else:
        inpipe = inpipe.to("cuda")
    # A full-res (2560x1440) VAE decode allocates ~1.76GB in one buffer and
    # OOMs a 12GB card; tile the VAE so the decode streams (mirrors
    # lw_gen_run._load_pipeline:451-455, the gen config tiled_vae=true).
    if getattr(inpipe, "vae", None) is not None:
        try:
            inpipe.vae.enable_tiling()
            inpipe.vae.enable_slicing()
        except Exception:  # noqa: BLE001 - tiling is best-effort
            pass
    _PIPE_CACHE[key] = inpipe
    return inpipe


def _run_pipe(pipe, image, mask, prompt, negative, strength, steps, guidance, seed):
    """Run one masked inpaint roll -> raw PIL result (pre paste-back). LAZY torch."""
    import torch

    generator = torch.Generator("cuda").manual_seed(int(seed))
    return pipe(
        prompt=prompt, negative_prompt=negative, image=image, mask_image=mask,
        strength=float(strength), num_inference_steps=int(steps),
        guidance_scale=float(guidance), width=image.width, height=image.height,
        generator=generator,
    ).images[0]


def inpaint_item(pipe, image, mask, prompt, negative, strength, steps, guidance,
                 seed):
    """Inpaint one item and paste-back -> (composited PIL RGB, mask_bbox).

    image is RGB, mask is "L" (white=inpaint). Runs the pipe, resizes the result
    to the input size if the pipe rounded it, composites so OUTSIDE-mask pixels
    are byte-identical to image, asserts that identity, and returns the composite
    plus the white-region bbox for the sidecar.
    """
    result = _run_pipe(pipe, image, mask, prompt, negative, strength, steps,
                       guidance, seed)
    if result.size != image.size:
        result = result.resize(image.size)
    inp_arr = np.asarray(image.convert("RGB"))
    result_arr = np.asarray(result.convert("RGB"))
    mask_arr = np.asarray(mask.convert("L"))
    composited = paste_back(inp_arr, result_arr, mask_arr)
    assert_outside_identity(inp_arr, composited, mask_arr)
    return Image.fromarray(composited), mask_bbox(mask_arr)


# --------------------------------------------------------------------------
# Worklist driver + selfcheck.
# --------------------------------------------------------------------------
def run_worklist(items, checkpoint, strength, steps, guidance, seed, prompt,
                 negative, offload=True, log=print):
    """Process the worklist SEQUENTIALLY (model loaded once). Returns done count.

    Per item: inpaint -> atomic-write <out>/<slug>_sdxl_cand.png +
    <out>/<slug>_sdxl.json. One progress line per item, then the
    `LW SDXL | done=<n> checkpoint=<name>` banner and a SENTINEL_DONE line.
    """
    abs_path, kind = resolve_checkpoint(checkpoint)
    done = 0
    # ONE hold spanning the checkpoint load and EVERY item. The pipe stays
    # resident on the card for the whole worklist (that is the point of the
    # cache), so releasing between items would hand another process a card LW
    # still occupies - the exact OOM this serializes away. Nothing inside this
    # block spawns a subprocess, so the child-waits-on-parent trap does not
    # apply here.
    with gpu_lock("cuda", log=log):
        pipe = build_inpaint_pipe(abs_path, kind, offload=offload)
        for item in items:
            image = Image.open(item["image"]).convert("RGB")
            mask = Image.open(item["mask"]).convert("L")
            composited, bbox = inpaint_item(
                pipe, image, mask, prompt, negative, strength, steps, guidance,
                seed)
            out_dir = item["out"]
            os.makedirs(out_dir, exist_ok=True)
            cand_path = os.path.join(out_dir, f"{item['slug']}_sdxl_cand.png")
            json_path = os.path.join(out_dir, f"{item['slug']}_sdxl.json")
            _atomic_write_png(cand_path, composited)
            _atomic_write_json(
                json_path,
                build_params(checkpoint, strength, steps, guidance, seed, bbox))
            done += 1
            log(f"LW SDXL | {item['slug']} -> {cand_path} bbox={bbox}")
    log(f"LW SDXL | done={done} checkpoint={checkpoint}")
    log("SENTINEL_DONE")
    return done


def selfcheck(checkpoint, offload=True):
    """Resolve + load the checkpoint; return a JSON-able readiness dict.

    Never raises: on any load failure it reports ready=False + a friendly error
    (the raw exception text is captured for the caller's log, not a UI panel).
    """
    info = {"tool": "lw_clean_sdxl", "checkpoint": checkpoint}
    try:
        abs_path, kind = resolve_checkpoint(checkpoint)
        info["abs_path"] = abs_path
        info["kind"] = kind
        info["exists"] = os.path.exists(abs_path)
        # selfcheck really does put SDXL weights on the card, so it takes the
        # mutex like any other GPU consumer. A GpuBusy here is caught by the
        # except below and reported as ready=False rather than a traceback.
        with gpu_lock("cuda"):
            build_inpaint_pipe(abs_path, kind, offload=offload)
        info["offload"] = bool(offload)
        info["loaded"] = True
        info["ready"] = True
    except Exception as exc:  # noqa: BLE001 - selfcheck reports readiness, never crashes
        info["loaded"] = False
        info["ready"] = False
        info["error"] = str(exc)
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="SDXL reconstruction inpaint worker for the Stage-2 "
                    "cleaning pass (content-bearing watermarks).")
    ap.add_argument("--worklist",
                    help='JSON list of {"slug","image","mask","out"} items')
    ap.add_argument("--checkpoint", default="animagine",
                    help="registry name (animagine|dreamshaper|realvis) or a raw path")
    ap.add_argument("--strength", type=float, default=DEFAULT_STRENGTH)
    ap.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    ap.add_argument("--guidance", type=float, default=DEFAULT_GUIDANCE)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--neg", default=DEFAULT_NEG)
    ap.add_argument("--no-offload", action="store_true",
                    help="skip enable_model_cpu_offload (all-resident .to cuda)")
    ap.add_argument("--selfcheck", action="store_true",
                    help="resolve + load the checkpoint, print JSON readiness, exit")
    args = ap.parse_args(argv)
    offload = not args.no_offload

    if args.selfcheck:
        info = selfcheck(args.checkpoint, offload=offload)
        print(json.dumps(info))
        return 0 if info.get("ready") else 4

    if not args.worklist:
        print(json.dumps({"error": "provide --worklist <json> or --selfcheck"}))
        return 2

    items = parse_worklist(args.worklist)
    run_worklist(items, args.checkpoint, args.strength, args.steps, args.guidance,
                 args.seed, args.prompt, args.neg, offload=offload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
