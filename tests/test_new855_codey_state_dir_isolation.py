"""
WP2.1 group 3 (NEW-855, closes NEW-425/NEW-812 as a consequence of the same
mechanism) -- `utils/config.py`'s `CODEY_STATE_DIR` env var override.

`core/memory_v2.py:743` runs `memory = get_memory()` at module IMPORT time,
which constructs `EpisodicMemory()`/`SymbolicMemory()`, which call
`core.state.get_state_store()` at their own `__init__` time. `core/state.py`
computes its DB path from `utils/config.py`'s `CODEY_STATE_DIR`. Before this
fix, that was hardcoded to `Path.home() / ".codeyOS"`, so merely importing
`core.memory_v2` (or `core.state`/`core.checkpoint`/`core.model_registry`)
unconditionally created a real on-disk `~/.codeyOS/state.db` -- confirmed
live: `pytest --collect-only` alone, with zero tests executed, already
created it. The fix makes `CODEY_STATE_DIR` honor an env var override
(mirroring `test_config_llama_server_bin.py`'s `LLAMA_SERVER_BIN`
env-override-vs-default convention), and the root `conftest.py` sets that
env var at collection time so every import-time state store in this test
session is redirected without editing any of those modules.
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def reload_config(monkeypatch):
    """Returns a function that reloads utils.config, restoring the real
    module state afterwards (module objects are process-global)."""
    import utils.config as cfg

    def _reload():
        return importlib.reload(cfg)

    yield _reload

    monkeypatch.undo()
    importlib.reload(cfg)


def test_codey_state_dir_env_override_wins(reload_config, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEY_STATE_DIR", str(tmp_path))

    reloaded = reload_config()

    assert reloaded.CODEY_STATE_DIR == tmp_path


def test_codey_state_dir_falls_back_to_home_default_when_unset(reload_config, tmp_path, monkeypatch):
    monkeypatch.delenv("CODEY_STATE_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    reloaded = reload_config()

    assert reloaded.CODEY_STATE_DIR == tmp_path / ".codeyOS"


def test_fresh_import_of_memory_v2_never_touches_real_codeyos_dir(tmp_path):
    """
    The actual mechanism this task fixes: importing `core.memory_v2` (whose
    module-level `get_memory()` call cascades into `core.state`'s
    import-time schema-init/mkdir/sqlite3 connection) with `CODEY_STATE_DIR`
    pointed at a fresh tmp_path must create `state.db` under that tmp_path
    and must NOT touch the real `~/.codeyOS`.

    Run in a subprocess (not the main test process) because `core.memory_v2`
    and friends are almost certainly already imported by the time any test
    runs, and importlib.reload() does not reliably re-run every transitively
    cascaded module-level side effect the way a genuinely fresh interpreter
    import does.
    """
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    isolated_state_dir = tmp_path / "isolated_state"

    env = dict(os.environ)
    env["HOME"] = str(fake_home)
    env["CODEY_STATE_DIR"] = str(isolated_state_dir)

    result = subprocess.run(
        [sys.executable, "-c", "import core.memory_v2"],
        cwd=str(Path(__file__).resolve().parent.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"import failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )

    assert (isolated_state_dir / "state.db").exists(), (
        "core.memory_v2 import should have created state.db under the "
        "isolated CODEY_STATE_DIR"
    )

    # The subprocess's HOME is the fake_home, not the real device HOME, so
    # this cannot and must not touch the real ~/.codeyOS/state.db at all
    # (per the task's explicit prohibition on querying it) — instead,
    # confirm the import didn't fall back to ".codeyOS" under the fake HOME
    # either, which would mean CODEY_STATE_DIR was silently ignored.
    assert not (fake_home / ".codeyOS" / "state.db").exists(), (
        "import must not have fallen back to $HOME/.codeyOS, ignoring the "
        "CODEY_STATE_DIR override"
    )
