# WP2.1 slice G15h — credential exposure (G15b-12 FN; G15b-48 redaction gaps; D-2 option (c) deferred)

Spec only (project-architect, 2026-10-24). No source, test or ledger file was edited to produce it. Base: HEAD `9a61e94` plus
UNCOMMITTED foreign work (G15e `core/protected_paths.py`, `tools/shell_tools.py`, `core/filesystem.py`, file tools; G15f `bench/*`),
all read-only here. `core/service_lifecycle.py`, `core/process_identity.py`, `lib/service_lifecycle.sh`, `core/action_gateway.py`,
`core/sessions.py`, `core/export_hygiene.py`, `utils/logger.py` are **unmodified in the working tree** (git status), so every
probe below ran against HEAD bytes for those files.

Scope: G15b-12 (`NEW-1021`, FN: secret out of argv), the redaction gaps of G15b-48 (`NEW-1033`, promoted from QUEUE by the task
statement) found by auditing every persistent writer that can carry argv/env/command text. **Out of scope, pending Ish:** D-2
option (c) (environment allowlist for ALL children). Ish decided option (b) only on 2026-10-23; (c) is DEFERRED and stays so.

## 0. Threat-model correction (rule 6: read this before the severity on NEW-1021)

`docs/wp2_1_g15b_consolidated.md` G15b-12 says HIGH, "readable via `cat /proc/<pid>/cmdline`". The artifacts bound that claim:

- `/proc` is mounted `proc /proc proc rw,relatime,gid=3009,hidepid=invisible` (`/proc/mounts`, read 2026-10-24). Processes of other
  uids are **invisible** to ordinary callers; only uid-equal code and members of gid 3009 (the `adb shell` identity) can list them.
  The exposure is therefore **same-uid (the agent, any script it runs) plus adb**, not "any local reader".
