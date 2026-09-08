---
name: new_issues_cleanup_batch4_telemetry_js_mirror_gap
description: NEW_ISSUES.md ledger closeout batch 4 (telemetry/metrics) — 6/7 findings approved, NEW-327 changes requested for missing JS-mirror update
metadata:
  type: project
---

Round: NEW_ISSUES.md ledger closeout batch 4 (telemetry/metrics),
2026-09-08, touching ccos/core/telemetry_engine.py, core/inference_hybrid.py,
core/loader_v2.py, core/plannd.py, telemetry/cli.py, telemetry/provenance.py,
telemetry/recorders.py, telemetry/rotate.py, telemetry/schema.py,
tests/test_loader_resource_gate.py.

**Verdict: CHANGES REQUESTED, scoped to NEW-327 only.** The other six
findings (NEW-77, NEW-78, NEW-90, NEW-336, NEW-343, NEW-347) are correct
and live-verified — see verification list below. Full test suite
self-reproduced: `1500 passed, 1 skipped in 230.72s`.

**NEW-327 (schema.py/provenance.py/cli.py) — real regression, live-proven.**
The fix makes `schema.validate()` recurse one level into list-of-dict body
fields and adds a matching `nulls["body.models[i].sha256"]` entry in
Python's `build_run_start_nulls()`. Both are correct **on the Python side**
— live-verified via captured `store.record`. But `~/Codey-Aigentik/telemetry.mjs`'s
`recordRunStart()` (same repo family, writes into the *same* shared
`~/.codeyOS/metrics` store — confirmed both `DEFAULT_METRICS_ROOT` (JS)
and `METRICS_DIR` (Python) resolve to `~/.codeyOS/metrics`, and both use
the identical `SCHEMA_SHA256_12`) builds its own `nulls` dict (lines
~1035-1047) and never adds a `body.models[i].sha256` entry for a
cold-cache model (`sha256: null, sha256_source: 'not_computed'`, line
816-817 / passed into `body.models` at line ~1023, before
`scheduleColdModelDigests()` resolves it asynchronously). NEW-327's own
entry (NEW_ISSUES.md line 14388) explicitly names this JS mirror and
gives a two-branch fix direction: extend the JS side too, OR add a
pinned test documenting the gap stays open. The diff did neither —
it only fixed Python, and `cli.py`'s `known_limitation_new_327` doctor
message was changed to unconditionally say **"closed"**, which is false.

Live-reproduced by hand-building a record shaped exactly like
`telemetry.mjs`'s own `recordRunStart()` output (cold-cache model, no
per-model nulls entry, `emitter: 'aigentik.node'`) and running it through
this repo's `schema.validate()`:
```
['body.models[0].sha256 is null with no entry in nulls', ...]
```
Before this diff, that nested null was invisible to `validate()` — a
JS-emitted cold-cache `run_start` record validated clean. After this diff,
`codey-metrics doctor` (which walks the *shared* on-disk store via
`_rollup.iter_records_for_date()` + `schema.validate()` regardless of
which process/language wrote a given record — confirmed by reading
`cmd_doctor`'s loop) will newly count this as a hard violation and flip
its exit code from 0 to 1 on entirely normal Aigentik-side telemetry. This
is the same class of bug flagged before in
[[telemetry_t1_aigentik_extraction_grounding_approved]]: cross-repo
JS/Python parity claims require reading both sides' actual source, not
just the design doc or the Python diff.

**Fix needed:** either (a) mirror the exact same one-level-into-`models`
nulls population in `telemetry.mjs`'s `recordRunStart()`, or (b) revert
`cli.py`'s doctor message to accurately say "closed on the Python side
only, JS mirror still open" and file a new NEW_ISSUES entry for the
now-actionable JS gap (previously latent/invisible, now would actually
fire doctor's exit code) rather than leaving the false "closed" claim
in place.

**What was verified correct (no changes needed):**
- NEW-77/78 (`ccos/core/telemetry_engine.py`): `self._lock` is
  `threading.Lock()` (non-reentrant); `record_execution()` now appends
  and checks/flushes under one `with self._lock:`, calling the new
  `_flush_buffer_locked()` (no lock acquired inside); the public
  `_flush_buffer()` still exists and correctly wraps
  `_flush_buffer_locked()` in its own `with self._lock:` — no
  double-lock/deadlock. Only other caller (`close()`, line ~716) still
  goes through the public method. `except Exception: pass` on the
  per-record insert replaced with a real `warning(...)` log — a genuine
  improvement, not new silent swallowing.
- NEW-90 (`core/loader_v2.py`): `_load_failures += 1` removed only from
  the gate-denial branch; the other 4 increment sites (real spawn
  failures) untouched — confirmed by grep. Test updated to assert
  `get_load_failures() == 0` and `get_last_ensure_outcome() ==
  LOAD_OUTCOME_GATE_DENIED` instead.
- NEW-336 (`telemetry/rotate.py`/`cli.py`): `acquire_rotate_lock(root,
  shared=True)` correctly uses `LOCK_SH` vs `LOCK_EX`; `cmd_rollup`/
  `cmd_rotate` still take the default exclusive lock (confirmed via
  grep, both untouched call sites at cli.py:699/717), so the new shared
  lock is a real contention point, not a no-op. Live-verified: handler
  called exactly once per invocation (no double-call), and a
  pre-held exclusive lock correctly produces the "in progress" stderr
  warning while still returning the read result (never blocks/crashes,
  per its own stated design constraint).
- NEW-343 (`core/inference_hybrid.py`/`core/plannd.py`): all new
  `_emit_inference_failed_telemetry()`/`record_inference_failed()` calls
  use variables (`_wall_start_mono`, `payload["messages"]`, `max_tokens`,
  `telemetry_emitter`) that are set unconditionally before the enclosing
  `try` can raise — confirmed by reading the full function bodies, not
  just the diff hunk. Live-verified via captured `store.record` that
  both new call sites (inference_hybrid's `nulls={"body.role": ...}`
  with `role` omitted, vs plannd's `role="planner"` with no `nulls`)
  both produce **schema-valid** records — the apparent asymmetry is
  correct because `_emit()`'s field-pruning rule (documented in its own
  docstring) drops any `None`-valued field with no matching `nulls`
  entry entirely rather than writing it as an unreasoned null, so a
  real (non-None) `role` value needs no `nulls` entry at all. The
  failure-telemetry call is wrapped in its own broad `except Exception`
  that only logs via `logging.getLogger(__name__).warning(...)` — cannot
  mask or replace the pre-existing `error()`/`_warning()` call that
  already ran before it.
- NEW-347 (`telemetry/recorders.py`): docstring-only, no behavior change
  — confirmed via diff, accurately describes `_emit()`'s existing
  pruning/nulls logic and the pre-existing `emitter`/NEW-341 precedent
  it cites.

**Process note for future telemetry rounds:** this project's telemetry
store is shared across two separate repos/languages
(`core/`+`telemetry/` in Codey-OS, `telemetry.mjs` in Codey-Aigentik) via
a single on-disk directory (`~/.codeyOS/metrics`) and one shared schema
hash (`SCHEMA_SHA256_12`, kept byte-identical on both sides). Any change
that *tightens* `telemetry/schema.py`'s `validate()` — not just any
change to a nulls-builder — must be checked against **both** emitters'
source, because `codey-metrics doctor`'s violation count/exit code is
computed over every record in the shared store regardless of which
process wrote it. A Python-only fix to a validator gap can turn a
previously-invisible (harmless) gap into a live, reproducible regression
for the untouched side. Grep target: `~/Codey-Aigentik/telemetry.mjs`.
