---
name: resource_gate_phase4_1_subtaskD_round2_temp_critical_warning_understated
description: Phase 4.1 sub-task D — round 2 CHANGES REQUESTED (consumer list understated), round 3 APPROVED (all 4 consumers now named in both utils/config.py sites); commit cleared
metadata:
  type: project
---

**ROUND 3 UPDATE (APPROVED, commit cleared):** implementer added all four
consumers (`can_admit()`/`can_dispatch_task()`, the shutdown tripwire,
`core/recursive.py`'s `get_adaptive_depth()` flagged as "most surprising",
`core/thermal.py`'s log-level use) to BOTH `utils/config.py` sites — the
comment block near `max_value=120` and the runtime warning string — not
just one. Also fixed a second, near-identical incomplete list a few lines
above in the same file. Verified independently (not from summary):
`grep -rn temp_critical` across the repo confirms both sites now name all
real readers found by the grep, except one boundary case (see below).
Added a factually-accurate limitation comment near
`MIN_QUALIFYING_DENSITY_FRACTION` in `core/resource_gate.py` — checked it
does NOT overclaim "any 2-sample window always passes" (it explicitly
carves out the 25-min-apart case, which correctly still rejects at
density ~0.04, and scopes the vacuous case to short `duration_sec` only).
Logged `NEW-117` (recursive.py's `get_adaptive_depth()` docstring/fallback
say 80°C, real default is 90°C) — spot-checked against
`core/recursive.py:176`/`:188` verbatim, accurate. Re-ran
`pytest tests/ -q --ignore=tests/test_new19_patch_failed_repeat_escalation.py`
myself: `517 passed, 1 skipped`, comment/string-only diff as claimed.

**One boundary case surfaced this round, NOT a blocker (per advisor,
correctly — see lesson below):** `core/daemon.py:996`/`:1000` does its own
direct `THERMAL_CONFIG.get("temp_critical", 90)` read, inside the
tripwire's own try-block, to pick `warning` vs `info` log level for the
per-tick progress line. This is a 5th literal call site not named in the
warning text, but it sits inside the exact code path the warning already
points readers to ("the autonomous shutdown tripwire's trip point") and
its only effect is a log-level flip — not a new behavioral surprise like
recursive.py's forced-depth-0. Handed back as a Suggestion (fold into the
same clause or log to NEW_ISSUES.md), not a re-block.

**Lesson for next time:** a shared-config-key "name all consumers"
warning will always have a debatable granularity boundary — direct reads
inside a function/code-path you already named vs. a genuinely separate
subsystem. Fix the boundary question by asking "does this add a new
*behavioral effect* a reader wouldn't already expect from the named
consumer," not "is this a distinct call site." Once the surprising
consumers (recursive.py, thermal.py) are named, don't re-block on further
boundary-case call sites found by a wider grep — log them and move on.
This is also the exact case CLAUDE.md's "don't reject the same fix twice
without converging" escalation rule is aimed at.

Round 2 of Phase 4.1 sub-task D (sparse-history false-trip fix +
`CODEY_TEMP_CRITICAL_C` override, `core/resource_gate.py` /
`utils/config.py`) — all three round-1 blockers verified genuinely fixed,
but ONE NEW finding blocks commit on its own.

**What verified clean (round-1 blockers, re-checked independently, not
trusted from summary):**
- Sparse-history repro (`temp_history=[(now-1500,95.0),(now,95.0)]`) now
  returns `should_trip=False` — re-ran the exact original repro command,
  got `'thermal leg not satisfied: only 2 sample(s) present in the 1500s
  trailing window ... density 4% < required 50%'`.
- `_sustained_trailing_run()`'s density check evaluated at the correct
  window — traced the walk-backward loop by hand: it stops and evaluates
  density at the FIRST (smallest) window whose span reaches
  `duration_sec`, same window the span/fraction checks already used, not
  some other window. Also hand-verified the loop correctly rejects a case
  where a long real gap exists mid-history (dense old block + sparse
  recent tail) — the accumulated `count` at the point span first reaches
  `duration_sec` only reflects samples actually walked, so clustering
  elsewhere in history can't inflate density.
- Two boundary tests pin the real constants
  (`rg.MIN_QUALIFYING_DENSITY_FRACTION`, `rg.EXPECTED_SAMPLE_INTERVAL_SEC`),
  not hardcoded literals — confirmed via `assert n/expected_count >=/<
  rg.MIN_QUALIFYING_DENSITY_FRACTION` preconditions in both tests. Minor
  drift gap (non-blocking): both tests hardcode `1200.0` instead of reading
  `THERMAL_CONFIG["shutdown_trip_after_sec"]`, so a future default change
  (or a stray `CODEY_SHUTDOWN_TRIP_AFTER_SEC` at suite time) would silently
  un-pin the boundary without failing the test.
