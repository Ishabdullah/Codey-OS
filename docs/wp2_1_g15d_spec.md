# WP2.1 slice G15d "classifier tail": technical specification

Date: 2026-10-23. Author: project-architect. Base: committed HEAD `e167e0c` (G15c default-deny classifier).
Status: **SPEC ONLY. No source or test file was edited.** Nothing here is implemented, reviewed or verified.
Decisions applied (Ish, 2026-10-23, recorded in `docs/wp2_1_g15b_consolidated.md` section 7): D-2 option (b), D-3, D-4.
F3 is decided but belongs to slice G15e (interface note in section 6).

Sections: 0 grounding | 1 findings covered | 2 cross-cutting rules | 3 Unit 1 | 4 Unit 2 | 5 Unit 3 | 6 F3/G15e interface |
7 files and functions | 8 test plan | 9 accepted false positives | 10 live-verification stance | 11 units and order |
12 open questions for Ish | 13 proposed ledger entries (for the coordinator, not written) | 14 residuals not closed.

## 0. Grounding (rule 12: everything below was read or run on this device on 2026-10-23, none from memory)

Method: `--help` dumps and benign scratch-file runs under `/data/data/com.termux/files/usr/tmp/g15d_scratch/` (disposable `HOME`,
proxy vars unset, no model, no network, no dangerous command), plus pure `classify_shell_command()` calls against HEAD `e167e0c`
through `python3 -I` (classification only, nothing executed past the gate). Versions: GNU sed 4.10, gawk 5.4.1, coreutils (multi-call
`$PREFIX/bin/coreutils`), pip 26.2.1, npm 11.21.1, node v24.18.0, qwen 0.20.1. `pnpm`, `yarn`, `ruby`, `perl`, `black`, `isort`, `flake8`,
`mypy`, `pylint`, `tsc` are NOT installed here, so nothing about their option grammar is claimed.

### 0.1 Facts that drive the design (verbatim observations)

1. **GNU/optparse/nopt long-option abbreviation is live, so every exact-string denylist is unsound.**
   - `sort --out=o1 f` created file `o1` (abbreviation of `--output`); `sed --in-pl s/a/X/ g` and `sed --in s/a/Y/ g2` edited the files in place.
   - `pip install --no-index --dry-run --find-l=<dir> zzz` and `... -qf <dir> zzz` both consumed the location (pip printed
     `WARNING: Location ... is ignored`), i.e. abbreviation and a short cluster hiding `-f` both work.
   - npm: `lib/utils/cmd-list.js` builds `abbrev(commands.concat(Object.keys(aliases)))`; `npm tes` ran the `test` script and
     `npm --node-opt=x tst` ran too (abbreviated option AND abbreviated alias). The alias table has 60+ entries
     (`c`, `x`, `it`, `cit`, `isntall`, `add-user`, `rum`, `urn`, `sit`, `verison`, ...).
2. **Current HEAD classification (captured by a pure `classify_shell_command` run, 2026-10-23):**

   | command | HEAD class | note |
   | --- | --- | --- |
   | `npm publ`, `npm pub`, `npm tok list`, `npm own ls`, `npm add-user` | **ACT** | G15c's `_NPM_HIGH_VERBS` exact-string denylist is bypassed by npm's own abbreviation/alias table (publish/token/owner/adduser "closed" items are open) |
   | `npm c edit`, `npm test --userconfig=x`, `npm test --node-opt=x`, `npm test --node-options=--import=data:text/javascript,1` | ACT | reviewer W2 reproduced |
   | `pip install -qf x foo`, `pip install --find-l=/tmp/d foo`, `pip install -t /tmp/x foo`, `pip --python /tmp/e install foo`, `pip install --report /tmp/r.json foo` | ACT | W1 plus new: `--python` runs an arbitrary interpreter, `--target/--report/--log` write arbitrary paths |
   | `pip install --ind=http://x foo` | HIGH | only because the value contains `http://` |
   | `node --inspect=0.0.0.0:9229 x.js`, `node --inspect x.js` | ACT | W3 |
   | `sort -o f1 f2`, `sort --out=f1 f2`, `sort --compress-program=sh f`, `uniq in out`, `tree -o out`, `tree -R`, `file -C -m x` | **READ** | READ-class writers/dispatchers (G15b-06, W4) |
   | `sed -i s/a/b/ f`, `sed 1e\ id f`, `awk BEGIN{system("id")}` | ACT | G15b-06 |
   | `find . -fprint x` | HIGH | already closed: `find` is in `_EXEC_WRAPPER_BASENAMES`, so the "ALLOWED find" write forms of B:SH-03 are moot |
   | `printenv`, `printenv HOME`, `env`, `cat /proc/self/environ`, `cat <HOME>/.ssh/id_ed25519_secondary` | READ | D-2 |
   | `./ls`, `/bin/ls`, `/system/bin/ls` | READ | D-3 / finding 23 |
   | `python3 -m http.server 8000` | ACT | finding 20 |
   | `npm install git+https://x/y.git`, `npm install user/repo`, `pnpm add github:u/r`, `yarn add https://x/t.tgz`, `pnpm link --global`, `yarn add git@github.com:u/r.git` | ACT | finding 13 |
   | `npm i x` | HIGH | accidental: operand `x` equals the `x` (exec) verb token |

3. **Per-tool option sets (full `--help` dumps, long options only; short options were read from the same dumps).**
   - Output-file or exec capable (need a table): `sed` (`-i[SUF]`, `--in-place[=SUF]`, `-e/-f` scripts with `e r R w W` commands and `s///e`, `s///w`; `--sandbox` exists), `sort` (`-o/--output`, `--compress-program`, `-T/--temporary-directory`, `--files0-from`, `--random-source`), `uniq` (`[INPUT [OUTPUT]]`, second positional is written), `tree` (`-o`, `-R`, `-H`, `-T`, `--fromfile`, `--fromtabfile`, `--gitfile`, `--infofile`, `--hintro`, `--houtro`), `file` (`-C/--compile` writes `<magic>.mgc`, `-m`, `-f/--files-from`, `-P`), `awk`/gawk (`-f`, `-e`, `-E/--exec`, `-i/--include`, `-l/--load`, `-d/-D/-o/-p[file]` write files, `system()`, `getline`, redirection).
   - Verified to have NO output-file or exec option (long-option dump read): `ls cat head tail grep wc date diff stat du df which whoami pwd cut tr`. Notes, none needing a fix: `date -s/--set` sets the clock (needs privilege), `diff -l/--paginate` spawns `pr`, `tail --pid/-f/--retry` can run to the 1800 s timeout, and several take an INPUT-file operand via an option (`wc --files0-from`, `du --files0-from`, `date -f`, `grep -f/--exclude-from`, `diff -X`), which the D-2 scan must see as a token.
   - `touch`, `mkdir`, `ln`, `cp`, `mv` write paths; their target policy is G15e (protected-path set), not G15d.
