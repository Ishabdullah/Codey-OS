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
- Shell requests are classified READ, ACT or HIGH_IMPACT, then audited. Routine prompts depend on `confirm_shell` and YOLO; HIGH requests refuse when no confirmation path is available. With prompts enabled, stdin must be a terminal and approval must be explicit.
- The primitive uses `shlex.split` and argv execution, not `shell=True`; compound shell syntax is not generally expanded. Opaque interpreter/script execution retains the accepted same-user ceiling described in section 9.
- YOLO mode (`--yolo`) disables routine prompts; it does not approve HIGH shell actions or bypass planning/operator-script approval checks.
- Commands run in user context only — no privilege escalation.
- Shell timeout defaults to **30 minutes (1800 s)** to support long builds; configurable per-call.
- Daemon shell requests use the shared classifier and protected/credential scans; unknown executable forms default to HIGH and refuse without confirmation.

**Recommendation:** Review `--plan` output before execution. Use `--no-execute` for dry runs.

---

### 3. Self-Modification

Opt-in feature that allows the agent to patch its own code and files.

**Risk:** If enabled and manipulated via clever prompts, it could introduce backdoors, delete data, or persist damage.

**Mitigations:**
- Requires explicit `--allow-self-mod` flag **or** `ALLOW_SELF_MOD=1` env var.
- Mediated core Python writes create checkpoints before mutation. Backup scope is narrower than HIGH classification; checkpoint failure/partial-copy and restore limits remain explicit (NEW-862/870/871/951).
- Git integration for versioning and rollback.
- File tools enforce workspace boundaries; self-modification permits the configured Codey source tree, rather than arbitrary outside paths. DENY paths remain blocked even when self-modification is enabled.

**Recommendation:** Keep disabled by default. Enable only for intentional experimentation. Review diffs and checkpoints immediately after any modification.

---

### 4. Memory and State Persistence

Hierarchical memory stored in SQLite (`~/.codeyOS/`).

**Risk:** Sensitive code snippets or personal data could be stored and leaked if the device is compromised or backups are mishandled.

