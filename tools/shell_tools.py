import shlex
import subprocess
from pathlib import Path

from core.action_gateway import (
    ACT,
    HIGH_IMPACT,
    OUTCOME_FAILED,
    OUTCOME_REFUSED,
    READ,
    get_action_gateway,
)
from utils.config import AGENT_CONFIG
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
    "find",
    "wc",
    "sort",
    "uniq",
    "pwd",
    "which",
    "env",
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

def _direct_git_after_quote_error(command: str) -> bool:
    """Recognize an identifiable Git executable even if later quoting fails."""
    lexer = shlex.shlex(command, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        executable = next(lexer, "")
    except ValueError:
        # An unclosed executable quote can still clearly start with git.
        raw = command.split(maxsplit=1)
        executable = raw[0].strip("\"'") if raw else ""
    base = Path(executable).name
    return base == "git" or base.startswith("git-")


def classify_shell_command(command: str) -> str:
    """Classify a shell command into one of the three gateway authority
    classes (READ/ACT/HIGH_IMPACT), for use with ActionGateway.gate_exec().

    Checked in this order, deliberately:
      1. DANGEROUS_PATTERNS (the existing, narrower, irreversible/
         security-relevant subset — NOT the broader DANGEROUS_COMMANDS
         set used by is_dangerous()'s warn-and-confirm path) -> HIGH_IMPACT.
         Checked first so a pattern match (e.g. "find X -delete") always
         wins over a base-command read, even though `find` alone would
         otherwise classify READ.
      2. Every direct git or git-* executable -> HIGH_IMPACT. Git
         configuration, hooks, and helpers can introduce opaque effects,
         including for queries. This conservative boundary does not claim
         every invocation is destructive; no discovery is performed.
      3. Other executables retain their previous READ/ACT labels.
         Wrappers and arbitrary scripts still require separate assessment.
    """
    cmd_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return HIGH_IMPACT

    try:
        parts = shlex.split(command)
    except ValueError:
        if _direct_git_after_quote_error(command):
            return HIGH_IMPACT
        parts = command.split()

    if not parts:
        return ACT

    base = Path(parts[0]).name
    if base == "git" or base.startswith("git-"):
        return HIGH_IMPACT
    if base in READ_COMMANDS:
        return READ
    return ACT


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

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
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
    """Search for files matching pattern. Uses subprocess list args to prevent injection."""
    try:
        result = subprocess.run(
            ["find", path, "-name", pattern], capture_output=True, text=True, timeout=15
        )
        lines = (result.stdout + result.stderr).strip().splitlines()
        lines = [l for l in lines if l.strip()][:50]
        return "\n".join(lines) if lines else "(no matches)"
    except subprocess.TimeoutExpired:
        return "[ERROR] Search timed out"
    except FileNotFoundError:
        return "[ERROR] 'find' command not available"
    except Exception as e:
        return f"[ERROR] {e}"
