"""Tests for tools/lw_gen_promote.py (CI-safe: stdlib + PIL, NO torch).

Covers:
  - slug legality via the real lw_pipeline.slugify;
  - the SIZE ASSERT (reject 2560x1440 and 4000x4000, accept 1344x768);
  - the atomic-write retry path (os.replace raises WinError-like once, succeeds);
  - review/ near-miss copy on zero PASS;
  - promote NEVER invokes intake/annotate (no subprocess call).
"""

import json
import os
import re
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_gen_promote  # noqa: E402
from tools import lw_pipeline  # noqa: E402

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# --------------------------------------------------------------------------- fx

def _png(path, size):
    Image.new("RGB", size, (120, 90, 60)).save(path)


def _cand(fname, verdict="PASS", subject_cos=0.30, **extra):
    base = {
        "file": fname,
        "seed": 111,
        "round": 1,
        "subject_cos": subject_cos,
        "off_cos": 0.20,
        "margin": subject_cos - 0.20,
        "aesthetic": 0.60,
        "lap_var": 250.0,
        "stage_a_pass": verdict == "PASS",
        "stage_b_pass": verdict == "PASS",
        "verdict": verdict,
        "reason": None if verdict == "PASS" else "wrong_subject",
    }
    base.update(extra)
    return base


def _manifest(batch_id, candidates, subject="Ambessa", style="splash", top_k=3):
    return {
        "batch_id": batch_id,
        "subject": subject,
        "style": style,
        "model": "placeholder.safetensors",
        "clip_model": "ViT-L-14",
        "top_k": top_k,
        "candidates": candidates,
        "promote": {},
    }


def _write_manifest(batch_dir, manifest):
    (batch_dir / "gen_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


@pytest.fixture()
def batch(tmp_path):
    b = tmp_path / "batch"
    b.mkdir()
    originals = tmp_path / "originals"
    originals.mkdir()
    return b, originals


# --------------------------------------------------------------------------- t

def test_promote_accepts_small_and_slug_is_legal(batch):
    batch_dir, originals = batch
    _png(batch_dir / "cand_01.png", (1344, 768))
    _write_manifest(
        batch_dir,
        _manifest("ambessa-splash-20260710", [_cand("cand_01.png")]))

    manifest = lw_gen_promote.promote(batch_dir, originals_dir=originals)
    promoted = manifest["promote"]["promoted"]

    assert len(promoted) == 1
    slug = promoted[0]["slug"]
    assert SLUG_RE.match(slug), slug
    assert len(slug) <= 64
    # Real slugify shape: subject-style-<4hex>.
    assert slug.startswith("ambessa-splash-")
    # The file actually landed and a slice sidecar was written.
    assert (originals / f"{slug}.png").exists()
    assert (batch_dir / f"{slug}.slice.json").exists()
    slice_obj = json.loads((batch_dir / f"{slug}.slice.json").read_text())
    assert slice_obj["source_url"] == "gen://lw-gen/ambessa-splash-20260710"
    assert slice_obj["tool"] == "lw-gen"


@pytest.mark.parametrize("size", [(2560, 1440), (4000, 4000), (2560, 800), (800, 1440)])
def test_promote_rejects_oversize(batch, size):
    batch_dir, originals = batch
    _png(batch_dir / "cand_01.png", size)
    _write_manifest(batch_dir, _manifest("b-splash-1", [_cand("cand_01.png")]))

    manifest = lw_gen_promote.promote(batch_dir, originals_dir=originals)

    assert manifest["promote"]["promoted"] == []
    review = manifest["promote"]["review"]
    assert len(review) == 1
    assert review[0]["reason"] == lw_gen_promote.REASON_OVERSIZE
    # Nothing should have been dropped into 0.Originals.
    assert list(originals.glob("*.png")) == []


def test_atomic_place_retry_path(tmp_path, monkeypatch):
    src = tmp_path / "src.png"
    _png(src, (1344, 768))
    dest = tmp_path / "originals" / "out.png"

    calls = {"n": 0}
    real_replace = os.replace

    def flaky_replace(a, b):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(5, "Access is denied")
        return real_replace(a, b)

    monkeypatch.setattr(lw_gen_promote.os, "replace", flaky_replace)

    # ops=None forces the local copy-to-.part + retry-wrapped os.replace path.
    sha = lw_gen_promote.atomic_place(src, dest, ops=None)

    assert calls["n"] == 2  # failed once, then succeeded
    assert dest.exists()
    assert sha == lw_gen_promote._sha256(dest)
    # Original candidate is preserved (copy, not move).
    assert src.exists()


def test_zero_pass_copies_best_to_review(batch):
    batch_dir, originals = batch
    _png(batch_dir / "cand_01.png", (1344, 768))
    _png(batch_dir / "cand_02.png", (1344, 768))
    cands = [
        _cand("cand_01.png", verdict="REJECT", subject_cos=0.19),
        _cand("cand_02.png", verdict="REJECT", subject_cos=0.24),
    ]
    _write_manifest(batch_dir, _manifest("b-splash-1", cands))

    manifest = lw_gen_promote.promote(batch_dir, originals_dir=originals)

    assert manifest["promote"]["promoted"] == []
    review = manifest["promote"]["review"]
    assert len(review) == 1
    # Best-scoring (highest subject_cos) near-miss chosen.
    assert review[0]["file"] == "cand_02.png"
    assert review[0]["reason"] == lw_gen_promote.REASON_ZERO_PASS
    assert (batch_dir / "review" / "cand_02.png").exists()
    assert list(originals.glob("*.png")) == []


def test_promote_never_invokes_intake_or_annotate(batch, monkeypatch):
    batch_dir, originals = batch
    _png(batch_dir / "cand_01.png", (1344, 768))
    _write_manifest(batch_dir, _manifest("b-splash-1", [_cand("cand_01.png")]))

    import subprocess

    def boom(*a, **k):
        raise AssertionError("promote must not shell out (intake/annotate)")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "call", boom)

    manifest = lw_gen_promote.promote(batch_dir, originals_dir=originals)
    assert len(manifest["promote"]["promoted"]) == 1


