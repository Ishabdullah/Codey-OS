import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union

CODEY_DIR = Path(os.environ.get("CODEY_DIR", Path.home() / "Codey-OS"))
MODEL_PATH = Path(
    os.environ.get(
        "CODEY_MODEL",
        Path.home() / "models" / "qwen3.5-4b-instruct" / "Qwen3.5-4B-Q4_K_M.gguf",
    )
)

# ── Primary Qwen3.5-4B model server (port 8080) ─────────────────────────────
PRIMARY_SERVER_PORT = int(os.environ.get("CODEY_PRIMARY_PORT", "8080"))

# Dedicated embedding model — Option C (v2.6.6)
# nomic-embed-text-v1.5: 80 MB Q4, 2048 ctx, 768-dim vectors.
# Runs on port 8082, separate from the generation server on 8080.
# ~50 ms/chunk, covers 92.6% of chunks; rest use BM25 keyword fallback.
EMBED_MODEL_PATH = Path(
    os.environ.get(
        "CODEY_EMBED_MODEL",
        Path.home() / "models" / "nomic-embed" / "nomic-embed-text-v1.5.Q4_K_M.gguf",
    )
)
EMBED_SERVER_PORT = int(os.environ.get("CODEY_EMBED_PORT", "8082"))

# Detection of llama-server binary and library path
_HOME_LLAMA = Path.home() / "llama.cpp" / "build" / "bin"
LLAMA_SERVER_BIN = (
    os.environ.get("CODEY_LLAMA_SERVER")
    or shutil.which("llama-server")
    or str(_HOME_LLAMA / "llama-server")
)
LLAMA_LIB = os.environ.get("CODEY_LLAMA_LIB") or str(_HOME_LLAMA)

# Context window (n_ctx) — overridable via CODEY_N_CTX for substitute/smaller
# models that can't handle the production default (e.g. NEW-95's resource-gate
# live-verification round). This is the single source of truth for the
# CODER role's INTERACTIVE ceiling — the real llama-server -c flag
# core/loader_v2.py:LlamaServer spawns the primary (Qwen3.5-4B) server with
# when core.resource_gate.is_interactive_session_active() is True, and the
# n_ctx the matching resource_gate.ModelSpec cost estimate uses for that
# same case (TODO.md 7.4b sub-task C). Since that sub-task, it is NOT the
# only n_ctx value in play: get_coder_background_n_ctx() (below) returns
# the coder's ceiling for
# daemon-dispatched BACKGROUND tasks (no interactive TUI/GUI session
# active) — both are functions, not constants, so they re-read
# MODEL_CONFIG["n_ctx"] live and pick up a runtime --ctx override (NEW-102/
# bug_002 fix) rather than freezing a value at import time; each clamps
# via `min(MODEL_CONFIG["n_ctx"], ...)` so a CODEY_N_CTX or --ctx override
# for a smaller substitute model still binds downward on them too; see
# each function's own comment.
# Overriding only the launch flag without also updating the ModelSpec
# passed to the resource gate (or vice versa) would desync the gate's
# admission math from what actually gets spawned (the NEW-84 class of
# bug) — this env var, and the two derived constants below it, are read
# fresh by both the spawn site and the gate site in each case. Fails
# loudly on a bad value rather than silently falling back, since a silent
# fallback here could hide a gate/spawn mismatch instead of preventing one.
_n_ctx_env = os.environ.get("CODEY_N_CTX")
if _n_ctx_env is None:
    _n_ctx = 65536
else:
    try:
        _n_ctx = int(_n_ctx_env)
        if _n_ctx <= 0:
            raise ValueError("must be a positive integer")
    except ValueError as e:
        raise ValueError(
            f"CODEY_N_CTX={_n_ctx_env!r} is not a valid n_ctx ({e}). "
            "Unset it to use the default (65536) or set it to a positive whole number."
        ) from e

MODEL_CONFIG = {
    "n_ctx": _n_ctx,
    # 4 -> 6, 2026-08-26, per Ish's request to speed up inference on this
    # device's 8-core CPU (confirmed via nproc). THERMAL_CONFIG's
    # "original_threads" (utils/config.py, below) derives from this value,
    # so the thermal manager's post-throttle restore target moves with it
    # automatically. Not yet live-benchmarked against the prior value of 4
    # for either raw speedup or how much sooner thermal throttling now
    # kicks in (core/thermal.py reduces after 10 min sustained inference) -
    # see NEW-195.
    "n_threads": 6,
    "n_gpu_layers": 0,
    "verbose": False,
    "temperature": 0.7,
    "max_tokens": 2048,
    "repeat_penalty": 1.1,
    "top_p": 0.8,
    "top_k": 20,
    "batch_size": 1024,
    "kv_type": "q4_0",
    # Stop the model before it can role-play the next user turn.
    # With /v1/chat/completions, llama-server handles ChatML stop tokens
    # automatically. These extra stops catch hallucinated role-play.
    "stop": ["<|im_end|>", "<|im_start|>", "\nUser:", "\nHuman:", "\nA:"],
}

