"""Perceptual near-duplicate gate on intake (tools/lw_pipeline.py).

Regression origin (2026-09-01): intake dedup was sha256-only, so a re-DOWNLOAD
of an already-processed artwork - same pixels, different JPEG encode - sailed
through as a brand new slug. Measured case: academy_ahri_..._dlj1ng3-pre.jpg
came back at 146064 bytes vs the 144582 already in 9.Image Backup, pHash and
dHash Hamming BOTH 0 at an identical 1163x687, and the existing slug was
already cleaned. The byte hash cannot see that; a perceptual hash can.

Bands follow SOURCE_RECOVERY section 4 / lw_recover.consensus_match: BOTH
pHash and dHash Hamming <= accept => near-dup; <= review (both agreeing) =>
review; otherwise clean. Consensus is the point - one hash agreeing is not
enough.

lw_pipeline is stdlib-only by contract, so the hashing hop is injected through
lw._image_hashes. Every band/refusal/cache test stubs it and runs on bare
Python; the one real-pixel test importorskips imagehash.
"""
from __future__ import annotations

import json
import math
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


def run(root: Path, *args: str) -> int:
    return lw.main(["--root", str(root), *args])


def _seed_backup(root: Path, slug: str, original_name: str,
                 content: bytes = b"already-here") -> Path:
    """Put a slug in 9.Image Backup the way a completed intake would."""
    d = root / "9.Image Backup" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / original_name).write_bytes(content)
    man = lw.new_manifest(slug, original_name, lw.sha256_file(d / original_name))
    (d / "manifest.json").write_text(json.dumps(man), encoding="ascii")
    return d


def _stub_hashes(monkeypatch: pytest.MonkeyPatch, table: dict) -> list:
    """Route lw._image_hashes through a filename -> (phash, dhash) table.

    Returns the list of paths actually hashed so a cache test can assert that
    the second run did no work.
    """
    seen: list = []

    def fake(path):
        seen.append(str(path))
        key = Path(path).name
        if key not in table:
            raise AssertionError(f"unexpected hash target {key}")
        ph, dh = table[key]
        return {"phash": ph, "dhash": dh}

    monkeypatch.setattr(lw, "_image_hashes", fake)
    return seen


# ---------------------------------------------------------------------------
# the regression: same pixels, different bytes, different filename
# ---------------------------------------------------------------------------

def test_near_dup_refuses_byte_different_reencode(root, monkeypatch, capsys):
    """A perceptual twin of an existing slug is refused even when bytes differ.

    The incoming filename is deliberately UNRELATED to the existing slug, so a
    pass here cannot be explained by the slug-collision branch in unique_slug -
    only a corpus-wide perceptual compare can catch it.
    """
    _seed_backup(root, "academy-ahri-dlj1ng3-pre", "academy_ahri_dlj1ng3-pre.jpg")
    _drop(root, "totally_different_name.jpg", b"different-bytes-same-pixels")
    _stub_hashes(monkeypatch, {
        "totally_different_name.jpg": (0xABCD1234, 0x5678FEDC),
        "academy_ahri_dlj1ng3-pre.jpg": (0xABCD1234, 0x5678FEDC),
    })

    assert run(root, "intake", "--all") == 0
    out = capsys.readouterr().out
    assert "near-duplicate" in out
    assert "academy-ahri-dlj1ng3-pre" in out
    # refused: the file stays put and no new slug is created
    assert (root / "0.Originals" / "totally_different_name.jpg").is_file()
    assert not (root / "1.First Pass Scratch" / "totally-different-name").exists()


def test_near_dup_review_band_intakes_and_flags(root, monkeypatch, capsys):
    """9..14 on both hashes is not confident enough to refuse - intake + flag."""
    _seed_backup(root, "existing-slug", "existing.jpg")
    _drop(root, "maybe_related.jpg")
    _stub_hashes(monkeypatch, {
        # 12 bits set against an all-zero neighbour -> Hamming 12 on BOTH
        # hashes, which is past accept (8) but inside review (14).
        "maybe_related.jpg": (0b111111111111, 0b111111111111),
        "existing.jpg": (0, 0),
    })

    assert run(root, "intake", "--all") == 0
    out = capsys.readouterr().out
    assert "near-dup review" in out
    assert (root / "1.First Pass Scratch" / "maybe-related").is_dir()
    assert not (root / "0.Originals" / "maybe_related.jpg").exists()


def test_clean_image_intakes_without_a_flag(root, monkeypatch, capsys):
    _seed_backup(root, "existing-slug", "existing.jpg")
    _drop(root, "brand_new.jpg")
    _stub_hashes(monkeypatch, {
        "brand_new.jpg": (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF),
        "existing.jpg": (0, 0),
    })

    assert run(root, "intake", "--all") == 0
    out = capsys.readouterr().out
    assert "near-dup" not in out
    assert (root / "1.First Pass Scratch" / "brand-new").is_dir()


def test_consensus_requires_both_hashes_to_agree(root, monkeypatch, capsys):
    """pHash 0 but dHash far apart is NOT a near-dup - guards false pairs."""
    _seed_backup(root, "existing-slug", "existing.jpg")
    _drop(root, "one_hash_only.jpg")
    _stub_hashes(monkeypatch, {
        "one_hash_only.jpg": (0, 0xFFFFFFFFFFFFFFFF),
        "existing.jpg": (0, 0),
    })

    assert run(root, "intake", "--all") == 0
    assert "near-duplicate" not in capsys.readouterr().out
    assert (root / "1.First Pass Scratch" / "one-hash-only").is_dir()