4. **`sed --sandbox` (probed on scratch files):** rejects `w` (`char 7: e/r/w commands disabled in sandbox mode`), `1e echo hi`, `s/a/echo zz/e`, `r f`, `R f`, `W f`, `-f` script containing `w`, and `w /dev/stdout`; it is position independent; it does **NOT** block `-i` (`sed --sandbox -i s/a/Z/ g3` rewrote `g3`); GNU abbreviation applies (`--sandb` accepted by sed, so the classifier must require the exact token). It also removes the `r`/`R` file-read primitive, which matters for D-2.
5. **Device layout for D-3:** `/usr/bin` and `/usr/local/bin` do not exist; `/bin -> /system/bin`; the real system bin is `/data/data/com.termux/files/usr/bin` (owned and writable by the agent's own uid `u0_a247`, so "system dir" is a naming convention here, not an ownership boundary). `ls`, `cat` are symlinks to `coreutils`. `_BUILD_TOOL_SYSTEM_DIRS` at `tools/shell_tools.py:300` is `{/usr/bin, /usr/local/bin, /bin, /data/data/com.termux/files/usr/bin}` and lacks `/system/bin`.
6. **PATH on this device:** `/data/data/com.termux/files/home/bin:/data/data/com.termux/files/home/google-cloud-sdk/bin:/data/data/com.termux/files/home/Codey-OS:/data/data/com.termux/files/home/Codey-v4:/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/home/.local/bin`. The repo root itself and three other user-writable directories precede `$PREFIX/bin`; `shutil.which` currently resolves every common name into `$PREFIX/bin`. See open question Q2.
7. **Credential-bearing artifacts that exist on this device (names listed with `ls`, contents never read):** `~/.ssh/{id_ed25519_secondary,id_ed25519_secondary.pub,authorized_keys,known_hosts}`, `~/.npmrc`, `~/.config/gh/{hosts.yml,config.yml}`, `~/.config/gcloud/{credentials.db,access_tokens.db,application_default_credentials.json,legacy_credentials,...}`, `~/.codeyOS/{age.key,gcp_credentials.json,cloudflare_tunnel_token.age,restoricon.db,...}`; code references `~/.codeyOS/aigentik_internal_token` (`utils/config.py:856`, `install.sh:381`), `~/.codeyOS/ccos_crm_read_token` (`ccos/plugins/crm/core_query/client.py:42`), `CODEY_STATE_DIR/config.json` (tunnel-token fallback, `utils/config.py:728`). `core/context.py:15-25` already has a default ignore list (`.env`, `*.pem`, `*.key`) that is applied only by `/read`, never to the shell or read tools.
8. **Existing invariant to preserve:** `tests/test_shell_wrapper_boundaries.py::test_classifier_does_not_discover_or_parse_children` monkeypatches `subprocess.run`, `Path.exists`, `Path.resolve`, `os.getenv` and `AGENT_CONFIG.get` to raise, then classifies `env`, `env X=value`, `find . -exec opaque ;`, `xargs opaque`. Any filesystem- or environment-dependent check therefore lives in `shell()` (next to the existing `_shell_command_targets_git_metadata` escalation at `tools/shell_tools.py:1063`), never in `classify_shell_command`. Purely lexical checks may live in the classifier.
9. **Callers of `classify_shell_command`** (grep, non-test): `tools/shell_tools.py:1061` (`shell()`), `core/task_executor.py:508,540` (`_daemon_shell`: audit label and the python/pip HIGH clause), `core/process_boundary.py:32` (fix/TDD/recovery, fixed argv `["python3", path]` and `["python3","-m","pytest",...]`, bare `python3`, so D-3 and the credential scan do not affect it; the module allowlist of finding 20 must keep `pytest`). `core/recovery.py` calls `run_process` with an explicit `authority` (`HIGH_IMPACT` for `pip install`, `READ` for `find`/`which`), so it never consults the classifier and is unaffected.

## 1. Findings covered

| G15b id | ledger | what | covered by | unit |
| --- | --- | --- | --- | --- |
| 06 | NEW-1022 | ALLOWED/READ text tools as writers/dispatchers (`sed`, `awk`, `sort`, `uniq`, `tree`, `file`); `find -fprint` already closed (section 0) | option tables, sed `--sandbox` rule, awk always HIGH (3.3) | 1 |
| 09 | NEW-1019 | basename-only classification, symlink/spoofed argv[0] | D-3 slash rule (3.1); PATH-shadow variant is Q2, NOT closed by D-3 (G15b-09 ends "narrowed", not CLOSED) | 1 |
| 10 | NEW-1020 | secret reads as READ, daemon included | D-2 option (b): bare `env`/`printenv` and allowlisted `printenv NAME` (3.2a), credential-path scan in `shell()` (3.2b) | 1 |
| 23 | NEW-1019 | audit-label inaccuracies (`./ls` READ, READ-class writers) | falls out of 3.1 and 3.3 | 1 |
| 13 | NEW-1023 | npm/pnpm/yarn `add\|install\|link` of git/URL specs; pip requirements-style URL operands | structural operand-shape rule (4.3, 4.2) | 2 |
| 14 | NEW-1023 | W1 `pip install -qf x foo` short cluster hides `-f`/`-i` | per-subcommand pip option tables (4.2) | 2 |
| 15 | NEW-1023 | W2 npm `--node-options`, `--userconfig`, `npm c edit\|fix` alias | exact-subcommand + exact-option npm allowlist (4.1), which also closes the abbreviation bypass of the publish verbs found in section 0 | 2 |
| 16 | NEW-1023 | W3 `node --inspect=0.0.0.0:9229` | attached-value shape rule (4.4) | 2 |
| 20 (optional) | NEW-1028 | `python3 -m http.server` / `-m code` | `-m` module allowlist (4.5) | 2 |
| 46 | NEW-1030 | peer escalation Enter = Yes; `.qwen/settings.json` allow-list | default-No + fail-closed interactivity (5.1); allow-list review is a proposal pending Ish (5.2) | 3 |
| 45 (part) | NEW-1029 | `peer_cli.is_interactive_environment()` fails open | 5.1 (the `CODEY_DAEMON_MODE`/`CODEY_NON_INTERACTIVE` never-set part stays queued) | 3 |

Not covered here, deliberately: D-2 option (c) environment scrubbing for children (deferred by Ish; G15h), `restoricon.db` read policy (Q4),
history files (Q4), G15b-07/08 write-target policy and F3 files (G15e), G15b-19/22/36 (accepted ceilings, unchanged).

## 2. Cross-cutting design rules (apply to every unit; this is the G15c lesson made explicit)

**R1. Exact full tokens only.** A tool option is accepted only if the whole token is on that tool's table, spelled out in full.
Because of live abbreviation (section 0 fact 1), an exact-string DENYlist is never sound and a prefix/`startswith` ALLOW is never
sound either. Any dash-led token not on the table makes the command HIGH_IMPACT. This also removes the whole "which spelling did the
tool accept" question: `--out`, `--in`, `--find-l`, `--node-opt`, `--sandb` all fail closed by construction.

**R2. Scan every token, honoring only `--`.** GNU getopt permutes (`sort f -o out` is `-o out`), so the walk must not stop at the first
non-option. Tokens after a bare `--` are operands. (This differs from the G15c node/ruby/perl walk, which correctly stops at the script name
because those interpreters do not permute.)

**R3. Short clusters are walked left to right.** For each letter: on the bare set continue; on the operand set take the rest of the token
as the operand (or, when the rest is empty, the next token, which must exist and must not start with `-`); anything else is HIGH.
So `-qf`, `-ro`, `-ni` can never hide an option.

**R4. Operand-taking options on a table are consumed, and the consumed value is validated or is data that cannot be code.** A separate
operand that starts with `-` makes the command HIGH (fail closed against our parser and the tool's disagreeing about operand boundaries).

**R5. Indirect-filename options are NOT on any table** (`--files0-from`, `--fromfile`, `-f FILE` for file, `--random-source`,
`--gitfile`, `--infofile`, `--exclude-from`): they let a file named by one token supply more arguments or paths. They are HIGH.

**R6. Where each check lives.**
- Lexical, no filesystem, no environment: in `classify_shell_command` (so the existing `test_classifier_does_not_discover_or_parse_children`
  stays green): bare `env`/`printenv` policy, the D-3 slash rule, all option tables, the python `-m` module allowlist, package-spec shapes.
- Needs cwd, `$HOME`, `CODEY_STATE_DIR`, symlinks or `PATH`: in `shell()` as an escalation to HIGH_IMPACT beside
  `_shell_command_targets_git_metadata` (D-2 credential scan; optional Q2 PATH-shadow check). `_daemon_shell` ends in `shell(command,
  yolo=True)` (`core/task_executor.py:553`), so the daemon is covered by both without a second implementation.

**R7. One shared option-walker.** Add one private helper in `tools/shell_tools.py` (suggested name `_walk_options(parts, table)`) and
a frozen dataclass `_OptionTable`. Per-tool differences are data, not code, so the next table edit cannot reintroduce a hand scan.

```
@dataclass(frozen=True)
class _OptionTable:
    short_bare: frozenset      # single letters, may be clustered
    short_operand: frozenset   # letters that consume the rest of the token or the next token
    long_bare: frozenset       # exact "--name", must not carry "=value"
    long_operand: frozenset    # exact "--name": value attached with "=" or in the next token
    long_optional: frozenset   # exact "--name": optional attached "=value", never consumes the next token
    max_positionals: int | None = None
    required: frozenset = frozenset()   # exact tokens that must appear before any "--" (sed: "--sandbox")
# returns (positionals, operands) or None when ANY token is off the table
def _walk_options(parts, table) -> tuple[list, list] | None
```
`None` means "fail closed, caller returns HIGH_IMPACT". A bare `-` token is a positional. Positional and operand lists are returned so
Unit 2 can validate package/requirement specs with the same walk.

**R8. One shared system-directory constant** `_SYSTEM_BIN_DIRS` replaces `_BUILD_TOOL_SYSTEM_DIRS` (`tools/shell_tools.py:300`) and is used by
`_build_tool_is_act` and by D-3. Value: `/bin`, `/sbin`, `/usr/bin`, `/usr/sbin`, `/usr/local/bin`, `/system/bin`, `/system/xbin`,
`/data/data/com.termux/files/usr/bin`. (`/system/bin` is new: `/bin` is a symlink to it on this device and `/system/bin/ls` is a real binary.)
Hard-coded, not derived from `$PREFIX` or `sys.prefix`, because the classifier must not read the environment. Document in the comment that
this is a naming convention, not an ownership boundary (the Termux bin dir is writable by the agent's uid), so a write into it is a G15e
protected-path question.

**R9. Doc comments.** Every function/constant touched or added gets a 2-4 sentence factual comment stating the non-obvious why (abbreviation,
permutation, no-discovery invariant). Tables carry the tool version they were derived from (as the node table does).

## 3. Unit 1: D-3, D-2 and the text-tool tables (G15b-06, 09, 10, 23)

### 3.1 D-3: argv[0] containing `/` must sit in a system directory (decided; applies to READ/ACT names too)

Change in `classify_shell_command` (`tools/shell_tools.py:644`), immediately after `parts`/`base` are computed (line 694), before the
git/termux/network/wrapper checks:

```
argv0 = parts[0]
if "/" in argv0 and not _argv0_in_system_dir(argv0):
    return HIGH_IMPACT
```
`_argv0_in_system_dir(argv0)` (new, lexical, no I/O): False when `argv0` is not absolute or ends with `/`; otherwise
`os.path.normpath(os.path.dirname(argv0)) in _SYSTEM_BIN_DIRS` (R8). `normpath` collapses `.`/`..`/`//` so
`/usr/bin/../../tmp/gcc` becomes parent `/tmp` (HIGH). A leading `//usr/bin` is kept by POSIX `normpath` and is not in the set, so it is HIGH
(fail closed). `_build_tool_is_act` loses its private `exe != base and str(Path(exe).parent) not in ...` clause (now unreachable) and uses
the shared constant only; its existing tests must stay green unchanged (`/usr/bin/gcc` ACT; `./gcc`, `/tmp/x/gcc`, `usr/bin/gcc`,
`/usr/bin/../../tmp/gcc` HIGH).

**Interpretation to state to Ish (not a silent change).** Ish decided "resolved parent". This spec implements the *lexically normalized*
parent, not symlink-following `realpath`, because `test_classifier_does_not_discover_or_parse_children` forbids the classifier touching the
filesystem and because the answer is the same for every path an attacker can construct: a symlinked directory has to live outside the
system dirs (its typed name is non-system, so HIGH), and a symlink or planted file INSIDE a system dir is a write-target problem that only
G15e's protected-path set can address ($PREFIX/bin is writable by the agent's uid). Listed as Q1 for confirmation.

**What D-3 does and does not close.** It closes the decided two-step form (`ln -s /usr/bin/git ls` then `./ls push origin main`; A:N01-N05,
`./ls` audit label) and `./venv/bin/pytest`-style spoofing. It does NOT close the bare-name form: with the PATH in section 0 fact 6 a name
without `/` is resolved by the OS through user-writable directories ahead of `$PREFIX/bin`, so `ln -s $(which git) <repo>/ls` followed by `ls push`
never puts a `/` in argv[0]. G15b-09 is therefore recorded as **narrowed, not closed**, pending Q2 (an optional `shutil.which` shadow check
in `shell()`, spec in 3.5) and G15e (protecting those directories as write targets).

Effects to announce: `./venv/bin/pytest`, `/home/u/.local/bin/ruff`, `/tmp/x/python3` and every `./tool` form become HIGH (refused in
confirm-less modes, prompted in the interactive REPL). `/bin/ls`, `/system/bin/ls`, `/usr/bin/git` (HIGH anyway) and
`/data/data/com.termux/files/usr/bin/*` keep their class. `core/process_boundary.run_process` passes bare `python3`, so fix/TDD/recovery are
unaffected.

### 3.2 D-2 option (b): credential-bearing reads in confirm-less modes, daemon included

Policy (decided): refuse (HIGH_IMPACT) credential-bearing paths and bare `env`/`printenv`. HIGH_IMPACT means: refused and audited where no
confirmation path exists (`--yolo`, daemon, `--fix`/`--tdd`, bench, CCOS), human-prompted in the interactive REPL. Option (c) (scrubbed child
environment) stays deferred.

**3.2a Lexical part, in `classify_shell_command`.**
- `if base == "env": return HIGH_IMPACT` (was: bare `env` READ, argument-bearing HIGH). Update the comment above `_EXEC_WRAPPER_BASENAMES`
  that says "only bare env remains READ".
- New `_printenv_is_safe(parts)`; before `if base in READ_COMMANDS: return READ` add
  `if base == "printenv" and not _printenv_is_safe(parts): return HIGH_IMPACT`. Safe means: at least one operand, no dash-led token at all
  (so `--null`, `--help`, `--version`, `-0` are HIGH), and every operand is an exact member of `_PRINTENV_SAFE_NAMES`:
  `HOME USER LOGNAME SHELL PWD OLDPWD LANG LC_ALL LC_CTYPE TERM TZ TMPDIR PREFIX PATH HOSTNAME SHLVL`. **Interpretation flagged as Q3:** Ish's
  words were "bare `env`/`printenv`"; the hunters' own evidence (C:C02) shows `printenv OPENROUTER_API_KEY` is the same leak, so the spec
  treats every non-allowlisted `printenv NAME` as HIGH too. `printenv` stays in `READ_COMMANDS` (the git-metadata exemption logic reads that
  set); only its argument shape gates it.
- Daemon: `_DAEMON_ALLOWED_PREFIXES` keeps `env` and `printenv` (the prefix test `test_daemon_prefix_word_boundary` pins `("env", True)`); the
  consequence is that daemon `env` is now always refused by `shell()` (the same "admitted prefix, refused by classification" shape as `find`),
  and `printenv` only runs for the allowlisted names. Rewrite the comment block at `core/task_executor.py:34-45` accordingly. **This is a visible
  daemon behavior change to announce to Ish.**

**3.2b Filesystem part, new `_shell_command_targets_credentials(command, *, cwd, home, state_dir) -> bool` in `shell()`.**
Called right after the git-metadata escalation (`tools/shell_tools.py:1063`), same pattern:
```
credential_escalation = False
if authority != HIGH_IMPACT and _scan_credentials_safely(command):   # builds cwd/home/state_dir, any exception => True (fail closed)
    authority = HIGH_IMPACT
    credential_escalation = True
```
and, in the `confirm()` closure, a `warning()` line mirroring the git-metadata one ("Command references a credential-bearing path ...").
`home` is `Path.home()` (reads `$HOME` at call time, so a disposable `HOME` works), `state_dir` is `_config.CODEY_STATE_DIR` read at call time
from the module attribute (it is computed once at `utils/config.py` import, so tests must `monkeypatch.setattr(shell_tools._config,
"CODEY_STATE_DIR", ...)`, not just set the env var), `cwd` is `Path(os.getcwd())`.

*Credential path set* (data constants, each with a one-line why; **Q4 asks Ish to confirm the list**):
- under `home`, equal-or-descendant: `.ssh` `.netrc` `.git-credentials` `.gnupg` `.aws` `.kube` `.npmrc` `.pypirc` `.docker/config.json` `.config/gh`
  `.config/gcloud` `.config/git/credentials`. (Grounded: section 0 fact 7; `.netrc`, `.git-credentials`, `.ssh` are Ish's list; the rest exist or are standard stores.)
- directly under `state_dir`: `age.key` `config.json` `gcp_credentials.json` `aigentik_internal_token` `ccos_crm_read_token` and any `*.age`.
- any directory, by final component (`fnmatchcase`): `.env` `.env.*` `*.pem` `*.key` `id_rsa*` `id_dsa*` `id_ecdsa*` `id_ed25519*`, except names ending `.pub`.
  Same family as the existing `core/context.py` default ignore list. **These basename patterns apply only to candidates that EXIST on disk (`os.lstat` on the lexical joined path succeeds; legal in `shell()`).**
  Without that guard every token is treated as a path, so a search pattern or string such as `grep -rn .env src`, `grep -r id_rsa .`, `grep -n '\.key' f` or `echo .env` would classify HIGH, which is the biggest friction source in the slice for model
  code searches. The literal home/state/`/proc` entries stay unconditional (a nonexistent `~/.netrc` is still refused: the model should not be probing for it). Residual: a pattern that coincides with a file that really exists in the cwd (`grep .env` while a `.env` file is there) is still HIGH.
- `/proc/<digits>/...`, `/proc/self/...`, `/proc/thread-self/...` with at least one component after the pid (covers `cmdline`, `environ`, `mem`,
  `maps`, `fd/N`, `root/...`, `cwd/...`). `/proc/cpuinfo`, `/proc/meminfo` stay readable.
- NOT in the set: the repo-root `config.json` (a `grep -r` from the repo would otherwise become HIGH), `restoricon.db`, shell history files (Q4).

*Candidate extraction, per token after argv[0], with NO READ-command exemption (READ commands are exactly the readers; do not copy the
git scan's exemption):* the token itself; the text after the first `=`; and, for a token that starts with a single `-` and is longer than two
characters, the text after the first two characters (attached short operand such as `-f/path`). Each candidate: skip if empty; a NUL byte
returns True; expand a leading `~`, `$HOME` or `${HOME}` using the passed `home` only (no environment reads); join to `cwd` when relative;
build the lexical form (`os.path.normpath`) and the resolved form (`Path.resolve(strict=False)`); `ValueError`/`OSError` returns True
(fail closed, same as the git scan). A candidate matches when either form satisfies the set above.

*Recursive content readers (ancestor rule).* For base in `{grep, egrep, fgrep, rgrep, diff, cp}` a candidate also matches when it is a path
EQUAL TO OR A PARENT OF any literal entry of the set (`home/.ssh`, `state_dir/age.key`, ..., plus `/proc`), e.g. `grep -r token /`, `grep -r x ~`,
`diff -r ~ x`. Additionally, for the grep family the process `cwd` is treated as one extra candidate (grep with no path operand
searches the cwd when recursive). Do not try to detect `-r`/`-R`/`-d recurse`/`--recursive`/abbreviations: treat every directory operand of
these tools as recursive (flag parsing here would be the hand-scan trap again). Basename patterns (`.env`, `*.pem`) are NOT applied as
ancestors (that would make every `grep -r` in a workspace HIGH); that residual is listed in section 14. `ls`/`du`/`tree` of a directory
expose names only and are not given the ancestor rule.

Why in `shell()` and not the classifier: it needs `cwd`, `$HOME`, `CODEY_STATE_DIR` and symlink resolution (section 0 fact 8).

### 3.3 G15b-06: option tables for the text tools (all derived from the `--help` dumps in section 0; accepted false positives in section 9)

Insert in `classify_shell_command` before `if base in READ_COMMANDS: return READ` (line 719), after the existing npm/pip clauses:
```
if base == "awk": return HIGH_IMPACT
table = _TEXT_TOOL_TABLES.get(base)            # sort, uniq, tree, file, sed
if table is not None and _walk_options(parts, table) is None: return HIGH_IMPACT
```
- **awk (gawk 5.4.1): HIGH in every form.** Its option set includes `-f`, `-e`, `-E/--exec`, `-i/--include`, `-l/--load`, `-d/-D/-o/-p[file]`, and programs can
  call `system()`, `getline` from commands and redirect. gawk has `-S/--sandbox`, but that was NOT probed in this pass (unlike sed), so nothing relies on it.
- **sed (GNU 4.10): ACT only when the exact token `--sandbox` appears (before any `--`) and every other token is on the table.** Table:
  `short_bare` = `n E r s u z`; `short_operand` = `e l`; `long_bare` = `quiet silent debug posix regexp-extended separate sandbox unbuffered
  null-data help version`; `long_operand` = `expression line-length`; `required` = `{"--sandbox"}`. Everything else is HIGH, notably `-i[SUF]` and every
  `--in-*` spelling (verified: `--sandbox` does not block in-place edits), and `-f/--file`. `--sandbox` is the child-side control: sed itself rejects `e r R w W`
  and `s///e`, `s///w` (verified by probe), so no script grammar is parsed by us. Without `--sandbox` the command is HIGH (the model learns on first refusal;
  the classifier must not rewrite argv, so what is audited is what runs). Rejected alternative: auto-injecting `--sandbox` at execution (breaks the
  classify-equals-execute invariant that `_run_shell_command_structured` documents).
- **sort:** `short_bare` = `b d f g i M h n R r V c C m s u z`; `short_operand` = `k t S`; `long_bare` = `ignore-leading-blanks dictionary-order ignore-case
  general-numeric-sort ignore-nonprinting month-sort human-numeric-sort numeric-sort random-sort reverse version-sort merge stable unique zero-terminated debug
  help version`; `long_operand` = `key field-separator sort buffer-size`; `long_optional` = `check`. Off table (HIGH): `-o/--output`, `--compress-program`,
  `-T/--temporary-directory`, `--files0-from`, `--random-source`, `--batch-size`, `--parallel`.
- **uniq:** `short_bare` = `c d D i u z`; `short_operand` = `f s w`; `long_bare` = `count repeated unique ignore-case zero-terminated help version`; `long_operand` =
  `skip-fields skip-chars check-chars`; `long_optional` = `all-repeated group`; `max_positionals` = 1 (the second positional is the OUTPUT file).
- **tree:** `short_bare` = `a d l f x q N Q p u g s h D F v t c U r i A S n C`; `short_operand` = `L P I`; `long_bare` = `noreport dirsfirst filesfirst prune du si
  ignore-case matchdirs metafirst inodes device nolinks condense gitignore version help`; `long_operand` = `sort filelimit`. Off table (HIGH): `-o`, `-R` (reruns tree
  and writes), `-H -T -X -J`, `--fromfile`, `--fromtabfile`, `--gitfile`, `--infofile`, `--hintro`, `--houtro`, `--charset`, `--timefmt` and the rest.
- **file:** `short_bare` = `b i k L h n N 0 p r s v z Z`; `short_operand` = none; `long_bare` = `brief mime mime-type mime-encoding extension apple keep-going dereference
  no-dereference no-buffer no-pad print0 preserve-date raw special-files uncompress uncompress-noreport version help`. Off table (HIGH): `-C/--compile`, `-m`, `-f`, `-c`, `-e`, `-F`, `-P`, `-S`, `-d`, `-l`.
- Tools verified to need no table (section 0 fact 3): `ls cat head tail grep wc date diff stat du df which whoami pwd cut tr`. They keep READ/ACT and are covered
  for indirect reads by the 3.2b token scan. `_GIT_METADATA_SCANNED_READ` is unchanged.
- Each table is a module constant with the tool version in its comment, and a test pins it exactly (the node-table precedent), so any change is a deliberate reviewed edit.

### 3.4 Finding 23 (audit labels)

No separate code. After 3.1 the `./ls` label cannot be READ, and after 3.3 `sort -o`, `uniq in out`, `tree -o` and `file -C` cannot be READ.

### 3.5 Optional (Q2, needs Ish): PATH-shadow check in `shell()`

If Ish answers yes: in `shell()`, for a non-HIGH command whose `parts[0]` contains no `/`, call `shutil.which(parts[0])`; when it finds a file whose
lexically normalized absolute parent is not in `_SYSTEM_BIN_DIRS`, escalate to HIGH_IMPACT (`shadow_escalation`). Unresolvable names are left alone (the exec fails with
not-found anyway). Cost: classification becomes PATH-dependent at the `shell()` layer only, one `which` per command. On this device it produces no false positive today
(section 0 fact 6: all common names resolve into `$PREFIX/bin`). Tests: a disposable `PATH` with a planted executable named `ls` in a temp dir ahead of a fake system dir.

## 4. Unit 2: VCS/URL/package-manager tail (G15b-13, 14, 15, 16, optional 20)

Depends on Unit 1 (`_OptionTable`/`_walk_options`, `_SYSTEM_BIN_DIRS`). Internal order, easiest first so a usage-limit cut leaves a coherent
state: 4.4, 4.5, 4.2, 4.1, 4.3. Each step must leave the suite green.

Shared operand-shape regexes (module constants, final text to be validated by the reviewer against the PEP 508 / npm package-name grammars, starting point):
- `_LOCAL_PATH_RE = ^(?:\.{1,2}|(?:\.{1,2}/|/|~/)[^\s:;]*)$` (explicitly local: `.`, `..`, `./x`, `../x`, `/abs`, `~/x`; no scheme colon).
- `_NPM_NAME_SPEC_RE = ^(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*(?:@[A-Za-z0-9._^~<>=*|-]+)?$` (registry name with optional version/tag; deliberately rejects
  `owner/repo` (GitHub shorthand), `github:`, `git+`, `git@host:`, `npm:alias@`, `https://`, `file:`, `link:`, tarball URLs).
- `_PIP_NAME_SPEC_RE`: name, optional `[extras]`, optional comma-joined comparison specifiers; rejects `@ url`, whitespace, `;` markers, any `:`.
- `_PIP_REL_PATH_RE = ^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+/?$` (pip only: `requirements/dev.txt`; pip never treats `a/b` as a remote shorthand, npm does).

### 4.4 W3 (G15b-16): `node --inspect=HOST:PORT`

Facts (node v24.18.0 `--help`): `--inspect[=[host:]port]` default `127.0.0.1:9229`; same for `--inspect-brk`, `--inspect-wait`. Today the three `--inspect*=` prefixes are in
`_NODE_SAFE_ATTACHED_PREFIXES` (`tools/shell_tools.py:533`), so any attached host, including `0.0.0.0`, is ACT. Change: remove the three prefixes from that tuple and accept an attached form
only when it fullmatches `_NODE_INSPECT_ATTACHED_RE = ^--inspect(?:-brk|-wait)?=(?:\d{1,5}|127\.0\.0\.1:\d{1,5}|\[::1\]:\d{1,5})$`. Bare `--inspect`, `--inspect-brk`, `--inspect-wait` stay in
`_NODE_SAFE_BARE_OPTIONS` unchanged (loopback by documented default). `localhost` is excluded because name resolution is not under the classifier's control. HIGH after the change:
`--inspect=0.0.0.0:9229`, `--inspect=:9229`, `--inspect-brk=192.168.1.5:9229`, `--inspect=localhost:9229`, `--inspect=[::]:9229`, `--inspect-port=0.0.0.0:1`. Stays ACT:
`node --inspect x.js`, `node --inspect=9229 x.js`, `node --inspect-brk=127.0.0.1:9229 x.js`. Existing test `test_node_option_table_derived_from_real_help_is_exact` keeps passing
(bare set unchanged); add a pin for the new regex.

### 4.5 Finding 20 (optional, recommended): `python -m` module allowlist

Today `_interpreter_requests_inline_code` returns False (ACT) as soon as it sees an `m` in a python short cluster or `-m` (`tools/shell_tools.py:630-639`), for any module. Change: extract the module
(rest of the cluster after `m`, else the next token; absent module = HIGH) and return "opaque" (HIGH_IMPACT) unless it is exactly in `_PYTHON_M_ALLOWED_MODULES`:
`pytest pip venv unittest ruff black isort flake8 mypy pylint py_compile compileall json.tool`. Derived from a repo grep of `python3? -m <module>` (counts: pytest 158, pip 7, venv 2, flake8 2, unittest 1,
ruff 1, py_compile 1); `core/tdd.py` needs `pytest`. HIGH after the change: `http.server`, `code`, `pdb`, `trace`, `runpy`, `smtpd`-style listeners, and every operator module seen in the same grep
(`restoricon_core.api.server`, `restoricon_core.migrate_aigentik`, `restoricon_core.backfill_*`, `tools.provision_ai_agent_auth`, `tools.encrypt_cloudflare_token`, `bench.promote`, `bench.scorecard`,
`aigentik.server`, `telemetry.cli`). Honest limit: `python3 tools/provision_ai_agent_auth.py` (script path) stays ACT, so this narrows G15b-21's module forms only; the in-function `/dev/tty` guard
(G15i) is still the real control. The daemon already refuses `-m` (`_DANGEROUS_FLAGS`), unchanged. `python3 -m pip ...` still reaches `_python_dash_m_pip_args` (so `pip` must be allowlisted here).

### 4.2 W1 (G15b-14) and the pip family: replace `_pip_is_high` marker scan with per-subcommand tables

Facts (pip 26.2.1): optparse accepts abbreviations and short clusters (section 0 fact 1); `pip --python <interp>` runs an arbitrary interpreter; `install --target/--root/--prefix/--src`, `--report FILE`,
`--log FILE` write arbitrary paths; `--proxy`, `--cert`, `--client-cert`, `--cache-dir`, `--keyring-provider`, `--use-feature` change trust or spawn helpers. The G15c marker scan
(`_PIP_HIGH_TOKENS`, URL markers, `-i`/`-f` prefix test, `tools/shell_tools.py:443-472`) cannot be made sound by adding cases. New policy for `pip`, `pip3`, `pipN.M` and `python -m pip`
(both reach the same function):
- Global tokens before the subcommand: only exact `-q -v -V -h --quiet --verbose --version --help --no-color --no-input --disable-pip-version-check --isolated --no-cache-dir`.
  The first non-dash token is the subcommand and must be exactly one of `install download uninstall list show freeze check`. `config`, `cache`, `index`, `wheel`, `lock`, `inspect`,
  `completion`, `debug`, `hash`, `search`, `help` and anything else are HIGH (so `pip config set ...` stays HIGH).
- One `_OptionTable` per subcommand, derived from that subcommand's `--help` (dumped on this device; the implementer re-dumps and the reviewer diffs):
  - `install`: `short_bare` = `U I q v h V`; `short_operand` = `r c e`; `long_bare` = `no-deps dry-run user upgrade force-reinstall ignore-installed ignore-requires-python no-build-isolation
    check-build-dependencies break-system-packages compile no-compile no-warn-script-location no-warn-conflicts require-hashes no-require-hashes no-clean pre prefer-binary no-index
    quiet verbose version help no-color no-input disable-pip-version-check isolated no-cache-dir`; `long_operand` = `requirement constraint editable`.
  - `download`: `short_bare` = `q v h V`; `short_operand` = `r c`; same `long_bare` as install minus `user upgrade force-reinstall ignore-installed break-system-packages compile no-compile
    no-warn-script-location no-warn-conflicts`; `long_operand` = `requirement constraint`. (`-d/--dest` is off table.)
  - `uninstall`: `short_bare` = `y q v h V`; `short_operand` = `r`; `long_bare` = `yes break-system-packages` plus the global bare set; `long_operand` = `requirement`.
  - `list`: `short_bare` = `o u e l q v h V`; `long_bare` = `outdated uptodate editable local user not-required exclude-editable include-editable pre prefer-binary no-index` plus globals;
    `long_operand` = `format`. (`-i`, `-f`, `--path`, `--exclude`, index options are off table: HIGH.) Note `-e` is a bare flag here and an operand flag in `install`: that is why tables are per subcommand.
  - `show`: `short_bare` = `f q v h V`; `long_bare` = `files` plus globals. `freeze`: `short_bare` = `l q v h V`; `long_bare` = `local user all exclude-editable` plus globals (`-r`, `--path`, `--exclude` off table).
    `check`: globals only.
- Operand validation: every positional and every consumed operand of `-r/-c/-e/--requirement/--constraint/--editable` must fullmatch `_PIP_NAME_SPEC_RE`, `_LOCAL_PATH_RE` or `_PIP_REL_PATH_RE`; otherwise HIGH.
  This is what closes URL/VCS specs (`git+https://...`, `https://...`, `file:...`, `pkg @ https://...`) and `-r https://host/reqs.txt` without a marker list. Residuals kept by decision: a local
  requirements file can itself contain `--index-url`/URL lines, bare PyPI names fetch and build code, local paths install local code (all ceiling-equivalent, consolidated G15b-13 "rest AR").
- Existing behavior preserved: `pip install requests|-U requests|-e .|-r requirements.txt|./localpkg`, `pip download requests`, `pip list|freeze|show foo`, `pip3 install foo`, `python3 -m pip install foo|list` stay ACT.
  Existing HIGH cases stay HIGH (`--index-url`, `-i`, `-f`, `--find-links`, `--trusted-host`, `--extra-index-url`, attached `-ihttps://x`, `git+...`, `file:///x`, `pip config set ...`), and the W5 false positive
  is fixed in the same edit: at HEAD `pip3.11 install foo`, `pip3.11 list` and `pip3.11 --version` classify HIGH (verified) because the pip clause is reached but the final ACT admission only knows
  the exact names `pip`/`pip3` in `ALLOWED_COMMANDS`, so the default-deny catches `pip3.11`/`pip3.14` (this device runs Python 3.14). Add `_PIP_BASENAME_RE.fullmatch(base)` to the final admission
  condition (`tools/shell_tools.py:721-728`) once the pip table accepted the command, and pin `pip3.14 install foo` ACT.
- Daemon: `_daemon_shell` keeps its own pattern/flag checks, then `classify_shell_command(cmd) == HIGH_IMPACT`; the new classification flows through the existing clause. No `task_executor.py` logic change.

### 4.1 W2 (G15b-15): npm exact-subcommand and exact-option allowlist (replaces `_npm_is_high`)

Facts (npm 11.21.1, `lib/utils/cmd-list.js` and live runs, section 0): npm resolves any unambiguous PREFIX of a command or alias and has ~60 aliases; nopt abbreviates options. G15c's `_NPM_HIGH_VERBS`
exact-string denylist is therefore bypassed today (`npm pub`, `npm publ`, `npm tok list`, `npm own ls`, `npm add-user` classify ACT; verified). New policy for base `npm`:
- Split the tokens after argv[0] at the first bare `--`; tokens after it are arguments for the project's own script and are not examined (script-file precedent).
- Before the subcommand only exact flags from `_NPM_SAFE_FLAGS` may appear (boolean forms such as `-q -s -d --quiet --silent --verbose --json --no-audit --no-fund --legacy-peer-deps --dry-run --offline
  --prefer-offline --save --save-dev -D -S -E --save-exact --no-save --ignore-scripts --no-package-lock --version -v --help -h`) and exact `name=value` forms only for an enumerated set of names with an
  enumerated value regex (`loglevel`, `omit`, `include`, `audit`, `fund`, `progress`, `package-lock`, `ignore-scripts`, `save`, `legacy-peer-deps`, `json`; values `^[A-Za-z0-9._-]{1,32}$`, so no `:` or `/`).
  The implementer derives the final lists from `npm install -h`, `npm run -h`, `npm test -h`, `npm ls -h`, `npm audit -h`, `npm view -h`, `npm help config` on this device (npm 11.21.1) and pins them. No operand-taking
  option is on the list (so there is no "option operand hides the subcommand" case: the first non-dash token IS the subcommand).
- The first non-dash token must be EXACTLY one of `_NPM_ACT_SUBCOMMANDS`: `install i add ci test t start stop restart run run-script rebuild rb pack ls list ll outdated audit why explain view v info show
  config init uninstall remove rm update up dedupe prune` (each must be a real command or alias in `cmd-list.js`; a test cross-checks this when the file exists, `skipif` otherwise). Everything else is HIGH:
  `publish unpublish deprecate login logout adduser add-user token owner access dist-tag exec x explore set link ln pub publ tok own c conf`, every abbreviation, every typo-alias, `version` (creates a git commit
  and tag), `cache`, `team`, `org`, `profile`, `trust`, `edit`, `repo`, `docs`, `bugs`, `get`, `search`.
- Per-subcommand operands: `install|i|add|update|up|uninstall|remove|rm|view|v|info|show|why|explain|pack|rebuild|rb|ls|list|ll|outdated|audit|dedupe|prune`: every non-dash token after the subcommand must fullmatch
  `_NPM_NAME_SPEC_RE` or `_LOCAL_PATH_RE` (this is G15b-13 for npm: no `git+`, `github:`, `owner/repo`, `https://`, `file:`, `npm:alias@`). `run|run-script`: exactly one script-name positional matching `^[A-Za-z0-9:_.-]+$`
  (colons are legal in script names) plus flags from the safe list only (`npm run build --silent` is fine); any second positional before `--` is HIGH. `test|t|start|stop|restart|ci`: no operands. `config`: exactly `get <key>` or `list|ls`, key `^[A-Za-z0-9_.-]+$`. `init`: only `-y`/`--yes`, no operands.
- Consequences against existing tests (rule 6 deliberate updates, see section 8.4): `npm i x` becomes ACT (the accidental `x`-token false positive disappears because only the SUBCOMMAND position is checked);
  `npm build` becomes HIGH (it is not an npm command: `Unknown command`); `npm run build --script-shell=sh` stays HIGH (`--script-shell` is not on the list).
  Hard-exclusion regression list that must classify HIGH: `--node-options=...`, `--node-opt=x`, `--userconfig=x`, `--globalconfig=x`, `--prefix=.`, `--prefix .`, `-g`, `--global`, `--location=global`, `--cache=x`, `--script-shell=sh`,
  `--registry=https://x`, `--@scope:registry=...`, `-w`, `--workspace=x`, `--init-module=x`, `--otp=1`, `--proxy=x`, `--cafile=x`, `--logs-dir=x`.

### 4.3 G15b-13 for pnpm and yarn (partially groundable only)

`pnpm` and `yarn` are not installed here, so their option grammar, aliases and abbreviation behavior cannot be established from the artifact (rule 12); no table is invented. Smaller structural changes in
`_build_tool_is_act` for those two basenames only:
- Add `link` and `ln` (the latter defensively, UNVERIFIED alias) to `_REMOTE_FETCH_SUBCOMMANDS["pnpm"|"yarn"]`: link writes symlinks into a global bin directory (same reasoning as the existing npm `link`/`ln` HIGH).
- When any token equals `add`, `install`, `i`, `update`, `up` or `upgrade`: every NON-dash token must fullmatch `_NPM_NAME_SPEC_RE` or `_LOCAL_PATH_RE`, and every dash-led token that contains `:` makes the command HIGH
  (catches `--registry=https://...`, `--filter=foo:bar` is an accepted false positive). Option operands that are not name-shaped (`--dir ./sub`, `-C ./sub`, `--cwd ./x`, `--filter pkg`) are
  non-dash tokens too: `./sub` passes as a local path, `pkg` passes as a name; an operand such as `https://x` fails. This keeps the G15c any-token philosophy and adds the operand shape.
- Residual (kept, stated): pnpm/yarn verb abbreviations or aliases that are not in `_REMOTE_FETCH_SUBCOMMANDS`/`_PUBLISH_VERBS` stay unverifiable until one of them is installed (Q6).

## 5. Unit 3: D-4 peer escalation default-No (G15b-46, part of 45)

Independent of Units 1 and 2 (different files); may run first or in parallel with Unit 1, but needs its own code-reviewer round.

### 5.1 Code change (`core/peer_cli.py`)

Facts read at HEAD: `PeerCLIManager.confirm` (`core/peer_cli.py:249-301`) returns `(True, None)` for `not ans or ans.lower() in ("y","yes")`; the prompt prints `y / enter  Call <cli>` and
`n  Skip`; `EOFError`/`KeyboardInterrupt` already return `(False, None)`. `is_interactive_environment()` (`:447-454`) returns True when `sys.stdin.isatty()` raises. The yes-answer is the
human approval for a HIGH_IMPACT egress whose peer is started with its auto-approve flag (`run_prompted(..., yolo_flag)`: `-y` for qwen, `--dangerously-skip-permissions` for antigravity),
via `gate_exec(confirm_available=True, confirm=lambda: approved)` at `:421-429`. `is_interactive_environment()` has no production caller (grep: only the definition and
`tests/test_escalation_review_queue.py`), so its change is a safe-default correction with no runtime effect today.
- `confirm()`: `y`/`yes` (case-insensitive) is the ONLY affirmative; empty input (bare Enter) and `n`/`no` return `(False, None)`; the switch/redirect branches are unchanged. Reprint the
  prompt lines as `y  Call <cli>` and `n / enter  Skip (default)` (or equivalent wording) so the displayed default matches the behavior. Add a 2-4 sentence comment on why Enter must not approve.
- `is_interactive_environment()`: `except Exception: return False`.
- No other behavior change. Not a process-lifecycle edit (no spawn/kill/PID/lock/bind change), so rule 4's special trigger does not apply, but the pipeline still requires a code-reviewer pass.

Tests (new `tests/test_peer_cli_confirm_default_no.py`, or additions to `tests/test_peer_cli_redesign.py`): monkeypatch `utils.logger.console` (imported inside `confirm()`) with a stub exposing
`print` and `input`; AND monkeypatch `PeerCLIManager.available` to return a fixed list of `PeerCLI` objects, because the real `available()` calls `shutil.which` and runs `claude --version`
(`check_cmd`) and so would spawn a real process on this device. Cases: `""` and `"   "` return `(False, None)`; `"y"`, `"YES"`, `" yes "` return `(True, None)`; `"n"`, `"No"` return `(False, None)`;
a known peer name or alias returns `("switch", name)`; free text returns `("redirect", text)`; `EOFError` and `KeyboardInterrupt` return `(False, None)`. Integration: drive the real `escalate()` with a recording
`PeerCLIManager.call` and an `input` that returns `""`: assert the gate is never invoked, `call` is never invoked, no audit row is written, and the return is `None`. `is_interactive_environment()`:
`patch("sys.stdin.isatty", side_effect=ValueError)` returns False; the existing `test_is_interactive_environment` stays unchanged and green. The existing `tests/test_peer_escalation_audit.py` mocks
`confirm()` and is unaffected.

### 5.2 `.qwen/settings.json` allow-list review: a proposal, not an edit

Facts: the file is tracked (`git ls-files .qwen` lists it); it contains 20 `Bash(...)` allow entries including `Bash(pkill *)` (rule 3 forbids name-pattern kills), `Bash(rm *)`, `Bash(curl *)`,
`Bash(git add *)`, `Bash(git commit *)`, `Bash(git config *)`, `Bash(command *)`, `Bash(nohup *)`, `Bash(timeout *)`, `Bash(python3 *)`, `Bash(pip install *)`, `Bash(codeydOS *)`, `Bash(pkg *)`,
`Bash(sleep *)`, `Bash(/voice *)`, `Bash(eof)`, `Bash(true)`, `Bash(termux-tts-speak *)`, `Bash(ls *)` and the llama-server binary path. Its three last commits are `Codey checkpoint: Self-modification: test_patch.txt`
(the automatic checkpoint commits), so it was not committed as a deliberate security review (observed from `git log`; intent unknown).
qwen is installed (v0.20.1, `@qwen-code/qwen-code`). Its complete `--help` (40 lines, read) lists no `-y`, `--yolo` or approval-mode option, while `qwen -y --version` and `qwen --yolo --version` both printed
`0.20.1` without a usage error; a version flag may short-circuit before option validation, so acceptance of `-y` is NOT established, and the semantics of `permissions.allow` under `-y` cannot be
determined from the artifact in this pass (a scan of the minified `cli.js` for the strings did not match, `chunks/` not exhaustively read). Consequently this spec does not assert that the allow-list is moot
under `-y`. **Proposal for Ish (Q5):** (A) leave as is; (B) drop the entries that grant destructive, egress, persistence or repo-mutating actions without a prompt (`pkill`, `rm`, `curl`, `git add`, `git commit`,
`git config`, `command`, `nohup`, `timeout`, `python3 *`, `pip install *`, `codeydOS`, the llama-server path) and keep the harmless ones; (C) empty the allow-list. Recommendation: (B), but it is Ish's
convenience trade-off for his own hand-launched qwen sessions in this repo; the implementer must not edit the file until he picks. If edited: JSON-validate it, keep `"$version": 4`, add a test that the file parses and
contains none of the dropped entries.

### 5.3 Verification stance for Unit 3

A light real-input check is worthwhile and cheap (no model, no real peers): reuse the NEW-971 pty harness precedent (`docs/wp2_1_new971_live_verification.md`: case 1a "accept via Enter (pty)" must flip from
PASS-accepted to declined, 1b "accept via y" must still dispatch the fake) with fake peer scripts and a PATH containing only the fakes. Required before calling D-4 "live verified"; code-complete and
reviewer-approved can be claimed without it.

## 6. Interface to G15e (F3 and the shared protected-path set; decided by Ish, NOT built here)

F3 (extend HIGH write classification to `main.py`, the launchers, `lib/*.sh`, `install.sh`, `setup*.sh`, `config.json`, non-`.py` plugin files including `manifest.json`) is slice G15e. G15d must not
pre-empt it, but it shapes three interfaces:
1. **Read set versus write set.** The credential set in 3.2b is read-side ("this operand names a secret"). G15e's protected set is write-side ("this operand is an authority/agent file"). `config.json`
   under the state dir is in BOTH. Keep the G15d constants as clearly named module-level data (`_CRED_HOME_ENTRIES`, `_CRED_STATE_ENTRIES`, `_CRED_BASENAME_PATTERNS`) so G15e can lift them into the shared
   module without rewriting logic; do not create the shared module in G15d.
2. **Reusable path-candidate extraction.** Implement the token-to-candidate step of 3.2b as its own private function (tokens -> `(lexical, resolved)` pairs, with a fail-closed signal for NUL bytes and
   `resolve()` errors). G15e's write-target argv scan and any later refactor of `_shell_command_targets_git_metadata` can then reuse it. Do NOT refactor the already-reviewed git-metadata scan in this slice.
3. **What G15d already shrinks on the shell write route (G15b-07).** After Unit 1, `sed -i`, `sed` without `--sandbox`, `sort -o`/`--output`/`--compress-program`, `uniq in out`, `tree -o`, `file -C` and `awk` are HIGH, so
   the silent shell write routes to F3/agent/evaluator files reduce to `ln -s/-f`, `touch`, `mkdir`, and the prompting `cp`/`mv`/`rm`/`dd`/`chmod` (`tee`, `install`, `truncate`, `shred`, `tar` were already
   refused by G15c default-deny). G15e should also put the PATH directories of section 0 fact 6 (`~/bin`, `~/.local/bin`, `~/google-cloud-sdk/bin`, the repo root, `~/Codey-v4`) and `$PREFIX/bin` on the
   write-protected list, because that is what makes bare-name shadowing (Q2) a write-target problem rather than a classifier problem.

## 7. Exact files and functions to change (line numbers are HEAD `e167e0c`)

| unit | file | change |
| --- | --- | --- |
| 1 | `tools/shell_tools.py` | rename `_BUILD_TOOL_SYSTEM_DIRS` (:300) to `_SYSTEM_BIN_DIRS`, add `/sbin /usr/sbin /system/bin /system/xbin`; add `_argv0_in_system_dir`; `_build_tool_is_act` (:376) drops its private dir test |
| 1 | `tools/shell_tools.py` | new `_OptionTable` + `_walk_options` (R7); new tables `_SED_TABLE`, `_SORT_TABLE`, `_UNIQ_TABLE`, `_TREE_TABLE`, `_FILE_TABLE`, mapped in `_TEXT_TOOL_TABLES`, each commented with tool version |
| 1 | `tools/shell_tools.py` `classify_shell_command` (:644) | D-3 early return after :694; `env` always HIGH (:703-704); `awk` HIGH and table walk and `printenv` gate inserted before `if base in READ_COMMANDS` (:719); docstring steps 1-4 extended with D-2/D-3/tables |
| 1 | `tools/shell_tools.py` | new `_PRINTENV_SAFE_NAMES`, `_printenv_is_safe`; new `_CRED_*` constants, `_path_candidates`, `_shell_command_targets_credentials`; `shell()` (:1034) escalation after :1063-1067 plus `confirm()` warning; update the comment at :198-200 and `classify_shell_command` docstring item 3 (:670-676, "Only a successfully tokenized bare env remains READ") |
| 1 | `core/task_executor.py` | comment/docstring only: block at :34-45 (env/printenv/find admitted but refused by classification) and `_daemon_shell` docstring (:494-502). No logic change; `_DAEMON_ALLOWED_PREFIXES` unchanged |
| 1 (opt, Q2) | `tools/shell_tools.py` | `_command_shadows_system_binary` + `shell()` escalation (3.5) |
| 2 | `tools/shell_tools.py` | `_NODE_SAFE_ATTACHED_PREFIXES` (:533) minus the three `--inspect*=` entries plus `_NODE_INSPECT_ATTACHED_RE` and its use in `_non_python_interpreter_requests_inline_code` (:547) |
| 2 | `tools/shell_tools.py` | `_interpreter_requests_inline_code` python `-m` branches (:630-639) use `_PYTHON_M_ALLOWED_MODULES` (4.5) |
| 2 | `tools/shell_tools.py` | replace `_PIP_HIGH_TOKENS`/`_PIP_REMOTE_SPEC_MARKERS`/`_pip_is_high` (:443-472) with per-subcommand `_OptionTable`s + operand-shape check; adapt both call sites (:713-718, `python -m pip`); final ACT admission (:721-728) accepts `_PIP_BASENAME_RE` names |
| 2 | `tools/shell_tools.py` | replace `_NPM_HIGH_VERBS`/`_NPM_CONFIG_WRITE_VERBS`/`_NPM_INIT_VERBS`/`_npm_is_high` (:338-373) with the exact-subcommand/exact-option allowlist (4.1); `_build_tool_is_act` (:376) pnpm/yarn `link`/`ln` and operand-shape rule (4.3) |
| 3 | `core/peer_cli.py` | `PeerCLIManager.confirm` (:249-301) and `is_interactive_environment` (:447-454) (5.1) |
| 3 (after Q5) | `.qwen/settings.json` | allow-list reduction, only if Ish picks (B) or (C) |
| all | tests | see section 8; every touched function/constant gets the R9 comment |

No change to `core/action_gateway.py`, `core/process_boundary.py`, `utils/config.py`, `install.sh` or `requirements.txt` (no new dependency; `install.sh` rule 11 not triggered).

## 8. Test plan

### 8.1 Harness rules (all units)

- Recording fakes only. Every test that reaches `shell()` or `_daemon_shell()` does `monkeypatch.setattr(shell_tools.subprocess, "run", Mock(...))` and asserts `assert_not_called()` for refusals and the exact recorded argv
  for admissions. Reuse the `gateway` fixture shape from `tests/test_shell_g15c_allowlist.py` (own `ActionGateway(audit_file=tmp)`, `AGENT_CONFIG["confirm_shell"]=False`). No real dangerous command is run by any test.
- Disposable state: `HOME=<tmp>/home`, `CODEY_STATE_DIR=<tmp>/state`, `CODEY_ACTION_GATEWAY_AUDIT=<tmp>/audit.jsonl`, plus `monkeypatch.setattr(shell_tools._config, "CODEY_STATE_DIR", <tmp>/state)` and
  `monkeypatch.setattr(shell_tools._config, "WORKSPACE_ROOT", <tmp>/ws)` and `monkeypatch.chdir(<tmp>/ws)`; fake credential files are created under the disposable home (`.ssh/id_rsa` containing `FAKE-KEY`). The real `~/.ssh`,
  `~/.codeyOS`, `~/.netrc` are never read or named by a test. Run with proxy variables unset and absolute `/data/data/com.termux/files/usr/tmp/...` paths.
- Prefer testing the pure pieces directly (`classify_shell_command`, `_walk_options`, `_shell_command_targets_credentials(cmd, cwd=, home=, state_dir=)`) AND one end-to-end row each through `shell()` and `_daemon_shell()`.
- Table-pin tests: each `_OptionTable` constant is asserted equal to the documented set (the node-table precedent) and a negative list proves the dangerous option names are absent.
- Mutation pass by the implementer (G15c precedent, 35 mutations): drop the D-3 early return; drop the credential-scan call in `shell()`; drop the `required` check; make a table's `short_operand` swallow dash tokens; stop at the first
  non-option instead of scanning all tokens; ignore `--`; flip the printenv gate; remove each table entry class; remove the ancestor rule; drop the NUL fail-closed branch. Each must kill at least one test; report survivors.

### 8.2 Unit 1 cases

- **D-3 (classify):** HIGH: `./ls`, `../ls`, `bin/ls`, `~/ls`, `/tmp/x/ls`, `/home/u/.local/bin/ruff`, `./venv/bin/pytest`, `/usr/bin/../../tmp/ls`, `//usr/bin/ls`, `/usr/bin/`. Unchanged: `/bin/ls` READ,
  `/system/bin/ls` READ, `/data/data/com.termux/files/usr/bin/ls` READ, `/usr/bin/python3 x.py` ACT, `ls` READ. Two-step pin: `ln -s /usr/bin/git ls` is ACT (documented, G15e) and `./ls push origin main` is HIGH and refused
  through `shell()` with the runner not called. Residual pin: bare `ls push origin main` is READ (documents Q2; flip this test if Q2 is adopted).
- **env/printenv:** HIGH: `env`, `env -i`, `/usr/bin/env`, `printenv`, `printenv OPENROUTER_API_KEY`, `printenv HOME SECRET`, `printenv --null HOME`, `printenv -0`. READ: `printenv HOME`, `printenv PATH TERM`. Daemon: `_daemon_shell("env")`,
  `("printenv")`, `("printenv OPENROUTER_API_KEY")` return `[BLOCKED]`, runner not called, audit row outcome refused, authority HIGH_IMPACT; `_daemon_shell("printenv HOME")` runs once with argv `["printenv","HOME"]`.
  `test_daemon_prefix_word_boundary` stays green unchanged.
- **Credential scan:** refused (HIGH, runner not called) in a confirm-less run AND through `_daemon_shell`: `cat <home>/.ssh/id_ed25519`, `cat ~/.ssh/id_rsa`, `cat $HOME/.ssh/id_rsa`, `cat ${HOME}/.netrc`, `head -n1 <home>/.git-credentials`,
  `cat <state>/age.key`, `cat <state>/cloudflare_tunnel_token.age`, `cat <state>/config.json`, `grep token <home>/.config/gh/hosts.yml`, `cat /proc/self/environ`, `cat /proc/1/cmdline`, `cat /proc/<pid>/cmdline`,
  `cat /proc/thread-self/environ`, `sed --sandbox -n 1p <home>/.npmrc`, `wc --files0-from=<home>/.ssh/x`, `grep -f <home>/.ssh/id_rsa file`, `cp <home>/.ssh/id_rsa out`, `cat -- <home>/.ssh/id_rsa`, `cat -n<home>/.ssh/id_rsa`,
  `cat <home>/x/../.ssh/id_rsa`, `cat ../home/.ssh/id_rsa` (cwd = ws), `cat .env`, `cat sub/id_rsa`, `cat key.pem` (these three with the file created in the disposable workspace first), a command containing a NUL byte, and the adversarial resolutions: a workspace symlink pointing at a credential file,
  `/proc/self/root<home>/.ssh/id_rsa` (the resolved form lands on the credential), `/proc/self/cwd/../home/.ssh/id_rsa`, `/proc/self/fd/0` (caught lexically by the `/proc` rule). `/dev/fd/N` is deliberately NOT flagged: `Path.resolve`
  follows it through `/proc/self/fd/N` to the final target, and a spawned child inherits only fds 0-2 (never a credential file), so no test asserts HIGH for it; pin its actual behavior in a comment only. Ancestor rule: `grep -r token <home>`, `grep -rn x /`, `grep -r x /proc`, `grep -R x <state>`, `diff -r <home> <ws>`,
  `cp -r <home> out`, bare `grep -r x` with cwd = `<home>`, `grep -r x .` with cwd = `<home>/.ssh`. Stay READ/ACT: `grep -rn foo src` and `grep -r todo .` with cwd = a disposable workspace, `ls <home>`, `du -sh <state>`, `cat /proc/cpuinfo`,
  `cat /proc/meminfo`, `ls /proc`, `cat README.md`, `tail -c 10 <home>/.bash_history` (pinned as NOT in the set, Q4), and the basename-pattern guard rows with NO such file present: `grep -rn .env src`, `grep -r id_rsa .`, `grep -n '\.key' f`, `echo .env`, `cat .env` (nonexistent).
  Audit-row expectation (do NOT copy the existing daemon tests' `task_executor.daemon_shell` assertion for these): `env`, `printenv NAME` and every credential-path refusal pass `_daemon_shell`'s prefix check and are refused inside `shell()`, so the last audit row has
  `action == "shell_tools.shell"`, `outcome == "refused"`, authority HIGH_IMPACT; only prefix/python-flag refusals carry `action == "task_executor.daemon_shell"`. The implementer must not move the new checks into `_daemon_shell` to satisfy the old assertion. No READ exemption: assert `cat`, `head`, `grep`, `sort` on a `.ssh` path are HIGH. Fail-closed: `Path.resolve` patched to raise `OSError`
  gives HIGH; `Path.home` patched to raise `RuntimeError` gives a refusal, not a crash. Interactive path preserved: with `confirm_shell` True and `ask_confirm` patched False the result is `[CANCELLED]` and the runner is not called; patched True the
  runner is called once with the exact argv.
- **Text tools:** one accept list and one refuse list per tool, enumerated here so the reviewer can diff them. sed ACT: `sed --sandbox -n 1,5p f`, `sed --sandbox -E s/a/b/ f`, `sed -n --sandbox p f`, `sed --sandbox -e s/a/b/ -e s/c/d/ f`,
  `sed --sandbox --expression=s/a/b/ f`, `sed --sandbox -z p f`, `sed --sandbox -- s/a/b/ f`. sed HIGH: `sed -n p f`, `sed -i s/a/b/ f`, `sed --sandbox -i s/a/b/ f`, `sed --sandbox -ni p f`, `sed --sandbox -n -i.bak p f`,
  `sed --sandbox --in-place s/a/b/ f`, `sed --sandbox --in-pl s/a/b/ f`, `sed --sandbox --in s/a/b/ f`, `sed --sandb -n p f`, `sed --sandbox -f s.sed f`, `sed --sandbox --file=s.sed f`, `sed -- --sandbox p f`, `sed --sandbox=1 p f`,
  `sed --sandbox -e`, `sed --sandbox -e -n f`, `sed 1e\ id f`, `sed --version`. sort READ: `sort f`, `sort -u -n -r f`, `sort -t, -k2,2n f`, `sort --key=2 --field-separator=, f`, `sort -nr f`, `sort --check=quiet f`. sort HIGH: `sort -o f1 f2`,
  `sort -of1 f2`, `sort -ro f1 f`, `sort --output=x f`, `sort --out=x f`, `sort --o=x f`, `sort --compress-program=sh f`, `sort --compress=sh f`, `sort -T /tmp f`, `sort --files0-from=list`, `sort --random-source=/dev/urandom -R f`, `sort f -o out`, `sort -k`, `sort -t -`.
  uniq READ: `uniq`, `uniq f`, `uniq -c f`, `uniq -f 1 f`, `uniq -f1 f`, `uniq --skip-fields=1 f`, `uniq --group f`, `uniq --all-repeated=separate f`. uniq HIGH: `uniq in out`, `uniq -c in out`, `uniq --count in out`, `uniq in -- out`, `uniq -D=1`.
  tree READ: `tree`, `tree -L 2`, `tree -aI node_modules`, `tree -L2`, `tree --noreport -d`, `tree -P '*.py' -I __pycache__`. tree HIGH: `tree -o out`, `tree -ro out`, `tree -R`, `tree -H http://x`, `tree -T t`, `tree -X`, `tree --fromfile .`,
  `tree --gitfile x`, `tree --infofile x`, `tree --hintro=f`, `tree --output=x`, `tree -o`, `tree -L -o`. file READ: `file f`, `file -b f`, `file --mime-type f`, `file -bi f`, `file -L f`. file HIGH: `file -C -m magic`, `file -C`, `file --compile`, `file -m x f`,
  `file --magic-file=x f`, `file -f list`, `file --files-from=list`, `file -P name=1 f`, `file -S f`, `file -e text f`, `file -F: f`. awk HIGH: `awk '{print}' f`, `awk --version`, `awk -f x f`, `awk 'BEGIN{system("id")}'`.
  No-regression: `ls -la`, `grep -rn x src`, `diff -u a b`, `wc -l f`, `head -n 5 f`, `tail -n 5 f`, `date +%F`, `stat f`, `du -sh .`, `df -h`, `cut -d, -f1 f`, `tr a b` keep their class.
- **Real-parser smoke (benign, scratch files, not through `shell()`):** for each ACCEPT row above, run the real tool once (`sed --sandbox -n p`, `sort -u`, `uniq -c`, `tree -L 1`, `file -b`) on a scratch file and assert exit 0, `skipif` the tool is
  absent. Purpose: catch a table entry the real tool does not recognize. It runs no dangerous form.

### 8.3 Unit 2 cases

- **node:** `node --inspect x.js`, `node --inspect=9229 x.js`, `node --inspect-brk=127.0.0.1:9229 x.js` ACT; `--inspect=0.0.0.0:9229`, `--inspect=:9229`, `--inspect-brk=192.168.1.5:9229`, `--inspect=localhost:9229`, `--inspect=[::]:9229`, `--inspect-port=0.0.0.0:1` HIGH.
- **python -m:** ACT: `python3 -m pytest -q`, `python3 -Im pytest`, `python3 -mpytest`, `python3 -m pip list`, `python3 -m venv .v`, `python3 -m unittest`, `python3 -m ruff check .`. HIGH: `python3 -m http.server`, `python3 -mhttp.server`, `python3 -Im http.server 8000`,
  `python3 -m code`, `python3 -m pdb x.py`, `python3 -m`, `python3 -m pytest.__main__`, `python3 -m restoricon_core.api.server --host 0.0.0.0`, `python3 -m tools.provision_ai_agent_auth`, `python3 -m bench.promote`.
- **pip:** HIGH: `pip install -qf x foo`, `pip install -fq x foo`, `pip install -qi x foo`, `pip install --find-l=/d foo`, `pip install --ind=x foo`, `pip install --index=x foo`, `pip install --fin x foo`, `pip install --extra-index-url=x foo`,
  `pip install -t /tmp/x foo`, `pip install --target=x foo`, `pip install --root x foo`, `pip install --report /tmp/r.json foo`, `pip install --log /tmp/l foo`, `pip --python /tmp/e install foo`, `pip --proxy http://x install foo`, `pip install --cert x foo`,
  `pip install --use-feature=x foo`, `pip install -C x foo`, `pip install --config-settings x foo`, `pip install --requirements-from-script f`, `pip install --group g`, `pip install foo --no-index -f x`, `pip download -d /tmp foo`, `pip download --dest=x foo`,
  `pip config set a b`, `pip cache purge`, `pip wheel .`, `pip install -r https://x/reqs.txt`, `pip install -e git+https://x/y#egg=z`, `pip install 'foo @ https://x/y.whl'`, `pip install git+ssh://h/r.git`, `pip install file:///x`, `pip list -i http://x`,
  `pip list --path /tmp`, `pip freeze -r requirements.txt`. ACT: all rows of the existing tests plus `pip install -U pip`, `pip install -qU foo`, `pip install --no-deps -r requirements/dev.txt`, `pip install "requests>=2,<3"`, `pip install requests[security]==2.0`,
  `pip3.14 install foo`, `python3 -m pip install -e .`, `pip uninstall -y foo`, `pip list --outdated --format=json`, `pip show -f foo`, `pip --version`, `pip install --user --break-system-packages foo`.
- **npm:** HIGH: `npm pub`, `npm publ`, `npm publish`, `npm tok list`, `npm own ls`, `npm add-user`, `npm adduser`, `npm c edit`, `npm c set x y`, `npm conf set x y`, `npm config set x y`, `npm test --node-options=--import=data:text/javascript,1`, `npm test --node-opt=x`,
  `npm test --userconfig=x`, `npm run build --script-shell=sh`, `npm --prefix sub test`, `npm -g install foo`, `npm install -g foo`, `npm install git+https://x/y.git`, `npm install github:u/r`, `npm install user/repo`, `npm install https://x/t.tgz`, `npm install file:../x`,
  `npm install npm:alias@1`, `npm install foo@git+https://x`, `npm install --registry=https://x foo`, `npm i --registry https://x foo`, `npm exec foo`, `npm x foo`, `npm ex foo`, `npm explore foo`, `npm link`, `npm ln`, `npm set x y`, `npm version patch`, `npm init vite`,
  `npm create vite`, `npm isntall foo`, `npm insta foo`, `npm tes`, `npm build`, `npm run`, `npm run a b`. ACT: `npm i x`, `npm install -D vitest`, `npm install left-pad@1.3.0`, `npm install @types/node`, `npm install ./local-pkg`, `npm test -- --watch`,
  `npm run build:prod`, `npm run test -- --node-options=--import=x` (tokens after `--` are script arguments, documented), `npm ci`, `npm ls --json`, `npm config get registry`, `npm config list`, `npm --version`, `npm init -y`, plus every row of the existing
  routine tests except `npm build`. A test cross-checks every `_NPM_ACT_SUBCOMMANDS` entry against the live `cmd-list.js` commands and aliases when that file exists.
- **pnpm/yarn:** HIGH: `pnpm add github:u/r`, `yarn add https://x/t.tgz`, `pnpm add git+https://x/y.git`, `pnpm add user/repo`, `yarn add git@github.com:u/r.git`, `pnpm add --registry=https://x foo`, `pnpm add --registry https://x foo`, `pnpm link --global`,
  `yarn link`, `pnpm ln`, `pnpm install npm:foo@1`, `yarn add foo@npm:bar`. ACT: `pnpm add foo`, `pnpm add -D foo@1.2.3`, `yarn add @scope/pkg`, `pnpm install`, `yarn install`, `pnpm add ./local`, `pnpm --dir ./sub add foo`, `pnpm run build:prod`, and every existing G15c row.
- **Daemon:** `_daemon_shell` with `pip install --find-l=x foo`, `pip install -qf x foo`, `pip install --target=x foo` refused without a spawn; `pip install foo` and `python3 x.py` still run once.

### 8.4 Existing tests that will change on purpose (rule 6 updates, each edit explains why in a comment; none may be weakened silently)

- `tests/test_shell_wrapper_boundaries.py::test_only_bare_env_is_read` (:45): all four rows (`env`, `  env  `, `'/temporary/path with spaces/env'`, `/temporary/bin/env`) become HIGH (D-2a and D-3); rename to `test_env_is_always_high`.
- same file, `test_unrelated_classifications_unchanged` (:56): `("printenv", READ)` becomes HIGH; add `("printenv HOME", READ)`.
- same file, `test_classifier_does_not_discover_or_parse_children` (:175-183): MUST stay green and unweakened; extend its command list with the new lexical cases (`./ls`, `printenv`, `sort -o x f`, `sed -i s/a/b/ f`) to prove the classifier still does no discovery.
- `tests/test_shell_git_environment_isolation.py::test_non_git_command_unaffected` (:210-222): `shell("env", yolo=True)` is now refused. Rewrite the probe to run an ACT script file (`python3 <tmp>/dump_env.py`, written under `tmp_path`, that writes `os.environ` to a file the test reads) through the real runner; keep the assertions
  (marker variable present, no `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0`).
- `tests/test_shell_g15c_allowlist.py`: node `--inspect` host rows added to the HIGH list while `node --inspect=9229 x.js` stays ACT; the `-m` residual comments updated and HIGH rows added; `npm build` rows move to HIGH (not an npm command); the `npm i x` accidental-false-positive comment in the routine test is
  updated (it is now ACT); pip rows per 4.2.
- Any other test whose argv[0] is a non-system absolute path expecting READ/ACT (search `/temporary/` and `tmp_path` argv[0] patterns under the shell tests): deliberate D-3 updates.
- Suite to run: the 12-file shell/daemon/recovery set from the G15c verification (1,680 passed; recompute it with a grep of `shell_tools|_daemon_shell|classify_shell_command` under `tests/`, the file list is not reproduced in the ledgers), plus `tests/test_peer_*.py`, `tests/test_main_peer_gateway.py`,
  `tests/test_escalation_review_queue.py`. Every failure is reported as deliberate-update or regression; a regression blocks. Known unrelated failures (handoff section 6) are excluded by name. Run in chunks under 100 s.

## 9. Accepted false positives (HIGH_IMPACT where the command is arguably benign; each is a deliberate fail-closed cost and goes in the register and the PROJECT_LOG entry)

- Unit 1: any `./tool`, `../tool`, `bin/tool`, `~/tool`, or absolute argv[0] outside the system dirs (`./venv/bin/pytest`, `~/.local/bin/ruff`); `env` in any form; bare `printenv` and `printenv` of any name outside the 16-name allowlist;
  `ls`/`stat`/`du`/`file`/`wc` (metadata only) of an operand that names a credential path (`ls ~/.ssh`); any operand that names an EXISTING file called `.env`, `.env.*` (including `.env.example`), `*.pem`, `*.key`, `id_rsa*` (a mere search pattern with no such file is not escalated); `/proc/self/*` and `/proc/<pid>/*` reads such as
  `cat /proc/self/status`; `grep`/`diff`/`cp` of `~` or `/` or any ancestor of the credential dirs, and any `grep` run from a cwd that is such an ancestor; `sed` without `--sandbox`, `sed -f`, `sed -i`; `awk` in every form (including `awk --version`);
  `sort -T`, `sort --parallel`, `sort --files0-from`; `uniq a b`; `tree -R/-H/-X/-J/-o`; `file -f/-m/-e/-F/-P`; `sort -t -`; any command whose option operand begins with `-`; GNU abbreviations of otherwise-allowed long options (`sort --stab`, `sed --quiet` spelled `--qui`).
- Unit 2: pip subcommands outside `install download uninstall list show freeze check` (`pip wheel`, `pip cache`, `pip index`, `pip inspect`); `pip download -d`, `pip freeze -r`, `pip list --path/--exclude`; `pip install` of a spec containing whitespace, `;` markers, `@ url` or any `:` (extras with quotes, environment markers); npm abbreviations and typo-aliases (`npm isntall`, `npm tes`, `npm ex`); `npm version`, `npm search`, `npm edit`, `npm get`; any npm flag not on the list including `-g`, `-w`, `--prefix`, `--registry`;
  `npm install owner/repo`; `pnpm`/`yarn add|install` operands that are not name-shaped or explicit local paths, and any dash-led token containing `:` next to those verbs (`--filter=foo:bar`); `python3 -m` of any module outside the 13-entry list (`python3 -m bench.scorecard`,
  `python3 -m timeit`, `python3 -m cProfile`); `node --inspect=localhost:9229`.
- Unit 3: pressing Enter at the peer escalation prompt now means "skip".
Everything above is refused in confirm-less modes and merely prompted in the interactive REPL.

## 10. Live-verification stance

- Units 1 and 2 are pure classification plus a `shell()` escalation: no model load, no process-lifecycle code (no spawn/kill/PID/lock/bind change), no RAM-sensitive path. A **live-verifier agent is not needed** and rule 2 (`free -h`, one model cycle) is not triggered.
  This is the same evidence tier as G15c (code-complete, then code-reviewer-approved; recording-fake evidence through the real `shell()` and `_daemon_shell` gates). Report it as that tier, never as "live verified".
- Because the tables are derived from tool help text, the benign real-parser smoke in 8.2 is part of the unit's tests, and the coordinator should run one end-to-end smoke after Unit 2: through the real `shell()`/`_daemon_shell` with REAL binaries for ACCEPT rows only in a disposable
  HOME/state/audit (`sort -u`, `sed --sandbox -n p`, `uniq -c`, `printenv HOME`, `pip --version`, `npm --version`) and recording fakes for every refusal row. This catches "table entry the real tool rejects" and "gate silently wired to the wrong function", the class that rule 7 and the
  `NEW-259` note describe.
- Unit 3: the pty real-input check in 5.3 (reuse the NEW-971 harness with fake peers) is required before anyone writes "live verified" for D-4; without it the tier is code-complete plus reviewer-approved.
- The code-reviewer is mandatory for every unit (security/RBAC-adjacent classification), adversarial, and must derive facts from the artifacts (rule 12): re-dump `sed/sort/uniq/tree/file/pip <sub>/npm` help and diff the tables, probe abbreviations on scratch files as done in section 0. Per the G15c
  lesson, expect 2-3 rounds; if the reviewer rejects the same fix twice without converging, stop and escalate (CLAUDE.md).

## 11. Proposed implementer units and order (at most three)

| unit | scope | depends on | est. tokens (not measured) |
| --- | --- | --- | --- |
| A | section 3: shared constant + `_OptionTable`/`_walk_options`, D-3, D-2 (classifier `env`/`printenv` + `shell()` credential scan), sed/sort/uniq/tree/file/awk, finding 23, daemon comment edit, test updates 8.4 | none | 1.2-1.8M |
| B | section 4: node inspect, python `-m` allowlist, pip tables, npm allowlist, pnpm/yarn shape rule | A (helper, constant) | 1.5-2.2M |
| C | section 5: `peer_cli` default-No + fail-closed interactivity (+ `.qwen/settings.json` only after Q5) | none | 0.3-0.5M |

Order: **A then B, strictly sequential** (both edit `classify_shell_command` and B reuses A's helper and system-dir constant, so they must not run in parallel in one working tree). C is independent (different files) and may run first or alongside A only if the coordinator accepts concurrent-agent
risk in the same tree (NEW-994: stage exact paths, never stash). Inside B the order is 4.4, 4.5, 4.2, 4.1, 4.3 with each step leaving the suite green and the work written to disk after each step (usage limits have killed three agents this project). The consolidated register estimated 1.5-2.5M tokens for all of G15d;
this scope (npm and pip restructure, D-2, D-3) is larger, about 3-4.5M, and that gap should be told to Ish. Each unit: architect spec (this document) -> implementer -> code-reviewer (APPROVED/CHANGES REQUESTED) -> coordinator runs the suites, updates ledgers, Ish approves exact paths -> commit.
Ledger updates after reviewer approval belong to the coordinator: the blueprint WP2.1 status note, `PROJECT_LOG.md` (top entry, real counts), `NEW_ISSUES.md`, and the consolidated register statuses (G15b-06, 10, 13-16, 23, 46 per unit; G15b-09 as "narrowed", not CLOSED, until Q2 and G15e land).

## 12. Open questions for Ish (recommended handling: dispatch Units C and A now on the stated defaults; every default is at least as strict as what Ish decided and each is reversible by loosening a constant, so Q1-Q4 need not gate Unit A; Q2 and Q5-Q7 should be answered before the unit they name; if Ish answers differently the change is a table edit, not a redesign)

- **Q1 (Unit A, interpretation of decided D-3).** "Resolved parent" is implemented as the lexically normalized parent against a fixed system-dir set, not symlink-following `realpath`, because the existing no-discovery test forbids filesystem access in the classifier and the result is the same for every
  attacker-constructible path. Confirm, or accept an FS-touching variant placed in `shell()` instead. Recommend: confirm as specced.
- **Q2 (Unit A, extends D-3).** PATH on this device begins with user-writable directories (`~/bin`, `~/google-cloud-sdk/bin`, the repo root, `~/Codey-v4`) ahead of `$PREFIX/bin`; `ln` is silent ACT, so the bare-name shadow (link git into the repo root as `ls`, run `ls push`) bypasses D-3 entirely.
  Add the `shutil.which`-based shadow check in `shell()` (3.5)? It costs one PATH lookup per command and makes `shell()` classification PATH-dependent. Recommend: yes, plus G15e protecting those directories as write targets. If no, G15b-09 stays "narrowed" permanently.
- **Q3 (Unit A, interpretation of decided D-2).** Treat `printenv NAME` for any name outside a 16-name non-secret allowlist as HIGH too (not only bare `printenv`)? Evidence C:C02: `printenv OPENROUTER_API_KEY` classifies READ today. Recommend: yes. Also confirm that daemon `env` becoming always-refused is acceptable (visible change).
- **Q4 (Unit A, the credential set).** Confirm the list in 3.2b. Open additions: shell history files (`.bash_history`, `.zsh_history`; hunter A rated MEDIUM; recommend yes, one-line add), `restoricon.db` plus `-wal`/`-shm` (PII; recommend yes, same directory), the repo-root `config.json` (recommend NO: it would make every `grep -r` in the repo HIGH,
  and F3/G15e covers its write side), `.env.example` (accepted as a false positive today). Also whether `ls`/`stat`/`du` of a credential path should be exempt (recommend no: simpler and fail-closed).
- **Q5 (Unit C).** `.qwen/settings.json` allow-list: (A) leave, (B) drop the destructive/egress/persistence/repo-mutating entries, (C) empty it. qwen's own semantics for `-y` and `permissions.allow` could not be established from the artifact (section 5.2). Recommend (B), your call because it affects your hand-launched qwen sessions in this repo.
- **Q6 (Unit B).** `pnpm`/`yarn` are not installed here, so only a conservative operand-shape rule plus `link` is specced for them; their verb aliases/abbreviations stay unverifiable (rule 12). Accept that residual (recommend yes: unused on this device), or install one to ground the table first?
- **Q7 (Units A/B, product trade-offs).** (a) `sed` is ACT only when the model writes `--sandbox` itself (no argv rewriting, refusal teaches it); alternative is auto-injection, rejected here because it breaks classify-equals-execute. (b) `awk` is HIGH in every form; alternative is to probe gawk `--sandbox` first and re-admit it.
  (c) `python -m` module allowlist (finding 20, optional): recommend yes, it also removes the module forms of the operator entry points. Confirm all three, or choose the alternatives.
- **Q8 (coordinator, not Ish).** NEW ids for the entries in section 13 must be allocated by the coordinator after `git status --short` shows nothing else touched `NEW_ISSUES.md`/`PROJECT_LOG.md` (last used NEW-1035; `PROJECT_LOG.md` and the consolidated register were already dirty when this spec was written).

## 13. Proposed ledger entries (for the coordinator to allocate and record; this spec did NOT edit `NEW_ISSUES.md`, `PROJECT_LOG.md`, the blueprint or the consolidated register)

1. **Confirmed (rule 6 correction to G15c closure claims):** the npm publish/token/owner/adduser/config denylist is bypassed by npm's own subcommand abbreviation and alias table: `npm pub`, `npm publ`, `npm tok list`, `npm own ls`, `npm add-user`, `npm c edit` classify ACT at `e167e0c`
   (pure classification run 2026-10-23). Reopens the npm part of G15b-03 ("publish/login/token forms explicit HIGH") and widens W2. Fix: Unit B 4.1.
2. **Confirmed:** pip option abbreviation and short clusters evade the marker scan (`pip install --find-l=<dir> foo`, `-qf <dir> foo`; probe: pip consumed the location), and `pip --python <interp>`, `pip install --target/--root/--prefix/--src/--report/--log` classify ACT. Widens W1. Fix: Unit B 4.2.
3. **Confirmed (class finding):** GNU/optparse/nopt long-option abbreviation makes every exact-string option denylist unsound; observed on scratch files: `sort --out=o1 f` wrote `o1`, `sed --in-pl` and `sed --in` edited files in place, `npm --node-opt=x tst` accepted. Basis for rule R1. Fix: Units A and B.
4. **Confirmed (observation; effect not exercised):** PATH order on this device puts user-writable directories ahead of `$PREFIX/bin` (section 0 fact 6); bare-name classification is therefore spoofable via a planted executable. G15b-09 is "narrowed, not closed" by D-3. Fix: Q2 plus G15e write protection.
5. **Confirmed:** `pip3.11`/`pip3.14` classify HIGH at HEAD (W5): the pip clause is reached but the final ACT admission only lists `pip`/`pip3`. Fix in Unit B 4.2.
6. **Confirmed (minor):** `_BUILD_TOOL_SYSTEM_DIRS` (`/usr/bin`, `/usr/local/bin`, `/bin`, Termux bin) does not match this device (`/usr/bin` absent, `/bin -> /system/bin`, `/system/bin` missing). Fix: R8.
7. **Confirmed:** `find` write/exec forms (`-fprint`, `-exec`) are already HIGH because `find` is in `_EXEC_WRAPPER_BASENAMES` (`find . -fprint x` -> HIGH_IMPACT); hunter B's SH-03 INCONCLUSIVE row can be closed on that basis.
8. **Confirmed (limits, no fix):** `awk` (gawk 5.4.1) ACT with `system()`/`-i`/`-l`/`-E`; `file -C` writer in READ; `sort --compress-program` dispatcher in READ: all in G15b-06, closed by Unit A.
9. **Suspected:** `.qwen/settings.json` entered git through automatic "Codey checkpoint: Self-modification" commits (last three commits), so its allow-list may never have been deliberately reviewed; `-y`/`permissions.allow` semantics for qwen 0.20.1 not established (its `--help` lists no such option; `qwen -y --version` printed the version).
10. **Observed, unrelated to this slice (Info / Suspected):** the `qwen` launcher script failed under this tool shell with `bad interpreter: /usr/bin/env: No such file or directory` (`/usr/bin` does not exist on this device; works only where termux-exec rewrites shebangs); `core/peer_shell.py` launches by argv, so whether the peer
    launch works depends on the launching environment. Not investigated.
11. **Info (no fix needed, verified):** `date -s/--set` (privileged), `diff -l/--paginate` (spawns `pr`), `tail -f/--retry` (can run to the 1800 s timeout) are the only non-read side effects among `ls cat head tail grep wc date diff stat du df which whoami pwd cut tr`.
12. **Status updates to propose after reviewer approval (tier: code-complete + reviewer-approved, not live verified):** G15b-06 and G15b-23 closed by A; G15b-08 "G01/G02/G05 (`sed -n 'w .git/config'`, `sort -o.git/config`, the awk redirect) closed by A as HIGH (the implementer pins those three exact commands as HIGH), G11-G13 open (G15e)";
    G15b-07 "shell write route narrowed (section 6 item 3), remaining `ln`/`touch`/`mkdir` and prompting `cp/mv` open (G15e)"; G15b-10 closed for the classifier/daemon scope by A (option (c) env scrubbing still open under G15h; G15b-11 unchanged); G15b-09 narrowed; G15b-13/14/15/16 closed by B (G15b-13 "rest AR" unchanged);
    G15b-20 closed by B if Q7(c) is yes; G15b-46 closed by C for the Enter default (allow-list per Q5); G15b-45 partially (fail-closed interactivity only).

## 14. Residuals this slice deliberately does not close (state them in the register; do not let "closed" wording hide them)

- Script-file ceiling (G15b-19): `python3 x.py`, `bash x.sh`, `pytest -p`, `make`, compiler configs can still read any credential, spawn anything, and run package build scripts; every classifier rule here is defense against direct and naive forms plus truthful audit, not a sandbox (consolidated section 1).
- D-2 option (c): children (shell, plugin Popen, bench agent) still inherit the full environment; `cat <credential>` through a script child is not stopped.
- Basename-pattern secrets (`.env`, `*.pem`) are caught by direct operand only; `grep -r KEY .` inside a workspace that contains them is not (ancestor rule uses literal entries only).
- `/dev/fd/N` and any fd-based indirection; hard links (`os.link` unavailable on this device, NEW-872); case-insensitive filesystems.
- Silent write routes that remain on the shell: `ln -s/-f`, `touch`, `mkdir`, and the prompting `cp/mv/rm/dd/chmod` (G15e). `$PREFIX/bin` and the PATH directories are writable by the agent's uid (G15e).
- Bare-name shadowing unless Q2 is adopted.
- Registry-name installs (`npm install foo`, `pip install foo`) and local-path installs still fetch/build and run code (ceiling-equivalent, G15b-13 "rest AR"); a requirements file can contain URL or index lines.
- `pnpm`/`yarn` aliases and abbreviations; `ruby`/`perl` tables (G15c, still unverified: not installed).
- npm tokens after the first `--` are passed to the project's own script unexamined (script-file precedent).
- Daemon IPC peer-uid check, `CODEY_DAEMON_MODE`/`CODEY_NON_INTERACTIVE` never set (G15b-44/45 remainder, queued).