**Mitigations:**
- Data stored in Termux app-private directories.
- Local inference is the default. Operator-selected remote inference sends prompt/messages without a per-request gateway prompt; configured backup, retrieval and business integrations also have network effects. Retry-triggered peer escalation separately requires explicit confirmation. These are not network-isolation guarantees (NEW-936).
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
- Token-protected routes resolve Bearer credentials to a persisted `AuthContext`. Public health/auth/assets/intake and scoped share-link routes have separate policies; do not assume every route uses the Bearer gate.
- Permission and ownership checks generally live in services. Some actor-less helpers rely on explicit route checks: estimate decisions, for example, require the staff route's permission/ownership checks or the public route's valid, unrevoked, unexpired scoped share token. A new route must preserve that caller contract.
- Customer isolation is enforced service-side (e.g. `sign_contract()`
  rejects signing another customer's contract and fails closed).
- Public intake is intentionally unauthenticated, with rate limits and honeypot checks. Public estimate viewing/decision routes instead validate scoped share tokens and their expiry/revocation, plus their own rate limits. A rate limiter is not authorization.

**Historical business audit references** (use `NEW_ISSUES.md` for each finding's current status): `NEW-264` / `NEW-266` (`update_user` accepts a suspension path
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

### 9. Action Gateway and the WP2.1 hardening (status as of 2026-10-26)

The agent's shell, file, plugin and approval paths now sit behind one classifier-and-audit layer (`core/action_gateway.py`, CCOS `CAPABILITY_AUTHORITY`, Restoricon `BUSINESS_MUTATION_AUTHORITY`). Work is tracked in `CODEY_OS_MASTER_BLUEPRINT.md` (WP2.1) and the findings ledger `NEW_ISSUES.md`; the umbrella is `NEW-1018`, the per-finding status is `docs/wp2_1_g15b_consolidated.md` sections 10 to 10f. **WP2.1 is not closed.**

**Risk:** a model-issued command or file write that is not stopped by a human reaches the device with the same privileges as you. In modes that cannot ask (`--yolo`, the daemon, `--fix` / `--tdd` configurations, the bench, CCOS dispatch) nothing else stands between the model and the effect.

**Defences in place** (each is code complete and code-reviewer approved; see the tier note below):
- **Default-deny shell classifier** (`tools/shell_tools.py::classify_shell_command`): an executable not on the READ / ALLOWED / build-tool lists is `HIGH_IMPACT` and is refused where there is no human to confirm (for example `tar`, `id`, `ps`, `tee`, `npx`, a direct `./script.sh`, `kill`, `su`, `crontab`). Option tables (sed, sort, pip, npm, node, python `-m`) close the dangerous forms, and a bare name is checked against PATH shadowing. Credential reads (`cat ~/.ssh/...`, `.netrc`, `/proc/*/environ`) are refused; the scan casefolds from S2-A (committed in `84c7bfd`).
- **Protected-path tiers** (`core/protected_paths.py`): file-tool DENY targets include startup/state/audit/credential/peer configuration, dedicated PATH directories and any `.git` component; `--allow-self-mod` does not unlock them. HIGH targets include repo launchers, scripts, root config, plugin data/manifests, `bench/**`, `ccos/core/**` and `restoricon_core/authority*.py`. HIGH file writes refuse without an available approval path, with the accepted `--allow-self-mod --yolo` exception below. REPL new-file and append approval requires a real stdin terminal. The shell scans the same protected set to promote named mutators to HIGH; it does not impose the file tools' unconditional DENY behavior on every approved shell command.
- **Audited plugin spawn and manifest authority** (`ccos/core/plugin_manager.py`): `entry_point` containment, duplicate-name refusal, an audit row per spawn (`ccos.plugin_spawn:<name>`, argv, env-var NAMES only, never values). From S2-B (committed in `84c7bfd`): zero-width/format characters are folded out of plugin names, `call_capability` refuses caller-supplied `yolo` / `confirm*` / `shell_fn`, and a plugin loaded from outside `ccos/plugins` cannot claim a canonical capability name.
- **Secret masking** (`core/export_hygiene.py::mask_secrets`) in the audit ledger, the daemon file logger, saved sessions, `codey config` output and CCOS `system.processes`; the cloudflared tunnel token is delivered by environment, not argv. From S2-A (committed in `84c7bfd`) a mid-line `NAME=secret` is masked. **Not covered:** the trajectory database, checkpoints, telemetry, recovery history, `episodic_log`, the memory tiers and the console (NEW-1060, NEW-1066).
- **Fail-closed confirmations:** a REPL confirmation (`utils.logger.confirm`), the peer-escalation confirmation and the default-Yes plan prompts refuse without reading stdin when stdin is not a tty, and attempt a best-effort typeahead flush on a tty (S2-D, S2-E; committed in `84c7bfd`). A piped `y` cannot approve; flush failure/stale interactive input remains a documented limit. `--yolo` does not skip the plan prompt; use `--no-plan`.
- **Operator-script human gates** (`core/tty_confirm.py`): `tools/provision_ai_agent_auth.py` and `core/setup_dr_key.py` ask on `/dev/tty` before provisioning/key generation and persistent changes, and refuse without a controlling terminal. Imports/inspection can have owned bootstrap effects; this does not certify mutation-free imports. Other operator entry points are not guarded (NEW-1070).
- **Bench evaluator lock** (`bench/lock.py`, `bench/suite.lock` v2): edits to covered evaluator/task bytes invalidate the lock; from S2-C (`84c7bfd`), detected symlinks under `bench/` also make verification refuse; unreadable-subtree, root-symlink and same-user limits remain documented (NEW-1091). Grading runs from a snapshot with a hardened pytest argv and a scrubbed child environment. Any edit to a covered `bench/*.py` needs a relock, and every old baseline must be re-run before comparison.
- **Census** (`tools/wp21_census.py`, register `docs/wp21_census/dispositions.tsv`): statically inventories its recognized call forms, with documented receiver/dynamic/regex blind spots (NEW-1009). UNKNOWN means "nobody has classified this", **not** "safe"; at `50f9aa2` 1,437 rows were UNKNOWN and the classification pass is not done. The coverage test is **blocking by default** (since 2026-10-27; the former `WP21_CENSUS_GATE` opt-in and warn-only branch were removed); `WP21_CENSUS_STRICT=1` additionally fails on any UNKNOWN row; `WP21_CENSUS_SKIP_REPO=1` skips both repo-level tests; `WP21_CENSUS_SOURCE=worktree` is a diagnostic mode. A commit that adds, removes or reorders a boundary call must update the register in the same commit. Known limitation (NEW-1103): stale register rows for files absent from the scan only warn rather than fail, so a file renamed to a `test_*` name drops out of the scan without failing the gate.

**What this is not (the ceiling).** The shell tool remains an audited `ACT` surface for opaque execution: a script file, `python3 -m ...` or an interpreter that the model writes and runs reaches anything your user can. The classifier closes named dangerous forms and makes the audit ledger truthful; it is not a sandbox. Accepted residuals (decided by Ish) include script-file execution, self-launch of a more-privileged agent child, `--allow-self-mod --yolo` writing HIGH paths unprompted, `--fix` re-running model-rewritten code unattended, and the service stop-script forms. Only an OS-level boundary (a separate uid, or proot with read-only repo and state mounts; a candidate work package, NEW-1069) removes the ceiling.

**Public capability argument contract (2026-10-25, NEW-1093).** Pass capability payload data by keyword: `pm.call_capability("coding.run_agent", prompt="...")`. Every positional argument after the capability name is refused and audited as HIGH_IMPACT before handler, module-function or external HTTP dispatch. This closes a positional `yolo`/confirmation override that the first S2-B keyword scan missed. Keyword authority-relaxing arguments and callable values remain refused. The internal `call_capability_trusted` path retains positional support and existing authority gating; it is a public Python method available to same-process code, so this contract does not provide process isolation. Correction is code complete and reviewer approved, committed in `84c7bfd`. The historical takeover run had 10 recorded baseline failures and one CCOS safety exclusion; current candidate results appear below. Live verification remains pending (takeover report).

**Committed prefreeze changes (`770dc66`, 2026-10-25).** Interactive REPL entry optionally imports standard-library readline; it adds no persistent history handling, key rebinding or signal handler. The dashboard activates only `thermal_monitor`. Plugin manifests accept a strict boolean `enabled` field (omitted means True); canonical `private_agent` and `aigentik` adapters are retained with `enabled: false`. Disabled definitions remain visible and reserve their canonical names/capabilities, but cannot load, start, execute or dispatch new work. An observed disable preserves an existing live/in-flight owner without automatically stopping or cleaning its PID; explicit unload/restart remains necessary. These integrations are unavailable, not repaired or live verified. All three changes have independent reviewer approval; final recursive checks completed with 9,294 passed /10 recorded baseline failures /2 skipped /19 subtests passed; guarded CCOS completed with 183 passed /2 known failures, zero guard refusals and no exclusions. The timing-sensitive failure passed its isolated control. The exact 21-path tranche was independently approved, committed and pushed; production source remains frozen there while closure evidence is completed. See the [closure progress report](wp2_1_g15z_closure_progress_2026-10-25.md).

**Verification tier.** Historical reports retain 1,014 probes and a 62-row disposable pseudo-terminal run; they predate later fixes and do not verify all final-source paths. The adapted V-A replay on frozen `770dc66` has an independently approved result: 266 data groups, including two explicitly unrun invalid/superseded cases; process/network attempts were recorded and refused. Its allowed own-root SQLite/bootstrap writes are real filesystem effects. Remaining replay units and the attended terminal, real tunnel token, DR key, peers and real bench checks remain open (`NEW-1092`, `LIVE_TEST_QUEUE.md`). The committed readline change addresses delayed Ctrl-C (NEW-996) with disposable PTY evidence; the attended Termux check is outstanding. WP2.1 is still open.

**Recommendation:** keep confirmations on; treat `--yolo` and the daemon as trusted-context only; do not rely on the classifier as an isolation boundary; keep secrets out of commands you type (masking is best effort, and the audit ledger `~/.codeyOS/action_gateway_audit.jsonl` is readable by your user).

---

## Current Hardening Summary

- Classified/audited shell requests; HIGH refuses without confirmation, with routine prompts controlled by mode
- Opt-in self-modification with mandatory checkpoints
- Workspace and file boundary enforcement
- Socket permissions locked to owner-only (`0600`)
- Restoricon Core API binds loopback-only by default, authenticates every
  non-public endpoint with a Bearer token, and enforces RBAC in the service
  layer rather than the router (the browser GUI that previously held this
  line was removed 2026-09-02 — see section 6)
- Default local inference; operator-selected remote backends and configured integrations can send data
- Thermal throttling prevents sustained CPU abuse
- Daemon shell uses the shared default-deny classifier and operand scans

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
