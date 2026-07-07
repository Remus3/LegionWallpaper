"""One-off: install the re-fetched DeviantArt originals as the crop sources for
the 3 bucket-C slugs whose scratch _firstinitial had degraded to an oEmbed-
preview-size file. Corrects the earlier crop that ran on the inferior 1095px
preview. For each: center-crop the fetched original to 16:9, overwrite
_firstinitial, drop the inferior precrop backup, append corrective provenance.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lw_first_pass import center_crop_box, aspect_class  # noqa: E402

SCRATCH = Path("images/1.First Pass Scratch")
FETCH_ROOT = Path("data/recovery/fetch_bucketc")
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
SLUGS = [
    "darius-the-hand-of-noxus-by-vexxsoul-dm8cizj-pre",
    "fantasy-design-by-aivio-dkdq5p7-pre",
    "fury-tempest-sona-by-ryoairtist-dm7ziam-pre",
]
DRY = "--execute" not in sys.argv


def largest(d):
    best, bpx = None, -1
    for p in Path(d).rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            try:
                with Image.open(p) as im:
                    px = im.size[0] * im.size[1]
            except Exception:  # noqa: BLE001 - skip unreadable, probe only
                continue
            if px > bpx:
                best, bpx = p, px
    return best


def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for slug in SLUGS:
        d = SCRATCH / slug
        orig = largest(FETCH_ROOT / slug)
        if orig is None:
            print(f"{slug}: NO fetched original, skip")
            continue
        with Image.open(orig) as im:
            im = im.convert("RGB")
            w, h = im.size
            cls, box, area_loss = aspect_class(w, h)
            box = box or (0, 0, w, h)
            cropped = im.crop(box)
            cw, ch = cropped.size
        up = round(2560 / cw, 3)
        print(f"{slug}: orig {w}x{h} -> crop {cw}x{ch} (upscale {up}x)")
        if DRY:
            continue
        dst = d / f"{slug}_firstinitial.jpg"
        old_sha = hashlib.sha256(dst.read_bytes()).hexdigest() if dst.exists() else None
        tmp = d / f"{slug}_firstinitial.jpg.tmp"
        cropped.save(tmp, "JPEG", quality=100, subsampling=0)
        tmp.replace(dst)
        # drop the inferior preview backup
        pre = d / f"{slug}_firstinitial_precrop.jpg"
        if pre.exists():
            pre.unlink()
        new_sha = hashlib.sha256(dst.read_bytes()).hexdigest()
        man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        man.setdefault("transitions", []).append({
            "ts": ts, "op": "SOURCE_RECOVER", "actor": "operator",
            "tool": "_install_fetched", "params": {"tier": 1,
            "source": str(orig), "orig_dims": [w, h], "crop_box": list(box),
            "out_dims": [cw, ch]},
            "src": orig.name, "dst": dst.name,
            "sha256_in": old_sha, "sha256_out": new_sha,
            "note": "gallery-dl original=true fetch; center-crop 16:9; corrects "
                    "the earlier crop on the degraded 1095px preview",
            "audit": None})
        tmp = d / "manifest.json.tmp"
        tmp.write_text(json.dumps(man, indent=1), encoding="utf-8")
        tmp.replace(d / "manifest.json")
        print("  installed + provenance appended")
    print("DRY (pass --execute)" if DRY else "DONE")


if __name__ == "__main__":
    main()
