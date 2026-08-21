---
name: new152-ever-spawned-narrowing-approved
description: NEW-152 fix (loader_v2.py/daemon.py _ever_loaded -> _ever_spawned narrowing) — APPROVED with 2 warnings, 1 suggestion
metadata:
  type: project
---

Reviewed the retroactive NEW-151/NEW-152 fix: `ModelLoader._ever_loaded`/
`was_ever_loaded()` (sticky True on EITHER genuine spawn OR port-in-use
adoption) renamed+narrowed to `_ever_spawned`/`was_ever_spawned()` (True
only on genuine `subprocess.Popen()` spawn, checked via
`self._server.process is not None`). Used by `core/daemon.py`'s
`_watchdog_check_model()` gate to decide whether a not-currently-running
coder is "never spawned, leave alone" vs "spawned before, restart it."

**Verdict: APPROVED.** Rename is complete (grepped whole repo for
`_ever_loaded`/`was_ever_loaded` — zero live references, only comments
citing the old name for history). Branch logic at `load_primary()`'s
success point correctly gates the flag write on the same
`self._server.process is not None` check that discriminates spawn from
adoption at the reuse-branch decision point ~30 lines earlier — verified
these two checks can't diverge (nothing between them touches
`self._server.process`). `unload()` correctly leaves `_ever_spawned`
untouched, matching documented intent (stickiness is the crash-restart
mechanism, same as `_loaded_at` already wasn't reset). Negative-control
test (`tests/test_loader_resource_gate.py`'s adoption-path test) flips
True→False and is the actual regression proof — reran it live, matches
literal 37/37 pass claim.

**Key technique used to resolve a plausible-sounding regression
concern** (would this narrowing silently break NEW-13's thermal
`restart_recommended` re-consumer, which relies on the watchdog calling
`ensure_model()` periodically?): read `LlamaServer.is_running()` — it
falls back to a real health-check probe when `self.process is None but
self._started`, so an adopted-and-alive coder still reads
`was_running=True` and the `not was_running and not
was_ever_spawned()` gate short-circuits on the first clause regardless
of the flag. `ensure_model()` still runs every tick while the server is
actually up. The `_ever_spawned` flag only matters in the "not
currently running" branch, which is exactly the NEW-152 gap. Lesson:
before flagging a rename as breaking an unrelated prior fix, trace the
liveness primitive it depends on, not just the flag being renamed.

**Findings not blocking, logged in the delivered review:**
- Warning: `test_watchdog_adopted_only_not_running_no_interactive_does_nothing`
  (new test added alongside the fix) is byte-identical in FakeLoader args
  and assertions to the pre-existing
  `test_watchdog_never_loaded_and_unrequested_does_nothing` — confirmed
  via diff of extracted function bodies. The `FakeLoader` abstraction
  can't represent "adopted" vs "never loaded" (both just set
  `ever_spawned=False`), so this "new regression test" is docstring-only,
  not actual new coverage. The real regression proof is the single
  flipped assertion in `tests/test_loader_resource_gate.py`. Don't take
  "new test added" claims in a watchdog-level test file at face value —
  check whether the fake/mock layer used can actually distinguish the
  two states the fix claims to distinguish.
- Suggestion: the `self._server is not None` half of the
  `if self._server is not None and self._server.process is not None:`
  guard at the `_ever_spawned = True` assignment site looked redundant
  at first read (self._server was just assigned unconditionally a few
  lines above) but is not: it fails safe if a concurrent thread calls
  `unload()` between the reuse-branch check and this line, since
  `unload()` can set `self._server = None`. Worth flagging as
  load-bearing so a future cleanup pass doesn't delete it as dead code.
- WORK_QUEUE.md was not touched by this diff and has zero prior mentions
  of NEW-145/`was_ever_loaded` at all (checked directly) — so despite
  this project's recurring "stale evidence doc shipping alongside its
  own code fix" pattern (memory lines 43/47/48/56), this is not a 5th
  occurrence: there was nothing there to go stale. NEW_ISSUES.md and
  TODO.md both accurately describe the fix as code-complete-only, real
  code-reviewer pass and live-verifier still pending — consistent with
  what was actually in the diff.

See also [[working_tree_cross_round_bleed]] — the "742 passed" full-suite
claim in this round's NEW_ISSUES.md entry was run against a working tree
that also contains several unstaged/untracked files unrelated to this
fix (embed_server.py, inference.py, planner_loader.py, resource_gate.py,
config.py, two new test files) — not evidence about this diff
specifically. The scoped 37/37 rerun of just the two touched test files
is the number that actually backs this review.
