"""Build a 1:1 before/after review sheet for a manual-QA cleaning lane.

The QA lane exists because the operator's EYE is the gate. The detector's
`overlay_score` is a DETECTION flag and never a removal-QUALITY measure (a frame
can sit deep inside the clean distribution and still show its artist credit line
at 1:1 - LEDGER 101-103), so this sheet shows the raw ROI crops the worker
already wrote, at native resolution, and reports the score only as provenance.

Reads `<runtime>/<slug>/<slug>_iopaint.json` per slug and emits an index.html
beside them with relative <img> srcs, so the page works straight off disk. It
writes NO pixels and mutates NO pipeline state.

  python tools/lw_clean_review.py --slugs lane.txt --title "centre overlay"
"""
from __future__ import annotations

import argparse
import html
import json
import os

RUNTIME = r"C:\LegionWallpaper\ops\runtime\clean"


def load_record(slug, runtime=RUNTIME):
    """Return the worker's per-slug JSON, or None when the lane never ran."""
    path = os.path.join(runtime, slug, f"{slug}_iopaint.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def row_html(slug, rec, runtime=RUNTIME, prefix="."):
    """One review row. A slug with no after-image is SHOWN as skipped, never dropped."""
    name = html.escape(slug)
    if rec is None:
        return (f'<section class="row skip"><h2>{name}</h2>'
                f'<p class="note">lane did not run - no worker record</p></section>')
    ov = rec.get("overlay") or {}
    before = f"{prefix}/{slug}/{slug}_iopaint_before.png"
    after = f"{prefix}/{slug}/{slug}_iopaint_after.png"
    # PIXELS decide whether there is something to look at, not the status word:
    # a `residual` result is a real candidate the operator must judge, and a
    # record claiming `cleaned` with no image on disk is not to be trusted.
    if not os.path.exists(os.path.join(runtime, slug, f"{slug}_iopaint_after.png")):
        return (f'<section class="row skip"><h2>{name}</h2>'
                f'<p class="note">status={html.escape(str(rec.get("status")))} '
                f'- no candidate to review</p></section>')
    status = str(rec.get("status"))
    flag = "" if status == "cleaned" else f' <b>[{html.escape(status)}]</b>'
    meta = (f'{flag} score {ov.get("score_before")} -&gt; {ov.get("score_after")} '
            f'(flag {ov.get("flag_threshold")}) | mask '
            f'{rec.get("mask_coverage_pct")}% of ROI | {html.escape(str(rec.get("mask")))}')
    # The algebraic pre-pass output, when the overlay lane wrote one. It inverts
    # the matting equation per pixel - it CANNOT displace a line or invent one -
    # so showing it beside the LaMa-filled result separates "removal too weak"
    # from "fill hallucinated". The 2026-08-22 operator review rejected all 45
    # filled results for exactly that pair of defects.
    raw_rel = f"{prefix}/{slug}/{slug}_overlay_raw.png"
    mid = ""
    if os.path.exists(os.path.join(runtime, slug, f"{slug}_overlay_raw.png")):
        mid = (f'<figure><figcaption>algebraic only (no fill)</figcaption>'
               f'<img src="{html.escape(raw_rel)}" alt="{name} algebraic"></figure>')
    return (f'<section class="row"><h2>{name}</h2>'
            f'<p class="note">{meta}</p><div class="pair">'
            f'<figure><figcaption>before</figcaption>'
            f'<img src="{html.escape(before)}" alt="{name} before"></figure>'
            f'{mid}'
            f'<figure><figcaption>after (LaMa fill)</figcaption>'
            f'<img src="{html.escape(after)}" alt="{name} after"></figure>'
            f'</div></section>')


CSS = """body{background:#111;color:#ddd;font:14px/1.5 Consolas,monospace;margin:0;padding:24px}
h1{font-size:18px}h2{font-size:15px;color:#8fd}
.note{color:#999;margin:2px 0 8px}
.row{border-top:1px solid #333;padding:16px 0}
.row.skip{color:#c96}
.pair{display:flex;gap:16px;flex-wrap:wrap}
figure{margin:0}figcaption{color:#777;font-size:12px}
img{image-rendering:pixelated;max-width:100%;border:1px solid #333}
.lead{color:#bbb;max-width:70em}"""


def build_page(slugs, title, runtime=RUNTIME, prefix="."):
    """Full HTML for the sheet. Pure apart from the per-slug record reads."""
    rows = [row_html(s, load_record(s, runtime), runtime, prefix) for s in slugs]
    shown = sum(1 for r in rows if 'class="row"' in r)
    lead = ("The score is PROVENANCE, not a verdict: it is a detection flag and "
            "has been measured to sit deep inside the clean distribution on a "
            "frame whose credit line is still legible at 1:1. Judge the pixels. "
            "Nothing here has been approved - candidates wait in the runtime dir.")
    return ("<!doctype html><meta charset=utf-8>"
            f"<title>LW cleaning review - {html.escape(title)}</title>"
            f"<style>{CSS}</style>"
            f"<h1>LW cleaning review - {html.escape(title)} "
            f"({shown} of {len(slugs)} with a candidate)</h1>"
            f'<p class="lead">{lead}</p>' + "".join(rows))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_review")
    ap.add_argument("--slugs", required=True, help="file with one slug per line")
    ap.add_argument("--title", default="cleaning QA lane")
    ap.add_argument("--runtime", default=RUNTIME)
    ap.add_argument("--out", default=None, help="output html (default <runtime>/review.html)")
    args = ap.parse_args(argv)

    with open(args.slugs, encoding="utf-8") as f:
        slugs = [ln.strip() for ln in f if ln.strip()]
    out = args.out or os.path.join(args.runtime, "review.html")
    prefix = os.path.relpath(args.runtime, os.path.dirname(os.path.abspath(out)))
    page = build_page(slugs, args.title, args.runtime, prefix.replace(os.sep, '/'))
    tmp = out + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    os.replace(tmp, out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
