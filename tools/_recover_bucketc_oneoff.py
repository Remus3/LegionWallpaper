"""One-off: run the FREE recovery tiers (Tier-0 local pHash + Tier-1 DeviantArt
oEmbed liveness) over the 8 bucket-C held first-pass slugs. No SauceNAO (quota),
no gallery-dl fetch - this is the read-only probe that tells us, per slug:
  - Tier 0: is there a higher-res local twin in Pictures + Desktop/Found?
  - Tier 1: is the DeviantArt deviation alive, and what are its TRUE dims
            (so we know whether an original=true 4K fetch could reach >= 2560w)?
Reports a table; the escalation/reject decision falls out of it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lw_recover as R  # noqa: E402
from lw_recover_campaign import build_corpus_hashes  # noqa: E402

SCRATCH = Path("images/1.First Pass Scratch")
CORPUS_DIRS = [r"C:\Users\Administrator\Pictures",
               r"C:\Users\Administrator\Desktop\Found"]
CACHE = "data/recovery/hashes.json"
SLUGS = [
    "darius-the-hand-of-noxus-by-vexxsoul-dm8cizj-pre",
    "fantasy-design-by-aivio-dkdq5p7-pre",
    "fury-tempest-sona-by-ryoairtist-dm7ziam-pre",
    "victorious-syndra-by-syndraislove-dkas1c7-pre",
    "inkshadow-yone-league-of-legends-by-penbedenizz-dmccsav-fullview",
    "ashe-league-of-legends-by-nortonki-dmc2wmf-fullview",
    "mfortune1",
    "wp11960522-league-of-legends-vayne-wallpapers",
]


def main():
    print("hashing corpus (cached)...", flush=True)
    corpus = build_corpus_hashes(CORPUS_DIRS, CACHE)
    print(f"corpus entries: {len(corpus)}\n", flush=True)
    print(f"{'slug':52} {'t0':>10} {'t1':>6} {'devdims':>12}")
    for slug in SLUGS:
        d = SCRATCH / slug
        src = next(iter(d.glob(f"{slug}_firstinitial.*")), None)
        man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        name = man.get("original_filename") or slug
        if src is None:
            print(f"{slug:52} {'NO-SRC':>10}")
            continue
        h = R.compute_hashes(str(src))
        target = {"phash": h["phash"], "dhash": h["dhash"],
                  "name": name, "path": str(src)}
        t0 = R.consensus_match(target, corpus, accept=8, review=14)
        t0s = t0["decision"]
        did = R.decode_deviation_token(name)
        t1 = "-"
        dims = "-"
        if did is not None:
            live = R.oembed_liveness(did, artist=R.parse_artist(name))
            # Report the module's own verdict rather than a local label: oEmbed
            # can confirm life but never refute it, so a non-alive result is
            # inconclusive, not dead.
            t1 = live.get("verdict", "unknown")
            if live.get("alive"):
                dims = f"{live.get('width')}x{live.get('height')}"
        else:
            t1 = "no-tok"
        extra = ""
        if t0s == "match":
            extra = " -> " + str(t0.get("source"))
        print(f"{slug:52} {t0s:>10} {t1:>16} {dims:>12}{extra}")


if __name__ == "__main__":
    main()
