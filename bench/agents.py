"""Agent adapters. An agent is a callable (task, workspace_path) -> None that edits the workspace."""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from .suite import Task

REPO = Path(__file__).resolve().parent.parent


def null_agent(task: Task, workspace: Path) -> None:
    """Does nothing. Must score 0 (proves tasks are not pre-solved)."""


def oracle_agent(task: Task, workspace: Path) -> None:
    """Copies the reference solution. Must score 100% (proves tasks are solvable)."""
    for f in task.reference.iterdir():
        shutil.copy2(f, workspace / f.name)


# System names the bench child may inherit; every CODEY_* name is also kept
# (minus the deny set) so existing state/config/port overrides behave as before.
_CHILD_ENV_ALLOW = frozenset({
    "PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ", "PREFIX",
    "LD_LIBRARY_PATH", "ANDROID_ROOT", "ANDROID_DATA", "ANDROID_I18N_ROOT",
    "ANDROID_TZDATA_ROOT", "ANDROID_ART_ROOT", "TERMUX_VERSION", "TERMUX__PREFIX",
    "TERMUX__HOME",
    # Identity/config names that core/git_execution.py _LOCAL_COMMIT_AMBIENT
    # reads for local commits, plus SHELL and SSL_CERT_FILE (harmless, needed by
    # shell tool / TLS). Deliberately DROPPED: credentials (OPENROUTER_*,
    # UNLIMITEDCLAUDE_*, AIGENTIK_*, RESTORICON_*, GOOGLE_*, CLOUDFLARE*), proxies,
    # NODE_OPTIONS, JAVA_HOME, PYTHON*/PYTEST_*; extra_env is the opt-in channel.
    "USER", "LOGNAME", "EMAIL", "XDG_CONFIG_HOME", "SHELL", "SSL_CERT_FILE",
    "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE",
    "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_COMMITTER_DATE"})
# Authority-class names: never inherited and never accepted through extra_env.
_CHILD_ENV_DENY = frozenset({"ALLOW_SELF_MOD", "CODEY_SELF_IMPROVE"})
# argparse accepts abbreviations (--allow-s reaches --allow-self-mod), so a
# prefix/denylist check is unsound; only these exact flags are accepted.
_ALLOWED_EXTRA_ARGS = frozenset({"--plan", "--no-plan"})


def bench_child_env(base: Mapping[str, str], task_id: str, extra_env: Mapping[str, str] | None = None) -> dict:
    """Environment for the bench agent child: allowlist of `base`, then trajectory tags, then extra_env.

    Keeps system names and CODEY_* (minus ALLOW_SELF_MOD/CODEY_SELF_IMPROVE),
    dropping credentials, proxies, PYTHON*/PYTEST_* and the rest. extra_env is
    the operator's explicit opt-in (e.g. a remote-backend API key) and is
    applied last, but may not carry an authority-class name (ValueError).
    """
    env = {k: v for k, v in base.items()
           if (k in _CHILD_ENV_ALLOW or k.startswith("CODEY_")) and k not in _CHILD_ENV_DENY}
    env.update({"CODEY_TRAJECTORY": "1", "CODEY_TRAJECTORY_TAG": f"bench:{task_id}"})
    extra = dict(extra_env or {})
    bad = sorted(set(extra) & _CHILD_ENV_DENY)
    if bad:
        raise ValueError(f"extra_env may not set authority-class variables: {bad}")
    env.update(extra)
    return env


def make_codey_cli_agent(timeout: int = 900, extra_env: dict | None = None, extra_args: list | None = None):
    """Real Codey-OS via one-shot CLI. Needs a running llama-server: on-device only.

    The child gets bench_child_env (not the ambient environment), no inherited
    stdin, and only exact-match extra_args from {--plan, --no-plan}; anything
    else raises ValueError at construction time.
    """
    # Copy first, validate the copy: a caller mutating its list afterwards cannot add flags.
    extra_args = tuple(extra_args or ())
    extra_env = dict(extra_env or {})
    bad_args = [a for a in extra_args if a not in _ALLOWED_EXTRA_ARGS]
    if bad_args:
        raise ValueError(f"extra_args not allowed: {bad_args} (allowed: {sorted(_ALLOWED_EXTRA_ARGS)})")
    if set(extra_env or {}) & _CHILD_ENV_DENY:
        bench_child_env({}, "", extra_env)  # raises the ValueError at construction time too

    def agent(task: Task, workspace: Path) -> None:
        env = bench_child_env(os.environ, task.id, extra_env)
        cmd = [sys.executable, str(REPO / "main.py"), task.prompt, "--yolo", "--no-resume"] + list(extra_args)
        try:
            subprocess.run(cmd, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            pass  # graded as-is; a timeout is a failure only if tests fail
    return agent
