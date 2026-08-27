---
name: new259-daemon-config-and-loader-port-fix-approved
description: NEW-259 two-bug fix (self._config AttributeError + missing reserve_slot port kwarg) inside already-twice-approved NEW-145/149/155 Option C fix — approved
metadata:
  type: project
---

Reviewed uncommitted working-tree fix (post-`b0d2d86`) for two real bugs
found by a live-verification attempt in [[plannd_new46_47_28_prompt_fix_approved]]-adjacent
Option C work ([[new145_149_155_option_c_approved]]):

1. `core/daemon.py:_handle_status()` referenced `self._config`, an
   attribute only `Daemon.__init__` sets — never `DaemonServer.__init__`
   (the class the method actually belongs to). Every real call would
   raise `AttributeError`. All 3 existing unit tests masked this by
   manually stubbing `handler._config = _FakeConfig(...)` directly onto
   a `__new__`-constructed test double, bypassing real `__init__`
   entirely. Fix: call the module-level `get_config()` singleton
   (imported via `from core.daemon_config import get_config`, confirmed
   a direct-name import so `patch.object(daemon_mod, "get_config", ...)`
   correctly intercepts it — the classic "patched the wrong module"
   trap did NOT apply here, verified by reading the import statement
   directly).

2. `core/loader_v2.py:ModelLoader.load_primary()` called
   `rg.reserve_slot(spec)` without `port=PRIMARY_SERVER_PORT` — the only
   call site of `reserve_slot()` in the codebase. `find_resident_slot()`
   filters `if port is not None and slot.get("port") != port: continue`
   — a slot registered with port=None never matches a real-port lookup,
   silently forcing every Option C upgrade check onto the already-broken
   `/proc` fallback (`NEW-200`). This would have made the entire
   respawn-on-upgrade mechanism a permanent silent no-op in production
   despite 100% of its own unit tests passing (none of them exercised a
   real `load_primary()` call to check what `reserve_slot()` actually
   receives — they all monkeypatched `find_resident_slot` directly).

**Both bugs independently reproduced via negative control** (revert fix,
run relevant test, confirm exact failure text, restore from a scratchpad
backup copy — not `git checkout`, per [[git_checkout_path_wipes_uncommitted_diff]]).
Bug 1: reverting `get_config()`→`self._config` makes all 3 rewritten
tests fail with literal `AttributeError: 'DaemonServer' object has no
attribute '_config'`. Bug 2: reverting the `port=` kwarg makes the new
regression test fail with `assert None == 8080`.

**Test-count reconciliation**: implementer's claimed "877 passed, 1
skipped + 6 pre-existing unrelated failures" only matches
`pytest tests/` (excludes `ccos/`). Full `pytest -q` on repo root gives
945 passed (877 + 68 ccos tests, no ccos regressions) + same 6
failures. Not a discrepancy — just a different collection root; always
check `--ignore=ccos` scope before treating a total-count mismatch as a
red flag on this project.

**NEW-260** (6 pre-existing plannd test failures, stale expected-value
formula predating this session by a `dfb655c`-vintage change to
`compute_outer_plan_timeout()`) independently reproduced via
`git stash` + running the two affected test files directly — confirmed
pre-existing and out of scope, correctly logged rather than silently
fixed or dropped (rule 8).

**Doc fix** (`AGENTS.md` pointing to both `CLAUDE.md`/`ANTIGRAVITY.md`;
`CODEY_MASTER_PLAN.md` rule 10 made tool-neutral) read coherently against
`ANTIGRAVITY.md`'s actual rule 10 wording (`define_subagent`) — confirmed
by reading `ANTIGRAVITY.md` directly, not assumed from AGENTS.md's own
description of it.

**One process note, not blocking**: an untracked `HANDOFF.md` (a
Claude→Antigravity coordination note, benign content, described in the
file itself as written for exactly this multi-agent-session situation)
existed in the working tree but was not mentioned in the round's
findings-summary to the reviewer. Non-code, doesn't affect approval, but
worth flagging in future rounds — any undisclosed untracked file in the
working tree during a review should be read before being waved off,
even when it turns out benign.

Verdict: **approved**. Chain closes NEW-259 with both root causes fixed,
both negative-controlled, full suite clean apart from the correctly-
out-of-scope NEW-260.
