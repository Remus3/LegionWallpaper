"""Legion Wallpaper - the TCP port block LW owns, and what sits in it.

SIX projects share the Legion machine - not the three this file was written
against in 2026-08 - and until 2026-08-01 none of them could answer "which
ports are mine" without grepping bind sites and hand-filtering vendored noise.
That is not academic: a sibling project came one step from assigning itself a
block that would have collided with LW's monitor, and it was caught only
because the operator asked it to read this tree first.

LW's reserved block is 8900-8919. Anything in LW that binds a socket takes its
port from ALLOCATIONS below, and `tests/test_lw_ports.py` pins each entry
against the module that actually binds - not against a restated literal, which
would pass forever while the real server moved.

The neighbours are now named here too, in FORBIDDEN, because a registry that
cannot say what is NOT ours can only prove disjointness by reading five other
trees. The old rule - "cite the block, never someone else's port" - STANDS and
is now enforced rather than merely written down: FORBIDDEN carries block
BOUNDARIES only, never a sibling's service port, and the guard test allows
exactly the numbers declared here. Riot Commander's `core/ports.py` remains the
cross-project registry of record; this is LW's read of it, stated by the
operator 2026-08-29.
"""

# Reserved range, inclusive. 20 wide so a new LW service does not require
# re-auditing the other two projects first.
LW_BLOCK = (8900, 8919)

# The pipeline monitor: serves web/monitor.html plus the JSON APIs on
# 127.0.0.1. The authoritative value is tools/lw_monitor.py DEFAULT_PORT; this
# entry is pinned against it by test, so the two cannot drift apart.
MONITOR = 8901

# The run dashboard: serves web/rundash.html plus the run/resume JSON APIs on
# 127.0.0.1. Same rule as MONITOR - tools/lw_rundash.py DEFAULT_PORT is
# authoritative and the pin test holds the two together. Took the block low
# because next_free() said so, not because 8900 reads nicely.
RUNDASH = 8900

ALLOCATIONS = {
    "monitor": MONITOR,
    "rundash": RUNDASH,
}

# The neighbours' blocks: what LW must never bind, and who to ask when
# something is already listening there. Block boundaries ONLY - a sibling's
# service port is still none of this file's business, and the guard test
# enforces that by allowing no other foreign literal.
#
# LL was 8810-8814 and is expanding to 8819 (operator, 2026-08-29); the wider
# range is reserved here, because the failure this file exists to prevent is
# LW taking a port a sibling is about to claim, not LW being conservative.
FORBIDDEN = {
    "RM": ((8770, 8789),),          # Red Moon
    "LL": ((8810, 8819),),          # Lanternlight
    "DS": ((8860, 8879),),          # Daemon Slayer
    "RC": ((2999, 2999), (8888, 8895)),   # Amberstone / Riot Commander
    "CS": ((8920, 8939),),          # Clockspeed
}


def in_block(port):
    """True when port falls inside LW's reserved block."""
    low, high = LW_BLOCK
    return low <= port <= high


def owner_of(port):
    """Which project's block this port falls in - "LW", a FORBIDDEN key, or None.

    None means unclaimed by any of the six, NOT free: the operator's registry
    is the authority on reservations and a listener can exist outside every
    block.
    """
    if in_block(port):
        return "LW"
    for code, blocks in FORBIDDEN.items():
        if any(low <= port <= high for low, high in blocks):
            return code
    return None


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
