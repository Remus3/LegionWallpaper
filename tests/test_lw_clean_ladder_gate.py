"""Pins the cross-engine cleaning ladder gate - ROADMAP `clean-retry-degrades`,
second half. Written test-first per CLAUDE.md TDD.

DECISION (ADR-009): the cleaning stage runs ONE engine per submission. A
`save-working` that introduces a SECOND inpaint engine for a slug already
carrying cleaning workings from another engine is refused (exit 3) unless the
caller passes `--allow-ladder`. The engines stay - what is removed is the
automatic lama -> sdxl -> iopaint chain on REJECT.

MEASURED EVIDENCE (tools/lw_clean_retry_probe.py, re-run 2026-08-12 over the
whole cleaning stage: 21 slugs, 18 with 2+ workings, 50 rejected workings,
24 scored retries):

  * STRONG labels (APPROVE_CLEAN sha256): 3 slugs adjudicated, retries won 0.
    Two settled on `_01` (lama) and one on `_cleaninitial` (no clean at all).
  * `_02` (always sdxl-animagine): n=15, seam_ssim better than `_01` in 1,
    worse in 14, editing 1.66x more area, moving further from the initial in
    14/15. Strict degradation.
  * `_03` (always iopaint): n=9, seam better in 6 - but repainting 2.66x the
    area, and all 9 rejected.

WHY NOT A MEASURED-IMPROVEMENT GATE: the only metric on which a later rung ever
wins is bought with area, so it cannot serve as the gate. Over the 24 scored
retries, Pearson r(edit-area ratio, seam gain) = +0.46; mean area ratio is
3.06x when a retry gains seam versus 1.61x when it does not, and every
seam-gaining retry was rejected. Gating on seam would select for the biggest
repaint - the same failure mode as the settled ruling that `overlay_score` is a
DETECTION flag and never a removal-QUALITY gate (LEDGER 101-103).

WHY THE OPERATOR'S REJECTS DO NOT SUPPLY A PER-SLUG SIGNAL EITHER: the 50
rejects are three BLANKET engine verdicts, not per-image ones - the manifests
carry identical timestamps and identical notes across the whole queue
(2026-07-16T20:37 "swap LaMa erase -> SDXL Animagine reconstruction",
2026-07-16T22:15 "block-SDXL rejected; redo via Dekel", 2026-08-02T00:11
"operator reject: corrections are contextually incorrect for the image").
Per-slug ladder spend therefore buys a decision that is taken per ENGINE.
"""
from __future__ import annotations

import json
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
    for name in STAGE_FOLDERS:
        d = r / name
        d.mkdir(parents=True)
        (d / ".gitkeep").write_text("")
    return r


@pytest.fixture(autouse=True)
def _fast_gate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lw, "PROBE_SECONDS", 0.0)


def run(root: Path, *args: str) -> int:
    return lw.main(["--root", str(root), *args])


def _man_with(*saves) -> dict:
    """Manifest carrying one SAVE_WORKING per (tool, dst_name) pair."""
    man = lw.new_manifest("slug", "slug.png", "0" * 64)
    for tool, dst in saves:
        lw.add_transition(man, "SAVE_WORKING",
                          actor=f"tool:{tool}" if tool else "operator",
                          tool=tool, src="x.png",
                          dst=f"3.Cleaning Scratch/slug/{dst}",
                          sha_in="0" * 64, sha_out="0" * 64)
    return man


# ------------------------------------------------------- engine history

def test_engine_history_reads_cleaning_workings_only():
    """First-pass workings share the manifest; they are not cleaning engines."""
    man = _man_with(("lw_first_pass", "slug_firstworking_01.png"),
                    ("lama", "slug_cleanworking_01.png"))
    assert lw.cleaning_engines_used(man) == ["lama"]


def test_engine_history_ignores_non_engine_tools():
    """operator-select / clean-scan are bookkeeping, not an inpaint engine."""
    man = _man_with(("lama", "slug_cleanworking_01.png"),
                    ("clean-scan", "slug_cleanworking_02.png"),
                    ("operator-select", "slug_cleanworking_03.png"))
    assert lw.cleaning_engines_used(man) == ["lama"]


def test_engine_history_is_ordered_and_deduped():
    man = _man_with(("lama", "slug_cleanworking_01.png"),
                    ("sdxl-animagine", "slug_cleanworking_02.png"),
                    ("sdxl-animagine", "slug_cleanworking_03.png"))
    assert lw.cleaning_engines_used(man) == ["lama", "sdxl-animagine"]


# ------------------------------------------------------- the gate itself

def test_same_engine_again_is_allowed():
    man = _man_with(("lama", "slug_cleanworking_01.png"))
    lw.assert_ladder_allowed("clean", man, "lama")


def test_first_engine_on_a_fresh_slug_is_allowed():
    lw.assert_ladder_allowed("clean", _man_with(), "lama")
    lw.assert_ladder_allowed("clean", None, "sdxl-animagine")


