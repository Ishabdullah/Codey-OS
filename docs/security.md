# Security

Codey-OS is a persistent, autonomous coding agent that runs as a background daemon, executes shell commands, maintains long-term memory, and loads local LLMs. These capabilities make it powerful but introduce non-trivial risks compared to a simple chat tool.

**This is early-stage open-source software. Use with caution on devices with sensitive data. Always review generated code and commands before execution.**

---

## Key Risks and Mitigations

### 1. Persistent Daemon

The daemon runs continuously with a Unix socket (`~/.codeyOS/codeyOS.sock`) for IPC.

**Risk:** If the socket has permissive permissions or is in a shared location, unauthorized local processes could send commands.

**Mitigations:**
- Socket created with `0600` permissions (owner-only read/write).
- Daemon runs under your Termux/Linux user — no root required.

**Recommendation:** Stop the daemon when not in use (`codeydOS stop`). Only run on trusted, single-user devices.

---

### 2. Shell Command Execution

Tools can execute shell commands based on agent decisions.

**Risk:** Prompt injection or hallucinated output could lead to unintended commands (`rm -rf`, data exfiltration, etc.).

**Mitigations:**
- All shell commands (including compound commands with `&&`, `|`, `;`, etc.) require explicit user confirmation before running. Dangerous commands (`rm`, `curl`, `wget`, `chmod`, etc.) receive an additional warning before the prompt.
- YOLO mode (`--yolo`) disables confirmation prompts — use only in trusted, non-interactive contexts.
- Commands run in user context only — no privilege escalation.
- Shell timeout defaults to **30 minutes (1800 s)** to support long builds; configurable per-call.
- Daemon mode blocks commands not in an explicit allowlist (`core/task_executor.py`).

**Recommendation:** Review `--plan` output before execution. Use `--no-execute` for dry runs.

---

### 3. Self-Modification

Opt-in feature that allows the agent to patch its own code and files.

**Risk:** If enabled and manipulated via clever prompts, it could introduce backdoors, delete data, or persist damage.

**Mitigations:**
- Requires explicit `--allow-self-mod` flag **or** `ALLOW_SELF_MOD=1` env var.
- Auto-creates checkpoints and full backups before any core file change.
- Git integration for versioning and rollback.
- Workspace boundary enforcement: files outside the workspace are blocked unless self-mod is active.

**Recommendation:** Keep disabled by default. Enable only for intentional experimentation. Review diffs and checkpoints immediately after any modification.

---

### 4. Memory and State Persistence

Hierarchical memory stored in SQLite (`~/.codeyOS/`).

**Risk:** Sensitive code snippets or personal data could be stored and leaked if the device is compromised or backups are mishandled.

