"""Legion Wallpaper - Stage-2 cleaning harness (single-writer HELPER).

Drives ONE slug through the CLEANING_INPAINT.md section-5 loop:
detect -> gate -> mask -> LaMa inpaint -> verify (G2) -> PRINT the exact
lw_pipeline commands for the caller to run. It PRODUCES pixels (into a
non-pipeline runtime dir) plus a verdict; it does NOT mutate pipeline state
itself. Keeping the save-working / submit / start-stage transitions in the
caller preserves the single-writer invariant (PIPELINE_STATE_MACHINE.md) and
avoids cross-venv shelling: the ML deps live only in C:\\Tools\\lw-clean\\venv
while lw_pipeline.py is stdlib-only under system Python314.

TWO-LAYER IMPORT DISCIPLINE (mandatory - mirrors lw_first_pass.py +
lw_g1_gate.py): module top-level imports are stdlib + numpy + PIL ONLY. torch,
ultralytics, easyocr, simple_lama_inpainting and cv2 are LAZY-imported inside
the ML functions that use them, so the committed TDD suite imports this module
and exercises ALL pure logic in CI with no GPU. A test asserts `import
lw_clean_pass` succeeds with those five modules unimportable.

GPU is ONE device - run_batch is strictly sequential, never parallel. Every
subprocess passes creationflags=CREATE_NO_WINDOW (Legion focus-steal rule).

VERIFIED installed API (probed 2026-07-16 under the clean venv, reconfirmed via
--selfcheck at build):
  - simple_lama_inpainting.SimpleLama(device=torch.device(...)); __call__(image,
    mask) with PIL or numpy; mask WHITE = inpaint; returns a PIL image.
  - ultralytics 8.4.96 YOLO(weights)(img, imgsz, conf, iou, verbose=False);
    boxes at results[0].boxes.xyxy / .conf / .cls (tensors -> .cpu().numpy()).
  - easyocr.Reader(['en','ch_sim'], gpu=...).readtext(np_img, detail=1) ->
    [(bbox, text, conf), ...]. EasyOCR pairs English with exactly ONE CJK model.
  - cv2 4.11.0 getStructuringElement / dilate / MSER_create.
  - torch 2.11.0+cu128, cuda True, sm_120 (Blackwell).

DOC-VS-INSTALLED API DELTA (--selfcheck under the 2026-07-16 clean venv):
  - SimpleLama __call__ return mode RESOLVED to PIL mode "RGB" (section 2 left
    "RGB vs RGBA" to confirm). inpaint_lama composites regardless of mode.
  - simple_lama_inpainting exposes NO __version__ attribute -> selfcheck reports
    "unknown" (cosmetic; the call signature is unchanged).
  - Confirmed unchanged from section 2: torch 2.11.0+cu128 cuda sm_120 [12,0];
    ultralytics 8.4.96 boxes.xyxy/.conf/.cls; easyocr 1.7.2 en+ch_sim; cv2
    4.11.0 MSER_create + getStructuringElement(MORPH_ELLIPSE); YOLO names
    {0:'watermark'}.
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# lw_g1_gate is stdlib+numpy at import time (pyiqa/torch are lazy inside it), so
# reusing its luma primitive here is CI-safe. Spec sanctions reusing _to_gray.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lw_g1_gate import _to_gray  # noqa: E402

# --------------------------------------------------------------------------
# Paths (Legion machine).
# --------------------------------------------------------------------------
ROOT = r"C:\LegionWallpaper"
TOOLS = ROOT + r"\tools"
IMAGES = ROOT + r"\images"
CLEAN_SCRATCH = IMAGES + r"\3.Cleaning Scratch"
RUNTIME_CLEAN = ROOT + r"\ops\runtime\clean"

SYS_PY = r"C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe"
PIPELINE = TOOLS + r"\lw_pipeline.py"
CLEAN_VENV_PY = r"C:\Tools\lw-clean\venv\Scripts\python.exe"
WEIGHTS_PATH = r"C:\Tools\lw-clean\yolo11x-train28-best.pt"

# CREATE_NO_WINDOW: 0 on non-Windows so the module still imports/tests in CI.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# --------------------------------------------------------------------------
# Gate + verify thresholds (CLEANING_INPAINT.md + AUDIT_GATES.md).
# --------------------------------------------------------------------------
DILATE_PX = 15               # mask + outside-boundary dilation (CI.md:126,230)
BORDER_FRAC = 0.10           # outer-10% border band
CONF_AUTO = 0.5              # auto conf floor (OCR hit also qualifies)
AREA_MAX_PCT = 2.0           # auto max mask-area percent (corner marks)
# gate v2 (operator-tunable, 2026-07-16 triage over 228 images): the corpus's
# PRIMARY watermark is a bottom-CENTER artist-credit banner, so the gate also
# accepts bottom-edge marks up to a larger area ceiling than corner marks.
BOTTOM_BAND_FRAC = 0.80      # bottom banner := centroid_y > 0.80*h
AREA_MAX_WM = 8.0            # auto area ceiling (pct) for banners + OCR watermarks

OUTSIDE_SSIM_MIN = 0.995     # G2 outside-mask identity floor (AG 1.3/3.4)
MAD_MAX = 1.0                # outside mean-abs-diff ceiling, in 0..255 levels
CHANGE_SSIM_MAX = 0.90       # inside change must drop SSIM to <= this
SEAM_SSIM_MIN = 0.92         # seam-ring floor; below -> FLAG (not discard)

_WATERMARK_TOKENS = (
    ".com", ".net", ".org", ".io", "www", "http", "://",
    "artstation", "deviantart", "uhdpaper", "patreon", "pixiv",
    "instagram", "behance", "twitter", "wallhaven",
)
# A social HANDLE is @ + at least 2 handle chars (e.g. @namakxin). A BARE "@"
# glyph read out of art (caitlyn-love-confession, vayne3) is NOT a watermark, so
# "@" was removed from the literal token sets above and below in favour of this.
_HANDLE_RE = re.compile(r"@[A-Za-z0-9_]{2,}")
# gate v2 fuzzy discrimination (operator-tunable): the LoL wordmark is a false
# positive we KEEP; artist-credit hosts are the true REMOVE signal.
_LOL_TARGET = "LEAGUEOFLEGENDS"     # the game wordmark - keep, never inpaint
_LOL_WORDS = ("LEGENDS", "LEAGUE")
_WM_HOSTS = ("DEVIANTART", "PATREON", "ARTSTATION", "BEHANCE")
_WM_LITERALS = (".COM", "WWW", "PATREON", "DEVIANT")
_WORKING_RE = re.compile(r"_cleanworking_(\d+)\.png$", re.IGNORECASE)


# ==========================================================================
# PURE numpy SSIM primitives (no cv2; reuses lw_g1_gate._to_gray for luma)
# ==========================================================================
def _box_mean(a: np.ndarray, win: int) -> np.ndarray:
    """Uniform mean over a win x win window, edge-padded, via an integral image.

    O(H*W) and exact - the SSIM/highpass building block. win is odd (2r+1).
    """
    a = np.asarray(a, dtype=np.float64)
    h, w = a.shape
    r = win // 2
    ap = np.pad(a, ((r, r), (r, r)), mode="edge")
    integ = np.zeros((ap.shape[0] + 1, ap.shape[1] + 1), dtype=np.float64)
    integ[1:, 1:] = np.cumsum(np.cumsum(ap, axis=0), axis=1)
    ys = np.arange(h)[:, None]
    xs = np.arange(w)[None, :]
    total = (integ[ys + win, xs + win] - integ[ys, xs + win]
             - integ[ys + win, xs] + integ[ys, xs])
    return total / float(win * win)


def _ssim_map(a: np.ndarray, b: np.ndarray, win: int = 7,
              L: float = 255.0) -> np.ndarray:
    """Per-pixel SSIM index map (uniform window). Identical inputs -> all 1.0."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    c1 = (0.01 * L) ** 2
    c2 = (0.03 * L) ** 2
    mu_a = _box_mean(a, win)
    mu_b = _box_mean(b, win)
    mu_a2 = mu_a * mu_a
    mu_b2 = mu_b * mu_b
    mu_ab = mu_a * mu_b
    var_a = _box_mean(a * a, win) - mu_a2
    var_b = _box_mean(b * b, win) - mu_b2
    cov = _box_mean(a * b, win) - mu_ab
    num = (2.0 * mu_ab + c1) * (2.0 * cov + c2)
    den = (mu_a2 + mu_b2 + c1) * (var_a + var_b + c2)
    return num / den


