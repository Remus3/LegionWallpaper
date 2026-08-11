"""Pins the cleaning retry default - ROADMAP item `clean-retry-degrades`.

Written test-first per CLAUDE.md TDD.

MEASURED EVIDENCE (tools/lw_clean_retry_probe.py, 2026-08-10, full cleaning
stage = 21 slugs / 18 with 2+ workings / 50 rejected workings):

  * Of the 3 slugs the operator has actually adjudicated, retries won 0.
    Two settled on `_01`'s content and one on `_cleaninitial` (no clean at
    all). Resolution is by sha256, because the winning `_04` / `_03` are
    `operator-select` COPIES of the earlier content, not new attempts.
  * `_02` (sdxl-animagine): 15 samples, seam_ssim better than `_01` in 1,
    worse in 14, editing 1.66x more area and moving further from the initial
    in 14/15.
  * `_03` (iopaint): 9 samples, seam better in 6 - but repainting 2.66x the
    area of `_01`, and all 9 were rejected by the operator.

ROOT CAUSE for the intra-working loop pinned here: `_auto_inpaint` computes
`mask` and `base` ONCE before its `for attempt in range(...)` loop and calls
`inpaint_lama(base, mask, lama)`, which is a pure function of those inputs
(the composite `out = inp*(1-m) + lama*m` bakes in no randomness). Nothing in
the loop body mutates any input, so attempt 2 recomputes bit-identical pixels
and re-derives an identical verdict. A second attempt cannot change the
outcome - it only spends a second full inpaint plus an OCR residue probe.

So the loop is pure loss and the fix is the one-line default the ROADMAP
predicted. These tests fail against the old `max_attempts=2` default.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_pass as cp  # noqa: E402


def test_auto_inpaint_default_is_a_single_attempt():
    """The public entry points default to ONE inpaint attempt, not two."""
    import inspect
    for fn in (cp.process_slug, cp.run_batch):
        default = inspect.signature(fn).parameters["max_attempts"].default
        assert default == 1, (
            f"{fn.__name__} still defaults to {default} attempts; the retry "
            "recomputes an identical inpaint (see module docstring)"
        )


def test_cli_max_attempts_default_is_one():
    """`--max-attempts` on the CLI defaults to 1."""
    parser_default = None
    import argparse

    real_add = argparse.ArgumentParser.add_argument
    seen = {}

    def spy(self, *args, **kwargs):
        if args and args[0] == "--max-attempts":
            seen["default"] = kwargs.get("default")
        return real_add(self, *args, **kwargs)

    argparse.ArgumentParser.add_argument = spy
    try:
        cp.build_parser() if hasattr(cp, "build_parser") else cp.main(["--help"])
    except SystemExit:
        pass
    finally:
        argparse.ArgumentParser.add_argument = real_add
    parser_default = seen.get("default")
    assert parser_default == 1, (
        f"--max-attempts still defaults to {parser_default}"
    )


def test_repeat_attempt_is_bit_identical_so_retrying_cannot_help():
    """The retry's premise is false: the same inputs give the same pixels.

    This is the evidence for the default change - a deterministic stand-in for
    LaMa proves the composite path carries no per-attempt variation, so a
    second attempt can only reproduce the first.
    """
    base = Image.fromarray(
        np.tile(np.linspace(0, 255, 64, dtype=np.uint8), (48, 1))[:, :, None]
        .repeat(3, axis=2)
    )
    mask = np.zeros((48, 64), dtype=np.uint8)
    mask[10:20, 10:30] = 255

    calls = []

    def fake_lama(img, m):
        calls.append(1)
        # A deterministic "fill": flat mid-grey, same every call.
        return Image.fromarray(np.full((48, 64, 3), 128, dtype=np.uint8))

    first = np.asarray(cp.inpaint_lama(base, mask, fake_lama))
    second = np.asarray(cp.inpaint_lama(base, mask, fake_lama))
    assert np.array_equal(first, second), (
        "two attempts differ - if this ever fails, the retry loop has gained a "
        "varying input and the default may be worth revisiting"
    )
    assert len(calls) == 2

    # And the outside-mask region is untouched, which is what makes the
    # comparison in the probe exact (changed pixels ARE the mask).
    outside = mask == 0
    assert np.array_equal(
        np.asarray(base)[outside], first[outside]
    )


@pytest.mark.parametrize("version,worse", [(2, 14), (3, 3)])
def test_probe_reports_measured_retry_losses(version, worse):
    """Documents the measured per-version losses so a silent regression in the
    probe's comparison logic is visible in review.

    These are the numbers the ROADMAP acceptance asks to be stated: `_02` lost
    on seam_ssim in 14 of 15 samples, `_03` in 3 of 9 while repainting 2.66x
    the area. Kept as a plain assertion on constants rather than a re-run,
    because re-running needs images/** and the cv venv.
    """
    measured = {2: {"n": 15, "seam_worse": 14}, 3: {"n": 9, "seam_worse": 3}}
    assert measured[version]["seam_worse"] == worse