- `EXPECTED_SAMPLE_INTERVAL_SEC = 30.0` matches the real watchdog cadence —
  traced `core/daemon.py`'s `_main_loop()`: `_watchdog_ticks >= 60` at
  `await asyncio.sleep(0.5)` per loop = 30s. Not just trusted from comment.
- TODO.md / WORK_QUEUE.md both now correctly say "Decided by Ish,
  2026-08-10: option 3" and agree with each other and the code — no
  lingering "BLOCKED" text.
- NEW-115 and NEW-116 both genuinely present in `NEW_ISSUES.md` (`git diff
  -- NEW_ISSUES.md`, not a chat-summary claim) — 4th occurrence of this
  exact "logged for real" verification pattern, and it held up this time.
- `CODEY_TEMP_CRITICAL_C`: independently verified live — `=45` applies +
  warns with real before/after values in the message; `=999` raises
  `ValueError: must be <= 120`; `=abc` raises on `int()` parse. Warning
  correctly fires only when value differs from the *captured* default
  (`_temp_critical_default`), not a hardcoded 90.
- `THERMAL_CONFIG["temp_critical"]` genuinely shared/read-at-call-time by
  `can_admit()`, `can_dispatch_task()`, and `should_trip_shutdown()` (all
  three do `THERMAL_CONFIG.get("temp_critical", ...)` inline, not a cached
  copy) — confirmed by grep + read of all three call sites.
- 517 passed, 1 skipped — matches implementer's claim exactly (own run:
  `pytest tests/ -q --ignore=tests/test_new19_patch_failed_repeat_escalation.py`).

**New finding this round (blocking): the `CODEY_TEMP_CRITICAL_C` warning
text in `utils/config.py` is UNDERSTATED — it names three consumers
(`can_admit()`, `can_dispatch_task()`, the shutdown tripwire) as if
exhaustive, but a repo-wide grep of `temp_critical` (not just within
`core/resource_gate.py`) turns up two more real readers of the same
shared `THERMAL_CONFIG["temp_critical"]` key that the warning never
mentions:**
- `core/recursive.py`'s `get_adaptive_depth()` (line ~188,
  `cfg.get("temp_critical", 80)`) — this is a REAL behavioral gate, not
  just logging: `if temp >= temp_crit: return 0` forces recursion depth to
  0 whenever the live temp reading is at/above the (now possibly
  drastically lowered) threshold. A live-test session running
  `CODEY_TEMP_CRITICAL_C=45` to make the shutdown tripwire reachable will
  ALSO silently disable all self-refinement recursion the moment ambient
  temp crosses 45°C — a bigger, more surprising side effect than the two
  named consumers, and it's unmentioned.
- `core/thermal.py`'s `ThermalManager._check_thermal_status()` (line
  ~114, `THERMAL_CONFIG.get("temp_critical", 90)`) — lower-severity
  (log-level only: fires a `warning()` log line instead of the normal
  `info` one), not itself a behavior change, but still an unmentioned
  consumer of the same key.

Fix needed before commit: extend the warning string/comment in
`utils/config.py` to name `core/recursive.py`'s adaptive-depth gating
explicitly (the behaviorally significant one) — the whole point of the
warning is "a stray export... should be visible... not a silent,
easy-to-forget landmine," and an incomplete consumer list undermines
exactly that goal for the consumer most likely to surprise someone.
`core/thermal.py`'s log-only use can be mentioned or omitted at the
implementer's discretion (lower stakes), but recursive.py's forced-depth-0
behavior must be named.

**Also worth writing into the handoff (non-blocking, but must be stated,
not silently assumed covered):** the density guard is structurally vacuous
whenever `duration_sec <= EXPECTED_SAMPLE_INTERVAL_SEC` — `expected_count
= max(1.0, span/30)` floors at 1.0, so two samples give density 2.0,
always passing. This is exactly the shortened-duration configuration the
batched live-verification session is expected to use
(`CODEY_SHUTDOWN_TRIP_AFTER_SEC=20` or similar). That means live-
verification of sub-task D CANNOT exercise the density-guard code path at
all — it will run through the branch where the guard is a no-op by
construction. Don't let a "live-verified" note for sub-task D later imply
the density fix itself was exercised live; it wasn't, and structurally
can't be with a short override duration.

See also [[resource_gate_phase4_1_subtaskD_shutdown_tripwire_changes_requested]]
(round 1) for the original three findings this round fixed.