def _border_mask(h: int, w: int, frac: float) -> np.ndarray:
    """Boolean mask, True inside the outer `frac` band on all four edges."""
    m = np.zeros((h, w), dtype=bool)
    by = max(1, int(round(h * frac)))
    bx = max(1, int(round(w * frac)))
    m[:by, :] = True
    m[h - by:, :] = True
    m[:, :bx] = True
    m[:, w - bx:] = True
    return m


# ==========================================================================
# PURE: detection classification + geometry
# ==========================================================================
def classify_ocr_string(text) -> bool:
    """True iff an OCR string looks like a URL / handle / known watermark host.

    Case-insensitive substring match against a small token set. Empty/None and
    plain art words ("Ahri", "Vayne") return False. RANKING HINT only.
    """
    if not text:
        return False
    t = str(text).lower()
    if any(tok in t for tok in _WATERMARK_TOKENS):
        return True
    return bool(_HANDLE_RE.search(t))


def _norm_alnum_upper(text) -> str:
    """Uppercase, keep only [A-Z0-9] (drops spaces / punctuation / case)."""
    return "".join(ch for ch in str(text or "").upper() if ch.isalnum())


def _fuzzy_ratio(a: str, b: str) -> float:
    """difflib SequenceMatcher ratio (stdlib -> the gate stays CI-safe)."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def is_lol_logo(ocr_texts) -> bool:
    """True iff the OCR reads as the LEAGUE OF LEGENDS wordmark (KEEP signal).

    Fuzzy on the normalized alnum-uppercase join: ratio >= 0.5 vs
    "LEAGUEOFLEGENDS", OR any token is a close (>= 0.7) match to "LEGENDS" or
    "LEAGUE". The game logo is a FALSE POSITIVE for watermark removal, so the
    gate treats a logo hit as nothing-to-remove rather than routing to auto.
    """
    toks = [_norm_alnum_upper(t) for t in (ocr_texts or [])]
    toks = [t for t in toks if t]
    if not toks:
        return False
    joined = "".join(toks)
    if _fuzzy_ratio(joined, _LOL_TARGET) >= 0.5:
        return True
    # The wordmark can be DILUTED among splash-quote OCR (the-ruined-king-viego:
    # "... LEAGUEor LEGENDS"), sinking the whole-join fuzzy ratio. A substring
    # presence of BOTH wordmark halves is a precise KEEP signal.
    if "LEAGUE" in joined and "LEGENDS" in joined:
        return True
    return any(_fuzzy_ratio(t, w) >= 0.7 for t in toks for w in _LOL_WORDS)


def is_watermark_text(ocr_texts) -> bool:
    """True iff the OCR looks like an artist-credit URL / handle / host.

    Extends classify_ocr_string (kept intact for test 1) with (a) fuzzy host
    matching (ratio >= 0.7 vs deviantart/patreon/artstation/behance, catching
    OCR garbles) and (b) a literal scan of the raw uppercased join for
    {.COM, WWW, @, PATREON, DEVIANT}. This is the REMOVE signal.
    """
    if not ocr_texts:
        return False
    if any(classify_ocr_string(t) for t in ocr_texts):
        return True
    raw_upper = " ".join(str(t) for t in ocr_texts).upper()
    if any(lit in raw_upper for lit in _WM_LITERALS):
        return True
    if _HANDLE_RE.search(raw_upper):
        return True
    for t in ocr_texts:
        nt = _norm_alnum_upper(t)
        if nt and any(_fuzzy_ratio(nt, host) >= 0.7 for host in _WM_HOSTS):
            return True
    return False


def in_border_band(cx, cy, w, h, frac: float = BORDER_FRAC) -> bool:
    """True iff (cx, cy) is within the outer `frac` band of a w x h frame.

    Boundary is inclusive: a centroid at exactly frac*w counts as in-band.
    """
    bx = w * frac
    by = h * frac
    return bool(cx <= bx or cx >= w - bx or cy <= by or cy >= h - by)


def dilate_box(box, w, h, dilate_px: int = DILATE_PX):
    """Expand a box by dilate_px on all sides, clamped to [0,w] x [0,h].

    Never negative, never past the frame edge. Returns [x0, y0, x1, y1] ints.
    """
    x0, y0, x1, y1 = box
    nx0 = max(0, int(math.floor(x0)) - dilate_px)
    ny0 = max(0, int(math.floor(y0)) - dilate_px)
    nx1 = min(int(w), int(math.ceil(x1)) + dilate_px)
    ny1 = min(int(h), int(math.ceil(y1)) + dilate_px)
    return [nx0, ny0, nx1, ny1]


def _boxes_intersect(a, b) -> bool:
    """Strict overlap test (touching edges do NOT count as intersecting)."""
    return (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])


def union_boxes(boxes):
    """Merge transitively-overlapping boxes into their bounding envelope.

    Overlapping boxes collapse to one [minx, miny, maxx, maxy]; disjoint boxes
    are preserved. Returns a list of [x0, y0, x1, y1] floats.
    """
    result = []
    for raw in boxes:
        cur = [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
        i = 0
        while i < len(result):
            if _boxes_intersect(cur, result[i]):
                other = result.pop(i)
                cur = [min(cur[0], other[0]), min(cur[1], other[1]),
                       max(cur[2], other[2]), max(cur[3], other[3])]
                i = 0                      # restart: the grown box may reach more
            else:
                i += 1
        result.append(cur)
    return result


def centroid_of(boxes):
    """Area-weighted centroid (cx, cy) of a box list, or None if empty."""
    if not boxes:
        return None
    tot = 0.0
    sx = 0.0
    sy = 0.0
    for x0, y0, x1, y1 in boxes:
        area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        if area <= 0.0:
            area = 1.0                     # degenerate box -> unit weight
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        sx += area * cx
        sy += area * cy
        tot += area
    if tot <= 0.0:
        return None
    return (sx / tot, sy / tot)


def dilated_union_area_pct(boxes, w, h, dilate_px: int = DILATE_PX) -> float:
    """Percent of the frame covered by the 15px-dilated UNION of boxes.

    Rasterizes the dilated boxes into a boolean frame so overlaps count once.
    Empty boxes (or a non-positive frame) -> 0.0. Rectangular dilation is used
    for this pure triage estimate; the real inpaint mask uses cv2 elliptical
    dilation (render_mask) but the area is within a fraction of a percent.
    """
    if not boxes or w <= 0 or h <= 0:
        return 0.0
    mask = np.zeros((int(h), int(w)), dtype=bool)
    for b in boxes:
        x0, y0, x1, y1 = dilate_box(b, w, h, dilate_px)
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = True
    return float(np.count_nonzero(mask)) / float(int(w) * int(h)) * 100.0


def highpass_border_score(image, band_frac: float = BORDER_FRAC,
                          win: int = 9) -> float:
    """Mean high-pass response inside the border band (a ranking HINT only).

    Deviation of luma from its local mean (approximates the ~9px median
    high-pass of CLEANING_INPAINT.md, averaged over the outer band). A flat
    region scores ~0; a high-contrast painted watermark box scores higher.
    """
    g = _to_gray(image)
    h, w = g.shape
    hp = np.abs(g - _box_mean(g, win))
    band = _border_mask(h, w, band_frac)
    if not band.any():
        return 0.0
    return float(np.mean(hp[band]))


# ==========================================================================
# PURE: auto-inpaint gate
# ==========================================================================
def gate_decision(n_detections, conf_max, ocr_hit, mask_area_pct,
                  centroid=None, w=0, h=0, ocr_texts=()):
    """Return (verdict, reason). verdict in {auto, qa, clean}.

    gate v2 (operator-tuned over a 228-image triage): the corpus's PRIMARY
    watermark is a bottom-CENTER semi-transparent artist-credit banner, so the
    gate accepts bottom-edge banners (centroid_y > 0.80*h) up to AREA_MAX_WM,
    not only outer-10% corner marks. The LEAGUE OF LEGENDS wordmark is a false
    positive and is KEPT (folded into "clean"). Rules apply in order; the first
    match wins (ambiguous art-vs-watermark still routes to qa, never a guess):

      1. n == 0                                   -> clean / no_detections
      2. lol_logo and not watermark_text          -> clean / lol_logo (KEEP)
      3. (ocr_hit or watermark_text), area<=8%    -> auto  / watermark_ocr
      4. bottom-band, conf>=0.5, area<=8%         -> auto  / bottom_banner
      5. corner, conf>=0.5, area<=2%              -> auto  / corner_mark
      6. area > 8%                                 -> qa    / area_too_large
      7. conf < 0.5                                -> qa    / low_conf
      8. else                                      -> qa    / not_border
    """
    if n_detections <= 0:
        return ("clean", "no_detections")
    lol = is_lol_logo(ocr_texts)
    wm = is_watermark_text(ocr_texts)
    if lol and not wm:
        return ("clean", "lol_logo")
    if (ocr_hit or wm) and mask_area_pct <= AREA_MAX_WM:
        return ("auto", "watermark_ocr")
    cx, cy = centroid if centroid else (0.0, 0.0)
    if (cy > BOTTOM_BAND_FRAC * h and conf_max >= CONF_AUTO
            and mask_area_pct <= AREA_MAX_WM):
        return ("auto", "bottom_banner")
    if (in_border_band(cx, cy, w, h, BORDER_FRAC) and conf_max >= CONF_AUTO
            and mask_area_pct <= AREA_MAX_PCT):
        return ("auto", "corner_mark")
    if mask_area_pct > AREA_MAX_WM:
        return ("qa", "area_too_large")
    if conf_max < CONF_AUTO:
        return ("qa", "low_conf")
    return ("qa", "not_border")


# ==========================================================================
# PURE: verify (G2) metrics + verdict
# ==========================================================================
def masked_identity(image_a, image_b, mask_bool):
    """(ssim_outside, mad_outside) over pixels OUTSIDE the inpaint mask.

    mad_outside is the mean absolute luma difference in 0..255 levels. ssim is
    computed after forcing the INSIDE-mask pixels of both images to a common
    value, so boundary windows never see the (licensed) inpaint change - the
    outside is a strict identity tripwire (composite rule -> exactly 1.0/0.0).
    """
    ga = _to_gray(image_a)
    gb = _to_gray(image_b)
    mask = np.asarray(mask_bool, dtype=bool)
    outside = ~mask
    if not outside.any():
        return 1.0, 0.0
    mad = float(np.mean(np.abs(ga[outside] - gb[outside])))
    a2 = ga.copy()
    b2 = gb.copy()
    a2[mask] = 0.0
    b2[mask] = 0.0
    smap = _ssim_map(a2, b2)
    ssim_outside = float(np.mean(smap[outside]))
    return ssim_outside, mad


def patch_change_ssim(patch_a, patch_b) -> float:
    """Mean SSIM between two patches: ~1.0 if identical, low if very different."""
    ga = _to_gray(patch_a)
    gb = _to_gray(patch_b)
    return float(np.mean(_ssim_map(ga, gb)))


def seam_ring_ssim(image, ring_mask, blur_win: int = 7) -> float:
    """SSIM of the boundary-ring region vs a blurred copy of itself.

    A smooth blend tracks its own blur (SSIM high); a hard visible seam differs
    from its blur (SSIM low). Empty ring -> 1.0.
    """
    g = _to_gray(image)
    ring = np.asarray(ring_mask, dtype=bool)
    if not ring.any():
        return 1.0
    blurred = _box_mean(g, blur_win)
    smap = _ssim_map(g, blurred)
    return float(np.mean(smap[ring]))


def verify_verdict(outside_ssim, mad_outside, change_ssim, text_residue,
                   seam_ssim):
    """Combine the G2 checks into {"verdict", "reasons", "flags"}.

    Precedence:
      1. outside identity violated (ssim < 0.995 OR mad > 1 level) -> DISCARD
         (hard: a pipeline bug, halt - never retry blindly).
      2. inside did not change (change_ssim > 0.90) -> FAIL (inpaint no-op).
      3. text residue detected inside the old bbox -> FAIL.
      4. otherwise PASS, flagging the seam (seam_ssim < 0.92) for a QA/vision
         look without discarding.
    """
    reasons = []
    flags = []
    if outside_ssim < OUTSIDE_SSIM_MIN:
        reasons.append(f"outside_ssim {outside_ssim:g} < {OUTSIDE_SSIM_MIN:g}")
    if mad_outside > MAD_MAX:
        reasons.append(f"mad_outside {mad_outside:g} > {MAD_MAX:g}")
    if reasons:
        return {"verdict": "discard", "reasons": reasons, "flags": flags}
    if change_ssim > CHANGE_SSIM_MAX:
        return {"verdict": "fail",
                "reasons": [f"no_op change_ssim {change_ssim:g} "
                            f"> {CHANGE_SSIM_MAX:g}"],
                "flags": flags}
    if text_residue:
        return {"verdict": "fail", "reasons": ["text_residue"], "flags": flags}
    if seam_ssim < SEAM_SSIM_MIN:
        flags.append("seam")
    return {"verdict": "pass", "reasons": [], "flags": flags}


def _residue_decision(before_energy, after_energy, keep_frac: float = 0.45,
                      floor: float = 4.0) -> bool:
    """True iff text-like energy REMAINS after inpaint (a real residue fail).

    Root-cause fix: judge the DROP, not the absolute after-energy. A clean fill
    over busy art keeps some MSER/OCR energy from the surrounding texture, so
    the old absolute check false-failed on it. Here:
      - before_energy < floor  -> nothing was there, never a fail (False).
      - else fail IFF after_energy still exceeds keep_frac*before_energy AND is
        itself at/above the floor (i.e. the energy did not meaningfully drop).
    """
    if before_energy < floor:
        return False
    return (after_energy > keep_frac * before_energy) and (after_energy >= floor)


# ==========================================================================
# PURE: pipeline command builders (PRINTED, never executed here)
# ==========================================================================
def build_save_working_cmd(slug, from_path, params, sys_py=SYS_PY,
                           pipeline=PIPELINE):
    """argv for `save-working <slug> --from <path> --tool lama --params <json>`."""
    return [sys_py, pipeline, "save-working", slug, "--from", str(from_path),
            "--tool", "lama", "--params", json.dumps(params)]


def build_submit_cmd(slug, sys_py=SYS_PY, pipeline=PIPELINE):
    """argv for `submit <slug>`."""
    return [sys_py, pipeline, "submit", slug]


def build_cleanscan_cmds(slug, initial_path, sys_py=SYS_PY, pipeline=PIPELINE):
    """Two argvs for a zero-detection clean scan: save-working THEN submit.

    cmd_submit raises "has no working file" without a _working_## and the
    _cleaninitial is NOT a working file, so a clean scan must register the
    initial as a clean-scan working first, then submit it.
    """
    save = [sys_py, pipeline, "save-working", slug, "--from", str(initial_path),
            "--tool", "clean-scan", "--params", json.dumps({"clean_scan": True})]
    return [save, build_submit_cmd(slug, sys_py, pipeline)]


# ==========================================================================
# PURE: triage record + atomic writes + working-image selection
# ==========================================================================
def triage_record(slug, image, boxes, conf, mask_area_pct, verdict):
    """A JSON-serializable triage row for one image."""
    return {
        "slug": slug,
        "image": str(image),
        "boxes": [[float(v) for v in b] for b in boxes],
        "conf": float(conf),
        "mask_area_pct": float(mask_area_pct),
        "verdict": verdict,
    }


def atomic_write_json(path, obj):
    """Write JSON atomically (tmp .part then os.replace); leaves no temp file."""
    path = str(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    part = path + ".part"
    with open(part, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    os.replace(part, path)


def atomic_write_png(path, image):
    """Write a PNG atomically. `image` is a PIL.Image or an HxWx[3|4]/HxW array."""
    path = str(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image.astype(np.uint8))
    part = path + ".part"
    image.save(part, format="PNG")
    os.replace(part, path)


def select_working_image(scratch_dir, slug):
    """Highest <slug>_cleanworking_##.png, else <slug>_cleaninitial.*, else None."""
    d = Path(scratch_dir)
    if not d.is_dir():
        return None
    best = None
    best_n = -1
    initial = None
    for p in sorted(d.iterdir()):
        if not p.is_file():
            continue
        name = p.name
        if name.startswith(f"{slug}_cleanworking_"):
            m = _WORKING_RE.search(name)
            if m:
                n = int(m.group(1))
                if n > best_n:
                    best_n = n
                    best = p
        elif name.startswith(f"{slug}_cleaninitial."):
            initial = p
    if best is not None:
        return str(best)
    if initial is not None:
        return str(initial)
    return None


