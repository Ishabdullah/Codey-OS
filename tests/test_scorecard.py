"""Tests for bench/scorecard.py (WP1.4).

Three required checks:
  (a) the fixture's score is a specific, hand-derived number (not the real
      repo's score -- CLAUDE.md rule 5: verification means real, verbatim
      output, not a paraphrase, and the real repo's number will keep
      changing as the repo changes).
  (b) running the scorer twice against the same fixture via two separate
      subprocess invocations produces byte-identical JSON output
      (determinism).
  (c) a manual-sidecar entry missing its `citation` field makes the
      scorer hard-error (non-zero exit), never silently default.

None of this invokes pytest from inside bench/scorecard.py itself (that
would violate the module's own HARD CONSTRAINT docstring) -- the
subprocess calls below live here, in the test file, exactly as
bench/scorecard.py's docstring says they must.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "scorecard_fixture"
FIXTURE_MANUAL = FIXTURE_ROOT / "bench" / "scorecard_manual.json"


def _run_scorecard(repo_root: Path, manual_file: Path = None, extra_args=None):
    args = [
        sys.executable, "-m", "bench.scorecard",
        "--repo-root", str(repo_root),
        "--no-history",
    ]
    if manual_file is not None:
        args += ["--manual-file", str(manual_file)]
    if extra_args:
        args += extra_args
    return subprocess.run(
        args, cwd=str(REPO_ROOT), capture_output=True, text=True,
    )


def _fixture_json() -> dict:
    proc = _run_scorecard(FIXTURE_ROOT)
    assert proc.returncode == 0, proc.stderr
    # stdout is: JSON blob, blank line, rendered markdown. The JSON blob is
    # everything up to the first blank line.
    json_text = proc.stdout.split("\n\n", 1)[0]
    return json.loads(json_text)


# ── (a) fixture score is a specific, hand-derived number ──────────────────


def test_fixture_score_matches_hand_derived_value():
    """
    Hand-derived from the fixture's known structure, applying the same
    rubric logic bench/scorecard.py implements:

      1a = 6.0   (core/preferences.py, core/learning.py,
                  prompts/layered_prompt.py all imported by main.py ->
                  all reachable)
      1b = 5.0   (core/trajectory.py has _bounded/_budgeted, and both
                  instrument_* functions call _budgeted)
      1c = 4.0 * (1/3) = 1.333
                 (memory_v2: imported AND called -> hit;
                  context: imported but never called -> miss;
                  embeddings: not imported at all -> miss)
      2a = 2.0   (ccos/core/skill_recombiner.py exists, not reachable
                  from main.py -> partial credit)
      2b = 0.0   (no caller of verified_teacher_traces at all)
      3a = 3.0   (ccos/core/goal_engine.py exists, not reachable ->
                  partial credit)
      4a = 6.0   (bench/suite.lock exists; bench/runner.py imports AND
                  calls verify_lock)
      4b = 0.0   (tests/test_trajectory.py not present in the fixture)
      4c = 0.0   (bench/gate.py not present)
      4d = 0.0   (bench/power_analysis.md not present)
      5a = 0.0   (core/model_registry.py / core/lora_import.py absent)
      5b = 0.0   (ccos/core/capability_optimizer.py absent)
      6a = 3.0   (mirrors 1b)
      6b = 0.0   (mirrors 2a's reachability: skill_recombiner unreachable)
      6c = 3.0 * (1/3) = 1.0   (mirrors 1c's call-site result)
      6d = 0.0   (no "corpus" path anywhere in the fixture)
      6e = 1.5   (MANUAL, fixture's own scorecard_manual.json)
      6f = 2.0   (ccos/core/capability_registry.py exists AND is
                  reachable -- main.py imports it directly)
      7a = 3.0 * (1/5) = 0.6
                 (5 ccos/core/*.py files total: capability_registry,
                  skill_recombiner, goal_engine, tool_router,
                  agent_orchestrator; only capability_registry has an
                  importer outside ccos/, namely main.py)
      7b = 0.0   (no ActionGateway class anywhere)
      7c = 1.0   (ccos/core/agent_orchestrator.py calls
                  validate_tool_safety, but agent_orchestrator.py itself
                  is not reachable from main.py -> the "caller exists but
                  isn't reachable" partial-credit branch)
      7d = 2.0   (MANUAL, fixture's own scorecard_manual.json)

    automated_subtotal = 6.0+5.0+1.333 +2.0+0.0 +3.0 +6.0+0.0+0.0+0.0
                          +0.0+0.0 +3.0+0.0+1.0+0.0 +2.0 +0.6+0.0+1.0
                        = 30.933
    manual_subtotal    = 1.5 + 2.0 = 3.5
    total_score         = 34.433
    """
    result = _fixture_json()

    assert result["total_scanned_files"] == 15
    assert result["reachable_file_count"] == 7
    assert result["entry_points"] == ["main.py"]
    assert result["parse_errors"] == []

    assert result["automated_subtotal"] == 30.933
    assert result["manual_subtotal"] == 3.5
    assert result["total_score"] == 34.433

    cat1 = result["categories"]["1_experience_to_behavior"]
    assert cat1["points"] == 12.333
    items_1 = {i["label"]: i["points"] for i in cat1["items"]}
    assert items_1["1a preferences write/read path reachable via core/learning.py bridge"] == 6.0
    assert items_1["1b trajectory full-fidelity recording (not truncate-at-record)"] == 5.0
    [c1_points] = [
        v for k, v in items_1.items() if k.startswith("1c ")
    ]
    assert c1_points == 1.333

    cat6 = result["categories"]["6_brain_swap_independence"]
    assert cat6["points"] == 7.5
    items_6 = {i["label"]: i["points"] for i in cat6["items"]}
    [c6_points] = [v for k, v in items_6.items() if k.startswith("6c ")]
    assert c6_points == 1.0

    cat7 = result["categories"]["7_safety_honesty"]
    assert cat7["points"] == 3.6


def test_fixture_1c_6c_call_site_detail_distinguishes_all_three_cases():
    """The call-site detail string must name the exact evidence found (or
    the exact reason a module was not counted) for each of the fixture's
    three deliberately distinct cases -- called, imported-but-not-called,
    and never-imported -- not just a bare True/False."""
    result = _fixture_json()
    cat1 = result["categories"]["1_experience_to_behavior"]
    [detail] = [
        i["detail"] for i in cat1["items"] if i["label"].startswith("1c ")
    ]
    assert "calls _remember(...)" in detail  # memory_v2: genuinely called
    assert "never called" in detail  # context: imported but not called
    assert "not imported" in detail  # embeddings: never imported at all


# ── (b) determinism across two separate subprocess invocations ────────────


def test_scorer_output_is_byte_identical_across_two_runs():
    proc1 = _run_scorecard(FIXTURE_ROOT)
    proc2 = _run_scorecard(FIXTURE_ROOT)
    assert proc1.returncode == 0
    assert proc2.returncode == 0
    assert proc1.stdout == proc2.stdout


# ── (c) a manual entry missing `citation` hard-errors ──────────────────────


def test_manual_entry_missing_citation_is_a_hard_error(tmp_path):
    manual_data = json.loads(FIXTURE_MANUAL.read_text(encoding="utf-8"))
    del manual_data[0]["citation"]
    broken_manual = tmp_path / "scorecard_manual_broken.json"
    broken_manual.write_text(json.dumps(manual_data), encoding="utf-8")

    # Note: this test only ever READS FIXTURE_MANUAL (to build `broken_manual`
    # in tmp_path) -- the fixture's own bench/scorecard_manual.json, and the
    # real bench/scorecard_manual.json, are never written to.
    proc = _run_scorecard(FIXTURE_ROOT, manual_file=broken_manual)
    assert proc.returncode != 0
    assert "FATAL" in proc.stderr
    assert "citation" in proc.stderr