# ── Coder (4B) BACKGROUND context ceiling — TODO.md 7.4b sub-task C ─────────
# Ish confirmed 2026-08-11: the coder's context stays at full n_ctx
# (MODEL_CONFIG["n_ctx"] / CODEY_N_CTX above, 65536 by default) whenever a
# human is actively using it interactively (core.resource_gate.
# is_interactive_session_active() is True), and drops to this smaller fixed
# ceiling for daemon-dispatched BACKGROUND coder tasks (no interactive
# TUI/GUI session active) — a two-value branch, not the fuller per-task
# adaptive n_ctx that stays parked as CODEY_OS_MASTER_VISION.md Section
# 11.9's future item. 16384 is the exact value TODO.md 7.4a sub-task E's
# own live-verification pass already proved admits cleanly with real,
# moderate (~900MiB-1.2GiB) swap movement — a known-safe intermediate point
# between full 32768 and a value nobody has tested live.
#
# NEW-102/bug_002 fix (2026-08-13): this is a FUNCTION, not a module-level
# constant, specifically so it re-reads MODEL_CONFIG["n_ctx"] on every call
# instead of freezing a value at import time. main.py's apply_overrides()
# mutates MODEL_CONFIG["n_ctx"] at runtime when --ctx is passed on the CLI
# (main.py ~line 115) — a plain constant bound at import would never see
# that mutation, since apply_overrides() always runs after utils.config is
# first imported. Reading MODEL_CONFIG live (not `_n_ctx`, which is also
# frozen at import) is what lets --ctx actually reach the background coder
# ceiling, matching the pattern core/loader_v2.py's interactive coder path
# already used correctly (MODEL_CONFIG.get("n_ctx", 4096), read at call
# time). Still clamped downward via min() so a substitute/smaller model
# run via CODEY_N_CTX (e.g. NEW-95's live-verification round) or a smaller
# --ctx override binds downward here too.
#
# M1-D (2026-08-23): a matching get_planner_n_ctx() used to sit above this
# function, giving the dedicated 1.5B/planner role its own small fixed
# ceiling distinct from the coder's. It's removed as of this change, not
# just unused: the planner now shares the coder's single Qwen3.5-4B
# llama-server process (see PLANNER_MODEL_PATH's comment below), which has
# exactly one `-c` flag — a separate planner-only context ceiling is no
# longer an expressible concept, not merely a dead call site.
def get_coder_background_n_ctx() -> int:
    return min(MODEL_CONFIG["n_ctx"], 16384)

AGENT_CONFIG = {
    "max_steps": 10,
    "token_budget": 1500,
    "confirm_shell": True,
    "confirm_write": True,
    "history_turns": 8,
    # Optional callable(command: str) -> str that replaces the default shell()
    # invocation.  Used by the daemon to enforce an allowlist without modifying
    # the global shell tool.  None means use the default shell() function.
    "_shell_fn": None,
}

# Thermal management + adaptive depth — Phase 8 (v2.6.8)
THERMAL_CONFIG = {
    "enabled": True,
    "warn_after_sec": 300,  # 5 minutes - log warning
    "reduce_threads_after_sec": 600,  # 10 minutes - reduce to 2 threads
    "min_threads": 2,
    "original_threads": 4,  # Will be set from MODEL_CONFIG
    # Adaptive recursion depth thresholds (tuned for Snapdragon — runs hotter)
    "temp_critical": 90,  # °C — skip recursion entirely
    "temp_warn": 75,  # °C — cap recursion depth to 1
    "batt_critical": 5,  # % — skip recursion (not charging)
    "batt_low": 15,  # % — cap recursion depth to 1 (not charging)
}

# Initialize original_threads from MODEL_CONFIG
THERMAL_CONFIG["original_threads"] = MODEL_CONFIG.get("n_threads", 4)

# ── Autonomous shutdown tripwire config (7.4 sub-task D) ────────────────────
# core/resource_gate.py's should_trip_shutdown() reads these two keys.
# `shutdown_trip_after_sec` (default 1200 = 20 min) is the sustained-window
# duration; `shutdown_cpu_pct` (default 90) is only used on the rare
# hardware/environment where a real CPU% reading is actually available (see
# should_trip_shutdown()'s own docstring for why this device's CPU leg is
# always skipped instead of gating on this value — NEW-108).
#
# Both are overridable via env var (CODEY_SHUTDOWN_TRIP_AFTER_SEC /
# CODEY_SHUTDOWN_CPU_PCT), same precedent as CODEY_N_CTX above and
# core/resource_gate.py's CODEY_TEST_PRIMARY_ARCH: fail loudly on a bad
# value rather than silently falling back, so a broken override can't
# masquerade as "just using the default." These env vars exist ONLY so a
# live-verification session can run with a drastically shortened duration
# (e.g. 20 seconds instead of 20 minutes) without ever needing a practically
# multi-hour session to observe a real trip — the committed default below
# must NEVER be permanently lowered to make live-testing more convenient;
# any lower value must come from the env var, set transiently for that one
# test session, never from editing this file.