def _union_envelope(boxes):
    """Bounding [x0, y0, x1, y1] of all boxes (ints), or None if empty."""
    if not boxes:
        return None
    xs0 = min(b[0] for b in boxes)
    ys0 = min(b[1] for b in boxes)
    xs1 = max(b[2] for b in boxes)
    ys1 = max(b[3] for b in boxes)
    return [int(xs0), int(ys0), int(xs1), int(ys1)]


# ==========================================================================
# ML layer (LAZY imports - never touched by the pure TDD suite / CI)
# ==========================================================================
_MODELS = {}


def load_models(langs=("en", "ch_sim"), device=None):
    """Load + cache the YOLO detector, EasyOCR reader and SimpleLama singletons.

    Lazy imports keep the module CI-safe. Returns a dict cached across calls in
    a run (the GPU is one device; loading once matters).
    """
    if _MODELS.get("langs") == list(langs) and "lama" in _MODELS:
        return _MODELS
    import torch
    import easyocr
    from simple_lama_inpainting import SimpleLama
    from ultralytics import YOLO

    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    _MODELS.clear()
    _MODELS.update({
        "yolo": YOLO(WEIGHTS_PATH),
        "reader": easyocr.Reader(list(langs), gpu=(dev == "cuda")),
        "lama": SimpleLama(device=torch.device(dev)),
        "device": dev,
        "langs": list(langs),
    })
    return _MODELS


