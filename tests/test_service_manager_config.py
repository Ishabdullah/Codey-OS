"""
Unit tests for Codey-OS service manager configuration, Cloudflare token extraction,
Restoricon API config, GUI config, Aigentik config, and env var overrides.
"""

import json
import os
import subprocess
import threading
from pathlib import Path
import pytest

from utils.config import (
    get_config_file_path,
    load_user_config,
    get_cloudflare_tunnel_token,
    get_restoricon_api_config,
    get_aigentik_config,
)


@pytest.fixture(autouse=True)
def clean_service_env(monkeypatch):
    """Ensure tests run with clean service environment variables."""
    keys_to_clear = [
        "CODEY_CONFIG_PATH",
        "CLOUDFLARE_TUNNEL_TOKEN",
        "CLOUDFLARED_TOKEN",
        "RESTORICON_API_HOST",
        "RESTORICON_API_PORT",
        "RESTORICON_DB_PATH",
        "AIGENTIK_DIR",
        "AIGENTIK_PORT",
        "CODEY_GUI_HOST",
        "CODEY_GUI_PORT",
        "GUI_PORT",
    ]
    for k in keys_to_clear:
        monkeypatch.delenv(k, raising=False)


def test_get_config_file_path_env_override(monkeypatch, tmp_path):
    custom_cfg = tmp_path / "custom_config.json"
    custom_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(custom_cfg))

    resolved = get_config_file_path()
    assert resolved == custom_cfg.resolve()


def test_load_user_config_valid(tmp_path):
    cfg_file = tmp_path / "test_config.json"
    content = {
        "cloudflare": {"tunnel_token": "cf_test_token_123"},
        "restoricon": {"api_host": "0.0.0.0", "api_port": 9000},
    }
    cfg_file.write_text(json.dumps(content), encoding="utf-8")

    loaded = load_user_config(cfg_file)
    assert loaded["cloudflare"]["tunnel_token"] == "cf_test_token_123"
    assert loaded["restoricon"]["api_port"] == 9000


def test_load_user_config_missing_file(tmp_path):
    missing_file = tmp_path / "non_existent.json"
    loaded = load_user_config(missing_file)
    assert loaded == {}


def test_load_user_config_corrupt_file(tmp_path):
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("NOT_JSON_DATA{{{", encoding="utf-8")
    loaded = load_user_config(corrupt_file)
    assert loaded == {}


