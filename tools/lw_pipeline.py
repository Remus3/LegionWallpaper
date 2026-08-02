"""lw_pipeline.py - Legion Wallpaper staged-folder pipeline core (stdlib only).

Implements docs/research/PIPELINE_STATE_MACHINE.md with the operator rulings:
- End Review rejection ENABLED (T7r: demote to 7.Last Scratch).
- Done-N GC only after hash-verified arrival in Done N+1 (FM-02).
- End Review PASS: _lastdone is copied to 9.Image Backup (hash-verified) and
  the 8.End Review\\<slug> folder IS deleted (full milestone chain already
  lives in 9.Image Backup via the per-stage _initial copies).
- Pipeline root defaults to C:\\LegionWallpaper\\images (.gitkeep tolerated).
- Delivery runs ONLY with an explicit --deliver flag, never by default.

Exit codes: 0 ok, 1 anomalies found, 2 precondition/argument error,
3 verification failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

DEFAULT_ROOT = Path(r"C:\LegionWallpaper\images")

STAGES = ["first", "clean", "final", "last"]
SCRATCH_DIR = {
    "first": "1.First Pass Scratch",
    "clean": "3.Cleaning Scratch",
    "final": "5.Final Scratch",
    "last": "7.Last Scratch",
}
DONE_DIR = {
    "first": "2.First Pass Done",
    "clean": "4.Cleaning Done",
    "final": "6.Final Done",
    "last": "8.End Review",
}
ORIGINALS = "0.Originals"
BACKUP = "9.Image Backup"

STATE_NAME = {
    1: "FIRST_SCRATCH", 2: "FIRST_DONE", 3: "CLEAN_SCRATCH", 4: "CLEAN_DONE",
    5: "FINAL_SCRATCH", 6: "FINAL_DONE", 7: "LAST_SCRATCH", 8: "END_REVIEW",
}
COUNT_KEY = {
    "FIRST_SCRATCH": "first_scratch", "FIRST_DONE": "first_done",
    "CLEAN_SCRATCH": "clean_scratch", "CLEAN_DONE": "clean_done",
    "FINAL_SCRATCH": "final_scratch", "FINAL_DONE": "final_done",
    "LAST_SCRATCH": "last_scratch", "END_REVIEW": "end_review",
    "PASSED": "passed",
}
START_OP = {"clean": "START_CLEAN", "final": "START_FINAL", "last": "START_LAST"}
APPROVE_OP = {
    "first": "APPROVE_FIRST", "clean": "APPROVE_CLEAN",
    "final": "APPROVE_FINAL", "last": "APPROVE_LAST",
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
PARTIAL_EXTS = {".crdownload", ".part", ".tmp", ".download"}
SIDECAR_NAMES = {"manifest.json", ".lw.lock", ".gitkeep"}
EDITOR_SIDECAR_EXTS = {".psd", ".kra", ".xcf", ".bak", ".autosave"}

MIN_AGE_SECONDS = 10.0     # intake gate: mtime must be at least this old
PROBE_SECONDS = 2.0        # intake gate: size-stability probe interval
STALE_PART_SECONDS = 86400.0
STALE_LOCK_SECONDS = 3600.0

RESERVED_NAMES = (
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)

MILESTONE_RE = re.compile(
    r"^(?P<slug>[a-z0-9][a-z0-9-]{0,63})"
    r"_(?P<stage>first|clean|final|last)"
    r"(?:(?P<phase>initial|needauth|done)|working_(?P<ver>[0-9]{2,}))"
    r"\.(?P<ext>[A-Za-z]+)$"
)


class PipelineError(Exception):
    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------- helpers

def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def iso_of(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def parse_milestone(name):
    """Parse a milestone filename; return dict or None (section 2.2)."""
    m = MILESTONE_RE.match(name)
    if not m:
        return None
    ext = m.group("ext").lower()
    if ext not in {"png", "jpg", "jpeg", "webp"}:
        return None
    phase = m.group("phase") or "working"
    ver = int(m.group("ver")) if m.group("ver") else None
    return {
        "slug": m.group("slug"), "stage": m.group("stage"),
        "phase": phase, "ver": ver, "ext": ext,
    }


def slugify(basename):
    """Slug per section 2.5 steps 1-6 (collision handling is separate)."""
    stem = os.path.splitext(basename)[0]
    stem = unicodedata.normalize("NFKD", stem)
    stem = stem.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem)
    slug = slug.strip("-")
    slug = slug[:64].rstrip("-")
    if not slug:
        slug = "img"
    if slug in RESERVED_NAMES:
        slug = slug + "-x"
    return slug


def milestone_name(slug, stage, phase, ver=None, ext="png"):
    if phase == "working":
        return f"{slug}_{stage}working_{ver:02d}.{ext}"
    return f"{slug}_{stage}{phase}.{ext}"


# ---------------------------------------------------------------- ops recorder

class Ops:
    """Executes filesystem ops, or records them under --dry-run."""

    def __init__(self, dry):
        self.dry = dry
        self.planned = []

    def note(self, text):
        self.planned.append(text)

    def mkdir(self, path):
        self.note(f"mkdir {path}")
        if not self.dry:
            path.mkdir(parents=True, exist_ok=True)

    def rename(self, src, dst):
        self.note(f"rename {src} -> {dst}")
        if self.dry:
            return
        if dst.exists():
            raise FileExistsError(str(dst))
        os.rename(src, dst)

    def delete(self, path):
        self.note(f"delete {path}")
        if not self.dry:
            path.unlink(missing_ok=True)

    def rmdir(self, path):
        self.note(f"rmdir {path}")
        if not self.dry:
            path.rmdir()

    def write_json(self, path, data):
        self.note(f"write-json {path}")
        if self.dry:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def safe_copy(self, src, dstdir, dstname, delete_src=False):
        """SAFE-MOVE primitive: copy+fsync+SHA256 verify (+delete src)."""
        dst = dstdir / dstname
        src_hash = sha256_file(src)
        verb = "safe-move" if delete_src else "safe-copy"
        self.note(f"{verb} {src} -> {dst}")
        if self.dry:
            return src_hash
        if dst.exists():
            if sha256_file(dst) == src_hash:
                if delete_src:
                    src.unlink()
                return src_hash
            raise PipelineError(
                f"hash-diff target exists: {dst}", code=3)
        part = dstdir / (dstname + ".part")
        with open(src, "rb") as fi, open(part, "wb") as fo:
            while True:
                chunk = fi.read(1 << 20)
                if not chunk:
                    break
                fo.write(chunk)
            fo.flush()
            os.fsync(fo.fileno())
        if sha256_file(part) != src_hash:
            part.unlink()
            raise PipelineError(f"copy verification failed: {dst}", code=3)
        try:
            os.rename(part, dst)
        except FileExistsError:
            existing = sha256_file(dst)
            part.unlink()
            if existing != src_hash:
                raise PipelineError(
                    f"hash-diff target appeared: {dst}", code=3)
        if delete_src:
            src.unlink()
        return src_hash

    def backup_put(self, src, backup_dir, name):
        """FM-09: hash-idempotent, never-overwrite backup write."""
        src_hash = sha256_file(src)
        stem, ext = os.path.splitext(name)
        candidate = name
        i = 2
        while True:
            target = backup_dir / candidate
            if not target.exists():
                return self.safe_copy(src, backup_dir, candidate)
            if not self.dry and sha256_file(target) == src_hash:
                self.note(f"backup skip (hash-equal): {target}")
                return src_hash
            if self.dry:
                self.note(f"backup put {src} -> {target}")
                return src_hash
            candidate = f"{stem}.{i}{ext}"
            i += 1


# ---------------------------------------------------------------- locking

def acquire_lock(folder, dry):
    if dry:
        return None
    path = folder / ".lw.lock"
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise PipelineError(f"locked: {path} already held", code=2)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        json.dump({"pid": os.getpid(), "ts": time.time()}, f)
    return path


def release_lock(path):
    if path is not None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------- manifest/log

def load_manifest(folder):
    p = folder / "manifest.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def new_manifest(slug, original_filename, original_sha256):
    return {
        "schema": 1, "slug": slug,
        "original_filename": original_filename,
        "original_sha256": original_sha256,
        "source_url": None, "created_ts": iso_now(),
        "delivered_as": None, "transitions": [],
    }


def add_transition(man, op, actor="operator", tool=None, params=None,
                   src=None, dst=None, sha_in=None, sha_out=None,
                   note=None, audit=None):
    man["transitions"].append({
        "ts": iso_now(), "op": op, "actor": actor, "tool": tool,
        "params": params, "src": src, "dst": dst,
        "sha256_in": sha_in, "sha256_out": sha_out,
        "note": note, "audit": audit,
    })


class Ctx:
    def __init__(self, root, dry=False):
        self.root = Path(root)
        self.project_root = self.root.parent
        self.dry = dry

    def log_path(self):
        return self.project_root / "PIPELINE_LOG.md"

    def state_path(self):
        return self.project_root / "ops" / "runtime" / "pipeline_state.json"

    def rel(self, path):
        try:
            return str(Path(path).relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return str(path)

    def log(self, slug, op, frm, to, sha12, actor="operator",
            status="ok", note=None):
        line = "{} | {} | {} | {} -> {} | actor={} | sha12={} | {} | note={}".format(
            iso_now(), slug, op, frm, to, actor, sha12, status, note or "-")
        if self.dry:
            return
        p = self.log_path()
        header = "" if p.exists() else "# PIPELINE_LOG - append-only, one line per transition\n\n"
        with open(p, "a", encoding="ascii", errors="replace") as f:
            f.write(header + line + "\n")


# ---------------------------------------------------------------- scanning

def _folder_ordinal(stage, kind):
    idx = STAGES.index(stage)
    return 2 * idx + 1 if kind == "scratch" else 2 * idx + 2


def _analyze_folder(folder, slug, stage, kind, anomalies):
    """Classify a slug folder's contents. Returns (milestones, working_max)."""
    now = time.time()
    milestones = []
    keys = {}
    working_max = 0
    for f in sorted(folder.iterdir()):
        name = f.name
        if f.is_dir():
            anomalies.append({"slug": slug, "class": "UNPARSED_FILE",
                              "detail": f"unexpected subfolder {name}",
                              "resumable": False})
            continue
        if name in SIDECAR_NAMES:
            if name == ".lw.lock" and now - f.stat().st_mtime > STALE_LOCK_SECONDS:
                anomalies.append({"slug": slug, "class": "STALE_LOCK",
                                  "detail": str(f), "resumable": True})
            continue
        if name.endswith(".part"):
            if now - f.stat().st_mtime > STALE_PART_SECONDS:
                anomalies.append({"slug": slug, "class": "STALE_PART",
                                  "detail": str(f), "resumable": True})
            continue
        m = parse_milestone(name)
        if m is None:
            if kind == "scratch" or f.suffix.lower() in EDITOR_SIDECAR_EXTS:
                continue  # adopt candidates / editor sidecars are legal in scratch
            anomalies.append({"slug": slug, "class": "UNPARSED_FILE",
                              "detail": str(f), "resumable": False})
            continue
        if m["slug"] != slug:
            anomalies.append({"slug": slug, "class": "UNPARSED_FILE",
                              "detail": f"slug mismatch: {name}",
                              "resumable": False})
            continue
        key = (m["stage"], m["phase"], m["ver"])
        if key in keys:
            anomalies.append({"slug": slug, "class": "DUPLICATE_KEY",
                              "detail": f"{keys[key]} vs {name}",
                              "resumable": False})
        else:
            keys[key] = name
        if m["phase"] == "working" and m["stage"] == stage:
            working_max = max(working_max, m["ver"])
        milestones.append((m, f))
    return milestones, working_max


