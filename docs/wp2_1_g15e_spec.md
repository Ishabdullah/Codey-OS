# WP2.1 slice G15e "protected-path set": technical specification

Date: 2026-10-23. Author: project-architect. Base: committed HEAD `9a61e94` (G15d code at `890d4b9`).
Status: **SPEC ONLY. No source, test or ledger file was edited.** Nothing here is implemented, reviewed or verified.
Decisions applied (Ish, 2026-10-23): **F3 yes** (HIGH write classification extends to `main.py`, the launchers `codeyOS codeydOS codey-start codey-stop codey`,
`lib/*.sh`, `install.sh`, `setup*.sh`, `config.json`, and non-`.py` plugin files including `ccos/plugins/**/manifest.json`; reverses fork 1 and part of fork 3),
**Q2 yes** (PATH-shadow protection: the PATH directories and `$PREFIX/bin` become write-protected: `~/bin`, `~/.local/bin`, `~/google-cloud-sdk/bin`, repo root,
`~/Codey-v4`, system bin). **Not decided, specified as separable data with a recommendation:** D-7, D-8 (section 11).

Sections: 0 grounding | 1 findings covered | 2 design principles | 3 the shared module | 4 the protected-set contents | 5 file-tool side |
6 shell-argv side | 7 tests | 8 accepted false positives | 9 residuals | 10 units, files, order, cost | 11 pending decisions and questions for Ish |
12 live-verification and reviewer needs | 13 proposed ledger entries (for the coordinator, not written) | 14 comments to add (R9 of the G15d spec).

## 0. Grounding (rule 12: every fact below was read or run on this device on 2026-10-23; nothing is from memory)

Method: read-only code reading plus probes in a disposable tree `/data/data/com.termux/files/usr/tmp/g15e_home` (a `git archive HEAD` extract of the repo as
`g15e_home/Codey-OS`, fake `HOME`, `CODEY_STATE_DIR=g15e_home/.codeyOS`, proxy variables unset, `python3 -I`, no model, no network). Probe scripts are
`/data/data/com.termux/files/usr/tmp/g15e_scratch/probe_filetools.py`, `probe_shell.py`, `probe2.py` (scratch, not committed). Real `~/.codeyOS` was never touched;
`~/.bashrc` was grepped only for lines containing `PATH` with the credential-looking words stripped.

### 0.1 Reachability baseline at HEAD (the thing G15e must change)

