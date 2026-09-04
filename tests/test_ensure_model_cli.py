"""
NEW-358 follow-up (Site 3) — tools/ensure_model_cli.py, the delegated
model-load entry point Codey-Aigentik's index.js:221 execSync()'s
(replacing the old inline `python3 -c "..."` one-liner). Asserts
`record_run_start(emitter="aigentik", repo="Codey-Aigentik", ...)` is
called strictly before `get_loader().ensure_model('primary')`, and that
a telemetry failure never prevents `ensure_model()` from still running
(telemetry is best-effort, never load-bearing — CLAUDE.md's exception-
handling rule).

No real model load, no real subprocess (CLAUDE.md rule 2 RAM discipline)
— `get_loader()` and `telemetry.recorders.record_run_start` are both
faked/patched.
"""
from unittest.mock import MagicMock, patch

from tools.ensure_model_cli import main as ensure_model_cli_main


def test_records_run_start_before_ensure_model():
    calls = []

    fake_loader = MagicMock()
    fake_loader.ensure_model.side_effect = lambda *a, **k: calls.append(
        ("ensure_model", a, k)
    )

    def _fake_record_run_start(**kwargs):
        calls.append(("record_run_start", (), kwargs))

    with patch(
        "telemetry.recorders.record_run_start", side_effect=_fake_record_run_start
    ), patch("core.loader_v2.get_loader", return_value=fake_loader):
        ensure_model_cli_main()

    order = [c[0] for c in calls]
    assert order == ["record_run_start", "ensure_model"]

    record_kwargs = calls[0][2]
    assert record_kwargs["emitter"] == "aigentik"
    assert record_kwargs["repo"] == "Codey-Aigentik"

    ensure_model_args = calls[1][1]
    assert ensure_model_args == ("primary",)


def test_record_run_start_failure_does_not_block_ensure_model():
    fake_loader = MagicMock()

    with patch(
        "telemetry.recorders.record_run_start", side_effect=RuntimeError("boom")
    ), patch("core.loader_v2.get_loader", return_value=fake_loader):
        ensure_model_cli_main()

    fake_loader.ensure_model.assert_called_once_with("primary")
