"""Root pytest config hook: strip proxy env vars before test collection.

WP1.1 (CODEY_OS_MASTER_BLUEPRINT.md §20.2/§21). A prior live-verification
session discovered that this device's own ambient HTTP_PROXY/HTTPS_PROXY
breaks loopback HTTP calls made by unhardened urllib/requests clients
(core/resource_gate.py's /slots polling, among others), producing test
failures that look like real regressions but are a dev-environment
artifact (NEW-756; PROJECT_LOG.md 2026-10-06). Clearing the full variant
set here, at collection time via conftest's module-level execution (which
runs before any test module import can cache a proxy-aware client), means
that artifact can't recur on this device or a CI runner that happens to
have a proxy configured.

All four casings matter: some libraries only honor the lowercase form,
others only the uppercase. NO_PROXY/no_proxy are cleared too so this
file's behavior doesn't depend on whichever form happened to be set.
"""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

for _var in (
    "HTTP_PROXY", "http_proxy",
    "HTTPS_PROXY", "https_proxy",
    "ALL_PROXY", "all_proxy",
    "NO_PROXY", "no_proxy",
):
    os.environ.pop(_var, None)

# WP2.1 group 3 (NEW-855, closes NEW-425/NEW-812 as a consequence of the same
# mechanism). core/memory_v2.py's module-level `get_memory()` call (and
# core/state.py, core/checkpoint.py, core/model_registry.py,
# core/symbolic_graph.py's own import-time schema-init code) compute their DB
# paths from utils/config.py's CODEY_STATE_DIR at IMPORT time — before any
# pytest fixture can run. Confirmed live: `pytest --collect-only` alone, with
# zero tests executed, already created a real on-disk ~/.codeyOS/state.db.
# Setting this env var here, at collection time via conftest's module-level
# execution (same technique as the NEW-756 block above, which runs before any
# test module import), redirects every one of those modules' import-time
# state store for the whole session without editing any of them.
# Only set when genuinely unset/empty (not os.environ.setdefault(), which
# would NOT override an already-exported CODEY_STATE_DIR="" -- an empty
# string is falsy, so utils/config.py's `os.environ.get("CODEY_STATE_DIR")`
# check would then fall through to the real ~/.codeyOS, exactly the
# pollution this block exists to prevent). A caller who explicitly sets a
# non-empty CODEY_STATE_DIR themselves (e.g. a live-verification session)
# is still left alone.
#
# The temp dir is removed at interpreter exit (code-reviewer W1 -- without
# this, every pytest session leaks one codeyos-test-state-* directory).
if not os.environ.get("CODEY_STATE_DIR"):
    _codey_test_state_dir = tempfile.mkdtemp(prefix="codeyos-test-state-")
    os.environ["CODEY_STATE_DIR"] = _codey_test_state_dir
    atexit.register(shutil.rmtree, _codey_test_state_dir, ignore_errors=True)

# WP2.1 group 4 (NEW-910/911/912). core/action_gateway.py's audit_path()
# falls back to CODEY_STATE_DIR when CODEY_ACTION_GATEWAY_AUDIT isn't set,
# so the block above already redirects it in the common case -- but a
# developer who explicitly exports a real CODEY_STATE_DIR (e.g. a live-
# verification session) while also running the test suite would otherwise
# have ccos/core/plugin_manager.py's new call_capability() gating append
# real rows to the real on-device ~/.codeyOS/action_gateway_audit.jsonl.
# Setting this explicitly, independent of CODEY_STATE_DIR, closes that
# gap the same way core/trajectory.py's db_path() env-override pattern is
# already mirrored by action_gateway.py itself. Same only-when-unset
# rationale as the CODEY_STATE_DIR block above (os.environ.setdefault()
# would not override an already-exported empty string).
if not os.environ.get("CODEY_ACTION_GATEWAY_AUDIT"):
    _codey_test_audit_dir = tempfile.mkdtemp(prefix="codeyos-test-audit-")
    os.environ["CODEY_ACTION_GATEWAY_AUDIT"] = str(
        Path(_codey_test_audit_dir) / "action_gateway_audit.jsonl"
    )
    atexit.register(shutil.rmtree, _codey_test_audit_dir, ignore_errors=True)

# WP2.2 S0. (Since S3 there is no DEFAULT_DB_PATH: a bare DatabaseManager()
# resolves $RESTORICON_DB_PATH or raises.) CODEY_STATE_DIR does not cover the
# Restoricon DB (NEW-907), so any test that relies on the env path (a bare
# DatabaseManager(), RestoriconAPIServer() with no db_path, provision() with
# no db_path) must find it redirected to a temp file, never the LIVE
# ~/.codeyOS/restoricon.db. Redirect it to a per-session temp
# file here, at collection time. Same only-when-unset/empty rationale as the
# blocks above (no os.environ.setdefault(): an exported empty string would
# be kept by setdefault and then be falsy at the consumer). A caller who
# explicitly exports a non-empty RESTORICON_DB_PATH is left alone;
# tests/test_wp22_s0_test_isolation.py fails if that value is the live DB.
if not os.environ.get("RESTORICON_DB_PATH"):
    _codey_test_restoricon_dir = tempfile.mkdtemp(prefix="codeyos-test-restoricon-")
    os.environ["RESTORICON_DB_PATH"] = str(
        Path(_codey_test_restoricon_dir) / "restoricon.db"
    )
    atexit.register(shutil.rmtree, _codey_test_restoricon_dir, ignore_errors=True)

# WP2.3 S2 (NEW-1105). ccos/core/capability_registry.py's
# get_capability_registry() singleton (and PluginManager()'s fallback to it)
# persists to the LIVE, gitignored ccos/data/capabilities.json on every
# register()/record_use(). Three tests write to it (tests/test_context_passing.py,
# ccos/tests/test_multi_domain.py, tests/test_agent_capability.py); the leak
# recurred on 2026-10-24 even after the dd49c1d isolation work, leaving
# test.* / crm.customer_query rows in the live file. CapabilityRegistry now
# honors CODEY_CAPABILITY_REGISTRY, set here at collection time to a
# per-session temp file. Same only-when-unset/empty rationale as the blocks
# above (os.environ.setdefault() would keep an exported empty string). A
# caller who exports a non-empty path is left alone.
if not os.environ.get("CODEY_CAPABILITY_REGISTRY"):
    _codey_test_registry_dir = tempfile.mkdtemp(prefix="codeyos-test-registry-")
    os.environ["CODEY_CAPABILITY_REGISTRY"] = str(
        Path(_codey_test_registry_dir) / "capabilities.json"
    )
    atexit.register(shutil.rmtree, _codey_test_registry_dir, ignore_errors=True)


import pytest  # noqa: E402  (after the collection-time env blocks above)


@pytest.fixture(autouse=True)
def _reset_capability_registry_singleton(monkeypatch):
    """Give every test a fresh get_capability_registry() singleton.

    The singleton caches its store path and in-memory rows at first use, so
    without a per-test reset one test's registrations (and any cached
    instance built before the env override) would leak into the next.
    monkeypatch restores the previous value afterward. Only resets the
    singleton if the module is already imported, so it adds no import cost
    to tests that never touch CCOS.
    """
    import sys

    mod = sys.modules.get("ccos.core.capability_registry")
    if mod is not None:
        monkeypatch.setattr(mod, "_registry", None)
    yield
    mod = sys.modules.get("ccos.core.capability_registry")
    if mod is not None:
        mod._registry = None
