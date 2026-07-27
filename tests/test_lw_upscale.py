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
from PIL import Image, ImageChops

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
# G0 over-target source-gate (CI-runnable: no torch, downscale-only path)
# ---------------------------------------------------------------------------


def test_covers_target_boundaries():
    """_covers_target is True iff src >= target in BOTH dims (inclusive edge)."""
    assert lw_upscale._covers_target(2560, 1440) is True
    assert lw_upscale._covers_target(3840, 2160) is True
    assert lw_upscale._covers_target(2559, 1440) is False
    assert lw_upscale._covers_target(2560, 1439) is False
    assert lw_upscale._covers_target(1920, 1080) is False


def test_first_pass_over_target_16x9_downscale_only(tmp_path):
    """An over-target 16:9 source takes the downscale-only path - no model needed.

    A 3840x2160 (16:9) source already covers the 2560x1440 target, so G0 skips
    the AI 4x and does one Lanczos downscale. model_path=None must NOT raise.
    """
    src = str(tmp_path / "over_target.png")
    out = str(tmp_path / "firstworking.png")
    _solid_16x9(3840, 2160).save(src, format="PNG")

    audit = lw_upscale.first_pass(src, out, backend="spandrel", model_path=None)

    assert audit["backend"] == "downscale-only"
    assert audit["scale"] == 1
    assert audit["model"] is None
    assert "model_sha256" not in audit
    assert audit["up_dims"] == [3840, 2160]
    assert audit["src_dims"] == [3840, 2160]

    assert os.path.exists(out)
    with Image.open(out) as got:
        assert got.size == (2560, 1440)
        assert got.mode == "RGB"


def test_first_pass_over_target_non_16x9_still_raises(tmp_path):
    """An over-target NON-16:9 source still hits the _finish aspect guard.

    3000x3000 covers the target in both dims but is 1:1 - _finish must raise
    ValueError rather than squash aspect, even on the downscale-only path.
    """
    src = str(tmp_path / "over_target_square.png")
    out = str(tmp_path / "firstworking_square.png")
    Image.new("RGB", (3000, 3000), (10, 10, 10)).save(src, format="PNG")

    with pytest.raises(ValueError):
        lw_upscale.first_pass(src, out, backend="spandrel", model_path=None)


# ---------------------------------------------------------------------------
# No-resample USM skip (R15): an at-target source is not re-sharpened
# ---------------------------------------------------------------------------


