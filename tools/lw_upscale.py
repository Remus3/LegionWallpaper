"""Legion Wallpaper - first-pass upscaler with two pluggable backends.

Backends:
  - spandrel/torch (primary): IllustrationJaNai DAT2 4x model, tiled inference.
  - realesrgan-ncnn-vulkan.exe (fallback): x4plus-anime.

Structural rule (never double-resample): exactly ONE AI upscale (4x),
ONE Lanczos downscale to the 2560x1440 target, ONE light unsharp mask.
Do not add extra resamples anywhere in this module.

Corollary - no resample, no sharpen: a source that is already exactly
2560x1440 gets NEITHER the (no-op) downscale nor the unsharp mask, because
sharpening pixels nothing touched only manufactures halos. See _usm_applies.

CI constraint: only PIL + numpy + stdlib may be imported at module top
level. torch and spandrel are LAZY-imported inside the spandrel-backend
functions so this module imports cleanly on a torch-less Python (CI 3.12,
system 3.14). No cv2 anywhere.
"""

from __future__ import annotations

import contextlib as _contextlib
import datetime as _datetime
import hashlib
import importlib.util as _importlib_util
import os
import subprocess
import sys as _sys
import time
from pathlib import Path as _Path

from PIL import Image, ImageFilter

# --------------------------------------------------------------------------
# Machine-wide GPU serialization (ops/loop/winmutex.py GPU_MUTEX)
# --------------------------------------------------------------------------
# One RTX 5070, shared by every headless loop on this machine. winmutex NAMES
# the mutex; the tool that touches CUDA is what ACQUIRES it - that placement is
# the only one under which a hand-run of this module is protected too, which is
# what the winmutex docstring promises.
#
# LEAF ONLY. A Windows named mutex is re-entrant per THREAD, not per process
# tree, so a child that waits on a mutex its parent holds blocks FOREVER.
# tools/lw_first_pass.py spawns this module under .venv-upscale, so an
# orchestrator-level hold would deadlock first pass against its own child.
# first_pass() below deliberately does not acquire - it also has a
# downscale-only branch that never touches the GPU at all.
#
# This is one of four copies (lw_upscale / lw_clean_sdxl / lw_g1_gate /
# lw_gen_run). A shared tools/ helper is not importable from all four venvs,
# and this module is contractually limited to PIL + numpy + stdlib at top level.
#
# 1800s: the longest legitimate single hold is a tiled 4x upscale of a large
# source, minutes not hours, so half an hour is generous for a healthy holder
# and still only a third of the 5400s headless cycle deadline - leaving the
# cycle room to LOG the failure and finish. timeout=None would instead turn a
# wedged holder in another repo into an invisible hang.
GPU_MUTEX_TIMEOUT_S = 1800.0
_WINMUTEX_MOD = "lw_loop_winmutex"
_GPU_TAG = "lw_upscale"


