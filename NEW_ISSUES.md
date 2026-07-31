# New Issues Found During V3 Overhaul

## Found during NEW-10 (SIGTERM handler) implementation, 2026-07-30 — NOT fixed, logged only

### [NEW-39] `tests/test_new19_patch_failed_repeat_escalation.py`'s `_in_subtask=False` tests are fragile to a dirty git working tree on `main.py` — they fail (with a stdin-capture `OSError`, not an assertion) whenever `main.py` has real uncommitted changes at test-run time

- **Confidence: Confirmed** — reproduced directly. With a clean working
  tree, `python3 -m pytest tests/test_new19_patch_failed_repeat_escalation.py -q`
  passes all 5 tests. With the NEW-10 `main.py` diff applied but
  uncommitted (a legitimate, in-progress, unrelated change), 3 of the 5
  tests fail: `test_repeated_patch_failed_actually_calls_escalate_with_error_context`,
  `test_repeated_patch_failed_escalate_redirect_branch`,
  `test_repeated_patch_failed_escalate_skipped_falls_through_to_marker`
  — all three call `agent.run_agent(..., _in_subtask=False)`, unlike the
  two that pass (`_in_subtask=True`, or no `_in_subtask` param at all).
  Confirmed by `git stash` / `git stash pop`: stashing the uncommitted
  `main.py` diff makes all 5 pass again; popping it reintroduces the same
  3 failures, with identical output both times.
- **Root cause:** `core/agent.py`'s `run_agent()` (around line 679-694,
  `git_status_paths(files_touched)` / `ask_confirm("\nStage and commit
  ONLY the file(s) touched this turn (shown above)?")`) runs a real `git
  status` on `files_touched` at the end of a turn and, if it sees
  changes, prompts interactively via `input()` for whether to stage and
  commit. The 3 failing tests target `main.py` as the file the mocked
  `patch_file` tool call touches (an existing, deliberate choice in that
  test file, unrelated to NEW-10). This auto-commit-prompt step is *not*
  mocked/disabled in those 3 tests. In a clean tree, `git status` on
  `main.py` reports nothing pending, so the prompt is skipped entirely.
  With any real uncommitted change already sitting on `main.py` (from
  totally unrelated in-progress work, e.g. this exact NEW-10 task), `git
  status` reports it as pending, the prompt fires, `input()` tries to
  read stdin, and pytest's stdin capture raises `OSError: pytest: reading
  from stdin while output is captured!` — a hard test-harness error, not
  a meaningful assertion failure about the feature under test.
- **Impact if confirmed:** any future task that touches `main.py` and
  leaves it modified-but-uncommitted while running the full test suite
  (a completely normal workflow state — code-reviewer approval and
  commit haven't happened yet) will see these 3 tests fail with a
  confusing `OSError`, not because of anything wrong with the change
  under test. Could cost real time misdiagnosing an unrelated diff as
  having broken NEW-19's escalation logic.
- **Not fixed here:** out of scope for NEW-10 (a `main.py` SIGTERM-handler
  task). The real fix belongs in
  `tests/test_new19_patch_failed_repeat_escalation.py` itself — either
  mock/disable the auto-commit-prompt path (e.g. mock `ask_confirm` or
  `git_status_paths`) for the `_in_subtask=False` tests the same way the
  other tests in that file already mock `agent.infer` and
  `core.peer_cli.escalate`, or have those tests operate on a scratch
  file instead of the live `main.py` so a dirty tree on the real
  `main.py` can't leak into `git_status_paths(files_touched)`.

### [NEW-40] NEW-10's new SIGTERM handler covers the 4 model-load `try/except (KeyboardInterrupt, SystemExit)` guards in `main.py`, but the REPL's steady-state `input()` wait has an existing SIGINT-only guard that does NOT catch the new SystemExit — a real asymmetry, not parity with SIGINT

- **Confidence: Confirmed** — read directly from `main.py`'s current
  structure. Only 4 of the 14 `shutdown()` call sites in `main.py` are
  reached via an `except (KeyboardInterrupt, SystemExit):` clause: the
  `loader.load_primary()` guards in `repl()` (~line 1271) and the
  `args.init`/`--tdd`/`--fix` branches (~lines 1467, 1479, 1504). The
  other 10 `shutdown()` calls are plain sequential calls on a success
  path, not exception guards, and are irrelevant to signal handling.
- **Correction (rule 6):** this entry originally claimed the REPL's
  main `input()` wait (line 1362, `except (KeyboardInterrupt, EOFError):`)
  was "same as SIGINT already does today" — **false, caught by
  code-reviewer**. Read directly: that clause DOES catch
  `KeyboardInterrupt` and DOES call `shutdown()` (lines 1363-1365)
  before `break` — `SIGINT` at the idle `input()` prompt is fully
  cleaned up today. It does NOT include `SystemExit` in its caught
  tuple, so `SIGTERM`'s new `raise SystemExit(143)` (from `NEW-10`)
  propagates past it uncaught, exiting without `shutdown()` running.
  This is a real asymmetry — `SIGINT` is covered there, `SIGTERM` is
  not — not equivalent behavior as originally stated. The separate
  initial-prompt non-one-shot branch (~line 1335, `except
  KeyboardInterrupt:`, no `finally`) is different again: it doesn't call
  `shutdown()` for `SIGINT` there either (just prints "Interrupted." and
  falls through into the REPL loop below), so this isn't a cleanup
  asymmetry versus `SIGINT` specifically — but it's still a real
  control-flow gap: `SIGINT` there is absorbed and the process continues
  into the REPL loop (reaching the covered site above on a later
  interrupt), while `SIGTERM`'s `SystemExit` propagates straight out of
  `main()`, skipping the loop and any later chance at cleanup entirely.
- **Where found:** while implementing NEW-10's `SIGTERM` handler in
  `main.py` (this round), an advisor review caught that NEW-10's task
  framing ("14 existing guards") did not match the actual code (`grep -n
  "except (KeyboardInterrupt, SystemExit)" main.py` shows only 4
  matches). Code-reviewer's independent pass then caught this entry's
  own "same as SIGINT" mischaracterization before commit.
- **Impact:** NOT a regression relative to pre-`NEW-10` behavior —
  `SIGTERM` at the `input()` wait was `SIG_DFL` (unconditional
  kernel-level termination, zero cleanup) before this round, and still
  results in no `shutdown()` running after this round (just via an
  uncaught `SystemExit` instead of a raw kernel kill — same net
  cleanup outcome, zero either way). But it IS a real, live gap: a
  `kill -TERM` sent to an idle interactive session (the common case for
  a human deliberately stopping one, and likely more commonly hit than
  the mid-model-load window `NEW-10` specifically targets) still won't
  get a clean `llama-server` unload today, while `Ctrl-C` at that exact
  same moment already does.
- **Not fixed here:** deliberately out of scope for NEW-10, which
  required not touching the existing `try/except` structure at any of
  the 14 `shutdown()` call sites. Closing this gap would mean either (a)
  adding `SystemExit` to the two uncovered `except` clauses (lines
  ~1335, ~1362) — itself a small, reviewable process-lifecycle change
  under CLAUDE.md rule 4 — or (b) a broader refactor wrapping `repl()`'s
  whole body in one outer `try/except (KeyboardInterrupt, SystemExit):
  shutdown()`. Needs its own scoped task and code-reviewer approval; not
  attempted here.

## Found during NEW-19 code-review (patch-failed repeat-escalation), 2026-07-30 — NOT fixed, logged only

## Found during NEW-19 live-verification, 2026-07-30 — NOT fixed, logged only

### [NEW-38] `[PATCH_FAILED, UNRESOLVED]` marker doesn't survive into saved-session `history` (Confirmed) — same append site suggests NEW-2's `[EDIT NOT APPLIED]` has the identical gap (Suspected, by code inspection only, not separately live-reproduced)

- **Confidence: Confirmed for the `[PATCH_FAILED, UNRESOLVED]` half** —
  reproduced live via a scripted `run_agent()`/`main._run_with_plan()`
  session, including confirming the marker genuinely reaches the
  `messages` list handed to the mocked `infer()` on the very next model
  call (not merely inferred from the append-site code — the driver
  printed the actual `messages` content seen by `infer()` and it
  contained the marker verbatim). **Suspected only, by code inspection,
  for the NEW-2 `[EDIT NOT APPLIED]` half** — that specific case (a
  file-mutating tool call still in an error state after retries/
  escalation exhausted) was not separately live-reproduced this round;
  the claim that it has the identical history-persistence gap rests on
  it sharing the same `_edit_not_applied_prefix` variable and the same
  final `history.append()` site (`core/agent.py:1989-1990`), not on a
  live run of that specific branch.
- **Where found:** live-verifying NEW-19's end-to-end wiring (this round).
  `core/agent.py`'s repeated-`[PATCH_FAILED]` branch (~line 1940-1949)
  folds the `[PATCH_FAILED, UNRESOLVED] ...` marker into
  `_edit_not_applied_prefix`, which is appended only to the in-turn
  `messages` list (`messages.append({"role": "user", "content":
  _edit_not_applied_prefix + "Tool result: " + ...})`, ~line 1953) — the
  local variable used to drive the current turn's model calls. But the
  `history` list returned by `run_agent()` (and saved to disk by
  `save_session()`) only ever gets two entries appended at the very end
  of the function, at `core/agent.py:1989-1990`: the original
  `user_message` and the final `response` string. The marker text is
  never one of those two things in this fallthrough path — it lives only
  inside `messages`, which is local to the turn and discarded when
  `run_agent()` returns.
- **Live reproduction:** drove a 2-declined-escalation session; the
  console/log showed the marker fire twice (verified via
  `agent.log_error` capture); `json.dumps(history, indent=2)` on the
  actual returned `history` showed only:
  ```json
  [
    {"role": "user", "content": "add a docstring to shutdown function in main.py"},
    {"role": "assistant", "content": "Please clarify the correct old_str for shutdown() (attempt 2)."}
  ]
  ```
  No occurrence of `[PATCH_FAILED, UNRESOLVED]` anywhere in `history`.
- **Why this matters:** NEW-19's own design intent (per its code comment
  at ~line 1926-1928, inherited from NEW-2's original design) was
  explicitly "fold the marker into the transcript itself (not just the
  console/log) so it survives in `history` for later review." That intent
  is not met for either marker in this fallthrough path — a
  user/reviewer reopening a saved session later would see no trace that
  an edit was attempted and dropped, only whatever the model's final
  clarifying text happened to say (which may not mention the failure at
  all). This appears to affect NEW-2's `[EDIT NOT APPLIED]` marker
  identically, since it's folded into the same `_edit_not_applied_prefix`
  variable via the same append site — not unique to NEW-19's new branch.
- **Not fixed here** — out of scope for a verification pass per CLAUDE.md
  rule 8 (log, don't silently fix). A fix would need to append the
  marker text into `history` explicitly (e.g. as a distinct system/
  assistant entry, or prepended into the final `response`/`history`
  assistant entry) rather than relying on `messages`, which is scoped to
  the turn.


### [NEW-36] The pre-existing verbatim-duplicate-tool-call guard bypasses NEW-19's repeat-`[PATCH_FAILED]` escalation entirely for the more common LLM failure mode (Confirmed)
- **Confidence: Confirmed** — verified by reading the actual code paths,
  not inferred. Found during code-reviewer's adversarial pass on
  `NEW-19`'s implementation.
- **Where found:** `core/agent.py`'s pre-existing `duplicate_count` guard
  (lines ~1645-1667, untouched by `NEW-19`) intercepts a byte-identical
  repeated tool call *before* `execute_tool()` runs. On the 2nd identical
  repeat it returns early with `"Done. " + last_tool_result[:300]` —
  misrepresenting a still-failed `[PATCH_FAILED]` result as success — and
  short-circuits before `execute_tool()` is re-invoked.
- **Why this matters:** `NEW-19`'s new repeat-`[PATCH_FAILED]` escalation
  logic (`patch_failed_counts`) only increments when `execute_tool()`
  actually runs again, which requires the model to vary `old_str` between
  attempts. When the model instead retries with the byte-identical
  `old_str` (arguably the more common LLM failure mode for this class of
  error), the duplicate-guard's "Done." short-circuit fires first,
  `NEW-19`'s counter never increments, and the false "Done." message
  likely makes the model believe the patch succeeded — a worse outcome
  than either the old bypass-forever behavior or `NEW-19`'s new
  escalation path. `NEW-19` materially narrows but does not close this
  gap.
- **Not fixed here** — pre-existing bug, not introduced by `NEW-19`;
  needs its own scoping pass (likely: should the duplicate-guard's
  "Done." short-circuit itself check for a `[PATCH_FAILED]`-prefixed
  `last_tool_result` and route to escalation/marker logic instead of
  claiming success?).
- **Addendum (Round 20, NEW-7 live session, 2026-07-30):** live
  corroboration that this guard is not `patch_file`-specific — it fired
  on a repeated, byte-identical `read_file` call during `b3` (see
  `NEW-7`'s Round 20 entry above), producing the same "Done. " +
  truncated-result short-circuit and the same synthetic
  "Task complete. Reply with 1 sentence only." injection, which directly
  caused the model's "Done." reply without any `patch_file` attempt.
  Confirms the guard's `sig = name + ":" + json.dumps(args,
  sort_keys=True)` keying (`core/agent.py:1645`) applies to any tool, not
  just `patch_file` — widens this entry's scope slightly but doesn't
  change its severity assessment.

### [NEW-37] `NEW-19`'s repeat-escalation now feeds `[PATCH_FAILED]` file-content text into `peer_cli.py`'s task-type keyword matching, and reuses `escalate()`'s fixed "exhausted its retry budget" wording even though retries were never entered for this path (Suspected)
- **Confidence: Suspected** — low-severity, not live-verified, logged per
  CLAUDE.md rule 8 rather than fixed silently during `NEW-19`'s review.
- **Where found:** `NEW-19` (`core/agent.py`) now appends
  `[PATCH_FAILED]` result text (which embeds up to 300 chars of the
  target file's actual content) into `error_log`, which previously only
  ever contained `is_error()`-matched failures. `error_log` flows into
  `core.peer_cli.escalate(user_message, error_log, files_touched)` →
  `detect_task_type()`'s fallback keyword match and `build_prompt()`'s
  fixed prompt wording.
- **Why this matters (two distinct sub-issues, both minor):**
  1. File content text (not error text) now participates in
     `detect_task_type()`'s fallback keyword match, worst case causing a
     suboptimal peer-CLI selection — bounded impact (only a fallback
     after `user_message` checks), not a safety issue.
  2. `build_prompt()`'s fixed wording ("exhausted its retry budget") is
     factually false for the `[PATCH_FAILED]`-repeat case, since
     `[PATCH_FAILED]` deliberately never enters the retry gate. This is
     inherited as-is from reusing the shared `escalate()` path, per
     `NEW-19`'s recorded design decision to reuse the existing
     escalation mechanism rather than build a parallel one.
- **Not fixed here** — needs its own scoping pass if `peer_cli.py`'s
  prompt wording is judged worth making conditional on escalation
  reason, rather than fixed text shared across all callers.

## Found during Track 1 prompt audit (system_prompt.py, layered_prompt.py, critique_prompts.py, plannd.py PLANNER_PROMPT), 2026-07-30 — NOT fixed, logged only

### [NEW-28] `_TOOL_VERBS` regex in `core/plannd.py` has no `edit` alternative — `filter_tool_steps` can silently drop legitimate "Edit <file>: ..." steps
- **Status: Confirmed, not fixed (code, not prompt text — out of this audit's
  scope, which covered `PLANNER_PROMPT` the string, not `filter_tool_steps`).**
  `PLANNER_PROMPT` explicitly instructs the 1.5B planner to emit `Edit <file>:
  ...` steps (STEP TEMPLATES, RULES #2). `filter_tool_steps` (plannd.py:130-162)
  keeps a non-first step only if it matches `_TOOL_VERBS`
  (`create|write|build|add|run|execute|install|verify|check|test|confirm|update
  |delete|remove|ask|have|use|tell|call|let|get|initialize|init|commit|push`),
  contains `Run:`/`Verify`/`Check`, or names a peer CLI. `edit` is not in that
  list, so an `Edit foo.py: ...` step at position 2+ fails all three checks and
  is dropped — unless a fallback happens to retain it. Recommend adding
  `edit` to `_TOOL_VERBS` as a follow-up code fix.
- **Update 2026-07-31 (live-verifier, 1.5B-only planner session, mechanism
  sharpened, status unchanged — still Confirmed, not fixed):** live-reproduced
  via a direct test prompt requiring an Edit step at position 2 of a
  Create → Edit → Run plan. The model correctly emitted
  `Edit foo_utils.py: add a docstring...` at position 2; `filter_tool_steps`
  dropped it. Traced the exact mechanism against the real code
  (`core/plannd.py:162`, `return kept if len(kept) > 1 else steps[:2]`):
  the Run step matches both the `_TOOL_VERBS` list (`run` is a listed
  verb) and the separate `Run:` regex, and survives into `kept` alongside
  the Create step, so `kept == [Create step, Run step]`, `len(kept) == 2`,
  and the `len(kept) > 1` condition is **True** — meaning the function
  returns `kept` itself (missing the Edit step), and the `steps[:2]`
  fallback (the `else` branch) never runs. The fallback only rescues a
  dropped step when *nothing else* survives (`len(kept) == 1`, i.e. only
  the first/Create step). Consequence: **more complete, well-formed plans
  (Create → Edit → Run) are the ones most likely to silently lose their
  Edit step**, since it's precisely the Run step's own survival that
  suppresses the one mechanism that would otherwise catch the loss.
  **Repro-recipe caveat:** this round's repro prompt produced
  `Edit foo_utils.py: add a docstring...` — phrasing close to the
  `core/voice.py` few-shot example that `NEW-46` (below) identifies as a
  source of leaked content. This doesn't weaken this finding (the filter
  drops a well-formed Edit step regardless of why the model emitted that
  particular wording), but if the planned `PLANNER_PROMPT` rewrite
  changes or removes those few-shot examples, this exact repro prompt
  may stop reproducing and would need re-deriving.

### [NEW-29] `orchestrator.py`'s `PLAN_PROMPT` diverges from `plannd.py`'s `PLANNER_PROMPT` on Edit-step format, and neither wires filenames/step verbs identically
- **Status: Confirmed, not fixed (out of the 4-file audit scope; touching
  `orchestrator.py` is a design call).** `orchestrator.py:14` only says
  "edit a file" generically with no `Edit <file>: <change>` template, no
  filename-fidelity section, and no verb-consistency enforcement, unlike
  `PLANNER_PROMPT`'s dedicated "CRITICAL RULE: FILENAMES AND PATHS" section.
  Two planner prompts for the same downstream 7B executor should use the
  same step-verb vocabulary; recommend either unifying them or explicitly
  documenting why they differ.

### [NEW-30] Adding "Edit" to `system_prompt.py`'s word→tool mapping (this round's fix) enables a step type that still needs two tool calls, contradicting the "exactly one tool call per response" rule
- **Status: Confirmed, not fixed — needs a design decision plus live-model
  validation.** An Edit step on a file the 7B model hasn't already read
  requires `read_file` then `patch_file` (two calls), but
  `system_prompt.py:55` and `:138` mandate the response is "always exactly
  one tool call," while `:207` separately requires reading before editing
  any unread file. This contradiction only bites on Edit steps — i.e.
  exactly the path this round's mapping fix (see report) now routes traffic
  through. Recommend either a documented two-call exception for Edit steps,
  or having the orchestrator pre-inject the target file's content into Edit
  step context so a single `patch_file` call suffices. Needs live-verifier
  confirmation once a fix is chosen.
- **Correction (rule 6), 2026-07-31 desk review for the 7B system-prompt
  scoping round:** the "needs a design decision" framing above is now
  partially stale — a documented two-call exception for unread files
  already exists in the current `system_prompt.py` text (the "PATCH_FILE —
  old_str MUST BE REAL FILE CONTENT" section, ~lines 216-219: "Never seen
  this file's real content yet ... Your ONE tool call this turn is
  `read_file` ... Emit the patch on your NEXT turn"). That text appears to
  have landed incidentally via the `NEW-7` old_str-grounding fix (commit
  `0026565`), not as a deliberate NEW-30 fix. **The contradiction is not
  resolved, only relocated**: `:143-146` ("AFTER THE TOOL RUNS: IF the tool
  succeeded with no error → Respond with exactly: Done.") and `:156`
  ("Never call extra tools to inspect, verify, or re-run after a step
  succeeds") both still instruct the model to end the step after a
  successful `read_file`, directly conflicting with ":218"'s "emit the
  patch on your NEXT turn" — i.e. the model has two contradictory
  instructions for what to do immediately after a successful `read_file`
  on an unread-file Edit step. This sharper framing (not the original
  "make a design decision" framing) is the anchor hypothesis for the
  live-test round scoped below; still Confirmed by static read, not yet
  live-model-validated.
- **Correction (rule 6), 2026-07-31, first live pass (7B-only, port 8080,
  one clean load/unload cycle, PID-tracked — RAM/PID compliance relayed
  from live-verifier's report, not independently witnessed here):** the
  static contradiction identified above is still real by direct text
  read (`:143-146`/`:156` vs. `:216-219` remain unchanged, uncommitted).
  What the live pass actually tested — whether the model says "Done."
  immediately after a successful `read_file` on an unread-file Edit step
  — did **not** reproduce in any completed trial. **Exact accounting:**
  6 trials attempted total. Case 1 (genuinely-unread-file Edit step): 3
  trials, all reached a terminal state — trial 3's terminal state was a
  crash (see new `NEW-55` below), not a model-chosen ending. Case 2
  (control — file content already in prompt context, no read-then-edit
  ambiguity should have existed at all): 3 trials attempted, only 2
  reached a terminal state (trial 3 was cut off by the test harness's own
  timeout, not a model-chosen ending). **Of the 4 trials that ran to a
  model-chosen ending (2 from case 1, 2 from case 2), `patch_file` was
  never called in any of them**; it also did not appear in case 1's
  crashed trial before it crashed. Specifically: one trial called
  `write_file` at a wrong path with the file's existing functions dropped
  from the written content (see new `NEW-56` below), one called
  `write_file` at a completely fabricated path, one gave up with "Done."
  after a blocked `shell` call, and one produced zero tool calls at all.
  **This means the fix's hypothesis is not supported as stated — the
  predicted symptom didn't occur, but neither did the intended fixed
  behavior (read_file → patch_file), including in the control case that
  needed no fix at all.** The live-verifier's own hypothesis (not yet
  confirmed, separate desk investigation in progress, not established by
  this pass) is that these trials ran through `core/recursive.py`'s
  critique/refine layer, meaning the observed tool sequences would be
  post-critique output rather than the model's raw draft; the
  critique/refine layer may be converting or discarding a
  correct draft `patch_file` proposal, or `layered_prompt.py`'s
  priority-based layer eviction may be dropping the identity layer
  carrying this round's fix from the composed prompt on this path
  entirely. **Status: NOT fixed. The prompt diff remains
  code-reviewer-approved but held back, unstaged and uncommitted,
  pending the separate desk investigation into recursive-critique/
  prompt-composition behavior — do not read this correction as either
  confirming or refuting the fix.**
- **Correction (rule 6), 2026-07-31, desk investigation into the
  recursive critique/refine hypothesis (project-architect, no code
  changed):** the "recursive critique/refine layer discarded the draft's
  `patch_file` proposal" hypothesis from the correction above does
  **not** survive verification and should not be treated as NEW-56's
  mechanism. Two independent gates rule it out for the trials actually
  observed:
  1. `core/agent.py:1489`'s `_use_recursive = step == 1 and not is_qa
     ...` — `step` is the agent's own tool-execution turn counter
     (incremented once per `while step < max_steps` iteration,
     `agent.py:1477-1478`), not the plan-step number. Recursion (draft +
     critique + optional refine) only ever runs on the **first turn** of
     a `run_agent` call. NEW-56's trial 1 sequence was `read_file` →
     `shell` → `shell` → `note_save` → `write_file` — the bad
     `write_file` was the agent loop's **5th** turn; trial 2's bad
     `write_file` was its **2nd**. Neither ran through recursion at all —
     both went through plain `infer()` with full conversation history,
     per the `else` branch at `agent.py:1528-1535`.
  2. Even on turn 1, `core/recursive.py`'s refine phase (`:512-532`) is
     unreachable for a normal single-file Edit task. `classify_breadth_need()`
     (`recursive.py:138-165`) returns `"standard"` (not `"deep"`) unless
     the message is >50 words or hits ≥3 deep-complexity signals, and
     `agent.py:1509` sets `max_depth = 1` for anything other than
     `"deep"`. With `max_depth=1`, `recursive_infer`'s loop
     (`recursive.py:434`, `range(1, max_depth+1)`) runs exactly one
     critique pass; the `if cycle >= max_depth:` branch (`:485-498`,
     which sits **above** the refine block at `:516`) always fires first
     and breaks before refine ever executes. Refine only becomes
     reachable at all when the user message classifies as `"deep"`.
  **Net effect: the anchor hypothesis handed into this round's desk
  investigation is refuted for the specific trials that produced
  NEW-56.** The refine-blindness bug described in the prior correction
  is still real by code read (see new `NEW-58` below) but is latent —
  not the cause of what was actually observed live. See new `NEW-57` for
  the more promising candidate mechanism (an `agent.py` gap, not a
  `recursive.py` one), and `WORK_QUEUE.md`'s "7B coder system-prompt
  round" entry for the corrected next steps.

### [NEW-31] `CRITIQUE_TOOL` and `CRITIQUE_PLAN` templates in `prompts/critique_prompts.py` are defined but never invoked — `select_critique_prompt()` has no callers
- **Status: Confirmed, not fixed (wiring it up is a behavior change beyond
  a wording fix).** `_build_critique_prompt` in `layered_prompt.py` hardcodes
  `CRITIQUE_CODE` for every critique-phase call; nothing in the codebase calls
  `select_critique_prompt()` except a comment reference in
  `orchestrator.py:341`. The module docstring's claim that "Three templates
  cover the main task types" is not true of current behavior — tool-call
  critiques and plan critiques both get the code-review template. Recommend
  either wiring `task_type` through `core/recursive.py` → `build_recursive_prompt`
  → `_build_critique_prompt`, or removing the unused templates/docstring claim.

### [NEW-32] `LayeredPrompt.add()`/`build()` in `prompts/layered_prompt.py` don't enforce layer-name uniqueness, which risks double-counting budget once Phase 5b adds tier-specific layers
- **Status: Suspected, not fixed — not triggerable today, flagged because
  Phase 5b is the change most likely to trigger it.** `build()` selects
  included layers into a `set[str]` of names, then restores insertion order
  with `[l for l in self._layers if l.name in selected_names]`. If two
  layers ever share a `name`, both would render in the final output while
  only one was charged against `self._budget` during the greedy pass — a
  silent budget-accounting bug. Currently unreachable (the only conditionally
  re-added name, `retrieval`, is added via if/elif so it can't collide with
  itself), but Phase 5b's stated plan of adding tier-specific prompt layers
  is exactly the kind of change that could introduce a name collision.
  Recommend `add()` raise or overwrite on duplicate `name` before 5b lands.

## Found during live-verifier's 1.5B-only planner test session, 2026-07-31 — NOT fixed, logged only (cross-references the Track 1 prompt audit above, NEW-28/29/30/31/32)

This round was read-only measurement of `core/plannd.py`'s `PLANNER_PROMPT`
against the real 1.5B model on port 8081, reported as two clean
model-load cycles with RAM tracked before/after and exact spawned PIDs
killed per rule 3, 7B never loaded. (This logging pass did not itself
witness the literal `free -h`/`ps aux` output — it is relaying the
live-verifier's reported compliance, not reproducing verbatim numbers
here.) No code or prompt text was touched this round — findings below
are inputs to a same-session `PLANNER_PROMPT` rewrite about to be scoped
to prompt-engineer.

### [NEW-46] Planner few-shot content leakage on edit-only prompts that don't use the literal "Edit `<file>`: `<change>`" surface form from `PLANNER_PROMPT`'s STEP TEMPLATES (Confirmed)
- **Status: Confirmed — live-verified 2026-07-31, discriminating repeat
  test (3/3 vs. 3/3), not a one-off.** When a user's edit-only request is
  phrased naturally instead of matching the template literally (test
  prompt: "Fix the off-by-one error in the loop in `core/legacy_calc.py`"),
  the 1.5B model does not reason about the actual request at all — it
  fabricates an unrelated Create → Edit → Run → Verify plan, with step
  content copied **verbatim** from `PLANNER_PROMPT`'s own embedded
  few-shot examples: "prints each Fibonacci number" (from the fibonacci
  example), "add a docstring to the speak function" (from the
  `core/voice.py` example), and "tally.json contains exactly 2 entries
  with timestamps" (from the `xform.py` example) — none of which appear
  anywhere in the user's actual prompt.
- **Not a filename-fidelity bug.** Filenames are still copied correctly
  into the fabricated steps, including a `core/` subdirectory prefix —
  the fabrication is specifically in step *content*, not filenames.
- **Discriminator (why this is Confirmed, not Suspected):** the identical
  underlying task phrased naturally produced this fabricated plan in 3/3
  trials. The same task re-phrased to literally match the template
  ("Edit `core/legacy_calc.py`: fix the off-by-one error in the loop")
  produced a correct, minimal, single-step plan in 3/3 trials. This
  isolates the trigger to the surface-form mismatch, not to the task
  itself or to model noise.
- **Why this matters — a real data-loss path, more severe than
  [NEW-28]:** if the 7B agent executed the fabricated
  "Create `core/legacy_calc.py`: ..." step as a Create/overwrite against
  an *existing* repository file, it would destroy that file's real
  content in service of what was actually a one-line bugfix request.
  NEW-28's failure mode is a dropped step (an omission); this one is
  active destructive fabrication.
- **Not fixed here** — logged as the primary input to the planned
  `PLANNER_PROMPT` rewrite (same session, prompt-engineer).
- **2026-07-31 update (same session, later):** the specific trigger
  described above — surface-form mismatch against the literal
  "Edit `<file>`: `<change>`" template — is now fixed and live-verified
  in the rewritten (still **uncommitted**) `PLANNER_PROMPT`: iteration 4's
  regression guard re-ran this exact test prompt 3 times and got 2/3
  pass. **However, the 1/3 failure was not a return of this same bug** —
  it leaked verbatim content from a different, plain (non-labeled-wrong)
  example elsewhere in the prompt. That is now tracked separately as
  `NEW-50` (a broader leakage finding, not yet fixed). Do not mark this
  entry fully closed on the strength of the 2/3 pass alone; see `NEW-50`
  for the open remainder.

### [NEW-47] Planner appends an unrequested `Run:` step, violating `PLANNER_PROMPT`'s own Rule 8 ("never invent capabilities") — RESOLVED for this decisive case, 5/5 live-verified 2026-07-31, uncommitted
- **Original status (superseded, kept for history): ~~Confirmed as an
  observation, but single-occurrence (n=1) — not yet repeat-tested, so
  weight it below [NEW-46]'s 3-vs-3 discriminated result when
  prioritizing the prompt rewrite.~~** Test prompt: "create a file, then
  ask claude to review it." The model appended an unrequested
  `Run: python report_gen.py data.json` step that the user never asked
  for, directly contradicting `PLANNER_PROMPT` Rule 8 ("Never invent
  capabilities. Only describe what the user explicitly stated.").
- **Full oscillation history across this session's 4-iteration
  `PLANNER_PROMPT` rewrite (rule 6 — recording so a future session doesn't
  re-litigate from scratch):**
  - Original finding: fail, 1/1 (n=1, above).
  - Iteration 1: fail, 3/7 — attempted a fix, but the same change caused a
    separate NEW regression (repeated-`Run` under-generation: "run it
    three times" produced only 1 `Run` step, confirmed via live A/B
    against pre-fix HEAD text).
  - Iteration 2: pass, 3/3 — but this pass was measured under
    `max_tokens=512`, not the real/pinned `max_tokens=1024` used
    elsewhere, so it is **not a fully comparable measurement** to the
    other rounds. (Iteration 2 also separately fixed the repeated-`Run`
    regression, live-confirmed 3/3, and found the unrelated sole-step
    peer-CLI delegation truncation bug fixed in iteration 3.)
  - Iteration 3: fail, 3/3, deterministic — re-tested with the properly
    pinned config this time (`max_tokens=1024`, `temp=0.2`) and failed
    every run. Traced to the model copying a VIOLATION (✗-labeled)
    example's own spelled-out wrong transcript verbatim into the plan — a
    content-leakage mechanism, not a logic failure.
  - Iteration 4 (pure deletion, no additions): removed that specific
    leaking VIOLATION example and its paired correct example. Final
    live-verify on this decisive case: **5/5 pass**, pinned config
    (`max_tokens=1024`, `temp=0.2`). Caveat: the 5 outputs were
    byte-identical — one dominant decode mode being sampled repeatedly,
    not five fully independent draws — so treat this as a clean flip from
    deterministic-fail to deterministic-pass-on-this-decode-path, not as
    5 independent confirmations.
- **Current state:** this specific decisive case is resolved — code
  complete and live-verified 5/5 — but **uncommitted**; the fix sits in
  the working tree pending a commit decision from Ish. The underlying
  leakage *mechanism* (verbatim copying from worked examples) is
  understood and was fixed here by deletion for this one example, but a
  **broader form of the same mechanism, sourced from a different, plain
  example, was found in this same round's regression testing** — see
  `NEW-50`. Do not read this entry as closing that broader class; it
  closes only this specific `Run:`-step case.

### [NEW-48] `parse_steps()`'s truncation-warning heuristic false-positives on well-formed, correct plans (Confirmed, code not prompt)
- **Status: Confirmed — 8/8 test prompts in the live-verifier's first run
  tripped this warning, including plans independently judged clean and
  correct.** `core/plannd.py`'s `parse_steps()` flags possible truncation
  by checking whether the last step's final character is alphabetic and
  not in `.!?)"`. This trips on any well-formed `Run:`/`Verify:` step that
  happens to end in a lowercase noun — e.g. `Run: python dice_roller.py`
  (ends in "y") and `Verify: counter.py printed exactly 10 lines` (ends
  in "s") both tripped it despite being complete, correct steps with
  nothing actually truncated.
