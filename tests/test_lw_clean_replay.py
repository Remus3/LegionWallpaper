"""Tests for tools/lw_clean_replay.py - the captured-mask replay diagnostic.

Pure stdlib + numpy; no model is ever loaded, so this runs in CI.

The load-bearing property is the one that already produced a false result: two
slugs' captures live under one tree and their iteration numbers COLLIDE, so an
unfiltered collect compares one slug's replay against another slug's output and
reports a 136-level divergence that means nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_replay as R  # noqa: E402


def _capture(root, slug, n):
    md = root / "2. masks"
    od = root / "3. outputs"
    md.mkdir(parents=True, exist_ok=True)
    od.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        (md / f"{slug}_cleaninitial_mask{i}.jpg").write_bytes(b"")
        (od / f"{slug}_cleaninitial_cleanup{i}.png").write_bytes(b"")


def test_iteration_index_is_read_with_or_without_parentheses():
    assert R.idx_of("x_mask7.jpg") == 7
    assert R.idx_of("x_cleanup (45).png") == 45
    assert R.idx_of("notes.txt") is None


def test_collect_keys_off_the_filename_not_the_folder(tmp_path):
    _capture(tmp_path, "105-cleanup", 3)
    masks, outs = R.collect(str(tmp_path))
    assert sorted(masks) == [1, 2, 3]
    assert sorted(outs) == [1, 2, 3]


def test_two_captures_under_one_tree_collide_without_a_filter(tmp_path):
    _capture(tmp_path / "a", "105-cleanup", 3)
    _capture(tmp_path / "b", "107-cleanup", 3)
    masks, _outs = R.collect(str(tmp_path))
    assert len(masks) == 3          # collision: 6 files, 3 keys
    filtered, _ = R.collect(str(tmp_path), "105-cleanup")
    assert len(filtered) == 3
    assert all("105-cleanup" in p for p in filtered.values())


def test_crop_follows_the_mask_and_clamps():
    m = np.zeros((200, 400), dtype=bool)
    m[100:110, 200:260] = True
    assert R.crop_around(m, 400, 200, margin=20) == (180, 80, 280, 130)
    m2 = np.zeros((50, 50), dtype=bool)
    m2[0:5, 0:5] = True
    assert R.crop_around(m2, 50, 50, margin=30) == (0, 0, 35, 35)


def test_an_empty_mask_has_no_crop():
    assert R.crop_around(np.zeros((20, 20), dtype=bool), 20, 20) is None