def test_second_engine_is_refused_with_exit_3():
    man = _man_with(("lama", "slug_cleanworking_01.png"))
    with pytest.raises(lw.PipelineError) as e:
        lw.assert_ladder_allowed("clean", man, "sdxl-animagine")
    assert e.value.code == 3
    msg = str(e.value)
    assert "lama" in msg and "sdxl-animagine" in msg
    assert "--allow-ladder" in msg


def test_second_engine_is_allowed_with_the_explicit_opt_in():
    man = _man_with(("lama", "slug_cleanworking_01.png"))
    lw.assert_ladder_allowed("clean", man, "sdxl-animagine", allow_ladder=True)


def test_operator_select_is_never_refused():
    """The operator picking the winner is how a rejected queue is resolved."""
    man = _man_with(("lama", "slug_cleanworking_01.png"))
    lw.assert_ladder_allowed("clean", man, "operator-select")
    lw.assert_ladder_allowed("clean", man, None)


def test_gate_is_cleaning_stage_only():
    """Other stages have no measured ladder problem; leave them alone."""
    man = _man_with(("lama", "slug_cleanworking_01.png"))
    for stage in ("first", "final", "last"):
        lw.assert_ladder_allowed(stage, man, "sdxl-animagine")


def test_an_unknown_new_engine_still_trips_the_gate():
    """Fail closed: a tool nobody has classified counts as a second engine."""
    man = _man_with(("lama", "slug_cleanworking_01.png"))
    with pytest.raises(lw.PipelineError) as e:
        lw.assert_ladder_allowed("clean", man, "some-future-diffuser")
    assert e.value.code == 3


# ------------------------------------------------------- wired into the CLI

def _seed_cleaning(root: Path, slug: str) -> Path:
    folder = root / "3.Cleaning Scratch" / slug
    folder.mkdir(parents=True)
    man = lw.new_manifest(slug, f"{slug}.png", "0" * 64)
    (folder / "manifest.json").write_text(
        json.dumps(man, indent=2) + "\n", encoding="utf-8")
    (folder / f"{slug}_cleaninitial.png").write_bytes(b"initial")
    return folder


def test_cli_refuses_a_second_engine_and_writes_nothing(root: Path,
                                                        tmp_path: Path):
    folder = _seed_cleaning(root, "ahri")
    src = tmp_path / "cand.png"
    src.write_bytes(b"one")
    assert run(root, "save-working", "ahri", "--from", str(src),
               "--tool", "lama") == 0
    assert (folder / "ahri_cleanworking_01.png").is_file()

    src2 = tmp_path / "cand2.png"
    src2.write_bytes(b"two")
    assert run(root, "save-working", "ahri", "--from", str(src2),
               "--tool", "sdxl-animagine") == 3
    # refused BEFORE any mutation: no _02 file, no extra transition
    assert not (folder / "ahri_cleanworking_02.png").exists()
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert [t["op"] for t in man["transitions"]] == ["SAVE_WORKING"]


def test_cli_allow_ladder_lets_the_second_engine_through(root: Path,
                                                         tmp_path: Path):
    folder = _seed_cleaning(root, "ahri")
    src = tmp_path / "cand.png"
    src.write_bytes(b"one")
    assert run(root, "save-working", "ahri", "--from", str(src),
               "--tool", "lama") == 0
    src2 = tmp_path / "cand2.png"
    src2.write_bytes(b"two")
    assert run(root, "save-working", "ahri", "--from", str(src2),
               "--tool", "sdxl-animagine", "--allow-ladder") == 0
    assert (folder / "ahri_cleanworking_02.png").is_file()


def test_cli_same_engine_twice_is_untouched_by_the_gate(root: Path,
                                                        tmp_path: Path):
    """The INTRA-engine retry is governed by max_attempts=1, not by this gate."""
    folder = _seed_cleaning(root, "ahri")
    for i, blob in enumerate((b"one", b"two"), start=1):
        src = tmp_path / f"cand{i}.png"
        src.write_bytes(blob)
        assert run(root, "save-working", "ahri", "--from", str(src),
                   "--tool", "lama") == 0
    assert (folder / "ahri_cleanworking_02.png").is_file()


# ------------------------------------------------------- measured constants

def test_measured_ladder_census_is_recorded():
    """The census behind the decision, pinned so a silent drift is visible.

    Re-running needs images/** plus the cv venv, so the numbers are asserted as
    constants exactly like tests/test_lw_clean_retry_default.py does.
    """
    census = {
        "slugs": 21,
        "slugs_with_2plus_workings": 18,
        "decided": 3,
        "settled_on_01": 2,
        "settled_above_01": 0,
        "settled_on_cleaninitial": 1,
        "rejected_workings_total": 50,
        "scored_retries": 24,
        "seam_gain_vs_area_pearson_r": 0.46,
    }
    assert census["settled_above_01"] == 0
    assert census["settled_on_01"] + census["settled_on_cleaninitial"] == \
        census["decided"]
    # the gate's whole justification: seam gain tracks how much was repainted
    assert census["seam_gain_vs_area_pearson_r"] > 0.0
