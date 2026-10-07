#!/usr/bin/env python3
"""WP0.6 (CODEY_OS_MASTER_BLUEPRINT.md §21, census §15.4): quarantine
ccos/data/ccos_memory.db's cap_metrics table and ccos/data/reflections.jsonl
-- both accumulated rows with no reachable production writer (confirmed:
every class that writes to them, AgentOrchestrator/AutoImprovementLoop/
GoalEngine/CapabilityOptimizer/LifecycleManager/SkillRecombiner, has no
constructor path that was ever actually invoked by a real entry point as
of the 2026-10-06 census) yet kept growing anyway, from CCOS test runs
writing into the real singleton with no test isolation (the root cause,
fixed separately in this same round -- see ccos/tests/conftest.py and
tests/conftest.py).

Moves aside, never deletes (per this work package's own intent -- "do not
delete until the §17 gate design confirms they're unwanted"):
- cap_metrics -> renamed in place to cap_metrics_quarantined_<date>; a
  fresh empty cap_metrics table is created automatically the next time
  PerformanceTracker() runs (_init_tables() uses CREATE TABLE IF NOT
  EXISTS).
- reflections.jsonl -> moved to reflections.jsonl.quarantined-<date>; a
  fresh ReflectionEngine simply starts with an empty in-memory list
  (_load() already tolerates a missing file).

Idempotent: running twice on an already-quarantined state is a no-op,
not an error.
"""
import datetime
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

CCOS_DATA_DIR = Path(__file__).parent.parent / "ccos" / "data"
DB_PATH = CCOS_DATA_DIR / "ccos_memory.db"
REFLECTIONS_PATH = CCOS_DATA_DIR / "reflections.jsonl"


def quarantine_cap_metrics(date_tag: str) -> str:
    quarantined_name = f"cap_metrics_quarantined_{date_tag.replace('-', '')}"
    con = sqlite3.connect(str(DB_PATH))
    try:
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "cap_metrics" not in tables:
            return "cap_metrics: already quarantined or never existed, nothing to do"
        if quarantined_name in tables:
            return f"{quarantined_name}: already exists, refusing to overwrite -- nothing to do"
        row_count = con.execute("SELECT COUNT(*) FROM cap_metrics").fetchone()[0]
        con.execute(f"ALTER TABLE cap_metrics RENAME TO {quarantined_name}")
        con.commit()
        return f"cap_metrics: renamed to {quarantined_name} ({row_count} rows quarantined, not deleted)"
    finally:
        con.close()


def quarantine_reflections(date_tag: str) -> str:
    if not REFLECTIONS_PATH.exists():
        return "reflections.jsonl: already quarantined or never existed, nothing to do"
    dest = REFLECTIONS_PATH.with_name(f"reflections.jsonl.quarantined-{date_tag}")
    if dest.exists():
        return f"{dest.name}: already exists, refusing to overwrite -- nothing to do"
    line_count = len(REFLECTIONS_PATH.read_text().strip().splitlines())
    shutil.move(str(REFLECTIONS_PATH), str(dest))
    return f"reflections.jsonl: moved to {dest.name} ({line_count} lines quarantined, not deleted)"


def main() -> int:
    date_tag = datetime.date.today().isoformat()
    print(quarantine_cap_metrics(date_tag))
    print(quarantine_reflections(date_tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
