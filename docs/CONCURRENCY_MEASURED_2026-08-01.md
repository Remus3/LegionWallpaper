# Three-way concurrency - measured (2026-08-01)

Closes two entries that sat on the hand-off as STILL UNMEASURED while N=3 was
already live in `ops/loop/config.json`: "three-way concurrency of any kind" and
"a contended acquire reaping a stale lock in a live run".

## What was actually measured, and what was not

**Measured:** the shared primitives - `ops/loop/slots.py` and
`ops/loop/winmutex.py` - under genuine contention from three and four SEPARATE
OS PROCESSES, with entry and exit timestamps recorded per process and peak
overlap computed by sweep line.

**NOT measured:** three repositories running their real loops. LW cannot drive
Riot Commander or Red Moon, and nothing in this harness reads or writes a
sibling tree. Anyone citing this must not upgrade it to "three repos ran
concurrently" - it is "the protocol the three repos coordinate through admits
exactly three, denies the fourth, and recovers from a dead holder".

Why real processes and not the existing thread test. `tests/test_loop_concurrency.py`
drives eight THREADS against two slots. That proves the bucket arithmetic and
nothing about the two properties N=3 rests on:

- `try_acquire` is `O_CREAT|O_EXCL` on the filesystem. Threads share one process
  and one interpreter; only separate processes exercise the exclusivity the
  cross-repo protocol is built on.
- `reap` decides on `pid_alive`. Every thread reports the SAME live pid, so a
  thread test structurally cannot exercise a dead-holder reap - the exact case
  that must not deadlock the other two repos.

Isolation: every run injects its own slots root under `tmp_path`, so the
machine-wide bucket at `C:\ProgramData\lw-loop\slots` is untouched (it was
observed empty at measurement time). The serialization run uses a TEST-ONLY
mutex name, never `winmutex.GPU_MUTEX` - taking the real `Global\LW_GPU` would
either block on a live sibling run or starve one.

Harness: `tests/test_three_way_concurrency.py`, four tests, 6.4s.

## A - three processes, max_slots=3: genuine overlap

```
peak concurrent = 3
pid   5608  slot 0.lock  enter +0.000s  exit +1.500s
pid  19152  slot 1.lock  enter +0.000s  exit +1.500s
pid  12244  slot 2.lock  enter +0.001s  exit +1.501s
```

Three distinct slots, three distinct pids, all inside within 1 ms of each other.
The load-bearing assertion is peak EQUALS 3, not `<= 3` - a bucket that
serialized everything would satisfy `<= 3` and prove nothing.

## B - four processes, max_slots=3: the fourth is held out

```
peak concurrent = 3
pid  14416  slot 0.lock  enter +0.000s  exit +1.501s
pid  20360  slot 1.lock  enter +0.001s  exit +1.501s
pid  18948  slot 2.lock  enter +0.001s  exit +1.501s
pid  10920  slot 0.lock  enter +1.549s  exit +3.049s   <- waited, then reused slot 0
```

The cap holds across process boundaries and the loser queues rather than
proceeding unslotted.

**Characteristic worth recording:** the fourth entered 48 ms after slot 0 freed,
under this harness's deliberately tight `backoff=0.05, jitter=0.05`. Production
uses the `slots.hold` defaults `backoff=2.0, jitter=2.0`, so real detection
latency after a slot frees is 0-4 s, not 48 ms. That is a throughput
characteristic, not a bug - the jitter is what stops two loops lockstepping -
but it means a freed slot is not picked up instantly and nobody should size a
cycle budget assuming it is.

## C - all three slots pre-held by a DEAD pid: fail-open reap under contention

```
peak concurrent = 3
pid   2240  slot 0.lock  enter +0.000s
pid  20232  slot 1.lock  enter +0.000s
pid   8464  slot 2.lock  enter +0.000s
```

Every slot was pre-planted with a lock owned by pid 999999999 before any
contender started, so the ONLY path through is a `pid_alive`-driven reap during
a contended acquire. All three entered immediately. The fail-open promise in
`slots.py` holds: a crashed holder in one repo cannot deadlock the other two.

## D - three processes, one named mutex: the opposite guarantee

```
peak concurrent = 1
pid  21180  enter +0.000s  exit +0.400s
pid   9736  enter +0.400s  exit +0.801s
pid   7912  enter +0.801s  exit +1.202s
```

Strict serialization, hand-off latency about 1 ms. This is the guarantee the GPU
mutex is there to give: slots admit three cycles, the GPU admits one CUDA job.
The two governors do different jobs and both were verified in the same run.

## Standing gap

A live three-repo run is still unobserved. What this closes is that the
mechanism is no longer taken on faith - it is measured, with numbers, and the
harness is permanent so a regression fails CI rather than being discovered
during a run.
