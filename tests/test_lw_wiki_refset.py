"""Tests for tools/lw_wiki_refset.py - the canonical wiki reference-set puller.

CI constraint: system python 3.14 and CI 3.12 with ONLY PIL + numpy + stdlib.
No network here, ever - the API and the byte fetch are injected, so every test
runs offline. What is asserted is the part that actually breaks: title grammar,
champion-name parsing (the wiki's names carry apostrophes, ampersands, spaces
and periods), Windows-safe destination paths, and the HD-missing fallback.

Written test-first per CLAUDE.md TDD.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import lw_wiki_refset as RS  # noqa: E402


# ---------------------------------------------------------------------------
# title grammar
# ---------------------------------------------------------------------------
def test_render_title_grammar():
    assert RS.render_title("Ahri") == "File:Ahri Render.png"
    assert RS.render_title("Kai'Sa") == "File:Kai'Sa Render.png"


def test_splash_title_grammar_defaults_to_the_hd_original():
    assert RS.splash_title("Ahri") == "File:Ahri OriginalSkin HD.jpg"
    assert RS.splash_title("Irelia", "SpiritBlossom") == \
        "File:Irelia SpiritBlossomSkin HD.jpg"


def test_splash_title_without_hd_is_the_standard_file():
    """The non-HD fallback is a DIFFERENT title, not the same one downgraded."""
    assert RS.splash_title("Ahri", hd=False) == "File:Ahri OriginalSkin.jpg"


# ---------------------------------------------------------------------------
# parsing what the category listing returns
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,expected", [
    ("File:Ahri Render.png", "Ahri"),
    ("File:Kai'Sa Render.png", "Kai'Sa"),
    ("File:Nunu & Willump Render.png", "Nunu & Willump"),
    ("File:Dr. Mundo Render.png", "Dr. Mundo"),
    ("Ahri Render.png", "Ahri"),               # allimages omits the namespace
])
def test_champion_from_render_handles_the_awkward_names(name, expected):
    assert RS.champion_from_render(name) == expected


def test_champion_from_render_parses_a_variant_without_judging_it():
    """Parsing is set-blind on purpose. Whether `Aatrox Winged` is a champion or
    a variant cannot be known from this one string - `Nunu & Willump` and
    `Dr. Mundo` are equally multi-token and equally real - so the judgement
    belongs to build_plan, which can see the whole set."""
    assert RS.champion_from_render("File:Aatrox Winged Render.png") == "Aatrox Winged"


def test_champion_from_render_rejects_a_non_render():
    assert RS.champion_from_render("File:Ahri OriginalSkin.jpg") is None


# ---------------------------------------------------------------------------
# destination paths - these land on Windows
# ---------------------------------------------------------------------------
def test_dest_path_is_windows_safe():
    """Apostrophes are legal on Windows but a colon or a slash is not, and a
    champion name is wiki text we do not control."""
    p = RS.dest_path(Path("/root"), "splash", "Kai'Sa", "Original", ".jpg")
    assert p.name == "KaiSa_Original.jpg"
    assert p.parent.name == "splash"


def test_dest_path_strips_every_reserved_character():
    p = RS.dest_path(Path("/root"), "render", 'Nunu & Willump', None, ".png")
    assert p.name == "Nunu_and_Willump.png"
    for bad in '<>:"/\\|?*':
        assert bad not in p.name


def test_dest_path_keeps_the_period_in_dr_mundo():
    """A period is legal and dropping it would silently rename the champion."""
    p = RS.dest_path(Path("/root"), "render", "Dr. Mundo", None, ".png")
    assert p.name == "Dr._Mundo.png"


# ---------------------------------------------------------------------------
# plan assembly + the HD fallback
# ---------------------------------------------------------------------------
def test_build_plan_pairs_render_and_splash_per_champion():
    plan = RS.build_plan(["File:Ahri Render.png", "File:Aatrox Render.png"])
    assert [r["champion"] for r in plan] == ["Aatrox", "Ahri"]   # sorted
    ahri = [r for r in plan if r["champion"] == "Ahri"][0]
    assert ahri["render_title"] == "File:Ahri Render.png"
    assert ahri["splash_title"] == "File:Ahri OriginalSkin HD.jpg"


@pytest.mark.parametrize("name,expected", [
    ("File:Ahri OriginalSkin.jpg", "Ahri"),
    ("File:Nunu & Willump OriginalSkin.jpg", "Nunu & Willump"),
    ("File:Dr. Mundo OriginalSkin.jpg", "Dr. Mundo"),
    ("Kayle OriginalSkin.jpg", "Kayle"),
])
def test_champion_from_original_skin(name, expected):
    """`<Champ> OriginalSkin.jpg` is the one unambiguous champion marker: the
    suffix is fixed, so the prefix is the whole name however many tokens it has.
    """
    assert RS.champion_from_original_skin(name) == expected


@pytest.mark.parametrize("name", [
    "File:Aatrox BloodMoonSkin.jpg",          # a non-Original skin
    "File:Aatrox Winged Render.png",          # a variant render
    "File:Kayle AflameSkin HD.jpg",           # a form
    "File:Ahri OriginalCentered.jpg",         # a different asset kind
    "File:Ahri OriginalSkin HD.jpg",          # the HD file, not the marker
])
def test_champion_from_original_skin_rejects_everything_else(name):
    """This is what makes the universe clean - no variant, form or placeholder
    has an OriginalSkin file, so none can leak in."""
    assert RS.champion_from_original_skin(name) is None


def test_build_universe_is_complete_and_variant_free():
    """Kayle regression: she has no render in Category:Champion renders, so a
    render-derived universe lost her entirely while still carrying four of her
    forms. The OriginalSkin universe has the opposite and correct behaviour."""
    members = ["File:Ahri OriginalSkin.jpg", "File:Kayle OriginalSkin.jpg",
               "File:Aatrox OriginalSkin.jpg", "File:Aatrox BloodMoonSkin.jpg",
               "File:Kayle AflameSkin.jpg", "File:Nunu & Willump OriginalSkin.jpg"]
    assert RS.build_universe(members) == [
        "Aatrox", "Ahri", "Kayle", "Nunu & Willump"]


def test_build_plan_keeps_every_render_name_including_multi_token_ones():
    """build_plan pairs, it does not judge - filtering is filter_to_resolvable's
    job, using the wiki's data rather than the shape of the name."""
    plan = RS.build_plan(["File:Nunu & Willump Render.png",
                          "File:Dr. Mundo Render.png",
                          "File:Aatrox Winged Render.png",
                          "File:Ahri Render.png"])
    assert [r["champion"] for r in plan] == [
        "Aatrox Winged", "Ahri", "Dr. Mundo", "Nunu & Willump"]


