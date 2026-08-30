#!/usr/bin/env python3
"""
Peer CLI escalation for Codey-OS.

When Codey exhausts its retry budget on a task, it can escalate to an
external AI coding CLI: Claude Code, Gemini CLI, or Qwen CLI.

Flow:
  1. Codey hits max retries on a task
  2. PeerCLIManager selects best CLI for the task type
  3. Rich confirmation prompt — user can approve, deny, redirect, or pick different CLI
  4. Approved: CLI runs in the foreground terminal (user can interact live)
     All output is captured to a temp file via `tee`
  5. When CLI exits, Codey reads captured output and summarizes
  6. Work continues with the result as context
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from utils.logger import info, separator, success, warning


@dataclass
class PeerCLI:
    name: str
    description: str
    cmd: str  # base shell command
    check_cmd: str  # command to test if installed
    strengths: List[str]
    aliases: List[str] = field(default_factory=list)
    enabled: bool = True
    disabled_reason: str = ""
    interactive: bool = True  # True = open full interactive session
    prompt_flag: str = ""  # flag for non-interactive prompt injection
    prompt_prefix: str = ""  # prefix before the prompt string
    use_pty: bool = True  # False = run via os.system (avoids nested PTY issues)
    yolo_flag: str = ""  # appended after the prompt to skip tool confirmations
    # e.g. "-y" for qwen so it can auto-approve its own tools


# ── Registry ──────────────────────────────────────────────────────────────────

PEER_REGISTRY: List[PeerCLI] = [
    PeerCLI(
        name="antigravity",
        description="Antigravity CLI (Google/Gemini)",
        cmd="agy",
        check_cmd="",
        strengths=["explain", "analysis", "large_context", "review", "generate", "debugging", "refactor", "architecture", "complex"],
        aliases=["agy", "gemini"],
        enabled=True,
        interactive=False,
        use_pty=False,
        prompt_flag="-p",
        yolo_flag="--dangerously-skip-permissions",
    ),
    PeerCLI(
        name="qwen",
        description="Qwen CLI",
        cmd="qwen",
        check_cmd="",  # No Node.js native modules — shutil.which check is sufficient
        strengths=["generate", "code", "completion", "quick_fix", "refactor"],
        aliases=["qwen-code", "qwen3.5"],
        enabled=True,
        interactive=False,
        use_pty=False,
        prompt_flag="-p",
        yolo_flag="-y",  # qwen -p "task" -y → auto-approve its own tool calls
    ),
    PeerCLI(
        name="claude",
        description="Claude Code (Anthropic)",
        cmd="claude",
        check_cmd="claude --version",
        strengths=["debugging", "refactor", "architecture", "complex", "review"],
        aliases=["claude-code"],
        enabled=False,
        disabled_reason="Claude Code is currently disabled (no API credits configured).",
        interactive=False,
        use_pty=False,
        prompt_flag="-p",  # claude -p "task" → non-interactive, clean output
    ),
]

# Task type → preferred CLI order (first available & enabled wins)
TASK_CLI_PREFERENCE: Dict[str, List[str]] = {
    "debugging": ["antigravity", "qwen"],
    "refactor": ["antigravity", "qwen"],
    "generate": ["qwen", "antigravity"],
    "review": ["antigravity", "qwen"],
    "explain": ["antigravity", "qwen"],
    "complex": ["antigravity", "qwen"],
    "default": ["antigravity", "qwen"],
}


def resolve_peer_name(name: str) -> Optional[str]:
    """Resolve an alias or canonical name to a canonical peer name in PEER_REGISTRY."""
    if not name:
        return None
    cleaned = name.strip().lower()
    for cli in PEER_REGISTRY:
        if cli.name.lower() == cleaned:
            return cli.name
        if any(alias.lower() == cleaned for alias in cli.aliases):
            return cli.name
    return None


def is_peer_enabled(name_or_cli: str | PeerCLI) -> bool:
    """Check if a peer is enabled by canonical name, alias, or PeerCLI object."""
    if isinstance(name_or_cli, PeerCLI):
        return name_or_cli.enabled
    canonical = resolve_peer_name(name_or_cli)
    if not canonical:
        return False
    for cli in PEER_REGISTRY:
        if cli.name == canonical:
            return cli.enabled
    return False


# ── Manager ───────────────────────────────────────────────────────────────────


class PeerCLIManager:
    """Manages escalation to external AI coding CLIs."""

    def __init__(self):
        self._available: Optional[List[PeerCLI]] = None

    def available(self, include_disabled: bool = False) -> List[PeerCLI]:
        """Return cached list of installed peer CLIs.

        If include_disabled is False (default), returns only installed AND enabled CLIs.
        If include_disabled is True, returns all installed CLIs.
        """
        if self._available is None:
            self._available = [c for c in PEER_REGISTRY if self._is_installed(c)]
        if include_disabled:
            return list(self._available)
        return [c for c in self._available if c.enabled]

    def _is_installed(self, cli: PeerCLI) -> bool:
        # shutil.which is the most reliable check — works even if
        # the CLI doesn't support --version or returns non-zero for it
        base_cmd = cli.cmd.split()[0]
        if not shutil.which(base_cmd):
            return False
        # For CLIs that bundle native node modules (e.g. node-pty), do a quick
        # smoke-test to catch platforms where the binary exists but crashes on
        # start (e.g. missing pty.node prebuilds on Android ARM64).
        if cli.check_cmd:
            try:
                result = subprocess.run(cli.check_cmd.split(), capture_output=True, timeout=5)
                stderr = (result.stderr or b"").decode("utf-8", errors="replace")
                # Detect node native-module crash signatures
                native_crash = any(
                    sig in stderr
                    for sig in [
                        "Failed to load native module",
                        "pty.node",
                        "prebuilds/",
                        "NODE_MODULE_VERSION",
                    ]
                )
                return not native_crash
            except FileNotFoundError:
                return False
            except subprocess.TimeoutExpired:
                # Timed out but binary exists (shutil.which passed) — assume installed
                return True
            except Exception:
                return False
        return True

    def detect_task_type(self, user_message: str, errors: List[str]) -> str:
        """Infer task type from the user message and accumulated error log."""
        msg = user_message.lower()
        err_text = " ".join(errors).lower()
        if any(k in msg for k in ["fix", "bug", "error", "broken", "crash", "fail", "debug"]):
            return "debugging"
        if any(k in msg for k in ["refactor", "rewrite", "restructure", "clean up"]):
            return "refactor"
        if any(k in msg for k in ["explain", "what does", "how does", "why does"]):
            return "explain"
        if any(k in msg for k in ["review", "audit", "analyze", "analyse", "check"]):
            return "review"
        if any(k in msg for k in ["create", "write", "build", "generate", "make", "implement"]):
            return "generate"
        if any(k in err_text for k in ["traceback", "syntaxerror", "error:", "failed"]):
            return "debugging"
        return "default"

    def select_cli(self, task_type: str, exclude: List[str] = None) -> Optional[PeerCLI]:
        """
        Pick the best available and enabled CLI for the task type.
        Falls back through preference list, skipping excluded names.
        """
        exclude_resolved = {resolve_peer_name(x) or x for x in (exclude or [])}
        available_clis = self.available(include_disabled=False)
        available_names = {c.name for c in available_clis}
        preference = TASK_CLI_PREFERENCE.get(task_type, TASK_CLI_PREFERENCE["default"])
        for name in preference:
            canonical = resolve_peer_name(name) or name
            if canonical not in exclude_resolved and canonical in available_names:
                return next((c for c in available_clis if c.name == canonical), None)
        return None

    def build_prompt(self, user_message: str, errors: List[str], files: List[str]) -> str:
        """Build a context-rich, directive prompt to pass to the external CLI.

        Requirements:
        - State what Codey already tried and failed at
        - Explicitly request complete file content (not analysis, not a diff)
        - Specify the exact output format Codey will parse to extract code
        - Forbid asking questions or seeking confirmation
        """
        lines = [
            f"Task: {user_message}",
            "",
            "Codey-OS has already attempted this and exhausted its retry budget.",
            "You are responding to an automated system. Do NOT ask for permission.",
            "Do NOT ask clarifying questions. Act immediately.",
        ]
        if files:
            lines.append(f"\nFiles involved: {', '.join(f for f in files if f)}")
        if errors:
            lines.append("\nErrors from Codey's previous attempts:")
            for e in errors[-3:]:
                lines.append(f"  • {e[:300]}")
        lines.append(
            "\nOUTPUT FORMAT (required — Codey parses this automatically):\n"
            "For each file to create or modify, use this exact format:\n\n"
            "**`filename.py`**\n"
            "```python\n"
            "# complete file content here\n"
            "```\n\n"
            "Write COMPLETE file content — no stubs, no placeholders, no '...'.\n"
            "Codey will write these files to disk automatically."
        )
        return "\n".join(lines)

    def confirm(
        self,
        cli: PeerCLI,
        task_type: str,
        user_message: str,
    ) -> Tuple:
        """
        Show the escalation confirmation prompt.

        Returns one of:
          (True,       None)         — proceed with suggested CLI
          (False,      None)         — skip escalation
          ("switch",   cli_name)     — user wants a specific different CLI
          ("redirect", instruction)  — user gave Codey a new instruction
        """
        from utils.logger import console

        available_names = [c.name for c in self.available()]
        others = [n for n in available_names if n != cli.name]

        separator()
        console.print("\n[bold yellow]  ⚠  Codey hit max retries and needs help.[/bold yellow]")
        console.print(
            f"  Task:       [dim]{user_message[:80]}{'…' if len(user_message) > 80 else ''}[/dim]"
        )
        console.print(
            f"  Suggest:    [bold cyan]{cli.description}[/bold cyan]  [dim]({task_type} task)[/dim]"
        )
        if others:
            console.print(f"  Fallbacks:  [dim]{', '.join(others)}[/dim]")
        console.print()
        console.print("  [bold]Your options:[/bold]")
        console.print(f"    [green]y / enter[/green]          Call {cli.description}")
        console.print(f"    [red]n[/red]                  Skip — return control to you")
        if others:
            console.print(f"    [cyan]{' | '.join(others)}[/cyan]" f"{'':>4}Use that CLI instead")
        console.print(f"    [cyan]<any text>[/cyan]         Tell Codey to try differently\n")

        try:
            ans = console.input("  → ").strip()
        except (EOFError, KeyboardInterrupt):
            return False, None

        if not ans or ans.lower() in ("y", "yes"):
            return True, None
        if ans.lower() in ("n", "no"):
            return False, None
        # Check if the answer is a known CLI name or alias
        canonical_ans = resolve_peer_name(ans.lower()) or ans.lower()
        by_name = {c.name: c for c in self.available()}
        if canonical_ans in by_name:
            return "switch", canonical_ans
        # Otherwise treat as a redirect instruction to Codey
        return "redirect", ans

    def call(self, cli: PeerCLI, prompt: str) -> str:
        """
        Open the peer CLI inside Codey's terminal via a PTY, auto-type the
        prompt, let the user interact freely, capture everything it outputs.
        Returns the full captured output as a string.
        """
        from core.peer_shell import run_direct, run_peer, run_prompted

        if cli.prompt_flag and prompt:
            # Non-interactive: cmd -p "task" — clean output, no TUI
            return run_prompted(cli.name, cli.cmd, cli.prompt_flag, prompt, cli.yolo_flag)
        elif cli.use_pty:
            return run_peer(cli.name, cli.cmd, prompt)
        else:
            return run_direct(cli.name, cli.cmd, prompt)

    @staticmethod
    def is_peer_error(output: str) -> bool:
        """Return True if the output is a [PEER_ERROR: ...] sentinel."""
        return bool(output and output.startswith("[PEER_ERROR:"))

    def summarize_result(self, cli_name: str, output: str, original_task: str) -> str:
        """Package the peer CLI output for injection into Codey's context."""
        if not output or len(output.strip()) < 10:
            return f"[Peer: {cli_name} produced no readable output]"
        if self.is_peer_error(output):
            return output  # pass the error sentinel through as-is
        preview = output[:2000].strip()
        return (
            f"[Peer CLI — {cli_name}]\n"
            f"Task: {original_task[:120]}\n"
            f"Output:\n{preview}" + ("\n… [truncated]" if len(output) > 2000 else "")
        )


