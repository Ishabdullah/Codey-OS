import os
import re
import shlex
import shutil
import stat
import subprocess
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from time import monotonic
from typing import Optional

import utils.config as _config
from core import protected_paths as _protected_paths
from core.action_gateway import (
    ACT,
    HIGH_IMPACT,
    OUTCOME_FAILED,
    OUTCOME_REFUSED,
    READ,
    get_action_gateway,
)
from core.git_execution import shell_git_environment
from utils.config import AGENT_CONFIG, CODE_DIR
from utils.logger import confirm as ask_confirm
from utils.logger import warning

SHELL_METACHARACTERS = {
    ";",
    "&&",
    "||",
    "|",
    "`",
    "$(",
    "${",
    "<(",
    ">(",
    ">",
    "<",
    "&",
    "\n",
    "\\",
}

DANGEROUS_COMMANDS = [
    "rm",
    "rmdir",
    "mkfs",
    "dd",
    "chmod",
    "wget",
    "curl",
    "mv",
    "cp",
]

ALLOWED_COMMANDS = {
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "wc",
    "sort",
    "uniq",
    "echo",
    "pwd",
    "which",
    "env",
    "printenv",
    "date",
    "whoami",
    "python",
    "python3",
    "pip",
    "pip3",
    "pytest",
    "node",
    "npm",
    "git",
    "cd",
    "mkdir",
    "touch",
    "cp",
    "mv",
    "ln",
    "diff",
    "file",
    "stat",
    "du",
    "df",
    "tree",
    "sed",
    "awk",
    "tr",
    "cut",
    "xargs",
    "termux-open",
    "termux-clipboard-set",
    "termux-clipboard-get",
}

DANGEROUS_PATTERNS = [
    "sudo ",
    "> /dev/",
    "| sh",
    "| bash",
    ":(){:|:&};:",
    "sh -c ",
    "bash -c ",
    "reset --hard",
    "push --force",
    "push -f ",
    " -delete",
    "rm -rf",
    "rm -r ",
    "mkfs",
    "dd if=",
    "> /etc/",
    "chmod 777",
    "curl.*|.*sh",
    "wget.*|.*sh",
]


def validate_command_structure(command: str) -> tuple:
    """
    Validate command structure to prevent shell injection.

    Returns:
        (is_valid, error_message) tuple
    """
    if not command or not command.strip():
        return True, ""

    sorted_chars = sorted(SHELL_METACHARACTERS, key=len, reverse=True)
    for char in sorted_chars:
        if char in command:
            return False, f"Blocked metacharacter '{char}' found in command"

    return True, ""


def is_dangerous(command: str) -> bool:
    """Check if a command is potentially dangerous using pattern matching."""
    cmd_lower = command.lower().strip()
    if not cmd_lower:
        return False

    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return True

    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()

    if not parts:
        return False

    base_cmd = Path(parts[0]).name
    if base_cmd in DANGEROUS_COMMANDS:
        return True

    if parts[0].startswith("-"):
        return True

    return False


READ_COMMANDS = {
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "wc",
    "sort",
    "uniq",
    "pwd",
    "which",
    "printenv",
    "date",
    "whoami",
    "diff",
    "file",
    "stat",
    "du",
    "df",
    "tree",
}

# Executables that dispatch their own trailing argv as a child process
# (find -exec/-ok..., xargs, and the process-control/tracing wrappers
# added for NEW-875's next slice, plus the WP2.1 group 1 closeout slice).
# Unconditionally HIGH_IMPACT at both classification sites below --
# content of the wrapped command is never parsed or evaluated, matching
# the pre-existing find/xargs precedent. `env` is handled by its own
# unconditional HIGH_IMPACT check (D-2: bare env leaks the environment, the
# argument-bearing form dispatches a child) and is deliberately NOT folded
# into this set. `su`, `doas`, and `proot` are handled separately
# as privilege wrappers and are always HIGH_IMPACT.
# `busybox` IS included despite being a multi-call binary -- a
# code-reviewer round for this change initially excluded it under a
# "closer to interpreter dispatch than a fixed wrapper" rationale that
# turned out to be false on direct probe: `busybox nice/env/timeout/
# chroot git push` all dispatch exactly like this set's other members,
# not like `sh -c`. Corrected rather than left standing (rule 6).
# This set retains compatibility labels for known wrappers. NEW-904's
# open-ended tail is structurally covered by the classifier's unknown-
# executable fallback: an unrecognized basename is HIGH_IMPACT.
_EXEC_WRAPPER_BASENAMES = frozenset({
    "find", "xargs", "timeout", "nice", "nohup", "setsid", "stdbuf",
    "chrt", "ionice", "strace", "flock", "watch",
    "script", "unshare", "taskset", "setarch", "ltrace", "unbuffer",
    "catchsegv", "time", "chroot", "nsenter", "busybox",
})


def _is_git_basename(base: str) -> bool:
    """True if a parsed argv[0] basename names git or a git-<subcommand>
    helper executable (e.g. git-upload-pack). Shared between
    classify_shell_command()'s HIGH_IMPACT check and
    _run_shell_command_structured()'s environment-isolation check (the
    execution primitive shell() calls) so the two can never classify and
    execute a command differently.
    """
    return base == "git" or base.startswith("git-")


def _is_termux_basename(base: str) -> bool:
    """True if a parsed argv[0] basename names any Termux:API executable
    (e.g. termux-sms-send, termux-telephony-call, termux-camera-photo,
    termux-torch). Whole-family conservative classification via basename
    prefix, mirroring _is_git_basename's style -- these binaries actuate
    real device hardware/telephony (confirmed present and resolvable via
    `command -v` on this device), and none of their variants is
    enumerated individually; the family as a whole is HIGH_IMPACT.
    """
    return base.startswith("termux-")


_NETWORK_CLIENT_BASENAMES = frozenset({
    # Confirmed INSTALLED on this device via `command -v` (WP2.1 group 9):
    # curl, wget, scp, rsync, ssh, sftp, ftp, telnet -- all real,
    # resolvable binaries that can push a local file to an arbitrary
    # remote host (curl -d @file, wget --post-file, scp, rsync,
    # ssh ... < file) with zero confirmation under yolo/any
    # no-confirmation-path caller (the same shape as NEW-918's termux-
    # sms-send finding, for network egress instead of device actuation).
    "curl", "wget", "scp", "rsync", "ssh", "sftp", "ftp", "telnet",
    # Included defensively though confirmed NOT installed on this device
    # today -- classification should not depend on local installation; a
    # future install or a different device shouldn't silently reopen this
    # gap.
    "nc", "ncat", "netcat",
})
# Opaque interpreter dispatch is handled structurally below; this set remains
# bounded to named network-client binaries.


def _is_network_client_basename(base: str) -> bool:
    """True if a parsed argv[0] basename names a network-client
    executable that can transfer a local file to a remote host (curl,
    wget, scp, rsync, ssh, sftp, ftp, telnet, nc/ncat/netcat). Whole-
    family conservative classification via basename, mirroring
    _is_termux_basename's style (WP2.1 group 9).
    """
    return base in _NETWORK_CLIENT_BASENAMES


# G15c explicit ACT allowlist for common build/lint/test tools (Ish decision,
# default-deny otherwise). Each runs project code or edits project files the
# same way the already-ACT pytest/npm/pip/node do (accepted NEW-904
# opaque-execution precedent; F2 "shell stays an audited ACT surface").
# Entries and why (repo evidence: core/linter.py runs ruff/flake8/mypy,
# docs/commands.md CODEY_LINTER, docs/installation.md uses cmake/clang;
# bench/tasks are pytest-only, so nothing here is bench-required):
#   ruff black isort flake8 mypy pylint  linters/formatters; `--fix`/format
#       edit files (an ACT-class write); flake8 plugins and mypy `plugins =`
#       execute project-configured code (group 14 note).
#   make cmake  run project Makefile/CMake recipes: arbitrary project code,
#       also via `make -f /dev/stdin` or `make SHELL=...` (same class).
#   cargo rustc gcc g++ cc clang go tsc javac  compilers/build drivers; build
#       scripts, proc-macros, `cargo run` and `go run` execute project code,
#       equal to `python3 script.py`.
#   pnpm yarn  JS package managers, same class as the ACT npm.
# NOT included: npx, curl/wget/ssh/scp/gh, su/doas/sudo, kill-family,
# interpreter inline modes, `sh -c`. pnpm/yarn `dlx|exec|create` and
# `go run`/`go install` of a remote `pkg@version` are the npx equivalent
# (fetch-and-run remote code) and stay HIGH_IMPACT.
# Residual (accepted, not fixed here): any allowlisted tool can execute
# arbitrary project code. A relative or non-system path (`./gcc`,
# `/tmp/x/gcc`) is not trusted by basename: only a bare name or a system
# bin directory qualifies, so a planted executable cannot borrow the label.
_BUILD_TOOL_ACT_BASENAMES = frozenset({
    "ruff", "black", "isort", "flake8", "mypy", "pylint",
    "make", "cmake", "cargo", "rustc", "gcc", "g++", "cc", "clang",
    "go", "tsc", "javac", "pnpm", "yarn",
})
# Shared system executable directories (G15d R8). Used by `_build_tool_is_act`
# and by the D-3 slash rule in `classify_shell_command`. Hard-coded, not
# derived from $PREFIX or sys.prefix, because the classifier must not read
# the environment. `/system/bin` is included because `/bin` is a symlink to it
# on this device. This is a naming convention, NOT an ownership boundary: the
# Termux bin dir is writable by the agent's own uid, so a write into it is a
# protected-path (G15e) question, not a classifier one.
_SYSTEM_BIN_DIRS = _protected_paths.SYSTEM_BIN_DIRS  # lifted to core/protected_paths.py (G15e)


def _argv0_in_system_dir(argv0: str) -> bool:
    """D-3: True only when `argv0` is an absolute path whose lexically
    normalized parent is in `_SYSTEM_BIN_DIRS`. Purely lexical (no
    filesystem access) so `classify_shell_command` stays free of discovery;
    `normpath` collapses `.`/`..`/`//`, so `/usr/bin/../../tmp/gcc` has parent
    `/tmp`. A leading `//usr/bin` is kept as-is by POSIX `normpath` and so
    fails closed. A symlink planted inside a system dir is a write-target
    problem (G15e), not something a lexical check can see.
    """
    if not argv0.startswith("/") or argv0.endswith("/"):
        return False
    return os.path.normpath(os.path.dirname(argv0)) in _SYSTEM_BIN_DIRS
