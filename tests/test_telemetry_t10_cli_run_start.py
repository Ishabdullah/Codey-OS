"""
T10 commit 3 / NEW-358 Site 1 — main.py's four one-shot CLI flags
(--init / --tdd / --fix / --import-lora) must each emit a category-G
`run_start` under emitter="codey-os.cli" BEFORE the branch does any
model-load work, so recorders.record_run_start()'s unconditional
store.mark_run_start_recorded() has already set the breadcrumb by the
time core/loader_v2.py's _ensure_run_start_fallback() reaches
store.claim_run_start() and no duplicate is emitted.

There is no pre-existing test for _record_tui_telemetry_run_start to
mirror — this is the first test for this call-site class.

Approach for the ordering cases: main.main() is driven end-to-end with a
minimal argv (monkeypatched sys.argv). The helper does a local
`from telemetry import recorders`, so the patch target is
`telemetry.recorders.record_run_start`, not a `main.`-scoped name. A
parent unittest.mock.Mock with attach_mock records the *relative order*
of record_run_start vs the branch's model-load sentinel:
  - --init / --tdd / --fix: the sentinel is
    main._load_primary_with_gate_recovery (the only thing in those
    branches that loads the primary model).
  - --import-lora: that branch never calls the loader directly; the
    model load happens inside import_lora_adapter -> swap_to_finetuned_model
    -> load_primary, so the sentinel is core.lora_import.import_lora_adapter.

Case 2 ("load_primary() would be hit 3x") is exercised by giving the
mocked import_lora_adapter a side effect that calls
core.loader_v2._ensure_run_start_fallback() three times — the fallback is
the only part of load_primary() that touches run_start, so this is the
faithful substitution for three real load_primary() calls.
"""

from __future__ import annotations

import json
import signal
import sys
from unittest.mock import Mock

import pytest

import main
from telemetry import envelope, schema, store
from utils import config


@pytest.fixture(autouse=True)
def _reset_telemetry_state(monkeypatch, tmp_path):
    envelope.reset_seq()
    store.reset_for_tests()
    monkeypatch.setattr(store, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(store, "METRICS_DIR", tmp_path)
    # The --fix branch mutates these two confirmation gates on the live
    # utils.config.AGENT_CONFIG dict directly (not via monkeypatch);
    # snapshot them here so monkeypatch restores them at teardown and the
    # off state never leaks into the rest of the suite.
    monkeypatch.setitem(config.AGENT_CONFIG, "confirm_write", config.AGENT_CONFIG.get("confirm_write"))
    monkeypatch.setitem(config.AGENT_CONFIG, "confirm_shell", config.AGENT_CONFIG.get("confirm_shell"))
    # main.main() installs its own SIGTERM handler on every call (NEW-10);
    # save and restore the process-wide disposition so these 8 invocations
    # don't leak it into the rest of the suite.
    _orig_sigterm = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, _orig_sigterm)
    store.reset_for_tests()


def _read_run_start_records(tmp_path):
    events_dir = tmp_path / "events"
    jsonl_files = list(events_dir.rglob("*.jsonl")) if events_dir.exists() else []
    records = []
    for f in jsonl_files:
        for line in f.read_text(encoding="utf-8").splitlines():
            records.append(json.loads(line))
    return [r for r in records if r["event_type"] == "run_start"]


# ── 1. Ordering: record_run_start fires before the model load, per flag ──


def _run_ordering_case(monkeypatch, argv, load_sentinel_target):
    """Drive main.main() with `argv` and assert record_run_start is called
    before the branch's model-load sentinel. Returns nothing; asserts."""
    monkeypatch.setattr(sys, "argv", argv)

    parent = Mock()
    mock_record = Mock()
    parent.attach_mock(mock_record, "record_run_start")
    monkeypatch.setattr("telemetry.recorders.record_run_start", mock_record)

    # Neutralise shutdown / teardown side effects.
    monkeypatch.setattr(main, "shutdown", Mock())

    if load_sentinel_target == "_load_primary_with_gate_recovery":
        mock_load = Mock(return_value=True)
        parent.attach_mock(mock_load, "load")
        monkeypatch.setattr(main, "_load_primary_with_gate_recovery", mock_load)
        monkeypatch.setattr(main, "_is_unrecovered_gate_denial", Mock(return_value=False))
        monkeypatch.setattr(main, "get_loader", Mock())
        monkeypatch.setattr(main, "run_init", Mock())
        monkeypatch.setattr("core.tdd.find_test_file", Mock(return_value="test_x.py"))
        monkeypatch.setattr("core.tdd.run_tdd_loop", Mock())
        monkeypatch.setattr("core.fixmode.fix_file", Mock())
    else:  # import_lora_adapter
        mock_load = Mock(return_value={"success": True, "model_path": "/x", "backup_path": None})
        parent.attach_mock(mock_load, "load")
        monkeypatch.setattr("core.lora_import.import_lora_adapter", mock_load)

    main.main()

    names = [c[0] for c in parent.mock_calls]
    assert "record_run_start" in names, names
    assert "load" in names, names
    assert names.index("record_run_start") < names.index("load"), names


