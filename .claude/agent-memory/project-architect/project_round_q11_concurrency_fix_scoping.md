---
name: project-round-q11-concurrency-fix-scoping
description: §8 Q11 (NEW-206 concurrency-oversubscription fix) answered by Ish 2026-08-26; design scoped desk-only, not implemented; biggest open item is a release-signal/prefix-cache-retention trap found by reading llama.cpp server source
metadata:
  type: project
---

2026-08-26: Ish answered `CODEY_MASTER_PLAN.md` §8 Q11 (the four fix
options `NEW-206`'s concurrency finding raised). Asked whether to run
option (a) first (a 65536-scale re-run targeting the two genuinely
untested gaps — fragmented-but-under-capacity failure, during-generation
collision), his verbatim answer: "lets forget about running a i think it
will just be the same thing as our last test with smaller context just do
the rest of it without doing a." (a) declined by his own judgment call,
not skipped by oversight. Chosen fix: **(c) as primary defense (resource
gate refuses admission once combined estimated context approaches the
shared pool) with (b) wired directly behind it as a serialization
backstop** — one mechanism with two behaviors, not two independent
circuit breakers, matching his own "b) as a safety AFTER c" framing.

**Scope decision:** design only this round, no code (rule 4 — this
touches resource-gate admission logic AND process/request coordination).
Design detail lives in `CODEY_MASTER_PLAN.md` §8 Q11 and
`PROJECT_LOG.md`'s 2026-08-26 entry.

**The one finding worth remembering for whoever implements this:** the
design's first-pass assumption — "release the reserved context budget the
instant the HTTP call to the server returns" — is WRONG, found on a second
design-review pass and confirmed by reading
`~/llama.cpp/tools/server/server-context.cpp` directly (not assumed from
API docs or family resemblance to a simpler mental model, per [[feedback_verify_never_assume]]-style
practice). `slot::release()` flips a slot to IDLE but its `reset()` does
NOT clear a normal (non-child) task's cached prompt tokens — the KV cells
stay resident for prefix-cache reuse across the SAME slot's future calls.
So a per-call reserve-then-release-on-return design under-counts real
occupancy in the dominant multi-turn conversation case, and
`core/inference_hybrid.py`'s own streaming path (a 15s per-read socket
timeout, a repeat-detection circuit breaker) can even return before the
server genuinely stops decoding, making "release on return" doubly wrong
in that path.

**The fix for this, confirmed viable (not just proposed) by tracing
`slot::to_json()`:** the server's own `/slots` endpoint (enabled by this
build's default, `params.endpoint_slots = true`, unmodified by this
project's spawn command) already reports each slot's real retained token
count as `n_prompt_tokens` — poll that and sum it, rather than trying to
track occupancy purely from the Python side via call-return timing. This
is genuinely a case where the server already knows ground truth and the
gate should read it rather than reconstruct it.

**Also found while enumerating reachable concurrency pairs (logged as
`NEW-207`, not fixed):** `core/daemon.py`'s `_process_planner_tasks()`
checks `can_dispatch_task()`'s `interactive_active` gate only ONCE, at
task-claim time — an already-claimed background task can run up to its
1800s timeout even if a human opens an interactive session partway
through, undermining that gate's own documented intent. The Q11 fix makes
the overlap safe but doesn't restore this gate's original policy — a
separate, narrower question for later.

**Process note:** two advisor passes were needed on this round — the
first flagged the release-signal trap and a footprint-measurement gap
(measured against the raw `SYSTEM_PROMPT` instead of the real
`prompts/layered_prompt.py::_build_draft_prompt()` `core/agent.py`
actually calls) as blocking; both were resolved by more source-reading
(not more guessing) before the round was considered done. Confirms the
project's standing pattern: a design round on rule-4-category work should
expect at least one correction pass, and "call advisor again after
addressing findings" is worth doing rather than declaring done after the
first pass looks clean.