# Any-token HIGH sets (an option operand can hide the real subcommand, so
# every token is tested). Beyond the npx-equivalents (`dlx|exec|create`):
#   node            `yarn node -e 1` / `pnpm node -p 1` / `yarn run node -e`
#                   dispatch to the node interpreter's inline-code mode.
#   env             `pnpm env use` downloads and installs a node runtime.
#   self-update     replaces the package manager binary (fetch + exec).
#   set             `yarn set version <url>` fetches and installs a release.
#   plugin          `yarn plugin import <url>` fetches and loads plugin code.
#   config          can set `script-shell` / registry / hooks.
#   explore         `yarn explore` / `npm explore` runs an arbitrary command in
#                   a dependency directory.
#   bin             `yarn bin` / `pnpm bin` dispatch-adjacent helper; blocked
#                   conservatively (listing binaries, no routine need).
# Accepted false positive: an operand or script named like one of these
# (`pnpm run node`, `yarn run config`) is HIGH_IMPACT, never the reverse.
#   link, ln        write symlinks into a global bin directory (same reasoning
#                   as the npm `link`/`ln`; `ln` is a defensive, UNVERIFIED
#                   alias because pnpm/yarn are not installed here, G15d 4.3).
_REMOTE_FETCH_SUBCOMMANDS = {
    "pnpm": {"dlx", "exec", "create", "node", "env", "self-update", "set",
             "plugin", "config", "explore", "bin", "link", "ln"},
    "yarn": {"dlx", "exec", "create", "node", "env", "self-update", "set",
             "plugin", "config", "explore", "bin", "link", "ln"},
}
# G15d 4.3 (G15b-13): with one of these verbs as ANY token, pnpm/yarn operands
# must be registry-name shaped or an explicit local path (no `github:`,
# `owner/repo`, `git+`, `https://`, `npm:alias@`), and a dash-led token that
# contains `:` (`--registry=https://x`) is refused. Their option grammar,
# aliases and abbreviations cannot be read from an artifact here (not
# installed, rule 12), so no table is invented: verb abbreviations stay an
# accepted residual (Ish, Q6, 2026-10-23). Accepted false positive:
# `--filter=foo:bar`.
_PNPM_YARN_FETCH_VERBS = frozenset({"add", "install", "i", "update", "up", "upgrade"})
# Publishing / registry-credential verbs (G15-F1). Tested against EVERY
# token after argv[0], not just the first non-dash one: an option can take an
# operand (`pnpm --dir . dlx x`, `pnpm -C . exec x`, `yarn --cwd . dlx x`,
# `pnpm --filter x exec y`), so "first non-dash token" can be an operand and
# hide the real subcommand. Accepted false positive: a script or argument
# literally named like a verb (`pnpm run exec`, `yarn run publish`) is
# HIGH_IMPACT, never the reverse.
_PUBLISH_VERBS = frozenset({
    "publish", "login", "logout", "adduser", "token", "owner", "yank",
})
# `cargo install` fetches and builds remote crates (build.rs runs): only an
# explicit local `--path` / `--list` / `--version`-style form stays ACT.
_CARGO_LOCAL_INSTALL_FLAGS = frozenset({"--path", "--list", "--help", "-h"})
# Residual (OPEN, not closed here): registry-name installs (`npm install foo`,
# `pip install foo`) and local-path installs still fetch/build and run code;
# `yarn plugin import <url>` / `yarn set version <url>` are HIGH via
# `_REMOTE_FETCH_SUBCOMMANDS`. npm policy: see `_npm_is_high` (G15d 4.1).


def _build_tool_is_act(parts) -> bool:
    """True when parts[0] is an allowlisted build tool and no remote-exec form."""
    exe = parts[0]
    base = Path(exe).name
    if base not in _BUILD_TOOL_ACT_BASENAMES:
        return False
    if exe != base and not _argv0_in_system_dir(exe):
        return False
    rest = parts[1:]
    if any(t in _REMOTE_FETCH_SUBCOMMANDS.get(base, ()) for t in rest):
        return False
    if base in {"cargo", "pnpm", "yarn"} and any(t in _PUBLISH_VERBS for t in rest):
        return False
    if base == "cargo" and "install" in rest:
        if any(t == "--git" or t.startswith(("--git=", "--registry", "--index"))
               for t in rest):
            return False
        if not any(t in _CARGO_LOCAL_INSTALL_FLAGS or t.startswith("--path=")
                   for t in rest):
            return False
    if base in {"pnpm", "yarn"} and any("script-shell" in t for t in rest):
        return False
    if base in {"pnpm", "yarn"} and any(t in _PNPM_YARN_FETCH_VERBS for t in rest):
        for t in rest:
            if t.startswith("-"):
                if ":" in t:
                    return False
            elif not (_NPM_NAME_SPEC_RE.fullmatch(t) or _LOCAL_PATH_RE.fullmatch(t)):
                return False
    if base == "go":
        if "get" in rest:
            return False
        if any(t in {"run", "install"} for t in rest) and any("@" in t for t in rest):
            return False
        # Executor-injection options (single- or double-dash, `=` attached):
        # -toolexec/-exec/-vettool run an arbitrary program; `generate` runs
        # //go:generate directives; `go env -w/-u` persists GOFLAGS etc.
        for t in rest:
            if t.startswith("-") and t.lstrip("-").split("=", 1)[0] in {
                "toolexec", "exec", "vettool",
            }:
                return False
        if "generate" in rest:
            return False
        if "env" in rest and any(
            t in {"-w", "-u", "--w", "--u"} for t in rest[rest.index("env"):]
        ):
            return False
        # Residual (OPEN, documented only): `go work`, `go mod download`,
        # `go build -overlay`, GOFLAGS/GOPROXY via env or go.env.
    if base == "cargo" and any(
        t == "--config" or t.startswith(("--config=", "-Z"))
        or "rustc-wrapper" in t.lower() or "rustc_wrapper" in t.lower()
        for t in rest
    ):
        # `--config build.rustc-wrapper=...` / `-Z` unstable flags run or
        # reconfigure arbitrary tools. (Residual: .cargo/config.toml in the
        # project and `[alias]` entries are not inspected.)
        return False
    if base in {"gcc", "g++", "cc", "clang", "rustc"} and "-wrapper" in rest:
        # Residual (OPEN, documented only): `-specs=`, `-B<dir>`,
        # `-fuse-ld=`, `-fplugin=`, rustc `-C linker=`.
        return False
    # `make --eval=STRING` / `-E STRING` evaluates make code (arbitrary
    # recipes) -> not ACT. Accepted false positive: `-C<dir with capital E>`.
    # `make -f x` / `SHELL=` stay ACT by the documented precedent.
    return not (base == "make" and any(
        t.startswith("--eval") or (not t.startswith("--") and t.startswith("-")
                                   and "E" in t[1:])
        for t in rest
    ))


_PIP_BASENAME_RE = re.compile(r"^pip\d*(?:\.\d+)*$")


# G15d 4.5 (G15b-20): `python -m <module>` runs that module's __main__ with the
# caller's authority, so `-m http.server` (a listener), `-m code`, `-m pdb`,
# `-m runpy` and every operator entry point (`restoricon_core.api.server`,
# `tools.provision_ai_agent_auth`, `bench.promote`, ...) were ACT. Only these
# modules stay ACT; the list is the set the repo actually invokes (repo grep of
# `python3? -m <module>`) plus a few standard dev tools. `pytest` is required
# by core/tdd.py. Anything else, a missing module, or a dotted submodule that
# is not listed (`pytest.__main__`) is HIGH_IMPACT.
_PYTHON_M_ALLOWED_MODULES = frozenset({
    "pytest", "pip", "venv", "unittest", "ruff", "black", "isort", "flake8",
    "mypy", "pylint", "py_compile", "compileall", "json.tool",
})
# python short options that take an operand (rest of the cluster or next token)
# and long options that take the next token (verified against `python3 --help-all`, Python 3.14).
_PYTHON_OPERAND_LONG_OPTIONS = frozenset({"--check-hash-based-pycs"})


def _python_scan_options(parts):
    """Walk a python argv the way the interpreter does and report what it will
    run. Returns ("code", None, None) for `-c`; ("module", name_or_None,
    args_after_module) for `-m` (name is None when no module follows);
    ("script", None, None) when a script path, `-` or `--` ends the options.
    Cluster rules (verified against `python3 --help-all`, Python 3.14): `c` = inline code,
    terminates the option list; `m` = module run, the module is the rest of
    the cluster or the next token; `W`/`X` take an operand (rest of the cluster
    or the next token), so `-Wc` is -W with argument `c`.
    """
    index = 1
    while index < len(parts):
        token = parts[index]
        if token == "--":
            return ("script", None, None)
        if not token.startswith("-") or token == "-":
            return ("script", None, None)
        if not token.startswith("--"):
            flags = token[1:]
            consumed = False
            for pos, letter in enumerate(flags):
                if letter == "c":
                    return ("code", None, None)
                if letter == "m":
                    rest = flags[pos + 1:]
                    if rest:
                        return ("module", rest, list(parts[index + 1:]))
                    if index + 1 < len(parts):
                        return ("module", parts[index + 1], list(parts[index + 2:]))
                    return ("module", None, [])
                if letter in "WX":
                    index += 1 if pos < len(flags) - 1 else 2
                    consumed = True
                    break
            if consumed:
                continue
            index += 1
            continue
        index += 2 if token in _PYTHON_OPERAND_LONG_OPTIONS else 1
    return ("script", None, None)


def _python_dash_m_pip_args(parts):
    """Tokens after `-m pip` in a python argv (any spelling of `-m`: `-m pip`,
    `-Im pip`, `-mpip`), or None when the module is not exactly `pip`."""
    kind, module, args = _python_scan_options(parts)
    if kind == "module" and module == "pip":
        return args
    return None


_PRIVILEGE_WRAPPER_BASENAMES = frozenset({"su", "doas", "proot"})
_SHELL_INTERPRETER_BASENAMES = frozenset({"sh", "bash"})
_SCRIPT_INTERPRETER_RE = re.compile(
    r"^(?:python(?:\d+(?:\.\d+)*)?|perl(?:\d+(?:\.\d+)*)?|ruby(?:\d+(?:\.\d+)*)?|node|nodejs)$"
)


def _shell_requests_command_string(parts) -> bool:
    """Whether sh/bash's leading option cluster requests `-c` execution."""
    option_operands = {"-O", "-o", "+O", "+o", "--init-file", "--rcfile"}
    index = 1
    while index < len(parts):
        token = parts[index]
        if token == "--":
            return False
        if not token.startswith(("-", "+")) or token in {"-", "+"}:
            return False
        if not token.startswith("--") and "c" in token[1:]:
            return True
        index += 2 if token in option_operands else 1
    return False


# Fail-closed option policy for node/nodejs/ruby/perl (G15c round 3). The old
# scanner stopped at the first non-dash token, which can be an option's
# OPERAND (`node -C x -e 1`, `ruby --disable gems -e x`), so each new
# operand-taking option re-opened the hole. These interpreters are now ACT
# only when every leading option is on a small explicit allowlist of options
# that take NO operand (or an attached, spec-checked one) and the first
# non-option token (script path / `-` / `--`) or end of argv is reached. ANY
# other leading option form is treated as possible inline code (HIGH_IMPACT).
# Node's table below was derived from `node --help` / `node --v8-options`
# (node v24.18.0, read on this device). ruby and perl are NOT installed here,
# so their tables are deliberately minimal, unverified-by-artifact and
# conservative: anything not listed fails closed.
# Accepted false positives: `node -r ts-node/register x.ts`,
# `node --env-file=.env x.js`, `node --conditions x`, `ruby -C dir x.rb`,
# `perl -I lib x.pl` (space operand) are HIGH_IMPACT.
_NODE_SAFE_BARE_OPTIONS = frozenset({
    "-v", "--version", "-h", "--help", "-i", "--interactive",
    "--inspect", "--inspect-brk", "--inspect-wait", "--test", "--test-only",
    "--watch", "--run", "--no-warnings", "--no-deprecation",
    "--trace-warnings", "--trace-deprecation", "--trace-uncaught",
    "--throw-deprecation", "--enable-source-maps", "--expose-gc",
    "--preserve-symlinks", "--experimental-vm-modules",
})
_NODE_SAFE_ATTACHED_PREFIXES = (
    "--run=",
    "--max-old-space-size=", "--stack-size=", "--test-name-pattern=",
    "--test-reporter=", "--disable-warning=",
)
# G15d 4.4 (G15b-16): `--inspect[=[host:]port]` (and -brk/-wait) binds the
# debugger, which evaluates arbitrary code for any client that connects, to
# `host`; the documented default host is 127.0.0.1 (node v24.18.0 `--help`).
# So the attached form is ACT only for a bare port or an explicit loopback
# literal. `localhost` is excluded (resolution is not under our control), and
# `--inspect-port=` is not on any safe list, so it stays HIGH_IMPACT.
_NODE_INSPECT_ATTACHED_RE = re.compile(
    r"^--inspect(?:-brk|-wait)?=(?:\d{1,5}|127\.0\.0\.1:\d{1,5}|\[::1\]:\d{1,5})$"
)
_RUBY_SAFE_BARE_OPTIONS = frozenset({
    "-v", "--version", "-h", "--help", "-w", "-W", "-W0", "-W1", "-W2",
})
_PERL_SAFE_BARE_OPTIONS = frozenset({
    "-v", "-h", "-w", "-W", "-X", "-t", "-T", "-l",
})
_PERL_MODULE_SPEC_BAD_RE = re.compile(r"[^\w:=,.+\-]")