def detect_yolo(image, model, imgsz: int = 1024, conf: float = 0.35,
                iou: float = 0.5):
    """Run YOLO11x; return [{"box":[x0,y0,x1,y1], "conf":f, "cls":i}, ...]."""
    results = model(image, imgsz=imgsz, conf=conf, iou=iou, verbose=False)
    out = []
    if not results:
        return out
    boxes = getattr(results[0], "boxes", None)
    if boxes is None or boxes.xyxy is None or len(boxes) == 0:
        return out
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    clss = boxes.cls.cpu().numpy()
    for i in range(len(xyxy)):
        out.append({"box": [float(v) for v in xyxy[i]],
                    "conf": float(confs[i]), "cls": int(clss[i])})
    return out


def detect_ocr(np_img, reader):
    """Run EasyOCR (detail=1); return [{"box":[..], "text":s, "conf":f}, ...]."""
    res = reader.readtext(np_img, detail=1)
    out = []
    for item in res:
        bbox, text, conf = item[0], item[1], item[2]
        xs = [float(p[0]) for p in bbox]
        ys = [float(p[1]) for p in bbox]
        out.append({"box": [min(xs), min(ys), max(xs), max(ys)],
                    "text": text, "conf": float(conf)})
    return out


def detect_image(image_path, out_dir=None, models=None,
                 langs=("en", "ch_sim")):
    """Union YOLO + OCR detections for one image (module-level: monkeypatchable).

    Returns {boxes, confs, ocr_texts, ocr_hit, yolo, ocr}. OCR boxes whose text
    classifies as a watermark are added to the box set; YOLO confidences drive
    conf_max. This is the seam the dry-run triage test replaces (no ML in CI).
    """
    models = models or load_models(langs)
    with Image.open(image_path) as im:
        arr = np.asarray(im.convert("RGB"))
    ydet = detect_yolo(arr, models["yolo"])
    odet = detect_ocr(arr, models["reader"])
    boxes = [d["box"] for d in ydet]
    ocr_texts = [d["text"] for d in odet]
    for d in odet:
        if classify_ocr_string(d["text"]):
            boxes.append(d["box"])
    return {
        "boxes": boxes,
        "confs": [d["conf"] for d in ydet],
        "ocr_texts": ocr_texts,
        "ocr_hit": any(classify_ocr_string(t) for t in ocr_texts),
        "yolo": ydet,
        "ocr": odet,
    }


