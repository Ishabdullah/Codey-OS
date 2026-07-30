# Pending Decisions — Deliberately Unwrapped Capabilities

Every item below was deliberately NOT exposed as a directly agent-callable
CCOS capability during Phase 2, per risk-tiered reasoning documented in
each plugin's manifest and in `PROJECT_LOG.md`. This file consolidates
them in one place so they can be reviewed as a batch rather than
rediscovered by reading through manifest prose or the full log.

None of these are technical blockers — the underlying functions all work
and remain reachable through their existing manual/CLI paths. These are
product/safety decisions about whether an *agent* should be able to
trigger them directly, not whether the functionality exists.

---

## 1. Fine-tuning / model swapping (`ccos/plugins/coding/finetune/`)

| Function | Risk |
|---|---|
| `swap_to_finetuned_model` | Replaces the live model file the daemon actually runs on |
| `merge_lora_with_llama_cpp` | Merges an adapter into a base model file |
| `import_lora_adapter` | High-level entry point that likely calls the above |

**Why unwrapped:** a bad or partial swap leaves the system without a
working model, recoverable only via this module's own backup/rollback
(unlike git, which has cheap, general-purpose undo). Making these
agent-callable risks a live-model swap as a side effect of an agent's own
planning, not just deliberate human action.

**Still reachable via:** `main.py --import-lora` (manual CLI path,
untouched).

**Note:** `create_backup_before_import`/`rollback_to_backup` were
reviewed under this same framing and Ish decided to add them (lower risk
— file-copy only, no model mutation) — already done, not pending.

