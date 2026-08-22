"""The mask-coverage guard applies to EVERY lane, not just the faint one.

Written after the 2026-08-22 operator review rejected the whole region lane with
one sentence: "the entirety of the cropped regions are being blurred out in the
image". Measured cause - the region lane's diff mask covered a median 47.6% of
the ROI (24 of 27 slugs over 25%, 16 over 40%), and the 25% refusal tripwire was
gated on `faint` so the region path walked straight past it into LaMa.

The guard is lane-independent by its own reasoning: a mask covering half the ROI
is the picture, not a mark, whichever lane built it. These tests pin that, and
pin that a refusal REMOVES any stale candidate from an earlier permissive run -
a leftover after-image would keep showing up in the review sheet as if it were a
result the operator should judge.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_iopaint as IO  # noqa: E402


def test_the_ceiling_is_shared_not_faint_specific():
    assert IO.COVERAGE_MAX == pytest.approx(25.0)
    assert IO.FAINT_COVERAGE_MAX == IO.COVERAGE_MAX


def test_coverage_ok_is_lane_independent():
    assert IO.mask_coverage_ok(24.9) is True
    assert IO.mask_coverage_ok(25.0) is True
    assert IO.mask_coverage_ok(25.1) is False
    assert IO.mask_coverage_ok(47.6) is False


def test_the_faint_alias_still_answers_the_same():
    assert IO.faint_mask_ok(30.5) is IO.mask_coverage_ok(30.5)


def test_a_refusal_clears_a_stale_candidate(tmp_path):
    slug = "victor"
    d = tmp_path / slug
    d.mkdir()
    after = d / f"{slug}_iopaint_after.png"
    cand = d / f"{slug}_clean_cand.png"
    after.write_bytes(b"stale")
    cand.write_bytes(b"stale")
    IO.clear_stale_candidate(str(d), slug)
    assert not after.exists()
    assert not cand.exists()


def test_clearing_is_safe_when_nothing_is_there(tmp_path):
    IO.clear_stale_candidate(str(tmp_path), "nobody")
