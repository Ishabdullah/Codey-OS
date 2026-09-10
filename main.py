#!/usr/bin/env python3
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core import context as ctx
from core.dashboard_data import get_render_text
from core.inference_v2 import was_last_streamed
from core.loader_v2 import get_loader
from core.sysmon import get_monitor
from utils.config import CODEY_VERSION
from utils.logger import console, error, info, separator, success, warning

BANNER = f"""[bold blue]
  ██████╗ ██████╗ ██████╗ ███████╗██╗   ██╗
 ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗ ██╔╝
 ██║     ██║   ██║██║  ██║█████╗   ╚████╔╝
 ██║     ██║   ██║██║  ██║██╔══╝    ╚██╔╝
  ╚██████╗╚██████╔╝██████╔╝███████╗   ██║
   ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝  ─ OS
[/bold blue][dim]  v{CODEY_VERSION} · Privacy-Focused AI Coding Assistant · Termux[/dim]
[dim]  🔒 100% Local · No Telemetry · No Cloud Required[/dim]
"""


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="Codey-OS - Local AI coding assistant")
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--yolo", action="store_true", help="Skip confirmations")
    parser.add_argument("--threads", type=int)
    parser.add_argument("--ctx", type=int)
    parser.add_argument("--version", action="store_true")
    parser.add_argument(
        "--status", action="store_true", help="Print current daemon/agent status and exit"
    )
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--read", nargs="+", metavar="FILE")
    parser.add_argument("--init", action="store_true", help="Generate CODEY.md")
    parser.add_argument("--fix", metavar="FILE", help="Run file, auto-fix errors")
    parser.add_argument("--tdd", metavar="FILE", help="TDD mode: source.py test_source.py")
    parser.add_argument("--tests", metavar="FILE", help="Test file for --tdd mode")
    parser.add_argument(
        "--session", nargs="?", const="list", metavar="ID", help="Resume saved session"
    )
    parser.add_argument("--clear-session", action="store_true", help="Clear saved session")
    parser.add_argument("--plan", action="store_true", help="Enable plan mode for complex tasks")
    parser.add_argument(
        "--no-plan", action="store_true", help="Disable orchestration/planning for complex tasks"
    )
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode (v2 feature)")
    parser.add_argument(
        "--no-resume", action="store_true", help="Start fresh, ignore saved session"
    )
    parser.add_argument(
        "--allow-self-mod",
        action="store_true",
        help="Allow self-modification with checkpoint enforcement",
    )
    # Fine-tuning commands (v2.3.0)
    parser.add_argument(
        "--finetune",
        action="store_true",
        help="Export fine-tuning dataset and generate Colab notebook",
    )
    parser.add_argument(
        "--ft-days", type=int, default=30, help="Days of history to include (default: 30)"
    )
    parser.add_argument(
        "--ft-quality", type=float, default=0.7, help="Min quality threshold 0.0-1.0 (default: 0.7)"
    )
    parser.add_argument(
        "--ft-model", choices=["7b"], default="7b", help="Model variant for fine-tuning"
    )
    parser.add_argument(
        "--ft-output", type=str, help="Output directory (default: ~/Downloads/codey-finetune)"
    )
    parser.add_argument("--import-lora", metavar="PATH", help="Import LoRA adapter from path")
    parser.add_argument(
        "--lora-model", choices=["primary"], default="primary", help="Model for LoRA import"
    )
    parser.add_argument(
        "--lora-quant", type=str, default="q4_0", help="Quantization for merged model"
    )
    parser.add_argument(
        "--lora-merge", action="store_true", help="Merge LoRA on-device (requires llama.cpp)"
    )
    return parser.parse_args()


def apply_overrides(args):
    import os

    from utils import config
    from utils.logger import info

    if args.yolo:
        config.AGENT_CONFIG["confirm_shell"] = False
        config.AGENT_CONFIG["confirm_write"] = False
        info("YOLO mode: confirmations disabled.")

    # Check for self-modification enablement (CLI flag or env var)
    allow_self_mod = args.allow_self_mod or os.environ.get("ALLOW_SELF_MOD", "0") == "1"
    if allow_self_mod:
        config.AGENT_CONFIG["allow_self_modification"] = True
        info("Self-modification enabled: Codey can modify its own source files (with checkpoints).")

    if args.threads:
        config.MODEL_CONFIG["n_threads"] = args.threads
    if args.ctx is not None:
        # NEW-102 fix (2026-08-13): --ctx previously had no positive-value
        # guard, unlike utils/config.py's CODEY_N_CTX env var (added in
        # U.31), which explicitly rejects zero/negative values because
        # they'd flow into core/resource_gate.py's KV-cache cost estimate
        # as a zero/negative term and cause the gate to under-estimate
        # real cost (a negative n_ctx actually SUBTRACTS from the computed
        # cost — a real over-admit risk, not just a milder zero-case).
        # Same guard applied here for the same reason. `is not None` (not
        # a bare truthiness check) so --ctx 0 is also caught explicitly
        # instead of silently no-op'ing (0 was previously falsy and just
        # skipped this whole branch, applying nothing with no error).
        if args.ctx <= 0:
            raise ValueError(
                f"--ctx={args.ctx} is not a valid n_ctx; it must be a positive integer."
            )
        config.MODEL_CONFIG["n_ctx"] = args.ctx


def _daemon_is_running() -> bool:
    """Check if the daemon is running (PID file check)."""
    try:
        from core.daemon import check_pid_file

        return check_pid_file()
    except Exception:
        return False


# Bounded above core.daemon's own worst-case `release_model_slot` latency
# (RELEASE_CONFIRM_TIMEOUT_S's confirm poll plus LlamaServer.stop()'s
# internal `process.wait(timeout=8)`, see core/daemon.py's
# `_handle_release_model_slot`/`_release_model_slot_sync`) rather than
# `send_command()`'s generic 60s default — this call sits in the CLI's own
# model-load path, so it should time out close to the daemon's own real
# worst case (~11s), not silently inherit an unrelated default.
_RELEASE_SLOT_TIMEOUT_S = 20.0


def _load_primary_with_gate_recovery(loader) -> bool:
    """
    Load the primary model via `loader.load_primary()`, and — only if the
    resource gate denied the reservation for a TRANSIENT reason
    (`LOAD_OUTCOME_GATE_DENIED`, not `_HARD`) — ask a running daemon (if
    any) to free a slot via the `release_model_slot` socket command, then
    retry the load exactly once. TODO.md 7.4 sub-task 5 / NEW-69.

    Single retry only: never loops even if the daemon keeps declining
    (busy/cooldown) or the retried load is denied again. Any failure that
    ISN'T a transient gate denial (missing model file, spawn failure, a
    HARD gate denial no release can fix) is returned as-is with no daemon
    contact at all — callers keep today's existing behavior for those
    (`core/inference_v2.py`'s own `ensure_model()` call already retries at
    actual inference time; this project already treats those outcomes as
    lazy-retryable, not something to hard-fail the CLI on at preload
    time — see `_is_unrecovered_gate_denial()` below for the check callers
    use to distinguish "bail now" from "let it lazy-retry").

    Never raises for daemon-communication problems (socket error, no
    daemon running, timeout, or the daemon's own "error" status, which
    `send_command()` turns into a `RuntimeError`) — all of those are
    treated identically to "no daemon to ask": report the ORIGINAL gate
    denial, don't crash on this secondary failure.

    `loader.get_last_ensure_outcome()`/`get_last_ensure_reason()` reflect
    whichever attempt actually ran last (the only attempt, if no retry
    happened; the retry, if one did) — callers should read them AFTER this
    returns, not assume the original denial is still current.
    """
    from core.loader_v2 import LOAD_OUTCOME_GATE_DENIED

    if loader.load_primary():
        return True

    if loader.get_last_ensure_outcome() != LOAD_OUTCOME_GATE_DENIED:
        return False

    original_reason = loader.get_last_ensure_reason()

    if not _daemon_is_running():
        error(
            "Resource gate denied the model load and no daemon is running "
            f"to free a slot: {original_reason}"
        )
        return False

    info("Resource gate denied the model load — asking the daemon to free a slot...")

    from core.daemon import (
        RELEASE_OUTCOME_ALREADY_UNLOADED,
        RELEASE_OUTCOME_RELEASED,
        send_command,
    )

    try:
        response = send_command(
            "release_model_slot",
            {"model_id": "primary"},
            timeout=_RELEASE_SLOT_TIMEOUT_S,
        )
    except Exception as e:
        # Daemon unreachable / socket error / timeout / the daemon's own
        # "error" status (send_command() raises RuntimeError for that) —
        # all treated the same as "no daemon to ask": report the ORIGINAL
        # gate denial, not this secondary communication failure.
        error(
            "Resource gate denied the model load; could not get the daemon "
            f"to free a slot ({e}). Original denial: {original_reason}"
        )
        return False

    outcome = response.get("outcome")
    if outcome not in (RELEASE_OUTCOME_RELEASED, RELEASE_OUTCOME_ALREADY_UNLOADED):
        # busy_task_running / busy_swap_in_flight / cooldown /
        # unload_attempted_unconfirmed (or an unrecognized value) — the
        # daemon did NOT actually free anything, so retrying the load has
        # no reason to succeed differently. Report the ORIGINAL gate
        # denial as the real failure, not this decline.
        error(
            "Resource gate denied the model load; the daemon declined to "
            f"free a slot ({outcome}: {response.get('message', '')}). "
            f"Original denial: {original_reason}"
        )
        return False

    info("Daemon freed a slot — retrying the model load once.")
    return loader.load_primary()


