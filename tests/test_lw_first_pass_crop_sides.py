"""Tests for the operator-directed crop override in tools/lw_first_pass.py.

The stock driver only ever center-crops to 16:9 and HOLDs anything whose crop
would lose more than AREA_LOSS_MAX of the frame. An operator reviewing a held
slug can instead name the sides the crop may come from ("crop from the bottom"),
which both anchors the crop window and authorises the heavy loss.

Reading of the operator instruction (settled 2026-08-17): the named sides are a
PERMISSION, not a demand. Only the axis that actually needs cropping is touched;
a horizontal permission on a too-tall image is simply unused. That keeps the
retained area maximal, which is the whole point of asking.

CI constraint (same as test_lw_first_pass.py): system python 3.14 and CI 3.12
with ONLY PIL + numpy + stdlib. No torch, no pyiqa, no GPU. These tests cover
pure geometry plus condition_source, which needs PIL alone.

Written test-first per CLAUDE.md TDD.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_first_pass as fp  # noqa: E402


# ---------------------------------------------------------------------------
# anchored_crop_box - geometry
# ---------------------------------------------------------------------------
def test_too_tall_top_only_takes_every_row_from_the_top():
    """akali 1920x1280: needs -200h, permitted 'top' -> all 200 off the top."""
    assert fp.anchored_crop_box(1920, 1280, ["top"]) == (0, 200, 1920, 1280)


def test_too_tall_bottom_only_takes_every_row_from_the_bottom():
    """puppet-master-syndra 1920x1279: needs -199h, all off the bottom."""
    assert fp.anchored_crop_box(1920, 1279, ["bottom"]) == (0, 0, 1920, 1080)


def test_too_tall_both_vertical_sides_matches_the_center_crop():
    """jhin 999x800 with top+bottom permitted is exactly the center crop."""
    assert (fp.anchored_crop_box(999, 800, ["top", "bottom"])
            == fp.center_crop_box(999, 800))


def test_too_wide_both_horizontal_sides_matches_the_center_crop():
    """bamboo 1024x510 with left+right permitted is the center crop."""
    assert (fp.anchored_crop_box(1024, 510, ["left", "right"])
            == fp.center_crop_box(1024, 510))


def test_too_wide_left_only_takes_every_column_from_the_left():
    """A too-wide frame with only 'left' permitted keeps the right edge."""
    w, h = 1024, 510
    box = fp.anchored_crop_box(w, h, ["left"])
    assert box[2] == w  # right edge untouched
    assert box[1] == 0 and box[3] == h  # full height
    assert box[0] == w - round(h * 16 / 9)


def test_horizontal_permission_on_a_too_tall_frame_is_ignored():
    """leblanc named left+bottom but is too TALL - width must stay full.

    This is the settled permission reading: the unusable horizontal grant is
    dropped rather than treated as a demand to narrow the frame.
    """
    box = fp.anchored_crop_box(1024, 640, ["left", "bottom"])
    assert box == (0, 0, 1024, 576)


def test_result_is_16x9_within_a_pixel_for_every_held_slug():
    """Every real held case lands on 16:9 (integer rounding tolerance)."""
    cases = [
        (1920, 1280, ["left", "top", "right"]),   # akali
        (1024, 510, ["left", "right"]),           # bamboo
        (1081, 739, ["left", "top", "right"]),    # brair
        (1024, 701, ["bottom"]),                  # evelynn dangerously-sexy
        (999, 800, ["top", "bottom"]),            # jhin
        (1024, 640, ["left", "bottom"]),          # leblanc
        (1920, 1279, ["left", "bottom"]),         # puppet-master-syndra
        (1280, 854, ["bottom"]),                  # spirit-blossom-vayne x2
    ]
    for w, h, sides in cases:
        left, top, right, bottom = fp.anchored_crop_box(w, h, sides)
        assert 0 <= left < right <= w
        assert 0 <= top < bottom <= h
        ratio = (right - left) / (bottom - top)
        assert abs(ratio - fp.TARGET_ASPECT) <= 0.01, (w, h, sides)


def test_no_permitted_side_on_the_needed_axis_raises():
    """A too-tall frame with only horizontal permissions cannot be honoured."""
    with pytest.raises(ValueError):
        fp.anchored_crop_box(1024, 640, ["left", "right"])


def test_unknown_side_name_raises():
    with pytest.raises(ValueError):
        fp.anchored_crop_box(1024, 640, ["botom"])


def test_empty_sides_raises():
    with pytest.raises(ValueError):
        fp.anchored_crop_box(1024, 640, [])


def test_already_16x9_source_is_returned_whole():
    """A frame already at 16:9 needs no crop whichever sides are permitted."""
    assert fp.anchored_crop_box(2560, 1440, ["top"]) == (0, 0, 2560, 1440)


# ---------------------------------------------------------------------------
# condition_source - the override path writes a real cropped temp
# ---------------------------------------------------------------------------
def _write_img(path, w, h):
    from PIL import Image
    Image.new("RGB", (w, h), (90, 120, 200)).save(path, format="PNG")
    return str(path)


def test_condition_source_override_crops_a_would_be_held_frame(tmp_path):
    """crop_sides turns a crop_heavy HOLD into a real anchored crop."""
    src = _write_img(tmp_path / "src.png", 1024, 701)
    out, plan = fp.condition_source(src, tmp_path, crop_sides=["bottom"])

    assert out is not None and out != src
    assert plan["cropped"] is True
    assert plan["aspect_class"] == "crop_override"
    assert plan["crop_box"] == (0, 0, 1024, 576)
    assert plan["crop_sides"] == ["bottom"]
    assert plan["area_loss"] == pytest.approx(125 / 701, abs=1e-6)

    from PIL import Image
    with Image.open(out) as im:
        assert im.size == (1024, 576)


def test_condition_source_without_override_still_holds(tmp_path):
    """Regression: the stock crop_heavy HOLD is untouched when no sides given."""
    src = _write_img(tmp_path / "src.png", 1024, 701)
    out, plan = fp.condition_source(src, tmp_path)
    assert out is None
    assert plan["aspect_class"] == "crop_heavy"


def test_condition_source_override_on_an_ok_frame_is_a_passthrough(tmp_path):
    """An already-16:9 source needs no temp write even with sides named."""
    src = _write_img(tmp_path / "src.png", 2560, 1440)
    out, plan = fp.condition_source(src, tmp_path, crop_sides=["top"])
    assert out == src
    assert plan["cropped"] is False
    assert plan["aspect_class"] == "ok"


# ---------------------------------------------------------------------------
# override parsing - the CLI/file contract
# ---------------------------------------------------------------------------
def test_parse_crop_overrides_reads_slug_to_sides(tmp_path):
    p = tmp_path / "ov.json"
    p.write_text('{"akali-x": "left,top,right", "vayne-y": ["bottom"]}',
                 encoding="utf-8")
    got = fp.parse_crop_overrides(str(p))
    assert got == {"akali-x": ["left", "top", "right"],
                   "vayne-y": ["bottom"]}


def test_parse_crop_overrides_rejects_an_unknown_side(tmp_path):
    p = tmp_path / "ov.json"
    p.write_text('{"akali-x": "sideways"}', encoding="utf-8")
    with pytest.raises(ValueError):
        fp.parse_crop_overrides(str(p))