def test_filter_to_resolvable_drops_variants_and_forms_by_evidence():
    """A real champion has a splash; a variant render and a form do not.

    This is the regression for a heuristic that got `Nunu & Willump` backwards:
    it dropped the champion because legacy `Nunu` also has a render, then failed
    the splash lookup for the name it kept.
    """
    plan = RS.build_plan(["File:Nunu Render.png",
                          "File:Nunu & Willump Render.png",
                          "File:Aatrox Winged Render.png",
                          "File:Kayle Aflame Render.png",
                          "File:Ahri Render.png"])
    info = {
        "File:Ahri OriginalSkin HD.jpg": {"url": "u", "size": 1},
        "File:Nunu & Willump OriginalSkin HD.jpg": {"url": "u", "size": 1},
        # legacy Nunu, the variant and the form have no splash of their own
    }
    kept, dropped = RS.filter_to_resolvable(plan, info)
    assert [r["champion"] for r in kept] == ["Ahri", "Nunu & Willump"]
    assert set(dropped) == {"Nunu", "Aatrox Winged", "Kayle Aflame"}
    assert all(r["hd"] for r in kept)


def test_filter_to_resolvable_falls_back_to_the_standard_splash():
    """No HD upload must mean standard-resolution, never dropped."""
    plan = RS.build_plan(["File:Norra Render.png"])
    info = {"File:Norra OriginalSkin.jpg": {"url": "u", "size": 1}}
    kept, dropped = RS.filter_to_resolvable(plan, info)
    assert dropped == []
    assert kept[0]["resolved_splash"] == "File:Norra OriginalSkin.jpg"
    assert kept[0]["hd"] is False


def test_resolve_falls_back_when_the_hd_file_is_absent():
    """A champion with no HD upload must still yield its standard splash, not
    be silently skipped - a 0 from a name guess is the failure mode to avoid
    (docs/MCP_LIFT_P3_2026-08-01.md)."""
    def fake_api(**params):
        titles = params["titles"].split("|")
        pages = {}
        for i, t in enumerate(titles):
            if t.endswith("HD.jpg"):
                pages[str(-i - 1)] = {"title": t, "missing": ""}
            else:
                pages[str(i + 1)] = {
                    "title": t, "imageinfo": [
                        {"url": "https://x/" + t, "width": 1215, "height": 717,
                         "size": 140000, "mime": "image/jpeg"}]}
        return {"query": {"pages": pages}}

    got = RS.resolve_titles(["File:Ahri OriginalSkin HD.jpg"], api=fake_api)
    assert got["File:Ahri OriginalSkin HD.jpg"] is None

    got2 = RS.resolve_titles(["File:Ahri OriginalSkin.jpg"], api=fake_api)
    assert got2["File:Ahri OriginalSkin.jpg"]["width"] == 1215


def test_resolve_titles_batches_within_the_api_limit():
    """The API caps titles per query; exceeding it silently truncates."""
    seen = []

    def fake_api(**params):
        n = len(params["titles"].split("|"))
        seen.append(n)
        return {"query": {"pages": {}}}

    RS.resolve_titles([f"File:C{i} Render.png" for i in range(120)], api=fake_api)
    assert seen, "no api call was made"
    assert max(seen) <= RS.TITLES_PER_QUERY
    assert sum(seen) == 120