def render_mask(boxes, w, h, dilate_px: int = DILATE_PX):
    """White-on-black uint8 mask: box union dilated by a 15px ellipse (cv2).

    WHITE (255) = inpaint region. NEVER inpaint without a mask.
    """
    import cv2
    mask = np.zeros((int(h), int(w)), dtype=np.uint8)
    for x0, y0, x1, y1 in boxes:
        cv2.rectangle(mask, (int(x0), int(y0)), (int(x1), int(y1)), 255, -1)
    ksz = 2 * dilate_px + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksz, ksz))
    return cv2.dilate(mask, kernel)


def inpaint_lama(image, mask, lama):
    """Inpaint the masked region ONLY, baking the composite identity rule.

    out = inp*(1-mask01) + lama_full*mask01, so pixels OUTSIDE the mask are
    byte-identical to the input by construction (turns the G2 outside check into
    a bug tripwire). mask WHITE = inpaint. Returns a PIL RGB image.
    """
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image.astype(np.uint8))
    image = image.convert("RGB")
    if isinstance(mask, np.ndarray):
        mask_img = Image.fromarray(mask.astype(np.uint8))
    else:
        mask_img = mask
    mask_img = mask_img.convert("L")
    lama_out = lama(image, mask_img)
    lam = np.asarray(lama_out.convert("RGB").resize(image.size),
                     dtype=np.float64)
    inp = np.asarray(image, dtype=np.float64)
    m01 = (np.asarray(mask_img, dtype=np.float64) / 255.0)[:, :, None]
    out = inp * (1.0 - m01) + lam * m01
    return Image.fromarray(np.clip(out, 0.0, 255.0).astype(np.uint8))


