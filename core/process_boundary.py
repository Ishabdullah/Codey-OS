"""Gateway boundary for bounded subprocess invocations in fix/TDD/recovery.

Classification shares shell tools' default-confirm policy: unknown executables
and opaque inline interpreters are HIGH_IMPACT, while known script-file and
pytest invocations retain their established authority.
"""

import shlex
import subprocess
from dataclasses import dataclass


@dataclass
class ProcessExecution:
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    execution_error: str | None = None
    decision: object = None

    @property
    def refused(self):
        return self.decision.outcome == "refused"


def run_process(argv, *, timeout, action, authority=None, confirm_available=None, confirm=None):
    """Run one argv command, retaining private output outside its audit row."""
    from core.action_gateway import HIGH_IMPACT, get_action_gateway
    from tools.shell_tools import classify_shell_command

    if authority is None:
        authority = classify_shell_command(shlex.join(argv))
    captured = ProcessExecution()

    def execute():
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            captured.execution_error = f"Process timed out after {timeout}s"
            raise RuntimeError("Process execution timed out") from None
        except Exception as exc:  # noqa: BLE001 - preserve private diagnostics outside audit
            captured.execution_error = str(exc)
            # Keep detailed diagnostics in-process, never in the audit ledger.
            raise RuntimeError("Process execution failed") from None
        captured.returncode = result.returncode
        captured.stdout = result.stdout
        captured.stderr = result.stderr
        if result.returncode < 0:
            captured.execution_error = f"Process interrupted by signal {-result.returncode}"
            raise RuntimeError("Process execution interrupted")
        if result.returncode != 0:
            raise RuntimeError("Process exited with nonzero status")
        return "Process execution completed"

    captured.decision = get_action_gateway().gate_exec(
        authority=authority, action=action, command=action,
        confirm_available=(callable(confirm) and confirm_available is not False)
        if authority == HIGH_IMPACT else False,
        confirm=confirm if callable(confirm) else None,
        execute=execute,
    )
    return captured
