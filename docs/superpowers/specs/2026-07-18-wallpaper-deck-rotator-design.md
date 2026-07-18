# Wallpaper Deck Rotator - design

Date: 2026-07-18
Status: approved (operator, 2026-07-18)
Tool: `tools/lw_wallpaper_rotate.py`

## Problem

The Windows 10 desktop slideshow repeats images constantly and at short
time variance. It does not feel random because it is not a shuffle.

Probed ground truth (2026-07-18, this machine):

- `HKCU\Control Panel\Personalization\Desktop Slideshow`:
  `Shuffle=1`, `Interval=60000`, `LastTickLow=0`, `LastTickHigh=0`
- `C:\Users\Administrator\Pictures`: 242 images, flat, no subdirectories
- 1 monitor, `\\.\DISPLAY1`, 2560x1440, primary
- `HKCU\Control Panel\Desktop`: `WallpaperStyle=10` (Fill)

`LastTickLow`/`LastTickHigh` pinned at 0 is the tell: Windows keeps no deck,
no cursor, and no shown-set. Shuffle mode is memoryless sampling with
replacement, and it re-seeds on wake, logon, and Explorer restart. With
N=242 at a 60s tick, the expected first repeat lands at about
sqrt(pi * N / 2) ~= 19 picks, so roughly every 19 minutes. The complaint is
an accurate read of the algorithm.

## Goal

Every image in the corpus is shown exactly once before any image is shown a
second time. No repeat across the cycle boundary either.

## Non-goals

- Multi-monitor per-display wallpapers (one monitor today; COM fallback
  below leaves the door open without building for it now).
- Transitions, fades, or any visual effect.
- Replacing the Windows personalization UI.
- Managing which images are in the corpus. That is the LW pipeline's job.
  This tool consumes whatever is in the source directory.

## Approach

A deck rotator. Shuffle the whole corpus into a permutation once, walk it
to the end, then reshuffle. Persist the permutation and the cursor so the
guarantee survives reboots, logons, and wake-from-sleep - the exact events
that reset the built-in shuffle.

Rejected alternatives:

