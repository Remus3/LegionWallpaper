"""Legion Wallpaper - the TCP port block LW owns, and what sits in it.

Three projects share the Legion machine and until 2026-08-01 none of them could
answer "which ports are mine" without grepping bind sites and hand-filtering
vendored noise. That is not academic: a sibling project came one step from
assigning itself a block that would have collided with LW's monitor, and it was
caught only because the operator asked it to read this tree first.

LW's reserved block is 8900-8919. Anything in LW that binds a socket takes its
port from ALLOCATIONS below, and `tests/test_lw_ports.py` pins each entry
against the module that actually binds - not against a restated literal, which
would pass forever while the real server moved.

Cross-project registry (all blocks, so any one project can prove disjointness
without reading the other two trees) lives in Riot Commander's `core/ports.py`.
Deliberately NOT mirrored here: a sibling repo's guard greps its own source for
foreign port numbers, so citing another project's literal in this file would
trip it. Cite the block, never the port.
"""

# Reserved range, inclusive. 20 wide so a new LW service does not require
# re-auditing the other two projects first.
LW_BLOCK = (8900, 8919)

# The pipeline monitor: serves web/monitor.html plus the JSON APIs on
# 127.0.0.1. The authoritative value is tools/lw_monitor.py DEFAULT_PORT; this
# entry is pinned against it by test, so the two cannot drift apart.
MONITOR = 8901

ALLOCATIONS = {
    "monitor": MONITOR,
}


def in_block(port):
    """True when port falls inside LW's reserved block."""
    low, high = LW_BLOCK
    return low <= port <= high


def next_free():
    """Lowest unallocated port in the block, or None when the block is full.

    For wiring a NEW LW service: take this number, add it to ALLOCATIONS with a
    name, and pin it in tests/test_lw_ports.py against its definition site.
    """
    low, high = LW_BLOCK
    taken = set(ALLOCATIONS.values())
    for port in range(low, high + 1):
        if port not in taken:
            return port
    return None
