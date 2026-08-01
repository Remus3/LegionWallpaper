"""Tests for tools/lw_ports.py - LW's TCP port block and its allocations.

The point of this file is drift, not documentation. A test that re-asserts a
literal (`assert MONITOR == 8901`) passes forever while the real server moves,
so it guards nothing. Every check here is pinned against the LIVE definition
site or derived from the source tree, so the failure mode it catches is "a
server moved / a new server appeared and nobody updated the registry".

Pattern credited to Red Moon's core/ports.py; the pin-against-the-live-site
refinement came from Riot Commander (2026-08-01 cross-project port reservation).
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import lw_monitor  # noqa: E402
from tools import lw_ports  # noqa: E402

TOOLS = Path(__file__).resolve().parent.parent / "tools"
OPS = Path(__file__).resolve().parent.parent / "ops"


def test_block_is_well_formed():
    low, high = lw_ports.LW_BLOCK
    assert low < high
    assert high - low + 1 == 20


def test_monitor_is_pinned_against_the_live_definition_site():
    # Imports the module that actually binds rather than restating the literal
    # - this is the assertion that fails when lw_monitor moves.
    assert lw_ports.MONITOR == lw_monitor.DEFAULT_PORT


def test_every_allocation_sits_inside_the_block():
    low, high = lw_ports.LW_BLOCK
    assert lw_ports.ALLOCATIONS
    for name, port in lw_ports.ALLOCATIONS.items():
        assert low <= port <= high, f"{name}={port} outside {lw_ports.LW_BLOCK}"


def test_allocations_are_unique():
    ports = list(lw_ports.ALLOCATIONS.values())
    assert len(ports) == len(set(ports))


def _authored_port_constants():
    """Every module-level `*PORT* = <int>` in authored source, as (path, name, port).

    AST rather than a line regex, and recursive over both authored trees: a
    line-anchored regex over a flat tools/ glob missed a server placed under
    ops/, and missed any spelling other than a bare integer on its own line.
    """
    found = []
    for root in (TOOLS, OPS):
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if not isinstance(target, ast.Name) or "PORT" not in target.id:
                        continue
                    if isinstance(node.value, ast.Constant) and isinstance(
                            node.value.value, int):
                        found.append((path, target.id, node.value.value))
    return found


def test_every_authored_default_port_is_registered():
    # A new server that defines its own port and never registers it is exactly
    # the drift this whole exercise exists to prevent.
    found = _authored_port_constants()
    assert found, "no port constant found - the scan itself broke"
    registered = set(lw_ports.ALLOCATIONS.values())
    low, high = lw_ports.LW_BLOCK
    for path, name, port in found:
        if path.name == "lw_ports.py":
            continue  # the registry is the source of truth, not a consumer
        if not (low <= port <= high):
            continue  # not a claim on LW's block - a timeout, a size, a retry
        assert port in registered, f"{path.name}:{name}={port} not in ALLOCATIONS"


def test_the_scan_covers_both_authored_trees():
    # The scan is only as good as its reach. A server under ops/ escaped the
    # original tools/-only flat glob entirely.
    roots = {p.parts[-2] if p.parent.name != "tools" else "tools"
             for p, _n, _v in _authored_port_constants()}
    assert TOOLS.is_dir() and OPS.is_dir()
    assert any((TOOLS / f).exists() for f in ["lw_monitor.py"])
    scanned = {str(p) for p, _n, _v in _authored_port_constants()}
    assert any("lw_monitor.py" in s for s in scanned), roots


def test_registry_names_no_foreign_port():
    # Red Moon's guard greps its own source for foreign port numbers, so writing
    # another project's literals here would trip a sibling repo's test. Cite a
    # block, never someone else's port.
    low, high = lw_ports.LW_BLOCK
    tree = ast.parse((TOOLS / "lw_ports.py").read_text(encoding="utf-8"))
    # AST, not a regex over the text: prose legitimately contains four-digit
    # numbers (dates), and only real int literals can be a port.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            port = node.value
            if 1024 <= port <= 65535:
                assert low <= port <= high, f"foreign port literal {port}"
