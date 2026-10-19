# WP2.1 NEW-959 — require absolute daemon paths (scoping spec)

**Execution status (2026-10-18): S1, S2 and S3 COMPLETE; mandatory reviewers
APPROVED; disposable on-device verification PASS.** S1 enforces absolute daemon
configuration through every public consumer. S2 adds private shell and
`process_identity.py` CLI defense in depth. S3 applies the root rule to the six
non-daemon lifecycle records and binds litestream's cwd to its validated path
snapshot. Final combined regression: `540 passed in 103.48s`; fatal Ruff,
shell syntax, and `git diff --check` passed. Durable evidence is in
`docs/wp2_1_new959_live_verification.md`. NEW-959 is closed; deliberately
excluded path classes remain separate ledger findings.

Scoped 2026-10-18 against HEAD `d3c2d8d` (working tree clean apart from `.claude/` memory files). Desk
analysis only: no source, test, or tracking-doc edit. Runtime probes, disclosed in full: (1) one
stdlib-only `python3 -I` check of `pathlib` behavior (F4) under a throwaway HOME/`CODEY_STATE_DIR`
with proxy variables unset; (2) one later `python3 -I` string-replace run to fix four line-reference
typos in this very file, which ran **without** the throwaway HOME/`CODEY_STATE_DIR` and without
unsetting proxy variables (it imported nothing from the repo, opened only this spec, and touched
nothing under `~/.codeyOS`, but it did not follow the letter of the constraint). Everything else was
`grep`/`sed`/`cat`/`ls` reads; the operator's real `~/.codeyOS` was only listed and `ls`-probed, no
config value from it was read because `config.json` does not exist there.

Decision implemented: Ish, 2026-10-18 ("yes if that's what you think is best") took option 1 of
the three offered in NEW-959: **require absolute daemon paths and refuse relative ones.** Option B
(state-root anchoring + migration) and option C (retain caller-relative) are rejected, so nothing in
this spec anchors, rewrites, or migrates a value. See "Product forks" for why no new question for Ish
is created.

Track A (WP2.1 group 13 residue / prerequisite completed before group 15). Rule 4 applies to the whole change: it touches
daemon startup guard, PID-record path selection, lifecycle-lock path selection and the service
launch path. Mandatory code-reviewer approval before commit and a live verification with disposable
fixtures.

---------------------------------------------------------------------------------------------------

## 1. Verified facts

### 1.1 How a daemon path becomes a value (all at HEAD)

| # | Fact | Evidence |
|---|------|----------|
| F1 | The default daemon PID/socket/log paths are `CODEY_STATE_DIR / "codeyOS.{pid,sock,log}"`, and `CODEY_STATE_DIR` is `Path(os.environ["CODEY_STATE_DIR"])` with **no absoluteness check** (`~/.codeyOS` only when the variable is unset/empty). A relative or `~`-prefixed env value (Python does not expand `~` here) therefore yields relative *defaults*, not just relative config overrides. | `utils/config.py:325-333` |
| F2 | The daemon config file is `CODEY_STATE_DIR/config.json` only (`CONFIG_FILE = DAEMON_CONFIG_FILE`); `DaemonConfig` does not honor `CODEY_CONFIG_PATH` or the repo `config.json` (unlike the separate service-config helper `get_config_file_path`). A relative `CODEY_STATE_DIR` therefore also makes the *config file's own location* cwd-dependent. | `core/daemon_config.py:19-20,57-71`; `utils/config.py:334,627-648` |
| F3 | `DEFAULT_CONFIG["daemon"]` is built at import from F1's constants, merged under `config.json` by shallow-recursive `_merge_configs`. | `core/daemon_config.py:22-29,73-81` |
| F4 | `DaemonConfig.get` returns the raw JSON value (any type) and expands only a leading `~` via `Path(current).expanduser()`. `$HOME/x` is **not** expanded (stays a relative literal). `~nosuchuser/x` raises `RuntimeError` (probed: "Could not determine home directory."). A `null`/number/dict value reaches `Path(...)` and raises `TypeError` (probed). An empty string becomes `Path("")` == `.` (probed), i.e. the pid "file" is the cwd. | `core/daemon_config.py:83-102,180-182`; probe |
| F5 | `resolve_daemon_paths(config=None)` is the single effective-path resolver; it builds `DaemonPaths(Path(...) x3)` with no validation. Its docstring says relative values "retain their existing invoking-cwd interpretation". `DaemonPaths` is a frozen dataclass with no `__post_init__`. | `core/daemon_config.py:162-183` |
| F6 | The 13c.2a/13c.2b work made **every** Python consumer go through that resolver or through a snapshot handed from it (list in 1.3). The shell layer holds **no path logic at all**: `lib/service_manager.sh` and `codeyOS`/`codeydOS` are thin wrappers that call `core/service_lifecycle.py`. The only shell-level state-root variable, `DAEMON_DIR="${CODEY_STATE_DIR:-$HOME/.codeyOS}"` (`lib/service_manager.sh:5`, `codeydOS:12`), is **dead** (grep of `lib/`, all launchers and `install.sh` finds no read of `$DAEMON_DIR`). `lib/service_lifecycle.sh` only receives pid/log/socket/cwd as positional strings from the Python plan (`core/service_lifecycle.py:183`). | `lib/service_manager.sh:5-12`; `codeydOS:11-12`; grep |
| F7 | `lock_exec` builds the whole plan *before* any effect: `selected = {name: service_paths(name) ...}` (`:156`) precedes `LifecycleRecord.__enter__()` (`:162`), which is the first place a directory is created (`process_identity.py:198`, `mkdir(parents=True)`). So a validation failure in `service_paths("daemon")` happens before any mkdir, lock file, signal or spawn. For `all`, `daemon` is first in `_LOCK_ORDER`, so a daemon-path refusal aborts the entire composite before restoricon/aigentik/etc. | `core/service_lifecycle.py:38-39,150-162` |
| F8 | The non-daemon services take their root from a second, raw read of the environment, **not** from `utils.config`: `Path(os.environ.get("CODEY_STATE_DIR") or Path.home()/".codeyOS")`. A relative root gives relative pid/log files and (litestream) a relative service cwd. | `core/service_lifecycle.py:68-69,107` |
| F9 | `main.py` `/cwd` calls `os.chdir(...)` in the live TUI process. It is the **only** `os.chdir` in `core/ tools/ utils/ ccos/ prompts/ main.py` (grep). The daemon never `chdir`s. | `main.py:1375`; grep |