**Correction (2026-07-30, tool/capability audit, rule 6):** the "file-copy
only, no model mutation" framing above does not hold for
`rollback_to_backup`. Reading `core/lora_import.py:385-430` directly:
it (1) `shutil.copy2(backup, original_path)` — **overwrites the live,
configured model file** the daemon runs on, (2) `backup.unlink()` —
**deletes the backup itself**, leaving nothing to fall back to if the
restored file is bad, then (3) unloads and reloads the model via
`core/loader_v2.py` — a real model-load cycle, the exact class of
operation CLAUDE.md rule 2 asks to be handled with RAM discipline. This
reads as this document's own tier-iii criteria ("mutates a live model
file", partial failure leaves "no rollback at all") rather than the
lower-risk tier it was approved under. `coding.finetune_rollback_backup`
remains wrapped and callable today — flagging for Ish to re-review, not
unwrapping unilaterally. `create_backup_before_import` is unaffected by
this correction (it only copies a file, doesn't touch the active model).

This is not just a theoretical tier-iii read: `rollback_to_backup`'s
`model_variant="secondary"` path calls `loader.load_secondary()`
(`core/lora_import.py:424`), the exact method `NEW_ISSUES.md`'s
`NEW-24` (Confirmed, unresolved) already documents as missing from
`ModelLoader` (`core/loader_v2.py` implements only `load_primary()` and
`unload()`). So calling this capability with the secondary variant is a
demonstrated failure, not an analogy: it overwrites the live model file,
deletes its own backup, then raises `AttributeError` — no working model,
no backup, no rollback.

---

## 2. Daemon control (`ccos/plugins/system/daemon_control/`)

| Function | Risk |
|---|---|
| `daemon_shutdown` | Kills the daemon process the whole system depends on |
| `command` (socket handler) | Submits a real task for the daemon to execute — triggers actual 7B inference and tool execution as a side effect of planning |

**Why unwrapped:** same reasoning as fine-tuning's model-swap functions —
an agent triggering either mid-planning would either take down the OS
shell's backing process, or consume real device resources running an
unplanned task.

**Still reachable via:** the daemon's socket protocol directly, or the
interactive CLI.

---

## 3. Peer CLI escalation (`ccos/plugins/coding/peer_escalation/`)

| Function | Risk |
|---|---|
| `escalate`, `confirm`, `call` (`core/peer_cli.py`) | Spawns real subprocess/pexpect sessions with external CLI tools (Claude Code, Qwen, Gemini) |
| `run_peer`, `run_direct`, `run_prompted`, `run_positional` (`core/peer_shell.py`) | The actual invocation mechanics behind `escalate` |

**Why unwrapped:** the existing consent mechanism
(`PeerCLIManager.confirm()`) is a blocking interactive terminal prompt —
there is no automated-call equivalent of "a human types y/n at a prompt."
This isn't a temporary gap, it's a structural property of the current
safety design. Wrapping these would either bypass consent entirely or
require designing a *new* consent mechanism for agent-initiated calls,
which is a real design question in its own right, not just a wrapping
decision.

**Still reachable via:** `core/agent.py:1715` → `escalate()` → `confirm()`,
exactly as before — completely untouched.

**Safe subset already wrapped:** `peer_list_available`,
`peer_detect_task_type`, `peer_select_cli` (dry-run), `peer_build_prompt`
(preview only, doesn't send) — all read-only, no subprocess spawn, no
external network/API contact.

---

## 4. Not yet scheduled anywhere — `core/observability.py`

Not a Phase 2 deferral, a genuine gap: `CODEY_OS_MASTER_VISION.md` Section
3 lists `core/observability.py` (the `/status` introspection module —
token usage, memory, task queue depth, active model, CPU/memory,
uptime/PID, health summary) as "complete but disconnected — needs a
`/status` CLI handler wired to call it," same category as `recovery.py`.
`recovery.py` got wrapped in Phase 2 item 9. `observability.py` never got
a slot in the 10-item list and has fallen through the cracks until now.

**Needs:** either its own small Phase 2-style wrap task, or folding into
whatever comes next — flagging here so it doesn't get lost again.

---

## Decisions — resolved 2026-07-30

### 1. Fine-tuning / model swapping — **manual-only indefinitely**
No further work. Stays reachable only via `main.py --import-lora`.

### 2. Daemon control — **wrap now, redesigned** (in progress)
Not a straight wrap of the existing functions — Ish specified a new design:

- `daemon_shutdown` is repurposed from a directly-callable kill into an
  autonomous safety tripwire: the daemon self-terminates if it detects
  ~20 minutes of sustained severe thermal + >90% CPU usage. Not agent- or
  user-triggered; a condition the daemon watches for itself.
- `command` (socket handler) is no longer a direct "run this now" entry
  point — it becomes queue-only. Callers enqueue work; the daemon pulls
  from the queue on its own schedule.
- The daemon must never do work while the user has the TUI or GUI open
  (mutual exclusion between daemon activity and interactive use).
- The daemon must only pull from the queue when resources actually allow
  it — RAM, battery, CPU, and temperature all gate whether/how often it
  runs anything, not just "is the queue non-empty." This is explicitly
  forward-looking: more models running concurrently are expected later,
  so the gating needs to be resource-aware now, not just model-count-aware.
- Queue semantics for now: simple FIFO add/delete. Reordering
  (moving items within the list) is a known, explicitly deferred future
  feature — not in scope for this round.
- `core/observability.py` (see item 4 below) is folded into this same
  round, since the resource-gating logic needs exactly the introspection
  (CPU/mem/temp/queue depth) that module already provides but was never
  wired up.

This is a process-lifecycle change (daemon start/stop, kill/shutdown
logic) — per CLAUDE.md rule 4, requires code-reviewer's explicit approval
before commit regardless of size.

### 3. Peer CLI escalation — **wrap later, with a redesigned consent
mechanism** (not started — design only, captured here)

Ish's direction for the redesign: if a daemon-queued item needs peer CLI
escalation, the daemon does not block waiting for human consent. Instead
it:
1. Pulls that item out of the main work queue,
2. Adds it to a separate "needs escalation review" list,
3. Sends the user a notification that an item is waiting on their review,
4. Continues working the rest of the main queue in the meantime.

The escalation-review list is only acted on when the user is ready to
review/approve those specific items — it's a decoupled, async,
human-gated queue distinct from the main work queue. This is a real
design task in its own right (new consent mechanism), not yet scoped
into implementation work.

### 4. `core/observability.py` — **folded into item 2's work**, not a
standalone task. The daemon-control redesign's resource-gating logic is
exactly what needs to read from this module, so wiring it up happens as
part of that round rather than separately.

---

## Status

Only item 2 (daemon control redesign, with item 4 folded in) is queued
as active work. Items 1 and 3 have decisions recorded above but no
further action pending.