def _non_python_interpreter_requests_inline_code(family: str, parts) -> bool:
    index = 1
    while index < len(parts):
        token = parts[index]
        index += 1
        if token in {"--", "-"} or not token.startswith("-"):
            # W1 (G15d review): the FIRST positional of `node` can be the
            # `inspect` subcommand (`node [opts] inspect ...`, listed in
            # `node --help`; verified on v24.18.0 that it is also taken after
            # `--` and after safe options). It starts the debugger client,
            # which can run `--probe ... --expr CODE`, `-e`/`-p` code, and
            # attach to `host:port`/pid, and everything after it is unscanned.
            # `inspect` anywhere AFTER the script (`node t.js inspect`) is a
            # script argument and stays ACT. (`node debug` is NOT special:
            # node treats it as a script file name.)
            first = parts[index] if token == "--" and index < len(parts) else token
            return family == "node" and first == "inspect"
        if family == "perl" and token == "-I" and index < len(parts) and (
            not parts[index].startswith("-")
        ):
            # `-I dir` (include path, kept ACT by the existing compat test):
            # the operand is a directory, never code. A dash-led next token
            # is NOT consumed, so `-I -e` still reaches the -e check.
            index += 1
            continue
        if family == "node":
            if (
                token in _NODE_SAFE_BARE_OPTIONS
                or token.startswith(_NODE_SAFE_ATTACHED_PREFIXES)
                or _NODE_INSPECT_ATTACHED_RE.fullmatch(token)
            ):
                continue
            # attached CommonJS preload only (`-r./x.js`, `--require=x`): a
            # module name, never inline code (`--import=` accepts `data:`
            # URLs and stays HIGH; bare `-r x` takes the next token).
            if (len(token) > 2 and token.startswith("-r")
                    and not token.startswith("--")) or token.startswith(
                        "--require="):
                continue
        elif family == "ruby":
            if token in _RUBY_SAFE_BARE_OPTIONS:
                continue
            # attached-operand library/include forms only (`-rcsv`, `-Ilib`);
            # a bare `-r`/`-I` takes the NEXT token, so it fails closed.
            if len(token) > 2 and token.startswith(("-r", "-I")) and not (
                token.startswith("--")
            ):
                continue
        elif family == "perl":
            if token in _PERL_SAFE_BARE_OPTIONS:
                continue
            if len(token) > 2 and token.startswith("-I"):
                continue
            # `-M'strict; system "id"'` injects code into the generated
            # `use` line: anything beyond a plain module spec is code.
            if (
                len(token) > 2 and token.startswith(("-M", "-m"))
                and not _PERL_MODULE_SPEC_BAD_RE.search(token[2:])
            ):
                continue
        return True
    return False


def _interpreter_requests_inline_code(base: str, parts) -> bool:
    """Conservatively identify inline-code/check modes in known interpreters."""
    if not _SCRIPT_INTERPRETER_RE.fullmatch(base):
        return False
    python_family = base.startswith("python")
    if not python_family:
        family = (
            "node" if base in {"node", "nodejs"}
            else "perl" if base.startswith("perl") else "ruby"
        )
        return _non_python_interpreter_requests_inline_code(family, parts)
    # `-c` = inline code; `-m` = module run, ACT only for the allowlisted
    # modules (G15d 4.5); a missing module is opaque too.
    kind, module, _args = _python_scan_options(parts)
    if kind == "code":
        return True
    if kind == "module":
        return module not in _PYTHON_M_ALLOWED_MODULES
    return False


# D-2 option (b): `printenv NAME` is readable only for these non-secret names.
# Bare `printenv` (whole environment) and any other NAME (for example an API key
# variable) is HIGH_IMPACT. Purely lexical: the classifier never reads the
# environment, so this is a name allowlist, not a value check.
_PRINTENV_SAFE_NAMES = frozenset({
    "HOME", "USER", "LOGNAME", "SHELL", "PWD", "OLDPWD", "LANG", "LC_ALL",
    "LC_CTYPE", "TERM", "TZ", "TMPDIR", "PREFIX", "PATH", "HOSTNAME", "SHLVL",
})


def _printenv_is_safe(parts) -> bool:
    """True when `printenv` has at least one operand, no dash-led token at all
    (so `--null`, `--help`, `-0` are refused) and every operand is an exact
    member of `_PRINTENV_SAFE_NAMES`.
    """
    args = parts[1:]
    if not args:
        return False
    return all(not a.startswith("-") and a in _PRINTENV_SAFE_NAMES for a in args)


@dataclass(frozen=True)
class _OptionTable:
    """Exact option grammar for one tool (G15d R7). Per-tool differences are
    data, not code, so a table edit cannot reintroduce a hand-written scan.
    Option names are accepted only as full exact tokens: GNU getopt, optparse
    and nopt all accept unambiguous long-option abbreviations (`sort --out=f`
    writes `f`, `sed --in` edits in place), so neither an exact-string
    denylist nor a prefix allow is sound.
    """
    short_bare: frozenset       # single letters that may be clustered
    short_operand: frozenset    # letters taking the rest of the token or the next token
    long_bare: frozenset        # exact names, must not carry "=value"
    long_operand: frozenset     # exact names: "=value" attached or value in the next token
    long_optional: frozenset = frozenset()  # exact names: optional attached "=value" only
    max_positionals: Optional[int] = None
    required: frozenset = frozenset()       # exact tokens that must appear before any "--"
    # Order constraint: option keys ("-e" for a short letter, "--expression"
    # for a long name) that may only be consumed AFTER every `required` token
    # has been seen. Needed for sed: GNU sed compiles each -e/--expression
    # script while still parsing options, so --sandbox only protects scripts
    # parsed after it (verified on sed 4.10: `sed -e 'w out' --sandbox f`
    # creates `out`).
    required_before: frozenset = frozenset()


def _walk_options(parts, table):
    """Walk argv[1:] against `table`; return (positionals, operands) or None
    when ANY token is off the table (the caller then fails closed to
    HIGH_IMPACT). Rules (G15d R2-R4): every token is scanned because GNU
    getopt permutes (`sort f -o out` is `-o out`); only a bare `--` ends
    option processing; short clusters are walked left to right so `-qf`
    cannot hide `-f`; a separate operand that starts with `-` fails closed
    (our parser and the tool's could disagree about operand boundaries);
    a bare `-` is a positional. No filesystem or environment access.
    """
    tokens = list(parts[1:])
    positionals = []
    operands = []
    seen_required = set()
    after_dd = False
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if after_dd or tok == "-" or not tok.startswith("-"):
            positionals.append(tok)
            continue
        if tok == "--":
            after_dd = True
            continue
        if tok.startswith("--"):
            name, eq, value = tok[2:].partition("=")
            if name in table.long_bare:
                if eq:
                    return None
                seen_required.add(tok)
            elif name in table.long_operand:
                if f"--{name}" in table.required_before and not table.required <= seen_required:
                    return None
                if eq:
                    operands.append(value)
                elif i < len(tokens) and not tokens[i].startswith("-"):
                    operands.append(tokens[i])
                    i += 1
                else:
                    return None
            elif name in table.long_optional:
                if eq:
                    operands.append(value)
            else:
                return None
            continue
        letters = tok[1:]
        for j, ch in enumerate(letters):
            if ch in table.short_bare:
                continue
            if ch in table.short_operand:
                if f"-{ch}" in table.required_before and not table.required <= seen_required:
                    return None
                rest = letters[j + 1:]
                if rest:
                    operands.append(rest)
                elif i < len(tokens) and not tokens[i].startswith("-"):
                    operands.append(tokens[i])
                    i += 1
                else:
                    return None
                break
            return None
    if not table.required <= seen_required:
        return None
    if table.max_positionals is not None and len(positionals) > table.max_positionals:
        return None
    return positionals, operands


# Option tables for the READ/ACT text tools (G15d section 3.3). Each was derived
# from the tool's own `--help` dump on this device (GNU sed 4.10, coreutils sort
# and uniq, tree, file 5.x) on 2026-10-23 and is pinned exactly by a test, so a
# change is a deliberate reviewed edit. Anything off a table is HIGH_IMPACT.
# Deliberately absent (they write files, run programs, or name more argv/paths
# indirectly): sed -i/--in-place/-f/--file (and --follow-symlinks, only useful
# with -i); sort -o/--output/--compress-program/-T/--files0-from/--random-source/
# --batch-size/--parallel; uniq's second positional (the OUTPUT file); tree
# -o/-R/-H/-T/-X/-J/--fromfile/--fromtabfile/--gitfile/--infofile/--hintro/
# --houtro/--charset/--timefmt; file -C/-m/-f/-c/-e/-F/-P/-S/-d/-l.
# sed is ACT only with the exact token `--sandbox` (sed itself then rejects the
# e/r/R/w/W commands and s///e, s///w; verified by probe, and it does NOT block
# -i, which is why -i stays off the table).
_SED_TABLE = _OptionTable(
    short_bare=frozenset("nErszu"),
    short_operand=frozenset("el"),
    long_bare=frozenset({
        "quiet", "silent", "debug", "posix", "regexp-extended", "separate",
        "sandbox", "unbuffered", "null-data", "help", "version",
    }),
    long_operand=frozenset({"expression", "line-length"}),
    required=frozenset({"--sandbox"}),
    required_before=frozenset({"-e", "--expression"}),
)
_SORT_TABLE = _OptionTable(
    short_bare=frozenset("bdfgiMhnRrVcCmsuz"),
    short_operand=frozenset("ktS"),
    long_bare=frozenset({
        "ignore-leading-blanks", "dictionary-order", "ignore-case",
        "general-numeric-sort", "ignore-nonprinting", "month-sort",
        "human-numeric-sort", "numeric-sort", "random-sort", "reverse",
        "version-sort", "merge", "stable", "unique", "zero-terminated",
        "debug", "help", "version",
    }),
    long_operand=frozenset({"key", "field-separator", "sort", "buffer-size"}),
    long_optional=frozenset({"check"}),
)
_UNIQ_TABLE = _OptionTable(
    short_bare=frozenset("cdDiuz"),
    short_operand=frozenset("fsw"),
    long_bare=frozenset({
        "count", "repeated", "unique", "ignore-case", "zero-terminated",
        "help", "version",
    }),
    long_operand=frozenset({"skip-fields", "skip-chars", "check-chars"}),
    long_optional=frozenset({"all-repeated", "group"}),
    max_positionals=1,
)
_TREE_TABLE = _OptionTable(
    short_bare=frozenset("adlfxqNQpugshDFvtcUriASnC"),
    short_operand=frozenset("LPI"),
    long_bare=frozenset({
        "noreport", "dirsfirst", "filesfirst", "prune", "du", "si",
        "ignore-case", "matchdirs", "metafirst", "inodes", "device",
        "nolinks", "condense", "gitignore", "version", "help",
    }),
    long_operand=frozenset({"sort", "filelimit"}),
)
_FILE_TABLE = _OptionTable(
    short_bare=frozenset("bikLhnN0prszvZ"),
    short_operand=frozenset(),
    long_bare=frozenset({
        "brief", "mime", "mime-type", "mime-encoding", "extension", "apple",
        "keep-going", "dereference", "no-dereference", "no-buffer", "no-pad",
        "print0", "preserve-date", "raw", "special-files", "uncompress",
        "uncompress-noreport", "version", "help",
    }),
    long_operand=frozenset(),
)
_TEXT_TOOL_TABLES = {
    "sed": _SED_TABLE,
    "sort": _SORT_TABLE,
    "uniq": _UNIQ_TABLE,
    "tree": _TREE_TABLE,
    "file": _FILE_TABLE,
}


