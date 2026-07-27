r"""The director's PREMISE-CHECK stamp must be load-bearing, not decoration.

`ops/loop/director_prompt.md` tells the director to open every directive with

    PREMISE-CHECK: <each factual claim> [from-digest] or [UNVERIFIED]

and until now NOTHING read it. The director could declare its own premise
unknown and the executor would act on it anyway.

TWO TAGS, TWO DIFFERENT TREATMENTS - this is the part that took RC two rounds:

  [UNVERIFIED]  PROPAGATE, do not judge. The executor must not decide whether
                "the inbox holds the file" is true. It does not have to: the
                director already declared it unknown, and an unknown is never a
                pass anywhere else in this seam. Propagating the director's own
                verdict is not inventing one. RC burned a whole cycle on a
                directive that said `[UNVERIFIED] staged .githooks changes
                exist` when nothing was staged.

  [from-digest] means "I read this in my context", NOT "this is true" - the
                digest itself can be fabricated upstream. RC's cycle 15: the
                AUDIT invented a file:line and a literal, the director stamped
                the claim [from-digest] in good faith, and the executor trusted
                it. So a from-digest claim naming a CHECKABLE referent (a path,
                a file:line) gets checked against disk. One making an
                unfalsifiable prose claim does not, and must not be guessed at.

Every test below was written to be able to go RED. That is the standing lesson
of 2026-07-27: RC's version of this guard shipped with the defect sitting in its
own regression fixture, and every existing test survived because each filtered
by finding kind, so none could ever have seen the gap.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "lw_executor_premise_under_test", ROOT / "ops" / "loop" / "executor.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ex = _load()


def kinds(findings):
    return sorted(f["kind"] for f in findings)


# ---- the core: an UNVERIFIED claim is surfaced ------------------------------

def test_an_unverified_claim_is_reported():
    d = "PREMISE-CHECK: staged .githooks changes exist [UNVERIFIED]\n"
    got = ex.premise_findings(d, root=ROOT)
    assert kinds(got) == ["unverified"]
    assert "staged .githooks" in got[0]["claim"]


def test_a_clean_from_digest_claim_with_no_referent_is_not_reported():
    """Do not manufacture findings on unfalsifiable prose - that is the guess
    this guard exists to replace."""
    d = "PREMISE-CHECK: the corpus is mostly alpha-bearing [from-digest]\n"
    assert ex.premise_findings(d, root=ROOT) == []


def test_a_directive_with_no_premise_check_is_silent():
    assert ex.premise_findings("just do the thing\n", root=ROOT) == []


# ---- RC refutation 1: scan EVERY occurrence, not the first line-anchored one -

def test_a_block_quoted_prior_directive_does_not_silence_the_guard():
    """RC's verifier caught this one. Both loops quote prior directives
    constantly, and an indented quote above the real field made the scan stop at
    the quote and never reach the live PREMISE-CHECK."""
    d = ("Context from last cycle:\n"
         "    PREMISE-CHECK: everything was fine [from-digest]\n"
         "\n"
         "PREMISE-CHECK: the venv is provisioned [UNVERIFIED]\n")
    got = ex.premise_findings(d, root=ROOT)
    assert kinds(got) == ["unverified"], (
        f"the live field after a block-quoted one must still be scanned, got {got!r}")


def test_an_indented_premise_check_is_itself_scanned():
    d = "    PREMISE-CHECK: the file is on disk [UNVERIFIED]\n"
    assert kinds(ex.premise_findings(d, root=ROOT)) == ["unverified"]


# ---- RC refutation 2: two tags on one line must not fold or drop a claim -----

def test_two_claims_on_one_line_are_kept_separate():
    """A correction naming a claim the director marked VERIFIED trains the
    reader to distrust the guard - worse than silence."""
    d = ("PREMISE-CHECK: the queue is drained [from-digest], "
         "the venv works headless [UNVERIFIED]\n")
    got = ex.premise_findings(d, root=ROOT)
    assert kinds(got) == ["unverified"], f"expected only the second claim, got {got!r}"
    assert "venv" in got[0]["claim"]
    assert "queue is drained" not in got[0]["claim"], (
        "the preceding from-digest claim was folded into the unverified one")


def test_two_unverified_claims_on_one_line_both_survive():
    d = "PREMISE-CHECK: A is true [UNVERIFIED], B is true [UNVERIFIED]\n"
    got = ex.premise_findings(d, root=ROOT)
    assert len(got) == 2, f"a leading claim was dropped: {got!r}"


# ---- RC refutation 3: abbreviations must not zero the findings ---------------

@pytest.mark.parametrize("abbr", ["e.g.", "i.e.", "cf.", "etc.", "vs.", "no."])
def test_a_claim_opening_with_an_abbreviation_is_not_swallowed(abbr):
    """Splitting claims on sentence boundaries makes each of these vanish."""
    d = f"PREMISE-CHECK: {abbr} the thing is present [UNVERIFIED]\n"
    got = ex.premise_findings(d, root=ROOT)
    assert kinds(got) == ["unverified"], f"{abbr} zeroed the findings: {got!r}"


# ---- the from-digest half: check what has a machine-readable referent -------

def test_a_from_digest_claim_citing_a_missing_path_is_reported():
    d = "PREMISE-CHECK: the fix lives at ops/loop/nonexistent_module.py [from-digest]\n"
    got = ex.premise_findings(d, root=ROOT)
    assert kinds(got) == ["digest-cites-missing-path"], got


def test_a_from_digest_claim_citing_a_real_path_is_accepted():
    d = "PREMISE-CHECK: the executor is ops/loop/executor.py [from-digest]\n"
    assert ex.premise_findings(d, root=ROOT) == []


def test_a_from_digest_file_line_beyond_the_end_of_file_is_reported():
    """RC's incident verbatim: the audit invented a file:line that does not
    exist and the director relayed it in good faith."""
    d = "PREMISE-CHECK: see ops/loop/executor.py:999999 [from-digest]\n"
    got = ex.premise_findings(d, root=ROOT)
    assert kinds(got) == ["digest-cites-missing-line"], got


def test_a_real_file_line_is_accepted():
    d = "PREMISE-CHECK: see ops/loop/executor.py:1 [from-digest]\n"
    assert ex.premise_findings(d, root=ROOT) == []


def test_an_unverified_claim_citing_a_path_stays_unverified():
    """Tag precedence: the director's own doubt outranks our path check. Do not
    downgrade a self-declared unknown to a passing path lookup."""
    d = "PREMISE-CHECK: ops/loop/executor.py was rewritten [UNVERIFIED]\n"
    assert kinds(ex.premise_findings(d, root=ROOT)) == ["unverified"]


# ---- the correction text, and it must not be a polite request ---------------

def test_the_correction_names_every_finding():
    d = ("PREMISE-CHECK: A [UNVERIFIED], B [UNVERIFIED], "
         "C is at ops/loop/gone.py [from-digest]\n")
    got = ex.premise_findings(d, root=ROOT)
    text = ex.premise_correction(got)
    assert text.count("- ") >= 3, text
    for f in got:
        assert f["claim"][:20] in text


def test_there_is_no_correction_when_there_is_nothing_to_correct():
    assert ex.premise_correction([]) == ""


def test_the_correction_orders_verification_rather_than_asking_for_a_mention():
    """RC's lesson: 'state this deviation in your summary line' IS NOT a
    mechanism. A model that silently complies teaches the director nothing."""
    text = ex.premise_correction(
        ex.premise_findings("PREMISE-CHECK: x [UNVERIFIED]\n", root=ROOT))
    low = text.lower()
    assert "verify" in low or "do not act" in low
    assert "summary line" not in low, (
        "asking the model to mention it is the mechanism that already failed")