- Same-uid code can already read `~/.codeyOS/age.key` and `~/.codeyOS/cloudflare_tunnel_token.age` (both mode 0600, owner = the
  agent's uid, `ls -l` 2026-10-24) and decrypt the token itself with `age -d`. **Moving the token out of argv creates no
  boundary against a same-uid script child** (this is the consolidated section 1 ceiling, G15b-19). The shell tool itself refuses
  the direct reads (G15d D-2(b) credential scan), a script does not.
- What the fix genuinely buys: (1) the token stops appearing in `ps`-class listings and in `/proc/<pid>/cmdline` (mode 0444,
  probed), which are the channels that reach the model *without touching a credential path*; (2) it removes the CCOS
  `system_info.list_processes` leak (section 1, fact F7), which is outside the shell classifier entirely; (3) it removes the token
  from the `bash -c` mechanics argv and the `process_identity.py spawn` helper argv, which today carry it as well (F3); (4) it
  removes the class "a `CalledProcessError`/`TimeoutExpired` repr of a launcher argv leaks the token" (those exceptions embed argv).
- Recommended framing for `NEW-1021`: **Medium (same-uid, defence in depth; closes a D-2(b) side-channel), not HIGH.** HIGH stays
  defensible only if "readable by the agent without a prompt" is the criterion; state which criterion the register uses.

## 1. Verified facts (artifact reads and probes, 2026-10-24; scratch only, disposable HOME/state, no network, no model, no live service)

| # | Fact | Evidence |
| --- | --- | --- |
| F1 | The only secret-in-argv launcher in the repo is cloudflared: `argv = ["cloudflared","tunnel","run","--token", token]` | `core/service_lifecycle.py:123-127`. Repo-wide scan for `--token/--password/--secret/--api-key/Authorization/Bearer` in argv-building code (non-test, non-restoricon-JS): no other hit. Other `subprocess` argv carrying key-ish values are age **public** keys (`core/backup_secrets.py:163`, `core/backup_documents.py:44`, `tools/encrypt_cloudflare_token.py:52`) or a key **path** (`utils/config.py:~690` `age -d -i <path>`; token read via `capture_output`, never argv). litestream: `-config <path>` only (`:122`). aigentik: `[runtime, script]` only (`:117`); its secret `AIGENTIK_INTERNAL_TOKEN` is env/file (`utils/config.py:856`). |
| F2 | Token sources, in precedence order: env `CLOUDFLARE_TUNNEL_TOKEN`/`CLOUDFLARED_TOKEN`; `~/.codeyOS/cloudflare_tunnel_token.age` decrypted with `age -d -i age.key` (WP0.7); legacy `config.json` plaintext. | `utils/config.py:697-731`. The repo-root `config.json` `cloudflare` section is now empty (`{}` plus a `_note`; keys listed without values, 2026-10-24); the plaintext copy is gone. The state dir holds `cloudflare_tunnel_token.age` (0600). |
| F3 | The token travels through **three** processes' argv, not one: (a) `lock_exec` puts `argv` into `plan` and `os.execvpe("bash", ["bash","-c",_BASH_FRAGMENT,"codey-service-mechanics",lib,service,operation,size,*plan], dict(os.environ))` => the `bash` mechanics process cmdline; (b) `lib/service_lifecycle.sh:69-71` `exec python3 core/process_identity.py spawn ... -- "${child_argv[@]}"` => the helper cmdline (lives through the 0.5 s startup check, and indefinitely if it becomes a retained guardian, `process_identity.py:573-589`); (c) `OwnedLaunch.run` `subprocess.Popen(self.argv, cwd, stdin=DEVNULL, stdout=log, stderr=STDOUT, close_fds=True)` => cloudflared itself, permanent. No `env=` is passed to that Popen, so the child inherits the helper's environment unchanged. | `core/service_lifecycle.py:195,198`; `lib/service_lifecycle.sh:62-73,195,211-218`; `core/process_identity.py:543-547`. The before-state through the real chain is measured in section 2. |
| F4 | cloudflared 2026.10.1 supports **three** token routes, read from the installed binary's own help (`cloudflared tunnel run --help`, rule 12): `--token value [$TUNNEL_TOKEN]` ("takes precedence over token-file"), `--token-file value [$TUNNEL_TOKEN_FILE]`, `--credentials-contents [$TUNNEL_CRED_CONTENTS]`. | Verbatim help read 2026-10-24. |
| F5 | All three routes reach cloudflared's token parser: with the fabricated, malformed canary `FAKE-G15H-CANARY-0123456789abcdef`, `--token`, env `TUNNEL_TOKEN`, `--token-file <regular 0600 file>`, `--token-file /proc/self/fd/N` over an **unlinked file** and over a **pipe** each print `Provided Tunnel token is not valid.` (rc 255, no network contact: it fails before connecting); a nonexistent token-file prints `Failed to read token file: ... no such file or directory`; no token prints `requires the ID or name of the tunnel`. So "the value was read" is distinguishable from "not found". | Probes 2026-10-24, scratch dir. A syntactically valid token was **not** used (it would contact Cloudflare). Whether cloudflared re-reads a token-file after start is **unverified** (cannot be proved without a real tunnel), which is why the fd/pipe route is rejected in section 3. |
| F6 | Exposure matrix for a process started with the canary (probed with stand-in sleepers): argv route => canary in `/proc/<pid>/cmdline` (mode `-r--r--r--`) and in `ps -A -o pid,args`; env route => cmdline clean, `ps` clean, canary only in `/proc/<pid>/environ` (mode `-r--------`); token-file route => neither (path only); a sibling same-uid process could read an inherited unlinked-file fd via `/proc/<pid>/fd/N` (canary readable). | Probes 2026-10-24. |
| F7 | A second, non-shell argv reader exists: CCOS capability `system_info.list_processes` runs `ps aux --sort=-pcpu` and returns `parts[10][:100]` (the first 100 chars of every visible process's argv) as a dict list. With a stand-in process whose argv was `... cloudflared tunnel run --token FAKE-G15H-CANARY-0123456789abcdef`, the capability returned the canary row (24 rows, 1 hit). Registered in `ccos/data/capabilities.json` and `ccos/plugins/system/system_info/manifest.json`. | `ccos/plugins/system/system_info/system_info.py:30-48`; probe 2026-10-24. Reachability from the model: via the CCOS capability dispatch (`call_capability`, unmediated per NEW-910, see group 4 spec). The 100-char cut would expose about 69 characters of a real token (the flag prefix is 31 chars): partial, but enough to matter. |
| F8 | What G15d D-2(b) already closes, measured end to end through the real `shell()` at a `git archive HEAD` copy with `yolo=True` and a live stand-in process carrying the canary in argv: `cat /proc/<pid>/cmdline`, `head -c 400`, `tail -c 400`, `cut -c1-300`, `grep -a token`, `diff ... /dev/null`, `cat /proc/<pid>/task/<pid>/cmdline`, `/proc/./<pid>/`, `/proc//<pid>/`, `/proc/../proc/<pid>/`, `/proc/<pid>/cwd/../cmdline`, `/proc/<pid>/environ`, `/proc/<pid>/stat`, `find /proc/<pid> -maxdepth 1 -name cmdline` => **14 of 14 forms** returned `[BLOCKED] HIGH_IMPACT ...`, no canary in any output. The 15th form `cat /proc/*/cmdline` fails only because `shell()` uses `shlex.split` without a shell, so the glob is never expanded (`cat: '/proc/*/cmdline': No such file or directory`); this is luck of the execution model, not a rule, and the classifier reports it READ with the credential scan False. `ps`, `ps aux`, `pgrep -af`, `top -b`, `strings`, `xargs`, `printenv`, `env` classify HIGH_IMPACT because of G15c default-deny (not because of D-2). | `tools/shell_tools.py` at HEAD (`git archive`), scratch `e2e_probe.py`/`cls_probe.py`; disposable HOME, state and audit path. |
| F9 | What D-2(b) does NOT close for G15b-12: (i) any script child (`python3 x.py`, `bash x.sh`) reading `/proc/*/cmdline` or running `ps` (ceiling, G15b-19); (ii) `system_info.list_processes` (F7); (iii) interactive-confirm modes by design (the operator is shown the HIGH warning and may say yes); (iv) adb/readproc-group readers outside the agent; (v) the transient `bash` and helper cmdlines (F3 a/b). |  |
| F10 | Redaction state of the persistent writers (section 4 has the full table): `core/sessions.py::redact_secrets` has 5 patterns and masked **2 of 15** probe shapes (`--password=`, `ghp_`); `core/export_hygiene.py::find_secret` (24 patterns) detected 11 of 15 (it misses the cloudflared `--token <b64>` and bare cf token, `AGE-SECRET-KEY-1...`, and `.netrc` `password`); `core/service_actions.py::_show_config` redacts by key substring `token/secret/api_key` only. The action-gateway audit ledger writes `command` verbatim; the daemon file logger writes every message verbatim. | Probe `redact_probe.py` 2026-10-24 (fabricated canaries only); `core/action_gateway.py:523-535`, `utils/logger.py:59-63`. |
| F11 | The service-lifecycle **public** audit row never carries argv: `command="service " + label` (`core/service_actions.py:~130`), and the worker/spawn error paths print fixed text ("the service argv is never printed", `core/process_identity.py:638`). The live audit ledger and all five service logs in `~/.codeyOS` contain no `eyJ`-shaped 80+ char blob, no `--token`, no `Bearer ...` (count-only greps, 2026-10-24). cloudflared masks its own flag in its startup log: `INF Settings: map[token:*****]` (87 occurrences in `cloudflared.log`), so the env route keeps that behaviour (the env var feeds the same `token` flag). | `core/service_actions.py`, count-only greps on `~/.codeyOS/*.log`, `action_gateway_audit.jsonl`. |
| F12 | `age-keygen` secret-key format (verified against a freshly generated throwaway key, printed nowhere but a length/regex check): 74 characters, matches `AGE-SECRET-KEY-1[QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L]{58}`. | Probe 2026-10-24. |
| F13 | The token is **not** in the operator's current ambient environment (`env` names only; no `*TUNNEL*`/`CLOUDFLARE*`). The telemetry comment at `utils/config.py:884-886` says the live env "carries" `CLOUDFLARE_TUNNEL_TOKEN`; that is a statement about an earlier session, not evidence about launch time. Whatever the operator's shell exports at `codey-start` is inherited by **every** service child (`lock_exec` passes `dict(os.environ)`, `process_identity` passes no `env=`): this is the deferred D-2(c)/G15b-11 item. | `env` listing 2026-10-24; `core/service_lifecycle.py:198`. |

## 2. Before-state through the real chain (measured 2026-10-24; this is the baseline the fix is judged against)

Method (Appendix A has the harness): disposable `HOME`, `CODEY_STATE_DIR`, `CODEY_ACTION_GATEWAY_AUDIT`; the canary is delivered through a
disposable age-encrypted `cloudflare_tunnel_token.age` (a throwaway `age-keygen` key), **not** through `CLOUDFLARE_TUNNEL_TOKEN` (an ambient env
source would make the environ assertions meaningless; the harness also `env -u`s `CLOUDFLARE_TUNNEL_TOKEN`, `CLOUDFLARED_TOKEN`, `TUNNEL_TOKEN`,
`TUNNEL_TOKEN_FILE` and the proxy variables); a **stub `cloudflared` first on `PATH`** records, at its own startup, whether the canary is in its
own argv/environ, in its parent's and grandparent's cmdline/environ, and in every `/proc/*/cmdline|environ` (t0, and again at t0+2 s). Only
`lock-exec cloudflared start` then `lock-exec cloudflared stop` are invoked (never `all`: that starts the daemon and loads models, rule 2). The
stub idles at most 24 s and is stopped by the lifecycle `stop` operation through the recorded identity (no `pkill`, no name-pattern kill).

| observation | before (HEAD) |
| --- | --- |
| `lock-exec cloudflared start` / `stop` | rc 0 / rc 0; "started (verified process identity ...)"; "stopped (verified owned-process exit)"; no stray process afterwards |
| stub argv | `[.../stubbin/cloudflared, tunnel, run, --token, <CANARY>]` (canary present) |
| stub `/proc/self/environ` | canary absent; `TUNNEL_TOKEN` not in env |
| parent (the `process_identity.py spawn` helper) cmdline | **canary present** (argv0 `python3`) |
| grandparent (the `bash -c "source ...; _codey_service_operation"` mechanics process) cmdline | **canary present** (argv0 `bash`) |
| parent / grandparent environ | canary absent |
| global `/proc/*` scan at t0 | **3 hits, all `cmdline`**: bash mechanics, spawn helper, the stub |
| global scan at t0+2 s | 1 hit (the stub's cmdline; helper and bash had exited) |
| canary on disk under the run dir (audit ledger, state.db, logs, pid/lock files) | none (only the harness's own canary file and the age ciphertext) |

Real binary baseline (same chain, real `cloudflared`, canary is the malformed token): start rc 2 ("launch failed"), `cloudflared.log` =
`Provided Tunnel token is not valid.`, stop rc 0 (`absent-dead`), nothing left running, no network contact (it fails in the parser, before any
connection). After the fix the same observable (rc 2, same log line) must hold: it is the proof that the env-delivered value reached cloudflared's
token parser (without it the log would read `"cloudflared tunnel run" requires the ID or name of the tunnel to run`, F5).

## 3. Unit A design — move the token out of every argv (G15b-12, `NEW-1021`; rule 4)

### 3.1 Options considered (decision basis: F4-F6, section 0)

| option | verdict |
| --- | --- |
| O1 `--token-file <regular 0600 file>` | **Rejected.** Reverses WP0.7 (Ish decision 7: the token left plaintext-at-rest; `~/.codeyOS/cloudflare_tunnel_token.age` is the only at-rest form). Would also add a new plaintext credential path to the G15d read set and the G15e protected set. Needs Ish; not chosen. |
| O2 `--token-file /proc/self/fd/N` (pipe or unlinked file) | **Rejected.** Parses (F5), but (i) needs `pass_fds` threaded through `close_fds=True` in `OwnedLaunch.run` and the bash `_close_extra_fds` discipline (more rule-4 surface); (ii) a pipe is read-once and whether cloudflared re-reads the token file after start **cannot be verified without a real tunnel** (rule 12; unverified, so not assumed); (iii) an unlinked file keeps plaintext on flash for the process lifetime and a sibling same-uid process can read it through `/proc/<pid>/fd/N` (F6); (iv) `os.memfd_create` does not exist in this Python build (`AttributeError`, probed), so no purely in-memory file is available. |
| **O3 env `TUNNEL_TOKEN` in the final `Popen` only** | **Recommended.** cloudflared documents `--token [$TUNNEL_TOKEN]` (F4) and parses the env value (F5). Argv of all three processes becomes clean; `environ` is `-r--------` (owner only, F6) and is not shown by `ps`; no disk copy; no re-read dependency. |
| O4 token in `lock_exec`'s env or bash env | **Rejected.** `lock_exec` passes one environment to the bash mechanics for **all** services of an `all` operation; the daemon (and through it the agent's shell children) would inherit the token. That makes G15b-11 worse. |
| O5 exec wrapper (`core/service_exec.py` resolves the token in the child, then `os.execvpe`) | **Fallback only**, if the reviewer rejects touching `OwnedLaunch`. Same exposure result, but a decrypt failure becomes a late exit after publication (the 0.5 s liveness window has passed) instead of a clean pre-spawn failure, and it adds an exec layer plus a second `PATH` resolution of `python3`. |

### 3.2 Mechanism (finite selector, no new argv channel)

- **A-1 `core/service_lifecycle.py::start_profile` (cloudflared branch, :123-127).** Return `argv = ["cloudflared","tunnel","run"]` when
  `shutil.which("cloudflared")` and a token is configured, else `[]`; `missing = not configured`. The decrypted value is used only for the boolean
  and is **never stored** (no `token` local kept in the returned tuple). Behavior for "no token / no binary" is unchanged ("optional service
  unavailable/not configured; skipped"). Add a comment that the secret is delivered by the spawn helper, and why (section 0). `status()` already
  never calls `start_profile` for cloudflared, so `codey status` still performs no decryption.
- **A-2 `core/process_identity.py`.** Add a fixed table `_SERVICE_SECRET_ENV = {"cloudflared": "TUNNEL_TOKEN"}` (service key -> env name; the
  *source* is hard-wired in the resolver, not configurable) and `_service_env_provider(service)` returning `None` for every other service. For
  `cloudflared` it returns a zero-argument callable that: imports `utils.config` with the repo root on `sys.path` (same pattern as
  `service_lifecycle._config_helpers`; the helper runs as a script from `core/`), calls `get_cloudflare_tunnel_token()`, raises
  `UnsafeRecord("Service credential unavailable")` (fixed text, no value) when it is falsy, and returns a **copy** of `os.environ` with
  `CLOUDFLARE_TUNNEL_TOKEN` and `CLOUDFLARED_TOKEN` removed (the consumed sources; cloudflared does not read them) and `TUNNEL_TOKEN` set. The
  helper's own `os.environ` is never mutated, so the token does not appear in the helper's `/proc/<pid>/environ`.
- **A-3 `OwnedLaunch`.** New optional parameter `env_provider=None`. In `run()`, immediately before the `Popen` (inside the existing `try`, after
  `record.inspect()` and `cleanup`, so a blocked launch never decrypts), call it; pass `env=` to `Popen` **only when not None** (the kwargs of every
  other service stay byte-identical; existing fakes that assert exact kwargs keep passing). An exception from the provider flows to the existing
  `except BaseException: pass` -> `finish_failure()` path: no child exists, `_reap_owned()` is True, `_report("failed-cleanup-confirmed")`, rc 2,
  record cleanup, lock released by the normal exit. No new signal, PID, lock or kill logic is added. `_spawn_main` passes
  `env_provider=_service_env_provider(args.service)`.
- **A-4 Invariants to state in the docstrings and pin by tests:** (1) no value from argv ever becomes an environment entry (an argv element
  `TUNNEL_TOKEN=x` stays a plain argv string); (2) only the table's service key gets an injected variable; (3) the helper's diagnostics stay
  payload-free (`process_identity.py:638`); (4) the secret exists in the helper only between provider call and `Popen` return.

Docstrings to add or update (rule 5, touched code only): `start_profile` (why cloudflared returns no secret), `OwnedLaunch` (env_provider and
the failure mapping), `_service_env_provider` (the finite selector and why it is not argv-configurable), and a module comment at
`_SERVICE_SECRET_ENV` naming the threat model (section 0).

No change to `lib/service_lifecycle.sh`, `core/service_actions.py` (public audit rows carry only `service <label>`, F11), `install.sh` or
`requirements.txt` (no dependency added; rule 11 not triggered). No new credential-bearing path appears, so the G15d credential read set and the
G15e protected-path set need no entry.

## 4. Unit B design — redaction gaps (G15b-48 / `NEW-1033` promoted, plus the new findings)

### 4.1 Writer audit (every persistent or externally-visible sink that can carry argv, env or command text)

| # | writer | carries | today | disposition |
| --- | --- | --- | --- | --- |
| S1 | action-gateway audit ledger `~/.codeyOS/action_gateway_audit.jsonl` (`core/action_gateway.py` `_append_audit`, rows built at :381-390, 454, 483, 505, 523-535) | `command`, `reason` verbatim | unmasked | **Unit B-3** (needs Ish Q-a) |
| S2 | file logger `utils/logger.py::_log_to_file` (:59-63) -> `codeyOS.log` in daemon mode; receives every `info/warning/error/think/debug` message including the `warning(f"...: `{command}`")` lines in `shell()` | any text | unmasked | **Unit B-4** (file sink only; console untouched) |
| S3 | session files `~/.codey_sessions/*.json` (`core/sessions.py::redact_secrets` :19-40, applied in `save_session`) | whole conversation | 5 patterns; masked **2 of 15** probe shapes | **Unit B-2** (correction of the C06 statement, rule 6, see 4.2) |
| S4 | `codey config` display `core/service_actions.py::_show_config` (:180-185) | config dict | key-substring `token/secret/api_key` only | **Unit B-5** |
| S5 | CCOS capability `system.processes` (`system_info.list_processes`, F7) | argv of all visible processes | unmasked, 100-char cut | **Unit B-6** |
| S6 | trajectory DB (`core/trajectory.py:12`) | prompts, tool args and results | unscrubbed **by design**; default OFF; `CODEY_TRAJECTORY` stays off until WP0.5/NEW-761 | **No change.** Export-side scrubbing gets the new patterns for free because `find_secret` reads the shared table. |
| S7 | `state.db` `episodic_log` (`core/agent.py:840` `result[:100]`; planner `description[:200]`/`result[:100]`/`error_msg[:200]`, `core/planner_v2.py:135,233,274`) | prefixes of tool output and prompts | unmasked | **Not argv/env; queued** (new id, Suspected, future trigger: a secret-bearing result observed there) |
| S8 | five-tier memory (`core/memory_v2.py`), checkpoints (`core/checkpoint.py`: file lists and a git hash only, `:155`) | content, not argv | no secret handling in either | **Queued, Suspected** (not audited line by line here) |
| S9 | telemetry/provenance | env | allow-list plus presence-only booleans for `OPENROUTER_API_KEY`, `UNLIMITEDCLAUDE_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN` (`utils/config.py:900-919`); `llama_server_argv` carries no secret flag (no `api-key` argument exists in `core/loader_v2.py`/`core/embed_server.py`, searched) | **No change** |
| S10 | service logs written by the services | whatever they print | cloudflared masks its own token (`Settings: map[token:*****]`); count-only scans of all five logs and the audit ledger found no `eyJ` blob, `--token` or `Bearer` | **No change** |
| S11 | process identity records; public service audit rows | fixed 6-key JSON (`process_identity.py:53-77`); `service <label>` | no argv | **No change** |
| S12 | exception reprs (`CalledProcessError`/`TimeoutExpired` embed argv) | argv | the only secret-in-argv launcher was cloudflared and it never used `subprocess.run` in a logged path | **Closed by Unit A**; residual: any future secret-in-argv |
| S13 | console / TUI | the operator's own screen | not persistent | **No change** (the operator must still see the real command) |

### 4.2 Measured redaction gaps (fabricated canaries only, 2026-10-24, `redact_probe.py`)

`core/sessions.py::redact_secrets` masked: `--password=`, `ghp_` (2 of 15). It leaked: cloudflared `--token <b64>`, a bare cloudflared token,
`TUNNEL_TOKEN=`, `export CLOUDFLARE_TUNNEL_TOKEN=`, `AGE-SECRET-KEY-1...`, `.netrc` `password`, `sk-or-v1-...`, `sk-ant-...`, `Authorization: Bearer ...`,
`mysql -pPW`, `AIGENTIK_INTERNAL_TOKEN=`, `hf_...`, an SSH private-key header. `core/export_hygiene.py::find_secret` detected 11 of 15 and **missed**
the cloudflared `--token <b64>` form, the bare cloudflared token, `AGE-SECRET-KEY-1...` and the `.netrc` `password`. **Correction (rule 6):** the G15b
consolidated entry for G15b-48 (and hunter C row C06) says the redactors "catch `NAME=token`, `sk-or-`, GitHub tokens"; that holds only for
`find_secret` (training-export), not for `sessions.redact_secrets`, which catches only `ghp_` and `password=`/`"password":`.

New patterns (all five were tested in scratch: every positive matched, every negative did not, and each is linear on 1 MB adversarial inputs, all
under 0.5 s; the table below is the acceptance set, to be pinned by tests):

| name | regex (proposed) | positives | negatives |
| --- | --- | --- | --- |
| `age_secret_key` | `\bAGE-SECRET-KEY-1[QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L]{58}\b` | a real `age-keygen` key (74 chars, F12) | `AGE-SECRET-KEY-1 placeholder` |
| `base64_json_blob` | `(?<![A-Za-z0-9+/_\-])eyJ[A-Za-z0-9+/_\-]{80,}={0,2}` | a cloudflared-shaped token; `TOKEN: <blob>.` | `eyJhbGciOiJIUzI1NiJ9` (short JWT header), prose "see eyJ in docs" |
| `secret_flag` | `(?<![A-Za-z0-9_\-])--(?:token\|password\|passwd\|api-?key\|secret\|access-?token\|auth-?token\|client-?secret)(?:=\|[ \t]+)['"]?(?![\-$%{/~<])[^\s"'\\]{8,}` | `cloudflared tunnel run --token <b64>`, `--password=Sup3rS3cretPw`, `--password 'Sup3rS3cretPw'`, `--api-key abcdef123456` | `--token-file /x/y`, `--token $VAR`, `--token <your-token>`, `--token-name`, `--secret-name abc` |
| `netrc_inline` | `(?i)\bmachine[ \t]+\S+[ \t]+login[ \t]+\S+[ \t]+password[ \t]+(?![${*<])\S{4,}` | `machine example.com login bob password Hunter2x` | `login bob password must be set`, `password xx`, `password {x}` |
| `netrc_line` | `(?im)^[ \t]*password[ \t]+(?![${*<])\S{6,}[ \t]*$` | multi-line netrc `password Hunter2x` | `password reset flow`, `Enter your password here` |

The cloudflared token shape is grounded in the binary, not recall (rule 12): the installed `cloudflared` carries the struct tags `AccountTag json:"a"`,
`TunnelSecret json:"s"`, `TunnelID json:"t"`, `Endpoint json:"e,omitempty"` (strings read from the binary, 2026-10-24), i.e. the token is base64 of a JSON
object. Any such JSON begins `{"`, and base64 of `{"` is `eyJ` for every one-character first key, so `eyJ` + a long base64 run is key-order independent. The
real token was **not** decrypted or examined. `base64_json_blob` is deliberately a shape heuristic (false positives cost one masked/dropped string).

### 4.3 Changes (Unit B)

- **B-1 `core/export_hygiene.py`.** Append the five patterns to `SECRET_PATTERNS` (keep the table where it is: tests monkeypatch
  `core.export_hygiene.SECRET_PATTERNS`, and `find_secret` must keep reading that module global). Add `mask_secrets(text, *, max_chars=262144) -> str`:
  pure, never raises, replaces each match of each pattern with `[REDACTED:<pattern-name>]`, truncates input beyond `max_chars` with a visible marker
  (fail-safe for audit/log use), returns the fixed string `[withheld: redaction failed]` on any internal error (never the raw text). Docstring: why
  logs/audit mask while training export drops whole examples (the existing module docstring explains drop-vs-redact). Side effect to state in the
  ledger: `find_secret`/`sanitize_examples` now also drop examples containing the five new shapes (more drops, never fewer).
- **B-2 `core/sessions.py`.** `redact_secrets` keeps its five legacy substitutions (they preserve the key and mask only the value) and then applies
  `mask_secrets`. Same signature and non-str passthrough.
- **B-3 `core/action_gateway.py::_append_audit`.** Mask the `command` and `reason` string fields of the record before `json.dumps`. The coalesce digest is
  computed from the raw key earlier and is unaffected; `GatewayDecision.detail["command"]` (in-process) stays raw. A masking failure still writes the row
  (with the withheld marker). **Blocked on Ish Q-a** (verbatim audit rows change).
- **B-4 `utils/logger.py::_log_to_file`.** Mask `message` before the handler call. Lazy import of `core.export_hygiene` inside the function (the `utils`
  package must not import `core` at module import time); an import failure writes the withheld marker, not the raw text. Console output is unchanged.
- **B-5 `core/service_actions.py::_show_config`.** Extend the key-substring list to `token, secret, api_key, apikey, api-key, password, passwd,
  credential, private_key, access_key` and pass remaining string leaves through `mask_secrets` (catches `"url": "https://u:pw@host"`).
- **B-6 `ccos/plugins/system/system_info/system_info.py::list_processes`.** `command = mask_secrets(parts[10])[:100]` (mask the whole string, then cut) with
  a guarded import; if the import fails return only `Path(argv0).name`. This closes the class (any future argv secret), not only the cloudflared instance.

Reachability note for F7 (correcting the earlier "unmediated" shorthand): WP2.1 group 4 now mediates `call_capability` through `gate_exec`
(`ccos/core/plugin_manager.py:951-1070`), but `system.processes` is classified **READ** (`plugin_manager.py:167-168`) so the gateway allows it, and
`ccos/core/skill_recombiner.py:239-241` proposes it for prompts mentioning processes. Whether the coding-agent model can reach it in a given mode was not
traced; treat it as reachable by CCOS-routed tasks.

## 5. Interaction with G15d (D-2 option (b), committed `890d4b9`) and the deferred option (c)

**Already closed (measured, F8):** in confirm-less modes the shell refuses `cat|head|tail|cut|grep|diff|find` of `/proc/<pid>/{cmdline,environ,stat,task/..}`
(14 of 14 forms, including `/proc/./N`, `/proc//N`, `/proc/../proc/N`, `/proc/N/cwd/..`) via the `/proc` rule of the credential scan, and `ps`, `pgrep`, `top`,
`strings`, `xargs`, `printenv`, `env` are HIGH by G15c default-deny. Unit A therefore does **not** touch `tools/shell_tools.py` and adds nothing to the
G15d read set or G15e protected set (no new credential path is created).

**Remaining after D-2(b) and what G15h does about it:**

| channel | closed by |
| --- | --- |
| script child (`python3 x.py`) reading `/proc/*/cmdline` or running `ps` | Unit A (nothing left in argv). The same child can still read `/proc/<pid>/environ`, `age.key` and the `.age` file: accepted ceiling (R1). |
| CCOS `system.processes` | Unit A (cloudflared) + Unit B-6 (class) |
| interactive-confirm modes | by design (operator sees the HIGH warning) |
| `bash`/helper transient cmdlines | Unit A |
| adb / readproc-group listing | Unit A (argv clean; environ is owner-only) |
| `cat /proc/*/cmdline` | harmless only because `shell()` never globs (`shlex.split`); not a rule. Logged as a fragility note (section 10), not fixed here (`tools/shell_tools.py` is G15e's file). |

**D-2 option (c) (environment allowlist for ALL children: shell, plugin Popen, bench agent) is DEFERRED by Ish (2026-10-23, option (b) only) and is OUT OF
SCOPE for G15h.** G15b-11 (`NEW-1020`) stays OPEN. What G15h does touch is narrower and not (c): the cloudflared child's own env drops the two
consumed token-source names (`CLOUDFLARE_TUNNEL_TOKEN`, `CLOUDFLARED_TOKEN`). Nothing changes for any other service or child. Whether to strip those names from
the other services' env ahead of (c) is Q-b.

## 6. Test plan (recording fakes everywhere; no real service, tunnel, model or network)

All runs: absolute disposable `HOME`, `CODEY_STATE_DIR`, `CODEY_ACTION_GATEWAY_AUDIT`; proxy variables unset; `python3 -I` for scratch scanners.

**Unit A** (new `tests/test_g15h_cloudflared_env_delivery.py`; extend `tests/test_owned_service_spawn.py` fakes and `tests/test_service_public_lifecycle.py`):
1. `start_profile("cloudflared", ...)` with a monkeypatched `get_cloudflare_tunnel_token` returning a canary and `shutil.which` true: argv is exactly `["cloudflared","tunnel","run"]`, canary in no element, `missing` False; token falsy => `missing` True, argv `[]`; binary absent => `missing` True and the getter is not called.
2. `lock_exec("cloudflared","start")` with a recording `os.execvpe`: canary in no element of the exec argv and not in the passed env (token comes from the patched getter, ambient env source unset).
3. `OwnedLaunch` with a recording `Popen`: with a provider, `Popen` receives `env` containing `TUNNEL_TOKEN=canary`, lacking `CLOUDFLARE_TUNNEL_TOKEN`/`CLOUDFLARED_TOKEN` even when those are set in the helper env, argv free of the canary, and `os.environ` of the helper unchanged afterwards; without a provider the `Popen` kwargs are exactly the pre-change set (no `env` key).
4. Provider raising: no `Popen` call, rc 2, `failed-cleanup-confirmed` on the ready pipe, record cleaned, canary absent from stdout, stderr, ready-pipe bytes and the pid/identity files.
5. `_spawn_main` selector: `--service cloudflared` installs the provider; `litestream`/`aigentik`/`daemon` do not; an argv element `TUNNEL_TOKEN=x` after `--` stays an argv string and creates no env entry; an unknown service gets none.
6. `test_service_public_lifecycle.py`: the recorded `cloudflared` profile argv equals `["cloudflared","tunnel","run"]` and the harness secret (`fixture-secret-never-print`, seeded at line 190 of that file) appears **nowhere** in `commands.jsonl`. Coverage gap fixed: today that harness records the cloudflared argv including the token and only inspects stdout/stderr.
7. Mutation pass by the implementer: put `--token` back into `start_profile` (tests 1, 2, 6 fail); drop the provider call (3 fails); drop source stripping (3 fails); make the provider read argv (5 fails); swallow the provider exception and launch with inherited env (4 fails).

**Unit B** (new `tests/test_g15h_masking_redaction.py`; extend `tests/test_export_hygiene.py`, `tests/test_service_action_gateway.py`, `tests/test_action_gateway_audit_failure.py`):
1. Pattern acceptance table of section 4.2 (positives mask, negatives unchanged) through `mask_secrets` and `find_secret`; the real-`age-keygen` positive generated in the test (skip if `age-keygen` absent).
2. `mask_secrets` contract: idempotent, never raises (patched pattern that raises => withheld marker), truncation marker beyond `max_chars`, linear time on 1 MB adversarial strings (`a*1e6`, `--token `*125000, `eyJ`+`a`*1e6, `password `*100000) under a loose bound.
3. `sessions.redact_secrets`: all 15 probe shapes of 4.2 masked; legacy behavior (`"password": "x"` keeps the key) preserved; `save_session` round trip writes no canary.
4. Audit ledger: a `gate_exec` of `curl -H 'Authorization: Bearer <canary>' x` writes `[REDACTED:bearer_token]`, the row's other fields and the decision/outcome are unchanged, `decision.detail["command"]` stays raw, a refused HIGH_IMPACT row is masked too, and a masking failure still appends a row.
5. Logger: with `setup_file_logging` on a temp file, `info/warning/error/debug` of text containing every canary leaves none in the file while the captured console string still has it; an import failure of `core.export_hygiene` writes the withheld marker.
6. `_show_config`: new key names redacted; a URL credential under a benign key is masked.
7. `list_processes` with a faked `subprocess.run` output containing the cloudflared argv: no canary in any `command`; import-failure branch returns argv0 only.
8. Perf sanity: 2,000 masked 300-char lines complete in a few seconds on-device (loose bound, flags a quadratic regex).
9. Full existing suites for the touched modules must stay green; known unrelated failures are listed in the 2026-10-23 handoff section 6.

## 7. Live verification (rule 4; disposable processes only, PID-tracked, never the live tunnel, services or DB)

Preconditions: `ps -A -o pid,args` scan by argv0 basename shows no `cloudflared`, `llama-server`, `litestream`, `restoricon`, `aigentik` of the operator's
(a naive `grep cloudflared` matches the scanning shell itself, as it did in the baseline); `free -h` recorded (no model is loaded; recorded for rule 2
discipline). State dir, HOME and audit path are disposable; `~/.codeyOS` is never named as `CODEY_STATE_DIR`. Only `lock-exec cloudflared start|stop` is used,
never `all`. Cleanup is the lifecycle `stop` (identity-verified) or, on harness failure, `kill <PID read from the disposable cloudflared.pid>`; no `pkill -f`.

- **L1 stub chain (after-state).** Appendix A harness, stub `cloudflared` first on `PATH`. Required report: stub `argv_has` false, argv `[stub, tunnel, run]`;
  stub `self_environ_has` true and `TUNNEL_TOKEN_in_env` true (the intended and only copy); parent and grandparent `cmdline_has` false and `environ_has` false;
  global scan at t0 and t0+2 s: **zero `cmdline` hits**, exactly one `environ` hit (the stub); `start`/`stop` rc 0; no canary on disk under the run dir
  (audit ledger, logs, state.db, pid/lock files); no stray process. Compare against the section 2 baseline (3 cmdline hits).
- **L2 real binary, fake token.** Same chain with the real `cloudflared` and the malformed canary in the disposable `.age`: expected start rc 2, log
  `Provided Tunnel token is not valid.` (proves env delivery reached the parser; absent => the log would ask for a tunnel name), canary absent from the log and from
  every cmdline, `stop` rc 0 `absent-dead`, nothing left. No network contact (fails in the parser). A syntactically valid fabricated token is **not** used (it would dial Cloudflare).
- **L3 failure paths.** (a) disposable state with no `.age` and no env: `start` prints "optional service unavailable/not configured; skipped", nothing spawned; (b) `.age`
  present but `age` hidden from `PATH` after the presence check is not reproducible, so cover provider failure by test 4 only.
- **L4 untouched services.** `lock-exec litestream|restoricon start` is NOT run live (they would start real binaries); their `Popen` kwargs are pinned by test 3.

**Not verifiable by the agent:** the real token with the real tunnel (a live tunnel registers with Cloudflare and fronts the public API). Propose a
`LIVE_TEST_QUEUE.md` step for Ish at the next manual start: after `codey start`, (1) `ps -A -o pid,args` shows `cloudflared tunnel run` with no token; (2)
`~/.codeyOS/cloudflared.log` shows `Settings: map[token:*****]` and a registered connection; (3) the public subdomains answer. Rollback = revert the Unit A commit
(the old `--token` argv form is one line). Until Ish runs it Unit A is code-complete, reviewer-approved and disposable-process verified, **not live verified** (rule 7).

## 8. Units, order and review

| unit | content | files | gates |
| --- | --- | --- | --- |
| **A** (first) | token out of argv, env delivery by the spawn helper | `core/service_lifecycle.py`, `core/process_identity.py`, new `tests/test_g15h_cloudflared_env_delivery.py`, `tests/test_owned_service_spawn.py`, `tests/test_service_public_lifecycle.py` | **rule 4: code-reviewer mandatory** (process lifecycle: launcher argv/env and the owned-spawn helper), adversarial brief below; L1-L3 live by live-verifier; no unit B dependency |
| **B** (independent, can run in parallel with A's review) | masking in sessions, audit ledger, file logger, `codey config`, `system.processes` | `core/export_hygiene.py`, `core/sessions.py`, `core/action_gateway.py`, `utils/logger.py`, `core/service_actions.py`, `ccos/plugins/system/system_info/system_info.py`, new `tests/test_g15h_masking_redaction.py` + extended tests | code-reviewer mandatory (security: audit evidence, shared by all gated actions); B-3 blocked on Q-a; no live step beyond the unit tests (pure text transforms) |

Why this split: A is the only lifecycle change and carries the live step; B is wide but text-only. They share no file. Collision check against in-flight work at
write time: G15e edits `tools/shell_tools.py`, `core/filesystem.py`, file tools and (per its spec) not `core/action_gateway.py`; `core/task_executor.py` is also
dirty in the tree (foreign, unattributed); G15f edits `bench/*`; G15g is specced (`docs/wp2_1_g15g_spec.md`) against `ccos/core/plugin_manager.py` and the plugin tree,
which B-6 only touches in `system_info.py` (re-check `git status` before staging; stage exact paths, never `-A`; do not `git stash`, even in a background command).

Reviewer brief for A (read-the-artifact, rule 12): (1) confirm with a `/proc` scan that no argv in the chain holds the secret (reproduce L1, do not trust the report);
(2) the failure mapping of a raising provider: no orphan child, record cleaned, lock released, readiness bytes parse via `parse_spawn_ready`; (3) the kwargs of `Popen` for
all other services are byte-identical; (4) the provider cannot be driven by argv; (5) no new signal, PID, kill or lock logic; (6) `status`/`logs`/`stop` never decrypt;
(7) `missing`/skip semantics unchanged; (8) the helper's `os.environ` never contains the token; (9) `import utils.config` from the helper adds no state-dir side effect
beyond what `lock_exec` already does.

## 9. Accepted residuals (state these in the register; none is a boundary claim)

R1 Same-uid code (any script child) can still read `/proc/<cloudflared>/environ`, `age.key`, `cloudflare_tunnel_token.age` and decrypt (consolidated ceiling, G15b-19; D-1).
R2 The token now lives in cloudflared's `environ` (owner-only, not in `ps`); D-2(b) refuses shell reads of it, scripts bypass.
R3 If the operator exports `CLOUDFLARE_TUNNEL_TOKEN`/`CLOUDFLARED_TOKEN` in the shell that runs `codey start`, every service except cloudflared still inherits it (D-2(c) deferred; Q-b).
R4 Real-token end-to-end is verified only by Ish's manual step (section 7).
R5 Masking is pattern-based: unknown shapes pass (same accepted false-negative policy as `export_hygiene`), and `base64_json_blob`/`secret_flag` can over-mask benign text. Defence in depth, not a boundary.
R6 Masking applies to the file/audit/session sinks only; trajectory, `episodic_log`, memory tiers and checkpoints are unchanged (section 4.1 S6-S8).
R7 The decrypted value exists briefly in the helper's heap and, as a discarded boolean source, in the `lock_exec` worker's memory; Python cannot zero it. Reading it requires same-uid memory access (`/proc/N/mem`, refused by the shell's `/proc` rule, not by scripts).
R8 `age -d` runs twice per cloudflared start (presence check, then the helper): negligible.
R9 Audit rows become less verbatim for secret-shaped commands (Q-a).

## 10. Proposed ledger entries (ids provisional: tail of `NEW_ISSUES.md` is NEW-1044; G15f holds 1045-1047, G15e 1048-1051, G15g 1052-1054; allocate from NEW-1055 and re-read the tail plus `git status --short` immediately before writing)

Status updates to existing entries (not new ids): `NEW-1021` (G15b-12): add the three-process finding (section 2) and **reframe severity to Medium (same-uid, defence in depth)**, status per tier after Unit A; `NEW-1033` (G15b-48): correction that `sessions.redact_secrets` masks only 2 of 15 shapes and `find_secret` misses the cloudflared/age/netrc shapes (rule 6), then status after Unit B; `NEW-1020` (G15b-10/11): G15b-10 unchanged, G15b-11 still OPEN, option (c) still deferred.

| id (provisional) | rating | entry |
| --- | --- | --- |
| NEW-1055 | CONFIRMED, Medium | CCOS `system.processes` (`system_info.list_processes`, `ccos/plugins/system/system_info/system_info.py:30-48`) returns the first 100 chars of every visible process's argv, READ-classified and gateway-allowed (`plugin_manager.py:167-168`); with a cloudflared-shaped argv it returned the canary (probe, 24 rows, 1 hit). Fix: Unit B-6 (mask) + Unit A. |
| NEW-1056 | CONFIRMED, Medium | `core/sessions.py::redact_secrets` masks 2 of 15 probed secret shapes and writes conversation history to disk; correction of the G15b-48/C06 claim. Fix: Unit B-2. |
| NEW-1057 | CONFIRMED, Low/Medium | The audit ledger (`core/action_gateway.py` `_append_audit`) and the daemon file logger (`utils/logger.py::_log_to_file`) persist command text and every log message verbatim; shell warnings embed the full command. Fix: Unit B-3/B-4 (B-3 pending Q-a). |
| NEW-1058 | CONFIRMED, Low | `_show_config` redacts by key substring `token/secret/api_key` only (misses `password`, `credential`, URL-embedded credentials). Fix: Unit B-5. |
| NEW-1059 | CONFIRMED, Low (test gap) | `tests/test_service_public_lifecycle.py` seeds `CLOUDFLARE_TUNNEL_TOKEN` and records the cloudflared profile argv containing it in `commands.jsonl` but asserts secret absence only on stdout/stderr (line ~190 and `run_command`). Fix: Unit A test 6. |
| NEW-1060 | SUSPECTED, Low | Other text sinks not audited line by line: `episodic_log` (`core/agent.py:840` `result[:100]`, planner description/result prefixes), five-tier memory, checkpoints. Not argv/env. Future trigger: any secret-bearing tool result seen there. |
| NEW-1061 | SUSPECTED, Low | `/proc/<pid>/...` credential rule is lexical; `cat /proc/*/cmdline` is safe only because `shell()` uses `shlex.split` without glob expansion (F8). Fragile if the execution model ever gains a shell. Pin with a test when `tools/shell_tools.py` is next touched (G15e's file). |
| NEW-1062 | INFO | cloudflared token-file re-read behavior and `os.memfd_create` absence (AttributeError in this Python build): reasons O2 was rejected; revisit only with a verified re-read answer. |

## 11. Cost

Unit A 0.6-0.9M tokens (small diff, heavy tests, one reviewer round expected, possibly two) + 0.3-0.4M live; Unit B 0.7-1.1M (wide, mostly mechanical, one reviewer round).
Total 1.3-2.0M + 0.3-0.4M live, slightly above the consolidated 1.0-1.5M + 0.5M estimate because the redaction audit (B) was widened beyond the one row G15b-48 named.
Agent runs: about 8-10. Write results to disk incrementally (usage limits killed agents before).

## 12. Open questions for Ish (the only genuine ones; defaults apply if unanswered)

- **Q-a. May the action-gateway audit rows be masked?** `command`/`reason` currently are verbatim evidence. Masking replaces only secret-shaped spans with `[REDACTED:<pattern>]` and keeps everything else. Recommend **yes** (a ledger that stores a pasted token defeats its purpose and the file is readable by the same-uid agent). Default if unanswered: ship B-1, B-2, B-4, B-5, B-6 and hold B-3.
- **Q-b. Strip `CLOUDFLARE_TUNNEL_TOKEN`/`CLOUDFLARED_TOKEN` from the *other* services' environment now, as a narrow step ahead of option (c)?** Recommend **no**; keep (c) deferred as decided. Default: only the cloudflared child's env is changed (section 5).
- Not questions, for the record: severity of `NEW-1021` is the coordinator's rubric call under pending F4 (recommended Medium, section 0); the real-token verification (section 7) is a manual step only Ish can perform.

## Appendix A. Disposable chain harness (recreate under the session scratch dir; it was used for the section 2 baseline)

Stub `cloudflared` (written with `#!<absolute python>`; reads the canary from `$G15H_CANARY_FILE`, writes JSON to `$G15H_REPORT`): at startup compute `argv_has`, whether
the canary is in `/proc/self/environ`, `TUNNEL_TOKEN` presence in `os.environ`, parent and grandparent cmdline/environ (walk `/proc/<pid>/stat` field 4 twice), and a
scan of every `/proc/<n>/{cmdline,environ}` for the canary (t0 and again after `sleep(2)`); then idle at most 24 s.

Driver (bash): create `run_$label/{home,state,stubbin}`, `chmod 700 state`; random canary `FAKE-G15H-CHAIN-CANARY-<12 hex>`; `age-keygen -o state/age.key`;
`printf %s "$CANARY" | age -r "$(age-keygen -y state/age.key)" -o state/cloudflare_tunnel_token.age`; run exactly
`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u CLOUDFLARE_TUNNEL_TOKEN -u CLOUDFLARED_TOKEN -u TUNNEL_TOKEN -u TUNNEL_TOKEN_FILE HOME=$R/home CODEY_STATE_DIR=$R/state CODEY_ACTION_GATEWAY_AUDIT=$R/audit.jsonl CODEY_OS_DIR=$REPO PATH=$R/stubbin:$PATH G15H_CANARY_FILE=... G15H_REPORT=... python3 $REPO/core/service_lifecycle.py lock-exec cloudflared start`,
`sleep 3.5`, print the report, then the same command with `stop`, then `grep -rlF "$CANARY" $R` excluding the harness's own canary and report files, then a scan of
`ps -A -o pid,args` for `$R/stubbin`. For L2 omit the stub directory from `PATH` so the real binary is found. Print every stream through `sed "s/$CANARY/<CANARY>/g"`.
