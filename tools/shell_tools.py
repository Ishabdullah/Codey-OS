import os
import shlex
import stat
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path
from time import monotonic

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

def _is_git_basename(base: str) -> bool:
    """True if a parsed argv[0] basename names git or a git-<subcommand>
    helper executable (e.g. git-upload-pack). Shared between
    classify_shell_command()'s HIGH_IMPACT check and
    _execute_shell_command()'s environment-isolation check so the two
    can never classify and execute a command differently.
    """
    return base == "git" or base.startswith("git-")


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
    return _is_git_basename(base) or base in {"find", "xargs", "env"}


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
      3. Direct find/xargs and argument-bearing env -> HIGH_IMPACT.
         These can dispatch children or produce other effects. Only a
         successfully tokenized bare env remains READ; no child is parsed.
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
    if _is_git_basename(base) or base in {"find", "xargs"}:
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
    - find/xargs/argument-bearing env: already HIGH_IMPACT from
      classify_shell_command(); this scan running on them changes
      nothing (HIGH_IMPACT -> HIGH_IMPACT), so no special exemption is
      carved out for the legitimate `find . -path ./.git -prune` idiom.
    - Ordinary READ_COMMANDS members minus _GIT_METADATA_SCANNED_READ:
      verified via --help to have no write-capable option; exempted so
      `cat .git/config`/`grep .git x`/`ls .git` stay frictionless reads.

    Named residuals (documented, not silently claimed covered):
    - A READ_COMMANDS member wrapped in a non-exempt basename
      (`timeout 5 cat .git/config`) loses its read exemption -- same
      argv[0]-only blind spot classify_shell_command() already has for
      `timeout N git push` (NEW-875). Directionally safe here (over-
      escalates a read) rather than unsafe.
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


def _execute_shell_command(command: str, timeout: int) -> str:
    """Actually run `command` via subprocess and return its output as a
    string. No confirmation, classification, or gating logic here — this
    is the execution primitive `ActionGateway.gate_exec()` delegates to,
    the same role `Filesystem.write()` plays for `gate_write()`.
    """
    try:
        args = shlex.split(command)
        if not args:
            return "[ERROR] Empty command"

        kwargs = {"capture_output": True, "text": True, "timeout": timeout}
        if _is_git_basename(Path(args[0]).name):
            kwargs["env"] = shell_git_environment()
        result = subprocess.run(args, **kwargs)
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        return output.strip() if output.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        return f"[ERROR] Command timed out after {timeout}s"
    except FileNotFoundError:
        return f"[ERROR] Command not found: {command.split()[0]}"
    except Exception as e:
        return f"[ERROR] {e}"


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

    decision = gateway.gate_exec(
        authority=authority,
        action="shell_tools.shell",
        command=command,
        confirm_available=confirm_available,
        confirm=confirm,
        execute=lambda: _execute_shell_command(command, timeout),
    )
    if decision.outcome == OUTCOME_REFUSED:
        if decision.reason == "Human confirmation declined; command not attempted.":
            return "[CANCELLED] User declined to run command."
        return f"[BLOCKED] {decision.reason}"
    if decision.outcome == OUTCOME_FAILED:
        # Not reachable in practice today — _execute_shell_command()
        # catches ordinary execution exceptions internally and returns an "[ERROR] ..."
        # string rather than raising — but handled explicitly rather than
        # silently falling through to the ALLOWED-shaped return below.
        return f"[ERROR] {decision.reason}"
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