def _is_unrecovered_gate_denial(loader) -> bool:
    """
    True if `loader`'s most recent `load_primary()` outcome is a gate
    denial that `_load_primary_with_gate_recovery()` either couldn't
    recover from (no daemon / daemon declined) or that a retry could never
    fix (`_HARD`). Callers use this to decide whether to bail out with a
    clear failure instead of letting the CLI proceed with no model loaded.
    """
    from core.loader_v2 import LOAD_OUTCOME_GATE_DENIED, LOAD_OUTCOME_GATE_DENIED_HARD

    return loader.get_last_ensure_outcome() in (
        LOAD_OUTCOME_GATE_DENIED,
        LOAD_OUTCOME_GATE_DENIED_HARD,
    )


def shutdown():
    # Stop system monitor
    try:
        get_monitor().stop()
    except Exception:
        pass
    # If daemon is running, leave llama-server alive for it
    if _daemon_is_running():
        return
    # Unload model and kill llama-server on port 8080 — scoped to the PID
    # this loader actually spawned. Never pkill by bare process name: that
    # would also kill unrelated llama-server instances (plannd on 8081, the
    # embed server on 8082, or another session's server entirely).
    try:
        from core.loader_v2 import get_loader

        loader = get_loader()
        _pid = loader.get_pid()
        try:
            loader.unload()
        except Exception:
            # unload() threw before finishing its own kill step — fall back
            # to killing only the PID we captured above, never a name pattern.
            if _pid:
                try:
                    import os
                    import signal

                    os.killpg(os.getpgid(_pid), signal.SIGKILL)
                except Exception:
                    pass
    except Exception:
        pass


def _record_tui_telemetry_run_start():
    """
    Category-G run provenance (docs/telemetry_layer_design.md §2.G, sub-
    task T2). Emitted once, at the start of the interactive TUI session
    (repl()'s call site — see _write_tui_pid_file()'s docstring for why
    this call site, not inside repl() itself, is where session-lifetime
    bookkeeping lives). Local imports and a broad except, same reasoning
    as _write_tui_pid_file()'s own OSError guard just below: telemetry is
    diagnostic, not load-bearing, and a failure here must never block the
    interactive session itself from starting.
    """
    try:
        import time

        from telemetry import provenance, recorders
        from utils.config import CODEY_DIR, EMBED_MODEL_PATH, LLAMA_SERVER_BIN, MODEL_PATH

        models = provenance.build_model_entries(
            [("primary", MODEL_PATH), ("embed", EMBED_MODEL_PATH)]
        )
        recorders.record_run_start(
            emitter="codey-os.tui",
            pid=os.getpid(),
            repo="Codey-OS",
            started_ts_wall=time.time(),
            repo_dir=CODEY_DIR,
            models=models,
            llama_server_bin=LLAMA_SERVER_BIN,
        )
    except Exception:
        warning("telemetry: failed to record run_start for TUI session")


def _record_cli_telemetry_run_start():
    """
    NEW-358 Site 1. Category-G run provenance for main.py's four one-shot
    CLI flags (--init / --tdd / --fix / --import-lora), each of which loads
    the primary model and exits without ever reaching the interactive repl
    path's own record_run_start() call. Without this, every such invocation
    reaches core/loader_v2.py's _ensure_run_start_fallback() and is recorded
    under the generic emitter="codey-os.loader" identity; this gives those
    flags their own emitter="codey-os.cli" identity instead, recorded BEFORE
    the branch does any model-load work, so recorders.record_run_start()'s
    unconditional store.mark_run_start_recorded() has already set the
    breadcrumb by the time core/loader_v2.py's _ensure_run_start_fallback()
    calls store.claim_run_start() -- which then returns False, so that
    fallback no-ops and emits nothing (no duplicate -- see that function's
    docstring).

    Deliberately passes NO `models=` (unlike _record_tui_telemetry_run_start,
    matching tools/ensure_model_cli.py and _ensure_run_start_fallback):
    record_run_start(models=...) schedules a background full-file model hash
    (~5.2s cold), and all four of these flags start a real llama-server load
    within milliseconds of this call and then exit quickly -- the TUI can
    absorb that background thread over a minutes-long session, these cannot.

    Best-effort, broad except: telemetry is diagnostic, never load-bearing,
    and must not block a CLI invocation. Same pattern as this module's
    _record_tui_telemetry_run_start and core/loader_v2.py's fallback.
    """
    try:
        import time

        from telemetry import recorders
        from utils.config import CODEY_DIR, LLAMA_SERVER_BIN

        recorders.record_run_start(
            emitter="codey-os.cli",
            pid=os.getpid(),
            repo="Codey-OS",
            started_ts_wall=time.time(),
            repo_dir=CODEY_DIR,
            llama_server_bin=LLAMA_SERVER_BIN,
        )
    except Exception:
        warning("telemetry: failed to record run_start for CLI flag")


def _write_tui_pid_file():
    """
    Write this process's PID into its own per-session file under
    utils.config.TUI_SESSIONS_DIR (TUI_SESSIONS_DIR / f"{pid}.pid") — the
    PID-bearing, self-healing lock file that lets a separate process (the
    daemon; see core/resource_gate.py's is_tui_session_active()) tell
    whether an interactive main.py session is currently running. Called
    around main()'s repl(...) call site (not from inside repl() itself —
    see that call site's own comment for why: repl()'s ~200-line body
    already has several internal early-return/break paths, each calling
    shutdown() directly, and wrapping the call site in try/finally covers
    all of them without restructuring that existing control flow).

    Not a single-instance-enforcement lock like DAEMON_PID_FILE: two
    concurrent interactive sessions (e.g. two terminals) are a normal,
    supported case here, unlike the daemon. One file per PID (not one
    shared file for all sessions) is what makes that safe: a second
    session's write can never overwrite/truncate a first session's own
    file, because they never share a path. See _remove_tui_pid_file()'s
    docstring for the matching removal side.

    Written via a fixed per-PID temp file in the same directory +
    os.replace(), matching core/resource_gate.py's own
    _write_state_locked() atomic-replace convention, rather than
    open(path, "w") + flock: open(path, "w") truncates BEFORE the lock is
    acquired, so a concurrent reader (is_tui_session_active(), a separate
    process, not this session) can observe an empty file in that window
    and reap this brand-new session's own file as "corrupt" before this
    write ever completes — os.replace() is atomic, so no reader can ever
    observe a partial/empty file for this path.

    Deliberately a FIXED name (TUI_SESSIONS_DIR / f".{pid}.tmp"), not
    tempfile.mkstemp()'s randomly-suffixed name: this function's only
    caller for a given PID is this same process, so there's never a
    collision to avoid, and a fixed name means a crash between opening
    this temp file and the os.replace() below (e.g. SIGKILL, which this
    function cannot catch to clean up after) leaves at most one orphaned
    temp file per PID rather than an ever-growing set of uniquely-named
    ones with no reaper — a future session reusing that same (recycled)
    PID overwrites it via O_TRUNC on the next write.
    """
    from utils.config import TUI_SESSIONS_DIR

    session_file = TUI_SESSIONS_DIR / f"{os.getpid()}.pid"
    tmp_file = TUI_SESSIONS_DIR / f".{os.getpid()}.tmp"
    try:
        TUI_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        with open(tmp_file, "w") as f:
            f.write(str(os.getpid()))
            f.flush()
        os.replace(tmp_file, session_file)
    except OSError:
        # Best-effort signal only — a write failure here (e.g. ~/.codeyOS
        # unwritable) must not block the interactive session itself from
        # starting; the daemon will simply not see this session as active.
        pass


def _remove_tui_pid_file():
    """
    Remove this process's own per-session file under
    utils.config.TUI_SESSIONS_DIR (TUI_SESSIONS_DIR / f"{pid}.pid").

    Because each session's filename is namespaced by its own PID (see
    _write_tui_pid_file()'s docstring), ownership is structural: this
    process can only ever name its own path here, so — unlike an earlier
    single-shared-file design — there is no read-back-and-compare check
    needed to avoid deleting a different, still-live session's entry. A
    second concurrent session's write/crash/exit can never touch this
    file, by construction, because it never shares this path.
    """
    from utils.config import TUI_SESSIONS_DIR

    session_file = TUI_SESSIONS_DIR / f"{os.getpid()}.pid"
    try:
        session_file.unlink(missing_ok=True)
    except OSError:
        # Best-effort cleanup only, called from a `finally` block around
        # repl() — a removal failure here (e.g. permissions changed
        # mid-session) must not raise out of session teardown; at worst
        # is_tui_session_active() reaps this entry itself once the PID is
        # confirmed dead on its own next check.
        pass