def scan_tree(ctx, verify=False, slug_filter=None):
    root = ctx.root
    anomalies = []
    images = {}
    presence = {}

    orig_dir = root / ORIGINALS
    pending = []
    if orig_dir.is_dir():
        pending = [p for p in orig_dir.iterdir()
                   if p.is_file() and p.name not in SIDECAR_NAMES]

    for stage in STAGES:
        for kind, dirname in (("scratch", SCRATCH_DIR[stage]),
                              ("done", DONE_DIR[stage])):
            base = root / dirname
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir()):
                if child.is_dir():
                    presence.setdefault(child.name, []).append(
                        (_folder_ordinal(stage, kind), kind, stage, child))
                elif child.name not in SIDECAR_NAMES:
                    anomalies.append({"slug": None, "class": "UNPARSED_FILE",
                                      "detail": str(child), "resumable": False})
    backup_base = root / BACKUP
    if backup_base.is_dir():
        for child in sorted(backup_base.iterdir()):
            if child.is_dir():
                presence.setdefault(child.name, []).append((9, "backup", None, child))

    for slug, entries in sorted(presence.items()):
        if slug_filter and slug != slug_filter:
            continue
        entries.sort(key=lambda e: e[0])
        pipeline_entries = [e for e in entries if e[0] <= 8]
        scratch_entries = [e for e in pipeline_entries if e[1] == "scratch"]
        done_entries = [e for e in pipeline_entries if e[1] == "done"]
        if len(scratch_entries) > 1:
            anomalies.append({"slug": slug, "class": "SPLIT_STATE",
                              "detail": f"slug in {len(scratch_entries)} scratch folders",
                              "resumable": False})
        if pipeline_entries:
            ordn, kind, stage, folder = pipeline_entries[-1]
            state = STATE_NAME[ordn]
        else:
            ordn, kind, stage, folder = entries[-1]
            state = "PASSED"

        substate = None
        working_max = 0
        img_anoms_before = len(anomalies)
        for e_ord, e_kind, e_stage, e_folder in pipeline_entries:
            ms, wmax = _analyze_folder(e_folder, slug, e_stage, e_kind, anomalies)
            names = {m[0]["stage"] + m[0]["phase"] for m in ms}
            if e_kind == "scratch":
                working_max = max(working_max, wmax)
                if e_stage + "done" in names:
                    substate = "APPROVED_PENDING_MOVE"
                    anomalies.append({"slug": slug, "class": "APPROVED_PENDING_MOVE",
                                      "detail": str(e_folder), "resumable": True})
                elif e_stage + "needauth" in names:
                    substate = "NEEDAUTH"
                elif ms:
                    substate = "EDITING"
                    if e_stage + "initial" not in names:
                        anomalies.append({"slug": slug, "class": "MISSING_INITIAL",
                                          "detail": str(e_folder), "resumable": False})
                else:
                    residue = [p.name for p in e_folder.iterdir()
                               if p.name not in SIDECAR_NAMES]
                    anomalies.append({"slug": slug, "class": "SCRATCH_RESIDUE",
                                      "detail": "{}: {}".format(e_folder, residue or "empty"),
                                      "resumable": not residue})

        # STALE_DONE: two done-tier folders coexist (FM-02 resumable GC)
        if len(done_entries) > 1:
            for e in done_entries[:-1]:
                anomalies.append({"slug": slug, "class": "STALE_DONE",
                                  "detail": f"{e[3]} superseded by {done_entries[-1][3]}",
                                  "resumable": True})

        if verify:
            _verify_folders(slug, [e[3] for e in entries], anomalies)

        man = load_manifest(folder)
        last_ts = None
        if man and man.get("transitions"):
            last_ts = man["transitions"][-1].get("ts")
        files = []
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.name not in SIDECAR_NAMES:
                entry = {"name": p.name, "bytes": p.stat().st_size,
                         "mtime": iso_of(p.stat().st_mtime)}
                if verify:
                    entry["sha256"] = sha256_file(p)
                files.append(entry)
        images[slug] = {
            "state": state, "substate": substate,
            "stage_folder": folder.parent.name,
            "working_max": working_max, "last_op_ts": last_ts,
            "files": files,
            "anomalies": [a["class"] for a in anomalies[img_anoms_before:]],
        }

    counts = {k: 0 for k in ("pending_intake first_scratch first_done "
                             "clean_scratch clean_done final_scratch final_done "
                             "last_scratch end_review passed").split()}
    counts["pending_intake"] = len(pending)
    for info in images.values():
        counts[COUNT_KEY[info["state"]]] += 1
    counts["anomalies"] = len(anomalies)

    return {
        "schema": 1, "generated_ts": iso_now(), "scan_verify": verify,
        "root": str(root), "counts": counts, "images": images,
        "anomalies": anomalies,
    }


