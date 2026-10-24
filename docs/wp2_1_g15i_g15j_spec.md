# WP2.1 G15i (operator-script guards) and G15j (HIGH file-write confirmation) — technical spec

Status: SPEC ONLY. No source, test or ledger file was edited while writing this. HEAD at writing: `8f41851`
(G15c-G15h committed; the G15f Unit B bench-lock files are uncommitted in the tree and were not touched).
Author: project-architect, 2026-10-24. Rule 12: every fact below was read from the artifact or probed in a
disposable directory (`/data/data/com.termux/files/usr/tmp/g15ij_probe`, disposable `HOME`, `CODEY_STATE_DIR`,
`--db-path`; the live Restoricon DB and `~/.codeyOS/config.json` / `age.key` were never opened).

**Provisional ids.** At first reading the tail of `NEW_ISSUES.md` was NEW-1066; a concurrent ledger writer then
took NEW-1067 (G15f Unit B residuals), NEW-1068 and NEW-1069 (candidate OS-boundary WP) while this spec was being
written (re-checked at handback: next free id is **NEW-1070**, tail NEW-1069). Every id proposed below is
PROVISIONAL and starts at NEW-1070; the coordinator must re-verify the tail immediately before writing
(CLAUDE.md "Working alongside another agent").

**Decisions already made by Ish that bound this spec (2026-10-24, per the coordinator):** F4 (rubric) ratified;
D-1 ratified = script-file / `-m` / self-launch / `--allow-self-mod` opaque execution are ACCEPTED RESIDUALS
(G15b-19, 22, 36), OS-level boundary logged as a candidate future WP. Consequence for G15i: it is a
guard against the *named, committed operator entry points being run unattended*, NOT a boundary against a
same-uid script (section 1.6 states this plainly). D-8 (confirm or lower the HIGH-by-ambiguity ratings) is NOT
decided; G15j is therefore "proposed, needs Ish's go" (section 2.0).

---------------------------------------------------------------------------------------------------------

## 1. G15i — operator-script guards (G15b-21 narrow; NEW-1028)

### 1.1 Verified facts

1. **`tools/provision_ai_agent_auth.py`** (292 lines). `main()` (:270-288) parses `--username/--email/--db-path`,
   calls `provision()` (:155-267) and `print(token)` (:287). `provision()` opens `DatabaseManager(db_path)` or
   `DatabaseManager()` (:179), which creates the schema via `CREATE TABLE IF NOT EXISTS` as a side effect of
   connecting (module docstring :13-18). For an existing user it **revokes every unrevoked token** (:225-230)
   then `auth.create_token(user)` (:265); for a new user it creates the user with `ROLE_AI_AGENT` (:192-199).
   The docstring (:40-49) itself documents that a casual rerun kills the deployed `core_api.token`.
   Default DB: `restoricon_core.database.DEFAULT_DB_PATH` = `~/.codeyOS/restoricon.db` unless `RESTORICON_DB_PATH`
   (printed by a read-only import; CLAUDE.md rule 0b: dev/test configs point `RESTORICON_DB_PATH` at a copy).
2. **`core/setup_dr_key.py`** (166 lines). `main()` (:92-162): if a `restoricon.dr_recipient_pubkey` exists and no
   `--force`, prints and returns 1 with no mutation (:116-123). Otherwise runs `age-keygen` (`_generate_keypair`
   :29-63, in memory, no temp file), rewrites the active config file (`config_path.parent.mkdir`, `open(...,"w")`
   :153-156) with the new public key, and prints the **private key to stdout** (`_print_handoff` :66-89), "shown
   once, never again". `--force` orphans every backup blob encrypted to the old DR key (docstring :96-104).
   It is invoked by `install.sh:549` (`python3 "$CODEY_OS_DIR/core/setup_dr_key.py"`, interactive branch only;
   the `SKIP_CONFIRM` branch :536-546 only prints a warning).
   Note both mutation cases (first generation AND `--force`) put the private half on stdout: if the invoker
   captures stdout (the shell tool does), the escrow private key lands in the agent's context and session logs.
   So the guard cannot be limited to `--force`.
3. **Current classification (probed with `tools.shell_tools.classify_shell_command`, 2026-10-24):**
   `python3 core/setup_dr_key.py --force` = **ACT**; `python3 core/setup_dr_key.py` = ACT;
   `python3 tools/provision_ai_agent_auth.py` = **ACT**; `python3 -m tools.provision_ai_agent_auth ...` =
   HIGH_IMPACT (G15d Unit B's 13-module `-m` allowlist, `tools/shell_tools.py:451-476`,
   `tests/test_shell_g15d_unit_b.py:78`); `PYTHONPATH=. python3 tools/provision_ai_agent_auth.py` = HIGH;
   `bash -c '...'`, `./core/setup_dr_key.py`, `python3 -c '...'` = HIGH.
   **Rule-6 correction to the register:** consolidated G15b-21 and NEW-1028 say `python3 -m
   tools.provision_ai_agent_auth` "stays ACT"; that was true post-G15c and is superseded by G15d Unit B (HIGH).
   The register text should be corrected when G15i lands.
4. **The script form of provision is reachable as ACT in an agent session.** A bare `python3
   tools/provision_ai_agent_auth.py` raises `ModuleNotFoundError: No module named 'restoricon_core'` (probe,
   `-I`, disposable HOME) because `sys.path[0]` is `tools/`, but `lib/bootstrap_environment.sh:4-9` exports
   `PYTHONPATH=<repo root>` and is sourced by `codey`, `codey-start`, `lib/service_lifecycle.sh`,
   `lib/service_manager.sh`. Probe: `PYTHONPATH=<repo> python3 tools/provision_ai_agent_auth.py --db-path
   <disposable>` (no `-I`) exits 0 and prints a 44-character token. So inside a launcher-started agent the
   process env supplies the path and the ACT-classified command mints a token. (Probe used a disposable DB
   path; nothing live was touched.)
5. **Which modes reach the ACT forms unprompted.** `shell()` (`tools/shell_tools.py:1899+`) asks `ask_confirm`
   for ACT only when `confirm_shell` is True and not yolo. So the REPL already shows a per-command prompt; the
   unattended exposure is `--yolo`, `--fix`/`--tdd`, daemon tasks (`python3 x.py` is daemon-allowlisted per the
   handoff), bench and CCOS `coding.run_agent` — exactly the confirm-less modes.
6. **`/dev/tty` cannot be opened in this agent harness.** Probe: `os.open('/dev/tty', O_RDWR|O_NOCTTY)` ->
   `OSError [Errno 6] No such device or address`. Therefore (a) a guard that needs `/dev/tty` is fail-closed
   for every harness-run script (desired), and (b) tests and the verification harness must inject a fake
   opener or use a pty (the NEW-977 test pattern below).
7. **NEW-977 precedent (the pattern to reuse), `core/lora_import.py:45-125`:** `_TTY_PATH="/dev/tty"`,
   `_open_tty()` (:64-70, raw fd `O_RDWR|O_NOCTTY`, `os.open` because `open(path,"r+")` fails on a tty),
   `_confirm_on_tty(prompt)` (:73-104: `termios.tcflush(TCIFLUSH)` before prompting so stale typeahead cannot
   approve; fail-closed if termios or the flush is unavailable; reads one byte at a time up to 256; empty read
   -> `EOFError`; only `y`/`yes` approve), `_gate_lora_action` (:107-125: `get_action_gateway().gate_exec(
   authority=HIGH_IMPACT, action=..., command=..., confirm_available=True, execute=..., confirm=lambda:
   _confirm_on_tty(prompt))`). Prompts use `!a` (ascii-escape) for paths (:607-613, :796-803). A thunk's exception
   is kept out of the audit row and re-raised afterwards via an `escaped` list (:806, :937-966). Tests:
   `tests/test_lora_action_boundaries.py` (36 tests; `_Pty` fake with a helper thread that answers only after
   the prompt text appears; seams `li._open_tty`, `li._TTY_PATH`, `li._confirm_on_tty`);
   `tests/conftest.py:149-163` autouse stand-in `lora_import._confirm_on_tty = lambda prompt: True`.
   NEW-977 was live-verified on a real pty (69/69, `docs/wp2_1_group14_b_c_e_live_verification.md`).
