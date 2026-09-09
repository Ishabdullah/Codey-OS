---
name: new415_418_421_finetune_reexport_stale_new24_claim
description: cleanup round 3 (NEW-415/416/417/418/421/422/423) — NEW-415/416/418/422/423 all verified accurate; NEW-421 and finetune.py's new docstring text contain a materially false claim (stale NEW-24 recurrence) that the round's own edited ledger already contradicted
metadata:
  type: project
---

Round 3 of the Codey-OS cleanup series (2026-09-09): except-narrowing in
`ccos/core/device_manager.py`/`goal_engine.py` (NEW-415/416), a dead-test
import-gap fix in `ccos/plugins/coding/finetune/finetune.py` (NEW-417),
and a `confirm_resident_and_mark_slot` test-stub speedup fix across 3
test files (NEW-418), plus 3 new findings logged not fixed (NEW-421/422/
423). **6 of 7 items verified clean; 1 (NEW-421 + finetune.py's docstring
text) contains a real factual error that must be corrected before commit
— not a code bug, a documentation/ledger overclaim.**

**NEW-415/416 (except narrowing, `device_manager.py`/`goal_engine.py`):**
every narrowed exception type independently verified against the actual
surrounding code (`goal_engine.py:345`'s `json.loads` — `isinstance` guard
above confirmed `steps_raw` is always `str`, so `json.JSONDecodeError`
alone is correct, no `TypeError` case exists; `device_manager.py`'s audio/
network `read_text()` sites — regex always has exactly 2 groups reached
only when `match` is truthy, so no `AttributeError`/`IndexError` case
exists, only `(PermissionError, OSError, UnicodeDecodeError)`). `_scan()`'s
catch-all genuinely can't be narrowed further (wraps 9 independent probe
calls) — confirmed correct, now logged via `warning()` instead of silent.