def _milestone_key(name):
    """Identity of a milestone FILE, ignoring its container format.

    slug + stage + phase + version, never the extension. The 2026-07-15
    aspect-correction pass saved corrected crops as .png over a .jpg intake and
    the 2026-08-01 wiki swap wrote .jpg over a .jpeg, and keying by filename made
    every one of those 9 files match no recorded transition at all - so `verify`
    checked NOTHING for them and reported clean. A replaced file that becomes
    UNVERIFIABLE is worse than one that reports a mismatch: the mismatch is
    noise, the silence reads as a pass. Found investigating vayne3, which was in
    that same operation and was only ever visible because its crop happened to
    keep the .jpg extension.
    """
    parsed = parse_milestone(os.path.basename(name or ""))
    if not parsed:
        return None
    return (parsed["slug"], parsed["stage"], parsed["phase"], parsed["ver"])


def _expected_hashes(folders):
    """milestone key -> the sha256_out of its LATEST transition, by TIMESTAMP.

    By timestamp and not by file order: a file's current truth is whatever was
    recorded about it most recently, and depending on dict-insertion order makes
    a manifest with out-of-order entries verify against a superseded hash. That
    matters now that REPLACE_SOURCE supersedes INTAKE for the same milestone
    (ROADMAP wiki-swap-manifest-hash-residue).

    Keyed by milestone identity rather than filename - see `_milestone_key`.
    """
    latest = {}
    for folder in folders:
        man = load_manifest(folder)
        if not man:
            continue
        for t in man.get("transitions", []):
            dst, sha = t.get("dst"), t.get("sha256_out")
            if not dst or not sha:
                continue
            key = _milestone_key(dst)
            if key is None:
                continue
            stamp = str(t.get("ts") or "")
            if key not in latest or stamp >= latest[key][0]:
                latest[key] = (stamp, sha)
    return {key: sha for key, (_, sha) in latest.items()}


def record_replace_source(folder, target, note=None, source_url=None,
                          actor="operator", tool=None):
    """Append a REPLACE_SOURCE transition for a file swapped in place.

    Returns True if one was written, False if there was nothing to record.

    The alternative - rewriting the INTAKE transition's hash - was REJECTED
    (ROADMAP wiki-swap-manifest-hash-residue): it makes `verify` green by editing
    history, and the manifest is the provenance record. A record that silently
    restates what was intaken can no longer answer what we actually started from,
    and every other ledger in this repo is append-only for exactly that reason.

    Idempotent by hash, so a backfill can be re-run: when the recorded hash
    already agrees with what is on disk, there is nothing to say and nothing is
    appended.
    """
    folder, target = Path(folder), Path(target)
    man = load_manifest(folder)
    if not man:
        return False
    current = sha256_file(target)
    previous = _expected_hashes([folder]).get(_milestone_key(target.name))
    if previous == current:
        return False
    add_transition(man, "REPLACE_SOURCE", actor=actor, tool=tool,
                   params={"source_url": source_url} if source_url else {},
                   src=source_url, dst=f"{folder.name}/{target.name}",
                   sha_in=previous, sha_out=current, note=note)
    Ops(dry=False).write_json(folder / "manifest.json", man)
    return True


def _verify_folders(slug, folders, anomalies):
    """Diff on-disk hashes against manifest-recorded sha256_out (FM-11)."""
    expected = _expected_hashes(folders)
    for folder in folders:
        for p in sorted(folder.iterdir()):
            if not p.is_file() or not parse_milestone(p.name):
                continue
            want = expected.get(_milestone_key(p.name))
            if want and sha256_file(p) != want:
                anomalies.append({"slug": slug, "class": "HASH_MISMATCH",
                                  "detail": str(p), "resumable": False})


def write_state(ctx, world):
    if ctx.dry:
        return
    ops = Ops(dry=False)
    ops.write_json(ctx.state_path(), world)


def refresh_state(ctx):
    """Post-mutation contract: rescan + atomic state rewrite."""
    if ctx.dry:
        return
    write_state(ctx, scan_tree(ctx))


# ---------------------------------------------------------------- lookups

def find_scratch(ctx, slug):
    for stage in STAGES:
        folder = ctx.root / SCRATCH_DIR[stage] / slug
        if folder.is_dir():
            return stage, folder
    return None, None


def find_done(ctx, slug):
    for stage in reversed(STAGES):
        folder = ctx.root / DONE_DIR[stage] / slug
        if folder.is_dir():
            return stage, folder
    return None, None