def _hard_edge_16x9(w, h):
    """A 16:9 image with a hard mid-tone vertical edge.

    A hard edge is the worst case for UnsharpMask, so a byte-identical result
    proves the USM did not run. The two sides are mid-tones, NOT pure black and
    white: a saturated 0/255 edge is a fixed point of UnsharpMask (the overshoot
    clamps back to the original value) and would pass this test vacuously.
    """
    img = Image.new("RGB", (w, h), (40, 60, 90))
    img.paste(Image.new("RGB", (w - w // 2, h), (200, 180, 150)), (w // 2, 0))
    return img


def test_usm_applies_predicate():
    """The predicate is False ONLY at exactly the target size.

    scale == 1 is NOT the condition: a genuine 3840x2160 -> 2560x1440 Lanczos
    downscale is also scale 1 and DOES resample, so it must keep its USM.
    """
    assert lw_upscale._usm_applies((2560, 1440), (2560, 1440)) is False
    assert lw_upscale._usm_applies((3840, 2160), (2560, 1440)) is True
    # 4x spandrel output of a 1920x1080 source.
    assert lw_upscale._usm_applies((7680, 4320), (2560, 1440)) is True


def test_finish_at_target_is_pixel_identical():
    """_finish on an already-target-sized image returns the RGB input unchanged.

    No resample happened, so there is nothing to re-sharpen - the USM alone
    would be the entire delta (it tripped the G1 halo_pct flag on refs-46).
    """
    up = _hard_edge_16x9(2560, 1440)
    out = lw_upscale._finish(up, target=(2560, 1440))
    assert out.size == (2560, 1440)
    assert out.mode == "RGB"
    assert ImageChops.difference(out, up.convert("RGB")).getbbox() is None


def test_finish_genuine_downscale_still_sharpens():
    """A real 4K -> 1440p downscale MUST still get its unsharp mask."""
    up = _hard_edge_16x9(3840, 2160)
    plain = up.convert("RGB").resize((2560, 1440), Image.LANCZOS)
    out = lw_upscale._finish(up, target=(2560, 1440))
    assert out.size == (2560, 1440)
    assert ImageChops.difference(out, plain).getbbox() is not None


def test_first_pass_at_target_skips_usm(tmp_path):
    """An exactly-2560x1440 source round-trips byte-for-byte, usm_applied False."""
    src = str(tmp_path / "at_target.png")
    out = str(tmp_path / "firstworking_at_target.png")
    _hard_edge_16x9(2560, 1440).save(src, format="PNG")

    audit = lw_upscale.first_pass(src, out, backend="spandrel", model_path=None)

    assert audit["backend"] == "downscale-only"
    assert audit["usm_applied"] is False
    assert audit["out_dims"] == [2560, 1440]

    with Image.open(src) as src_img, Image.open(out) as out_img:
        src_rgb = src_img.convert("RGB")
        out_rgb = out_img.convert("RGB")
        assert ImageChops.difference(out_rgb, src_rgb).getbbox() is None


def test_first_pass_over_target_reports_usm_applied(tmp_path):
    """A 3840x2160 source genuinely resamples, so usm_applied is True."""
    src = str(tmp_path / "over_target_usm.png")
    out = str(tmp_path / "firstworking_over_target.png")
    _hard_edge_16x9(3840, 2160).save(src, format="PNG")

    audit = lw_upscale.first_pass(src, out, backend="spandrel", model_path=None)

    assert audit["backend"] == "downscale-only"
    assert audit["usm_applied"] is True


# ---------------------------------------------------------------------------
# Alpha-drop audit hygiene (R26).
#
# first_pass ALWAYS writes RGB, so any alpha-carrying source is silently
# flattened. The audit did not record that, which made a corpus-wide flatten
# invisible to a reviewer. These tests pin source_mode + alpha_flattened onto
# the audit dict. They use the over-target downscale-only path, which needs no
# model and no torch.
# ---------------------------------------------------------------------------

# Every audit key that existed BEFORE the alpha fields were added. Frozen here
# so a future field addition cannot quietly drop one of them.
PREEXISTING_AUDIT_KEYS = {
    "backend", "model", "scale", "src_path", "src_sha256", "src_dims",
    "up_dims", "out_path", "out_sha256", "out_dims", "target", "usm",
    "usm_applied", "tile", "overlap", "seconds", "ts_note",
}


def test_first_pass_rgba_source_records_alpha_flattened(tmp_path):
    """An RGBA source is flattened to RGB, and the audit says so."""
    src = str(tmp_path / "rgba_over_target.png")
    out = str(tmp_path / "firstworking_rgba.png")
    Image.new("RGBA", (3840, 2160), (200, 50, 50, 128)).save(src, format="PNG")

    audit = lw_upscale.first_pass(src, out, backend="spandrel", model_path=None)

    assert audit["source_mode"] == "RGBA"
    assert audit["alpha_flattened"] is True

    with Image.open(out) as got:
        assert got.size == (2560, 1440)
        assert got.mode == "RGB"


def test_first_pass_rgb_source_records_no_alpha(tmp_path):
    """A plain RGB source flattens nothing - alpha_flattened stays False."""
    src = str(tmp_path / "rgb_over_target.png")
    out = str(tmp_path / "firstworking_rgb.png")
    _solid_16x9(3840, 2160).save(src, format="PNG")

    audit = lw_upscale.first_pass(src, out, backend="spandrel", model_path=None)

    assert audit["source_mode"] == "RGB"
    assert audit["alpha_flattened"] is False


def test_first_pass_palette_transparency_source_flags_alpha(tmp_path):
    """A palette PNG carries alpha in info['transparency'], not in its mode.

    Mode "P" looks opaque to a mode-only check, so this guards the palette
    blind spot: the tRNS chunk is real transparency and IS flattened.
    """
    src = str(tmp_path / "palette_over_target.png")
    out = str(tmp_path / "firstworking_palette.png")
    _solid_16x9(3840, 2160).convert("P").save(src, format="PNG", transparency=0)

    audit = lw_upscale.first_pass(src, out, backend="spandrel", model_path=None)

    assert audit["source_mode"] == "P"
    assert audit["alpha_flattened"] is True


def test_first_pass_audit_keeps_every_preexisting_key(tmp_path):
    """Adding the alpha fields must not drop any pre-existing audit key."""
    src = str(tmp_path / "regression_over_target.png")
    out = str(tmp_path / "firstworking_regression.png")
    _solid_16x9(3840, 2160).save(src, format="PNG")

    audit = lw_upscale.first_pass(src, out, backend="spandrel", model_path=None)

    missing = PREEXISTING_AUDIT_KEYS - set(audit)
    assert not missing, f"dropped pre-existing audit keys: {sorted(missing)}"


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