# ── Singleton + entry point ────────────────────────────────────────────────────

_manager: Optional[PeerCLIManager] = None


def get_peer_cli_manager() -> PeerCLIManager:
    global _manager
    if _manager is None:
        _manager = PeerCLIManager()
    return _manager


def escalate(
    user_message: str,
    errors: List[str],
    files: List[str],
) -> Optional[str]:
    """
    Top-level escalation entry point. Called by agent when retries are exhausted.

    Returns:
      - Summary string to inject into agent context   (peer ran successfully)
      - "[redirect]: <instruction>"                    (user wants Codey to try differently)
      - None                                           (user skipped / no CLIs available)
    """
    mgr = get_peer_cli_manager()

    if not mgr.available():
        warning("No peer CLIs found. Install antigravity / qwen " "to enable escalation.")
        return None

    task_type = mgr.detect_task_type(user_message, errors)
    excluded: List[str] = []

    while True:
        cli = mgr.select_cli(task_type, exclude=excluded)
        if not cli:
            warning("No more peer CLIs available to try.")
            return None

        result, payload = mgr.confirm(cli, task_type, user_message)

        if result is False:
            info("Peer CLI escalation skipped.")
            return None

        if result == "switch":
            canonical_payload = resolve_peer_name(payload) or payload
            by_name = {c.name: c for c in mgr.available()}
            cli = by_name.get(canonical_payload)
            if not cli:
                warning(f"CLI '{payload}' is not available.")
                excluded.append(canonical_payload)
                continue
            result = True  # fall through to call

        if result == "redirect":
            return f"[redirect]: {payload}"

        if result is True:
            prompt = mgr.build_prompt(user_message, errors, files)
            output = mgr.call(cli, prompt)
            summary = mgr.summarize_result(cli.name, output, user_message)
            success(f"Peer CLI ({cli.name}) done — Codey is reading the result…")
            return summary

        # Shouldn't reach here, but skip and try next
        excluded.append(cli.name)


