"""The lane comparison strip: what the eye is asked to look at, and only that.

The verdict on `--stubs` / `--scoped-revert` is an EYE decision at 1:1, and the
per-run review sheets cannot serve it: each one stacks untouched-above /
cleaned-below for ONE configuration, so telling two configurations apart means
flipping between two sheets of the same crop. What the eye needs is every
configuration in one column, cropped to the pixels that actually differ between
them - everything else in the frame is identical by construction and only makes
the crop smaller.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import lw_clean_lane_compare as LC  # noqa: E402


def _frame(h=40, w=60):
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_identical_variants_have_no_changed_box():
    a, b = _frame(), _frame()
    assert LC.changed_box([a, b], pad=4) is None


def test_the_box_covers_every_differing_pixel_with_pad():
    a, b = _frame(), _frame()
    b[20, 30] = 255
    box = LC.changed_box([a, b], pad=4)
    assert box == (26, 16, 35, 25)


def test_a_third_variant_widens_the_box():
    a, b, c = _frame(), _frame(), _frame()
    b[20, 30] = 255
    c[10, 5] = 255
    box = LC.changed_box([a, b, c], pad=2)
    assert box == (3, 8, 33, 23)


def test_the_box_is_clipped_to_the_frame():
    a, b = _frame(h=10, w=10), _frame(h=10, w=10)
    b[0, 0] = 255
    b[9, 9] = 255
    assert LC.changed_box([a, b], pad=50) == (0, 0, 10, 10)


def test_a_single_variant_is_never_a_difference():
    assert LC.changed_box([_frame()], pad=4) is None
