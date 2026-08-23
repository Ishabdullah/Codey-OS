"""
U.31 (TODO.md) — CODEY_N_CTX env-var override for MODEL_CONFIG["n_ctx"].

utils/config.py's MODEL_CONFIG["n_ctx"] is the single source of truth read
by BOTH core/loader_v2.py (the real llama-server -c flag it spawns with)
and resource_gate.ModelSpec's cost estimate (core/loader_v2.py — formerly
also core/planner_loader.py, deleted in M1-D, 2026-08-23). Overriding it
only in the gate (mirroring core/resource_gate.py's CODEY_TEST_PRIMARY_ARCH
pattern) would desync the gate's admission math from what actually spawns
— the NEW-84 class of bug. Instead the override lives here, at the shared
source, exactly like MODEL_PATH/PLANNER_MODEL_PATH already do via
os.environ.get(...) at import time.

Because utils/config.py reads its env var at import time, these tests
reload the module under a patched environment and restore the unpatched
module afterward so other tests in the same process see the real default.
"""
import importlib
import os

import pytest

import utils.config as cfg


@pytest.fixture(autouse=True)
def restore_config_module():
    """Ensure utils.config is left in its default (env-unset) state for any
    other test that imports it later in the same process."""
    yield
    os.environ.pop("CODEY_N_CTX", None)
    importlib.reload(cfg)


def test_n_ctx_default_unset_is_65536():
    os.environ.pop("CODEY_N_CTX", None)
    reloaded = importlib.reload(cfg)
    assert reloaded.MODEL_CONFIG["n_ctx"] == 65536
    assert isinstance(reloaded.MODEL_CONFIG["n_ctx"], int)


def test_n_ctx_override_valid_integer_is_used():
    os.environ["CODEY_N_CTX"] = "4096"
    try:
        reloaded = importlib.reload(cfg)
        assert reloaded.MODEL_CONFIG["n_ctx"] == 4096
        assert isinstance(reloaded.MODEL_CONFIG["n_ctx"], int)
    finally:
        os.environ.pop("CODEY_N_CTX", None)


def test_n_ctx_override_invalid_value_fails_loudly():
    os.environ["CODEY_N_CTX"] = "not-a-number"
    try:
        with pytest.raises(ValueError, match="CODEY_N_CTX"):
            importlib.reload(cfg)
    finally:
        os.environ.pop("CODEY_N_CTX", None)
        # The failed reload may have left utils.config partially executed;
        # reload again now that the bad env var is cleared to restore a
        # known-good module state before the autouse fixture's own reload.
        importlib.reload(cfg)


def test_n_ctx_override_non_positive_value_fails_loudly():
    """int() alone would silently accept 0 or negative values, which would
    flow into resource_gate's KV-cache cost estimate as a zero/negative
    term — the gate would under-estimate load cost and over-admit,
    exactly the admission-math-vs-reality mismatch this override exists
    to avoid. 0/-1 are syntactically valid ints but invalid n_ctx values,
    so they must be rejected just as loudly as non-numeric garbage."""
    for bad_value in ("0", "-1"):
        os.environ["CODEY_N_CTX"] = bad_value
        try:
            with pytest.raises(ValueError, match="CODEY_N_CTX"):
                importlib.reload(cfg)
        finally:
            os.environ.pop("CODEY_N_CTX", None)
            importlib.reload(cfg)