def _thermal_int_env_override(env_name: str, default: int, max_value: Optional[int] = None) -> int:
    raw = os.environ.get(env_name)
    if raw is None:
        return default
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError("must be a positive integer")
        if max_value is not None and value > max_value:
            raise ValueError(f"must be <= {max_value}")
    except ValueError as e:
        raise ValueError(
            f"{env_name}={raw!r} is not valid ({e}). Unset it to use the "
            f"default ({default}) or set it to a valid positive whole number."
        ) from e
    return value


THERMAL_CONFIG["shutdown_trip_after_sec"] = _thermal_int_env_override(
    "CODEY_SHUTDOWN_TRIP_AFTER_SEC", 1200
)
# max_value=100: a CPU percentage above 100 would silently make the CPU leg
# of should_trip_shutdown()'s AND unsatisfiable on any hardware where CPU is
# actually measurable — fail loudly on that instead of accepting a value
# that quietly defeats the check it's supposed to gate.
THERMAL_CONFIG["shutdown_cpu_pct"] = _thermal_int_env_override(
    "CODEY_SHUTDOWN_CPU_PCT", 90, max_value=100
)

# `CODEY_SHUTDOWN_TRIP_AFTER_SEC`/`CODEY_SHUTDOWN_CPU_PCT` above shorten the
# tripwire's *duration*, but do nothing about the fixed 90°C threshold
# itself — meaning a live-verification session that wants to observe a real
# trip still needs to drive the device to a genuinely sustained 90°C, which
# may not be practical in a short test session (code-reviewer follow-up,
# 4.1 sub-task D). `CODEY_TEMP_CRITICAL_C` lets a live-verification session
# temporarily lower the threshold to something the device's real ambient/
# inference-load temperature can actually reach (e.g. 45°C), same
# "transient, for one test session, never edited into the committed
# default" posture as the two overrides above. `temp_critical` is also read
# by `core/resource_gate.py`'s `can_admit()`/`can_dispatch_task()`
# (model-admission and task-dispatch thermal checks), by
# `core/recursive.py`'s `get_adaptive_depth()` (forces recursion depth to 0
# once temp >= temp_critical — this one is the most surprising consumer,
# since it silently changes agent behavior/output quality via
# draft/critique/refine depth, not just a resource-gating decision), and by
# `core/thermal.py`'s `ThermalManager._check_thermal_status()` (log-level
# only, lower stakes) — this override affects all of those too, not just
# the shutdown tripwire, since it's one shared threshold, not a separate
# copy per consumer. That's expected for a live-test session (a lowered
# threshold should make the whole thermal-gated stack behave
# consistently), but is worth knowing before setting it during any session
# that's also exercising admission/dispatch/recursion behavior.
#
# max_value=120: mirrors shutdown_cpu_pct's own max_value=100 guard
# immediately above, for the same reason but a worse failure direction if
# left unguarded — an unbounded-high override here wouldn't just defeat one
# leg of one check (the CPU leg), it would silently make the ENTIRE thermal
# stack unsatisfiable at once: can_admit()'s thermal check,
# can_dispatch_task()'s thermal check, and the shutdown tripwire all stop
# firing together, get_adaptive_depth()'s force-to-0 branch never fires
# either, and ThermalManager's log-level reporting goes quiet too — since
# all of these read this one shared key, not a separate copy per consumer.
# This guard only rejects absurd/mistyped values (e.g. an accidental extra
# digit) — it does NOT, by itself, catch a plausible-but-wrong value that
# RAISES the threshold within range (e.g. 95, comfortably under 120, which
# would still quietly disarm the tripwire relative to the committed 90).
# That case is covered by the load-time warning below instead, which fires
# on ANY active override, in either direction, not just an out-of-range
# one.
#
# This override is also logged (not just silently applied) whenever it's
# active and different from the committed default — unlike the two
# duration-only overrides above, a LOWERED temp_critical arms the shutdown
# tripwire (the admission/dispatch thermal checks, and
# get_adaptive_depth()'s force-to-0 branch) at a temperature this device
# can plausibly reach under ordinary inference load, not just under a
# genuine overheat condition. A stray export left in a shell profile after
# a live-test session should be visible in the logs on every subsequent
# run, not a silent, easy-to-forget landmine.
#
# Captured BEFORE the override call, not hardcoded as a literal `90` in the
# comparison below — this is the same value THERMAL_CONFIG["temp_critical"]
# was set to a few lines above, so if that committed default is ever
# retuned, the "is the override actually active?" comparison and the
# warning message stay correct automatically instead of silently firing a
# false "overriding to N (committed default is 90)" warning on every run
# with no env var set at all.
_temp_critical_default = THERMAL_CONFIG["temp_critical"]
THERMAL_CONFIG["temp_critical"] = _thermal_int_env_override(
    "CODEY_TEMP_CRITICAL_C", _temp_critical_default, max_value=120
)
if THERMAL_CONFIG["temp_critical"] != _temp_critical_default:
    # Lazy import: utils.logger doesn't import utils.config, so this isn't a
    # circular-import risk, but keeping it lazy (rather than a top-of-file
    # import) matches this module's existing posture of not adding new
    # unconditional imports for a rarely-exercised branch.
    from utils.logger import warning as _warn_temp_critical_override

    _warn_temp_critical_override(
        f"utils.config: CODEY_TEMP_CRITICAL_C is overriding temp_critical to "
        f"{THERMAL_CONFIG['temp_critical']}°C (committed default is "
        f"{_temp_critical_default}°C) — this changes can_admit()/"
        "can_dispatch_task()'s thermal checks, the autonomous shutdown "
        "tripwire's trip point, core/recursive.py's get_adaptive_depth() "
        "(forces recursion depth to 0 once temp >= temp_critical, silently "
        "degrading agent output quality, not just resource gating), AND "
        "core/thermal.py's ThermalManager log-level reporting — not just "
        "live-verification timing. Unset it once the live-test session "
        "that needs it is done."
    )