def is_interactive_environment() -> bool:
    """Return True if standard input is an interactive TTY and not running as background daemon."""
    if os.getenv("CODEY_DAEMON_MODE") == "1" or os.getenv("CODEY_NON_INTERACTIVE") == "1":
        return False
    try:
        return sys.stdin.isatty()
    except Exception:
        return True


def escalate_or_park(
    task_id: str,
    user_message: str,
    errors: List[str],
    files: List[str],
    non_blocking: bool = False,
) -> Optional[str]:
    """
    Escalate interactively if in an interactive terminal session, OR park the
    task onto the TaskBlackboard escalation review queue if running headlessly
    in a daemon or if non_blocking is requested (Track A / Item 4.5).
    """
    # If non-blocking or non-interactive daemon environment, park on blackboard queue
    if non_blocking or os.getenv("CODEY_DAEMON_MODE") == "1" or os.getenv("CODEY_NON_INTERACTIVE") == "1":
        try:
            from ccos.core.task_blackboard import get_task_blackboard

            mgr = get_peer_cli_manager()
            task_type = mgr.detect_task_type(user_message, errors)
            suggested_cli = mgr.select_cli(task_type)
            pref_name = suggested_cli.name if suggested_cli else None

            bb = get_task_blackboard()
            error_summary = "\n".join(errors) if errors else ""
            bb.park_escalation(
                task_id=task_id,
                goal=user_message,
                reason="exhausted_retries",
                error_summary=error_summary,
                files_touched=files,
                preferred_peer=pref_name,
            )
            warning(
                f"Task [{task_id}] parked for escalation review on TaskBlackboard "
                f"(suggested peer: {pref_name or 'none'})."
            )
            return f"[parked]: Task {task_id} parked for escalation review."
        except Exception as e:
            warning(f"Failed to park task {task_id} to TaskBlackboard: {e}")
            return None

    # Otherwise run normal interactive escalation
    return escalate(user_message, errors, files)