**Mitigations:**
- Data stored in Termux app-private directories.
- No unsolicited network calls. Exception: peer CLI escalation (Claude Code, Gemini CLI, Qwen CLI) can send local file contents to external LLMs when triggered — requires explicit user confirmation before any files are shared (see [Peer CLI Escalation](../README.md#peer-cli-escalation)).
- Encryption is not yet implemented (planned).

**Recommendation:** Avoid feeding sensitive information (API keys, passwords) to the agent. Periodically review or clear state:
- **In-chat:** type `/clear` to wipe history, context, undo history, and saved session
- **CLI flag:** `codeyOS --clear-session` to clear the saved session before starting
- **Manual:** `rm -f ~/.codey_sessions/*.json` to delete all saved sessions

---

### 5. Model Loading and Fine-tuning

Loads external GGUF files; supports importing LoRA adapters.

**Risk:** Malicious or poisoned model files could cause unexpected behavior or OOM crashes.

**Mitigations:**
- Models are downloaded manually — no auto-download.
- LoRA import creates a full backup before modifying the active model.

**Recommendation:** Only use models from trusted sources (Hugging Face official repos). Verify file hashes when possible. Test untrusted adapters on an isolated device.

---

### 6. GUI / Dashboard Server — REMOVED 2026-09-02

`gui/server.py` and its browser dashboard **no longer exist.** The GUI was
removed outright (Ish's decision) in favour of the Restoricon Core web
dashboard at `/admin`, which is served by the Core API and is covered by
**section 8** rather than here. A GUI may be reintroduced later; if it is,
this section's mitigations are the baseline it must meet again, which is
why they are recorded below rather than deleted.

**This entire attack surface is therefore closed by removal, not by a
fix** — the same distinction `NEW-111` and `NEW-279` are marked with. The
prior audit's **finding C-2 is resolved by removal** on that basis: nobody
hardened the WebSocket command console, it ceased to exist.

**What the removed server did, and what protected it** (retained as the
bar for any future reintroduction): it served metrics plus a command
console over WebSocket, started backgrounded and PID-tracked by
`codey-start`/`codeyOS`. A web server accepting commands is a far larger
attack surface than a CLI. It was mitigated by loopback-only binding
(`127.0.0.1`, overridable via `CODEY_GUI_HOST`), an `Origin`-header
allowlist on `/ws`, a per-process session token
(`secrets.token_urlsafe(32)`) regenerated each start and compared with
`hmac.compare_digest` independently of the Origin check, and a disabled
`access_log` so the token in the WebSocket URL never reached disk.

**If a GUI is reintroduced:** meet all four of the above, and note that
the interactive-session signal it used to feed
(`core/resource_gate.py`'s `is_gui_client_connected()`) was removed with
it because its no-PID-file branch failed *open* — any replacement must
fail closed. See `NEW-282`.

---

### 7. Android / Termux Constraints

Runs with Termux permissions (storage, potentially network if tools are expanded).

**Risk:** Long inference sessions can cause thermal stress or battery drain.

**Mitigations:**
- CPU-only inference — no GPU or NPU access.
- Built-in thermal management: warning at 5 minutes, thread reduction at 10 minutes.
- Adaptive recursion depth based on device temperature and battery level.

**Recommendation:** Monitor device temperature and battery. Use `codeydOS status` to check thermal state.

---

### 8. Restoricon Core API and the `/admin` web dashboard

The surface that replaced the GUI (section 6). `restoricon_core/api/server.py`
serves a JSON REST API plus three rendered web surfaces (`/admin`,
`/portal`, `/quote`) over a `ThreadingHTTPServer`.

**Risk:** this is the highest-risk surface in the project. It is
authenticated, multi-role, and holds every customer, contract, invoice and
financial record the business has. One authorization bug means one customer
sees another's contract. Unlike the removed GUI, it is *intended* to become
reachable from the public internet (via Cloudflare Tunnel — see
`CODEY_MASTER_PLAN.md` §6.6), which removes the loopback boundary that the
GUI relied on as its primary protection.

**Mitigations (verified in code, not assumed):**
- Binds `127.0.0.1:8770` by default (`server.py:31-32`), overridable via
  `RESTORICON_API_HOST` / `RESTORICON_API_PORT` or `--host`/`--port`.
- Bearer-token authentication on every endpoint except the deliberately
  public intake routes; the token is resolved to an `AuthContext` by
  `authenticate_token()` (`routes.py:226`).
- **RBAC is enforced in the service layer, not the router** — the router's
  only auth job is resolving the token (`routes.py:68`). This is
  deliberate: it means a new route cannot accidentally skip the permission
  check, because the check lives with the data access.
- Customer isolation is enforced service-side (e.g. `sign_contract()`
  rejects signing another customer's contract and fails closed).
- The public intake endpoints (`/api/v1/public/*`) are intentionally
  unauthenticated and are protected instead by a sliding-window rate
  limiter (20 requests / 60s per client IP, `api/rate_limiter.py:16`) plus
  honeypot spam mitigation.

**Known open items on this surface** (tracked in `NEW_ISSUES.md`, not yet
fixed): `NEW-264` / `NEW-266` (`update_user` accepts a suspension path
that never revokes tokens, and a role/customer_id shape `create_user`
refuses), `NEW-276` (audit `details=` payloads capture new state only at
59 of 63 call sites, so most changes are visible but not reconstructible),
and `NEW-273` (two admin save buttons discard input while reporting
success). Phase B6 covers the web layer's completion.

**Recommendation:** keep the API on loopback until the Cloudflare Tunnel
configuration itself has had a dedicated review. `CODEY_MASTER_PLAN.md`
§6.6 requires a mandatory code-reviewer pass on the tunnel/DNS setup and a
dedicated authorization test suite — "it works when I log in" is
explicitly not the bar.

---

### 9. Action Gateway and the WP2.1 hardening (status as of 2026-10-25)

The agent's shell, file, plugin and approval paths now sit behind one classifier-and-audit layer (`core/action_gateway.py`, CCOS `CAPABILITY_AUTHORITY`, Restoricon `BUSINESS_MUTATION_AUTHORITY`). Work is tracked in `CODEY_OS_MASTER_BLUEPRINT.md` (WP2.1) and the findings ledger `NEW_ISSUES.md`; the umbrella is `NEW-1018`, the per-finding status is `docs/wp2_1_g15b_consolidated.md` sections 10 to 10f. **WP2.1 is not closed.**

**Risk:** a model-issued command or file write that is not stopped by a human reaches the device with the same privileges as you. In modes that cannot ask (`--yolo`, the daemon, `--fix` / `--tdd` configurations, the bench, CCOS dispatch) nothing else stands between the model and the effect.

**Defences in place** (each is code complete and code-reviewer approved; see the tier note below):
- **Default-deny shell classifier** (`tools/shell_tools.py::classify_shell_command`): an executable not on the READ / ALLOWED / build-tool lists is `HIGH_IMPACT` and is refused where there is no human to confirm (for example `tar`, `id`, `ps`, `tee`, `npx`, a direct `./script.sh`, `kill`, `su`, `crontab`). Option tables (sed, sort, pip, npm, node, python `-m`) close the dangerous forms, and a bare name is checked against PATH shadowing. Credential reads (`cat ~/.ssh/...`, `.netrc`, `/proc/*/environ`) are refused; the scan casefolds from S2-A (committed in `84c7bfd`).
- **Protected-path tiers** (`core/protected_paths.py`, shared by the file tools and the shell argv scan): a DENY tier that nothing unlocks, not even `--allow-self-mod` (rule names seen in verification: `home-startup`, `state-dir`, `audit-sink`, `peer-agent-config`, `path-dedicated`), and a HIGH tier (launchers, `main.py`, `lib/*.sh`, `install.sh`, `setup*.sh`, `config.json`, `manifest.json`, `bench/**`, `ccos/core/**`, any `.git` component) that is refused in confirm-less modes and asks in the REPL. New-file and append writes to HIGH paths now ask too (needs a real tty; no tty means refusal).
- **Audited plugin spawn and manifest authority** (`ccos/core/plugin_manager.py`): `entry_point` containment, duplicate-name refusal, an audit row per spawn (`ccos.plugin_spawn:<name>`, argv, env-var NAMES only, never values). From S2-B (committed in `84c7bfd`): zero-width/format characters are folded out of plugin names, `call_capability` refuses caller-supplied `yolo` / `confirm*` / `shell_fn`, and a plugin loaded from outside `ccos/plugins` cannot claim a canonical capability name.
- **Secret masking** (`core/export_hygiene.py::mask_secrets`) in the audit ledger, the daemon file logger, saved sessions, `codey config` output and CCOS `system.processes`; the cloudflared tunnel token is delivered by environment, not argv. From S2-A (committed in `84c7bfd`) a mid-line `NAME=secret` is masked. **Not covered:** the trajectory database, checkpoints, telemetry, recovery history, `episodic_log`, the memory tiers and the console (NEW-1060, NEW-1066).
- **Fail-closed confirmations:** a REPL confirmation (`utils.logger.confirm`), the peer-escalation confirmation and the default-Yes plan prompts refuse without reading stdin when stdin is not a tty, and flush typeahead on a tty (S2-D, S2-E; committed in `84c7bfd`), so a piped or pre-typed `y` does not approve. `--yolo` does not skip the plan prompt; use `--no-plan`.
- **Operator-script human gates** (`core/tty_confirm.py`): `tools/provision_ai_agent_auth.py` and `core/setup_dr_key.py` ask on `/dev/tty` before any side effect and refuse without a controlling terminal. Other operator entry points are not guarded (NEW-1070).
- **Bench evaluator lock** (`bench/lock.py`, `bench/suite.lock` v2): any edit to a bench module, task file or (from S2-C, committed in `84c7bfd`) any symlink under `bench/` makes the lock fail; grading runs from a snapshot with a hardened pytest argv and a scrubbed child environment. Any edit to a covered `bench/*.py` needs a relock, and every old baseline must be re-run before comparison.
- **Census** (`tools/wp21_census.py`, register `docs/wp21_census/dispositions.tsv`): lists every effectful call site. UNKNOWN means "nobody has classified this", **not** "safe"; at `50f9aa2` 1,437 rows were UNKNOWN and the classification pass is not done. The coverage test is warn-only unless `WP21_CENSUS_GATE=1`; `WP21_CENSUS_STRICT=1` fails on any UNKNOWN row; `WP21_CENSUS_SKIP_REPO=1` skips both. A commit that adds, removes or reorders a boundary call must update the register in the same commit.

**What this is not (the ceiling).** The shell tool remains an audited `ACT` surface for opaque execution: a script file, `python3 -m ...` or an interpreter that the model writes and runs reaches anything your user can. The classifier closes named dangerous forms and makes the audit ledger truthful; it is not a sandbox. Accepted residuals (decided by Ish) include script-file execution, self-launch of a more-privileged agent child, `--allow-self-mod --yolo` writing HIGH paths unprompted, `--fix` re-running model-rewritten code unattended, and the service stop-script forms. Only an OS-level boundary (a separate uid, or proot with read-only repo and state mounts; a candidate work package, NEW-1069) removes the ceiling.

**Public capability argument contract (2026-10-25, NEW-1093).** Pass capability payload data by keyword: `pm.call_capability("coding.run_agent", prompt="...")`. Every positional argument after the capability name is refused and audited as HIGH_IMPACT before handler, module-function or external HTTP dispatch. This closes a positional `yolo`/confirmation override that the first S2-B keyword scan missed. Keyword authority-relaxing arguments and callable values remain refused. The internal `call_capability_trusted` path retains positional support and existing authority gating; it is a public Python method available to same-process code, so this contract does not provide process isolation. Correction is code complete and reviewer approved, committed in `84c7bfd`. The historical takeover run had 10 recorded baseline failures and one CCOS safety exclusion; current candidate results appear below. Live verification remains pending (takeover report).

**Approved prefreeze changes (2026-10-25; not yet committed).** Interactive REPL entry optionally imports standard-library readline; it adds no persistent history handling, key rebinding or signal handler. The dashboard activates only `thermal_monitor`. Plugin manifests accept a strict boolean `enabled` field (omitted means True); canonical `private_agent` and `aigentik` adapters are retained with `enabled: false`. Disabled definitions remain visible and reserve their canonical names/capabilities, but cannot load, start, execute or dispatch new work. An observed disable preserves an existing live/in-flight owner without automatically stopping or cleaning its PID; explicit unload/restart remains necessary. These integrations are unavailable, not repaired or live verified. All three changes have independent reviewer approval; final recursive checks completed with 9,294 passed /10 recorded baseline failures /2 skipped /19 subtests passed; guarded CCOS completed with 183 passed /2 known failures, zero guard refusals and no exclusions. The timing-sensitive failure passed its isolated control. Final documentation review is APPROVED for the exact 21-path commit. See the [closure progress report](wp2_1_g15z_closure_progress_2026-10-25.md).

**Verification tier, stated plainly.** The defences above were re-probed by independent verifiers on snapshots with recording fakes (1,014 probes, no regression of a closed finding) and a 62-row pseudo-terminal run on a disposable environment. That is **not** live verification on the attended Termux terminal, with the real tunnel token, the real DR key, real peers or a real bench run; those remain open (`NEW-1092`, `LIVE_TEST_QUEUE.md`). The S2 fixes marked "committed in `84c7bfd`" are code complete and reviewer approved but not live verified. The pending prefreeze readline change addresses delayed Ctrl-C (NEW-996) with disposable PTY evidence; an attended Termux check remains outstanding.

**Recommendation:** keep confirmations on; treat `--yolo` and the daemon as trusted-context only; do not rely on the classifier as an isolation boundary; keep secrets out of commands you type (masking is best effort, and the audit ledger `~/.codeyOS/action_gateway_audit.jsonl` is readable by your user).

---

## Current Hardening Summary

- User confirmation required for all shell commands; dangerous commands receive an explicit warning
- Opt-in self-modification with mandatory checkpoints
- Workspace and file boundary enforcement
- Socket permissions locked to owner-only (`0600`)
- Restoricon Core API binds loopback-only by default, authenticates every
  non-public endpoint with a Bearer token, and enforces RBAC in the service
  layer rather than the router (the browser GUI that previously held this
  line was removed 2026-09-02 — see section 6)
- Fully local — no network calls by default
- Thermal throttling prevents sustained CPU abuse
- Daemon mode shell allowlist (explicit prefix-based)

---

## Planned Improvements

- Encrypted memory and state storage
- Runtime sandboxing (bubblewrap / seccomp on Linux)
- Model file hash verification
- Audit logs and anomaly detection

---

## Reporting Vulnerabilities

The full source is open. If you find a vulnerability, please report it responsibly — open a GitHub issue with the `security` label or DM the maintainer. Contributions to security features are especially welcome.

**Use at your own risk.** This project is experimental and carries no warranties. Start small, monitor closely, and disable risky features until you are comfortable.
