"""
--fix mode: run a Python file, capture the error, auto-patch it.
codey --fix script.py
codey --fix script.py "also add argument parsing while you're at it"
"""

from pathlib import Path

from utils.logger import error, info, separator, success, warning


class CaptureResult(tuple):
    """Backward-compatible (success, output), with structured stop metadata."""

    def __new__(cls, success, output, *, refused=False, execution_error=False):
        value = super().__new__(cls, (success, output))
        value.refused = refused
        value.execution_error = execution_error
        return value


def run_and_capture(path: str, *, confirm_available=None, confirm=None) -> tuple[bool, str]:
    """Run Python through the gateway; preserve the success/output tuple API."""
    from core.process_boundary import run_process

    result = run_process(
        ["python3", str(path)], timeout=30, action="fixmode.run_and_capture",
        confirm_available=confirm_available, confirm=confirm,
    )
    if result.refused:
        return CaptureResult(False, result.decision.reason, refused=True)
    if result.execution_error is not None:
        return CaptureResult(False, f"[ERROR] {result.execution_error}", execution_error=True)
    return CaptureResult(
        result.decision.allowed,
        result.stdout if result.returncode == 0 else result.stderr or result.stdout,
    )


def fix_file(filepath: str, extra_instruction: str = "", yolo: bool = False):
    """
    Main fix mode entrypoint.
    1. Read the file
    2. Run it and capture error
    3. If error, ask Codey to fix it
    4. Write the fix
    5. Re-run to verify
    """
    from core.agent import run_agent
    from core.context import load_file

    p = Path(filepath).expanduser()
    if not p.exists():
        error(f"File not found: {filepath}")
        return

    # Override confirmations in fix mode
    if yolo:
        from utils import config

        config.AGENT_CONFIG["confirm_write"] = False
        config.AGENT_CONFIG["confirm_shell"] = False

    info(f"Running {p.name}...")
    captured = run_and_capture(str(p))
    ok, output = captured
    if getattr(captured, "refused", False) or getattr(captured, "execution_error", False):
        error(output)
        return

    if ok:
        success(f"{p.name} ran successfully:")
        from utils.logger import console
        console.print(output)
        if extra_instruction:
            info(f"Applying extra instruction: {extra_instruction}")
            load_file(str(p))
            history = []
            run_agent(f"File {p.name} runs fine. Now: {extra_instruction}", history, yolo=yolo)
        return

    # Error — show it and auto-fix
    warning(f"Error in {p.name}:")
    from utils.logger import console
    console.print(output)
    separator()
    info("Auto-fixing...")

    # Load the broken file into context
    load_file(str(p))

    # Build fix prompt
    prompt = (
        f"The file {p.name} has an error. Fix it.\n\n"
        f"Error output:\n{output}\n\n"
        f"The file contents are in your context above. "
        f"Write the complete corrected version of {p.name}."
    )
    if extra_instruction:
        prompt += f"\n\nAlso: {extra_instruction}"

    history = []
    result, _ = run_agent(prompt, history, yolo=yolo)

    # Verify the fix worked
    separator()
    info(f"Verifying fix...")
    verified = run_and_capture(str(p))
    ok2, output2 = verified
    if getattr(verified, "refused", False) or getattr(verified, "execution_error", False):
        error(output2)
        return
    if ok2:
        success(f"Fixed! {p.name} now runs successfully.")
        if output2.strip():
            from utils.logger import console
            console.print(output2)
    else:
        warning(f"Fix attempt did not fully resolve the error:")
        from utils.logger import console
        console.print(output2)
        info("Try: codey --read " + str(p) + ' "fix this error: ' + output2[:100] + '"')
