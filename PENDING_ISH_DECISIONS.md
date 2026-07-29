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

## Decisions needed from Ish

For each of sections 1–3: wrap now, wrap later with a redesigned
consent/safety mechanism, or leave manual-only indefinitely? No urgency —
these are all working fine as manual-only paths today.

For section 4: schedule `observability.py`'s wrap.
