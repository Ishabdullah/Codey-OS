"""
Sandbox — Isolated execution environment.

All plugin installations, generated code execution, and testing
happens inside this sandbox. Rules:

- No direct system file access outside allowed directories
- No destructive commands (rm -rf /, etc.)
- No background persistence without approval
- Resource limits (timeout, output size)
"""

import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# Allowed directories for sandbox operations
ALLOWED_DIRS = [
    str(Path(__file__).parent.parent),  # ccos/ directory
    tempfile.gettempdir(),  # platform temp dir; on Termux this is $PREFIX/tmp,
    # not bare /tmp -- the sandbox's own tempfile.mkdtemp()-created working
    # dir (see Sandbox.__init__ below) must resolve inside this or every
    # command fails its own allowlist check before it can run at all.
    str(Path.home() / ".local" / "share" / "ccos"),
]

# Blocked commands — never execute these
BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf ~",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",  # fork bomb
    "chmod 777 /",
    "chown root",
    "> /dev/sda",
]

# Resource limits
MAX_TIMEOUT = 120  # seconds
MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB


class SandboxViolation(Exception):
    """Raised when a sandbox rule is violated."""
    pass


class SandboxResult:
    """Result of a sandboxed execution."""

    def __init__(
        self,
        success: bool,
        stdout: str = "",
        stderr: str = "",
        return_code: int = 0,
        duration_ms: float = 0,
        timed_out: bool = False,
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.return_code = return_code
        self.duration_ms = duration_ms
        self.timed_out = timed_out

    @property
    def output(self) -> str:
        return self.stdout if self.success else self.stderr

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout[:10000],  # truncate for storage
            "stderr": self.stderr[:5000],
            "return_code": self.return_code,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
        }


def _is_command_blocked(command: str) -> bool:
    """Check if a command contains blocked patterns."""
    cmd_lower = command.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked.lower() in cmd_lower:
            return True
    return False


def _validate_path(path: str, allowed_dirs: List[str] = None) -> bool:
    """Check if a path is within allowed directories."""
    resolved = Path(path).resolve()
    for allowed in (allowed_dirs or ALLOWED_DIRS):
        try:
            resolved.relative_to(Path(allowed).resolve())
            return True
        except ValueError:
            continue
    return False


