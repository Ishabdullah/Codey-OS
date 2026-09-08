---
name: new409-new70-daemon-lifecycle-batch1-approved
description: NEW-409 codeydOS kill loop de-8081 + NEW-70 loader_v2 thermal-restart try/except split — both approved, sub-batch 1 of daemon/process-lifecycle ledger closeout
metadata:
  type: project
---

Reviewed uncommitted diff: `codeydOS`, `core/loader_v2.py`,
`tests/test_loader_resource_gate.py`, `NEW_ISSUES.md` — sub-batch 1 of
the daemon/process-lifecycle ledger closeout (highest-risk category per
CLAUDE.md rule 4).

**NEW-409** (`codeydOS` `kill_llama_server_gracefully()`): the
`for port in 8080 8081` loop was genuinely removed, not left as a
single-element loop — body logic (kill -TERM, 10x 0.5s poll, kill -9
fallback, `rm -f pid_file`) is byte-identical, just de-indented one
level. Verified all 4 call sites (`start_daemon`, `stop_daemon` x3) are
bare `kill_llama_server_gracefully` with no port arg, and grepped the
whole file for `8081`/`llama-server-8081` — zero orphaned references
left. Real fix, matches [[new83_embed_server_kill_by_pid_approved]]'s
"track and kill a specific PID" pattern already in use here (unchanged).

**NEW-410** (implementer's own new finding, hardcoded `8080` in 3 places
in `codeydOS` vs `utils/config.py:PRIMARY_SERVER_PORT`/
`CODEY_PRIMARY_PORT` env override used consistently on the Python side):
confirmed real and accurately scoped by reading
`core/loader_v2.py:767` (`CODEY_STATE_DIR / f"llama-server-{self.port}.pid"`,
`self.port` defaults to the *env-overridable* `SERVER_PORT`) against
`codeydOS`'s hardcoded `llama-server-8080.pid` — if `CODEY_PRIMARY_PORT`
were ever set non-default, the two sides would write/look for different
PID filenames. Confirmed pre-existing (the `port_healthy(8080)` call
predates this round) — NEW-409's fix inherits the existing hardcode
pattern rather than introducing a new one. Correctly logged as Suspected
per rule 8, not drive-fixed.

**NEW-70** (`core/loader_v2.py` `ensure_model()` thermal-restart branch):
confirmed the try/except split is real and correctly scoped by reading
the method body directly (not the changelog description) —
first try wraps ONLY `get_thermal_manager()` + the
`tm.restart_recommended` read (fail-open unchanged, `restart_recommended
= False` on any exception); a separate try, entered only `if
restart_recommended:`, wraps `self.unload()` / `tm.restart_recommended =
False` / `self.load_primary()` and on exception sets
`_load_failures += 1`, `_last_ensure_outcome = LOAD_OUTCOME_ERROR`,
`_last_ensure_reason`, returns `False`. This exactly mirrors
`load_primary()`'s own catch-all at `~1520-1524` (`_load_failures += 1`,
`LOAD_OUTCOME_ERROR`, `_last_ensure_reason = str(e)`) — verified by
reading that block directly, not taking the implementer's claim on
faith. New regression test
(`test_ensure_model_thermal_restart_failure_not_reported_as_success`,
parametrized over `unload`/`load_primary` raising via
`monkeypatch.setattr(loader, raising_method, _raise)` on a real
`ModelLoader` instance, not a mock) genuinely exercises the real method
— confirmed by reading it, not trusting the docstring. Existing
happy-path test (`test_ensure_model_already_loaded_sets_outcome`) is
byte-unmodified in the diff and still relies on the real
`core.thermal` import failing naturally (no thermal module mocked) to
exercise the fail-open branch — still valid post-split since that
branch's shape is unchanged.

**Design judgment call the implementer explicitly flagged** (persistent
`unload()`/`load_primary()` failure → daemon watchdog retries the
thermal restart every tick forever instead of the old silent-lie
one-shot): traced precisely. `tm.restart_recommended = False` sits
*between* `self.unload()` and `self.load_primary()` inside the second
try — so the "stays True forever" behavior is only actually true for the
`unload()`-raises subcase (exception fires before the reset line). If
`load_primary()` itself raises, `restart_recommended` was already reset
to `False` before the call, `self._loaded` is already `False` (set by
`unload()`), so the *next* `ensure_model()` call takes the entirely
separate cold-load branch (outer `if self._loaded and ...` is now
False), not a "thermal restart retry" — a different code path than what
the implementer's ledger note technically describes, though the
practical effect (some kind of retry each tick) still holds. Net
functional behavior is fine either way; the ledger's causal explanation
is slightly imprecise for the `load_primary()`-raises branch specifically
— worth a wording fix if picked up in a later pass, not worth blocking
on. **On the retry-forever-on-persistent-failure shape itself**: grepped
the whole file for `backoff`/`cooldown`/`MAX_LOAD_ATTEMPTS` — none
exist; `_load_failures` is an unthrottled counter everywhere in this
file. Every other genuine failure path in `ensure_model()`/
`load_primary()` already retries on every tick with zero backoff, so
this fix does not introduce a new retry-storm risk category, it just
extends the codebase's existing (also-imperfect, not this round's scope)
no-backoff pattern to one more failure branch. Approved as consistent
with existing design, not as an endorsement that the no-backoff pattern
itself is ideal — that's a systemic gap worth its own future finding if
thermal-restart failures turn out to be common in practice (deferred to
live-verify).

Independently ran full `python -m pytest tests/ -q`: confirmed literal
`1502 passed, 1 skipped in 231.77s` — matches the implementer's claim
exactly (test suite took ~4 min under Termux, ran via `run_in_background`
+ poll rather than the default 120s foreground timeout).

Verdict: **APPROVED**. Both NEW-409 and NEW-70 fixes are real, correctly
scoped, and match this file's/module's existing conventions. No live
model-load verification performed this round (correctly deferred per
CLAUDE.md rule 2 — this batch is mocks-only by design).