### 1.2 Where cwd is bound (how a relative value is interpreted)

Launch (caller cwd = C1):
1. `codey-start`/`codeydOS`/`codey-stop` do not `cd` (`codey-start:11-19`, `codeydOS:10-14`; the `$(cd ... && pwd -P)` is a subshell used only to find the repo). The public wrapper spawns the worker with inherited cwd (`core/service_actions.py:96`).
2. Worker resolves paths relative to C1: `LifecycleRecord(paths.pid_file, ...)` (`service_lifecycle.py:161`) `mkdir`s and opens `<pid_file>.lifecycle.lock` with `O_NOFOLLOW` relative to cwd (`process_identity.py:198,201`).
3. `start_profile("daemon")` sets `cwd = Path.cwd()` (`service_lifecycle.py:93`) and passes `str(selected.*)` to `core/daemon_bootstrap.py` as three argv strings (`:96`); the owned-spawn passes `--cwd "$service_cwd"` and the relative `--pid-file/--log-file` (`lib/service_lifecycle.sh:61-63`). The daemon is thus launched **with cwd C1 and relative strings**, so at birth it agrees with its launcher.
4. The daemon never changes cwd (F9), so it keeps interpreting the value against C1 for its whole life: lock, record publish (`daemon.py:138-145`), `remove_pid_file` (`:148+`, uses the stored relative `Path`), unix socket bind (`:791-793`), log file (`:955-959`).

Later clients (cwd = C2), each re-resolving the same config string:
- `codeyOS status|task|cancel` (`cli_client.py:25-47`), `send_command`/`is_daemon_running` (`daemon.py:2246-2283`), observability (`observability.py:215,238,262`), daemon_control plugin (`daemon_control.py:107`), `codeydOS status|stop|restart|reload` and `codey-stop` (all via `service_paths`, `service_lifecycle.py:66`).

### 1.3 Observed / derivable failure modes (relative value, daemon launched from C1)

1. **Invisible daemon -> duplicate daemon.** From C2 the pid record resolves to `C2/<rel>` which does not exist -> identity "absent", `usable_daemon`/`cli_client` say "not running", `codeydOS start` from C2 acquires a *different* lifecycle lock (`C2/<rel>.lifecycle.lock`), passes `check_pid_file`, and starts a second daemon sharing `state.db` and the llama-server port. `daemon.py:119-135` can only detect duplicates it can see through the same path.
2. **Unstoppable daemon.** `codeydOS stop`/`codey-stop` from C2 inspects the wrong record; the C1 record and process are never signaled. `stop` reports "already stopped" (DEAD/absent), which is false-clean.
3. **Two roots for one daemon inside one process.** The TUI `/cwd` (F9) changes cwd after the first resolve; the next fresh `resolve_daemon_paths()` (every `send_command`/`is_daemon_running` call re-resolves, `daemon.py:2250,2268`) lands under a second root. `get_config()` caches the *string*, not the path.
4. **Unreliable lock identity.** The lock/record inode check (`process_identity.py:217-223`) compares an `lstat` of the cwd-relative lock path with the held descriptor; after a cwd change the same string names a different inode, so the lock check can raise `UnsafeRecord` or, worse, validate against a different file.
5. **Relative CODEY_STATE_DIR spreads the same class across everything** (F1, F2, F8): config location, state.db, all six non-daemon service pid/log files.
6. **Error-shaped but silent inputs (F4):** `""` (pid file == cwd), `$HOME/x`, `./x`, `~bob/x`, `null`, numbers: today these become surprising relative paths, a `TypeError`/`RuntimeError` traceback, or a directory used as a file.

