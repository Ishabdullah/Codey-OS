"""WP2.3 S2 (NEW-1105): the test suite must never write the live capability registry.

The live file is ccos/data/capabilities.json (gitignored runtime state).
Three known writers register fixtures through the process-wide
get_capability_registry() singleton: tests/test_context_passing.py
(create_test_plugin_manager), ccos/tests/test_multi_domain.py (the
test_orchestrator_multi_domain_deliberation_and_execution body) and
tests/test_agent_capability.py (real "agent" plugin load). The guard tests
re-run each writer in a subprocess pytest session with the repo's root
conftest active and compare the md5 of the live file before and after.
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ccos.core.capability_registry import (
    Capability,
    CapabilityRegistry,
    get_capability_registry,
)
from ccos.core.plugin_manager import PluginManager

REPO = Path(__file__).resolve().parent.parent
LIVE = REPO / "ccos" / "data" / "capabilities.json"


def _md5(p: Path):
    return hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else None


_PREV_TEST_SINGLETON = []  # strong ref so the previous instance cannot be GC'd and its id reused


def test_singleton_uses_temp_path_not_live():
    reg = get_capability_registry()
    assert Path(reg._store_path).resolve() != LIVE.resolve()
    assert reg._store_path == os.environ["CODEY_CAPABILITY_REGISTRY"]
    _PREV_TEST_SINGLETON[:] = [reg]


def test_singleton_is_reset_between_tests():
    """The autouse fixture in the root conftest.py hands each test a fresh
    instance; the one the previous test used must not be reused."""
    reg = get_capability_registry()
    assert reg is get_capability_registry()  # still a singleton within a test
    if _PREV_TEST_SINGLETON:  # empty if run in isolation / reordered
        assert reg is not _PREV_TEST_SINGLETON[0]


def test_env_override_honored_and_explicit_path_wins(tmp_path, monkeypatch):
    env_path = tmp_path / "env.json"
    monkeypatch.setenv("CODEY_CAPABILITY_REGISTRY", str(env_path))
    assert CapabilityRegistry()._store_path == str(env_path)
    explicit = tmp_path / "explicit.json"
    assert CapabilityRegistry(store_path=str(explicit))._store_path == str(explicit)
    monkeypatch.delenv("CODEY_CAPABILITY_REGISTRY")
    assert CapabilityRegistry()._store_path == str(LIVE)


@pytest.mark.skipif(not LIVE.exists(), reason="no live capabilities.json on this checkout")
def test_plugin_manager_register_leaves_live_file_untouched():
    before = _md5(LIVE)
    pm = PluginManager(plugin_dirs=[])
    pm._registry.register(
        Capability(name="wp23.isolation_probe", description="x", implementation="builtin")
    )
    assert pm._registry.has("wp23.isolation_probe")
    assert _md5(LIVE) == before


_WRITERS = [
    "tests/test_context_passing.py",
    "ccos/tests/test_multi_domain.py::test_orchestrator_multi_domain_deliberation_and_execution",
    "tests/test_agent_capability.py",
]


@pytest.mark.skipif(not LIVE.exists(), reason="no live capabilities.json on this checkout")
@pytest.mark.skipif(
    os.environ.get("WP23_REGISTRY_GUARD_CHILD") == "1", reason="no recursion"
)
@pytest.mark.parametrize("node", _WRITERS)
def test_known_writers_leave_live_registry_byte_identical(node):
    """Run each known writer in a child pytest (root conftest active) and
    prove the live registry's md5 is unchanged. The child result itself is
    not asserted: NEW-805 can fail test_multi_domain for unrelated reasons.
    """
    env = dict(os.environ)
    env.pop("CODEY_CAPABILITY_REGISTRY", None)  # force conftest to set it
    env["WP23_REGISTRY_GUARD_CHILD"] = "1"
    before = _md5(LIVE)
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", node],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=300,
    )
    assert _md5(LIVE) == before