# --- G15d 4.2 (G15b-14): pip per-subcommand option tables ---------------------
# pip 26.2.1 (read from `pip <subcommand> --help` on this device, 2026-10-23).
# optparse accepts unambiguous long-option abbreviations (`--find-l=<dir>`) and
# short clusters (`-qf <dir>`), so the old marker scan (`-i`/`-f` prefix test,
# URL substrings) could be evaded; `--python <interp>` runs an arbitrary
# interpreter and `--target/--root/--prefix/--src/--report/--log` write
# arbitrary paths. New policy: the subcommand must be exactly one of
# `_PIP_SUBCOMMAND_TABLES`, every option must be an exact full token on that
# subcommand's table (`_walk_options`), and every positional / consumed operand
# must be name-shaped or an explicit local path, so URL and VCS specs fail
# without a marker list. `-e` is a bare flag for `list` and an operand option
# for `install`, which is why the tables are per subcommand.
# Residuals kept by decision: a local requirements file can itself contain
# `--index-url`/URL lines, a bare PyPI name fetches and builds code, and a
# local path installs local code (ceiling-equivalent, consolidated G15b-13).
_PIP_GLOBAL_BARE_LONG = frozenset({
    "quiet", "verbose", "version", "help", "no-color", "no-input",
    "disable-pip-version-check", "isolated", "no-cache-dir",
})
_PIP_GLOBAL_TABLE = _OptionTable(
    short_bare=frozenset("qvVh"), short_operand=frozenset(),
    long_bare=_PIP_GLOBAL_BARE_LONG, long_operand=frozenset(),
)
_PIP_INSTALL_TABLE = _OptionTable(
    short_bare=frozenset("UIqvhV"),
    short_operand=frozenset("rce"),
    long_bare=_PIP_GLOBAL_BARE_LONG | frozenset({
        "no-deps", "dry-run", "user", "upgrade", "force-reinstall",
        "ignore-installed", "ignore-requires-python", "no-build-isolation",
        "check-build-dependencies", "break-system-packages", "compile",
        "no-compile", "no-warn-script-location", "no-warn-conflicts",
        "require-hashes", "no-require-hashes", "no-clean", "pre",
        "prefer-binary", "no-index",
    }),
    long_operand=frozenset({"requirement", "constraint", "editable"}),
)
# `pip download` has no --dry-run/--user/--upgrade/... (help dump); `-d/--dest`
# is deliberately absent (writes an arbitrary directory).
_PIP_DOWNLOAD_TABLE = _OptionTable(
    short_bare=frozenset("qvhV"),
    short_operand=frozenset("rc"),
    long_bare=_PIP_GLOBAL_BARE_LONG | frozenset({
        "no-deps", "ignore-requires-python", "no-build-isolation",
        "check-build-dependencies", "require-hashes", "no-require-hashes",
        "no-clean", "pre", "prefer-binary", "no-index",
    }),
    long_operand=frozenset({"requirement", "constraint"}),
)
_PIP_UNINSTALL_TABLE = _OptionTable(
    short_bare=frozenset("yqvhV"),
    short_operand=frozenset("r"),
    long_bare=_PIP_GLOBAL_BARE_LONG | frozenset({"yes", "break-system-packages"}),
    long_operand=frozenset({"requirement"}),
)
# `list -i/-f/--path/--exclude` and the index options are off the table.
_PIP_LIST_TABLE = _OptionTable(
    short_bare=frozenset("ouelqvhV"),
    short_operand=frozenset(),
    long_bare=_PIP_GLOBAL_BARE_LONG | frozenset({
        "outdated", "uptodate", "editable", "local", "user", "not-required",
        "exclude-editable", "include-editable", "pre", "prefer-binary",
        "no-index",
    }),
    long_operand=frozenset({"format"}),
)
_PIP_SHOW_TABLE = _OptionTable(
    short_bare=frozenset("fqvhV"), short_operand=frozenset(),
    long_bare=_PIP_GLOBAL_BARE_LONG | frozenset({"files"}),
    long_operand=frozenset(),
)
# `freeze -r/--requirement`, `--path`, `--exclude` are off the table.
_PIP_FREEZE_TABLE = _OptionTable(
    short_bare=frozenset("lqvhV"), short_operand=frozenset(),
    long_bare=_PIP_GLOBAL_BARE_LONG | frozenset({
        "local", "user", "all", "exclude-editable",
    }),
    long_operand=frozenset(),
)
_PIP_CHECK_TABLE = _PIP_GLOBAL_TABLE
_PIP_SUBCOMMAND_TABLES = {
    "install": _PIP_INSTALL_TABLE,
    "download": _PIP_DOWNLOAD_TABLE,
    "uninstall": _PIP_UNINSTALL_TABLE,
    "list": _PIP_LIST_TABLE,
    "show": _PIP_SHOW_TABLE,
    "freeze": _PIP_FREEZE_TABLE,
    "check": _PIP_CHECK_TABLE,
}
_PIP_LIST_FORMATS = frozenset({"columns", "freeze", "json"})
# Operand shapes (rule 12 note: the PEP 508 name grammar is
# `[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?`; extras and comparison operators
# are from PEP 508 / PEP 440). Anything containing `:`, `@`, `;`, `/` (except
# the relative-path form) or whitespace does not match, which is what rejects
# `git+https://...`, `https://...`, `file:...` and `pkg @ https://...`.
_PIP_NAME_SPEC_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
    r"(?:\[[A-Za-z0-9._,-]+\])?"
    r"(?:(?:===|==|~=|!=|<=|>=|<|>)[A-Za-z0-9._*+!-]+"
    r"(?:,(?:===|==|~=|!=|<=|>=|<|>)[A-Za-z0-9._*+!-]+)*)?$"
)
# Explicitly local: `.`, `..`, `./x`, `../x`, `/abs`, `~/x`, optionally with a
# trailing `[extras]` on the dot forms (`.[dev]`); no scheme colon, no `;`.
_LOCAL_PATH_RE = re.compile(
    r"^(?:\.{1,2}(?:\[[A-Za-z0-9._,-]+\])?|(?:\.{1,2}/|/|~/)[^\s:;]*)$"
)
# pip only: `requirements/dev.txt`. pip never treats `a/b` as a remote
# shorthand (npm does), so this is not reused for npm.
_PIP_REL_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+/?$")


def _pip_operand_ok(value: str) -> bool:
    return bool(
        _PIP_NAME_SPEC_RE.fullmatch(value)
        or _LOCAL_PATH_RE.fullmatch(value)
        or _PIP_REL_PATH_RE.fullmatch(value)
    )


def _pip_is_high(args) -> bool:
    """True unless `args` (the tokens after `pip` / `pip3.N` / `python -m pip`)
    are a fully table-conformant invocation (G15d 4.2). Global flags may precede
    the subcommand (exact tokens only); the first non-dash token must be exactly
    one of `_PIP_SUBCOMMAND_TABLES`; a bare `pip`, `pip --version` or
    `pip --help` has no subcommand and is ACT. Anything off a table, an
    unknown subcommand, or an operand that is not name-shaped / local is HIGH.
    """
    args = list(args)
    split = next((i for i, t in enumerate(args) if not t.startswith("-")), len(args))
    # A bare `--` before the subcommand is refused outright: whether pip still
    # treats the next token as a subcommand is not something we rely on.
    if "--" in args[:split]:
        return True
    walked = _walk_options(["pip", *args[:split]], _PIP_GLOBAL_TABLE)
    if walked is None or walked[0] or walked[1]:
        return True
    if split == len(args):
        return False
    table = _PIP_SUBCOMMAND_TABLES.get(args[split])
    if table is None:
        return True
    walked = _walk_options(["pip", *args[split + 1:]], table)
    if walked is None:
        return True
    positionals, operands = walked
    if args[split] == "list":
        return bool(positionals) or not set(operands) <= _PIP_LIST_FORMATS
    return not all(_pip_operand_ok(v) for v in (*positionals, *operands))



# --- G15d 4.1 (G15b-15): npm exact-subcommand / exact-option allowlist --------
# npm 11.21.1 (lib/utils/cmd-list.js and @npmcli/config definitions, read on
# this device 2026-10-23). npm resolves any unambiguous PREFIX of a command or
# alias (`npm pub`, `npm publ` = publish, `npm tok` = token, `npm own` = owner,
# `npm c` = config, `npm add-user` = adduser; `abbrev(commands + aliases)`) and
# nopt abbreviates options (`--node-opt`), so an exact-string verb denylist is
# unsound. Policy: the first non-dash token must be EXACTLY one of
# `_NPM_ACT_SUBCOMMANDS`; before it only exact flags from `_NPM_SAFE_FLAGS`
# may appear (no operand-taking option, so the first non-dash token IS the
# subcommand); flags may also appear after it, from the same list. Every
# non-dash operand must be name-shaped or an explicit local path (no
# `git+`, `github:`, `owner/repo`, `https://`, `file:`, `npm:alias@`).
# Tokens after a bare `--` are script arguments only for the script-running
# commands (`run`, `test`, `start`, ...) and are not examined there; for every
# other command they are npm positionals and are validated like any operand.
_NPM_ACT_SUBCOMMANDS = frozenset({
    "install", "i", "add", "ci", "test", "t", "start", "stop", "restart",
    "run", "run-script", "rebuild", "rb", "pack", "ls", "list", "ll",
    "outdated", "audit", "why", "explain", "view", "v", "info", "show",
    "config", "init", "uninstall", "remove", "rm", "update", "up", "dedupe",
    "prune",
})
# Commands whose tokens after `--` belong to the project's own script.
_NPM_SCRIPT_SUBCOMMANDS = frozenset({
    "run", "run-script", "test", "t", "start", "stop", "restart",
})
# Commands that take registry-name / local-path operands.
_NPM_NAME_OPERAND_SUBCOMMANDS = frozenset({
    "install", "i", "add", "uninstall", "remove", "rm", "update", "up",
    "view", "v", "info", "show", "why", "explain", "pack", "rebuild", "rb",
    "ls", "list", "ll", "outdated", "audit", "dedupe", "prune",
})
# Boolean flags only (verified in the definitions dump: each is a Boolean
# config or a shorthand for one). Deliberately absent: -g/--global,
# -w/--workspace, -C/--prefix, -L/--location, -c/--call, -f/--force,
# --registry, --script-shell, --node-options, --userconfig, --globalconfig,
# --cache, --otp, --proxy, --cafile, --logs-dir, --init-module and every
# other option that takes a value, writes a path or changes trust.
_NPM_SAFE_FLAGS = frozenset({
    "-q", "-s", "-d", "--quiet", "--silent", "--verbose", "--json",
    "--no-audit", "--no-fund", "--legacy-peer-deps", "--dry-run", "--offline",
    "--prefer-offline", "--save", "--save-dev", "-D", "-S", "-E",
    "--save-exact", "--no-save", "--ignore-scripts", "--no-package-lock",
    "--version", "-v", "--help", "-h",
    # `ls`/`outdated` display flags and `init -y`.
    "-l", "--long", "-a", "--all", "-p", "--parseable", "-y", "--yes",
})
# `--name=value` forms: exact names only, value from a conservative charset
# (no `:` or `/`, so no URL or path).
_NPM_SAFE_VALUE_FLAGS = frozenset({
    "loglevel", "omit", "include", "audit", "fund", "progress",
    "package-lock", "ignore-scripts", "save", "legacy-peer-deps", "json",
})
_NPM_FLAG_VALUE_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
# Registry name with optional version/tag; deliberately rejects `owner/repo`
# (GitHub shorthand), `github:`, `git+`, `git@host:`, `npm:alias@`,
# `https://`, `file:`, `link:` and tarball URLs (npm-package-arg routes every
# remote form through a `:` or `/`, which this pattern excludes).
_NPM_NAME_SPEC_RE = re.compile(
    r"^(?:@[A-Za-z0-9][A-Za-z0-9._~-]*/)?[A-Za-z0-9][A-Za-z0-9._~-]*"
    r"(?:@[A-Za-z0-9._^~<>=*|-]+)?$"
)
_NPM_SCRIPT_NAME_RE = re.compile(r"^[A-Za-z0-9:_.-]+$")
_NPM_CONFIG_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
# `npm config get <key>` must not read a credential out of ~/.npmrc.
_NPM_CONFIG_SECRET_KEY_RE = re.compile(r"auth|token|pass|secret|cert|key|otp|^_", re.IGNORECASE)