Residual that survives even with all-absolute paths (unchanged, not this slice): no pidfd, check-to-signal race (NEW-957 context), same-UID forgery.

### 1.4 Complete enumeration of daemon-path sources and consumers

Sources: (a) `config.json` `daemon.pid_file|socket_file|log_file`; (b) defaults from `CODEY_STATE_DIR` (F1); (c) `CODEY_STATE_DIR` as config-file locator (F2); (d) argv strings to `daemon_bootstrap` (`daemon_bootstrap.py:7-15`); (e) argv strings to `service_lifecycle.py usable-daemon` (`:220-229,309-310,336`; **no caller exists** anywhere outside tests/docs — dead command, grep); (f) argv to `process_identity.py` CLI (`inspect|stop|signal|record|cleanup <pid_file>`, `spawn --pid-file --log-file --cwd`, `process_identity.py:645-679,598-620`), fed only from the validated plan by `lib/service_lifecycle.sh:13,21,25,62`; (g) `create_default_config` persists F1 defaults (`daemon_config.py:119-125,156-159`, via `codeydOS config` `service_actions.py:146-148`) — with a relative root it would **write relative paths into config.json**.

Resolver consumers (inherit any check placed in `resolve_daemon_paths`): `core/daemon.py:124,143,181,953,2250,2268,2394`; `core/observability.py:215,238,262`; `core/cli_client.py:29`; `core/service_lifecycle.py:66` (-> `lock_exec`, `status`, `show_logs`, `path_data`); `ccos/plugins/system/daemon_control/daemon_control.py:107`.
Direct constructors (bypass the resolver): `core/daemon_bootstrap.py:15`; tests (`DaemonPaths(...)` in `ccos/plugins/system/daemon_control/test.py:50`, `tests/test_daemon_effective_paths.py`).
Not daemon paths (out of scope; do not conflate): model paths (loader/registry, never daemon config), `state.db_path` in `DEFAULT_CONFIG["state"]` (**dead key**: no reader in `core/state.py`/anywhere — grep of `"state"` keys; `docs/configuration.md` advertises it anyway), non-daemon service files (S3).

Exception handling today at each consumer (this is what the refusal design must respect):

| Consumer | Today on a resolver exception | Evidence |
|---|---|---|
| `daemon.main` startup | uncaught -> traceback | `daemon.py:2390-2398` |
| `daemon.check_pid_file` | caught only `(OSError, UnsafeRecord)` -> returns `True` (blocked) | `daemon.py:124,132-135` |
| `daemon.is_daemon_running`, `send_command` | propagate | `daemon.py:2246-2283` |
| `daemon_task_in_progress` | `except Exception` -> **True (busy), fail-closed** — the model to follow | `daemon.py:2321,2346-2363` (try around `is_daemon_running`/`send_command`) |
| `main._daemon_is_running` | `except Exception: return False` | `main.py:145-155` |
| `main.shutdown()` | `if _daemon_is_running(): return` else **unloads the model** | `main.py:302-330` |
| `main` gate recovery | False -> logs "no verified reachable daemon", returns not-recovered | `main.py:208-212` |
| `planner_service` | inside a try -> returns `None` (fallback) | `core/planner_service.py:40-45` |
| `cli_client.main` | catches `(ClientError, OSError, ValueError, TypeError, KeyError, AttributeError)` -> `[ERROR] msg`, rc 1; **not** `RuntimeError` | `cli_client.py:167-169` |
| `service_lifecycle.main` | catches `(OSError, UnsafeRecord, ValueError, TypeError)` -> fixed "Service mechanics unavailable or unsafe", rc 2; not `RuntimeError` | `service_lifecycle.py:343-345` |
| `service_actions._worker_main` | `except Exception` -> same fixed text, rc 2 | `service_actions.py:156-158` |
| `main --status` / observability | uncaught -> traceback | `main.py:2237-2240` |

### 1.5 The operator's actual configuration (read-only checks)

- `~/.codeyOS/config.json` **does not exist** (`ls`: "No such file or directory"). No `CODEY_STATE_DIR`/`CODEY_*` variable is exported in the session environment, and no shell rc file under `$HOME` sets one (grep). The daemon therefore runs on the absolute F1 defaults (`/data/data/com.termux/files/home/.codeyOS/codeyOS.{pid,sock,log}`).
- The repo-root `config.json` (gitignored, mode 600) has no `daemon` section (grep for `"daemon"|pid_file|socket_file|log_file`: no match) and `DaemonConfig` does not read it anyway (F2). Its contents were not printed.
- No `~/.codeyOS/codeyOS.pid` exists (no recorded daemon).
- `docs/configuration.md:11-14` documents `~/.codeyOS/...` tilde paths; those expand to absolute and stay valid. `config.json.example` has no daemon keys. Nothing in the repo advertises a relative daemon path.