def test_top_k_caps_promotions(batch):
    batch_dir, originals = batch
    cands = []
    for i in range(1, 6):
        name = f"cand_{i:02d}.png"
        _png(batch_dir / name, (1344, 768))
        cands.append(_cand(name, subject_cos=0.20 + i * 0.01))
    _write_manifest(batch_dir, _manifest("b-splash-1", cands, top_k=2))

    manifest = lw_gen_promote.promote(batch_dir, originals_dir=originals)
    promoted = manifest["promote"]["promoted"]

    assert len(promoted) == 2
    # Ranked by subject_cos desc: cand_05 (0.25) then cand_04 (0.24).
    assert promoted[0]["file"] == "cand_05.png"
    assert promoted[1]["file"] == "cand_04.png"


def test_local_slug_collision_suffixing(batch):
    batch_dir, originals = batch
    _png(batch_dir / "cand_01.png", (1344, 768))
    _write_manifest(batch_dir, _manifest("b-splash-1", [_cand("cand_01.png")]))

    manifest = lw_gen_promote.promote(batch_dir, originals_dir=originals)
    first_slug = manifest["promote"]["promoted"][0]["slug"]

    # A same-named file already sits in 0.Originals: force a -2 suffix by
    # pre-creating the exact destination the next run would pick.
    (originals / f"{first_slug}.png").write_bytes(b"occupied")
    # Re-run with a byte-identical candidate would collide on the same short
    # hash; the local guard must append -2 rather than overwrite.
    manifest2 = lw_gen_promote.promote(batch_dir, originals_dir=originals)
    second_slug = manifest2["promote"]["promoted"][0]["slug"]

    assert second_slug != first_slug
    assert second_slug.startswith(first_slug + "-")
    assert SLUG_RE.match(second_slug)


def test_promote_uses_rewritten_cand_file(batch):
    # (e) contract: promote copies whatever cand["file"] points at - here the
    # stage-rewritten cand_00_finish.png. Only the _finish artifact exists on
    # disk, so a raw-stem lookup would miss and route to review instead.
    batch_dir, originals = batch
    _png(batch_dir / "cand_00_finish.png", (1344, 768))
    _write_manifest(batch_dir, _manifest("b-splash-1", [_cand("cand_00_finish.png")]))

    manifest = lw_gen_promote.promote(batch_dir, originals_dir=originals)
    promoted = manifest["promote"]["promoted"]

    assert len(promoted) == 1
    assert promoted[0]["file"] == "cand_00_finish.png"
    slug = promoted[0]["slug"]
    assert (originals / f"{slug}.png").exists()