8. **Gateway `gate_exec` already supports `confirm`** (`core/action_gateway.py:412-553`): for HIGH_IMPACT with a
   callback, approval requires `confirm() is True`; `EOFError`/`KeyboardInterrupt`/any other exception ->
   REFUSED row with a static reason, `execute` never called. The audit row masks secrets in `command`/`reason`
   (G15h, `_append_audit` :114-148) and never records the thunk's result (:540-544).
9. **G15e constraint (an existing AST test):** `tests/test_filesystem_protected_paths.py::
   test_operator_modules_do_not_import_the_file_tool_layer` and `tests/test_g15e_unit_c.py::
   test_operator_writers_and_readers_do_not_use_the_guarded_filesystem` assert `core/setup_dr_key.py` (and
   `core/backup_secrets.py`, `core/daemon_config.py`, `core/service_lifecycle.py`, `core/service_actions.py`)
   never import `core.filesystem`, `core.protected_paths`, `tools.file_tools`, `tools.patch_tools`,
   `tools.shell_tools` (the AST walk covers function-local imports; it checks direct imports only, not
   transitive). `core.action_gateway` imports `core.filesystem` at module level (:54) — transitive, so the test
   would still pass, but the intent ("operator code is never routed through the file-tool guard layer") argues
   for keeping `setup_dr_key.py` off `core.action_gateway` unless the audit row is judged worth it. See 1.3 option
   B and open question Q-A.
10. **Existing tests that call the guarded code paths** (all must keep passing): `tests/test_setup_dr_key.py`
    (5 tests: `main()` with `subprocess.run` patched, `capsys` for the private key, `CODEY_CONFIG_PATH` fixture),
    `tests/test_provision_ai_agent_auth.py` (calls `provision(db_path=":memory:")`/tmp files directly, ~15
    sites), `tests/test_ccos_crm_read.py:32` (imports `provision` as a fixture to mint a CRM-reader token),
    `tests/test_business_mutation_authority_coverage.py:19`. `provision()` must therefore keep returning a
    token string and raising `ValueError` for a wrong-role user.
11. `age-keygen` exists at `/data/data/com.termux/files/usr/bin/age-keygen` (so a live run in a disposable config
    could use the real binary; I recommend a PATH shim anyway, see 1.7). The Ish memory "PENDING ISH: escrow DR
    key (`setup_dr_key.py --force`) must not be run by agents" binds the live-verifier: it may run the script
    only with `CODEY_CONFIG_PATH` pointing at a disposable file and a shim `age-keygen`.

### 1.2 What G15i is and is not

- IS: a human-presence check *inside* the two operator entry points, so that the committed, named, ACT-classified
  forms (`python3 core/setup_dr_key.py [--force]`, `python3 tools/provision_ai_agent_auth.py`, and the
  `-m` form if ever allowlisted) cannot mint a credential or write the escrow key without a person at the
  controlling terminal, in every mode (REPL, `--yolo`, daemon, bench, CCOS).
- IS NOT a boundary. Accepted residual (D-1, F2): a same-uid script can `import` the function and call it,
  reimplement it (there is deliberately no importable unguarded twin). The register's sentence that a guard inside the
  irreversible function "is not" bypassable by a wrapper script (consolidated G15b-21, section 4) is
  **overstated** (rule 6): a wrapper that imports and calls `provision()` hits a function-level guard unless it
  patches the module (there is no private unguarded twin to call), so a function-level guard stops the casual and
  accidental wrapper (a model writing `print(provision())` as a convenience script) but nothing adversarial.
  The spec asks for the function-level placement for that reason, and records the limit in the ledger.

### 1.3 Design

**Shared primitive (new module `core/tty_confirm.py`).** Extract the NEW-977 tty logic so three consumers share
it. Contents, copied faithfully from `core/lora_import.py:61-104`:

```
TTY_PATH = "/dev/tty"
def open_tty() -> int                      # os.open(TTY_PATH, O_RDWR|O_NOCTTY); raises OSError with no ctty
def confirm_on_tty(prompt: str, *, open_tty=open_tty) -> bool
    # identical algorithm: tcflush(TCIFLUSH) first (fail closed), write prompt, read 1 byte at a time <=256,
    # b"" -> EOFError, only y/yes (case-folded, stripped) -> True; fd always closed in `finally`
def gate_human_action(action, command, prompt, execute, *, confirm=None, open_tty=open_tty):
    # thin wrapper: get_action_gateway().gate_exec(authority=HIGH_IMPACT, action=action, command=command,
    #   confirm_available=True, execute=execute,
    #   confirm=confirm or (lambda: confirm_on_tty(prompt, open_tty=open_tty)))
    # imports core.action_gateway lazily (inside the function) so importing core.tty_confirm is dependency-free
```

The module imports only `os`; `termios` and `core.action_gateway` are imported inside functions. It must not
import `core.filesystem`, `core.protected_paths`, `tools.*` (AST-test intent, fact 9).

**Test/patch seams (explicit, call-time lookups).** `core/tty_confirm.py` exposes `gate_human_action(...,
open_tty=None, confirm=None)`: when `confirm` is None it uses `confirm_on_tty(prompt, open_tty=open_tty)`. Each
consumer module defines its OWN module-level seam that it passes in, looked up at call time:
`tools/provision_ai_agent_auth.py` defines `_open_tty()` (delegating to `core.tty_confirm.open_tty`) and
`_confirm_on_tty(prompt)` (delegating to `tty_confirm.confirm_on_tty(prompt, open_tty=_open_tty)`), and calls
`gate_human_action(..., confirm=lambda: _confirm_on_tty(prompt))`; `core/setup_dr_key.py` defines the same two
plus `_stdout_is_terminal()`. Tests and the conftest stand-ins patch `<module>._confirm_on_tty` /
`<module>._open_tty`, exactly like `lora_import` (so the stand-in in §1.5 patches something real).

**`core/lora_import.py` delegates** (minimal edit, behaviour byte-identical): keep `_TTY_PATH`, `_open_tty`
(still reading the module global `_TTY_PATH` at call time) and `_confirm_on_tty(prompt)` in the module; change
only `_confirm_on_tty`'s body to `return tty_confirm.confirm_on_tty(prompt, open_tty=_open_tty)` (looked up at
call time so `monkeypatch.setattr(li, "_open_tty", ...)` in `tests/test_lora_action_boundaries.py:_Pty` still
works) and `_gate_lora_action` unchanged. Acceptance: `tests/test_lora_action_boundaries.py` (36), the lora
tests that use the conftest stand-in, and `tests/test_group14_*` pass UNMODIFIED. If any lora test needs an edit
to pass, stop and fall back to leaving `lora_import.py` untouched and duplicating the 30 lines with a parity
test (same pty scenarios against both implementations) — decide by the implementer's first red run, report it.

**`tools/provision_ai_agent_auth.py`.**
- **No importable unguarded twin.** The current body of `provision()` becomes a **closure** (`def _run() -> str`)
  defined INSIDE the new `provision()` and passed as the gate's `execute` thunk (verbatim move of the body; the
  `_validate_custom_permissions` call stays first in `provision()` so a bad permission map still raises before
  any prompt). Do NOT create a module-level `_provision_impl`: a public-ish unguarded sibling is the first
  thing a model reading the file would call, which would void §1.2's rationale for the function-level guard.