def _bind_gpu_busy():
    """Bind tools/lw_gpu_busy.py BY PATH. See lw_g1_gate._bind_gpu_busy for why.

    Short version: one shared class object, cached under a fixed sys.modules key,
    because `except GpuBusy` matches by identity and a fork breaks every
    cross-module catch. Here the raise still happens before any output file is
    written, so a timeout never leaves a half-written PNG behind.
    """
    mod = _sys.modules.get("lw_gpu_busy")
    if mod is None:
        path = _Path(__file__).resolve().parent / "lw_gpu_busy.py"
        spec = _importlib_util.spec_from_file_location("lw_gpu_busy", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load lw_gpu_busy from {path}")
        mod = _importlib_util.module_from_spec(spec)
        _sys.modules["lw_gpu_busy"] = mod
        spec.loader.exec_module(mod)
    return mod


# The ONE GpuBusy. Never re-declare it here - see tools/lw_gpu_busy.py.
GpuBusy = _bind_gpu_busy().GpuBusy


def _gpu_log(msg):
    """Append one line to logs/YYYY-MM-DD.log. Never raises.

    Not print(): under pythonw.exe there is no stdout at all, and this module is
    run as a `python -c` child whose stdout carries a JSON contract that a stray
    line would corrupt. The daily log is what the operator already reads, and it
    is what makes a hold window measurable after a concurrent run.
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

    ops/loop has no __init__.py, and .venv-upscale does not have the repo root
    on sys.path, so a package-style import would fail everywhere the code
    actually executes while passing in CI.
    """
    mod = _sys.modules.get(_WINMUTEX_MOD)
    if mod is not None:
        return mod
    path = _Path(__file__).resolve().parent.parent / "ops" / "loop" / "winmutex.py"
    spec = _importlib_util.spec_from_file_location(_WINMUTEX_MOD, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load winmutex from {path}")
    mod = _importlib_util.module_from_spec(spec)
    _sys.modules[_WINMUTEX_MOD] = mod
    spec.loader.exec_module(mod)
    return mod


@_contextlib.contextmanager
def gpu_lock(device="cuda", log=None):
    """Hold GPU_MUTEX around real CUDA work. A no-op when device is not cuda.

    The CPU fallback must NOT take it: serializing CPU work across repos buys
    nothing and costs throughput. A winmutex import failure DEGRADES to unheld
    with the same UNSERIALIZED marker winmutex itself emits - the mutex is a
    cross-repo governor, not a dependency of this tool, and a venv that cannot
    see it must still be able to upscale.
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


# Target output geometry and the finishing unsharp-mask defaults. These are
# the exact values Session 1 used; keep them identical so an IJN-vs-fallback
# comparison isolates only the upscaler.
TARGET = (2560, 1440)
USM_DEFAULT = (1.2, 70, 3)

# UnsharpMask parameter caps (documented sane maxima). radius controls the
# blur kernel used for the mask; a large radius produces coarse haloing, so we
# clamp it. percent is the sharpening strength; over ~150 the result rings.
# threshold is the minimum tonal difference that gets sharpened; it cannot be
# negative.
USM_MAX_RADIUS = 3.0
USM_MAX_PERCENT = 150
USM_MIN_THRESHOLD = 0

# Aspect-ratio match tolerance for _finish (guards against silently squashing
# a non-16:9 upscale into a 16:9 frame).
ASPECT_TOL = 0.02

# Default ncnn fallback executable location on the Legion machine.
NCNN_EXE_DEFAULT = r"C:\Tools\realesrgan\realesrgan-ncnn-vulkan.exe"

# CREATE_NO_WINDOW: Legion focus-steal rule - always pass it so a background
# subprocess does not flash a console window or steal focus. getattr guard so
# the module still imports on non-Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _sha256(path: str) -> str:
    """Return the hex sha256 of a file, streamed in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _has_alpha(img):
    """True iff a PIL image carries transparency of any kind.

    first_pass always writes RGB, so every alpha-carrying source is flattened.
    That flatten was invisible in the audit trail, which let a corpus-wide alpha
    drop go unreviewed. Mode alone is not enough: a palette PNG/GIF reports mode
    "P" yet stores real transparency in a tRNS chunk, surfaced by PIL as
    info["transparency"], so both signals are checked.
    """
    return img.mode in ("RGBA", "LA", "PA", "RGBa", "La") or (
        "transparency" in img.info
    )


def _clamp_usm(usm):
    """Clamp an unsharp-mask (radius, percent, threshold) triple to sane maxima.

    Caps: radius <= 3, percent <= 150, threshold >= 0. Returns a new tuple.
    """
    radius, percent, threshold = usm
    radius = min(float(radius), USM_MAX_RADIUS)
    percent = min(int(percent), USM_MAX_PERCENT)
    threshold = max(int(threshold), USM_MIN_THRESHOLD)
    return (radius, percent, threshold)


def _covers_target(src_w, src_h, target=TARGET):
    """True iff a source already covers the target in BOTH dimensions.

    G0 over-target gate: when the source is at least the target size on each
    axis (e.g. a 4K/8K source vs the 2560x1440 target), the AI 4x upscale is
    pathological (an 8K source blows up to a ~531-megapixel tensor and minutes
    of compute) AND the 1440p output scores false-soft under the G1 common-scale
    rule (G1 upscales the output back to the native source resolution to
    compare). ADR-002 doctrine: never double-resample. So an over-target source
    skips the AI upscale and takes ONE Lanczos downscale only. AI cleaning is the
    Stage-2 cleaning job, not first-pass.
    """
    return src_w >= target[0] and src_h >= target[1]


def _usm_applies(img_size, target=TARGET):
    """True iff the image handed to _finish will actually be resampled.

    The unsharp mask exists to recover the detail a resample softens. When the
    image is ALREADY exactly the target size the Lanczos resize is a no-op, so
    the USM would be the entire delta - it manufactures halos out of nothing and
    trips the G1 halo_pct flag (measured 0.0711 on the refs-46 batch, whose 46
    sources are all exactly 2560x1440).

    The condition is size equality, NOT `scale == 1`: a genuine 3840x2160 ->
    2560x1440 Lanczos downscale also reports scale 1 yet really does resample,
    and it MUST keep its unsharp mask.
    """
    return tuple(img_size) != tuple(target)


def _finish(upscaled_img, target=TARGET, usm=USM_DEFAULT):
    """Downscale a raw 4x upscale to the target and apply one unsharp mask.

    Pure PIL - CI-testable without torch. Performs exactly ONE Lanczos resize
    to `target` followed by exactly ONE UnsharpMask. The unsharp-mask params
    are clamped to sane maxima (radius <= 3, percent <= 150, threshold >= 0).

    Exception - no resample, no sharpen: an input that is ALREADY exactly
    `target` is returned as-is (RGB-converted only). See _usm_applies.

    Raises ValueError if the source aspect ratio does not match the target
    aspect within ASPECT_TOL - the pipeline must never silently squash aspect.
    """
    src_w, src_h = upscaled_img.size
    tgt_w, tgt_h = target
    src_aspect = src_w / src_h
    tgt_aspect = tgt_w / tgt_h
    if abs(src_aspect - tgt_aspect) > ASPECT_TOL:
        raise ValueError(
            f"aspect mismatch: source {src_w}x{src_h} ({src_aspect:.4f}) vs "
            f"target {tgt_w}x{tgt_h} ({tgt_aspect:.4f}) exceeds tolerance "
            f"{ASPECT_TOL:.4f} - refusing to squash aspect"
        )

    img = upscaled_img.convert("RGB")
    if not _usm_applies(upscaled_img.size, target):
        # Already at target: the resize is a no-op and the USM would be the
        # whole delta. Return the untouched pixels.
        return img
    # ONE Lanczos downscale to target.
    img = img.resize(target, Image.LANCZOS)
    # ONE light unsharp mask (params clamped).
    radius, percent, threshold = _clamp_usm(usm)
    img = img.filter(
        ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold)
    )
    return img


def _tile_infer(net, img_tensor, tile=512, overlap=32, scale=4):
    """Run `net` over `img_tensor` in overlapping tiles and stitch a 4x result.

    Built for the 12GB VRAM ceiling: the full image never hits the net at once.
    Splits the (1,3,H,W) input into tiles of side `tile` (input space) that
    overlap their neighbours by `overlap` pixels, runs `net` on each tile, and
    accumulates the 4x outputs into a (1,3,H*scale,W*scale) canvas using a
    per-pixel weight sum so overlapping seams are averaged (no visible seam).
    Edge tiles that run past the image are clamped to a full-size window
    anchored at the border, so every tile is exactly `tile` on a side where the
    image is large enough, and partial where it is not.

    torch is lazy-imported here so the module stays torch-free at import time.
    """
    import torch

    if overlap >= tile:
        raise ValueError(f"overlap ({overlap}) must be smaller than tile ({tile})")

    _, channels, height, width = img_tensor.shape
    out_h, out_w = height * scale, width * scale

    accum = torch.zeros(
        (1, channels, out_h, out_w), dtype=torch.float32, device=img_tensor.device
    )
    weight = torch.zeros(
        (1, 1, out_h, out_w), dtype=torch.float32, device=img_tensor.device
    )

    step = tile - overlap

    def _starts(total):
        """Tile start offsets covering [0, total) with the last tile flush right."""
        if total <= tile:
            return [0]
        pts = list(range(0, total - tile + 1, step))
        if pts[-1] != total - tile:
            pts.append(total - tile)
        return pts

    y_starts = _starts(height)
    x_starts = _starts(width)

    for y0 in y_starts:
        y1 = min(y0 + tile, height)
        for x0 in x_starts:
            x1 = min(x0 + tile, width)
            in_tile = img_tensor[:, :, y0:y1, x0:x1]
            with torch.no_grad():
                out_tile = net(in_tile)
            oy0, oy1 = y0 * scale, y1 * scale
            ox0, ox1 = x0 * scale, x1 * scale
            accum[:, :, oy0:oy1, ox0:ox1] += out_tile
            weight[:, :, oy0:oy1, ox0:ox1] += 1.0

    # Average overlapped regions. weight is >= 1 everywhere the image was
    # covered; clamp guards against any zero from a degenerate shape.
    weight = weight.clamp(min=1.0)
    return accum / weight


def _to_tensor(img):
    """PIL RGB image -> (1,3,H,W) float32 tensor in 0..1. Lazy torch/numpy."""
    import numpy as np
    import torch

    arr = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0  # H,W,3
    arr = np.transpose(arr, (2, 0, 1))  # 3,H,W
    return torch.from_numpy(arr).unsqueeze(0).contiguous()


def _to_pil(tensor):
    """(1,3,H,W) float32 tensor in 0..1 -> PIL RGB image. Lazy torch/numpy."""
    import numpy as np

    arr = tensor.squeeze(0).clamp(0.0, 1.0).mul(255.0).round()
    arr = arr.to("cpu").byte().numpy()  # 3,H,W
    arr = np.transpose(arr, (1, 2, 0))  # H,W,3
    return Image.fromarray(arr, mode="RGB")


def upscale_spandrel(src_path, model_path, tile=512, overlap=32, device="cuda"):
    """Load a spandrel model and produce the raw 4x upscale of src_path.

    Returns (raw_4x_pil_image, meta_dict). The returned image is the raw AI
    upscale (NOT yet finished - no downscale, no unsharp). torch and spandrel
    are lazy-imported here.
    """
    import torch
    from spandrel import ModelLoader

    t0 = time.time()

    src_img = Image.open(src_path).convert("RGB")
    src_dims = list(src_img.size)  # (w, h)

    # ONE hold spanning model load -> tiled inference -> empty_cache. Splitting
    # it would let another process allocate against a card that already holds a
    # partially resident DAT2 model, which is the OOM this exists to prevent.
    # It does NOT span the PIL open above or the meta/sha work below - the GPU
    # is idle there.
    with gpu_lock(device):
        descriptor = ModelLoader().load_from_file(model_path)
        scale = int(descriptor.scale)
        arch = descriptor.architecture
        arch_name = getattr(arch, "name", None) or str(arch)
        net = descriptor.model.eval().to(device)

        img_tensor = _to_tensor(src_img).to(device)

        # Count tiles for the audit trail (mirror _tile_infer's tiling math).
        _, _, height, width = img_tensor.shape
        step = tile - overlap

        def _n_starts(total):
            if total <= tile:
                return 1
            pts = list(range(0, total - tile + 1, step))
            if not pts or pts[-1] != total - tile:
                pts.append(total - tile)
            return len(pts)

        n_tiles = _n_starts(height) * _n_starts(width)

        out_tensor = _tile_infer(net, img_tensor, tile=tile, overlap=overlap,
                                 scale=scale)
        out_tensor = out_tensor.clamp(0.0, 1.0)
        raw = _to_pil(out_tensor)

        # Free VRAM BEFORE releasing, so the next holder starts on an empty
        # card rather than racing this process's deallocation.
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    meta = {
        "backend": "spandrel",
        "model": os.path.basename(model_path),
        "model_sha256": _sha256(model_path),
        "arch": arch_name,
        "scale": scale,
        "src_dims": src_dims,
        "up_dims": list(raw.size),
        "n_tiles": n_tiles,
        "seconds": round(time.time() - t0, 3),
    }
    return raw, meta


def upscale_ncnn(
    src_path,
    out_tmp_path,
    model="realesrgan-x4plus-anime",
    exe=NCNN_EXE_DEFAULT,
):
    """Run realesrgan-ncnn-vulkan.exe to produce the raw 4x upscale.

    Subprocesses the exe with CREATE_NO_WINDOW (Legion focus-steal rule), then
    loads the produced PNG at out_tmp_path as the raw 4x result. Returns
    (raw_4x_pil_image, meta_dict). No finishing applied here.
    """
    t0 = time.time()
    src_img = Image.open(src_path).convert("RGB")
    src_dims = list(src_img.size)

    cmd = [exe, "-i", src_path, "-o", out_tmp_path, "-n", model, "-s", "4"]
    # realesrgan-ncnn-vulkan is a Vulkan GPU consumer even though no torch is
    # involved, so it belongs behind the same mutex as the spandrel path. It is
    # a non-python exe that can never acquire the mutex itself, so spawning it
    # from inside the hold cannot deadlock (the child-waits-on-parent trap).
    with gpu_lock("cuda"):
        subprocess.run(cmd, check=True, creationflags=_NO_WINDOW)

    raw = Image.open(out_tmp_path).convert("RGB")
    meta = {
        "backend": "ncnn",
        "model": model,
        "scale": 4,
        "src_dims": src_dims,
        "up_dims": list(raw.size),
        "seconds": round(time.time() - t0, 3),
    }
    return raw, meta


def first_pass(
    src_path,
    out_path,
    backend="spandrel",
    model_path=None,
    target=TARGET,
    usm=USM_DEFAULT,
    tile=512,
    overlap=32,
):
    """Orchestrate one first-pass upscale and write the finished PNG atomically.

    Picks the backend, gets the raw 4x PIL image, calls _finish (one Lanczos
    downscale to `target`, one clamped unsharp mask - both skipped when the raw
    image is already exactly `target`, see _usm_applies), and saves the PNG to
    out_path atomically (write tmp, then os.replace). Returns a full audit dict.

    The audit records both `usm` (the CONFIGURED recipe, always present) and
    `usm_applied` (whether that recipe actually ran on this image).

    The audit dict deliberately omits a wall-clock timestamp - the caller
    stamps time (see ts_note). time.time() is used only for durations.
    """
    t0 = time.time()
    src_sha256 = _sha256(src_path)

    # G0 over-target source-gate. Open the source once and read its dims. If it
    # already covers the target in both axes, skip the AI 4x entirely (see
    # _covers_target) and take a downscale-only path: the raw image IS the
    # source, and _finish does the single Lanczos downscale. This branch needs
    # no model, so the spandrel model_path check below must not fire when it
    # takes over.
    with Image.open(src_path) as _src_probe:
        src_w, src_h = _src_probe.size
        # Read the source mode BEFORE any convert("RGB"). The probe opens the
        # same file every backend re-opens, so this covers both branches.
        source_mode = _src_probe.mode
        source_has_alpha = _has_alpha(_src_probe)
        if _covers_target(src_w, src_h, target):
            raw = _src_probe.convert("RGB")
            meta = {
                "backend": "downscale-only",
                "model": None,
                "scale": 1,
                "src_dims": [src_w, src_h],
                "up_dims": [src_w, src_h],
                "seconds": round(time.time() - t0, 3),
            }
        else:
            raw = None

    if raw is None:
        if backend == "spandrel":
            if not model_path:
                raise ValueError("spandrel backend requires model_path")
            raw, meta = upscale_spandrel(
                src_path, model_path, tile=tile, overlap=overlap
            )
        elif backend == "ncnn":
            # Stage the ncnn PNG next to the final output, then finish + atomic move.
            ncnn_tmp = out_path + ".ncnn.png"
            raw, meta = upscale_ncnn(src_path, ncnn_tmp)
        else:
            raise ValueError(f"unknown backend: {backend!r}")

    usm_applied = _usm_applies(raw.size, target)
    finished = _finish(raw, target=target, usm=usm)

    # Atomic write: render to a sibling temp file, then os.replace onto out_path.
    tmp_path = out_path + ".tmp.png"
    finished.save(tmp_path, format="PNG")
    os.replace(tmp_path, out_path)

    clamped = _clamp_usm(usm)
    audit = {
        "backend": meta["backend"],
        "model": meta["model"],
        "scale": meta["scale"],
        "src_path": src_path,
        "src_sha256": src_sha256,
        "src_dims": meta["src_dims"],
        "up_dims": meta["up_dims"],
        "out_path": out_path,
        "out_sha256": _sha256(out_path),
        "out_dims": list(finished.size),
        "target": list(target),
        "usm": {
            "radius": clamped[0],
            "percent": clamped[1],
            "threshold": clamped[2],
        },
        "usm_applied": usm_applied,
        # The output is always RGB, so an alpha-carrying source IS flattened.
        "source_mode": source_mode,
        "alpha_flattened": source_has_alpha,
        "tile": tile,
        "overlap": overlap,
        "seconds": round(time.time() - t0, 3),
        "ts_note": "caller stamps time",
    }
    if meta["backend"] == "spandrel":
        audit["model_sha256"] = meta["model_sha256"]
    return audit
