"""Guard for the Desktop hand-off target: tools/lw_next_session.py.

WHY THIS EXISTS (BACKLOG next-session-handoff-enforcement): the Legion Desktop
is SHARED by three concurrent sessions - LW, RC and RM - each ending a session
by overwriting its own `<PREFIX>-NEXT-SESSION.txt`. The namespace prefix is the
only thing keeping one repo's hand-off from clobbering another's. So the write
target must never be taken on trust: it is read from an on-disk intent
document, and ANY non-conforming value falls back to the LW default rather than
being honoured. A cross-repo write must be a deliberate act, never a fallback.

The rejection set is the point - absolute paths, drive letters, `..` segments,
path separators, empty/blank, non-string, and any filename not prefixed `LW-`.
A stale or doctored intent document must not be able to aim an LW session at
`RC-NEXT-SESSION.txt`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_next_session as ns  # noqa: E402


# ---------------------------------------------------------------------------
# 1. the default
# ---------------------------------------------------------------------------
def test_the_default_filename_is_the_lw_namespaced_one():
    assert ns.DEFAULT_NAME == "LW-NEXT-SESSION.txt"
    assert ns.DEFAULT_NAME.startswith(ns.REQUIRED_PREFIX)


def test_no_intent_document_resolves_to_the_default(tmp_path):
    name, reason = ns.choose_filename_from_intent(tmp_path / "missing.json")
    assert name == ns.DEFAULT_NAME
    assert "no intent document" in reason


def test_target_lands_on_the_desktop_under_the_given_home(tmp_path):
    target = ns.resolve_target(home=tmp_path, intent_path=tmp_path / "none.json")
    assert target == tmp_path / "Desktop" / ns.DEFAULT_NAME


# ---------------------------------------------------------------------------
# 2. the accepted case
# ---------------------------------------------------------------------------
def test_a_conforming_lw_prefixed_name_is_honoured():
    name, reason = ns.choose_filename("LW-NEXT-SESSION-batch21.txt")
    assert name == "LW-NEXT-SESSION-batch21.txt"
    assert reason == ""


def test_a_conforming_name_is_read_out_of_the_intent_document(tmp_path):
    doc = tmp_path / "intent.json"
    doc.write_text(json.dumps({"filename": "LW-HANDOFF.txt"}), encoding="utf-8")
    name, reason = ns.choose_filename_from_intent(doc)
    assert name == "LW-HANDOFF.txt"
    assert reason == ""


# ---------------------------------------------------------------------------
# 3. the rejection set - every one falls back to the default
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", [
    "RC-NEXT-SESSION.txt",                  # a SIBLING's hand-off - the whole point
    "RM-NEXT-SESSION.txt",
    "NEXT-SESSION.txt",                     # unprefixed
    "lw-next-session.txt",                  # prefix is case-sensitive
    "C:/Users/Administrator/Desktop/LW-X.txt",   # absolute + drive letter
    "C:\\Users\\Administrator\\Desktop\\LW-X.txt",
    "/etc/passwd",
    "../LW-NEXT-SESSION.txt",               # escape upward
    "..\\LW-NEXT-SESSION.txt",
    "sub/LW-NEXT-SESSION.txt",              # any separator at all
    "sub\\LW-NEXT-SESSION.txt",
    "LW-../escape.txt",                     # prefix present but still escapes
    "",                                     # empty
    "   ",                                  # blank
    "LW-",                                  # prefix and nothing else
    ".",
    "..",
])
def test_non_conforming_values_fall_back_to_the_default(value):
    name, reason = ns.choose_filename(value)
    assert name == ns.DEFAULT_NAME, f"{value!r} was honoured but must not be"
    assert reason, "a rejection must explain itself"


@pytest.mark.parametrize("value", [None, 42, 3.5, True, ["LW-x.txt"], {"a": 1}])
def test_non_string_values_fall_back_to_the_default(value):
    name, reason = ns.choose_filename(value)
    assert name == ns.DEFAULT_NAME
    assert reason


def test_a_sibling_repo_cannot_be_targeted_via_the_intent_document(tmp_path):
    """The headline attack: a stale/doctored document aimed at RC's hand-off."""
    doc = tmp_path / "intent.json"
    doc.write_text(json.dumps({"filename": "RC-NEXT-SESSION.txt"}), encoding="utf-8")
    name, reason = ns.choose_filename_from_intent(doc)
    assert name == ns.DEFAULT_NAME
    assert "LW-" in reason
    target = ns.resolve_target(home=tmp_path, intent_path=doc)
    assert target.name == ns.DEFAULT_NAME


# ---------------------------------------------------------------------------
# 4. a malformed intent document is not an error path, it is the default path
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("body", ["{ not json", "[]", '"a string"', "null", "{}",
                                  '{"other_key": "LW-x.txt"}'])
def test_a_malformed_intent_document_falls_back_rather_than_raising(tmp_path, body):
    doc = tmp_path / "intent.json"
    doc.write_text(body, encoding="utf-8")
    name, reason = ns.choose_filename_from_intent(doc)
    assert name == ns.DEFAULT_NAME
    assert reason


# ---------------------------------------------------------------------------
# 5. the write itself
# ---------------------------------------------------------------------------
def test_write_is_atomic_and_leaves_no_temp_file(tmp_path):
    (tmp_path / "Desktop").mkdir()
    written = ns.write_handoff("NEXT SESSION\nbody\n", home=tmp_path,
                               intent_path=tmp_path / "none.json")
    assert written.read_text(encoding="utf-8") == "NEXT SESSION\nbody\n"
    assert list((tmp_path / "Desktop").iterdir()) == [written]


def test_write_creates_the_desktop_directory_if_absent(tmp_path):
    written = ns.write_handoff("x\n", home=tmp_path,
                               intent_path=tmp_path / "none.json")
    assert written.is_file()


def test_write_overwrites_rather_than_appends(tmp_path):
    kw = {"home": tmp_path, "intent_path": tmp_path / "none.json"}
    ns.write_handoff("first\n", **kw)
    second = ns.write_handoff("second\n", **kw)
    assert second.read_text(encoding="utf-8") == "second\n"


def test_write_refuses_a_sibling_target_end_to_end(tmp_path):
    doc = tmp_path / "intent.json"
    doc.write_text(json.dumps({"filename": "RC-NEXT-SESSION.txt"}), encoding="utf-8")
    written = ns.write_handoff("body\n", home=tmp_path, intent_path=doc)
    assert written.name == ns.DEFAULT_NAME
    assert not (tmp_path / "Desktop" / "RC-NEXT-SESSION.txt").exists()


def test_written_content_is_ascii_only_by_contract(tmp_path):
    """The repo is 7-bit ASCII; the hand-off is authored text like any other."""
    with pytest.raises(ValueError):
        ns.write_handoff("smart \u201cquotes\u201d\n", home=tmp_path,
                         intent_path=tmp_path / "none.json")
