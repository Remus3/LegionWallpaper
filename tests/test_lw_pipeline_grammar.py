"""Slug + milestone grammar tests for tools/lw_pipeline.py.

Spec: docs/research/PIPELINE_STATE_MACHINE.md sections 2.2 (grammar) and
2.5 (slugging / collision policy). Written test-first per CLAUDE.md TDD.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_pipeline as lw  # noqa: E402

STAGE_FOLDERS = [
    "0.Originals",
    "1.First Pass Scratch",
    "2.First Pass Done",
    "3.Cleaning Scratch",
    "4.Cleaning Done",
    "5.Final Scratch",
    "6.Final Done",
    "7.Last Scratch",
    "8.End Review",
    "9.Image Backup",
]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "images"
    for name in STAGE_FOLDERS + ["reference_pictures"]:
        d = r / name
        d.mkdir(parents=True)
        (d / ".gitkeep").write_text("")
    return r


@pytest.fixture(autouse=True)
def _fast_gate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lw, "PROBE_SECONDS", 0.0)


def _drop(root: Path, name: str, content: bytes = b"fake-image-bytes") -> Path:
    p = root / "0.Originals" / name
    p.write_bytes(content)
    old = p.stat().st_mtime - 120
    os.utime(p, (old, old))
    return p


# ---------------------------------------------------------------- slugify

def test_slugify_basic():
    assert lw.slugify("Ahri_Star Guardian_fullview.jpg") == "ahri-star-guardian-fullview"


def test_slugify_kills_underscores_and_illegal_chars():
    assert lw.slugify("mf_firstdone.png") == "mf-firstdone"
    assert lw.slugify('a<>:"/\\|?*b.png') == "a-b"


def test_slugify_collapses_and_trims_hyphens():
    assert lw.slugify("--Foo---Bar--.png") == "foo-bar"


def test_slugify_non_ascii_dropped():
    # "cafe etoile" with accented e's - escapes keep this file byte-ASCII
    # (CLAUDE.md hard rule) while still exercising non-ASCII input handling.
    assert lw.slugify("caf\u00e9 \u00e9toile.png") == "cafe-etoile"


def test_slugify_empty_becomes_img():
    # Japanese hiragana "ai" - fully non-ASCII basename collapses to "img".
    assert lw.slugify("\u3042\u3044.png") == "img"


def test_slugify_reserved_device_names():
    assert lw.slugify("CON.png") == "con-x"
    assert lw.slugify("com1.jpg") == "com1-x"


def test_slugify_caps_at_64_and_trims_trailing_hyphen():
    s = lw.slugify(("x" * 63) + "-y-extra-tail.png")
    assert len(s) <= 64
    assert not s.endswith("-")
    assert s[:63] == "x" * 63


# ---------------------------------------------------------------- parse

def test_parse_milestone_phases():
    m = lw.parse_milestone("ahri_firstinitial.jpg")
    assert m and m["slug"] == "ahri" and m["stage"] == "first" and m["phase"] == "initial"
    m = lw.parse_milestone("ahri_cleanneedauth.png")
    assert m and m["stage"] == "clean" and m["phase"] == "needauth"
    m = lw.parse_milestone("ahri_lastdone.png")
    assert m and m["stage"] == "last" and m["phase"] == "done"


def test_parse_milestone_working_versions():
    m = lw.parse_milestone("ahri_finalworking_02.png")
    assert m and m["phase"] == "working" and m["ver"] == 2
    m = lw.parse_milestone("ahri_finalworking_100.png")
    assert m and m["ver"] == 100


def test_parse_first_underscore_starts_token():
    # slug itself contains the text "firstdone" - hyphens keep it unambiguous
    m = lw.parse_milestone("mf-firstdone_firstinitial.png")
    assert m and m["slug"] == "mf-firstdone" and m["stage"] == "first"


def test_parse_rejects_bad_names():
    assert lw.parse_milestone("Ahri_firstdone.png") is None  # uppercase slug
    assert lw.parse_milestone("ahri__firstdone.png") is None  # double underscore
    assert lw.parse_milestone("ahri_firstworking_1.png") is None  # 1 digit
    assert lw.parse_milestone("ahri_firstdone.bmp") is None  # bad ext
    assert lw.parse_milestone("ahri_middone.png") is None  # bad stage
    assert lw.parse_milestone("ahri.png") is None  # no token


def test_parse_ext_case_insensitive():
    m = lw.parse_milestone("ahri_firstdone.PNG")
    assert m and m["ext"] == "png"


# ---------------------------------------------------------------- collisions

def test_intake_collision_suffix(root: Path):
    _drop(root, "Ahri.png", b"one")
    assert lw.main(["--root", str(root), "intake", "--all"]) == 0
    _drop(root, "ahri.jpg", b"two")  # case-insensitive dupe name, new content
    assert lw.main(["--root", str(root), "intake", "--all"]) == 0
    scratch = root / "1.First Pass Scratch"
    assert (scratch / "ahri" / "ahri_firstinitial.png").is_file()
    assert (scratch / "ahri-2" / "ahri-2_firstinitial.jpg").is_file()


def test_reintake_identical_file_refused(root: Path, capsys: pytest.CaptureFixture):
    _drop(root, "ahri.png", b"same-bytes")
    assert lw.main(["--root", str(root), "intake", "--all"]) == 0
    _drop(root, "ahri.png", b"same-bytes")
    rc = lw.main(["--root", str(root), "intake", "--all"])
    out = capsys.readouterr().out
    assert rc == 0  # skip with reason, not a crash
    assert "duplicate" in out.lower()
    # the duplicate stays in 0.Originals for the operator to handle
    assert (root / "0.Originals" / "ahri.png").is_file()
    assert not (root / "1.First Pass Scratch" / "ahri-2").exists()


def test_collision_suffix_retruncates_to_64(root: Path):
    long_name = ("z" * 80) + ".png"
    _drop(root, long_name, b"one")
    assert lw.main(["--root", str(root), "intake", "--all"]) == 0
    (root / "0.Originals" / long_name).unlink(missing_ok=True)
    _drop(root, ("z" * 80) + ".jpg", b"two")
    assert lw.main(["--root", str(root), "intake", "--all"]) == 0
    slugs = sorted(
        p.name for p in (root / "1.First Pass Scratch").iterdir() if p.is_dir()
    )
    assert len(slugs) == 2
    assert all(len(s) <= 64 for s in slugs)
    assert any(s.endswith("-2") for s in slugs)