def _find_disallowed_path_token(command: str, allowed_dirs: List[str], cwd: str) -> Optional[str]:
    """Best-effort scan for path-shaped tokens in `command` that resolve
    outside `allowed_dirs` (NEW-42). This is a mitigation layer ON TOP of
    the existing `cwd` allowlist check, not a replacement for it -- a
    command can `cd`/`cwd` into an allowed dir and still reference an
    out-of-sandbox path as an argument (e.g. `cat /etc/passwd`), which the
    cwd-only check does not catch.

    `cwd` must be the actual directory the command will execute under
    (the sandbox's `exec_cwd`), not the reviewing process's own
    `os.getcwd()` -- a relative token containing `../` is resolved
    against `cwd` here so the escape check reflects where the command
    really runs.

    Known limitations, deliberately not handled here:
    - paths supplied via environment variable expansion (`$HOME/../..`)
    - paths built via command substitution (`$(echo /etc/passwd)`)
    - encoded/obfuscated path forms
    - relative-path escape via a prior `cd`, e.g. `cd .. && cat secrets`
      -- a bare relative token (no leading `/`/`~`, no literal `../`) is
      indistinguishable from an in-sandbox relative path by inspecting the
      token alone, so it is not checked here
    Only literal path-shaped tokens in the command string are checked.

    Fails OPEN (returns None / "no violation found") if `shlex.split`
    can't parse the command (e.g. unbalanced quotes) -- this is a
    best-effort extra layer, not the sandbox's sole line of defense, so a
    parse failure here should not block a command the existing checks
    would otherwise allow.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None

    for token in tokens:
        if token.startswith("/") or token.startswith("~"):
            candidate = os.path.expanduser(token)
        elif "../" in token:
            candidate = str((Path(cwd) / token).resolve())
        else:
            continue
        if not _validate_path(candidate, allowed_dirs):
            return token
    return None


class Sandbox:
    """
    Sandboxed execution environment.

    Provides:
    - Shell command execution with restrictions
    - Python code execution in subprocess
    - Plugin testing in isolation
    """

    def __init__(self, allowed_dirs: List[str] = None):
        self._allowed_dirs = allowed_dirs or ALLOWED_DIRS.copy()
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="ccos_sandbox_"))

    def run_command(
        self,
        command: str,
        timeout: int = 30,
        cwd: str = None,
        env: Dict[str, str] = None,
    ) -> SandboxResult:
        """
        Execute a shell command in the sandbox.

        Validates against blocked commands and path restrictions.
        """
        if _is_command_blocked(command):
            return SandboxResult(
                success=False,
                stderr=f"[SANDBOX VIOLATION] Blocked command: {command[:100]}",
                return_code=-1,
            )

        exec_cwd = cwd or str(self._tmp_dir)

        bad_token = _find_disallowed_path_token(command, self._allowed_dirs, exec_cwd)
        if bad_token is not None:
            return SandboxResult(
                success=False,
                stderr=f"[SANDBOX VIOLATION] Path not allowed: {bad_token}",
                return_code=-1,
            )

        if not _validate_path(exec_cwd, self._allowed_dirs):
            return SandboxResult(
                success=False,
                stderr=f"[SANDBOX VIOLATION] Path not allowed: {exec_cwd}",
                return_code=-1,
            )

        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        start = time.time()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=min(timeout, MAX_TIMEOUT),
                cwd=exec_cwd,
                env=exec_env,
            )
            duration = (time.time() - start) * 1000

            stdout = result.stdout[:MAX_OUTPUT_SIZE]
            stderr = result.stderr[:MAX_OUTPUT_SIZE]

            return SandboxResult(
                success=result.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=result.returncode,
                duration_ms=duration,
            )

        except subprocess.TimeoutExpired:
            duration = (time.time() - start) * 1000
            return SandboxResult(
                success=False,
                stderr=f"[TIMEOUT] Command exceeded {timeout}s limit",
                return_code=-1,
                duration_ms=duration,
                timed_out=True,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                stderr=f"[ERROR] {str(e)}",
                return_code=-1,
            )

    def run_python(
        self,
        code: str,
        timeout: int = 30,
        working_dir: str = None,
    ) -> SandboxResult:
        """
        Execute Python code in a subprocess.
        """
        # Write code to temp file
        code_file = self._tmp_dir / "sandbox_exec.py"
        code_file.write_text(code)

        return self.run_command(
            f"python3 {code_file}",
            timeout=timeout,
            cwd=working_dir,
        )

    def run_plugin_test(self, plugin_path: str, test_path: str = None) -> SandboxResult:
        """
        Run a plugin's test suite in the sandbox.
        """
        plugin_dir = Path(plugin_path)
        if not plugin_dir.exists():
            return SandboxResult(
                success=False,
                stderr=f"Plugin path not found: {plugin_path}",
            )

        if test_path:
            test_file = Path(test_path)
        else:
            test_file = plugin_dir / "test.py"

        if not test_file.exists():
            return SandboxResult(
                success=False,
                stderr=f"Test file not found: {test_file}",
            )

        return self.run_command(
            f"python3 {test_file}",
            timeout=60,
            cwd=str(plugin_dir),
        )

    def install_package(self, package: str) -> SandboxResult:
        """
        Install a Python package in the sandbox.
        Uses --target to isolate from system packages.
        """
        if any(c in package for c in [";", "&&", "|", "`"]):
            return SandboxResult(
                success=False,
                stderr="[SANDBOX VIOLATION] Invalid package name",
            )

        target = self._tmp_dir / "packages"
        target.mkdir(exist_ok=True)

        return self.run_command(
            f"pip install --target={target} {package}",
            timeout=120,
        )

    def create_workspace(self, name: str) -> Path:
        """Create an isolated workspace directory."""
        ws = self._tmp_dir / name
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    def cleanup(self):
        """Clean up sandbox temporary files."""
        try:
            shutil.rmtree(str(self._tmp_dir), ignore_errors=True)
        except Exception:
            pass

    def get_tmp_dir(self) -> str:
        return str(self._tmp_dir)


# Singleton
_sandbox: Optional[Sandbox] = None


def get_sandbox() -> Sandbox:
    global _sandbox
    if _sandbox is None:
        _sandbox = Sandbox()
    return _sandbox