def _npm_flag_ok(token: str) -> bool:
    if token in _NPM_SAFE_FLAGS:
        return True
    name, eq, value = token.partition("=")
    return bool(
        eq and name.startswith("--") and name[2:] in _NPM_SAFE_VALUE_FLAGS
        and _NPM_FLAG_VALUE_RE.fullmatch(value)
    )


def _npm_operand_ok(value: str) -> bool:
    return bool(_NPM_NAME_SPEC_RE.fullmatch(value) or _LOCAL_PATH_RE.fullmatch(value))


def _npm_is_high(parts) -> bool:
    """True unless the npm argv is an exact allowlisted subcommand with only
    allowlisted flags and well-shaped operands (G15d 4.1). No subcommand at
    all (`npm`, `npm --version`, `npm -h`) is ACT; a `--` before the
    subcommand is HIGH (verified npm 11.21.1: `npm -- nonexistentcmd` answers
    `Unknown command`, i.e. the first word after `--` is still dispatched as
    the command, lib/npm.js `parsedArgv.remain`)."""
    rest = list(parts[1:])
    tail = []
    had_dd = "--" in rest
    if had_dd:
        cut = rest.index("--")
        rest, tail = rest[:cut], rest[cut + 1:]
    sub = None
    operands = []
    for t in rest:
        if t.startswith("-"):
            if not _npm_flag_ok(t):
                return True
        elif sub is None:
            sub = t
        else:
            operands.append(t)
    if sub is None:
        return had_dd
    if sub not in _NPM_ACT_SUBCOMMANDS:
        return True
    if sub in _NPM_SCRIPT_SUBCOMMANDS:
        if sub in {"run", "run-script"}:
            return not (len(operands) == 1 and _NPM_SCRIPT_NAME_RE.fullmatch(operands[0]))
        return bool(operands)
    if sub in _NPM_NAME_OPERAND_SUBCOMMANDS:
        return not all(_npm_operand_ok(v) for v in (*operands, *tail))
    if tail:
        return True
    if sub == "ci" or sub == "init":
        return bool(operands)
    if sub == "config":
        if operands in (["list"], ["ls"]):
            return False
        return not (
            len(operands) == 2 and operands[0] == "get"
            and _NPM_CONFIG_KEY_RE.fullmatch(operands[1])
            and not _NPM_CONFIG_SECRET_KEY_RE.search(operands[1])
        )
    # Deliberate fail-closed backstop: every _NPM_ACT_SUBCOMMANDS entry is
    # handled above, so this is reached only if a subcommand is added to the
    # allowlist without a rule here (a mutation pass showed it carries weight).
    return True


def classify_shell_command(command: str) -> str:
    """Classify a shell command into one of the three gateway authority
    classes (READ/ACT/HIGH_IMPACT), for use with ActionGateway.gate_exec().

    Checked in this order, deliberately:
      1. DANGEROUS_PATTERNS (the existing, narrower, irreversible/
         security-relevant subset — NOT the broader DANGEROUS_COMMANDS
         set used by is_dangerous()'s warn-and-confirm path) -> HIGH_IMPACT.
         Pattern matches always win before executable classification.
      2. Every direct git or git-* executable -> HIGH_IMPACT. Git
         configuration, hooks, and helpers can introduce opaque effects,
         including for queries. This conservative boundary does not claim
         every invocation is destructive; no discovery is performed.
      2b. Every direct termux-* executable (the whole Termux:API family --
         e.g. termux-sms-send, termux-telephony-call, termux-camera-photo,
         termux-torch) -> HIGH_IMPACT. Whole-family conservative
         classification via basename prefix, matching the git check's
         style, not a hand-picked dangerous subset: these actuate real
         device hardware/telephony and none is individually enumerated.
      2c. Every direct network-client executable (_NETWORK_CLIENT_BASENAMES:
         curl, wget, scp, rsync, ssh, sftp, ftp, telnet, nc, ncat,
         netcat) -> HIGH_IMPACT. Whole-family conservative classification
         via basename, matching the termux-* check's style -- these can
         exfiltrate a local file to an arbitrary remote host with zero
         confirmation under yolo. Opaque interpreter dispatch is classified
         structurally below.
      3. Direct exec-wrapper basenames (_EXEC_WRAPPER_BASENAMES: find,
         xargs, timeout, nice, nohup, setsid, stdbuf, chrt, ionice,
         strace, flock, watch, script, unshare, taskset, setarch,
         ltrace, unbuffer, catchsegv, time, chroot, nsenter, busybox)
         and env in every form -> HIGH_IMPACT. These can dispatch
         children or produce other effects; bare env prints the whole
         environment (D-2). No child is parsed.
      3b. argv[0] containing `/` outside _SYSTEM_BIN_DIRS (D-3) -> HIGH_IMPACT
         (checked first, lexically). awk in any form, `printenv` outside the
         name allowlist, and sed/sort/uniq/tree/file with any option off
         their exact _OptionTable -> HIGH_IMPACT (G15d).
      3c. G15d Unit B: `python -m <module>` is ACT only for
         _PYTHON_M_ALLOWED_MODULES; pip (any pipN.M, `python -m pip`) only for
         an exact subcommand with exact per-subcommand options and name-shaped
         operands; npm only for an exact allowlisted subcommand (npm's own
         abbreviations/aliases such as `npm pub` are HIGH_IMPACT); node
         `--inspect*=` only for a port or a loopback host; pnpm/yarn
         add/install operands must be name-shaped or local.
      4. Privilege wrappers and opaque shell/interpreter inline execution ->
         HIGH_IMPACT. Known READ/ACT commands retain their labels; every other
         executable basename defaults to HIGH_IMPACT.
    """
    cmd_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return HIGH_IMPACT

    try:
        parts = shlex.split(command)
    except ValueError:
        return HIGH_IMPACT

    if not parts:
        return ACT

    base = Path(parts[0]).name
    # D-3 (G15d): any argv[0] containing `/` must sit in a system bin dir, so
    # a planted/symlinked `./ls` or `/tmp/x/git` cannot borrow a READ/ACT
    # label by basename. Lexical only (no discovery); the bare-name PATH
    # shadow variant is checked in shell() (_command_shadows_system_binary).
    if "/" in parts[0] and not _argv0_in_system_dir(parts[0]):
        return HIGH_IMPACT
    if (
        _is_git_basename(base)
        or _is_termux_basename(base)
        or _is_network_client_basename(base)
        or base in _EXEC_WRAPPER_BASENAMES
        or base in _PRIVILEGE_WRAPPER_BASENAMES
    ):
        return HIGH_IMPACT
    # D-2 option (b): `env` in every form is HIGH_IMPACT. Bare `env` prints
    # the whole environment (API keys, tokens), so it is a secret read, not a
    # harmless introspection; the argument-bearing form dispatches a child.
    if base == "env":
        return HIGH_IMPACT
    if base == "command" and len(parts) > 1:
        return HIGH_IMPACT
    if base in _SHELL_INTERPRETER_BASENAMES and _shell_requests_command_string(parts):
        return HIGH_IMPACT
    if _interpreter_requests_inline_code(base, parts):
        return HIGH_IMPACT
    if base == "npm" and _npm_is_high(parts):
        return HIGH_IMPACT
    if _PIP_BASENAME_RE.fullmatch(base) and _pip_is_high(parts[1:]):
        return HIGH_IMPACT
    if base.startswith("python"):
        pip_args = _python_dash_m_pip_args(parts)
        if pip_args is not None and _pip_is_high(pip_args):
            return HIGH_IMPACT
    # awk (gawk 5.4.1) is HIGH in every form: -f/-e/-E/-i/-l, system(),
    # getline from commands and output redirection make it a general
    # executor/writer, and its --sandbox was not probed (G15d 3.3).
    if base == "awk":
        return HIGH_IMPACT
    if base == "printenv" and not _printenv_is_safe(parts):
        return HIGH_IMPACT
    table = _TEXT_TOOL_TABLES.get(base)
    if table is not None and _walk_options(parts, table) is None:
        return HIGH_IMPACT
    if base in READ_COMMANDS:
        return READ
    if (
        base in ALLOWED_COMMANDS
        or base in DANGEROUS_COMMANDS
        or base in _SHELL_INTERPRETER_BASENAMES
        or _SCRIPT_INTERPRETER_RE.fullmatch(base)
        or base == "command"
        or _build_tool_is_act(parts)
        # `pip3.11` / `pip3.14` (W5): the pip clause above already accepted
        # the arguments; only the exact names pip/pip3 are in ALLOWED_COMMANDS.
        or _PIP_BASENAME_RE.fullmatch(base)
    ):
        return ACT
    return HIGH_IMPACT


_GIT_METADATA_SCANNED_READ = {"sort", "uniq", "tree", "file"}  # READ_COMMANDS members
# with a verified file-write option (sort -o/--output=, uniq's positional
# OUTPUT arg, tree -o, file -C -m, each confirmed via --help); every other
# READ_COMMANDS member has no write-capable flag (verified via --help on
# every member, not assumed) and keeps the existing read exemption.