def slug_in_use(ctx, slug):
    low = slug.lower()
    dirs = ([ctx.root / SCRATCH_DIR[s] for s in STAGES]
            + [ctx.root / DONE_DIR[s] for s in STAGES]
            + [ctx.root / BACKUP])
    for base in dirs:
        if base.is_dir():
            for child in base.iterdir():
                if child.is_dir() and child.name.lower() == low:
                    return True
    return False


def unique_slug(ctx, base_slug, original_hash):
    """Section 2.5 step 7. Raises PipelineError on identical re-intake."""
    candidate = base_slug
    i = 2
    while slug_in_use(ctx, candidate):
        backup_dir = ctx.root / BACKUP / candidate
        if backup_dir.is_dir():
            for p in backup_dir.iterdir():
                if p.is_file() and p.name not in SIDECAR_NAMES \
                        and sha256_file(p) == original_hash:
                    raise PipelineError(
                        f"duplicate of existing slug {candidate} (hash-equal original)", code=2)
        suffix = f"-{i}"
        candidate = base_slug[: 64 - len(suffix)].rstrip("-") + suffix
        i += 1
    return candidate


def scratch_workings(folder, slug, stage):
    out = []
    for p in folder.iterdir():
        m = parse_milestone(p.name) if p.is_file() else None
        if m and m["slug"] == slug and m["stage"] == stage and m["phase"] == "working":
            out.append((m["ver"], p))
    return sorted(out)


# ---------------------------------------------------------------- intake (T1)

def eligibility_reason(path):
    ext = path.suffix.lower()
    if ext in PARTIAL_EXTS:
        return "partial-download extension"
    if ext not in IMAGE_EXTS:
        return "unsupported extension"
    size = path.stat().st_size
    if size == 0:
        return "zero-byte file"
    if time.time() - path.stat().st_mtime < MIN_AGE_SECONDS:
        return "modified too recently (still downloading?)"
    time.sleep(PROBE_SECONDS)
    if path.stat().st_size != size:
        return "size still changing"
    return None


def cmd_intake(ctx, files, do_all):
    orig_dir = ctx.root / ORIGINALS
    if do_all:
        targets = sorted(p for p in orig_dir.iterdir()
                         if p.is_file() and p.name not in SIDECAR_NAMES)
    else:
        targets = []
        for name in files:
            p = Path(name)
            targets.append(p if p.is_absolute() else orig_dir / name)
    if not targets and not do_all:
        raise PipelineError("intake: no files given (use --all)", code=2)

    for src in targets:
        if not src.is_file():
            print(f"skip {src.name}: not found")
            continue
        reason = eligibility_reason(src)
        if reason:
            print(f"skip {src.name}: {reason}")
            continue
        original_hash = sha256_file(src)
        try:
            slug = unique_slug(ctx, slugify(src.name), original_hash)
        except PipelineError as e:
            print(f"skip {src.name}: {e}")
            continue
        ops = Ops(ctx.dry)
        scratch = ctx.root / SCRATCH_DIR["first"] / slug
        backup = ctx.root / BACKUP / slug
        ops.mkdir(scratch)
        lock = acquire_lock(scratch, ctx.dry)
        try:
            ops.mkdir(backup)
            ops.backup_put(src, backup, src.name)
            initial = milestone_name(slug, "first", "initial",
                                     ext=src.suffix.lower().lstrip("."))
            ops.safe_copy(src, scratch, initial)
            man = new_manifest(slug, src.name, original_hash)
            add_transition(
                man, "INTAKE",
                src=f"{ORIGINALS}/{src.name}",
                dst="{}/{}/{}".format(SCRATCH_DIR["first"], slug, initial),
                sha_in=original_hash, sha_out=original_hash)
            ops.write_json(scratch / "manifest.json", man)
            ops.write_json(backup / "manifest.json", man)
            ops.delete(src)
            ctx.log(slug, "INTAKE", ORIGINALS, SCRATCH_DIR["first"],
                    original_hash[:12])
        finally:
            release_lock(lock)
        _emit(ctx, ops, f"intake {src.name} -> {slug}")
    refresh_state(ctx)
    return 0


# ---------------------------------------------------------------- start-stage (T2)

def cmd_start_stage(ctx, slug, pick_next):
    if pick_next:
        candidates = []
        for stage in STAGES[:-1]:
            base = ctx.root / DONE_DIR[stage]
            if base.is_dir():
                for child in base.iterdir():
                    if child.is_dir():
                        candidates.append((child.stat().st_mtime, child.name))
        if not candidates:
            raise PipelineError("start-stage --next: nothing in a Done stage", code=2)
        slug = sorted(candidates)[0][1]
    done_stage, done_folder = find_done(ctx, slug)
    if done_stage is None:
        raise PipelineError(f"start-stage: {slug} not in any Done folder", code=2)
    if done_stage == "last":
        raise PipelineError(
            f"start-stage: {slug} is in End Review (use finalize/reject)", code=2)
    s_stage, s_folder = find_scratch(ctx, slug)
    if s_stage is not None:
        raise PipelineError(
            f"start-stage: {slug} already in {SCRATCH_DIR[s_stage]}", code=2)
    next_stage = STAGES[STAGES.index(done_stage) + 1]
    scratch = ctx.root / SCRATCH_DIR[next_stage] / slug
    ops = Ops(ctx.dry)
    ops.mkdir(scratch)
    lock = acquire_lock(scratch, ctx.dry)
    try:
        initial_name = milestone_name(slug, next_stage, "initial")
        new_initial_hash = None
        for p in sorted(done_folder.iterdir()):
            m = parse_milestone(p.name) if p.is_file() else None
            if not m or m["slug"] != slug:
                continue
            if m["stage"] == done_stage and m["phase"] == "done":
                new_initial_hash = ops.safe_copy(p, scratch, initial_name)
            else:
                ops.safe_copy(p, scratch, p.name)
        if new_initial_hash is None:
            raise PipelineError(
                f"start-stage: {slug} has no _{done_stage}done milestone",
                code=2)
        backup = ctx.root / BACKUP / slug
        ops.mkdir(backup)
        if not ctx.dry:
            ops.backup_put(scratch / initial_name, backup, initial_name)
        man = load_manifest(done_folder) or new_manifest(slug, slug, new_initial_hash)
        add_transition(
            man, START_OP[next_stage],
            src=f"{DONE_DIR[done_stage]}/{slug}",
            dst=f"{SCRATCH_DIR[next_stage]}/{slug}/{initial_name}",
            sha_in=new_initial_hash, sha_out=new_initial_hash)
        ops.write_json(scratch / "manifest.json", man)
        ctx.log(slug, START_OP[next_stage], DONE_DIR[done_stage],
                SCRATCH_DIR[next_stage], new_initial_hash[:12])
    finally:
        release_lock(lock)
    _emit(ctx, ops, f"start-stage {slug} -> {next_stage}")
    refresh_state(ctx)
    return 0


# ---------------------------------------------------------------- save-working (T3)

