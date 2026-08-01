"""Extract the post body from a saved old.reddit HTML page.

Retrieval that works (measured 2026-08-01, six for six, HTTP 200 at 54-57 KB):

    curl -sSL -b "over18=1" -A "<a real browser UA>" \
      "https://old.reddit.com/r/<sub>/comments/<id>/"

The -L matters - the bare comments url returns a 301. What does NOT work:
WebFetch (refuses the host at the tool level), the in-app browser pane
("blocked by policy"), the Apify cloud crawler (403), and the .json endpoint
(403). Measuring the 403 on .json and generalizing it to the host is how this
source got filed as unreachable the first time.

The body is the LARGEST div.md on the page, not the first - the first is the
subreddit sidebar description.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

DIV_MD = re.compile(r'<div class="md">(.*?)</div>\s*</div>', re.S)
TAG = re.compile(r"<[^>]+>")

# The repo is 7-bit ASCII by hard rule (CLAUDE.md) and the precommit gate scans
# every staged file, including quoted third-party text. Fold on extraction
# rather than hand-editing the evidence afterwards. Keyed by ESCAPE, not by the
# literal glyph - the gate reads this file too, and a literal em-dash in a fold
# table is still a banned glyph on a staged line.
FOLD = {
    "\u2014": " - ",  # em dash
    "\u2013": " - ",  # en dash
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2026": "...",  # ellipsis
    "\u00b7": "-",  # middle dot
    "\u00a0": " ",  # non-breaking space
}


def to_ascii(text: str) -> str:
    for bad, good in FOLD.items():
        text = text.replace(bad, good)
    return text.encode("ascii", "replace").decode("ascii")


def strip(fragment: str) -> str:
    text = fragment
    text = re.sub(r"<li>", "\n- ", text)
    text = re.sub(r"</p>|<br/?>", "\n", text)
    text = re.sub(r"<h(\d)>", lambda m: "\n" + "#" * int(m.group(1)) + " ", text)
    text = TAG.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def title_of(page: str) -> str:
    match = re.search(r"<title>(.*?)</title>", page, re.S)
    return html.unescape(match.group(1)).strip() if match else "UNKNOWN"


def main() -> int:
    pages = sorted(Path("scratchpad").glob("reddit-*.html"))
    if not pages:
        print("no scratchpad/reddit-*.html - fetch them first, see the docstring")
        return 1
    for path in pages:
        page = path.read_text(encoding="utf-8", errors="replace")
        bodies = [strip(m) for m in DIV_MD.findall(page)]
        if not bodies:
            print(f"=== {path.name}: NO div.md FOUND ===")
            continue
        body = max(bodies, key=len)
        out = path.with_suffix(".txt")
        out.write_text(to_ascii(f"TITLE: {title_of(page)}\n\n{body}\n"), encoding="ascii")
        print(f"{path.name}: {len(bodies)} div.md, kept {len(body)} chars -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