- **This is code, not `PLANNER_PROMPT` text** — out of the planned prompt
  rewrite's scope. Recommend a follow-up code task loosen or drop this
  heuristic rather than continuing to chase it as a real truncation
  signal; at an 8/8 false-positive rate on this sample it is not
  distinguishing truncated from complete output.
- **Not fixed here.**

### [NEW-49] `daemon.py` step-1 plan enrichment hardcodes Create/full-rewrite semantics regardless of the step's actual verb (Suspected)
- **Status: Suspected — code-reviewer's own confidence level, from static
  analysis and logical inference only, not live-reproduced.** Found during
  code-reviewer's review of this session's `core/plannd.py`
  `PLANNER_PROMPT` rewrite (targeting [NEW-46]/[NEW-47]) and `_TOOL_VERBS`
  regex fix ([NEW-28]).
- **Location:** `core/daemon.py`, lines ~166-194 — the
  `if steps and len(steps) > 1:` branch's `else` clause, specifically the
  `for i, step in enumerate(steps): if i == 0: ...` block.
- **Mechanism:** the branch keys purely on position (`i == 0`), not on the
  step's actual verb. Its own comment says "Step 1: full context — the
  executor needs all requirements to write the code," assuming step 1 of
  any multi-step plan is always a Create. Regardless of what `steps[0]`
  actually is, a 2+-step plan always gets step 0 rewritten to append:
  "Write the COMPLETE file with ALL features described above. Do not skip
  any requirement." That is a full-file-overwrite directive — correct for
  a genuine Create step, but actively harmful if `steps[0]` is really an
  Edit step, since it tells the 7B executor to rewrite the entire file
  from scratch instead of making a targeted change (the same
  overwrite/data-loss shape [NEW-46] fixed at the planner-prompt level).
- **Why newly reachable / relevant now:** before this session's
  `PLANNER_PROMPT` rewrite, the 1.5B planner rarely produced faithful
  multi-step Edit-first plans (it tended to hallucinate steps or add
  spurious ones instead — see [NEW-46]/[NEW-47]). The rewrite specifically
  fixes the planner to produce correct multi-step plans including
  Edit-first ones (e.g. "Edit foo.py to add X, then run the tests") —
  meaning this `daemon.py` code path, previously rarely exercised with an
  Edit-first plan, is now the common path for that request shape.
- **Suggested fix direction (not done here):** branch the step-1
  enrichment text on the step's actual verb (detect Create vs Edit vs
  Run/Verify per step) instead of assuming position 0 is always Create. A
  live test with an Edit-first 2-step plan should confirm the executor no
  longer receives full-rewrite instructions for an edit task before this
  is marked resolved.
- **Not fixed here.**
- **Update, 2026-07-31, first live pass of the 7B system-prompt round:**
  the planned live test (daemon step-0 Create-style enrichment applied to
  an actual Edit-verb step, "case 3" of the test matrix) was never
  reached — the pass ran out of its inference-time budget (7B is slow on
  this device, ~260-450s/trial) partway through case 2. **Still
  Suspected, neither confirmed nor refuted this round; needs its own
  dedicated model-load cycle.**

## Found during the 2026-07-31 `PLANNER_PROMPT` 4-iteration rewrite + live-verify round (prompt text changed, uncommitted)

The section above (`NEW-46`/`NEW-47`/`NEW-48`) came from a read-only
live-verifier pass with no code or prompt text touched. This section is
different: prompt-engineer went through 4 iterations of edits to
`core/plannd.py`'s `PLANNER_PROMPT` this same session (targeting
`NEW-46`/`NEW-47`, plus an implementer fix to `_TOOL_VERBS` for `NEW-28`),
each followed by code-reviewer review and a live-verifier re-test.
**As of this entry, none of these edits are committed** — the diff sits
uncommitted in the working tree, and the commit decision is pending with
Ish directly. Treat "live-verified" below as verified against the current
uncommitted working-tree prompt text, not against `HEAD`.

### [NEW-50] `PLANNER_PROMPT`'s worked examples leak verbatim content into unrelated user requests regardless of ✓/✗ labeling — confirmed from a plain correct example, not just violation-labeled ones (Confirmed; mechanism verbatim-traced; frequency 1/3 on this prompt)

- **Status:** Confirmed. Not deterministic at the frequency observed —
  1 failure in 3 trials on the exact regression-guard prompt that
  iteration 4 was believed to have fixed (`NEW-46`'s original test
  prompt: "Fix the off-by-one error in the loop in
  `core/legacy_calc.py`").
- **Relationship to `NEW-46`:** `NEW-46` (above) identified the first
  confirmed instance of this leak pattern — verbatim step content copied
  from `PLANNER_PROMPT`'s embedded few-shot examples into a plan for an
  unrelated real request. Iteration 3 of this session's rewrite traced a
  failure of the fix-in-progress to the model copying a **VIOLATION
  (✗-labeled)** example's own spelled-out wrong transcript verbatim, and
  iteration 4 fixed that specific instance by deleting the leaking
  VIOLATION example and its paired correct example (see the corrected
  `NEW-47` entry below for the full oscillation history — same rewrite,
  different specific bug). The final iteration-4 live-verify re-ran
  `NEW-46`'s original regression-guard prompt 3 times as a guard against
  reintroducing that fixed leak, and got 2/3 pass, 1/3 fail — but the
  1 failing run leaked from a **different, plain (non-labeled-wrong)**
  example elsewhere in the prompt, not the one that was just deleted.
- **Mechanism (verbatim-traced):** the failing output's fabricated step
  content is a byte-for-byte verbatim match to `PLANNER_PROMPT`'s
  fibonacci example (around lines ~127-128 of the current uncommitted
  prompt text), welded onto the user's real filename
  (`core/legacy_calc.py`) with an unrequested prepended `Create` step —
  i.e. structurally identical to `NEW-46`'s original failure mode, just
  sourced from a different, correctly-labeled example instead of a
  ✗-labeled VIOLATION example.
- **Why this is a distinct, broader finding, not the same bug as
  `NEW-46`/iteration-4's fix:** iteration 4's fix (deleting one leaking
  VIOLATION example) closed that specific leak source and is itself
  live-verified clean on its own decisive test (see corrected `NEW-47`
  entry, 5/5). But this same round's regression guard shows the
  underlying leakage mechanism — the 1.5B model pattern-matching and
  copying literal content from *any* worked example in the prompt,
  regardless of ✓/✗ labeling, when it should be reasoning about the
  actual request — is a general property of this prompt's structure
  (many long, content-rich worked examples), not something fixed by
  removing one example. Deleting every individual leak source found this
  way does not scale; the prompt's example-density/structure is the
  likely real lever.
- **Not fixed here.** Logged as a new, separate open issue from the
  now-closed (for its own specific case) `NEW-47`. A future prompt round
  should treat "does this new edit leak content from an unrelated
  example" as a standing regression class to test for, not a one-off.

### [NEW-51] Rule 9 peer-CLI delegation format fails entirely (0/3, no delegation step emitted) on a fresh phrasing not matching prior tested patterns (Confirmed; deterministic; causal link to this session's changes not established)

- **Status:** Confirmed — deterministic, 0/3 across 3 trials. Explicitly
  **not** claimed as a regression from this session's `PLANNER_PROMPT`
  edits: this exact prompt was never tested before this round, so there
  is no pre-session baseline to compare against, and no causal link to
  this session's changes should be inferred from this entry alone.
- **Test prompt (verbatim):** "Have gemini check payment_processor.py
  for race conditions."
- **Result:** the planner produced no delegation step at all (no
  `Ask gemini ...`-shaped step per `PLANNER_PROMPT`'s Rule 9). Instead it
  treated the request as a Create task, fabricating a plan to create
  `payment_processor.py` from scratch — the request was to have a peer
  CLI *check* an existing file, not create one.
- **Contrast — phrasing that does work:** iteration 3 of this session's
  rewrite (STEP TEMPLATES addition, aimed at fixing sole-step delegation
  truncation) confirmed 3/3 that a peer-CLI delegation as the sole plan
  step is emitted correctly for phrasing matching the templates tested
  that round (e.g. requests structured closer to "ask `<cli>` to
  <task>"). This session never tested the "Have `<cli>` check `<file>`
  for `<issue>`" surface form specifically before this failure was found
  — the gap is in phrasing coverage, not a known-good case regressing.
- **Open question this entry flags, not answers:** whether this failure
  mode pre-dates this session's `PLANNER_PROMPT` edits (a pre-existing
  gap only now discovered because it was never tested) or was introduced
  by one of the 4 iterations. **The test that would settle this:** run
  the identical prompt ("Have gemini check payment_processor.py for race
  conditions") against the pre-session `HEAD` version of `PLANNER_PROMPT`
  (before any of this round's 4 iterations) and compare. Not done as
  part of this documentation-only task.
- **Possible relation to `NEW-50`'s leak pattern (hypothesis, not a
  finding):** a Create-task fabrication in response to a delegation
  request has surface similarity to `NEW-46`/`NEW-50`'s pattern of
  fabricating an unrelated Create plan instead of correctly reasoning
  about the actual request. This is noted as a hypothesis worth checking
  in a future round, not established here — no shared verbatim-content
  trace was found linking the two.
- **Not fixed here.**

## Found during desk-only scoping of the 7B system-prompt test round, 2026-07-31 — read-only, no code/prompt touched, no model loaded

This section came from grounding a request to scope a 7B-only,
hand-planned-input test round (analogous to the just-completed 1.5B
`PLANNER_PROMPT` round). All three entries below were found by reading
`core/orchestrator.py`, `core/daemon.py`, `core/task_executor.py`,
`core/agent.py`, and `prompts/system_prompt.py` together — none are
live-reproduced, all rated per rule 8 on static-analysis confidence only,
consistent with how `NEW-49` (same class of finding, different file) was
rated.

### [NEW-52] `core/orchestrator.py`'s `run_queue` appends a hardcoded "use write_file... COMPLETE code" tool hint whenever a filename is found in the goal/step text, regardless of the step's actual verb (Suspected)
- **Location:** `core/orchestrator.py:583-591`. When `_FILE_RE` finds a
  filename in `original` (the overall goal) or, failing that, in
  `task.description`, the code unconditionally appends: `"\n\nUse
  write_file to create {fname} with the COMPLETE code. Output ONLY:
  <tool>...write_file...`" — with no check of whether `task.description`
  is actually a Create step or an Edit/Patch step.
- **Why this matters:** this is the same shape as the already-logged
  `NEW-49` (`core/daemon.py`'s step-1 enrichment hardcoding Create/
  full-rewrite semantics by position), but on a different code path
  (`orchestrator.run_queue`, used by `is_complex()`'s in-process planning,
  not `daemon.py`'s plannd-fed task queue). An Edit step whose goal/step
  text happens to name the target file gets told to `write_file` the
  "COMPLETE code" — a full-rewrite directive — even though the step is a
  targeted edit. Not live-reproduced; rated Suspected on the same basis
  `NEW-49` was.
- **Not fixed here.** Flagged so the 7B system-prompt test round scoped
  below can either avoid this contamination in its Edit-step test prompts
  (drive the model via `task_executor`'s path instead, which does not
  have this injection) or deliberately include one variant that exercises
  it, to convert this from Suspected to Confirmed/Refuted alongside
  `NEW-49`.

### [NEW-53] `append_file` and `note_forget` are listed in `system_prompt.py`'s AVAILABLE TOOLS table but have no corresponding word→tool trigger anywhere in the prompt text, making them unreachable via the documented step-word protocol (Confirmed)
- **Location:** `prompts/system_prompt.py:171-181` (AVAILABLE TOOLS table,
  lists `append_file` and `note_forget` as valid tools with required args)
  vs. both word→tool mapping blocks (`:29-37` and `:159-163`), neither of
  which maps any step word to `append_file` or to `note_forget`. `:37`
  maps "Save:"/"Remember" to `note_save` only — there is no corresponding
  word for "forget"/"remove note."
- **Confirmed by direct text read** (no live test needed to establish the
  gap exists — it is an objective absence in the prompt text itself). Not
  yet confirmed whether this causes real failures in practice (e.g.
  whether the 7B ever needs to call these tools and cannot find a
  documented trigger word) — that would need a live scenario, which is a
  candidate test case for the round scoped below.
- **Not fixed here.**

### [NEW-54] Peer-CLI delegation is advertised in `CAPABILITIES_PROMPT` as an agent capability, but is not an available tool in `system_prompt.py`'s AVAILABLE TOOLS list nor in `core/agent.py`'s tool-dispatch table (`TOOL_MAP`, `agent.py:49-70`) — it is decided entirely upstream via regex on the raw message, before the 7B ever sees a tool-calling turn (Confirmed)
- **Location:** `prompts/system_prompt.py:257-260`
  (`CAPABILITIES_PROMPT`: "...delegate to peer CLIs (Claude, Gemini, Qwen)
  for second opinions") vs. `core/agent.py:49-70` (the tool dispatch
  table — no `peer_cli`/`delegate` entry) vs. `core/agent.py:739`
  (`_detect_peer_delegation(user_message)`, a regex-based detector run
  against the raw `user_message` at `agent.py:991-993`, before
  `system_prompt.py`'s tool-calling protocol is even invoked for that
  turn).
- **Why this matters for the round scoped below:** the 7B coder itself
  never chooses to delegate via a tool call — delegation is fully decided
  before the model runs, by pattern-matching the incoming text. This means
  an "Ask-peer-CLI" plan step's behavior is NOT a test of
  `system_prompt.py`'s tool-calling instructions at all; it is a test of
  whether the *enriched step string* (built by whichever caller feeds the
  step to `run_agent`) happens to match `_detect_peer_delegation`'s regex.
  Any peer-CLI-delegation test scenario in the round below needs to be
  understood and reported as testing that regex/step-string interaction,
  not as testing `system_prompt.py`'s own instructions — a real
  tool-completeness gap relative to the "does the 7B coder have all the
  tools it needs" question Ish asked, since delegation isn't something
  the model can invoke on its own via the documented tool-call protocol.
- **Confirmed by direct text/code read** (dispatch table and prompt table
  both directly inspectable; the absence is objective). **Not fixed
  here.**

## Found during the 2026-07-31 7B coder system-prompt round's first live pass (NEW-30 test, 7B-only, port 8080, one clean load/unload cycle, PID-tracked; RAM/PID compliance relayed from live-verifier's report, not independently witnessed here) — no code or prompt text touched, `system_prompt.py`'s diff stays uncommitted

Test setup: hand-crafted `core/daemon.py`-style step-enrichment strings
(mimicking the 1.5B planner's real output format, without starting the
daemon or plannd processes) fed to `core/agent.run_agent(prompt,
history=[], yolo=True, no_plan=True, _in_subtask=True)` — the same flags
`TaskExecutor._execute_task` uses. 2 cases, 6 trials attempted, 5 reached
a terminal state (3 in case 1, genuinely-unread-file; 2 of 3 in case 2,
the control with content already in context) before an inference-time
budget (7B is slow on this device, ~260-450s/trial) forced a stop before
a planned case 3. See the corrected `NEW-30` entry above for the
full result this pass produced against its original hypothesis.

### [NEW-55] `core/agent.py:1676`'s low-confidence retry gate calls a plain, unguarded `input()` with no `EOFError` handling, crashing the whole task in headless/non-interactive contexts (Confirmed, live-reproduced)
- **Location:** `core/agent.py`, inside the low-confidence gate (`if
  _low_confidence:` block, ~lines 1672-1689). The line immediately after
  `ask_confirm(...)` — which does safely handle `EOFError`, returning
  `False` — is a plain `input("Type guidance to correct it...")` call
  with no `try/except EOFError` around it at all.
- **Confidence: Confirmed, live-reproduced, not a static hypothesis.**
  Reproduced live in trial 3 of case 1 (the genuinely-unread-file Edit
  case) of this round's first live pass: the task crashed with an
  unhandled `EOFError` at this exact line.
- **Why it matters:** the real daemon (`core/task_executor.py`'s
  `TaskExecutor._execute_task`, the actual production entry point for
  plan-step execution) runs headless, with no TTY — any `input()` call
  reads from a closed/empty stdin and raises `EOFError` immediately.
  Confirmed by direct code read that this gate is **not** conditioned on
  `yolo`, `_in_subtask`, or any of `TaskExecutor`'s daemon overrides
  (`confirm_write`/`confirm_shell`/`_shell_fn` don't touch this code
  path) — so any daemon task that triggers a low-confidence
  recursive-critique result hits this same crash, unconditionally.
- **Severity note:** likely higher severity than the prompt-quality work
  this round was scoped to chase (`NEW-30`) — this is a real, unguarded
  crash risk on the production daemon path, not a prompt-wording issue.
  A code-reviewer/implementer fix task is being scoped separately; this
  entry logs the finding only, not a fix.
- **Cross-reference:** found during the `NEW-30` live-test round (see
  `WORK_QUEUE.md`'s "7B coder system-prompt round" entry); not itself a
  `NEW-30` finding, an adjacent crash bug surfaced by the same test
  session.

### [NEW-56] On an Edit-step task, the 7B coder produced `write_file` calls at wrong/hallucinated/truncated paths instead of `patch_file`, and in one case silently dropped the target file's existing content (Confirmed, live-reproduced)
- **Location:** observed in case 1 (genuinely-unread-file Edit step) of
  this round's first live pass (see the corrected `NEW-30` entry above
  for the full test setup). **Mechanism not established here** — the
  live-verifier's hypothesis (not confirmed) is that these trials ran
  through `core/agent.run_agent`'s recursive critique/refine layer,
  meaning the observed sequences would be post-critique output rather
  than the model's raw draft; that attribution is a separate, ongoing
  desk investigation and should not be read as settled by this entry.
- **Trial 1:** `read_file` → `shell` → `shell` → `note_save` →
  `write_file` to a **wrong path** (`target1.py`, dropping the real
  scratchpad path prefix from the intended target). The written content
  contained only the new function requested — the file's **existing**
  functions (`add`/`subtract`) were silently dropped from the write,
  i.e. real, live-reproduced data loss, not just a wrong destination.
- **Trial 2:** `read_file` → `write_file` to a **completely fabricated,
  unrelated path** (`ccos/core/math_utility.py`), never touching the
  real target file at all.
- **Trial 3:** crashed before completing a `write_file`/`patch_file`
  decision — see `NEW-55` (a separate, unrelated bug hit mid-trial).
- **Distinct from prior related findings:** not the same as `NEW-44`
  (which is about the 7B choosing the *wrong function within the
  correct file*, `old_str` still real/grounded) — this finding is about
  the wrong/fabricated *file path* entirely, plus outright content loss
  on the one trial that did write to something resembling the correct
  file. Also distinct from `NEW-46` (1.5B planner few-shot leakage) —
  this is 7B-coder behavior downstream of a correctly-formed
  single-step Edit prompt, not a planner-generation bug.
- **Confidence: Confirmed** — live-reproduced with real tool-call
  sequences and real written file content inspected directly (not
  inferred), not a one-off guess; both of the 2 non-crashed, non-timed-out
  trials in this case showed this shape (wrong path in trial 1,
  fabricated path in trial 2). Sample size is small (2 trials) — pattern
  is confirmed to exist, but its frequency across more prompts/trials is
  not yet established.
- **Not fixed here.** Root cause (recursive critique/refine layer vs.
  prompt composition) is under the same separate desk investigation
  referenced in the corrected `NEW-30` entry — do not scope a fix to this
  entry alone until that investigation lands.
- **Correction (rule 6), 2026-07-31, desk investigation (project-architect,
  no code changed):** the recursive critique/refine layer is now ruled
  out as the mechanism for both trials described above — see the
  corrected `NEW-30` entry's two-gate argument (`agent.py:1489`'s
  `step==1`-only gate, plus `classify_breadth_need`/`max_depth=1` making
  `recursive.py`'s refine phase unreachable for a standard single-file
  Edit task). Both trials' bad `write_file` calls happened on agent-loop
  turns that ran plain `infer()` with full conversation history intact
  (turn 5 for trial 1, turn 2 for trial 2), not through recursion. The
  true mechanism is still unestablished — see new `NEW-57` for a
  candidate found so far (a context-surfacing gap in `agent.py`'s own
  tool-execution loop, unrelated to `recursive.py`) — **downgraded to
  Suspected on a second pass, see the entry itself; its original
  "read_file vs. write_file asymmetry" framing did not survive a check
  of what `_mem.load_file` actually is**.

### [NEW-57] A file read via `read_file` is only ever surfaced to the model as raw conversation-history text, never as a labeled "Loaded Files" context block — but this is NOT an asymmetry with `write_file`/`patch_file` as first framed (Suspected, downgraded from an incorrect Confirmed claim)
- **Location:** `core/agent.py:1710-1716` (the `read_file` branch, only
  calls `_get_learning().learn_from_file`, pattern-mining) vs.
  `:1693-1709` (the `write_file`/`patch_file` branch, calls
  `_mem.load_file(fpath, _wcontent)`).
- **Correction to this entry's own first draft:** the first pass of this
  entry claimed `write_file`/`patch_file` "mirrors" into the layered
  prompt's "files" context block and `read_file` should do the same.
  That is wrong. `_mem` at `agent.py:1701` is `core.memory_v2.memory` —
  a different store from `core.context`, which is what
  `prompts/layered_prompt.py:196-198`'s `_get_file_block` actually reads
  via `core.context.build_file_context_block()`/`list_loaded()`.
  Grepping the codebase for callers of `core.context.load_file()` found
  exactly two: `core/fixmode.py:45` and `core/tdd.py:106` — **not**
  `agent.py`'s normal tool-execution path at all, for either `read_file`
  or `write_file`/`patch_file`. So there is no asymmetry to fix by
  "mirroring" — neither branch populates the layered-prompt "files"
  layer today. The real, narrower, still-real finding: a file's content
  reaches the model via `messages` history (confirmed — `agent.py`'s
  `messages.append(...)` calls, e.g. `:1656-1682`/`:1860`, do carry tool
  results forward, and no message-trimming logic exists in `agent.py` to
  drop them within a handful of turns) but never via the clearly-labeled
  "Loaded Files" block a fresh system prompt would otherwise show.
  Whether that surfacing difference (raw history text vs. a labeled
  context block) measurably affects a 7B model's attention on a later
  turn is genuinely unknown — this entry does not establish that it
  does.
- **Confidence: Suspected, not Confirmed.** The code-read facts above
  (two separate stores; only 2 callers of `core.context.load_file()`,
  neither in `agent.py`'s tool loop; history does carry content forward
  with no trimming) are all directly verified. What is NOT established:
  whether this surfacing gap has any measurable effect on NEW-56's
  observed wrong-path/dropped-content `write_file` calls. Do not treat
  this as NEW-56's root cause without a live pass that specifically
  checks whether the read file's content is still attended to/reflected
  correctly at the turn the bad `write_file` occurs.
- **Cost note for whoever scopes a fix:** `core.context.load_file()`
  adds the file to the *persistent* loaded set — it would then be
  re-injected into every later prompt at priority 4 (`layered_prompt.py:338`/
  `:432`, lowest priority, first evicted under budget pressure) and
  would participate in `_files_hash()`'s cache-invalidation check on
  every subsequent draft-prompt build. That is a real, recurring
  prompt-budget cost on this token-constrained device, not a free
  one-line add — any fix task must weigh that explicitly, not just wire
  the call in.
- **Not fixed here.** Held pending the two-store question above being
  fully reconciled with `core/memory_v2.py`'s own role, and ideally one
  attribution-logged live pass (see `WORK_QUEUE.md`) showing whether
  content is actually still attended to at the bad-write turn, before
  committing implementer time to a fix here.

### [NEW-58] `core/recursive.py`'s refine phase has no path to see the draft's actual proposed tool call, forcing blind regeneration if refine is ever reached — real by code read, but currently latent (Confirmed, not currently triggerable in the observed NEW-56 trials)
- **Location:** `recursive.py:516-532` — the refine call passes
  `user_message`, `prior_critique`, and `retrieved_context` but never the
  draft's own text/tool-call JSON. `_build_refine_prompt`
  (`layered_prompt.py:385-409`) and the `build_recursive_prompt`
  dispatcher (`:441-476`) have no `prior_draft` parameter on the refine
  path at all, unlike critique (`recursive.py:440-445`,
  `layered_prompt.py:352-382`, which does receive `prior_draft`).
  Conversation history is also explicitly dropped for refine
  (`recursive.py:512-514`, "History is dropped to free ~1000 tokens").
  If critique rejects a draft that contained a correct `patch_file` call
  (real `old_str`/`new_str` file excerpts), refine has to regenerate the
  entire response, including exact file content, from nothing but a
  critique summary — the most plausible way this bug *would* manifest as
  hallucinated/wrong-path `write_file` output, if and when it fires.
- **Confidence: Confirmed as a real code gap by direct read.
  NOT confirmed as active in the NEW-56 trials** — see the corrected
  `NEW-30`/`NEW-56` entries above: refine is only reachable when
  `classify_breadth_need()` returns `"deep"` (`max_depth=2`), which a
  normal single-file Edit-step message is unlikely to trigger
  (`recursive.py:138-165`), and even then only for turn-1 responses
  (`agent.py:1489`). This is a latent bug worth closing, not an
  established root cause.
- **Not fixed here.** See `WORK_QUEUE.md`'s updated "7B coder
  system-prompt round" entry for the scoped fix (threading a
  `prior_draft` parameter through the refine path, tool-call-boundary-
  aware truncation) — scoped as hardening, explicitly not claimed to fix
  NEW-56.

### [NEW-59] `core/recursive.py`'s critique phase double-truncates the draft preview (`recursive.py:440`'s `draft[:2000]`, then `layered_prompt.py:378`'s `prior_draft[:1500]` again), and the binding 1500-char cut can split a `patch_file` call's JSON mid-string (Confirmed, not currently triggerable in the observed NEW-56 trials)
- **Location:** `recursive.py:440` truncates the draft to 2000 chars
  before passing it as `prior_draft` to `build_recursive_prompt(...,
  phase="critique", ...)`; `layered_prompt.py:378` truncates again to
  1500 chars inside `_build_critique_prompt`, making the outer 2000-char
  cut dead code in practice (the inner 1500-char cut is always the
  binding one). A real `patch_file` call's JSON, containing verbatim
  `old_str`/`new_str` file excerpts, can easily exceed 1500 chars and get
  cut mid-string, which could make a legitimately correct draft tool
  call look syntactically broken to the critique model and trigger a
  spurious rejection — pushing the draft into a refine cycle
  unnecessarily (see `NEW-58`).
- **Confidence: Confirmed as a real code gap by direct read.
  NOT confirmed as active in the NEW-56 trials** — same reachability
  caveat as `NEW-58`: critique itself only runs on turn-1 responses for
  non-`"minimal"`-breadth messages, and NEW-56's bad `write_file` calls
  did not occur on turn 1. Reachability is narrower still:
  `recursive.py:388`'s `get_adaptive_depth()` (`:171-220`) can force
  `max_depth` to 0 under thermal-critical or battery-critical device
  state, which would make even the single critique pass's loop
  (`range(1, max_depth+1)`, `:434`) empty. Budget headroom exists to fix
  this cheaply, on the occasions critique does run:
  critique's overall budget is 8000 chars (`layered_prompt.py:368`)
  against `CRITIQUE_CODE` + a 1000-char request block + the 1500-char
  draft — there is room to raise the draft cap and/or exempt a
  `<tool>{...}</tool>` block from truncation entirely.
- **Not fixed here.** See `WORK_QUEUE.md`'s updated "7B coder
  system-prompt round" entry for the scoped fix — a small, contained
  change, explicitly not claimed to fix NEW-56, but worth doing since
  it's real and cheap.

## Correction round, 2026-07-31 — both live passes on the 7B coder system-prompt round invalidated by a workspace-boundary contamination bug; one new Confirmed finding (`NEW-60`), no code/prompt touched

**What happened:** a second live pass ran this session (after the first
pass documented above), targeting `NEW-49`'s never-reached case 3 and a
`NEW-30` follow-up, using the same hand-crafted-scratch-file test
approach as the first pass. Its own trial count and detail are relayed
from that live-verifier's report, not independently re-derived by this
correction round. A third live-verifier session, checking why both
passes kept producing wrong-path/blocked/give-up outcomes, discovered
that **every scratch test file used in both passes lived under
`/data/data/com.termux/files/usr/tmp/claude-10247/.../scratchpad/...` —
entirely outside `core/filesystem.py`'s `_validate_path()` boundary
(`WORKSPACE_ROOT`/`CODE_DIR`, both `/data/data/com.termux/files/home/
Codey-OS` on this device).** Confirmed independently (not just relayed)
by a direct Python check against the live `Filesystem` instance:

```
WORKSPACE_ROOT: /data/data/com.termux/files/home/Codey-OS
CODE_DIR: /data/data/com.termux/files/home/Codey-OS
target: /data/data/com.termux/files/usr/tmp/claude-10247/-data-data-com-termux-files-home-Codey-OS/d4d9925f-0066-4a40-a815-b3799c069c66/scratchpad/new30_files/target1.py
EXC: Access denied: /data/data/com.termux/files/usr/tmp/claude-10247/-data-data-com-termux-files-home-Codey-OS/d4d9925f-0066-4a40-a815-b3799c069c66/scratchpad/new30_files/target1.py is outside workspace (/data/data/com.termux/files/home/Codey-OS)
```

Every `read_file` call against those scratch files in both passes
therefore returned `[ERROR] Access denied: ...`, not real file content.
Everything measured downstream in case 1 of both passes — wrong-path
`write_file` guesses, dropped/fabricated content, blocked-`shell`
attempts, premature "Done." responses — was the model's recovery
behavior after a denied read, not a measurement of the read-then-patch
instruction or of `NEW-30`/`NEW-56`'s originally-hypothesized bugs. **No
valid data exists this session on case 1's read-then-edit question, or
on `NEW-49`'s planned test (same case-1-shaped fixture).** Case 2's
outcomes (the control, file content pre-injected into the prompt
directly rather than read via `read_file`) cannot be cleanly attributed
either way: a denied read does not explain them (no read was denied,
because none was attempted for that fixture), but neither does anything
else established this session — they remain data with an unestablished
cause, not evidence for or against `NEW-56`'s original framing.

### [NEW-30] correction — both live passes invalidated; fix remains untested
`NEW-30`'s 6-site `prompts/system_prompt.py` fix (code-reviewer approved,
still uncommitted) has **not been meaningfully live-tested at all this
session** — both live-test attempts tested error-recovery behavior after
a denied read, not the read-then-edit contradiction the fix targets.
One narrower, verifiable positive signal survives the contamination and
should be kept, clearly bounded: in case 1 of the first pass (the
genuinely-unread-file scenario, where a correct turn-1 `read_file` was
actually called for), the 2 of 3 trials that produced a first tool call
at all (see the corrected `NEW-30` entry above, "Exact accounting")
targeted `read_file` at the **correct real file path** before being
denied — i.e. the fix's "read first" instruction is being followed at
least that far. The third case-1 trial crashed later in its sequence
(`NEW-55`); this correction round did not re-derive whether its own
turn-1 call was also a correctly-targeted `read_file`, so it is not
counted either way. Case 2's trials (the control, file already in
context) are not counted toward this signal at all — a turn-1
`read_file` was never the expected first action there in the first
place. This does **not** confirm or refute the fix's actual target
behavior — does the model correctly proceed to `patch_file` after a
**successful** read. Pass 2's trial outcomes are relayed from the third
live-verifier's report only (not independently re-derived here) and are
not folded into this count. **Status: needs a proper re-test with valid
file access before this can be called fixed, partially fixed, or
unfixed.**

