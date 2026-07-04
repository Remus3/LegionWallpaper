"""Legion Wallpaper - first-pass upscaler with two pluggable backends.

Backends:
  - spandrel/torch (primary): IllustrationJaNai DAT2 4x model, tiled inference.
  - realesrgan-ncnn-vulkan.exe (fallback): x4plus-anime.

Structural rule (never double-resample): exactly ONE AI upscale (4x),
ONE Lanczos downscale to the 2560x1440 target, ONE light unsharp mask.
Do not add extra resamples anywhere in this module.

CI constraint: only PIL + numpy + stdlib may be imported at module top
level. torch and spandrel are LAZY-imported inside the spandrel-backend
functions so this module imports cleanly on a torch-less Python (CI 3.12,
system 3.14). No cv2 anywhere.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time

from PIL import Image, ImageFilter

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


def _clamp_usm(usm):
    """Clamp an unsharp-mask (radius, percent, threshold) triple to sane maxima.

    Caps: radius <= 3, percent <= 150, threshold >= 0. Returns a new tuple.
    """
    radius, percent, threshold = usm
    radius = min(float(radius), USM_MAX_RADIUS)
    percent = min(int(percent), USM_MAX_PERCENT)
    threshold = max(int(threshold), USM_MIN_THRESHOLD)
    return (radius, percent, threshold)


def _finish(upscaled_img, target=TARGET, usm=USM_DEFAULT):
    """Downscale a raw 4x upscale to the target and apply one unsharp mask.

    Pure PIL - CI-testable without torch. Performs exactly ONE Lanczos resize
    to `target` followed by exactly ONE UnsharpMask. The unsharp-mask params
    are clamped to sane maxima (radius <= 3, percent <= 150, threshold >= 0).

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
    descriptor = ModelLoader().load_from_file(model_path)
    scale = int(descriptor.scale)
    arch = descriptor.architecture
    arch_name = getattr(arch, "name", None) or str(arch)
    net = descriptor.model.eval().to(device)

    src_img = Image.open(src_path).convert("RGB")
    src_dims = list(src_img.size)  # (w, h)

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

    out_tensor = _tile_infer(net, img_tensor, tile=tile, overlap=overlap, scale=scale)
    out_tensor = out_tensor.clamp(0.0, 1.0)
    raw = _to_pil(out_tensor)

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
    # Free VRAM promptly; harmless if CUDA is unavailable.
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
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
    downscale to `target`, one clamped unsharp mask), and saves the PNG to
    out_path atomically (write tmp, then os.replace). Returns a full audit dict.

    The audit dict deliberately omits a wall-clock timestamp - the caller
    stamps time (see ts_note). time.time() is used only for durations.
    """
    t0 = time.time()
    src_sha256 = _sha256(src_path)

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
        "out_path": out_path,
        "out_sha256": _sha256(out_path),
        "out_dims": list(finished.size),
        "target": list(target),
        "usm": {
            "radius": clamped[0],
            "percent": clamped[1],
            "threshold": clamped[2],
        },
        "tile": tile,
        "overlap": overlap,
        "seconds": round(time.time() - t0, 3),
        "ts_note": "caller stamps time",
    }
    if meta["backend"] == "spandrel":
        audit["model_sha256"] = meta["model_sha256"]
    return audit
