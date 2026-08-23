"""The credit-line lane runner: crop windows, and what a run records."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import lw_clean_creditline_run as RUN  # noqa: E402


def _hit(x0, y0, x1, y1):
    return {"box": [x0, y0, x1, y1], "text": "XDEVIANTARTCOM", "conf": 0.9}


def test_crop_box_unions_every_hit():
    box = RUN.crop_box_from_hits([_hit(100, 200, 300, 240),
                                  _hit(400, 210, 500, 250)], (1440, 2560),
                                 pad=0)
    assert box == (100, 200, 500, 250)


def test_crop_box_pads_and_clips_to_the_frame():
    box = RUN.crop_box_from_hits([_hit(5, 3, 40, 20)], (30, 50), pad=20)
    assert box == (0, 0, 50, 30)


def test_crop_box_is_none_without_hits():
    assert RUN.crop_box_from_hits([], (100, 100)) is None


def test_run_one_records_the_mask_the_fill_saw():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (200, 300, 3), dtype=np.uint8)
    hits = [_hit(100, 120, 180, 140)]
    seen = {}

    def inpaint(crop_rgb, crop_mask_u8):
        seen["px"] = int((crop_mask_u8 > 127).sum())
        return crop_rgb

    out, rec = RUN.run_one(img, hits, inpaint)
    assert out.shape == img.shape
    assert rec["mask_px"] > 0
    assert seen["px"] > 0
    assert rec["blobs"] >= 1
    assert rec["box"] == [100, 120, 180, 140]


def test_run_one_without_hits_is_a_no_op():
    img = np.zeros((40, 40, 3), dtype=np.uint8)

    def inpaint(_c, _m):  # pragma: no cover - must never be called
        raise AssertionError("no hits means no fill")

    out, rec = RUN.run_one(img, [], inpaint)
    assert rec["mask_px"] == 0
    assert np.array_equal(out, img)


def test_review_order_puts_a_surviving_read_first():
    rows = [{"slug": "quiet", "still_reads": [], "held": 0, "mask_px": 900},
            {"slug": "held", "still_reads": [], "held": 2, "mask_px": 100},
            {"slug": "reads", "still_reads": [{"text": "X"}], "held": 0,
             "mask_px": 10}]
    assert [r["slug"] for r in RUN.review_order(rows)] == ["reads", "held",
                                                          "quiet"]


def test_the_index_links_every_sheet_and_states_no_verdict(tmp_path):
    summary = {"n": 1, "held": 0, "still_reads": 1,
               "rows": [{"slug": "a", "still_reads": [{"text": "X"}],
                         "held": 0, "mask_px": 5,
                         "sheet": str(tmp_path / "a_sheet.png")}]}
    p = RUN.write_index(summary, str(tmp_path / "REVIEW.md"))
    body = open(p, encoding="utf-8").read()
    assert "[a_sheet.png](a_sheet.png)" in body
    assert "FAIL" in body
    assert "pass" not in body.lower().split("proves")[0]