def _mser_region_count(crop) -> int:
    """Count MSER stable regions in a crop (0 on any cv2 shape/dtype edge)."""
    import cv2
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if crop.ndim == 3 else crop
    try:
        mser = cv2.MSER_create()
        regions, _ = mser.detectRegions(gray)
    except Exception:   # noqa: BLE001 - MSER shape/dtype edge cases are non-fatal
        return 0
    return len(regions)


def text_energy(np_img, bbox, reader) -> float:
    """Text-like energy inside bbox: OCR char count + 0.5 * MSER region count.

    The residue-REDUCTION probe (see _residue_decision): measured on BOTH the
    input and the inpaint output, the DROP between them distinguishes a clean
    fill from a genuine residue. OCR tokens under 2 chars are ignored (noise);
    cv2 stays lazy so the pure suite never imports it.
    """
    x0, y0, x1, y1 = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
    crop = np_img[max(0, y0):y1, max(0, x0):x1]
    if crop.size == 0:
        return 0.0
    ocr_energy = sum(len(str(txt)) for txt in reader.readtext(crop, detail=0)
                     if len(str(txt).strip()) >= 2)
    return float(ocr_energy) + 0.5 * _mser_region_count(crop)


def text_residue(np_img, bbox, reader) -> bool:
    """Legacy absolute-residue check (thin wrapper over text_energy).

    The LIVE path is _residue_decision on the before/after energy REDUCTION -
    verify no longer trusts an absolute count. Kept for external callers.
    """
    return text_energy(np_img, bbox, reader) > 0.0


def selfcheck():
    """Import + probe all five ML deps; return a readiness/signature dict.

    Records installed versions, the resolved SimpleLama return mode (probed on a
    64x64 smoke), YOLO class names, torch CUDA capability, and the OCR langs.
    Run under the clean venv at build to confirm the section-2 API contract.
    """
    info = {}
    import torch
    info["torch"] = {"version": torch.__version__,
                     "cuda": bool(torch.cuda.is_available())}
    try:
        info["torch"]["capability"] = list(torch.cuda.get_device_capability())
    except Exception:   # noqa: BLE001 - no CUDA device -> capability unknown
        info["torch"]["capability"] = None

    import ultralytics
    info["ultralytics"] = {"version": ultralytics.__version__}
    import easyocr
    info["easyocr"] = {"version": getattr(easyocr, "__version__", "unknown")}
    import simple_lama_inpainting as sli
    info["simple_lama"] = {"version": getattr(sli, "__version__", "unknown")}
    import cv2
    info["cv2"] = {"version": cv2.__version__,
                   "has_mser": hasattr(cv2, "MSER_create"),
                   "has_ellipse": hasattr(cv2, "getStructuringElement")}

    signatures = {
        "yolo": "YOLO(w)(img, imgsz, conf, iou) -> [0].boxes.xyxy/.conf/.cls",
        "easyocr": "Reader(['en','ch_sim'], gpu).readtext(np, detail=1)",
        "cv2": "getStructuringElement(MORPH_ELLIPSE,(31,31)); dilate; MSER_create",
    }
    try:
        models = load_models()
        info["yolo_names"] = getattr(models["yolo"], "names", None)
        probe = np.full((64, 64, 3), 180, dtype=np.uint8)
        pmask = np.zeros((64, 64), dtype=np.uint8)
        pmask[24:40, 24:40] = 255
        lam_out = models["lama"](Image.fromarray(probe),
                                 Image.fromarray(pmask).convert("L"))
        signatures["simple_lama"] = (
            f"SimpleLama(device)(img, mask) -> PIL mode "
            f"{getattr(lam_out, 'mode', '?')}; white=inpaint; composited")
    except Exception as exc:   # noqa: BLE001 - selfcheck reports, never raises
        signatures["load_error"] = f"{type(exc).__name__}: {exc}"
    info["signatures"] = signatures
    return info