CODE_DIR = Path(__file__).parent.parent.resolve()
WORKSPACE_ROOT = Path(os.getcwd()).resolve()

# ── Codey-OS state directory — single source of truth ──────────────────────
# Do not hardcode ".codeyOS" or similar anywhere else; import from here.
CODEY_STATE_DIR = Path.home() / ".codeyOS"

DAEMON_PID_FILE = CODEY_STATE_DIR / "codeyOS.pid"
DAEMON_SOCKET_FILE = CODEY_STATE_DIR / "codeyOS.sock"
DAEMON_LOG_FILE = CODEY_STATE_DIR / "codeyOS.log"
DAEMON_CONFIG_FILE = CODEY_STATE_DIR / "config.json"
STATE_DB_FILE = CODEY_STATE_DIR / "state.db"
CHECKPOINT_DIR = CODEY_STATE_DIR / "checkpoints"
NOTES_FILE = CODEY_STATE_DIR / "notes.json"
PLANND_PID_FILE = CODEY_STATE_DIR / "plannd.pid"        # unchanged, already generic
PLANND_LOG_FILE = CODEY_STATE_DIR / "plannd.log"        # unchanged, already generic
GUI_PID_FILE = CODEY_STATE_DIR / "gui-server.pid"       # unchanged, already generic

# Track 3 Phase 5a / 7.4 sub-task B: the "is a user actively using the TUI or
# GUI right now" interactive-session signal (core/resource_gate.py's
# is_interactive_session_active()). TUI_SESSIONS_DIR holds one per-session
# file per interactive main.py process (TUI_SESSIONS_DIR / f"{pid}.pid"),
# written/removed around main()'s repl(...) call site (see main.py's
# _write_tui_pid_file()/_remove_tui_pid_file()) — a directory of per-PID
# files, not a single shared file, because two concurrent interactive
# sessions are a normal, supported case here and a single shared file
# cannot hold two sessions' presence at once (a second session's write, or
# even its crash, would silently erase the first session's signal).
# GUI_CLIENTS_FILE is written by gui/server.py whenever its `clients`
# websocket set changes. Neither is a single-instance-enforcement lock like
# DAEMON_PID_FILE — see each writer's own docstring.
TUI_SESSIONS_DIR = CODEY_STATE_DIR / "tui-sessions"
GUI_CLIENTS_FILE = CODEY_STATE_DIR / "gui-clients.count"

# Recursive Inference — Phase 2 (v2.6.2)
# Controls the draft → critique → refine self-improvement loop.
# CODEY_RECURSIVE=1  — force on   (even for remote backends)
# CODEY_RECURSIVE=0  — force off  (single-pass inference)
# unset              — auto: on for local, off for remote (remote models need fewer retries)
_recursive_env = os.environ.get("CODEY_RECURSIVE", "").strip()
_recursive_backend = os.environ.get("CODEY_BACKEND", "local").lower()
_recursive_default = _recursive_backend not in ("openrouter", "unlimitedclaude")
_recursive_enabled = (
    True if _recursive_env == "1" else False if _recursive_env == "0" else _recursive_default
)
RECURSIVE_CONFIG = {
    "enabled": _recursive_enabled,
    # Max critique+refine cycles per request (1 = 1 critique + 1 refine = 3 calls total)
    # Raise for higher quality at the cost of 2x–3x inference time.
    "max_depth": 1,
    # Quality gate: skip refinement if the model rates its own output >= this × 10
    "quality_threshold": 0.7,
    # Apply recursion for file-write tasks (write_file / patch_file)
    "recursive_for_writes": True,
    # Apply recursion during task planning (orchestrator)
    "recursive_for_plans": True,
    # Skip recursion for Q&A / conversational messages (always skipped via breadth=minimal)
    "recursive_for_qa": False,
    # Max tokens allocated to the critique response (keeps critique calls fast)
    "critique_budget": 512,
    # Max chars of KB context injected into the refine prompt for NEED_DOCS gaps
    "retrieval_budget": 1200,
}

