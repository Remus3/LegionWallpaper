"""Fresh-interpreter import probe for the "stays torch-free" test family.

Several tools modules promise their heavy backends (torch / cv2 / diffusers /
onnxruntime / open_clip / controlnet_aux / scipy) are LAZY - imported inside
function bodies, never at module scope - so the module stays importable under
base python. The tests asserting that used to read the ambient `sys.modules`
of the pytest process:

    import tools.lw_gen_qa
    assert "torch" not in sys.modules

which only holds if nothing EARLIER in the session imported torch. Run the
file alone and it passes; run the full suite and an earlier test (or a PIL
plugin chain) has already pulled torch in, so the assertion fails on global
state that has nothing to do with the module under test. That is a false
failure, and worse, the check is vacuous in the other direction: if torch is
absent the assertion passes even when the module imports it, as long as some
other test imported it first.

Probing in a CLEAN interpreter tests the real property directly and is immune
to collection order. Cost is one interpreter spawn per probe (~0.2-0.5s).

Note the deliberate choice NOT to snapshot/restore sys.modules instead: torch
cannot be meaningfully un-imported (its C extensions stay loaded), and tearing
it out of sys.modules while other tests hold live references invites far
stranger failures than the one being fixed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Legion rule: every spawned subprocess suppresses the console window.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def probe_imports(module: str, candidates, after: str = "", timeout: int = 180):
    """Import `module` in a fresh interpreter; return which candidates loaded.

    module    - dotted name importable with REPO_ROOT on sys.path,
                e.g. "tools.lw_gen_qa".
    candidates- module names to look for in the child's sys.modules.
    after     - optional statement(s) run after the import and before the
                check, for probing that CALLING something also stays clean.
                The imported module is bound to its dotted name, so reference
                it fully (e.g. "tools.lw_gen_qa.laplacian_variance(...)").

    Raises AssertionError if the child cannot import the module at all - a
    broken probe must be loud, never silently "clean".
    """
    lines = [
        "import json, sys",
        f"sys.path.insert(0, {REPO_ROOT!r})",
        f"import {module}",
    ]
    if after:
        lines.append(after)
    lines.append(
        f"print('__PROBE__' + json.dumps("
        f"[m for m in {sorted(candidates)!r} if m in sys.modules]))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", "\n".join(lines)],
        capture_output=True, text=True, timeout=timeout,
        creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"import probe for {module} failed (exit {proc.returncode}):\n"
            f"{proc.stderr.strip()[-2000:]}"
        )
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("__PROBE__"):
            return json.loads(line[len("__PROBE__"):])
    raise AssertionError(
        f"import probe for {module} produced no result line.\n"
        f"stdout: {proc.stdout.strip()[-1000:]}\n"
        f"stderr: {proc.stderr.strip()[-1000:]}"
    )


def assert_import_free(module: str, banned, after: str = ""):
    """Assert importing `module` (then running `after`) loads none of `banned`."""
    leaked = probe_imports(module, banned, after=after)
    assert not leaked, (
        f"importing {module} pulled in {leaked}; these must stay lazy "
        f"(imported inside function bodies, not at module scope)"
    )
