"""Tests for tools/lw_render_skn.py.

Scope: the pure-numpy camera/bounds helpers and the CLI contract. These run in the
MAIN env - moderngl and pyritofile live only in .venv-poc, so anything needing a GL
context or a .skn parse is deliberately out of scope here (the render path is proven
by running it, not by CI). The helpers are importable precisely because the GPU
imports are deferred into the functions that need them; a regression that hoists
them back to module scope breaks these tests, which is the point.
"""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import lw_render_skn as R  # noqa: E402


def test_module_imports_without_gl_stack():
    # The GPU deps are NOT in the main env. Importing the module must not need them.
    assert "moderngl" not in sys.modules
    assert R.FLIP_V is False
    assert R.BG_LEVEL == 128


def test_bounds_center_and_radius():
    pos = np.array([[-1, -2, -3], [1, 2, 3]], dtype="f4")
    center, radius = R.bounds(pos)
    assert np.allclose(center, [0.0, 0.0, 0.0])
    # half the diagonal of the 2x4x6 box
    assert radius == pytest.approx(math.sqrt(4 + 16 + 36) / 2.0, rel=1e-5)


def test_bounds_offcenter_box():
    pos = np.array([[10, 10, 10], [12, 14, 16]], dtype="f4")
    center, radius = R.bounds(pos)
    assert np.allclose(center, [11.0, 12.0, 13.0])
    assert radius > 0.0


def test_look_at_is_orthonormal():
    eye = np.array([0.0, 0.0, 5.0], dtype="f4")
    target = np.zeros(3, dtype="f4")
    up = np.array([0.0, 1.0, 0.0], dtype="f4")
    m = R.look_at(eye, target, up)
    basis = m[:3, :3]
    assert np.allclose(basis @ basis.T, np.identity(3), atol=1e-5)


def test_look_at_places_target_down_negative_z():
    # Right-handed GL convention: the viewed point lands in front of the camera,
    # which is -Z in eye space.
    eye = np.array([0.0, 0.0, 5.0], dtype="f4")
    target = np.zeros(3, dtype="f4")
    up = np.array([0.0, 1.0, 0.0], dtype="f4")
    m = R.look_at(eye, target, up)
    seen = m @ np.array([0.0, 0.0, 0.0, 1.0], dtype="f4")
    assert seen[2] == pytest.approx(-5.0, abs=1e-4)


def test_perspective_maps_near_and_far_to_clip_range():
    znear, zfar = 0.1, 100.0
    m = R.perspective(35.0, 1.0, znear, zfar)
    for z, expect in ((-znear, -1.0), (-zfar, 1.0)):
        clip = m @ np.array([0.0, 0.0, z, 1.0], dtype="f4")
        assert clip[3] == pytest.approx(-z, rel=1e-4)
        assert clip[2] / clip[3] == pytest.approx(expect, abs=1e-3)


def test_perspective_aspect_scales_x_only():
    wide = R.perspective(35.0, 2.0, 0.1, 10.0)
    square = R.perspective(35.0, 1.0, 0.1, 10.0)
    assert wide[0, 0] == pytest.approx(square[0, 0] / 2.0, rel=1e-5)
    assert wide[1, 1] == pytest.approx(square[1, 1], rel=1e-5)


def test_orbit_eye_keeps_constant_distance_around_yaw():
    center = np.array([0.0, 0.0, 0.0], dtype="f4")
    radius, dist = 10.0, 26.0
    seen = [R.orbit_eye(center, radius, dist, 2.0 * math.pi * i / 12) for i in range(12)]
    for eye in seen:
        horiz = math.hypot(float(eye[0]), float(eye[2]))
        assert horiz == pytest.approx(dist, rel=1e-5)
        assert float(eye[1]) == pytest.approx(radius * 0.15, rel=1e-5)


def test_orbit_eye_yaw_zero_is_on_positive_z():
    center = np.zeros(3, dtype="f4")
    eye = R.orbit_eye(center, 10.0, 26.0, 0.0)
    assert float(eye[0]) == pytest.approx(0.0, abs=1e-4)
    assert float(eye[2]) == pytest.approx(26.0, rel=1e-5)


def test_orbit_eye_respects_center_offset():
    center = np.array([100.0, 0.0, -50.0], dtype="f4")
    eye = R.orbit_eye(center, 10.0, 26.0, 0.0)
    assert float(eye[0]) == pytest.approx(100.0, abs=1e-4)
    assert float(eye[2]) == pytest.approx(-50.0 + 26.0, rel=1e-5)


def test_main_rejects_missing_inputs(tmp_path, capsys):
    rc = R.main([
        "--skn", str(tmp_path / "nope.skn"),
        "--tex", str(tmp_path / "nope.png"),
        "--out", str(tmp_path / "out"),
    ])
    assert rc == 2
    assert "missing input" in capsys.readouterr().err


def test_main_rejects_zero_angles(tmp_path, capsys):
    skn = tmp_path / "x.skn"
    tex = tmp_path / "x.png"
    skn.write_bytes(b"stub")
    tex.write_bytes(b"stub")
    rc = R.main([
        "--skn", str(skn), "--tex", str(tex),
        "--out", str(tmp_path / "out"), "--angles", "0",
    ])
    assert rc == 2
    assert "--angles" in capsys.readouterr().err


def test_parser_defaults_match_the_proven_run():
    args = R.build_parser().parse_args(["--skn", "a", "--tex", "b", "--out", "c"])
    # The 2026-08-15 proof run was 12 angles at 1024px.
    assert (args.size, args.angles) == (1024, 12)
    assert args.stem is None
