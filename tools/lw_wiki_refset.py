"""Legion Wallpaper - pull a canonical reference set from the LoL wiki.

WHAT AND WHY. lw-gen's open direction (ADR-011) is more-real faces on the
animagine base without the uncanny register, and the ruling that got us there
was blunt about the failure mode: CLIP corpus similarity ranked the two WORST
bases first because it reads rendering register and is blind to hands, weapon
canon and likeness. Those are exactly the axes a human judges, and judging them
needs canon reference to judge AGAINST. This pulls it.

Two complementary axes per champion:

  * `render`  - the isolated figure on transparency. Anatomy, silhouette,
                proportion and pose with no background to hide behind.
  * `splash`  - the HD splash original (5000-7000px). Pose in composition,
                the corpus's colour register, and face detail at real
                resolution rather than at wallpaper downscale.

SOURCE. wiki.leagueoflegends.com (wiki.gg) Action API, direct - settled by
LEDGER 72 after both candidate MediaWiki MCP servers were measured to wrap this
same anonymous API and buy no capability. wiki.gg needs no `?format=original`;
that rule is Fandom's. The API-declared sha1 is deliberately NOT asserted
against the bytes, because no host serves bytes matching it - provenance records
the sha256 of what actually arrived.

BOUNDARY. This writes ONLY under `data/reference/`, which is gitignored. The
repo is public and the bytes are third-party art: the process is the deliverable,
the art never is. Nothing here touches pipeline state.

Import discipline: stdlib + PIL only. The API call and the byte fetch are both
injectable so the whole module is testable offline.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

WIKI = "https://wiki.leagueoflegends.com/en-us/api.php"
UA = "lw_wiki_refset/1.0 (Legion Wallpaper; canonical reference set)"

# The Action API caps titles per query at 50 for anonymous callers and silently
# TRUNCATES past it rather than erroring, so a batch that ignores this loses
# rows without saying so.
TITLES_PER_QUERY = 50

# Courtesy delay between byte fetches. These are multi-MB originals off a
# community wiki; there is no rush and no reason to hammer it.
FETCH_DELAY_S = 0.35

RENDER_SUFFIX = " Render.png"
_WIN_RESERVED = re.compile(r'[<>:"/\\|?*]')


# ---------------------------------------------------------------------------
# title grammar
# ---------------------------------------------------------------------------
def render_title(champion: str) -> str:
    return f"File:{champion}{RENDER_SUFFIX}"


def splash_title(champion: str, skin: str = "Original", hd: bool = True) -> str:
    """`File:<Champ> <Skin>Skin HD.jpg`, or the standard file when hd=False.

    The HD upload is a SEPARATE title, not a parameter on the standard one -
    `Ahri OriginalSkin.jpg` is 1215x717 while `Ahri OriginalSkin HD.jpg` is
    6000x3524. Confusing them silently costs a factor of five in resolution.
    """
    tail = "Skin HD.jpg" if hd else "Skin.jpg"
    return f"File:{champion} {skin}{tail}"


def champion_from_render(name: str):
    """Champion name from a render filename, or None if it is not a render.

    Deliberately set-blind: it parses, it does not judge. Whether
    `Aatrox Winged` is a champion or a variant is unknowable from this one
    string, since `Nunu & Willump` and `Dr. Mundo` are equally multi-token and
    equally real. build_plan makes that call, because it can see the set.
    """
    if name.startswith("File:"):
        name = name[len("File:"):]
    if not name.endswith(RENDER_SUFFIX):
        return None
    champ = name[: -len(RENDER_SUFFIX)].strip()
    return champ or None


ORIGINAL_SUFFIX = " OriginalSkin.jpg"


def champion_from_original_skin(name: str):
    """Champion name from `<Champ> OriginalSkin.jpg`, else None.

    This is the champion universe, and it is chosen over the render category
    for two measured reasons. It is COMPLETE - `Kayle Render.png` exists but is
    not in `Category:Champion renders`, so a render-derived universe lost Kayle
    outright. And it is UNAMBIGUOUS - the suffix is fixed, so the prefix is the
    full name however many tokens it has, and no variant render, form or
    placeholder has an OriginalSkin file to leak in with.
    """
    if name.startswith("File:"):
        name = name[len("File:"):]
    if not name.endswith(ORIGINAL_SUFFIX):
        return None
    champ = name[: -len(ORIGINAL_SUFFIX)].strip()
    return champ or None


def build_universe(skin_file_names):
    """Sorted champion list from a `Category:Champion skins` listing."""
    return sorted({c for c in (champion_from_original_skin(n)
                               for n in skin_file_names) if c})


def dest_path(root: Path, kind: str, champion: str, skin, ext: str) -> Path:
    """Windows-safe path under `root/kind/`.

    Champion names are wiki text: they carry apostrophes (Kai'Sa), ampersands
    (Nunu & Willump) and periods (Dr. Mundo). The period must survive - dropping
    it renames the champion - while the reserved set must not reach the
    filesystem at all.
    """
    safe = champion.replace("&", "and").replace("'", "")
    safe = _WIN_RESERVED.sub("", safe)
    safe = "_".join(safe.split())
    stem = f"{safe}_{skin}" if skin else safe
    return Path(root) / kind / f"{stem}{ext}"


def build_plan(render_names):
    """One row per render-bearing name, pairing it with its HD original splash.

    No variant filtering here. A name-shape heuristic cannot do it: `Aatrox
    Winged` is a variant, `Nunu & Willump` and `Dr. Mundo` are champions, and
    `Kayle Aflame` is a FORM - all multi-token, all indistinguishable by shape.
    An earlier attempt that dropped a name whose prefix also had a render got
    `Nunu & Willump` exactly backwards, keeping legacy `Nunu` instead.
    `filter_to_resolvable` settles it with the wiki's own data instead.
    """
    champs = sorted({c for c in (champion_from_render(n) for n in render_names) if c})
    return [{"champion": c,
             "render_title": render_title(c),
             "splash_title": splash_title(c)} for c in champs]


def plan_for_champions(champions):
    """Plan rows straight from a champion list (the OriginalSkin universe)."""
    return [{"champion": c,
             "render_title": render_title(c),
             "splash_title": splash_title(c)} for c in champions]


def filter_to_resolvable(plan, info):
    """Keep the rows the wiki actually has a splash for; report the rest.

    This is the variant filter, and it is the wiki's answer rather than my
    guess: a real champion has a splash under `<Name> OriginalSkin[ HD].jpg`,
    while `Aatrox Winged` and `Kayle Aflame` have none because they are a
    variant render and a form. Returns (kept, dropped).
    """
    kept, dropped = [], []
    for row in plan:
        std = splash_title(row["champion"], hd=False)
        if info.get(row["splash_title"]) is not None:
            kept.append({**row, "resolved_splash": row["splash_title"], "hd": True})
        elif info.get(std) is not None:
            kept.append({**row, "resolved_splash": std, "hd": False})
        else:
            dropped.append(row["champion"])
    return kept, dropped


# ---------------------------------------------------------------------------
# network (both injectable)
# ---------------------------------------------------------------------------
def _default_api(**params):
    params.setdefault("format", "json")
    url = WIKI + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _default_fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def resolve_titles(titles, api=None):
    """{title: imageinfo-or-None} for every requested title.

    A missing file maps to None rather than being dropped, so the caller can
    tell "the wiki does not have it" from "I forgot to ask" - the exact
    distinction MCP_LIFT_P3 calls the failure mode to avoid. Batched to
    TITLES_PER_QUERY because the API truncates silently past its cap.
    """
    api = api or _default_api
    out = {t: None for t in titles}
    for i in range(0, len(titles), TITLES_PER_QUERY):
        chunk = titles[i:i + TITLES_PER_QUERY]
        js = api(action="query", titles="|".join(chunk),
                 prop="imageinfo", iiprop="url|size|dimensions|mime|sha1")
        for _, pg in (js.get("query", {}).get("pages", {}) or {}).items():
            ii = (pg.get("imageinfo") or [None])[0]
            if ii is not None:
                out[pg["title"]] = ii
    return out


def category_files(category, api=None, limit=None):
    """Every file title in a category, following continuation."""
    api = api or _default_api
    names, cont = [], None
    while True:
        params = dict(action="query", list="categorymembers",
                      cmtitle=f"Category:{category}", cmtype="file", cmlimit=500)
        if cont:
            params["cmcontinue"] = cont
        js = api(**params)
        names += [m["title"] for m in js.get("query", {}).get("categorymembers", [])]
        if limit and len(names) >= limit:
            return names[:limit]
        cont = (js.get("continue") or {}).get("cmcontinue")
        if not cont:
            return names


def save_verified(body, path: Path):
    """Decode before writing, then write atomically.

    Decoding first is not ceremony: a truncated download and a full disk both
    produce a file that exists and is wrong, and this box has run out of disk
    before (memory `reference-legion-disk-full-claude-temp`).
    """
    from PIL import Image
    with Image.open(io.BytesIO(body)) as im:
        im.load()
        w, h = im.size
        fmt = im.format
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(body)
    os.replace(tmp, path)
    return {"width": w, "height": h, "format": fmt, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest()}


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="lw_wiki_refset",
        description="Pull canonical LoL wiki renders + HD splashes as generator reference")
    p.add_argument("--out", default=r"C:\LegionWallpaper\data\reference\wiki")
    p.add_argument("--limit", type=int, help="cap the number of champions")
    p.add_argument("--kinds", default="render,splash",
                   help="comma list: render, splash")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)

    kinds = [k.strip() for k in a.kinds.split(",") if k.strip()]
    root = Path(a.out)
    print("enumerating Category:Champion skins ...", flush=True)
    champs = build_universe(category_files("Champion skins"))
    plan = plan_for_champions(champs)
    print(f"champions: {len(plan)}", flush=True)

    # Resolve the HD splash for every candidate, then the standard splash for
    # whatever has no HD. Both rounds feed the same evidence-based filter.
    info = resolve_titles([r["render_title"] for r in plan]
                          + [r["splash_title"] for r in plan])
    fallbacks = [splash_title(r["champion"], hd=False)
                 for r in plan if info.get(r["splash_title"]) is None]
    if fallbacks:
        print(f"no HD for {len(fallbacks)}, trying the standard splash", flush=True)
        info.update(resolve_titles(fallbacks))

    plan, dropped = filter_to_resolvable(plan, info)
    if dropped:
        print(f"dropped {len(dropped)} non-champions (variant renders + forms): "
              f"{', '.join(sorted(dropped))}", flush=True)
    if a.limit:
        plan = plan[:a.limit]

    need = []
    for r in plan:
        if "render" in kinds:
            need.append(r["render_title"])
        if "splash" in kinds:
            need.append(r["resolved_splash"])
    total = sum(info[t]["size"] for t in need if info.get(t))
    have = sum(1 for t in need if info.get(t))
    print(f"champions kept: {len(plan)} | files: {have}/{len(need)} | "
          f"{total/2**30:.2f} GB", flush=True)
    if a.dry_run:
        print(json.dumps({"champions": len(plan), "files": have, "bytes": total,
                          "no_hd": sum(1 for r in plan if not r["hd"]),
                          "dropped": sorted(dropped)}, indent=1))
        return 0

    prov, ok, miss = [], 0, 0
    for r in plan:
        for kind in kinds:
            if kind == "render":
                title, skin = r["render_title"], None
            else:
                title, skin = r["resolved_splash"], "Original"
            ii = info.get(title)
            if ii is None:
                miss += 1
                prov.append({"champion": r["champion"], "kind": kind,
                             "title": title, "status": "missing"})
                continue
            ext = os.path.splitext(urllib.parse.urlparse(ii["url"]).path)[1] or ".jpg"
            out = dest_path(root, kind, r["champion"], skin, ext)
            if out.exists():
                ok += 1
                continue
            try:
                meta = save_verified(_default_fetch(ii["url"]), out)
            except Exception as exc:  # noqa: BLE001 - degrade, record, continue
                miss += 1
                prov.append({"champion": r["champion"], "kind": kind, "title": title,
                             "status": f"failed: {type(exc).__name__}"})
                continue
            ok += 1
            prov.append({"champion": r["champion"], "kind": kind, "title": title,
                         "status": "ok", "source_url": ii["url"],
                         "declared_sha1": ii.get("sha1"), **meta,
                         "path": str(out)})
            print(f"  {r['champion'][:22]:24} {kind:7} {meta['width']}x{meta['height']}"
                  f" {meta['bytes']/1e6:6.2f} MB", flush=True)
            time.sleep(FETCH_DELAY_S)

    root.mkdir(parents=True, exist_ok=True)
    ppath = root / "provenance.json"
    tmp = ppath.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(prov, indent=1), encoding="utf-8")
    os.replace(tmp, ppath)
    print(f"\nLW WIKI REFSET | champions={len(plan)} saved={ok} missing={miss} "
          f"| out={root} | provenance={ppath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
