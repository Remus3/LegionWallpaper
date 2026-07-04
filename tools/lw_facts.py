# arch: live LW state probe | section=tools | frozen=no
"""lw_facts.py - print live ground truth for the Legion Wallpaper project.

Designed to be invoked as a Claude Code SessionStart hook on Legion.
Output (markdown to stdout) is injected as additional context, so the
session starts with current state instead of relying on possibly-stale
memory entries.

Probes (all wrapped in their own try/except; total wall-clock is capped
by a shared budget well under the 8s hook timeout):
  - git: current branch, dirty file count, last 3 commits one line each.
  - Scheduled tasks matching LW-* via schtasks, state for each
    ("none registered yet" fallback - do NOT register tasks from here).
  - ops/runtime/health.json summary if the file exists, else
    "no runtime yet (product TBD)".
  - Pipeline digest: per-stage counts under images/, loose files in
    0.Originals awaiting intake, needs-attention count from
    ops/runtime/pipeline_state.json, PIPELINE_LOG.md last line.
    Degrades to "pipeline idle" when nothing is staged or probing fails.
  - WAKEUP_NOTES.md first non-empty line (session-notes freshness hint).

Cheap and idempotent. A single failing probe can never break session
start. Caller (the hook) gets stdout; non-zero exit just means
"couldn't probe" and is non-blocking.

Run manually any time:
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/lw_facts.py
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import time
from pathlib import Path

# SessionStart hook runs under windowless pythonw.exe; a console child would
# otherwise get a fresh console allocated - an on-screen + taskbar flash.
# CREATE_NO_WINDOW suppresses it (Windows-only; 0 elsewhere).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_ROOT = Path(__file__).resolve().parent.parent
_HEALTH = _ROOT / "ops" / "runtime" / "health.json"
_WAKEUP = _ROOT / "WAKEUP_NOTES.md"

# Shared wall-clock budget (seconds). The hook timeout is 8s; every
# subprocess gets min(its own cap, whatever budget remains), so the
# script as a whole finishes well under the hook limit even if some
# probe hangs to its cap.
_BUDGET_S = 6.0
_T0 = time.monotonic()


def _remaining() -> float:
    return _BUDGET_S - (time.monotonic() - _T0)


def _run(cmd: list[str], cap: float = 2.0) -> str | None:
    """Run a command; return stripped stdout on success else None. Never raises."""
    timeout = min(cap, _remaining())
    if timeout <= 0.1:
        return None
    try:
        p = subprocess.run(
            cmd, capture_output=True, timeout=timeout, text=True,
            encoding="utf-8", errors="replace", cwd=str(_ROOT),
            creationflags=_NO_WINDOW,
        )
        if p.returncode == 0:
            return p.stdout.strip()
    except Exception:  # noqa: BLE001 - a probe must never break the hook
        pass
    return None


# -- probes (each returns markdown lines; each is exception-proof) --------

def _git_lines(anomalies: list[str]) -> list[str]:
    try:
        branch = _run(["git", "branch", "--show-current"])
        if branch is None:
            return ["- git: not a git repo yet (or git unavailable)"]
        status = _run(["git", "status", "--porcelain"])
        dirty = len(status.splitlines()) if status else 0
        lines = [f"- git: branch={branch or '?'} dirty_files={dirty}"]
        log = _run(["git", "log", "--oneline", "-3"])
        if log:
            lines.append("- last 3 commits:")
            for ln in log.splitlines():
                lines.append(f"  - {ln}")
        else:
            lines.append("- last 3 commits: none yet (unborn branch)")
        return lines
    except Exception:  # noqa: BLE001
        anomalies.append("git probe crashed")
        return ["- git: probe failed"]


def _task_lines(anomalies: list[str]) -> list[str]:
    """LW-* scheduled tasks via schtasks CSV (documented convention: LW-*)."""
    try:
        out = _run(["schtasks", "/Query", "/FO", "CSV", "/NH"], cap=4.0)
        if out is None:
            return ["- scheduled tasks: probe unavailable"]
        rows: list[tuple[str, str]] = []
        for rec in csv.reader(io.StringIO(out)):
            if len(rec) < 3:
                continue
            name = rec[0].split("\\")[-1]
            if name.startswith("LW-"):
                rows.append((name, rec[2] or "?"))
        if not rows:
            return ["- scheduled tasks (LW-*): none registered yet"]
        lines = [f"- scheduled tasks ({len(rows)} LW-*):"]
        for name, state in sorted(set(rows)):
            lines.append(f"  - {name}: state={state}")
            if state.lower() == "disabled":
                anomalies.append(f"scheduled task {name} is Disabled")
        return lines
    except Exception:  # noqa: BLE001
        anomalies.append("schtasks probe crashed")
        return ["- scheduled tasks: probe failed"]


def _health_lines(anomalies: list[str]) -> list[str]:
    try:
        if not _HEALTH.is_file():
            return ["- runtime: no runtime yet (product TBD) - ops/runtime/health.json absent"]
        h = json.loads(_HEALTH.read_text(encoding="utf-8"))
        pid = h.get("pid")
        alive = h.get("alive")
        mode = h.get("mode") or "?"
        version = h.get("lw_version") or h.get("version") or "?"
        lines = [
            f"- runtime health.json: pid={pid} alive={alive} mode={mode} "
            f"version={version} (keys={len(h)})"
        ]
        if alive is False:
            anomalies.append(f"runtime not alive (pid={pid})")
        return lines
    except Exception:  # noqa: BLE001
        anomalies.append("ops/runtime/health.json exists but unreadable/invalid")
        return ["- runtime health.json: UNREADABLE"]


# Stage folders exactly per the pipeline contract (docs/research/
# PIPELINE_STATE_MACHINE.md). 0.Originals holds loose intake files; stages
# 1-9 hold per-image subfolders; reference_pictures is the non-pipeline
# reference corpus.
_STAGE_FOLDERS = (
    "0.Originals",
    "1.First Pass Scratch",
    "2.First Pass Done",
    "3.Cleaning Scratch",
    "4.Cleaning Done",
    "5.Final Scratch",
    "6.Final Done",
    "7.Last Scratch",
    "8.End Review",
    "9.Image Backup",
)


def _pipeline_state_lines(anomalies: list[str], state_path: Path) -> list[str]:
    """needs-attention summary from ops/runtime/pipeline_state.json."""
    try:
        if not state_path.is_file():
            return ["- pipeline_state.json: absent (no scan yet)"]
        state = json.loads(state_path.read_text(encoding="utf-8"))
        counts = state.get("counts") or {}
        need = counts.get("anomalies")
        if need is None:
            need = len(state.get("anomalies") or [])
        line = f"- pipeline_state.json: needs_attention={need}"
        ts = state.get("generated_ts")
        if ts:
            line += f" (scanned {ts})"
        if need:
            anomalies.append(f"pipeline needs attention: {need} anomalies in pipeline_state.json")
        return [line]
    except Exception:  # noqa: BLE001 - a probe must never break the hook
        anomalies.append("pipeline_state.json exists but unreadable/invalid")
        return ["- pipeline_state.json: UNREADABLE"]


def _pipeline_log_line(log_path: Path) -> list[str]:
    """Last non-empty line of PIPELINE_LOG.md (never raises)."""
    try:
        if not log_path.is_file():
            return ["- PIPELINE_LOG.md: not present yet"]
        last = ""
        for ln in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.strip():
                last = ln.strip()
        if last:
            return [f"- PIPELINE_LOG.md last: {last}"]
        return ["- PIPELINE_LOG.md: present but empty"]
    except Exception:  # noqa: BLE001
        return ["- PIPELINE_LOG.md: probe failed"]


def _pipeline_lines(anomalies: list[str], root: Path | None = None) -> list[str]:
    """Pipeline digest for the session-start hook.

    root is injectable for tests (defaults to the repo root); everything is
    derived from it: images/ tree, ops/runtime/pipeline_state.json,
    PIPELINE_LOG.md. Cheap (one shallow scandir per stage folder) and
    exception-proof; degrades to "pipeline idle".
    """
    if root is None:
        root = _ROOT
    try:
        images = root / "images"
        lines: list[str] = []
        if not images.is_dir():
            lines.append("- pipeline idle - images/ tree not present")
        else:
            # 0.Originals: loose files awaiting intake ("new since last
            # intake" - intake removes files, so presence = pending).
            awaiting = 0
            orig = images / _STAGE_FOLDERS[0]
            if orig.is_dir():
                awaiting = sum(
                    1 for p in orig.iterdir() if p.is_file() and p.name != ".gitkeep"
                )
            # Stages 1-9: per-image subfolder counts.
            stage_counts: list[tuple[str, int]] = []
            staged_total = 0
            for stage in _STAGE_FOLDERS[1:]:
                d = images / stage
                n = sum(1 for p in d.iterdir() if p.is_dir()) if d.is_dir() else 0
                stage_counts.append((stage, n))
                staged_total += n
            ref = images / "reference_pictures"
            ref_n = (
                sum(1 for p in ref.iterdir() if p.is_file() and p.name != ".gitkeep")
                if ref.is_dir()
                else 0
            )
            if awaiting == 0 and staged_total == 0 and ref_n == 0:
                lines.append("- pipeline idle - no files staged under images/")
            else:
                lines.append(f"- 0.Originals: {awaiting} loose files awaiting intake")
                lines.append(
                    "- stages: "
                    + " | ".join(f"{name}={n}" for name, n in stage_counts)
                )
                lines.append(f"- reference_pictures: {ref_n} files")
        lines.extend(
            _pipeline_state_lines(anomalies, root / "ops" / "runtime" / "pipeline_state.json")
        )
        lines.extend(_pipeline_log_line(root / "PIPELINE_LOG.md"))
        return lines
    except Exception:  # noqa: BLE001 - a probe must never break the hook
        anomalies.append("pipeline probe crashed")
        return ["- pipeline: probe failed (treat as pipeline idle)"]


def _wakeup_lines(anomalies: list[str]) -> list[str]:
    try:
        if not _WAKEUP.is_file():
            return ["- WAKEUP_NOTES.md: not present yet"]
        for ln in _WAKEUP.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.strip():
                return [f"- WAKEUP_NOTES.md first line: {ln.strip()}"]
        return ["- WAKEUP_NOTES.md: present but empty"]
    except Exception:  # noqa: BLE001
        anomalies.append("WAKEUP_NOTES.md unreadable")
        return ["- WAKEUP_NOTES.md: probe failed"]


def main() -> int:
    out: list[str] = []
    out.append("# LW live state (lw_facts.py)\n")
    out.append(f"_probed at {time.strftime('%Y-%m-%d %H:%M:%S')}_\n")

    anomalies: list[str] = []

    out.append("## Repo\n")
    out.extend(_git_lines(anomalies))

    out.append("\n## Scheduled tasks\n")
    out.extend(_task_lines(anomalies))

    out.append("\n## Runtime\n")
    out.extend(_health_lines(anomalies))

    out.append("\n## Pipeline\n")
    out.extend(_pipeline_lines(anomalies))

    out.append("\n## Session notes\n")
    out.extend(_wakeup_lines(anomalies))

    # -- Anomaly summary first if any (matches rc_facts.py output style) --
    if anomalies:
        head = "## ! Anomalies\n\n" + "\n".join(f"- {a}" for a in anomalies) + "\n\n"
        sys.stdout.write(head)
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