def test_allow_near_dup_overrides_the_refusal(root, monkeypatch, capsys):
    """The operator is never refused (same shape as ADR-009 --allow-ladder)."""
    _seed_backup(root, "existing-slug", "existing.jpg")
    _drop(root, "twin.jpg")
    _stub_hashes(monkeypatch, {
        "twin.jpg": (42, 99),
        "existing.jpg": (42, 99),
    })

    assert run(root, "intake", "--all", "--allow-near-dup") == 0
    out = capsys.readouterr().out
    assert "near-dup override" in out
    assert (root / "1.First Pass Scratch" / "twin").is_dir()


def test_dry_run_reports_the_verdict_and_mutates_nothing(root, monkeypatch,
                                                         capsys):
    _seed_backup(root, "existing-slug", "existing.jpg")
    _drop(root, "twin.jpg")
    _stub_hashes(monkeypatch, {
        "twin.jpg": (42, 99),
        "existing.jpg": (42, 99),
    })

    assert run(root, "intake", "--all", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "near-duplicate" in out
    assert (root / "0.Originals" / "twin.jpg").is_file()
    assert not (root / "1.First Pass Scratch" / "twin").exists()
    assert not (root / "9.Image Backup" / "twin").exists()


def test_gate_degrades_when_imagehash_is_absent(root, monkeypatch, capsys):
    """No imagehash -> note it and intake anyway; never crash the pipeline."""
    _seed_backup(root, "existing-slug", "existing.jpg")
    _drop(root, "twin.jpg")

    def boom(path):
        raise ImportError("No module named 'imagehash'")

    monkeypatch.setattr(lw, "_image_hashes", boom)

    assert run(root, "intake", "--all") == 0
    out = capsys.readouterr().out
    assert "near-dup gate skipped" in out
    assert (root / "1.First Pass Scratch" / "twin").is_dir()


def test_backup_hashes_are_cached_between_runs(root, monkeypatch):
    _seed_backup(root, "existing-slug", "existing.jpg")
    _drop(root, "first_in.jpg")
    seen = _stub_hashes(monkeypatch, {
        "first_in.jpg": (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF),
        "existing.jpg": (0, 0),
    })
    assert run(root, "intake", "--all") == 0
    assert any("existing.jpg" in s for s in seen)

    cache = root.parent / "ops" / "runtime" / "intake_phash_cache.json"
    assert cache.is_file()
    assert json.loads(cache.read_text(encoding="ascii"))

    # second run: the backup corpus is unchanged, so only the new drop is hashed
    _drop(root, "second_in.jpg")
    seen2 = _stub_hashes(monkeypatch, {
        "second_in.jpg": (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF),
    })
    assert run(root, "intake", "--all") == 0
    assert not any("existing.jpg" in s for s in seen2)


def test_sha256_refusal_still_fires_first(root, monkeypatch, capsys):
    """The byte-identical path is untouched by the new gate."""
    content = b"identical-bytes"
    _seed_backup(root, "dupe-me", "dupe_me.jpg", content=content)
    _drop(root, "dupe_me.jpg", content=content)
    _stub_hashes(monkeypatch, {
        "dupe_me.jpg": (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF),
    })

    assert run(root, "intake", "--all") == 0
    assert "hash-equal original" in capsys.readouterr().out
    assert (root / "0.Originals" / "dupe_me.jpg").is_file()


# ---------------------------------------------------------------------------
# real pixels - the actual 2026-09-01 shape, needs imagehash
# ---------------------------------------------------------------------------

def test_real_reencode_of_the_same_image_is_refused(root):
    pytest.importorskip("imagehash")
    from PIL import Image

    # Smooth but STRUCTURED content on purpose, and measured rather than
    # assumed. pHash is a DCT measure over the low frequencies, so both
    # extremes are useless as a fixture: a high-frequency pattern is shredded
    # by JPEG quantization (measured q92-vs-q71 pHash Hamming 12) and a pure
    # linear ramp has no stable structure for the median split to bite on
    # (measured 20). Sinusoidal blobs sit where real artwork sits and measure
    # 0/0 across the same re-encode - which is exactly what the real
    # academy-ahri pair measured on disk.
    im = Image.new("RGB", (160, 96))
    for x in range(160):
        for y in range(96):
            v = math.sin(x / 13.0) * math.cos(y / 9.0)
            u = math.sin((x + y) / 21.0)
            im.putpixel((x, y), (int(128 + 100 * v), int(128 + 90 * u),
                                 int(128 + 80 * v * u)))

    d = root / "9.Image Backup" / "seed-slug"
    d.mkdir(parents=True)
    im.save(d / "seed.jpg", quality=92)
    man = lw.new_manifest("seed-slug", "seed.jpg", lw.sha256_file(d / "seed.jpg"))
    (d / "manifest.json").write_text(json.dumps(man), encoding="ascii")

    # same pixels, different encoder settings -> different bytes, same pHash
    incoming = root / "0.Originals" / "redownloaded.jpg"
    im.save(incoming, quality=71)
    old = incoming.stat().st_mtime - 120
    os.utime(incoming, (old, old))
    assert lw.sha256_file(incoming) != lw.sha256_file(d / "seed.jpg")

    assert run(root, "intake", "--all") == 0
    assert incoming.is_file()
    assert not (root / "1.First Pass Scratch" / "redownloaded").exists()