### [NEW-30] third pass, 2026-07-31 — FIXED on its actual mechanism, live-verified
A fourth live-verifier session re-ran the test with both required fixes
applied: scratch fixtures moved inside `WORKSPACE_ROOT`
(`.live_verify_scratch/`, gitignored) instead of `/usr/tmp`, and a hard
precondition gate confirming each `read_file` call actually returned real
content (not `[ERROR]`) before spending inference budget on a trial. RAM
discipline: `free -h` recorded before/after both model-load cycles (no
crash, no swap thrashing), PIDs tracked, `ps aux | grep llama-server`
clean after both — one cycle hit the codebase's own thermal-triggered
auto-restart mid-run (device thermal-management code stopping/reloading
the server itself, not a manual kill), unaffected by CLAUDE.md rule 3.

**Case 1 (anchor, single draw):** correct two-turn behavior — `read_file`
turn 1, `patch_file` turn 2 with a correctly-grounded `old_str`, `Done.`
turn 3; on-disk change verified (30→60).

**A/B cycle (decisive test, 3 draws per arm, same running server, fixture
reset between every draw):** with the fix, **3/3** draws called
`read_file` before attempting `patch_file`. Without the fix (pre-fix
`system_prompt.py`, same session), **0/3** draws read first — all three
skipped straight to a guessed `patch_file` call that happened to match
the real content by luck on a generic fixture (the classic
ungrounded-`old_str` failure mode this project tracks separately as
`NEW-7`/`NEW-44`). **This is the discriminating result: the fix changes
the read-before-patch behavior 0/3 → 3/3.**

One of the three "fixed" draws (`fixed-1`) still failed to apply its
patch — but for an unrelated, newly-found reason (see `NEW-61` below),
not a recurrence of "Done. right after read_file." The raw
patch-application success rate (2/3 fixed vs. 3/3 pre-fix-by-luck) is
explicitly **not** the right metric here; the mechanism the fix targets
is read-before-patch, and that flipped cleanly.

**Case 2 (control, file content pre-injected into the prompt):** the
model called `read_file` anyway before `patch_file`, a real deviation
from the fix's intended behavior — but the injection went into the user
message text via `_execute_task` (which always clears memory and passes
`history=[]`), not the real system-prompt "Loaded Files" layer, so this
may not be a fair test of the fix's actual target condition. Reported
as-is, not resolved either way.

**`NEW-49` (daemon step-0 "Write the COMPLETE file" enrichment on an
Edit-verb step):** refuted at n=1 — model read then patched correctly,
did not rewrite the whole file — real evidence against the hypothesis,
but a single draw doesn't close a Suspected finding.

**Verdict: `NEW-30` is FIXED on its actual mechanism (read-before-patch
on a genuinely unread file), live-verified 3/3 vs. 0/3 in a same-session
A/B test. It is NOT fixed on the broader old_str-grounding/guessing
question — that remains `NEW-7`'s open scope, now with additional A/B
corroboration that the pre-fix prompt reproduces the guessing behavior
reliably (3/3).** The `prompts/system_prompt.py` diff (code-reviewer
approved, now live-verified) remains uncommitted — commit decision
pending directly with Ish.

### [NEW-61] `core/agent.py`'s JSON-repair regex corrupts `old_str`/`new_str` when the model emits single-quoted string values (Confirmed, live-reproduced)
`_fix_unquoted_values()` (`core/agent.py:280-303`) only treats a value as
"already quoted" if it starts with `"` — a Python-style single-quoted
value (`'return 30'`, invalid JSON but a plausible LLM output) is
misclassified as unquoted, and the repair wraps the literal single-quote
characters into the resulting double-quoted string, corrupting the
`old_str`/`new_str` value it was supposed to fix. Live-reproduced during
the `NEW-30` third-pass A/B cycle (draw `fixed-1`): the model emitted a
single-quoted `old_str`, the repair regex mangled it, `patch_file` failed
to match, and the model gave up with "Done." after a corrective re-read
rather than retrying correctly. Not yet scoped to an implementer.

### [NEW-56] correction — downgraded, cause reattributed
The specific observed behavior (wrong paths, dropped content, both
documented above with real inspected tool-call sequences) is real and
reproduced twice in the first pass. Its cause is now understood to be a
workspace-access-denial recovery failure (see new `NEW-60` below), **not
necessarily** evidence of a `patch_file`-vs-`write_file` decision bug
under normal (valid-access) conditions. The prior desk-investigation
correction (recursive critique/refine hypothesis refuted — see above)
still stands on its own evidence and is not affected by this
correction; only the underlying premise that these were genuine
patch-vs-write decisions is now superseded. Whether the 7B model *also*
has a normal-conditions `patch_file`-avoidance problem, independent of
denied-read recovery, remains untested and open.

### [NEW-55] correction — provenance note added, finding NOT downgraded
`NEW-55` (unguarded `input()`/`EOFError` crash at `core/agent.py:1676`)
stays Confirmed and live-reproduced — this correction does not touch
that status. Provenance note: the trial it reproduced in (case 1,
trial 3 of the first pass) ran under the same workspace-denial
conditions described above. This does not affect the finding's
validity: the `input()` call at `agent.py:1676` has no `EOFError` guard
regardless of what routed the task into the low-confidence retry gate
that reaches it — a denied-read-driven low-confidence result crashes it
exactly the same way a legitimately low-confidence result would. Kept
Confirmed, not reopened.

### [NEW-49] — no change, second attempt also inconclusive
Still Suspected, undetermined. The second pass's attempt to test case 3
(an Edit-first plan through `daemon.py`'s real step-0 enrichment text)
also never reached a genuine write-vs-patch decision point — it got
stuck in the same denied-read recovery loop described above, per the
third live-verifier session's report (relayed, not independently
re-derived here).