def _shell_command_targets_git_metadata(command: str, *, cwd: Path, roots) -> bool:
    """Detect whether a non-git shell command's argv references a path
    under the workspace or CODE_DIR's own `.git` directory (NEW-894
    follow-up). Used to escalate the command's authority to HIGH_IMPACT
    (not deny outright: a shell
    command's argv token can equally be a write target, a legitimate
    read source, an exclusion pattern, or crash-recovery cleanup like
    `rm .git/index.lock`, so only Filesystem's own single-target mutation
    path (core/filesystem.py::_reject_git_metadata_mutation) can safely
    deny outright; this generic argv scan cannot).

    Exemptions:
    - git/git-* basenames: already HIGH_IMPACT and environment-isolated
      (NEW-893) via a separate mechanism; this scan is a no-op for them.
    - _EXEC_WRAPPER_BASENAMES members/argument-bearing env: already
      HIGH_IMPACT from classify_shell_command(); this scan running on
      them changes nothing (HIGH_IMPACT -> HIGH_IMPACT), so no special
      exemption is carved out for the legitimate
      `find . -path ./.git -prune` idiom.
    - Ordinary READ_COMMANDS members minus _GIT_METADATA_SCANNED_READ:
      verified via --help to have no write-capable option; exempted so
      `cat .git/config`/`grep .git x`/`ls .git` stay frictionless reads.

    Named residuals (documented, not silently claimed covered):
    - A READ_COMMANDS member wrapped in a non-exempt basename
      (`proot cat .git/config`) loses its read exemption -- same
      argv[0]-only blind spot classify_shell_command() already has for
      wrapper basenames outside _EXEC_WRAPPER_BASENAMES (NEW-875;
      `timeout`/`nice`/etc. are now covered unconditionally by that set
      instead; `proot` itself remains one of the deliberately-deferred
      names, see _EXEC_WRAPPER_BASENAMES's comment). Directionally safe
      here (over-escalates a read) rather than unsafe.
    - sort/uniq/tree/file are scanned on every argument, not just their
      specific output-option value -- a .git-path read source given to
      one of them is escalated too. Accepted; confirm-gated, not blocked.
    - Attached short options with no separator (`-o.git/x`) and
      sed/awk script-embedded secondary writes (`sed -n 'w .git/config'`,
      an awk `print > ".git/x"` inside a script argument) are not
      inspected -- only literal argv path tokens (and their `=`-split
      RHS) are. Same trade-off classify_shell_command() already accepts
      for find/xargs (not a full argument-grammar parser per tool).
    - Interpreter-internal writes (`python3 -c "open('.git/config','w')"`)
      are invisible to argv inspection by construction.
    - Nested/submodule .git elsewhere in the tree: out of scope here, same
      caveat already logged against NEW-894. Closed for non-exempt bases by
      the G15e protected-path scan in shell() (`_shell_command_targets_protected_path`,
      any `.git` component, no root limit); this scan is unchanged.
    - `.git` used as an exclusion/archival pattern (`tar --exclude=.git`)
      is escalated to require confirmation even though it's common and
      harmless -- the accepted cost of a generic scan; adds a prompt,
      doesn't block.
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    if not parts:
        return False

    base = Path(parts[0]).name
    if _is_git_basename(base):
        return False
    if base in READ_COMMANDS and base not in _GIT_METADATA_SCANNED_READ:
        return False

    resolved_roots = [Path(r).resolve() for r in roots]

    def _hits_git(path_obj) -> bool:
        for root in resolved_roots:
            try:
                rel = path_obj.relative_to(root)
            except ValueError:
                continue
            if rel.parts and rel.parts[0] == ".git":
                return True
        return False

    for token in parts:
        candidates = [token]
        if "=" in token:
            candidates.append(token.split("=", 1)[1])  # dd of=/if=, --output=, --exclude=, etc.
        for candidate in candidates:
            if not candidate:
                continue
            # Path() itself does not validate content (e.g. an embedded
            # NUL constructs fine); the known failure mode is
            # resolve()/lstat() below, not construction, so there is no
            # construction-stage try/except here.
            base_path = Path(candidate)
            base_path = base_path if base_path.is_absolute() else cwd / base_path
            # Lexical form first: catches an already-planted symlink AT the
            # .git-rooted path itself, without following it.
            lexical = Path(os.path.normpath(str(base_path)))
            if _hits_git(lexical):
                return True
            try:
                # Resolved form: catches an indirect symlink elsewhere that
                # redirects INTO .git/.
                resolved = base_path.resolve(strict=False)
            except (OSError, ValueError):
                # resolve() can fail on pathological input -- confirmed on
                # this device: an embedded NUL raises ValueError
                # ("embedded null character in path") from the underlying
                # lstat(); other platforms may raise OSError for a symlink
                # loop or an over-length component (neither reproduces a
                # raise on this device's resolve(), per round testing). The
                # lexical check above already ruled out a direct .git
                # match; a resolve() failure here means an indirect
                # symlink redirect cannot be verified, so fail closed
                # (escalate) rather than silently treating it as safe.
                return True
            if _hits_git(resolved):
                return True
    return False


# D-2 option (b), read side of the credential set (G15d 3.2b). Kept as clearly
# named module data so G15e can lift it into a shared protected-path module.
# Entries under $HOME (equal or descendant). Why: private keys, API/registry
# tokens, cloud and VCS credential stores, and shell history (can embed
# secrets typed on a command line).
# The credential data below was lifted verbatim into core/protected_paths.py
# (G15e, the single shared protected-path set) and is re-exported under the
# old names so the G15d scan and its tests are unchanged.
_CRED_HOME_ENTRIES = _protected_paths.CRED_HOME_ENTRIES
_CRED_STATE_ENTRIES = _protected_paths.CRED_STATE_ENTRIES
_CRED_STATE_PATTERNS = _protected_paths.CRED_STATE_PATTERNS
_CRED_BASENAME_PATTERNS = _protected_paths.CRED_BASENAME_PATTERNS
# Recursive content readers: any directory operand is treated as recursive, so
# a path that is an ancestor of a credential entry also escalates (no flag
# parsing: abbreviations and clusters would be the hand-scan trap again).
_CRED_ANCESTOR_BASES = frozenset({"grep", "egrep", "fgrep", "rgrep", "diff", "cp"})
_CRED_RECURSIVE_GREP = frozenset({"grep", "egrep", "fgrep", "rgrep"})
_CRED_PATH_ALIASES = _protected_paths.CRED_PATH_ALIASES
_cred_canon = _protected_paths.canon


def _path_candidates(command: str, *, cwd: Path, home: Path):
    """Turn a command's argv (after argv[0]) into path candidates.

    Returns a list of (lexical, resolved) canonical string pairs, or None as
    the fail-closed signal (NUL byte, or resolve() failure). Per token the
    candidates are the token, the text after its first `=`, and for a single
    dash token longer than two characters the text after the first two
    characters (attached short operand such as `-f/path`). A leading `~`,
    `$HOME` or `${HOME}` is expanded with the PASSED home only (no environment
    reads); relative paths are joined to `cwd`. No READ-command exemption:
    READ commands are exactly the readers. Reusable by G15e's write-target scan.
    """
    if "\x00" in command:
        return None
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    home_str = str(home)
    out = []
    for token in parts[1:]:
        cands = [token]
        if "=" in token:
            cands.append(token.split("=", 1)[1])
        if token.startswith("-") and not token.startswith("--") and len(token) > 2:
            cands.append(token[2:])
        for cand in cands:
            if not cand:
                continue
            if cand == "~" or cand.startswith("~/"):
                cand = home_str + cand[1:]
            elif cand == "$HOME" or cand.startswith("$HOME/"):
                cand = home_str + cand[5:]
            elif cand == "${HOME}" or cand.startswith("${HOME}/"):
                cand = home_str + cand[7:]
            base_path = Path(cand)
            base_path = base_path if base_path.is_absolute() else cwd / base_path
            lexical = _cred_canon(str(base_path))
            try:
                resolved = _cred_canon(str(base_path.resolve(strict=False)))
            except (OSError, ValueError, RuntimeError):
                # An indirect symlink redirect cannot be verified: fail closed.
                return None
            out.append((lexical, resolved))
    return out


def _cred_under(path: str, entry: str) -> bool:
    """True when `path` equals `entry` or is a descendant of it."""
    return path == entry or path.startswith(entry.rstrip("/") + "/")


def _cred_is_proc_secret(path: str, *, pid_dir_too: bool) -> bool:
    """`/proc/{self,thread-self,<digits>}/<something>`: environ, cmdline, mem,
    maps, fd/N, root/..., cwd/... all expose another process's secrets.
    `/proc/cpuinfo` and `/proc/meminfo` stay readable. With `pid_dir_too` the
    bare pid directory also counts (a recursive reader would walk into it).
    """
    pieces = path.split("/")
    if len(pieces) < 3 or pieces[0] != "" or pieces[1] != "proc":
        return False
    who = pieces[2]
    if who not in ("self", "thread-self") and not who.isdigit():
        return False
    return len(pieces) >= 4 or pid_dir_too


def _shell_command_targets_credentials(command: str, *, cwd: Path, home: Path, state_dir: Path) -> bool:
    """D-2 option (b): True when any argv token of a non-HIGH command names a
    credential-bearing path (see the `_CRED_*` constants). Lives in shell()
    rather than the classifier because it needs cwd, $HOME, the state dir and
    symlink resolution. Lexical and resolved forms are both compared (so a
    workspace symlink to a credential file, `/proc/self/root<home>/...`, and
    `../` spellings are caught), each folded through `_cred_canon`, and the
    entries themselves are compared lexically and resolved. Fail closed (True)
    on a NUL byte or any resolve() failure. Accepted false positives:
    metadata-only reads (`ls ~/.ssh`) and any operand naming an EXISTING file
    called `.env`, `*.pem`, `*.key`, `id_rsa*`. Residuals: pattern secrets are
    matched by direct operand only (not as ancestors), `/dev/fd/N`, hard links.
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    if not parts:
        return False
    base = Path(parts[0]).name
    cands = _path_candidates(command, cwd=cwd, home=home)
    if cands is None:
        return True
    ancestor = base in _CRED_ANCESTOR_BASES
    if base in _CRED_RECURSIVE_GREP:
        # grep with no path operand searches the cwd when recursive.
        cwd_s = _cred_canon(str(cwd))
        cands.append((cwd_s, cwd_s))

    state_dirs = {state_dir, home / ".codeyOS"}
    entries = set()
    state_roots = set()
    for rel in _CRED_HOME_ENTRIES:
        entries.add(home / rel)
    for sd in state_dirs:
        state_roots.add(sd)
        for name in _CRED_STATE_ENTRIES:
            entries.add(sd / name)
    # Every comparison below is casefolded (S2-A, G15z NV33/EV03), like the
    # write-side scan in core.protected_paths: `$HOME/.SSH/id_rsa` must not
    # dodge the credential scan on a case-insensitive mount, while the
    # write scan already blocks `$HOME/.BASHRC`. Accepted false positive: on a
    # case-sensitive filesystem a differently-cased sibling such as `.SSH`
    # is also escalated (the cost is a prompt/refusal, never an execution).
    literal = set()
    for e in entries:
        literal.add(_cred_canon(str(e)).casefold())
        try:
            literal.add(_cred_canon(str(e.resolve(strict=False))).casefold())
        except (OSError, ValueError, RuntimeError):
            return True
    roots = set()
    for sd in state_roots:
        roots.add(_cred_canon(str(sd)).casefold())
        try:
            roots.add(_cred_canon(str(sd.resolve(strict=False))).casefold())
        except (OSError, ValueError, RuntimeError):
            return True

    state_patterns = tuple(pat.casefold() for pat in _CRED_STATE_PATTERNS)
    basename_patterns = tuple(pat.casefold() for pat in _CRED_BASENAME_PATTERNS)

    def matches(path: str) -> bool:
        path = path.casefold()
        if any(_cred_under(path, e) for e in literal):
            return True
        if _cred_is_proc_secret(path, pid_dir_too=ancestor):
            return True
        parent, name = os.path.split(path)
        if parent in roots and any(
            fnmatchcase(name, pat) for pat in state_patterns
        ):
            return True
        if ancestor and (
            any(_cred_under(e, path) for e in literal)
            or _cred_under("/proc", path)
        ):
            return True
        return False

    def existing_secret_name(path: str) -> bool:
        name = os.path.basename(path).casefold()
        if name.endswith(".pub"):
            return False
        if not any(fnmatchcase(name, pat) for pat in basename_patterns):
            return False
        try:
            os.lstat(path)
        except OSError:
            # Not stat-able (absent, not a directory, or name too long): it
            # cannot be a credential file the command would read, and treating
            # every search pattern as a hit would make code searches unusable.
            return False
        return True

    for lexical, resolved in cands:
        if matches(lexical) or matches(resolved):
            return True
        if existing_secret_name(lexical) or existing_secret_name(resolved):
            return True
    return False


def _scan_credentials_safely(command: str) -> bool:
    """shell()-side wrapper: builds cwd/home/state_dir at call time and treats
    any exception as a hit. Failing closed is safe here: the only cost of a
    false positive is a refusal (or a human prompt), never an execution.
    """
    try:
        return _shell_command_targets_credentials(
            command,
            cwd=Path(os.getcwd()),
            home=Path.home(),
            state_dir=Path(_config.CODEY_STATE_DIR),
        )
    except Exception:
        return True


