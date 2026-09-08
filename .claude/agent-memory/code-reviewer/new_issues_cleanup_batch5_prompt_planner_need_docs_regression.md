---
name: new_issues_cleanup_batch5_prompt_planner_need_docs_regression
description: Batch 5 (prompt/planner) NEW_ISSUES.md ledger closeout — CHANGES REQUESTED; NEW-31's critique-template wiring silently disables NEED_DOCS targeted retrieval for plan/tool critique
metadata:
  type: project
---

Round: core/agent.py, core/orchestrator.py, core/plannd.py, core/recursive.py,
prompts/layered_prompt.py, prompts/system_prompt.py, utils/config.py,
NEW_ISSUES.md. Verdict: **CHANGES REQUESTED** (1 blocking finding; everything
else independently verified and correct).

**6 of 7 fixes verified clean, all live-reproduced or grep-traced, not just
diff-read:**
- NEW-29 (orchestrator.py Edit-step template) — copied verbatim from
  plannd.py's PLANNER_PROMPT, confirmed byte-identical.
- NEW-127 (peer-delegation keyword sync) — both `_action_kws` lists now
  carry the same 5 entries; confirmed agent.py's list was untouched this
  round (it already had them, orchestrator.py was the drifted one).
- NEW-166 (remote planner timeout) — `compute_planner_timeout()` reused
  correctly, same try/except ImportError -> 300.0 fallback pattern as the
  local path, `PLANNER_MAX_TOKENS` import scope confirmed in-function.
- NEW-342 (get_plan() caller-graph comment fix) — **initially flagged as a
  possible false-claim collision with NEW-172's "zero production callers"
  finding** (two different `get_plan()` functions exist: `core/plannd.py`'s
  real one and a since-fully-deleted `core/planner_service.py` one that
  NEW-172 was about). Traced the full caller graph: `core.plannd.get_plan`
  is imported only by `core/planner_client.py::send_plan_request_async()`,
  which is called only from `core/daemon.py`; `main.py`'s `_try_daemon_plan()`
  goes through `core.planner_service._request_daemon_plan()` (a socket RPC),
  never in-process `get_plan()`. The corrected comment is accurate; the
  *old* comment's "main.py's synchronous interactive path" claim was the
  actual falsehood. NEW-342 approved.
- NEW-32 (LayeredPrompt.add() duplicate-name ValueError) — grepped
  `LayeredPrompt` repo-wide outside `prompts/layered_prompt.py`: zero
  external instantiations (not even in tests). Audit claim "no current
  caller triggers it" fully verified, not just asserted.
- NEW-28 status quote — `_TOOL_VERBS` regex pasted into NEW_ISSUES.md
  matched the live regex byte-for-byte.
- Stale-comment sweep (8 sites, "7B"/"1.5B" -> current-model language) —
  all comment-only, no logic riding along.
- NEW-408/NEW-409 (new Suspected/Confirmed entries) — both independently
  verified accurate: `core/summarizer.py`'s M1-D docstring really does
  call the primary 4B on port 8080, contradicting agent.py's stale
  "0.5B" comment (NEW-408); `codeydOS`'s `kill_llama_server_gracefully()`
  really does still loop `8080 8081` despite the file's own M1-D header
  saying 8081 is retired (NEW-409) — and `codeydOS` itself was confirmed
  genuinely untouched (`git status --short -- codeydOS` empty), correctly
  left out of scope per CLAUDE.md rule 4 (process-lifecycle gate).
- NEW-51 status correction confirmed NOT over-closed (still says "needs
  2+ more trials", matches the review task's explicit ask).
- Test suite: `1500 passed, 1 skipped in 231.87s` — ran it myself, matches
  claim verbatim.

**Blocking finding — NEW-31's fix has an undisclosed side effect:**
`prompts/critique_prompts.py`'s module docstring claims all three critique
templates ask the model to "Emit 'NEED_DOCS: <topic>'" for targeted KB
retrieval (this docstring predates the diff, untouched by it). In truth
only `CRITIQUE_CODE` contains that instruction — `CRITIQUE_TOOL` and
`CRITIQUE_PLAN` never did. Before this diff, `orchestrator.py`'s
`task_type="plan"` critique call was silently getting `CRITIQUE_CODE`
(the pre-existing bug NEW-31 correctly fixes) and therefore incidentally
*did* carry the NEED_DOCS trigger. After the fix, plan critique correctly
gets `CRITIQUE_PLAN` — but that template has no NEED_DOCS line, so
`extract_doc_needs()` (`core/recursive.py:248`, feeds the refine phase's
targeted KB retrieval at `core/recursive.py:544-546`) will now essentially
never fire on the plan-critique path. This is a real, reachable behavior
change (traced `extract_doc_needs()` -> refine prompt injection directly,
confirmed the code path is live, not dead) that neither the new
`build_recursive_prompt()` docstring nor the NEW_ISSUES.md fix entry
mentions. Matches this project's established rejection pattern (T9,
t8a, NEW-357): a docstring/prose claim ships alongside code that silently
contradicts it.

Fix direction: either add a NEED_DOCS line to `CRITIQUE_TOOL`/
`CRITIQUE_PLAN` (restores the capability for those task types, consistent
with the module docstring's existing claim), or explicitly narrow the
module docstring to say "code critique only" and note the tradeoff in
`build_recursive_prompt()`'s docstring. Either is acceptable; leaving it
undisclosed is not.

**Warning, not blocking:** zero new tests for any of the three
behavior-changing fixes (NEW-31 wiring, NEW-32 ValueError, NEW-166 remote
timeout) — confirmed via repo-wide grep, no existing test touches the
critique phase at all. Batch 1 added 5 tests for its round; this batch
added none. Live-reproduced all three myself this round (task_type ->
template selection, ValueError raise, timeout formula) so the round
itself is verified, but there's no regression protection going forward.

Process note: advisor caught the NEED_DOCS regression from re-reading the
three templates I'd already pasted into the transcript — I had verified
template *selection* correctness but not template *content* completeness
against the pre-existing docstring's claims. When wiring a previously-dead
selector function into a live path, diff every downstream side-effect the
newly-reachable branches produce, not just whether the selector itself
routes correctly.
