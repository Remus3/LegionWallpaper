"""One-off: hand-crop the 4 viable held first-pass slugs to exact 16:9.

Operator ruling 2026-07-07 (crop-held NEXT, bucket A+B): center-crop these 4 to
16:9 (they have the source pixels), clear the aspect HOLD, then re-run the
first-pass driver so they re-enter the needauth queue for crop QA. The 8
sub-resolution held slugs (bucket C) are NOT touched here - they route to the
source-recovery waterfall separately.

Provenance-safe: backs up the original source, records a MANUAL_CROP transition
with old/new sha256 + the crop box, and neutralizes (does not delete) the prior
HOLD audit so slug_state() returns 'editing' instead of 'held'.
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
SLUGS = ["chengwei-pan-1", "chengwei-pan-2", "rey-jinn-up-2",
         "tina-wei-final-official"]
DRY = "--execute" not in sys.argv


def sha256_file(p):
    h = hashlib.sha256()
    h.update(Path(p).read_bytes())
    return h.hexdigest()


def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for slug in SLUGS:
        d = SCRATCH / slug
        src = d / f"{slug}_firstinitial.jpg"
        man_p = d / "manifest.json"
        with Image.open(src) as im:
            w, h = im.size
            cls, box, area_loss = aspect_class(w, h)
            print(f"{slug}: {w}x{h} cls={cls} loss={round(area_loss,4)} box={box}")
            if box is None:
                print("  already ~16:9, skipping crop")
                continue
            cropped = im.crop(box)
            cw, ch = cropped.size
            new_ratio = cw / ch
            print(f"  -> cropped {cw}x{ch} ratio={round(new_ratio,4)}")
            if DRY:
                continue
            # back up original, then overwrite the source with the 16:9 crop
            backup = d / f"{slug}_firstinitial_precrop.jpg"
            old_sha = sha256_file(src)
            backup.write_bytes(src.read_bytes())
            tmp = d / f"{slug}_firstinitial.jpg.tmp"
            cropped.save(tmp, "JPEG", quality=100, subsampling=0)
            tmp.replace(src)
        if DRY:
            continue
        new_sha = sha256_file(src)
        man = json.loads(man_p.read_text(encoding="utf-8"))
        # neutralize prior HOLD audits so slug_state() -> 'editing'
        for t in man.get("transitions", []):
            a = t.get("audit")
            if isinstance(a, dict) and a.get("hold"):
                a["hold_resolved"] = a.pop("hold")
        man.setdefault("transitions", []).append({
            "ts": ts, "op": "MANUAL_CROP", "actor": "operator",
            "tool": "_crop_held_oneoff", "params": {"crop_box": list(box),
            "src_dims": [w, h], "out_dims": [cw, ch],
            "area_loss": round(area_loss, 6)},
            "src": src.name, "dst": src.name,
            "sha256_in": old_sha, "sha256_out": new_sha,
            "note": "bucket A+B manual 16:9 center-crop; HOLD cleared",
            "audit": None})
        tmp = man_p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(man, indent=1), encoding="utf-8")
        tmp.replace(man_p)
        print("  committed crop + cleared hold")
    print("DRY-RUN (pass --execute to apply)" if DRY else "DONE")


if __name__ == "__main__":
    main()