def test_init_emits_run_start_before_model_load(monkeypatch):
    _run_ordering_case(monkeypatch, ["codeyOS", "--init"], "_load_primary_with_gate_recovery")


def test_tdd_emits_run_start_before_model_load(monkeypatch):
    _run_ordering_case(
        monkeypatch, ["codeyOS", "--tdd", "src.py"], "_load_primary_with_gate_recovery"
    )


def test_fix_emits_run_start_before_model_load(monkeypatch):
    _run_ordering_case(monkeypatch, ["codeyOS", "--fix", "src.py"], "_load_primary_with_gate_recovery")


def test_import_lora_emits_run_start_before_model_load(monkeypatch):
    _run_ordering_case(
        monkeypatch, ["codeyOS", "--import-lora", "/tmp/adapter"], "import_lora_adapter"
    )


# ── 2. --import-lora single-emit even if load_primary would be hit 3x ────


def test_import_lora_single_run_start_emission(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["codeyOS", "--import-lora", "/tmp/adapter"])
    monkeypatch.setattr(main, "shutdown", Mock())

    from core import loader_v2

    def fake_import(*_a, **_kw):
        # Simulate swap_to_finetuned_model hitting load_primary() 3x; the
        # run_start-relevant part of load_primary() is the fallback.
        for _ in range(3):
            loader_v2._ensure_run_start_fallback()
        return {"success": True, "model_path": "/x", "backup_path": None}

    monkeypatch.setattr("core.lora_import.import_lora_adapter", fake_import)

    main.main()
    store.reset_for_tests()  # flush the writer thread

    run_starts = _read_run_start_records(tmp_path)
    assert len(run_starts) == 1, run_starts
    assert run_starts[0]["emitter"] == "codey-os.cli"


# ── 3. Real claim semantics: main.py wins, loader fallback no-ops ────────


def test_init_real_claim_semantics_single_record(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["codeyOS", "--init"])
    monkeypatch.setattr(main, "shutdown", Mock())
    monkeypatch.setattr(main, "get_loader", Mock())
    monkeypatch.setattr(main, "_is_unrecovered_gate_denial", Mock(return_value=False))
    monkeypatch.setattr(main, "run_init", Mock())

    from core import loader_v2

    def fake_load(_loader):
        # A real load reaches _ensure_run_start_fallback(); it must find the
        # run_start already recorded by main.py's own call and no-op.
        loader_v2._ensure_run_start_fallback()
        return True

    monkeypatch.setattr(main, "_load_primary_with_gate_recovery", fake_load)

    main.main()
    store.reset_for_tests()  # flush

    run_starts = _read_run_start_records(tmp_path)
    assert len(run_starts) == 1, run_starts
    assert run_starts[0]["emitter"] == "codey-os.cli"

    # runs/<run_id>.json written exactly once too.
    run_files = list((tmp_path / "runs").glob("*.json")) if (tmp_path / "runs").exists() else []
    assert len(run_files) == 1, run_files


# ── 4. emitter="codey-os.cli" present in the emitted record ─────────────


def test_emitted_record_carries_cli_emitter(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["codeyOS", "--init"])
    monkeypatch.setattr(main, "shutdown", Mock())
    monkeypatch.setattr(main, "get_loader", Mock())
    monkeypatch.setattr(main, "_load_primary_with_gate_recovery", Mock(return_value=True))
    monkeypatch.setattr(main, "_is_unrecovered_gate_denial", Mock(return_value=False))
    monkeypatch.setattr(main, "run_init", Mock())

    main.main()
    store.reset_for_tests()

    run_starts = _read_run_start_records(tmp_path)
    assert len(run_starts) == 1, run_starts
    rec = run_starts[0]
    assert rec["emitter"] == "codey-os.cli"
    assert rec["body"]["emitter"] == "codey-os.cli"
    assert rec["category"] == "provenance"
    # First record ever emitted under the v2-only "codey-os.cli" enum
    # value, models= omitted -> validate() closes enum membership and the
    # honest-null invariant in one call.
    assert schema.validate(rec) == [], schema.validate(rec)


# ── 5. Negative: --finetune emits no run_start ─────────────────────────


def test_finetune_emits_no_run_start(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["codeyOS", "--finetune"])
    monkeypatch.setattr(main, "shutdown", Mock())
    mock_record = Mock()
    monkeypatch.setattr("telemetry.recorders.record_run_start", mock_record)
    mock_prep = Mock(return_value={})
    monkeypatch.setattr("core.finetune_prep.prepare_finetune_data", mock_prep)

    main.main()

    mock_prep.assert_called_once()  # guard against a vacuous pass
    mock_record.assert_not_called()
