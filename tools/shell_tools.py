import os
import re
import shlex
import stat
import subprocess
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from time import monotonic
from typing import Optional

import utils.config as _config
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
# bare-vs-argument-bearing check at both sites and is deliberately NOT
# folded into this set. `su`, `doas`, and `proot` are handled separately
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
_BUILD_TOOL_SYSTEM_DIRS = frozenset({
    "/usr/bin", "/usr/local/bin", "/bin",
    "/data/data/com.termux/files/usr/bin",
})
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
_REMOTE_FETCH_SUBCOMMANDS = {
    "pnpm": {"dlx", "exec", "create", "node", "env", "self-update", "set",
             "plugin", "config", "explore", "bin"},
    "yarn": {"dlx", "exec", "create", "node", "env", "self-update", "set",
             "plugin", "config", "explore", "bin"},
}
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
_NPM_HIGH_VERBS = frozenset({
    "publish", "login", "logout", "adduser", "token", "owner", "access",
    "deprecate", "unpublish", "dist-tag", "exec", "x",
    # round 3: `explore` runs an arbitrary command in a dependency dir;
    # `set` writes config (script-shell/registry); `link` writes symlinks
    # into the global prefix (can shadow binaries on PATH). Judged ACT and
    # left alone: `rebuild` and `pack` run only the project's own lifecycle
    # scripts, the same class as the ACT `install`/`test`/`run`.
    "explore", "set", "link", "ln",
})
_NPM_CONFIG_WRITE_VERBS = frozenset({"set", "edit", "delete", "fix"})
_NPM_INIT_VERBS = frozenset({"init", "create", "innit"})
# Residual (OPEN, not closed here): `npm install|pip install <url/vcs/pkg>`
# and `pnpm add|yarn add <git-url>` fetch remote code but stay ACT by the
# existing npm/pip precedent; `yarn plugin import <url>` / `yarn set
# version <url>` likewise.


def _npm_is_high(parts) -> bool:
    """npm publishing/credential verbs and npx-equivalent initializers."""
    rest = parts[1:]
    if any(t in _NPM_HIGH_VERBS for t in rest):
        return True
    if "config" in rest and any(t in _NPM_CONFIG_WRITE_VERBS for t in rest):
        return True
    if any("script-shell" in t for t in rest):
        return True
    for i, t in enumerate(rest):
        if t in _NPM_INIT_VERBS:
            # bare `npm init` / `npm init -y` stay ACT; an initializer
            # package or an --init* flag fetches and runs remote code.
            tail = rest[i + 1:]
            return any(
                (not x.startswith("-")) or x.startswith("--init") for x in tail
            )
    return False


def _build_tool_is_act(parts) -> bool:
    """True when parts[0] is an allowlisted build tool and no remote-exec form."""
    exe = parts[0]
    base = Path(exe).name
    if base not in _BUILD_TOOL_ACT_BASENAMES:
        return False
    if exe != base and str(Path(exe).parent) not in _BUILD_TOOL_SYSTEM_DIRS:
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
_PIP_HIGH_TOKENS = frozenset({
    "config", "--index-url", "-i", "--extra-index-url", "--find-links", "-f",
    "--trusted-host",
})
_PIP_REMOTE_SPEC_MARKERS = (
    "git+", "hg+", "svn+", "bzr+", "http://", "https://", "ftp://", "file:",
)


def _pip_is_high(args) -> bool:
    """pip redirected to another index / config write / remote or VCS spec.

    `args` are the tokens after `pip` (or after `python -m pip`). A plain
    `pip install foo`, `-U foo`, `-e .`, `-r requirements.txt` stay ACT
    (routine; accepted residual: a requirements file can itself list URLs,
    and a bare PyPI name fetches code by the existing precedent). Accepted
    false positive: any argument containing a URL/VCS marker.
    """
    for t in args:
        if t in _PIP_HIGH_TOKENS:
            return True
        if t.startswith(("--index-url=", "--extra-index-url=", "--find-links=",
                         "--trusted-host=")):
            return True
        # attached short forms: `-ihttps://x`, `-fhttps://x`
        if len(t) > 2 and t.startswith(("-i", "-f")) and not t.startswith("--"):
            return True
        if any(m in t.lower() for m in _PIP_REMOTE_SPEC_MARKERS):
            return True
    return False