# Knowledge Base + Retrieval — Phase 1 (v2.6.1)
RETRIEVAL_CONFIG = {
    "enabled": True,
    "kb_path": str(CODEY_DIR / "knowledge"),
    "semantic_search": True,  # prefer embeddings when index exists
    "max_chunks": 4,  # max results per retrieval query
    "budget_chars": 2400,  # max chars of retrieved content (~600 tokens)
    "embedding_model": "all-MiniLM-L6-v2",  # legacy key (sentence-transformers era); actual model is EMBED_MODEL_PATH (nomic-embed-text-v1.5)
    "min_score": 0.0,  # minimum raw score (keyword: overlap count)
    "semantic_threshold": 0.3,  # minimum cosine similarity per chunk
    "relevance_gate": 0.72,  # min best-chunk cosine to inject anything at all
    # (prevents noisy general content injection when
    # the KB has no specifically relevant material)
}

CODEY_VERSION = "3.0.0"
CODEY_NAME = "Codey-OS"

# ── Symbolic Graph (Mentalese Engine) — v3.0.0 ────────────────────────────────
# CODEY_SYMBOLIC=1  — enable symbolic graph pipeline
# CODEY_SYMBOLIC=0  — disable (default, backward compat)
# When enabled, the pipeline routes: language -> planner -> graph -> coder -> language
SYMBOLIC_CONFIG = {
    "enabled": os.environ.get("CODEY_SYMBOLIC", "0") == "1",
    # Graph operations supported
    "operations": ["observe", "cause", "possess", "agentive", "spatial", "temporal", "intend"],
    # Maximum graph size before pruning (prevents unbounded growth)
    "max_concepts": 10000,
    "max_relations": 50000,
    # Consistency check on each batch (can be disabled for performance)
    "check_consistency": True,
}

# ── Multilingual Embeddings — v3.0.0 ─────────────────────────────────────────
# sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
# 384-dim, 50+ languages, same vector space for all languages
EMBEDDING_CONFIG = {
    "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "dimension": 384,
    "fallback": "nomic-embed-text-v1.5",  # llama-server fallback on Termux
}

# ── OpenRouter backend (optional) ────────────────────────────────────────────
# ── Remote backend selection ─────────────────────────────────────────────────
# Set CODEY_BACKEND to route inference to a remote API instead of local models.
# The embed model (port 8082) always runs locally regardless of backend.
#
# Values:
#   local           — default: all three models run on-device
#   openrouter      — OpenRouter API (openrouter.ai)
#   unlimitedclaude — UnlimitedClaude API (unlimitedclaude.com)
CODEY_BACKEND = os.environ.get("CODEY_BACKEND", "local").lower()

# Planner/summarizer backend — independent of the coder backend.
# Defaults to CODEY_BACKEND so existing setups need no change.
# Set CODEY_BACKEND_P to mix backends, e.g.:
#   export CODEY_BACKEND=openrouter        # coder → OpenRouter
#   export CODEY_BACKEND_P=unlimitedclaude # planner → UnlimitedClaude
#   export CODEY_BACKEND_P=local           # planner → local primary model (port 8080)
CODEY_PLANNER_BACKEND = os.environ.get("CODEY_BACKEND_P", CODEY_BACKEND).lower()


# Helpers — True for any backend that uses a remote OpenAI-compatible API
def is_remote_backend() -> bool:
    return CODEY_BACKEND in ("openrouter", "unlimitedclaude")


def is_remote_planner_backend() -> bool:
    return CODEY_PLANNER_BACKEND in ("openrouter", "unlimitedclaude")


# ── OpenRouter ────────────────────────────────────────────────────────────────
# OPENROUTER_API_KEY    — sk-or-... key from openrouter.ai/keys
# OPENROUTER_MODEL      — coding model,  e.g. "qwen/qwen-2.5-coder-7b-instruct"
# OPENROUTER_PLANNER_MODEL — planning model, e.g. "meta-llama/llama-3.2-1b-instruct:free"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "qwen/qwen-2.5-coder-7b-instruct")
# For planning, default to the same model as coding.
# If you have a paid OpenRouter account, a small fast model works well:
#   export OPENROUTER_PLANNER_MODEL=meta-llama/llama-3.2-1b-instruct:free
OPENROUTER_PLANNER_MODEL = os.environ.get("OPENROUTER_PLANNER_MODEL", OPENROUTER_MODEL)
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# ── UnlimitedClaude ───────────────────────────────────────────────────────────
# UNLIMITEDCLAUDE_API_KEY     — key from unlimitedclaude.com/dashboard
# UNLIMITEDCLAUDE_MODEL       — coding model,   e.g. "claude-sonnet-4-5"
# UNLIMITEDCLAUDE_PLANNER_MODEL — planning model, e.g. "claude-haiku-4-5"
UNLIMITEDCLAUDE_API_KEY = os.environ.get("UNLIMITEDCLAUDE_API_KEY", "")
UNLIMITEDCLAUDE_MODEL = os.environ.get("UNLIMITEDCLAUDE_MODEL", "qwen3-coder-next")
UNLIMITEDCLAUDE_PLANNER_MODEL = os.environ.get("UNLIMITEDCLAUDE_PLANNER_MODEL", "claude-haiku-4.5")
UNLIMITEDCLAUDE_BASE_URL = os.environ.get(
    "UNLIMITEDCLAUDE_BASE_URL", "https://api.unlimitedclaude.com/v1"
)