def run_init():
    from core.codeymd import find_codeymd, get_init_prompt, write_codeymd
    from core.inference_v2 import infer
    from core.project import detect_project

    existing = find_codeymd()
    if existing:
        warning(f"CODEY.md already exists at {existing}")
        ans = console.input("Overwrite? [y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            info("Aborted.")
            return
    proj = detect_project()
    info(f"Analyzing {proj['type']} project in {proj['cwd']}...")
    messages = [
        {
            "role": "system",
            "content": "You are a technical writer. Output only clean markdown, no preamble.",
        },
        {"role": "user", "content": get_init_prompt(proj)},
    ]
    info("Generating CODEY.md...")
    content = infer(messages, stream=False)
    if content.startswith("[ERROR]"):
        error(f"Generation failed: {content}")
        return
    path = write_codeymd(content)
    success(f"CODEY.md written to {path}") if not path.startswith("[ERROR]") else error(path)


def _try_daemon_plan(prompt: str, no_plan: bool = False, tier: str = "hard"):
    """Thin shim — delegates to core.planner_service._request_daemon_plan."""
    from core.planner_service import _request_daemon_plan

    if no_plan:
        return None
    return _request_daemon_plan(prompt, tier=tier)


def _extract_filename_from_step(step: str) -> str:
    """
    Extract a filename from a plan step description.

    Matches backtick-quoted names first (e.g. `wordcount.py`), then falls back
    to any word containing a dot-extension (e.g. fibonacci.py).
    Returns an empty string if no filename is found.
    """
    import re

    m = re.search(r"`([^`]+\.[a-zA-Z0-9]{1,10})`", step)
    if m:
        return m.group(1)
    m = re.search(r"\b(\w[\w.-]*\.[a-zA-Z0-9]{1,5})\b", step)
    if m:
        return m.group(1)
    return ""


def _execute_agent_capability(
    prompt: str = "",
    history: list = None,
    yolo: bool = False,
    use_plan: bool = False,
    no_plan: bool = False,
    in_subtask: bool = False,
    plan_rag_block: str = "",
    confirm_shell: bool = None,
    confirm_write: bool = None,
    shell_fn = None,
    **kwargs,
):
    """
    Unified agent execution helper routing through CCOS capability `coding.run_agent`.
    Returns (response, history) compatible with the AgentExecutionResult contract.
    """
    from ccos.core.plugin_manager import get_plugin_manager

    pm = get_plugin_manager()
    if "agent" not in pm._modules:
        pm.load("agent")

    return pm.call_capability(
        "coding.run_agent",
        prompt=prompt,
        history=history,
        yolo=yolo,
        use_plan=use_plan,
        no_plan=no_plan,
        in_subtask=in_subtask,
        plan_rag_block=plan_rag_block,
        confirm_shell=confirm_shell,
        confirm_write=confirm_write,
        shell_fn=shell_fn,
        **kwargs,
    )


def _run_with_plan(prompt: str, history: list, yolo: bool, use_plan: bool, no_plan: bool):
    """
    Execute a user prompt, routing through the daemon for planning when available.

    If the daemon is running and plannd returns a plan:
      1. Print the numbered plan from DeepSeek before any execution begins.
      2. Run each step through run_agent() locally (7B model, visible in terminal).
      3. After file-creation steps, verify the file was actually written.
         If not, retry the step once before continuing.

    Otherwise fall back to a direct run_agent() call — identical to existing behaviour.

    Returns (response, updated_history) with the same contract as run_agent().
    """
    import os
    import re
    from pathlib import Path

    # ── Peer delegation gate ──────────────────────────────────────────────────
    # For SINGLE-STEP peer directives ("ask claude to X" with no follow-up),
    # skip plannd and route straight to run_agent — the _detect_peer_delegation
    # path in agent.py handles it directly.
    #
    # For MULTI-STEP prompts ("Use Gemini to design X. Then use Qwen to
    # implement it."), fall through to plannd so ALL steps get planned and
    # executed in sequence. plannd Rule 8 preserves "Ask gemini to X" phrasing,
    # and filter_tool_steps keeps peer steps in the plan.
    _PEER_NAMES = [
        "antigravity",
        "agy",
        "gemini",
        "qwen",
        "qwen-code",
        "qwen3.5",
        "claude",
        "claude-code",
    ]
    _peer_directive_re = re.compile(
        r"\b(?:ask|call|have|tell|use|get|let)\s+(" + "|".join(_PEER_NAMES) + r")\b",
        re.IGNORECASE,
    )
    # Multi-step signals: sentence-boundary transition words, or more than one peer mentioned
    _MULTI_STEP_RE = re.compile(
        r"[.!?\n]\s*\b(?:then|after(?:\s+that)?|also|additionally|next|finally|"
        r"and\s+(?:run|show|test|verify|use|ask|have|call|write|create|commit|init))\b",
        re.IGNORECASE,
    )
    _peer_hits = _peer_directive_re.findall(prompt)
    _is_solo_peer = (
        bool(_peer_hits)
        and len(set(h.lower() for h in _peer_hits)) == 1  # only one peer mentioned
        and not _MULTI_STEP_RE.search(prompt)  # no multi-step signals
    )
    if not no_plan and _is_solo_peer:
        return _execute_agent_capability(prompt, history, yolo=yolo, use_plan=use_plan, no_plan=no_plan)
    # Multi-peer or multi-step peer prompts fall through to plannd below

    # ── Complexity gate: skip the planner for simple, non-complex tasks ───────
    # Mirrors the pattern in core/agent.py:1256 which gates its own orchestrator
    # planner behind is_complex(). Simple single-step edits should go straight
    # to the agent instead of routing through the planner.
    #
    # 7.3 sub-task E, Task B (2026-08-24): score once and reuse for both the
    # easy-tier gate and the medium/hard tier split below, rather than
    # scoring the same prompt twice.
    from core.orchestrator import _score_message, is_complex

    score = _score_message(prompt)
    if not is_complex(prompt, score=score):
        return _execute_agent_capability(prompt, history, yolo=yolo, use_plan=use_plan, no_plan=no_plan)

    # Medium/hard tier split on the post-easy-gate population: reuses
    # is_complex()'s own existing `length > 300` boundary (NEW-174 notes
    # this boundary is currently dead-identical to `length > 150` inside
    # is_complex() itself — unrelated pre-existing defect, not fixed here).
    # "hard" (enable_thinking=True) is the default/fallback, matching
    # M1-D's thinking-mode-by-default design.
    tier = "medium" if score.length > 300 else "hard"
    if not no_plan:
        # Guarded on no_plan: _try_daemon_plan(prompt, no_plan=True, ...)
        # below returns None immediately without planning at all — logging
        # a tier decision for a plan that never happens would be noise on
        # every --no-plan invocation.
        info(
            f"Planning tier: {tier} (has_action={score.has_action}, "
            f"length={score.length}, signal_count={score.signal_count})"
        )

    plan = _try_daemon_plan(prompt, no_plan, tier=tier)

    if plan:
        separator()
        console.print("[bold cyan]Plan:[/bold cyan]")
        for i, step in enumerate(plan, 1):
            console.print(f"  [bold cyan]{i}.[/bold cyan] {step}")
        separator()

        _CREATE_KEYWORDS = {"create", "write", "make", "build", "generate", "save"}

        # Retrieve once on the full user prompt so every step gets the richest
        # possible KB context instead of querying on terse planner-generated text.
        _plan_rag = ""
        try:
            from core.retrieval import retrieve

            _plan_rag = retrieve(prompt) or ""
        except Exception:
            pass

        response = ""
        for i, step in enumerate(plan, 1):
            console.print(f"\n[dim]── Step {i}/{len(plan)}: {step}[/dim]")
            # Prepend the original user goal so the agent can resolve any
            # filename/path discrepancies introduced by the planner (e.g.
            # planner abbreviates "fibonacci.py" → "fib.py"; agent sees the
            # overall goal and uses the correct name per the system prompt rule).
            step_with_goal = f"Overall goal: {prompt}\n\nCurrent step: {step}"
            step_resp, history = _execute_agent_capability(
                step_with_goal, history, yolo=yolo, no_plan=True, plan_rag_block=_plan_rag
            )
            response = step_resp or response

            # Post-step: if this step was supposed to create a file, verify it
            # actually exists. If not, retry once before moving to the next step.
            step_low = step.lower()
            if any(k in step_low for k in _CREATE_KEYWORDS):
                fname = _extract_filename_from_step(step)
                # Also try extracting the filename from the original user prompt
                # in case the planner abbreviated it (e.g. fib.py vs fibonacci.py).
                fname_goal = _extract_filename_from_step(prompt)
                # Use the goal filename when it shares a stem with the plan filename
                # (e.g. "fib" is a prefix of "fibonacci") — the goal is authoritative.
                if fname_goal and fname and fname != fname_goal:
                    plan_stem = Path(fname).stem.lower()
                    goal_stem = Path(fname_goal).stem.lower()
                    if goal_stem.startswith(plan_stem) or plan_stem.startswith(goal_stem):
                        fname = fname_goal
                if fname:
                    target = Path(os.getcwd()) / fname
                    if not target.exists():
                        # Check if the file was placed in a subdirectory instead
                        found_elsewhere = list(Path(os.getcwd()).rglob(fname))
                        if found_elsewhere:
                            wrong_path = found_elsewhere[0]
                            rel = wrong_path.relative_to(os.getcwd())
                            warning(
                                f"Step {i}: '{fname}' created at '{rel}' instead of cwd — retrying"
                            )
                            console.print(
                                f"\n[dim]↺  Step {i}/{len(plan)} retry (wrong path)[/dim]"
                            )
                            _retry_prefix = (
                                f"RETRY: '{fname}' was written to '{rel}' instead of the "
                                f"current working directory. "
                                f'Run: shell mv "{rel}" "{fname}" to move it, OR '
                                f"delete '{rel}' and re-create '{fname}' directly in cwd. "
                                "Do NOT create or use subdirectories.\n\n"
                            )
                        else:
                            warning(f"Step {i}: '{fname}' not found after step — retrying")
                            console.print(
                                f"\n[dim]↺  Step {i}/{len(plan)} retry (file not created)[/dim]"
                            )
                            _prev_summary = (step_resp or "")[:300]
                            _retry_prefix = (
                                f"RETRY: The previous attempt did not create '{fname}'. "
                                f"Previous result: {_prev_summary}. "
                                f"You MUST create '{fname}' in the current working directory "
                                "using write_file. Do not create subdirectories.\n\n"
                            )
                        step_resp, history = _execute_agent_capability(
                            _retry_prefix + step_with_goal,
                            history,
                            yolo=yolo,
                            no_plan=True,
                            plan_rag_block=_plan_rag,
                        )
                        response = step_resp or response

        return response, history

    # No plan available — run directly as before
    return _execute_agent_capability(prompt, history, yolo=yolo, use_plan=use_plan, no_plan=no_plan)


def print_diff(diff_output: str):
    for line in diff_output.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-") and not line.startswith("---"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")
        else:
            console.print(line)