- New `provision(...)` (same signature and docstring contract) validates `custom_permissions` first (pure, no
  I/O), then builds a **static** audit label and a dynamic prompt:
  - `action="provision_ai_agent_auth.provision"`, `command="provision ai_agent bearer token"` (static, no
    username/path: gate_exec records these and G15h masking is pattern-based).
  - Prompt (to the tty only): `[HIGH IMPACT] Mint a Restoricon Core bearer token.`, `db: {resolved_db!a}`,
    `user: {username!a}`, `role: ai_agent`, `any existing unrevoked token for this user is REVOKED (the
    deployed core_api.token stops working)`, `the token will be printed on stdout ({'a terminal' if
    sys.stdout.isatty() else 'NOT a terminal - it may be captured by the calling process'})`, `Proceed? [y/N]: `.
    `resolved_db` = `db_path` if given else the string of `restoricon_core.database.DEFAULT_DB_PATH` (read the
    module constant; do NOT instantiate `DatabaseManager`: connecting creates/touches the DB file, and the
    check must precede any side effect). `:memory:` is shown as-is.
  - Run `_run` as the `execute` thunk through `gate_human_action`. Keep the original exception out of
    the audit row and re-raise it afterwards (the lora `escaped` pattern): thunk catches `Exception as exc`,
    appends to a list, re-raises a static `RuntimeError("provision failed")` (so gate_exec's `str(e)` reason is
    static); after the gate returns, if the list is non-empty `raise escaped[0]`, preserving the `ValueError`
    contract tested today.
  - If the decision is REFUSED (declined, EOF, no tty, interrupted): raise a new `class ProvisionNotConfirmed
    (PermissionError)` with a static message (`"Refused: no human confirmation on /dev/tty (declined,
    unavailable or interrupted); no token was minted."`). `main()` catches it, prints it to stderr, returns 2.
    A bare traceback must not be the CLI's refusal shape.
  - `:memory:` is NOT exempted (an exemption is a code path to maintain for no security value); tests get an
    autouse stand-in instead.
- Import-time and `--help` behaviour unchanged; `main()` still prints only the token to stdout on success.

**`core/setup_dr_key.py`.**
- Split `main()`: everything from `_generate_keypair()` through `_print_handoff()` (:132-162) becomes a local
  closure `_generate_and_store() -> int` INSIDE `main()` (verbatim body; closing over `config`, `config_path`),
  invoked only after consent — no module-level function that generates and stores without a prompt. (The existing
  module-level `_generate_keypair`/`_print_handoff` remain: they do not mutate state by themselves — keygen is
  in-memory and printing is output — so they are not a bypass of the config write.) `main()` keeps arg parsing, config load and the
  two pre-existing early branches (the already-configured no-op return 1, and the `--force` notice). The new
  guard sits immediately before `_generate_and_store`, so the benign no-op path never prompts and no key is
  generated before consent.
- **Structural stdout rule (extra, cheap, specific to this script):** before prompting, refuse unless
  `sys.stdout.isatty()` (new seam `_stdout_is_terminal()` so tests/CI can inject). Rationale (fact 2): the
  private key is printed to stdout "once"; a captured/redirected stdout (the shell tool, `| tee`, a daemon)
  defeats the one-time-display contract and leaks the escrow private key into transcripts regardless of the
  prompt. The legitimate callers (`install.sh:549`, an operator at a terminal) always have a terminal stdout.
  The refusal message says so. This is intentionally NOT applied to provision (token capture with `$(...)` is a
  plausible legitimate operator use; there the prompt discloses the stdout status instead).
- Prompt: first-time: `[HIGH IMPACT] Generate the disaster-recovery keypair.`, `config file: {config_path!a}`;
  `--force` with an existing key: additionally `REPLACES DR public key {existing!a}: every backup blob
  encrypted to it becomes undecryptable by the DR party`; always: `the PRIVATE key will be printed once on this
  terminal's stdout and is not stored anywhere`. `Proceed? [y/N]: `.
- Gate: `action="setup_dr_key.generate"` (static; `--force` does not change the label: put the force bit in
  `command`: `"generate DR keypair"` vs `"regenerate DR keypair (--force)"`, both static). To keep
  `core/setup_dr_key.py` off `core.action_gateway` (fact 9) the script calls `tty_confirm.confirm_on_tty`
  directly (option A, recommended) and writes no audit row, OR calls `tty_confirm.gate_human_action` (option B,
  lazy gateway import, audit row). I recommend **A for `setup_dr_key.py`** (the script is the operator's own DR
  tool, runs from `install.sh` before the audit state dir may exist, and the AST-test intent is to keep it on
  plain IO) and **B for provision** (it already lives under `tools/`, runs against Core, and an audit row for
  "a credential was minted" is the valuable attribution). Open question Q-A offers Ish the uniform-B choice.
- Refusal path (declined/EOF/no tty/stdout not a terminal): print one static line to stderr, return 1; nothing
  generated, config untouched, `age-keygen` not invoked (assert `subprocess.run` not called).
- **Q-D check (read, not assumed):** `install.sh` has no `tee`, `exec >`, `| bash` or log redirection around
  line 549, and `README.md:142` / `docs/installation.md:18` document plain `bash install.sh` / `./install.sh`, so
  the one legitimate caller has a terminal stdout. The only break is a user who pipes the installer through
  `tee`/a log or runs it non-interactively; they hit the existing `|| print_warning "setup_dr_key.py did not
  complete — run it manually later: python3 core/setup_dr_key.py"` fallback (acceptable; the refusal line should
  say "run it directly in a terminal"). The `SKIP_CONFIRM` branch never calls the script at all.
- `install.sh` needs no change (still calls the script from an interactive terminal; the existing `|| print_warning
  "...run it manually later"` handles a refusal). CLAUDE.md rule 11: no new dependency or setup step, so
  `install.sh` is unchanged — state this in the PR.

### 1.4 Files and functions (touch list)

| file | change |
| --- | --- |
| `core/tty_confirm.py` (new) | `open_tty`, `confirm_on_tty`, `gate_human_action`; 2-4 sentence module docstring (safety-relevant: why `/dev/tty`, why tcflush, why raw fd) |
| `core/lora_import.py` | `_confirm_on_tty` delegates; nothing else |
| `tools/provision_ai_agent_auth.py` | `provision` wrapper with the body as an inner closure (no module-level twin) + `ProvisionNotConfirmed` + `main()` handling + docstring paragraph |
| `core/setup_dr_key.py` | local closure `_generate_and_store`, guard, `_stdout_is_terminal`, `_open_tty`/`_confirm` seams, docstring paragraph |
| `tests/conftest.py` | autouse audit-path isolation fixture (NEW, required) + autouse approve stand-ins for provision and setup_dr_key (see 1.5), mirroring `_lora_import_tty_confirm_approves_by_default` |
| `tests/test_g15i_operator_script_guards.py` (new) | the guard tests |
| `tests/test_tty_confirm.py` (new) | primitive tests (pty), plus parity checks against lora |
| docs/ledgers | coordinator, not the implementer (section 1.8) |

### 1.5 Tests (recording fakes, fake tty, disposable DB only)

Global rules for every test: tmp_path-only DBs (`str(tmp_path / "core.db")` or `:memory:`), `CODEY_CONFIG_PATH`
and `CODEY_ACTION_GATEWAY_AUDIT` in tmp_path, `reset_action_gateway()`, `RESTORICON_DB_PATH` set to a tmp file in
an autouse fixture so any accidental default-DB open lands on a copy, and a guard that fails the test if
`DatabaseManager()` is constructed with no path or if the resolved path starts with the real
`~/.codeyOS` (assert on `DEFAULT_DB_PATH` resolution under the patched env). No `age-keygen` execution:
`core.setup_dr_key.subprocess.run` is a recording fake (as in `tests/test_setup_dr_key.py`).
`/dev/tty` never opened for real: either an injected `open_tty` returning a pty slave dup (copy the `_Pty` class
from `tests/test_lora_action_boundaries.py:121-186`) or a fake `confirm` callable.