Conclusion: **zero behavior change for the operator's current install**; the break surface is hypothetical relative-config installs, of which none are evidenced.

---------------------------------------------------------------------------------------------------

## 2. What "require absolute" means (contract)

**Rule.** An effective daemon pid/socket/log path is accepted only if, after the existing default merge and leading-`~` expansion, it is a `str` that is non-empty, contains no NUL, is at most 4096 bytes, and `PurePath(value).is_absolute()`. Otherwise the operation **refuses** (fail closed, nonzero, clear message) *before* any directory creation, lock open, record read/write, signal, spawn, socket connect or bind.

**Never** `abspath`, `normpath`, `resolve()`, `realpath`, anchor to cwd or state root, or "fix up" a value. Reasons: (1) identity records use `O_NOFOLLOW` + `lstat` inode agreement (`process_identity.py:91,201,217-223`), so resolving symlinks would change which inode a record is keyed to; (2) any silent rewrite is exactly option B/C which Ish declined; (3) `/a/../b` is absolute and cwd-independent, so it is accepted verbatim.

**The check is on the effective value, not the raw config value**, because defaults are already relative whenever `CODEY_STATE_DIR` is (F1). Additionally the config file's own location must be absolute (F2): a relative `CODEY_STATE_DIR` is refused even if all three config values happen to be absolute.