# --- G15e Unit B: write-target scan over the shared protected-path set -------
# Lives in shell() (like the credential scan), NOT in classify_shell_command:
# it needs cwd, $HOME, the state dir, symlink resolution and the PATH.
# Bases that cannot write by construction, so a protected path in their argv is
# a read or a literal: READ_COMMANDS (after G15d every member is read-only; the
# ones with an output option are READ only through an option table), `sed`
# (ACT only with --sandbox and no -i), and echo/cd/cut/tr/termux-clipboard-get
# which have no write option (shell=False, so `>` is a literal argument).
# Git basenames are already HIGH. Pinned exactly by a drift test: widening this
# set is a deliberate, reviewed edit. Every other base is scanned by default.
_PROTECTED_SCAN_EXEMPT_BASES = frozenset(READ_COMMANDS) | frozenset({
    "echo", "cd", "cut", "tr", "sed", "termux-clipboard-get",
})
# File mutators: every rule applies, including the runner-exempt rows, so
# `cp x core/agent.py` is HIGH.
_PROTECTED_MUTATOR_BASES = frozenset({
    "cp", "mv", "ln", "touch", "mkdir", "rm", "rmdir", "chmod", "dd",
})
# Bases whose operand may be a DIRECTORY that contains a protected entry
# (`rm -rf ~`, `cp -r payload ~`, `ln -s x ~`, `mv ~/.codeyOS elsewhere`).
_PROTECTED_ANCESTOR_BASES = frozenset({"cp", "mv", "ln", "rm", "rmdir", "chmod"})
# Rows that do not apply to runner operands. `core-py-mirror` / rows tagged
# runner_exempt: `python3 tools/x.py` or `pytest tests/...` executing a core
# file is the registered script-file ceiling (G15b-19), flagging it would make
# normal development HIGH. `path-shadow` is a file-CREATION rule: a runner's
# token such as `pytest` in `python3 -m pytest` or `install` in `pip install`
# is a subcommand name, not a path it creates, and would otherwise refuse the
# common case of cwd == repo root. F3 rows are deliberately NOT exempt:
# running an F3 file (`python3 main.py`, `bash install.sh`) is flagged on
# purpose, which also NARROWS (does not close) G15b-22.
_PROTECTED_RUNNER_SKIP_RULES = frozenset({"core-py-mirror", "path-shadow"})


def _protected_scan_base(command: str) -> Optional[str]:
    """Basename of argv[0] when the protected scan applies to `command`, else
    None (empty command, git, or an exempt read-only base)."""
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    if not parts:
        return None
    base = Path(parts[0]).name
    if _is_git_basename(base) or base in _PROTECTED_SCAN_EXEMPT_BASES:
        return None
    return base


def _shell_command_targets_protected_path(command: str, *, cwd: Path, home: Path, ctx) -> Optional[str]:
    """G15e: the rule id of the first protected path (core.protected_paths)
    named by a non-exempt command's argv, or None. Candidate extraction is
    G15d's `_path_candidates` (every token after argv[0], the text after `=`,
    attached short operands, `~`/`$HOME` expansion, lexical and resolved
    forms), deliberately with no positional parsing: GNU option abbreviation
    and clustering would reopen a hand-written operand scan, so every
    non-option-looking token is a candidate (accepted false positives, spec
    section 8). Mutator bases get every rule; other bases skip
    `_PROTECTED_RUNNER_SKIP_RULES` and the rows tagged runner_exempt.
    Fail closed: a NUL byte or resolve() failure returns "unresolvable-operand".
    """
    base = _protected_scan_base(command)
    if base is None:
        return None
    cands = _path_candidates(command, cwd=cwd, home=home)
    if cands is None:
        return "unresolvable-operand"
    skip = frozenset()
    if base not in _PROTECTED_MUTATOR_BASES:
        skip = _PROTECTED_RUNNER_SKIP_RULES | frozenset(
            e.rule for e in ctx.entries if e.runner_exempt
        )
    ancestor = base in _PROTECTED_ANCESTOR_BASES
    for lexical, resolved in cands:
        forms = (lexical, resolved)
        hit = _protected_paths.first_hit(forms, ctx, shell=True, skip=skip)
        if hit is None and ancestor:
            hit = _protected_paths.ancestor_hit(forms, ctx)
        if hit is not None:
            return hit.rule
    return None


def _scan_protected_safely(command: str) -> Optional[str]:
    """shell()-side wrapper: builds cwd/home/context at call time (nothing is
    cached across calls) and turns ANY exception into the rule "scan-error".
    Failing closed is safe: the only cost of a false positive is a refusal or
    a human prompt, never an execution.
    """
    try:
        if _protected_scan_base(command) is None:
            return None
        ctx = _protected_paths.build_context(
            code_dir=CODE_DIR, workspace_root=_config.WORKSPACE_ROOT,
        )
        return _shell_command_targets_protected_path(
            command, cwd=Path(os.getcwd()), home=Path.home(), ctx=ctx,
        )
    except Exception:
        return "scan-error"


