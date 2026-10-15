import os
import shlex
import stat
import subprocess
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from time import monotonic
from typing import Optional

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
import utils.config as _config

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
# folded into this set. Known-incomplete -- `su`, `doas`, `proot`
# deliberately deferred: privilege-elevation-shaped wrappers are a
# different risk category than plain command dispatch and need a
# product-direction decision from Ish, not just a wider enumeration.
# `busybox` IS included despite being a multi-call binary -- a
# code-reviewer round for this change initially excluded it under a
# "closer to interpreter dispatch than a fixed wrapper" rationale that
# turned out to be false on direct probe: `busybox nice/env/timeout/
# chroot git push` all dispatch exactly like this set's other members,
# not like `sh -c`. Corrected rather than left standing (rule 6).
# This set is a known-incomplete enumeration, not an exhaustive
# classification of every process-dispatching wrapper on a Linux system
# -- see NEW-904 for the long tail of same-class binaries (numactl,
# prlimit, setpriv, firejail, proxychains, systemd-run, pkexec, etc.)
# identified but not added this round.
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
# Deliberately NOT covered: opaque-interpreter egress (python3 -c
# "import urllib...", node -e "fetch(...)", curl piped through another
# shell) -- that is NEW-904's already-logged open-ended tail (basename
# enumeration has no natural end), not addressed by this change; this
# set is bounded to named network-client binaries only, same scope
# boundary as the exec-wrapper set above.


def _is_network_client_basename(base: str) -> bool:
    """True if a parsed argv[0] basename names a network-client
    executable that can transfer a local file to a remote host (curl,
    wget, scp, rsync, ssh, sftp, ftp, telnet, nc/ncat/netcat). Whole-
    family conservative classification via basename, mirroring
    _is_termux_basename's style (WP2.1 group 9).
    """
    return base in _NETWORK_CLIENT_BASENAMES


def _direct_high_impact_after_quote_error(command: str) -> bool:
    """Recognize an identifiable restricted executable despite malformed quoting."""
    lexer = shlex.shlex(command, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        executable = next(lexer, "")
    except ValueError:
        # An unclosed executable quote can still identify a restricted family.
        raw = command.split(maxsplit=1)
        executable = raw[0].strip("\"'") if raw else ""
    base = Path(executable).name
    return (
        _is_git_basename(base)
        or _is_termux_basename(base)
        or _is_network_client_basename(base)
        or base in _EXEC_WRAPPER_BASENAMES
        or base == "env"
    )


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
         confirmation under yolo. Named-binary enumeration only; does
         NOT cover opaque-interpreter egress (python3 -c "import
         urllib...", node -e "fetch(...)") -- see NEW-904's already-
         logged open-ended tail for that class.
      3. Direct exec-wrapper basenames (_EXEC_WRAPPER_BASENAMES: find,
         xargs, timeout, nice, nohup, setsid, stdbuf, chrt, ionice,
         strace, flock, watch, script, unshare, taskset, setarch,
         ltrace, unbuffer, catchsegv, time, chroot, nsenter, busybox)
         and argument-bearing env -> HIGH_IMPACT. These can dispatch
         children or produce other effects. Only a successfully
         tokenized bare env remains READ; no child is parsed.
      4. Other executables retain their previous READ/ACT labels.
         Wrappers and arbitrary scripts still require separate assessment.
    """
    cmd_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return HIGH_IMPACT

    try:
        parts = shlex.split(command)
    except ValueError:
        if _direct_high_impact_after_quote_error(command):
            return HIGH_IMPACT
        parts = command.split()

    if not parts:
        return ACT

    base = Path(parts[0]).name
    if (
        _is_git_basename(base)
        or _is_termux_basename(base)
        or _is_network_client_basename(base)
        or base in _EXEC_WRAPPER_BASENAMES
    ):
        return HIGH_IMPACT
    if base == "env":
        return READ if len(parts) == 1 else HIGH_IMPACT
    if base in READ_COMMANDS:
        return READ
    return ACT


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
        elif base0 in _EXEC_WRAPPER_BASENAMES or base0 == "env":
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
