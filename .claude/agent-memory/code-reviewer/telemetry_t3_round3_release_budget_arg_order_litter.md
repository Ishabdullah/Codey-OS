---
name: telemetry-t3-round3-release-budget-arg-order-litter
description: T3 test-fix round (T3 admission mocks + NEW-280 embed_server fix) approved; found real pre-existing production bug (release_context_budget arg-order) whose failure mode is opposite of implementer's claim and resolves NEW-277
metadata:
  type: project
---

Follow-up to [[telemetry_t3_prefix_cache_hit_round2_flaky_test_rejected]]. Round3: two test
fixes landed — (A) the 4 T3 tests in `tests/test_restoricon_core/test_api.py` now mock
`core.resource_gate.wait_and_reserve_context_budget`/`release_context_budget` via
`monkeypatch.setattr` (correct pattern for a route handler that does the real import as a
LOCAL import inside the function body — patching the module attribute before that import
executes at request time does intercept it), and (B) `tests/test_loader_resource_gate.py`'s
two embed-server slot tests now also patch `_port_is_bound` (not just `_is_port_open`), closing
`NEW-280`. **Both APPROVED** — negative-control verified myself (flipped `admitted=False`,
got the predicted `429`; real socket bound to 8082, both NEW-280 tests still passed), full
suite run twice back-to-back both `1325 passed, 0 failed, 1 skipped`.

**Real finding, corrected mechanism.** The implementer flagged (accurately, but with the wrong
mechanism) that `restoricon_core/api/routes.py:1456` calls
`release_context_budget(port, reservation_id)` against the real signature
`release_context_budget(reservation_id: str, state_dir: Optional[Path] = None)` — i.e. `port`
(int) lands in the `reservation_id` slot and the real reservation-id string lands in the
`state_dir` slot. The implementer claimed this raises `TypeError`, swallowed by the bare
`except Exception: pass` at the call site. **I traced and reproduced it directly — that's
backwards.** `Path(<uuid-string>)` is a perfectly valid path (not a TypeError); the real bug is
a **silent no-op that also litters the filesystem**: `_get_db_path`/`_get_lock_path` `mkdir()`
a directory named after the reservation id in the server's CWD, create a fresh empty
`resource_bus.db`/`resource_bus.lock` inside it, the `UPDATE ... WHERE lease_id=<port>` matches
nothing, and `release_context_budget()` returns `False` — no exception ever fires, nothing for
the `except` to swallow.

**Confirmed live in production, not theoretical**: `find` in the repo root turned up 72 real
32-hex-char directories, each with a `resource_bus.db`/`resource_bus.lock` pair, matching
**`NEW-277`** exactly (already logged, "presumably per-run scratch state... not guessed at
here" — and `.gitignore:44`'s pattern for these directories was added in the SAME commit,
`69b0346`, 2026-08-31, that introduced this bug). This bug is `NEW-277`'s root cause — resolve
that cross-reference when logging.

**Why:** an advisor call caught this before it went into `NEW_ISSUES.md` with the wrong
mechanism — I had accepted the implementer's "raises and swallowed" framing without tracing
the actual arg-type binding myself. A quick `python3 -c` repro (`release_context_budget(8080,
'probe-uuid')`) settled it in under a minute and turned up real, already-existing evidence
(the 72 live directories) that upgraded the severity from "latent" to "confirmed, currently
firing."

**How to apply:** when a bug report describes an exception being swallowed by a bare `except`,
don't just confirm the except exists — trace what the WRONG-TYPED argument actually does at
each call site downstream. A type mismatch across a `(str, Optional[Path])` boundary in Python
often does NOT raise (any string coerces into a valid `Path`), so "silent no-op / wrong
behavior" is at least as likely as "raises." Reproduce with a real interpreter call before
writing the mechanism into a findings ledger — the actual repro is cheap and the two mechanisms
(raise-and-swallow vs. silent-no-op-with-litter) have very different severity and remediation
implications. Also: an existing "N mystery scratch directories accumulating, cause not
identified" finding (like NEW-277) is exactly the kind of thing a newly-found arg-order bug
should be checked against before assuming it's a brand-new, unrelated finding.