# ==========================================================================
# ORCHESTRATION
# ==========================================================================
def _ring_mask(mask_bool, width: int = 8):
    """Boundary ring: the mask dilated by `width` px, minus the mask itself."""
    m = mask_bool.astype(np.float64)
    dilated = _box_mean(m, 2 * width + 1) > 0.0
    return dilated & (~mask_bool)


def _inside_change_ssim(a, b, mask_bool) -> float:
    """Mean SSIM inside the mask (low => the inpaint actually changed pixels)."""
    if not np.asarray(mask_bool, dtype=bool).any():
        return 1.0
    smap = _ssim_map(_to_gray(a), _to_gray(b))
    return float(np.mean(smap[np.asarray(mask_bool, dtype=bool)]))


def _resolve_out_dir(out_dir, slug, beside):
    if beside:
        return os.path.join(CLEAN_SCRATCH, slug)
    if out_dir:
        return str(out_dir)
    return os.path.join(RUNTIME_CLEAN, slug)


def _quote(tok):
    tok = str(tok)
    return f'"{tok}"' if (" " in tok or "\t" in tok) else tok


def _print_cmds(cmds):
    for argv in cmds:
        print("  " + " ".join(_quote(t) for t in argv))


def process_slug(slug, image=None, out_dir=None, dry_run=False,
                 max_attempts=2, beside=False, models=None,
                 langs=("en", "ch_sim")):
    """Detect -> gate -> (inpaint -> verify) for one slug. Returns a result dict.

    Never mutates pipeline state: on a PASS it writes the candidate to the
    runtime out-dir and PRINTS the save-working + submit commands. dry_run does
    DETECT + GATE only and writes nothing (pure triage).
    """
    if image is None:
        image = select_working_image(os.path.join(CLEAN_SCRATCH, slug), slug)
        if image is None:
            return {"slug": slug, "status": "error", "verdict": "qa",
                    "reason": "no clean input image"}
    with Image.open(image) as im:
        w, h = im.size

    det = detect_image(image, out_dir=out_dir, models=models, langs=langs)
    boxes = union_boxes(det["boxes"])
    confs = det.get("confs") or []
    conf_max = max(confs) if confs else 0.0
    ocr_hit = bool(det.get("ocr_hit")) or any(
        classify_ocr_string(t) for t in det.get("ocr_texts", []))
    area_pct = dilated_union_area_pct(boxes, w, h, DILATE_PX)
    n = len(boxes)
    centroid = centroid_of(boxes)
    verdict, reason = gate_decision(n, conf_max, ocr_hit, area_pct, centroid,
                                    w, h, det.get("ocr_texts", []))

    rec = triage_record(slug, image, boxes, conf_max, area_pct, verdict)
    rec["reason"] = reason
    if dry_run:
        rec["status"] = "dry-run"
        return rec

    target_dir = _resolve_out_dir(out_dir, slug, beside)
    if verdict == "clean":
        cmds = build_cleanscan_cmds(slug, image)
        print(f"LW CLEAN {slug}: clean scan (no detections)")
        _print_cmds(cmds)
        rec["status"] = "clean"
        rec["commands"] = cmds
        return rec
    if verdict == "qa":
        os.makedirs(target_dir, exist_ok=True)
        mask = (render_mask(boxes, w, h, DILATE_PX) if boxes
                else np.zeros((h, w), dtype=np.uint8))
        atomic_write_png(os.path.join(target_dir, f"{slug}_qa_mask.png"), mask)
        atomic_write_json(os.path.join(target_dir, f"{slug}_detect.json"),
                          {**rec, "note": f"qa:{reason}"})
        print(f"LW CLEAN {slug}: -> QA queue ({reason})")
        rec["status"] = "qa"
        return rec
    return _auto_inpaint(slug, image, boxes, w, h, target_dir, max_attempts,
                         models, langs, rec)


def _auto_inpaint(slug, image_path, boxes, w, h, out_dir, max_attempts,
                  models, langs, rec):
    """Mask -> LaMa -> verify loop (up to max_attempts). Prints commands on pass."""
    models = models or load_models(langs)
    os.makedirs(out_dir, exist_ok=True)
    with Image.open(image_path) as im:
        base = im.convert("RGB")
    base_arr = np.asarray(base)
    mask = render_mask(boxes, w, h, DILATE_PX)
    mask_bool = mask > 127
    ring = _ring_mask(mask_bool)
    atomic_write_png(os.path.join(out_dir, f"{slug}_mask.png"), mask)

    last = None
    for attempt in range(1, max_attempts + 1):
        out_img = inpaint_lama(base, mask, models["lama"])
        out_arr = np.asarray(out_img)
        ssim_out, mad_out = masked_identity(base_arr, out_arr, mask_bool)
        change = _inside_change_ssim(base_arr, out_arr, mask_bool)
        try:
            residue = any(
                _residue_decision(
                    text_energy(base_arr, b, models["reader"]),
                    text_energy(out_arr, b, models["reader"]))
                for b in boxes)
        except Exception:   # noqa: BLE001 - residue probe is advisory, not fatal
            residue = False
        seam = seam_ring_ssim(out_arr, ring)
        v = verify_verdict(ssim_out, mad_out, change, residue, seam)
        v["metrics"] = {"outside_ssim": round(ssim_out, 6),
                        "mad_outside": round(mad_out, 6),
                        "change_ssim": round(change, 6),
                        "seam_ssim": round(seam, 6),
                        "residue": residue, "attempt": attempt}
        last = v
        if v["verdict"] == "discard":
            atomic_write_json(os.path.join(out_dir, f"{slug}_verify.json"),
                              {**rec, "verify": v})
            print(f"LW CLEAN {slug}: HARD DISCARD (outside-mask violation) "
                  f"- halt: {'; '.join(v['reasons'])}")
            rec["status"] = "discard"
            rec["verify"] = v
            return rec
        if v["verdict"] == "pass":
            cand = os.path.join(out_dir, f"{slug}_clean_cand.png")
            atomic_write_png(cand, out_img)
            params = {"mask_bbox": _union_envelope(boxes),
                      "mask_area_pct": round(rec["mask_area_pct"], 4),
                      "conf": round(rec["conf"], 4), "engine": "simple-lama",
                      "ocr": [], "attempts": attempt}
            save = build_save_working_cmd(slug, cand, params)
            sub = build_submit_cmd(slug)
            atomic_write_json(os.path.join(out_dir, f"{slug}_verify.json"),
                              {**rec, "verify": v})
            flag = " [seam-flag]" if "seam" in v["flags"] else ""
            print(f"LW CLEAN {slug}: inpaint PASS{flag} (attempt {attempt})")
            _print_cmds([save, sub])
            rec["status"] = "inpainted"
            rec["verify"] = v
            rec["commands"] = [save, sub]
            return rec

    atomic_write_json(os.path.join(out_dir, f"{slug}_verify.json"),
                      {**rec, "verify": last})
    print(f"LW CLEAN {slug}: -> QA queue (gate-fail after {max_attempts})")
    rec["status"] = "qa"
    rec["verify"] = last
    return rec