def cmd_save_working(ctx, slug, from_path, adopt, tool, params_json):
    stage, folder = find_scratch(ctx, slug)
    if stage is None:
        raise PipelineError(f"save-working: {slug} not in any scratch", code=2)
    params = None
    if params_json:
        try:
            params = json.loads(params_json)
        except ValueError:
            raise PipelineError("save-working: --params is not valid JSON", code=2)
    ops = Ops(ctx.dry)
    lock = acquire_lock(folder, ctx.dry)
    try:
        n = (scratch_workings(folder, slug, stage) or [(0, None)])[-1][0] + 1
        target_name = milestone_name(slug, stage, "working", ver=n)
        if adopt:
            candidates = [
                p for p in folder.iterdir()
                if p.is_file() and p.name not in SIDECAR_NAMES
                and p.suffix.lower() in IMAGE_EXTS
                and parse_milestone(p.name) is None]
            if not candidates:
                raise PipelineError(
                    f"save-working --adopt: no unparsed image file in {folder}",
                    code=2)
            src = max(candidates, key=lambda p: p.stat().st_mtime)
            sha = sha256_file(src)
            ops.rename(src, folder / target_name)
        else:
            src = Path(from_path)
            if not src.is_file():
                raise PipelineError(f"save-working: missing --from file {src}",
                                    code=2)
            sha = ops.safe_copy(src, folder, target_name)
        man = load_manifest(folder)
        if man is not None:
            add_transition(
                man, "SAVE_WORKING",
                actor=(f"tool:{tool}") if tool else "operator",
                tool=tool, params=params, src=str(src),
                dst=f"{SCRATCH_DIR[stage]}/{slug}/{target_name}",
                sha_in=sha, sha_out=sha)
            ops.write_json(folder / "manifest.json", man)
        ctx.log(slug, "SAVE_WORKING", SCRATCH_DIR[stage], SCRATCH_DIR[stage],
                sha[:12], actor=(f"tool:{tool}") if tool else "operator")
    finally:
        release_lock(lock)
    _emit(ctx, ops, f"save-working {slug} v{n:02d}")
    refresh_state(ctx)
    return 0


# ---------------------------------------------------------------- submit (T4)

def cmd_submit(ctx, slug):
    stage, folder = find_scratch(ctx, slug)
    if stage is None:
        raise PipelineError(f"submit: {slug} not in any scratch", code=2)
    needauth = folder / milestone_name(slug, stage, "needauth")
    if needauth.exists():
        raise PipelineError(f"submit: {slug} already submitted", code=2)
    workings = scratch_workings(folder, slug, stage)
    if not workings:
        raise PipelineError(f"submit: {slug} has no working file", code=2)
    ops = Ops(ctx.dry)
    lock = acquire_lock(folder, ctx.dry)
    try:
        _, src = workings[-1]
        sha = sha256_file(src)
        ops.rename(src, needauth)
        man = load_manifest(folder)
        if man is not None:
            add_transition(man, "SUBMIT", src=src.name, dst=needauth.name,
                           sha_in=sha, sha_out=sha)
            ops.write_json(folder / "manifest.json", man)
        ctx.log(slug, "SUBMIT", SCRATCH_DIR[stage], SCRATCH_DIR[stage], sha[:12])
    finally:
        release_lock(lock)
    _emit(ctx, ops, f"submit {slug}")
    refresh_state(ctx)
    return 0


# ---------------------------------------------------------------- reject (T4r/T7r)

def cmd_reject(ctx, slug, note, stage_flag):
    if stage_flag == "last" and (ctx.root / DONE_DIR["last"] / slug).is_dir():
        return _end_review_reject(ctx, slug, note)
    stage, folder = find_scratch(ctx, slug)
    if stage is None:
        raise PipelineError(f"reject: {slug} not in any scratch", code=2)
    needauth = folder / milestone_name(slug, stage, "needauth")
    if not needauth.exists():
        raise PipelineError(f"reject: {slug} has nothing submitted", code=2)
    ops = Ops(ctx.dry)
    lock = acquire_lock(folder, ctx.dry)
    try:
        sha = sha256_file(needauth)
        for _attempt in range(1000):
            n = (scratch_workings(folder, slug, stage) or [(0, None)])[-1][0] + 1
            target = folder / milestone_name(slug, stage, "working", ver=n)
            try:
                ops.rename(needauth, target)
                break
            except FileExistsError:
                continue  # FM-05: rescan and retry with the new max
        man = load_manifest(folder)
        if man is not None:
            add_transition(man, "REJECT", src=needauth.name, dst=target.name,
                           sha_in=sha, sha_out=sha, note=note)
            ops.write_json(folder / "manifest.json", man)
        ctx.log(slug, "REJECT", SCRATCH_DIR[stage], SCRATCH_DIR[stage],
                sha[:12], note=note)
    finally:
        release_lock(lock)
    _emit(ctx, ops, f"reject {slug}")
    refresh_state(ctx)
    return 0


def _end_review_reject(ctx, slug, note):
    """T7r: demote from 8.End Review back to 7.Last Scratch (operator-enabled)."""
    review = ctx.root / DONE_DIR["last"] / slug
    scratch = ctx.root / SCRATCH_DIR["last"] / slug
    ops = Ops(ctx.dry)
    lock = acquire_lock(review, ctx.dry)
    try:
        ops.mkdir(scratch)
        lastdone = review / milestone_name(slug, "last", "done")
        if not lastdone.exists():
            raise PipelineError(f"reject --stage last: {slug} has no _lastdone",
                                code=2)
        n = (scratch_workings(scratch, slug, "last") or [(0, None)])[-1][0] + 1
        sha = sha256_file(lastdone)
        ops.safe_copy(lastdone, scratch,
                      milestone_name(slug, "last", "working", ver=n),
                      delete_src=True)
        for p in sorted(review.iterdir()):
            m = parse_milestone(p.name) if p.is_file() else None
            if m and m["slug"] == slug:
                ops.safe_copy(p, scratch, p.name, delete_src=True)
        man = load_manifest(review)
        if man is not None:
            add_transition(man, "REJECT", src="{}/{}".format(DONE_DIR["last"], slug),
                           dst="{}/{}".format(SCRATCH_DIR["last"], slug),
                           sha_in=sha, sha_out=sha, note=note)
            ops.write_json(scratch / "manifest.json", man)
            ops.delete(review / "manifest.json")
        release_lock(lock)
        lock = None
        _gc_folder(ctx, ops, review)
        ctx.log(slug, "REJECT", DONE_DIR["last"], SCRATCH_DIR["last"],
                sha[:12], note=note)
    finally:
        release_lock(lock)
    _emit(ctx, ops, f"end-review reject {slug}")
    refresh_state(ctx)
    return 0


# ---------------------------------------------------------------- approve (T5/T6)

def _gc_folder(ctx, ops, folder, force=False):
    """FM-13 scratch/review GC: delete only grammar files + known temp files."""
    if ctx.dry:
        ops.note(f"gc {folder}")
        return True
    residue = False
    for p in sorted(folder.iterdir()):
        name = p.name
        if p.is_dir():
            residue = True
            continue
        if (name in SIDECAR_NAMES or name.endswith(".part")
                or parse_milestone(name) or force):
            ops.delete(p)
        else:
            residue = True
    if residue and not force:
        print(f"SCRATCH_RESIDUE: {folder} kept (non-pipeline files remain)")
        return False
    ops.rmdir(folder)
    return True