### [NEW-57] — held-pending condition restated, not re-rated
Stays Suspected — its code-read facts (`core.memory_v2` vs.
`core.context` being separate stores, neither populated by `agent.py`'s
normal tool loop) are independently verified and unaffected by this
correction. Its held-pending condition (`WORK_QUEUE.md`'s "one
attribution-logged live pass showing whether a read file's content is
actually still attended to at the turn a bad `write_file` occurs")
is now understood to rest on a premise that never held this session: no
valid-access bad-write turn was ever actually observed to check
attention against. The question NEW-57 was meant to help answer is
therefore still fully open, not partially answered by anything logged
this session.

### [NEW-60] Workspace-access-denied `read_file` calls send the 7B agent into an unrecoverable, unbounded failure spiral with no reliable path to a correct outcome (Confirmed by code read + literal reproduction; failure-shape sample is 2 trials, not the full 8)
- **Location:** `core/filesystem.py:79-127`'s `_validate_path()` denies
  any `read_file`/`write_file`/`patch_file` call outside
  `WORKSPACE_ROOT`/`CODE_DIR` (both resolve to
  `/data/data/com.termux/files/home/Codey-OS` on this device), returning
  a `FilesystemAccessError` that `core/agent.py`'s tool-dispatch wraps as
  `"[ERROR] " + error_msg` (`agent.py:489`). `core/agent.py:492-521`'s
  `is_error()` correctly detects the `[ERROR]` prefix and
  `agent.py:1748`'s `if is_error(last_tool_result, name) and
  auto_retries < max_retries:` triggers an automatic retry — the gate
  itself works as designed. What is not reliable is the model's own
  recovery behavior on that retry.
- **Confidence: Confirmed — by direct code read (`filesystem.py:79-127`
  → `agent.py:489` → `is_error` at `:492-521` → retry at `:1748`) plus
  an independent literal Python check reproducing the exact denial (see
  the block above). The mechanism itself is code-verified, not just
  trial-counted, which is the stronger evidence here.** Live
  failure-shape corroboration is narrower than "8 trials" — it is
  documented specifically for the 2 case-1 (genuinely-unread-file)
  trials of the first pass, where a denied `read_file` is directly on
  record (`NEW-56`'s trial 1/2 detail: wrong-path `write_file` guesses,
  mangled paths, a dropped directory prefix, a fabricated unrelated
  filename). Case-1 trial 3 (first pass) crashed via `NEW-55` before
  showing further spiral behavior; that crash trial did include one
  unrelated wandering read of `core/agent.py` itself (~84KB) per the
  third live-verifier's relayed report — not independently re-measured
  here, and notably that particular read succeeded (it's inside
  `WORKSPACE_ROOT`), so the spiral is "denied reads produce unreliable
  recovery," not "every subsequent read is also denied." Case 2's 2
  completed trials (blocked `shell`, zero tool calls) are **not**
  attributed to this mechanism at all — that fixture pre-injected the
  target file's content directly into the prompt, so no `read_file`
  denial was in play there; see the `NEW-30` correction above for why
  case 2 is excluded. Pass 2's 2 trials are relayed from the third
  live-verifier's report only, not independently re-derived, and are
  not counted as confirmed reproductions here — only as consistent with
  the same reported shape.
- **Why it matters — production-reachable, not test-artifact-only:**
  any daemon-queued task step naming a path outside the workspace root
  (a path genuinely outside the repo, a typo'd path, or a path built
  from a stale/relative reference) hits this exact same denial-then-
  spiral behavior in production, independent of anything `NEW-30`/
  `NEW-56`-specific. This is the actual bug that produced both
  contaminated live passes, and it is real regardless of the
  `NEW-30`/`NEW-56` question.
- **Not fixed here.** Logged only. A fix would need to bound the
  model's retry behavior on an access-denial specifically (e.g. a
  clearer recovery instruction in the retry prompt, or a hard stop
  instead of an open-ended retry) — out of scope for this
  documentation-only correction round.

### Also logged (Confirmed, related, smaller) — attribution logging still only covers turn 1
`core/recursive.py`'s `[Recursive] Turn attribution` log line (added
during the `NEW-58`/`NEW-59` fix round, `recursive.py:393-398`) only
fires for calls that go through `recursive_infer()` at all — turns
where `core/agent.py:1489`'s `step==1` gate is false skip this function
entirely and produce no attribution line (this is the same "own plain
infer() branch has no log line here" limitation the code comment at
`recursive.py:381-390` already self-discloses, not a newly discovered
gap; not assigned a new `NEW-##`). This directly blocked getting a
clean per-turn read on turns 2+ in both this session's live passes too
— the companion log line in `core/agent.py`'s own plain-`infer()` loop
(`WORK_QUEUE.md`'s "7B coder system-prompt round," sub-task 1) is still
needed before a future live pass can cleanly attribute which turn/path
produced a given tool call, and is now doubly important given `NEW-60`:
a future pass needs to distinguish "model ignored the fix" from "model
was recovering from a denied read" turn-by-turn, not just at the final
tool call.

## Found during Track 1 tool/capability audit (ccos/plugins/*/manifest.json vs. implementation), 2026-07-30 — NOT fixed, logged only

### [NEW-34] All 3 auto-generated `ccos/plugins/compound/skill_*` plugins are broken by construction (no data piped between pipeline steps) and are live, agent-callable capabilities produced by the permanently-gated `skill_recombiner` (Confirmed)
- **Broken pipeline (Confirmed, verified by reading code):**
  `pipeline.py` in each compound skill (e.g.
  `ccos/plugins/compound/skill_camera_capture_tts/pipeline.py:81-89`)
  calls `pm.call_capability(capability)` with no positional/keyword
  arguments for every step. `speech.tts` requires `text`; with no
  argument the call cannot meaningfully succeed, so
  `skill.camera_capture_tts` is non-functional as authored despite
  reporting `estimated_success_rate: 1.0` in its own manifest.
  `skill.info_info` (`info -> info`, identical capability twice) and
  `skill.info_processes` read as throwaway pattern-mining artifacts, not
  intentional compositions.
- **Gate question (Confirmed, needs Ish's decision, CLAUDE.md rule 1):**
  these 3 manifests are `author: "CCOS-SkillRecombiner"` — output of
  `core/skill_recombiner.py`, one of the four mechanisms rule 1 says
  must stay "permanently gated off from live execution." The recombiner
  *engine* being gated does not stop `ccos/core/plugin_manager.py`'s
  `_discover()` from auto-loading everything under
  `ccos/plugins/compound/` like any other plugin — these 3 skills are
  registered, live, callable capabilities today, sitting in the repo
  since the initial CCOS commit. Whether pre-generated recombiner output
  being live counts as "activating" the gated mechanism is a real
  product question, not something to resolve unilaterally here.
- **Under-declared hardware_requirements (Confirmed):**
  `skill_camera_capture_tts/manifest.json` declares
  `"hardware_requirements": []` at both the top-level `capabilities[0]`
  entry, despite its pipeline invoking `vision.camera_capture` (declared
  `["camera"]`) and `speech.tts` (declared `["audio_output"]`).
  `capability_registry.py:163` gates capability availability on exactly
  that field, so this compound skill currently passes the hardware gate
  and is offered as callable on a device with no camera and no speakers
  — the two hardware requirements its own pipeline steps individually
  declare are lost at the compound-skill level.
- **Recommendation:** remove all 3 (both for being broken and for the
  gate question) pending Ish's explicit call; not deleted in this audit
  since it's a design/product judgment, not a descriptive fix.
- **Interim disable, 2026-07-30 (still open — this is not a resolution):**
  Ish asked for these turned off now, safely, while the permanent
  remove-vs-keep-and-fix decision waits. Renamed all 3 directories with a
  leading `_` (`ccos/plugins/compound/_skill_camera_capture_tts`,
  `_skill_info_info`, `_skill_info_processes`) — `plugin_manager.py`'s
  `_discover()` already skips any dir starting with `_` (lines 81, 84),
  so this required zero code changes and reuses an existing, already-
  tested exclusion path. Verified live: `PluginManager().list_plugins()`
  now returns 13 plugins total with none matching `skill.*` (previously
  included the 3). Nothing deleted — manifest/pipeline/test files intact
  on disk under the renamed dirs, git history preserved via `git mv`.
  Grepped the repo first for hardcoded references to the old dotted
  names/paths outside their own plugin dirs: only prose (docs, this
  entry, `PROJECT_LOG.md`), gitignored runtime state
  (`ccos/data/capabilities.json`, regenerates on next load), a queued-but-
  never-acted-on `goals_queue.json` goal description, and
  `ccos/tests/test_skill_recombiner.py` (generates skills in-memory via a
  temp registry, doesn't read the live plugin dirs) — nothing that
  resolves these plugins by path/import, so the rename is safe. Also
  noted in `WORK_QUEUE.md`'s Parked section. Reversible: strip the `_`
  prefix to re-enable. Still needs Ish's permanent call on final
  disposition.
- **RESOLVED 2026-07-31 — permanently deleted, direct instruction from
  Ish.** `git rm -r` on all 3 renamed dirs
  (`_skill_camera_capture_tts`/`_skill_info_info`/`_skill_info_processes`
  under `ccos/plugins/compound/`) — manifest/pipeline/test files gone
  from the working tree, git history preserved. Not restaged from the
  interim `_`-prefix disable; a clean removal. This closes NEW-34.

### [NEW-35] `vision.camera_capture`'s default output path (`camera.py:53`, `f"/tmp/ccos_capture_{...}.jpg"`) is likely wrong on Termux (Suspected)
- Termux's writable temp dir is `$PREFIX/tmp`, not `/tmp` — bare `/tmp`
  may not exist or be writable under Termux's app-sandboxed filesystem.
  Not verified live in this audit (out of scope — audit covered manifest
  accuracy, not a live device test); flagging per rule 8 rather than
  silently fixing, since the correct default path needs an actual Termux
  run to confirm, not just a read of the code.

## Found during root-level/docs UNCLEAR-files cleanup, 2026-07-30 — NOT fixed, logged only

### [NEW-27] Root-level/docs orphaned-markdown audit: discoverability gaps (Confirmed) and two ambiguous files (Suspected)
- **Status: Confirmed (discoverability gaps), Suspected (AUDIT_REPORT.md
  disposition, docs/TODO2.md staleness) — not fixed, logged only.** Found
  while executing the paused WORK_QUEUE.md Track 0 item to resolve
  `CODEY_OS_MASTER_VISION.md` Section 8's "Root-level and docs/ UNCLEAR
  files" bullet.
  - **Confirmed — README doc-table gap:** `MODEL_COMPARISON.md`,
    `PRIVACY.md`, and `docs/importantdoc.md` all have real, current
    content but zero inbound links from `README.md`'s docs table (verified
    via `grep -n "docs/" README.md` and separate greps for each filename —
    none appear). `Codey-OS-audit.md` is likewise absent from that table,
    though it is well-referenced elsewhere (`.claude/agents/project-architect.md`,
    code-reviewer memory, `PROJECT_PLAN.md`, `PROJECT_LOG.md`). Low-severity
    discoverability issue; a future docs pass could add these to the table.
  - **Confirmed — QWEN.md stale tree, only partially fixed:** its
    directory-tree section listed `TODO.md` and `test_patch.txt`, both
    already gone (`test_patch.txt` confirmed absent via `ls`; `TODO.md`
    deleted this round) — those two entries were removed this round. The
    tree remains materially incomplete beyond that: it omits `CLAUDE.md`,
    `Codey-OS-audit.md`, `PENDING_ISH_DECISIONS.md`, `PROJECT_LOG.md`,
    `PROJECT_PLAN.md`, `QWEN.md` itself, and `WORK_QUEUE.md` — all
    current root-level files. Since QWEN.md is read at the start of every
    Qwen session, a full tree refresh is worth a small follow-up task.
  - **Suspected — `AUDIT_REPORT.md` disposition unresolved:** read in
    full (351 lines). It is a June-13-2026 "Codey-V3" era
    architecture/feature-inventory + investor-pitch document — confirmed
    NOT a duplicate of `Codey-OS-audit.md` (a July-29 severity-rated bug
    audit; different purpose entirely). Content is stale (predates CCOS
    and the Codey-OS rename) but not a clean duplicate, so it wasn't
    deleted unilaterally per CLAUDE.md rule 8's "flag rather than delete
    anything ambiguous." Needs Ish's call: archive vs. delete outright.
  - **Suspected — `docs/TODO2.md` staleness unverified:** a 2026-03-29
    (v2.7.2-era) deferred-items list, not linked from README, not
    re-verified against current code. One item is already contradicted:
    it claims `validate_command_structure` was "removed in v2.7.1," but
    `grep -rl validate_command_structure --include="*.py" .` shows it
    still present in `tools/shell_tools.py` and
    `tests/security/test_shell_injection.py`. Other referenced symbols
    (`plannd`, `peer_shell`, `_is_review`, `SECONDARY_MODEL_PATH`) do
    still exist, so the file isn't wholesale dead either. A note was
    added to the file itself; a scoped re-verification pass of its 10
    items is needed before deciding keep/archive/delete — not adjudicated
    here.

## Found during dynamic model-tier routing architecture exploration, 2026-07-30 — NOT fixed, logged only

### [NEW-24] `core/lora_import.py:336` calls `loader.load_secondary()`, which doesn't exist on `ModelLoader`
- **Status: Confirmed, not fixed.** Found while exploring the model
  loader (`core/loader_v2.py`) during the PENDING_ISH_DECISIONS /
  master-vision architecture round for dynamic model-tier routing.
  `core/loader_v2.py`'s `ModelLoader` class implements only
  `load_primary()` and `unload()` — no `load_secondary()` method exists
  anywhere on the class. `core/lora_import.py:336` calls
  `loader.load_secondary()` regardless, as part of
  `swap_to_finetuned_model`'s reload-after-swap logic.
  - **Why this matters:** this is a latent `AttributeError` waiting to
    fire the first time `swap_to_finetuned_model` actually runs through
    that code path — `SECONDARY_MODEL_PATH` (Qwen2.5-Coder-1.5B) is
    configured in `utils/config.py` and clearly intended to be loadable,
    but the loader method it depends on was never written.
  - **Out of scope for this round** — found during read-only exploration
    for an architecture-planning session (updating
    `CODEY_OS_MASTER_VISION.md` Section 7), not during implementation.
    Logging per CLAUDE.md rule 8 rather than silently fixing it.
  - Likely relevant to Section 7.4's planned slot-aware loader API
    (`acquire`/`release`), which would need to properly support a second
    concurrently-loadable model anyway — worth resolving as part of that
    work rather than as an isolated patch, since a one-off
    `load_secondary()` method would just be superseded by the slot API
    shortly after.

## Found during Phase 3 entry-point scoping pass, 2026-07-30 — NOT fixed, logged only

### [NEW-22] `README.md:53` misdescribes `gui/start.sh` as something `codey-start` orchestrates, and three independent copies of "start gui/server.py + PID file + trap-kill" logic exist
- **Status: Resolved in part (commit `63ab3df`, 2026-07-30).** Ish decided
  to delete `gui/start.sh` outright and fix `README.md`'s wording rather
  than make the launchers call it — this closes the README-misdescription
  half of this finding and the `gui/start.sh` copy of the duplicated
  logic. **Still open:** the underlying duplication this finding is really
  about — `codey-start:55-75` and `codeyOS:396-415` still each
  independently reimplement the GUI-launch/PID-file/trap-kill pattern (63ab3df
  did not touch either's launch logic, only a stale comment in
  `codey-start`). Re-verified at HEAD: both blocks are still present
  (`codey-start` lines 57-74, `codeyOS` lines 396-415). This residual
  two-copy duplication remains Confirmed and unscoped — adjacent to the
  NEW-12 dual-launcher bug class, no live symptom observed yet.
- **Original finding** (2026-07-30). Found while scoping
  PROJECT_PLAN.md's Phase 3 "unified entry points" checklist.
  `README.md:52-54` says the older entry points including `gui/start.sh`
  "still exist underneath and are what `codey-start` orchestrates." This
  is factually wrong: `codey-start` (lines 55-75) and `codeyOS` (lines
  396-415) each **reimplement** gui/start.sh's exact pattern
  (start `gui/server.py` in background, write a GUI PID file, trap on
  exit to kill only if started here) independently, in bash, rather than
  calling `gui/start.sh` itself. Grepped `codey-start`, `codeyOS`, and
  `codeydOS` for any exec/source of `gui/start.sh` — zero hits. Meanwhile
  `gui/start.sh` itself (line 58) calls `python main.py` directly, a
  fourth, still-different code path nothing else uses.
  - **Why this matters:** three near-identical, independently-maintained
    copies of the same GUI-launch/teardown logic is exactly the kind of
    duplication `CODEY_OS_MASTER_VISION.md` Section 6 says to avoid
    ("Not going to duplicate effort by maintaining two implementations
    of the same job... without a stated reason"). It's also adjacent to
    the NEW-12 dual-launcher class of bug (two things independently
    managing GUI-server lifecycle) — no live symptom observed yet, but
    the same shape of risk.
  - **Not fixed this round** — scoping pass only, per explicit
    instruction not to implement. Needs a decision (see
    `PROJECT_PLAN.md`'s Phase 3 entry-point checklist / hand-off to Ish):
    either delete `gui/start.sh` and fix the README wording, or make
    `codey-start`/`codeyOS` actually call `gui/start.sh` instead of
    reimplementing it.

### [NEW-23] `ccos_main.py` is an orphaned standalone MVP demo script — nothing in the current codebase execs or imports it
- **Status: RESOLVED (commit `63ab3df`, 2026-07-30).** Ish decided to
  delete `ccos_main.py` outright rather than keep it as a documented
  standalone demo. Deletion confirmed zero live references by the
  implementer, independently re-verified from scratch by the
  code-reviewer, who found nothing missed. Documentation references
  updated to match (`README.md`, `CODEY_OS_MASTER_VISION.md`, `QWEN.md`).
- **Original finding** (2026-07-30). Grepped the full repo
  (`.py`/`.sh`) for `ccos_main` — the only hit besides the file itself is
  documentation (`README.md`, `CODEY_OS_MASTER_VISION.md`, `PROJECT_PLAN.md`,
  `PROJECT_LOG.md`, `Codey-OS-audit.md`, `QWEN.md`). None of `codey-start`,
  `codeyOS`, `codeydOS`, or `gui/start.sh` reference it. Its own docstring
  calls it "the MVP demo script. Run: python ccos_main.py" — i.e. it was
  never wired into the unified launchers to begin with, unlike
  `codeyOS`/`codeydOS`/`gui/start.sh` which genuinely are orchestrated
  under the hood by `codey-start`.
  - **Why this matters:** `CODEY_OS_MASTER_VISION.md` Section 6a's
    rationale for not deleting the old fragmented entry points is that
    "`codey-start` orchestrates them" — that rationale does not apply to
    `ccos_main.py`, since nothing orchestrates it. The real decision is
    "delete this demo script outright" vs. "keep it as a standalone,
    documented demo with a stated reason," not "retire as user-facing
    surface" (it was arguably never that).
  - **Not fixed this round** — flagged for Ish's decision alongside the
    Phase 3 entry-point checklist.

### [NEW-26] `CODEY_OS_MASTER_VISION.md` Section 6a and `QWEN.md`'s tree listing still name `codey3`/`codeyd3` as the fragmented entry points being replaced, but the actual files in the repo are `codeyOS`/`codeydOS` — `codey3`/`codeyd3` don't exist on disk

**(Renumbered from a duplicate NEW-24 to NEW-26 on 2026-07-30 — two
unrelated issues had been assigned the same ID; content unchanged, ID
corrected only, to keep IDs unique per the convention documented in
`WORK_QUEUE.md`.)**
- **Status: Suspected, not fixed** (2026-07-30). Found while executing
  the Phase 3 entry-point cleanup round (NEW-22/NEW-23/main.py doc
  task). `ls codey3 codeyd3` at repo root returns "No such file or
  directory" for both; the actual files present are `codeyOS` and
  `codeydOS`. Yet `CODEY_OS_MASTER_VISION.md` Section 6a ("This replaces
  the current fragmented entry points (`codey3`, `codeyd3`)...") and
  `QWEN.md`'s tree (`codey3`/`codeyd3` listed as present, "Legacy entry
  point (to be retired)") both still use the old names. This looks like
  leftover wording from before a rename (codey3/codeyd3 → codeyOS/
  codeydOS) that happened at some point without these two docs being
  updated to match.
  - **Why "Suspected" not "Confirmed":** haven't traced the exact commit
    that renamed the scripts or confirmed there was never a separate
    codey3/codeyd3 pair coexisting with codeyOS/codeydOS at some point;
    only confirmed the current on-disk state via `ls`.
  - **Second data point, same tree-drift class:** `QWEN.md`'s tree also
    listed `ccos/ccos_main.py` ("CCOS entry point") at line 22 before
    this round's edit removed it — that path never existed either (only
    the now-deleted root-level `ccos_main.py` did). `QWEN.md`'s
    structural tree appears to have drifted from the real repo layout
    in more than one place; a full audit of it against the actual
    filesystem is out of this round's scope.
  - **Left untouched this round** — out of this round's explicit scope
    (task instructions named only `gui/start.sh`, `ccos_main.py`, and
    the main.py-documentation items; rewriting the codey3/codeyd3
    references is a separate, not-yet-approved edit to the canonical
    spec doc).

### [NEW-25] `codeyOS --daemon` mode forwards a literal string `$@` instead of the actual arguments, due to a backslash-escape outside the heredoc
- **Status: Resolved (2026-07-30), code-reviewer approved.** Removed the
  stray backslash (`"\$@"` → `"$@"`), matching the already-correct
  pattern in the file's direct-mode fallback branch. code-reviewer
  independently confirmed: syntax valid (`bash -n codeyOS`), no `shift`
  needed (verified `main.py`'s argparse genuinely expects `--daemon` in
  its own args, unshifted, same as the direct-mode branch), grepped the
  whole file for any other stray-backslash-before-`$@` instances (found
  none), and confirmed nothing relies on the old broken behavior. No
  live-verifier pass needed for this class of change (pure shell
  argument-forwarding fix, not a runtime process-lifecycle behavior
  change).
- **Status: Confirmed, not fixed** (2026-07-30). Found while verifying a
  `docs/commands.md` claim during the Phase 3 entry-point cleanup round
  (not otherwise in scope). `codeyOS` line 119, inside the `--daemon`
  branch:
  ```
  python3 "$TMPSCRIPT" "\$@"
  ```
  The `\$@` sits outside the heredoc body (after the closing `PYEOF`),
  so the backslash is interpreted by the outer shell at that point,
  producing the literal two-character string `$@` passed as a single
  argument to `main.py` — not the actual positional arguments. Compare
  the direct-mode branch at line 428, which is correct:
  `python3 "$TMPSCRIPT" "$@"` (no backslash). Net effect: `codeyOS
  --daemon --threads 4` (or any other flag) does not actually forward
  `--threads 4` to `main.py` — only the literal string `$@` is passed.
  - **Not fixed this round** — process-lifecycle-adjacent (daemon
    startup argument handling), requires code-reviewer approval per
    project rule 4, and is out of this round's approved scope.

## Milestone (2026-07-30): all four original punch-list items resolved

The user's original four-item punch list — [NEW-3], [NEW-1], [NEW-5],
and [NEW-2] — is now fully resolved (see each entry below for its own
resolution evidence and commit). [NEW-6] (sibling `load_primary()`
KeyboardInterrupt gap at three call sites in `main.py`) is now also
Resolved (2026-07-30, Round 8, commit `435c120`). [NEW-7] (the
`[Recursive]` planner's tendency to synthesize whole duplicate
functions with `old_str=""` instead of targeted patches) and [NEW-8]
(a pre-existing, unrelated `ccos/tests/test_ccos.py::test_sandbox`
failure) remain open. [NEW-9] (a residual, intermittent atfork/fork-
window race that can bypass the guard pattern shared by NEW-5's and
NEW-6's fixes, at all four call sites) was newly discovered during
Round 8's live-verification of NEW-6 and logged Confirmed — needs its
own dedicated scoping pass, not yet queued for a fix.

## Found during Round 3 (NEW-4) live-verification pass, 2026-07-29 — NOT fixed, logged only

### [NEW-5] `llama-server` child can outlive `gui/start.sh`'s (or any) parent process indefinitely on a TERM/Ctrl+C during mid-load, with no automatic recovery
- **Status: Resolved** (2026-07-30, Round 6). Fixed by commit `eed29dc`:
  `main.py`'s `repl()` (~line 1267-1274) now wraps `loader.load_primary()`
  in `try/except (KeyboardInterrupt, SystemExit)`, calling the existing
  `shutdown()` and returning cleanly, reusing the scoped-PID teardown
  path with no new kill logic. code-reviewer approved; live-verifier
  independently reproduced a genuine mid-load `SIGINT` via `pty.fork()`
  (tracked child PID) and confirmed no orphan `llama-server` remained
  (`ps -eo pid,ppid,pgid,comm | grep -E "python|llama"` empty, `free -h`
  RAM recovered), plus a regression check on the normal-completion path.
  See `PROJECT_LOG.md` 2026-07-30 entry for full verbatim evidence.
  `NEW_ISSUES.md` [NEW-6] (same unguarded pattern at three sibling call
  sites) remains open as a separate, unscoped follow-up.
- **Caveat added (2026-07-30, Round 8 live-verification of NEW-6) — per
  CLAUDE.md rule 6, correcting the record rather than letting the
  unqualified "fully live-verified" claim above stand as if this gap
  didn't exist.** Round 8's live-verifier, testing the sibling `try/except
  (KeyboardInterrupt, SystemExit)` guard at three other call sites that
  share this exact pattern, found that the same guard shape used here in
  `repl()` has a narrow, intermittent residual gap: if `SIGINT` lands
  during `subprocess.Popen()`'s internal `os.fork()` call inside
  `core/loader_v2.py` (~lines 116-130), CPython's own atfork exception
  handling can silently swallow the `KeyboardInterrupt` before it ever
  reaches the guard's `try/except` — meaning the guard simply never fires
  in that narrow window, in all four call sites that share this pattern
  (this one included), not just the three new ones. This is **not** a
  regression in this fix and does **not** downgrade this entry's overall
  Resolved status — the guard demonstrably works correctly for the vast
  majority of the interrupt window (this entry's own Round 6
  live-verification above, plus 2 of 2 clean reruns of the sibling
  `args.init` site in Round 8). It is a newly-discovered, narrower,
  pre-existing residual gap in the shared `core/loader_v2.py` Popen/fork
  code, logged in full as its own entry, [NEW-9] below.
- **Confidence: Confirmed** (upgraded 2026-07-29, Round 6 — live-reproduced
  and root-caused by reading the code; previously Suspected on a single
  observation).
- **Original (Suspected) finding, Round 3:** implementer's live
  verification of the default (no-flag) path for the Round 3
  `--dashboard-only` task (`gui/start.sh`, commit `ea954eb`) observed the
  spawned `llama-server` child (a tracked PID) "still alive briefly"
  after the parent script exited on a mid-load `TERM`, before being
  killed directly by that tracked PID. Not reproduced a second time at
  the time; no root cause investigated.
- **Round 6 live reproduction (this entry's upgrade):** live-verifier sent
  `kill -TERM` to the tracked `gui/start.sh` script PID while the 7B
  model was mid-load, then polled every 0.5s for 10+ seconds. The bash
  script, `gui/server.py`, `main.py`, and `llama-server` were **all still
  alive, unchanged**, for the entire polling window — not "briefly"
  outliving the parent, but surviving it with no sign of any teardown in
  progress. Letting it run to full completion (~40s later total), the
  script's own `trap ... TERM` handler **never fired**, because bash was
  blocked in `wait()` on its foreground child (`python main.py`), which
  does not exit on its own when sent `TERM` this way. The tracked PIDs
  (`main.py` and `llama-server`) had to be killed individually and
  manually — there is no automatic recovery path.
- **Root cause (identified by reading the code, not just observing
  behavior):**
  - `main.py`'s `repl()` (around line 1269) calls
    `loader.load_primary()` with no `try/except KeyboardInterrupt`
    wrapper around the call.
  - `ModelLoader.load_primary()`'s own exception handler
    (`core/loader_v2.py` around line 351) is `except Exception`, which
    does **not** catch `KeyboardInterrupt` (it subclasses
    `BaseException`, not `Exception`), so a `KeyboardInterrupt` raised
    during the load window propagates straight out of `load_primary()`
    uncaught.
  - There is also no top-level exception handler around `main()` itself
    (bottom of `main.py`, `if __name__ == "__main__": main()` is bare),
    so an uncaught `KeyboardInterrupt` during this window exits the
    process without ever calling `shutdown()` (`main.py` line ~125,
    which contains the correct scoped-PID teardown logic via
    `loader.get_pid()` / `loader.unload()`).
  - Separately, `llama-server` is spawned with `preexec_fn=os.setsid`
    (`core/loader_v2.py` line 127), putting it in its own process
    group specifically to insulate it from terminal signal groups —
    meaning it is never touched by a terminal-delivered signal that
    hits `main.py`, and depends entirely on `main.py`'s own code
    explicitly killing it. When that code path is skipped (as above),
    `llama-server` becomes a genuine, indefinitely-running orphan.
  - Important supporting detail for any fix: `ModelLoader.load_primary()`
    (`core/loader_v2.py` line 341) assigns `self._server = LlamaServer(...)`
    **before** calling `self._server.start()` (line 342), and `start()`
    itself sets `self.process` (the `Popen` handle, with its real PID)
    immediately after spawning (line 123-130), well before the up-to-60s
    health-check polling loop that follows (lines 132-153). This means
    `loader.get_pid()` / `loader.unload()` are both usable to tear down a
    partially-started server for nearly the entire load window, not just
    after a successful load — a catch-and-teardown fix has a real target
    to kill for almost the full duration of the exposure window.
- **Confirmed NOT broken:** a normal Ctrl+C at the `You>` prompt (i.e.
  post-load, in the REPL's own input loop) works cleanly and tears
  everything down in ~1.5s — the REPL's existing
  `except (KeyboardInterrupt, EOFError)` blocks (e.g. `main.py` line 948)
  catch it fine there. The gap is specific to the model-load window,
  before any of those handlers are active.
- **Scope note:** lives entirely in `main.py`'s own model-load call site
  and `core/loader_v2.py`'s exception handling, not in `gui/start.sh`'s
  trap logic. Confirmed unreachable in `--dashboard-only` mode, since
  `main.py` never runs there.
- **Fix direction (scoped as a Round 6 follow-on task, not yet applied):**
  wrap the `loader.load_primary()` call in `repl()` (`main.py` ~line
  1269) in a `try/except (KeyboardInterrupt, SystemExit)` that, on catch,
  calls the existing `shutdown()` (`main.py` line 125) to tear down any
  partially-started server via the scoped-PID path it already uses, then
  exits cleanly — reusing `shutdown()`, not reinventing a parallel kill
  path. This is CLAUDE.md rule 4 territory (process/daemon lifecycle,
  kill logic) and requires code-reviewer's explicit approval before
  commit regardless of how small the diff looks.

## Found during Round 6 NEW-5 root-cause investigation, 2026-07-29 — NOT fixed, logged only

### [NEW-6] Same unguarded `loader.load_primary()` pattern exists at three other call sites in `main.py`
- **Status: Resolved (2026-07-30, Round 8, commit `435c120`).** `main.py`'s
  `args.init`/`args.tdd`/`args.fix` sites each now wrap
  `loader.load_primary()` in `try/except (KeyboardInterrupt, SystemExit)`,
  calling the existing `shutdown()` and returning cleanly — the same
  pattern as NEW-5's `repl()` fix (`eed29dc`). code-reviewer approved.
  live-verifier ran all three sites plus a `--tdd`/`--fix` pass: 3 of 4
  site-tests (`--init` reruns x2, `--tdd`, `--fix`) came back clean —
  guard fired, no orphan `llama-server`, `ps` empty afterward, `free -h`
  recovered RAM each time. One of four `--init` attempts reproduced a
  genuine orphan (real `llama-server`, PPID 1, `ps` confirmed), root-caused
  to a residual atfork/fork-window race in the **shared**
  `core/loader_v2.py` Popen call — pre-existing in the underlying
  `try/except (KeyboardInterrupt, SystemExit)` pattern itself, not a
  regression introduced by this round's diff, and not specific to the
  three new sites (it affects `repl()`'s existing guard too). See
  `PROJECT_LOG.md` 2026-07-30 Round 8 entry for full verbatim evidence.
  **This fix works exactly as scoped** — the guard correctly catches
  `KeyboardInterrupt`/`SystemExit` and tears down via `shutdown()` for the
  vast majority of the model-load window at all three sites, matching
  NEW-5's `repl()` behavior. The residual fork-window race is a separate,
  already-logged concern, not a defect in this round's diff — tracked as
  its own entry, [NEW-9] below, since it needs its own dedicated
  scoping/fix pass (likely relocating or supplementing the guard to also
  cover the fork window itself).
- **Confidence: Suspected** (same code shape confirmed by reading the
  code; not independently live-reproduced at each site the way NEW-5 was
  for the `repl()` path — but the mechanism is identical, so the risk is
  the same in kind).
- **Where found:** while investigating NEW-5's root cause, grepped all
  call sites of `loader.load_primary()` in `main.py`. In addition to
  `repl()` (~line 1269, the one covered by NEW-5's scoped fix), the same
  unguarded pattern (`loader = get_loader(); loader.load_primary()` with
  no surrounding `try/except KeyboardInterrupt`) appears at:
  - `args.init` path, `main.py` ~line 1458
  - `args.tdd` path, `main.py` ~line 1465-1466
  - `args.fix` path, `main.py` ~line 1485-1486
- **Why this matters:** a `KeyboardInterrupt` (e.g. Ctrl+C) during model
  load in any of these one-shot CLI paths would hit the same gap as
  NEW-5 — no handler catches it before it propagates out of
  `load_primary()`, `shutdown()` is never called, and `llama-server`
  (spawned in its own process group via `preexec_fn=os.setsid`) is left
  as an orphan.
- **Not fixed here:** the NEW-5 fix task is deliberately scoped to just
  the `repl()` call site (the one actually live-reproduced). These three
  sibling sites are logged for a possible dedicated follow-up task, not
  bundled into the NEW-5 fix, to keep that fix tightly scoped per
  CLAUDE.md's project-architect instructions.

## Found during Round 9 (NEW-9) scoping pass, 2026-07-30 — NOT fixed, logged only

### [NEW-10] `main.py` has no `SIGTERM` handler at all — a direct `SIGTERM` during model load (or any point) terminates the process instantly, bypassing every existing `try/except (KeyboardInterrupt, SystemExit)` guard entirely
- **Confidence: Suspected.** Confirmed via code-reading and a Python
  semantics check (`signal.getsignal(signal.SIGTERM)` returns `SIG_DFL`
  in a fresh interpreter; `grep -n "signal\." main.py` shows no
  `signal.signal(signal.SIGTERM, ...)` call anywhere in `main.py`) —
  not yet live-reproduced as an actual orphan from a direct `SIGTERM`
  sent to the `main.py` process itself (distinct from NEW-5's Round 6
  finding, which was about `gui/start.sh`'s bash wrapper not forwarding
  `TERM` to its foreground child, a different mechanism).
- **Where found:** while root-causing NEW-9's atfork/fork-window race
  (Round 9 scoping pass), checked whether the same race applies to
  `SIGTERM` as well as `SIGINT`. It does not apply in the same way —
  it's worse. `SIGINT` has a default Python-level handler
  (`signal.default_int_handler`) that raises `KeyboardInterrupt`, which
  is what lets `try/except (KeyboardInterrupt, SystemExit)` guards catch
  it at all (when the atfork race doesn't swallow it first). `SIGTERM`'s
  disposition in `main.py` is unmodified `SIG_DFL`, whose default action
  is immediate process termination at the kernel level — it never
  reaches Python bytecode, never raises any exception, and cannot be
  caught by any `try/except`, including the NEW-5/NEW-6 guards, at any
  point in the model-load window (not just the narrow fork window NEW-9
  describes).
- **Impact if confirmed:** a direct `kill -TERM <main.py PID>` (as
  opposed to sending TERM to `gui/start.sh`'s bash wrapper, which was
  NEW-5's original scenario) during model load would orphan
  `llama-server` unconditionally, 100% of the time, with none of the
  NEW-5/NEW-6/NEW-9 guard work having any effect on this path.
- **Not fixed here:** out of scope for NEW-9's scoping pass, which is
  specifically about the `SIGINT`/`KeyboardInterrupt`/atfork race.
  Needs its own dedicated scoping pass: likely direction is installing
  an explicit `signal.signal(signal.SIGTERM, ...)` handler early in
  `main.py` that translates `SIGTERM` into a controlled shutdown path
  (e.g. raising `SystemExit` or directly invoking the existing
  `shutdown()`), which is CLAUDE.md rule 4 territory and needs
  code-reviewer's explicit approval before commit.

## Found during Round 10 NEW-9 follow-up discussion, 2026-07-30 — NOT fixed, logged only

### [NEW-11] Daemon's 30s watchdog checks a stale in-memory flag, not real process liveness
- **Status: Resolved (Round 13, commit `ab13a8d`).** code-reviewer
  approved. **Fully live-verified**, after two earlier live-verification
  attempts crashed Termux entirely at 7B model-load time (via the full
  `codeydOS start`, which also spawns a separate 1.5B "plannd" planner
  process) and a third attempt self-aborted proactively (per the
  live-verifier's own safety instructions) after observing swap climb
  from a ~1Gi baseline to 7.5-8.5Gi within ~40 seconds of steady-state
  startup with all three models running — see [NEW-14] below. The
  successful verification used a lighter, isolated harness instead:
  launching the daemon directly via `python3 main.py --daemon` (bypassing
  the `codeydOS` wrapper script that spawns the separate plannd process),
  running only the 7B primary + embed server. Baseline `free -h`:
  `used 3.3Gi / available 7.3Gi / swap 1.2Gi`. After daemon+7B+embed
  started (confirmed via `ps` — no plannd process present):
  `used 8.7Gi / available 1.8Gi / swap 1.8Gi`, stable, no aggressive
  climb. `curl http://127.0.0.1:8080/health` → `{"status":"ok"}`. Killed
  the tracked `llama-server` PID (921) directly via `kill -9 921` (not a
  name-pattern kill). Watchdog fired on schedule, literal daemon log:
  ```
  2026-07-30 01:11:41,418 - WARNING - 7B model server died — restarting...
  2026-07-30 01:11:41,444 - INFO - llama-server PID: 3034, logging to .../llama-server.log
  2026-07-30 01:11:51,056 - INFO - llama-server started on port 8080
  ```
  New PID (3034) confirmed distinct from the killed PID (921), fired at
  exactly the expected 30s-tick timing (4 ticks after the daemon started
  listening). A real inference call against the restarted server (not
  just a health check) returned `{"choices":[{"message":{"content":"PONG"}}]}`.
  Clean teardown via `SIGTERM` on the tracked daemon PID (845) — the
  daemon's own shutdown path stopped the model server and embed server
  itself (`Stopping model server... / Embed server stopped / Daemon
  socket stopped / Daemon stopped`). Final `ps` empty, PID file and
  socket file both removed. Final `free -h`:
  `used 2.9Gi / available 7.6Gi / swap 1.7Gi`. Peak swap this run: ~1.9Gi
  (vs. 7.5-8.5Gi in the full 3-model-stack attempt), confirming the
  separate plannd process was the dominant RAM/swap pressure source, not
  the daemon/watchdog code itself.
- **Confidence: Confirmed** (read directly from code, not inferred).
- **Where:** `core/daemon.py:549-563`, the periodic (every 30s / 60 ticks
  × 0.5s) watchdog inside `_main_loop`. It checks
  `loader.get_loaded_model()` and, if falsy, logs `"7B model server
  died — restarting..."` and calls `loader.load_primary()`.
- **The gap:** `get_loaded_model()` (`core/loader_v2.py:382-384`) just
  returns `"primary" if self._loaded else None` — an in-memory boolean
  set once at load time. It does **not** call `self.process.poll()` or
  otherwise check real process liveness. Once `self._loaded` becomes
  `True`, it stays `True` forever (no periodic poll resets it), so this
  watchdog only catches "the daemon never successfully loaded the model
  in the first place" — it would **not** detect a genuine mid-session
  crash of an already-successfully-loaded `llama-server` while the
  daemon keeps running.
- **Mitigating factor:** the daemon is not the only safety net.
  `core/inference_v2.py:90-94` calls `loader.ensure_model()` on every
  single inference request, and `ensure_model()`
  (`core/loader_v2.py:376-380`) **does** check real liveness
  (`is_running()` → `process.poll()`/HTTP health check) and will
  respawn via `load_primary()` if genuinely dead. So a crash would
  still self-heal on the next inference call, just not proactively via
  the watchdog.
- **Impact:** Low-to-medium. Not a process-orphaning bug itself
  (opposite problem — it under-reacts, not over-spawns), but it means
  the daemon's own dashboard/status data could show "model loaded" when
  it's actually dead, for however long until the next real inference
  request.
- **Not fixed here** — logging only, per CLAUDE.md rule 8. Fix direction
  for a future pass: change the watchdog's check to call
  `loader._server.is_running()` (real liveness) instead of
  `get_loaded_model()` (stale flag), or reset `self._loaded = False`
  when `is_running()` becomes false.
- **Relation to NEW-9:** separate, unrelated mechanism — **not** the
  same bug. Confirmed by direct evidence: NEW-9's live-reproductions
  all happened 2026-07-30 while `~/.codeyOS/codeyOS.log` shows the
  daemon was only ever started once, on 2026-07-29 13:35, and never run
  since (no PID file, no process currently alive). The daemon could not
  have been involved in any NEW-9 reproduction.

### [NEW-12] Duplicated/scattered model-launch configuration — a second, uncoordinated `llama-server` launcher exists with no port-conflict check
- **Confidence: Confirmed** (read directly from code — exact file:line
  citations below, not inferred).
- **Where found:** investigating the user's report that changing which
  model Codey-OS uses required updating the path in multiple locations.
- **Core finding:** there are two independent places that build and
  launch a `llama-server` subprocess command for the primary 7B model
  on port 8080, not one:
  1. `core/loader_v2.py:127` (`LlamaServer.start()`, in `LlamaServer`
     class) — the canonical path used by daemon and CLI via
     `get_loader()`. Command built at `core/loader_v2.py:58-110`. Uses
     `os.setsid` (line 131) for clean process-group teardown via
     `killpg` (line 179). Does check port-in-use before spawning
     (`loader_v2.py:49-53`, `_is_port_in_use()` at 212-231) and reuses
     an existing server if one answers instead of double-spawning.
  2. `core/inference.py:40-103` (`_start_server()`) — a second, legacy
     launcher with a different flag set (no `--host`, no `--embedding`,
     no mmap/mlock handling; see `core/inference.py:60-79`). Has **no**
     port-in-use check at all before `subprocess.Popen` (line 84) —
     only skips spawning if its own module-global `_server_proc` is
     already alive, which is irrelevant to whether some other process
     already has port 8080 bound. No `os.setsid`/process-group
     detachment — plain `Popen` with `stdout=DEVNULL, stderr=DEVNULL`
     (no logs, no group-kill handle). Its `stop_server()`
     (`core/inference.py:106-110`) is never called from anywhere in the
     codebase (confirmed via grep, zero callers) — meaning if this path
     spawns a server, nothing in the daemon's shutdown path
     (`core/daemon.py:583-588`, which only knows about
     `loader_v2.get_loader().unload()`) or anywhere else ever tears it
     down.
- **Is the legacy path reachable, or dead code? Reachable, not dead.**
  `core/inference_v2.py:192-213` (`_infer_http`) imports and calls
  `core.inference.infer` as a fallback (`core/inference_v2.py:196`),
  triggered whenever the primary chat backend fails to initialize or
  throws an exception (`core/inference_v2.py:59-61` init exception
  path, `core/inference_v2.py:99-106` mid-request exception path). So
  under a real, plausible failure condition, live code will call into
  `core/inference.py`'s independent, no-port-check, never-torn-down
  launcher.
- Port 8080 has no single named config constant (unlike ports
  8081/8082, which have `PLANND_SERVER_PORT`/`EMBED_SERVER_PORT` in
  `utils/config.py`) — it's hardcoded independently in
  `core/loader_v2.py:25` (`SERVER_PORT = 8080`),
  `core/inference.py:14,77`, and `core/inference_hybrid.py:34`
  (`port: int = 8080` default param).
- **Separately (same investigation, related but distinct):**
  `PLANNER_MODEL_PATH`/`PLANND_SERVER_PORT` are defined in
  `utils/config.py:233-239` but never read by any process-launching
  code anywhere in the repo (confirmed via grep) — the 1.5B planner
  server is evidently expected to be started manually by the user via a
  hand-typed shell command, completely disconnected from
  `utils/config.py`. `docs/configuration.md:155` also documents the
  wrong default model file for this (`~/models/qwen2.5-0.5b/...`) vs.
  what `utils/config.py:236` actually defaults to
  (`~/models/qwen2.5-coder-1.5b/...`), and `install.sh:36,41` builds/
  downloads yet another value independently. This is very likely the
  direct cause of the user's "had to update the model path in multiple
  locations" experience for the planner model specifically (the
  primary 7B model's path is properly centralized via `MODEL_PATH` in
  `utils/config.py`, imported consistently by `core/loader_v2.py`,
  `core/inference.py`, `core/lora_import.py`).
- **Cross-process coordination:** within one Python process,
  `get_loader()` is a true singleton (module-level,
  `core/loader_v2.py:417-422`) so one process can't double-spawn via
  `loader_v2` alone. But across processes (e.g. the daemon and a
  separately/directly-run `python3 main.py` CLI invocation, each with
  their own independent `ModelLoader` singleton), the only protection
  is the `_is_port_in_use()` HTTP probe — a TOCTOU race, not a lock. If
  both processes start near-simultaneously during the up-to-60s
  health-check window (`loader_v2.py:139` polls up to 60s), both could
  see port 8080 as free and both attempt to spawn. There is no
  flock/pidfile-based mutex dedicated to the model-server port itself
  (the daemon's own `fcntl.flock` at `core/daemon.py:55-93` only
  prevents daemon-vs-daemon double-start, not daemon-vs-CLI).
- **Impact/assessment:** this is a plausible, concrete contributing
  factor to the broader family of process-lifecycle bugs already
  tracked (NEW-5/NEW-6/NEW-9), not purely a maintainability nuisance —
  specifically via (a) the untracked, no-port-check
  `core/inference.py:_start_server()` fallback path, reachable in
  production, capable of spawning an unmanaged second `llama-server`
  with no cleanup hook, and (b) the TOCTOU race window in
  `_is_port_in_use()` when a daemon and a CLI process start close
  together. Not confirmed as the direct cause of any specific
  already-reproduced NEW-5/6/9 orphan (those were traced to a
  different, lower-level atfork/signal-timing mechanism, confirmed
  unrelated to this in the NEW-11 write-up above) — this is a separate,
  additional risk in the same problem family, not a re-explanation of
  the already-diagnosed bugs.
- **Not fixed here** — logging only, per CLAUDE.md rule 8. Fix
  directions for a future dedicated pass (do not scope as a task yet,
  just list as candidates):
  1. Quarantine or delete `core/inference.py`'s independent
     `_start_server()`/`Popen` launcher — route its fallback through
     `core.loader_v2.get_loader()` instead of building its own command.
  2. Add a single named `SERVER_PORT`/`PRIMARY_SERVER_PORT` constant in
     `utils/config.py` that all three files (`loader_v2.py`,
     `inference.py`, `inference_hybrid.py`) import, instead of each
     hardcoding `8080` independently.
  3. Either wire `PLANNER_MODEL_PATH`/`PLANND_SERVER_PORT` into an
     actual launcher (so the 1.5B planner starts the same way the 7B
     model does) or remove/clearly-mark them as unused-today in
     `utils/config.py` and `docs/configuration.md`, and fix
     `docs/configuration.md:155`'s wrong default to match
     `utils/config.py:236`.
  4. Consider replacing/augmenting the HTTP port-probe
     (`_is_port_in_use()`) with a real cross-process lock (e.g. an
     flock'd `.pid`/`.lock` file per port) before spawning, to close the
     daemon-vs-CLI TOCTOU race.

**Status: Resolved (Round 11, commit `59f4f69`).** Fixed exactly item 1
of the fix directions above: `core/inference.py`'s independent,
uncoordinated `_start_server()`/`Popen` launcher was removed and its
fallback path now delegates to `core.loader_v2.get_loader().ensure_model()`
— the canonical, port-checked, singleton-guarded launcher. code-reviewer
approved (and separately flagged a scope-adjacent regression, now logged
as [NEW-13] below). Live-verified: `free -h` before (`4.5Gi` used,
`2.9Gi` free) / after (`4.5Gi` used, `3.2Gi` free) showed no RAM leak;
starting the primary model then calling the fallback `core.inference.infer()`
in the same process produced no second `"Loading model:"`/`"Starting
llama-server..."`/`"llama-server PID:"` log line (i.e. no second `Popen()`
was invoked — `ensure_model()` short-circuited on its already-running
check) and the fallback call returned a real completion (`'Hello'`), not
an `[ERROR]` string; teardown used the single tracked PID. **Caveat:**
this is verified via log-line-absence + successful-completion +
clean-teardown evidence, not a literal multi-checkpoint `ps` snapshot —
the verifier's in-script `ps` capture had a filter bug (`ps`'s COMMAND
column truncates `llama-server` to `llama-serv`, so the substring match
never actually confirmed "exactly one process" via a literal `ps` table
at each checkpoint) and was not re-run, per the one-cycle-only RAM
discipline rule. Items 2-4 of the fix directions above (a single named
port constant, wiring the planner launcher, a real cross-process lock)
remain open, deferred to a future round.

### [NEW-13] Removing `core/inference.py`'s independent launcher (Round 11, NEW-12 fix, commit `59f4f69`) orphaned `ThermalManager`'s thread-reduction restart mechanism
- **Status: Resolved (Round 12, commit `0935cbd`).** Wired an equivalent
  restart-recommended check into `core/loader_v2.py`'s `ensure_model()`
  — when `ThermalManager.restart_recommended` is set, it now stops and
  restarts the running primary `llama-server` with the updated thread
  count and clears the flag. code-reviewer approved, with two
  non-blocking Warnings (no lock around the check-then-act sequence —
  not currently exploitable with only one call site; no unit test
  coverage of the new branch). **Fully live-verified:** started the
  primary model (PID 14619), forced `restart_recommended = True`,
  called `ensure_model()` again in the same process — confirmed a real
  restart (not a short-circuit): PID changed 14619 → 14800, old PID
  gone (`ps -p 14619` returncode 1), the flag correctly cleared
  afterward, a real inference call issued post-restart returned `'OK'`
  (not an error string), and clean teardown (`ps -p 14800` returncode 1
  after `unload()`). Verified via exact-PID `ps -p <pid>` checks rather
  than a `comm`-substring grep, since Termux's `ps` truncates `COMMAND`
  to `llama-serv` and would false-negative a `"llama-server"`
  substring match (environmental wrinkle, not a code defect).
  `free -h` before (`4.9Gi` used, `2.0Gi` free) / after (`3.3Gi` used,
  `5.6Gi` free) showed full RAM recovery, no leak. An unrelated test
  artifact (the inference call's side-effect embed server, PID 15580)
  was cleaned up by its own tracked PID, not a name-pattern kill.
- **Confidence: Confirmed** (found by code-reviewer during Round 11's
  NEW-12 review, verified via repo-wide grep, not inferred).
- **Where:** `core/thermal.py`'s `ThermalManager` class sets
  `self.restart_recommended = True` when `_reduce_threads()` fires
  (sustained inference triggers a thread-count reduction to manage
  device heat). The class's own comment states this flag exists so that
  "inference.py checks this and restarts llama-server with the updated
  thread count on next call." Before Round 11, `core/inference.py`'s
  `_start_server()` was the ONLY consumer of `restart_recommended`
  anywhere in the repo (confirmed via repo-wide grep for
  `restart_recommended`/`ThermalManager`/`get_thermal_manager`) — it
  checked the flag, terminated the old `_server_proc`, and restarted
  `llama-server` with the reduced thread count.
- **What changed:** Round 11's NEW-12 fix (commit `59f4f69`) removed
  `core/inference.py`'s independent `_start_server()` entirely (it was
  an uncoordinated, port-check-free llama-server launcher, correctly
  removed for that reason) and replaced it with a delegation to
  `core.loader_v2.get_loader().ensure_model()`. `core/loader_v2.py`'s
  launcher has no equivalent thermal-restart check anywhere in its own
  code path — it was never wired up there, since `core/inference.py`'s
  fallback path was thermal.py's only consumer.
- **Impact:** `ThermalManager` still detects sustained inference, still
  warns, and still reduces `MODEL_CONFIG["n_threads"]` in memory — but
  the actual server restart that was supposed to apply the new
  (reduced) thread count to the already-running `llama-server` process
  no longer fires from anywhere. This silently breaks the device-heat
  mitigation `core/thermal.py`'s own module docstring advertises
  (reducing threads after sustained inference to prevent thermal
  throttling on this mobile device).
- **Not fixed here** — logging only, per CLAUDE.md rule 8 (found outside
  NEW-12's stated scope during its review, correctly not silently fixed
  nor silently dropped). This is a real, if narrow, functional
  regression, not just a maintainability note — flag it as Confirmed,
  not Suspected.
- Fix direction for a future dedicated pass (not scoped here): wire an
  equivalent restart-recommended check into `core/loader_v2.py`'s
  `ModelLoader`/`LlamaServer` (the now-canonical launcher), likely
  inside `ensure_model()` or a periodic check point, so the mitigation
  applies regardless of which code path (primary or fallback) is
  currently in use. Needs its own scoping pass to decide exactly where
  the check belongs given `loader_v2.py`'s different structure (e.g.
  the NEW-9-hardened `pthread_sigmask` block around `Popen` — any
  restart logic must not interfere with that).

## Found during Round 13 (NEW-11) live-verification, 2026-07-30 — NOT fixed, logged only (observational)

### [NEW-14] Full `codeydOS start` (daemon + 7B + 1.5B plannd + embed server, all three models concurrently) pushes this device into severe swap pressure within seconds, even under normal conditions
- **Confidence: Confirmed** (directly observed, and consistent with two
  earlier Termux crashes at model-load time before this pattern was
  understood).
- **Where observed:** during Round 13 (NEW-11) live-verification. The
  first two live-verification attempts, both using the full `codeydOS
  start` wrapper (which launches the daemon plus the 7B primary model,
  the separate 1.5B "plannd" planner process, and the embed server, all
  concurrently), crashed Termux entirely, apparently right at 7B
  model-load time. A third attempt, same full stack, did not crash but
  self-aborted proactively per the live-verifier's own safety
  instructions after observing swap climb from a ~1Gi baseline to
  7.5-8.5Gi used within ~40 seconds of steady-state daemon startup —
  well before the actual kill/restart test began. Verbatim readings:
  `check 1: used 9.0Gi available 1.5Gi swap 4.6Gi` →
  `check 2: used 9.0Gi available 1.5Gi swap 7.1Gi` → settled around
  `swap 7.5Gi`. The device stayed responsive only because the test
  aborted itself in time, not because the risk wasn't real.
- **Contrast:** a fourth attempt, using a lighter, isolated harness
  (`python3 main.py --daemon` directly, bypassing the `codeydOS` wrapper
  and thus skipping the separate plannd process — only the 7B primary +
  embed server running), completed the same test safely with peak swap
  around ~1.9Gi, a small fraction of the full-stack figure. This strongly
  suggests the separate 1.5B plannd process (or the combination of all
  three models loading concurrently) is the dominant swap-pressure
  source, not the daemon/watchdog code exercised by the test itself.
- **Impact:** this is not a code bug — no exception, no crash-inducing
  logic error was found. It appears to be the genuine resource cost of
  running the full 3-model stack concurrently on this specific ~10.8GB
  device. It may explain other historical flakiness/crashes previously
  attributed to unclear causes, and is directly relevant to CLAUDE.md's
  RAM-discipline rule 2.
- **Not fixed here, and not necessarily fixable in a traditional
  code-level sense** — logged per CLAUDE.md rule 8 as a device-capacity
  finding worth preserving, not a bug to scope. Candidate follow-ups for
  a future pass (not scoped here): explicit user-facing documentation
  that the full `codeydOS start` (all three models) is heavy on
  ~10.8GB-class devices and should not be run alongside other memory-
  intensive live-verification tests; consider whether the daemon-only /
  plannd-optional lighter path used successfully here should become a
  documented, supported "lite" mode for constrained devices.

## Found during Round 8 (NEW-6) live-verification pass, 2026-07-30 — NOT fixed, logged only

### [NEW-9] Residual, intermittent atfork/fork-window race can silently bypass the `try/except (KeyboardInterrupt, SystemExit)` model-load guard at all four sites (`repl()`, `args.init`, `args.tdd`, `args.fix`)
- **Status: STILL OPEN — Round 9 fix attempt (commit `1a1c0b7`) did NOT
  close this**, corrected 2026-07-30 per CLAUDE.md rule 6 after Round 9's
  own live-verification. `1a1c0b7` wrapped only the `subprocess.Popen(...)`
  call itself in `signal.pthread_sigmask(SIG_BLOCK/SIG_UNBLOCK)`, but
  live-verifier's repeated-attempt testing (16 valid independent attempts)
  reproduced the identical orphan in 3/16 (~19%), statistically
  indistinguishable from the original ~1-in-4 rate. Root cause of the
  fix's failure: the vulnerable window starts far earlier than the
  `Popen()` call — the `"Starting llama-server..."` log line fires at
  `core/loader_v2.py` line ~55, roughly 70 lines before the
  `pthread_sigmask(SIG_BLOCK)` call at line ~125 (command-list
  construction, mmap/mlock config lookup, log-file open all happen in
  between, unguarded). A `SIGINT` landing in that gap is delivered
  normally by the OS before the mask is ever applied, arms the
  interpreter's pending-interrupt flag, and can still surface inside the
  forked child's atfork callback exactly as before — the mask was simply
  placed too late to cover the real window. Verbatim reproduction
  (attempt a9 of 16): `Exception ignored in atfork callback` printed,
  `"Interrupted during model load, cleaning up..."` never printed, and
  `ps -p 14123 -o pid,ppid,pgid,etimes,cmd` confirmed a real orphan
  (`14123  1  14123  13  .../llama-server ...`). Do not consider `1a1c0b7`
  a completed fix — it is a partial, insufficient mitigation left in
  place (harmless, narrows nothing meaningfully, but not the fix). This
  needs a fresh scoping pass that moves the block point up to cover the
  full window from the log line (or earlier) through the `Popen()` call,
  not just the call itself.
- **Status: STILL OPEN — Round 10 fix attempt (commit `2aaabb1`)
  substantially reduced but did NOT fully close this**, corrected
  2026-07-30 per CLAUDE.md rule 6 after Round 10's own live-verification.
  `2aaabb1` widened the masked region identified as missing in Round 9's
  correction above — moving `signal.pthread_sigmask(SIG_BLOCK)` up to
  cover the full window from at/before `"Starting llama-server..."`
  through the `Popen()` call, not just the call itself.
  live-verifier's repeated-attempt testing (22 valid, independent
  attempts, `pty.fork()`-based harness, tracked child PID, real
  `os.kill(pid, SIGINT)`, delay varied 0.0s-0.3s; 4 additional attempts
  were invalid/contaminated by leftover orphans from earlier failures and
  excluded from the count) found **20/22 clean at delays ≥0.03s, but 2/22
  FAILED — both at delay=0.0s** (`SIGINT` sent the instant `"Starting
  llama-server..."` was observed), reproducing the identical
  `atfork`-swallowed-`KeyboardInterrupt` orphan symptom. This is a real,
  substantial improvement (2/22 ≈ 9%, clustered only at the absolute
  earliest timing, vs. Round 9's 3/16 ≈ 19% spread across the whole
  range, vs. the original ~1-in-4 to ~1-in-5 rate) — but it is **not**
  zero, and this is now the **second consecutive fix attempt on NEW-9 to
  be live-verified as incomplete**. Verbatim reproduction (attempt a01 of
  22):
  ```
  ℹ  Starting llama-server...
  ℹ  7B model: mmap=enabled, mlock=disabled
  Exception ignored in atfork callback <function _afterFork at 0x764aa8b530>:
  Traceback (most recent call last):
    File ".../python3.14/logging/__init__.py", line 245, in _afterFork
      def _afterFork():
  KeyboardInterrupt:
  ℹ  llama-server PID: 9141, logging to /data/data/com.termux/files/home/.codeyOS/llama-server.log
  ✓  llama-server started on port 8080
  ✓  Loaded model (qwen2.5-coder-7b-instruct-q4_k_m.gguf)
  ...
  You>
  ```
  The `KeyboardInterrupt` was silently swallowed by CPython's atfork
  machinery, never reached `main.py`'s `except (KeyboardInterrupt,
  SystemExit)` guard. The REPL continued as if uninterrupted, loaded the
  model fully, sat at the `You>` prompt. Post-check: `ps` showed PID
  9141, `llama-server`, PPID 1 (orphaned/reparented to init), 224s
  elapsed, 1.87GB RSS. Killed via `kill -TERM 9141` (exact tracked PID),
  confirmed reaped, RAM recovered. A second, independent attempt (a24)
  reproduced an identical failure signature (same `atfork` traceback),
  PID 15693, PPID 1, 128s elapsed, 914MB RSS — also killed by tracked PID
  and confirmed reaped. **Root cause observation (not yet a confirmed fix
  path):** both failures show `KeyboardInterrupt` raised *inside*
  `logging._afterFork`, an `os.register_at_fork()` callback invoked as
  part of `subprocess.Popen()`'s internal `fork()` — even though
  `signal.pthread_sigmask(SIG_BLOCK, {SIGINT})` is active for the entire
  widened region at the time of the interrupt. The mask should be
  preventing `SIGINT` from reaching Python's normal signal-check point at
  all, yet this specific atfork-callback code path still independently
  observes/raises the interrupt. This suggests the remaining failure mode
  is deeper than "the guarded window was too narrow" (which explained
  Round 9's failure and which Round 10 correctly fixed for the vast
  majority of the window) — possible explanations not yet confirmed
  include a Termux/Android-specific signal-delivery quirk, or some
  property of CPython's atfork-callback execution that isn't fully
  governed by `pthread_sigmask` in this environment. **`2aaabb1` is not
  being reverted** — it is a genuine, verified improvement, not a
  regression — but it must not be described anywhere as having resolved
  NEW-9. A third fix attempt should not simply repeat the "widen the
  masked window further" approach without new information: the Round
  9→Round 10 pattern (progressively widening the masked region) has
  shown diminishing but nonzero returns and does not appear to be
  converging to zero through mask-widening alone. Per CLAUDE.md's
  escalation rules, this is being brought to Ish directly for a decision
  on how to proceed — no new fix attempt has been scoped here.
- **Confidence: Confirmed** (directly reproduced live during Round 8's
  live-verification of the NEW-6 fix — a real orphaned `llama-server`
  process was caught, root-caused by reading CPython's `subprocess.Popen`/
  `os.fork()` internals, not inferred). Reconfirmed as still-open via
  Round 9's 16-attempt live-verification above.
- **Where found:** Round 8 live-verifier's `--init` testing (attempt 1 of
  4 total attempts across all four guarded call sites). Hit rate observed:
  1-in-4 across this round's testing.
- **Root cause:** `core/loader_v2.py`'s `LlamaServer.start()`
  (~lines 116-130) calls `subprocess.Popen(...)`, which internally performs
  `os.fork()`. If a `SIGINT` arrives in the narrow window during that
  internal fork, CPython's own atfork exception-handling machinery
  (specifically observed here interacting with `logging`'s
  `_afterFork` callback) can silently discard the resulting
  `KeyboardInterrupt` before it ever propagates up to the caller's
  `try/except (KeyboardInterrupt, SystemExit)` guard. The guard code
  itself is not wrong — it simply never gets invoked, because the
  exception is swallowed one layer below it, inside the standard library.
  This means the guard pattern introduced by NEW-5's fix (`eed29dc`) and
  extended by NEW-6's fix (`435c120`) has a real, narrow gap that no
  amount of correct `try/except` placement at the call site can close on
  its own.
- **Affected call sites — all four that share this guard pattern:**
  - `repl()`, `main.py` (NEW-5's original fix, `eed29dc`)
  - `args.init`, `main.py` (NEW-6's fix, `435c120`)
  - `args.tdd`, `main.py` (NEW-6's fix, `435c120`)
  - `args.fix`, `main.py` (NEW-6's fix, `435c120`)
- **Reproduction evidence (verbatim, `--init` attempt 1, Round 8):**
  ```
  CHILD_PID=27122
  ℹ  Starting llama-server...
  >>> SENDING SIGINT to 27122 at t=0.18s
  Exception ignored in atfork callback <function _afterFork at 0x73f8ff7530>:
  Traceback (most recent call last):
    File ".../logging/__init__.py", line 245, in _afterFork
  KeyboardInterrupt:
  ℹ  llama-server PID: 27124, logging to /data/data/com.termux/files/home/.codeyOS/llama-server.log
  >>> CHILD STILL RUNNING after wait loop
  ```
  Post-check: `ps -p 27124 -o pid,ppid,pgid,etimes,cmd` showed
  `27124  1  27124  62  .../llama-server -m ...` — a real orphan (PPID=1,
  reparented). The expected "Interrupted during model load, cleaning
  up..." message never printed — the guard's `try/except` never fired.
  live-verifier killed it directly by tracked PID (`kill -TERM 27124`),
  confirmed reaped, RAM recovered. All 3 subsequent attempts across the
  other sites (`--init` rerun, `--tdd`, `--fix`) came back clean — guard
  fired correctly each time.
- **Impact:** in this narrow, timing-dependent window (hit 1-in-4 across
  Round 8's own testing), `llama-server` can still be orphaned
  indefinitely on `SIGINT` during model load, at any of the four call
  sites — the same underlying failure mode NEW-5/NEW-6 were meant to
  close, just a much narrower slice of it than either fix targeted.
- **Not fixed here — deliberately out of scope for Round 8**, whose scope
  was limited to NEW-6's three sibling call sites (same fix, same pattern
  as NEW-5 already had). This is a different, deeper problem in the
  shared `core/loader_v2.py` Popen/fork mechanism itself, not something
  the existing guard pattern can be fixed to catch without a different
  approach.
- **Fix direction (not scoped, needs its own dedicated pass):** the
  guard cannot be relocated to "wrap the fork itself" in the naive sense,
  since the swallowing happens inside CPython/stdlib internals during
  `os.fork()`, not in caller-reachable code. Plausible directions for a
  future scoping pass to evaluate (none decided here):
  - Investigate whether disabling/deferring the `logging` module's atfork
    handler (the specific callback seen swallowing the exception in the
    reproduction above) around the `Popen()` call changes the behavior.
  - Consider an interrupt-safe mechanism that doesn't rely on
    `KeyboardInterrupt` propagation through the fork window at all — e.g.
    a signal handler installed before the `Popen()` call that sets a flag
    checked immediately after, rather than depending on the exception
    reaching a `try/except` above the call.
  - Confirm whether this is Termux/Android-`libc`-specific or general
    CPython behavior on any Linux target, since that affects how
    aggressively to prioritize a fix.
  - Any fix needs code-reviewer's explicit approval before commit per
    CLAUDE.md rule 4 (process-lifecycle/kill-logic changes) — this
    touches the exact category that has produced this project's worst
    bugs before.
- **Queue position:** discovered mid-Round-8, not part of the original
  four-item punch list (NEW-3/1/5/2) or the two incidental follow-ups
  already queued (NEW-4, NEW-7). Recommend asking Ish whether this should
  be prioritized ahead of NEW-4/NEW-7 in the queue (it's a RAM-crash-class
  process-lifecycle gap, arguably higher severity) or simply appended
  after them — not decided unilaterally here.

## Found during Round 2 (C-2) live-verification pass, 2026-07-29 — NOT fixed, logged only

### [NEW-4] `gui/start.sh` unconditionally chains into `main.py`, forcing a full 7B model load just to view the dashboard
- **Status: RESOLVED (2026-07-29, Round 3, commit `ea954eb`).** This
  entry was never marked Resolved despite the fix landing back in
  Round 3 — corrected 2026-07-30. `gui/start.sh` gained an opt-in
  `--dashboard-only` flag (or `CODEY_GUI_DASHBOARD_ONLY=1` env var)
  that skips `main.py`'s eager 7B model load entirely and just serves
  the GUI/dashboard, waiting on the GUI server's own PID instead.
  Default (no-flag) behavior is unchanged — still chains into
  `main.py` — matching the original suggested direction below (an
  opt-in decoupling, not a default-behavior change). code-reviewer
  approved (one non-blocking suggestion: last-positional-arg-wins in
  the new arg-parsing loop, latent/no current caller affected). Fully
  live-verified: default path showed a real model-load cycle
  (`free -h` 8.3Gi used during load → 3.1Gi after teardown);
  `--dashboard-only` path confirmed via `pgrep` that no `main.py` or
  `llama-server` process ever started, and `curl` to the dashboard
  endpoint returned 200. See `PROJECT_LOG.md`'s 2026-07-29 Round 3
  entry for full verbatim evidence. (This round's live-verification
  also surfaced the original NEW-5 finding as a side observation,
  since separately resolved.)
- **Confidence: Confirmed** (directly observed live during the C-2
  live-verification pass, not inferred).
- **Where found:** live-verifier's real launch of `gui/start.sh` (the
  actual daemon-managed GUI startup path, not a scratch instance) while
  confirming C-2's GUI-security fixes end-to-end.
- **Finding:** `gui/start.sh` unconditionally chains into `main.py` after
  starting `gui/server.py`, and `main.py` eagerly loads the 7B model with
  zero user interaction required. There is no path to bring up the GUI
  server/dashboard alone without also paying the full 7B model-load cost
  — observed directly: launching via `gui/start.sh` triggered a real
  `llama-server` 7B load (PID 25675) before the dashboard was usable.
- **Impact:** a user who only wants to check the dashboard (RAM/CPU/temp,
  task status, etc.) via the GUI has no way to do so without incurring a
  full model load, which on this device is a meaningful RAM/time cost and
  runs against this project's RAM-discipline concerns (rule 2 in
  `CLAUDE.md`).
- **Suggested direction (not applied — out of scope for the C-2
  live-verification task that found it):** decouple `gui/server.py`'s
  dashboard-only capabilities (which read from `core/dashboard_data.py`,
  not the model) from `main.py`'s model-loading REPL, so `gui/start.sh`
  can optionally start just the dashboard server without also spawning
  `main.py`. Needs its own scoped task — not a security issue, a
  resource-cost/UX one.

## Found during Round 2 (C-2 GUI security) sub-task 3/3, 2026-07-29 — RESOLVED in Round 4, commit `efe9f5c`

### [NEW-3] GUI session token may leak into access logs if logging is ever configured for `gui/server.py`
- **Status: RESOLVED (2026-07-29, commit `efe9f5c`).** `gui/server.py`'s
  `web.run_app()` call now passes `access_log=None`, disabling aiohttp's
  default `AccessLogger` outright rather than relying on the current
  absence of a configured `logging` handler to keep the token dormant.
  code-reviewer approved: confirmed `access_log` is a genuine documented
  `aiohttp` kwarg (aiohttp 3.14.3 installed) and verified no other log
  call site in `gui/server.py` could leak the token. No live-verification
  performed for this fix specifically — scoped as a negative/absence
  assertion with no new live-session behavior to exercise, already
  covered by the prior Round 2 (C-2) full live-verification of normal GUI
  start (see `PROJECT_LOG.md`). Original finding detail preserved below.
- **Confidence: Suspected** (dormant today, plausible future trigger; not
  verified as currently reachable).
- **Where found:** code-reviewer's review of the C-2 sub-task 3 session-token
  commit (`1198ba1`).
- **Location:** `gui/server.py`, `web.run_app()` call (entry point, ~line 300).
- **Finding:** `web.run_app(make_app(), host=HOST, port=PORT, print=lambda
  *_: None)` is called without `access_log=None`, so aiohttp's default
  `AccessLogger` remains active and logs the full request line — including
  the `?token=<SESSION_TOKEN>` query string on `/ws` upgrade requests — at
  INFO level via Python's `logging` module.
- **Why not currently exploitable:** nothing in this repo calls
  `logging.basicConfig()` (or otherwise configures a handler) for the GUI
  process, and `gui/start.sh` backgrounds `python gui/server.py &` without
  redirecting stdout/stderr to a persistent file. Python's `logging`
  module's default `lastResort` handler only surfaces WARNING+ to stderr, so
  the INFO-level access log line is silently dropped today — the token does
  not currently land in any file or terminal output.
- **Why it's still worth tracking:** this is fragile, not fixed. If a future
  change adds `logging.basicConfig()` anywhere in the process (common when
  wiring up broader observability), or if `gui/start.sh` (or any future
  daemon supervisor) redirects the GUI subprocess's stdout/stderr to a log
  file, the session token starts landing in a readable log with no code
  change to `gui/server.py` itself required to trigger it.
- **Suggested fix (not applied — out of scope for this sub-task):** either
  pass `access_log=None` to `web.run_app()`, or move the token off the query
  string (header on upgrade, or first-message-after-connect) so it's not
  part of what any access logger would capture by default.

## Found during H-4 self-race / C-1 short-prompt follow-up task, 2026-07-29 — NOT fixed, logged only

### [NEW-2] `patch_file` with `old_str: ""` silently no-ops instead of inserting or erroring
- **Status: Resolved (2026-07-29/30, Round 7, commit `55e408c`).**
  `core/agent.py`'s fallthrough branch (~line 1831+) now logs and
  transcribes an explicit `[EDIT NOT APPLIED] <tool> on <path> failed
  after retries and escalation were exhausted — no file was modified.`
  marker when a `write_file`/`patch_file`/`append_file` call is still
  in an error state after both retry and peer-CLI escalation are
  exhausted, replacing the previous silent fallthrough to a generic
  "Next action or final answer" turn. code-reviewer independently
  traced `last_tool_result` freshness, ran the targeted test (`1 passed
  in 0.19s`) and the full suite (`321 passed, 1 pre-existing unrelated
  failure`), approved with no Critical/Warning findings. **Code
  complete, code-reviewer approved — not live-verified against the
  real model post-fix** (the pre-fix reproduction below was live; the
  post-fix confirmation is static/control-flow analysis + mocked
  tests, judged sufficient for this logging/control-flow change per
  Ground Rule 4/7). See `PROJECT_LOG.md` 2026-07-30 Round 7 entry for
  full detail. `NEW_ISSUES.md` [NEW-7] (the underlying planner
  behavior of synthesizing whole duplicate functions instead of
  targeted patches) remains open, unscoped, tracked separately.
- **Confidence: Confirmed** (directly observed, not inferred).
- **Where found:** Live verification of the C-1 short-QA-prompt fix. In a
  single warm `python3 main.py --no-resume` session, after two QA turns
  ("hello", "what can you do?"), a real coding request was sent: "add a
  docstring to the `shutdown` function in `main.py`". This correctly took
  the full/non-lightweight path (`main.py` loaded into context,
  `[Recursive] Draft (1/2)` → `[Recursive] Review (2/2)` → "Accepted —
  quality 8/10") and the model emitted a `patch_file` tool call:
  `{"name": "patch_file", "args": {"path": "main.py", "old_str": "", "new_str": "def shutdown():\n    \"\"\"...docstring...\"\"\"\n    print('Shutting down...')\n    # Add your shutdown logic here."}}`.
- **Evidence it no-op'd:** Immediately after acceptance, the harness
  logged `⚠ Malformed tool call — JSON parse failed, retrying`, which
  triggered a second, near-identical `patch_file` call with the same
  `old_str: ""`. No error or success message about the patch's actual
  effect was ever printed before the next `You>` prompt appeared.
  `git diff main.py` afterward showed **zero changes** — `shutdown()` at
  line 125 has no docstring, unmodified from HEAD. The model's tool call
  ran (or was retried) but never touched the file.
- **Likely root cause (not yet verified against `tools/patch_tools.py`):**
  the model appears to be using `old_str: ""` to mean "insert without
  matching," but `patch_file`'s matching logic likely treats an empty
  `old_str` as either "match nothing" (silent no-op) or a bad match
  that gets swallowed rather than surfaced as `[PATCH_FAILED]` to the
  user. Note `tests/test_patch.py`'s pre-existing failure (further down
  this file) is about the *format* of the failure message
  (`[PATCH_FAILED]` vs `[ERROR] String not found`) — this is a different,
  possibly related but unconfirmed, issue about a failure not being
  surfaced at all for the empty-`old_str` case.
- **Impact:** A user asking for a simple, common edit ("add a docstring
  to X") can get a "quality 8/10, accepted" response with an emitted tool
  call that looks successful in the transcript, while the file is
  actually untouched — a silent-failure UX gap, not a crash.
- **Not fixed here:** out of scope for the H-4/C-1 task that surfaced it
  (this task touched `core/daemon.py`, `prompts/system_prompt.py`, and
  `prompts/layered_prompt.py` only). Needs a dedicated look at
  `tools/patch_tools.py`'s handling of empty/non-matching `old_str`
  before deciding whether the fix is in the tool implementation or in
  prompting the model to never emit an empty `old_str`.
- **Correction (2026-07-29, Round 3 scoping pass) — the hypothesized
  root cause above does not hold up; downgrading per CLAUDE.md rule 6.**
  Read `tools/patch_tools.py:19-22` directly: an empty/non-string
  `old_str` is already explicitly rejected —
  `if not old_str or not isinstance(old_str, str): return "[ERROR]
  Invalid old_str: empty or not a string"` — and `git log --follow -p`
  shows this check has existed since commit `8ab96e1` (Jun 13 2026), well
  before this session. So `tool_patch_file` itself does **not**
  silently no-op on `old_str: ""` — it returns a clear, explicit error
  string. The originally-suspected fix location (`patch_tools.py`'s
  matching logic) is not where the bug is.
  - **Re-reading the original transcript evidence with this in mind:**
    the "malformed tool call — JSON parse failed" warning fired
    *before* any tool executed, meaning `tool_patch_file` was likely
    never actually called on the first attempt (the JSON never parsed,
    probably due to unescaped literal newlines inside the multi-line
    docstring in `new_str`, which breaks strict JSON parsing). The
    retry then produced a second near-identical malformed call.
  - **New, more likely mechanism (unconfirmed, needs live reproduction
    to nail down):** `core/agent.py:1434` sets `max_retries = 1`, so
    the malformed-tool-call retry path (`core/agent.py:1537-1553`) only
    gets one retry attempt. If the second attempt *also* fails to parse,
    `auto_retries >= max_retries` and the code falls through past the
    `if tool_dict:` block entirely (nothing between lines ~1553 and
    ~1843 re-enters it for a null `tool_dict` after retries are
    exhausted) to `history.append(...); return response, history`
    around `core/agent.py:1869-1873` — i.e. the raw, still-malformed
    model text becomes the "final answer" with no explicit surfacing of
    "the patch never applied." This would explain a silent-looking
    failure without any code in `patch_tools.py` being at fault.
  - **Status:** downgraded from Confirmed-root-cause to Suspected — the
    silent-no-op *symptom* is still Confirmed (git diff showed zero
    change), but the mechanism is now believed to be in
    `core/agent.py`'s malformed-JSON-retry exhaustion path, not
    `tools/patch_tools.py`. Needs a fresh live reproduction (single warm
    session, ask for a multi-line docstring/edit likely to trigger an
    unescaped-newline JSON break) with the raw model output captured
    verbatim before scoping an implementer task — not ready to hand off
    yet.

- **Correction (2026-07-30, live-verifier reproduction with real 7B
  model) — the Round 3 malformed-JSON hypothesis above does not hold up
  either; correcting per CLAUDE.md rule 6, root cause now Confirmed by
  direct live reproduction.**
  - **What Round 3 believed:** that `parse_tool_call()` failed to parse
    the model's `<tool>` JSON (a JSON-parse failure), and that this made
    the user see raw broken text that "looks like" a false claim of
    success.
  - **What was actually observed live (single warm session, prompt "add
    a docstring to the shutdown function in main.py", `[Recursive]`
    planner path):** the model's JSON was **well-formed both times** —
    `parse_tool_call()` succeeds and `tool_dict` is truthy on both
    attempts. There is no JSON-parse failure anywhere in this trace. The
    call was `{"name": "patch_file", "args": {"path": "main.py",
    "old_str": "", "new_str": "<a whole duplicate shutdown() function>"}}`.
  - **Confirmed actual mechanism, traced end-to-end:**
    1. `execute_tool(tool_dict)` calls `tool_patch_file(path, old_str="",
       new_str=...)`. `tools/patch_tools.py:21-22`'s empty-`old_str`
       guard (present since commit `8ab96e1`, as Round 3 found) fires
       and returns the string `"[ERROR] Invalid old_str: empty or not a
       string"`. This is a normal, working rejection — not a no-op and
       not swallowed.
    2. `core/agent.py:480-488` (`is_error()`) sees the `[ERROR]` prefix
       and returns `True`.
    3. First attempt: `core/agent.py:1700-1702` — `auto_retries(0) <
       max_retries(1)` (set at `core/agent.py:1434-1435`) — increments
       `auto_retries` to 1 and prints exactly the observed `⚠ Error
       detected — auto-retry 1/1`, then appends the raw `[ERROR]` text
       to the conversation and `continue`s. This matches what
       live-verifier saw.
    4. The model retries and emits the **identical** `old_str: ""` call
       again (this is the actual planner/prompting gap — see the new
       NEW-7-adjacent note below). `tool_patch_file` rejects it
       identically.
    5. Second attempt: `auto_retries(1) >= max_retries(1)`, so
       `core/agent.py:1760-1787`'s `elif` branch fires instead of the
       retry branch: it calls `core/peer_cli.py:303 escalate()`. On this
       device (no peer CLI configured / user did not opt in), `escalate()`
       returns `None` (`core/peer_cli.py:318-320` prints its own "No peer
       CLIs found" warning, or `mgr.confirm()` returns `False` and
       `core/peer_cli.py:333-335` prints "Peer CLI escalation skipped." —
       either way this is a *different* warning than the retry one, which
       is why no second "Error detected — auto-retry" line appeared).
    6. Falling through the `elif` (comment at `core/agent.py:1787`: "else:
       user skipped escalation, fall through to normal handling") reaches
       `core/agent.py:1788` unconditionally, then the `name ==
       "write_file"` check at `1792` is `False` for `patch_file`, so
       control lands in the `else` branch at `core/agent.py:1830-1841`:
       it appends `"Tool result: [ERROR] Invalid old_str...\nNext action
       or final answer:"` to `messages` and `continue`s the main loop —
       i.e. the model is invoked a **third** time.
    7. This third call is where the model, now holding the `[ERROR]`
       text as context, gives up on re-emitting a tool call and instead
       replies with plain text: *"Please provide the correct content for
       the `old_str` argument in the patch_file call."* This is an
       honest, if easy-to-miss, clarification request — **not** a false
       claim of success, contrary to Round 1's original framing.
    8. Because this third response contains no `<tool>` block,
       `tool_dict` is falsy, `is_hallucination()` doesn't trigger (the
       response isn't claiming a file/run happened), so execution falls
       through to `core/agent.py:1869-1873` and returns this text as an
       ordinary final answer — with no distinct ERROR-level surfacing
       anywhere in this whole path that an edit was attempted twice and
       both times rejected. This is the actual "silent" part of
       "silent no-op": not silent in the sense of "no error was ever
       produced" (two clear `[ERROR]` strings were produced, correctly,
       by `patch_tools.py`), but silent in the sense that **neither
       `[ERROR]` was ever escalated past ordinary conversational turns
       into something the user is guaranteed to notice** before the
       session moves on.
  - **Confirmed via:** `git diff main.py` after the session was
    completely empty; `main.py:125 def shutdown()` unmodified from HEAD.
  - **Status: Confirmed root cause** (upgraded from Suspected). The
    off-by-one retry-budget gating logic from Round 3's hypothesis
    (`max_retries = 1` meaning only one retry is allowed) was correct in
    spirit; what was wrong was believing the trigger was a JSON-parse
    failure and that the user gets a "looks like success" message. The
    actual trigger is a **failed tool-application** (empty `old_str`
    rejected by `patch_tools.py`'s existing, correct guard), and the
    actual user-visible result is an honest clarification question with
    no explicit "your edit did not apply" error surfaced.
  - **Scoped fix (handed to implementer):** when the tool-call/retry loop
    exhausts retries on a `write_file`/`patch_file`/`append_file` call
    that never produced a successful result (i.e. `is_error()` was still
    `True` on the last attempt and peer-CLI escalation did not resolve
    it), `core/agent.py`'s fallthrough at the `else` branch around
    `core/agent.py:1830-1841` should surface a clear, distinct, ERROR-
    level message/log stating that an edit was attempted and did **not**
    apply, rather than silently reusing the generic "Tool result: ...
    Next action or final answer:" framing that lets the loop end on an
    ordinary-looking clarification question. Scope is intentionally
    limited to this surfacing gap — it does **not** include fixing why
    the `[Recursive]` planner keeps synthesizing `old_str: ""` with a
    whole duplicate function instead of a targeted edit; that is tracked
    separately as NEW-7 below.

### [NEW-7] `[Recursive]` planner path may be prompted to synthesize whole functions rather than targeted patches (Confirmed, reproducible, NOT recursion-specific — prompt fix landed `0026565`, Round 21 live-verified with mixed result: 67%→50% on the narrow old_str-grounding metric but 67%→67% (unchanged) on the baseline's own task-completion metric, n=6 small sample, plus a new uncharacterized wrong-function-targeting failure mode the fix does not address — still open)
- **Confidence: Suspected.** Observed once, in the same live session that
  reproduced NEW-2 above; not yet isolated from NEW-2's retry-surfacing
  gap or confirmed across multiple prompts.
- **Where found:** Same transcript as NEW-2. The `[Recursive] Draft` /
  `[Recursive] Review (2/2)` / "Accepted — quality 8/10" path
  (`core/agent.py:1462-1520`, backed by `core/recursive.py:326
  recursive_infer()`) both times produced `old_str: ""` with `new_str`
  containing a **complete duplicate `shutdown()` function** (docstring +
  body), rather than a minimal patch to the real function at
  `main.py:125`. `core/recursive.py`'s draft/critique/refine loop
  (read `core/recursive.py:390-403`) re-invokes the same generic
  `infer()` on the same message history with critique feedback — there
  is no `patch_file`-specific prompt telling the model that `old_str`
  must match existing file content verbatim; the model appears to be
  treating "add a docstring" as "write a new function" instead of "find
  and edit the existing one."
- **Not investigated:** whether this is specific to the `[Recursive]`
  path or would also happen on the plain (non-recursive) path; whether
  it's specific to docstring-insertion requests; whether it happens
  consistently or was one draw from the model. Needs a dedicated
  scoping pass with multiple live reproductions before an implementer
  task is written — deliberately not bundled into NEW-2's fix.

- **Round 14 (2026-07-30) — desk scoping pass, no live session run.**
  Mechanism re-verified against current code (line numbers below refreshed
  from Round 1's citation, which had drifted). No fix or reproduction was
  attempted this round — this only refines the reproduction plan handed to
  the next live-verification round.
  - `core/agent.py:1467` — `_use_recursive = step == 1 and not is_qa and
    RECURSIVE_CONFIG.get("enabled", True)`. `RECURSIVE_CONFIG["enabled"]`
    (`core/recursive.py:111-118`) is controlled by the `CODEY_RECURSIVE`
    env var: `1` forces on, `0` forces off, unset defaults to on for the
    local backend (which is what this device uses). **This is a clean,
    already-existing knob to isolate recursive vs. plain path across two
    separate sessions** — no code change needed to test both paths.
  - Even when `_use_recursive` is `True`, `core/agent.py:1477-1485` calls
    `classify_breadth_need()` (`core/recursive.py:138-165`) first; a
    "minimal" classification (short Q&A-shaped messages) still takes the
    plain `infer()` call, not `recursive_infer()`. "Add a docstring to the
    shutdown function in main.py" (10 words, contains the action keyword
    "add") classifies as "standard" → `max_depth=1` → one real
    draft/critique/refine cycle through `recursive_infer()`
    (`core/agent.py:1487-1496`), matching the originally observed
    `[Recursive] Draft (1/2)` → `[Recursive] Review (2/2)` transcript.
  - **New structural finding, relevant to root-causing (not yet a fix):**
    the draft-phase system prompt (`build_recursive_prompt(phase="draft")`,
    aliased as `core/agent.py:614 build_system_prompt()`) is IDENTICAL
    between the plain and recursive paths — both are seeded with the same
    system prompt before the step loop (`core/agent.py:1402`). This means
    if the `old_str: ""` behavior originates in the draft call itself, it
    is not a recursion-specific prompting gap and should reproduce on the
    plain path too. The recursive path's only structural difference is the
    critique+refine loop that runs *after* the draft.
  - **Second structural finding:** the critique phase's system prompt
    (`_build_critique_prompt()`, `prompts/layered_prompt.py:352-382`)
    deliberately drops repo/file context — the critique model only sees
    the critique instructions (`CRITIQUE_CODE`,
    `prompts/critique_prompts.py:23-38`), the original user request, and
    the prior draft text, never the real file content. `CRITIQUE_CODE`'s
    7 checklist items (syntax, logic bugs, missing imports, task
    completeness, security, uncertain APIs, multi-action completeness)
    contain nothing that would catch "does `old_str` actually match real
    file content" — the critique model has no ground truth to check that
    against even if it wanted to. This means the observed "quality 8/10,
    Accepted" outcome is not surprising: the critique step is structurally
    incapable of catching this class of bug, independent of whether the
    draft-generation bug itself is recursion-specific. This is a candidate
    explanation for *why* recursion didn't self-correct the problem, but
    does not by itself explain why the draft was wrong in the first place
    — still needs live evidence.
  - Confirmed `tools/patch_tools.py:14-22` (`tool_patch_file`) and
    `prompts/system_prompt.py:90,163,174,192` (the `patch_file` tool
    documentation shown to the model) contain no instruction that
    `old_str` must be a verbatim substring of the real file, nor any
    warning against using an empty `old_str` to mean "insert new content."
    This is a real gap in the prompt but not yet confirmed as *the* cause
    of the observed behavior — could equally be a base-model tendency
    unrelated to prompt wording.
  - Also confirmed `main.py:396-406` (`/clear` REPL command) resets
    conversation history/context/undo/session **without** reloading the
    model — usable to run multiple independent draws in one model-load
    cycle for a same-prompt consistency check, per CLAUDE.md rule 2's
    batching guidance.
  - **Reproduction task designed and handed to the next live-verification
    round** (not run this round): two short, sequential, single-model-load
    `python3 main.py --no-resume` REPL sessions (never both processes
    live at once — confirm teardown between them per CLAUDE.md rule 2),
    testing the same 3 edit-style prompts in each:
    1. Session A — recursive path (default env, no override):
       `python3 main.py --no-resume`
    2. Session B — plain path forced: `CODEY_RECURSIVE=0 python3 main.py
       --no-resume`
    - In each session, send in order, with `/clear` between each prompt
      (resets context without a reload) to avoid cross-contaminating the
      model's context with its own prior attempt:
      a. "Add a docstring to the shutdown function in main.py." (exact
         repeat of the original Round 1 prompt — direct reproducibility
         check)
      b. `/clear`, then the same prompt again — consistency/sampling-
         variance check on an identical prompt within the same path.
      c. `/clear`, then "Add error handling to the load_primary function
         in core/loader_v2.py." — different verb ("add error handling"
         vs. "add a docstring"), different target function
         (`core/loader_v2.py:337 def load_primary(self)`), to check
         whether the bug is docstring-specific or broader.
      d. `/clear`, then "Rename the variable `p` to `file_path` in
         tool_patch_file in tools/patch_tools.py." (`tools/patch_tools.py:
         14,28 p = Path(path).expanduser()`) — a rename-style edit, the
         third distinct prompt style, on a third distinct target file.
    - After each prompt, capture verbatim: the full `<tool>` call emitted
      (or lack thereof), whether `old_str` is empty vs. a real substring
      of the target file, and `git diff <target file>` immediately after
      the turn to confirm whether the edit actually landed. Reset
      (`git checkout -- <file>`) between prompts if a patch does land, so
      each prompt starts from a clean baseline.
    - Confirm process teardown between Session A and Session B (`ps -eo
      pid,ppid,comm | grep -E "python|llama"` showing nothing but the
      grep itself, per the project's established non-`pgrep -af` pattern)
      and run `free -h` before Session A, between sessions, and after
      Session B per CLAUDE.md rule 2.
    - This 2-session x 4-prompt design (8 draws total) directly answers
      all three open questions: (a) reproducibility/consistency, via the
      repeated identical prompt in each session; (b) recursive-specific
      vs. plain-path, via the `CODEY_RECURSIVE` env toggle across the two
      sessions; (c) docstring-specific vs. broader, via the 3 distinct
      prompt styles/targets. No code changes required to run this — it is
      a live-reproduction task only, not a fix.

- **Round 14 (2026-07-30) — live-reproduction pass, 6 of 8 planned draws
  completed; stopped early at swap-thrashing, per CLAUDE.md rule 2's
  instability instruction (a safe, correct stop, not a failure).** Two
  sessions run: Session A (recursive, default env) and Session B
  (`CODEY_RECURSIVE=0`, plain path — confirmed via absence of
  `[Recursive]` labels in the transcript, not just assumed from the env
  var).

  | # | Session | Prompt | `old_str` observed | Bug reproduced? |
  |---|---|---|---|---|
  | a1 | A (recursive) | docstring (1st) | `"def shutdown():\n    pass"` — non-empty but hallucinated/wrong stub | No (empty-string bug) — but a distinct hallucinated-`old_str` failure |
  | a2 | A (recursive) | docstring (repeat) | `""` | **Yes** — exact reproduction of the original NEW-7 bug |
  | a3 | A (recursive) | loader_v2 error handling | N/A — draft only issued a `read_file` call, no patch attempted; quality 3/10, hit low-confidence gate | No (different failure mode — no patch attempt) |
  | a4 | A (recursive) | patch_tools rename | `"p = Path(path).expanduser()"` — real, correct substring | No — correctly targeted patch, no bug |
  | b1 | B (plain, confirmed via absent `[Recursive]` labels) | docstring (1st) | Attempt 1: `""`; retry attempt 2 (same turn): `"\ndef shutdown():\n    pass"` (hallucinated) | **Yes** on attempt 1 |
  | b2 | B (plain) | docstring (repeat) | `"def shutdown():\n    pass\n"` — non-empty, hallucinated stub | No (empty-string bug) — same hallucinated-stub variant as a1 |
  | b3 | B (plain) | loader_v2 error handling | NOT RUN — stopped for swap thrashing | N/A |
  | b4 | B (plain) | patch_tools rename | NOT RUN — stopped for swap thrashing | N/A |

  **Conclusions this data supports — correcting the record per CLAUDE.md
  rule 6 (this entry was previously "Suspected... observed once"):**
  - The literal `old_str: ""` bug is real and reproducible: 2/6 completed
    draws (a2, b1), one on EACH path (recursive and plain) —
    **this settles the open question: the bug is NOT recursion-specific.**
    The plain path's draft-phase system prompt is identical to the
    recursive path's (per this round's earlier structural finding), so
    this result is consistent with that prediction.
  - A closely related variant (non-empty but hallucinated/wrong
    `old_str`, assuming `shutdown()` is a one-line `pass` stub instead of
    its real ~15-line body) occurred in 2 more draws (a1, b2) — same
    underlying failure class (model doesn't ground `old_str` in real
    file content), different surface symptom.
  - Combined: **4 of 6 completed draws (67%) failed to produce a valid
    patch on the "add a docstring to `shutdown()`" prompt**, split evenly
    between the two `old_str`-grounding failure variants.
  - Neither the loader_v2/error-handling style (a3) nor the
    patch_tools/rename style (a4) reproduced any variant of the bug in
    the draws that did run — a4 in particular got a real, correct
    `old_str` substring match. This suggests the failure may correlate
    with the specific "add a docstring" prompt style/target more than
    with edit-requests broadly, though this is **not fully confirmed**
    since only one of the two other styles ran per session before the
    stop.
  - **Not yet answered, needs a follow-up round:** b3 and b4 (the
    loader_v2/patch_tools prompts on the PLAIN path) were never run, so
    there is no clean same-path comparison for those two prompt styles.
    A future round should complete these two draws (fresh model-load
    cycle, fresh baseline) before this can be called fully characterized.
  - This investigation also surfaced 4 additional, distinct structural
    findings beyond NEW-7 itself, logged separately per CLAUDE.md rule 8:
    [NEW-15] (a `write_file`-escalation path that can attempt to
    reconstruct an entire file in the wrong location after `patch_file`
    fails — the most severe finding of this round), [NEW-16] (the patch
    UI panel renders as if successful even when the underlying patch
    call failed), [NEW-17] (the post-edit commit offer can scope-bleed
    into unrelated pre-existing dirty files), and [NEW-18] (a single
    lightweight REPL session hit severe swap-thrashing after only 2
    model calls with retries, independent of NEW-14's full 3-model-stack
    finding).

  **RAM discipline note (all real, verbatim, all clean teardowns by
  tracked PID, never by pattern):**
  - Pre-Session-A: 4.9Gi free / 7.0Gi available, swap 1.6Gi
  - Mid-Session-A: 163Mi free / 2.0Gi available, swap 3.6Gi (high, not
    thrashing)
  - Post-Session-A teardown: 4.8Gi free / 6.8Gi available, swap 1.6Gi
  - Mid-Session-B after b1: 653Mi free / 2.0Gi available, swap 2.2Gi
  - **After b2: swap jumped to 8.9Gi used, `llama-server` RSS collapsed
    to ~2MB (nearly fully swapped out), CPU 113% — genuine
    swap-thrashing.** Live-verifier stopped immediately per CLAUDE.md
    rule 2's explicit instability instruction.
  - Post-forced-teardown: 4.8Gi free / 7.0Gi available, swap back to
    1.9Gi — full recovery confirmed, no orphaned processes.

  **Status after this round: Confirmed (upgraded from Suspected),
  reproducible (4/6 completed draws on the docstring-insertion prompt,
  67%), confirmed NOT recursion-specific. Not yet confirmed whether it
  generalizes to other edit-request styles (b3/b4 outstanding). Still
  open, still unfixed — no implementer task scoped this round
  (investigation/logging only, per this round's explicit scope).**

- **Round 20 (2026-07-30) — live-reproduction pass, b3/b4 completed
  (the 2 draws left outstanding by Round 14).** One session run:
  `CODEY_RECURSIVE=0 python3 main.py --no-resume`, confirmed plain path
  both via env var and via `RECURSIVE_CONFIG` printed directly
  (`{'enabled': False, ...}`) and via absence of `[Recursive]` labels in
  the transcript. Both prompts sent in one model-load cycle with `/clear`
  between them, per the Round 14 plan. Reproduced verbatim from the
  transcript (timestamps/spinner noise stripped):

  - **b3 (loader_v2 error-handling prompt, plain path):** prompt sent —
    "Add error handling to the load_primary function in
    core/loader_v2.py." Model issued two `read_file` calls on
    `core/loader_v2.py` (16645 chars), then replied "Done." with **no
    `patch_file` call ever attempted**. `git diff core/loader_v2.py`
    immediately after: empty, no edit landed. **Same observable outcome
    as Round 14's `a3` (no patch call, no edit landed) — but a DIFFERENT
    mechanism, confirmed by re-reading the raw log, not inferred.** The
    log shows only ONE `✓ Read core/loader_v2.py (16645 chars)` line
    (`grep -c` = 1), even though the model issued the `read_file` call
    twice with byte-identical args — the second call's context only grew
    by 104 tokens (vs. 547 for the first), too small for a re-sent
    16645-char file. This is `core/agent.py:1645-1667`'s pre-existing
    verbatim-duplicate-tool-call guard (the exact mechanism `NEW-36`
    documents, previously only confirmed on `patch_file` calls) — it
    intercepted the second, identical `read_file` call, injected
    `"Already ran that... Task complete. Reply with 1 sentence only."`
    into the conversation instead of re-executing it, which is what
    directly produced the "Done." reply. So `b3`, like `a3`, DID have a
    mechanism intervene before any `patch_file` call was attempted —
    just a different one (the duplicate-call guard, not the
    critique/quality gate) — **this is new live corroboration that
    `NEW-36`'s guard fires on `read_file`, not just `patch_file`,
    logged as an addendum to `NEW-36` below.** Whether the model would
    have attempted a `patch_file` call absent this guard is not
    established this round.
  - **b4 (patch_tools rename prompt, plain path):** prompt sent —
    "Rename the variable `p` to `file_path` in tool_patch_file in
    tools/patch_tools.py." Model issued:
    ```
    <tool>
    {"name": "patch_file", "args": {"path": "/data/data/com.termux/files/home/Codey-OS/tools/patch_tools.py", "old_str": "p = Path(path).expanduser()", "new_str": "file_path = Path(path).expanduser()"}}
    ```
    `old_str` is a **real, correct, verbatim substring** of
    `tools/patch_tools.py` (confirmed present, and confirmed UNIQUE —
    `grep -c` = 1 — both before and after this round's session) —
    matching Round 14's `a4` result exactly (correctly targeted patch,
    no `old_str`-grounding bug). The model then issued a second,
    identical `patch_file` call after the first was not applied (see
    caveat below), again with the same correct `old_str`/`new_str`.
    - **Caveat — the live turn's edit did NOT land, and this is a
      test-harness artifact, not a reproduction of the NEW-7 bug:**
      `tool_patch_file` requires an interactive `ask_confirm("Apply
      patch?")` (`tools/patch_tools.py:75`, `utils/logger.py:116-134`)
      before applying. This round's non-interactive input file (`b3
      prompt` / `/clear` / `b4 prompt` / `/exit`, piped via stdin) did
      not include an explicit `y` answer for this prompt — the plan's
      exact wording did not anticipate an apply-confirmation step.
      `/exit` was consumed as an invalid answer (re-prompted), then the
      confirm hit EOF and defaulted to `False` (`utils/logger.py:
      129-131`), rejecting the patch both times. `git diff
      tools/patch_tools.py` after the live turn: empty.
    - **Applicability confirmed separately, by a static post-hoc replay
      (no model/RAM load — a direct Python call to `tool_patch_file()`
      with `ask_confirm` monkey-patched to return `True`, then
      immediately reverted with `git checkout --`):** the exact same
      `old_str`/`new_str` the model emitted DOES apply cleanly (`Patched
      tools/patch_tools.py (27 chars → 35 chars)`, confirmed via `git
      diff` then reverted). So the `old_str`-grounding property this
      draw was designed to test is fully confirmed correct — but see
      `NEW-43` below for two things this replay also surfaced: (1) the
      live turn's cancelled-patch panel rendered as if successful (a gap
      in `NEW-16`'s coverage), and (2) the replay shows this specific
      rename, even if accepted, would leave the code referencing an
      undefined variable in 4 other places — an edit-completeness
      question distinct from `old_str` grounding, logged separately, not
      part of NEW-7's own scope.

  **RAM discipline note (all real, verbatim; first launch attempt was
  interrupted by an external event before any model output — see below):**
  - First launch attempt (`nohup ... &`, no active monitoring) was cut
    off mid-startup by an unrelated session interruption. Confirmed on
    resumption: no orphaned `python`/`llama-server` processes (`ps -eo
    pid,ppid,comm | grep -E "python|llama"` → empty), `git diff` on both
    target files empty, no data produced by that attempt — discarded,
    not counted as a draw.
  - Pre-relaunch baseline: 198Mi free / 5.4Gi available, swap 2.1Gi used
    / 9.9Gi free (recovered better than the pre-session baseline before
    the interrupted attempt, which was 1.2Gi free / 3.9Gi available,
    swap 4.2Gi used / 7.8Gi free).
  - Mid-session (during b3, `llama-server` RSS 4.4GB, CPU 300–370%):
    137Mi–276Mi free / ~2.1Gi available, swap 3.5–3.7Gi used — stable,
    no RSS collapse, not thrashing.
  - Mid-session (during b4, after the rejected apply-patch retries):
    139Mi free / 2.1Gi available, swap rose to 5.6Gi used — elevated but
    `llama-server` CPU still 372% (actively computing, not swapped out),
    no thrashing signature (no RSS collapse toward ~0).
  - Session exited cleanly on its own (`/exit` was consumed by the
    apply-patch confirm as described above, so the REPL's next `input()`
    call hit EOF and the app's own `except (KeyboardInterrupt,
    EOFError)` handler triggered normal shutdown — "Session saved.
    Goodbye!" / "Stopping model server..." — no forced kill needed).
  - Post-teardown: 1.2Gi free / 4.4Gi available, swap down to
    3.1–3.2Gi used. `ps -eo pid,ppid,comm | grep -E "python|llama"` →
    empty. Full clean recovery, no orphaned processes, no
    swap-thrashing observed this round (unlike Round 14's b2, which hit
    genuine thrashing at 8.9Gi swap / ~2MB RSS).

  **Conclusions — this completes the same-path comparison Round 14 left
  open:**
  - `a3`/`b3` (loader_v2 error-handling): same observable outcome (no
    patch attempt) on BOTH the recursive and plain paths, but via
    DIFFERENT confirmed mechanisms — `a3` was gated by the critique loop
    (quality 3/10), `b3` was intercepted by the pre-existing
    verbatim-duplicate-tool-call guard on a repeated `read_file` call
    (see bullet above, also logged as `NEW-36` corroboration). Both
    mechanisms independently prevented any `patch_file` attempt on this
    prompt style, on both paths — reproducible, but not (yet) evidence
    of a single shared root cause.
  - `a4`/`b4` (patch_tools rename): identical success (real, correct,
    unique `old_str` substring match, confirmed applicable via the
    post-hoc replay above) on BOTH paths — the rename-style prompt still
    does not reproduce any NEW-7 `old_str`-grounding failure variant on
    either path.
  - Combined with Round 14's data, the full 8-draw matrix is now
    complete: the "add a docstring to `shutdown()`" prompt style remains
    the only one that reproduces the `old_str`-grounding bug (4/6 of
    those draws, 67%); neither the loader_v2/error-handling style nor
    the patch_tools/rename style reproduced any variant of the bug in
    any of their 4 completed draws (a3, a4, b3, b4), across both
    recursive and plain paths. This strengthens Round 14's tentative
    conclusion — no longer "not fully confirmed" — that the failure
    correlates with the specific "add a docstring" prompt/target
    combination rather than with edit-requests broadly.

  **Status after this round: NEW-7 is now fully characterized ON THE
  `old_str`-GROUNDING QUESTION specifically** — which is the entry's own
  stated completion bar ("A future round should complete these two
  draws... before this can be called fully characterized" — Round 14).
  All 8 planned draws across the 2-session x 4-prompt design are
  complete, and for every draw the `old_str`-grounding property (empty /
  hallucinated vs. real-and-unique substring) is directly evidenced —
  including `b4`, via the post-hoc replay confirming applicability where
  the live turn's own confirm-prompt answer was lost to a harness gap.
  Findings stand as: Confirmed, reproducible (4/6 draws, 67%)
  specifically on the docstring-insertion prompt style, NOT
  recursion-specific. Neither of the two other prompt styles tested
  (loader_v2 error-handling, patch_tools rename) reproduced any
  `old_str`-grounding failure variant in any of their 4 completed draws
  (a3, a4, b3, b4) — **but 2 of those 4 (a3, b3, both the loader_v2
  prompt, one per path) produced no `patch_file` call at all**, a
  distinct failure to complete the requested edit that is a real
  characterization finding in its own right, not a null result; the
  other 2 (a4, b4, both the patch_tools prompt) produced correct,
  applicable patches. Still open, still unfixed — this round was
  characterization only, no fix attempted, per this task's explicit
  scope. Ready for an implementer task to be scoped (root-causing why
  the docstring-insertion prompt specifically triggers the
  `old_str`-grounding failure, and separately, why the loader_v2 prompt
  style produces no patch attempt at all on either path, per Round 14's
  structural findings on `system_prompt.py`/`patch_tools.py`'s missing
  verbatim-substring instruction). See also `NEW-43` for two related,
  out-of-scope findings surfaced this round (a `NEW-16` coverage gap on
  cancelled patches, and a Suspected edit-completeness issue on the
  rename prompt).

- **Round 21 (2026-07-30) — live-verification pass of the `old_str`
  prompt fix committed at `0026565` (`prompts/system_prompt.py`,
  `prompts/critique_prompts.py`), code-reviewer-approved on static
  grounds only. This round re-ran the exact same "Add a docstring to the
  shutdown function in main.py." prompt against the NEW prompt to
  compare against the pre-fix 67% (4/6) baseline.**
  - **Record correction (CLAUDE.md rule 6):** `main.py` has grown
    substantially since Round 14/20 (this session's NEW-10/NEW-25 work
    touched it) — now 68174 chars vs. the smaller file the original
    baseline was drawn against. `shutdown()` itself is now ~33 lines
    (`main.py:126-158`, includes a daemon-aware early return and a
    fallback PID-scoped kill path), not the ~15-line body Round 14/20
    described. `def shutdown():` remains a real, unique substring
    (`grep -c` = 1), so the fix's own worked example (which uses this
    exact string) is still valid against current file content.
  - **Confirmed the fix text was actually exercised on the tested path
    (closes a gap the original round plan didn't cover):** direct static
    checks, no model load — `python3 -c "from prompts.system_prompt
    import get_system_prompt; print('old_str MUST BE REAL FILE CONTENT'
    in get_system_prompt())"` → `True`; and, more importantly, calling
    the actual function the recursive draft phase uses,
    `prompts.layered_prompt._build_draft_prompt('Add a docstring to the
    shutdown function in main.py.')`, and confirming the same string is
    present in its returned 12494-char output → `True`. So the new
    PATCH_FILE instructions were genuinely present in the system prompt
    sent to the model on every one of this round's 6 draws, not just in
    the underlying constant — the "50%" result below reflects the fix
    being exercised, not a false read of a prompt path that never
    reached the model. The critique-phase half of the same commit
    (`prompts/critique_prompts.py`'s new checklist item #8, "is old_str
    empty?") was independently confirmed present too — calling
    `prompts.layered_prompt._build_critique_prompt()` directly with a
    sample empty-`old_str` `patch_file` draft shows the item rendered
    verbatim in the critique prompt. So both halves of `0026565` were
    live-exercised on every draw, not just the draft-phase half — which
    sharpens draw 3's significance: the critique model saw the new
    "rate below 5/10 if old_str is empty" instruction and still rated
    that turn "Accepted — quality 8/10," i.e. the critique-side guard
    the fix added did not catch the exact failure it was designed to
    catch, in this instance.
  - **Per-draw write/no-write independently confirmed via the session's
    own `/undo main.py` output** (not just the final `git status`):
    `/undo` returned `[ERROR] No history for main.py. Was it edited this
    session?` after draws 1, 3, and 5 (confirming no write occurred —
    consistent with each of their `patch_file` calls being rejected by
    the tool before ever reaching disk), and returned `Restored main.py
    to version from <timestamp>` (confirming a write DID occur) after
    draws 2, 4, and 6 — exactly matching the table's grounding-failure
    column and independently corroborating that draw 4 (wrong function)
    really did land a file change, distinct from draws 1/3/5 which
    never touched disk at all.
  - **Methodology note — two harness gaps found and corrected before
    valid data could be collected, both logged here for future rounds:**
    1. A first attempt (6 draws, `/clear` between each, single `y`
       answer per draw for the anticipated `Apply patch?` confirm)
       produced only 3 completed draws before hitting stdin EOF. Cause:
       every successful patch triggers a SECOND, previously
       undocumented confirm — `core/agent.py:694`'s
       "Stage and commit ONLY the file(s) touched this turn?" — which
       consumed subsequent scripted lines out of order, cascading
       misalignment. It also caused 3 unintended real commits
       (`608d2d5`, `6026e84`, `840a436`) of accumulating duplicate
       docstrings in `shutdown()`, since draws also weren't reset
       between each other. These 3 commits were verified to touch only
       `main.py` (`git diff 0026565..HEAD --stat`) and were cleanly
       reverted via `git reset --hard 0026565` before re-running.
    2. Corrected second attempt used `--yolo` (disables the `Apply
       patch?` confirm entirely, a documented CLI flag, not a
       process-lifecycle change) plus `/undo main.py` after each draw
       (verified no-confirm-required, per `core/filehistory.py:49
       undo()`) to reset file state between draws within the single
       model-load session, and answered `n` to the remaining
       "Stage and commit" confirm to avoid creating unwanted commits.
       This ran cleanly to completion; `git status --short main.py` was
       empty after the session, confirming `/undo` fully reset the file
       each time.
  - **6 of 6 planned draws completed, single model-load session
    (`python3 main.py --no-resume --yolo`, default env = recursive
    path), verbatim `old_str` observed per draw (via clean-log
    extraction) and independently confirmed against real `main.py`
    content with a direct Python substring-count check:**

    | # | `old_str` emitted | Real substring of `main.py`? | Grounding failure? | Notes |
    |---|---|---|---|---|
    | 1 | `"def run_agent():"` | **No — 0 occurrences anywhere in main.py** (`run_agent` is only imported/called there, never defined in that file) | **Yes** — hallucinated, non-existent string | Also targeted the wrong function entirely (not `shutdown`) |
    | 2 | `"def shutdown():"` | Yes — real, unique (count=1) | No | Correct patch, correct target, applied cleanly |
    | 3 | `""` (empty) | N/A | **Yes** — classic empty-`old_str` bug, exact reproduction | `new_str` attempted to reconstruct nearly the whole file from memory via `patch_file` (NEW-15-adjacent escalation pattern, but through `patch_file` not `write_file`) |
    | 4 | `"def parse_args():"` | Yes — real, unique (count=1) | No (grounding is correct) | But wrong target function (not `shutdown`) — a distinct failure mode, see below |
    | 5 | `"def shutdown():\n    pass"` (attempt 1); retry in same turn: `"def shutdown():\n    \"\"\"Gracefully stop the model server and save session state.\"\"\"\n    pass\n"` (attempt 2) | No — 0 occurrences, both attempts | **Yes** — hallucinated one-line-stub assumption, same variant as original Round 14's a1/b2, and the retry compounds the hallucination rather than correcting it | |
    | 6 | `"def shutdown():"` | Yes — real, unique (count=1) | No | Correct patch, correct target, applied cleanly |

  - **Two different metrics give two different before/after readings —
    both are reported here, per CLAUDE.md rule 6 (do not lead with only
    the favorable one):**
    - **Narrow `old_str`-grounding-only metric** (is `old_str`
      empty/hallucinated vs. real file content, NEW-7's own stated
      definition): **3/6 (50%)** this round — draws 1, 3, 5 — vs. the
      pre-fix baseline's **4/6 (67%)** (Round 14+20 combined). On this
      narrow metric there is a modest reduction.
    - **The baseline's own actually-stated metric** — "failed to
      produce a valid patch on the docstring-insertion prompt" (Round
      14's exact wording) — i.e. did the turn produce the requested
      docstring edit to `shutdown()` at all: **4/6 (67%)** this round —
      draws 1, 3, 4, 5 (draw 4 produced a valid, correctly-grounded
      patch, but to the wrong function, so it still failed to deliver
      the requested edit) — **identical to the pre-fix 67% baseline, no
      measurable improvement on this reading.**
    - The two metrics coincided in the original baseline (every
      grounding failure was also a task failure, and vice versa) but
      diverge post-fix because of the new wrong-function-targeting mode
      (draw 4). **Bottom line: improved on the narrow grounding metric
      (67%→50%, n=6, small sample); unchanged on the task-completion
      metric the baseline itself was originally stated in (67%→67%).**
      This is a genuinely mixed result, not a clean before/after win —
      the specific grounding bug the fix targets (empty `old_str`, or
      hallucinated-stub `old_str` for `shutdown()` itself) still
      reproduced in half of this round's draws, including one case (draw
      3) that is arguably a more severe variant than anything in the
      original baseline — an empty-`old_str` `patch_file` call whose
      `new_str` attempts a near-complete file reconstruction.
  - **New failure mode surfaced this round, NOT part of the original
    67% baseline or its two grounding-failure variants: wrong-function
    targeting.** Draws 1 and 4 (2/6, 33%) picked an entirely different
    function (`run_agent`, `parse_args`) instead of `shutdown` — draw 4
    did so with a real, correctly-grounded `old_str` (so it does not
    count as a grounding failure by NEW-7's own definition), meaning
    **NOT ALL failures this round were addressed even in principle by
    this fix**, since the fix's instructions are entirely about
    `old_str` verbatim-matching, not about correctly identifying which
    function the user meant. This is logged as a new, distinct
    Suspected finding (see `NEW-7`-adjacent note below) — plausibly
    correlated with `main.py`'s substantial growth since the original
    baseline (more candidate functions to confuse with `shutdown`), but
    not confirmed against a controlled comparison this round.
  - **Sample size caveat:** 6 draws (this round) vs. 6 draws (Round
    14+20 combined baseline) is a small sample either side — a
    17-percentage-point difference (67% → 50%) on n=6 is directionally
    suggestive of improvement but not statistically strong. Do not
    overclaim a confirmed fix from this alone.
  - **`--yolo` harness-difference caveat, checked and confirmed benign
    for prompt content (not fully equivalent for retry dynamics):** the
    pre-fix 67% baseline (Round 14+20) ran WITHOUT `--yolo`; all 6 of
    this round's draws ran WITH it (adopted to fix the confirm-cascade
    harness gap — see methodology note above and `NEW-45`). Checked
    `grep -n "yolo" core/agent.py`: the `yolo` flag is threaded only
    into `shell()` calls and recursive `run_agent()` follow-up calls
    (auto-fix-and-retry paths) and `run_queue()` — it is never passed
    into `build_recursive_prompt()`/`build_system_prompt()` or any
    prompt-construction call, so it does not alter what the model is
    shown. It is NOT apples-to-apples in one respect, though: under the
    baseline's confirm-gated config, a patch reaching the `Apply patch?`
    confirm could be `[CANCELLED]` by a lost/EOF-defaulted answer (the
    exact harness gap NEW-7's own Round 20 addendum documents for `b4`),
    which could provoke a different retry pattern than `--yolo`'s
    immediate-apply. This round's draws never hit that ambiguity since
    `--yolo` applies successful patches immediately — a real, disclosed
    procedural difference from the baseline, though not one expected to
    change whether `old_str` itself is grounded correctly.
  - **Path coverage:** only the recursive (default env) path was run
    this round, per this task's instructions (the recursive-vs-plain
    question was already settled as "not recursion-specific" in Round
    14). The plain path (`CODEY_RECURSIVE=0`) was not re-tested against
    the new prompt this round — if a future round wants a stronger
    signal, running plain-path draws too would help, but is not required
    to close this task.
  - **RAM discipline note (all real, verbatim):**
    - Pre-session-A (first, discarded due to methodology gap #1 above):
      884Mi free / 4.3Gi available, swap 3.0Gi used / 9.0Gi free.
    - Post-teardown after discarded attempt: 4.8Gi free / 7.1Gi
      available, swap 1.8Gi used / 10Gi free — full clean recovery, `ps
      -eo pid,ppid,comm | grep -E "python|llama"` empty.
    - Pre-session-A2 (corrected `--yolo` run): 4.5Gi free / 7.0Gi
      available, swap 1.7Gi used / 10Gi free.
    - Mid-session-A2 (sustained across all 6 draws): free RAM oscillated
      77Mi–399Mi, available 1.8Gi–2.3Gi, swap 2.9Gi–4.0Gi used
      throughout — elevated and tight but `llama-server` RSS stayed in
      the multi-GB range the whole time (checked directly via `ps aux`,
      RSS 3.8GB at one check, CPU 343%, actively computing) — **no
      RSS-collapse-toward-zero thrashing signature observed at any check
      point**, unlike Round 14's b2. Session ran to completion without
      intervention.
    - Post-teardown after session-A2: 4.8Gi free / 6.5Gi available, swap
      2.0Gi used / 9Gi free. `ps -eo pid,ppid,comm | grep -E
      "python|llama"` → empty. Full clean recovery, no orphaned
      processes.
  - **Status after this round: mixed result, not a confirmed fix —
    inconclusive-to-negative on the metric the baseline itself was
    stated in.** The fix's PATCH_FILE instructions were confirmed
    present in the actual rendered draft prompt sent to the model on
    every draw (see above), so this is a genuine measurement of the
    fix, not a null test. On the narrow `old_str`-grounding-only metric,
    failure rate dropped from 67% to 50% (small-sample, directionally
    positive, not statistically strong). But on the baseline's own
    originally-stated metric — "failed to produce a valid patch on the
    docstring-insertion prompt" — the rate is unchanged at 67%, because
    a new failure mode (wrong-function targeting, draws 1 and 4) that
    the fix does not address even in principle replaced one instance of
    the old failure mode. The fix's specific worked example
    (`shutdown()` as a real, unique substring) remains valid against
    current `main.py`, and the fix did not eliminate the grounding bug
    it targets (draws 1, 3, 5 still failed, including a more severe
    near-full-file-reconstruction variant in draw 3). `NEW-7` should
    **stay open** — not marked fully done — pending either a stronger
    prompt-engineering iteration (e.g., explicitly instructing the model
    to `read_file` and locate the exact target function by name before
    drafting, addressing both the grounding and wrong-target failure
    modes together) or a larger-sample re-run to firm up either signal.
    `WORK_QUEUE.md` updated accordingly.

## Found during Round 21 (NEW-7) live-verification pass, 2026-07-30 — NOT fixed, logged only

### [NEW-44] `patch_file` requests can target a plausible-but-wrong function instead of the one named in the user's prompt, even when `old_str` is a real, correctly-grounded substring of the file (Suspected)

- **Confidence: Suspected.** Observed in 2 of 6 draws in a single live
  session (Round 21, NEW-7 live-verification, 2026-07-30) — not yet
  isolated across multiple sessions/prompts, and not yet confirmed
  whether it correlates with `main.py`'s size/complexity or is a
  broader base-model tendency.
- **Where found:** Both draws sent the identical prompt "Add a docstring
  to the shutdown function in main.py." (recursive path, default env,
  `python3 main.py --no-resume --yolo`). Draw 1 emitted `old_str:
  "def run_agent():"` — a string that does not exist anywhere in
  `main.py` (confirmed via direct Python `content.count()`, 0
  occurrences; `run_agent` is only imported/called in that file, never
  defined there). Draw 4 emitted `old_str: "def parse_args():"` — a
  real, unique substring of `main.py` (`main.py:30`), so `patch_file`
  would have applied it cleanly, but `parse_args` is not the function
  the user asked to edit.
- **Why this is distinct from NEW-7's own `old_str`-grounding
  definition:** NEW-7 (see above) is specifically about whether
  `old_str` is empty/hallucinated vs. real file content. Draw 4's
  `old_str` is real and correctly grounded by that definition — the
  model successfully quoted real file content verbatim, it just quoted
  the wrong function's real content. This means the `0026565` prompt
  fix (which only instructs verbatim-matching, not target-function
  identification) does nothing for this failure mode, even in
  principle.
- **Not yet investigated:** whether this correlates with `main.py`
  having grown substantially since NEW-7's original baseline (68174
  chars now, many more candidate function definitions for the model to
  confuse with `shutdown`), whether it's specific to this prompt style,
  or how often it happens on smaller/simpler files. Needs a dedicated
  scoping pass with multiple live reproductions, similar to how NEW-7
  itself was characterized, before a fix is scoped.

### [NEW-45] `core/agent.py:694`'s post-edit "Stage and commit" confirm is a second, undocumented confirmation beyond `patch_file`'s own "Apply patch?" confirm — non-interactive/scripted test sessions that only account for the first confirm will misalign and can produce unintended real commits (Confirmed)

- **Confidence: Confirmed.** Directly reproduced and root-caused during
  Round 21 (NEW-7 live-verification, 2026-07-30).
- **Where found:** A scripted 6-draw REPL session (piped stdin, one `y`
  answer per draw for the anticipated `Apply patch?` confirm) only
  completed 3 of 6 planned draws before hitting stdin EOF. Root cause:
  every turn where a `patch_file`/`write_file` call actually changed a
  tracked file triggers `check_git_and_offer_commit()`
  (`core/agent.py:671-701`), which calls `ask_confirm("\nStage and
  commit ONLY the file(s) touched this turn (shown above)?")`
  unconditionally, independent of `AGENT_CONFIG["confirm_write"]` (i.e.
  `--yolo` does NOT suppress it). A scripted session that only answers
  the first (`Apply patch?`) confirm has its next scripted line consumed
  by this second confirm instead, cascading misalignment through the
  rest of the script. In this instance it produced 3 unintended real
  commits (`608d2d5`, `6026e84`, `840a436` — all reverted via `git reset
  --hard` to the pre-session commit after confirming via `git diff
  --stat` that only `main.py` was touched) before the script's input
  lines ran out and the session exited via `EOFError`.
- **Why this matters beyond NEW-7's own scope:** this is the same class
  of harness gap NEW-7's own Round 20 addendum already documented once
  (the `Apply patch?` confirm itself causing a false negative on `b4`)
  — this is a SECOND, distinct confirm with the same footgun, now
  confirmed to exist independently of `--yolo`. Any future live-testing
  round that scripts multi-turn edit sessions via piped stdin needs to
  account for both confirms, not just one. Round 21's corrected
  methodology (`--yolo` to suppress `Apply patch?`, explicit `n` answers
  for the "Stage and commit" confirm, `/undo <file>` between draws
  instead of relying on `git checkout`) worked cleanly and is the
  reusable pattern for future rounds.
- **Not fixed here** — this is a test-harness/methodology finding, not a
  product bug per se (the double-confirm behavior itself may be
  intentional UX — asking separately about writing the patch and about
  committing it). Logged for future live-verification rounds' benefit,
  not scoped as an implementer task.

## Found during Round 14 (NEW-7) live-reproduction pass, 2026-07-30 — NOT fixed, logged only

### [NEW-15] After `patch_file` fails, the model can autonomously escalate to reconstructing an ENTIRE file from memory via `write_file` — and place the edit in the wrong location (Resolved 2026-07-30, Round 15, commit `7756581`)

- **Resolution:** `tools/file_tools.py`'s `tool_write_file()` now refuses
  to overwrite an existing `.py` file with syntactically invalid content
  (via `core/linter.py`'s `check_syntax()`, fail-open if the linter
  import fails), and `tools/patch_tools.py`'s `[PATCH_FAILED]` message
  was reworded to de-emphasize `write_file` and warn against
  partial-memory reconstruction (the tool itself remains available).
  Code-reviewer approved after directly exercising `tool_write_file()`
  with a live throwaway script confirming blocked/allowed/new-file/
  fail-open behavior against the running code, and explicitly assessed
  that an on-device model session was not warranted for this
  deterministic, tool-level guardrail. Full unit test coverage added
  (`tests/test_file_tools.py`, 4 new tests; full suite 258 passed). See
  `PROJECT_LOG.md`'s 2026-07-30 Round 15 entry for full detail.
- **Scope note:** this fix addresses only the `write_file`
  full-file-corruption risk. [NEW-16], [NEW-17], and [NEW-18] below —
  logged during the same Round 14 investigation that found this issue —
  remain open and unscoped, not addressed by this fix. NEW-7 itself
  (the underlying planner behavior that triggers the `patch_file`
  failures in the first place) also remains open — Round 14's b3/b4
  reproduction draws were never completed.

- **Confidence: Confirmed** — directly observed twice, in both plain-path
  draws (b1, b2) where `patch_file` failed.
- **Where found:** Round 14 NEW-7 live-reproduction session B (plain
  path, `CODEY_RECURSIVE=0`). In both b1 and b2, after `patch_file` was
  rejected by `tools/patch_tools.py:56-61`'s `old_str` uniqueness
  guardrail, the model autonomously escalated to a `write_file` call
  attempting to reconstruct the ENTIRE 62,975-character `main.py` from
  its own context — generation was still in progress (594-614 tokens in,
  function body barely started) when the turn ended. In b1, the
  reconstructed `shutdown()` was placed in the WRONG location (right
  after the `BANNER` string near the top of the file, not its real
  location at line 125).
- **Why this is more severe than NEW-7 itself:** had
  `AGENT_CONFIG["confirm_write"]` been `False` (e.g. a `--yolo`-style
  mode) or a user reflexively accepted the write confirmation, this
  escalation path could have TRUNCATED/DESTROYED the rest of `main.py`,
  not just introduced a duplicate function. The confirmation gate is
  what prevented actual damage in this investigation — it worked, but
  shouldn't be relied on as the only safeguard against a
  full-file-reconstruction escalation combined with a wrong-location
  edit.
- **Relevant code, not yet pinned down precisely:** `core/agent.py` (the
  `write_file` escalation path taken after a `patch_file` failure —
  live-verifier did not cite exact line numbers for this specific
  escalation branch; a future investigation needs to pin down the exact
  trigger logic). `core/peer_cli.py:223` ("Codey hit max retries"
  escalation prompt — may be related, not yet confirmed).
  `AGENT_CONFIG["confirm_write"]` (currently `True` by default in this
  environment).
- **Not fixed here** — flag as needing its own dedicated
  investigation/scoping round, likely higher priority than NEW-7 itself
  given the severity (potential for silent full-file data loss, not just
  a bad edit).

### [NEW-16] The "Patching `<file>`" diff-preview UI panel renders unconditionally, regardless of whether the underlying patch actually succeeded (Resolved 2026-07-30, Round 16, commit `99d922f`)

- **Coverage correction (Round 20, 2026-07-30, per CLAUDE.md rule 6):**
  this fix is resolved ONLY for the `[ERROR]`/`[PATCH_FAILED]` result
  classes it was built and tested against. The `[CANCELLED]` result
  class (user/EOF declines the apply-patch confirm) is NOT covered —
  `is_error()`'s deliberate `[CANCELLED]` exclusion means the original
  false-success panel still renders for that case, confirmed by live
  reproduction. See `NEW-43` for the full finding.
- **Status: Resolved.** `core/agent.py`'s `show_patch()`/
  `show_file_write()` call sites now thread `error=is_error(result,
  name)` through to `core/display.py`, which switches to a red border +
  "PATCH FAILED"/"WRITE FAILED" title on error (unchanged happy-path
  styling otherwise, mirroring `show_shell()`'s existing convention).
  The identical bug in `show_file_write()` was bundled into the same fix
  (same file, same pattern). `show_patch()`'s call site additionally
  gained a narrow inline check for `tools/patch_tools.py`'s
  `[PATCH_FAILED]` prefix, deliberately not via widening the shared
  `is_error()` (which by design excludes `[PATCH_FAILED]` from the
  retry/escalation logic — see [NEW-19] below for a deferred design
  question this surfaced). code-reviewer approved: confirmed
  `is_error()` and all four retry/escalation call sites untouched,
  happy-path output byte-for-byte unchanged, full suite 325 passed (1
  pre-existing unrelated failure). **Code complete, code-reviewer
  approved via direct `execute_tool()`-level verification — no live
  model session, explicitly assessed as unwarranted for this
  display-only class of change.** See `PROJECT_LOG.md` 2026-07-30 Round
  16 entry for full detail.
- **Confidence: Confirmed** — observed in all 4 of 4 failed draws this
  round (a1, a2, b1, b2).
- **Where found:** `core/agent.py`'s `show_patch()` call (live-verifier
  cited ~line 410-413; re-verify exact line numbers before scoping a
  fix). It renders the green "Patching `main.py`" diff-preview panel
  unconditionally, regardless of whether the underlying
  `TOOLS[name](args)` patch call actually succeeded. In every one of the
  4 failed draws this round, the UI showed a success-looking "Patching
  main.py" panel that had nothing to do with what actually happened on
  disk (confirmed via `git diff` showing no change in every single
  failed draw).
- **Why this matters:** a real UI-honesty gap, independent of NEW-7's
  root cause — a user watching the terminal would see a success-looking
  panel even when nothing was written to disk.
- **Not fixed here.**

### [NEW-17] The post-edit "offer to commit" prompt scopes to ALL current working-tree changes, not just the current turn's edit (Confirmed)

- **Status: RESOLVED (commit `f4f51fa`), code-reviewer approved via
  direct scratch-repo verification, 2026-07-30.** No live model session
  needed for this class of change (see `PROJECT_LOG.md` Round 17 for
  full details).
- **Confidence: Confirmed** — observed in every draw of this
  investigation.
- **Where found:** `core/agent.py`'s `check_git_and_offer_commit()`
  (live-verifier cited ~line 659-680; re-verify exact line numbers
  before scoping a fix). It fires whenever `patch_file`/`write_file` was
  ATTEMPTED this turn (success or failure), and offers to commit ALL
  current working-tree changes, not just this turn's. In every draw of
  this investigation it fired against a PRE-EXISTING, unrelated dirty
  `NEW_ISSUES.md` already in the working tree.
- **Why this matters:** a real scope-bleed risk — a user reflexively
  answering "y" to this prompt after a failed edit attempt could commit
  unrelated in-progress work they didn't intend to commit yet.
- **Fix:** added `git_status_paths()`/`git_commit_paths()` to
  `core/githelper.py` (scoped `git add -- <paths>` / `git commit -- <paths>`,
  never `-A`), threaded the already-existing per-turn `files_touched`
  list into `check_git_and_offer_commit()`. `git_commit()`/`git_status()`
  themselves untouched, still used by `main.py`'s intentionally-broad
  manual-commit flows.
- **Accepted low-priority footnote (not tracked as its own issue):**
  code-reviewer noted `files_touched` accumulates paths from any tool
  call with a `path` arg (including `read_file`), not strictly
  write/patch tools. Harmless today — `git_status_paths()`/
  `git_commit_paths()` no-op on files with no actual working-tree
  changes — but slightly imprecise. Judged too minor to warrant a
  dedicated NEW-2x entry; revisit only if `files_touched`'s population
  logic is touched again for an unrelated reason.

### [NEW-18] A single lightweight REPL session (no daemon/plannd/embed stack) hit severe swap-thrashing after only 2 model calls with retries — swap pressure isn't limited to the full 3-model stack (Confirmed, possibly related to [NEW-14])

- **Confidence: Confirmed** — directly observed once this round; not yet
  investigated for root cause or reproducibility.
- **Where found:** Round 14 NEW-7 live-reproduction, Session B. Swap
  usage climbed to 8.9Gi (from a healthy ~1.6-2.2Gi baseline) within a
  SINGLE REPL session after only 2 model calls with retries (b1, b2),
  using the LIGHT harness (plain `main.py --no-resume`, no
  daemon/plannd/embed server) — a harness previously assumed safe based
  on NEW-13's earlier-this-session live-verification.
- **Why this matters:** suggests swap-thrashing risk isn't limited to the
  full 3-model `codeydOS start` stack ([NEW-14]) — it can also occur
  within a single lightweight REPL session under retry-heavy/multi-turn
  load.
- **Open question:** whether this is inherent to sustained single-session
  multi-turn agent use on this device, or specific to the
  retry/escalation-heavy failure pattern this investigation was
  triggering (multiple failed patch attempts + `write_file` escalation
  attempts in the same session, as seen in [NEW-15]).
- **Not fixed here** — flag as needing a dedicated investigation given
  its implications for CLAUDE.md rule 2's RAM-discipline guidance (may
  need updating to caution about sustained retry-heavy sessions, not
  just concurrent multi-model stacks).

## Found during Round 16 (NEW-16) scoping pass, 2026-07-30 — NOT fixed, logged only

### [NEW-19] Whether `[PATCH_FAILED]`'s deliberate bypass of the retry/escalation logic is fully correct as designed, and whether it needs its own distinct transcript marker (Suspected)

- **Confidence: Suspected** — a design question surfaced during Round
  16's scoping, not yet confirmed as a bug. Needs its own dedicated
  scoping pass, not fixed here.
- **Where found:** while scoping Round 16's `show_patch()`/
  `show_file_write()` display fix, confirmed (by reading
  `tools/patch_tools.py` and `core/agent.py`'s retry/escalation call
  sites) that `[PATCH_FAILED]` (the old_str-not-found case) is
  deliberately excluded from `is_error()`, so it never enters the
  auto-retry gate, the peer-CLI escalation path, or NEW-2's
  `[EDIT NOT APPLIED]` transcript marker — by design, so the model sees
  full untruncated file content to reconstruct the edit itself, rather
  than a truncated retry message.
- **Open question 1:** is bypassing retry/escalation entirely the right
  behavior for every `[PATCH_FAILED]` case, or should some subset (e.g.
  repeated failures on the same file/turn) still escalate?
- **Open question 2:** if a `[PATCH_FAILED]` case is never resolved
  within a turn, there is currently no transcript marker recording that
  outcome at all. Reusing NEW-2's existing `[EDIT NOT APPLIED] <tool> on
  <path> failed after retries and escalation were exhausted — no file
  was modified.` marker verbatim would be **inaccurate** for this case
  specifically: `[PATCH_FAILED]` never enters retry or escalation in the
  first place, so the phrase "after retries and escalation were
  exhausted" is false here. If a marker is wanted for this case, it
  needs its own distinct wording, not a naive reuse of NEW-2's marker.
- **Not fixed here** — this is a design question, not a display bug (the
  narrow, display-only fix in Round 16 addresses only the UI-honesty gap
  at the panel-rendering layer, not this deeper retry/escalation/
  transcript-marker question). Needs its own dedicated scoping pass in
  NEW-2/NEW-15 territory before any fix is attempted.
- **Decisions recorded 2026-07-30 (Ish, direct):**
  1. Keep single-failure `[PATCH_FAILED]` behavior as-is (full untruncated
     file shown, no retry) — but if the SAME file fails with
     `[PATCH_FAILED]` more than once in a turn, route it into the
     existing peer-CLI escalation path (`core/peer_cli.py`'s `escalate()`,
     already used at `core/agent.py:1781` for exhausted-retry cases)
     instead of showing full content again indefinitely.
  2. Add a new, distinct transcript marker for this case (not a reuse of
     NEW-2's `[EDIT NOT APPLIED]`, since that marker's "after retries and
     escalation were exhausted" wording would be false here) — fires when
     a `[PATCH_FAILED]` case is never resolved within a turn.
  3. **Verified still current as of 2026-07-30** (re-checked before
     recording this decision, not assumed stale): `core/agent.py:1715`'s
     actual retry gate (`is_error(last_tool_result, name) and
     auto_retries < max_retries`) still excludes `[PATCH_FAILED]` —
     confirmed `is_error()` (`core/agent.py:492`) only matches an
     `[ERROR]` prefix or shell-specific traceback signals, neither of
     which `[PATCH_FAILED]` is. The Round 16 fix's `_is_err` check for
     `[PATCH_FAILED]` (`core/agent.py:416-417`) is display-only (feeds
     `show_patch()`'s red-border styling), not this gate — so this
     decision is scoping a real, still-open gap, not a stale one.
  - **Status: scoped, decision recorded, not yet implemented.** Moved to
    `WORK_QUEUE.md` Track 2 as its own task.
  - **Update (implementation pass, 2026-07-30):** implemented in
    `core/agent.py` — added a per-turn, per-path `patch_failed_counts`
    dict; a repeated (>1) `[PATCH_FAILED]` on the same path within a turn
    now routes into the existing `core.peer_cli.escalate()` call (mirroring
    the exhausted-retries call site), and a new
    `[PATCH_FAILED, UNRESOLVED] <tool> on <path> repeated old_str-not-found
    failures were not resolved in this turn — no file was modified.` marker
    fires if it's still unresolved after that (escalation skipped/didn't
    resolve it, or `_in_subtask=True` skipped escalation entirely — the
    wording was deliberately kept true in both cases, unlike a naive reuse
    of NEW-2's wording). Code-complete and covered by 5 new unit tests in
    `tests/test_new19_patch_failed_repeat_escalation.py` (263/263 full
    suite passing) — **not yet live-verified** (no live model-load test was
    run for this pass; needed before this can be marked fully done) and
    **not yet code-reviewer approved.**
  - **Two small pre-existing/adjacent items surfaced while implementing,
    not fixed here (deliberately, per this task's scope):**
    1. NEW-2's own `[EDIT NOT APPLIED]` marker already has the same
       wording flaw the new NEW-19 marker was deliberately written to
       avoid: it says "failed after retries and escalation were exhausted"
       even when `_in_subtask=True`, where escalation is skipped entirely
       (never attempted, so "exhausted" is imprecise). Pre-existing, not
       introduced by this change. Confidence: Suspected.
    2. `patch_failed_counts` (this fix) and the pre-existing
       `files_touched` list are both keyed on the raw `args["path"]`
       string as given by the model — `main.py`, `./main.py`, and an
       absolute path to the same file would not collate, so the repeat
       counter (and `files_touched` dedup) could under-count if the model
       varies its path spelling across attempts. Consistent with
       `files_touched`'s pre-existing convention, so left as-is here, but
       worth normalizing (e.g. via `Path(...).resolve()`) in a future
       pass. Confidence: Suspected.
  - **Update (code-review pass, 2026-07-30):** code-reviewer independently
    re-verified scoping, key population, and elif-chain mutual exclusivity,
    and ran the 5 new tests plus the full 263-test suite live rather than
    trusting the implementer's summary — **APPROVED** (static/unit-test
    grounds only at this point; live-verifier confirmation against a real
    session was still outstanding).
  - **Update (live-verifier pass, 2026-07-30): CONFIRMED end-to-end,
    with one real gap surfaced and logged (not silently fixed) — see
    `NEW-38` below.** Drove `core/agent.py`'s real `run_agent()` two ways:
    directly, and (2nd run) through `main._run_with_plan(..., no_plan=True)`
    — the same dispatch `main.py`'s REPL loop calls — with a scripted/
    mocked `infer` (no local 7B/1.5B/embedding model loaded; `ps aux |
    grep llama-server` showed nothing before or after either run,
    confirmed). Fed two, then a third, `patch_file` calls with a
    nonexistent `old_str` on the same path (`main.py`) within escalating
    turns, `_in_subtask=False`. Deliberately did **not** mock
    `core.peer_cli.escalate()` (unlike the unit tests) so its real
    `confirm()` interactive prompt (`console.input()`) would fire for
    real — it did, verbatim, on the 2nd same-path `[PATCH_FAILED]`:
    ```
      ⚠  Codey hit max retries and needs help.
      Task:       add a docstring to shutdown function in main.py
      Suggest:    Gemini CLI (Google)  (debugging task)
      Fallbacks:  qwen
    ```
    Answered "n" via real stdin to decline. Confirmed live: (1) the
    prompt fires on the 2nd same-path `[PATCH_FAILED]`; a 3rd same-path
    failure (fed in the 2nd run) correctly fires the prompt **again**
    (escalation is offered on every new occurrence past the first, not
    just once per turn) — no double-fire for the *same* failure, no
    infinite loop, no crash; (2) declining falls through each time to
    `[PATCH_FAILED, UNRESOLVED] patch_file on main.py repeated
    old_str-not-found failures were not resolved in this turn — no file
    was modified.` via `agent.log_error` (2 log entries for the 2-decline
    run) — **not** NEW-2's `[EDIT NOT APPLIED]` marker, confirming the two
    are mutually exclusive as designed; (3) `git status` clean afterward
    both runs (patch never matched, so no file was ever actually mutated,
    as expected for this failure mode).
    **Correction to an initial overclaim (per CLAUDE.md rule 6):** the
    first live-verification pass claimed the marker was "confirmed
    present in `history`/response chain" — that was asserted without
    actually inspecting `history`, and a follow-up check disproved it:
    `history` returned by `run_agent()`/`_run_with_plan()` only ever gets
    the original `user_message` and the final `response` appended
    (`core/agent.py:1989-1990`); the `[PATCH_FAILED, UNRESOLVED]` marker
    is folded only into the in-turn `messages` list (the model's own
    context for that turn), which is discarded once the turn ends — it
    does **not** survive into the `history` that gets saved to disk via
    `save_session()`. So the marker is visible live in the console/log at
    the moment it fires, and — **separately confirmed live, not just
    read from code** — actually reaches the `messages` list handed to
    the model on the immediately-following call (a 3rd driver run
    printed the exact `messages` content seen by the mocked `infer()`
    for that call and it contained, verbatim: `'[PATCH_FAILED,
    UNRESOLVED] patch_file on main.py repeated old_str-not-found
    failures were not resolved in this turn — no file was modified.\n
    Tool result: [PATCH_FAILED] old_str not found in main.py (1583
    lines)...'`). But a user reopening a **saved session** afterward
    would not see it in the transcript. Logged as `NEW-38` below rather
    than silently accepted or fixed, since this is outside this task's
    scope (verification, not a fix). Downgrading the "in the
    transcript/history" wording accordingly.
    **Scope caveat (NEW-36):** this run's `old_str` values were
    deliberately non-identical across attempts (`_LIVE2_v1`/`_v2`/`_v3`,
    matching the existing unit tests' convention) specifically to avoid
    the pre-existing verbatim-duplicate-tool-call guard documented in
    `NEW-36` (Confirmed), which intercepts byte-identical repeat tool
    calls before NEW-19's counter ever increments. So this live
    verification covers the **varied-old_str repeat** path only —
    `NEW-36` itself notes that exact-repeat (identical `old_str`) is
    actually the *more* common real-LLM failure mode, and that path
    still bypasses NEW-19's escalation entirely, unchanged by this round.
    **NEW-19's core escalation/marker-firing logic (for the varied-old_str
    repeat path) is live-verified working as designed; the
    transcript-persistence gap is a separate, logged, not-yet-fixed
    follow-up (`NEW-38`); the exact-repeat gap remains `NEW-36`, also not
    fixed here.**


### [NEW-43] `is_error()`'s deliberate `[CANCELLED]` exclusion means the Round 16 (`NEW-16`) patch-panel-honesty fix does not cover the user/EOF-declined-confirm case — the green "Patching `<file>`" success panel still renders when a patch was cancelled and nothing was written (Confirmed) — plus a related, distinct finding: a real, correctly-grounded rename `old_str` can still produce an incomplete/code-breaking edit if the target variable is used more than once in the function (Suspected)

- **Confidence: Confirmed** (panel-honesty gap), reproduced live once
  this round; **Suspected** (incomplete-rename finding), confirmed by a
  static post-hoc replay of the exact tool call, not by a live multi-turn
  session continuing past the first patch.
- **Where found:** Round 20 (NEW-7 b3/b4 live-reproduction session,
  2026-07-30). During `b4` (patch_tools rename prompt), the model's
  `patch_file` call had a correct `old_str`, but the test harness's
  non-interactive stdin didn't answer `tools/patch_tools.py:75`'s
  `ask_confirm("Apply patch?")` — `utils/logger.py:129-131`'s EOF path
  defaulted to `False`, so `tool_patch_file()` returned
  `"[CANCELLED] Patch cancelled."` (`tools/patch_tools.py:76`) and no
  file was modified (confirmed via `git diff` immediately after: empty).
  **The terminal transcript still showed the panel titled "Patching
  `patch_tools.py`" — not "PATCH FAILED", which per `NEW-16`'s own
  resolution note is the title `error=True` produces — with no failure
  indication, and the model's own next message was "Done."** (colour
  was not independently observable in the captured log, since ANSI
  codes were stripped during parsing; the title text is the load-bearing
  evidence here) — a real user answering `N` to the same confirm prompt
  would see the identical false-success signal.
- **Root cause, confirmed by reading the code (not just re-asserting
  NEW-16's fix):** `core/agent.py:415-424`'s `_is_patch` branch computes
  `_is_err = is_error(result, name) or result.startswith("[PATCH_FAILED]")`
  and passes it to `show_patch(..., error=_is_err)`
  (`core/display.py:89`, the exact mechanism NEW-16's Round 16 fix
  added). But `core/agent.py:492`'s `is_error()` has an explicit,
  deliberate early return: `if "[cancelled]" in result_lower: return
  False` (line 496-497) — this predates and is untouched by the Round 16
  fix, and was apparently never exercised by Round 16's own live-reproduction
  draws (a1/a2/b1/b2, all genuine `[PATCH_FAILED]`/`[ERROR]` cases, never
  a user-declined confirm). **This is a real gap in NEW-16's coverage,
  not a regression of the Round 16 fix itself** — the fix works exactly
  as designed for the case it was built and tested against; `[CANCELLED]`
  is a third, distinct result class that was never in scope for that fix
  and still produces the original NEW-16 symptom.
- **Why this matters:** identical severity to NEW-16's original finding —
  a user watching the terminal, or the model itself narrating "Done.",
  gets a success-looking signal for an edit that did not happen. This is
  arguably *more* likely to occur in normal use than the `[PATCH_FAILED]`
  case, since declining a patch confirmation (accidentally or
  deliberately) is a common, ordinary interaction, not an edge case.
- **Distinct second finding — incomplete rename, Suspected only:** a
  post-hoc, non-live replay of the model's exact `patch_file` args
  (`old_str="p = Path(path).expanduser()"`,
  `new_str="file_path = Path(path).expanduser()"`) against
  `tools/patch_tools.py`, with `ask_confirm` monkey-patched to return
  `True` (no model/RAM load involved — a static function call, confirmed
  via `git diff` then immediately reverted with `git checkout --`),
  showed the patch **applies successfully** (the string is unique in the
  file, confirmed via `grep -c` = 1) but leaves the function referencing
  an undefined name `p` in 4 more places (`p.exists()` x2, `p =
  Path(os.getcwd())...`, `p.read_text(...)`) that the rename request
  ("rename the variable `p` to `file_path`") did not touch — the
  resulting code would raise `NameError` at runtime. In the live
  transcript, the model said "Done." immediately after this single patch
  attempt (before the harness's confirm-default-reject kicked in),
  suggesting it would have stopped after one patch call even had the
  edit been accepted, without completing the rename across all uses.
  **Not confirmed live** (the real turn never got a "yes" answer to
  actually apply it and observe whether the model's *next* turn would
  have caught and fixed the resulting `NameError`) — flagged as
  Suspected, needs its own live draw with the confirm actually answered
  `y` to settle whether the model self-corrects.
- **Not fixed here** — both items are out of NEW-7's scope
  (NEW-7 investigates `old_str` grounding specifically; both of these are
  about different mechanisms — UI-honesty on cancellation, and edit
  completeness). Logged per CLAUDE.md rule 8, not silently fixed or
  dropped.

## Found during Round 18 (NEW-18 live-reproduction attempt), 2026-07-30 — NOT fixed, logged only

### [NEW-18] update — original question remains UNANSWERED after Round 18 attempt (correction per Ground Rule 6)

- **Correction:** Round 18 attempted to reproduce and isolate NEW-18's
  open question (whether swap-thrashing is driven by context SIZE or by
  turn COUNT/retries) by comparing a small-file multi-turn session
  against a one-large-file-read session. **The comparison could not be
  run** — the test harness hit a distinct, unrelated bug in `main.py`'s
  stdin handling (see [NEW-20] below) before either session produced any
  model traffic. Zero requests reached `llama-server` in this attempt
  (confirmed via `llama-server.log` showing no incoming requests after
  the "listening on http://127.0.0.1:8080" line).
- **This is not new evidence either way.** NEW-18's original open
  question (size vs. count/retries as the driver) is still exactly as
  open as it was when originally logged. Do not read this round as
  confirming, refuting, or narrowing that question.
- **For any future reproduction attempt:** originally, this guidance
  required a TTY-backed harness (e.g. a `pty`, `script(1)`, or similar),
  not plain stdin piping into `main.py --no-resume` — see [NEW-20] for
  why plain piping didn't work at the time. **Update (Round 19):** this
  constraint is now relaxed. NEW-20 was fixed in commit `ac732e9` and
  fully live-verified — plain stdin piping into `main.py --no-resume` no
  longer hangs, spins, or garbles input, so a future NEW-18 reproduction
  attempt can safely use plain stdin piping again; a TTY-backed harness
  is no longer required for this reason (though may still be worth using
  if a TTY-specific behavior is itself under test). The harness should
  still control for baseline free RAM
  before model load, which varied meaningfully between the two runs
  attempted so far (this run's baseline was 4.3Gi used/2.2Gi free vs.
  the original NEW-7 run's baseline of 4.9Gi free) and is a likely
  confound on severity, independent of the size-vs-count question.
- **Not fixed here** — NEW-18 remains open, unresolved, unchanged in
  substance from its original entry above.

### [NEW-20] `main.py`'s paste-detection `select()` logic busy-loops at ~100% CPU and mis-concatenates input when stdin is a non-TTY file/pipe (Resolved)

- **Resolved in Round 19, commit `ac732e9`.** The paste-detection
  `select()` loop is now wrapped in `if sys.stdin.isatty():`, so it's
  skipped entirely for non-TTY stdin — falling through to the plain
  single-line `input()` result with existing `EOFError` handling taking
  over naturally at end of input. TTY sessions keep the exact same
  paste-glue behavior.
- **Code-reviewer approved:** independently reproduced pre-fix hang
  (piped input times out, exit 124), post-fix clean processing (exits in
  under a millisecond), and confirmed via a pty-based TTY simulation that
  paste-glue still fires correctly for genuine interactive sessions.
  Checked all launcher scripts (`gui/start.sh`, `codeydOS`, `codeyOS`)
  for stdin wrapping that could affect `isatty()` in real use — none
  found.
- **Fully live-verified (Round 19):** real invocation
  `printf 'hello\nwhat is 2+2\n/exit\n' | timeout 180 python3 main.py
  --no-resume` — `real 0m27.791s`, exit 0. The two piped lines were
  processed as two distinct, correctly-answered turns (not garbled
  together), with clean `/exit` teardown and no orphaned `llama-server`
  process afterward. This did involve a real model-load cycle (`repl()`
  calls `loader.load_primary()` unconditionally before the input loop),
  confirmed fully unloaded afterward per CLAUDE.md rule 2.
- **Consequence for [NEW-18]:** the harness guidance in NEW-18's entry
  below is updated — plain stdin piping into `main.py --no-resume` is now
  safe to use in a future reproduction attempt, since this fix is exactly
  what made it unsafe.

- **Confidence: Confirmed** — directly reproduced this round, and
  root-caused by reading the code and cross-referencing the session log
  and `llama-server.log`.
- **Where found:** `main.py:1337-1359`. The multi-line-paste-detection
  code calls `select.select([sys.stdin], [], [], 0.02)` to decide whether
  more input is immediately available (to distinguish a pasted
  multi-line block from a single line typed interactively). When stdin is
  a non-TTY file or pipe (e.g. a test harness piping a static input file
  into `main.py --no-resume`'s stdin), `select()` always reports stdin as
  "readable" — including once the file is at EOF. This caused two
  distinct failures in sequence this round:
  1. On the very first `input()` call, the paste-detection logic drained
     the *entire* remaining input file in one pass, concatenating all of
     it into a single garbled message instead of treating it as separate
     turns.
  2. After EOF, `readline()` returns `''` forever while `select()` keeps
     reporting the descriptor as "ready" — so the loop spins indefinitely
     with no forward progress and no way to exit. Observed at ~88% CPU on
     a 13MB-RSS process, with the model loaded successfully but zero
     requests ever reaching `llama-server` (confirmed via
     `llama-server.log` showing no incoming requests after the "listening
     on http://127.0.0.1:8080" line).
- **Why this matters:** this is a real, distinct bug independent of
  RAM/swap behavior — it currently blocks any automated/scripted testing
  of the REPL via stdin redirection, and could plausibly affect any real
  non-interactive invocation of `main.py` (e.g. piped input from another
  script or process), not just test harnesses.
- **Not fixed here** — flag as needing its own scoping/fix pass. This is
  a clean, cheap, well-isolated candidate for a near-future round: the
  root cause is already fully identified (the `select()`-based paste
  heuristic is TTY-only-safe and needs an `os.isatty(sys.stdin.fileno())`
  guard, or equivalent, before relying on `select()`'s readiness signal).

### [NEW-21] Model load alone (before any inference) can drive swap from ~1.2Gi to ~5.6Gi within ~10 seconds when baseline free RAM is tight (Confirmed, related to [NEW-14])

- **Confidence: Confirmed** — directly observed this round via
  `llama-server.log` timestamps and `free -h` readings taken by the
  live-verifier during the (otherwise inconclusive) Round 18 attempt.
- **Where found:** Round 18 live-reproduction attempt, using the light
  harness (plain `main.py --no-resume`, single model, no daemon/plannd/
  embed stack). Swap climbed from ~1.2Gi to ~5.6Gi within roughly 10
  seconds purely from the model load itself — confirmed via
  `llama-server.log` timestamps that this happened before any turn could
  possibly have been dispatched (and independently confirmed no requests
  ever reached the server this run at all). `llama-server`'s own RSS was
  subsequently squeezed from 5.6GB down to 1.26GB (partially swapped out),
  with swap climbing further to 6.8Gi over the following minute.
- **Baseline-dependency observation:** this run's baseline going into the
  load was 4.3Gi used / 2.2Gi free — notably worse than the original
  NEW-7 run's baseline of 4.9Gi free. Severity likely depends on how much
  free RAM exists before load starts, not just on the load itself; this
  is a relevant confound for any future comparison, not a fixed constant.
- **Why this matters:** consistent with [NEW-14]'s underlying concern
  (`n_ctx=32768`'s KV-cache reservation being large relative to this
  device's RAM budget), but now confirmed to affect even a **single
  lightweight model load**, not just the full 3-model
  `codeydOS start` stack. Same observational character as NEW-14 — may
  inform a future `n_ctx` tuning discussion, but no action is recommended
  yet.
- **Not fixed here** — observational only, logged for future reference.

## Found during Round 1 (C-1/H-1/H-4) fix task, 2026-07-29 — NOT fixed, logged only

### [NEW-1] `pytest tests/` spawns a real 7B `llama-server` and orphans it — matches audit finding L-6

- **Status: RESOLVED (commit `c65be95`), fully live-verified 2026-07-29.**
  live-verifier ran the full suite: `pytest tests/ -q` → **253 passed in
  0.43s** (previously ~42s, due to the hidden real 7B model load). No
  orphan `llama-server` process remained afterward, confirmed via
  `ps -eo pid,ppid,comm | grep llama` (not `pgrep -af`, which has a
  false-positive self-match issue in this shell environment — the
  wrapper's own command-line text matches the `llama` pattern). `free -h`
  was stable before/after (563Mi free → 816Mi free; swap unchanged at
  1.6Gi). Per Ground Rule 7, this closes the "code complete" →
  "fully live verified" gap left open after code-reviewer's approval,
  which had only re-run `tests/test_memory.py` in isolation, not the full
  suite.
- **Confidence: Confirmed (upgraded from Suspected, Round 5 diagnostic
  investigation, 2026-07-29).** The mechanism below was live-reproduced
  3+ times, including a decisive proof: catching the orphaned
  `llama-server`'s PPID pointing directly at the live pytest process
  itself, before OS reparenting to PID 1 had occurred.
- **Root cause:**
  `tests/test_memory.py::TestMemoryCompressSummary::test_compress_summary_handles_inference_failure`
  (lines ~351-361) calls `self.memory.compress_summary(long_history)`
  with **no mocking of inference at all**, despite its name and docstring
  ("compress_summary should return fresh turns when inference fails")
  implying it tests a failure/degraded path. Call chain: test →
  `core/memory_v2.py:600-627` `compress_summary()` unconditionally does
  `from core.inference_v2 import infer; ... compressed = infer(prompt,
  stream=False)` (line 619, wrapped in a bare `try/except Exception`,
  line 603/625, which is why the test still passes either way and never
  signaled the problem) → `core/inference_v2.py:65-94` `infer()` does
  `loader = get_loader(); if not loader.ensure_model(): ...` (lines
  92-94) — this `ensure_model()` call is the real model-load trigger,
  spawning an actual local 7B `llama-server` subprocess.
- **Evidence:**
  - A timestamped, verbose pytest log showed a 28-second gap (consistent
    with a real 7B model load) immediately before this specific test,
    versus ~5ms between every other adjacent test pair in the suite.
  - Live-reproduced 3+ times in Round 5.
  - Decisive proof: in one reproduction, the orphan `llama-server`'s PPID
    was caught pointing directly at the live pytest process ID before OS
    reparenting to PID 1 occurred (matches the two earlier PPID-1
    orphan observations logged below, which were seen only after
    reparenting had already happened).
  - Nothing in the test's setUp/tearDown (`tests/test_memory.py:335-340`,
    `reset_memory()` only) tracks or kills the spawned server, which is
    why it's left running/orphaned after the test session ends.
- **Original correlation evidence (Round 1, retained for record):** Ran
  `python3 -m pytest tests/ -q` (253/253 pass, no failures) inside one
  single shell command that also ran `free -h; pgrep -af llama-server`
  immediately after — that combined command's output showed a full 7B
  `llama-server` on port 8080 running with `PPID 1` (reparented/orphaned),
  no PID file anywhere (`~/.codeyOS/codeyOS.pid` doesn't exist), no daemon
  running. Reproduced in an earlier separate run too (different PID).
  Both times the process outlived the pytest run and had to be killed
  manually (`kill -TERM -<pid>`, scoped to that PID's process group) to
  recover RAM — that part (kill discipline, RAM recovery) is solid and
  verified both times via `free -h` before/after.
- **Impact:** a device crash occurred during the Round 1 session in which
  this was first observed, with RAM going from ~6.6 GB available to under
  200 MB free with 6+ GB in swap without any deliberate model-load
  action. Now that the mechanism is confirmed, this test is a real,
  reproducible RAM-crash contributor, not just a plausible one — every
  plain `pytest tests/` run loads a full 7B model and orphans the server.
- **Round 1 static investigation (superseded by Round 5, not
  retracted):** a targeted grep-level search
  (`grep -rn "llama-server\|LlamaServer\|subprocess\|Popen\|get_loader\|ensure_model" tests/*.py`)
  missed the mechanism because it only checked for direct spawn/loader
  calls inside `tests/*.py` files, not the indirect path through
  `core/memory_v2.py`'s `compress_summary()` (`infer(` is called from
  non-test code). That static approach could not have found this; the
  gap is closed by the Round 5 dynamic (timestamped-log + PPID-capture)
  investigation above.
- **Fix direction:** mock `core.inference_v2.infer` (or the loader it
  calls) in `test_compress_summary_handles_inference_failure` so the test
  actually exercises the inference-unavailable branch it claims to test,
  without triggering a real model load. See fix task scoped in
  `PROJECT_PLAN.md` / handed to implementer.

## Found during Round 7 (NEW-2) full-suite runs, 2026-07-29/30 — NOT fixed, logged only

### [NEW-8] `ccos/tests/test_ccos.py::test_sandbox` fails on this device, pre-existing and unrelated to Round 7's changes
- **Confidence: Confirmed** (independently reproduced twice — once by
  implementer, once by code-reviewer running the full suite separately
  — both during Round 7's NEW-2 work, in `ccos/tests/test_ccos.py`, a
  file untouched by Round 7's diff).
- **Where found:** `pytest tests/ ccos/... -q`-style full-suite runs
  during Round 7 (NEW-2). Result both times: `321 passed, 1 failed`,
  the failure being `ccos/tests/test_ccos.py::test_sandbox`.
- **Likely cause (from code-reviewer's read, not yet root-caused in
  depth):** an `echo` command sandbox-path-allowlist issue in
  `ccos/core/sandbox.py`'s handling of the test's shell-command case,
  not related to any file this round's diff touched.
- **Impact:** cosmetic to Round 7 (doesn't affect its correctness
  claim, since it's outside the diff), but represents a real,
  reproducible environment/test gap worth its own investigation.
- **Not fixed here:** out of scope for Round 7 (NEW-2), which only
  touched `core/agent.py` and added
  `tests/test_new2_edit_not_applied.py`. Needs a dedicated look at
  `ccos/core/sandbox.py`'s `echo`-command allowlist logic and
  `ccos/tests/test_ccos.py::test_sandbox`'s expectations before scoping
  a fix.
- **Status: RESOLVED, verified 2026-07-30.** Root cause was exactly as
  suspected: `ALLOWED_DIRS` in `ccos/core/sandbox.py` hardcoded the
  literal string `"/tmp"`, but `Sandbox.__init__`'s
  `tempfile.mkdtemp(prefix="ccos_sandbox_")` (no `dir=` arg) resolves
  against `tempfile.gettempdir()`, which on this Termux device is
  `/data/data/com.termux/files/usr/tmp`, not `/tmp` — so the sandbox's
  own working directory failed its own allowlist check and every
  command failed, including `echo hello`. Fix: replaced the `"/tmp"`
  literal with `tempfile.gettempdir()`. Verified with
  `python3 -m pytest ccos/tests/test_ccos.py::test_sandbox -v` → `1
  passed` (via a real `assert result.success` on `echo hello`, not a
  bare `return True`), and `python3 -m pytest tests/ ccos/tests/ -q` →
  `334 passed, 0 failed`. Diff was a single 5-line, comment-included
  change to `ALLOWED_DIRS`; no other lines in `sandbox.py` touched.

### [NEW-41] `Sandbox.cleanup()` calls `shutil.rmtree()` with no `import shutil` in `ccos/core/sandbox.py`, and the resulting `NameError` is silently swallowed
- **Confidence: Confirmed** (found while reviewing the NEW-8 fix;
  `git blame` on the line dates it to commit `30e22b2c`, pre-existing
  and unrelated to the NEW-8 `ALLOWED_DIRS` change).
- **Where:** `ccos/core/sandbox.py`, `Sandbox.cleanup()` (around line
  268): `shutil.rmtree(str(self._tmp_dir), ignore_errors=True)` inside
  a `try: ... except Exception: pass`. The module only imports `os`,
  `subprocess`, `tempfile`, `time`, `Path` — never `shutil`.
- **Impact:** every call to `cleanup()` raises `NameError: name
  'shutil' is not defined`, which the bare `except Exception: pass`
  silently discards. The sandbox's per-instance temp directory (now
  living under the just-widened `tempfile.gettempdir()` allowlist,
  per the NEW-8 fix above) is therefore never actually deleted —
  `Sandbox()` leaks one `ccos_sandbox_*` directory per
  instantiation/singleton-reset for the life of the device, with no
  visible error anywhere.
- **Not fixed here:** out of scope for the NEW-8 fix, which only
  touched the `ALLOWED_DIRS` list. Needs its own round: add
  `import shutil` (or drop the `try/except Exception: pass` and let
  cleanup failures surface, since silently swallowing exceptions is
  its own smell per this project's review checklist).

### [NEW-42] `ccos/core/sandbox.py`'s `ALLOWED_DIRS`/`_validate_path` only gates the execution `cwd`, not what a command can touch
- **Confidence: Confirmed** (read of `Sandbox.run_command`, which
  passes `command` to `subprocess.run(..., shell=True, cwd=exec_cwd)`
  after `_validate_path` checks only `exec_cwd`).
- **Impact:** the allowlist is not a filesystem containment boundary —
  a command like `cat /etc/passwd` or `rm -rf ~/important` will run
  fine from any allowed `cwd`, since `_validate_path` never inspects
  the command string's own path arguments. This was true before the
  NEW-8 fix too (widening `"/tmp"` to `tempfile.gettempdir()` doesn't
  change this posture — on Termux the new path is actually
  app-private and strictly narrower than shared `/tmp` would have
  been on stock Linux, so NEW-8 is not a regression here).
- **Not fixed here:** out of scope for NEW-8. If this sandbox is ever
  relied on as a real security boundary (vs. a footgun-prevention
  convenience for the self-improvement/plugin-test paths it's used
  from), it needs its own design pass — e.g. a real filesystem
  namespace/chroot, not a `cwd`-only string-prefix check.

## Pre-existing Test Failures (Not Introduced by V3 Changes)

### test_hallucination.py (8 failures)
- **Status: RESOLVED, verified 2026-07-30.** `python3 -m pytest tests/test_patch.py tests/test_hallucination.py -q` → `24 passed`, 0 failures. Whatever caused the original 8 failures no longer reproduces on current code — confirmed by directly running the test file, not inferred. Marked done during a NEW_ISSUES.md accuracy sweep; not tied to a specific round/commit since the fix (if any) predates when this was checked.
- **Original issue (for history)**: Hallucination detection tests failing
- **Original root cause**: The `detect_hallucination()` function in `core/agent.py` didn't detect past-tense claims like "I created", "I wrote", "I modified"
- **Files**: `tests/test_hallucination.py`, `core/agent.py`

### test_patch.py (1 failure)
- **Status: RESOLVED, verified 2026-07-30.** Same test run as above confirms 0 failures in `test_patch.py`. The test's expectations were already updated to match the current `[PATCH_FAILED]` message format (confirmed during Round 15's code review, which noted `tests/test_patch.py` only asserts `assertIn("old_str not found", res)` — a substring unaffected by later wording changes).
- **Original issue (for history)**: Patch error message format changed
- **Original root cause**: The patch tool now returns `[PATCH_FAILED]` instead of `[ERROR] String not found`
- **Files**: `tests/test_patch.py`, `tools/patch_tools.py`

## Additional Security Hardening Needed

### 1. Command Injection via Filename (agent.py:863-865)
- **Status**: Partially addressed
- **Issue**: Shell commands built from LLM-generated filenames
- **Recommendation**: Add filename sanitization before shell command construction

### 2. Daemon Shell Allowlist Too Broad (task_executor.py:47-52)
- **Status**: Documented but not changed
- **Issue**: `python` and `pip` are allowed prefixes, enabling arbitrary code execution
- **Recommendation**: Consider restricting to specific script paths

### 3. Unix Socket Authentication (daemon.py)
- **Status**: Added peer UID check
- **Issue**: Current implementation relies on Unix domain socket permissions
- **Recommendation**: Consider adding token-based authentication for additional security

## Code Quality Improvements Needed

### 1. Unused Imports (129 F401 violations)
- **Files**: Multiple files throughout codebase
- **Recommendation**: Run `autoflake --remove-all-unused-imports` to clean up

### 2. Line Length Violations (1343 E501 violations)
- **Files**: Multiple files throughout codebase
- **Recommendation**: Consider using `black` formatter with line length 100

### 3. Comparison Style (74 E712 violations)
- **Files**: Multiple files
- **Recommendation**: Replace `== False` with `is False` or `not cond`

## Privacy Enhancements Needed

### 1. Network Request Logging
- **Status**: Not implemented
- **Issue**: No logging of network requests for audit trail
- **Recommendation**: Add optional network request logging

### 2. Data Retention Policy
- **Status**: Not implemented
- **Issue**: No automatic cleanup of old session data
- **Recommendation**: Add configurable data retention settings

## Testing Gaps

### 1. Integration Tests
- **Status**: Missing
- **Issue**: No integration tests for daemon mode
- **Recommendation**: Add integration tests for daemon startup/shutdown

### 2. Security Tests
- **Status**: Partial
- **Issue**: Shell injection tests exist, but no tests for path traversal
- **Recommendation**: Add path traversal tests for filesystem operations

## Documentation Updates Needed

### 1. Security Guide
- **Status**: Referenced in README but may need updates
- **Issue**: Security guide should document V3 security improvements
- **Recommendation**: Update `docs/security.md` with V3 changes

### 2. Privacy Policy
- **Status: RESOLVED, verified 2026-07-30.** `PRIVACY.md` exists in the
  repo root with real content (87 lines — 100%-local-by-default, no
  telemetry, data handling practices). This entry was stale; the file
  it asked for already exists. Confirmed by directly reading the file,
  not inferred.
- **Original issue (for history)**: No explicit privacy policy document