def _python_dash_m_pip_args(parts):
    """Tokens after `-m pip` in a python argv, or None when not `-m pip`."""
    for i, t in enumerate(parts[1:-1], start=1):
        if t == "-m" or (
            t.startswith("-") and not t.startswith("--") and t.endswith("m")
        ):
            return parts[i + 2:] if _PIP_BASENAME_RE.fullmatch(parts[i + 1]) else None
        if not t.startswith("-"):
            return None
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
    "--inspect=", "--inspect-brk=", "--inspect-wait=", "--run=",
    "--max-old-space-size=", "--stack-size=", "--test-name-pattern=",
    "--test-reporter=", "--disable-warning=",
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
            return False  # end of options / stdin script / script path
        if family == "perl" and token == "-I" and index < len(parts) and (
            not parts[index].startswith("-")
        ):
            # `-I dir` (include path, kept ACT by the existing compat test):
            # the operand is a directory, never code. A dash-led next token
            # is NOT consumed, so `-I -e` still reaches the -e check.
            index += 1
            continue
        if family == "node":
            if token in _NODE_SAFE_BARE_OPTIONS or token.startswith(
                _NODE_SAFE_ATTACHED_PREFIXES
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
    option_operands = {"-W", "-X", "--check-hash-based-pycs"}
    index = 1
    while index < len(parts):
        token = parts[index]
        if token == "--":
            return False
        if not token.startswith("-") or token == "-":
            return False
        flags = token[1:]
        if python_family and not token.startswith("--"):
            # Walk the short-flag cluster the way python does (verified
            # against `python3 --help`): `c` = inline code (terminates the
            # option list, rest/next token is code); `m` = module run (kept
            # ACT by precedent so `python3 -m pytest` works; residual `-m
            # http.server`/`-m code`); `W`/`X` take an operand (rest of the
            # cluster or the next token), so `-Wc` is -W with arg `c`.
            consumed = False
            for pos, letter in enumerate(flags):
                if letter == "c":
                    return True
                if letter == "m":
                    return False
                if letter in "WX":
                    index += 1 if pos < len(flags) - 1 else 2
                    consumed = True
                    break
            if consumed:
                continue
        if python_family and token == "-m":
            return False
        index += 2 if token in option_operands else 1
    return False


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
         and argument-bearing env -> HIGH_IMPACT. These can dispatch
         children or produce other effects. Only a successfully
         tokenized bare env remains READ; no child is parsed.
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
    if (
        _is_git_basename(base)
        or _is_termux_basename(base)
        or _is_network_client_basename(base)
        or base in _EXEC_WRAPPER_BASENAMES
        or base in _PRIVILEGE_WRAPPER_BASENAMES
    ):
        return HIGH_IMPACT
    if base == "env":
        return READ if len(parts) == 1 else HIGH_IMPACT
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
    if base in READ_COMMANDS:
        return READ
    if (
        base in ALLOWED_COMMANDS
        or base in DANGEROUS_COMMANDS
        or base in _SHELL_INTERPRETER_BASENAMES
        or _SCRIPT_INTERPRETER_RE.fullmatch(base)
        or base == "command"
        or _build_tool_is_act(parts)
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
    - Nested/submodule .git elsewhere in the tree: out of scope, same
      caveat already logged against NEW-894.
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
    # Both conditions matter here, not `not yolo` alone: TOOLS["shell"]'s
    # lambda never forwards yolo (always False there), so confirm_shell is
    # what's actually set to False in every "nobody's watching" context
    # (main.py --yolo, fixmode, tdd, the daemon's own prior check). Using
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
