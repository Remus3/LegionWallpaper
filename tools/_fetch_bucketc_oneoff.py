"""One-off: gallery-dl original=true fetch of the 6 alive bucket-C deviations
(operator-approved quota spend 2026-07-07). Fetches each true original to a
per-slug dir, reports the REAL dimensions + path. No source replacement / re-run
here - dims decide the per-slug path (re-run if usable, reject if still tiny).
"""
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lw_recover as R  # noqa: E402
from lw_recover_campaign import _assemble_config  # noqa: E402

SCRATCH = Path("images/1.First Pass Scratch")
FETCH_ROOT = Path("data/recovery/fetch_bucketc")
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
SLUGS = [
    "darius-the-hand-of-noxus-by-vexxsoul-dm8cizj-pre",
    "fantasy-design-by-aivio-dkdq5p7-pre",
    "fury-tempest-sona-by-ryoairtist-dm7ziam-pre",
    "victorious-syndra-by-syndraislove-dkas1c7-pre",
]


def largest_image(d: Path):
    best = None
    best_px = -1
    for p in d.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            try:
                with Image.open(p) as im:
                    px = im.size[0] * im.size[1]
                    dims = im.size
            except Exception:  # noqa: BLE001 - skip unreadable, probe only
                continue
            if px > best_px:
                best_px, best, best_dims = px, p, dims
    return (best, best_dims) if best else (None, None)


def main():
    cfg = _assemble_config()
    if "deviantart" not in cfg:
        print("DeviantArt NOT configured - abort")
        return
    FETCH_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"{'slug':52} {'status':>14} {'orig_dims':>14}  file")
    for slug in SLUGS:
        man = json.loads((SCRATCH / slug / "manifest.json").read_text(encoding="utf-8"))
        name = man.get("original_filename") or slug
        did = R.decode_deviation_token(name)
        if did is None:
            print(f"{slug:52} {'no_token':>14}")
            continue
        dest = FETCH_ROOT / slug
        dest.mkdir(exist_ok=True)
        res = R.gallery_dl_fetch(did, cfg, str(dest), original=True)
        if not res.get("ok"):
            print(f"{slug:52} {res.get('status'):>14}")
            continue
        f, dims = largest_image(dest)
        dstr = f"{dims[0]}x{dims[1]}" if dims else "-"
        print(f"{slug:52} {'fetched':>14} {dstr:>14}  {f}")


if __name__ == "__main__":
    main()
