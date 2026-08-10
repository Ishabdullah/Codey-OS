---
name: resource-gate-phase5a-subtaskA-cpu-sentinel-round2-approved
description: Phase 5a/7.4 sub-task A round 2 — both round-1 blocking findings fixed and independently reverified; APPROVED
metadata:
  type: project
---

Follow-up to [[resource_gate_phase5a_subtaskA_cpu_sentinel_changes_requested]].
Round 2 verdict: **approved**.

**Blocking finding 1 (cpu_percent 0.0 sentinel) — fixed, verified for
real, not just by type annotation.** Traced `sample_cpu_percent()`,
`get_current_cpu_percent()`, `ResourceSnapshot.cpu_percent` in
`core/resource_gate.py` — all now `Optional[float]`, and the actual
`return` statements on the unreadable-file and first-call-seed paths are
`return None`, not `0.0`. Confirmed the corresponding
`tests/test_resource_gate.py` assertions are genuinely `is None` (not
`== 0.0` left in place) for both paths, and read through
`reset_cpu_sampler()`/the seed-flag logic by hand to confirm these tests
would actually fail if `0.0` were reintroduced (not vacuous — e.g.
`test_sample_cpu_percent_unreadable_file_returns_none_and_no_history` and
`test_sample_cpu_percent_first_call_seeds_and_returns_none` both assert
`is None` directly against the real return value, no mock substituting
the result).

**Blocking finding 2 (NEW-108 overclaim + stale TODO.md line) — fixed
correctly per rule 6.** NEW-108 was edited in place with an explicit
"**Correction (code-review, 2026-08-09):**" paragraph that names the
original overclaimed wording, explains why it was wrong, and documents
the actual fix and its live-verified output (`"cpu_percent": null` from
`python main.py --status`) — not just appended as a new entry alongside
the stale one. TODO.md's 4.1 line was rewritten from "zero implementation
started" to "sub-task A ... code-complete, pending code-reviewer
approval," with sub-tasks B-E correctly still marked not started.
WORK_QUEUE.md's matching line was updated the same way.

**NEW-110 (git-status-coupled test hang)** — logged accurately as a new,
correctly-scoped-out finding (pre-existing test design flaw, not
introduced by this sub-task), matches round 1's own analysis almost
verbatim. Correctly left unfixed.

**Test runs, verbatim:**
- `pytest tests/test_resource_gate.py -q` → `74 passed in 0.67s`
- `pytest tests/ -q --ignore=tests/test_new19_patch_failed_repeat_escalation.py`
  → `444 passed, 1 skipped in 122.27s` (matches the git-diff-cross-check
  quirk in [[resource_gate_phase5a_subtaskA_cpu_sentinel_changes_requested]]
  — this run was itself done against a dirty working tree, consistent
  with NEW-110's own finding that the *excluded* file is what would have
  hung, not this one).

**Reusable technique for cpu/sentinel-style "did they really fix it or
just change the type annotation" claims:** don't stop at `Optional[float]`
in the signature — grep every `return` in the function body and confirm
none of them still return the old sentinel on a path the type change was
supposed to cover. Also independently confirm the test's assertion
operator itself changed (`== 0.0` → `is None`), since a stale `== 0.0`
assertion left in place would still pass against a `None` return by
accident in some but not all comparison contexts (though not here) —
cheap enough to check directly rather than trust it.