def _gc_prior_done(ctx, ops, slug, prior_folder, current_folder):
    """FM-02: GC Done N only after every file hash-verifies in Done N+1."""
    current_hashes = {sha256_file(p) for p in current_folder.iterdir()
                      if p.is_file() and parse_milestone(p.name)}
    for p in sorted(prior_folder.iterdir()):
        if p.is_file() and parse_milestone(p.name):
            if sha256_file(p) not in current_hashes:
                return False
    if ctx.dry:
        ops.note(f"gc-done {prior_folder}")
        return True
    for p in sorted(prior_folder.iterdir()):
        if p.is_file():
            ops.delete(p)
    ops.rmdir(prior_folder)
    ctx.log(slug, "GC_DONE", prior_folder.parent.name, current_folder.parent.name,
            "0" * 12)
    return True


def _latest_gate_audit(man, stage):
    """The most recent gate verdict recorded for `stage`'s milestone, or None.

    Gate verdicts ride in an ANNOTATE transition's `audit` slot (cmd_annotate),
    never at manifest top level. The scan stops at the transition that OPENED
    this milestone so a verdict earned by an earlier stage can never be
    misreported as this stage's.
    """
    entry_op = "INTAKE" if stage == "first" else START_OP[stage]
    for t in reversed(man.get("transitions", [])):
        if t.get("op") == entry_op:
            break
        audit = t.get("audit")
        if isinstance(audit, dict) and "verdict" in audit:
            return audit
    return None


def _approval_record(man, stage):
    """The honest gate record for a promotion out of `stage`.

    Approving over a FAIL stays ALLOWED - it is an operator judgement, and
    refusing it would wedge the operator's own workflow. What must never happen
    is that override looking identical to an approval over a clean PASS, so the
    three outcomes are written distinctly and greppably: an approval over a
    clean pass, an override, and no verdict on record at all (the legacy
    pre-audit case, which is NOT the same claim as "it passed").
    """
    audit = _latest_gate_audit(man, stage)
    if audit is None:
        return {"gate_check": "no_audit", "override": False, "gate": None,
                "verdict": None, "reasons": []}
    verdict = audit.get("verdict")
    reasons = list(audit.get("reasons") or [])
    clean = verdict == "PASS" and not reasons
    return {
        "gate_check": "pass" if clean else "override",
        "override": not clean,
        "gate": audit.get("gate"),
        "verdict": verdict,
        "reasons": reasons,
    }


def _complete_approve(ctx, ops, slug, stage, folder, done_src_name, force,
                      op_name=None):
    done_dir = ctx.root / DONE_DIR[stage] / slug
    done_name = milestone_name(slug, stage, "done")
    ops.mkdir(done_dir)
    sha_done = None
    for p in sorted(folder.iterdir()):
        m = parse_milestone(p.name) if p.is_file() else None
        if not m or m["slug"] != slug:
            continue
        if p.name == done_src_name:
            sha_done = ops.safe_copy(p, done_dir, done_name)
        elif m["phase"] == "initial":
            ops.safe_copy(p, done_dir, p.name)
        # working/needauth files are intentionally discarded per scheme
    if sha_done is None:
        raise PipelineError(f"approve: {slug} missing {done_src_name}", code=2)
    man = load_manifest(folder)
    if man is not None:
        add_transition(man, op_name or APPROVE_OP[stage],
                       src=f"{SCRATCH_DIR[stage]}/{slug}/{done_src_name}",
                       dst=f"{DONE_DIR[stage]}/{slug}/{done_name}",
                       sha_in=sha_done, sha_out=sha_done,
                       audit={"approval": _approval_record(man, stage)})
        ops.write_json(done_dir / "manifest.json", man)
    _gc_folder(ctx, ops, folder, force=force)
    if stage != "first":
        prior = STAGES[STAGES.index(stage) - 1]
        prior_folder = ctx.root / DONE_DIR[prior] / slug
        if prior_folder.is_dir() and not ctx.dry:
            if not _gc_prior_done(ctx, ops, slug, prior_folder, done_dir):
                print(f"STALE_DONE: {prior_folder} kept (hash not verified downstream)")
    ctx.log(slug, op_name or APPROVE_OP[stage], SCRATCH_DIR[stage],
            DONE_DIR[stage], sha_done[:12])
    return sha_done


def cmd_approve(ctx, slug, force):
    stage, folder = find_scratch(ctx, slug)
    if stage is None:
        raise PipelineError(f"approve: {slug} not in any scratch", code=2)
    needauth = folder / milestone_name(slug, stage, "needauth")
    done_local = folder / milestone_name(slug, stage, "done")
    if not needauth.exists() and not done_local.exists():
        raise PipelineError(f"approve: {slug} has nothing submitted", code=2)
    ops = Ops(ctx.dry)
    lock = acquire_lock(folder, ctx.dry)
    try:
        if needauth.exists():
            if ctx.dry:
                ops.note(f"rename {needauth} -> {done_local}")
                done_src = needauth.name  # plan against the pre-rename file
            else:
                ops.rename(needauth, done_local)
                done_src = done_local.name
        else:
            done_src = done_local.name  # APPROVED_PENDING_MOVE resume
        _complete_approve(ctx, ops, slug, stage, folder, done_src, force)
    finally:
        release_lock(lock)
    _emit(ctx, ops, f"approve {slug} ({stage})")
    refresh_state(ctx)
    return 0


# ---------------------------------------------------------------- finalize (T7)

def _next_free_sequential(deliver_dir):
    taken = set()
    for p in deliver_dir.iterdir():
        m = re.match(r"^([0-9]{3,})\.png$", p.name)
        if m:
            taken.add(int(m.group(1)))
    n = 1
    while n in taken:
        n += 1
    return n


def _deliver(ctx, ops, slug, src, deliver_dir, sequential):
    """FM-12: .part + fsync + hash-verify + atomic rename; number at rename time."""
    deliver_dir = Path(deliver_dir)
    if not deliver_dir.is_dir():
        raise PipelineError(f"finalize: --deliver dir missing: {deliver_dir}",
                            code=2)
    src_hash = sha256_file(src)
    for _attempt in range(1000):
        if sequential:
            name = f"{_next_free_sequential(deliver_dir):03d}.png"
        else:
            name = slug + ".png"
        if ctx.dry:
            ops.note(f"deliver {src} -> {deliver_dir / name}")
            return name
        part = deliver_dir / (name + ".part")
        with open(src, "rb") as fi, open(part, "wb") as fo:
            while True:
                chunk = fi.read(1 << 20)
                if not chunk:
                    break
                fo.write(chunk)
            fo.flush()
            os.fsync(fo.fileno())
        if sha256_file(part) != src_hash:
            part.unlink()
            raise PipelineError("deliver: copy verification failed", code=3)
        try:
            ops.rename(part, deliver_dir / name)
            return name
        except FileExistsError:
            part.unlink()
            if not sequential:
                if sha256_file(deliver_dir / name) == src_hash:
                    return name
                raise PipelineError(
                    f"deliver: {name} exists with different content", code=3)
    raise PipelineError("deliver: could not find a free sequential name", code=3)