**Audit-sink isolation (verified gap):** `tests/conftest.py` has NO autouse fixture isolating
`CODEY_ACTION_GATEWAY_AUDIT` or `CODEY_STATE_DIR` (probed: its autouse fixtures cover telemetry dir, doc store,
llama bin, CCOS singletons and the lora stand-in only). Once `provision()` goes through `gate_exec`, every
existing test that calls it (~15 sites in `test_provision_ai_agent_auth.py`, the `test_ccos_crm_read.py` fixture,
`test_business_mutation_authority_coverage.py`) would append rows to the REAL
`~/.codeyOS/action_gateway_audit.jsonl`. Unit G15i-B must therefore add, in the SAME unit, a conftest autouse
fixture that sets `CODEY_ACTION_GATEWAY_AUDIT=<tmp_path>/gateway_audit.jsonl` and calls `reset_action_gateway()`
before and after each test (it composes with tests that set their own value later: function-scope `monkeypatch`
ordering lets the test's own `setenv` win), plus an assertion test that the real ledger's size/mtime is unchanged
across a `provision(db_path=":memory:")` call. Per the F4/G15e rule that DENY covers the audit ledger for file
tools, this is data-integrity hygiene, not optional.

New conftest autouse stand-ins (default approve, like 14e): patch the module-level seams `tools.provision_ai_agent_auth._confirm_on_tty`
and `core.setup_dr_key._confirm_on_tty`/`_stdout_is_terminal` (defined per §1.3) to approve, so the ~15 existing provision calls and
5 existing DR tests run unmodified. The new tests override them per-test.

Provision (`tests/test_g15i_operator_script_guards.py`):
1. approve (`y`, `yes`, `Y`): token returned; user row + one live token exists; exactly one audit row
   `HIGH_IMPACT / provision_ai_agent_auth.provision / allowed` with static `command`; the token string and the
   username never appear in the audit bytes.
2. decline (`n`, empty line, `yep`, `no`, `\x04` EOF): `ProvisionNotConfirmed` raised; the DB has NO `users` row
   and NO `api_tokens` row (open a second `DatabaseManager` on the same tmp file to check; for `:memory:` check
   `DatabaseManager` was never constructed via a recording fake); one `refused` audit row.
3. no tty (`open_tty` raises `OSError`): same as decline; message static.
4. rerun with an existing user and an existing live token, declined: the old token still authenticates
   (`authenticate_token` not None) — i.e. the revoke did not happen before consent (this is the harmful path).
5. rerun approved: old token revoked, new token valid (existing behaviour preserved).
6. stale-typeahead: bytes `y\n` written to the pty master before the prompt do not approve (copy the 14e test).
7. `ValueError` for a user that exists with a non-`ai_agent` role is still raised to the caller on the approved
   path, and the audit row is `failed` with a static reason (no exception text).
8. bad `custom_permissions` raises `ValueError` BEFORE any prompt (opener never called).
9. prompt contents: seen on the pty, contains the db path, `REVOKED`, the stdout-terminal disclosure line;
   a username containing `\x1b[31m` or a newline is shown ascii-escaped (`!a`), never raw.
10. `main()`: declined -> returns 2, stderr has the static line, stdout EMPTY (no token); approved -> stdout is
    exactly the token plus newline.
11. static/AST: the string `provision_ai_agent_auth.provision` and the fixed `command` are literals (no f-string)
    in the `gate_human_action` call (AST check, like the 14e label test).

DR key:
12. approve with a tty-like stdout (`_stdout_is_terminal` -> True): behaviour identical to today (config gets the
    pubkey only; private key on stdout once; no file contains `AGE-SECRET-KEY`), with `subprocess.run` called once.
13. decline / EOF / no tty / stdout NOT a terminal: return 1; `subprocess.run` NOT called; config bytes
    identical before/after (`cfg_file.read_text()` equal); nothing printed to stdout.
14. the already-configured no-`--force` path returns 1 with NO prompt (opener never called) — the benign path
    must stay prompt-free.
15. `--force` over an existing key, declined: config still holds the OLD pubkey; approved: new pubkey; the prompt
    names the old pubkey.
16. stdout-not-a-terminal is refused even when the human would approve (opener never called).
17. AST: `core/setup_dr_key.py` imports none of the banned names (the two existing AST tests still pass), and
    `core/tty_confirm.py` imports none of them either.

Primitive (`tests/test_tty_confirm.py`): the same y/yes/n/empty/EOF/`^C`/no-tty/stale-typeahead matrix as the 14e
tests, against `core.tty_confirm.confirm_on_tty` with an injected `open_tty`; plus a parity test that the same
scenarios give the same result through `lora_import._confirm_on_tty`.

Regression set to run (disposable env, chunks under 100 s): `tests/test_lora_action_boundaries.py`,
`tests/test_setup_dr_key.py`, `tests/test_provision_ai_agent_auth.py`, `tests/test_ccos_crm_read.py`,
`tests/test_business_mutation_authority_coverage.py`, `tests/test_filesystem_protected_paths.py`,
`tests/test_g15e_unit_c.py`, the shell classification suites that name these scripts
(`tests/test_shell_g15d_unit_b.py`), `tests/test_action_gateway*.py`.

### 1.6 Accepted residuals (state them in the ledger)

R1 same-uid script children can patch the module guard or use `DatabaseManager`/`AuthService.create_token`
directly or reimplement `age-keygen` + config write (D-1, F2, G15b-19); G15i guards the named entry points only.
R2 a script that creates its own pty (`pty.fork`, `script`, `expect`) can answer the prompt; no OS boundary exists
(D-10 future WP). R3 a human who approves while the command was started by an agent receives a token/key on a
stdout the agent may see: for provision the prompt discloses the stdout status but cannot prevent approval; for
the DR key the stdout-must-be-a-terminal rule closes the captured-pipe case but not a pty-wrapping parent.
R4 a background process group opening `/dev/tty` can be stopped by SIGTTIN rather than refused (same as lora).
R5 the REPL already shows a per-command `shell()` prompt for ACT; the in-function prompt is then a *second*
prompt for the same act (intended: the second one is the HIGH-impact-aware one that names the revocation).
R6 `python3 -m tools.provision_ai_agent_auth` is HIGH in confirm-less modes but in the REPL the per-command
shell prompt plus the new tty prompt both apply. R7 audit rows only exist for provision (option A for DR). R8
the unguarded siblings listed in G15b-21 (`bash setup_repo.sh`, `bash <repo>/codey-stop`, migrate/backfill
`--apply`, `restoricon_core.api.server --host 0.0.0.0`) are NOT guarded by this slice (narrow by the register's
own wording). Candidates for a follow-up are logged, not done.

### 1.7 Rule 4, review and live verification

- **Rule 4 (process-lifecycle):** not literally triggered — no daemon start/stop, PID, kill, lock or Core API
  server binding/auth is changed. But the slice edits the credential-minting path and (through the delegation)
  `core/lora_import.py`, whose confirmation guards model swap/rollback, so I classify it as
  **code-reviewer mandatory (security/auth-adjacent + touches a live-verified lifecycle-adjacent module)** and
  ask the reviewer to apply the rule-4 adversarial standard to the delegation edit.
- **Live verification (recommended, small):** pty harness reusing the NEW-971 pattern
  (`docs/wp2_1_new971_live_verification.md`: real pty, real subprocess, disposable everything) and the 14e
  harness. Run the REAL CLIs as subprocesses under `pty.fork()` so there is a real controlling tty:
  (a) `python3 tools/provision_ai_agent_auth.py --db-path <disposable>` with `PYTHONPATH=<repo>`: answer `n` ->
  rc 2, DB has no user; answer `y` -> token, DB has user+token; run again `y` -> prior token revoked; run with
  `start_new_session=True` and stdin/stdout piped (no ctty) -> rc 2, no DB rows (this reproduces the agent
  harness's ENXIO for real); (b) `python3 core/setup_dr_key.py` with `CODEY_CONFIG_PATH=<disposable>` and a
  PATH shim `age-keygen` (a shell script printing a canned `# public key:` + `AGE-SECRET-KEY-` pair; assert
  `shutil.which('age-keygen')` resolves to the shim) -> `n` leaves config bytes unchanged; `y` writes the pubkey;
  captured stdout (pipe) -> refused even though a ctty exists; (c) the same `shell()` route: through the real
  `tools.shell_tools.shell` under `confirm_shell=False` (the `--yolo` shape), `python3 core/setup_dr_key.py` is
  classified ACT and executes, but the child's `/dev/tty` open fails (shell child has no ctty in the harness) so
  nothing is generated — this is the end-to-end proof the guard covers the confirm-less mode that was open.
  No model load, no `free -h` requirement beyond the usual baseline; the verifier must assert the resolved
  `CODEY_CONFIG_PATH`, `--db-path` and `HOME` are under the disposable dir BEFORE launching and abort otherwise,
  and must not touch `~/.codeyOS`. Tier language: code complete / reviewer-approved / live-verified are separate.

### 1.8 Ledger entries to propose (all PROVISIONAL ids)

- Update NEW-1028 (G15b-21 row): "FIXED at the code-complete tier for the named entry points" + the rule-6
  correction of fact 3 (`-m provision` is HIGH since G15d Unit B; the ACT residual is the script forms) + fact 4
  (the script form works under launcher `PYTHONPATH`) + residuals R1-R8. Update NEW-977 with a one-line pointer to
  `core/tty_confirm.py` (delegation). Update consolidated register G15b-21 (coordinator, after the slice).
- NEW-1070 (provisional) CONFIRMED, Low-Medium, follow-up: unguarded sibling operator entry points named in
  G15b-21 that G15i does not cover (`setup_repo.sh`, `codey-stop` by path, migrate/backfill `--apply`,
  `restoricon_core.api.server --host 0.0.0.0`) — queue, future trigger "any of them reachable in a confirm-less
  mode after D-1".
- NEW-1071 (provisional) CONFIRMED, Low: `provision()`'s docstring warns that a rerun kills the deployed token but
  the CLI printed nothing before acting; resolved as a side effect by the prompt text (record as closed-by-G15i
  rather than a separate open item; only write it if the reviewer wants it tracked).

### 1.9 Cost and split

Estimated 0.5-0.8M tokens (consolidated section 8) holds: the work is two small refactors plus one shared module
and a pty-backed test file; the lora delegation is the only risk item. **Two implementer units, in order:**
- **Unit G15i-A:** `core/tty_confirm.py` + `lora_import.py` delegation + `tests/test_tty_confirm.py`. Pure
  extraction, no behaviour change; gate = the entire existing lora suite green and unmodified.
- **Unit G15i-B:** the two operator-script guards + conftest stand-ins + `tests/test_g15i_operator_script_guards.py`
  (depends on A). Live verification after B.

---------------------------------------------------------------------------------------------------------

## 2. G15j — HIGH_IMPACT file-write confirmation in the REPL and non-tty runs (G15b-37; NEW-1027)

### 2.0 Status: PROPOSED, NEEDS ISH'S GO (D-8 undecided)

D-8 asks whether the "HIGH (amb)" rating of G15b-37 stands (consolidated recommendation: keep HIGH). Until Ish
answers, nothing in this section should be implemented. The design is complete so a "yes" can be executed
without another architect round. Everything is scoped to the narrowest set of call sites that evidence shows
are unprompted, and uses NO new config knob (so no dashboard-editability question arises; section 2.3).

### 2.1 Verified facts

1. **Where HIGH file writes are unprompted.** `tools/file_tools.py`:
   - `tool_write_file` (:215-346): the human is asked only for an EXISTING file, via `ask_confirm` at :300
     (`WRITE_PROTECTED` names) or :306 (`confirm_write`). A new file reaches the gateway with no prompt.
     The call is :330-341: `authority = classify_write_action(...)`, `confirm_available = bool(AGENT_CONFIG.get(
     "confirm_write", True)) or bool(AGENT_CONFIG.get("allow_self_modification", False))`, `gate_write(...,
     confirm_available=confirm_available)`.
   - `tool_append_file` (:349-382): no prompt of any kind, same Boolean (:364-377). (Register text cites
     `file_tools.py:294`; the line moved with G15e, the logic is now :331-333 and :367-369.)
   - Because `confirm_write` defaults True (`utils/config.py:157`) in the REPL and in one-shot `main.py "task"`,
     `confirm_available` is True there and the gateway's HIGH fail-closed rule (`core/action_gateway.py:225`,
     :328) does not fire. `confirm_available=True` "only unblocks the fail-closed rule and does not itself
     constitute consent" (module docstring :29-36) — the writes then proceed.
2. **`tools/patch_tools.py` is NOT part of the gap.** `tool_patch_file` (:15-155) asks `ask_confirm("Apply
   patch?")` whenever `confirm_write` is set (:86-94) BEFORE the gateway call, and returns `[CANCELLED]` on No.
   So in every mode where `confirm_available` is True via `confirm_write`, a patch has had a human prompt.
   The slice list in the consolidated table names `patch_tools.py`; evidence says it needs no code change
   (a test asserting this is added instead; section 2.5 test 12). If Ish wants a uniform tty-based prompt for
   patches too, that is a separate decision (Q-F).
3. **Gateway.** `ActionGateway.gate_write` (:196-290) and `gate_append` (:292-388) take only the Boolean.
   `gate_exec` (:412-553) already takes `confirm: Optional[Callable[[], bool]]` and implements the semantics
   wanted: HIGH_IMPACT + available path + callback -> `confirm() is True` required; `EOFError`/
   `KeyboardInterrupt` -> refused ("unavailable or interrupted"); any other exception -> refused ("callback
   failure", exception text deliberately omitted); `False`/non-True -> refused ("declined"). Those three reason
   strings are pinned verbatim by `tests/test_action_gateway_confirmation.py:15-19` and
   `tests/test_shell_refusal_accounting.py:14-16` — the strings contain the noun "command".
4. **There is already an in-agent precedent for exactly this callback pairing:** `tools/shell_tools.py`
   (:1950-1980) builds `confirm()` calling `ask_confirm(f"Run shell command: ...")` for HIGH commands when
   `confirm_shell` is true and passes it to `gate_exec(..., confirm=confirm)`. It uses the stdin-based
   `utils.logger.confirm` (`utils/logger.py:124-142`: `console.input("...[y/N]: ")`; EOF -> False; empty -> False).
   G15j mirrors this pairing for file writes; it does NOT reuse the `/dev/tty` primitive (decision in 2.3 and
   Q-C), because the shell tool's HIGH confirm, the overwrite confirm and the patch confirm are all stdin
   `ask_confirm` and a new, different channel for one write path would be inconsistent in the REPL.
5. **Other callers of `gate_write`/`gate_append`** (repo grep, non-test): `main.py:1429` (`/ignore`, ACT,
   `confirm_available=False`) and `core/preferences.py:545` (`_sync_to_codeymd`, hardcoded HIGH_IMPACT,
   Boolean `confirm_available`; it too writes `CODEY.md` unprompted in the REPL — a model-steering write with
   the same Boolean gap, but it is a learning-system side effect not a model tool call, outside the three
   files of this slice; logged as an adjacent finding, 2.8). Adding an optional keyword with default `None`
   leaves both callers byte-identical.
6. **Mode matrix (read from `main.py:112-121,2351`, `core/fixmode.py:61`, `core/tdd.py:127`,
   `core/task_executor.py:422`, `ccos/plugins/coding/agent/agent.py:72-137`):** `--yolo`, `--fix`, `--tdd`, daemon
   tasks and CCOS `coding.run_agent(confirm_write=False)` set `confirm_write=False`, so `confirm_available` is
   False unless `allow_self_modification` — HIGH is refused (or, with self-mod, allowed by the 2026-10-08
   decision and the accepted G15b-36 residual). The unprompted gap is therefore exactly: **`confirm_write` True
   (REPL and non-yolo one-shot), HIGH_IMPACT target, new file or append.** Reachability precondition: the
   target must be inside the workspace (`WORKSPACE_ROOT = cwd`) or, with `--allow-self-mod`, under `CODE_DIR`
   (`core/filesystem.py:185-210`); for core files that means cwd = repo (or an ancestor), or self-mod on.
7. **What HIGH covers after G15e** (`classify_write_action`, `tools/file_tools.py:89-157`): `is_core_file`
   (`*.py` under core/tools/utils/prompts/ccos-plugins/bench roots, `core/checkpoint.py:69-86`) and every
   `core.protected_paths` hit at either tier except `git-component`; DENY-tier hits are also labelled HIGH so
   confirm-less modes get an audited refusal, and `Filesystem` raises for DENY in every mode with no flag
   (`core/filesystem.py:107-120`). So in the REPL a DENY target (`.bashrc`, `.ssh`, state dir, audit ledger,
   `.git`) already ends in `[ERROR] Access denied`; **a callback must not ask the human about a write that
   `Filesystem` will refuse** (pre-validation, 2.3).
8. **Pinned test that G15j flips deliberately:** `tests/test_file_tools_protected_classification.py:
   test_repl_f3_new_file_and_append_unprompted_deny_refused` (:186-211) asserts `ask.assert_not_called()` for a
   REPL new-file write and append of `install.sh` under `allow_self_modification=True`, `confirm_write=True`,
   and `ask.call_count == 1` for the overwrite. Its comment names G15j. The test must be rewritten, not deleted.
9. `utils.logger.confirm` is imported lazily inside the tool functions (`file_tools.py:231`:
   `from utils.logger import confirm as ask_confirm`), so tests patch `utils.logger.confirm` (as the pinned
   test does). The new callback must import it lazily the same way.
10. `rich` markup: `console.input(f"...{question}...")` renders markup in the question, so a model-chosen path
    containing `[red]`/`[/x]` can restyle or raise `MarkupError`. The existing shell confirm does not escape;
    the new prompt must (`rich.markup.escape(ascii(path))`).
11. Known pre-check mismatch: `tool_write_file` computes `file_exists` against `os.getcwd()` not `fs.workspace`
    (NEW-1063). Hence the design below keys "did a human already consent in this call" on an explicit flag, not on
    `file_exists`.

### 2.2 The documented Boolean convention — what changes and what does not

The gateway docstring (:29-36) states "Callback-free calls and file gates retain the existing Boolean convention".
G15j changes the second half: file gates GAIN an optional callback with the same semantics as `gate_exec`, and the
sentence is updated. The convention for callback-free calls is **unchanged**: HIGH + `confirm_available=True` +
`confirm=None` still proceeds (preferences sync, the self-mod/no-confirm path). Nothing is made mandatory at the
gateway: the authority model stays "caller opts into a prompt", and the REPL file tools are the callers that
opt in. I deliberately do NOT make a callback mandatory for HIGH at the gateway: it would break `preferences`
(no human channel there), the `allow_self_modification` decision of 2026-10-08, and every confirm-less caller.

### 2.3 Design

**A. `core/action_gateway.py`**
- New private helper `_confirmation_refusal_reason(confirm, noun: str) -> Optional[str]` containing the existing
  try/except block of `gate_exec` (:484-494) with the three strings built from `noun` (`f"Human confirmation
  declined; {noun} not attempted."` etc.). `gate_exec` calls it with `noun="command"` so its strings are
  byte-identical (pinned by the two test files above; also add a parity test).
- `gate_write(..., confirm: Optional[Callable[[], bool]] = None)` and `gate_append(..., confirm=None)`: after the
  `HIGH_IMPACT and not confirm_available` refusal and BEFORE `get_filesystem()`/`filesystem.write`, insert:
  `if authority == HIGH_IMPACT and confirm is not None: reason = _confirmation_refusal_reason(confirm, "write")`
  (noun `"write"`/`"append"`); if not None, build a REFUSED decision with `detail={"action","path"}` and audit
  it exactly like the existing fail-closed refusal (same fields), return. READ/ACT ignore the callback.
- Docstrings: update the module paragraph and both methods' `confirm` Args. The callback is called at most once,
  runs before any filesystem effect (no checkpoint, no mkdir, no snapshot), and is never given the content.

**B. `tools/file_tools.py`**
- New private helper `_high_write_confirm(kind: str, path: str, content: str)` returning a zero-arg callable that
  implements: (1) fail closed unless `sys.stdin.isatty()` (try/except -> False): no read from a pipe or closed
  stdin, so a parent feeding `y` cannot approve and a one-shot with stdin closed is refused (this is the
  "fail-closed when there is no tty" requirement; `ask_confirm`'s own EOF -> False is the second line of
  defence); (2) build the prompt: kind (neutral wording, not "create a new file": `write to` / `append to`, because the NEW-1063 pre-check mismatch means the tool may not know the file exists; optionally append "(file already exists)" when `fs` can prove it), `ascii(path)` capped at 300 chars,
  byte length of `content`, an `ascii(content[:200])` preview, the sentence "This is a Codey-OS core / protected
  file (HIGH_IMPACT).", all passed through `rich.markup.escape`; (3) return `ask_confirm(prompt) is True` using
  the lazily imported `utils.logger.confirm` (default No: empty/EOF/interrupt already return False there).
- `tool_write_file`: set `human_consented = False` at the top; set it True when the existing-file branch's
  `ask_confirm` (:300 or :306) returned True. After computing `authority` and `confirm_available` (unchanged
  expressions), compute the callback:
  `confirm_cb = None` unless **all** of: `authority == HIGH_IMPACT`; `bool(AGENT_CONFIG.get("confirm_write",
  True))` (a human prompt path exists in this mode); `not human_consented`; and a pre-validation
  `fs._validate_for_mutation(path)` does NOT raise `FilesystemAccessError` (otherwise leave `confirm_cb=None` so
  the gateway proceeds to `Filesystem`, which raises and produces the same `[ERROR] Access denied` + `failed`
  audit row as today, with no prompt). Pass `confirm=confirm_cb` to `gate_write`; when `confirm_cb is None` call
  it WITHOUT the keyword (keeps recording-fake gateways in existing tests, which may not accept `confirm=`,
  byte-compatible).
- `tool_append_file`: same, with `human_consented=False` always (append never prompted).
- A REFUSED decision keeps today's mapping `[BLOCKED] {reason}`; the reason now reads "Human confirmation
  declined; write not attempted." etc., which is truthful and distinct from the fail-closed text.
- `confirm_available` expressions and the `allow_self_modification` semantics are NOT edited. Behaviour table
  (HIGH target, valid path):

  | mode | `confirm_write` | self-mod | new file / append today | after G15j |
  | --- | --- | --- | --- | --- |
  | REPL / one-shot with a terminal | True | False | proceeds, no prompt | prompt; No/Enter/EOF/no tty -> `[BLOCKED]` |
  | REPL / one-shot with a terminal | True | True | proceeds, no prompt | prompt (default; Q-B) |
  | one-shot, stdin closed or piped | True | any | proceeds, no prompt | `[BLOCKED]`, no read from stdin |
  | `--yolo`, daemon, fix, tdd, bench, CCOS | False | False | `[BLOCKED]` (fail-closed) | unchanged |
  | same | False | True | proceeds (G15b-36 accepted) | unchanged |
  | existing file overwrite | True | any | legacy `Overwrite?` prompt only | unchanged (no second prompt) |
  | patch | True | any | legacy `Apply patch?` prompt only | unchanged |

**C. `tools/patch_tools.py`:** no functional change (fact 2). Add a 2-sentence comment at the gateway call noting
the earlier `ask_confirm("Apply patch?")` is the human consent for HIGH targets and so no callback is passed, with
a pointer to `file_tools._high_write_confirm` — the explicit reason a future reader should not "add" one. The
file stays on the slice's touch list only for that comment and for a regression test.

**D. New knobs:** none. The behaviour is derived from the existing `confirm_write` and `allow_self_modification`
settings, both already editable via the existing config/dashboard path, so Ish's rule "everything configurable
must be dashboard-editable" is satisfied by construction. (If Q-B is answered "allow-self-mod suppresses the
prompt" it is still a derivation from the existing flag, no new setting.)

**E. Why stdin `ask_confirm` and not the `/dev/tty` primitive from G15i.** (1) In the REPL the file-write
callback shares a process, a console and a prompt style with the shell HIGH confirm, the overwrite confirm
and the patch confirm, all `ask_confirm`; (2) the threat G15j addresses is *missing consent while a human is
present* (and silent success when none is), not a hostile same-uid parent — a same-uid script already writes
the files directly (F2/D-1); (3) the `isatty()` guard makes the no-human case fail closed, matching
`main.py`'s own `sys.stdin.isatty()` interactivity test (`main.py:511,869,893`); (4) stale typeahead remains a
property of every `ask_confirm` prompt in the REPL, tracked as an adjacent finding rather than fixed here.
The alternative (route the file prompt through `core/tty_confirm.confirm_on_tty`, gaining tcflush) is cheap once
G15i-A lands; it is offered as Q-C, default "no".

### 2.4 Files and functions (touch list)

| file | change |
| --- | --- |
| `core/action_gateway.py` | `_confirmation_refusal_reason`, `confirm=` on `gate_write`/`gate_append`, `gate_exec` delegates, docstrings |
| `tools/file_tools.py` | `_high_write_confirm`, `human_consented` tracking, pre-validation, pass `confirm=` conditionally; update the module-level comment at :312-329 |
| `tools/patch_tools.py` | comment only |
| `tests/test_file_tools_protected_classification.py` | rewrite the pinned test (fact 8) |
| `tests/test_action_gateway_file_confirmation.py` (new) | gateway-level tests |
| `tests/test_g15j_file_tool_confirmation.py` (new) | tool-level tests incl. mode matrix |

### 2.5 Tests (recording fakes, fake tty; no real writes outside tmp_path)

Environment for every test: tmp_path workspace and a tmp `CODE_DIR` copy (use the fixture style of
`tests/test_file_tools_protected_classification.py:env`), `CODEY_ACTION_GATEWAY_AUDIT` in tmp_path,
`reset_action_gateway()`, `Filesystem._require_checkpoint` stubbed with a `Mock` (no git), `utils.logger.confirm`
replaced by a recording `Mock`, `sys.stdin.isatty` patched via `monkeypatch.setattr(file_tools, "_stdin_is_tty",
lambda: True)` (add that one-line seam so the test never touches real stdin), `AGENT_CONFIG` via `monkeypatch.
setitem`. The real `/dev/tty` and the real console are never used.

Gateway-level (`test_action_gateway_file_confirmation.py`), mirroring `tests/test_action_gateway_confirmation.py`:
1. matrix: callback returns True/False/"yes"/None, raises `EOFError`/`KeyboardInterrupt`/`RuntimeError("secret")`
   -> only a literal `True` writes; every other case REFUSED with the three expected reasons (noun `write` /
   `append`), exception text absent from the reason and from the audit bytes, one audit row per call.
2. the callback runs BEFORE the filesystem: use a recording fake `Filesystem` whose `write`/`append`/`get_filesystem`
   record calls; on decline `calls == []` (no checkpoint, mkdir or snapshot — assert `_require_checkpoint` not
   called).
3. callback is ignored for ACT and READ (not called; write proceeds) and `confirm=None` HIGH + `confirm_available=
   True` proceeds exactly as today (convention preserved); HIGH + `confirm_available=False` + callback still
   fail-closed and the callback is NOT called.
4. parity: `gate_exec` reason strings unchanged (re-run `tests/test_action_gateway_confirmation.py` and
   `tests/test_shell_refusal_accounting.py` untouched).

Tool-level (`test_g15j_file_tool_confirmation.py`; HIGH targets: `core/zz_new.py`, `install.sh`,
`ccos/plugins/x/manifest.json` inside the tmp CODE_DIR with `allow_self_modification` as required):
5. REPL (`confirm_write` True, tty True): new-file write to a HIGH path prompts exactly once; `y` writes the
   file and audits `allowed`; `n`, empty, EOF -> `[BLOCKED] Human confirmation declined...`, file absent, audit
   `refused`; the prompt text contains the ascii-escaped path, the size and the preview; a path with `\x1b[31m`,
   a newline and `[bold]` markup is shown escaped (assert `rich.markup.escape` applied: the recorded question
   has no raw ESC, no raw newline in the path portion).
6. same for `tool_append_file`.
7. ACT target (ordinary workspace file) in the REPL: NO new prompt (`ask.assert_not_called()`), identical output
   to today — the change must not add friction to ordinary writes.
8. existing HIGH file overwrite in the REPL: exactly ONE prompt (the legacy `Overwrite?`), not two; declined legacy
   prompt returns `[CANCELLED]` and never reaches the gateway; an approved legacy prompt passes no callback.
9. no tty (`_stdin_is_tty` False, i.e. closed or piped stdin) with `confirm_write` True: `[BLOCKED]`, `ask`
   NEVER called, file absent — also with a "piped y" simulated (`ask` would return True if called).
10. DENY target in the REPL (`$HOME/.bashrc`, state dir, `.git/hooks/x`) and an out-of-workspace path: NO prompt,
    result `[ERROR] Access denied ...`, audit `failed` (pre-validation leaves `confirm=None`), file absent.
11. confirm-less modes unchanged: `confirm_write` False, self-mod False -> `[BLOCKED]` fail-closed, `ask` not
    called; `confirm_write` False, self-mod True -> writes without a prompt (G15b-36 residual pinned).
12. `tool_patch_file` on a HIGH file in the REPL: exactly one prompt (`Apply patch?`), no `confirm=` kwarg passed
    to the gateway (recording gateway spy), behaviour unchanged.
13. NEW-1063 mismatch: cwd != workspace, target exists in the workspace but `file_exists` computed False: the
    write still gets exactly one HIGH prompt (proves `human_consented` rather than `file_exists` drives it).
14. rewritten pinned test: with `allow_self_modification=True`, `confirm_write=True` the new-file write and
    append of `install.sh` now each prompt (call_count 2) and the overwrite adds the legacy prompt (3), or the
    Q-B alternative if Ish chooses it. Keep its DENY half (`~/.ssh/authorized_keys` -> `[ERROR]`, no `.ssh` dir).
15. recording-gateway test: tool functions pass `confirm=` only for the HIGH + `confirm_write` + not-consented
    case and not otherwise (so third-party fakes without the kwarg keep working).

Regression chunks to run: `tests/test_action_gateway*.py`, `tests/test_file_tools*.py`, `tests/test_patch_tools.py`
(NEW-1065: it writes into the real repo `core/` — run in a disposable copy or with the known caveat),
`tests/test_filesystem*.py`, `tests/test_preferences_sync_to_codeymd.py`, `tests/test_shell_*gateway*`/`test_shell_refusal_accounting.py`,
`tests/test_g15e_unit_c.py`, `tests/test_wp21_census.py` (the census scans for `gate_write` call sites: the
new keyword must not change a row classification; run `tools/wp21_census.py --check` per the handoff §4 item 5
only if the gateway signature change is flagged by the census test).

### 2.6 Accepted residuals

R1 same-uid script children write the files directly (F2/D-1); G15j is a consent control for the file TOOLS.
R2 `ask_confirm` has no typeahead flush: a "y" typed ahead during generation can approve a later prompt in the
REPL (pre-existing for shell, overwrite and patch prompts too; adjacent finding). R3 `isatty()` is true under any
pty, including one an agent child created; the file tools run in the agent's own process so this concerns only
nested agent launches. R4 `--allow-self-mod` + `--yolo` (confirm_write False) stays unprompted (accepted
G15b-36). R5 `CODEY.md` sync (`core/preferences.py`) and the `/ignore` append stay unprompted (2.8). R6 the
preview shows only the first 200 characters; a large append can hide its payload after the cut — the prompt
states the byte length and a human who is unsure answers No. R7 prompts can now appear for every new core file in
a self-mod REPL session (the friction is the point; Q-B offers the opt-out). R8 TOCTOU between the pre-validation
and the write (symlink swapped between) is inside the F2 ceiling and `Filesystem` re-validates at write time.
R9 the existing-file HIGH overwrite is covered by the legacy prompt whose text does not say "HIGH"; wording is
left alone.

### 2.7 Rule 4, review and live verification

- **Review:** code-reviewer MANDATORY (CLAUDE.md workflow: security/RBAC; the slice edits the gateway's
  authority model for all file writes). Rule 4 in its literal text (daemon/PID/kill/lock/API binding) is not
  triggered, but I recommend the reviewer apply the same adversarial standard as for rule 4 and specifically try:
  (a) a callback that returns a truthy non-True, (b) an exception whose message contains the path or content,
  (c) a prompt injection through path/content (ANSI, newline, rich markup), (d) the REPL with stdin closed, (e)
  the `human_consented` flag being set on a path where the human answered No, (f) a recording-fake gateway
  without the `confirm` kwarg, (g) `gate_exec` string drift.
- **Live verification:** needed, and it should be done on a real pty, reusing the NEW-971 harness pattern
  (`docs/wp2_1_new971_live_verification.md`: real `console.input` on a real pty slave, a private audit file,
  fakes only for external CLIs): a driver run under `pty.fork()` that imports the REAL `tools.file_tools` in a
  disposable workspace and disposable CODE_DIR copy (assert both resolve under the disposable root before
  launch), with `confirm_write=True`, drives: `y` / `n` / Enter / `^D` / `^C` on a HIGH new-file write and a HIGH
  append; the ACT control (no prompt); the DENY control (no prompt, refused); the same driver started with
  `stdin=DEVNULL` and with stdin piped `y\n` (must be `[BLOCKED]`, no prompt text emitted); and the real audit
  rows. This closes CLAUDE.md's gap between "reviewer-approved" and "live-verified" (`NEW-259` is the cautionary
  case). No model load, no network, no git (stub `_require_checkpoint`). A second, optional leg: the real
  `main.py` one-shot with a scripted model is NOT required and would load a model; do not do it.

### 2.8 Ledger entries to propose (all PROVISIONAL ids; verify the tail first)

- Update NEW-1027: on implementation mark "FIXED at the code-complete tier for REPL / non-yolo one-shot new-file
  and append HIGH writes"; record fact 2 (patch already prompts; the register's `patch_tools.py` was not a gap),
  fact 1 (line moved, register's `file_tools.py:294` is stale), the `human_consented` design and R1-R9; flip the
  pinned-test note; correct NEW-1027's "Fix design" to say the callback is stdin `ask_confirm` + `isatty()` and
  pairs with `shell()`'s precedent.
- NEW-1072 (provisional) CONFIRMED, Medium-Low, adjacent: `core/preferences.py:545` `_sync_to_codeymd` writes
  `CODEY.md` (steers the agent's system prompt, G15b-40 class) as HIGH_IMPACT with the Boolean `confirm_available`
  — unprompted in the REPL; the learning system, not the model, is the writer. Future trigger: any change to
  `preferences` or a decision on G15b-40 (steering state).
- NEW-1073 (provisional) CONFIRMED, Low, adjacent: `utils.logger.confirm` does not flush typeahead and does not
  check `isatty()`; every REPL confirm (shell, overwrite, patch, and G15j's) can be satisfied by queued input or a
  piped `y`; `tools/shell_tools.py` HIGH confirm has no tty guard (G15j adds one for file writes only). Fix would
  be a shared hardened `ask_confirm`; future trigger: a decision that REPL confirms must be tty-bound.
- Consolidated register G15b-37 row and NEW-975's note ("Interactive default mode prompts per write") are
  corrected by the coordinator after the slice, not by the implementer.

### 2.9 Cost and split

Estimated 0.7-1.1M tokens, below the consolidated 1.0-1.5M (patch_tools needs no code; no tty primitive). **Two
implementer units:**
- **Unit G15j-A:** `core/action_gateway.py` (helper + `confirm=` on the two methods + docstrings) +
  `tests/test_action_gateway_file_confirmation.py`. Pure addition; gate: existing gateway and shell-refusal tests
  green and unmodified. Reviewer round on the gateway change alone.
- **Unit G15j-B:** `tools/file_tools.py` + the `patch_tools.py` comment + rewritten pinned test +
  `tests/test_g15j_file_tool_confirmation.py` (depends on A). Live verification after B.

---------------------------------------------------------------------------------------------------------

## 3. Cross-cutting: unit order, dependencies, open questions

### 3.1 Unit order (at most two per slice)

1. G15i-A (shared tty primitive + lora delegation) — no dependency, no Ish decision needed.
2. G15i-B (the two operator-script guards) — after A. Live-verify B.
3. G15j-A (gateway callback) and 4. G15j-B (file tools) — ONLY after Ish's go on D-8 for G15b-37. G15j does not
   depend on G15i (it uses `ask_confirm`, Q-C aside), so it may run in either order once approved.
No unit touches `bench/` (the G15f Unit B files are uncommitted and in review) or any ledger file; the
coordinator writes ledgers after reviewer approval. No new dependency, so `install.sh` is unchanged (rule 11).
The implementer prompts must say: never `git stash`/reset/checkout/clean/add -A; use
`/data/data/com.termux/files/usr/bin/grep`; run every pytest with an absolute disposable `HOME`,
`CODEY_STATE_DIR`, `CODEY_ACTION_GATEWAY_AUDIT`, `CODEY_CONFIG_PATH`, `RESTORICON_DB_PATH` under
`/data/data/com.termux/files/usr/tmp/<name>`, proxy vars unset; no model loads.

### 3.2 Open questions for Ish (genuine; everything else was decided on the stated default)

- **Q-G (gating): G15j go/no-go = D-8 for G15b-37.** Keep the HIGH rating and implement G15j (recommended), or
  lower it to Medium and leave the REPL gap as an accepted residual?
- **Q-B: with `--allow-self-mod` in the REPL (`confirm_write` True), should a HIGH new-file/append write prompt?**
  Spec default: YES (consistent with the existing overwrite prompt in the same mode). The alternative treats the
  flag as the consent (as for `--yolo --allow-self-mod`, G15b-36) and leaves self-mod REPL sessions prompt-free
  for new files.
- **Q-A: audit row for `setup_dr_key.py`?** Spec default: no gateway/audit row (keep the operator DR tool on plain
  IO, AST-test intent, runs before state dir exists in `install.sh`); provision gets one. Alternative: uniform
  audited gating for both.
- **Q-C: should G15j's file prompt use the `/dev/tty` primitive (typeahead flush, cannot be fed by a pipe) instead
  of stdin `ask_confirm` + `isatty()`?** Spec default: no, for consistency with every other REPL confirm.
- **Q-D: the DR-key stdout-must-be-a-terminal rule** is an addition beyond "confirm on /dev/tty". Default: include
  (the private key must not reach a captured pipe). Ish may decline if any legitimate redirected use exists.
- **Q-E: may the lora delegation edit (`core/lora_import.py`, NEW-977, live-verified) be made in this slice?**
  Default: yes, under the "lora tests pass unmodified" acceptance rule with a fall-back to duplication.
- **Q-F: should patches also go through the new callback** (uniform channel) instead of relying on the legacy
  `Apply patch?` prompt? Default: no.
- Not asked, but flagged because Ish owns them: the PENDING ISH item "run `setup_dr_key.py` to create the escrow DR
  key" stays pending; nothing in this spec creates one, and verification uses a shim `age-keygen` only.