- Third-party switcher (John's Background Switcher, BioniX, DisplayFusion).
  Working no-repeat mode today with zero build cost, but adds a resident
  app with opaque state and no LW integration. Kept as the fallback if the
  Win32 path proves unworkable.
- Feeder-folder hack (script rewrites a small staging directory that the
  Windows slideshow points at). Fights the Windows slideshow cache and is
  fragile. Rejected.

## Architecture

One module, four boundaries. Each unit is independently testable and the
only unit that touches Windows is the shim.

| Unit | Responsibility | Depends on | Headless-testable |
| --- | --- | --- | --- |
| deck logic | shuffle, reconcile, advance | stdlib `random` only | yes, pure functions |
| state io | atomic JSON load and save | `pathlib`, `json` | yes |
| win32 shim | set the desktop wallpaper | `ctypes` | no, mocked in tests |
| cli | argument parsing, command dispatch | the three above | yes |

The deck logic takes plain lists and returns plain lists. It never reads the
filesystem and never calls Windows. That is what makes the once-per-cycle
guarantee provable in a test rather than observable by watching a desktop
for twelve hours.

One file is the right size here (roughly 250 lines). Splitting a module this
small across four files would add import ceremony without adding clarity.

## State

`ops/runtime/wallpaper_deck.json`, written atomically
(`tmp.write_text(...)` then `tmp.replace(target)`) per the CLAUDE.md hard
rule, because a tick can land while another reader is mid-read.

```json
{
  "version": 1,
  "source_dir": "C:\\Users\\Administrator\\Pictures",
  "deck": ["a.png", "b.png", "c.png"],
  "cursor": 1,
  "cycle": 7,
  "last_shown": "a.png",
  "cycle_started_utc": "2026-07-18T09:00:00Z",
  "last_tick_utc": "2026-07-18T09:03:00Z"
}
```

`deck` is the whole permutation for the current cycle. `deck[:cursor]` has
been shown; `deck[cursor:]` is still owed. One list and one integer, so
"shown" and "owed" cannot drift out of sync with each other - which they
could if they were two separate lists.

Filenames are stored relative to `source_dir`, not as absolute paths, so
moving the corpus does not invalidate the deck.

## Tick algorithm

1. Scan `source_dir` for image files (`.jpg`, `.jpeg`, `.png`, `.bmp`) ->
   `present`.
2. Reconcile the deck against `present`:
   - Drop from `deck[cursor:]` anything no longer in `present` (deleted).
   - Splice anything in `present` but absent from the whole deck into
     `deck[cursor:]` at random positions, so newly delivered pipeline
     output joins the current cycle instead of waiting for the next one.
   - Leave `deck[:cursor]` alone. History is history.
3. If `cursor >= len(deck)`, start a new cycle: reshuffle all of `present`,
   set `cursor = 0`, increment `cycle`. If the fresh `deck[0]` equals
   `last_shown` and the deck has more than one entry, swap it with a random
   other index.
4. `pick = deck[cursor]`; `cursor += 1`.
5. Set `pick` as the wallpaper.
6. Persist state atomically.

Step 3's swap is the part a naive reshuffle gets wrong. Without it, the last
image of cycle N can be the first image of cycle N+1, which is a visible
back-to-back repeat and exactly the complaint being fixed.

Deleting an already-shown file is a no-op: it stays in `deck[:cursor]` as
history and is never set again this cycle. It simply will not appear in the
next reshuffle.

## Setting the wallpaper

`SystemParametersInfoW(SPI_SETDESKWALLPAPER=0x0014, 0, path,
SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE)` via `ctypes`.

Setting a concrete file drops Windows out of slideshow mode into
single-image mode, which is what stops the built-in slideshow from fighting
the rotator. `--install` also writes `Interval` and clears `Shuffle` under
`HKCU\Control Panel\Personalization\Desktop Slideshow` so the old behavior
cannot reassert itself from a stale theme.

`WallpaperStyle` is left at its current value (10, Fill). The rotator has no
business changing how images are fitted. Sources are already 2560x1440 to
match the display.

Documented fallback, not built now: the `IDesktopWallpaper` COM interface
(`CLSID_DesktopWallpaper`). If Windows ever reasserts slideshow mode over
the SPI call, `IDesktopWallpaper::SetWallpaper` is the escalation, and it is
also the path that would add per-monitor support if a second display is
ever attached.

## CLI

```
lw_wallpaper_rotate.py tick [--dry-run]   advance one image
lw_wallpaper_rotate.py status             cycle, position, remaining, next few
lw_wallpaper_rotate.py reshuffle          force a new cycle now
lw_wallpaper_rotate.py install            register the LW-Wallpaper task
lw_wallpaper_rotate.py uninstall          remove the LW-Wallpaper task
```

`--dry-run` on `tick` reports the pick and writes nothing, so the deck can
be inspected without consuming it.

## Configuration

`tools/lw_wallpaper_config.json`:

```json
{
  "source_dir": "C:\\Users\\Administrator\\Pictures",
  "interval_minutes": 3,
  "state_path": "ops/runtime/wallpaper_deck.json",
  "extensions": [".jpg", ".jpeg", ".png", ".bmp"]
}
```

Interval is configuration, not a constant, so retuning it is one edit plus a
task re-register rather than a code change.

At 242 images and a 3 minute tick, a full cycle runs about 12.1 hours, so
roughly every image once per waking day.

## Scheduling

Scheduled task `LW-Wallpaper`, per the `LW-*` naming convention.

- Trigger: at logon, repeating every `interval_minutes` indefinitely.
- Action: `pythonw.exe tools/lw_wallpaper_rotate.py tick`.

`pythonw.exe` rather than `python.exe` so no console window flashes every
three minutes.

Registered by `--install` via `schtasks` / `New-ScheduledTaskTrigger`, not
by hand through the Task Scheduler UI, so the registration is reproducible
and reviewable. Note that the Task Scheduler UI only offers preset
repetition intervals; an arbitrary interval such as 3 minutes has to be set
programmatically, which `--install` does.

## Error handling

- Missing or corrupt state file: log it, rebuild a fresh deck, continue. A
  rotator must never wedge the desktop over a bad JSON file.
- Empty source directory: log and exit 0 without touching the wallpaper.
  Nothing to show is not an error.
- Source directory missing: log and exit non-zero. That is a real
  misconfiguration and should surface.
- `SystemParametersInfoW` returns false: log `GetLastError`, do not advance
  the cursor, exit non-zero. The image was not shown, so it is still owed.
- All logging goes to `logs/YYYY-MM-DD.log` per the existing convention.
  Raw API error strings stay in the log and out of any user-facing surface.

## Testing

TDD, failing tests first, per CLAUDE.md. `tests/test_lw_wallpaper_rotate.py`,
matching the existing `tests/test_lw_*.py` convention. The win32 shim is
mocked; every other unit runs for real.

Required cases:

1. Full cycle over N images yields all N exactly once, no repeat.
2. Cycle seam: the first pick of a new cycle never equals the last pick of
   the previous one.
3. A file added mid-cycle is shown during that same cycle.
4. A file deleted mid-cycle is never set as wallpaper.
5. A file deleted after being shown does not corrupt the deck.
6. Missing or corrupt state rebuilds cleanly rather than raising.
7. Atomic write leaves no partial state file behind on failure.
8. `--dry-run` does not advance the cursor.
9. A single-image corpus does not infinite-loop at the seam swap.

## As-built deltas

Three corrections found during implementation. Recorded here so this
document does not drift from the shipped tool.

1. **Tick step 2 is conditional.** Taken literally, reconcile ran before the
   roll check on every tick, which spliced all present files into an empty
   deck on fresh state. `cursor >= len(deck)` was then never true, `cycle`
   stayed 0, and the seam swap in step 3 was unreachable. Reconcile is now
   skipped when no cycle is in progress. It still runs before the roll check
   for in-progress cycles, which is load-bearing: deleting the last owed file
   must roll the cycle rather than pick a deleted file.
2. **The task carries a TimeTrigger as well as a LogonTrigger.** A
   `LogonTrigger`'s `Repetition` only begins when that trigger fires, so a
   logon-only task registers `Ready` with `Next Run Time: N/A` and sits idle
   until the next logon. `task_xml` emits a `TimeTrigger` whose
   `StartBoundary` is install time, so rotation starts immediately; the
   `LogonTrigger` remains so the task survives reboots.
3. **A failed `SystemParametersInfoW` persists nothing at all**, rather than
   persisting state with the cursor held back. Same invariant, less state to
   reason about: the image stays owed and the next tick re-derives.

Scheduling is a Task Scheduler XML fed to `schtasks /Create /XML` rather
than bare `schtasks` flags, because `/RI` is rejected for `/SC ONLOGON`.
The XML is written to `ops/runtime/lw_wallpaper_task.xml` for review.

## Verification tier

Tier-1 (new module, local logic, no schema or core-contract change):
`py_compile` plus this module's tests. Followed by a live install and an
observed tick against the real 242-image corpus, since the win32 shim is the
one unit tests cannot cover.