**Exception type.** New `DaemonPathError(ValueError)` in `core/daemon_config.py` (ValueError so `cli_client`'s existing `except ValueError` prints it and `check_pid_file` can add it explicitly). The resolver converts the `TypeError`/`RuntimeError` of F4 into it. `service_lifecycle.py` (stdlib-only by design, `service_lifecycle.py:1-5`) converts it to a local `ServicePathRefused(identity.UnsafeRecord)` in `service_paths("daemon")`, so the lifecycle module stays decoupled from `utils.config` and every existing `UnsafeRecord`-aware handler remains fail-closed.

**Message content (exact wording is the implementer's; these elements are required and testable).** One line, no traceback: the field name (`daemon.pid_file`) or `CODEY_STATE_DIR`; the offending value shown as `repr()` truncated to 120 characters (control characters escaped; paths are already printed by `show_logs`, so no new disclosure class); the word "absolute"; the source (config file path or "default derived from CODEY_STATE_DIR"); and for a config-key source a second sentence: "If a daemon was started under this relative value, set the key to the absolute location it was started in before stopping it; tools will not scan for, adopt, move or stop it." No "did you mean" absolute suggestion computed from cwd (that would silently teach the unstable interpretation).

**No silent degradation.** Refusal is never reported as "daemon not running". Where an existing handler maps exceptions to "absent", the refusal must be surfaced (table in 3).

---------------------------------------------------------------------------------------------------

## 3. Decision table (path source -> today -> required -> test)

| Source / consumer | Today's semantics | Required semantics | Test (assert) |
|---|---|---|---|
| `config.json` `daemon.*_file` relative (`rel.pid`, `./x`, `a/b`) | Resolved against whichever process's cwd (1.2) | `resolve_daemon_paths` raises `DaemonPathError` naming key | each of the three keys, rel -> raises; message contains key + "absolute" |
| same, `""` / `null` / int / list / dict | `""` -> `.`; others `TypeError` | `DaemonPathError` | parametrized; no `TypeError` escapes |
| same, `$HOME/x` | relative literal | `DaemonPathError` | message shows the literal |
| same, `~/x` | expanded, absolute | **accepted** (unchanged) | resolves under disposable HOME |
| same, `~nosuchuser/x` | `RuntimeError` traceback | `DaemonPathError` | no `RuntimeError` escapes |
| same, `/abs/with space/x`, `/a/../b` | accepted | accepted unchanged, byte-identical in `str()` | existing custom-spaces cases still pass |
| same, NUL / >4096 bytes | `daemon_bootstrap` rejects later | `DaemonPathError` at resolver | parametrized |
| Defaults with relative `CODEY_STATE_DIR` (incl. `~/x` literal) | relative defaults | `DaemonPathError` (source "default derived from CODEY_STATE_DIR"), even if all three config keys are absolute | subprocess with `CODEY_STATE_DIR=relstate`; no `relstate/` created in cwd |
| `DaemonPaths(...)` constructed directly (bootstrap, tests) | no validation | `__post_init__` applies the same value rules | `DaemonPaths(Path("rel"),...)` raises |
| `daemon_bootstrap.main(argv)` | non-empty/NUL/size only, then relative accepted | add the absoluteness test to the **existing line-9 pre-import schema check** (`daemon_bootstrap.py:9`), so refusal precedes `from core.daemon import main` at `:12` (heavy import; `DaemonPaths(...)` is only constructed at `:13`-`:15`, after it). `DaemonPaths.__post_init__` is the second layer, not the first. Raises `ValueError("Invalid daemon path snapshot")` as today | flip `test_service_public_lifecycle.py:357`; extend invalid-schema parametrize (`:350`) with a relative value |
| `daemon.main` / `Daemon.__init__` / `DaemonServer.__init__` | traceback | `main()` catches `DaemonPathError`, `error(msg)`, `sys.exit(2)` (distinct from duplicate-block exit 1) before `check_pid_file`, mkdir (`:954-956`) and logging setup | in-process with patched `Daemon`, `check_pid_file`; none called; no dir created |
| `check_pid_file(paths=None)` | `(OSError, UnsafeRecord)` -> blocked | add `DaemonPathError` to the except tuple: still blocked (fail closed) | resolver raising -> returns `True` |
| `service_lifecycle.service_paths("daemon")` | relative accepted | raises `ServicePathRefused`; covers `lock_exec`, `status`, `show_logs`, `path_data` | see lifecycle rows |
| `lock_exec` start/stop/restart/reload/preflight, `all` | uses relative paths | refuse at `:156` before any lock/mkdir; `all`: nothing in the set is touched (worker-level test calls `lock_exec`/`_worker_main` in-process, bypassing the gateway, so the audit row is not in play) | patched `os.execvpe`, `subprocess.Popen`, `os.kill`, `os.killpg`, `identity.OwnedLaunch`, `LifecycleRecord.__enter__/signal/stop` all `raise AssertionError` **before** the call; assert rc 2, message on stderr, state root and cwd unchanged (no `*.lifecycle.lock`, no new dir) |
| `stop`/`codey-stop` with an invalid config while a record exists | inspects wrong record | still refuses (nothing signaled) — see "Stop under invalid config" in 5 | pre-existing disposable record under tmp; signal functions patched to raise |
| `status daemon`, `daemon-status` | relative accepted | refuse, message, rc 2 | rc 2, stderr message |
| `status all`, `logs all` | n/a | the daemon entry prints `daemon: REFUSED (<message>)`, other services still report, final rc 2 (READ-only, no authority at stake) | stdout has the other five names |
| `paths` data channel (`path_data`, `:246-267`) | emits relative | refuse before writing to the pipe; pipe delivers EOF with no data; stdout still empty | extend `private_path_data` helper |
| `usable-daemon` argv (`:220-229`; no caller) | accepts any non-empty | require absolute too (same validator) or delete the dead command; **default: validate**, log deletion as residual | relative arg -> rc 2 |
| `cli_client` (`status/task/cancel/--bg`) | relative accepted | `DaemonPathError` is a `ValueError` -> existing `[ERROR] <message>`, rc 1, no socket, no inspect | no `socket.socket` call (patched to raise) |
| `daemon.is_daemon_running`, `send_command` | propagate | propagate `DaemonPathError` unchanged (never convert to False/absent) | raises; no `socket` call |
| `main._daemon_is_running` | any Exception -> False | still False for generic failures; **log the refusal message at warning level** when the exception is `DaemonPathError` | warning emitted |
| `main.shutdown()` (`main.py:309`) | `_daemon_is_running()` False -> `loader.unload()` | **No behavior change: warn and proceed to the existing unload** (False stays False). Verified in code: `LlamaLoader.unload` (`loader_v2.py:1830-1857`) stops only a server this loader owns (`server.process is not None`); for an adopted/daemon server it drops the local reference and reservation and never stops the other owner's child. So proceeding cannot kill the daemon's model, while skipping unload on refusal would leak the TUI's own llama-server in the most likely misconfiguration (relative root, no daemon) — a rule-2 RAM leak with nothing left to stop it | `_daemon_is_running` returns False and logs the refusal warning; shutdown still calls the (patched) `unload` once |
| `main --status` / observability props | traceback | `main.py` catches `DaemonPathError` around `_observability_status()`, prints one-line message, exit 2; the property/plugin functions propagate (do not return `pid=None`, which would be a false "no daemon") | rc 2, message, no traceback |
| `daemon_control` plugin | propagate | unchanged (propagates; dispatcher reports error) | raises |
| `planner_service` | try -> None | unchanged (fallback is benign); the refusal is logged by `is_daemon_running` callers' existing warning path or not at all | no change expected; note in review |
| `loader_v2` model-upgrade gate | via `daemon_task_in_progress` fail-closed busy | unchanged | existing test |
| `process_identity.py` CLI / `lib/service_lifecycle.sh` | trusts argv | S2: refuse non-absolute `pid_file`, `--log-file`, `--cwd` (defense in depth; `LifecycleRecord` itself unchanged) | CLI rc 2 + `UNSAFE` on relative |
| `create_default_config` (`codeydOS config`) | writes defaults, relative if root is | refuse to write (resolver root check) | relative root -> rc 2, no file created |
| Non-daemon service roots (`service_lifecycle.py:68,107`) | raw `CODEY_STATE_DIR` | S3 | see S3 |

---------------------------------------------------------------------------------------------------

## 4. Slice plan (ordered, independently reviewable)

### S1 — validator, resolver, daemon startup, bootstrap and all consumer refusal handling (REQUIRED)

One logical unit because splitting consumer handling away leaves an interim state where a refusal
reads as "daemon absent" (the `main.py:309` hazard). If the reviewer wants two diffs, the only
acceptable seam is A = items 1-4, B = items 5-9, and A must then include the `main.py` shutdown guard.

Files (production):
1. `core/daemon_config.py` — `DaemonPathError`, value validator, `DaemonPaths.__post_init__`, resolver conversion of `TypeError`/`RuntimeError`, config-file-location check, `create_default_config` guard. Update the `resolve_daemon_paths` docstring (it currently documents the retained relative semantics).
2. `core/daemon_bootstrap.py` — rely on `DaemonPaths` validation; keep refusal before importing `core.daemon`; update docstring.
3. `core/daemon.py` — `main()` catch + exit 2; `check_pid_file` except tuple. Docstring of `main`.
4. `core/service_lifecycle.py` — `ServicePathRefused`, conversion in `service_paths`, message printing in `main()`; `status`/`show_logs` per-service refusal lines; `path_data` refusal; `usable_daemon` validation. Docstring of `service_paths` (currently says relative values retain current meaning, `:53`).
5. `core/service_actions.py` — `_worker_main` prints the refusal text before the generic handler.
6. `main.py` — `_daemon_is_running` warning (no `shutdown()` change, see section 3), `--status` catch.
7. `core/cli_client.py` — no code change expected (ValueError already caught); add test only. `core/observability.py`, `ccos/plugins/system/daemon_control/daemon_control.py` — no code change; add one comment line each only if touched.

Files (tests): flip `tests/test_service_lifecycle_mechanics.py:320` (`test_relative_custom_paths_are_not_reinterpreted_pending_product_choice`, currently asserts relative values pass through) to assert refusal and rename it; flip `tests/test_service_public_lifecycle.py:357`; extend `tests/test_daemon_effective_paths.py` (resolver matrix), `tests/test_cli_client.py`, `tests/test_main_tui_lock.py`/a new focused `tests/test_new959_absolute_daemon_paths.py` for the `main.py` branches. Grep found no existing fixture setting a relative `CODEY_STATE_DIR` (all use `tmp_path`-derived absolutes), so no other flips are expected; the implementer must re-grep after coding.

### S2 — shell/CLI defense in depth (COMPLETE, separately reviewed/live-verified)

`lib/service_lifecycle.sh` (`_codey_locked_identity` and `_codey_spawn_owned`: `case "$pid_file" in /*) ;; *) return 2 ;; esac`, same for `log_file`, `service_cwd`) and `core/process_identity.py` CLI (`main` and `_spawn_main` argument checks only; `LifecycleRecord` and the Python API stay untouched because loader/embed/plugin supervisors derive absolute paths from `CODEY_STATE_DIR` and widening the class is a different blast radius). Value: the Python plan is the only caller today, so this is belt-and-braces against future callers; it is not needed for correctness of S1. Tests: shell-fixture cases using the existing fail-closed wrapper in `tests/test_service_lifecycle_mechanics.py` (WRAPPER) with a relative pid arg, asserting `identity:*` is never reached and rc 2. Also delete or document the dead `DAEMON_DIR` variable (F6) here — it is a no-op shell edit but in a reviewed file.

### S3 — non-daemon service state root (COMPLETE, separately reviewed/live-verified)

`core/service_lifecycle.py` requires an absolute root for the six non-daemon
services and derives litestream cwd from the validated PID-path snapshot. S1
already makes a relative `CODEY_STATE_DIR` fail daemon operations; S3 closes
single-service operations too. It remained separate because it widened the
blast radius from daemon paths to every service lifecycle record. Related but
unscoped: Aigentik directory and Restoricon DB inputs accept relative values
and silently anchor them through `.resolve()`; they are application inputs,
not lifecycle PID/log roots (NEW-1002).

### S4 — docs (small, after S1)

`docs/configuration.md` (state that daemon paths must be absolute or `~/`-prefixed, `$VAR` is not expanded, `CODEY_STATE_DIR` must be absolute, and that `state.db_path` shown there is not honored), `CODEY_OS_MASTER_BLUEPRINT.md` roadmap note and `PROJECT_LOG.md`/`NEW_ISSUES.md` closeout done by the coordinator (not the implementer) with the honest tier: code-complete -> reviewer-approved -> live-verified.

Dependencies: S2 and S3 only depend on S1's validator naming; S4 depends on S1.

---------------------------------------------------------------------------------------------------

## 5. Behavior decisions (defaults chosen, with rationale)

- **Existing install with a relative path configured: refuse, do not auto-migrate.** This is the choice Ish made (option 1). No rewrite, no warning-and-continue, no scan for old records, no adoption.
- **Stop under invalid config: refuse everything, including `stop`/`codey-stop`.** Rationale: the right record cannot be identified, so any signal would be a guess (rule 3 spirit); the operator escape hatch is the message's instruction (set the key to the absolute location the daemon was started in, then stop). Accepted consequence: a daemon started before the change under a relative value cannot be stopped through the tooling until the config is corrected. Because no relative config is evidenced on this device (1.5) this is a theoretical cost; flag it in the closeout so a later reader knows it is deliberate.
- **READ diagnostics fail visibly, not softly:** `status`/`logs` of one service refuse; composites print the refusal for the daemon and continue for the rest.
- **Exit codes:** service tooling rc 2 (matches the existing "unavailable or unsafe" code), `cli_client` rc 1 (existing), `daemon.main` exit 2 (distinct from duplicate-block 1).
- **Accept `/a/../b` and symlinked absolute paths verbatim**; accept paths whose parent does not exist (mkdir stays an authorized-write concern of startup, unchanged).
- **Not added:** a check that pid/socket/log are three distinct paths, parent-directory ownership checks, or a state.db relocation. Logged as residuals.

## 6. Test strategy (fixtures forbid real kill/model/Popen)

- All refusal tests assert the **negative effects** explicitly: before invoking the unit under test, monkeypatch `subprocess.Popen`, `os.kill`, `os.killpg`, `os.execvpe`/`os.execv*`, `signal.pthread_kill` and `core.process_identity.OwnedLaunch` / `LifecycleRecord.__enter__` / `.signal` / `.stop` to raise `AssertionError("must not be reached on refusal")`; `socket.socket` patched the same way for client tests; the loader/`get_loader` and `llama` modules replaced by stubs that raise on use (no model). Patches are installed **before** the call, never after.
- No synthetic integer PID is ever created, recorded or signaled. Refusal tests create **no** pid records. The single "stop under invalid config with an existing record" case writes a record only inside `tmp_path`, with every signal entry point patched to raise before invocation (NEW-957 rule: a test-looking integer is never safe to signal).
- Every test runs with `HOME`, `CODEY_STATE_DIR`, `CODEY_ACTION_GATEWAY_AUDIT` pointing into `tmp_path` and with proxy variables unset (sandbox-proxy lesson); relative-path tests `monkeypatch.chdir(tmp_path)` and assert no `*.lifecycle.lock`, no new directory and no `.identity` file appears in cwd or the state root.
- Public-wrapper tests reuse the existing fail-closed WRAPPER/allowlist primitives (`tests/test_service_lifecycle_mechanics.py` header, `tests/test_service_public_lifecycle.py` harness) so any stray `python3`/`bash` service dispatch exits 91 instead of falling through to installed tools.
- Regression kept green: all existing absolute/custom-spaces/UDS cases in `tests/test_daemon_effective_paths.py`, `tests/test_service_lifecycle_mechanics.py`, `tests/test_service_public_lifecycle.py`, `tests/test_cli_client*.py`, `tests/test_new107_new109_observability_daemon_pid_uptime.py`, `ccos/plugins/system/daemon_control/test.py`.
- New resolver matrix is pure (no process, no filesystem): table-driven over the F4 inputs plus `~`, absolute-with-spaces and `/a/../b`.
- Run the focused set plus the full suite before review (guarded); record exact counts fresh — do not reuse stale counts.

## 7. Live-verification requirements (rule 4, rule 5, rule 7)

Required, disposable HOME and `CODEY_STATE_DIR` (absolute, throwaway), proxies unset, `free -h` recorded before/after, no model, no network, no existing service touched, `ps` baseline before/after:

1. **Refusal, no service effect** with a config of relative values (case A) and separately a relative `CODEY_STATE_DIR` (case B): run the real installed entrypoints `codeydOS start|stop|restart|reload|status|config`, `codeyOS status`, `codey-stop`. **Do not run `python3 main.py --status` live**: importing `main.py` triggers the NEW-855-class import-time state creation (`state.db` etc.) before any refusal can run, so it cannot show "no files created"; its refusal branch is covered by unit test only. Capture verbatim stderr, rc, and a before/after listing + SHA of the state root and cwd, plus a `ps` diff (empty), against the **expected-effects whitelist** below. `PATH` is restricted to a fail-closed stub directory so any service exec would fail loudly.
   - **Expected-effects whitelist (public wrapper path):** the seven wrapper operations go through `run_public` -> `ActionGateway.gate_exec`, which writes **one best-effort local audit row after the worker returns** (`core/action_gateway.py:114-131,_audit_exec`, outcome "failed"/refused) and `mkdir`s the audit file's parent first (`:121`); direct `codeyOS status` produces no local audit row. So the whitelist is exactly: one new line per wrapper operation in the file named by `CODEY_ACTION_GATEWAY_AUDIT` (set to an absolute disposable path for every case), no line for direct `codeyOS status`, and nothing else. Anything else (a `*.lifecycle.lock`, `.identity`, `.pid`, a new directory in cwd or the state root, a log file) is a failure.
   - **Case B caveat (audit sink):** `audit_path()` falls back to `CODEY_STATE_DIR` when `CODEY_ACTION_GATEWAY_AUDIT` is unset (`action_gateway.py:109-111`), so with a relative root and no override the audit append itself would create a cwd-relative directory — the same bug class, in the gateway, not in daemon-path code. Out of scope for NEW-959 (residual 9 in section 10). The live run therefore always sets the absolute override; the *absence of lifecycle writes* under a relative root is additionally proven at worker level (`service_actions._worker_main`/`lock_exec` called in-process with patched effects, no gateway) in the unit tests.
   - Import-chain check for the refusal path: `utils/config.py` and `core/daemon_config.py` have no import-time `mkdir` (grep: `daemon_config.py:119,126` only inside `save`/`create_default_config`; none in `utils/config.py`). `core/action_gateway.py` imports `core.filesystem`; the live run's before/after SHA of the state root is what proves no import-time state is created on the refusal path — if it shows a write, record it as a finding rather than relaxing the whitelist.
2. **Positive regression, absolute paths with spaces and `~/`:** rerun the audited simulated-profile public start/reload/restart/stop/status harness used for 13c.2b.3 (stubbed setup/backup/cloud effects, fail-closed command allowlist, retained Popen handles, no model, no actual daemon — the prior reports state "No actual daemon or model process ran"). Same verbatim-output standard as `docs/wp2_1_group13c2b3_live_resumed.md`.
3. **One end-to-end disposable daemon-like cycle is NOT required**: the change adds a refusal in front of unchanged mechanics; a real daemon/model start would add RAM risk (rule 2) without testing anything new.
4. **Cross-cwd regression (the original bug), positive form:** with an *absolute* custom pid/socket in a disposable root, run `status` from two different cwds and show both resolve the identical record (this proves cwd independence is now structural).

Closeout achieved: S1 is code complete, reviewer APPROVED, and live verified
(items 1, 2, and 4). S2 and S3 are separately reviewer-approved and
live-verified. NEW-959 is FIXED; see the execution status and durable report.

## 8. Rule 4 review focus (for the code-reviewer brief)

- The refusal precedes every daemon-path `mkdir`/lock open/spawn on every path in 1.4 (resolver, `lock_exec:156` ordering, `Daemon.__init__:954`, `LifecycleRecord.__enter__:198`). It does **not** precede the Action Gateway's single post-worker audit row on the public wrapper path (`action_gateway.py:114-131`); that is expected and whitelisted (section 7), not a violation.
- No new place where a refusal is converted into "absent/not running/DEAD" except the explicit, justified `main._daemon_is_running` (warning logged) and `planner_service` (benign fallback).
- `main.shutdown()` is deliberately unchanged: refusal still reads False there, which is safe because `unload()` only stops an owned child (`loader_v2.py:1830-1857`); the reviewer should confirm that reading rather than expect a guard.
- No `abspath`/`resolve`/`realpath`/cwd join added anywhere; the validator is a predicate.
- Messages contain only the offending path value (escaped), config key and fixed text; no cwd-derived suggestion; no secrets (config values other than the three path keys are never echoed).
- Existing fail-closed behavior of `check_pid_file` preserved, including the `is_current_self_record` self-race protection (`daemon.py:126-129`) — the new except branch must not alter that ordering.

## 9. Product forks for Ish

**None genuinely open.** Ish chose "require absolute"; the only alternative
that touches existing installs (auto-migrate) is rejected option B. No relative
daemon configuration exists on this device, and current docs/examples do not
advertise one. Stop refuses under invalid config and S3 is complete. Making
stop possible without correcting config would be a new product decision and
would require an explicit operator-supplied absolute record path.

## 10. Residuals / findings logged at closeout

1. NEW-1000: daemon config-file authority mismatch.
2. NEW-1001: dead/documentary `state.db_path` key.
3. The dead shell `DAEMON_DIR` assignments were removed in S2 (closed here).
4. NEW-1005: caller-free `usable-daemon` cleanup.
5. NEW-1002: relative inputs are accepted and cwd-anchored by Aigentik/Restoricon config helpers; loader/embed/plugin reachability remains suspected.
6. NEW-1004: path distinctness and parent-directory safety are not enforced.
7. Repo-root hex-directory hygiene was already tracked as NEW-277/451.
8. A pre-change daemon launched under a relative value cannot be stopped through tooling until config is corrected (documented consequence, not a separate defect).
9. NEW-1003: Action Gateway's fallback audit sink remains cwd-relative under a relative state root.

## 11. Completed closeout records

Completed 2026-10-18: `NEW_ISSUES.md` NEW-959, the blueprint WP2.1 status
note, `PROJECT_LOG.md`, and the group 13 historical pointer were updated. The
durable report carries exact counts and raw-report hashes.
