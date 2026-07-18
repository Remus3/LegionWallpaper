# arch: tests for the wallpaper deck rotator | section=tests | frozen=no
"""Tests for tools/lw_wallpaper_rotate.py.

Design contract: docs/superpowers/specs/2026-07-18-wallpaper-deck-rotator-design.md
(section "Testing" lists the 9 required cases; each is tagged below).

Everything runs inside tmp_path. The real corpus at
C:\\Users\\Administrator\\Pictures, the real ops/runtime/wallpaper_deck.json,
the real logs/ tree and the real desktop wallpaper are NEVER touched: the
win32 shim is injected per call AND replaced module-wide by an autouse
fixture that raises if anything reaches it, LOG_DIR is redirected into
tmp_path, and the schtasks runner is injected.

Determinism: every rotation test drives a seeded random.Random, and the
assertions are set / multiset properties rather than exact orderings.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from tools import lw_wallpaper_rotate as rot  # noqa: E402

NAMES = [f"img{i:02d}.png" for i in range(6)]


# -- fixtures / helpers ----------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """No test may touch the real desktop, the real logs, or the real state."""

    def _never(*_a, **_k):
        raise AssertionError("the real win32 shim must never run in tests")

    monkeypatch.setattr(rot, "set_wallpaper", _never)
    monkeypatch.setattr(rot, "LOG_DIR", tmp_path / "logs")


class _Recorder:
    """Stand-in for the win32 shim: records paths, reports success or failure."""

    def __init__(self, ok: bool = True):
        self.ok = ok
        self.calls: list[str] = []

    def __call__(self, path):
        self.calls.append(str(path))
        return self.ok


class _ForcedRng:
    """Deterministic rng stub: puts `first` at index 0, then picks the low bound."""

    def __init__(self, first):
        self.first = first
        self.randrange_calls = 0

    def shuffle(self, seq):
        seq.sort()
        if self.first in seq:
            seq.remove(self.first)
            seq.insert(0, self.first)

    def randrange(self, start, stop=None):
        self.randrange_calls += 1
        return start


def _corpus(root: Path, names=NAMES) -> Path:
    src = root / "Pictures"
    src.mkdir(parents=True, exist_ok=True)
    for name in names:
        (src / name).write_bytes(b"fake-image-bytes")
    return src


def _cfg(root: Path, src: Path) -> dict:
    return {
        "source_dir": str(src),
        "interval_minutes": 3,
        "state_path": str(root / "ops" / "runtime" / "wallpaper_deck.json"),
        "extensions": [".jpg", ".jpeg", ".png", ".bmp"],
    }


def _ticks(cfg, n, rng, rec, dry_run=False) -> list:
    picks = []
    for _ in range(n):
        code, pick = rot.tick(cfg, rng=rng, set_wallpaper_fn=rec, dry_run=dry_run)
        assert code == 0, f"tick returned {code}"
        picks.append(pick)
    return picks


def _state(cfg) -> dict:
    return json.loads(Path(cfg["state_path"]).read_text(encoding="utf-8"))


# -- case 1: a full cycle shows every image exactly once --------------------

def test_full_cycle_shows_every_image_exactly_once(tmp_path):
    cfg = _cfg(tmp_path, _corpus(tmp_path))
    rec = _Recorder()
    picks = _ticks(cfg, len(NAMES), random.Random(1234), rec)
    assert sorted(picks) == sorted(NAMES)
    assert len(set(picks)) == len(NAMES)
    assert len(rec.calls) == len(NAMES)
    # the shim is handed an absolute path inside the source dir, not a bare name
    assert all(Path(c).parent == Path(cfg["source_dir"]) for c in rec.calls)


def test_deck_is_a_permutation_not_the_scan_order(tmp_path):
    """A shuffle, not a directory walk: at least one seed must reorder."""
    reordered = False
    for seed in range(8):
        root = tmp_path / f"s{seed}"
        cfg = _cfg(root, _corpus(root))
        picks = _ticks(cfg, len(NAMES), random.Random(seed), _Recorder())
        assert sorted(picks) == sorted(NAMES)
        reordered = reordered or picks != sorted(NAMES)
    assert reordered, "no seed produced a non-alphabetical order"


# -- case 2: the cycle seam never repeats the previous pick -----------------

def test_cycle_seam_never_repeats_the_previous_pick(tmp_path):
    names = NAMES[:3]  # small deck: a naive reshuffle collides often
    for seed in range(10):
        root = tmp_path / f"seed{seed}"
        cfg = _cfg(root, _corpus(root, names))
        picks = _ticks(cfg, 2 * len(names), random.Random(seed), _Recorder())
        assert picks[len(names)] != picks[len(names) - 1], f"seam repeat at seed {seed}"
        assert sorted(picks[: len(names)]) == sorted(names)
        assert sorted(picks[len(names):]) == sorted(names)


def test_new_cycle_deck_swaps_when_first_equals_last_shown(tmp_path):
    """Pure seam logic with an rng forced into the collision."""
    rng = _ForcedRng("b.png")
    deck = rot.new_cycle_deck(["a.png", "b.png", "c.png"], last_shown="b.png", rng=rng)
    assert deck[0] != "b.png"
    assert sorted(deck) == ["a.png", "b.png", "c.png"]
    assert rng.randrange_calls == 1


def test_new_cycle_deck_leaves_a_non_colliding_first_alone():
    rng = _ForcedRng("a.png")
    deck = rot.new_cycle_deck(["a.png", "b.png", "c.png"], last_shown="c.png", rng=rng)
    assert deck[0] == "a.png"
    assert rng.randrange_calls == 0


# -- case 3: a file added mid-cycle joins the current cycle -----------------

def test_file_added_mid_cycle_is_shown_in_the_same_cycle(tmp_path):
    src = _corpus(tmp_path, NAMES[:5])
    cfg = _cfg(tmp_path, src)
    rng = random.Random(99)
    rec = _Recorder()
    picks = _ticks(cfg, 2, rng, rec)
    (src / "zz_new.png").write_bytes(b"fake-image-bytes")
    picks += _ticks(cfg, 4, rng, rec)  # 3 owed + the newcomer
    assert "zz_new.png" in picks
    assert sorted(picks) == sorted(NAMES[:5] + ["zz_new.png"])
    assert _state(cfg)["cycle"] == 1, "the newcomer must not have forced a new cycle"


def test_reconcile_splices_new_files_into_the_owed_tail_only(tmp_path):
    deck = ["a.png", "b.png", "c.png"]
    out = rot.reconcile_deck(deck, 1, ["a.png", "b.png", "c.png", "d.png"],
                             rng=random.Random(5))
    assert out[0] == "a.png", "history must not move"
    assert sorted(out[1:]) == ["b.png", "c.png", "d.png"]


# -- case 4: a file deleted mid-cycle is never set as wallpaper -------------

def test_file_deleted_mid_cycle_is_never_set_as_wallpaper(tmp_path):
    src = _corpus(tmp_path)
    cfg = _cfg(tmp_path, src)
    rng = random.Random(7)
    rec = _Recorder()
    picks = _ticks(cfg, 1, rng, rec)
    st = _state(cfg)
    owed = st["deck"][st["cursor"]:]
    doomed = owed[0]  # the very next pick
    (src / doomed).unlink()
    picks += _ticks(cfg, len(owed) - 1, rng, rec)
    assert doomed not in picks
    assert not any(Path(c).name == doomed for c in rec.calls)
    assert sorted(picks) == sorted(n for n in NAMES if n != doomed)


def test_reconcile_drops_deleted_files_from_the_owed_tail():
    out = rot.reconcile_deck(["a.png", "b.png", "c.png"], 1, ["a.png", "c.png"],
                             rng=random.Random(1))
    assert out == ["a.png", "c.png"]


# -- case 5: a file deleted after being shown does not corrupt the deck -----

def test_file_deleted_after_being_shown_does_not_corrupt_the_deck(tmp_path):
    src = _corpus(tmp_path)
    cfg = _cfg(tmp_path, src)
    rng = random.Random(21)
    rec = _Recorder()
    picks = _ticks(cfg, 1, rng, rec)
    shown = picks[0]
    (src / shown).unlink()
    picks += _ticks(cfg, len(NAMES) - 1, rng, rec)
    assert sorted(picks) == sorted(NAMES)
    st = _state(cfg)
    assert shown in st["deck"][: st["cursor"]], "history keeps the deleted file"
    assert st["cursor"] == len(st["deck"])
    # the next cycle rebuilds from what is present and skips the deleted file
    code, nxt = rot.tick(cfg, rng=rng, set_wallpaper_fn=rec)
    assert code == 0
    assert nxt != shown
    assert nxt in NAMES
    assert _state(cfg)["cycle"] == 2


# -- case 6: missing or corrupt state rebuilds cleanly ----------------------

def test_missing_state_rebuilds_cleanly(tmp_path):
    missing = tmp_path / "ops" / "runtime" / "wallpaper_deck.json"
    st = rot.load_state(missing, source_dir="C:/nope")
    assert st["deck"] == []
    assert st["cursor"] == 0
    assert st["version"] == rot.STATE_VERSION


@pytest.mark.parametrize(
    "blob",
    ["{not json", "", "[]", '{"version": 1, "deck": "nope", "cursor": 0}',
     '{"version": 1, "deck": ["a.png"], "cursor": 99}',
     '{"version": 999, "deck": ["a.png"], "cursor": 0}'],
)
def test_corrupt_state_rebuilds_cleanly(tmp_path, blob):
    path = tmp_path / "ops" / "runtime" / "wallpaper_deck.json"
    path.parent.mkdir(parents=True)
    path.write_text(blob, encoding="utf-8")
    st = rot.load_state(path, source_dir="C:/nope")
    assert st["deck"] == []
    assert st["cursor"] == 0


def test_tick_over_corrupt_state_still_shows_an_image(tmp_path):
    cfg = _cfg(tmp_path, _corpus(tmp_path))
    path = Path(cfg["state_path"])
    path.parent.mkdir(parents=True)
    path.write_text("{ truncated", encoding="utf-8")
    rec = _Recorder()
    code, pick = rot.tick(cfg, rng=random.Random(3), set_wallpaper_fn=rec)
    assert code == 0
    assert pick in NAMES
    assert _state(cfg)["cursor"] == 1


# -- case 7: the atomic write leaves no partial state file behind -----------

def test_atomic_write_leaves_no_partial_state_file_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "ops" / "runtime" / "wallpaper_deck.json"
    good = rot.default_state("C:/src")
    good["deck"] = ["a.png", "b.png"]
    good["cursor"] = 1
    rot.save_state(path, good)
    before = path.read_bytes()

    # serialization failure: nothing is opened, so no tmp is ever created
    doomed = dict(good)
    doomed["deck"] = [object()]
    with pytest.raises(TypeError):
        rot.save_state(path, doomed)
    assert path.read_bytes() == before
    assert list(path.parent.glob("*.tmp")) == []

    # replace failure: the tmp is cleaned up and the target keeps the old bytes
    def _boom(self, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(type(path), "replace", _boom)
    with pytest.raises(OSError):
        rot.save_state(path, good)
    assert path.read_bytes() == before
    assert list(path.parent.glob("*.tmp")) == []


def test_save_state_round_trips(tmp_path):
    path = tmp_path / "ops" / "runtime" / "wallpaper_deck.json"
    st = rot.default_state("C:/src")
    st["deck"] = ["a.png"]
    rot.save_state(path, st)
    assert json.loads(path.read_text(encoding="utf-8"))["deck"] == ["a.png"]
    assert list(path.parent.glob("*.tmp")) == []


# -- case 8: --dry-run does not advance the cursor --------------------------

def test_dry_run_does_not_advance_the_cursor(tmp_path):
    cfg = _cfg(tmp_path, _corpus(tmp_path))
    rec = _Recorder()
    _ticks(cfg, 1, random.Random(11), rec)
    before = Path(cfg["state_path"]).read_bytes()
    st = _state(cfg)
    expected = st["deck"][st["cursor"]]

    dry = _Recorder()
    code, pick = rot.tick(cfg, rng=random.Random(11), set_wallpaper_fn=dry, dry_run=True)
    assert code == 0
    assert pick == expected, "dry-run reports the pick a real tick would consume"
    assert dry.calls == [], "dry-run must not set the wallpaper"
    assert Path(cfg["state_path"]).read_bytes() == before, "dry-run must write nothing"

    # and the real tick that follows still gets that same image
    code, real = rot.tick(cfg, rng=random.Random(11), set_wallpaper_fn=rec)
    assert code == 0
    assert real == expected


# -- case 9: a single-image corpus does not infinite-loop at the seam -------

def test_single_image_corpus_does_not_infinite_loop(tmp_path):
    cfg = _cfg(tmp_path, _corpus(tmp_path, ["only.png"]))
    rec = _Recorder()
    picks = _ticks(cfg, 5, random.Random(2), rec)
    assert picks == ["only.png"] * 5
    assert _state(cfg)["cycle"] == 5


def test_new_cycle_deck_with_one_image_skips_the_swap():
    rng = _ForcedRng("only.png")
    deck = rot.new_cycle_deck(["only.png"], last_shown="only.png", rng=rng)
    assert deck == ["only.png"]
    assert rng.randrange_calls == 0, "a 1-image deck must not try to swap"


# -- error handling (spec section "Error handling") ------------------------

def test_empty_source_dir_exits_zero_without_touching_the_wallpaper(tmp_path):
    src = tmp_path / "Pictures"
    src.mkdir()
    cfg = _cfg(tmp_path, src)
    rec = _Recorder()
    code, pick = rot.tick(cfg, rng=random.Random(0), set_wallpaper_fn=rec)
    assert code == 0
    assert pick is None
    assert rec.calls == []
    assert not Path(cfg["state_path"]).exists()


def test_missing_source_dir_exits_non_zero(tmp_path):
    cfg = _cfg(tmp_path, tmp_path / "does-not-exist")
    rec = _Recorder()
    code, pick = rot.tick(cfg, rng=random.Random(0), set_wallpaper_fn=rec)
    assert code != 0
    assert pick is None
    assert rec.calls == []


def test_failed_wallpaper_call_does_not_advance_the_cursor(tmp_path):
    cfg = _cfg(tmp_path, _corpus(tmp_path))
    ok = _Recorder()
    _ticks(cfg, 1, random.Random(4), ok)
    before = Path(cfg["state_path"]).read_bytes()
    st = _state(cfg)
    owed = st["deck"][st["cursor"]]

    bad = _Recorder(ok=False)
    code, pick = rot.tick(cfg, rng=random.Random(4), set_wallpaper_fn=bad)
    assert code != 0
    assert pick == owed
    assert Path(cfg["state_path"]).read_bytes() == before, "a failed show stays owed"

    code, again = rot.tick(cfg, rng=random.Random(4), set_wallpaper_fn=ok)
    assert code == 0
    assert again == owed


def test_scan_source_filters_by_extension_and_ignores_directories(tmp_path):
    src = tmp_path / "Pictures"
    src.mkdir()
    for name in ("a.png", "b.JPG", "c.bmp", "d.txt", "e.webp"):
        (src / name).write_bytes(b"x")
    (src / "subdir").mkdir()
    found = rot.scan_source(src, [".jpg", ".jpeg", ".png", ".bmp"])
    assert found == ["a.png", "b.JPG", "c.bmp"]


# -- config / status / reshuffle -------------------------------------------

def test_load_config_fills_defaults_and_resolves_state_path(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"source_dir": "C:/pics"}), encoding="utf-8")
    cfg = rot.load_config(path)
    assert cfg["source_dir"] == "C:/pics"
    assert cfg["interval_minutes"] == rot.DEFAULT_CONFIG["interval_minutes"]
    assert cfg["extensions"] == rot.DEFAULT_CONFIG["extensions"]
    assert Path(cfg["state_path"]).is_absolute()


def test_shipped_config_matches_the_spec():
    cfg = rot.load_config(rot.CONFIG_PATH)
    assert cfg["extensions"] == [".jpg", ".jpeg", ".png", ".bmp"]
    assert cfg["interval_minutes"] == 3
    assert Path(cfg["state_path"]).name == "wallpaper_deck.json"


def test_status_reports_cycle_position_and_remaining(tmp_path):
    cfg = _cfg(tmp_path, _corpus(tmp_path))
    _ticks(cfg, 2, random.Random(8), _Recorder())
    text = "\n".join(rot.status(cfg))
    assert "cycle=1" in text
    assert f"position=2/{len(NAMES)}" in text
    assert f"remaining={len(NAMES) - 2}" in text


def test_status_on_a_fresh_install_does_not_raise(tmp_path):
    cfg = _cfg(tmp_path, _corpus(tmp_path))
    assert rot.status(cfg)


def test_reshuffle_starts_a_new_cycle_without_setting_the_wallpaper(tmp_path):
    cfg = _cfg(tmp_path, _corpus(tmp_path))
    rec = _Recorder()
    _ticks(cfg, 2, random.Random(6), rec)
    calls_before = len(rec.calls)
    code = rot.reshuffle(cfg, rng=random.Random(6))
    assert code == 0
    st = _state(cfg)
    assert st["cursor"] == 0
    assert st["cycle"] == 2
    assert sorted(st["deck"]) == sorted(NAMES)
    assert len(rec.calls) == calls_before, "reshuffle does not show an image"
    picks = _ticks(cfg, len(NAMES), random.Random(6), rec)
    assert sorted(picks) == sorted(NAMES)


# -- scheduling: schtasks is shelled out to, never actually run here --------

def test_install_shells_out_to_schtasks_and_registers_nothing_live(tmp_path, monkeypatch):
    def _no_real_subprocess(*_a, **_k):
        raise AssertionError("install must not spawn a real process in tests")

    monkeypatch.setattr(subprocess, "run", _no_real_subprocess)
    monkeypatch.setattr(subprocess, "Popen", _no_real_subprocess)

    seen = []

    class _Result:
        returncode = 0
        stdout = "SUCCESS"
        stderr = ""

    def _runner(argv, **kwargs):
        seen.append((argv, kwargs))
        return _Result()

    registry = []
    cfg = _cfg(tmp_path, _corpus(tmp_path))
    xml_path = tmp_path / "task.xml"
    code = rot.install(cfg, runner=_runner, registry_fn=registry.append, xml_path=xml_path)

    assert code == 0
    assert len(seen) == 1
    argv, kwargs = seen[0]
    assert argv[0] == "schtasks"
    assert "/Create" in argv
    assert rot.TASK_NAME in argv
    assert "/XML" in argv
    assert kwargs.get("creationflags") == rot.NO_WINDOW
    assert registry == [cfg["interval_minutes"]]

    xml = xml_path.read_text(encoding="utf-16")
    assert "<LogonTrigger>" in xml
    assert f"<Interval>PT{cfg['interval_minutes']}M</Interval>" in xml
    assert "lw_wallpaper_rotate.py" in xml
    assert "pythonw" in xml.lower()
    assert "tick" in xml


def test_install_reports_a_schtasks_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("no real spawn"))

    class _Fail:
        returncode = 1
        stdout = ""
        stderr = "ERROR: Access is denied."

    cfg = _cfg(tmp_path, _corpus(tmp_path))
    code = rot.install(cfg, runner=lambda *a, **k: _Fail(),
                       registry_fn=lambda _i: None, xml_path=tmp_path / "task.xml")
    assert code != 0


def test_uninstall_deletes_the_task(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("no real spawn"))
    seen = []

    class _Result:
        returncode = 0
        stdout = "SUCCESS"
        stderr = ""

    def _runner(argv, **kwargs):
        seen.append(argv)
        return _Result()

    assert rot.uninstall(runner=_runner) == 0
    assert seen[0][0] == "schtasks"
    assert "/Delete" in seen[0]
    assert rot.TASK_NAME in seen[0]


# -- CLI wiring -------------------------------------------------------------

def test_cli_status_prints_without_touching_the_real_corpus(tmp_path, capsys, monkeypatch):
    cfg = _cfg(tmp_path, _corpus(tmp_path))
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    code = rot.main(["status", "--config", str(cfg_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "cycle=" in out


def test_cli_tick_dry_run_writes_nothing(tmp_path, capsys):
    cfg = _cfg(tmp_path, _corpus(tmp_path))
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    code = rot.main(["tick", "--dry-run", "--config", str(cfg_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert not Path(cfg["state_path"]).exists()
    assert any(n in out for n in NAMES)
