"""
NEW-754 Part D — utils/config.py's `LLAMA_SERVER_BIN` resolution order.

Ish's decision: prefer the install.sh-built binary
(`~/llama.cpp/build/bin/llama-server`, from `install_llama_cpp()`) over
whatever's on PATH; fall back to PATH (`shutil.which("llama-server")`)
only when the source-built binary doesn't exist/isn't executable.

`LLAMA_SERVER_BIN` is computed at module-import time from `Path.home()`
and `shutil.which()`, so each case here reloads `utils.config` with `HOME`
pointed at an isolated tmp dir and `shutil.which` patched — never touches
the real device binaries (CLAUDE.md rule 2; no process is spawned here at
all, this is pure path-resolution logic).
"""
import importlib
import os

import pytest


@pytest.fixture
def reload_config(monkeypatch, tmp_path):
    """Returns a function that reloads utils.config with HOME pointed at
    an isolated tmp_path (so Path.home()-derived paths never touch the
    real device), restoring the real module afterwards."""
    import utils.config as cfg

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CODEY_LLAMA_SERVER", raising=False)
    # Avoid the CODEY_N_CTX validation path raising on a hostile env value
    # left over from another test/session — reload must not depend on it.
    monkeypatch.delenv("CODEY_N_CTX", raising=False)

    def _reload():
        return importlib.reload(cfg)

    yield _reload

    # Restore the real module state for any test that runs after this one
    # in the same session (module objects are process-global).
    monkeypatch.undo()
    importlib.reload(cfg)


def test_prefers_source_built_binary_over_path(reload_config, tmp_path, monkeypatch):
    source_dir = tmp_path / "llama.cpp" / "build" / "bin"
    source_dir.mkdir(parents=True)
    source_bin = source_dir / "llama-server"
    source_bin.write_text("#!/bin/sh\n")
    source_bin.chmod(0o755)

    # shutil.which would also find a PATH binary — source build must win.
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/llama-server")

    reloaded = reload_config()

    assert reloaded.LLAMA_SERVER_BIN == str(source_bin)


def test_falls_back_to_path_when_source_build_missing(reload_config, monkeypatch):
    # No ~/llama.cpp/build/bin/llama-server created in tmp_path's HOME.
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/llama-server")

    reloaded = reload_config()

    assert reloaded.LLAMA_SERVER_BIN == "/usr/bin/llama-server"


def test_falls_back_to_source_path_string_when_neither_exists(reload_config, monkeypatch, tmp_path):
    """Matches old behavior's final fallback: even with nothing resolvable,
    LLAMA_SERVER_BIN must still be a non-None string (the source-built
    path), not None — so downstream `str(LLAMA_SERVER_BIN)` callers never
    see a None."""
    monkeypatch.setattr("shutil.which", lambda name: None)

    reloaded = reload_config()

    expected = str(tmp_path / "llama.cpp" / "build" / "bin" / "llama-server")
    assert reloaded.LLAMA_SERVER_BIN == expected


def test_non_executable_source_build_falls_back_to_path(reload_config, tmp_path, monkeypatch):
    """A file existing at the source-build path but not executable (e.g. a
    failed/partial build) must not be preferred — falls back to PATH."""
    source_dir = tmp_path / "llama.cpp" / "build" / "bin"
    source_dir.mkdir(parents=True)
    source_bin = source_dir / "llama-server"
    source_bin.write_text("#!/bin/sh\n")
    source_bin.chmod(0o644)  # not executable

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/llama-server")

    reloaded = reload_config()

    assert reloaded.LLAMA_SERVER_BIN == "/usr/bin/llama-server"


def test_env_override_still_wins_over_both(reload_config, tmp_path, monkeypatch):
    source_dir = tmp_path / "llama.cpp" / "build" / "bin"
    source_dir.mkdir(parents=True)
    source_bin = source_dir / "llama-server"
    source_bin.write_text("#!/bin/sh\n")
    source_bin.chmod(0o755)

    monkeypatch.setenv("CODEY_LLAMA_SERVER", "/custom/path/llama-server")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/llama-server")

    reloaded = reload_config()

    assert reloaded.LLAMA_SERVER_BIN == "/custom/path/llama-server"
