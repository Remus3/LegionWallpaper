"""Guards for the two helpers in the wiki-swap one-off that can fail SILENTLY.

The swap itself is a one-shot data operation, but two pieces of it are exactly
the kind that pass while doing the wrong thing, and both cost a discarded run
during the real swap:

  1. `stale_initial` must find `<slug>_firstinitial.<ANY ext>`. The first
     version of this comparison globbed a hard-coded `.png`, matched nothing on
     every .jpg-sourced slug, and silently fell back to treating the 2560x1440
     `_firstdone` OUTPUT as the source.
  2. `verify` must REFUSE bytes whose decoded dimensions are not the ones the
     plan was built on. A swap that stages a different image than the one that
     was measured would look identical in every log line.

Nothing here touches the network or images/.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import lw_wiki_swap_oneoff as sw  # noqa: E402


def _png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("ext", [".png", ".jpg", ".jpeg", ".webp"])
def test_stale_initial_finds_any_extension(tmp_path, ext):
    d = tmp_path / "myslug"
    d.mkdir()
    target = d / f"myslug_firstinitial{ext}"
    target.write_bytes(b"x")
    (d / "myslug_firstdone.png").write_bytes(b"y")
    assert sw.stale_initial(d) == target


def test_stale_initial_never_returns_the_firstdone_output(tmp_path):
    # The exact silent-fallback shape: an output present, no initial at all.
    d = tmp_path / "myslug"
    d.mkdir()
    (d / "myslug_firstdone.png").write_bytes(b"y")
    assert sw.stale_initial(d) is None


def test_stale_initial_is_deterministic_across_mixed_extensions(tmp_path):
    d = tmp_path / "myslug"
    d.mkdir()
    for ext in (".webp", ".jpg", ".png"):
        (d / f"myslug_firstinitial{ext}").write_bytes(b"x")
    assert sw.stale_initial(d).name == "myslug_firstinitial.jpg"


def test_stale_initial_on_a_missing_dir(tmp_path):
    assert sw.stale_initial(tmp_path / "nope") is None


def test_verify_accepts_the_planned_dimensions():
    meta = sw.verify(_png(64, 36), 64, 36)
    assert meta["w"] == 64 and meta["h"] == 36
    assert meta["format"] == "PNG"
    assert len(meta["sha256"]) == 64


def test_verify_refuses_a_dimension_mismatch():
    # Staging a different image than the one that was measured must be loud.
    with pytest.raises(RuntimeError, match="!= planned"):
        sw.verify(_png(64, 36), 65, 36)


def test_verify_refuses_undecodable_bytes():
    with pytest.raises(Image.UnidentifiedImageError):
        sw.verify(b"not an image", 64, 36)
