"""CI-safe tests for tools/lw_gen_train_weapon_lora.py (W4 weapon LoRA trainer).

Torch-free by construction: importing lw_gen_train_weapon_lora must NOT pull
torch / diffusers / peft / PIL / numpy (every heavy dep is lazy inside the
training path). Only the pure helpers (list_pairs / read_caption / sample_aug)
are exercised here; the training loop needs a real GPU and is run by the
operator, not CI.
"""
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_gen_train_weapon_lora as tr  # noqa: E402


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fo:
        fo.write(text)


def test_list_pairs_matches_and_sorts(tmp_path):
    # Two matched png+txt pairs, deliberately out of sort order on disk.
    _write(os.path.join(str(tmp_path), "b_img.png"), "png-bytes")
    _write(os.path.join(str(tmp_path), "b_img.txt"), "caption b")
    _write(os.path.join(str(tmp_path), "a_img.png"), "png-bytes")
    _write(os.path.join(str(tmp_path), "a_img.txt"), "caption a")
    # One orphan png with no paired caption -> must be skipped.
    _write(os.path.join(str(tmp_path), "orphan.png"), "png-bytes")

    pairs = tr.list_pairs(str(tmp_path))

    assert len(pairs) == 2
    # Sorted by png path: a_img before b_img.
    assert os.path.basename(pairs[0][0]) == "a_img.png"
    assert os.path.basename(pairs[1][0]) == "b_img.png"
    for png, txt in pairs:
        assert png.endswith(".png")
        assert txt.endswith(".txt")
        assert os.path.isfile(txt)
        # The pair shares a stem.
        assert os.path.splitext(png)[0] == os.path.splitext(txt)[0]


def test_read_caption_strips(tmp_path):
    p = os.path.join(str(tmp_path), "c.txt")
    _write(p, "  vaynecrossbow, wrist-mounted repeating crossbow \n\n")
    assert tr.read_caption(p) == "vaynecrossbow, wrist-mounted repeating crossbow"


def test_sample_aug_deterministic():
    # Same seed -> identical params (two freshly seeded generators).
    a = tr.sample_aug(random.Random(123))
    b = tr.sample_aug(random.Random(123))
    assert a == b
    assert set(a.keys()) == {"angle", "scale", "flip"}


def test_sample_aug_ranges():
    for seed in range(300):
        s = tr.sample_aug(random.Random(seed))
        assert -10.0 <= s["angle"] <= 10.0
        assert 0.9 <= s["scale"] <= 1.1
        assert isinstance(s["flip"], bool)


def test_sample_aug_flip_takes_both_values():
    # Over many seeds the flip bool must exercise both True and False.
    flips = {tr.sample_aug(random.Random(seed))["flip"] for seed in range(100)}
    assert flips == {True, False}