def cmd_finalize(ctx, slug, deliver_dir, sequential, audit_json):
    review = ctx.root / DONE_DIR["last"] / slug
    if not review.is_dir():
        raise PipelineError(f"finalize: {slug} not in 8.End Review", code=2)
    lastdone = review / milestone_name(slug, "last", "done")
    if not lastdone.exists():
        raise PipelineError(f"finalize: {slug} has no _lastdone", code=2)
    audit = None
    if audit_json:
        try:
            audit = json.loads(Path(audit_json).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise PipelineError("finalize: cannot read --audit-json", code=2)
    ops = Ops(ctx.dry)
    backup = ctx.root / BACKUP / slug
    lock = acquire_lock(review, ctx.dry)
    try:
        ops.mkdir(backup)
        sha = ops.backup_put(lastdone, backup, lastdone.name)
        delivered = None
        if deliver_dir:
            delivered = _deliver(ctx, ops, slug, lastdone, deliver_dir, sequential)
            ctx.log(slug, "DELIVER_PICTURES", DONE_DIR["last"], str(deliver_dir),
                    sha[:12], note=delivered)
        man = load_manifest(review)
        if man is not None:
            if delivered:
                man["delivered_as"] = delivered
            # finalize promotes out of End Review, so it carries the same
            # override risk as approve; the supplied end-review audit rides
            # alongside the record rather than being replaced by it.
            if isinstance(audit, dict):
                final_audit = dict(audit)
            elif audit is None:
                final_audit = {}
            else:
                final_audit = {"end_review": audit}
            # An operator payload of its own carrying "approval" would other-
            # wise be dropped by the line below, which is the same silent loss
            # this record exists to prevent.
            if "approval" in final_audit:
                final_audit["supplied_approval"] = final_audit["approval"]
            final_audit["approval"] = _approval_record(man, "last")
            add_transition(man, "FINALIZE",
                           src="{}/{}/{}".format(DONE_DIR["last"], slug, lastdone.name),
                           dst=f"{BACKUP}/{slug}/{lastdone.name}",
                           sha_in=sha, sha_out=sha, audit=final_audit,
                           note=(f"delivered as {delivered}") if delivered else None)
            ops.write_json(backup / "manifest.json", man)
        # operator correction: verify every milestone landed in 9, then delete 8
        if not ctx.dry:
            backup_hashes = {sha256_file(p) for p in backup.iterdir()
                             if p.is_file() and p.name != "manifest.json"}
            for p in sorted(review.iterdir()):
                if p.is_file() and parse_milestone(p.name):
                    if sha256_file(p) not in backup_hashes:
                        raise PipelineError(
                            f"finalize: {p.name} not hash-verified in backup",
                            code=3)
        release_lock(lock)
        lock = None
        _gc_folder(ctx, ops, review, force=False)
        ctx.log(slug, "FINALIZE", DONE_DIR["last"], BACKUP, sha[:12],
                note=(f"delivered as {delivered}") if delivered else None)
    finally:
        release_lock(lock)
    _emit(ctx, ops, f"finalize {slug}")
    refresh_state(ctx)
    return 0


# ---------------------------------------------------------------- annotate

def cmd_annotate(ctx, slug, source_url, metrics_obj, tool):
    """Record provenance (source_url) and/or G1 metrics into manifest.json.

    Locates the slug in scratch, then Done, then 9.Image Backup. Sets the
    top-level man["source_url"] when --source-url is given, and appends an
    ANNOTATE transition carrying the metrics in its `audit` slot (the same
    field cmd_finalize uses) when --metrics is given.

    Behavior choice: an ANNOTATE transition is ALWAYS appended whenever the
    command mutates - so a source_url-only call still records one ANNOTATE
    transition, and that transition's `audit` is None. Metrics ride in `audit`
    only when --metrics is supplied; no new top-level field is invented.
    """
    if source_url is None and metrics_obj is None:
        raise PipelineError(
            "annotate: nothing to do (give --source-url and/or --metrics)",
            code=2)
    stage, folder = find_scratch(ctx, slug)
    if folder is None:
        stage, folder = find_done(ctx, slug)
    if folder is None:
        backup = ctx.root / BACKUP / slug
        if backup.is_dir():
            folder = backup
    if folder is None:
        raise PipelineError(
            f"annotate: {slug} not found in any stage/backup", code=2)
    man = load_manifest(folder)
    if man is None:
        raise PipelineError(f"annotate: {slug} has no manifest.json", code=2)
    actor = f"tool:{tool}" if tool else "operator"
    ops = Ops(ctx.dry)
    lock = acquire_lock(folder, ctx.dry)
    try:
        if source_url is not None:
            man["source_url"] = source_url
        add_transition(man, "ANNOTATE", actor=actor, tool=tool,
                       audit=metrics_obj, note="provenance/metrics annotation")
        ops.write_json(folder / "manifest.json", man)
        ctx.log(slug, "ANNOTATE", folder.parent.name, folder.parent.name,
                "0" * 12, actor=actor)
    finally:
        release_lock(lock)
    _emit(ctx, ops, f"annotate {slug}")
    refresh_state(ctx)
    return 0


# ---------------------------------------------------------------- scan/status/verify

def cmd_scan(ctx, verify, fix_resumable, as_json):
    world = scan_tree(ctx, verify=verify)
    if fix_resumable:
        _fix_resumable(ctx, world)
        world = scan_tree(ctx, verify=verify)
    write_state(ctx, world)
    if as_json:
        print(json.dumps(world, indent=2))
    else:
        c = world["counts"]
        print("scan: {}".format(" ".join("{}={}".format(*kv) for kv in sorted(c.items()))))
        for a in world["anomalies"]:
            print("anomaly {} slug={} {}".format(a["class"], a["slug"], a["detail"]))
    if any(a["class"] == "HASH_MISMATCH" for a in world["anomalies"]):
        return 3
    return 1 if world["anomalies"] else 0


def _fix_resumable(ctx, world):
    for a in world["anomalies"]:
        if not a.get("resumable"):
            continue
        cls, slug = a["class"], a["slug"]
        if cls == "STALE_PART":
            Path(a["detail"]).unlink(missing_ok=True)
            print("fixed STALE_PART: {}".format(a["detail"]))
        elif cls == "APPROVED_PENDING_MOVE":
            folder = Path(a["detail"])
            stage = next(s for s in STAGES
                         if SCRATCH_DIR[s] == folder.parent.name)
            ops = Ops(dry=False)
            lock = acquire_lock(folder, dry=False)
            try:
                _complete_approve(ctx, ops, slug, stage, folder,
                                  milestone_name(slug, stage, "done"),
                                  force=False, op_name="RECOVER")
            finally:
                release_lock(lock)
            print(f"fixed APPROVED_PENDING_MOVE: {slug}")
        elif cls == "STALE_DONE":
            prior = Path(a["detail"].split(" superseded by ")[0])
            current = Path(a["detail"].split(" superseded by ")[1])
            ops = Ops(dry=False)
            if _gc_prior_done(ctx, ops, slug, prior, current):
                print(f"fixed STALE_DONE: {prior}")
            else:
                print(f"STALE_DONE kept (hash not verified downstream): {prior}")
        elif cls == "SCRATCH_RESIDUE":
            folder = Path(str(a["detail"]).split(": ")[0])
            if folder.is_dir():
                ops = Ops(dry=False)
                _gc_folder(ctx, ops, folder)
                print(f"fixed empty scratch remnant: {folder}")


def cmd_status(ctx, slug, as_json):
    world = scan_tree(ctx, slug_filter=slug)
    if as_json:
        print(json.dumps(world["images"], indent=2))
        return 0
    if slug:
        info = world["images"].get(slug)
        if not info:
            raise PipelineError(f"status: unknown slug {slug}", code=2)
        print(f"{slug}  {info['state']}  {info['substate'] or '-'}  "
              f"w{info['working_max']}  {info['last_op_ts'] or '-'}")
        for f in info["files"]:
            print(f"  {f['name']} ({f['bytes']} bytes)")
        _, folder = find_scratch(ctx, slug)
        if folder is None:
            _, folder = find_done(ctx, slug)
        if folder is None and (ctx.root / BACKUP / slug).is_dir():
            folder = ctx.root / BACKUP / slug
        man = load_manifest(folder) if folder else None
        if man:
            for t in man["transitions"][-5:]:
                print("  {} {} {}".format(t["ts"], t["op"], t.get("dst") or "-"))
    else:
        for s, info in sorted(world["images"].items()):
            print(f"{s:<40} {info['state']:<14} {info['substate'] or '-':<22} "
                  f"w{info['working_max']:<3} {info['last_op_ts'] or '-'}")
        print(f"pending intake: {world['counts']['pending_intake']}")
    return 0


def cmd_verify(ctx, slug):
    world = scan_tree(ctx, verify=True, slug_filter=slug)
    mismatches = [a for a in world["anomalies"] if a["class"] == "HASH_MISMATCH"]
    for a in mismatches:
        print("HASH_MISMATCH {} {}".format(a["slug"], a["detail"]))
    if mismatches:
        return 3
    print(f"verify: ok ({len(world['images'])} image(s) checked)")
    return 0


def _emit(ctx, ops, title):
    if ctx.dry:
        print(f"DRY-RUN {title}")
        for line in ops.planned:
            print("  " + line)
    else:
        print(title)


# ---------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(
        prog="lw_pipeline",
        description="Legion Wallpaper staged-folder pipeline core")
    p.add_argument("--root", default=str(DEFAULT_ROOT),
                   help=f"pipeline root (default {DEFAULT_ROOT})")
    p.add_argument("--json", action="store_true", help="machine output")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="rebuild world state from the filesystem")
    s.add_argument("--verify", action="store_true")
    s.add_argument("--fix-resumable", action="store_true")

    s = sub.add_parser("status", help="human view of pipeline state")
    s.add_argument("slug", nargs="?")
    s.add_argument("--stage")

    s = sub.add_parser("intake", help="T1: 0.Originals -> first scratch")
    s.add_argument("files", nargs="*")
    s.add_argument("--all", action="store_true")
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("start-stage", help="T2: Done N -> Scratch N+1")
    s.add_argument("slug", nargs="?")
    s.add_argument("--next", action="store_true")
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("save-working", help="T3: register next _working_##")
    s.add_argument("slug")
    s.add_argument("--from", dest="from_path")
    s.add_argument("--adopt", action="store_true")
    s.add_argument("--tool")
    s.add_argument("--params")
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("submit", help="T4: latest working -> _needauth")
    s.add_argument("slug")
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("approve", help="T5/T6: needauth -> done, set -> Done")
    s.add_argument("slug")
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("reject", help="T4r: needauth -> next working; --stage last = T7r")
    s.add_argument("slug")
    s.add_argument("--note")
    s.add_argument("--stage", choices=["last"])
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("finalize", help="T7: End Review pass -> 9.Image Backup")
    s.add_argument("slug")
    s.add_argument("--deliver", metavar="DIR")
    s.add_argument("--rename-sequential", action="store_true")
    s.add_argument("--audit-json")
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser(
        "annotate",
        help="record provenance (source_url) and/or G1 metrics into manifest.json")
    s.add_argument("slug")
    s.add_argument("--source-url")
    s.add_argument("--metrics", help="inline JSON, or @path to a JSON file")
    s.add_argument("--tool")
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("verify", help="re-hash and diff vs manifests (read-only)")
    s.add_argument("slug", nargs="?")
    s.add_argument("--all", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    dry = bool(getattr(args, "dry_run", False))
    ctx = Ctx(args.root, dry=dry)
    try:
        if args.cmd == "scan":
            return cmd_scan(ctx, args.verify, args.fix_resumable, args.json)
        if args.cmd == "status":
            return cmd_status(ctx, args.slug, args.json)
        if args.cmd == "intake":
            return cmd_intake(ctx, args.files, args.all)
        if args.cmd == "start-stage":
            if not args.slug and not args.next:
                raise PipelineError("start-stage: give a slug or --next", code=2)
            return cmd_start_stage(ctx, args.slug, args.next)
        if args.cmd == "save-working":
            if bool(args.from_path) == bool(args.adopt):
                raise PipelineError(
                    "save-working: exactly one of --from/--adopt", code=2)
            return cmd_save_working(ctx, args.slug, args.from_path, args.adopt,
                                    args.tool, args.params)
        if args.cmd == "submit":
            return cmd_submit(ctx, args.slug)
        if args.cmd == "approve":
            return cmd_approve(ctx, args.slug, args.force)
        if args.cmd == "reject":
            return cmd_reject(ctx, args.slug, args.note, args.stage)
        if args.cmd == "finalize":
            return cmd_finalize(ctx, args.slug, args.deliver,
                                args.rename_sequential, args.audit_json)
        if args.cmd == "annotate":
            metrics_obj = None
            if args.metrics is not None:
                raw = args.metrics
                try:
                    if raw.startswith("@"):
                        raw = Path(raw[1:]).read_text(encoding="utf-8")
                    metrics_obj = json.loads(raw)
                except (OSError, ValueError):
                    raise PipelineError(
                        "annotate: --metrics is not valid JSON (or file unreadable)",
                        code=2)
            return cmd_annotate(ctx, args.slug, args.source_url, metrics_obj,
                                args.tool)
        if args.cmd == "verify":
            return cmd_verify(ctx, args.slug)
        raise PipelineError("unknown command", code=2)
    except PipelineError as e:
        print(f"error: {e}")
        return e.code


if __name__ == "__main__":
    sys.exit(main())
