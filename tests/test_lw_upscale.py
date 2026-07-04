"""Tests for tools/lw_upscale.py.

Two tiers:
  - CI-runnable (PIL/numpy/stdlib only): exercise _finish and the usm clamp.
    These run in CI on 3.12 and on system 3.14 - real coverage.
  - torch-guarded (pytest.importorskip("torch")): exercise _tile_infer seam
    correctness with a deterministic FAKE net (nearest x4 interpolate, no
    weights, no GPU model, no download). SKIPPED where torch is absent.
"""

import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_upscale  # noqa: E402


# ---------------------------------------------------------------------------
# CI-runnable tests (PIL / numpy / stdlib only)
# ---------------------------------------------------------------------------


def _solid_16x9(w, h, color=(80, 120, 200)):
    """A solid-color 16:9 test image (stands in for a raw 4x upscale)."""
    return Image.new("RGB", (w, h), color)


def test_finish_resizes_16x9_to_target():
    """A 16:9 upscale is downscaled to exactly the target, mode RGB."""
    up = _solid_16x9(5120, 2880)  # 16:9, 2x the target - one Lanczos downscale
    out = lw_upscale._finish(up, target=(2560, 1440))
    assert out.size == (2560, 1440)
    assert out.mode == "RGB"


def test_finish_accepts_smaller_16x9():
    """Aspect check is ratio-based, not size-based: 1280x720 also finishes."""
    up = _solid_16x9(1280, 720)
    out = lw_upscale._finish(up, target=(2560, 1440))
    assert out.size == (2560, 1440)
    assert out.mode == "RGB"


def test_finish_rejects_non_16x9():
    """A non-16:9 source must raise ValueError - never silently squash aspect."""
    up = Image.new("RGB", (2000, 2000), (10, 10, 10))  # 1:1
    with pytest.raises(ValueError):
        lw_upscale._finish(up, target=(2560, 1440))


def test_finish_from_rgba_source():
    """Non-RGB inputs are converted; output is RGB at target size."""
    up = Image.new("RGBA", (3840, 2160), (200, 50, 50, 128))  # 16:9 RGBA
    out = lw_upscale._finish(up, target=(2560, 1440))
    assert out.mode == "RGB"
    assert out.size == (2560, 1440)


def test_usm_clamp_caps_radius_percent_and_threshold():
    """radius capped to 3, percent to 150, threshold floored at 0."""
    assert lw_upscale._clamp_usm((99, 999, -5)) == (3.0, 150, 0)
    # In-range values pass through untouched (radius promoted to float).
    assert lw_upscale._clamp_usm((1.2, 70, 3)) == (1.2, 70, 3)


def test_finish_with_extreme_usm_does_not_error():
    """_finish must clamp an out-of-range usm (radius=99) and still produce output."""
    up = _solid_16x9(2560, 1440)
    out = lw_upscale._finish(up, target=(2560, 1440), usm=(99, 999, -1))
    assert out.size == (2560, 1440)
    assert out.mode == "RGB"


# ---------------------------------------------------------------------------
# torch-guarded test (SKIPPED where torch is absent - CI 3.12, system 3.14)
# ---------------------------------------------------------------------------


def test_tile_infer_seam_matches_untiled():
    """The tiler must reconstruct exactly what the un-tiled net would produce.

    Uses a deterministic FAKE net (nearest x4 interpolate) so no weights, no
    GPU model, and no download are needed. Because nearest interpolation is
    exact and the stitcher averages overlaps of identical values, the tiled
    result must equal the whole-image result within a tight tolerance.
    """
    torch = pytest.importorskip("torch")
    import torch.nn.functional as F

    def fake_net(x):
        return F.interpolate(x, scale_factor=4, mode="nearest")

    torch.manual_seed(0)
    inp = torch.rand(1, 3, 80, 80)

    tiled = lw_upscale._tile_infer(fake_net, inp, tile=32, overlap=8, scale=4)
    whole = fake_net(inp)

    assert tiled.shape == whole.shape
    assert torch.allclose(tiled, whole, atol=1e-5)
