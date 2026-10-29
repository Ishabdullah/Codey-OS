"""CODEY_PRIMARY_MMAP / CODEY_PRIMARY_MLOCK env precedence.

utils/config.py reads these at import time. The old CODEY_7B_MMAP /
CODEY_7B_MLOCK names stay as deprecated fallbacks; the new name wins when
both are set. Each case runs in a fresh subprocess so no module reload
leaks into other tests.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_NAMES = ("CODEY_PRIMARY_MMAP", "CODEY_PRIMARY_MLOCK", "CODEY_7B_MMAP", "CODEY_7B_MLOCK")


def _flags(**env):
    child = {k: v for k, v in os.environ.items() if k not in _NAMES}
    child.update(env)
    out = subprocess.run(
        [sys.executable, "-c",
         "import json, utils.config as c; print(json.dumps([c.QWEN_MMAP, c.QWEN_MLOCK]))"],
        cwd=ROOT, env=child, capture_output=True, text=True, timeout=60, check=True,
    )
    return tuple(json.loads(out.stdout.strip().splitlines()[-1]))


def test_defaults_mmap_on_mlock_off():
    assert _flags() == (True, False)


def test_new_names_are_honoured():
    assert _flags(CODEY_PRIMARY_MMAP="0", CODEY_PRIMARY_MLOCK="1") == (False, True)


@pytest.mark.parametrize("env,expected", [
    ({"CODEY_7B_MMAP": "0"}, (False, False)),
    ({"CODEY_7B_MLOCK": "1"}, (True, True)),
])
def test_deprecated_names_still_work_as_fallback(env, expected):
    assert _flags(**env) == expected


def test_new_name_wins_over_deprecated_name():
    assert _flags(CODEY_PRIMARY_MMAP="1", CODEY_7B_MMAP="0",
                  CODEY_PRIMARY_MLOCK="0", CODEY_7B_MLOCK="1") == (True, False)
    assert _flags(CODEY_PRIMARY_MMAP="0", CODEY_7B_MMAP="1",
                  CODEY_PRIMARY_MLOCK="1", CODEY_7B_MLOCK="0") == (False, True)


def test_dead_planner_daemon_config_removed():
    import utils.config as cfg
    for name in ("PLANND_PID_FILE", "PLANND_LOG_FILE", "PLANND_SERVER_PORT"):
        assert not hasattr(cfg, name)
