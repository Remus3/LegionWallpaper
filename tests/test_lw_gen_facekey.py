"""CI-safe tests for tools/lw_gen_facekey.py (face-key correction).

Numpy-only: the face detector and its weights are imported lazily inside the
CLI, so nothing here loads ultralytics or torch.

The correction exists because six prompt/CFG arms and a face-region refinement
pass all failed to move face-vs-body lighting (docs/GEN_FACE_REALISM_2026-08-16.
md). Its targets are measured off the 21 real Ahri splashes: face skin sits
+24.3 levels above body skin with 0.83x the modelling.
"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from tools import lw_gen_facekey as fk  # noqa: E402

from _import_probe import assert_import_free  # noqa: E402


def test_module_imports_without_torch_or_ultralytics():
    assert_import_free("tools.lw_gen_facekey", ("torch", "ultralytics", "PIL"))


def test_targets_lift_the_face_to_the_corpus_offset():
    gain, target_mean = fk.key_targets(face_mean=140.0, face_std=30.0,
                                       body_mean=150.0, body_std=40.0)
    assert target_mean == pytest.approx(150.0 + fk.CORPUS_OFFSET)
    assert gain == pytest.approx(fk.CORPUS_RATIO * 40.0 / 30.0)


def test_gain_is_clipped_so_a_flat_face_cannot_explode():
    gain, _ = fk.key_targets(face_mean=140.0, face_std=0.001,
                             body_mean=150.0, body_std=60.0)
    assert gain == fk.GAIN_CLIP[1]


def test_zero_body_std_does_not_divide_by_zero():
    gain, _ = fk.key_targets(140.0, 30.0, 150.0, 0.0)
    assert np.isfinite(gain) and gain == fk.GAIN_CLIP[0]


def test_interior_of_a_solid_mask_stays_fully_weighted():
    """THE BUG THIS FIXES: blurring a mask directly leaves the interior at a
    fraction of 1.0, so only a fraction of the computed shift ever lands."""
    m = np.zeros((80, 80), dtype=bool)
    m[20:60, 20:60] = True
    w = fk.feathered_weight(m, feather_px=9)
    assert w[40, 40] == pytest.approx(1.0)
    assert w[0, 0] == pytest.approx(0.0)
    assert 0.0 < w[19, 40] < 1.0


def test_apply_moves_the_mean_toward_the_target_without_overshooting():
    """Contract CHANGED 2026-08-16: the correction is bounded, so it moves the
    shading toward the target rather than landing on it exactly. The old test
    asserted an exact landing, which is what an unbounded gain buys - and an
    unbounded gain is what crushed lash lines to black."""
    rng = np.random.default_rng(0)
    lum = rng.normal(140.0, 30.0, size=(64, 64))
    rgb = np.stack([lum * 1.1, lum, lum * 0.9], axis=-1)
    mask = np.ones((64, 64), dtype=bool)
    w = fk.feathered_weight(mask, feather_px=3)
    gain, target_mean = fk.key_targets(lum.mean(), lum.std(), 150.0, 40.0)
    out = fk.apply_face_key(rgb, mask, w, gain, target_mean)
    before, after = fk.luminance(rgb).mean(), fk.luminance(out).mean()
    assert before < after <= target_mean + 1.0


def test_fine_dark_detail_survives_the_correction():
    """The mascara failure: a 1px dark stroke must not be driven toward black."""
    base = np.full((64, 64), 150.0)
    base[30:32, 10:54] = 40.0                      # a lash-like stroke
    rgb = np.stack([base * 1.15, base, base * 0.9], axis=-1)
    mask = np.ones((64, 64), dtype=bool)
    w = fk.feathered_weight(mask, feather_px=3)
    out = fk.apply_face_key(rgb, mask, w, gain=fk.GAIN_CLIP[1], target_mean=200.0)
    stroke_before = fk.luminance(rgb)[30:32, 10:54].min()
    stroke_after = fk.luminance(out)[30:32, 10:54].min()
    assert stroke_after >= stroke_before - fk.MAX_DARKEN


def test_correction_cannot_crush_pixels_to_black():
    rng = np.random.default_rng(3)
    lum = rng.normal(60.0, 25.0, size=(64, 64)).clip(10, 255)
    rgb = np.stack([lum, lum, lum], axis=-1)
    mask = np.ones((64, 64), dtype=bool)
    w = fk.feathered_weight(mask, feather_px=3)
    out = fk.apply_face_key(rgb, mask, w, gain=fk.GAIN_CLIP[1], target_mean=200.0)
    crush, blow = fk.harm(rgb, out)
    assert crush <= fk.CRUSH_LIMIT and blow <= fk.BLOWOUT_LIMIT


def test_pixels_outside_the_mask_are_byte_identical():
    rng = np.random.default_rng(1)
    rgb = rng.integers(0, 255, size=(40, 40, 3)).astype(np.float64)
    mask = np.zeros((40, 40), dtype=bool)
    mask[10:20, 10:20] = True
    w = fk.feathered_weight(mask, feather_px=5)
    out = fk.apply_face_key(rgb, mask, w, gain=1.3, target_mean=200.0)
    far = w <= 0.0
    assert np.array_equal(out[far], rgb.astype(np.uint8)[far])


def test_correction_preserves_hue_because_it_is_multiplicative():
    """An ADDITIVE lift pushes colour toward grey; the ratio test catches it."""
    base = np.full((16, 16), 100.0)
    rgb = np.stack([base * 1.4, base, base * 0.6], axis=-1)
    mask = np.ones((16, 16), dtype=bool)
    w = fk.feathered_weight(mask, feather_px=3)
    out = fk.apply_face_key(rgb, mask, w, gain=1.0, target_mean=160.0).astype(np.float64)
    before = rgb[..., 0] / rgb[..., 2]
    after = out[..., 0] / np.maximum(out[..., 2], 1e-6)
    assert np.allclose(before, after, rtol=0.02)


def _synthetic_frame(face_level, body_level, face_spread, body_spread):
    """A frame with a skin-coloured face patch over a skin-coloured body patch."""
    rng = np.random.default_rng(7)
    img = np.zeros((200, 120, 3), dtype=np.float64)
    img[..., 0], img[..., 1], img[..., 2] = 40.0, 30.0, 30.0  # non-skin ground
    face = rng.normal(face_level, face_spread, size=(40, 40))
    body = rng.normal(body_level, body_spread, size=(80, 60))
    for patch, (y, x) in ((face, (20, 40)), (body, (100, 30))):
        h, w = patch.shape
        img[y:y + h, x:x + w, 0] = patch * 1.25
        img[y:y + h, x:x + w, 1] = patch
        img[y:y + h, x:x + w, 2] = patch * 0.80
    return img, (40, 20, 80, 60)


def test_iteration_never_leaves_a_frame_worse_than_it_found_it():
    """The guard: an unguarded residual pass pushed a real frame past the
    target (+13.5 -> -2.7). Each pass must now move it CLOSER or be dropped."""
    img, box = _synthetic_frame(face_level=120.0, body_level=150.0,
                                face_spread=10.0, body_spread=40.0)
    out, before, after = fk.correct_frame(img, box)
    assert before is not None and after is not None
    assert fk._distance(after) <= fk._distance(before)


def test_a_face_already_in_the_corpus_relationship_is_left_alone():
    img, box = _synthetic_frame(face_level=150.0 + fk.CORPUS_OFFSET,
                                body_level=150.0, face_spread=33.0,
                                body_spread=40.0)
    _, before, after = fk.correct_frame(img, box)
    assert fk.in_band(*before)
    assert fk._distance(after) <= fk._distance(before) + 1e-9


def test_a_frame_inside_the_band_is_never_pushed_out_of_it():
    """Measured over 57 frames: distance-only acceptance took 3 in-band frames
    OUT of the band. Being inside the corpus band outranks being closer to its
    centre."""
    img, box = _synthetic_frame(face_level=150.0 + fk.CORPUS_OFFSET - 10.0,
                                body_level=150.0, face_spread=30.0,
                                body_spread=40.0)
    _, before, after = fk.correct_frame(img, box)
    if fk.in_band(*before):
        assert fk.in_band(*after), "an in-band frame was pushed out of the band"


def test_a_frame_with_no_detectable_face_is_passed_through_not_dropped(tmp_path, monkeypatch):
    """Found on the Vayne set: one frame had no face and vanished from the
    output folder. A batch tool must never silently lose a frame."""
    from PIL import Image

    src = tmp_path / "in"
    src.mkdir()
    img, _ = _synthetic_frame(120.0, 150.0, 10.0, 40.0)
    Image.fromarray(img.astype(np.uint8)).save(src / "cand_00.png")
    monkeypatch.setattr(fk, "_detect_face", lambda *_a, **_k: None)
    out = tmp_path / "out"
    assert fk.main([str(src), str(out)]) == 0
    dst = out / "cand_00.png"
    assert dst.is_file(), "frame was dropped instead of passed through"
    assert dst.read_bytes() == (src / "cand_00.png").read_bytes()
    report = json.loads((out / "facekey_report.json").read_text(encoding="utf-8"))
    assert report[0]["skipped"] == "no_face"


def test_blur_padding_does_not_bias_the_shading_split():
    """Zero padding depressed the low-frequency term near the border, the detail
    term absorbed the deficit, and the correction double-counted it (+22 levels
    of overshoot on a synthetic frame). The split must be unbiased."""
    rng = np.random.default_rng(11)
    lum = rng.normal(140.0, 30.0, size=(64, 64))
    low, detail = fk.shading_split(lum, face_width=64)
    assert low.mean() == pytest.approx(lum.mean(), abs=1.0)
    assert detail.mean() == pytest.approx(0.0, abs=1.0)