# ── Planner/summarizer — collapsed onto the primary server ──────────────────
# M1-B (2026-08-23): PLANNER_MODEL_PATH was repointed at the same Qwen3.5-4B
# model file as MODEL_PATH — the dedicated small planner model (formerly
# Qwen2.5-Coder-1.5B, upgraded at the time from 0.5B for better code-aware
# planning and task decomposition; see NEW-12 in NEW_ISSUES.md) is retired.
# M1-D (2026-08-23, this change): the separate port-8081 llama-server
# process itself is retired too, along with core/planner_loader.py (the
# module that spawned/swapped it) and the CODEY_PLANND_PORT-configurable
# PLANND_SERVER_PORT constant that named its port. There is now exactly one
# local model server: the primary Qwen3.5-4B on PRIMARY_SERVER_PORT
# (8080). "Planning" is no longer a separate process at all — it's a
# thinking-mode request (chat_template_kwargs={"enable_thinking": True})
# against that same primary server (see core/plannd.py:get_plan()), and
# "summarization" (core/summarizer.py) is likewise a plain request against
# it. PLANNER_MODEL_PATH itself is kept (identical to MODEL_PATH today) only
# because core/lora_import.py's fine-tune-swap code paths still read it as a
# distinct config key for a "planner-focused" LoRA artifact — see that
# module's own comments for why mutating it still matters even though both
# names point at the same physical server.
PLANNER_MODEL_PATH = Path(
    os.environ.get(
        "CODEY_PLANNER_MODEL",
        Path.home() / "models" / "qwen3.5-4b-instruct" / "Qwen3.5-4B-Q4_K_M.gguf",
    )
)

# ── Model memory-mapping settings — Change 2 ────────────────────────────────
# QWEN_MMAP=True  → weights are mmap'd from disk; only touched pages load into RAM.
# QWEN_MLOCK=False → OS can page weights out under memory pressure (default).
# These settings apply to the Qwen3.5-4B model (M1-B, 2026-08-23: constants
# renamed from QWEN_7B_MMAP/QWEN_7B_MLOCK — the "7B" naming became
# inaccurate once every model slot moved to Qwen3.5-4B; the previous "0.5B
# summarizer model is unaffected" line was already wrong before this change
# too, per NEW-124, since core/loader_v2.py applies these flags
# unconditionally to every LlamaServer instance it spawns, not just the
# primary one). The env vars themselves (CODEY_7B_MMAP/CODEY_7B_MLOCK) are
# NOT renamed here — that would also require updating docs/commands.md,
# docs/configuration.md, and docs/troubleshooting.md, more than this file
# plus core/loader_v2.py, so it's left for a later pass.
QWEN_MMAP = os.environ.get("CODEY_7B_MMAP", "1") != "0"  # default: True
QWEN_MLOCK = os.environ.get("CODEY_7B_MLOCK", "0") != "0"  # default: False

# ── Planner settings ─────────────────────────────────────────────────────────
# Temperature 0.2 keeps plans focused.
# NEW-164 (2026-08-23, M1-E live verification): 1024 was sized for the
# retired Qwen2.5-1.5B planner, which had no thinking mode at all. On
# Qwen3.5-4B with `chat_template_kwargs: {"enable_thinking": true}`
# (core/plannd.py:get_plan()), 1024 tokens is not enough headroom for a
# real reasoning trace before the model reaches its numbered-plan answer —
# live-reproduced: a 2,425-prompt-token request hit `finish_reason:
# "length"` at 1024 completion tokens with `message.content` still empty
# and 4,632 chars of unfinished `reasoning_content`. Raised to 2048.
# Corrected 2026-08-23 (code-reviewer's NEW-167 sanity check): this
# comparison used to say "chosen against daemon.py's task_timeout=1800s,
# leaving ~1100s for execution afterward" — wrong on two counts. First,
# the ~667s figure was computed with this constant's ORIGINAL,
# since-corrected PLANNER_MIN_PREFILL_TPS/PLANNER_MIN_GEN_TPS (20/4,
# corrected to 10/2 per NEW-167 below); with the current constants the
# same worst-case inner timeout is ~1296.5s, not ~667s (see
# compute_planner_timeout() in core/plannd.py). Second, task_timeout
# (core/daemon.py's _process_planner_tasks, wrapping task EXECUTION) and
# planning's own timeout do not actually share a budget in the code at
# all — they wrap two independent, sequential asyncio.wait_for calls,
# planning then execution, not one combined ceiling. Do not restate a
# shared-budget framing that doesn't exist in the control flow. The
# ceiling actually worth checking against is core/planner_service.py's
# client-side socket timeout (_request_daemon_plan()), which NEW-169
# found was a stale flat 185s — it is now itself derived from this same
# formula, so it no longer needs a separate hardcoded comparison here.
# 4096 tokens would roughly double 2048's own worst-case cost again — not
# defensible for a single planning call regardless of which downstream
# ceiling is checked. This value happens to equal
# MODEL_CONFIG["max_tokens"] above (the server's --n-predict startup
# default) — that is a COINCIDENCE, not a dependency. Confirmed against
# llama.cpp's server request schema: a request's own `max_tokens`/
# `n_predict` has no clamp to the server's startup default, so do not
# "simplify" this by referencing MODEL_CONFIG["max_tokens"] instead of a
# literal — a future change to one must not silently change the other.
#
# IMPORTANT: the reasoning trace itself is unbounded in principle — no
# fixed token budget is guaranteed sufficient on a harder prompt, because
# there is no way to cap the reasoning portion separately from the answer
# (confirmed: core/loader_v2.py's server spawn args expose no such flag).
# This is why core/plannd.py's get_plan() logs a warning whenever a
# thinking-mode request comes back with finish_reason == "length" and
# empty content — that is the actually-silent failure mode this comment
# cannot fix by itself.
PLANNER_TEMPERATURE = 0.2
PLANNER_MAX_TOKENS = 2048

