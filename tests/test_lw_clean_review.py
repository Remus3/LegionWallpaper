"""Tests for tools/lw_clean_review.py - the manual-QA before/after review sheet.

Pure stdlib: every fixture is a tmp_path runtime dir with a hand-written worker
record. No pixels beyond a zero-byte stand-in, no ML deps, so this runs in CI.

The load-bearing property is that a slug NEVER disappears from the sheet. A lane
that quietly drops the images it could not process reads as "all done" to the
operator whose eye is the actual gate, which is the failure this sheet exists to
prevent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_review as rev  # noqa: E402


def _slug_dir(root, slug, status="cleaned", after=True):
    d = root / slug
    d.mkdir(parents=True, exist_ok=True)
    rec = {"slug": slug, "status": status, "mask": "overlay-matte",
           "mask_coverage_pct": 12.5,
           "overlay": {"score_before": 0.36, "score_after": 0.05,
                       "flag_threshold": 0.15}}
    (d / f"{slug}_iopaint.json").write_text(json.dumps(rec), encoding="utf-8")
    if after:
        (d / f"{slug}_iopaint_after.png").write_bytes(b"")
        (d / f"{slug}_iopaint_before.png").write_bytes(b"")
    return rec


def test_a_cleaned_slug_renders_both_crops(tmp_path):
    _slug_dir(tmp_path, "alpha")
    page = rev.build_page(["alpha"], "t", str(tmp_path))
    assert "./alpha/alpha_iopaint_before.png" in page
    assert "./alpha/alpha_iopaint_after.png" in page
    assert "1 of 1 with a candidate" in page


def test_a_slug_with_no_record_is_shown_not_dropped(tmp_path):
    page = rev.build_page(["ghost"], "t", str(tmp_path))
    assert "ghost" in page
    assert "lane did not run" in page
    assert "0 of 1 with a candidate" in page


def test_a_partial_result_is_shown_with_its_status_not_hidden(tmp_path):
    _slug_dir(tmp_path, "romeo", status="residual")
    page = rev.build_page(["romeo"], "t", str(tmp_path))
    assert "romeo_iopaint_after.png" in page
    assert "[residual]" in page


def test_an_errored_slug_is_shown_as_skipped(tmp_path):
    _slug_dir(tmp_path, "bravo", status="error", after=False)
    page = rev.build_page(["bravo"], "t", str(tmp_path))
    assert "bravo" in page
    assert "no candidate to review" in page
    assert "bravo_iopaint_after.png" not in page


def test_a_record_claiming_cleaned_without_pixels_is_not_trusted(tmp_path):
    _slug_dir(tmp_path, "charlie", status="cleaned", after=False)
    page = rev.build_page(["charlie"], "t", str(tmp_path))
    assert "no candidate to review" in page


def test_the_sheet_says_the_score_is_not_a_verdict(tmp_path):
    _slug_dir(tmp_path, "delta")
    page = rev.build_page(["delta"], "t", str(tmp_path))
    assert "not a verdict" in page
    assert "Nothing here has been approved" in page


def test_slug_text_is_escaped(tmp_path):
    page = rev.build_page(["<script>x</script>"], "t", str(tmp_path))
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_image_paths_are_relative_to_the_sheet(tmp_path):
    _slug_dir(tmp_path, "foxtrot")
    page = rev.build_page(["foxtrot"], "t", str(tmp_path), prefix="..")
    assert "../foxtrot/foxtrot_iopaint_after.png" in page


def test_main_writes_the_sheet_atomically(tmp_path):
    _slug_dir(tmp_path, "echo")
    lst = tmp_path / "lane.txt"
    lst.write_text("echo\n", encoding="utf-8")
    out = tmp_path / "review.html"
    assert rev.main(["--slugs", str(lst), "--runtime", str(tmp_path),
                     "--out", str(out)]) == 0
    assert out.exists()
    assert not (tmp_path / "review.html.part").exists()
    assert "echo" in out.read_text(encoding="utf-8")


def test_the_algebraic_only_frame_is_shown_when_present(tmp_path):
    _slug_dir(tmp_path, "sierra")
    (tmp_path / "sierra" / "sierra_overlay_raw.png").write_bytes(b"")
    page = rev.build_page(["sierra"], "t", str(tmp_path))
    assert "sierra_overlay_raw.png" in page
    assert "algebraic only" in page
    # order matters for the eye: before, then no-fill, then filled
    assert (page.index("_iopaint_before.png") < page.index("_overlay_raw.png")
            < page.index("_iopaint_after.png"))


def test_no_algebraic_frame_when_the_pre_pass_left_nothing(tmp_path):
    _slug_dir(tmp_path, "tango")
    page = rev.build_page(["tango"], "t", str(tmp_path))
    assert "_overlay_raw.png" not in page
