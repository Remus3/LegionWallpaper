"""CI-safe tests for tools/lw_gen_medium.py (the MEDIUM yardstick).

Torch-free: importing lw_gen_medium must NOT pull open_clip/torch/PIL - the
encoder is lazy, and every test here feeds synthetic embeddings instead.

The measure under test is the one that produced the 0.8373 real-vs-real ceiling
recorded in docs/GEN_MODELS.md: mean pairwise CLIP image-embedding cosine over a
reference set, against which an arm's mean cross cosine to that set is compared.
"""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from tools import lw_gen_medium  # noqa: E402

from _import_probe import assert_import_free  # noqa: E402


def _unit(rows):
    a = np.asarray(rows, dtype=np.float64)
    return a / np.linalg.norm(a, axis=1, keepdims=True)


def test_module_imports_without_torch():
    assert_import_free("tools.lw_gen_medium", ("torch", "open_clip", "PIL"))


def test_ceiling_is_the_upper_triangle_mean_not_the_diagonal():
    """Identical rows would read 1.0 either way; orthogonal rows separate the two.

    Three mutually orthogonal unit vectors have every off-diagonal cosine 0, so
    the ceiling is 0.0. A mean over the FULL matrix would read 1/3.
    """
    embs = _unit([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    assert lw_gen_medium.mean_pairwise_cos(embs) == pytest.approx(0.0, abs=1e-12)


def test_ceiling_of_a_known_pair():
    embs = _unit([[1, 0], [1, 1]])
    assert lw_gen_medium.mean_pairwise_cos(embs) == pytest.approx(math.sqrt(0.5))


def test_ceiling_needs_at_least_two_members():
    with pytest.raises(ValueError):
        lw_gen_medium.mean_pairwise_cos(_unit([[1, 0]]))


def test_cross_mean_is_over_every_pair_not_index_matched():
    """arm[0] matches real[0] exactly and arm[1] is orthogonal to both."""
    real = _unit([[1, 0], [1, 0]])
    arm = _unit([[1, 0], [0, 1]])
    assert lw_gen_medium.mean_cross_cos(arm, real) == pytest.approx(0.5)


def test_report_carries_the_delta_and_names_the_side_of_the_ceiling():
    real = _unit([[1, 0], [1, 0.05]])
    below = _unit([[0, 1], [0.1, 1]])
    rep = lw_gen_medium.medium_report(below, real, label="below-arm")
    assert rep["label"] == "below-arm"
    assert rep["n_arm"] == 2 and rep["n_real"] == 2
    assert rep["delta"] == pytest.approx(rep["arm_mean_cos"] - rep["ceiling"])
    assert rep["delta"] < 0 and rep["verdict"] == "below"

    at_or_above = _unit([[1, 0.02], [1, 0.03]])
    rep2 = lw_gen_medium.medium_report(at_or_above, real, label="above-arm")
    assert rep2["delta"] > 0 and rep2["verdict"] == "at_or_above"


def test_report_keeps_a_per_image_row_so_one_outlier_is_visible():
    real = _unit([[1, 0], [1, 0]])
    arm = _unit([[1, 0], [0, 1]])
    rep = lw_gen_medium.medium_report(arm, real, label="x", files=["a.png", "b.png"])
    rows = rep["per_image"]
    assert [r["file"] for r in rows] == ["a.png", "b.png"]
    assert rows[0]["mean_cos"] == pytest.approx(1.0)
    assert rows[1]["mean_cos"] == pytest.approx(0.0)


def test_rows_are_normalised_before_comparison():
    """A caller passing unnormalised embeddings must not get inflated cosines."""
    raw = np.asarray([[3.0, 0.0], [0.0, 5.0]])
    assert lw_gen_medium.mean_pairwise_cos(raw) == pytest.approx(0.0, abs=1e-12)