# 7.3 sub-task E, Task B (2026-08-24): medium-tier budget for a planning
# request made with `chat_template_kwargs: {"enable_thinking": false}`
# (core/plannd.py:get_plan()'s enable_thinking=False branch). Verified
# directly against the live GGUF's embedded Jinja chat template (rule 12 —
# not assumed from family resemblance to anything): enable_thinking=false
# (or unset) produces a pre-closed, empty `<think>\n\n</think>\n\n` block —
# the model emits NO reasoning trace at all in that case, so none of
# PLANNER_MAX_TOKENS's headroom for an unbounded thinking trace (see that
# constant's own comment above) applies here. 1024 is sized from
# PLANNER_PROMPT's own answer shape instead: 1-8 short plain-English steps,
# no code, no markdown — real answers run roughly 50-400 tokens, so 1024 is
# 2.5x+ headroom over the largest realistic non-thinking answer. This is
# NOT "the retired Qwen2.5-1.5B planner used 1024" — that would be a
# family-resemblance justification for an unrelated model/prompt shape,
# explicitly rejected during scoping.
#
# Invariant that must never be silently inverted (advisor-flagged): a
# larger medium-tier budget than hard-tier's would mean "less capable
# planning mode" costs MORE tokens than "more capable" — the opposite
# of the intent. PLANNER_MAX_TOKENS_MEDIUM < PLANNER_MAX_TOKENS always.
PLANNER_MAX_TOKENS_MEDIUM = 1024

# NEW-165 (2026-08-23, M1-E live verification): formula-based HTTP timeout
# inputs for core/plannd.py's get_plan() (local backend only — NOT
# _get_plan_remote(), a different backend with its own timeout=60 left
# untouched).
#
# NEW-167 (2026-08-23, post-fix live re-verification): the first pass at
# these two constants (20 / 4) was NOT actually a floor below M1-E's
# measured range — it was M1-E's range itself, cited from a different
# call shape (M1-E's 23-26 tok/s prefill and 4.87 tok/s figures came from
# a non-thinking coding request and a differently-loaded device state).
# A direct re-measurement of a cold-cache, thinking-mode planning call —
# the exact shape these constants are meant to bound — measured
# 10.63-11.5 tok/s prefill and 2.15-2.74 tok/s generation on this same
# device (~/.codeyOS/llama-server.log, task 0's print_timing line for
# prefill; three separate completions for generation). The values below
# are set at approximately that measured floor itself (10/10.63 ≈ 94% of
# the lowest single prefill sample; 2/2.15 ≈ 93% of the lowest single
# generation sample) — NOT halved, despite an earlier draft of this
# comment claiming that; corrected by code-reviewer 2026-08-23. A ~6-7%
# cushion is a thin margin, especially given the FIRST calibration
# attempt (the original 20/4, sourced from a differently-shaped M1-E
# measurement) was already found ~2x optimistic once via live
# re-measurement. If this recurs a third time, don't re-derive by hand
# again — widen the cushion deliberately or gather more samples (rule 12:
# measure the artifact the constant actually governs, not a
# family-resemblant figure from a different code path).
PLANNER_MIN_PREFILL_TPS = 10
PLANNER_MIN_GEN_TPS = 2
PLANNER_TIMEOUT_MARGIN_SECONDS = 30


# ── User Configuration & Service Orchestration Settings ─────────────────────

def get_config_file_path() -> Path:
    """
    Return the active config.json path.
    Precedence:
      1. CODEY_CONFIG_PATH environment variable (if set and non-empty)
      2. ~/.codeyOS/config.json (if exists)
      3. <CODEY_DIR>/config.json (if exists)
      4. Default fallback: <CODEY_DIR>/config.json
    """
    env_path = os.environ.get("CODEY_CONFIG_PATH")
    if env_path and env_path.strip():
        return Path(env_path.strip()).expanduser().resolve()

    state_config = CODEY_STATE_DIR / "config.json"
    repo_config = CODEY_DIR / "config.json"

    if state_config.is_file():
        return state_config
    if repo_config.is_file():
        return repo_config

    return repo_config


