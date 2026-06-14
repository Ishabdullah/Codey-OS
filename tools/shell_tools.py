import shlex
import subprocess
from pathlib import Path

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


def shell(command: str, yolo: bool = False, timeout: int = 1800) -> str:
    """
    Execute a shell command safely. Uses shlex.split() instead of shell=True.

    All commands go through the user confirmation path when confirm_shell=True.
    Dangerous commands receive an explicit warning before confirmation.

    Args:
        command: The shell command to execute
        yolo: Skip confirmation prompts
        timeout: Command timeout in seconds (default: 30 minutes)

    Returns:
        Command output or error message
    """
    if not command or not command.strip():
        return "[ERROR] Empty command"

    should_confirm = False

    if is_dangerous(command):
        warning(f"Potentially dangerous command: `{command}`")
        should_confirm = True
    elif AGENT_CONFIG["confirm_shell"] and not yolo:
        should_confirm = True

    if should_confirm and not yolo:
        if not ask_confirm(f"Run shell command: `{command}`?"):
            return "[CANCELLED] User declined to run command."

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
