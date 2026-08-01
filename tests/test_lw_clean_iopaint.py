"""Tests for tools/lw_clean_iopaint.py - the Stage-2 IOPaint-emulation cleaner.

CI constraint (read before editing imports): the PURE tests run on system python
3.14 and CI 3.12 with ONLY numpy + PIL + stdlib available - NO torch, simple_lama,
cv2, or lw_clean_dekel, and NO GPU. The mask builder, chroma term, morphology,
argv builders and region-identity tripwire are all pure numpy and run in CI. The
ML integration tests (namakx one-pass reproduction) start with importorskip on the
ML deps, so they SKIP wherever those are absent and only run under the lw-clean
venv. NEVER touch images/** - all pure fixtures are synthetic numpy arrays.

The two load-bearing lessons from the validated namakx recipe are asserted here:
  1. the COMPLETE mask covers the bright glyph FILL *and* the dark glyph OUTLINE
     (dropping the dark term leaves the outline unmasked - the dark-edge ghost);
  2. the CHROMA term catches a coloured stroke that a luma-only mask misses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_iopaint as io  # noqa: E402


# ---------------------------------------------------------------------------
# synthetic-ROI helpers (pure numpy, no ML, thin strokes so diff-from-median
# catches the whole stroke the way it catches a real thin watermark glyph)
# ---------------------------------------------------------------------------
def _bright_and_dark_roi():
    """Dark bg (90) with thin bright FILL strokes and an ISOLATED dark stroke.

    The isolated dark stroke (no bright neighbour) is the "outline ghost" probe:
    only the dark-diff term can catch it.
    """
    roi = np.full((100, 240, 3), 90, dtype=np.uint8)
    roi[30:70, 60:63, :] = 230        # bright vertical stroke (fill)
    roi[30:70, 100:103, :] = 230      # bright vertical stroke (fill)
    roi[30:70, 150:153, :] = 40       # ISOLATED dark stroke (outline only)
    return roi


def _colored_same_luma_roi():
    """Neutral bg (gray 128) with a thin BLUE stroke of the SAME luma.

    BGR [180,110,94] has mean 128, so gray-diff is ~0 (luma-only misses it), but
    its chroma is far from the neutral background.
    """
    roi = np.full((100, 240, 3), 128, dtype=np.uint8)
    roi[30:70, 118:124, :] = [180, 110, 94]
    return roi


# ===========================================================================
# 1. mask covers the bright FILL
# ===========================================================================
def test_mask_covers_bright_fill():
    mask = io.build_watermark_mask(_bright_and_dark_roi())
    assert mask.dtype == np.uint8
    assert set(np.unique(mask)).issubset({0, 255})
    assert mask[50, 61] > 0            # inside a bright stroke
    assert mask[50, 101] > 0
    assert mask[5, 5] == 0             # far background stays unmasked


# ===========================================================================
# 2. mask ALSO covers the dark OUTLINE (the load-bearing lesson)
# ===========================================================================
def test_mask_covers_dark_outline():
    mask = io.build_watermark_mask(_bright_and_dark_roi())
    assert mask[50, 151] > 0           # the isolated dark stroke is masked


def test_dropping_dark_term_leaves_the_ghost():
    """With the dark term effectively off, the isolated dark stroke is MISSED.

    This is the white-only-mask failure the recipe fixes: a mask that only
    catches bright pixels leaves a dark edge ghost.
    """
    roi = _bright_and_dark_roi()
    white_only = io.build_watermark_mask(roi, dark_thr=-300.0)
    assert white_only[50, 151] == 0    # dark stroke unmasked -> ghost
    assert white_only[50, 61] > 0      # bright fill still caught
    complete = io.build_watermark_mask(roi)
    assert complete[50, 151] > 0       # the complete mask recovers it


# ===========================================================================
# 3. coverage lands in a sane band (not empty, not the whole ROI)
# ===========================================================================
def test_mask_coverage_in_sane_band():
    cov = io.mask_coverage_pct(io.build_watermark_mask(_bright_and_dark_roi()))
    assert 1.0 < cov < 50.0


def test_mask_coverage_pct_bounds():
    h, w = 20, 30
    assert io.mask_coverage_pct(np.zeros((h, w), np.uint8)) == 0.0
    assert io.mask_coverage_pct(np.full((h, w), 255, np.uint8)) == 100.0
    half = np.zeros((h, w), np.uint8)
    half[:, : w // 2] = 255
    assert io.mask_coverage_pct(half) == pytest.approx(50.0, abs=0.1)


# ===========================================================================
# 4. the CHROMA term catches a coloured stroke a luma-only mask misses
# ===========================================================================
def test_chroma_catches_colored_stroke_luma_misses():
    roi = _colored_same_luma_roi()
    luma_only = io.build_watermark_mask(roi, chroma_thr=None)
    assert io.mask_coverage_pct(luma_only) < 0.5     # same luma -> missed
    with_chroma = io.build_watermark_mask(roi, chroma_thr=12.0)
    assert with_chroma[50, 120] > 0                  # colour caught
    assert io.mask_coverage_pct(with_chroma) > 1.0


# ===========================================================================
# 5. morphology primitives
# ===========================================================================
def test_disk_se_shape_and_symmetry():
    se = io._disk_se(3)
    assert se.shape == (7, 7)
    assert se[3, 3] and se.dtype == bool
    assert np.array_equal(se, se[::-1]) and np.array_equal(se, se[:, ::-1])


def test_dilate_grows_erode_shrinks():
    m = np.zeros((21, 21), bool)
    m[10, 10] = True
    se = io._disk_se(1)
    dil = io._binary_dilate(m, se)
    assert dil.sum() > m.sum()
    assert io._binary_erode(dil, se).sum() <= dil.sum()


def test_close_fills_single_pixel_hole():
    m = np.ones((15, 15), bool)
    m[7, 7] = False
    assert io._binary_close(m, io._disk_se(1))[7, 7]


def test_median_blur_ignores_lone_spike():
    gray = np.full((40, 40), 100.0)
    gray[20, 20] = 250.0
    bg = io._median_blur(gray.astype(np.uint8), 21)
    assert abs(bg[20, 20] - 100.0) < 5.0


# ===========================================================================
# 6. ROI geometry + the region-identity tripwire
# ===========================================================================
def test_resolve_roi_clamps_to_frame():
    box = io.resolve_roi((1440, 2560, 3), (848, 1122, 1712, 1430), pad=20)
    assert box == (828, 1102, 1732, 1440)   # y1 clamps to the 1440 frame height
    edge = io.resolve_roi((100, 100, 3), (0, 0, 100, 100), pad=20)
    assert edge == (0, 0, 100, 100)      # clamped, never negative / past-edge


def test_paste_region_back_only_touches_region():
    full = np.zeros((60, 80, 3), np.uint8)
    roi_after = np.full((20, 30, 3), 200, np.uint8)
    box = (10, 5, 40, 25)
    out = io.paste_region_back(full, roi_after, box)
    assert np.array_equal(out[5:25, 10:40], roi_after)
    outside = out.copy()
    outside[5:25, 10:40] = 0
    assert not outside.any()             # nothing outside the box changed


def test_assert_region_identity_passes_then_raises():
    full = (np.arange(60 * 80 * 3) % 251).reshape(60, 80, 3).astype(np.uint8)
    box = (10, 5, 40, 25)
    ok = full.copy()
    ok[5:25, 10:40] = 0                  # only inside the box changed -> OK
    io.assert_region_identity(full, ok, box)
    bad = ok.copy()
    bad[0, 0, 0] = (int(bad[0, 0, 0]) + 7) % 256   # a pixel OUTSIDE the box
    with pytest.raises(AssertionError):
        io.assert_region_identity(full, bad, box)


# ===========================================================================
# 7. argv builders emit --tool iopaint
# ===========================================================================
def test_build_save_working_cmd_emits_tool_iopaint():
    params = {"engine": "simple-lama-iopaint", "mode": "one-pass"}
    argv = io.build_save_working_cmd("myslug", r"C:\out\myslug_clean_cand.png",
                                     params, sys_py="py", pipeline="p.py")
    assert argv[:4] == ["py", "p.py", "save-working", "myslug"]
    assert "--tool" in argv and argv[argv.index("--tool") + 1] == "iopaint"
    assert "--from" in argv
    assert argv[argv.index("--from") + 1].endswith("myslug_clean_cand.png")
    assert json.loads(argv[argv.index("--params") + 1])["mode"] == "one-pass"


def test_build_submit_cmd():
    argv = io.build_submit_cmd("myslug", sys_py="py", pipeline="p.py")
    assert argv == ["py", "p.py", "submit", "myslug"]


# ===========================================================================
# 8. cluster presets are well-formed
# ===========================================================================
def test_cluster_presets_shapes():
    for name, preset in io.CLUSTER_PRESETS.items():
        assert set(preset) == {"region", "chroma_thr", "slugs"}
        assert preset["region"] is None or len(preset["region"]) == 4
    assert io.CLUSTER_PRESETS["namakx"]["chroma_thr"] is None   # white -> luma-only
    assert io.CLUSTER_PRESETS["pebano"]["chroma_thr"] is not None  # colour -> chroma


# ===========================================================================
# 9. lazy-import proof (CI-safety): the ML modules are never needed to build a
#    mask, price the coverage, or build the pipeline commands.
# ===========================================================================
def test_pure_surface_with_ml_modules_absent(monkeypatch):
    for m in ("torch", "simple_lama_inpainting", "cv2", "lw_clean_dekel",
              "ultralytics", "easyocr", "scipy", "skimage"):
        monkeypatch.setitem(sys.modules, m, None)   # None -> import raises
    monkeypatch.delitem(sys.modules, "lw_clean_iopaint", raising=False)
    import lw_clean_iopaint as fresh                 # must import with ML absent
    mask = fresh.build_watermark_mask(_bright_and_dark_roi())   # cv2-free path
    assert mask[50, 151] > 0                         # dark outline still caught
    assert fresh.mask_coverage_pct(mask) > 1.0
    argv = fresh.build_save_working_cmd("s", "p.png", {"mode": "one-pass"})
    assert argv[argv.index("--tool") + 1] == "iopaint"


# ===========================================================================
# ML INTEGRATION (lw-clean venv only): reproduce the near-clean namakx result.
# ===========================================================================
_NAMAKX_SLUG = "dfz5w2g-8ba7345b-5776-4d83-b939-4ca7d045f545"


def _skip_unless_ml():
    for m in ("torch", "simple_lama_inpainting", "cv2"):
        pytest.importorskip(m)


def test_integration_namakx_one_pass_removes_watermark(tmp_path):
    _skip_unless_ml()
    import os
    src = os.path.join(io.CLEAN_SCRATCH, _NAMAKX_SLUG,
                       f"{_NAMAKX_SLUG}_cleaninitial.png")
    if not os.path.isfile(src):
        pytest.skip("namakx cleaninitial not present")
    res = io.clean_slug(_NAMAKX_SLUG, image=src, region=io.NAMAKX_REGION,
                        out_dir=str(tmp_path), log=lambda *a, **k: None)
    assert res["status"] == "cleaned"
    assert os.path.isfile(res["cand"])
    assert 20.0 < res["mask_coverage_pct"] < 45.0     # validated ~31% band
    # the candidate command records --tool iopaint
    save = res["commands"][0]
    assert save[save.index("--tool") + 1] == "iopaint"
    # the watermark energy in the ROI must DROP (before/after diff-from-median)
    import numpy as _np
    before = _np.asarray(io._load_full_bgr(res["before"]), dtype=_np.float64)
    after = _np.asarray(io._load_full_bgr(res["after"]), dtype=_np.float64)
    gb = before.mean(2)
    ga = after.mean(2)
    bgb = io._median_blur(_np.clip(gb, 0, 255).astype(_np.uint8), 21)
    bga = io._median_blur(_np.clip(ga, 0, 255).astype(_np.uint8), 21)
    e_before = float(_np.mean(_np.abs(gb - bgb)))
    e_after = float(_np.mean(_np.abs(ga - bga)))
    assert e_after < 0.6 * e_before      # watermark deviation energy collapses


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# --------------------------------------------------------------------------
# per-slug presets (the 2026-07-16 triage's confirmed PARTIAL fixes)
# --------------------------------------------------------------------------
def test_slug_preset_spirit_blossom_turns_chroma_on():
    region, chroma, src = io.resolve_preset(
        "spirit-blossom-ahri-mono-01-by-hriful-dk79ceq-pre")
    assert chroma == 12.0
    assert src == "slug"
    assert region == io.NAMAKX_REGION


def test_slug_preset_viego_uses_full_width_band():
    region, chroma, src = io.resolve_preset(
        "viego-the-king-by-slimshadywallpaper-dhawigh-pre")
    assert region == (860, 958, 1720, 1035)
    assert chroma == 12.0
    assert src == "slug"


def test_slug_preset_aidraw_widens_region_right():
    region, chroma, _ = io.resolve_preset(
        "aidraw-2662100118-by-watercolornessie-dma7o8j-fullview")
    assert region[2] > io.NAMAKX_REGION[2]
    assert chroma == 12.0


def test_explicit_region_and_chroma_beat_the_slug_preset():
    region, chroma, src = io.resolve_preset(
        "viego-the-king-by-slimshadywallpaper-dhawigh-pre",
        region=(1, 2, 3, 4), chroma_thr=5.0)
    assert region == (1, 2, 3, 4)
    assert chroma == 5.0
    assert src == "explicit"


def test_cluster_beats_the_slug_preset():
    region, chroma, src = io.resolve_preset(
        io.NAMAKX_SLUGS[0], cluster="namakx")
    assert region == io.NAMAKX_REGION
    assert chroma is None
    assert src == "cluster"


def test_unknown_slug_falls_back_to_the_namakx_default():
    region, chroma, src = io.resolve_preset("no-such-slug-at-all")
    assert region == io.NAMAKX_REGION
    assert chroma is None
    assert src == "default"