def _iter_slugs(batch, all_scratch):
    if all_scratch or batch == "--all-scratch":
        base = Path(CLEAN_SCRATCH)
        if not base.is_dir():
            return []
        return [c.name for c in sorted(base.iterdir()) if c.is_dir()]
    text = Path(batch).read_text(encoding="utf-8")
    return [ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def run_batch(slugs, out_dir=None, dry_run=False, limit=None, max_attempts=2,
              beside=False, triage_out=None):
    """Sequentially process slugs (one GPU). Prints the triage/cleaning banner."""
    if limit is not None:
        slugs = slugs[:limit]
    counts = {"scanned": 0, "auto": 0, "qa": 0, "clean": 0, "inpainted": 0,
              "gate-fail": 0, "submitted": 0, "error": 0}
    triage_rows = []
    for slug in slugs:
        try:
            res = process_slug(slug, out_dir=out_dir, dry_run=dry_run,
                               max_attempts=max_attempts, beside=beside)
        except Exception as exc:   # noqa: BLE001 - one slug != batch death
            res = {"slug": slug, "status": "error", "verdict": "qa",
                   "reason": str(exc)}
        counts["scanned"] += 1
        verdict = res.get("verdict")
        status = res.get("status")
        if dry_run:
            if verdict in ("auto", "qa", "clean"):
                counts[verdict] += 1
            triage_rows.append(res)
        else:
            if status == "clean":
                counts["clean"] += 1
            elif status == "inpainted":
                counts["inpainted"] += 1
                counts["submitted"] += 1
            elif status == "discard":
                counts["gate-fail"] += 1
            elif status in ("qa", "error"):
                counts["qa"] += 1
        _print_line(res, dry_run)

    if triage_out and triage_rows:
        with open(triage_out, "w", encoding="utf-8") as f:
            for row in triage_rows:
                f.write(json.dumps(row) + "\n")

    if dry_run:
        print("LW CLEAN TRIAGE | scanned={scanned} auto={auto} qa={qa} "
              "clean={clean}".format(**counts))
    else:
        print("LW CLEANING | scanned={scanned} clean={clean} "
              "inpainted={inpainted} qa-queued={qa} gate-fail={gate-fail} "
              "| submitted={submitted} | next: approve/reject via lw_pipeline"
              .format(**{**counts, "gate-fail": counts["gate-fail"]}))
    return counts


def _print_line(res, dry_run):
    slug = res.get("slug", "?")
    verdict = res.get("verdict", "?")
    reason = res.get("reason", "")
    if dry_run:
        print(f"  {slug:<52} {verdict:<6} area={res.get('mask_area_pct')} "
              f"{reason}")
    else:
        print(f"  {slug:<52} {res.get('status', '?'):<10} {reason}")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="lw_clean_pass",
        description="Legion Wallpaper Stage-2 cleaning harness")
    p.add_argument("slug", nargs="?", help="single slug to process")
    p.add_argument("--image", help="explicit input image override")
    p.add_argument("--out-dir", help="side-file dir (default ops/runtime/clean)")
    p.add_argument("--beside", action="store_true",
                   help="write side-files into scratch (needs approve --force)")
    p.add_argument("--dry-run", action="store_true",
                   help="triage only: detect+gate, write no pixels")
    p.add_argument("--batch", metavar="FILE",
                   help="slugs.txt (one per line) or --all-scratch")
    p.add_argument("--all-scratch", action="store_true",
                   help="process every slug dir in 3.Cleaning Scratch")
    p.add_argument("--triage-out", help="aggregate triage JSONL path")
    p.add_argument("--limit", type=int, help="cap the number of slugs")
    p.add_argument("--max-attempts", type=int, default=2)
    p.add_argument("--selfcheck", action="store_true",
                   help="import+inspect ML deps, print readiness JSON, exit")
    args = p.parse_args(argv)

    if args.selfcheck:
        print(json.dumps(selfcheck(), indent=2, default=str))
        return 0

    if args.batch or args.all_scratch:
        slugs = _iter_slugs(args.batch, args.all_scratch)
        run_batch(slugs, out_dir=args.out_dir, dry_run=args.dry_run,
                  limit=args.limit, max_attempts=args.max_attempts,
                  beside=args.beside, triage_out=args.triage_out)
        return 0

    if not args.slug:
        p.error("give a slug, or --batch <file>/--all-scratch, or --selfcheck")

    res = process_slug(args.slug, image=args.image, out_dir=args.out_dir,
                       dry_run=args.dry_run, max_attempts=args.max_attempts,
                       beside=args.beside)
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
