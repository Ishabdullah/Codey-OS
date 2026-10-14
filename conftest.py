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
