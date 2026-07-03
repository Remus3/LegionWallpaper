# Legion Wallpaper - Roadmap

_Now + Next only. Highest priority at the TOP. Full history in `docs/history_notes.md`. Aspirational in `BACKLOG.md`._

---

## Open items - High priority

_Shipped/closed entries move to `docs/LEDGER.md` (append-only). Only open/in-flight work stays below, highest priority first._

- **Define the product - wallpaper engine scope decision (NOW, operator-gated).**
  Legion Wallpaper has NO defined product yet. First real work item: decide what
  the wallpaper app IS (static rotation? live/animated engine? system-state-aware
  rendering? scheduling?), what it renders with, and what "done v1" means. Output
  is an ADR (`docs/adr/ADR-002-...`), not code. Do NOT build blind - no code
  before the scope ADR is accepted.

- **First ADRs (NOW, follows the scope decision).** ADR-001 (inherit the RC
  operating system) is DONE - `docs/adr/ADR-001-inherit-rc-operating-system.md`.
  Next: ADR-002 product scope (above), then one ADR per load-bearing early
  choice (rendering approach, process model, config format) as each is made.
  Use `docs/adr/TEMPLATE.md`.

- **Arm the audit/hygiene scheduled tasks once code exists (NEXT, operator-gated).**
  The standard roster (`LW-Supervisor`, `LW-GeminiAudit`, `LW-WeeklyHygiene`,
  `LW-CIWatchdog`) is documented in `docs/OPERATIONS.md` with example
  registration commands, all marked NOT YET REGISTERED. Do not register any of
  them until (a) the product has code + a test suite for the watchdogs to
  defend, and (b) the operator explicitly directs it. Same gate applies to the
  deep-audit program (`docs/DEEP_AUDIT_CHARTER.md` - DORMANT).

## Open items - Medium priority

- **Seed the test suite skeleton (LATER, unblocks CI + watchdogs).** Once
  ADR-002 lands: `tests/` gets the first RED-first tests, CI goes green on the
  empty-but-real suite, and only then do the watchdog tasks above have anything
  to defend.

- **First `ops/runtime/health.json` producer (LATER).** The supervisor pattern
  (`docs/ARCHITECTURE.md`) needs a main process that heartbeats health.json and
  honors `restart_trigger.txt`. TBD - product not yet defined; build it as part
  of the first runnable slice, not before.

## Status at a glance

Live status is intentionally NOT duplicated here - a static table goes stale.
Sources of truth (all TBD until the product runs):

- Process, pid, alive flag: `ops/runtime/health.json`
- Daily log: `logs/YYYY-MM-DD.log`
- Scheduled tasks: `Get-ScheduledTask -TaskName "LW-*" | Select TaskName, State`
  (expected result today: none - nothing is registered yet)

---

## Cross-cutting principles (never violate)

- **Frozen files** - see CLAUDE.md. Explicit operator sign-off required for any
  change. (The frozen list is currently EMPTY - files earn freeze status as the
  product stabilizes.)
- **Atomic writes only** - `tmp.write_text(...); tmp.replace(target)`.
- **`py_compile` before restart** - syntax errors crash silently under `pythonw.exe`.
- **Restart via `restart_trigger.txt`** - never `Stop-Process`; `taskkill /F /PID`
  for hard kills.
- **7-bit ASCII only** in authored content - no em/en dashes, no smart quotes.
- **Do not build blind** - product-shaping choices need an ADR or an explicit
  operator directive first.
