"""Resolve and write the LW Desktop hand-off file, with the namespace guarded.

The Legion Desktop is shared by three concurrent sessions - LW, RC and RM -
and each ends a session by OVERWRITING its own `<PREFIX>-NEXT-SESSION.txt`.
The prefix is the only thing keeping one repo's hand-off off another's, so the
write target is never taken on trust.

Contract:
  * default target is `~/Desktop/LW-NEXT-SESSION.txt`;
  * an optional on-disk intent document may name a DIFFERENT file, but only a
    bare filename under the Desktop that starts with `LW-`;
  * every other value - absolute path, drive letter, `..` segment, any path
    separator, empty/blank, non-string, malformed or missing document - falls
    back to the default instead of being honoured.

A cross-repo write must be a deliberate act, never a fallback. Rejections are
returned as a reason string rather than raised: a stale intent document must
not be able to fail an operator's `/done`, only to be ignored.

Pure stdlib, so it runs on the CI interpreter. Coverage:
tests/test_lw_next_session_guard.py.

CLI:
    python tools/lw_next_session.py --path            # print the resolved target
    python tools/lw_next_session.py --write FILE      # write FILE's content
    ... | python tools/lw_next_session.py --write -   # write stdin
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_NAME = "LW-NEXT-SESSION.txt"
REQUIRED_PREFIX = "LW-"

# Optional. Absent is the normal case - the default is not a fallback for
# failure so much as the standing answer.
INTENT_PATH = ROOT / "ops" / "runtime" / "next_session_intent.json"
INTENT_KEY = "filename"

_SEPARATORS = ("/", "\\")


def choose_filename(value):
    """Validate an intent filename. Returns (filename, reason).

    reason is "" when `value` was accepted; otherwise it explains the rejection
    and the returned filename is DEFAULT_NAME.
    """
    if not isinstance(value, str) or isinstance(value, bool):
        return DEFAULT_NAME, f"intent filename is not a string ({type(value).__name__})"
    name = value.strip()
    if not name:
        return DEFAULT_NAME, "intent filename is empty"
    if any(sep in name for sep in _SEPARATORS):
        return DEFAULT_NAME, f"intent filename {name!r} contains a path separator"
    # A drive letter cannot appear in a bare filename; ":" also catches NTFS
    # alternate data streams.
    if ":" in name:
        return DEFAULT_NAME, f"intent filename {name!r} contains a drive letter or stream"
    if name in (".", "..") or ".." in name:
        return DEFAULT_NAME, f"intent filename {name!r} contains a parent-directory segment"
    if Path(name).is_absolute():
        return DEFAULT_NAME, f"intent filename {name!r} is absolute"
    if not name.startswith(REQUIRED_PREFIX):
        return DEFAULT_NAME, (
            f"intent filename {name!r} is not prefixed {REQUIRED_PREFIX!r} - "
            "it could target a sibling repo's hand-off")
    if name == REQUIRED_PREFIX:
        return DEFAULT_NAME, "intent filename is the bare prefix with no name"
    return name, ""


def choose_filename_from_intent(intent_path=None):
    """Read the intent document and validate what it names. Returns (name, reason)."""
    path = Path(intent_path) if intent_path is not None else INTENT_PATH
    if not path.is_file():
        return DEFAULT_NAME, f"no intent document at {path}"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return DEFAULT_NAME, f"intent document unreadable ({exc.__class__.__name__})"
    if not isinstance(doc, dict):
        return DEFAULT_NAME, "intent document is not a JSON object"
    if INTENT_KEY not in doc:
        return DEFAULT_NAME, f"intent document has no {INTENT_KEY!r} key"
    return choose_filename(doc[INTENT_KEY])


def resolve_target(home=None, intent_path=None):
    """The full path the hand-off will be written to."""
    base = Path(home) if home is not None else Path.home()
    name, _reason = choose_filename_from_intent(intent_path)
    return base / "Desktop" / name


def write_handoff(text, home=None, intent_path=None):
    """Atomically write `text` to the resolved target. Returns the path written.

    Raises ValueError on non-ASCII content: the hand-off is authored text and
    the repo-wide 7-bit ASCII rule applies to it like any other.
    """
    if not isinstance(text, str):
        raise TypeError("hand-off content must be a string")
    try:
        text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(
            f"hand-off content is not 7-bit ASCII at position {exc.start}: "
            f"{text[exc.start:exc.end]!r}") from exc
    target = resolve_target(home=home, intent_path=intent_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="ascii", newline="\n")
    tmp.replace(target)
    return target


def main(argv=None):
    ap = argparse.ArgumentParser(description="LW Desktop hand-off writer")
    ap.add_argument("--path", action="store_true",
                    help="print the resolved target and exit")
    ap.add_argument("--write", metavar="FILE",
                    help="write FILE's content ('-' for stdin)")
    args = ap.parse_args(argv)

    name, reason = choose_filename_from_intent()
    if reason and "no intent document" not in reason:
        print(f"intent ignored: {reason}", file=sys.stderr)

    if args.path or not args.write:
        print(resolve_target())
        return 0

    text = sys.stdin.read() if args.write == "-" else Path(args.write).read_text(encoding="utf-8")
    try:
        written = write_handoff(text)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