def load_user_config(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Load JSON configuration from config_path or active get_config_file_path().
    Returns an empty dict if the file is missing or invalid JSON.
    """
    path = Path(config_path).expanduser().resolve() if config_path else get_config_file_path()
    if not path.is_file():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_cloudflare_tunnel_token(config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Extract Cloudflare tunnel token.
    Precedence:
      1. CLOUDFLARE_TUNNEL_TOKEN or CLOUDFLARED_TOKEN env var
      2. config["cloudflare"]["tunnel_token"] or config["cloudflare_tunnel_token"]
    Returns string token if set and non-empty, otherwise None.
    """
    env_token = os.environ.get("CLOUDFLARE_TUNNEL_TOKEN") or os.environ.get("CLOUDFLARED_TOKEN")
    if env_token is not None and env_token.strip():
        return env_token.strip()

    cfg = config if config is not None else load_user_config()
    cf_section = cfg.get("cloudflare", {}) if isinstance(cfg, dict) else {}
    token = None
    if isinstance(cf_section, dict):
        token = cf_section.get("tunnel_token")
    if not token and isinstance(cfg, dict):
        token = cfg.get("cloudflare_tunnel_token") or cfg.get("tunnel_token")

    if token and isinstance(token, str) and token.strip():
        return token.strip()
    return None


def get_restoricon_api_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extract Restoricon Core API server configuration.
    Precedence:
      1. RESTORICON_API_HOST / RESTORICON_API_PORT / RESTORICON_DB_PATH env vars
      2. config["restoricon"]["api_host"] / ["api_port"] / ["db_path"]
      3. Defaults: host="127.0.0.1", port=8770, db_path="~/.codeyOS/restoricon.db"
    """
    cfg = config if config is not None else load_user_config()
    rest_section = cfg.get("restoricon", {}) if isinstance(cfg, dict) else {}
    if not isinstance(rest_section, dict):
        rest_section = {}

    host = (
        os.environ.get("RESTORICON_API_HOST")
        or rest_section.get("api_host")
        or rest_section.get("host")
        or "127.0.0.1"
    )

    port_raw = (
        os.environ.get("RESTORICON_API_PORT")
        or rest_section.get("api_port")
        or rest_section.get("port")
        or 8770
    )
    try:
        port = int(port_raw)
    except (ValueError, TypeError):
        port = 8770

    db_path_raw = (
        os.environ.get("RESTORICON_DB_PATH")
        or rest_section.get("db_path")
        or str(CODEY_STATE_DIR / "restoricon.db")
    )
    db_path = str(Path(os.path.expanduser(str(db_path_raw))).resolve())

    return {
        "host": str(host),
        "port": port,
        "db_path": db_path,
    }


def get_aigentik_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extract Codey-Aigentik configuration.
    Precedence:
      1. AIGENTIK_DIR / AIGENTIK_PORT env vars
      2. config["aigentik"]["dir"] / ["port"]
      3. Defaults: dir="~/Codey-Aigentik", port=8000
    """
    cfg = config if config is not None else load_user_config()
    aig_section = cfg.get("aigentik", {}) if isinstance(cfg, dict) else {}
    if not isinstance(aig_section, dict):
        aig_section = {}

    dir_raw = (
        os.environ.get("AIGENTIK_DIR")
        or aig_section.get("dir")
        or str(Path.home() / "Codey-Aigentik")
    )
    dir_path = str(Path(os.path.expanduser(str(dir_raw))).resolve())

    port_raw = (
        os.environ.get("AIGENTIK_PORT")
        or aig_section.get("port")
        or 8000
    )
    try:
        port = int(port_raw)
    except (ValueError, TypeError):
        port = 8000

    return {
        "dir": dir_path,
        "port": port,
    }


def get_gui_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extract GUI server configuration.
    Precedence:
      1. CODEY_GUI_HOST / CODEY_GUI_PORT / GUI_PORT env vars
      2. config["gui"]["host"] / ["port"]
      3. Defaults: host="127.0.0.1", port=8888
    """
    cfg = config if config is not None else load_user_config()
    gui_section = cfg.get("gui", {}) if isinstance(cfg, dict) else {}
    if not isinstance(gui_section, dict):
        gui_section = {}

    host = (
        os.environ.get("CODEY_GUI_HOST")
        or gui_section.get("host")
        or "127.0.0.1"
    )

    port_raw = (
        os.environ.get("CODEY_GUI_PORT")
        or os.environ.get("GUI_PORT")
        or gui_section.get("port")
        or 8888
    )
    try:
        port = int(port_raw)
    except (ValueError, TypeError):
        port = 8888

    return {
        "host": str(host),
        "port": port,
    }

