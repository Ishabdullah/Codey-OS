---
name: telemetry-t9-loader-argv-provenance-scope-gap
description: T9 loader_v2.py argv provenance — CHANGES REQUESTED (doc/disclosure only); implementer's "confirmed absent" docstring claim didn't cover main.py's --init/--tdd/--fix flags
metadata:
  type: project
---

Round T9 (last sub-task of the telemetry rollout), `core/loader_v2.py`
`_emit_argv_provenance()` + `_emit_gate_telemetry()`, `telemetry/recorders.py`
`record_run_start_amended()` extension, `telemetry/cli.py` `_print_run()`
merge-all-amendments fix. The mechanism itself (SIGINT-masked-window
addition, meminfo double-read, unconditional gate telemetry, amendment
merge/null-clearing, emitter enum) was all independently verified sound —
see the diff review for the full trace. Both test suites matched the
implementer's claim exactly: `pytest tests/` 1420 passed/1 skipped,
`pytest` (repo root) 1527 passed/1 skipped.

**What blocked approval:** `_emit_argv_provenance()`'s docstring claimed
the orphaned-`run_start_amended` risk (a process reaching
`load_primary()` without ever having called `record_run_start()` first,
so `store.get_run_id()` lazily mints a run_id with no matching
`run_start`) was "confirmed NOT to happen for the daemon or
interactive-TUI-repl paths," and flagged only `core/lora_import.py`'s
LoRA-swap callers as unverified. Hand-tracing `main.py`'s `main()`
(lines 1848-2076) showed the claim was **narrower than it reads**:
`--init` (line 1928), `--tdd` (line 1947), and `--fix` (line 1979) all
call `_load_primary_with_gate_recovery()` → `loader.load_primary()` and
then `return` — all three exit *before* line 2061's
`_record_tui_telemetry_run_start()`, which only runs on the default
repl path. `_load_primary_with_gate_recovery()` itself (lines 153-240)
contains no `record_run_start()` call either. So the same orphan-record
mechanism the implementer disclosed only for `lora_import.py` also fires
on every `codeyOS --init`/`--tdd`/`--fix` invocation — a materially
larger, undisclosed blast radius than "confirmed NOT to happen for ...
main.py" implies.

Runtime severity is low (best-effort telemetry, `except Exception`-wrapped,
`codey-metrics doctor`'s existing orphan-detection already covers this
exact record shape, no crash/RAM/process-lifecycle impact) — this is a
doc-accuracy/disclosure gap (rule 6: correct the record when a claim
doesn't hold up), not a functional regression. Required fix: correct the
docstring's scope claim + log a `NEW_ISSUES.md` Confirmed entry expanding
the residual to cover `main.py`'s three one-shot flags, not just
`lora_import.py`.

**Pattern reinforced (see also
[[t8a_daemon_dedup_docstring_overclaim]],
[[new345_thread_identity_run_stats_changes_requested]],
[[new206_q11_context_budget_reservation_lifetime_double_count]]):** when
a docstring says "confirmed absent for X, Y" and names specific call
sites, don't take the enumerated list as complete — re-derive the full
call-site set yourself (grep every caller of the reachable function, not
just the two the docstring names) before accepting a "verified elsewhere"
claim. Here the docstring's phrasing ("interactive-TUI-repl paths") was a
narrower true statement standing in for a broader false implication
("main.py is covered") — the words were literally accurate and still
misleading. Worth explicitly re-deriving call-site sets rather than
trusting a docstring's own scoping language, every time a "verified/
confirmed absent" claim appears.

Separate, non-blocking observation logged for NEW_ISSUES (not required
to fix here): the new `_emit_gate_telemetry()` call in
`ModelLoader.load_primary()` sits between `reserve_slot()` (which
registers a PENDING slot) and the pre-existing reserve→spawn→confirm
`try/finally` leak-guard (see
[[resource_gate_subtask2_confirm_mark_slot_leak]]) — a KeyboardInterrupt/
SystemExit during its lazy imports/JSONL append would escape the
`except Exception` and leak that slot, since the leak-guard doesn't start
until a few lines later. Same shape as the bug that memory file already
documents, just widened slightly to include file I/O. Not blocking:
`except BaseException` would be the wrong fix (this project has
explicitly rejected swallowing KeyboardInterrupt, NEW-5/6), and the
emission can't move inside the later `try` since the denial branch
returns before reaching it.
