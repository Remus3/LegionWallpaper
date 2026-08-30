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


def test_round_two_reads_the_previous_output_when_there_is_one(tmp_path):
    scratch = tmp_path / "scratch" / "a"
    scratch.mkdir(parents=True)
    (scratch / "a_cleaninitial.png").write_bytes(b"")
    prev = tmp_path / "r1"
    prev.mkdir()
    assert RUN.source_for("a", str(tmp_path / "scratch"), None).endswith(
        "a_cleaninitial.png")
    assert RUN.source_for("a", str(tmp_path / "scratch"), str(prev)).endswith(
        "a_cleaninitial.png"), "no previous output means the initial"
    (prev / "a_creditline.png").write_bytes(b"")
    assert RUN.source_for("a", str(tmp_path / "scratch"), str(prev)).endswith(
        "a_creditline.png")


def test_a_second_round_works_the_box_the_first_round_worked(tmp_path):
    """The reader only finds what still READS; a ghost is under its floor.

    So round two does not re-detect for its region - it re-opens the box round
    one recorded and re-derives the glyph mask from the frame as it now stands.
    A slug whose line has gone quiet still gets looked at.
    """
    plan = {"box": [1029, 983, 1561, 1017]}
    m = RUN.box_mask_from_plan(plan, (1440, 2560), pad=0)
    assert m[983:1017, 1029:1561].all()
    assert not m[:983].any()
    assert m.sum() == (1017 - 983) * (1561 - 1029)


def test_no_recorded_box_means_no_second_round(tmp_path):
    assert RUN.box_mask_from_plan({}, (10, 10)) is None
    assert RUN.box_mask_from_plan({"box": None}, (10, 10)) is None


def test_every_option_the_run_loop_reads_is_on_the_parser():
    """A missing --pad crashed a whole round after the models had loaded.

    argparse fails at ATTRIBUTE time, deep in the loop, so the parser and the
    loop have to be checked against each other rather than trusted.
    """
    args = RUN.build_parser().parse_args([])
    for name in ("scratch", "out", "slug", "limit", "no_rollback", "box",
                 "cpu", "input_dir", "plans_from", "glyph_pct", "pad",
                 "scoped_revert", "no_scoped_revert", "stubs"):
        assert hasattr(args, name), name
    assert args.pad == 20
    assert args.input_dir is None


def test_the_lane_defaults_are_the_2026_08_29_verdict():
    """scoped ON, stubs OFF - the operator's verdict, one per lane.

    Measured over all 39 credit-line slugs by the mark HANDED BACK (mask px
    ending byte-identical to the untouched frame): whole revert 272,893 px
    (28.13 percent), scoped 17,508 (1.80), stubs alone 285,870 (29.47), stubs
    on top of scoped 29,474 (3.04). Scoped is no worse than the whole revert on
    any of the 39; stubs improves none of them and regresses four, one of which
    (107-cleanup) goes from clean to a legible credit line. `105-cleanup`
    scores 11.562 against 15.454 untouched under every one of the four.
    """
    args = RUN.build_parser().parse_args([])
    assert args.no_scoped_revert is False, "scoped is the default"
    assert args.stubs is False, "stubs stays opt-in"


def test_the_whole_revert_is_still_reachable_from_the_command_line():
    args = RUN.build_parser().parse_args(["--no-scoped-revert"])
    assert args.no_scoped_revert is True


def test_the_old_scoped_revert_flag_is_still_accepted():
    """Recorded commands in the ledger and the docs must keep running."""
    args = RUN.build_parser().parse_args(["--scoped-revert"])
    assert args.scoped_revert is True
    assert args.no_scoped_revert is False


def test_the_run_lane_hands_the_pixels_to_the_left_edge_measurement():
    """The measured left extension is inert unless run_one passes `img`.

    `mask_from_hits` only measures where the mark starts when it is given the
    frame; with no pixels it falls back to `box_x0 - PAD`, which is the bug the
    measurement exists to fix. This asserts the wiring rather than the maths -
    a mark whose ink runs left of the read box must widen the mask, and the
    only way run_one can know that is by handing the image down.
    """
    h, w = 400, 600
    img = np.full((h, w, 3), 40, dtype=np.uint8)
    y0, y1 = 250, 280
    x0, x1 = 300, 420
    # The read box holds the letters; a detached blob of the same ink sits to
    # its left, past PAD, exactly as the (c) ring does on a real frame.
    img[y0:y1, x0:x1] = 220
    img[y0:y1, 240:270] = 220

    _out, rec = RUN.run_one(img, [_hit(x0, y0, x1, y1)], lambda c, m: c)
    ys, xs = np.nonzero(RUN.CL.mask_from_hits(img.shape,
                                              [_hit(x0, y0, x1, y1)], img=img))
    assert xs.min() < x0 - RUN.CL.PAD, "measurement itself is not reaching left"
    assert rec["box_px"] > 0
    lane = RUN.CL.mask_from_hits(img.shape, [_hit(x0, y0, x1, y1)], img=img)
    assert rec["box_px"] >= int(lane.sum()), (
        "run_one built a narrower box than the measured mask - it is not "
        "passing img= down to mask_from_hits")


def test_reopening_a_recorded_box_measures_its_left_edge_too():
    """Round two must work the region round one worked, left end included.

    The plan records the READ box, not the mask, so rebuilding it without
    pixels would hand round two the `box_x0 - PAD` edge that round one had
    already measured past - and the mark's left end would come back on exactly
    the half-cleaned frames a second round exists for.
    """
    h, w = 400, 600
    img = np.full((h, w, 3), 40, dtype=np.uint8)
    img[250:280, 300:420] = 220
    img[250:280, 240:270] = 220
    plan = {"box": [300, 250, 420, 280]}

    blind = RUN.box_mask_from_plan(plan, img.shape[:2], img=None)
    seeing = RUN.box_mask_from_plan(plan, img.shape[:2], img=img)
    assert np.nonzero(seeing)[1].min() < np.nonzero(blind)[1].min()
    assert int(seeing.sum()) > int(blind.sum())