def _command_shadows_system_binary(command: str) -> bool:
    """Q2 PATH-shadow check: for a bare-name argv[0] (no `/`), True when the
    name resolves via the current PATH to a file outside `_SYSTEM_BIN_DIRS`.
    D-3 only sees a `/`; a planted `ls` in a user-writable PATH directory
    ahead of $PREFIX/bin would otherwise inherit the READ label. An unresolvable
    name is left alone (the exec fails with not-found). Uses the same
    process PATH the child inherits. Any error fails closed (True).
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        return True
    if not parts or "/" in parts[0]:
        return False
    try:
        found = shutil.which(parts[0])
        if found is None:
            return False
        return os.path.normpath(os.path.dirname(os.path.abspath(found))) not in _SYSTEM_BIN_DIRS
    except Exception:
        return True


def _parse_command(command: str) -> list:
    """Safely parse a shell command into arguments using shlex."""
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _validate_command(command: str) -> tuple:
    """Validate a command against the allowlist. Returns (is_valid, reason)."""
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()

    if not parts:
        return False, "Empty command"

    base_cmd = Path(parts[0]).name

    if base_cmd not in ALLOWED_COMMANDS:
        return False, f"Command '{base_cmd}' not in allowlist"

    for part in parts[1:]:
        if part.startswith("-") and not part.startswith("--"):
            if any(c in part for c in "rRfFiI"):
                return False, f"Suspicious flag detected: {part}"

    return True, "OK"


def _argv_token_hits_git(token: str) -> bool:
    """True if `token` (one already-parsed argv element) is itself a
    git/git-* basename, or -- for a `-c`/single-string wrapper dispatch
    shape where the whole wrapped command arrives as one already-quoted
    token (`flock /tmp/l -c 'git push'`, `watch 'git push'`, `script -c
    'git push' /dev/null`) -- shlex-splitting the token reveals a
    git/git-* basename among ITS OWN sub-tokens. The plain-token check
    always runs first and is unconditional; the shlex.split() attempt on
    the token only adds coverage on top of it. On malformed quoting
    inside the token, falls back to a bare whitespace .split() -- the
    same fallback this module's other shlex.split() call sites use on a
    ValueError (e.g. _parse_command(), _validate_command()) -- rather
    than giving up, since a malformed-but-identifiable token (e.g.
    `"git push 'unterminated"`) must still be found: this check only
    ever adds coverage on top of the plain-token result, never
    suppresses it, so it cannot regress detection below the pre-fix
    baseline.
    """
    if _is_git_basename(Path(token).name):
        return True
    try:
        sub_tokens = shlex.split(token)
    except ValueError:
        sub_tokens = token.split()
    return any(_is_git_basename(Path(t).name) for t in sub_tokens)


@dataclass(frozen=True)
class _ShellExecResult:
    """Structured companion to `_execute_shell_command()`'s plain-text
    return value.

    `kind`/`code` are set directly from what `subprocess.run()` (or the
    exception it raised) actually reported — never by re-parsing `text` —
    so a command that legitimately succeeds (`returncode == 0`) but whose
    own stdout/stderr happens to start with something that looks like one
    of our own markers (e.g. `echo '[ERROR] hi'`, `echo '[EXIT 1] x'`)
    cannot spoof a caller's status classification. `text` is unchanged
    from before this split and remains the thing shown to the user/model;
    only classification moved off it (NEW-874 follow-up).

    `kind` is one of "ok", "exit", "timeout", "not_found", "empty", "error".
    `code` is the real OS exit status (only set for "exit"; may be
    negative for a signal-terminated process) — always a bounded int from
    `subprocess.CompletedProcess.returncode`, never attacker/output
    controlled, so formatting it into a reason string can't itself
    reintroduce an unbounded-length audit value.
    """

    text: str
    kind: str
    code: Optional[int] = None


def _run_shell_command_structured(command: str, timeout: int) -> _ShellExecResult:
    """Actually run `command` via subprocess and report both the
    human-facing text and a structured, non-text-derived status.

    This is the sole execution primitive `shell()`'s `execute()` closure
    calls; classification decisions must use `kind`/`code`, never parse
    `text` (NEW-874 — text-sniffing the return string is exactly the bug
    this split fixes).
    """
    try:
        args = shlex.split(command)
        if not args:
            # shell() already short-circuits a blank/whitespace-only
            # command before reaching here; this remains reachable only
            # for a command string that shlex.split() reduces to no
            # tokens despite passing that check (e.g. a lone quote pair).
            # Its own "kind" so callers don't lump it in with "error"
            # ([ERROR] Empty command is not an unexpected exception).
            return _ShellExecResult("[ERROR] Empty command", "empty")

        kwargs = {"capture_output": True, "text": True, "timeout": timeout}
        base0 = Path(args[0]).name
        if _is_git_basename(base0):
            kwargs["env"] = shell_git_environment()
        elif (
            base0 in _SHELL_INTERPRETER_BASENAMES
            and _shell_requests_command_string(args)
        ) or _interpreter_requests_inline_code(base0, args):
            # Opaque command strings can invoke git without exposing a stable
            # child argv to this layer. Apply isolation unconditionally to an
            # approved opaque dispatch; it changes only Git configuration.
            kwargs["env"] = shell_git_environment()
        elif (
            base0 in _EXEC_WRAPPER_BASENAMES
            or base0 in _PRIVILEGE_WRAPPER_BASENAMES
            or base0 in {"env", "command"}
        ):
            # NEW-875 follow-up, extended for the WP2.1 group 1 closeout
            # (NEW-875 follow-on): a git/git-* command wrapped by one of
            # these exec wrappers (e.g. `timeout 5 git push`) is already
            # HIGH_IMPACT via classify_shell_command(), but args[0] here
            # is the wrapper's own basename, not git's -- without this,
            # an approved wrapped git command would run fully ambient,
            # unlike a direct `git push`. Scans every remaining argv
            # token (not just the first) via _argv_token_hits_git(),
            # which checks both the token itself AND (for a `-c`/
            # single-string dispatch shape like `flock /tmp/l -c 'git
            # push'`, `watch 'git push'`, `script -c 'git push'
            # /dev/null`, where the wrapped command arrives as one
            # already-quoted argv token) that token's own shlex-split
            # sub-tokens, since a plain Path(token).name check alone
            # never matches a multi-word quoted token. Position varies
            # by wrapper; this also means a git basename appearing
            # anywhere in argv (e.g. as a plain argument to `find`/
            # `grep`, not the command being wrapped) triggers the same
            # env isolation. Accepted as benign over-application --
            # these commands are already HIGH_IMPACT, and env isolation
            # only sets environment variables, it doesn't change what
            # runs.
            #
            # Still-named residuals (not claimed covered by this scan):
            # - Only one level of shlex-splitting is attempted per
            #   token, so a doubly-nested dispatch shape
            #   (`watch "sh -c 'git push'"`) still misses -- the outer
            #   token's sub-tokens are `sh`, `-c`, `git push`, and
            #   `git push` itself is never re-split again.
            # - The benign over-application noted above now also
            #   extends to a single-string token's sub-tokens: a
            #   non-git single-string payload that happens to embed a
            #   bare `git` word (e.g. `watch 'echo git status later'`)
            #   also picks up env isolation, same accepted trade-off.
            if any(_argv_token_hits_git(a) for a in args[1:]):
                kwargs["env"] = shell_git_environment()
        result = subprocess.run(args, **kwargs)
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        output = output.strip() if output.strip() else "(no output)"
        if result.returncode != 0:
            # NEW-874: a nonzero exit is a real execution failure, not a
            # successful run that merely printed something. The `kind`/
            # `code` fields (not this string) are what a caller must use
            # to tell the two apart — see _ShellExecResult's docstring.
            return _ShellExecResult(f"[EXIT {result.returncode}] {output}", "exit", result.returncode)
        return _ShellExecResult(output, "ok")
    except subprocess.TimeoutExpired:
        return _ShellExecResult(f"[ERROR] Command timed out after {timeout}s", "timeout")
    except FileNotFoundError:
        return _ShellExecResult(f"[ERROR] Command not found: {command.split()[0]}", "not_found")
    except Exception as e:
        return _ShellExecResult(f"[ERROR] {e}", "error")


def shell(command: str, yolo: bool = False, timeout: int = 1800) -> str:
    """
    Execute a shell command safely. Uses shlex.split() instead of shell=True.

    All commands go through the user confirmation path when confirm_shell=True.
    Dangerous commands receive an explicit warning before confirmation.

    Routed through core.action_gateway (WP2.1 slice 2): the command is
    classified (READ/ACT/HIGH_IMPACT), and a HIGH_IMPACT command with no
    confirmation path available (confirm_shell=False or yolo=True) fails
    closed — refused and audited, never executed. Classification only
    affects the audit label and the HIGH_IMPACT fail-closed rule; it does
    NOT change the existing confirm-prompt behavior below for READ/ACT
    commands. Prompt declines are audited as refused; unavailable or
    interrupted prompts block without exposing exception text.

    Args:
        command: The shell command to execute
        yolo: Skip confirmation prompts
        timeout: Command timeout in seconds (default: 30 minutes)

    Returns:
        Command output or error message
    """
    if not command or not command.strip():
        return "[ERROR] Empty command"

    authority = classify_shell_command(command)
    git_metadata_escalation = False
    if authority != HIGH_IMPACT and _shell_command_targets_git_metadata(
        command, cwd=Path(os.getcwd()), roots=(_config.WORKSPACE_ROOT, CODE_DIR)
    ):
        authority = HIGH_IMPACT
        git_metadata_escalation = True
    # D-2 option (b): credential-bearing operands. Needs cwd/$HOME/state dir
    # and symlink resolution, so it lives here and not in the classifier
    # (which must stay free of filesystem and environment access). Any
    # exception inside the scan escalates (see _scan_credentials_safely).
    credential_escalation = False
    if authority != HIGH_IMPACT and _scan_credentials_safely(command):
        authority = HIGH_IMPACT
        credential_escalation = True
    # G15e: write targets in the shared protected-path set (core/protected_paths:
    # audit ledger, state dir, $HOME startup/credential files, .git components,
    # PATH directories, F3 launchers/scripts/config/plugin data). Only ACT is
    # escalated: READ commands cannot write and HIGH is already gated. A scan
    # failure escalates too (rule "scan-error").
    protected_rule = None
    if authority == ACT:
        protected_rule = _scan_protected_safely(command)
        if protected_rule is not None:
            authority = HIGH_IMPACT
    # Q2: bare-name PATH shadow (a planted executable in a user-writable PATH
    # directory borrowing a system tool's READ/ACT label).
    shadow_escalation = False
    if authority != HIGH_IMPACT and _command_shadows_system_binary(command):
        authority = HIGH_IMPACT
        shadow_escalation = True
    # Both conditions matter here, not `not yolo` alone: TOOLS["shell"]'s
    # lambda never forwards yolo (always False there), so confirm_shell is
    # what's actually set to False in every "nobody's watching" context
    # (main.py --yolo, fixmode, `--tdd --yolo` (plain --tdd confirms since D-9), the daemon's own prior check). Using
    # `not yolo` alone would make confirm_available=True (not fail-closed)
    # in exactly those contexts — the opposite of the intended tightening.
    confirm_available = (not yolo) and bool(AGENT_CONFIG.get("confirm_shell", True))

    gateway = get_action_gateway()
    confirm = None
    if authority == HIGH_IMPACT:
        if confirm_available:
            def confirm():
                if is_dangerous(command):
                    warning(f"Potentially dangerous command: `{command}`")
                if git_metadata_escalation:
                    warning(f"Command targets this repository's own Git metadata directory: `{command}`")
                if credential_escalation:
                    warning(f"Command references a credential-bearing path: `{command}`")
                if protected_rule is not None:
                    warning(f"Command references a protected path ({protected_rule}): `{command}`")
                if shadow_escalation:
                    warning(f"Command name resolves outside the system bin directories: `{command}`")
                return ask_confirm(f"Run shell command: `{command}`?")
    else:
        # Preserve READ/ACT UI choices before mediation, so cancellation is
        # recorded as refusal rather than a successfully executed command.
        dangerous = is_dangerous(command)
        if dangerous:
            warning(f"Potentially dangerous command: `{command}`")
        if (dangerous or AGENT_CONFIG.get("confirm_shell", True)) and not yolo:
            try:
                approved = ask_confirm(f"Run shell command: `{command}`?") is True
            except (EOFError, KeyboardInterrupt):
                # Missing/interrupted human input cannot authorize execution.
                reason = "Human confirmation unavailable or interrupted; command not attempted."
            except Exception:
                # Fail closed without persisting arbitrary prompt exception text.
                reason = "Human confirmation unavailable due to callback failure; command not attempted."
            else:
                reason = None if approved else "Human confirmation declined; command not attempted."
            if reason is not None:
                gateway.refuse_exec(
                    authority=authority, action="shell_tools.shell",
                    command=command, reason=reason,
                )
                if reason == "Human confirmation declined; command not attempted.":
                    return "[CANCELLED] User declined to run command."
                return f"[BLOCKED] {reason}"

    # NEW-874: capture the real result via `nonlocal` before deciding
    # whether to raise, mirroring core/githelper.py::_gate_local_commit's
    # precedent for this exact pattern. gate_exec()'s audit `reason` field
    # is written to an on-disk ledger (action_gateway.py:470-474 explains
    # why command output never goes there), so only fixed, bounded reason
    # strings are raised here — never the literal exception text or any
    # of the command's own output.
    #
    # Classification is read from _run_shell_command_structured()'s
    # `kind`/`code` fields, never by string-sniffing `exec_result` (the
    # text ultimately returned to the agent/model, unchanged from
    # before) — a real success whose own stdout happens to start with
    # "[ERROR]"/"[EXIT 1] " etc. would otherwise be misclassified as a
    # failure by a text check, exactly backwards (this was a real,
    # reviewer-caught bug in the prior string-sniffing version of this
    # closure; see NEW-874 code-reviewer notes).
    exec_result = None

    def execute():
        nonlocal exec_result
        structured = _run_shell_command_structured(command, timeout)
        exec_result = structured.text
        if structured.kind == "timeout":
            raise RuntimeError("command execution timed out")
        if structured.kind == "not_found":
            raise RuntimeError("command executable not found")
        if structured.kind == "empty":
            raise RuntimeError("command was empty")
        if structured.kind == "error":
            raise RuntimeError("command execution raised an unexpected exception")
        if structured.kind == "exit":
            raise RuntimeError(f"command exited with status {structured.code}")
        return exec_result

    decision = gateway.gate_exec(
        authority=authority,
        action="shell_tools.shell",
        command=command,
        confirm_available=confirm_available,
        confirm=confirm,
        execute=execute,
    )
    if decision.outcome == OUTCOME_REFUSED:
        if decision.reason == "Human confirmation declined; command not attempted.":
            return "[CANCELLED] User declined to run command."
        return f"[BLOCKED] {decision.reason}"
    if decision.outcome == OUTCOME_FAILED:
        # Live now (NEW-874): _run_shell_command_structured() reporting a
        # timeout/not-found/exception/nonzero-exit `kind` makes execute()
        # raise above, so this branch is reached whenever the command
        # itself failed. Return the original string captured via
        # `nonlocal` — it already carries the real "[ERROR] ..."/
        # "[EXIT N] ..." text — rather than reconstructing one from
        # decision.reason, which is only the bounded, ledger-safe label.
        return exec_result
    return decision.detail.get("result", "(no output)")


def search_files(pattern: str, path: str = ".") -> str:
    """Audited READ basename search using Python fnmatchcase, capped at 50 lines.

    Paths are literal and unrestricted; no utility options, expansion, or
    resolution are applied. Matching is case-sensitive, includes hidden entries,
    and treats backslashes literally rather than using GNU find glob/locale
    semantics. Directory symlinks are not intentionally followed, including a
    starting link with trailing slashes. Results are unsorted. Errors discard
    partial matches; traversal continues after the display cap to detect them.
    The 15-second deadline is cooperative and cannot interrupt blocked syscalls.
    This provides no containment, snapshot, or concurrent replacement guarantee.
    """
    def execute():
        if (
            not isinstance(pattern, str) or not isinstance(path, str)
            or not path or "\0" in path or "\0" in pattern
        ):
            raise RuntimeError("Invalid search arguments")
        try:
            deadline = monotonic() + 15

            def check_deadline():
                if monotonic() >= deadline:
                    raise TimeoutError

            lines = []

            def match(display, name):
                if fnmatchcase(name, pattern):
                    for line in display.splitlines():
                        if line.strip() and len(lines) < 50:
                            lines.append(line)

            # Strip only trailing separators so lstat inspects a starting
            # symlink itself, rather than following the trailing-slash form.
            root = path.rstrip(os.sep) or os.sep
            check_deadline()
            mode = os.lstat(root).st_mode
            check_deadline()
            match(root, os.path.basename(root))
            pending = [root] if stat.S_ISDIR(mode) else []
            while pending:
                directory = pending.pop()
                check_deadline()
                with os.scandir(directory) as entries:
                    check_deadline()
                    for entry in entries:
                        check_deadline()
                        display = os.path.join(directory, entry.name)
                        match(display, entry.name)
                        check_deadline()
                        is_directory = entry.is_dir(follow_symlinks=False)
                        check_deadline()
                        if is_directory:
                            pending.append(display)
                    check_deadline()
            check_deadline()
            return "\n".join(lines) if lines else "(no matches)"
        except TimeoutError:
            raise RuntimeError("Search timed out") from None
        except FileNotFoundError:
            raise RuntimeError("Search path not found") from None
        except PermissionError:
            raise RuntimeError("Search permission denied") from None
        except Exception:
            # Normalize traversal failures before auditing: exception text can
            # disclose paths or query data, and partial output is not success.
            raise RuntimeError("Search failed") from None

    decision = get_action_gateway().gate_exec(
        authority=READ, action="shell_tools.search_files",
        command="recursive basename search", confirm_available=False,
        execute=execute,
    )
    if decision.outcome == OUTCOME_REFUSED:
        return f"[BLOCKED] {decision.reason}"
    if decision.outcome == OUTCOME_FAILED:
        return f"[ERROR] {decision.reason}"
    return decision.detail.get("result", "(no matches)")
