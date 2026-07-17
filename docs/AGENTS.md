# Legion Wallpaper - Agent Framework (inherited PATTERN)

> **THIS IS THE INHERITED PATTERN, NOT A RUNNING SYSTEM.** No agent code exists
> in this repo yet. The product is now defined (ADR-002 - the restoration
> pipeline); every module path below stays TBD until an operator directive
> wires the framework in. The pattern is recorded now so the eventual wiring
> copies a proven shape instead of inventing one. For operating rules see
> `CLAUDE.md`.

## Two-supervisor architecture pattern

| Supervisor | File | Port(s) | Role |
|---|---|---|---|
| **LW Supervisor** | `ops/lw_supervisor.py` (TBD) | - | Owns the main product process lifecycle; PID lock; restart trigger |
| **Agent Supervisor** | `agents/supervisor.py` (TBD) | TBD | Orchestrates Agents 0-7; exposes the analyze/dispatch surface |

Both coexist on Legion. Neither kills the other.

## Agent roster - ROLE TEMPLATE

Numbered roster; the NUMBER + ROLE are the durable pattern, the module paths
and task-kind numbering are wiring TBD.

| Agent | Role name | Module | Role |
|---|---|---|---|
| **0** | Gatekeeper | TBD | Task policy gate (fixed criteria set). Rejections split into two outcomes: dead_letter (permanent) vs auto_retry_once (transient). Explicitly NOT a user security boundary. |
| **1** | Lead Scheduler | TBD | SINGLE writer of `agents/state/task_queue.jsonl`. Priority queue with JSONL persistence. Applies the gate policy (below) to every filed task. |
| **2** | Backend Ingest | TBD | Turns inbound events into persisted rows/state. Owns its own transport (TBD - product not yet defined). |
| **3** | Testing | TBD | Pytest suite covering all agents + core modules. |
| **4** | Analyzer | TBD | Offline analysis over accumulated data; activates learned modifiers only past an explicit sample threshold. |
| **5** | UI Fallback | TBD | Serves a best-effort answer when the primary live source is down, via a ranked multi-signal fallback chain. |
| **6** | Auditor | TBD | Security audit probes - path traversal, subdir substring, dotfiles; source-quality ratings. |
| **7** | Context / NL Parser | TBD | User strings -> tasks via the Agent 1 scheduler. Two-stage: rule-based fast path (~80%), LLM fallback. NEVER dispatches agents directly - only files tasks. |

## Gate policy pattern

Every task kind is classified ONCE, at filing time, by Agent 1:

- **Hard gates** (destructive / operator-consequential kinds) ->
  `needs_explicit_approval` - sits until the operator approves; never
  auto-runs.
- **Review kinds** (policy-sensitive but automatable) -> Agent-0 review -
  the gatekeeper evaluates against its criteria; pass -> `ready`, fail ->
  dead_letter or auto_retry_once per the rejection split.
- **Ungated kinds** (routine, reversible) -> `ready` immediately.

Which task-kind numbers map to which bucket is wiring TBD - the buckets and
their semantics are the invariant.

## `agents/state/` runtime file conventions

| File | Contents |
|---|---|
| `lockfile` | PID lock - the agent supervisor heartbeats it every 5s; duplicate launches detect a fresh heartbeat and abort |
| `task_queue.jsonl` | Append-only log of EVERY task status transition; Agent 1 replays it on startup to rebuild queue state (never truncate, never rewrite) |
| `resolved_decisions.json` | Locked topology/design decisions the framework must not re-litigate at runtime |

## Architecture map (target shape - all TBD)

```
agents/
  supervisor.py           Agent orchestrator (ports TBD)
  agent0_gatekeeper/      Task policy gate
  agent1_lead/            Task queue (scheduler) - JSONL writer, priority queue
  agent2_backend/         Ingest (transport TBD - product not yet defined)
  agent3_testing/         Pytest suite
  agent4_analyzer/        Offline analyzer - threshold-gated modifiers
  agent5_ui/              UI fallback chain
  agent6_auditor/         Security audit probes
  agent7_context/         NL input parser -> Agent 1
  state/                  task_queue.jsonl, lockfile, resolved_decisions.json
```
