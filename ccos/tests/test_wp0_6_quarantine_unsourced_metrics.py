"""
WP0.6 (CODEY_OS_MASTER_BLUEPRINT.md §21, census §15.4): cap_metrics
(ccos/data/ccos_memory.db) and reflections.jsonl (ccos/data/) had
accumulated rows with no reachable production writer, yet kept growing
from CCOS test runs writing into the real process-wide singletons with
no test isolation. This covers both halves of the fix:

1. A fresh PerformanceTracker()/ReflectionEngine() against an isolated
   store starts with zero rows/reflections -- no unsourced data is
   readable by any gate-adjacent consumer (CapabilityOptimizer,
   AutoImprovementLoop, GoalEngine, etc., all of which read through
   these two singletons with no other filter of their own).
2. The isolation fixture in this directory's conftest.py (and the
   top-level tests/conftest.py) actually prevents the real on-device
   files from being written to during a test run -- this is the
   regression test for the root cause, not just the quarantine's
   immediate effect.
"""
from ccos.core.performance_tracker import PerformanceTracker
from ccos.core.reflection_engine import ReflectionEngine
from ccos.core.agent_orchestrator import AgentOrchestrator


def test_fresh_performance_tracker_has_no_unsourced_rows(tmp_path):
    db_path = tmp_path / "ccos_memory.db"
    pt = PerformanceTracker(db_path=str(db_path))
    assert pt._conn.execute("SELECT COUNT(*) FROM cap_metrics").fetchone()[0] == 0
    assert pt.get_capability_metrics("anything")["total_uses"] == 0


def test_fresh_reflection_engine_has_no_unsourced_reflections(tmp_path):
    log_path = tmp_path / "reflections.jsonl"
    engine = ReflectionEngine(log_path=str(log_path))
    assert engine.get_recent() == []


def test_default_constructed_classes_never_touch_the_real_device_files():
    """The actual regression test: constructing these with NO explicit
    override (the exact shape every CCOS test in this repo uses) must
    route through the isolated singleton this conftest.py sets up, not
    the real ccos/data/ files -- reproduces, in miniature, the exact
    scenario that let cap_metrics grow from 454 (the census count) to
    467 purely from test runs before this fix."""
    import ccos.core.performance_tracker as pt_mod
    import ccos.core.reflection_engine as refl_mod
    from pathlib import Path

    real_db_path = Path(__file__).resolve().parent.parent / "data" / "ccos_memory.db"
    real_reflections_path = Path(__file__).resolve().parent.parent / "data" / "reflections.jsonl"

    # Confirm this test file's own isolation fixture (autouse, from
    # conftest.py) already redirected these -- not the real paths.
    assert pt_mod.DB_PATH != str(real_db_path)
    assert refl_mod.REFLECTIONS_PATH != str(real_reflections_path)

    real_db_before = real_db_path.read_bytes() if real_db_path.exists() else None
    real_reflections_exists_before = real_reflections_path.exists()

    orchestrator = AgentOrchestrator()
    assert orchestrator is not None  # construction alone must not raise
    # Touch the capability-metrics read path a real orchestrator call would use.
    pt_mod.get_performance_tracker().get_capability_metrics("system.info")
    refl_mod.get_reflection_engine().get_recent()

    real_db_after = real_db_path.read_bytes() if real_db_path.exists() else None
    assert real_db_after == real_db_before
    assert real_reflections_path.exists() == real_reflections_exists_before