def handle_command(user_input: str, history: list, yolo: bool = False) -> tuple[bool, list]:
    cmd = user_input.strip()
    low = cmd.lower()

    if low in ("/exit", "/quit", "exit", "quit"):
        from core.sessions import save_session

        save_session(history)
        console.print("[dim]Session saved. Goodbye![/dim]")
        shutdown()
        sys.exit(0)

    if low == "/clear":
        history.clear()
        ctx.clear_context()
        from core.filehistory import clear_history

        clear_history()
        from core.sessions import clear_session

        clear_session()
        success("History, context, undo history, and saved session cleared.")
        return True, history

    if low == "/summarize":
        if len(history) < 4:
            info("Not enough history to summarize (need at least 2 turns).")
        else:
            from core.summarizer import summarize_history
            from core.tokens import estimate_messages_tokens

            old_tokens = estimate_messages_tokens(history)
            history = summarize_history(history)
            new_tokens = estimate_messages_tokens(history)
            success(f"Context compressed: {old_tokens} → {new_tokens} tokens")
        return True, history

    if low.startswith("/undo"):
        from core.filehistory import list_history, undo

        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            hist = list_history()
            if not hist:
                info("Nothing to undo this session.")
            else:
                console.print("[bold]Files with undo history:[/bold]")
                for path, timestamps in hist.items():
                    console.print(f"  📄 {Path(path).name} — {', '.join(timestamps)}")
                info("Usage: /undo <filename>")
        else:
            result = undo(parts[1])
            error(result) if result.startswith("[ERROR]") else None
        return True, history

    if low.startswith("/diff"):
        from core.filehistory import diff, list_history

        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            hist = list_history()
            if not hist:
                info("No file changes this session.")
            else:
                console.print("[bold]Changed files:[/bold]")
                for path in hist:
                    console.print(f"  📄 {Path(path).name}")
                info("Usage: /diff <filename>")
        else:
            result = diff(parts[1])
            if result.startswith("[ERROR]") or result.startswith("No"):
                info(result)
            else:
                print_diff(result)
        return True, history

    if low.startswith("/search"):
        from core.search import search_in_project

        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            info("Usage: /search <pattern> [path]")
            info("       /search def run_agent")
            info("       /search import core/")
        else:
            query_parts = parts[1].rsplit(maxsplit=1)
            # Only treat last arg as path if it looks like a path (starts with . / ~ or is a dir)
            if len(query_parts) > 1 and (
                query_parts[-1].startswith((".", "/", "~")) or os.path.isdir(query_parts[-1])
            ):
                pattern = query_parts[0]
                search_path = query_parts[1]
            else:
                pattern = parts[1]  # whole thing is the pattern
                search_path = "."
            result = search_in_project(pattern, search_path)
            console.print(result)
        return True, history

    if low.startswith("/git"):
        from core.githelper import (detect_conflicts, generate_commit_message,
                                    get_conflict_sections, git_branch_create,
                                    git_branches, git_checkout, git_commit,
                                    git_commit_log_messages,
                                    git_current_branch, git_diff_for_commit,
                                    git_log, git_merge, git_push, git_status,
                                    is_git_repo)

        parts = cmd.split(maxsplit=2)

        if not is_git_repo():
            error("Not a git repository.")
            return True, history

        sub = parts[1].strip() if len(parts) > 1 else ""
        sub_low = sub.lower()
        arg = parts[2].strip() if len(parts) > 2 else ""

        if sub_low == "status" or sub == "":
            console.print(git_status())

        elif sub_low == "log":
            console.print(git_log())

        elif sub_low == "branches":
            console.print(git_branches())

        elif sub_low == "branch":
            if not arg:
                error("Usage: /git branch <name>")
            else:
                result = git_branch_create(arg)
                success(result) if not result.startswith("[ERROR]") else error(result)

        elif sub_low == "checkout":
            if not arg:
                error("Usage: /git checkout <branch>")
            else:
                current = git_current_branch()
                console.print(f"Switching from [bold]{current}[/bold] → [bold]{arg}[/bold]")
                try:
                    confirm = input("Confirm? [y/N] ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    confirm = "n"
                if confirm == "y":
                    result = git_checkout(arg)
                    success(result) if not result.startswith("[ERROR]") else error(result)
                else:
                    info("Checkout cancelled.")

        elif sub_low == "merge":
            if not arg:
                error("Usage: /git merge <branch>")
            else:
                result = git_merge(arg)
                if result.startswith("OK:"):
                    success(result[3:].strip() or "Merged successfully.")
                elif result.startswith("[CONFLICT]"):
                    warning(result)
                    # Conflict resolution flow
                    conflict_files = detect_conflicts()
                    if conflict_files:
                        console.print(
                            f"\n[bold red]Conflicts in {len(conflict_files)} file(s):[/bold red]"
                        )
                        for cf in conflict_files:
                            console.print(f"  • {cf}")
                        try:
                            resolve = (
                                input("\nAsk Codey to resolve conflicts? [y/N] ").strip().lower()
                            )
                        except (EOFError, KeyboardInterrupt):
                            resolve = "n"
                        if resolve == "y":
                            conflict_context = []
                            for cf in conflict_files[:3]:  # cap at 3 files
                                sections = get_conflict_sections(cf)
                                if sections.get("has_conflicts"):
                                    conflict_context.append(
                                        f"File: {cf}\n"
                                        f"OURS (HEAD):\n{sections['ours']}\n"
                                        f"THEIRS ({arg}):\n{sections['theirs']}\n"
                                        f"({sections['count']} conflict block(s))"
                                    )
                            prompt = (
                                f"There are merge conflicts after merging branch '{arg}'. "
                                f"Please resolve them.\n\n" + "\n\n".join(conflict_context)
                            )
                            _, history = _execute_agent_capability(prompt, history, yolo=yolo)
                    else:
                        info("Resolve conflicts manually, then run: /git commit")
                else:
                    error(result)

        elif sub_low == "diff":
            diff = git_diff_for_commit()
            console.print(diff or "(no diff)")

        elif sub_low == "commit":
            # Smart AI-generated commit message
            if arg:
                # Message provided directly: /git commit <message>
                result = git_commit(arg)
            else:
                # Generate message from diff
                diff = git_diff_for_commit()
                if diff == "(no diff available)":
                    info("Nothing to commit — working tree clean.")
                    return True, history
                console.print("[dim]Analyzing diff to generate commit message…[/dim]")
                history_msgs = git_commit_log_messages()
                suggested = generate_commit_message(diff, history_msgs)
                console.print(f"\nSuggested message: [bold cyan]{suggested}[/bold cyan]")
                try:
                    user_msg = input("Press Enter to accept, or type a new message: ").strip()
                except (EOFError, KeyboardInterrupt):
                    info("Commit cancelled.")
                    return True, history
                final_msg = user_msg if user_msg else suggested
                result = git_commit(final_msg)
            if result.startswith("[ERROR]"):
                error(result)
            elif result.startswith("Nothing"):
                info(result)
            else:
                success(result)

        elif sub_low.startswith("push"):
            result = git_push()
            success(result) if not result.startswith("[ERROR]") else error(result)

        elif sub_low == "conflicts":
            conflict_files = detect_conflicts()
            if not conflict_files:
                success("No conflicts detected.")
            else:
                console.print(f"[bold red]Conflicted files ({len(conflict_files)}):[/bold red]")
                for cf in conflict_files:
                    sections = get_conflict_sections(cf)
                    blocks = sections.get("count", "?")
                    console.print(f"  • {cf}  ({blocks} block(s))")

        else:
            # Backward compat: treat sub+arg as a raw commit message
            raw_msg = (sub + (" " + arg if arg else "")).strip()
            result = git_commit(raw_msg)
            if result.startswith("[ERROR]"):
                error(result)
            elif result.startswith("Nothing"):
                info(result)
            else:
                success(result)

        return True, history

    if low.startswith("/sessions"):
        from core.sessions import list_sessions

        sessions = list_sessions()
        if not sessions:
            info("No saved sessions.")
        else:
            console.print("[bold]Saved sessions:[/bold]")
            for s in sessions:
                console.print(
                    f"  📁 {Path(s['project']).name} — {s['turns']} turns — {s['saved_at']}"
                )
        return True, history

    if low.startswith("/load"):
        parts = cmd.split()[1:]
        if not parts:
            info("Usage: /load <file|glob|dir> ...")
        else:
            for target in parts:
                p = Path(target)
                if p.is_dir():
                    ctx.load_directory(str(p))
                elif "*" in target or "?" in target:
                    ctx.load_glob(target)
                else:
                    ctx.load_file(target)
        return True, history

    if low.startswith("/read"):
        parts = cmd.split()[1:]
        if not parts:
            info("Usage: /read <file1> [file2] ...")
        else:
            for f in parts:
                ctx.load_file(f)
        return True, history

    if low.startswith("/unread"):
        parts = cmd.split()[1:]
        for f in parts:
            ctx.unload_file(f)
        return True, history

    if low == "/context":
        from core.memory_v2 import memory as _mem

        s = _mem.status()
        loaded = s["file_names"]
        if loaded:
            console.print(f"[bold]Files in memory (turn {s['turn']}):[/bold]")
            for fname in loaded:
                files = _mem._files
                for k, r in files.items():
                    if r.name == fname:
                        age = s["turn"] - r.last_used_turn
                        score_hint = f"last used {age} turns ago"
                        console.print(f"  📄 {r.name} ({r.tokens} tokens, {score_hint})")
        else:
            info("No files in memory. Use /load or /read to add files.")
        return True, history

    if low == "/project":
        from core.project import detect_project

        proj = detect_project()
        console.print(f"[bold]Project:[/bold] {proj['type']} · {proj['cwd']}")
        if proj["key_files"]:
            console.print(f"[bold]Key files:[/bold] {', '.join(proj['key_files'])}")
        return True, history

    if low == "/init":
        run_init()
        return True, history

    if low == "/memory":
        from core.codeymd import find_codeymd, read_codeymd

        path = find_codeymd()
        if path:
            console.print(f"[bold]CODEY.md[/bold] ({path}):\n")
            console.print(read_codeymd())
        else:
            info("No CODEY.md found. Run /init to generate one.")
        return True, history

    if low.startswith("/memory-status"):
        from core.memory_v2 import memory as _mem

        s = _mem.status()
        console.print(f"[bold]Memory status — turn {s['turn']}:[/bold]")
        console.print(f"  Files in memory:  {s['files']} — {', '.join(s['file_names']) or 'none'}")
        console.print(f"  Summary:          {s['summary_tokens']} tokens")
        if _mem.get_summary():
            console.print(f"[dim]{_mem.get_summary()}[/dim]")
        return True, history

    if low.startswith("/memory-v2"):
        from core.memory_v2 import memory as _mem

        s = _mem.status()
        console.print("[bold]Four-Tier Memory Status:[/bold]")
        console.print()
        # Tier 1: Working Memory
        console.print("[bold cyan]1. Working Memory[/bold cyan]")
        console.print(
            f"   Files: {s['working']['files']} — {', '.join(s['working']['file_names']) or 'none'}"
        )
        console.print(f"   Tokens: {s['working']['total_tokens']} / {s['working']['turn']} turns")
        console.print()
        # Tier 2: Project Memory
        console.print("[bold cyan]2. Project Memory (never evicted)[/bold cyan]")
        _proj_files = _mem.project.get_protected_files()
        console.print(f"   Protected files: {len(_proj_files)}")
        for pf in _proj_files[:10]:
            console.print(f"     • {pf}")
        if len(_proj_files) > 10:
            console.print(f"     ... and {len(_proj_files) - 10} more")
        console.print()
        # Tier 3: Long-term Memory
        console.print("[bold cyan]3. Long-term Memory (embeddings)[/bold cyan]")
        _lt = s["longterm"]
        if _lt["available"]:
            console.print(f"   Status: available")
            console.print(f"   Embeddings: {_lt['embeddings']}")
        else:
            console.print(f"   Status: unavailable ({_lt.get('init_error', 'not initialized')})")
        console.print()
        # Tier 4: Episodic Memory
        console.print("[bold cyan]4. Episodic Memory (action log)[/bold cyan]")
        _recent = _mem.episodic.get_recent(10)
        if _recent:
            console.print(f"   Recent actions (last {len(_recent)}):")
            for action in _recent[-5:]:
                _action = action.get("action", "unknown")
                _details = action.get("details", "")[:60]
                _ts = action.get("timestamp", "")
                console.print(f"     [{_ts}] {_action}: {_details}")
        else:
            console.print("   No recent actions logged")
        console.print()
        # Tier 5: Symbolic Memory
        console.print("[bold cyan]5. Symbolic Memory (concept graph)[/bold cyan]")
        _sym = s["symbolic"]
        if _sym.get("available"):
            console.print(f"   Status: available")
            console.print(f"   Concepts: {_sym.get('concepts', 0)}")
            console.print(f"   Relations: {_sym.get('relations', 0)}")
        else:
            console.print(f"   Status: unavailable ({_sym.get('init_error', 'not initialized')})")
        console.print()
        return True, history

    if low.startswith("/cwd"):
        parts = cmd.split(maxsplit=1)
        if len(parts) > 1:
            try:
                os.chdir(parts[1])
                new_cwd = os.getcwd()
                # Update WORKSPACE_ROOT so Filesystem boundary checks use new dir
                from pathlib import Path as _Path

                import utils.config as _cfg

                _cfg.WORKSPACE_ROOT = _Path(new_cwd).resolve()
                # Reset Filesystem singleton so next tool call picks up new workspace
                from core.filesystem import reset_filesystem

                reset_filesystem()
                # Invalidate project cache (repo map, project type)
                from core.project import invalidate_cache

                invalidate_cache()
                # Invalidate .codeyignore pattern cache for old cwd
                from core import context as _ctx

                _ctx._ignore_cache.clear()
                success(f"Working directory: {new_cwd}")
            except Exception as e:
                error(str(e))
        else:
            info(f"Current directory: {os.getcwd()}")
        return True, history

    if low.startswith("/ignore"):
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            info("Usage: /ignore <pattern>")
        else:
            pattern = parts[1].strip()
            ignore_file = Path(os.getcwd()) / ".codeyignore"
            try:
                with open(ignore_file, "a") as f:
                    f.write(f"\n{pattern}")
                success(f"Added '{pattern}' to .codeyignore")
            except Exception as e:
                error(f"Could not update .codeyignore: {e}")
        return True, history

    if low == "/learning":
        from core.learning import get_learning_manager

        learning = get_learning_manager()
        status = learning.get_status()

        console.print("\n[bold]Learning System Status[/bold]\n")

        # Preferences
        console.print("[bold cyan]Preferences:[/bold cyan]")
        prefs = status["preferences"]["preferences"]
        if prefs:
            for key, value in prefs.items():
                conf = status["preferences"]["confidence"].get(key, 0)
                bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
                console.print(f"  {key}: [green]{value}[/green] [{bar}]")
        else:
            console.print("  [dim]No preferences learned yet[/dim]")

        # Errors
        console.print("\n[bold cyan]Error Database:[/bold cyan]")
        console.print(f"  Patterns: {status['errors']['total_patterns']}")
        console.print(f"  Occurrences: {status['errors']['total_occurrences']}")
        console.print(f"  Fixed: {status['errors']['total_fixed']}")
        console.print(f"  Success Rate: {status['errors']['success_rate']}")

        # Strategies
        console.print("\n[bold cyan]Strategy Tracker:[/bold cyan]")
        console.print(f"  Strategies: {status['strategies']['total_strategies']}")
        console.print(f"  Total Attempts: {status['strategies']['total_attempts']}")
        console.print(f"  Overall Success: {status['strategies']['overall_success_rate']:.1f}%")

        top = status["strategies"].get("top_strategies", [])
        if top:
            console.print("  [dim]Top Strategies:[/dim]")
            for s in top[:3]:
                console.print(
                    f"    {s['name']}: {s['success_rate']*100:.0f}% ({s['attempts']} attempts)"
                )

        return True, history

    # ── /review ──────────────────────────────────────────────────────────────
    if low.startswith("/review"):
        from core.linter import get_available_linters, run_all_linters

        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            info("Usage: /review <file.py>")
            return True, history

        filepath = parts[1].strip()
        from pathlib import Path as _P

        if not _P(filepath).exists():
            error(f"File not found: {filepath}")
            return True, history

        available = get_available_linters()
        if not available:
            warning("No linters installed. Get better results with: pip install ruff")

        console.print(f"\n[bold]Code Review:[/bold] {filepath}\n")
        all_results = run_all_linters(filepath)
        total_issues = 0
        review_lines = []

        for tool_name, issues in all_results:
            if tool_name == "syntax" and not issues:
                continue  # skip clean syntax row — clutters the output
            errors_only = [i for i in issues if i.severity == "error"]
            warnings_only = [i for i in issues if i.severity != "error"]
            if issues:
                console.print(f"  [bold cyan]{tool_name}[/bold cyan] — {len(issues)} issue(s):")
                for issue in (errors_only + warnings_only)[:20]:
                    color = "red" if issue.severity == "error" else "yellow"
                    sym = "✗" if issue.severity == "error" else "⚠"
                    console.print(
                        f"    [{color}]{sym} Line {issue.line}[/{color}] [{issue.code}] {issue.message}"
                    )
                    review_lines.append(f"Line {issue.line}: [{issue.code}] {issue.message}")
                if len(issues) > 20:
                    console.print(f"    [dim]... and {len(issues) - 20} more[/dim]")
                total_issues += len(issues)
            else:
                console.print(f"  [bold cyan]{tool_name}[/bold cyan] — [green]clean[/green]")

        if not all_results:
            console.print("  [dim]No linters available. Run: pip install ruff[/dim]")

        console.print(f"\n  [bold]Total:[/bold] {total_issues} issue(s)\n")

        # Offer agent explanation + fix
        if total_issues > 0 and review_lines:
            try:
                ans = console.input("  Ask Codey to explain and fix? [y/N]: ").strip().lower()
                if ans in ("y", "yes"):
                    ctx_block = "\n".join(review_lines[:15])
                    response, history = _execute_agent_capability(
                        f"Review {filepath} and fix these linter issues (read the file first):\n{ctx_block}",
                        history,
                        yolo=yolo,
                    )
                    if response and not response.startswith("["):
                        separator()
                        console.print(f"\n[bold green]Codey-OS:[/bold green] {response}")
                        separator()
                    from core.sessions import save_session

                    save_session(history)
            except (KeyboardInterrupt, EOFError):
                pass
        return True, history

    # ── /voice ───────────────────────────────────────────────────────────────
    if low.startswith("/voice"):
        from core.voice import get_voice

        v = get_voice()
        parts = cmd.split()
        sub = parts[1].lower() if len(parts) > 1 else ""

        if sub == "on":
            v.turn_on()
        elif sub == "off":
            v.turn_off()
        elif sub == "listen":
            text = v.listen()
            if text:
                info(f"Voice input: {text}")
                # Run as agent task immediately
                try:
                    response, history = _execute_agent_capability(text, history, yolo=yolo)
                    if response and not response.startswith("["):
                        separator()
                        console.print(f"\n[bold green]Codey-OS:[/bold green] {response}")
                        separator()
                        if v.enabled and v.tts_available():
                            try:
                                v.speak(response)
                            except KeyboardInterrupt:
                                pass
                    from core.sessions import save_session

                    save_session(history)
                except KeyboardInterrupt:
                    console.print("\n[dim]Interrupted.[/dim]")
        elif sub == "rate":
            if len(parts) > 2:
                try:
                    v.set_rate(float(parts[2]))
                except ValueError:
                    error("Usage: /voice rate <number>  (e.g. /voice rate 1.5)")
            else:
                error("Usage: /voice rate <number>  (e.g. /voice rate 1.5)")
        elif sub == "pitch":
            if len(parts) > 2:
                try:
                    v.set_pitch(float(parts[2]))
                except ValueError:
                    error("Usage: /voice pitch <number>  (e.g. /voice pitch 0.9)")
            else:
                error("Usage: /voice pitch <number>")
        elif sub == "speak" and len(parts) > 2:
            # /voice speak <text> — one-shot TTS test
            text_to_speak = " ".join(parts[2:])
            if not v.speak(text_to_speak):
                warning("TTS unavailable. Install Termux:API.")
        else:
            # /voice with no sub-command → show status + help
            console.print(f"\n  {v.status()}\n")
            console.print("  [bold]Voice commands:[/bold]")
            console.print("    /voice on              Enable voice mode (TTS + STT)")
            console.print("    /voice off             Disable voice mode")
            console.print("    /voice listen          One-shot voice input → agent")
            console.print("    /voice rate <n>        Set TTS speed  (default 1.0)")
            console.print("    /voice pitch <n>       Set TTS pitch  (default 1.0)")
            console.print("    /voice speak <text>    Test TTS with given text\n")
        return True, history

    if low.startswith("/peer"):
        from core.peer_cli import (get_peer_cli_manager, is_peer_enabled,
                                   resolve_peer_name)

        mgr = get_peer_cli_manager()
        parts = cmd.split(maxsplit=2)
        all_clis = mgr.available(include_disabled=True)
        enabled_clis = mgr.available(include_disabled=False)
        if not all_clis:
            warning("No peer CLIs found (antigravity / qwen / claude).")
            return True, history

        # /peer → list available CLIs
        if len(parts) == 1:
            console.print("[bold]Available peer CLIs:[/bold]")
            for c in all_clis:
                if c.enabled:
                    alias_str = f" [dim](aliases: {', '.join(c.aliases)})[/dim]" if c.aliases else ""
                    console.print(f"  [cyan]{c.name}[/cyan]  —  {c.description}{alias_str}")
                else:
                    reason = f" [dim]({c.disabled_reason})[/dim]" if c.disabled_reason else " [dim](disabled)[/dim]"
                    console.print(f"  [dim red]{c.name}[/dim red]  —  [dim]{c.description}{reason}[/dim]")
            console.print("\nUsage: /peer <name> <task>  or  /peer <name>  (open interactive)")
            console.print("       /peer antigravity explain this function")
            console.print("       /peer qwen write a hello world in Python")
            return True, history

        # /peer <name> <task>  OR  /peer <task>  (auto-pick)
        canonical_target = resolve_peer_name(parts[1].lower())
        by_name = {c.name: c for c in all_clis}
        if canonical_target and canonical_target in by_name:
            if not is_peer_enabled(canonical_target):
                peer_obj = by_name[canonical_target]
                reason = peer_obj.disabled_reason or "disabled"
                warning(f"Peer '{canonical_target}' is disabled ({reason}).")
                task = parts[2] if len(parts) >= 3 else ""
                if task:
                    fallback_cli = mgr.select_cli(mgr.detect_task_type(task, []))
                    if fallback_cli:
                        info(f"Redirecting to {fallback_cli.description}...")
                        cli = fallback_cli
                    else:
                        error(f"No enabled fallback peer available.")
                        return True, history
                else:
                    return True, history
            else:
                cli = by_name[canonical_target]
                task = parts[2] if len(parts) >= 3 else ""
        else:
            # No CLI name given — auto-pick based on task
            task = " ".join(parts[1:])
            task_type = mgr.detect_task_type(task, [])
            cli = mgr.select_cli(task_type)
            if not cli:
                error("No peer CLIs available.")
                return True, history
            info(f"Auto-selected: {cli.description}")

        # Pass the raw task — no wrapping needed for direct /peer calls
        output = mgr.call(cli, task)
        if mgr.is_peer_error(output):
            error(f"Peer {cli.name} failed: {output}")
        elif output and len(output.strip()) > 10:
            summary = mgr.summarize_result(cli.name, output, task)
            history.append({"role": "user", "content": f"/peer {cli.name}: {task}"})
            history.append({"role": "assistant", "content": summary})
            success(f"Result from {cli.name} added to conversation context.")
        return True, history

    # ── /rag ─────────────────────────────────────────────────────────────────
    if low.startswith("/rag"):
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            info("Usage: /rag <prompt>   — show what the KB would inject for that prompt")
            return True, history

        from core.retrieval import retrieve_debug

        d = retrieve_debug(parts[1])

        console.print(f"\n[bold]RAG Debug[/bold] — query sent to KB: [cyan]\"{d['query']}\"[/cyan]")
        console.print(
            f"  Backend: [cyan]{d['backend']}[/cyan]   "
            f"Score threshold: [cyan]{d.get('threshold', '?')}[/cyan]\n"
        )

        all_chunks = d.get("all_chunks", [])
        kept_set = {id(r) for r in d.get("kept_chunks", [])}

        if not all_chunks:
            if "error" in d:
                warning(f"KB unavailable: {d['error']}")
            else:
                info("No results — KB is empty or no match found.")
            return True, history

        console.print(f"[bold]All chunks returned ({len(all_chunks)}):[/bold]")
        for i, r in enumerate(all_chunks, 1):
            score = r.get("score", 0)
            source = Path(r.get("source", "")).name or "?"
            text = r.get("text", "").strip()
            kept = id(r) in kept_set
            tag = "[green]✓ kept[/green]" if kept else "[red]✗ filtered[/red]"
            console.print(
                f"\n  [{i}] {tag}  score=[cyan]{score:.3f}[/cyan]  source=[dim]{source}[/dim]"
            )
            # Show first 3 lines of the chunk
            preview = "\n".join(text.splitlines()[:3])
            if len(text.splitlines()) > 3:
                preview += f"\n    [dim]... ({len(text.splitlines())} lines total)[/dim]"
            for line in preview.splitlines():
                console.print(f"      {line}")

        console.print(f"\n[bold]Block injected into prompt ({len(d['block'])} chars):[/bold]")
        if d["block"]:
            console.print(f"[dim]{d['block'][:1200]}[/dim]")
            if len(d["block"]) > 1200:
                console.print(f"[dim]  ... ({len(d['block'])} chars total)[/dim]")
        else:
            info("(nothing injected — all chunks filtered out or KB empty)")
        console.print()
        return True, history

    if low.startswith("/graph"):
        from core.memory_v2 import memory as _mem

        parts = cmd.split(maxsplit=1)
        sub = parts[1].strip().lower() if len(parts) > 1 else ""

        if sub == "clear":
            _mem.symbolic.clear()
            success("Symbolic graph cleared.")
        elif sub == "state":
            state = _mem.get_graph_state()
            console.print(f"[bold]Symbolic Graph State:[/bold]")
            console.print(f"  Nodes: {len(state['nodes'])}")
            console.print(f"  Edges: {len(state['edges'])}")
            for node in state["nodes"][:10]:
                console.print(f"    - {node['label']} (type={node['node_type']})")
            if len(state["nodes"]) > 10:
                console.print(f"    ... and {len(state['nodes']) - 10} more")
        elif sub == "check":
            issues = _mem.symbolic.check_consistency()
            if issues:
                warning(f"Consistency issues found: {len(issues)}")
                for issue in issues[:5]:
                    console.print(f"  [red]![/red] {issue}")
            else:
                success("Graph is consistent.")
        else:
            status = _mem.symbolic.status()
            console.print(f"[bold]Symbolic Graph:[/bold]")
            console.print(f"  Available: {status.get('available', False)}")
            console.print(f"  Concepts: {status.get('concepts', 0)}")
            console.print(f"  Relations: {status.get('relations', 0)}")
            console.print("\n  Subcommands: state, check, clear")
        return True, history

    if low == "/help":
        console.print("""
[bold]File commands:[/bold]
  /read <file>           Load file into context
  /load <file|*.py|dir>  Load file, glob, or whole directory
  /unread <file>         Remove file from context
  /ignore <pattern>      Add pattern to .codeyignore
  /context               Show loaded files and sizes
  /diff [file]           Show what Codey-OS changed (colored diff)
  /undo [file]           Restore file to previous version

[bold]Code Review (v2.5.2):[/bold]
  /review <file.py>      Run all linters + optional agent fix
  (auto-lint runs after every file write — no command needed)

[bold]Search:[/bold]
  /search <pattern>      Grep across all project files
  /search <pat> <dir>    Grep in specific directory

[bold]Git:[/bold]
  /git                   Show git status
  /git <message>         Stage all and commit
  /git push              Push to remote
  /git log               Show recent commits

[bold]Project:[/bold]
  /init                  Generate CODEY.md project memory
  /memory                Show CODEY.md contents
  /project               Show project info
  /cwd [path]            Show or change directory

[bold]Session:[/bold]
  /sessions              List all saved sessions
  /summarize             Compress conversation to save context
  /clear                 Clear history, context, undo, session
  /exit                  Save session and quit

[bold]Knowledge Base:[/bold]
  /rag <prompt>          Show what the KB would inject for that prompt

[bold]Learning:[/bold]
  /learning              Show learning system status (v2.2.0)

[bold]Symbolic Graph (v3.0.0):[/bold]
  /graph                 Show symbolic graph status
  /graph state           Show graph nodes and edges
  /graph check           Check graph consistency
  /graph clear           Clear the entire graph

[bold]Voice (v2.5.1 — requires Termux:API):[/bold]
  /voice                 Show voice status and commands
  /voice on              Enable voice mode (TTS + STT)
  /voice off             Disable voice mode
  /voice listen          One-shot voice input → send to agent
  /voice rate <n>        Set TTS speed (default 1.0, range 0.1–4.0)
  /voice pitch <n>       Set TTS pitch (default 1.0)
  /voice speak <text>    Test TTS with given text
  (In voice mode, press Enter on a blank line to speak your task)

[bold]Peer CLIs:[/bold]
  /peer                  List available peer CLIs
  /peer <name> <task>    Call a specific CLI (antigravity/qwen)
  /peer <task>           Auto-pick best CLI for the task

[bold]CLI flags:[/bold]
  codeyOS "task"              One-shot
  codeyOS --chat "task"       Chat with prefilled prompt
  codeyOS --yolo "task"       Skip all confirmations
  codeyOS --fix file.py       Run file, auto-fix any errors
  codeyOS --read file.py      Pre-load file into context
  codeyOS --init              Generate CODEY.md and exit
  codeyOS --no-resume         Start fresh (ignore saved session)
  codeyOS --allow-self-mod    Enable self-modification (with checkpoints)
  codeyOS --no-peer          Disable peer CLI escalation

[bold]Fine-tuning (v2.3.0):[/bold]
  codeyOS --finetune          Export fine-tuning dataset + Colab notebook
  codeyOS --finetune --ft-days 30 --ft-quality 0.7 --ft-model both
  codeyOS --import-lora /path/to/adapter --lora-model primary

[bold]Environment variables:[/bold]
  ALLOW_SELF_MOD=1             Enable self-modification (alternative to flag)
  CODEY_SYMBOLIC=1             Enable symbolic graph pipeline (v3.0.0)
  CODEY_MODEL                  Override model path
  CODEY_THREADS                Override thread count
        """)
        return True, history

    return False, history


def repl(
    initial_prompt=None,
    yolo=False,
    one_shot=False,
    preload=None,
    plan=False,
    no_plan=False,
    session_path=None,
    no_resume=False,
):
    console.print(BANNER)
    separator()

    # Start system monitor (background thread — also updates terminal title)
    monitor = get_monitor()
    monitor.start()

    # v2: Use loader_v2 to ensure model is available (skip for remote backends)
    from utils.config import is_remote_backend

    if not is_remote_backend():
        loader = get_loader()
        try:
            ok = _load_primary_with_gate_recovery(loader)
        except (KeyboardInterrupt, SystemExit):
            console.print("\n[dim]Interrupted during model load, cleaning up...[/dim]")
            shutdown()
            return
        if not ok and _is_unrecovered_gate_denial(loader):
            error(
                "Model could not be loaded: the resource gate denied the "
                f"reservation and no recovery was possible ({loader.get_last_ensure_reason()})."
            )
            shutdown()
            return

    from core.codeymd import find_codeymd
    from core.project import detect_project

    proj = detect_project()
    if proj["type"] != "unknown":
        info(f"Project: [bold]{proj['type']}[/bold] · {os.getcwd()}")
    if find_codeymd():
        info("Memory: [bold]CODEY.md[/bold] found")
    else:
        info("No CODEY.md — run [bold]/init[/bold] to create project memory")

    if preload:
        for f in preload:
            ctx.load_file(f)

    # Load saved session
    from core.sessions import load_session, save_session

    history = []
    if not no_resume:
        if session_path:
            history = load_session(path=session_path)
        else:
            history = load_session()  # auto-resume from cwd-based session file

    if initial_prompt and one_shot:
        try:
            response, history = _run_with_plan(initial_prompt, history, yolo, False, no_plan)
            # Display the response for one-shot mode
            if response and not response.startswith("["):
                if was_last_streamed():
                    separator()
                else:
                    separator()
                    console.print(f"\n[bold green]Codey-OS:[/bold green] {response}")
                    separator()
            save_session(history)
        except KeyboardInterrupt:
            pass
        finally:
            shutdown()
        return

    info("Type your task. /help for commands.")
    separator()

    if initial_prompt:
        try:
            response, history = _run_with_plan(initial_prompt, history, yolo, plan, no_plan)
            # Display the response
            if response and not response.startswith("["):
                if was_last_streamed():
                    separator()
                else:
                    separator()
                    console.print(f"\n[bold green]Codey-OS:[/bold green] {response}")
                    separator()
            save_session(history)
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")

    while True:
        loaded = ctx.list_loaded()
        file_hint = f" ({len(loaded)} file{'s' if len(loaded)!=1 else ''})" if loaded else ""
        try:
            # Use plain input() instead of Rich console.input() —
            # Rich's input conflicts with raw sys.stdout.write() used
            # during streaming, causing the REPL to hang after responses.
            user_input = input(f"\033[1;34mYou{file_hint}>\033[0m ").strip()
            # Paste detection: terminal pastes arrive as multiple buffered lines.
            # Drain any immediately-available continuation lines and join them
            # so a multi-line paste is treated as one message, not many short ones.
            try:
                if sys.stdin.isatty():
                    import select as _sel

                    _extra = []
                    while _sel.select([sys.stdin], [], [], 0.02)[0]:
                        _line = sys.stdin.readline().rstrip("\n").strip()
                        if _line:
                            _extra.append(_line)
                    if _extra:
                        user_input = user_input + " " + " ".join(_extra)
            except Exception:
                pass  # select unavailable — proceed with single line
        except (KeyboardInterrupt, EOFError, SystemExit):
            # SystemExit added here (NEW-40): SIGTERM's handler
            # (_sigterm_handler, below) raises SystemExit at whatever
            # point the process happens to be executing, including this
            # idle input() wait. Before this fix that propagated past
            # this clause uncaught (SystemExit doesn't match
            # `except Exception` either, at the clause below), skipping
            # shutdown() entirely and leaving llama-server running. This
            # matches the existing pattern used by the 4 model-load
            # guards elsewhere in this file
            # (`except (KeyboardInterrupt, SystemExit):`) and, like
            # those, exits 0 via `break` rather than letting
            # SystemExit's original 128+signum code propagate — the
            # same tradeoff those guards already make (see
            # _sigterm_handler's docstring: "In the 4 guarded paths
            # this is moot ... the process exits 0 there regardless").
            save_session(history)
            print("\nSession saved. Goodbye!")
            shutdown()
            break
        except Exception as e:
            # Handle any terminal input errors gracefully
            error(f"Input error: {e}")
            save_session(history)
            print("\nSession saved. Exiting...")
            shutdown()
            break

        if not user_input:
            # In voice mode: blank input → trigger STT
            try:
                from core.voice import get_voice as _get_voice

                _v = _get_voice()
                if _v.enabled and _v.stt_available():
                    spoken = _v.listen()
                    if spoken:
                        user_input = spoken
                    else:
                        continue
                else:
                    continue
            except Exception:
                continue

        # ── Stats bar after input ──────────────────────────────────────────
        console.print(get_render_text())

        was_cmd, history = handle_command(user_input, history, yolo=yolo)
        if was_cmd:
            continue

        try:
            response, history = _run_with_plan(user_input, history, yolo, plan, no_plan)
            # Display the response if it's not a tool execution result
            if response and not response.startswith("["):
                if was_last_streamed():
                    separator()
                else:
                    separator()
                    console.print(f"\n[bold green]Codey-OS:[/bold green] {response}")
                    separator()
                # Speak the response if voice mode is on (Ctrl+C to interrupt)
                try:
                    from core.voice import get_voice as _get_voice

                    _v = _get_voice()
                    if _v.enabled and _v.tts_available():
                        try:
                            _v.speak(response)
                        except KeyboardInterrupt:
                            _v.stop_speaking()
                            console.print("[dim]Speech interrupted.[/dim]")
                except Exception:
                    pass
            save_session(history)
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")
        except SystemExit:
            # Allow clean exit
            raise
        except Exception as e:
            error(f"Agent error: {e}")
            import traceback

            traceback.print_exc()
            # Continue the REPL even after errors
            console.print("\n[dim]An error occurred. You can continue chatting.[/dim]")


def _sigterm_handler(signum, frame):
    """Translate SIGTERM into SystemExit (NEW-10).

    Deliberately does nothing beyond raising an exception here -- no
    shutdown() call, no I/O, no cleanup logic. This mirrors exactly what
    CPython's own default SIGINT handler (signal.default_int_handler)
    does: raise, and let the call stack unwind through whatever
    try/except is active. That's what lets this reuse the 4 existing
    `except (KeyboardInterrupt, SystemExit): ... shutdown()` guards around
    each model-load call site in main.py (repl(), args.init/--tdd/--fix
    branches — each now calls `_load_primary_with_gate_recovery()` rather
    than `loader.load_primary()` directly as of TODO.md 7.4 sub-task 5,
    but that call still sits inside the same try/except shape) unchanged
    -- SIGTERM becomes just another case they already catch during model
    load, with zero new shutdown-calling logic. Doing real work directly
    inside a signal handler (which can fire mid-syscall or mid-bytecode)
    is the kind of thing CLAUDE.md rule 4 exists to avoid.

    UPDATE (NEW-40 follow-up fix): the REPL's steady-state input() wait
    (~line 1711, `except (KeyboardInterrupt, EOFError, SystemExit):`)
    previously had no SystemExit clause, so SIGTERM's SystemExit
    propagated uncaught there and the process exited without running
    shutdown() -- unlike SIGINT, which that same clause DOES catch and
    clean up. That asymmetry is now fixed: SystemExit is caught there
    too and shutdown() runs, same as SIGINT, before `break`. See that
    clause's own comment for the exit-code tradeoff (exits 0 via
    `break` rather than propagating 128+signum, matching what the 4
    model-load guards already do).

    Still NOT fully general: the initial-prompt non-one-shot branch
    (~line 1684, `except KeyboardInterrupt:`) is deliberately left
    uncovered. It doesn't call shutdown() for SIGINT either (just
    prints "Interrupted." and falls through into the REPL loop below),
    so adding SystemExit there would mean a termination signal gets
    absorbed into a continued session rather than exiting -- worse than
    today's behavior of propagating out of main() uncaught. Today's
    behavior there (SystemExit propagates straight out of main(),
    skipping the REPL loop and shutdown()) is not a regression versus
    pre-fix behavior (SIG_DFL was unconditional kernel-level
    termination with zero cleanup either way), so it's left as-is.
    Logged as NEW-40; the idle-input()-wait half is now fixed, this
    half remains open by design.

    Exit code: 128 + signum (the conventional shell/POSIX "terminated by
    signal N" code, e.g. 143 for SIGTERM) rather than SystemExit(0), so
    that in the two uncovered paths above, an uncaught propagation still
    reports "killed by a signal" to any supervisor/shell waiting on this
    process -- not a false "clean voluntary exit". In the 4 guarded paths
    this is moot: they all `return` after shutdown() rather than letting
    the exception keep propagating, so the process exits 0 there
    regardless.

    Known residual gap (not introduced or closed by this handler): NEW-9
    describes a fork-window race in core/loader_v2.py where a signal
    delivered during os.fork() can be swallowed by CPython's atfork
    exception-handling suppression. That applies identically to SIGINT
    today and will apply identically to SIGTERM now that it uses the same
    raise-and-let-existing-guards-catch-it mechanism. Not addressed here.
    """
    raise SystemExit(128 + signum)


def main():
    # NEW-10: SIGTERM's disposition defaults to SIG_DFL (immediate
    # kernel-level termination, no Python-level exception, unlike SIGINT
    # which Python's own default handler turns into KeyboardInterrupt).
    # Installed as the very first thing main() does, before any
    # argument-dependent branch can begin loading a model, so every
    # model-load window below (loader.load_primary() / ensure_model())
    # is covered from the start.
    #
    # NOTE: if args.daemon is set below, core/daemon.py's Daemon.__init__
    # installs its OWN SIGTERM handler (core/daemon.py:443) in this same
    # process partway through construction, and legitimately overrides
    # this one -- the daemon has its own dedicated graceful-shutdown path
    # (SIGTERM is a daemon's normal stop signal, e.g. from `codeydOS
    # stop`). Daemon.__init__ does some setup (config, state store,
    # get_planner() -- a lazy in-process singleton with no subprocess/
    # model-load side effects, verified by reading core/planner_v2.py)
    # BEFORE registering its own handler at line 443; this handler is the
    # active disposition during that narrow window instead. That's fine,
    # not a gap of consequence: nothing in that window loads a model or
    # spawns a process, so a SIGTERM there has nothing to orphan either
    # way. The daemon's own handler takes over well before its model
    # pre-load (Daemon._main_loop -> loader.ensure_model()), which is the
    # window that actually matters for RAM/orphan concerns.
    signal.signal(signal.SIGTERM, _sigterm_handler)

    args = parse_args()

    if args.version:
        print(f"Codey-OS v{CODEY_VERSION}")
        sys.exit(0)

    if args.status:
        # PENDING_ISH_DECISIONS.md item 4: core/observability.py's status()
        # was complete but never wired to a CLI command. Display-only —
        # reads existing state (SQLite task queue, loader's in-memory
        # "is a model loaded" flag, etc.) and prints it; does not load a
        # model or change any daemon state.
        #
        # Also surfaces core/resource_gate.py's snapshot composer (Track 3
        # Phase 5a / 7.4 sub-task A) under its own "resources" key, next to
        # observability's figures — that's the live, system-wide CPU/RAM
        # counterpart to observability's own per-process cpu/memory numbers
        # (see NEW-107), and the only way to observe the rolling CPU
        # sampler's cold-start path without babysitting the daemon for 60+
        # seconds.
        import dataclasses
        import json

        from core.observability import status as _observability_status
        from core.resource_gate import get_resource_snapshot

        payload = _observability_status()
        payload["resources"] = dataclasses.asdict(get_resource_snapshot())
        print(json.dumps(payload, indent=2, default=str))
        return

    apply_overrides(args)

    # Daemon mode (v2 feature)
    if args.daemon:
        from core.daemon import Daemon, check_pid_file

        if check_pid_file():
            error("Daemon is already running. Use --daemon-stop to shut it down.")
            sys.exit(1)
        info("Starting Codey-OS daemon mode...")
        daemon = Daemon()
        daemon.run()
        return

    if args.clear_session:
        from core.sessions import clear_session

        clear_session()
        return

    if args.init:
        # NEW-358 Site 1: emit run_start before any model-load work, so the loader fallback's claim_run_start() then no-ops
        _record_cli_telemetry_run_start()
        loader = get_loader()
        try:
            ok = _load_primary_with_gate_recovery(loader)
        except (KeyboardInterrupt, SystemExit):
            console.print("\n[dim]Interrupted during model load, cleaning up...[/dim]")
            shutdown()
            return
        if not ok and _is_unrecovered_gate_denial(loader):
            error(
                "Model could not be loaded: the resource gate denied the "
                f"reservation and no recovery was possible ({loader.get_last_ensure_reason()})."
            )
            shutdown()
            return
        run_init()
        shutdown()
        return

    if args.tdd:
        # NEW-358 Site 1: emit run_start before any model-load work, so the loader fallback's claim_run_start() then no-ops
        _record_cli_telemetry_run_start()
        loader = get_loader()
        try:
            ok = _load_primary_with_gate_recovery(loader)
        except (KeyboardInterrupt, SystemExit):
            console.print("\n[dim]Interrupted during model load, cleaning up...[/dim]")
            shutdown()
            return
        if not ok and _is_unrecovered_gate_denial(loader):
            error(
                "Model could not be loaded: the resource gate denied the "
                f"reservation and no recovery was possible ({loader.get_last_ensure_reason()})."
            )
            shutdown()
            return
        from core.tdd import find_test_file, run_tdd_loop

        test_file = args.tests or find_test_file(args.tdd)
        if not test_file:
            # Suggest test file name
            from pathlib import Path as _P

            suggested = "test_" + _P(args.tdd).name
            error(
                f"No test file found. Create {suggested} or use: codeyOS --tdd {args.tdd} --tests {suggested}"
            )
            shutdown()
            return
        run_tdd_loop(args.tdd, test_file, yolo=args.yolo)
        shutdown()
        return

    if args.fix:
        # NEW-358 Site 1: emit run_start before any model-load work, so the loader fallback's claim_run_start() then no-ops
        _record_cli_telemetry_run_start()
        loader = get_loader()
        try:
            ok = _load_primary_with_gate_recovery(loader)
        except (KeyboardInterrupt, SystemExit):
            console.print("\n[dim]Interrupted during model load, cleaning up...[/dim]")
            shutdown()
            return
        if not ok and _is_unrecovered_gate_denial(loader):
            error(
                "Model could not be loaded: the resource gate denied the "
                f"reservation and no recovery was possible ({loader.get_last_ensure_reason()})."
            )
            shutdown()
            return
        from core.fixmode import fix_file
        # --fix is automated, always disable confirmations
        from utils import config

        config.AGENT_CONFIG["confirm_write"] = False
        config.AGENT_CONFIG["confirm_shell"] = False
        fix_file(args.fix, extra_instruction=args.prompt or "", yolo=True)
        shutdown()
        return

    # Fine-tuning data export (v2.3.0)
    if args.finetune:
        from core.finetune_prep import prepare_finetune_data

        info("Preparing fine-tuning dataset...")
        results = prepare_finetune_data(
            days=args.ft_days,
            min_quality=args.ft_quality,
            model_variant=args.ft_model,
            output_dir=args.ft_output,
        )
        if "error" in results:
            error(results["error"])
            sys.exit(1)
        shutdown()
        return

    # LoRA adapter import (v2.3.0)
    if args.import_lora:
        # NEW-358 Site 1: emit run_start before any model-load work, so the loader fallback's claim_run_start() then no-ops
        _record_cli_telemetry_run_start()
        from core.lora_import import import_lora_adapter

        info(f"Importing LoRA adapter from {args.import_lora}...")
        results = import_lora_adapter(
            adapter_path=args.import_lora,
            model_variant=args.lora_model,
            quantize=args.lora_quant,
            merge_on_device=args.lora_merge,
        )
        if results.get("success"):
            success(f"LoRA adapter imported: {results.get('model_path')}")
            if results.get("backup_path"):
                info(
                    f"Backup created: {results['backup_path']} "
                    "(no CLI rollback command exists; restore via the "
                    "'coding.finetune_rollback_backup' CCOS capability — note "
                    "NEW-91: rollback overwrites the fine-tuned checkpoint at "
                    f"{results.get('model_path')} in place with the backed-up "
                    "base weights and then deletes the backup file, permanently "
                    "destroying the fine-tuned checkpoint with no way to recover "
                    "it, so copy that file elsewhere first if you want to keep "
                    "it before rolling back)"
                )
        else:
            error(f"Import failed: {results.get('error', 'Unknown error')}")
            if results.get("instructions"):
                print(results["instructions"])
            sys.exit(1)
        shutdown()
        return

    resolved_session = None
    if hasattr(args, "session") and args.session and args.session != "list":
        from pathlib import Path as _P

        from core.sessions import SESSIONS_DIR

        matches = list(_P(SESSIONS_DIR).glob(f"*{args.session}*.json"))
        if matches:
            resolved_session = str(matches[0])
            info(f"Resuming: {matches[0].name}")

    one_shot = bool(args.prompt and not args.chat)
    # Track 3 Phase 5a / 7.4 sub-task B: mark this interactive session live
    # for the whole span of repl() (start -> every return/break inside it,
    # any uncaught exception, or normal completion) so
    # core/resource_gate.py's is_tui_session_active() can see it from a
    # separate process. try/finally here — not inside repl() itself — keeps
    # this additive to repl()'s existing multi-path control flow (several
    # early returns/breaks already call shutdown() internally; see
    # CLAUDE.md rule 4) rather than restructuring it.
    _record_tui_telemetry_run_start()
    _write_tui_pid_file()
    try:
        repl(
            initial_prompt=args.prompt,
            yolo=args.yolo,
            one_shot=one_shot,
            preload=args.read,
            session_path=resolved_session,
            plan=args.plan,
            no_plan=args.no_plan,
            no_resume=args.no_resume,
        )
    finally:
        _remove_tui_pid_file()


if __name__ == "__main__":
    main()