1. **File tools, workspace = fake home (so the repo copy, `.codeyOS`, `.ssh`, `bin` are all inside the workspace), `confirm_write=False`, `allow_self_modification=False`.**
   `tool_append_file` returned success (`Appended to` / `Created`) for **every one** of these targets: `.bashrc`, `.ssh/authorized_keys`, `.gitconfig`,
   `.config/git/config`, `.codeyOS/age.key`, `.codeyOS/config.json`, `.codeyOS/action_gateway_audit.jsonl`, `bin/ls`, `Codey-OS/main.py`, `Codey-OS/codeyOS`,
   `Codey-OS/lib/service_manager.sh`, `Codey-OS/install.sh`, `Codey-OS/config.json`, `Codey-OS/ccos/plugins/crm/core_query/manifest.json`,
   `Codey-OS/ccos/core/plugin_manager.py`, `Codey-OS/restoricon_core/authority.py`, `Codey-OS/ls`, `Codey-OS/conftest.py`, `proj/sub/.git/config` (nested),
   `proj/.GIT/config` (case variant; on this f2fs home `.GIT` is a distinct literal directory, see 0.4). The only refusal was the workspace-root `.git/config`
   (`[ERROR] Access denied: ... Git metadata directory`).
   `tool_write_file` over `.codeyOS/action_gateway_audit.jsonl` (9 seeded rows plus the probe's own rows) left **2 lines** (`lines now: 2`): the replacement content plus the
   gateway's own success row. `tool_patch_file` on `Codey-OS/main.py` returned `Patched ... (7 chars -> 9 chars)`.
2. **Shell, same tree (`probe_shell.py`; classification plus the two existing scans).** `cp`, `mv`, `ln -sf /dev/null <ledger>`, `touch <.termux/boot/start.sh>`, `mkdir -p <.termux/boot>`,
   `chmod +x <main.py>`, `cp /bin/ls <bin/ls>`, `rm <ledger>`, `cp x <install.sh>`, `dd of=<main.py>`, `python3 <main.py>`, `cp x <.gitconfig>`, `cp x <.config/git/config>`,
   `cp x <manifest.json>`, `cp /bin/ls <Codey-OS/ls>`, `cp x <proj/sub/.git/hooks/pre-commit>`, `cp x <proj/.GIT/hooks/pre-commit>` and the **`/data/user/0/...` spelling of
   `.bashrc`** were all `ACT` with `git_scan=False` and `credential_scan=False`. Only `rm -rf <.codeyOS>` was HIGH, and only because `rm -rf` classifies HIGH by itself.
   `cat <.bashrc>` READ. So the shell route has no cwd precondition and no scan for any protected target.
3. **Reads (a D-2 shaped gap on the file-tool side, not in the register).** `tool_read_file(".ssh/id_rsa")` returned the file content (`'FAKEKEY\n'`) with workspace = fake home.
   `tool_patch_file(<path>, "NOPE", "x")` on a fake `.codeyOS/age.key` AND on a fake secret **outside** the workspace returned `[PATCH_FAILED] ... Current file content:` followed by the
   content (`'TOPSECRET-FAKE' in result` was True; `'AGE-SECRET-KEY-FAKEFAKE' in result` was True). `tools/patch_tools.py:28-55` reads `Path(path).expanduser()` before any
   `_validate_path`. This **re-confirms G15b-38 (previously UNSUPPORTED) with retained evidence**.
4. **Alias spelling.** `/data/user/0/com.termux/files/home` and `/data/data/com.termux/files/home` have the same `st_ino`/`st_dev`; `Path.resolve()` and `os.path.realpath()` leave each
   spelling unchanged (neither is a symlink). The **file tools deny** the alias spelling (`Access denied: ... is outside workspace`, `_validate_path` compares resolved paths to the
   canonical workspace), so for file tools the alias fails closed by accident; the **shell does not** (item 2). Any set keyed on one spelling is bypassed by the other on the shell route (NEW-1039).

### 0.2 Facts that drive the design

5. **Who calls what.** `Filesystem` mutation entry points that must all be guarded: `write` (`core/filesystem.py:203`), `restore` (:254), `make_parent_dirs` (:275), `patch` (:294),
   `append` (:354). Production users: `tools/file_tools.py` (write/append through `gate_write`/`gate_append`), `tools/patch_tools.py:109`, `core/recovery.py:496`, `core/filehistory.py`
   (`/undo`), `main.py:568` and `:1429` (`.codeyignore` append), `core/codeymd.py:49`, `core/preferences.py:545`. None of those target a path in the sets of section 4.
6. **`.git` today.** `_reject_git_metadata_mutation` (`core/filesystem.py:81-109`) matches only `rel.parts[0] == ".git"` under `self.workspace` or `CODE_DIR` (case-sensitive). The shell scan
   `_shell_command_targets_git_metadata` (`tools/shell_tools.py:1285-1396`) has the same root limit and a READ exemption. Pinned by `tests/test_filesystem_git_metadata.py::test_nested_repository_git_is_not_blocked` (line 181) and
   `tests/test_shell_git_metadata_escalation.py::test_git_shaped_token_outside_both_roots_not_detected` (line 218).
7. **Classification today.** `tools/file_tools.py:89-120` `classify_write_action(path)` is `HIGH_IMPACT` iff `core.checkpoint.is_core_file` (any `*.py` under `core tools utils prompts ccos/plugins bench`),
   else ACT. It resolves the raw string against the **process cwd**, whereas `Filesystem` joins relative paths to `self.workspace` (`core/filesystem.py:131-134`). `core/recovery.py:481-499` already passes the
   `fs._validate_path(...)` result instead. `is_core_file` also decides `_require_checkpoint` (git commit plus backup), so it must NOT be widened (NEW-951 split; section 5.3).
8. **HIGH is a weak control for file tools.** `confirm_available = bool(confirm_write) or bool(allow_self_modification)` (`tools/file_tools.py:294-296`, :330, `tools/patch_tools.py:106`) and `gate_write` takes a Boolean,
   not a callback. Consequences, both already in the ledger or new here: (a) in the REPL (`confirm_write` True) a HIGH new-file write or append proceeds with no prompt (NEW-1027, G15j); (b) `--allow-self-mod` turns every HIGH write into
   an allowed one. So **HIGH classification of `~/.ssh`, the PATH dirs or the audit ledger would be unlocked by `--allow-self-mod --yolo`** and would not protect the REPL at all. This is why section 4 defines a DENY tier that no flag unlocks.
9. **Device PATH.** Process `PATH` = `~/bin:~/google-cloud-sdk/bin:~/Codey-OS:~/Codey-v4:$PREFIX/bin:~/.local/bin` (no relative or empty entries). `~/Codey-v4` **does not exist** (`stat` failed). `~/.bashrc` lines 3, 6, 16, 19
   export those entries; **`install.sh:455-462` adds the repo root to PATH** (`export PATH="$CODEY_OS_DIR:$PATH"` appended to the shell config; `install.sh:438` already knows a symlink-into-bin-dir alternative).
   `~/bin` (2 files), `~/.local/bin`, `~/google-cloud-sdk/bin` and `$PREFIX/bin` are owned by the agent's uid with mode 700 (`u0_a247`). `$PREFIX/bin` has 1235 entries (`os.listdir` 10.8 ms); the repo root 315 entries;
   `/system/bin` and `/bin` raise `PermissionError` for `os.listdir` (cannot be enumerated), `/usr/bin`, `/sbin`, `/system/xbin` do not exist. Files created by the file tools are mode `-rw-------` (umask 0077), so a
   planted file is not executable unless a later `cp -p`/`ln`/`chmod` makes it so; overwriting an **existing** executable keeps its mode.
10. **Launchers and F3 files, from the artifact (`git ls-files`).** Tracked `*.sh`: `install.sh lib/bootstrap_environment.sh lib/service_lifecycle.sh lib/service_manager.sh setup.sh setup_repo.sh tools/setup_skills.sh`. Tracked mode 100755:
    `codey codey-metrics codey-start codey-stop codeyOS codeydOS install.sh setup.sh setup_repo.sh` (+ `assets/codey-mascot.png`). **`codey-metrics` is a tracked bash launcher missing from Ish's list.** Tracked non-`.py` under
    `ccos/plugins`: 19 `manifest.json` + 1 `.md` (nothing else; untracked `__pycache__/*.pyc` also lives there). Repo-root `config.json` is gitignored and absent from a `git archive` but present in the working tree.
    `config.json` readers: `utils/config.py:627-648` (`CODEY_CONFIG_PATH` > `CODEY_STATE_DIR/config.json` > `CODE_DIR/config.json`).
11. **Operator-owned writers never touch the gates.** `codey config` is `show_service_config` (display only, `codey:64-67`); `codeydOS config` runs `service_lifecycle.py config-create` -> `core.service_actions` -> `core.daemon_config.DaemonConfig`
    (`save()`/`create_default_config()` use plain `open(..., "w")`, `core/daemon_config.py:156-168`). None of `core/daemon_config.py`, `core/service_lifecycle.py`, `core/setup_dr_key.py`, `core/backup_secrets.py`,
    `core/service_actions.py` imports `core.filesystem`, `tools.file_tools` or `tools.shell_tools` (grep). So protection placed in `Filesystem`, `classify_write_action` and `shell()` cannot block `codeydOS config` or the dashboard.
12. **Daemon shell surface.** `_DAEMON_ALLOWED_PREFIXES` (`core/task_executor.py:56-72`) admit only `pytest ls cat echo grep find "git status/log/diff/show" "cd " pwd which env printenv`, plus `python`/`python3` (script form) and `pip(3) install`
    via `_PYTHON_ALLOWED_PATTERNS`. **`cp mv rm ln touch mkdir chmod dd` are not daemon-admitted**, so the daemon's reachable write route to protected paths is only a script operand (`python3 main.py`, `pytest <path>`), plus the file tools. The
    interactive/`--yolo`/`--fix`/`--tdd`/bench/CCOS shell has the full ALLOWED set: `cp mv ln touch mkdir` (ACT), `rm rmdir chmod dd` (DANGEROUS + ACT, `_daemon_shell` is not involved), `python3 pytest node npm pip make` and the 19 build tools.
13. **`ALLOWED_COMMANDS` members** (dumped): awk cat cd cp cut date df diff du echo env file find git grep head ln ls mkdir mv node npm pip pip3 printenv pwd pytest python python3 sed sort stat tail termux-clipboard-get
    termux-clipboard-set termux-open touch tr tree uniq wc which whoami xargs. `READ_COMMANDS`: cat date df diff du file grep head ls printenv pwd sort stat tail tree uniq wc which whoami. `DANGEROUS_COMMANDS`: chmod cp curl dd mkfs mv rm rmdir wget.
    After G15d, `sort uniq tree file` are READ only when they pass an option table (no output option), `sed` is ACT only with `--sandbox` and no `-i`, `awk` and `find`/`xargs`/`env` are always HIGH: **every read-only-by-construction base can be exempted from a write-target scan**.
14. **Extra startup/exec vectors that exist on this device and are NOT in anyone's list (evidence of existence only, exploitation not exercised):** `$PREFIX/etc/bash.bashrc` and `$PREFIX/etc/profile` (both mode 600, owned by the agent uid),
    `$PREFIX/etc/profile.d/*` (`gawk.sh`, `gawk.csh`, `init-termux-properties.sh`, `java.sh` symlink), `$PREFIX/lib/python3.14/site-packages/*.pth` (`distutils-precedence.pth`, `google_cloud_storage-2.11.0-py3.9-nspkg.pth`; `.pth`
    lines beginning `import` run at every interpreter start, including the daemon), the user site `~/.local/lib/python3.14/site-packages` (exists, so `sitecustomize.py`/`usercustomize.py`/`*.pth` there also run), peer-agent config
    (`~/.claude`, `~/.claude.json`, `~/.qwen`, `~/.codex`, `~/.gemini` all exist; repo `.claude/`, `.qwen/settings.json`), `~/.codey_sessions` (B:HM-07 forged sessions). Section 11 proposes them as Ish-gated candidates.
15. **Case sensitivity.** The home filesystem is f2fs (case-sensitive; probe: `touch Aa` then `ls aA` fails; `mkdir .Git` then `ls -d .git` fails). `/sdcard` is `fuse` (the hunters report case-insensitive behavior there, B:CS-01; not re-probed here).
    So `.GIT` on `$HOME` is harmless today, but the shared set casefolds everything (cost: negligible false positives) so a path reached through a case-insensitive mount is covered.
16. **Test environment.** `conftest.py:53-73` points `CODEY_STATE_DIR` at `tempfile.mkdtemp("codeyos-test-state-")` and `CODEY_ACTION_GATEWAY_AUDIT` at a separate temp dir. So `audit_path()` is the env path in the suite and
    `state_dir/action_gateway_audit.jsonl` in production; a test guarding only the default path would stay green while guarding the wrong file (section 7). Existing tests patch `core.checkpoint.CODE_DIR` and `core.filesystem.CODE_DIR`
    (module attributes), not `utils.config.CODE_DIR` (`tests/test_core_file_classification*.py`).

## 1. Findings covered

| G15b id | ledger | what | covered by | unit |
| --- | --- | --- | --- | --- |
| 07 | NEW-1022 | silent shell writes to protected targets (`ln -sf`, `touch`, `mkdir`, prompting `cp/mv/rm/dd/chmod`; `sed -i`/`sort -o` already HIGH since G15d) | shell argv scan (6) over the shared set | B |
| 08 | NEW-1022 | git-metadata scan gaps G11-G13: sibling-repo `.git/hooks`, `~/.gitconfig`, `~/.config/git/config` | `.git` any-component rule plus `~/.gitconfig`/`~/.config/git/**` in the set (4), both surfaces | A (file tools), B (shell) |
| 26 | NEW-1024 | `config.json` (repo, state, active path) ACT-writable | state/active config DENY, repo-root `config.json` HIGH (F3) | A, B |
| 27 | NEW-1024 | launchers, `main.py`, `lib/`, `install.sh`, `setup*.sh`, `tools/setup_skills.sh` ACT-writable | F3 HIGH entries (4.3), file tools and shell | A, B |
| 25 (classification part only) | NEW-1024 | plugin `manifest.json` and every non-`.py` plugin file ACT-writable | F3 HIGH entry `ccos/plugins/**` (4.3). The non-reversing part (duplicate-name refusal, `entry_point` containment, spawn audit row) is **G15g**, untouched | A, B |
| 28 | NEW-1024 | non-root authority files (`ccos/core/**`, `restoricon_core/authority.py`, ...) | D-7 data tuples, **empty until Ish answers** (11) | C |
| 33 | NEW-1026 | file tools with cwd = `$HOME`/repo write `.bashrc`, `.termux/boot`, `authorized_keys`, `.gitconfig`, Codey `config.json`/`age.key`, launchers | DENY entries (4.1, 4.2) | A |
| 34 | NEW-1026 | audit-ledger truncation/tamper via file tools and shell | `audit_path()` and the state dir in the DENY tier, resolved at call time | A (file tools), B (shell) |
| 35 | NEW-1026, 894 | nested `.git`, case variants | any-component, casefolded, on both surfaces | A, B |
| 09 (second half) | NEW-1037 | PATH-shadow write side (G15d left "narrowed, not closed") | PATH directories in the set (4.4) | A, B |
| (NEW-1039) | NEW-1039 | `/data/user/0` vs `/data/data` aliases | `canon()` folds both on every comparison, both directions (3.2) | A, B |
| 38 (optional, Q7) | NEW-1031 | `patch_file` reads and echoes any readable file before validation | `_validate_path` before `read_text` (5.4) | A (optional) |
| new (optional, Q7) | NEW-1048 (proposed) | `read_file` returns credential files when workspace = `$HOME` | credential-read DENY in `Filesystem.read` (5.4) | A (optional) |

Not covered, deliberately: G15b-30..32 bench lock/conftest/env (G15f). G15b-29's classification half (`bench/**` every suffix HIGH) is **data in this module's `bench-evaluator` row, shipped in Unit C if Ish accepts G15f's Q1** (see 10a); the existing `bench/*.py` HIGH rule is untouched until then; G15b-25 non-reversing part (G15g); G15b-37 REPL/non-tty unprompted HIGH writes and the Boolean `confirm_available` (G15j, NEW-1027);
G15b-19/22/36 accepted ceilings (but see 6.6: the scan narrows G15b-22 as a side effect and the register must not claim it closed).

## 2. Design principles (each one removes a bypass class found in reading the code)

**P1. One shared module, two enforcement surfaces, two tiers.** A single data set in a new module (3) is consulted by (a) `core.filesystem.Filesystem` (the five mutation entry points), (b) `tools.file_tools.classify_write_action`,
and (c) a new shell argv scan in `shell()`. Each entry carries a **tier**:
- `deny`: file tools refuse with `FilesystemAccessError` and **no flag unlocks it** (not `confirm_write`, not `--allow-self-mod`, not `--yolo`), same shape as the existing `.git` denial; the shell scan escalates the command to HIGH_IMPACT.
- `high`: file tools classify the write HIGH_IMPACT (exactly like core `.py` today, so `allow_self_modification` still counts as the operator's confirmation, Ish 2026-10-08); the shell scan escalates to HIGH_IMPACT.
Why a deny tier exists at all: fact 8. HIGH would be a no-op in the REPL (NEW-1027) and would be unlocked by `--allow-self-mod --yolo`, which Ish granted for self-modification of Codey code, not for `$HOME` persistence, credentials, PATH directories or the audit ledger.
Tier is per-entry data, so flipping an entry from deny to high is a one-token edit (Q1).

**P2. The classifier stays free of filesystem access.** `classify_shell_command` is not touched. The new module is imported only by `core/filesystem.py`, `tools/file_tools.py` and the shell-side scan; resolution (`resolve()`, `listdir`, `stat`) happens in the
callers or in injected callables. A test asserts that patching the new module's functions to raise does not change any `classify_shell_command` result (7.5), and `test_classifier_does_not_discover_or_parse_children` stays unchanged.

**P3. Read set and write set are separate data in one module.** G15d's credential constants (`_CRED_HOME_ENTRIES`, `_CRED_STATE_ENTRIES`, `_CRED_STATE_PATTERNS`, `_CRED_BASENAME_PATTERNS`, `_CRED_PATH_ALIASES`, `_cred_canon`) are **moved** into the module and re-exported from
`tools/shell_tools.py` under their old names, so `tests/test_shell_g15d_unit_a.py` passes **unmodified** (that is the evidence the lift preserved behavior). The write set reuses `CRED_HOME_ENTRIES` as its credential-store entries but adds its own
startup, PATH and F3 entries. Merging the two sets would make `cat main.py` and in-repo `grep -r` HIGH (the G15d spec rejected that for `config.json`), so they stay distinct.

**P4. Compare both forms, canonicalized, casefolded.** Every candidate is checked as the lexical absolute path and the `resolve()`d path, each through `canon()` (alias fold) and then `.casefold()`. Entries are stored in the same form. Lexical catches a planted
symlink AT the protected path; resolved catches a workspace symlink redirecting INTO it.

**P5. Dynamic where the code is dynamic.** The audit sink (`core.action_gateway.audit_path()`, env-selectable), the active config file (`utils.config.get_config_file_path()`, `CODEY_CONFIG_PATH`), `CODEY_STATE_DIR`, `Path.home()` and `PATH` are read **at call time**, never
cached at import. `CODE_DIR` is passed in by each caller from its own module global (file tools: `core.checkpoint.CODE_DIR`; `Filesystem`: `core.filesystem.CODE_DIR`; shell: `tools.shell_tools.CODE_DIR`), because the existing suites monkeypatch those module attributes (fact 16).

**P6. Classify the path the tool will actually write.** `classify_write_action` currently resolves the raw string against the process cwd while `Filesystem` joins it to its workspace (fact 7). The tools pass `Filesystem.workspace` (new keyword) so both agree; a test runs with cwd != workspace.

**P7. Do not widen `is_core_file`.** It also triggers `_require_checkpoint` (git commit plus backup). The new predicate is consulted only by `classify_write_action` and the shell scan; `CORE_PATTERNS` and `is_core_file` are unchanged (NEW-951 split).

## 3. The shared module `core/protected_paths.py` (new, Unit A)

Imports: stdlib only at module level (`os`, `fnmatch`, `dataclasses`, `pathlib`). No import of `core.action_gateway`, `core.filesystem`, `core.checkpoint`, `tools.*` at module level (avoids the `action_gateway -> filesystem` cycle and the
`core.checkpoint` import-time `mkdir`, `core/checkpoint.py:29`); those are imported lazily inside `build_context()` only.

### 3.1 API (names are suggestions; behavior is the contract)

```
TIER_DENY = "deny"; TIER_HIGH = "high"
@dataclass(frozen=True) class Hit: tier: str; rule: str          # rule is a stable id from section 4, used in messages and audit text
SYSTEM_BIN_DIRS = frozenset({...})                               # moved from shell_tools._SYSTEM_BIN_DIRS (:309), re-exported under the old name
CRED_HOME_ENTRIES, CRED_STATE_ENTRIES, CRED_STATE_PATTERNS, CRED_BASENAME_PATTERNS, CRED_PATH_ALIASES   # moved verbatim (shell_tools:1404-1435)
def canon(path: str) -> str            # == _cred_canon: normpath + fold CRED_PATH_ALIASES prefix. Behavior-preserving move.
def fold(path: str) -> str             # canon(path).casefold(); what the protected set compares
@dataclass(frozen=True) class Context: ...   # immutable snapshot, see 3.3
def build_context(*, code_dir, workspace_root, home=None, state_dir=None, audit=None, config_paths=None,
                  path_env=None, listdir=os.listdir, is_exec=<os.stat based>) -> Context
def first_hit(forms, ctx) -> Hit | None        # forms: absolute path strings (lexical, resolved); deny beats high EXCEPT the F3 precedence of 4.3a
def ancestor_hit(forms, ctx) -> Hit | None     # a form equal to, or a parent of, an exact entry / subtree root / PATH dir (for rm, mv, cp, ln, chmod)
def has_git_component(path: str, bases=()) -> bool
```
`build_context` defaults are read at call time (P5). Everything filesystem-touching in the module is behind the injected `listdir` and `is_exec` callables, so unit tests pass recording fakes and the module itself performs no
discovery beyond those two (and `resolve()` of the context's own entries, done once in `build_context`, with any error mapped to "entry kept in lexical form only"). Measured cost of resolving 52 entries (the expected count): about 1.5 ms per context build on this device, so building one per mutation or per `shell()` call is acceptable; the implementer must not cache a context across calls (P5).

### 3.2 `canon`, alias fold, casefold

`canon` is G15d's `_cred_canon` verbatim (`/data/user/0/` -> `/data/data/`; user 0 only, because only that alias was observed, fact 4). `fold` adds `.casefold()`. Entries are folded when the context is built; candidates are folded at match time.
Alias handling is symmetric: because both sides are folded, a workspace/CODE_DIR/`HOME` that was itself obtained in alias spelling (`os.getcwd()` does not collapse it) still compares equal. Tests cover alias spelling of the **candidate**, of the **home/state dir**, and of **cwd**.

### 3.3 The `.git` rule

`has_git_component(path, bases)`: after `fold()`, strip the longest entry of `bases` that is an ancestor of `path` (bases = workspace root and `CODE_DIR`), then test each remaining component: `component.rstrip(". ") == ".git"`.
If no base is an ancestor, all components are tested. Why relative to a base: a workspace that happens to live under a directory named `.git` must not deny every write, while `proj/sub/.git/hooks/x`, `<sibling repo>/.git/hooks/x` (absolute, outside both roots) and `proj/.GIT/config` all hit.
`rstrip(". ")` covers the FAT/exFAT-style trailing dot/space aliasing for free; Unicode-ignorable code points (HFS+ style) are a documented residual (9). Both surfaces call this one function; it replaces the first-component test at `core/filesystem.py:105`.

### 3.4 Lazy callables (the only discovery)

- `is_exec(path) -> bool`: `os.stat(path).st_mode & 0o111` (False on any error). Used only for direct children of **mixed** PATH directories (4.4).
- `shadow_names() -> frozenset[str]`: union of `listdir(d)` for every PATH directory and `SYSTEM_BIN_DIRS` entry other than the mixed directory being asked about, errors swallowed (fact 9: `/system/bin` raises `PermissionError`, so the set is incomplete by construction; residual 9).
  Computed **at most once per `Context`** and only when a candidate is a direct child of a mixed PATH directory (measured: 10.8 ms for `$PREFIX/bin`; a write elsewhere pays nothing).

## 4. Contents of the protected set (module data; one tuple per row; each carries a one-line why in a comment)

`$H` = `Path.home()` read at call time; `$S` = each of `utils.config.CODEY_STATE_DIR` and `$H/.codeyOS` (both always, as in G15d, so an overridden `CODEY_STATE_DIR` does not unprotect the default); `$C` = the caller's `CODE_DIR`.
"Subtree" = the path itself or any descendant. All entries are stored `fold()`ed and matched against both forms (P4).

### 4.1 DENY tier, non-repo targets

| rule id | entries | why (evidence) |
| --- | --- | --- |
| `git-component` | any path component equal to `.git` after `fold`+`rstrip(". ")`, measured below the workspace/CODE_DIR base (3.3) | `.git/config`/`hooks` execute at Git's next call without an exec bit (NEW-894); nested and sibling repos, A:G11-G13, B:FT07/FT08/CS-01; probe 0.1 item 1 (`proj/sub/.git/config` created) |
| `audit-sink` | file `core.action_gateway.audit_path()` resolved at call time, and `$S/action_gateway_audit.jsonl` | G15b-34: probe 0.1 item 1 truncated the ledger to 2 lines; the gateway itself appends with plain `open(..., "a")`, which is not a `Filesystem` path, so it is unaffected |
| `state-dir` | subtree `$S` | age key, `config.json`, `state.db`, `checkpoints/`, `notes.json`, sessions, tokens, `restoricon.db`; B:HM-05/08/12; no legitimate model write targets this directory (section 0 item 5) |
| `config-active` | files `utils.config.get_config_file_path()` and the `CODEY_CONFIG_PATH` value (both when set) | read live for tunnel token, `api_host`, `aigentik.dir` launcher, GCS bucket (G15b-26); data, not Codey code, so `--allow-self-mod` should not unlock it (Q1) |
| `home-startup` | files `$H/` `.bashrc .bash_profile .bash_login .profile .bash_logout .inputrc` (bash and sh are the installed shells, see the grounding paragraph below this table); defensive, shells not installed here: `.zshrc .zshenv .zprofile .zlogin .zlogout .vimrc .tmux.conf .nanorc`; subtree `$H/.config/fish` | executes at the operator's next shell; B:HM-01. `.bashrc` and `.bash_history` exist here; `.profile` etc. are creation-protection |
| `home-credential` | `CRED_HOME_ENTRIES` (G15d, lifted): subtrees `.ssh .gnupg .aws .kube .config/gh .config/gcloud`, files `.netrc .git-credentials .npmrc .pypirc .docker/config.json .config/git/credentials .bash_history .zsh_history` | write side of the credential set: `authorized_keys` (B:HM-03), registry/index rewrites (`.npmrc`, `.pypirc`) |
| `home-git` | file `$H/.gitconfig`, subtree `$H/.config/git` | `core.hooksPath`, aliases, `core.sshCommand` (A:G11-G13; B:HM-04) |
| `home-termux` | subtrees `$H/.termux` (boot scripts, `termux.properties`, shell override) and `$H/.shortcuts` | persistence (B:HM-02 wrote `.termux/boot/start.sh`); only `termux.properties` exists here, `boot/` does not (creation-protection) |
| `path-dedicated` | subtrees: `$H/bin`, `$H/.local/bin`, `$H/google-cloud-sdk/bin`, every `SYSTEM_BIN_DIRS` entry, and every absolute PATH entry whose basename is `bin` or `sbin` | Ish Q2; section 0 item 9; a planted executable here shadows a command in the operator's shell |
| `path-shadow` | direct children of **mixed** PATH dirs (4.4) that collide with an existing command name or are already executable | Ish Q2 for the repo root and `~/Codey-v4` |

Grounding of the shells row: `bash dash sh nano` exist in `$PREFIX/bin`; `zsh fish tmux vim nvim` do not (`ls`); of the `$H` startup names only `.bashrc` (+ `.bash_history`, `.bashrc.backup`) exist. The defensive names cost nothing; they are listed here so the reviewer can drop them.

### 4.2 Why the whole state dir and not a hand list

A hand list of state files (`age.key`, `config.json`, ...) goes stale (G15d needed `restoricon.db*`, `*.age` additions already). The state directory is Codey's own store; the model's legitimate writes go to the workspace, `CODEY.md`, notes (through `_note_save`, not `Filesystem`)
and the gateway ledger (plain `open`). Operator tools (`codeydOS config`, `setup_dr_key.py`, `backup_secrets.py`) write the state dir by plain IO and are unaffected (section 0 item 11, proven by the regression tests in 7.6).

### 4.3 HIGH tier, repository targets (Ish F3), plus the shell-only core mirror

| rule id | entries under `$C` | applies to |
| --- | --- | --- |
| `f3-launcher` | `main.py codey codeyOS codeydOS codey-start codey-stop codey-metrics` (the last one is **not on Ish's list**; it is a tracked bash launcher in the same class, section 0 item 10: Q4) | file tools + shell |
| `f3-script` | any file whose name ends `.sh` at any depth (covers `install.sh setup.sh setup_repo.sh lib/*.sh tools/setup_skills.sh` and future ones) and the subtree `lib/` (any suffix) | file tools + shell |
| `f3-config` | `config.json` at the repo root (gitignored, operator-local; the state-dir and active config files are DENY in 4.1) | file tools + shell |
| `f3-plugin-data` | every file under `ccos/plugins/` that is not `*.py` (`manifest.json`, `.md`, `.pyc`, anything). `*.py` there is already HIGH via `is_core_file` | file tools + shell |
| `core-py-mirror` | `*.py` under `core.checkpoint.CORE_CLASSIFICATION_ROOTS` (imported lazily in `build_context`, so there is one definition) | **shell scan only**, and only for file-mutator bases (6.2); file tools already get this from `is_core_file` |
| `bench-evaluator` | **empty tuple until Unit C**: subtree `bench/`, every suffix, every depth (G15f needs this and asks Ish as its Q1; it extends the `.py`-only scope recorded as Ish fork 1, 2026-10-17). Shipped as data in this module, never as a second mechanism, so the "one shared set" constraint holds | both |
| `d7-authority` | **empty tuple in Units A and B** (11, D-7) | both |
| candidates `cand-*` | **empty tuples** until Ish accepts (11, Q6) | both |

`f3-script` is structural (suffix at any depth) rather than a hand list on purpose: the register's own list (`setup*.sh`, `tools/setup_skills.sh`) would have missed `lib/` additions. A drift test (7.2) scans the real repo root, read-only, and asserts every
root-level file that starts with `#!` or has an exec bit is covered by `f3-launcher` or `f3-script`, so a future launcher cannot be forgotten.
`allow_self_modification` unlocks HIGH-tier writes exactly as it unlocks core `.py` writes today (Ish 2026-10-08) and never unlocks a DENY-tier entry (Q2).

### 4.3a Precedence (one explicit rule; found in advisor review because the first draft got it wrong)

A path matched by any `f3-*` row keeps its **HIGH** tier even when `path-shadow` or `config-active` would also match it. Reason, both verified: (a) the tracked launchers and root scripts are mode 755 (`ls -la`: `codey codey-metrics codey-start codey-stop codeyOS codeydOS install.sh setup.sh setup_repo.sh` are `-rwx------`), so `path-shadow`'s
`is_exec` test would otherwise turn every F3 launcher into DENY, silently overriding Ish's F3 decision ("HIGH write classification") and the `--allow-self-mod` rule of 4.3; (b) `utils.config.get_config_file_path()` returns `CODE_DIR/config.json` whenever `<state>/config.json` is absent (`utils/config.py:640-648`), so `config-active` would make the decided-HIGH root `config.json` DENY on a device
(or in the test suite, whose temp state dir has no config) without a state config and HIGH where one exists: a tier that depends on device state (the flake class of G15b-49). Mechanism: `first_hit` collects all matching rows; if any `f3-*` row matched, it drops hits whose rule is in `F3_OVERRIDES = {"path-shadow", "config-active"}`; every other DENY row
(`state-dir`, `git-component`, `audit-sink`, `home-*`, `path-dedicated`) still wins over HIGH. Making the launchers or the root `config.json` DENY is a reversal of F3 and is therefore asked as Q1(b), not done as a side effect. Required tests (7.1, 7.4): launchers (mode 755) and root `config.json` classify HIGH and are writable under `--allow-self-mod`; `$C/ls`
and a brand-new exec-bit direct child stay DENY; the root `config.json` outcome is identical with the state `config.json` present and absent.

### 4.4 PATH directories (Ish Q2)

Sources, read at call time: the fixed list (`$H/bin`, `$H/.local/bin`, `$H/google-cloud-sdk/bin`, `$C`, `$H/Codey-v4`, `SYSTEM_BIN_DIRS`) **union** the absolute entries of `os.environ["PATH"]`. A non-existent directory still counts (`~/Codey-v4` does not exist here and `mkdir` of it is
the plant). Relative or empty PATH entries are ignored (residual 9; resolving them against the agent cwd would make ordinary workspace files shadow-protected; this device has none, section 0 item 9).
- **Dedicated** bin directory (`path-dedicated`): the directory and everything below it are DENY.
- **Mixed** directory (`$C`, `$H/Codey-v4`, any other non-`bin` PATH entry): only **direct children** are examined, and a child is DENY iff its basename is in `shadow_names()` or `is_exec(child)`. Nested files and everything else in the directory are unaffected.
  Consequence stated plainly: with the repo root on PATH, a new direct child of the repo root named like any command on PATH (`test`, `install`, `patch`, `ls`, ...) or any already-executable file there is refused; ordinary names (`notes.txt`, `build`, `out`) are not.
- Because file-tool-created files have no exec bit (section 0 item 9), the realistic plants are `cp`/`ln`/`mv`/`chmod` through the shell scan and overwrites of existing executables through the file tools; both are covered.
- **Open question for Ish (Q3):** the repo root is on PATH only because `install.sh:455-462` appends it to the shell config (and `~/.bashrc:6` exports it); `install.sh:438` already supports symlinks into a bin directory. Replacing the PATH export by symlinks would make the repo root
  an ordinary directory and delete the `path-shadow` rule. That is an `install.sh` change (rule 11), so it is a decision, not part of this slice.

## 5. File-tool side (Unit A)

### 5.1 `core/filesystem.py`: one guard, five entry points

Add `Filesystem._validate_for_mutation(self, raw) -> Path` and use it in `write`, `restore`, `make_parent_dirs`, `patch` and `append` in place of the current `self._validate_path(...)` + `self._reject_git_metadata_mutation(...)` pair (`make_parent_dirs` also checks `path.parent`, as it does now).
It performs: (1) `resolved = self._validate_path(raw)` (unchanged workspace/CODE_DIR boundary); (2) `lexical = Path(os.path.normpath(self.workspace / raw))` (or `raw` when absolute): the pre-`resolve()` form, needed so a planted symlink AT a protected path is judged by its own name as well as by its target (P4);
(3) `_reject_git_metadata_mutation(resolved)` (see below) and (4) `ctx = build_context(code_dir=CODE_DIR, workspace_root=self.workspace)`; a DENY-tier `first_hit((lexical, resolved), ctx)` raises
`FilesystemAccessError(f"Access denied: {resolved} is a protected path ({hit.rule}) and cannot be modified by file tools.")`. HIGH-tier hits are NOT acted on here (classification is the caller's job, 5.2). The guard runs before `_require_checkpoint`, `mkdir` and `_snapshot`,
so a denied call has no side effect.
`_reject_git_metadata_mutation` keeps its name, its exact message (`is inside a Git metadata directory`) and its call sites, but its body becomes `has_git_component(path, (self.workspace, CODE_DIR))`. This is a deliberate behavior change: nested and case-variant `.git` are now denied, so
**`tests/test_filesystem_git_metadata.py::test_nested_repository_git_is_not_blocked` (:181) must be inverted** (declared flip, not an edit to make a test pass). Read paths (`read`, `exists`, `is_file`, `is_dir`, `list_dir`) are unchanged except for the optional 5.4.

### 5.2 `tools/file_tools.py`: classify the validated path, HIGH for every hit

`classify_write_action(path, *, workspace=None)`:
1. `target` = the path `Filesystem` would write: join a relative `path` to `workspace` (default `utils.config.WORKSPACE_ROOT`) and `resolve()`; malformed input (`TypeError`/`ValueError`/`OSError`, e.g. NUL) keeps the existing `ACT` fallback (the downstream `Filesystem` rejects it).
2. `is_core_file(target)` -> `HIGH_IMPACT` (unchanged, P7).
3. Otherwise `first_hit((lexical, target), build_context(code_dir=core.checkpoint.CODE_DIR, workspace_root=workspace))`: **any tier** -> `HIGH_IMPACT`. Defense in depth: a DENY-tier target is also labelled HIGH, so in confirm-less modes the gateway refuses it with an audited HIGH row before `Filesystem` is reached; in
   modes where a confirmation path exists, `Filesystem` raises and the gateway records `OUTCOME_FAILED`. Either way it is blocked and audited.
4. Any other exception while building the context -> `HIGH_IMPACT` (fail closed; the cost of a false HIGH is a refusal).
`tool_write_file`, `tool_append_file` (`tools/file_tools.py:293`, :327) and `tool_patch_file` (`tools/patch_tools.py:102`) pass `workspace=` the `Filesystem` instance's `.workspace`; `core/recovery.py:499` and `core/filehistory.py:105` already pass absolute validated paths and are unchanged.
`core/action_gateway.py` is **not** changed (its `gate_write`/`gate_append` trust the caller's authority; verified at :205-273 and :308-371). The register's file list named it only as the classification call site, which actually lives in `tools/file_tools.py`.

### 5.3 What `allow_self_modification` and the REPL get (stated so the ledger wording is exact)

- DENY tier: refused in **every** mode including the REPL and `--allow-self-mod --yolo` (Q1/Q2 defaults).
- HIGH tier (F3 files, `f3-plugin-data`, future D-7): refused in confirm-less modes without `--allow-self-mod`; allowed with `--allow-self-mod` (Ish 2026-10-08); **allowed unprompted in the REPL for new files and appends** (an existing-file overwrite still gets the ordinary `confirm_write` prompt) until G15j gives `confirm_available` a real callback (NEW-1027). The ledger must say exactly this; "F3 closed" is true for confirm-less modes only.
- The REPL human who wants `.bashrc` edited uses the shell tool (HIGH, real `ask_confirm` prompt with a warning, section 6) or edits it himself.

### 5.4 Optional read-side items (Q7; each independently skippable)

(a) `tool_patch_file` calls `get_filesystem(...)._validate_path(p)` right after resolving `p` and before `read_text` (`tools/patch_tools.py:28-40`), returning `[ERROR] <message>` on `FilesystemAccessError`. Today a failed patch echoes the whole file (0.1 item 3), including files outside the workspace. A successful patch outside the
workspace already fails later at the gateway, so only the echo changes. Recommend yes; it is G15b-38 / NEW-1031. Risk to check: existing `tests/test_patch_tools.py` patch files in tmp dirs that may sit outside the Filesystem workspace.
(b) `Filesystem.read` denies the credential literals (`home-credential`, `state-dir`; not `.env`-style basename patterns, which G15d scopes to existing files only and which G15b-39 covers) when the path resolves into them. Closes probe 0.1 item 3 (`read_file(".ssh/id_rsa")` returned the key). To avoid a second implementation, the nested `matches()` of
`_shell_command_targets_credentials` moves into the module as `credential_path_hit(forms, ctx)`; `test_shell_g15d_unit_a.py` unmodified is the equivalence evidence. This extends D-2 (decided for shell only) to the file tools, so it needs Ish's yes (Q7); estimate +0.2-0.3M.

## 6. Shell-argv side (Unit B)

### 6.1 Placement in `shell()` (`tools/shell_tools.py:1853-1873`)

After the credential block and before the shadow block:
```
protected_rule = None
if authority == ACT:                                     # READ is exempt below; HIGH is already refused/prompted
    protected_rule = _scan_protected_safely(command)     # builds cwd/home/ctx at call time; any exception -> "scan-error" (fail closed)
    if protected_rule is not None:
        authority = HIGH_IMPACT
```
and one more `warning(f"Command references a protected path ({protected_rule}): `{command}`")` line in the `confirm()` closure. `_daemon_shell` ends in `shell(command, yolo=True)` (`core/task_executor.py:566`), so the daemon is covered with no second implementation; only its comment block (`:34-45`) and `_daemon_shell` docstring gain a sentence.
`classify_shell_command` is **not** modified (P2). `_shell_command_targets_git_metadata` and `_shell_command_targets_credentials` are not modified either (the git scan's docstring residual list gets a "closed by the protected scan for non-exempt bases" note; both stay as reviewed, the three scans overlap harmlessly).

### 6.2 `_shell_command_targets_protected_path(command, *, cwd, home, ctx) -> str | None` (returns the first rule id, or None)

- Tokenization and candidate extraction: reuse G15d's `_path_candidates(command, cwd=, home=)` **unchanged** (token, text after first `=`, attached short operand, `~`/`$HOME`/`${HOME}` expanded from the passed `home`, relative joined to `cwd`, `(lexical, resolved)` pairs, `None` = NUL/resolve failure = fail closed). Note `_run_shell_command_structured` passes argv literally with no expansion
  (`subprocess.run(args)`, no `shell=True`, no `cwd=`; read), so expanding `~`/`$HOME` is a deliberate over-approximation shared with G15d.
- **Exempt bases** (return None): `_PROTECTED_SCAN_EXEMPT_BASES = frozenset(READ_COMMANDS) | {"echo", "cd", "cut", "tr", "sed", "termux-clipboard-get"}`. Why each is safe: `READ_COMMANDS` after G15d are read-only by construction (option tables for `sort uniq tree file`; no write option on the rest, G15d fact 3); `sed` is ACT only with `--sandbox` and no `-i`
  (G15d 3.3), so it cannot write; `echo`, `cd`, `cut`, `tr` have no write option and `shell=False` means `>` is a literal argument; `termux-clipboard-get` takes no path. Git basenames are exempt (already HIGH).
- **Rule application by role.** File mutators `_PROTECTED_MUTATOR_BASES = {cp, mv, ln, touch, mkdir, rm, rmdir, chmod, dd}`: every rule, including the runner-exempt rows (so `cp x core/agent.py` is HIGH). Every other non-exempt base (runners such as `python python3 pytest node npm pip pip3 bash make` and the 19 build tools; `termux-open`;
  `termux-clipboard-set`): every rule **except** the rows tagged `runner_exempt` (`core-py-mirror`, `bench-evaluator`, `d7-authority`; the F3 rows are deliberately NOT tagged), because `python3 tools/some_script.py` / `pytest tests/...` executing a core `.py` is the registered script-file ceiling (G15b-19) and flagging it would make normal development HIGH. Executing an F3 file (`python3 main.py`, `bash install.sh`, `bash codeyOS`) IS flagged on purpose (6.6).
- **Ancestor rule** for `_PROTECTED_ANCESTOR_BASES = {cp, mv, ln, rm, rmdir, chmod}`: an operand form that is equal to, or a parent of, any exact entry, subtree root, F3 launcher or PATH directory is a hit (`ancestor_hit`). Closes `rm -rf ~`, `mv ~/.codeyOS elsewhere`, `cp -r payload ~`, `ln -s x ~`, `cp -r payload ~/.config`
  (the destination operand is the parent of `.config/git`). Only entries that are enumerable (exact files, subtree roots, directories) are ancestor-checked; the dynamic rules (`.git` component, `*.sh` anywhere, `core-py-mirror`) are not (residual 9: `rm -rf proj` containing a nested `.git`).
- Lexical and resolved forms are both checked (P4), `fold`ed. Candidate list includes every token after argv[0], with no positional parsing (accepted false positives, section 8).

### 6.3 Drift guards (so the exempt list cannot silently rot)

A test iterates `ALLOWED_COMMANDS | DANGEROUS_COMMANDS | the 19 build tools` and asserts each base is in exactly one of {exempt, mutator, runner/other}. A test monkeypatches a new member into `ALLOWED_COMMANDS` and asserts it is **scanned** (default-scan, not default-exempt). A test pins `_PROTECTED_SCAN_EXEMPT_BASES` exactly
(the node-table precedent), so widening it is a deliberate, reviewed edit.

### 6.4 Daemon, stated exactly (section 0 item 12)

The daemon does not admit `cp mv rm ln touch mkdir chmod dd`; for it the scan matters only for script operands. Required daemon end-to-end rows (through the real `_daemon_shell` with a recording runner): `python3 main.py` and `python3 install.sh` are refused with an audited `shell_tools.shell` HIGH row and the runner is not called;
`python3 tests/x.py`, `pytest tests`, `ls`, `cat <F3 file>` are unchanged. Everything else the scan guards is the interactive/`--yolo`/`--fix`/`--tdd`/bench/CCOS shell, which has the full ALLOWED set.

### 6.5 `.git`, PATH and aliases on the shell side

`.git`: `has_git_component` on both forms for every non-exempt base, with no root limit; this closes A:G11-G13 and the `~/.gitconfig` / `~/.config/git/config` forms (those are also `home-git` entries). PATH: the `path-dedicated` and `path-shadow` rules (4.4). Aliases: both candidate forms and every context entry are `fold()`ed, so
`/data/user/0/...` spellings hit (probe 0.1 item 2 showed the alias spelling of `.bashrc` was ACT at HEAD). `ln -s /usr/bin/git ls` followed by a relative `./ls`: the symlink creation is `ln` with operand `ls` = a direct child of cwd; if cwd is a mixed PATH dir and `ls` is a shadow name it is DENY/HIGH, otherwise the existing D-3/shadow
checks still stop the later `./ls push`.

### 6.6 Side effect to record without claiming closure (G15b-22 / G15b-21)

Because executing an F3 file as a runner operand is now HIGH, `python3 main.py --yolo --allow-self-mod`, `bash codeyOS --yolo ...` and `bash setup_repo.sh` (examples in G15b-21/22) are refused in confirm-less modes when the F3 path appears literally in argv. G15b-22 (accepted residual, Ish D-1 pending) is therefore **narrowed, not closed**: a script that execs `main.py` internally, or a
`PATH`-resolved `codeyOS` (already HIGH via the G15d shadow check) is unchanged. The register must say "narrowed".

## 7. Tests (recording fakes and disposable dirs only; no real dangerous command, no model, no network)

Every new test file sets, via `monkeypatch`, an **absolute disposable** `HOME`, `utils.config.CODEY_STATE_DIR` (module attribute; the env var alone is read once at import, G15d 3.2b), `CODEY_ACTION_GATEWAY_AUDIT`, and the `CODE_DIR` module attributes the code under test reads (`core.filesystem.CODE_DIR`, `core.checkpoint.CODE_DIR`,
`tools.shell_tools.CODE_DIR`); proxy variables unset. The implementer runs with `python3 -I`, `env -u HTTP_PROXY -u HTTPS_PROXY`, and never touches `~/.codeyOS`.

**Stated cwd precondition (carried from the register).** File-tool reachability of every home/state/PATH/F3 item requires the protected path to lie inside the workspace (or `CODE_DIR` with self-mod). The tests therefore build a fake home that IS the workspace (`Filesystem(workspace=fake_home)`, `monkeypatch.chdir(fake_home)`), and each file-tool test file
carries that sentence in its docstring. Shell tests carry no such precondition (absolute paths) and use `monkeypatch.chdir` only where a relative operand is the point. Nobody has established how Ish actually launches the daemon/REPL (consolidated section 0); the ledger wording must say "reachable given repo or `$HOME` in the workspace".

### 7.1 `tests/test_protected_paths.py` (pure module, recording fakes for `listdir`/`is_exec`)
`canon`/`fold` (alias both directions, casefold, `normpath` of `..`), `has_git_component` table (hits: `.git/config`, `a/b/.git/hooks/x`, `.GIT/x`, `x/.git /y`, `x/.git./y`, absolute sibling repo path; non-hits: `.github/x`, `.gitignore`, `foo.git.txt`, `a.git/b`, and a workspace that itself lives under a `.git` directory with a benign file below it),
every row of 4.1 and 4.3 with a positive and a neighbouring negative control (`~/.ssh2/x`, `~/.bashrc.backup`, `$C/config.json.example`, `$C/mainx.py`, `$C/ccos/plugins/a/x.py` is `core` not `f3-plugin-data`), deny-beats-high plus the F3 precedence of 4.3a (mode-755 launcher and root `config.json` stay HIGH with the state config present and absent; `$C/ls` and a new exec-bit child stay DENY), `audit-sink` with `CODEY_ACTION_GATEWAY_AUDIT` **set and unset** (via `monkeypatch.delenv`) and the default path guarded in both cases,
`config-active` with `CODEY_CONFIG_PATH` set and unset, dedicated vs mixed PATH dirs (PATH built from `monkeypatch.setenv`, relative and empty entries ignored, non-existent `~/Codey-v4` still a hit), `shadow_names()` called **0 times** for a path that is not a direct child of a mixed dir and **once** per context otherwise,
`is_exec` honoured, ancestor rows (`~`, `~/.config`, `$C`, `..` of home), empty `d7-authority` and `cand-*` tuples produce no hit.

### 7.2 `tests/test_protected_paths_repo_drift.py` (read-only walk of the real repo)
Every root-level regular file that starts with `#!` or has an exec bit is covered by `f3-launcher` or `f3-script`; every file under `lib/` is covered; every non-`.py` file under `ccos/plugins/` (including untracked `__pycache__/*.pyc`) is covered by `f3-plugin-data`; `core-py-mirror` agrees with `core.checkpoint.is_core_file` on a corpus of paths. No writes.

### 7.3 `tests/test_filesystem_protected_paths.py`
For each 4.1 entry and each of `write`, `append`, `patch`, `restore`, `make_parent_dirs`: `FilesystemAccessError` naming the rule, target content/existence unchanged, `_require_checkpoint`/`mkdir`/`_snapshot` not called (recording fakes). Controls: `proj/notes.txt`, `CODEY.md`, `.codeyignore`, `.github/x`, `.gitignore` succeed; F3 entries are NOT denied here (HIGH is classification, 5.2).
Alias: workspace given in `/data/user/0/...` spelling with a canonical-spelling target and the reverse. Symlinks: workspace symlink -> `~/.bashrc` (resolved form), and a symlink planted AT `~/.bashrc` pointing to a harmless file (lexical form). `.git`: nested (`proj/sub/.git/config`, flips the old test), case variant (`proj/.GIT/config`), sibling repo outside both roots via `CODE_DIR`-relative absolute path.
Audit ledger: seed 9 rows, `write`/`append`/`patch` denied, bytes unchanged, **and** the gateway can still append its own row afterwards (guard does not break the sink). Operator regression (section 0 item 11): `DaemonConfig(config_file=<state>/config.json).save()` and `.create_default_config()` succeed while `Filesystem.write` of the same path is denied; an AST scan asserts `core/daemon_config.py`, `core/service_lifecycle.py`,
`core/service_actions.py`, `core/setup_dr_key.py`, `core/backup_secrets.py` import none of `core.protected_paths`, `core.filesystem`, `tools.file_tools`, `tools.shell_tools`. Existing `tests/test_undo_action_boundaries.py`, `test_init_ignore_action_boundaries.py`, `test_execution_recovery_gateway.py` stay green unmodified.

### 7.4 `tests/test_file_tools_protected_classification.py`
`classify_write_action`: HIGH for each F3/`f3-plugin-data` entry and (defense in depth) each DENY entry, ACT for controls, malformed path (NUL) stays ACT, context-build failure -> HIGH (monkeypatched to raise), **cwd != workspace** (`monkeypatch.chdir(elsewhere)`, `workspace=` the fake home) agrees with `Filesystem`.
`is_core_file` and `CORE_PATTERNS` unchanged; writing `main.py` with `allow_self_modification=True` does **not** call `_require_checkpoint` (P7). End-to-end through the real `tool_write_file`/`tool_append_file`/`tool_patch_file`, `AGENT_CONFIG` patched, ledger read back:
(i) confirm-less, no self-mod: F3 -> `[BLOCKED]` + one `refused` audit row, DENY -> `[BLOCKED]`; (ii) confirm-less + `allow_self_modification=True`: F3 write allowed, DENY still `[ERROR] Access denied` + a `failed` row; (iii) REPL (`confirm_write=True`): an F3 **new-file write or append** is allowed with no prompt (pinned with a comment naming NEW-1027/G15j so G15j flips it knowingly; overwriting an EXISTING file still hits the regular `confirm_write` prompt in `tool_write_file`, so that test fakes `ask_confirm` and records that it was asked), DENY refused.

### 7.5 `tests/test_shell_g15e_protected_scan.py`
Pure rows of `_shell_command_targets_protected_path(cmd, cwd=, home=, ctx=)`: the cross product {`cp mv ln touch mkdir rm rmdir chmod dd`} x {one target per 4.1/4.3 rule, canonical and alias spelling} -> a hit (0 misses); runners `python3 main.py`, `bash install.sh`, `bash codeyOS`, `python3 ccos/plugins/x/manifest.json` -> hit, `python3 core/agent.py`, `pytest tests`, `python3 tools/wp21_census.py` -> no hit;
exempt `cat main.py`, `sed --sandbox -n p main.py`, `echo ~/.bashrc`, `grep -r x ~/Codey-OS`, `ls ~/bin` -> no hit; ancestor rows (`rm -rf ~`, `cp -r payload ~`, `mv x ..` from `$H`, `cp x .` from `$C`) hit and the same operands for `ls`/`pytest .` do not; `.git` rows including sibling repo hooks and `.GIT`;
shadow rows with fake `listdir`; NUL byte and `resolve()` failure -> fail closed; scan exception -> rule `"scan-error"`.
End to end through the real `shell()` with `_run_shell_command_structured` replaced by a recorder: ACT->HIGH refused in `confirm_shell=False` (recorder never called, one audit row with action `shell_tools.shell`), prompted with the warning text in the REPL with a fake `ask_confirm` (declined -> not run; accepted -> run once); through `_daemon_shell` the rows of 6.4.
Invariants: `test_classifier_does_not_discover_or_parse_children` unmodified and green; a new test patches every public function of `core.protected_paths`, `Path.resolve`, `Path.exists` and `os.listdir` to raise (not `os.stat`, which pytest itself needs) and shows `classify_shell_command` results over a 60-command corpus equal the pre-patch baseline (P2); the drift tests of 6.3; `tests/test_shell_g15d_unit_a.py` and `..._b.py` pass **unmodified** (lift equivalence).

### 7.6 Mutation pass by the implementer (G15c precedent; each mutation must turn at least one test red, results listed in the report)
Drop `fold` casefold; drop alias fold; compare only the resolved form; compare only the lexical form; drop deny-over-high precedence; drop `rstrip(". ")`; drop base stripping in `has_git_component`; cache `audit_path()` at import; drop the `CODEY_CONFIG_PATH` entry; drop `home-git`, `home-termux`, `lib/`, the `.sh` rule, `f3-plugin-data`;
drop the ancestor rule; apply `core-py-mirror` to runners; make unknown bases exempt; drop the `scan-error` fail-closed path; skip the `restore` guard; skip the `make_parent_dirs` parent check; run the guard after `_snapshot`; classify with the process cwd instead of `workspace`; widen `is_core_file`; list every `shadow_names()` call eagerly.

### 7.7 Declared test flips (intended behavior changes, not edits to make a test pass; grep of `tests/` found no other pin of these classes except a classifier-level `ln -s /usr/bin/git ls` == ACT at `test_shell_g15d_unit_a.py:337`, which stays true because the scan lives in `shell()`)
- `tests/test_filesystem_git_metadata.py::test_nested_repository_git_is_not_blocked` (:181): inverted (nested `.git` is now denied); renamed accordingly.
- `tests/test_core_file_classification_ext.py::test_non_py_and_non_ext_paths_unaffected`: rows `ccos/plugins/coding/agent/manifest.json`, `ccos/plugins/README.md`, `ccos/plugins/a/run.sh`, `ccos/plugins/a/x.pyc` move to a HIGH parameter set (`is_core_file` stays False, `classify_write_action` becomes HIGH). The `bench/*` rows (`bench/scorecard.md`, `bench/suite.lock`, `bench/scorecard_history.jsonl`, `bench/tasks/t01/task.yaml`; `bench/scorecard_manual.json` to be added) stay ACT in Units A and B and flip to HIGH **in Unit C, together with the `bench-evaluator` data row, only if Ish accepts G15f's Q1** (see 10a). `ccos/core/plugin_manager.py` stays ACT until Unit C and only if D-7 is accepted.
- `tests/test_core_file_classification.py::test_non_core_nested_path_unaffected`: rows `main.py` and `tools/x/y.sh` -> HIGH.
- The implementer must run the whole `tests/` tree once in chunks under 100 s to find any unexpected pin, and report each found with the same declaration.
Suites to run: the files above, `tests/test_file_tools.py`, `tests/test_patch_tools.py`, `tests/test_filesystem_workspace_root_live.py`, the 12 shell/daemon/recovery files of the G15c list, `tests/test_shell_g15d_unit_a.py`, `..._b.py`, then the remaining tree. Known unrelated failures are listed in `docs/WP2_1_HANDOFF_2026-10-23.md` section 6 and NEW-1043; `tests/test_loader_v2_load_mode.py` takes about 90 s alone.

## 8. Accepted false positives (cost of a generic scan; adds a refusal or a prompt, never an execution)

- File tools: a new direct child of the repo root named like any command on PATH (`test`, `install`, `patch`, ...) or any executable already there; any write under `~/bin`, `~/.local/bin`, `~/google-cloud-sdk/bin`, `$PREFIX/bin` (Ish's own scripts there are edited with his editor, not through the agent); any path with a `.git` component (including a deliberate nested-repo fixture
  written via `write_file`; use `git init` through the shell tool); every file under `lib/`, every `*.sh`, every non-`.py` plugin file; REPL requests to edit `.bashrc`/`.gitconfig`/`.ssh/config` through the file tools (use the shell tool, which prompts).
- Shell: `cp main.py /tmp/bak`, `mv`, `ln -s ~/.bashrc x`, `chmod +x tools/new.sh`, `touch lib/x`, `python3 main.py --help`, `bash install.sh`, `pytest --ignore=.git`, `rm -rf .` and `cp x .` / `mv x ..` when cwd is the repo root or `$HOME` (ancestor rule), `cp -r ~/Codey-OS /tmp/bak`, a project file literally named like a command in the repo root.
  Reading is never affected (`cat`, `grep`, `ls`, `head`, `tail`, `diff`, `wc`, `file`, `sort`, `uniq`, `tree`, `sed --sandbox`, `echo`).

## 9. Residuals (named, not claimed covered; each belongs in the ledger entry that closes the slice)

1. Script-file ceiling (G15b-19): `python3 x.py`, `bash x.sh`, `make`, compilers, package build scripts write anything the uid can. The scan sees literal argv paths only; every rule here is defense against direct and naive forms plus truthful audit, not a sandbox (consolidated section 1).
2. `pip install`/`npm -g`/`pkg` write into `$PREFIX/bin` and site-packages without a path operand; the scan cannot see it (G15b-13 residual).
3. TOCTOU: the guard checks at call time; a concurrent child that swaps a symlink between check and write wins.
4. Hard links: `os.link` is unavailable on this device (B:HL-01 INCONCLUSIVE), so NEW-872 cannot be exercised or fixed here.
5. PATH: relative/empty entries ignored; `/system/bin` cannot be listed (`PermissionError`), so `shadow_names()` is incomplete by construction; the operator's login-shell PATH can differ from the agent process PATH (mitigated by the static list unioned with the process PATH).
6. `.git` variants: `.gitmodules`, `.gitattributes`, `.gitignore` and Unicode-ignorable code points (HFS+-style) are not matched; case-insensitive mounts are handled only by casefold. Because `has_git_component` strips the workspace/CODE_DIR base, a workspace that itself sits inside a `.git` directory can write hooks beside itself (by design, to avoid denying every write for such a workspace; nobody launches Codey from inside `.git`).
7. Dynamic rules (`.git` component, `*.sh` anywhere, `core-py-mirror`) are not ancestor-checked: `rm -rf proj` containing a nested repo is not a hit.
8. Sibling development repos (`~/Codey-Aigentik`, `~/restoricon`, `~/Codey-Estimator-reference`) are not protected: the agent legitimately edits them, and protecting `restoricon_core/**` would block Track B (NEW-1016 friction). Only the D-7 authority files, if accepted, are named.
9. HIGH tier is a real block only in confirm-less modes without `--allow-self-mod`; in the REPL it proceeds unprompted until G15j (NEW-1027). `--allow-self-mod` unlocks the HIGH tier by design (Ish 2026-10-08).
10. The audit sink still swallows `OSError` by design, and a hash chain is queue-level (G15b-34 optional).
11. Reachability wording: file-tool items need the protected path inside the workspace; the operator's launch cwd is not established.
12. G15b-22 is narrowed, not closed (6.6); G15b-21 loses only its `bash setup_repo.sh` example (G15i keeps the rest).

## 10. Units, exact files, order, cost

Line numbers are HEAD `9a61e94`.

| unit | scope | files | tests | cost (order of magnitude, not measured) |
| --- | --- | --- | --- | --- |
| **A** | shared module, file-tool side, lift of G15d data | NEW `core/protected_paths.py`; `core/filesystem.py` (`_validate_for_mutation`, `_reject_git_metadata_mutation` body :81-109, the five entry points :203, :254, :275, :294, :354); `tools/file_tools.py` (`classify_write_action` :89-120 + callers :293, :327); `tools/patch_tools.py` (:102 `workspace=`; optional 5.4a ordering :28-40); `tools/shell_tools.py` **only** to delete the moved constants (`_SYSTEM_BIN_DIRS` :309, `_CRED_*` :1404-1435, `_cred_canon` :1438) and re-export them under the old names | 7.1, 7.2, 7.3, 7.4, flips of 7.7; `test_shell_g15d_unit_a.py`/`_b.py` unmodified and green | 1.0-1.5M (+0.2-0.3M if Q7(b)) |
| **B** | shell argv scan | `tools/shell_tools.py` (new `_shell_command_targets_protected_path`, `_scan_protected_safely`, exempt/mutator/ancestor constants, `shell()` block after :1867, `confirm()` warning, docstring note on the git scan); `core/task_executor.py` comment only (:34-45, `_daemon_shell` docstring); depends on A | 7.5, daemon rows, drift tests, mutation pass | 0.8-1.2M |
| **C** | Ish-gated data | `core/protected_paths.py` tuples only (`d7-authority`, `cand-*`), pinned-test flips for whatever Ish accepts | extra rows in 7.1/7.4/7.5, flip of `ccos/core/plugin_manager.py` pin if D-7 accepted | 0.3-0.5M, blocked on Q5/Q6 |

**Unit A internal order (each step leaves the suite green, so a usage-limit cut leaves a coherent state):** (A1) create `core/protected_paths.py` with `canon`/`fold`/`SYSTEM_BIN_DIRS`/`CRED_*` moved and re-exported from `tools/shell_tools.py`; `test_shell_g15d_unit_a.py` and `_b.py` pass unmodified; module unit tests 7.1/7.2 for the pure parts.
(A2) the data rows (4.1, 4.3, 4.3a, 4.4) and `first_hit`/`ancestor_hit`/`build_context`, then `Filesystem._validate_for_mutation` + the `.git` any-component change + the nested-`.git` flip + 7.3 (this step alone closes the audit-ledger truncation, persistence-file and nested-`.git` file-tool items). (A3) `classify_write_action(workspace=)` + callers + the classification flips + 7.4. (A4) optional 5.4 items.

Total 2.1-3.2M, above the consolidated envelope for G15e (1.5-2.5M) because of the deny tier, the shell scan and the test flips; say so rather than hide it. Order: **A, then B, then C.** A first so the must-close audit-ledger and persistence items (G15b-33/34/35 via file tools) land even if a usage limit cuts the round; B depends on A's module API (frozen after A's reviewer pass); C is data after Ish answers.
Implementer instructions that must be repeated verbatim in each dispatch: no `git stash`, `reset`, `checkout`, `clean`, `add -A` (even inside background commands); stage exact paths; write results to disk incrementally; absolute disposable `HOME`, `CODEY_STATE_DIR`, `CODEY_ACTION_GATEWAY_AUDIT` under `/data/data/com.termux/files/usr/tmp/<name>`; proxy variables unset; `python3 -I`; no model load; use `/data/data/com.termux/files/usr/bin/grep` (the `grep`/`find` aliases are broken).

### 10a. Coordination with the concurrent G15f spec (`docs/wp2_1_g15f_spec.md`, uncommitted, written by another session; read, not edited)

`git status` at the time of writing shows uncommitted `bench/agents.py`, `bench/verify.py`, `tests/test_bench_integrity_grader.py`, `docs/wp2_1_g15f_spec.md` that are not mine. Overlaps, and the resolution proposed here:
- **Shared function and test file.** G15f's section 5 asks the shared set for `bench/**` (every suffix, every depth) at HIGH and lists the four `bench/*` rows plus `bench/scorecard_manual.json` as flips "in G15e's diff". This spec ships that as the `bench-evaluator` data row in `core/protected_paths.py` (one mechanism, not two) and makes the flips part of Unit C, gated on G15f's Q1 (extends Ish's fork 1; recommended yes by both specs).
  Two slices must not both edit `classify_write_action` or `tests/test_core_file_classification_ext.py`: **G15e owns both**; G15f edits neither. G15f's own pin test (`tests/test_bench_integrity_classification.py`) is its Unit B and passes only after G15e Unit C lands.
- **Order (matches G15f's own Q6 recommendation):** G15f Unit A (independent: `bench/verify.py`, `bench/agents.py`) any time -> G15e A -> G15e B -> G15e C (including `bench-evaluator`) -> G15f Unit B (lock/relock; its pin test is then a real test, not `xfail`). If Ish wants G15f B first, G15f ships its pin `xfail(strict=True, reason="G15e")` and the coordinator flips it in the G15e C commit.
- **Runner exemption.** `bench-evaluator` is tagged `runner_exempt` (6.2): `python3 bench/...` as a runner operand is the script-file ceiling, not a write; mutator bases (`cp`, `ln -sf`, `touch`, `mkdir`, ...) are HIGH.
- **Ledger ids.** G15f's spec tentatively takes NEW-1045..1047. To avoid the collision CLAUDE.md warns about, this spec's new entries are numbered NEW-1048..1051 and are **provisional**: the coordinator re-reads the `NEW_ISSUES.md` tail and runs `git status --short` immediately before writing and allocates sequentially in landing order.

## 11. Pending decisions and genuine questions for Ish (defaults are what the implementer builds unless told otherwise)

**Not decided, specified as separable data (do not record as decided):**
- **D-7 (root set for non-root authority files).** Recommendation: `ccos/core/**` and `restoricon_core/authority*.py` yes; `telemetry/store.py`, `pipeline/run.py`, `codey_estimator/__init__.py` queue. Design: a module tuple `D7_HIGH_ENTRIES` that is **empty in Units A and B**, filled in Unit C; HIGH tier (so `--allow-self-mod` still unlocks); limited to `authority*.py` inside `restoricon_core/` so the rest of Track B stays writable (NEW-1016 friction). Probe 0.1 item 1 showed `ccos/core/plugin_manager.py` and `restoricon_core/authority.py` are ACT-writable today. No env knob (Ish's dashboard-single-surface rule); flipping is a code edit with a pinned test.
- **D-8 (HIGH-by-ambiguity ratings).** No code depends on it. G15e touches G15b-07, 28, 35: their ledger severity labels stay "HIGH (amb), pending D-8". The recommended keep-HIGH for 07 and 35 matches what is built.

**Questions (each has a default; only Q1, Q3 and Q5/Q6 change what ships):**
1. **Q1, DENY tier.** (a) Default yes: non-repo targets (audit sink, state dir, active config files, `$HOME` startup and credential files, `.git` components, PATH directories) are refused by `Filesystem` in every mode with no flag unlocking them. Alternative: classify them HIGH only (then `--allow-self-mod --yolo` writes `~/.ssh` and the ledger, and the REPL writes new files/appends to them unprompted: fact 8). (b) Optional, a reversal of F3 if taken: promote the launchers and repo-root `config.json` from HIGH (as decided, and as built per 4.3a) to DENY. Default no.
2. **Q2, scope of `--allow-self-mod`.** Default: it unlocks only the HIGH tier (core `.py` today, plus F3/D-7), never the DENY tier. This keeps Ish's 2026-10-08 decision about self-modification of Codey code from silently widening to `$HOME` and credentials.
3. **Q3, repo root on PATH.** Default: implement the `path-shadow` rule as decided (friction in 4.4). Alternative worth a decision: stop adding the repo root to PATH (`install.sh:455-462`, `~/.bashrc:6`; `install.sh:438` already knows symlinks into a bin directory). That is an `install.sh` change (rule 11) and would remove the friction and the rule.
4. **Q4, launcher list.** Default yes: add `codey-metrics` (tracked bash launcher, same class) to `f3-launcher`.
5. **Q5, D-7 acceptance** as above (Unit C).
6. **Q6, candidate additions found by this pass (existence verified, exploitation not exercised), Unit C if accepted; recommendation yes to C-1 and C-2, yes to C-3 with the peer-config subset:** C-1 `$PREFIX/etc/**` (`bash.bashrc`, `profile`, `profile.d/*`); C-2 `*.pth`, `sitecustomize.py`, `usercustomize.py` inside any `site-packages`/`dist-packages` directory (system site, `~/.local/lib/python3.14/site-packages`, venvs);
   C-3 peer-agent config and sessions: `$H/.claude`, `$H/.claude.json`, `$H/.qwen`, `$H/.codex`, `$H/.gemini`, `$H/.config/opencode`, `$H/.config/mimocode`, `$C/.claude`, `$C/.qwen`, `$H/.codey_sessions`.
7. **Q7, read side.** (a) `patch_file` validates before reading (G15b-38; recommend yes, pure bug); (b) `Filesystem.read` denies the credential literals (recommend yes, it extends D-2 decided for shell only).
8. **Q9, `bench/**` (G15f's Q1).** Default yes: `bench/**` every suffix HIGH via the `bench-evaluator` row, Unit C. The answer is G15f's; recorded here only because the data lives in this module.
9. **Q8, friction acknowledgement.** Dedicated bin directories are not writable through the file tools even in the REPL; the REPL human uses the shell tool (HIGH prompt) or his editor.

## 12. Reviewer, live verification, process-lifecycle stance

- **code-reviewer: mandatory** for A and B (security classification and enforcement; CLAUDE.md names security/RBAC). Reviewer must derive facts from the artifact (rule 12): re-run the probes of 0.1 against the finished code in a disposable tree, and re-run the 7.6 mutations.
- **Rule 4 is NOT triggered:** no daemon start/stop, PID file, kill logic, lock, IPC or API-binding code is changed. `core/task_executor.py` gets comment text only. Say so in the dispatch so the reviewer does not hunt for it, but the reviewer should still confirm `_daemon_shell`'s code path is byte-identical (diff).
- **Live verification: not required** for code-complete/reviewer-approved; no model is loaded and `free -h` is not needed. Evidence tier at close: "code complete, code-reviewer-approved (once approved), NOT live-verified". A real-REPL check would need a model and is not proposed. The first real exposure of the false positives in section 8 is Ish's own sessions; the PROJECT_LOG entry should list them.

## 13. Proposed ledger entries (for the coordinator; ids to be re-checked against the `NEW_ISSUES.md` tail at write time, last verified id NEW-1044; NEW-1045..1047 are tentatively claimed by the uncommitted G15f spec, hence the provisional numbering below)

New:
- **NEW-1048 (provisional)** CONFIRMED (probe 0.1 item 3), HIGH (amb, same rating as G15b-10): `tool_read_file` returns credential files (`.ssh/id_rsa`) when the workspace contains them; D-2 option (b) covered only the shell. Status OPEN; fixed by Q7(b) if accepted. Overlap NEW-1020, NEW-1031.
- **NEW-1049 (provisional)** CONFIRMED existence, exploitation not exercised, HIGH (amb): unlisted startup/exec vectors writable by the agent uid: `$PREFIX/etc/{bash.bashrc,profile,profile.d/*}`, system and user `site-packages` `*.pth`/`sitecustomize`/`usercustomize` (user site exists here), peer-agent config (`~/.claude*`, `~/.qwen`, `~/.codex`, `~/.gemini`, `~/.config/{opencode,mimocode}`), `~/.codey_sessions`. Status OPEN, NEEDS-ISH-POLICY (Q6).
- **NEW-1050 (provisional)** CONFIRMED (code/config read), MEDIUM: `install.sh:455-462` and `~/.bashrc` put the repo root (and a non-existent `~/Codey-v4`) on PATH, so the repo root is an executable-shadow surface and any write protection for it is permanently friction-bearing; decision Q3. Overlap NEW-1037.
- **NEW-1051 (provisional)** reserved for the G15e accepted residuals and false positives (sections 8 and 9), mirroring NEW-1044 for G15d; write it at close.
Updates (status wording must keep the three tiers separate): NEW-1022 (G15b-07/08: file-tool and shell write routes via the shared set; sed/sort/awk part was already G15d); NEW-1024 (G15b-26, 27, 28 per D-7, 25 classification part only; the non-reversing G15g part untouched); NEW-1026 (G15b-33, 34, 35); NEW-1031 (G15b-38: UNSUPPORTED -> CONFIRMED with retained evidence, rule-6 correction; closed by Q7(a) if accepted);
NEW-1037 (PATH-shadow write side closed except residuals 9.2, 9.5; G15b-09 may move from "narrowed" to CLOSED only if Ish accepts that residual 9.2 is the script/package ceiling); NEW-1039 (alias fold now in the shared set on both surfaces); NEW-1027 (note: HIGH tier still unprompted in REPL; DENY tier is the protection there). Consolidated register section 10 gets a "status after G15e" block; blueprint WP2.1 status note and `PROJECT_LOG.md` top entry
(with the real test counts, the mutation list and the declared flips) by the coordinator after reviewer approval. No `CODEY_MASTER_PLAN.md` Appendix A line (Track A).

## 14. Comments to add in the touched code (project item 5; 2-4 sentences each, factual, the non-obvious why)

`core/protected_paths.py` module docstring (two tiers and why, both forms, no-discovery contract, call-time reads), `fold`/`canon` (device alias), `has_git_component` (relative to base, `rstrip`), `build_context` (what is read at call time and why `CODE_DIR` is passed in), each data tuple (one line of why per row, evidence ids), `shadow_names` (lazy, incomplete by construction);
`Filesystem._validate_for_mutation` and the changed `_reject_git_metadata_mutation` docstring (the nested-repo scope caveat from NEW-894 is now closed; read paths unchanged); `classify_write_action` docstring (tier-agnostic HIGH, validated-path basis, why `is_core_file` is not widened); `_shell_command_targets_protected_path` and its constants (why each exempt base is safe, mutator vs runner, ancestor rule, G15b-22 side effect);
the `shell()` block comment; the `_shell_command_targets_git_metadata` docstring residual list (what the protected scan now closes); the `core/task_executor.py` comment block and `_daemon_shell` docstring (daemon admits no file mutators; scan covers script operands).