def list_parked_escalations(status: Optional[str] = "pending") -> List[Dict]:
    """List parked escalation review items from TaskBlackboard."""
    try:
        from ccos.core.task_blackboard import get_task_blackboard

        bb = get_task_blackboard()
        return bb.list_escalations(status=status)
    except Exception as e:
        warning(f"Failed to list escalation reviews: {e}")
        return []


def resolve_parked_escalation(
    task_id: str,
    action: str = "approve",
    peer_name: Optional[str] = None,
    notes: str = "",
) -> bool:
    """
    Resolve or reject a parked escalation review.
    action can be 'approve' / 'resolved' or 'reject' / 'failed'.
    """
    try:
        from ccos.core.task_blackboard import get_task_blackboard

        bb = get_task_blackboard()
        status = "resolved" if action in ("approve", "resolved", "approve_and_run") else "rejected"
        return bb.resolve_escalation(
            task_id=task_id,
            status=status,
            resolution_notes=notes,
            preferred_peer=peer_name,
        )
    except Exception as e:
        warning(f"Failed to resolve escalation review for {task_id}: {e}")
        return False


def execute_parked_escalation(task_id: str, peer_name: Optional[str] = None) -> Optional[str]:
    """
    Execute a previously parked escalation item using the designated or preferred peer CLI.
    """
    try:
        from ccos.core.task_blackboard import get_task_blackboard

        bb = get_task_blackboard()
        record = bb.get_escalation(task_id)
        if not record:
            warning(f"No escalation review found for task {task_id}")
            return None

        mgr = get_peer_cli_manager()
        cli_to_use = peer_name or record.get("preferred_peer") or "antigravity"
        by_name = {c.name: c for c in mgr.available()}
        cli = by_name.get(cli_to_use)
        if not cli:
            # Fallback to any available
            avail = mgr.available()
            if not avail:
                warning("No peer CLIs available.")
                return None
            cli = avail[0]

        prompt = mgr.build_prompt(
            record.get("goal", ""),
            [record.get("error_summary", "")],
            record.get("files_touched", []),
        )
        output = mgr.call(cli, prompt)
        summary = mgr.summarize_result(cli.name, output, record.get("goal", ""))
        bb.resolve_escalation(
            task_id=task_id,
            status="resolved",
            resolution_notes=f"Executed via {cli.name}",
            preferred_peer=cli.name,
        )
        return summary
    except Exception as e:
        warning(f"Failed to execute parked escalation for {task_id}: {e}")
        return None