**NEW-418 (`confirm_resident_and_mark_slot` test stub):** stub lambda
signature (`slot_id, baseline_meminfo, estimated_cost_bytes,
timeout_s=None, poll_interval_s=None, pid=None`) matches the real
function's signature in `core/loader_v2.py:121` exactly (positional order
+ names), and matches the one real call site at `core/loader_v2.py:1516`
(3 positional + `pid=` kwarg). None of the 3 affected test files
(`test_lora_import_swap_sync.py`, `test_new84_stale_model_path.py`,
`test_new91_new163_rollback_preserves_finetune.py`) actually test
`confirm_resident_and_mark_slot`'s own polling/timeout logic — all test
path-swap/rollback/config-sync behavior, so bypassing residency
confirmation is safe for these specific tests. **Independently
time-verified myself** (not trusting the implementer's numbers): pre-fix
`git stash` rerun → `10 passed in 50.25s` (claim: 50.33s), post-fix →
`10 passed in 0.15s` (claim: 0.18-0.27s). Real speedup, not just claimed.

**NEW-417 (finetune.py re-export fix):** independently reproduced the
pre-fix `ImportError` is real, and post-fix `python3
ccos/plugins/coding/finetune/test.py` genuinely runs all 8 test functions
to completion with real sha256 checksum assertions on the backup/rollback
round-trip (not just "no import error") — confirmed via direct execution,
not trusted from implementer report.

**NEW-421 — THE FINDING WITH A REAL PROBLEM.** The implementer's own new
finding (and the docstring text this round added to `finetune.py`'s
module header, and the NEW-417 resolution note's "Found while fixing
this entry" bullet) all assert: *"`coding.finetune_rollback_backup`'s
`model_variant='secondary'` branch still hits `NEW-24`, calling
`loader.load_secondary()` — a method `ModelLoader` does not implement —
AFTER the live model file has already been overwritten and the backup
already deleted."* **This is false in the current codebase, and the
round's own `NEW_ISSUES.md` edits should have caught it:** `NEW-24`'s own
ledger entry (already committed, unrelated to this round — `git show
HEAD:NEW_ISSUES.md` confirms it predates this diff) says **Status: FIXED
(2026-08-09, round 5; corrected 2026-09-04)** — `rollback_to_backup()`
and `swap_to_finetuned_model()` no longer call `load_secondary()` at all,
and as of M1-D (2026-08-23, `core/lora_import.py` inline comments at
~L360-394 and ~L525-541 say this explicitly) planning collapsed onto the
single primary server: **both `"primary"` and `"secondary"` branches of
`rollback_to_backup()` route through the exact same
`get_loader().load_primary()` call (line 545)**. I independently
confirmed via `grep -rn "load_secondary"` across `core/` and `ccos/` that
no production code path calls `load_secondary()` anywhere — the only
places that name appears are historical comments describing the
already-fixed bug, and an unused defensive stub method on a test file's
`_FakeLoader`. `ModelLoader` (confirmed via grep) implements only
`load_primary()`/`unload()` — `load_secondary` was never added, but it's
also never called. **The crash NEW-421 describes cannot happen with the
current code.** The stale claim traces to `manifest.json`'s capability
description (unchanged in this diff, dated "corrected 2026-07-30" — a
date *before* the 2026-08-23 M1-D collapse that made the claim stale) —
the implementer trusted that pre-existing manifest text and the original
`NEW-24` finding text without re-reading `rollback_to_backup()`'s actual
current code closely enough to notice the M1-D collapse comment sitting
right there contradicting it, despite editing that exact file's imports
this round.

**What this changes about the actual risk, and my call:** the
reachability claim (item 1: 6 capabilities become dispatchable through
`ccos/core/plugin_manager.py`'s `getattr(module, func_name, None)` +
`raise RuntimeError` fallback, confirmed by reading L532-568 myself) is
real and correctly described — before this round's fix, calling any of
the 6 raised `RuntimeError("No loaded plugin implements ...")` at
call-time; the plugin itself still loaded fine (import gap was in
`test.py`, not `finetune.py`, since `finetune.py`'s own
`from core.lora_import import (validate_lora_adapter,)` never referenced
the missing names and never raised on its own). `model_variant` and
`backup_path` are both fully agent-controllable (dispatch forwards
`**kwargs` straight to the function, no schema/enum enforcement in
manifest.json). But the *specific* crash-then-data-loss sequence NEW-421
describes is not real. The actual residual risk is narrower: `rollback_to
_backup()`'s "not a backup name" fallback branch (L488-507) reproduces
NEW-91/163's original data-loss shape if an agent supplies a
`backup_path` that doesn't match `create_backup_before_import()`'s own
`<stem>.backup<suffix>` naming convention — already caught and logged via
`warning()`, not a new gap this round introduces. Since Ish's own
capability-wrapping decision (`PENDING_ISH_DECISIONS.md`) already
accepted `rollback_to_backup` as agent-callable under the *corrected*
(2026-07-30) understanding that it mutates the live model file (just not
under the further-stale "still crashes via load_secondary" framing), the
underlying re-export code change is safe to ship as-is.

**Verdict: split.** NEW-415/416/417(code)/418/422/423 all APPROVED,
independently verified. `finetune.py`'s re-export code change (the
`from core.lora_import import (...)`/`from core.finetune_prep import
(...)` diff hunks) is APPROVED to commit. **BLOCKED as written:**
`finetune.py`'s new docstring paragraph (the `~L14-24` diff hunk
asserting the still-crashes claim) and `NEW_ISSUES.md`'s `NEW-417`
resolution note's "Found while fixing this entry" bullet + the entire
`NEW-421` entry — these need to be corrected to say what's actually true
(reachability is new and real; the NEW-24 crash path is not, per NEW-24's
own already-corrected FIXED status; residual risk is the narrower
backup_path-naming-mismatch fallback, already logged) before commit. This
is a rule-6 ("correct the record") violation risk in the making — same
shape as [[t8a_daemon_dedup_docstring_overclaim]] and
[[new206_q11_context_budget_reservation_lifetime_double_count]]: code is
fine, newly-added documentation/ledger text is not, and this project's
culture treats that as blocking, not a nitpick — especially here, since
the false claim would sit in a **module docstring agents reference when
deciding whether a capability is safe to call**, not just an internal
ledger.

Full suites independently run: `python -m pytest tests/ -q` →
`1517 passed, 1 skipped` (exact match), `python -m pytest ccos/tests/ -q`
→ `111 passed` (exact match), `python3
ccos/plugins/coding/finetune/test.py` → genuinely passes with real
checksum assertions (exact match to implementer's claim).