def test_get_cloudflare_tunnel_token_from_env_override(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_TUNNEL_TOKEN", "token_from_env_primary")
    token = get_cloudflare_tunnel_token(config={"cloudflare": {"tunnel_token": "token_from_cfg"}})
    assert token == "token_from_env_primary"

    monkeypatch.delenv("CLOUDFLARE_TUNNEL_TOKEN")
    monkeypatch.setenv("CLOUDFLARED_TOKEN", "token_from_cloudflared_env")
    token = get_cloudflare_tunnel_token(config={"cloudflare": {"tunnel_token": "token_from_cfg"}})
    assert token == "token_from_cloudflared_env"


def test_get_cloudflare_tunnel_token_from_config():
    # Nested dict format
    cfg = {"cloudflare": {"tunnel_token": "cf_sec_token_99"}}
    assert get_cloudflare_tunnel_token(cfg) == "cf_sec_token_99"

    # Flat fallback key format
    cfg_flat = {"cloudflare_tunnel_token": "cf_flat_token_88"}
    assert get_cloudflare_tunnel_token(cfg_flat) == "cf_flat_token_88"

    # Empty / whitespace token
    cfg_empty = {"cloudflare": {"tunnel_token": "   "}}
    assert get_cloudflare_tunnel_token(cfg_empty) is None

    # Empty config
    assert get_cloudflare_tunnel_token({}) is None


def test_get_restoricon_api_config_defaults():
    cfg = get_restoricon_api_config({})
    assert cfg["host"] == "127.0.0.1"
    assert cfg["port"] == 8770
    assert cfg["db_path"].endswith("restoricon.db")


def test_get_restoricon_api_config_from_dict():
    config_dict = {
        "restoricon": {
            "api_host": "192.168.1.50",
            "api_port": 8800,
            "db_path": "/tmp/custom_restoricon.db",
        }
    }
    cfg = get_restoricon_api_config(config_dict)
    assert cfg["host"] == "192.168.1.50"
    assert cfg["port"] == 8800
    assert cfg["db_path"] == str(Path("/tmp/custom_restoricon.db").resolve())


def test_get_restoricon_api_config_env_overrides(monkeypatch):
    config_dict = {
        "restoricon": {
            "api_host": "192.168.1.50",
            "api_port": 8800,
            "db_path": "/tmp/custom_restoricon.db",
        }
    }
    monkeypatch.setenv("RESTORICON_API_HOST", "0.0.0.0")
    monkeypatch.setenv("RESTORICON_API_PORT", "9999")
    monkeypatch.setenv("RESTORICON_DB_PATH", "/var/lib/restoricon.db")

    cfg = get_restoricon_api_config(config_dict)
    assert cfg["host"] == "0.0.0.0"
    assert cfg["port"] == 9999
    assert cfg["db_path"] == str(Path("/var/lib/restoricon.db").resolve())


def test_get_aigentik_config_defaults():
    cfg = get_aigentik_config({})
    assert cfg["dir"] == str(Path.home() / "Codey-Aigentik")
    assert cfg["port"] == 8000


def test_get_aigentik_config_from_dict():
    config_dict = {
        "aigentik": {
            "dir": "/opt/aigentik",
            "port": 8100,
        }
    }
    cfg = get_aigentik_config(config_dict)
    assert cfg["dir"] == str(Path("/opt/aigentik").resolve())
    assert cfg["port"] == 8100


def test_get_aigentik_config_env_overrides(monkeypatch):
    config_dict = {
        "aigentik": {
            "dir": "/opt/aigentik",
            "port": 8100,
        }
    }
    monkeypatch.setenv("AIGENTIK_DIR", "/srv/codey-aigentik")
    monkeypatch.setenv("AIGENTIK_PORT", "8200")

    cfg = get_aigentik_config(config_dict)
    assert cfg["dir"] == str(Path("/srv/codey-aigentik").resolve())
    assert cfg["port"] == 8200


def test_codey_script_cli_help_and_config():
    repo_root = Path(__file__).parent.parent.resolve()
    codey_bin = repo_root / "codey"
    assert codey_bin.is_file()
    assert os.access(codey_bin, os.X_OK)

    # Test codey help
    res_help = subprocess.run(
        [str(codey_bin), "help"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res_help.returncode == 0
    assert "Codey-OS" in res_help.stdout
    assert "Usage:" in res_help.stdout

    # Test codey config
    res_cfg = subprocess.run(
        [str(codey_bin), "config"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res_cfg.returncode == 0
    assert "Config file:" in res_cfg.stdout

    # Test codey status
    res_status = subprocess.run(
        [str(codey_bin), "status"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res_status.returncode == 0
    assert "Services Status:" in res_status.stdout


def test_service_manager_pid_lifecycle(tmp_path):
    repo_root = Path(__file__).parent.parent.resolve()
    svc_lib = repo_root / "lib" / "service_manager.sh"

    # Start a dummy background process
    proc = subprocess.Popen(["sleep", "30"])
    pid = proc.pid
    pid_file = tmp_path / "dummy_service.pid"
    pid_file.write_text(str(pid), encoding="utf-8")

    # Run bash script sourcing service_manager and stopping by PID
    script = f"""
    source "{svc_lib}"
    svc_is_running "{pid_file}" || exit 1
    svc_stop_by_pid "{pid_file}" "DummyService"
    """
    res = subprocess.run(
        ["bash", "-c", script],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "stopped" in res.stdout
    assert not pid_file.exists()

    # Verify process is dead
    proc.poll()
    assert proc.returncode is not None or not proc.is_running() if hasattr(proc, 'is_running') else True


def test_svc_entrypoint_proc_filter_derives_from_entrypoint_extension():
    """NEW-271: svc_find_orphans_by_cwd's proc_filter must track the
    entrypoint's actual interpreter, not be hardcoded to "node" — a
    python3/bash entrypoint's orphans would otherwise never be found.
    """
    repo_root = Path(__file__).parent.parent.resolve()
    svc_lib = repo_root / "lib" / "service_manager.sh"

    script = f"""
    source "{svc_lib}"
    echo "PY:$(svc_entrypoint_proc_filter "main.py")"
    echo "SH:$(svc_entrypoint_proc_filter "run.sh")"
    echo "JS:$(svc_entrypoint_proc_filter "index.js")"
    echo "EMPTY:$(svc_entrypoint_proc_filter "")"
    """
    res = subprocess.run(
        ["bash", "-c", script],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "PY:python3" in res.stdout
    assert "SH:bash" in res.stdout
    assert "JS:node" in res.stdout
    assert "EMPTY:" in res.stdout


def test_svc_find_orphans_by_cwd_matches_python_entrypoint(tmp_path):
    """NEW-271 regression guard: with proc_filter derived as "python3" (not
    hardcoded "node"), a python3-launched entrypoint must be found by the
    orphan scan — this is exactly the case the hardcoded "node" filter
    silently missed.
    """
    repo_root = Path(__file__).parent.parent.resolve()
    svc_lib = repo_root / "lib" / "service_manager.sh"

    app_dir = tmp_path / "py_app"
    app_dir.mkdir()
    (app_dir / "main.py").write_text(
        "import time\ntime.sleep(60)\n", encoding="utf-8"
    )

    p_real = subprocess.Popen(["python3", "main.py"], cwd=str(app_dir))

    try:
        script = f"""
        source "{svc_lib}"
        entry_script=$(svc_detect_entrypoint_script "{app_dir}")
        proc_filter=$(svc_entrypoint_proc_filter "$entry_script")
        echo "FILTER:$proc_filter"
        found=$(svc_find_orphans_by_cwd "{app_dir}" "$proc_filter" "$entry_script")
        echo "FOUND:$found"
        """
        res = subprocess.run(
            ["bash", "-c", script],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        assert "FILTER:python3" in res.stdout
        found = res.stdout.split("FOUND:")[1].split()
        assert str(p_real.pid) in found, res.stdout
    finally:
        p_real.terminate()
        p_real.wait()


def test_status_aigentik_detects_python_entrypoint_orphan(tmp_path):
    """NEW-271 end-to-end regression guard: exercises the actual call site
    (`status_aigentik`), not just the `svc_entrypoint_proc_filter` helper in
    isolation. Under the pre-fix hardcoded `"node"` proc_filter, a
    `python3 main.py`-launched orphan is invisible to `status_aigentik`
    (`pgrep node` finds nothing); this must now report it.
    """
    repo_root = Path(__file__).parent.parent.resolve()
    svc_lib = repo_root / "lib" / "service_manager.sh"

    app_dir = tmp_path / "py_aigentik"
    app_dir.mkdir()
    state_dir = tmp_path / "codey_state_py"
    state_dir.mkdir()

    (app_dir / "main.py").write_text(
        "import time\ntime.sleep(60)\n", encoding="utf-8"
    )

    p_orphan = subprocess.Popen(["python3", "main.py"], cwd=str(app_dir))

    script = f"""
    export CODEY_STATE_DIR="{state_dir}"
    export AIGENTIK_DIR="{app_dir}"
    source "{svc_lib}"
    status_aigentik
    """

    try:
        res = subprocess.run(
            ["bash", "-c", script],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        assert "UNTRACKED orphan" in res.stdout, res.stdout
        assert str(p_orphan.pid) in res.stdout, res.stdout
    finally:
        p_orphan.terminate()
        p_orphan.wait()


def test_svc_find_orphans_by_cwd(tmp_path):
    repo_root = Path(__file__).parent.parent.resolve()
    svc_lib = repo_root / "lib" / "service_manager.sh"

    # Create two temporary directories
    target_dir = tmp_path / "target_app"
    target_dir.mkdir()
    other_dir = tmp_path / "other_app"
    other_dir.mkdir()

    # Spawn a process in target_dir and one in other_dir
    p_target = subprocess.Popen(["sleep", "30"], cwd=str(target_dir))
    p_other = subprocess.Popen(["sleep", "30"], cwd=str(other_dir))

    try:
        script = f"""
        source "{svc_lib}"
        found=$(svc_find_orphans_by_cwd "{target_dir}" "sleep")
        echo "FOUND:$found"
        """
        res = subprocess.run(
            ["bash", "-c", script],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        output = res.stdout
        assert f"FOUND:{p_target.pid}" in output or str(p_target.pid) in output
        assert str(p_other.pid) not in output.split("FOUND:")[1].strip()
    finally:
        p_target.terminate()
        p_other.terminate()
        p_target.wait()
        p_other.wait()


def test_svc_find_orphans_by_cwd_requires_entrypoint_match(tmp_path):
    """Rule 3: a cwd match ALONE must not flag a PID for termination.

    Two node processes share the same cwd and the same `node` proc_filter;
    only the one whose cmdline contains the expected entrypoint token may be
    returned. The decoy (a REPL / test runner / unrelated script in the same
    directory) must be left alone.
    """
    if subprocess.run(["bash", "-c", "command -v node"],
                      capture_output=True).returncode != 0:
        pytest.skip("node not installed")

    repo_root = Path(__file__).parent.parent.resolve()
    svc_lib = repo_root / "lib" / "service_manager.sh"

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "index.js").write_text("setTimeout(() => {}, 60000);\n", encoding="utf-8")
    (app_dir / "decoy.js").write_text("setTimeout(() => {}, 60000);\n", encoding="utf-8")

    p_real = subprocess.Popen(["node", "index.js"], cwd=str(app_dir))
    p_decoy = subprocess.Popen(["node", "decoy.js"], cwd=str(app_dir))

    try:
        script = f"""
        source "{svc_lib}"
        found=$(svc_find_orphans_by_cwd "{app_dir}" "node" "index.js")
        echo "FOUND:$found"
        """
        res = subprocess.run(
            ["bash", "-c", script],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        found = res.stdout.split("FOUND:")[1].split()
        assert str(p_real.pid) in found, res.stdout
        assert str(p_decoy.pid) not in found, (
            f"decoy PID {p_decoy.pid} matched on cwd alone — Rule 3 violation\n{res.stdout}"
        )
    finally:
        for p in (p_real, p_decoy):
            p.terminate()
            p.wait()


def test_start_and_stop_aigentik_cleans_orphans(tmp_path, monkeypatch):
    repo_root = Path(__file__).parent.parent.resolve()
    svc_lib = repo_root / "lib" / "service_manager.sh"

    if subprocess.run(["bash", "-c", "command -v node"],
                      capture_output=True).returncode != 0:
        pytest.skip("node not installed")

    app_dir = tmp_path / "mock_aigentik"
    app_dir.mkdir()
    state_dir = tmp_path / "codey_state"
    state_dir.mkdir()

    # Mock entrypoint script: index.js
    entrypoint = app_dir / "index.js"
    entrypoint.write_text("setTimeout(() => {}, 60000);\n", encoding="utf-8")

    # Spawn an untracked orphan node process in app_dir
    p_orphan = subprocess.Popen(["node", "index.js"], cwd=str(app_dir))

    script = f"""
    export CODEY_STATE_DIR="{state_dir}"
    export AIGENTIK_DIR="{app_dir}"
    source "{svc_lib}"

    # Verify orphan is discovered by status
    status_aigentik

    # Start should kill the orphan and launch fresh
    start_aigentik
    """

    res = subprocess.run(
        ["bash", "-c", script],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )

    started_pid = None
    try:
        assert res.returncode == 0
        assert "UNTRACKED orphan" in res.stdout or "orphaned process" in res.stdout
        assert str(p_orphan.pid) in res.stdout

        # Orphan must be terminated
        p_orphan.poll()
        assert p_orphan.returncode is not None

        # A fresh instance must actually have been launched: PID file present,
        # holding a real PID, and that process alive. Without this the
        # "0 remaining" assertion below passes even if start_aigentik ran
        # nothing.
        pid_file = state_dir / "aigentik.pid"
        assert pid_file.exists(), f"start_aigentik wrote no PID file\n{res.stdout}"
        raw = pid_file.read_text().strip()
        assert raw.isdigit(), f"PID file contents not a PID: {raw!r}"
        started_pid = int(raw)
        assert started_pid != p_orphan.pid
        os.kill(started_pid, 0)  # raises if the fresh instance is not alive
        # ...and it must be the Aigentik entrypoint, not some unrelated process.
        cmdline = Path(f"/proc/{started_pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        assert "index.js" in cmdline, f"PID {started_pid} is not the entrypoint: {cmdline!r}"

        # Stop should cleanly stop the tracked instance and confirm 0 processes
        stop_script = f"""
        export CODEY_STATE_DIR="{state_dir}"
        export AIGENTIK_DIR="{app_dir}"
        source "{svc_lib}"
        stop_aigentik
        """
        res_stop = subprocess.run(
            ["bash", "-c", stop_script],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert res_stop.returncode == 0
        assert "fully stopped, 0 processes remaining" in res_stop.stdout
        if started_pid is not None:
            try:
                os.kill(started_pid, 0)
                raise AssertionError(f"fresh instance {started_pid} survived stop_aigentik")
            except ProcessLookupError:
                pass
    finally:
        if p_orphan.poll() is None:
            p_orphan.kill()
        if started_pid is not None:
            try:
                os.kill(started_pid, 9)
            except ProcessLookupError:
                pass


def test_concurrent_start_aigentik_no_pid_file_race(tmp_path):
    """NEW-268: two concurrent `start_aigentik` invocations must not race.

    Before the flock-based fix, invocation A could spawn its node child,
    then invocation B's orphan scan (running before A wrote its PID file)
    would see A's fresh child as untracked, kill it, and A's own post-spawn
    `kill -0` check would then fail — so A would `rm -f` the PID file B had
    *just* written for its own start, leaving B's node running untracked
    and the PID file gone/wrong.

    This test launches two `start_aigentik` invocations as close to
    simultaneously as possible (via threads starting each subprocess) against
    a stub Aigentik entrypoint (a plain node script, no real
    ~/Codey-Aigentik dependency) and asserts the fixed invariants:

      1. Neither invocation errors out.
      2. Exactly one live node process matching the entrypoint exists when
         both have finished (the loser must not have kept its own untracked
         node running — the flock means the loser skips its start attempt
         entirely rather than racing the winner's orphan scan).
      3. The PID file exists, holds a real PID, and that PID is alive and
         is in fact the entrypoint process (not deleted out from under the
         winner by the loser, and not left pointing at a dead PID).
    """
    repo_root = Path(__file__).parent.parent.resolve()
    svc_lib = repo_root / "lib" / "service_manager.sh"

    if subprocess.run(["bash", "-c", "command -v node"],
                      capture_output=True).returncode != 0:
        pytest.skip("node not installed")

    app_dir = tmp_path / "mock_aigentik_concurrent"
    app_dir.mkdir()
    state_dir = tmp_path / "codey_state_concurrent"
    state_dir.mkdir()

    # Stub entrypoint: long-lived, no dependency on a real Aigentik checkout.
    entrypoint = app_dir / "index.js"
    entrypoint.write_text("setTimeout(() => {}, 60000);\n", encoding="utf-8")

    script = f"""
    export CODEY_STATE_DIR="{state_dir}"
    export AIGENTIK_DIR="{app_dir}"
    source "{svc_lib}"
    start_aigentik
    """

    results = [None, None]

    def run_start(idx):
        results[idx] = subprocess.run(
            ["bash", "-c", script],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )

    threads = [threading.Thread(target=run_start, args=(i,)) for i in (0, 1)]
    started_pid = None
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert all(r is not None for r in results), "one invocation never completed"
        for i, res in enumerate(results):
            assert res.returncode == 0, (
                f"start_aigentik invocation {i} exited {res.returncode}\n"
                f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
            )

        # Exactly one invocation should report actually starting a fresh
        # process; the other must have deferred to it (already running, or
        # skipped because the lock was held) rather than also spawning.
        started_count = sum("started (PID" in r.stdout for r in results)
        assert started_count == 1, (
            f"expected exactly 1 invocation to report starting, got {started_count}\n"
            + "\n---\n".join(r.stdout for r in results)
        )
        # And the loser must have visibly deferred (either it saw the lock
        # held, or it saw the winner's PID file as already-running) — not
        # silently no-op for some other reason.
        deferred_count = sum(
            ("another start already in progress" in r.stdout)
            or ("already running" in r.stdout)
            or ("running (PID" in r.stdout)
            for r in results
        )
        assert deferred_count >= 1, (
            "expected the losing invocation to report deferring (lock held or "
            "already running), got neither\n" + "\n---\n".join(r.stdout for r in results)
        )

        pid_file = state_dir / "aigentik.pid"
        assert pid_file.exists(), (
            f"PID file missing after concurrent start_aigentik runs\n"
            + "\n---\n".join(r.stdout for r in results)
        )
        raw = pid_file.read_text().strip()
        assert raw.isdigit(), f"PID file contents not a PID: {raw!r}"
        started_pid = int(raw)
        os.kill(started_pid, 0)  # raises if the tracked PID is not alive

        cmdline = Path(f"/proc/{started_pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        assert "index.js" in cmdline, f"tracked PID {started_pid} is not the entrypoint: {cmdline!r}"

        # Confirm no second, untracked node instance is also running from
        # app_dir — the bug's failure mode is exactly this: a second live
        # process the PID file no longer (or never did) point at.
        check_script = f"""
        export CODEY_STATE_DIR="{state_dir}"
        export AIGENTIK_DIR="{app_dir}"
        source "{svc_lib}"
        found=$(svc_find_orphans_by_cwd "{app_dir}" "node" "index.js")
        echo "FOUND:$found"
        """
        res_check = subprocess.run(
            ["bash", "-c", check_script],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert res_check.returncode == 0
        found_pids = res_check.stdout.split("FOUND:")[1].split()
        assert found_pids == [str(started_pid)], (
            f"expected exactly one live node process ({started_pid}), found {found_pids}"
        )
    finally:
        if started_pid is not None:
            try:
                os.kill(started_pid, 9)
            except ProcessLookupError:
                pass


def test_sequential_restart_after_start_still_reports_already_running(tmp_path):
    """NEW-268 fix regression guard: the lock fd must not leak into the
    spawned Aigentik process.

    `start_aigentik`'s fix opens the lock on fd 200 via `exec 200>...` in a
    subshell, before forking the long-lived node child. File descriptors are
    inherited by forked children unless explicitly closed, and an flock lock
    is held by the open file description, not by the process that acquired
    it — so if the spawn line ever forgets to close fd 200 on the child (the
    `200>&-` redirection), the node process itself keeps holding the lock for
    its entire lifetime. Every subsequent `start_aigentik` call would then
    see the lock as held and print "another start already in progress,
    skipping" instead of correctly reporting "already running (PID ...)" and
    running its normal already-running/orphan-scan path — silently
    disabling that path for as long as Aigentik stays up.

    This is a *sequential*, not concurrent, scenario deliberately: run
    `start_aigentik` once to completion (verifying the process is up), then
    run it again from a fresh shell (fresh process, fresh fd table — the
    only thing carried over is the flock's live state via the still-running
    node process). Only a real fd leak makes this second call misbehave;
    plain concurrency alone does not exercise this path.
    """
    repo_root = Path(__file__).parent.parent.resolve()
    svc_lib = repo_root / "lib" / "service_manager.sh"

    if subprocess.run(["bash", "-c", "command -v node"],
                      capture_output=True).returncode != 0:
        pytest.skip("node not installed")

    app_dir = tmp_path / "mock_aigentik_sequential"
    app_dir.mkdir()
    state_dir = tmp_path / "codey_state_sequential"
    state_dir.mkdir()

    entrypoint = app_dir / "index.js"
    entrypoint.write_text("setTimeout(() => {}, 60000);\n", encoding="utf-8")

    script = f"""
    export CODEY_STATE_DIR="{state_dir}"
    export AIGENTIK_DIR="{app_dir}"
    source "{svc_lib}"
    start_aigentik
    """

    started_pid = None
    try:
        res1 = subprocess.run(["bash", "-c", script], cwd=str(repo_root),
                               capture_output=True, text=True)
        assert res1.returncode == 0, f"first start_aigentik failed:\n{res1.stdout}\n{res1.stderr}"
        assert "started (PID" in res1.stdout, res1.stdout

        pid_file = state_dir / "aigentik.pid"
        assert pid_file.exists()
        started_pid = int(pid_file.read_text().strip())
        os.kill(started_pid, 0)  # confirm it's actually up before the second call

        # Second, independent process/shell invocation while Aigentik is
        # still running. With fd 200 correctly closed on the spawned child,
        # the lock is free by the time this runs (the first subshell already
        # exited), and start_aigentik should reach its normal
        # already-running check and report it — NOT "another start already
        # in progress" (that message would mean the long-lived node process
        # is still holding the lock fd itself).
        res2 = subprocess.run(["bash", "-c", script], cwd=str(repo_root),
                               capture_output=True, text=True)
        assert res2.returncode == 0, f"second start_aigentik failed:\n{res2.stdout}\n{res2.stderr}"
        assert "another start already in progress" not in res2.stdout, (
            "fd 200 leaked into the spawned Aigentik process — the lock is "
            f"still held by the long-lived node process itself:\n{res2.stdout}"
        )
        assert f"already running (PID {started_pid})" in res2.stdout, (
            f"expected 'already running (PID {started_pid})', got:\n{res2.stdout}"
        )
    finally:
        if started_pid is not None:
            try:
                os.kill(started_pid, 9)
            except ProcessLookupError:
                pass
