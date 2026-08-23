"""The glyph-percentile sweep: labels the operator reads off a stacked sheet."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import lw_clean_creditline_sweep as SW  # noqa: E402


def test_a_row_label_carries_the_three_numbers_that_explain_it():
    rec = {"mask_px": 18168, "held": 2, "committed": 9,
           "still_reads": [{"text": "X"}]}
    assert SW.label_for(70.0, rec) == "p70  mask=18168  9 healed, 2 held  reads"


def test_a_quiet_row_says_so():
    rec = {"mask_px": 40000, "held": 0, "committed": 4, "still_reads": []}
    assert SW.label_for(50.0, rec) == "p50  mask=40000  4 healed, 0 held  quiet"


def test_the_percentiles_run_thin_to_thick():
    """p88 keeps the top 12 percent of the high-pass; a LOWER number is a
    THICKER mask. The sheet reads top to bottom as more and more paint."""
    assert SW.parse_pcts("88,70,50") == [88.0, 70.0, 50.0]
    assert SW.parse_pcts("50, 88 ,70") == [88.0, 70.0, 50.0]


def test_a_percentile_outside_the_range_is_refused():
    for bad in ("101", "-1", "abc", ""):
        try:
            SW.parse_pcts(bad)
        except (ValueError, SystemExit):
            continue
        raise AssertionError(f"accepted {bad!r}")
