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
import os

for _var in (
    "HTTP_PROXY", "http_proxy",
    "HTTPS_PROXY", "https_proxy",
    "ALL_PROXY", "all_proxy",
    "NO_PROXY", "no_proxy",
):
    os.environ.pop(_var, None)
