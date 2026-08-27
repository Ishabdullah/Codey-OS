# New Issues Found During V3 Overhaul

**This is the project's append-only findings ledger (CLAUDE.md rule 8),
subordinate to `CODEY_MASTER_PLAN.md` — the single authoritative plan.**
It is NOT archived and is still where every out-of-scope finding gets
logged, rated Confirmed or Suspected. Per-issue status is authoritative
*here*; the master plan carries only the findings that shape open work
(its Appendix B) and deliberately does not restate 155 statuses it would
have to guess at. Sections are chronological by the round that found
them, not by issue number — search for `[NEW-nnn]` rather than scrolling.

## Found during the 2026-08-22 one-model decision scoping (§1.4 of `CODEY_MASTER_PLAN.md`) — desk-only, GGUF header + binary `strings` reads, NO model loaded, NOT fixed, logged only

### [NEW-156] `MAX_CONCURRENT_MODEL_BUDGET_BYTES` (8.90GiB) and `MAX_SWAP_ASSIST_BYTES` (10.00GiB) are both derived from models that are being retired — their entire basis disappears with the one-model decision

- **Status:** Confirmed (arithmetic provenance, read directly from
  `core/resource_gate.py` and this project's own derivation records).
- **Mechanism:** `MAX_CONCURRENT_MODEL_BUDGET_BYTES` was computed as
  exactly 7B (6.361GiB) + 1.5B (2.166GiB) + embed (~0.328GiB) at
  `n_ctx=32768`, rounded up to 8.90GiB (see `NEW-133` for the correction
  history). Two of those three models leave the system under Ish's
  2026-08-22 decision. `MAX_SWAP_ASSIST_BYTES` was raised from 768MiB to
  10.00GiB in 7.4a sub-task F for one specific purpose: making the 7B at
  `n_ctx=32768` reachable through swap assist. That target no longer
  exists either.
- **Impact:** neither constant is "slightly stale" — each one's stated
  derivation refers to a configuration that will not exist. A cumulative
  ceiling sized for three concurrent models, applied to a system that
  loads one generation model plus an embedder, is not conservative; it is
  meaningless. The 10GiB swap-assist cap is the more concerning of the
  two: `TODO.md` 7.4a sub-task F already documented that it makes
  `can_admit()`'s plain-`MemAvailable` check effectively non-binding for
  any single admissible model, and that reasoning holds with more force
  once the model it was sized for is gone.
- **Fix direction:** re-derive both, but only AFTER the new model's real
  resident cost is measured live (master plan M1-E → M1-F). Deriving them
  from arithmetic first is precisely the mistake `NEW-133` recorded.
- **Not fixed this round** — documentation/scoping round, no code touched.

### [NEW-157] `core/resource_gate.py`'s `ModelArch` cannot represent a hybrid Transformer-SSM model — Qwen3.5-4B has 8 full-attention layers and 24 SSM layers, so the gate over-estimates its KV cache by ~4x and would wrongly refuse an affordable `n_ctx=65536` (entry corrected same-day — see below)

- **Status:** Confirmed that the metadata field exists and that
  `ModelArch` has no way to express it; Suspected as to the exact size of
  the resulting error (that requires live measurement).
- **Mechanism:** `ModelArch(n_layers, n_kv_heads, head_dim,
  kv_bytes_per_element)` and `estimate_model_load_cost()`'s KV term assume
  **uniform full attention on every layer**:
  `2 × 2 × n_layers × n_kv_heads × head_dim × n_ctx`. Qwen3.5-4B's GGUF
  header (read directly, no model load) declares
  `qwen35.full_attention_interval = 4` alongside `block_count = 32`,
  `attention.head_count_kv = 4`, `attention.key_length = 256`. A
  `full_attention_interval` of 4 indicates only every 4th layer carries a
  full KV cache, the rest using a cheaper (sliding-window or linear)
  mechanism with a small fixed state.
- **CORRECTION, same day, per rule 6 — the first version of this entry
  had the sign of the error backwards, and Ish caught it.** That version
  said the model costs 131,072 bytes/token, "2.29x the retired 7B,"
  treating the ~4x hybrid discount as an unverified possibility. It was
  produced by applying a conventional all-layers-attend formula to a
  model that is not conventional, reasoning partly from the older
  Qwen3-4B's behavior on the strength of a similar name. **The GGUF
  settles it directly**: `full_attention_interval = 4` over
  `block_count = 32` gives **8 full-attention layers**, and the `ssm.*`
  metadata block (`ssm.state_size = 128`, `ssm.inner_size = 4096`,
  `ssm.conv_kernel = 4`, `ssm.group_count = 16`,
  `ssm.time_step_rank = 32`) shows the other **24 layers are SSM/linear**,
  holding a fixed recurrent state that does not grow with context. The
  real growing-KV figure is `2 x 2 x 8 x 4 x 256` = **32,768 bytes/token
  — 0.571x the 7B, not 2.29x.**
  **The first inspection missed the `ssm.*` block entirely** because it
  filtered the GGUF's metadata against a list of expected field names
  instead of dumping the full key set. That is the specific mechanism
  behind the wrong conclusion, and why `CODEY_MASTER_PLAN.md` §2 now
  carries **rule 14** (never assume; dump the whole key set before
  narrowing; a model-family name is not evidence).
- **Impact, corrected:** the finding itself stands — `ModelArch` still
  cannot express a hybrid model, so the gate computes the KV term from 32
  layers and **over-estimates by ~4x**. The error direction is the safe
  one (over-estimate → refuse, never over-admit), so this is **not an
  admission-safety bug**. What it costs is context: at the over-estimate
  the gate refuses `n_ctx=65536`, which the corrected arithmetic shows is
  comfortably affordable (4.852GiB total against a ~6.49GiB ceiling).
  Left unfixed it silently caps the device below what it can carry.
- **Fix direction:** master plan M1-A — either add a hybrid field to
  `ModelArch` (e.g. `n_attention_layers = block_count /
  full_attention_interval`), or pass `n_layers=8` with a comment stating
  exactly why that number disagrees with the model's real layer count so
  the next reader does not "correct" it back to 32. Either way the
  constant must record that this is a hybrid Transformer-SSM model and
  name the GGUF fields it came from. M1-E then confirms against real
  resident cost — including the SSM-state figure. **Corrected 2026-08-22
  in M1-A's review:** that figure is 52,690,944 bytes (50.25MiB), read
  from llama.cpp's own allocator, not the ~25MiB this entry first
  carried; the original formula dropped `ssm.group_count` and assumed
  fp16 where the allocator uses F32. Source-derived is still not
  measured — M1-E's task stands.
- **Addressed 2026-08-22 by M1-A (code-complete; first review returned
  REJECT on the SSM constant above, corrected, re-review pending; no
  live component). Not closed until that re-review approves.**
- **Status: CLOSED, 2026-08-23 — resolved with real measurement, M1-E.**
  Three independent live spawns of the real model at `n_ctx=65536`
  clustered 2-10% above M1-A's point estimate of 5,209,547,936 bytes
  (4.8518GiB): real RSS readings were 5.19GiB, 5.1645GiB, 5.3431GiB, and
  4.9476GiB. All four are comfortably inside the ×1.25 headroom factor
  (6.065GiB required vs. ~4.95-5.34GiB actual peak) — this is a legitimate
  future refinement of the flat overhead constant if ever wanted, not an
  admission-safety problem. The hybrid-arch fix itself (8 attention layers
  vs. the pre-fix all-32-attend formula) is confirmed directionally and
  quantitatively correct by this measurement — nowhere near the ~4x error
  the old formula would have produced.

### [NEW-158] `core/loader_v2.py`'s spawn command never passes `--jinja`, so the GGUF chat template — and therefore Qwen3.5-4B's `enable_thinking` switch — is inert

- **Status:** Confirmed by direct read of `_spawn_locked()`'s command
  list (`core/loader_v2.py:331-378`) and of the model's own chat template
  (7,816 chars, read from the GGUF header, no model load).
- **Mechanism:** the spawn command passes `-m`, `--host`, `--port`, `-c`,
  `-t`, sampling flags, `--flash-attn`, `--embedding`, `--pooling`,
  `--reverse-prompt` stops, and `--mmap`/`--mlock` — but not `--jinja`.
  Without it, `llama-server` does not apply the model's own Jinja chat
  template, and `chat_template_kwargs` (the mechanism that sets
  `enable_thinking`) has nothing to act on. Qwen3.5-4B's template gates
  reasoning entirely on that variable: true → emit `<think>\n`;
  otherwise → emit an empty `<think>\n\n</think>` block, forcing
  non-thinking mode.
- **Impact:** the plan to replace the dedicated planner model with the
  same model in thinking mode (master plan §1.4) cannot work at all until
  this flag is passed. It is a one-line prerequisite for an
  architecture-level decision, which is why it is logged rather than left
  as an implementation detail. Note also that adding `--jinja` changes
  prompt formatting for the EXISTING coding path too (the server would
  begin using the model's own template instead of its built-in guess) —
  that is a real behavior change requiring its own verification, not a
  free addition.
- **Related, same round:** the installed `llama-server`
  (`~/llama.cpp/build/bin/llama-server`, 2026-08-11 build) does carry the
  `qwen35` architecture string plus `--jinja`, `--reasoning-format`,
  `chat_template_kwargs`, `enable_thinking`, and `reasoning_content` —
  verified via `strings`. That is evidence the build supports them, NOT
  proof the architecture runs correctly; an actual load remains
  unverified.
- **Fix direction:** master plan M1-C. Add `--jinja` and
  `--reasoning-format`, verify the thinking switch genuinely changes
  output, and re-verify the non-thinking coding path against the template
  change before trusting it.
- **Not fixed this round.**
- **Status: CLOSED, 2026-08-23 — resolved live, M1-E.** A real
  thinking-mode request against the live server confirmed
  `--reasoning-format deepseek` genuinely splits `message.content` from
  `message.reasoning_content` in the actual HTTP response — not a no-op.
  `parse_steps()` correctly reads `.content` only. The thinking switch is
  live and functioning as designed.


### [NEW-159] Disposition note, 2026-08-22: five open findings are PENDING CLOSURE on the one-model decision, but none are closed yet — and `NEW-142` must not be closed this way at all

Recorded as its own ledger entry (not just in `CODEY_MASTER_PLAN.md`)
because rule 8 makes this file authoritative for a finding's status, and
a plan that says "pending verification" while the ledger says nothing is
how a finding gets silently dropped.

Ish's 2026-08-22 decision (master plan §1.4) retires the
Qwen2.5-Coder-7B primary and the Qwen2.5-Coder-1.5B planner in favour of
a single Qwen3.5-4B. Several open findings describe a configuration that
will no longer exist:

- **`NEW-137`** (production `n_ctx=32768` never reached the swap-assist
  band) — specific to the 7B's cost at 32768.
- **`NEW-140` scenario 3** (low-swap-headroom single-model case) — the
  scenario was defined against the retired model's footprint. **CLOSED
  2026-08-25 — see `NEW-140`'s own entry for the confirmation.**
- **`NEW-141`** (concurrent primary+planner at 32768 reproduces
  `NEW-14`'s swap distress) — requires a model pair. **CLOSED 2026-08-25 —
  see `NEW-141`'s own entry for the confirmation.**
- **`NEW-143`** (the 7B's cost estimate sits ~137MiB under the
  hard-reject ceiling) — specific to the 7B.

**Status of those four: pending closure, NOT closed.** They close only
when master plan M1-D's code read confirms the retired paths are actually
gone rather than dormant, and M1-E's live numbers replace the arithmetic
they were built on. Do not tick them off from the decision alone.

**Update, 2026-08-23 — half of that bar cleared.** M1-D's code read is
done (code-complete, code-reviewer-approved, not yet committed):
`core/planner_loader.py` deleted in full, `_evict_planner_and_confirm_
free()` deleted, `codeydOS`'s `start_plannd()`/`stop_plannd()` and the
port-8081 `pkill` sites all confirmed gone. **All four move to
code-read confirmed, pending M1-E — still NOT closed.** M1-E's live
numbers are the other half of this bar and have not run.

**`NEW-142` is explicitly excluded from the above, and it CLOSED,
2026-08-23, on exactly the code read this note specified.** Its
mechanism was `core/planner_loader.py:ensure_planner()` evicting the
primary while bypassing the gate's `reserve_slot()` path — an
eviction-bypass code path, not a property of which two models happen to
be involved. It is what made `NEW-141` reproducible at all. M1-D deleted
`core/planner_loader.py` in full and deleted `core/loader_v2.py`'s
`_evict_planner_and_confirm_free()` — the exact candidate this note
named to check. **Confirmed gone. Closed on a code read, not on the
decision, per this note's own instruction.**

Cross-references: `NEW-156` (constants derived from the retired models),
`NEW-157` (hybrid attention vs. the gate's cost formula), `NEW-158`
(`--jinja` missing, thinking mode inert).


### [NEW-160] Qwen3.5-4B's GGUF chat template opens with vision/multimodal namespaces (`image_count`/`video_count`) and `general.tags` carries `image-text-to-text`, yet the file has no `qwen35.vision.*` keys and no mmproj beside it — `--jinja` (M1-C) switches the server onto that template including those branches

- **Status:** **Confirmed** for the artifact facts; **Suspected** for the
  behavioral consequence. Found 2026-08-22 while doing the full 46-key
  GGUF metadata dump for M1-A scoping (desk-only, header read, no model
  loaded). Out of scope for M1-A, which touches
  `core/resource_gate.py`'s cost model only.
- **Confirmed (read directly from
  `~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf`):** the
  `tokenizer.chat_template` value is 7,816 characters and its opening
  section sets up `image_count` / `video_count` namespaces; the
  `general.tags` field carries `image-text-to-text`. At the same time,
  the full key dump contains **no** `qwen35.vision.*` block, and there is
  no mmproj/projector file alongside the GGUF in that directory. The
  text-only GGUF is internally consistent and fine to run as-is — the
  vision branches simply have no image content to act on.
- **Suspected (not tested):** M1-C adds `--jinja`, which is precisely the
  flag that makes `llama-server` stop using its built-in template guess
  and start executing *this* template — vision namespace setup included.
  Whether those branches are inert no-ops for a pure-text request, or
  whether they alter the rendered prompt (extra tokens, changed role
  framing, a different content-part shape) is **unverified**. It is
  plausible they are harmless; that is a hypothesis, not a finding.
- **Impact:** this compounds `NEW-158`'s already-noted caveat that
  `--jinja` changes prompt formatting for the existing coding path.
  `NEW-158` frames that as "the model's own template instead of the
  built-in guess"; this entry names the specific part of that template
  most likely to behave unexpectedly under a text-only build.
- **Fix direction:** none needed yet. M1-C must **verify, not assume** —
  capture the server's rendered prompt (or an A/B of identical requests
  with and without `--jinja`) before trusting the coding path across the
  flag change. Rule 14 applies directly: the template is the artifact,
  and it has already been read; what has not been read is what
  `llama-server` does with it.
- **Not fixed this round** — logged during M1-A scoping, belongs to M1-C.
- **Status: CLOSED, 2026-08-23 — resolved live, M1-E.** The actual
  7,816-char `tokenizer.chat_template` was extracted from the live GGUF
  and rendered with real jinja2 against a plain-text message with both
  `enable_thinking=False` and `enable_thinking=True` — no
  vision-namespace tokens (`image_count`/`video_count`) leaked into
  rendered output for either case. A real coding-path inference request
  in the same session independently confirmed clean output with no
  role-framing corruption. The vision branches are confirmed inert for
  text-only requests.


### [NEW-161] Interim state after M1-A alone: `model_id="primary"` resolves to Qwen3.5-4B's hybrid arch while `MODEL_PATH` still points at the Qwen2.5-Coder-7B file, so the gate under-estimates a 7B load's KV cache by 768MiB — in the unsafe direction

- **Status:** **Confirmed** — arithmetic against the committed code, no
  model loaded. Found 2026-08-22 by `code-reviewer` (W-2) during M1-A's
  review. Closed by M1-B; recorded because it is a real property of the
  state M1-A commits, not a hypothetical.
- **Mechanism:** M1-A repoints `KNOWN_MODEL_ARCHS["primary"]` at
  `QWEN35_4B_ARCH` (8 attention layers, 4 KV heads, head_dim 256).
  M1-A deliberately does **not** touch `utils/config.py` — that is M1-B —
  so `cfg.MODEL_PATH` still names
  `~/models/qwen2.5-coder-7b/...`, and `estimate_model_load_cost()` stats
  that file for `model_bytes` while costing its KV with the *4B's* arch.
- **The number:** at `n_ctx=32768` the gate computes `8 * 2 * 4 * 256 *
  32768 * 2` = **1,073,741,824** bytes of KV, where the real 7B needs
  `28 * 2 * 4 * 128 * 32768 * 2` = **1,879,048,192**. An
  **805,306,368-byte (768MiB) under-estimate**, ~1.0GiB once the ×1.25
  headroom factor is applied. Under-estimating is the `NEW-21`/`NEW-84`
  direction — it can admit a load that should have been refused.
- **Why it is accepted rather than fixed here:** the A-before-B order is
  deliberate. Doing B first would leave the gate costing the 4B file with
  the 7B's 28-layer arch — a ~4x *over*-estimate that would refuse the
  `n_ctx=65536` Ish chose (§8 Q1). One of the two orders has to carry a
  transient mismatch, and A-first carries it in a window that `§6.2`
  fences with "do this before anything loads."
- **What keeps it honest:** M1-B closes it by pointing every model slot
  at the Qwen3.5-4B file. Until then, treat any gate admission decision
  involving `model_id="primary"` as unsound. M1 chains can stall
  mid-sequence when a review rejects — if M1-B is not landing
  immediately after M1-A, this is the finding that says why that matters.
- **Not fixed this round** — closes with M1-B.
- **Status: CLOSED, 2026-08-23.** M1-B landed (code-complete,
  code-reviewer-approved, not yet committed): `utils/config.py`'s
  `MODEL_PATH` and `PLANNER_MODEL_PATH` both now point at
  `~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf`. The mismatch this
  finding described (primary costed with the 4B's arch while
  `MODEL_PATH` still named the 7B) no longer exists — confirmed by
  reading the committed `utils/config.py`.


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
- **Reconfirmed, 2026-08-09** (`TODO.md` 7.4 sub-task 5 round; originally
  logged separately as a duplicate, `NEW-93`, before being merged in
  here): same 3 tests, same failure mode, hit again by an unrelated
  uncommitted `main.py` diff during that round's full-suite run.
  Independently traced to the same call chain, named more precisely this
  time: `core/agent.py`'s `check_git_and_offer_commit()` (called after
  any turn using `patch_file`/`write_file`) shells out to
  `core/githelper.py`'s `git_status_paths()`, and if that's non-empty,
  calls `utils.logger.confirm()` — same real-stdin-read-under-pytest-
  capture crash. Re-reproduced via the same `git stash`/pop method
  (3/5 failing with the diff present, 5/5 clean with it stashed). Still
  not fixed — this is now the second round to hit it; worth prioritizing
  the actual fix (mock `check_git_and_offer_commit()`/its dependencies in
  those 3 tests) rather than re-discovering and re-reproducing it a third
  time.
- **Third occurrence, 2026-08-10, logged separately as `NEW-110`**
  (code-reviewer, Phase 4.1 sub-task A review) — same 3 tests, same
  `check_git_and_offer_commit()`/`git_status_paths()`/`confirm()` call
  chain, same dirty-working-tree trigger. Cross-referenced here
  (2026-08-11, project-architect consolidation pass) rather than merged,
  since `NEW-110` already exists as its own entry — but both describe the
  identical bug and should be closed together by one fix in
  `tests/test_new19_patch_failed_repeat_escalation.py`. No currently
  open/upcoming `TODO.md` item's stated scope covers fixing this test
  file's existing fragility (`U.20`/`U.21` cover unused imports/lint and
  *missing* test coverage respectively, not repairing an existing
  flaky/hanging test) — stays open and unattached to any TODO item pending
  a dedicated pickup.

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
- **Correction, 2026-08-25 (rule 6):** this entry and several neighbors
  (`NEW-46`/`NEW-47`/`NEW-51`) describe the 4-iteration `PLANNER_PROMPT`
  rewrite as "uncommitted, commit decision pending with Ish." That is
  now stale — `git log --oneline -- core/plannd.py` shows the rewrite
  landed as `d674a0c` ("Fix planner prompt: NEW-46/NEW-28/NEW-47 fixed,
  live-verified on 1.5B") at some point after this round, and the
  fibonacci example this entry traces as the leak source is still
  present, unchanged, in the current HEAD (`edc9e36`) — confirmed via
  direct read of `core/plannd.py:137-149`, not assumed. `NEW-50` itself
  is neither confirmed nor refuted against the new Qwen3.5-4B thinking-
  mode model — it was found on the retired 1.5B planner and has not been
  re-tested since the migration. See `CODEY_MASTER_PLAN.md` Appendix A's
  `M1-G` entry for the pre-registered re-test plan (not yet run).

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

### [NEW-57] second correction, 2026-07-31 — the "two-store" downgrade above was itself wrong; UPGRADED back to Confirmed
A desk investigation into a separate question (why a live-test control
case behaved unexpectedly) re-traced this exact code path and found the
prior correction's central claim is false: `core.context` is **not** a
separate store from `core.memory_v2`. `core/context.py:11` reads
`from core.memory_v2 import memory as _mem` — the identical module-level
singleton (`core/memory_v2.py:713-728`: `_memory` is a single global,
`get_memory()` returns it idempotently, `memory = get_memory()` binds it
once at import time). `core/context.py:175-176`'s
`build_file_context_block()` is a one-line passthrough to
`_mem.build_file_block(message)` on that same singleton — which is
exactly what `prompts/layered_prompt.py`'s `_get_file_block()` calls to
build the "files" priority-4 layer. So `core/agent.py:1699-1706`'s
`write_file`/`patch_file` branch, which already calls
`_mem.load_file(fpath, _wcontent)` on this same singleton, **does**
populate the layered-prompt "Loaded Files" block — the original
asymmetry framing was correct all along. `read_file` (`agent.py:1715-1721`)
is the only branch that doesn't register its content into this store.
**Status: Confirmed** (verified by direct code read of the singleton
wiring, not inference). A fix (mirror `write_file`/`patch_file`'s
`_mem.load_file()`/`_mem.touch_file()` calls into the `read_file` branch)
is in progress this round — see `WORK_QUEUE.md`. The cost note above
(recurring prompt-budget cost, `_files_hash()` cache-invalidation
participation) still applies and was factored into the fix's scope. The
open question of whether this gap specifically caused `NEW-56`'s observed
bad `write_file` calls remains unestablished — this correction confirms
the architectural gap exists, not that it's NEW-56's root cause.

### [NEW-62] `detect_filenames()`'s regex drops the leading dot on dot-prefixed path segments, silently failing the existence check (Confirmed by manual trace, fix in progress)
`core/context.py`'s `detect_filenames()` pattern
(`r"(?:\.{0,2}/)?[\w\-/]+\.(?:py|js|ts|...)"`) matches a path like
`.live_verify_scratch/case1_anchor.py` WITHOUT its leading dot — the
character class `[\w\-/]` excludes `.`, and the optional
`(?:\.{0,2}/)?` prefix only absorbs a dot immediately followed by `/` at
the very start of the match, not a dot inside a path segment.
`re.findall()` returns `"live_verify_scratch/case1_anchor.py"` (dot
silently dropped), which then fails `Path(m).exists()` even when the
real file exists at the dotted path — so `auto_load_from_prompt()`
(`core/context.py:220`) never preloads such files, silently. Found
incidentally during the `NEW-30` third live pass: the test's own
`.live_verify_scratch/` scratch directory (created to fix `NEW-60`'s
workspace-boundary bug) happened to dodge auto-load entirely because of
this bug, not by test design — meaning that pass's "genuinely unread
file" framing held only by accident. Fix in progress this round — see
`WORK_QUEUE.md`.

### [NEW-63] `detect_filenames()`'s fixed regex still drops the path prefix before a directory segment with an embedded (non-leading) dot, e.g. `com.termux` — Confirmed by direct regex test, found while live-verifying the NEW-62 fix
While live-verifying the NEW-62 fix (leading-dot path segments,
e.g. `.config/settings.json`), tested the new pattern against this
device's own actual absolute repo path,
`/data/data/com.termux/files/home/Codey-OS/core/agent.py`. Both the old
pattern and the NEW-62-fixed pattern truncate the match to
`.termux/files/home/Codey-OS/core/agent.py` (or `termux/...` for the old
pattern) — losing the `/data/data/com` prefix entirely, because
`com.termux` is a single path segment with a dot in the middle
(not at the start), and neither `[\w\-/]` (old char class) nor
`(?:\.?[\w\-]+/)*` (NEW-62's per-segment leading-dot allowance) can
consume a mid-segment dot — the task's own NEW-62 fix instructions
explicitly excluded that, to avoid the regex swallowing sentence
punctuation (e.g. "...section 2. Then edit main.py"), and that
exclusion is the right call in general. This is not a regression
from the NEW-62 fix — verified the pre-existing (old) pattern fails
identically on this exact path, just truncating to a different (also
wrong) substring. Confirmed via direct `re.findall()` comparison:
- old pattern on `/data/data/com.termux/files/home/Codey-OS/core/agent.py`
  gives `['termux/files/home/Codey-OS/core/agent.py']`
- NEW-62-fixed pattern on the same string
  gives `['.termux/files/home/Codey-OS/core/agent.py']`
- both fail `Path(m).exists()` and the `os.getcwd()`-join fallback, so
  `detect_filenames()` silently fails to recognize this device's own
  absolute repo path whenever a mid-segment dot like `com.termux`
  appears before the target file. Confirmed against a clean absolute
  path without an embedded-dot segment (e.g.
  `/home/user/project/core/agent.py`) which both old and new patterns
  match correctly in full — so the failure is specifically tied to
  mid-segment dots like Android's `com.termux`, not absolute paths in
  general. Left unfixed and out of scope for the NEW-62 round per the
  task's explicit instruction not to open dots up anywhere inside the
  character class. A real fix would need a different strategy entirely
  (e.g. a broader "looks like an absolute/relative path with no spaces"
  heuristic, or checking `Path(m).exists()` against progressively
  shorter/longer candidate substrings) — scope for a future round.

### [NEW-64] `read_file`'s new working-memory registration (this round's fix) has no size cap, unlike the write_file/patch_file registration it mirrors (Suspected, flagged by code-reviewer, non-blocking)
Fix for the `read_file`/working-memory asymmetry (see `NEW-57`'s
correction above) registers `last_tool_result` — the full file content
returned by `tool_read_file()` → `Filesystem.read()`, capped at 10MB —
into `core.memory_v2`'s `WorkingMemory` on every successful read,
unconditionally. The `write_file`/`patch_file` branch it mirrors only
ever registers small, model-generated content (`args["content"]`/
`args["new_str"]`), so this is a new, much larger worst-case input to the
same code path (~1000x larger than anything previously stored there).
`WorkingMemory._evict_by_tokens()` skips files touched this turn and
`break`s early once under budget, so one large read can push total
tokens over `MAX_FILE_CONTEXT_TOKENS` (12,000) while evicting *other,
more-useful* resident files, and — unlike a transient read — this
content now persists across up to `LRU_EVICT_AFTER` (3) further steps.
Code-reviewer flagged this as non-blocking for the `NEW-57`/read-registration
fix itself (approved to land as-is) but recommends a size cap on
`read_file`'s registration as a follow-up. Not yet scoped to an
implementer.

### [NEW-65] `LlamaServer.start()`'s 7B-only mmap/mlock flags (`QWEN_7B_MMAP`/`QWEN_7B_MLOCK`) are applied unconditionally to every `LlamaServer` instance, including the new planner (1.5B) launcher (Confirmed, found while implementing NEW-12's remaining items)
`core/loader_v2.py:LlamaServer.start()` (the try/except around
`QWEN_7B_MMAP`/`QWEN_7B_MLOCK` import and the `--mmap`/`--no-mmap`/`--mlock`
flag-building block) is not gated on which model is being started — it runs
for every `LlamaServer(...)` instance regardless of `model_path`/`port`,
despite `utils/config.py`'s own comment on those two settings stating
"These settings apply ONLY to the Qwen 7B model." Same class of issue for
`MODEL_CONFIG` generally: `n_ctx` (32768), `n_threads`, `temperature`,
`top_p`, `top_k`, `repeat_penalty`, `--n-predict` are all a single global
dict sized for the 7B model, and `LlamaServer.start()`'s command-building
has no per-model override — the new planner launcher (`core/planner_loader.py`,
this round's NEW-12 fix) inherits all of these as-is. In practice this is
likely benign for the planner today (mmap-on/mlock-off are sane defaults
for any model; `core/plannd.py:get_plan()`'s per-request payload already
overrides `temperature`/`max_tokens` for actual generation, so the
server-level defaults mostly only matter as a fallback), but it is a real
naming/scoping mismatch between the code and its own comments, not
verified harmless in all cases (e.g. `n_ctx: 32768` reserves more KV-cache
RAM for the 1.5B planner than a value sized for it would). Not fixed here —
out of NEW-12's explicit scope (task said not to change `MODEL_CONFIG`/
model generation parameters for either model). Fix direction for a future
round: either parameterize `LlamaServer` by a per-model config dict, or
gate the mmap/mlock block on `self.port == PRIMARY_SERVER_PORT` (or
equivalent) so it stops silently applying to non-7B instances.
- **Code-reviewer note (2026-07-31):** the `--mmap`/`--mlock` half of this
  is reasonably out-of-scope as filed, but `n_ctx: 32768` reserving 7B-sized
  KV-cache RAM for the 1.5B planner is a real RAM claim on a device with a
  documented OOM history — exactly what NEW-12's sequential-swap
  requirement exists to protect. Needs `free -h` + actual planner RSS
  recorded at live-verify time, not accepted as "likely benign" without
  measurement.

### [NEW-66] `core/daemon.py`'s 30s watchdog tick unconditionally calls `ModelLoader.ensure_model()` for the primary 7B model, which (after NEW-12's sequential-swap fix) will now evict a planner load that is genuinely still resident and in active use — not just an in-flight-swap race (Suspected, reasoned from code read, not live-reproduced)
`core/daemon.py:549-564`'s watchdog block runs every ~30s and always calls
`get_loader().ensure_model()` for the primary model when not running
remote, regardless of whether the planner (1.5B) is the model currently
intended to be loaded. This round's NEW-12 sequential-swap fix
(`core/loader_v2.py`'s `SWAP_GUARD`, `ensure_model()`/
`PlannerLoader.ensure_planner()`) only protects the narrow in-flight-swap
race (the watchdog firing *during* `get_plan()`'s own swap, via the
non-blocking `SWAP_GUARD`) — deliberately in scope for NEW-12, since it's
mutual exclusion, not resource-gating. It does NOT stop the watchdog from
evicting the planner on its very next tick (≤30s) once a `get_plan()` call
has *finished* and released `SWAP_GUARD`, even if the planner is still the
"correct" model to have loaded (e.g. multiple planning calls in quick
succession, or a slow single planning call whose own HTTP round-trip
outlives 30s). This is by design for NEW-12's stated sequential-swap
contract — "swap, don't add concurrency-awareness" — and the watchdog
reloading the primary shortly after planning finishes is the intended
self-healing restore path, not a bug in the swap logic itself. But it
means: (a) back-to-back planning calls within a ~30s window may each pay a
fresh 7B-unload + 1.5B-cold-start cost if the watchdog reclaims the
primary in between, and (b) RAM churn from repeated 7B/1.5B load/unload
cycles on a device that has OOM-crashed before is a real cost even though
each individual swap is now race-free. Not fixed here — resolving it
would mean either making the watchdog aware of "planner intentionally
loaded, don't evict yet" (a form of the resource/intent-awareness NEW-12
explicitly deferred to Track 3 Phase 5a) or debouncing the watchdog's
primary-reload after a planning call, both out of NEW-12's scope. Flagged
for a future round; live-verification of NEW-12's swap should specifically
check whether this watchdog interaction is observed as thrashing, not
just whether a single swap cycle is race-free.

### [NEW-68] `ModelLoader.ensure_model()`'s non-blocking `SWAP_GUARD` acquisition means any caller can now get a transient `False`/failure during the narrow window a planner swap is in flight, not just the daemon watchdog (Confirmed by code read, not live-reproduced)
`ensure_model()` (`core/loader_v2.py`) is called from more places than the
daemon watchdog this round's NEW-12 fix was primarily reasoned about:
`core/daemon.py:512` (pre-load at daemon startup — already handles `False`
gracefully, logs a warning and lazy-loads on first request) and, more
significantly, `core/inference.py:_start_server()` (line 40), which is the
legacy-HTTP fallback path `core/inference_v2.py:_infer_http()` calls when
the hybrid chat-completions backend is unavailable — this is the exact
fallback path NEW-12's original Round 11 fix routed through
`get_loader().ensure_model()` instead of an independent launcher. That
function currently does `if not get_loader().ensure_model(): raise
RuntimeError(...)` with no retry — previously this would only return
`False` on genuine load failure (missing model file, binary, or spawn
timeout); after this round's sequential-swap fix, it can also return
`False` transiently whenever `SWAP_GUARD` is held by an in-flight
`get_plan()` planner-load in the same process (bounded by
`LlamaServer.start()`'s own timeouts — lock-contention poll + spawn
health-wait, up to ~60s each). Traced the propagation: the `RuntimeError`
is not caught in `core/inference.py`/`core/inference_v2.py`, but IS caught
generically by `core/task_executor.py:_execute_task()`'s `except Exception`
(re-raised) and then by `core/daemon.py`'s task-dispatch `except Exception`
(`~line 654`/`~680`), which marks the task `failed` with the error message
rather than crashing the daemon — so this is NOT a daemon-crash risk, only
a possible extra task failure in the rare case a planning request and a
7B-inference request needing a fresh (not-already-running) primary load
race within the same narrow window. Not fixed here — the non-blocking
design is required for `core/daemon.py:562`'s watchdog call (which runs
directly on the event loop; blocking there would stall the whole daemon),
so a caller-specific retry/backoff would need to distinguish call contexts,
which edges toward the concurrency-awareness work this round's task
explicitly deferred to Track 3 Phase 5a. Flagged for a future round to
decide whether `core/inference.py:_start_server()` specifically should
retry a bounded few times before raising, given it runs off the event loop
(inside `run_in_executor`) and can afford a short bounded wait that the
watchdog cannot.

**Severity correction, 2026-07-31 (code-reviewer, rule 6):** the ~180s
worst-case timing this entry's neighboring `NEW-12` writeup used
(lock-contention poll ≤60s + cold-start health-wait ≤60s + HTTP timeout
≤60s) undercounts real worst case — it omits `LlamaServer.stop()`'s
`wait(timeout=8)`+SIGKILL path, `probe_port_health`'s 2s timeout, and
`_is_port_in_use()`'s socket+HTTP checks (run twice on the
lock-contention branch). Real worst case is ~190s+, which **exceeds**
`core/daemon.py:164`'s `asyncio.wait_for(get_plan..., timeout=180.0)`.
This means a cold planner swap under lock contention is a **plausible,
not rare**, way to blow the daemon's own plan-request timeout — and when
it does, the orphaned executor thread can still be holding `SWAP_GUARD`
after the daemon has already given up and fallen back to unplanned
execution, so the fallback's own `ensure_model()` call (via
`core/inference.py:_start_server()`, this entry's own traced mechanism)
can also transiently fail. Do not read this finding as "rare race" —
read it as a real, currently-reachable timeout-budget mismatch. Not
fixed here; needs either a shorter internal timeout budget on the
lock/swap path or a longer `asyncio.wait_for` on the daemon side,
decided together, not independently.

**Fix-up round impact, 2026-07-31 (implementer):** fixing Bug 1 of the
code-reviewer's rejection (thermal-restart branch bypassing
`SWAP_GUARD`) required widening `SWAP_GUARD` to cover `ensure_model()`'s
*entire* body, not just the cold-load branch — so `ensure_model()` now
always acquires the guard first, even when the primary is already loaded
and healthy with no thermal restart pending. Previously that case never
touched `SWAP_GUARD` at all and could not fail from contention. Now it
can: a concurrent `ensure_planner()` swap holding the guard can make
`ensure_model()` return `False` purely from timing, even though the
primary was already fine. Traced the consumer: `core/inference.py:
_start_server()`'s `if not get_loader().ensure_model(): raise
RuntimeError(...)` (no retry) turns this into a task failure. **This is
worse-but-bounded, not a new unbounded risk** — same class of failure
this entry already describes, same ~60-190s timeout bound, just now also
reachable from a case that used to be immune. No fix required beyond
what this entry already recommends (a future round deciding on retry/
backoff, or the timeout-budget reconciliation the severity correction
above calls for).

### [NEW-70] `ModelLoader.ensure_model()`'s thermal-restart branch swallows any exception from `unload()`/`load_primary()` and unconditionally reports success anyway (Suspected, found during NEW-12's fix-up round, pre-existing before this round's changes)
In `ensure_model()`'s "already loaded" fast path, the thermal-restart
check is `try: ... tm.restart_recommended ... except Exception: pass`
immediately followed by `return True` — if `self.unload()` or the
subsequent `self.load_primary()` raises partway through a thermal
restart, the exception is silently swallowed and the method still
reports the model as loaded/healthy, even though the restart may have
left no server running at all. Found by the implementer while fixing
NEW-12's Bug 1 (restructuring this same branch to close the `SWAP_GUARD`
gap) — pre-existing before this round, not introduced by it. Not fixed
here, out of the 3-bug rejection's scope. Flagged for a future round:
the `except Exception: pass` should at minimum distinguish "thermal
check itself failed" (fine to fail open, matches the existing comment's
intent) from "the restart's own unload/reload failed" (should not report
success).

### [NEW-69] Interactive-CLI direct model loads (`main.py`) bypass the NEW-12 sequential-swap arbiter entirely — the primary and planner can end up resident together via this path, and a naive fix would break normal CLI usage (Confirmed by code read, needs a project-architect scoping decision, not a quick patch)
`main.py:1271/1552/1564/1589` call `core.loader_v2`'s `load_primary()`
directly, never `ensure_model()` — so none of `NEW-12`'s new
`_evict_planner_and_confirm_free()` eviction logic runs on this path.
`codeyOS:370-371`'s own comment confirms this is a real, designed-for
scenario, not a rare edge case: "All other prompts always run
interactively via direct Python (even when the daemon is running)." So a
user with the daemon running (planner possibly loaded from a recent
`core/plannd.py:get_plan()` call) launching an interactive `codeyOS`
prompt can spawn the 7B directly on top of it — violating the hard
"never both resident" requirement `NEW-12`'s swap logic exists to
enforce, just from an untouched call site.
- **Do NOT fix by routing these calls through `ensure_model()`.** In a
  fresh CLI process, `core.planner_loader.get_planner_loader()` is a
  brand-new singleton with `is_loaded() == False` (it has no memory of
  what the separate daemon process has loaded), so `ensure_model()`'s
  eviction step would see "nothing to evict" and fall through to
  `probe_port_health(PLANND_SERVER_PORT)` alone deciding the outcome —
  and since CLAUDE.md rule 3 forbids killing a process this loader
  didn't spawn, it cannot evict the daemon's planner even if it detects
  it. Net effect of the naive fix: the CLI would fail-closed and refuse
  to load the 7B at all whenever the daemon happens to have a planner up
  — a real regression to ordinary interactive use, not a fix.
- **This needs a real cross-process signal or arbitration mechanism**
  (the daemon evicting its own planner on request, a shared lock file
  richer than a simple flock, or similar) to resolve correctly — which
  is architecturally adjacent to Track 3 Phase 5a's planned
  resource-gate authority, not a quick patch to `main.py`. Flagged for
  Ish/project-architect to decide: accept this as a known residual risk
  for now (interactive CLI use during an active daemon session already
  carried some risk before this round; this doesn't make an
  already-safe path newly unsafe, it just means the new swap guarantee
  has a real gap), or prioritize a cross-process fix ahead of Phase 5a.
- **Not fixed here.** Logged per CLAUDE.md rule 8, found by code-reviewer
  during `NEW-12`'s review pass, not introduced by this round (the
  underlying direct-`load_primary()`-call pattern in `main.py` predates
  `NEW-12`'s work — this round's swap logic just makes the gap concrete
  and newly relevant).

### [NEW-67] `codey-stop` has its own third, independent block that reads/writes `$DAEMON_DIR/gui-server.pid` — adjacent to the NEW-22 start-side duplication just fixed, but a different (stop-by-PID-file) pattern, not touched this round (Suspected, out of this round's scope)
- Found while fixing NEW-22's residual "GUI-launch/PID-file/trap-kill"
  duplication in `codey-start` and `codeyOS` (2026-07-31), which was
  extracted into `lib/gui_launch.sh`. `codey-stop:20-33` independently
  reads `$DAEMON_DIR/gui-server.pid`, checks liveness with `kill -0`,
  sends `SIGTERM` then `SIGKILL` after a 0.5s grace period, and removes
  the PID file — plus a `pkill -9 -f "gui/server.py"` safety sweep for
  any untracked process. This is a genuinely different pattern from the
  *start*+trap logic just deduplicated (it's a *stop* path, invoked by a
  completely separate script, not something a caller `source`s alongside
  `gui_launch_ensure_running`), so it was explicitly left alone — the
  NEW-22 task instructions named only `codey-start` and `codeyOS`'s
  start-side blocks in scope, and this task's "what NOT to do" said not
  to touch `codeydOS`'s or the daemon's own separate PID-file logic;
  `codey-stop`'s block, while not literally `codeydOS`, is the same kind
  of separate-script PID-file logic and extending scope to it without
  being asked risked exactly the kind of unscoped change CLAUDE.md rule
  8 says to log instead of silently act on.
  - **Why "Suspected" not "Confirmed" as an actual problem:** the
    stop-side and start-side logic serve different purposes (kill vs.
    launch) and don't have to be literally the same code to avoid
    duplication-as-a-bug-source — three places knowing the PID-file path
    (`$DAEMON_DIR/gui-server.pid`) and format (bare PID, one line) is a
    much smaller shape of duplication than three places reimplementing
    the full launch+trap sequence was. No live symptom observed from
    this; flagging for a project-architect scoping decision on whether
    it's worth a small follow-up (e.g. a `GUI_PID_FILE` path constant
    shared via `lib/gui_launch.sh`, or leaving it as-is since it's a
    single `cat`+`kill -0`, low duplication cost) rather than assuming it
    needs the same treatment as the just-fixed start-side pattern.
  - **Also noted (code-reviewer, review pass):** `codey-stop`'s
    `pkill -9 -f "llama-server"` / `pkill -9 -f "gui/server.py"` blanket
    sweep is the exact bare-pattern-kill shape CLAUDE.md rule 3 warns
    against — pre-existing, untouched by this round, not blocking this
    review, but worth its own `NEW_ISSUES.md` entry in a future round if
    one doesn't already exist for it specifically (this entry is about
    the PID-read block, not the sweep).

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
    **Resolved-by-deletion 2026-08-08:** `QWEN.md` was merged into
    `CLAUDE.md` and `git rm`'d on Ish's explicit instruction (Qwen CLI
    sessions are no longer part of the active workflow) — the stale-tree
    problem no longer applies to a file that doesn't exist. `CLAUDE.md`'s
    new structure section is directory-level, not per-file, specifically
    to avoid recreating this same drift.
  - **Resolved 2026-08-08 (Ish's explicit decision: archive) —
    `AUDIT_REPORT.md` disposition:** read in full (351 lines). It is a
    June-13-2026 "Codey-V3" era architecture/feature-inventory +
    investor-pitch document — confirmed NOT a duplicate of
    `Codey-OS-audit.md` (a July-29 severity-rated bug audit; different
    purpose entirely). Content is stale (predates CCOS and the Codey-OS
    rename). Moved to `docs/archive/AUDIT_REPORT.md` (`git mv`) with an
    archival header added noting its historical-only status.
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
- **Status: Residual fixed, 2026-07-31, code-reviewer approved.**
  Extracted the shared "start `gui/server.py` in background, write PID
  file, trap-kill only if started here" pattern out of `codey-start`
  (was lines 55-75) and `codeyOS` (was lines 397-411) into a new sourced
  library, `lib/gui_launch.sh`, with a single function
  `gui_launch_ensure_running`. Both scripts now `source
  "$CODEY_OS_DIR/lib/gui_launch.sh"` and call the function instead of
  reimplementing the block. Verified `CODEY_OS_DIR`/`DAEMON_DIR` are
  already defined identically in both scripts before this point, *and*
  that `CODEY_OS_DIR` resolves correctly even when the scripts are
  invoked via `PATH` from an unrelated `cwd` — checked `install.sh`/
  `setup.sh`: they add the repo directory itself to `PATH`
  (`export PATH="$CODEY_OS_DIR:$PATH"`), not a symlink or copy into a
  separate bin directory, and `type codeyOS`/`type codey-start` on this
  device both resolve to the actual repo-root files — so
  `$(dirname "${BASH_SOURCE[0]}")` inside either script always lands on
  the repo root regardless of invocation `cwd`. Confirmed with a real
  `PATH`-based invocation from `/tmp` (see live-verification note below).
  - **Trap-signal convergence — converged on `EXIT` only, not
    `EXIT INT TERM`.** The two copies differed (`codey-start` trapped
    `EXIT` only; `codeyOS` trapped `EXIT INT TERM`). Grepped both files —
    neither has any other `trap` call, so this was drift, not an
    intentional per-script difference. An earlier draft of this fix
    converged on `EXIT INT TERM`, reasoning it would give more prompt
    cleanup; that reasoning was wrong on two counts, found by testing and
    by reading `main.py`, and was reverted before this fix was
    considered final (rather than left standing, per the project's
    "correct the record" rule):
    1. **No promptness benefit.** `kill -INT` sent to a real wrapper PID
       while blocked on a synchronous foreground child (tested against
       both a plain `sleep` stand-in and the real `python3 ... main.py`)
       did not run the trap until the foreground child exited on its
       own — identical to plain `EXIT`'s behavior in the same scenario.
    2. **Trapping INT is actively wrong for this codebase's real Ctrl+C
       path.** `main.py` catches `KeyboardInterrupt` in 10+ places (e.g.
       lines 527, 949, 1314, 1335, 1423) and *continues* its interactive
       loop — Ctrl+C there commonly cancels one in-flight generation, not
       the session. A real terminal Ctrl+C delivers SIGINT to the whole
       foreground process group (wrapper + `python3` child together). If
       the wrapper trapped INT, that keystroke would tear the GUI down
       immediately while `main.py` absorbs the same signal and keeps
       running — the user would lose the GUI mid-session without the
       wrapper actually exiting, and (a trap without an explicit `exit`
       does not terminate the shell — verified directly) nothing would
       re-arm it afterward. `EXIT`-only does not have this failure mode:
       it only fires when the wrapper itself is actually exiting.
       Real termination in actual usage happens via either the foreground
       child genuinely dying (child doesn't catch the signal, or normal
       completion) — `wait` returns and the wrapper's own exit runs the
       `EXIT` trap — or `codey-stop` (out of this file's scope), which
       kills the GUI server's own recorded PID directly and never signals
       the wrapper's PID at all.
  - **Live-verified, real command output (implementer + independently
    re-verified by code-reviewer):** (1) direct
    `gui_launch_ensure_running` calls under each script's exact
    preceding `CODEY_OS_DIR`/`DAEMON_DIR` setup start the GUI, write
    `$DAEMON_DIR/gui-server.pid`, and the EXIT trap kills the process and
    removes the PID file on normal exit; (2) the "already running"
    short-circuit was verified with a GUI server started independently
    of the test invocation — the second invocation printed "(already
    running)", did not start a duplicate, and on its own exit did NOT
    kill the pre-existing GUI server (the safety property this code
    exists for); (3) a real `bash codeyOS` invocation exercised the
    sourced library end-to-end, including trap cleanup on `SIGINT`, with
    no leaked `gui/server.py` process or stale PID file afterward
    (confirmed via `ps aux` / PID-file check post-exit); (4) a real
    `codeyOS` invocation via `PATH` from `/tmp` (not the repo root)
    correctly located and sourced `lib/gui_launch.sh`, started the GUI,
    and cleaned it up on interrupt with no leaked `llama-server` or
    `gui/server.py` process afterward. Did not run `codey-start`'s
    daemon-start path end-to-end (would trigger a second 7B model load
    beyond the ones already incurred verifying `codeyOS` directly — out
    of scope for this task per its own instructions, and
    avoided per CLAUDE.md rule 2's single-model-load-cycle discipline);
    equivalence of `codey-start`'s setup was instead confirmed by
    invoking the extracted function directly under `codey-start`'s exact
    `CODEY_OS_DIR`/`DAEMON_DIR` values. **Code-reviewer note:** bash's own
    "EXIT trap fires on SIGTERM" claim was independently re-tested (not
    just accepted) via a minimal `trap ... EXIT; sleep &` + `kill -TERM`
    repro, confirmed firing with no leaked process; the SIGINT case
    specifically was not independently re-tested by the reviewer (a known
    sandbox limitation — backgrounded children get `SIGINT=SIG_IGN` here,
    making `kill -INT` an unreliable signal in this environment), so that
    half of the trap-signal claim rests on the implementer's own
    `main.py`-reading-based reasoning, not a second independent live
    reproduction.
  - **Found but not fixed, logged separately:** `codey-stop` has its own
    third, related-but-not-identical block that reads/writes
    `$DAEMON_DIR/gui-server.pid` (a *stop*-by-PID-file block, not the
    *start*+trap pattern this finding was scoped to) — see NEW-67.
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

**Correction, 2026-07-31 (rule 6):** re-checked all three residual items
before scoping a fix round. **Item 2 is already done** — `utils/config.py:20`
defines `PRIMARY_SERVER_PORT`, and `loader_v2.py`, `inference.py`, and
`inference_hybrid.py` all already import and use it (confirmed via grep,
zero remaining hardcoded `8080` literals in those three files). Unclear
which prior round did this: not mentioned in any `PROJECT_LOG.md` entry
found by title/topic search, and not previously reflected here or in
`WORK_QUEUE.md` — likely landed as a side effect of other work without
being logged against this finding. **Item 3's docs/install.sh mismatch
sub-part is also already fixed** — `docs/configuration.md:155` and
`install.sh:36/41` both already state `qwen2.5-coder-1.5b`, matching
`utils/config.py:242`'s actual default; the originally-cited wrong
default no longer exists in either file. **Item 3's actual core ask (wire
`PLANNER_MODEL_PATH`/`PLANND_SERVER_PORT` into a real launcher) and item
4 (real cross-process lock) remain genuinely open** — scoped as a Track 2
task, see `WORK_QUEUE.md`.

**Fix round in progress, 2026-07-31.** Implemented a real cross-process
flock lock for the model-server port (Item 4) and a real sequential-swap
planner launcher (`core/planner_loader.py`, Item 3 — planner and primary
never resident at once, per Ish's decision). **First pass REJECTED by
code-reviewer**: 3 required bugs (thermal-restart branch bypasses
`SWAP_GUARD`; `PlannerLoader`'s eviction check isn't actually symmetric
with `ModelLoader`'s — missing exception handling; a lock-contention unit
test could spawn a real 7B model, no `Popen` mock) plus a 4th finding
logged separately and deferred (`NEW-69` — interactive-CLI direct loads
in `main.py` bypass the swap arbiter entirely; needs a real architectural
decision, not a quick patch). See `NEW-65`/`NEW-66`/`NEW-68`/`NEW-69`
above for adjacent findings surfaced along the way. **Correction (rule 6):
the fix-up round is committed as `ea14d7f` and has now been live-verified —
see the block immediately below, which supersedes the "not yet committed,
not yet live-verified" status this paragraph originally carried.**

**Live-verified, 2026-07-31 (commit `ea14d7f`).** Real, non-mocked, on-device
test — no `Popen`/`ensure_model` mocking, real 7B and real 1.5B `llama-server`
processes on this Samsung S24 Ultra device. Full protocol and verbatim output
in the live-verification session; summary below.

`free -h` before: `total 10Gi, used 4.4Gi, free 244Mi, available 6.1Gi, swap
used 1.2Gi`. `ps aux | grep llama-server` before: no server process running
(only the grep itself). After the full test sequence (all phases below plus
the cross-process contention test), `free -h`: `total 10Gi, used 3.9Gi, free
2.7Gi, available 6.7Gi, swap used 1.6Gi` and `ps aux | grep llama-server`
showed nothing but the grep — fully torn down, all three PIDs spawned during
the session (2680, 2847, 5829) tracked and killed via `.unload()`, none by
bare `pkill`.

- **Sequential swap (Item 3), single-process, real production call path:**
  `core.loader_v2.get_loader().ensure_model()` cold-loaded the primary
  (11.1s) → `core.plannd.get_plan(...)` (the real daemon call path, not a
  direct `ensure_planner()` call) evicted the primary, cold-loaded the
  planner, and returned a real plan (`['Create add.py: accepts two
  arguments, adds them, and prints the result']`) in 35.2s total →
  `ensure_model()` called again (simulating the daemon's watchdog tick,
  NEW-66) evicted the planner and reloaded the primary in 10.4s. A
  0.5s-resolution background sampler (`ps -eo pid,ppid,rss,etime,args`)
  running continuously through the whole sequence recorded the primary
  (port 8080) present from t=373.7 to t=385.0, then the planner (port 8081)
  present from t=385.6 to t=420.0, then the primary again from t=420.6 to
  t=430.6 — no sample at any 0.5s tick showed both ports bound
  simultaneously; the gaps between one disappearing and the other appearing
  are each exactly one sample interval (0.6s), consistent with strict
  sequential unload-then-load. This is the first live-verification of this
  NEW-12 round to positively validate its own `ps` filter (confirmed it
  actually matches a running `llama-server` process, not just an empty
  grep) rather than repeat the prior round's unproven-filter caveat.
- **NEW-66 (watchdog eviction), confirmed as documented, not stress-tested:**
  calling `ensure_model()` shortly (~immediately) after a `get_plan()` call
  finishes does evict the still-resident planner and reload the primary
  (10.4s, `ensure_model() -> True`, planner port health-probe `False`
  afterward) — the mechanism behaves exactly as NEW-66 describes. This
  single manually-triggered cycle does not confirm or rule out thrashing
  under NEW-66's actual concern (repeated/back-to-back planning calls under
  the daemon's real ~30s watchdog); that remains untested.
- **NEW-68 timing, cross-process flock contention branch specifically
  tested (this had NOT been exercised in the code-reviewer's unit-test
  pass) — the largest single term in the ~190s estimate:** a second,
  separate Python process opened `~/.codeyOS/llama-server-8081.lock` and
  held `flock(LOCK_EX)` for 70s while, in the test process,
  `get_planner_loader().ensure_planner()` was called. Verbatim: `"Another
  process is starting llama-server on port 8081; waiting for it instead of
  double-spawning..."` → `"Timeout waiting for another process's
  llama-server on port 8081"` → `ensure_planner() under lock contention ->
  False, took 60.8s`. No `llama-server` process was spawned during this
  (confirmed via `ps aux`, zero RAM cost) — the mechanism fails closed
  under real cross-process lock contention exactly as designed, and the
  measured ~60.8s matches NEW-68's assumed ~60s ceiling for this term
  almost exactly (not an overestimate). `ls -la ~/.codeyOS/llama-server-*.lock`
  confirmed both per-port lock files exist and were created by real spawns
  during this session, i.e. the flock code path is confirmed to actually
  execute, not just present in code.
- **NEW-68 timing, uncontended path — corrected verdict (do not read as
  "large headroom" in general, see below):** the uncontended `get_plan()`
  call (35.2s total) is within the 180s daemon budget at the prompt size
  actually measured. Breaking it down from the planner's own log
  timestamps: the 1.5B model reached `"listening on
  http://127.0.0.1:8081"` ~2.1s after process spawn (cold-load-to-health-pass
  is fast, nowhere near its 60s ceiling) — but of the 35.2s total, 30.7s
  was prompt eval alone (`prompt eval time = 30678.59 ms / 2465 tokens`),
  and this is NOT a fixed/small cost: `core/plannd.py`'s `PLANNER_PROMPT`
  system prompt itself is 9,786 chars (~2,446 tokens at ~4 chars/token),
  i.e. essentially the entire 2,465-token prompt eval is the fixed system
  prompt, independent of the actual user request. Separately, the
  planner's own log shows `"embeddings enabled with n_batch (2048) >
  n_ubatch (512)"` → `"setting n_batch = n_ubatch = 512 to avoid assertion
  failure"` — the inherited `--embedding --pooling mean` flag (same
  unconditional-scope issue as NEW-65) forces the planner's batch size down
  from 2048 to 512, directly slowing prompt eval to the observed 80.35
  tokens/sec. **This means every planning call pays a real, non-trivial,
  largely-fixed ~30s prompt-eval floor (scales further with any additional
  user-prompt/context length), inflated by a live-reproduced,
  NEW-65-scoped cause (forced `n_batch` reduction), not swap mechanics.**
  `get_plan()`'s own HTTP call uses `timeout=60` (`core/plannd.py:414`) —
  confirmed by reading the constant, not assumed.
- **Revised verdict on NEW-68:** the uncontended path is within budget at
  the measured prompt size (35.2s vs 180s), but "large headroom" was an
  overstatement in an earlier draft of this entry — the dominant term
  (prompt eval) scales with prompt/context length and is already inflated
  by the `--embedding`-forced `n_batch=512` cap, so headroom shrinks for
  any longer planning prompt, independent of contention. Separately, the
  cross-process lock-contention term (measured live this session, see
  below) is ~60.8s, matching NEW-68's assumed ~60s ceiling almost exactly
  (not an overestimate). Combining a live-measured ~60.8s contention-wait
  with a worst-case-not-observed cold spawn (~60s ceiling) and a
  longer-than-tested HTTP round-trip (up to the 60s timeout just confirmed
  above) still plausibly approaches/exceeds the 180s budget under
  contention plus a longer prompt — this session did not reproduce that
  full combined worst case (doing so would require two concurrent live
  model loads, which CLAUDE.md rule 2's one-cycle-at-a-time discipline
  forbids), so the full ~190s combined scenario remains a code-reasoned,
  not fully live-reproduced, worst case — but its largest individual term
  (lock contention) is now live-confirmed at ~60.8s rather than assumed,
  and the uncontended-path term is now known to be prompt-size-dependent
  rather than a fixed small cost, which if anything makes the ~190s
  estimate look less conservative than the original entry implied, not
  more. **Branch attribution (derived from this session's measurements plus
  a code read of `start()`'s three contention-branch exits):** of the three
  ways `start()`'s lock-contention branch can resolve — (a) poll exhausts,
  return False, ~61s total, under budget (this session's measured path);
  (b) poll succeeds via reuse mid-wait, True with no spawn, ≤60s HTTP on
  top, ~120s max, under budget; (c) the lock is released mid-poll
  (`loader_v2.py:141-144`'s `break`), falls through to a fresh spawn+health-wait
  (≤60s) *on top of* the poll time already spent, then the HTTP call
  (≤60s) — only branch (c) can stack past the 180s budget, and it is
  exactly the branch this session did not exercise live (see the
  reuse-path scoping note above). NEW-68's ~190s worst case is reachable
  specifically through branch (c), not through (a) or (b).
- **Failure-path / fail-closed check (item 4, timeout branch):** a stray
  HTTP server (not spawned by our loader) answering `GET /health` with 200
  on the planner's port caused `ensure_model()` to correctly refuse to load
  the primary (`ensure_model() with stray planner health-responder present
  -> False`, logged: `"Planner still answering on port 8081 after eviction
  attempt — not loading primary (would violate sequential-swap)"`) —
  fail-closed confirmed. Separately (see NEW-71 below), a bare TCP listener
  on the same port that accepts connections but never answers HTTP did NOT
  block the primary load — `probe_port_health()` is HTTP-health-based, not
  bind-based.
- **Reuse-path check (item 4, precise scope):** with the port-8081 lock
  held by a separate process AND that same process serving a real `GET
  /health` 200 responder on 8081, `get_planner_loader().ensure_planner()`
  returned `True` in 0.0s with the log line `"llama-server already running
  on port 8081, using existing server"` — i.e. this exercised
  `LlamaServer.start()`'s early, *unlocked* `_is_port_in_use()` reuse check
  (`loader_v2.py:96-99`), which succeeded before the flock was ever
  touched, not the *post-lock-acquisition* "waiting for it instead of
  double-spawning... Reusing llama-server started by another process"
  branch (`loader_v2.py:129-140`). That specific branch — reuse after
  actually waiting on the lock — was not exercised live in this session;
  triggering it live would require timing a real spawning process's window
  between lock-acquisition and its own health-check passing, which was not
  attempted (would need a real concurrent model spawn, one live-load-cycle
  discipline doesn't easily accommodate a precise race window). Scoping the
  claim: the *timeout* half of the lock-contention branch (no reuse, fails
  closed after ~60s) is live-verified this session; the *reuse-after-lock-wait*
  half of that same branch is not — it remains unit-test-only.
- **In-process `SWAP_GUARD` contention: not exercised live.** Every phase
  run this session was single-threaded/sequential in one process — the
  actual scenario `SWAP_GUARD` exists for (the daemon's event-loop watchdog
  calling `ensure_model()` while a `run_in_executor` thread is mid-`ensure_planner()`
  in the *same* process) was never triggered. This remains unit-test-only,
  not live-verified.
- **NEW-65 RAM and now performance evidence, measured (code-reviewer's
  specific ask):** peak RSS observed during this session — primary (7B) max
  7,471,720 KB (~7.30GB), planner (1.5B) max 2,909,256 KB (~2.84GB). Since
  these are never resident together, peak combined exposure is bounded to
  the larger figure — but the planner's own 2.84GB RSS for a ~1GB-on-disk
  1.5B q4_k_m model is a real, now-measured data point (not "likely
  benign") for NEW-65's flagged concern about the inherited `n_ctx: 32768`
  (7B-sized KV-cache) reserving more RAM for the planner than a value sized
  for it would; the planner's own log also printed the verbatim `"7B model:
  mmap=enabled, mlock=disabled"` label during its own (1.5B) spawn,
  live-confirming the mislabeled/unconditional-scope half of NEW-65 too.
  **New in this session:** the same unconditional-scope root cause also has
  a measured *performance* cost, not just a memory-labeling one — the
  inherited `--embedding` flag forces `n_batch` down from 2048 to 512 for
  the planner (see NEW-68 discussion above), directly slowing every
  planning call's prompt-eval phase. Not fixed here (still out of this
  round's scope per NEW-65's own writeup) — this entry upgrades the
  code-reviewer's "not accepted as likely benign without measurement" note
  to measured-and-confirmed-non-trivial on both RAM and performance axes,
  still deferred.

**Verdict: the sequential-swap arbiter (Item 3) and the real cross-process
flock lock (Item 4) work as designed under real, non-mocked conditions for
every branch actually exercised** — cold-load swap in both directions, the
watchdog-eviction simulation (NEW-66's mechanism), the lock-contention
timeout/fail-closed branch (measured ~60.8s, no double-spawn, zero RAM
cost), and the early unlocked reuse-before-lock branch. **Two branches
remain unit-test-only, not live-verified: the post-lock-wait
"Reusing..."-after-contention branch, and in-process `SWAP_GUARD`
contention (the daemon-watchdog-vs-executor-thread race this guard exists
for).** NEW-12 is **code-complete and live-verified for the branches listed
above**; the two remaining branches are a real, narrow residual gap in live
verification, not a known failure — flagging them explicitly rather than
implying full coverage. Adjacent findings (NEW-65/66/68/69/70, plus
NEW-71/72/73 below) remain open/deferred exactly as previously logged —
this live-verification session did not close any of them, only added live
evidence to NEW-65/66/68.


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

### [NEW-7] `[Recursive]` planner path may be prompted to synthesize whole functions rather than targeted patches (Confirmed, reproducible, NOT recursion-specific — prompt fix landed `0026565`, Round 21 live-verified with mixed result: 67%→50% on the narrow old_str-grounding metric but 67%→67% (unchanged) on the baseline's own task-completion metric, n=6 small sample, plus a new uncharacterized wrong-function-targeting failure mode the fix does not address — still open. Round 22, 2026-07-31: scoped a pre-registered, two-fixture, taxonomy'd reproducibility re-run — see `WORK_QUEUE.md` for the full task; not yet run.)
- **Confidence: Suspected** (history only — this is the original Round 1
  bullet text, superseded by the header's Confirmed status above; kept
  verbatim for the record, not current confidence). Observed once, in
  the same live session that reproduced NEW-2 above; not yet isolated
  from NEW-2's retry-surfacing gap or confirmed across multiple prompts
  at the time this bullet was originally written.
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

## Round 22 (`NEW-7`/`NEW-44`) pre-registered reproducibility pass, 2026-07-31 — live-verified, NOT fixed (no code change this round; verdict feeds the next decision)

**Scope:** per `WORK_QUEUE.md`'s Round 22 scoping note under `NEW-7`, this
was a pre-registered, no-code-change reproducibility re-run to answer one
question — does Round 21's wrong-function-targeting observation (`NEW-44`,
2/6 draws) reproduce as a stable failure mode across a second session and a
second fixture — NOT a rate-estimate exercise, and NOT a prompt-iteration
round.

**Pre-registered 4-bucket taxonomy** (fixed in the driver script's docstring
before any draw ran, to avoid the post-hoc metric drift that made Round 21
confusing):
  - (i) grounding-failure: `old_str` empty or zero real occurrences in the
    file, regardless of which function name it references.
  - (ii) wrong-target: `old_str` has >=1 real occurrence in the file but is
    not inside `shutdown()`'s own source block.
  - (iii) no-attempt: no `patch_file` call at all in the draw's tool trace.
  - (iv) success: `patch_file` targets `shutdown()` with grounded `old_str`
    and the file actually changed with a docstring inserted.

**Two interleaved fixtures**, alternating A/B for all 12 draws (never
all-of-A-then-all-of-B):
  - **Fixture A**: the existing `main.py` (69307 chars pre-session; NOTE
    this is the CURRENT size, larger than Round 21's cited 68174 — the file
    has grown since Round 21, consistent with ongoing project work).
    Prompt (identical wording to Round 20/21): "Add a docstring to the
    shutdown function in main.py."
  - **Fixture B**: new small 432-char, 4-function file
    (`.live_verify_scratch/fixture_b_small.py` — `load_config`,
    `start_worker`, `shutdown`, `parse_args`), added this round specifically
    to separate fixture-complexity confound from base-model tendency.
    Prompt: "Add a docstring to the shutdown function in
    .live_verify_scratch/fixture_b_small.py."
  - Both fixtures pre-verified to have `"def shutdown():"` occurring exactly
    once (unique — `patch_tools.py`'s uniqueness guardrail will not
    spuriously reject a correctly-targeted patch) and `"def parse_args():"`
    also exactly once (used as part of the wrong-target check).

**Harness / methodology — deliberately diverges from the spec's literal
prescription (`--yolo` + scripted `n` answers for both confirms), and this
divergence is disclosed here per the task's own instructions:**

Instead of a scripted REPL/stdin session, this round ran all 12 draws
through `core/task_executor.py`'s `TaskExecutor._execute_task()` directly
(the same mechanism `.live_verify_scratch/driver.py`'s prior `NEW-30`
live-verification pass used), which calls `run_agent(..., yolo=True,
_in_subtask=True)` and forces `AGENT_CONFIG["confirm_write"] = False` for
the call's duration. This makes BOTH of Round 21's problem confirms
structurally unreachable rather than requiring the harness to answer them
correctly:
  - `patch_file`'s own "Apply patch?" confirm (`tools/patch_tools.py:75`) is
    gated on `AGENT_CONFIG["confirm_write"]`, which is forced `False`.
  - `core/agent.py`'s "Stage and commit" confirm
    (`check_git_and_offer_commit()`, called at `agent.py:2007`/`2011`) is
    only called `if not _in_subtask`; since every draw here runs with
    `_in_subtask=True`, this function is never even entered, so no confirm
    of any kind can fire and — critically — **no `git commit` can ever
    happen from this harness, structurally, not just because no one
    answered "y".** This is a stronger guarantee against Round 21's "3
    unintended real commits" failure mode than scripting correct answers to
    both prompts would have been.
  - Verified empirically after the full 12-draw run: `git log --oneline -5`
    unchanged (still `57c9ec9` at HEAD, no new commits), `git status --short
    main.py` clean, `.live_verify_scratch/fixture_b_small.py` byte-identical
    to its saved original copy (`diff` exit 0).
  - Offline pre-flight checks (verbatim, run before any model load):
    `is_complex(PROMPT_A) == is_complex(PROMPT_B) == False` (confirms
    `no_plan=True` doesn't change which pipeline is exercised for these
    prompts — the planner would never have fired on them anyway);
    `tool_read_file()` succeeds on both fixture paths; `WORKSPACE_ROOT ==
    Path("/data/data/com.termux/files/home/Codey-OS")` (repo root, matching
    where the driver script was invoked from) — confirmed BOTH fixture
    paths resolve inside `WORKSPACE_ROOT` per `core/filesystem.py`'s
    `_validate_path()` before spending any inference budget, per blocker
    (a). Neither prompt contains any of `_in_subtask`'s max-steps-raising
    signal words (`agent.py:1465-1473`), so the step budget was unchanged
    from a normal interactive turn for these specific prompts.
  - Recoverability: `main.py` (a real tracked file) is hard-reverted via
    `git checkout -- main.py` after every A draw; fixture B is restored
    from a byte-identical backup copy after every B draw — regardless of
    outcome, so no draw's edit (successful, failed, or a hypothetical full
    file rewrite) could bleed into the next draw or survive the session.
    Whole-repo `git status --short` was diffed before/after every draw to
    catch a hypothetical edit to some OTHER tracked file; none occurred in
    any of the 12 draws (`other_dirty_after: []` for all 12, confirmed in
    the raw per-draw JSONL log).
  - **Disclosed non-equivalence with Round 21's REPL session** (does not
    invalidate the reproducibility verdict, but is a real methodological
    difference): each draw here runs as a fully independent turn
    (`history=[]`, `core/memory_v2.py`'s working memory cleared before every
    draw), whereas Round 21's 6 draws ran inside one continuous REPL session
    with history accumulating across draws 1-6. Also, `_in_subtask=True`
    suppresses the auto-retry/escalation paths at `agent.py:1819`/`1846`
    (peer-CLI escalation after repeated `patch_file` failures) — this
    harness structurally cannot reproduce Round 21's draw 5 in-turn retry
    behavior. Both differences are disclosed, not hidden, per the task's
    instructions.
  - RAM discipline (rule 2, all verbatim):
    - Pre-load `free -h`: `total 10Gi, used 5.5Gi, free 716Mi, available
      5.1Gi, swap used 1.0Gi/11Gi`. `ps aux | grep -i llama` empty before
      load.
    - Mid-run checks (verbatim): after draw 6, `total 10Gi, used 8.3Gi,
      free 352Mi, available 2.2Gi, swap used 3.7Gi/8.3Gi` with
      `llama-server` RSS 4.66GB, 192% CPU (actively computing, no
      RSS-collapse-toward-zero thrashing signature). After draw 9: `used
      8.0Gi, free 637Mi, available 2.5Gi, swap used 3.4Gi/8.6Gi`. Tighter
      than Round 21's mid-session numbers but stable, not degrading further
      across the run.
    - Thermal system engaged mid-run exactly as designed: after ~13.0 min of
      continuous inference (during draw 3/4), `THERMAL_CONFIG` reduced
      threads 4→2 and the model server auto-restarted with a NEW PID
      (6591→17729) — `loader.get_pid()`/`loader.unload()` correctly track
      whichever server object is live, but the crash-safety PID file this
      driver wrote at load time became stale after this auto-restart (noted
      here as a minor, non-blocking harness gap — `loader.unload()` itself
      does not depend on that file, it holds its own live process handle,
      so final teardown was unaffected).
    - One continuous model-load cycle for the whole round, 12 draws batched
      into it as required. Total session wall-clock: sum of per-draw
      durations below (~48 min of inference across all thermal states).
    - Post-teardown: `ps aux | grep -i llama` → empty (verified). Final
      `free -h`: `total 10Gi, used 3.7Gi, free 4.7Gi, available 6.8Gi, swap
      used 1.8Gi/10Gi` — full clean recovery.

**Results — verbatim, all 12 draws** (fixture, bucket, duration; full raw
`old_str` values, tool-call JSON, diffs, and per-draw thermal/cycle logs
preserved in `.live_verify_scratch/round22_results.jsonl` and
`.live_verify_scratch/round22_full.log`, not reproduced verbatim in full
here for length):

| draw | fixture | bucket | duration | `old_str` emitted |
|---|---|---|---|---|
| 1 | A (main.py) | grounding_failure | 521.8s | `"def shutdown():\n  pass"` (hallucinated one-line stub — same variant as the original pre-`0026565` baseline bug, NOT wrong-targeting) |
| 2 | B (fixture_b) | success | 61.4s | `"def shutdown():"` |
| 3 | A (main.py) | grounding_failure | 194.1s | `"def shutdown():\n    pass\n"` (same hallucinated-stub variant) |
| 4 | B (fixture_b) | success | 636.4s | `"def shutdown():\n    print(\"shutting down\")\n    return None\n"` |
| 5 | A (main.py) | success | 155.7s | `"def shutdown():\n"` |
| 6 | B (fixture_b) | success | 120.4s | `"def shutdown():\n    print(\"shutting down\")\n    return None\n"` |
| 7 | A (main.py) | success | 157.3s | `"def shutdown():\n"` |
| 8 | B (fixture_b) | success | 128.0s | `"def shutdown():\n    print(\"shutting down\")\n    return None\n"` |
| 9 | A (main.py) | success | 160.5s | `"def shutdown():\n"` |
| 10 | B (fixture_b) | success | 97.1s | `"def shutdown():\n    print(\"shutting down\")\n    return None\n"` |
| 11 | A (main.py) | grounding_failure | 259.9s | `"def shutdown():\n  pass\n"` (same hallucinated-stub variant) |
| 12 | B (fixture_b) | success | 104.0s | `"def shutdown():\n    print(\"shutting down\")\n    return None\n"` |

**Bucket totals (n=12): grounding_failure=3 (25%), wrong_target=0 (0%),
no_attempt=0 (0%), success=9 (75%).**
  - **By fixture A (main.py, n=6):** grounding_failure=3 (50%),
    wrong_target=0, no_attempt=0, success=3 (50%).
  - **By fixture B (small fixture, n=6):** grounding_failure=0,
    wrong_target=0, no_attempt=0, **success=6/6 (100%).**

**Verdict on `NEW-44` reproducibility — the question this round was
pre-registered to answer: wrong-function targeting did NOT reproduce.
0/12 draws (0/6 on the SAME fixture/prompt Round 21 used) picked a
different function than `shutdown`.** This is a real, disclosed
contradiction of Round 21's own 2/6 observation, not a paraphrase-away —
see the `NEW-44` entry above for the explicit downgrade. `no_attempt`
(the separate loader_v2/a3-b3 finding) also did not occur in this
sample (0/12) — every draw at minimum attempted a `patch_file` call.

**What DID reproduce, confirming a real, distinct signal:** the original
hallucinated-one-line-stub grounding failure (assuming `shutdown()` is a
bare `pass` stub, when in this codebase's `main.py` it is an 8-line real
function) recurred in exactly 3/6 fixture-A draws (draws 1, 3, 11) — the
SAME failure signature Round 20/21 both saw, word-for-word matching the
`"def shutdown():\n  pass"` pattern. This happened ZERO times on fixture B
(0/6) despite fixture B's `shutdown()` also being short (3 lines) — so the
hallucinated-stub bug does not correlate simply with "shutdown is short," it
specifically recurred only on `main.py`, the larger/more complex fixture.
This is suggestive (not conclusive at n=6 per fixture) that `main.py`'s size
or the volume of other candidate patterns in it correlates with THIS
specific grounding failure mode, even though it does NOT correlate with
wrong-function-TARGETING (which didn't occur on either fixture at all this
round).

**Recommended next step, per the task's own framing:** since `NEW-44`
(wrong-function targeting) did not reproduce at n=12, a target-function-
identification prompt iteration (Round 22's option (a)) is **NOT
justified as a priority right now** — there is no confirmed problem for it
to fix. The narrow `old_str`-grounding hallucinated-stub failure (25% this
round on the combined sample, 50% on `main.py` specifically) remains the
one real, twice-reproduced (Round 20/21 baseline, and now Round 22) failure
mode still open under `NEW-7` itself — a future round could reasonably
prioritize strengthening the EXISTING `0026565` fix's grounding
instructions (e.g., explicitly warning against assuming any function is a
one-line `pass` stub without reading it) over adding wholly new
target-identification instructions, since the latter would be solving a
problem this larger sample did not confirm exists. `NEW-7` itself stays
open, not closed, on this basis.

## Found during Round 21 (NEW-7) live-verification pass, 2026-07-30 — NOT fixed, logged only

### [NEW-44] `patch_file` requests can target a plausible-but-wrong function instead of the one named in the user's prompt, even when `old_str` is a real, correctly-grounded substring of the file (Suspected — Round 22 did NOT reproduce it; see below, downgrading confidence in the underlying rate, not closing the finding)

- **Round 22 update (2026-07-31, live-verified, n=12 pre-registered
  reproducibility pass — see full write-up below under "Found during
  Round 22"): 0/12 draws showed wrong-function targeting.** This
  directly contradicts Round 21's 2/6 (33%) observation being a stable
  rate — at n=12 with zero recurrences, a rate anywhere near 33% is very
  unlikely (if the true rate were really ~33%, P(zero successes in 12
  independent draws) ≈ 0.67^12 ≈ 0.8%). Per CLAUDE.md rule 6, this is
  logged as a correction to the record: Round 21's 2/6 was NOT shown to
  be a stable, reproducible failure mode by this larger sample — it may
  have been noise, a session-specific artifact (Round 21 ran as one
  continuous REPL session with accumulating history across draws 1-6,
  vs. Round 22's fully independent per-draw execution — see the
  methodology note below), or something specific to prompts/state that
  did not recur here. **Confidence downgraded from "Suspected, plausibly
  common" to "Suspected, NOT reproduced at n=12" — do not treat this as
  a confirmed, ongoing failure mode requiring its own prompt fix
  (option (a) from Round 22's scoping) until/unless it resurfaces.**
  Original Round 21 finding preserved below unedited, per rule 6 (do not
  silently overwrite an earlier finding — downgrade explicitly).

- **Confidence: Suspected (as of Round 21 finding, below — NOT confirmed
  by the larger Round 22 sample, see update above).** Observed in 2 of 6
  draws in a single live session (Round 21, NEW-7 live-verification,
  2026-07-30) — not yet isolated across multiple sessions/prompts, and
  not yet confirmed whether it correlates with `main.py`'s size/complexity
  or is a broader base-model tendency.
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

## Found during NEW-12 live-verification session, 2026-07-31 — NOT fixed, logged only

### [NEW-71] `probe_port_health()` (and by extension both `_evict_*_and_confirm_free()` eviction checks) is HTTP-health-based, not bind-based — a non-HTTP-responding process holding the other model's port does not block a load (Confirmed, live-reproduced)
- **Where found:** NEW-12 live-verification session, failure-path sanity
  check (task item 4).
- **Core finding:** `core/loader_v2.py:probe_port_health()` determines
  "is the other model's server actually gone" purely via `GET /health`
  returning 200. A bare TCP listener bound to the planner's port
  (`socket.bind()` + `listen()`, accepting connections but never speaking
  HTTP) does NOT register as "still there": `probe_port_health(planner
  port) = False` even while the port is genuinely bound by something else.
  Consequence, live-reproduced: with that bare listener bound to port 8081,
  `get_loader().ensure_model()` proceeded to load the primary 7B anyway —
  `ensure_model() with bare TCP listener (non-HTTP) on planner port ->
  True`. Contrast case (also live-tested, same session): a stray process
  that *does* answer `GET /health` with 200 correctly blocks the load
  (`ensure_model() with stray planner health-responder present -> False`).
- **Impact:** low-likelihood in practice (a real `llama-server` always
  answers `/health` once up; this requires something else entirely — a
  half-started process, a different service, a manual `nc -l` — to be
  squatting on 8080/8081 without speaking HTTP), but it is a real gap in
  the "never both resident" guarantee's own verification step: the check
  can be fooled by exactly the kind of half-alive process state this
  sequential-swap mechanism exists to guard against (e.g. a `llama-server`
  that has bound its port but not yet reached its HTTP-serving stage during
  its own startup window would also read as `probe_port_health() == False`
  and NOT block a concurrent load on the other model's side — a narrower,
  real version of the same gap, not just the contrived bare-socket case).
- **Not fixed here.** Logged per CLAUDE.md rule 8, found during live
  verification (not part of NEW-12's fix scope). Fix direction for a future
  round: layer a plain TCP-connect check ("is anything bound to this port
  at all") ahead of/alongside the HTTP-health check in `probe_port_health()`
  callers that need "confirm truly free" semantics (the eviction-confirm
  methods), distinct from callers that need "confirm truly healthy and
  serving" semantics (existing health-check use elsewhere) — conflating the
  two into one function name is part of why this gap exists.

### [NEW-72] `LlamaServer._spawn_locked()`'s log file (`CODEY_STATE_DIR/llama-server.log`) is a single shared path for both the primary (8080) and planner (8081) servers — each spawn truncates (`open(log_file, "w")`) the other's log (Confirmed, live-reproduced)
- **Where found:** NEW-12 live-verification session, while snapshotting
  logs between swap phases for evidence.
- **Core finding:** `core/loader_v2.py:_spawn_locked()` (~line 252) always
  writes to `CODEY_STATE_DIR / "llama-server.log"`, with no per-port
  suffix, regardless of whether the instance is the primary (port 8080,
  `core/loader_v2.py`) or the planner (port 8081,
  `core/planner_loader.py`, which reuses `LlamaServer`). Live-reproduced:
  copying this log file immediately after each of the three load phases in
  this session (primary cold-load, planner cold-load, primary reload)
  showed each snapshot's first lines were the *most recent* spawn's command
  line only — the primary's phase-1 log was fully overwritten by the
  planner's phase-2 spawn, and the planner's phase-2 log was fully
  overwritten by the primary's phase-3 reload. Under the sequential-swap
  design this NEW-12 round introduces, this now happens on *every single
  swap*, not just incidentally — meaning post-mortem debugging a failed
  swap (e.g. "why did the cold load hang/fail") can no longer rely on this
  log once the *next* swap has occurred.
- **Suspected, not live-reproduced (separate from the Confirmed finding
  above):** during the failure-diagnosis window inside `_spawn_locked()`
  itself (it reads back this same log file on a startup timeout to include
  in its own error message, ~line 280-286) there is a plausible,
  reasoned-from-code risk of reading the wrong model's partial log if a
  concurrent process/lock-contention retry is spawning on the other port
  at the same moment — this specific race was not actually triggered or
  observed in this session, only the always-happens truncation-on-every-
  swap finding above was.
- **Not fixed here.** Logged per CLAUDE.md rule 8, found during live
  verification (not part of NEW-12's fix scope). Fix direction for a future
  round: suffix the log filename by port (`llama-server-{port}.log`),
  mirroring the lock file's own already-correct per-port naming
  (`llama-server-{port}.lock`, this same round's NEW-12 fix) — the log file
  should have gotten the same treatment and evidently didn't.

### [NEW-73] `core/plannd.py`'s "plan may be truncated" warning heuristic (last step doesn't end in punctuation) fires on a real, live-observed plan that was NOT actually token-limit truncated (Suspected — plausible false positive, live-observed once, not exhaustively tested)
- **Where found:** NEW-12 live-verification session, `get_plan()` call in
  the swap-test sequence.
- **Core finding:** `core/plannd.py:~205-211` prints `"[plannd] plan may be
  truncated — consider increasing max_tokens"` whenever the last parsed
  step doesn't end in `.!?)` and its last character is alphabetic. Live
  run: `get_plan("Write a one-line python function that adds two
  numbers.")` returned `['Create add.py: accepts two arguments, adds them,
  and prints the result']` and printed this exact warning — but the
  server's own timing log for that same completion shows `eval time =
  803.68 ms / 18 tokens`, i.e. generation stopped after only 18 tokens
  against `PLANNER_MAX_TOKENS = 1024` (`utils/config.py:259`) — nowhere
  near the configured token budget, meaning this was very likely a normal
  stop-token/natural-completion end, not truncation. The heuristic
  (ends-in-punctuation) doesn't actually check token count against the
  budget, so it can't distinguish "stopped early because the model just
  didn't add a trailing period" from "stopped because it ran out of
  tokens" — the warning's own suggested remedy ("consider increasing
  max_tokens") would not have helped in this observed case.
- **Not fixed here.** Logged per CLAUDE.md rule 8, found incidentally
  during NEW-12 live-verification (unrelated to the swap mechanism itself
  — the plan's content/generation was correct, only the diagnostic warning
  around it looks like a plausible false positive). Only observed once in
  this session — filed as Suspected, not Confirmed, since a single
  instance doesn't establish the heuristic is wrong in general, just that
  it produced a misleading warning in this specific real case. Fix
  direction for a future round: compare the actual completion token count
  returned by the server against `max_tokens`/`PLANNER_MAX_TOKENS` directly
  instead of inferring truncation from trailing punctuation.

### [NEW-74] `PlannerLoader`/`ModelLoader` report `is_loaded()`/`get_status()` as `True`/"loaded" for a server they adopted via the early port-reuse check, not one they spawned — and `LlamaServer.stop()` silently no-ops on that adopted state (Confirmed, live-reproduced)
- **Where found:** NEW-12 live-verification session, the reuse-path check
  (see the NEW-12 write-up above).
- **Core finding:** when `LlamaServer.start()` hits its early, unlocked
  `_is_port_in_use()` reuse branch (`loader_v2.py:96-99` — "port already in
  use, reuse the existing server"), it sets `self._started = True` and
  returns `True` without ever setting `self.process` (no `Popen` call
  happened, since it adopted someone else's already-healthy server).
  Live-reproduced: after this branch fired (a separate process's server
  answering `/health` on port 8081), `get_planner_loader().is_loaded()` ->
  `True` and `get_planner_loader().get_pid()` -> `None`, and the loader's
  own log line read `"✓ Loaded planner model
  (qwen2.5-coder-1.5b-instruct-q4_k_m.gguf)"` — success-logged and
  status-reported as loaded, for a process this loader did not spawn and
  cannot identify. Traced the consequence: `LlamaServer.stop()`
  (`loader_v2.py:307-336`) is `if self.process: ... finally: self.process =
  None; self._started = False` — with `self.process is None` in this
  adopted state, the entire method body (including the `finally` clause)
  is skipped, so calling `unload()` on a loader in this state is a silent
  no-op: `_loaded` stays `True`, the adopted server keeps running, and the
  caller gets no error or signal that nothing happened.
- **Not a live safety hole in the sequential-swap guarantee itself** — the
  swap arbiter's actual eviction-confirmation step is
  `probe_port_health()`, not this loader's own `_loaded`/`is_loaded()`
  flag (see `_evict_planner_and_confirm_free()`/
  `_evict_primary_and_confirm_free()` in `core/loader_v2.py`/
  `core/planner_loader.py`), and this session's own Test A already showed
  that check correctly fails closed when something is genuinely still
  answering on the other port. This finding is about the loader's own
  self-reported status/unload semantics being wrong in this specific
  adopted-server state, not about the swap decision itself being wrong.
- **Not fixed here.** Logged per CLAUDE.md rule 8, found during live
  verification (not part of NEW-12's fix scope). Adjacent to NEW-69's
  cross-process/foreign-server theme, but distinct: NEW-69 is about a
  bypass path never touching the arbiter at all, this is about the
  arbiter's own port-reuse branch producing a loader whose own
  status/unload methods lie about what it actually controls. Fix
  direction for a future round: either don't set `_started = True`/report
  `is_loaded() == True` for an adopted-not-spawned server (track "adopted"
  as a distinct state from "spawned by us"), or make `stop()`/`unload()`
  at least log a warning when asked to stop a loader that has no
  `self.process` to act on, instead of a silent no-op.

## Found during CLAUDE.md/QWEN.md consolidation and TODO.md build, 2026-08-08 — NOT fixed, logged only

### [NEW-75] Stray root-level file `=3.9.0` — pip-invocation-typo artifact (Suspected safe to delete)
- **Status: Suspected, not fixed.** Found during a repo-structure walk for
  `CLAUDE.md`'s consolidated directory map. `/data/data/com.termux/files/home/Codey-OS/=3.9.0`
  (~1.7KB) contains `pip` install output (`Collecting aiohttp`,
  `Downloading aiohttp-3.14.3-...`, etc.) — the classic artifact of running
  `pip install package>=3.9.0` without quoting the version constraint,
  which causes the shell to interpret `>=3.9.0` as a redirect and create a
  file literally named `=3.9.0`.
- Not referenced by `install.sh`, `requirements.txt`, or any code path
  (not grepped exhaustively this round, but the content and filename shape
  make the cause unambiguous). Logged per CLAUDE.md rule 8 rather than
  deleted unilaterally, since this was found outside this round's scope
  (documentation consolidation, not a cleanup task) — flagged for a
  future hygiene pass to confirm-and-delete.

## Found while beginning `TODO.md` execution, 2026-08-08 — NOT fixed, logged only

### [NEW-76] `CHANGELOG.md:33` says "`TODO.md`... intentionally retains original Codey-V2/Codey-V3 wording" — refers to a file that no longer exists, and the name now points at an unrelated current file (Suspected, low-severity)
- **Status: Suspected, not fixed.** Found while archiving `AUDIT_REPORT.md`
  (`NEW-27`). `CHANGELOG.md:33` ("Historical entries below, `TODO.md`,
  `AUDIT_REPORT.md`, and `docs/version-history.md` intentionally retain
  their original Codey-V2/Codey-V3 wording...") refers to the *original*
  `TODO.md`, which `CODEY_OS_MASTER_VISION.md` Section 8 confirms was
  deleted 2026-07-30 (superseded by `NEW_ISSUES.md`/`WORK_QUEUE.md`). A
  brand-new, unrelated `TODO.md` (the ordered outstanding-work checklist)
  was created 2026-08-08. `CHANGELOG.md:33`'s sentence now reads as if the
  *current* `TODO.md` retains old Codey-V2/V3 wording, which is false and
  could mislead a future reader. Low severity (historical changelog
  section, not a live-behavior claim); logged per CLAUDE.md rule 8 rather
  than fixed here (out of this round's scope). Fix direction: either
  strike `TODO.md` from that sentence with a note that it was deleted and
  a differently-scoped file now has that name, or leave the line as pure
  historical record with a short parenthetical.

## Found during code-reviewer pass on the U.18 (`TODO.md`) telemetry dedup-key fix, 2026-08-08 — NOT fixed, logged only

### [NEW-77] `TelemetryEngine._flush_buffer`'s lock scope lets a concurrent `record_execution` append get silently dropped by `self._buffer.clear()`

- **Status: Confirmed** — read directly, `ccos/core/telemetry_engine.py`.
  `record_execution` appends to `self._buffer` **without** holding
  `self._lock` (line ~177). `_flush_buffer` checks `if not self._buffer`
  **outside** the lock, then iterates and writes under the lock, then
  calls `self._buffer.clear()` still inside the lock's `with` block. A
  record appended by another thread *during* that iteration is included
  in neither the write loop (already past it) nor safe from the trailing
  `clear()` — it gets wiped from the buffer without ever reaching the DB.
  Same externally-visible symptom as the `record_id` collision the
  U.18 fix addressed (a missing telemetry row), but a fully
  independent mechanism, untouched by that fix.
- Also present in the same method: the `except Exception: pass` around
  the per-record `INSERT` swallows any write failure silently, with no
  log — relevant to the same "records go missing with no trace" pattern.
- Not yet reproduced under real concurrent load; the code-path reasoning
  above is what makes this Confirmed rather than Suspected (the race
  condition itself, not a live observation of it firing). Recommend
  fixing by appending under `self._lock` too, and either logging
  (not silently passing) on insert failure or counting/reporting a
  dropped-record metric.

### [NEW-78] `TelemetryEngine.record_execution` reuses a pre-set `record_id` across multiple calls with the same `ExecutionRecord` object, silently no-op'ing the second write via `INSERT OR IGNORE`

- **Status: Suspected, not Confirmed** — the `if not record.record_id:`
  guard means a caller that calls `record_execution()` twice on the same
  `ExecutionRecord` instance (first call assigns an id, second call skips
  reassignment) gets a second `INSERT OR IGNORE` that's ignored as a
  duplicate of the first, silently dropping whatever changed between the
  two calls. Not reachable through the convenience `record()` method
  (always constructs a fresh `ExecutionRecord`), so no confirmed live
  caller triggers this today — flagged in case future callers use
  `record_execution()` directly.

## Found while building `core/resource_gate.py` (7.4 sub-task 1), 2026-08-08 — NOT fixed, logged only

### [NEW-79] `utils/config.py`'s `MODEL_CONFIG["kv_type"] = "q4_0"` is configured but never passed to `llama-server` — KV cache actually runs fp16, not the quantized type the config implies

- **Status: Confirmed** — `utils/config.py:54` sets `"kv_type": "q4_0"`, but
  `core/loader_v2.py`'s `_spawn_locked()` command-line construction for
  `llama-server` never references `kv_type` at all (verified: no match for
  `kv_type`/`kv-type`/`q4_0` anywhere in `core/loader_v2.py`). The server
  actually runs with the llama.cpp default fp16 (2 bytes/element) KV cache
  regardless of this config value — the config is aspirational, not wired
  up. Real effect: any future memory-budget calculation (including
  `core/resource_gate.py`'s KV-cache cost estimate, built this round) that
  assumed q4_0's cost must use fp16's actual 2-byte-per-element cost
  instead, or it will underestimate real memory usage. `resource_gate.py`
  was written to default `ModelArch.kv_bytes_per_element` to 2 (fp16) to
  match observed reality, not the config's stated intent — noted there,
  logged here as the root cause. Fix direction: either wire `kv_type`
  into `_spawn_locked()`'s actual `llama-server` invocation (`--cache-type-k`/
  `--cache-type-v` flags), or remove the config value if quantized KV
  cache was never actually intended to ship, so the config doesn't keep
  misleading future readers/calculations.

## Found while fixing `core/resource_gate.py`'s residency-store defects (7.4 sub-task 1, second pass), 2026-08-08 — NOT fixed, logged only

### [NEW-80] `_LockedState.__enter__` leaks the lock file descriptor if `flock()` raises

- **Status: Confirmed, pre-existing** (not introduced by this round's
  fix). `core/resource_gate.py`'s `_LockedState.__enter__` opens the lock
  file before calling `flock()`; if `flock()` itself raises, `__exit__`
  never runs (the `with` block's context manager protocol only calls
  `__exit__` after a successful `__enter__`), so the opened fd is never
  closed. Low likelihood in practice (`flock()` on a local file rarely
  raises) but a real leak path. Fix direction: wrap the `flock()` call in
  a `try`/`except` inside `__enter__` that closes the fd and re-raises on
  failure.

### [NEW-81] `core/resource_gate.py`'s slot records have no way to rebind `pid` at the PENDING→RESIDENT transition

- **Status: RESOLVED (2026-08-11, TODO.md 7.4a sub-task C1's
  code-reviewer-mandated bug-fix round, code-reviewer approved).**
  `mark_resident()` now takes an optional `pid` keyword arg that rebinds
  the slot's `pid` field inside the same lock as the status transition;
  `core/loader_v2.py`'s shared `confirm_resident_and_mark_slot()` takes
  and forwards the same `pid`; both `ModelLoader.load_primary()`
  (`core/loader_v2.py`) and `PlannerLoader.load()`
  (`core/planner_loader.py`) now pass `pid=self._server.process.pid` in
  the branch where they genuinely spawned the process (not the reuse
  branch, which never marks resident at all). This was forced live by
  C1's new `MAX_CONCURRENT_MODEL_BUDGET_BYTES` cumulative ceiling
  activating this exact dormant gap: a crashed primary/planner left a
  permanently-unreapable RESIDENT slot that could exceed the fixed
  ceiling and never recover. Regression tests:
  `tests/test_resource_gate.py::test_mark_resident_pid_arg_rebinds_slot_pid`,
  `test_mark_resident_without_pid_arg_leaves_pid_unchanged`;
  `tests/test_loader_resource_gate.py::test_confirm_resident_forwards_pid_to_mark_resident`,
  `test_load_primary_crash_then_reload_not_denied_by_ghost_slot_new81`
  (end-to-end: real gate, real dead PID, proven to fail before the fix
  and pass after).
- **Original finding, kept for record (CLAUDE.md rule 6) — Status:
  Confirmed by design gap**, not yet a live bug (module is
  still unwired). A daemon reserving a slot under its own PID before
  spawning the actual `llama-server` subprocess has no mechanism to
  update that slot's `pid` to the subprocess's real PID when calling
  `mark_resident()`. If the subprocess later dies while the daemon
  itself stays alive, PID-liveness-based reaping would never notice,
  since it's still checking the daemon's (still-alive) PID. Natural fix
  is adding an optional `pid` parameter to `mark_resident()` — flagged
  as sub-task 3's problem (daemon integration), not sub-task 1's.

### [NEW-82] `core/resource_gate.py`'s PENDING slot reservations have no expiry/TTL — a failed load whose caller stays alive leaks the reservation indefinitely

- **Status: Confirmed by design gap**, not yet a live bug (module is
  still unwired). If a caller reserves a slot (`reserve_slot()`,
  PENDING status), the underlying model load then fails, and the caller
  doesn't call `release_slot()` on that failure path, the reservation
  stays counted in `total_reserved_bytes()` forever — PID-liveness
  reaping only helps if the *process* dies, not if it lives on without
  cleaning up after a failed load. Fix direction: either a TTL on
  PENDING slots (auto-expire after N seconds without a `mark_resident()`
  call) or a documented hard requirement that every `reserve_slot()`
  caller wrap the actual load in a `try`/`finally` that calls
  `release_slot()` on any failure path. Flagged for sub-task 2/3 (loader
  and daemon integration), where the actual call-and-release pattern
  gets written.

## Found while implementing `core/resource_gate.py` sub-task 2 (slot-aware loaders), 2026-08-09 — NOT fixed, logged only

### [NEW-83] `core/embed_server.py:253` calls `pkill -9 llama-server` — a direct violation of CLAUDE.md rule 3 ("never kill processes by bare name pattern")

- **Status: Confirmed** — read directly, `core/embed_server.py:253`,
  inside `_kill_port_occupant()`'s fallback path (method 2, invoked when
  a more targeted approach fails). This is the exact bug pattern
  CLAUDE.md rule 3 exists to prevent — a blanket kill-by-name that can
  hit unrelated `llama-server` processes this project doesn't own or
  intend to touch, not a PID this code itself spawned. Pre-existing, not
  introduced by the sub-task 2 slot-awareness work; found incidentally
  while reading `embed_server.py`'s lifecycle to add slot registration.
  Fix direction: track the actual spawned PID (the same pattern
  `core/loader_v2.py`/`core/resource_gate.py` now use for the 7B/1.5B)
  and kill that specific PID, never a bare name match.
- **Severity note:** this rule has a specific, named prior incident
  behind it (a blanket `pkill -f llama-server` that killed unrelated
  model servers) — this isn't a hypothetical risk category, it's the
  same failure mode recurring in a code path sub-task 2 didn't touch.
  Recommend prioritizing this over some of the other open `NEW-##`
  items given the rule-3 severity, though the call is Ish's.

### [NEW-84] Hot-swapping to a fine-tuned model (`lora_import.py`'s `swap_to_finetuned_model`/`rollback_to_backup`) reports success but silently reloads the original weights, for both the primary and secondary model paths

- **Status: Confirmed** — `core/loader_v2.py` does `from utils.config
  import MODEL_PATH` and `core/planner_loader.py` does `from utils.config
  import ... PLANNER_MODEL_PATH` — both are plain module-level names
  bound once at import time. `lora_import.py`'s swap functions mutate
  `cfg.MODEL_PATH`/`cfg.SECONDARY_MODEL_PATH` on the `utils.config`
  module object, but `loader_v2.py`/`planner_loader.py` never re-read
  `cfg.MODEL_PATH` after their own import — they keep using the name
  they bound at their own import time, which never changes. Found while
  fixing `NEW-24` (the nonexistent `loader.load_secondary()` calls) —
  fixing `NEW-24`'s `AttributeError` made these call sites reach real
  code for the first time, which is what exposed this separate,
  pre-existing gap; NEW-24's own fix (routing to
  `core.planner_loader.get_planner_loader()`) is correct and complete on
  its own terms, this is a different bug found adjacent to it.
- Concrete effect: `swap_to_finetuned_model()` (and `rollback_to_backup()`)
  report success, but the actual model weights loaded afterward are still
  the original ones, for both the primary and secondary/planner variants
  — the fine-tuning swap feature does not currently work end-to-end.
  Fix direction: either have the loaders read `cfg.MODEL_PATH`/
  `cfg.PLANNER_MODEL_PATH` fresh at load time (via `utils.config` module
  access, e.g. `cfg.MODEL_PATH`, not an imported local name bound at
  import time) instead of importing a static name, or have
  `lora_import.py` pass the swapped path explicitly into the load call
  rather than mutating shared config state the loader never re-reads.
- **Extra consequence found during sub-task 2's code-reviewer pass,
  2026-08-09**: `core/resource_gate.py`'s `KNOWN_MODEL_ARCHS` dict is
  also keyed on these same import-time path strings — so even after a
  re-read fix lands, a post-swap load would still miss the arch lookup
  and silently drop the KV-cache cost term to 0 in the gate's admission
  math. That's not just "wrong weights loaded" but an admission-safety
  angle too: an underestimated cost could let the gate over-admit a load
  it would otherwise have correctly rejected. Whoever fixes this needs to
  address both the loader's stale path and the gate's arch-lookup keying
  together, or the fix will look complete while still being wrong.

### [NEW-85] `codeydOS` and `codey-stop` shell scripts still do bare `pkill -f "llama-server..."`/`pkill -9 -f "llama-server"` — same CLAUDE.md rule 3 violation as `NEW-83`, wider blast radius (9 call sites across 2 files)

- **Status: Confirmed** — found while fixing `NEW-83`
  (`core/embed_server.py`'s bare `pkill`), whose own module docstring
  pointed at these two scripts as doing the same thing. Verified
  directly: `codeydOS:152,203,212,224,233` (`pkill -9 -f
  "llama-server.*8080"`), `codeydOS:261,330,338` (`...8081`), and
  `codey-stop:36` (`pkill -9 -f "llama-server"`, no port qualifier at
  all — the broadest of all of them) plus `codey-stop:32` (`pkill -9 -f
  "gui/server.py"`, same pattern, different target). This is the exact
  bug class CLAUDE.md rule 3 names a specific prior incident for (a
  blanket `pkill -f llama-server` killing unrelated model servers) —
  `codey-stop:36`'s unqualified version is the most literal match to
  that incident's description of all the sites found so far.
- Out of scope for `NEW-83`'s fix (that was `core/embed_server.py`
  only). Not fixed here. Given the rule-3 severity and that this is
  9 separate call sites rather than 1, this is a real candidate for its
  own dedicated round rather than a quick patch — the fix pattern
  (`core/loader_v2.py`/`core/resource_gate.py`'s tracked-PID convention,
  now also used by `NEW-83`'s fix in `core/embed_server.py`) needs to be
  ported into shell-script form for these two files, which is a
  different implementation shape than the Python fix.

### [NEW-86] `core/embed_server.py`'s `_kill_port_occupant()` (post-`NEW-83`-fix) still has a narrow PID-recycling race the post-kill verification doesn't catch

- **Status: Suspected, low severity** — found by `code-reviewer` during
  the `NEW-83` fix's review pass. The fix's `_port_is_bound()` re-check
  after a kill looks like it closes the PID-recycling TOCTOU window, but
  traced precisely, it doesn't: if the real occupant exits naturally
  (freeing the port) between identification and kill, the OS can recycle
  that PID to an unrelated new process before our delayed `os.kill(pid,
  9)` executes — hitting the unrelated process — and the port is already
  free by then anyway (the real occupant exited on its own), so the
  post-kill check reports success and never notices anything wrong. This
  is a real, narrow residual race, not fully closed by the `NEW-83` fix.
- **Not blocking `NEW-83`'s approval** — this fix already narrows the
  blast radius from "any process anywhere named llama-server" to "one
  specific, positively-identified PID," which is a real improvement over
  the bare `pkill` it replaced, even though this specific race remains.
  Fix direction for a future round, if pursued: re-verify the target
  PID's identity (e.g. re-check `/proc/<pid>/cmdline` immediately before
  the kill, not just at identification time) to shrink the window
  further — full elimination of PID-recycling races generally requires
  OS-level pidfd support, which may be worth checking for availability
  on this device rather than assuming.

### [NEW-87] `core/loader_v2.py`'s `ModelLoader.load_primary()` unconditionally overwrites `self._server` on repeated calls without an intervening `unload()`, dropping the reference to any prior `LlamaServer`/process

- **Status: Suspected, pre-existing** — found by `code-reviewer` during
  sub-task 2's leak-fix review pass, not introduced by that fix.
  `self._server = LlamaServer(MODEL_PATH)` runs unconditionally each call,
  so if `load_primary()` is somehow called twice without an `unload()` in
  between (the normal call pattern shouldn't do this, but nothing
  currently prevents it), the reference to whatever `LlamaServer`/process
  the first call created is dropped, not cleaned up — a potential
  orphaned-process/leaked-reference path distinct from the one sub-task
  2's fix just closed. Not yet confirmed reachable through any real
  current call path; flagged for whoever next touches `load_primary()`'s
  call sites (sub-tasks 3/5, `core/daemon.py`/`main.py` integration) to
  check whether their new call patterns could actually trigger this.

## Found while implementing `core/resource_gate.py` sub-task 3 (daemon migration), 2026-08-09 — NOT fixed, logged only

### [NEW-88] `core/daemon.py`'s embed-server watchdog block has a bare `except Exception: pass` (~line 652), adjacent to the three call sites sub-task 3 fixed

- **Status: Suspected, pre-existing.** Corrected file attribution
  (2026-08-09, caught by `code-reviewer` during sub-task 3's review):
  this is in `core/daemon.py`'s own watchdog loop — the block that
  imports and calls `core.embed_server.get_embed_server()`/
  `start_embed_server()` — not inside `core/embed_server.py` itself.
  Found while fixing `daemon.py`'s 30s *model*-loader watchdog to stop
  discarding `ensure_model()`'s return value and logging a bare `pass`
  on its own exceptions. The embed-server watchdog block sits right next
  to it (same `try`/`except` pattern, same watchdog loop) but was not in
  this sub-task's scope (`core/daemon.py`'s three *model-loader* call
  sites specifically, not the adjacent embed-server watchdog block) and
  was left untouched — but it has the same class of problem: an
  exception there is silently swallowed with no log, same as the
  model-loader watchdog had before
  this sub-task's fix. Flagged for a future round; not fixed here.

### [NEW-89] A detached daemon-crash scenario can leave a `resource_gate` slot accounted for a process the daemon itself no longer knows about, with no current API to reconcile it

- **Status: Suspected** — `core/daemon.py`'s shutdown path's `finally`
  block is what calls `unload()`/releases the gate slot on a clean
  shutdown. If the daemon process dies without running that `finally`
  (e.g. `SIGKILL`, a crash that bypasses normal Python exception
  unwinding), the already-spawned llama-server process can be left
  running detached while the gate's residency record for it never gets
  released — a different leak shape than `NEW-82`'s "caller stays alive
  but doesn't release" case; this is "caller is gone entirely." PID-
  liveness reaping in `list_slots()`/`reserve_slot()` only helps if the
  slot's recorded `pid` is the daemon's own PID (per `NEW-81`, still
  deferred) — if it were ever set to the actual llama-server subprocess
  PID instead, reaping wouldn't fire at all since that process is still
  genuinely alive and doing real work. Reconciling this properly needs a
  `resource_gate.py` API addition (e.g. a way to detect and re-adopt an
  orphaned-but-still-running resident process) — out of scope for
  sub-task 3, and arguably contingent on how `NEW-81` eventually gets
  resolved, since the two are related.

### [NEW-90] `ModelLoader.load_primary()` increments an internal `_load_failures` counter on a gate-denied reservation, same as a genuine spawn failure — no current consumer distinguishes them, but a future one might mis-escalate

- **Status: Suspected, low severity** — found while adding outcome
  tracking (`LOAD_OUTCOME_*` constants) in sub-task 3. `_load_failures`
  (used elsewhere, e.g. for retry/backoff logic in code not touched by
  this sub-task) increments identically whether a load failed because
  the gate correctly denied it (expected, healthy behavior under real
  resource pressure) or because the actual spawn genuinely crashed
  (a real fault). No current consumer of `_load_failures` treats these
  differently, so this isn't causing a live bug today — but any future
  code that escalates or alerts based on `_load_failures` crossing a
  threshold would conflate "the gate is correctly protecting the device
  under load" with "something is actually broken." Fix direction: either
  don't increment `_load_failures` on a gate-denial outcome specifically
  (distinguishable now via the new `LOAD_OUTCOME_*` constants this
  sub-task added), or give gate-denial its own separate counter.

## Found while fixing `NEW-84` (stale model-path binding), 2026-08-09 — NOT fixed, logged only

### [NEW-91] `core/lora_import.py`'s `rollback_to_backup()`, secondary/planner branch, now newly reachable — overwrites the on-disk fine-tuned `.gguf` file in place with backed-up base weights, instead of resetting the config pointer back to the original base path

- **Status: Suspected** (design-quirk, not obviously a bug, but real
  data-loss-on-rollback behavior). Found by `code-reviewer` while
  reviewing `NEW-84`'s fix. `rollback_to_backup()`
  (`core/lora_import.py` ~L418-473) does `shutil.copy2(backup,
  original_path)`, where `original_path = cfg.PLANNER_MODEL_PATH` — after
  a successful swap, that now points at the fine-tuned file's path, not
  the pre-swap base path. So rolling back a secondary/planner swap
  overwrites the fine-tuned checkpoint file irrecoverably rather than
  just pointing the config back at the original base file. Functionally
  the outcome is still correct (the planner reloads base weights), but
  the fine-tuned artifact itself is destroyed in the process, with no
  way to get it back afterward.
- This exact pattern already existed for the **primary** branch before
  `NEW-84`'s fix (pre-existing, dormant) — not a new bug in that half.
  What's new: the **secondary** branch is newly *reachable* for the
  first time (previously dead due to a `SECONDARY_MODEL_PATH`/
  `PLANNER_MODEL_PATH` mismatch, compounded by `NEW-24`'s
  `AttributeError`), so this is genuinely new exposure created by fixing
  those two issues, not something that shipped with this round. Fix
  direction: `rollback_to_backup()` should restore the config pointer to
  the original base path rather than overwriting whatever file the
  pointer currently references — or, if overwriting-in-place is the
  intended rollback semantics, back up the fine-tuned file itself before
  overwriting it, so a rollback doesn't permanently destroy a checkpoint
  the user might want back.

### [NEW-92] `main.py`'s `args.init`/`args.tdd`/`args.fix` branches call `loader.load_primary()` unconditionally, with no `is_remote_backend()` guard — a remote-backend user still spawns a local 7B on these three paths (Confirmed by code read, found while wiring TODO.md 7.4 sub-task 5's gate-denial recovery path, not fixed)

- **Location:** `main.py`'s `args.init`/`args.tdd`/`args.fix` branches
  (each starts with `loader = get_loader(); ... loader.load_primary()`,
  now `_load_primary_with_gate_recovery(loader)` as of sub-task 5 — the
  gap predates and is untouched by that change). `repl()`, right above
  them, explicitly wraps its own equivalent call in
  `if not is_remote_backend(): ...`, but none of the other three do —
  found by direct comparison while touching all four call sites in this
  round.
- **Effect:** a user running with a remote backend configured
  (`CODEY_BACKEND`/`is_remote_backend()` true) who runs `codeyOS --init`,
  `--tdd`, or `--fix` still triggers a real local 7B load attempt (and,
  as of sub-task 5, a real resource-gate reservation / daemon
  release-and-retry dance on denial) that serves no purpose for a remote
  backend — wasted RAM/spawn time at best, a spurious failure/error
  message at worst if the local model file isn't even present on a
  remote-only setup.
- **Not fixed here** — out of this sub-task's scope (sub-task 5 is about
  the gate-denial recovery path on the CLI's existing four call sites,
  not about whether those call sites should fire at all under a remote
  backend). A real fix would wrap each of these three call sites in the
  same `is_remote_backend()` guard `repl()` already uses, but that's a
  small independent behavior change worth its own scoped task/review
  rather than folding it silently into this one.

*(A duplicate entry, originally NEW-93, was logged here for this exact
issue during this round — merged into `NEW-39`'s existing entry above
as a "Reconfirmed, 2026-08-09" note instead of kept as a second, separate
finding for the same bug. See `NEW-39`.)*

## Found while adding the test-only model-arch override to `core/resource_gate.py`, 2026-08-09 — NOT fixed, logged only

### [NEW-94] `tests/test_resource_gate.py::test_known_model_archs_resolved_by_path` has a stale name — it actually resolves by `model_id`, not by path (cosmetic, no behavior bug)

- **Status: Confirmed, cosmetic only.** Left over from the `NEW-84` fix
  that moved `KNOWN_MODEL_ARCHS` from path-keyed to `model_id`-keyed —
  the test's assertions were updated to match the new behavior at the
  time, but its name wasn't. No fix needed beyond a rename whenever
  someone's next in that file; not worth a standalone task.

## Found during first real on-device live-verification of TODO.md 7.4 (resource gate), 2026-08-09 — daemon started with substitute Qwen3-4B (`CODEY_TEST_PRIMARY_ARCH=qwen3-4b`) + substitute 0.5B planner (`CODEY_TEST_PLANNER_ARCH=qwen2.5-0.5b-planner`), NOT fixed, logged only

### [NEW-95] Substitute primary model (Qwen3-4B) is hard-rejected by `resource_gate`'s device ceiling at this project's real production `n_ctx` (32768) — the happy-path "model actually loads and occupies a slot" scenario could not be live-exercised at all with the requested substitute file

- **Status: Confirmed**, by direct live `can_admit()` call (no spawn) and
  by the daemon's own real preload/watchdog/CLI behavior, all agreeing.
  `utils/config.py:44`'s `MODEL_CONFIG["n_ctx"] = 32768` is the real
  value `core/loader_v2.py:296` passes to `llama-server -c` and
  `core/loader_v2.py:627` puts into the `ModelSpec` used for admission —
  there is no env override for `n_ctx`, so this is not a test artifact.
- Live numbers (`core/resource_gate.can_admit()`, real `/proc/meminfo`,
  `CODEY_TEST_PRIMARY_ARCH=qwen3-4b` set): substitute 4B cost estimate =
  7597552800 bytes (7246MiB) vs. device ceiling 6973867622 bytes
  (6651MiB, `DEVICE_CEILING_USABLE_FRACTION=0.60 * MemTotal`) →
  `hard_reject=True`. Cause: the substitute's real GGUF-header
  architecture (36 layers, 8 KV heads, head_dim 128) has a KV-cache
  footprint ~2.57x the production 7B's (28 layers, 4 KV heads, head_dim
  128) at the same `n_ctx` — so despite being a smaller-parameter,
  smaller-file model (2.50GB vs 4.68GB), its *total* estimated cost
  (7.60GB) at production `n_ctx` exceeds the *production 7B's* own
  estimated cost (6.83GB, computed cleanly with no arch-override
  contamination — see below) and the device ceiling both.
- For comparison, the production 7B itself at the same real `n_ctx`
  (32768, no substitution) was NOT hard-rejected: cost 6830557184 bytes
  (6514MiB) is under the 6973867622-byte (6651MiB) ceiling, but was
  soft-denied on this run's actual headroom (6514MiB * 1.25
  `REQUIRED_HEADROOM_FACTOR` = 8143MiB required vs. 4707MiB headroom
  available at that moment) — a real, correct, transient
  `LOAD_OUTCOME_GATE_DENIED`, not a hard denial. The 7B clears the
  ceiling by only 137MiB (6651-6514) on this device's real `MemTotal`,
  a much thinner margin than `resource_gate.py:171-172`'s own comment
  ("~6.4GiB... comfortably admits") implies — see NEW-97 below.
- **Practical effect on this task**: Stage 1's "does the daemon actually
  load the substitute primary through the full gate/slot-aware path and
  unload cleanly" could not be observed as a genuine load-then-unload
  cycle, because the substitute file was never admitted in the first
  place. What WAS observed and is real, useful verification: the gate
  correctly refuses to spawn `llama-server` on 8080 for a model whose
  real KV-cache shape doesn't fit, at every layer that was actually
  reached: the daemon's own startup preload/watchdog never got this far
  (blocked earlier by a different check — see NEW-96 below), but the
  CLI's direct `main.py --init` invocation (`loader.load_primary()`,
  which skips the sequential-swap eviction check `ensure_model()` does)
  DID reach `can_admit()` and reported the hard ceiling denial verbatim,
  with the exact byte figures (7246MiB / 6651MiB) matching this entry's
  offline `can_admit()` computation precisely — live confirmation the
  `CODEY_TEST_PRIMARY_ARCH` override was genuinely active inside a real
  load path, not just in an offline check.
- **Not fixed** — this is a real device/config interaction, not a code
  bug in the gate; flagged here because a future live-verification round
  aiming for a full load cycle will need either a genuinely smaller-KV
  substitute model, or a documented (not silently hand-edited) way to
  vary `n_ctx` for a test run, since `MODEL_CONFIG["n_ctx"]` has no env
  override today.

### [NEW-96] `core/daemon.py`'s startup preload / 30s watchdog never reach `resource_gate.can_admit()` for the primary model as long as `plannd` (the separate, bash-script-managed 1.5B/substitute planner on port 8081, started by `codeydOS start`/`codeydOS:280`) is running — a pre-admission "sequential-swap eviction" check fails first with `eviction_failed`, and the resulting log message ("will load on first request") is the exact false promise TODO.md 7.4 sub-task 3 was built to eliminate, just for a denial class that fix didn't cover

- **Status: Confirmed**, by direct live observation, `~/.codeyOS/codeyOS.log`
  (verbatim): `"Planner still answering on port 8081 after eviction
  attempt — not loading primary (would violate sequential-swap)"`
  followed by `"7B model pre-load failed (eviction_failed: could not
  confirm the planner (1.5B) freed its port before loading the primary
  (7B) — sequential-swap guard) — will load on first request"` at
  startup, then on each subsequent 30s watchdog tick (observed twice,
  ~65s apart): `"7B model not loaded (eviction_failed: ...) — attempted
  load, still not running"`.
- Root cause (by direct code read): both `core/daemon.py:805-845`
  (startup preload) and `:726-786` (watchdog) call
  `core/loader_v2.py:ModelLoader.ensure_model()`, whose cold-load branch
  (`:822-830`) calls `self._evict_planner_and_confirm_free()` at line 823
  and only reaches `load_primary()` (line 830, where `reserve_slot()`/
  `can_admit()` actually live) if that eviction check succeeds — so the
  sequential-swap eviction genuinely runs, and can genuinely block
  admission, BEFORE `can_admit()` is ever called, confirmed by reading
  `ensure_model()`'s body directly, not inferred from log strings alone.
  `ensure_model()`'s gate-aware outcome tracking has exactly three explicitly-handled
  denial branches — `LOAD_OUTCOME_GATE_DENIED_HARD`,
  `LOAD_OUTCOME_GATE_DENIED`, `LOAD_OUTCOME_DEFERRED` — plus a generic
  fallback for everything else. `eviction_failed` (the real outcome
  observed live) is NOT one of the three named constants, so both call
  sites fall through to their generic branch. The watchdog's generic
  branch (`:774`, "attempted load, still not running") is honest and
  fine. The startup-preload's generic branch (`:838-841`) is NOT: it
  unconditionally says **"will load on first request"** — the identical
  false-promise wording sub-task 3's own scope note (TODO.md 7.4
  sub-task 3, "7B model pre-load failed... would be a false promise
  under a denial") explicitly set out to eliminate for gate denials, but
  `eviction_failed` (a distinct pre-gate denial reached via the
  primary/planner sequential-swap guard, not `can_admit()` itself)
  wasn't in scope of that fix and still carries the old message.
- **Why this isn't cosmetic**: in the configuration actually exercised
  live (default `codeydOS start`, which always launches `plannd` as a
  separate always-on process on port 8081, per `codeydOS:239-309`),
  `eviction_failed` is not transient in practice — `plannd`'s
  llama-server is spawned directly by a bash `nohup` call, entirely
  outside `resource_gate`'s `reserve_slot()`/`register_slot()`
  accounting (see NEW-97 immediately below) and outside the daemon's own
  `release_model_slot` command's reach for that process. Nothing in a
  normal `codeydOS start` session will ever cause the primary to load on
  "first request" while `plannd` is up — the message is actively
  misleading for this device's actual default runtime shape, not just
  technically imprecise.
- **Fixed 2026-08-09** (`TODO.md` `U.27`). `core/daemon.py`'s startup
  preload (extracted into a new `_preload_primary_model()` method,
  mirroring the same extraction sub-task 3 already did for the watchdog)
  and the watchdog (`_watchdog_check_model()`) both now handle
  `LOAD_OUTCOME_EVICTION_FAILED` (a pre-existing `core/loader_v2.py`
  constant, not newly added) as a fourth explicitly-named outcome,
  correctly taking precedence over the generic "died"/fallback branch.
  Neither message now promises a retry will succeed. Code-reviewer
  approved, verifying the precedence ordering with a real test (a mocked
  server whose `is_running()` returns `False` — the exact condition that
  would otherwise fall into the "died" branch — confirming eviction-failed
  genuinely pre-empts it). 8 new tests (not 9, corrected per a reviewer
  note); full suite 501/501 passing. `NEW-97` (the actual architectural
  gap — `plannd` bypassing the gate's accounting entirely, which is *why*
  this denial class fires at all in the default runtime configuration —
  remains open, tracked separately as `U.28`).

### [NEW-97] `plannd` (`codeydOS:239-309`, the bash-script-managed planner daemon on port 8081, distinct from `core/planner_loader.py`'s gate-aware `PlannerLoader`) spawns `llama-server` directly via `nohup`, entirely bypassing `resource_gate.reserve_slot()`/`register_slot()` — the gate under-counts real resident RAM whenever `plannd` is running, on every subsequent admission decision

- **Status: Confirmed**, by direct live observation: after `codeydOS
  start` (which starts `plannd` unconditionally, no gate involvement),
  `ps aux` showed a live `llama-server` process on port 8081 (PID 15050,
  the substitute 0.5B `planner-codey.gguf`, ~757MB RSS observed), but
  `core/resource_gate.list_slots(reap_dead=False)` and `list_slots(reap_dead=True)`
  both returned only the `embed` slot (registered separately via
  `core/embed_server.py`'s `register_slot()`) — zero entries for
  `plannd`'s process, at any point during the whole live session.
- **Effect**: any future `can_admit()` call for the primary (or anything
  else) computes headroom from live `/proc/meminfo` `MemAvailable` minus
  `reserved_bytes` (declared, gate-tracked reservations only) — it has
  no way to know `plannd`'s real resident RAM is already spoken for
  beyond whatever `MemAvailable` already reflects at read time. In
  practice this mostly self-corrects because `MemAvailable` is a live
  kernel figure that already accounts for `plannd`'s actual RSS — but it
  means the gate's own residency model (`list_slots()`, the very
  structure TODO.md 7.4 sub-task 1 built to be "cross-process-aware") is
  silently incomplete for this specific, always-running process: nothing
  querying `list_slots()` for "what's resident and why" can see `plannd`
  at all, and nothing can ask the gate to admit/evict it since it was
  never `reserve_slot()`'d in the first place.
- Distinct from (but same general shape as) the already-logged
  `core/lora_import.py` bare-`pkill` issues and `NEW-83`'s embed-server
  fix — this is an accounting gap, not a process-kill-safety bug. Also
  distinct from `core/planner_loader.py`'s `PlannerLoader`, which IS
  gate-aware (`reserve_slot()`, confirmed via `release_model_slot`'s
  `model_id="planner"` routing in `core/daemon.py` — see that handler)
  — `plannd` (bash-script-launched, port 8081, always-on) and
  `PlannerLoader` (gate-aware, on-demand, same port) are two independent
  code paths that happen to target the same port, which is itself worth
  someone confirming isn't its own latent conflict (not confirmed as a
  bug here — out of this task's scope to chase further).
- **Not fixed** — found live, out of scope for this verification task.
  Fix direction: either route `plannd`'s startup through
  `core/planner_loader.py`'s existing gate-aware `PlannerLoader.load()`
  instead of a raw bash `nohup`, or have `codeydOS`'s `start_plannd()`
  call `resource_gate.register_slot()` directly (the same
  accounted-but-exempt pattern `core/embed_server.py` already uses)
  after confirming the process is up.

### [NEW-98] (Suspected, low severity — calibration-comment drift, not a code bug) `resource_gate.py:171-172`'s comment claims the production 7B's cost estimate "comfortably admits" under the 0.60 `DEVICE_CEILING_USABLE_FRACTION` ceiling — live measurement on this exact device shows a 137MiB margin (6651MiB ceiling vs. 6514MiB actual cost at production `n_ctx=32768`), not "comfortable"

- **Status: Suspected** (framing/comment accuracy issue, not incorrect
  behavior — the ceiling check still correctly admits the 7B by the
  actual numbers). Live-measured via `core/resource_gate.can_admit()`
  with a real `ModelSpec` matching `core/loader_v2.py`'s actual call
  site (`model_id="primary"`, real 7B file path,
  `n_ctx=MODEL_CONFIG["n_ctx"]=32768`, no arch override): cost estimate
  6830557184 bytes (6514MiB) vs. device ceiling 6973867622 bytes
  (6651MiB) — a 137MiB margin, i.e. the 7B clears the hard ceiling by
  ~2%, not the "comfortable" margin the comment (written when
  `DEVICE_CEILING_USABLE_FRACTION` was set) implies. Sub-task 1's own
  comment says the 0.60 value is "an un-calibrated first default... not
  confirmed against real on-device load behavior" — this is exactly
  that calibration check, now done, showing the margin is thin.
- **Not fixed** — flagging for whoever next tunes
  `DEVICE_CEILING_USABLE_FRACTION`/`REQUIRED_HEADROOM_FACTOR` against
  real behavior, per that comment's own stated intent; no action needed
  unless the margin's thinness is itself judged a problem (e.g. minor
  `MemTotal` reporting variance across boots could flip the 7B from
  admitted to hard-rejected).

### [NEW-99] (Suspected, same class as `NEW-83`) `codeydOS:151` and `codeydOS:261` use pattern-based `pkill -9 -f "llama-server.*8080"` / `"llama-server.*8081"` to clear orphaned processes before starting the main daemon / `plannd` respectively

- **Status: Suspected** — port-scoped (not a bare `pkill -f llama-server`,
  so less severe than the bug `NEW-83`/commit `09aec66` already fixed in
  `core/embed_server.py`), but still a pattern-based process kill rather
  than a specific tracked PID, the exact class CLAUDE.md rule 3 and this
  project's history (the original blanket-`pkill` incident) both warn
  against. Not confirmed to have caused a real incident here — flagged
  because it's the same code shape already fixed once elsewhere in this
  project, not because it fired incorrectly during this session.
- **Not fixed** — pre-existing code, out of this live-verification
  task's scope to touch.
- **Status: PARTIALLY CLOSED, 2026-08-23.** M1-D deleted `codeydOS`'s
  `start_plannd()` entirely, taking `codeydOS:261`'s
  `pkill -9 -f "llama-server.*8081"` with it — that half of this finding
  is closed by direct code read (confirmed: no `8081` string remains in
  `codeydOS`). `codeydOS:151`'s `pkill -9 -f "llama-server.*8080"` (and
  the other 8080-pattern `pkill` sites `NEW-103` also names) remain and
  stay open under this finding number.

## Found while fixing U.28/NEW-97 (registering `plannd` with the gate), 2026-08-09 — NOT fixed, logged only

### [NEW-100] `core/daemon.py`'s `release_model_slot` handler for `model_id="planner"` can report `already_unloaded` while `resource_gate.list_slots()` simultaneously shows a RESIDENT `"planner"` slot actually holding real memory — a contradiction newly *observable* now that `plannd` has any gate presence at all

- **Status: Confirmed by design, not yet a live-observed failure.** The
  `release_model_slot` handler operates on the in-process
  `PlannerLoader` singleton (`core/planner_loader.py`), which — per that
  handler's own pre-existing docstring — usually isn't the process
  actually holding `plannd`'s slot, since `plannd` is a separate,
  bash-`nohup`-launched process (see `NEW-97`, now fixed for
  registration/accounting but not for this). Before `U.28`'s fix,
  `plannd` had zero gate presence, so there was nothing to contradict.
  Now that `codeydOS`'s `start_plannd()` registers a RESIDENT
  `"planner"` slot for the real process, a caller using
  `release_model_slot(model_id="planner")` to try to free planner memory
  can be told "nothing to free" (`already_unloaded`, correct from the
  in-process loader's own point of view) while the gate's own residency
  store still shows real memory held by `plannd`, unaffected.
- **Not fixed** — out of `U.28`'s scope (that task's job was making
  `plannd` visible to the gate, not reconciling two independent code
  paths that both claim the `"planner"` role). Fix direction: either
  make `release_model_slot`'s handler aware of `plannd`'s registered
  slot too (e.g. check `resource_gate.list_slots()` for a RESIDENT
  `"planner"` entry not owned by the in-process loader, and report
  accurately that a release isn't possible via this command for a
  gate-visible-but-not-loader-owned process), or clarify in that
  handler's docstring/response that it can only ever affect the
  in-process loader's own model, never `plannd`.
- **Status: CLOSED, 2026-08-23.** M1-D deleted `core/planner_loader.py`
  (the `PlannerLoader` singleton this finding is about) and `plannd` as a
  separate process entirely — there is no longer a second, bash-`nohup`
  process holding an independent `"planner"` gate slot for
  `release_model_slot` to disagree with. The contradiction this finding
  described requires two independent code paths both claiming the
  `"planner"` role; only one exists now. Confirmed by direct code read.

### [NEW-101] (Suspected, low severity, bounded) A `plannd` crash without `stop_plannd()` running (e.g. OOM-killed) leaves its RESIDENT gate slot un-released until the next reap; the following `start_plannd()` registers a second `"planner"` slot before that happens

- **Status: Suspected**, bounded impact — RESIDENT slots are excluded
  from `total_reserved_bytes()`'s admission-relevant sum (see `NEW-100`
  above), so this doesn't affect admission math, and the dead slot
  self-heals via existing PID-liveness reaping (`reap_dead=True`) the
  next time anything calls `list_slots()`/`reserve_slot()` elsewhere.
  In the meantime it's duplicate-registration noise in `list_slots()`'s
  observability output, not a resource leak in the RAM-usage sense.
- **Not fixed** — out of `U.28`'s scope. Fix direction, if the gate's
  observability accuracy matters enough to warrant it: dedupe on
  `(model_id, port)` at registration time in `start_plannd()` — release
  any existing `"planner"` slot on port 8081 before registering a new
  one, rather than relying solely on eventual reap.
- **Status: CLOSED, 2026-08-23.** M1-D deleted `codeydOS`'s
  `start_plannd()`/`stop_plannd()` entirely — there is no longer a
  separate `plannd` process to crash without releasing its slot, and no
  port-8081 registration path left to duplicate. Confirmed by direct
  code read.

## Found during `code-reviewer`'s pass on `U.31` (`CODEY_N_CTX` override), 2026-08-09 — NOT fixed, logged only

### [NEW-102] `main.py`'s `--ctx` CLI flag never actually reaches `core/memory_v2.py`'s `CTX_TOTAL` — import order means the module-level constant is always bound before the flag is applied; the flag also lacks the positive-value validation the new `CODEY_N_CTX` env var has

- **Status: Confirmed** (upgraded from the implementer's original
  "Suspected" — `code-reviewer` traced the actual import chain rather
  than reasoning about it abstractly). `main.py:9` (`from core import
  context as ctx`, module-level) imports `core/context.py:11`
  (`from core.memory_v2 import memory as _mem`, also module-level),
  which executes `core/memory_v2.py:38`'s `CTX_TOTAL =
  MODEL_CONFIG["n_ctx"]` — all of this runs at Python import time,
  before `main.py:113`'s `config.MODEL_CONFIG["n_ctx"] = args.ctx` (the
  actual `--ctx` flag handling) ever executes. `CTX_TOTAL` is therefore
  always bound to whatever `n_ctx` was before `--ctx` was applied — the
  flag has no effect on `memory_v2.py`'s notion of total context, only
  on whatever reads `MODEL_CONFIG["n_ctx"]` live afterward
  (`core/summarizer.py`, `core/tokens.py`, which re-read the dict on
  each call rather than caching it at import time).
- **Second, related gap**: `main.py:37`'s `--ctx` argument (`type=int`)
  has no positive-value guard — unlike the new `CODEY_N_CTX` env var
  (`utils/config.py`, `U.31`), which explicitly rejects zero/negative
  values because they'd flow into `resource_gate.py`'s KV-cache cost
  estimate as a zero/negative term and cause the gate to under-estimate
  real cost (verified: a negative `n_ctx` actually *subtracts* from the
  computed cost, a real over-admit risk, not just a milder zero-case).
  `--ctx 0` or `--ctx -1` on the command line hits this same door,
  unvalidated.
- **Not fixed** — found and confirmed during `U.31`'s review, explicitly
  out of that task's scope (which was adding the `CODEY_N_CTX` env-var
  override, not auditing every existing `n_ctx` mutation path). Fix
  direction: either make `core/memory_v2.py`'s `CTX_TOTAL` a live
  re-read (matching `summarizer.py`/`tokens.py`'s pattern) instead of an
  import-time constant, or move `--ctx`'s handling earlier in `main.py`
  before `memory_v2` is imported; separately, add the same
  positive-value guard `CODEY_N_CTX` already has to `--ctx`'s argparse
  definition or its handling at `main.py:113`.
- **Cross-reference (2026-08-11, project-architect consolidation pass):**
  `TODO.md`'s 7.4b sub-task C ("coder interactive-vs-daemon context
  branching") already has an implementer touching exactly this code —
  `main.py`'s `--ctx`/n_ctx call sites and `core/loader_v2.py:
  load_primary()`'s `MODEL_CONFIG.get("n_ctx", ...)` read — to wire the
  new interactive/background context branch. Pick up this finding's
  fix (both the `CTX_TOTAL` import-order gap and the missing
  `--ctx` positive-value guard) alongside that sub-task's implementation
  rather than as a separate future round. See `TODO.md` 7.4b sub-task C
  for the matching note.
- **Status: RESOLVED, 2026-08-13.** Sub-task C's own first pass had, in
  fact, reintroduced this exact trap for two NEW values
  (`PLANNER_N_CTX`/`CODER_BACKGROUND_N_CTX`) instead of closing the
  original `CTX_TOTAL` instance — caught by cloud ultrareview as
  `bug_002` on that sub-task's own landing, not by this consolidation
  note. Real fix, not a re-log: `CTX_TOTAL`,
  `PLANNER_N_CTX`, and `CODER_BACKGROUND_N_CTX` all converted from
  import-time constants to functions (`get_ctx_total()`,
  `get_planner_n_ctx()`, `get_coder_background_n_ctx()`) that re-read
  `MODEL_CONFIG["n_ctx"]` live; `main.py`'s `--ctx` handling changed to
  `if args.ctx is not None:` with an explicit `ValueError` on
  `args.ctx <= 0`. Confirmed as a real regression, not just a gap:
  baseline `163b5e5`'s `core/planner_loader.py:88` read
  `MODEL_CONFIG.get("n_ctx", 4096)` live, so `--ctx` reached the planner
  before sub-task C's first (constant-based) pass and stopped reaching
  it after — this fix restores that and extends it to the new
  background-coder ceiling too. 4 new regression tests added to
  `tests/test_74b_planner_and_coder_n_ctx.py` (12/12 passing), including
  one that calls `main.apply_overrides()` directly with a fake `--ctx`
  and asserts both `get_planner_n_ctx()`/`get_coder_background_n_ctx()`
  follow it — the check that would have caught this the first time.
  Verification tier: code complete, unit-verified — no live model load
  needed (default-path numbers are unchanged by this fix, only the
  `--ctx`-override path's behavior changed). See `TODO.md` 7.4b
  sub-task C for the full resolution note.

## Found during live-verification of `TODO.md` 7.4 (resource gate happy-path round 2), 2026-08-09 — NOT fixed, logged only

### [NEW-103] `codeydOS`'s `start_plannd()` / `stop_daemon()` kill llama-server by bare name pattern (`pkill -9 -f "llama-server.*8081"` / `"llama-server.*8080"`), the exact anti-pattern CLAUDE.md rule 3 forbids

- **Status: Confirmed** — direct code read (`codeydOS:261` inside
  `start_plannd()`; `codeydOS:203,212,224,233` inside `stop_daemon()`)
  plus live confirmation during this round: `stop_daemon()`'s
  `pkill -9 -f "llama-server.*8080"` is what actually cleaned up an
  orphaned primary-model `llama-server` process this round (PID 26007,
  spawned by a `main.py --init` CLI invocation and left running
  intentionally for the daemon to adopt — see `NEW-104` below) — not
  any PID-tracked kill path. It worked here because the pattern
  happened to match only the intended target, but it is the same class
  of bug CLAUDE.md rule 3 cites as having already caused a real
  incident on this project (a blanket `pkill -f llama-server` killing
  unrelated model servers). Any process whose command line happens to
  contain `llama-server.*8080`/`llama-server.*8081` — including a
  future second Codey-OS instance, a manual debug invocation, or an
  unrelated tool — would be silently killed by these calls.
- **Not fixed** — out of this live-verification round's scope (verification-only, per this round's instructions). Fix direction: track
  each spawned server's PID at spawn time (`plannd.pid`, and a new
  equivalent PID file/lookup for whatever `llama-server` ends up
  running on 8080, including ones adopted via `core/loader_v2.py`'s
  "reuse an existing server" branch) and kill only that specific PID,
  matching the discipline `core/daemon.py`'s own `check_pid_file()`/
  `resource_gate.py`'s `_pid_alive()` already use elsewhere in this
  codebase.
- **Addendum, 2026-08-26 (scope extension, same finding, different
  file):** the real `codey-start` entry point's teardown script,
  `codey-stop`, has the identical anti-pattern in a form this entry
  didn't previously name. `codey-stop:38` runs bare
  `pkill -9 -f "llama-server" 2>/dev/null || true` — not even
  port-scoped like `codeydOS`'s `8080`/`8081` patterns, the single
  broadest form CLAUDE.md rule 3 forbids outright. `codey-stop:34`
  (`pkill -9 -f "gui/server.py"`) is the same class for the GUI
  process. Found live during this round's `codey-start`/`codey-stop`
  full-stack verification pass (see `NEW-195`/`NEW-196`): teardown that
  round required manually `kill -TERM`-ing three stuck TUI-side PIDs
  first, then running `codey-stop`, whose blanket `pkill` calls were
  verified safe *in that specific instance only* by confirming a clean
  pre-launch baseline (`ps aux | grep llama-server` empty, so nothing
  foreign could have been hit that run) — not because the code itself
  is safe in general. Recorded here rather than as a new ID because it
  is the same defect shape this entry already tracks, just a second
  call site in a second file; `codey-stop:34,38` should be fixed
  together with `codeydOS`'s sites whenever this is picked up.

### [NEW-104] `resource_gate.reserve_slot()`/`register_slot()` slots are keyed to the *calling process's* PID, never the spawned `llama-server` child's PID/port — causes premature reaping when a short-lived `main.py` CLI process loads/adopts a model while the daemon is running, and a mirror stale-slot risk on the daemon's own side

- **Status: Confirmed**, live-reproduced this round (the CLI-side
  premature-reaping half; the daemon-side stale-slot half is a direct
  code-read consequence of the same root cause, not separately
  reproduced this round — see below for what's directly observed vs.
  inferred). Sequence observed: (1) with the daemon already holding a
  `"primary"` slot, `main.py --init` was gate-denied, asked the daemon
  to `release_model_slot`, the daemon stopped its own copy and released
  the slot; (2) the CLI's retried `load_primary()` spawned a *new*
  `llama-server` (PID 26007) and called `resource_gate.reserve_slot()`
  with the default `pid=os.getpid()` — i.e. the **CLI's own,
  short-lived** PID, not the spawned child's PID
  (`core/loader_v2.py:629`, `rg.reserve_slot(spec)` with no `pid=`/
  `port=` override — the same call site, not just the CLI's usage of
  it); (3) `main.py`'s `shutdown()` (`main.py:242-274`) deliberately
  does *not* unload/release when a daemon is running (correct — the
  model should stay up for the daemon to use), so the CLI process
  exits with the slot still owned by its own now-dead PID.
  **Directly observed**: at that point `resource_gate.list_slots()`
  showed zero `"primary"` entries while `ps` confirmed `llama-server`
  PID 26007 was still running, healthy, and consuming ~4.4GB RSS — a
  real, resident, healthy model the gate's own accounting is blind to.
  **Inferred, not directly observed**: the CLI's own slot registration
  in step (2) — `list_slots()` was not queried while the CLI process
  was still alive, so its existence is inferred from `reserve_slot()`
  having returned `admitted=True` on the successful retry, not
  observed directly in the store. The daemon's own subsequent watchdog
  tick correctly avoided a double-spawn (its `load_primary()` detected
  the port already answering and took the existing "reuse an existing
  server" branch, per `core/loader_v2.py:679-694`), but that reuse
  branch does not register a replacement slot either — it explicitly
  releases its own fresh reservation instead (by design, to avoid
  double-accounting) — so no code path ever re-establishes gate
  visibility for this now-daemon-adopted model.
- **Root cause is broader than the CLI case**: this is not specific to
  `main.py`. The *daemon's own* slot for a model it spawns itself has
  the identical shape — e.g. this round's daemon-spawned slot read
  back as `{'model_id': 'primary', 'cost_bytes': 3067704480, 'pid':
  21550, 'port': None, ...}` — `pid: 21550` is the **daemon process**,
  not `llama-server` child PID 21908, and `port` is `None` (never
  passed at the `core/loader_v2.py:629` call site either). This is the
  mirror failure mode: if `llama-server` dies unexpectedly while the
  daemon process itself keeps running, the slot has no way to be
  reaped (the daemon PID is still alive) and would persist as
  `RESIDENT` forever with nothing to correct it, and the slot isn't
  discoverable by port (`port: None`) either. `register_slot()`'s own
  docstring already anticipates the correct usage: *"callers may pass a
  different PID if the actual model server subprocess's PID is known
  and different from the caller's own (e.g. the daemon registering on
  behalf of a spawned llama-server)"* — the API supports this; neither
  call site in `core/loader_v2.py` actually uses it.
- **Impact is observability/accounting, not admission-safety**: the
  live headroom check in `can_admit()` reads real `/proc/meminfo`
  (`MemAvailable`) directly, which already reflects a resident
  process's true RAM cost regardless of
  `list_slots()`/`total_reserved_bytes()` — so this round did not find
  a case where the gate over-admitted because of this gap. The risk is
  that anything relying on `list_slots()`/`total_reserved_bytes()` to
  know "is a primary model genuinely resident right now" (current or
  future code) would incorrectly conclude none is (CLI-handoff case) or
  incorrectly conclude one still is after it's actually died
  (daemon-side stale-slot case).
- **Not fixed** — found live during this verification round, out of
  its scope. Fix direction: at both `reserve_slot()`/`mark_resident()`
  call sites in `core/loader_v2.py` (and the equivalent in
  `core/planner_loader.py`), once the actual server child PID is known
  (`self._server.process.pid`) and its port is known, update the slot's
  `pid`/`port` fields to the real spawned process — not the caller's
  own PID — before or when marking it `RESIDENT`. This alone would also
  make the "reuse an existing server" branch capable of re-registering
  a `RESIDENT` slot for the adopted process (mirroring how
  `codeydOS`'s `start_plannd()` already does an unconditional
  `register_slot(..., status=RESIDENT, pid=<child PID>, port=8081)` for
  the process it spawns outside the gate-aware loader path) — fixing
  the reuse branch alone, without fixing the underlying pid/port
  binding, would leave the daemon-side stale-slot mirror case broken.

### [NEW-105] `core/loader_v2.py`'s `confirm_resident_and_mark_slot()` resident-confirmation window (10s, 0.5x cost threshold, `MemAvailable`-delta based) did not confirm a genuine, correctly-sized, successful primary-model load this round — fell through to the "mark resident anyway" timeout fallback every time

- **Status: Confirmed**, live-reproduced on both admitted loads this
  round (the daemon's startup-adjacent watchdog-tick load, and,
  implicitly, the CLI's retried load). Log line, verbatim:
  `resource_gate: could not confirm a MemAvailable drop for slot
  231dc93a1adb46589557745fdb5ec0ed within 10.0s (threshold 1463MiB) —
  marking resident anyway rather than leaving it permanently PENDING`.
  This fired on a load that was NOT actually a failure — `ps` showed
  `llama-server` PID 21908 at RSS 3062140 KB (~2.99GB) immediately
  after, matching the gate's own cost estimate (2926MiB) almost
  exactly — yet the confirmation mechanism never saw the drop it was
  looking for (`CONFIRM_RESIDENT_FRACTION=0.5` × 2926MiB ≈ 1463MiB
  required `MemAvailable` drop within `CONFIRM_RESIDENT_TIMEOUT_S=10.0`
  seconds) and fell through to its own documented "mark resident
  anyway" fallback instead of a true positive confirmation.
- **Likely cause** (reasoned from the observed numbers, not separately
  instrumented this round): `core/loader_v2.py`'s own file-header
  comment already flags `mmap`'d weights as paged in over time rather
  than all at once, and pages that were already resident in the page
  cache before this load (or reclaimed/paged back in from swap) don't
  necessarily show up as a `MemAvailable` drop the same way fresh
  anonymous allocation would — `MemAvailable` is a kernel estimate of
  reclaimable memory, not a 1:1 mirror of any one process's RSS. A
  `MemAvailable`-delta-based signal appears to be the wrong shape for
  confirming an `mmap`-backed load's residency, even though it's a
  real, successful, correctly-estimated load by every other measure
  available this round (RSS match to the cost estimate).
- **Consequence of the fallback, not a masked failure**: per this
  function's own docstring, the fallback correctly avoids the worse
  failure mode (a permanently-PENDING slot double-counting a
  genuinely-loaded model's cost) — so this is not a safety regression
  this round found. But it does mean the confirmation mechanism's
  *actual* job (distinguishing "genuinely landed" from "not yet
  landed, still declared cost") never executed successfully on either
  observed load, which is exactly the retuning trigger
  `core/loader_v2.py:99-103`'s own comment names: *"uncalibrated first
  defaults reasoned from NEW-21's swap-growth observation... retune
  against real observed load behavior once this is live-verified"* —
  this round is that live verification, and the result is a 0-for-2
  confirmation rate on this device, not a confirmed-working mechanism.
- **Not fixed** — found live during this verification round, out of
  its scope. Fix direction: retune the signal, not just the numbers —
  consider a process-RSS-based confirmation (`/proc/<pid>/status`
  `VmRSS`, matching the ~2.99GB observed here almost exactly against
  the 2926MiB estimate) instead of/alongside a system-wide
  `MemAvailable` delta, since RSS is a direct per-process measurement
  that isn't confounded by other processes' concurrent page-cache
  activity the way a system-wide `MemAvailable` reading is.
- **Update, 2026-08-11 (TODO.md 7.4a sub-task D3, docs/comment-only —
  not resolved, sharpened context only)**: with `core/resource_gate.py`'s
  swap-assisted admission (sub-task C2) now code-complete, this gap's
  severity changes shape. A swap-assisted admission is, by definition,
  one the device's live `MemAvailable` alone was NOT enough to satisfy —
  so a larger share of a swap-assisted load's pages landing in swap
  (rather than fresh anonymous RAM) makes the `MemAvailable`-delta this
  function polls for even less likely to appear within `timeout_s` than
  it already is on today's plain-RAM path, where it has never once fired
  (0-for-2 above). This is reasoning from the mechanism's own shape, NOT
  a new live measurement — no swap-assisted load has actually been run
  through this confirmation path yet (that's sub-task E, still pending,
  deliberately deferred past D). Practical effect either way: the
  "mark resident anyway" fallback already exists and is already the
  observed behavior on every path tested so far, so this is not a new
  blocking bug — just a sharpened expectation that sub-task E's live pass
  should explicitly capture whether this path ever fires under
  swap-assisted admission, rather than assuming today's 0-for-2 rate
  simply carries over unchanged. See `core/loader_v2.py`'s
  `confirm_resident_and_mark_slot()` docstring for the same note in code.

### [NEW-106] `core/observability.py`'s `State.temperature` property returns the LLM sampling temperature (`MODEL_CONFIG["temperature"]`, default 0.2), not device CPU/SoC temperature — a naming collision that will silently produce a wildly wrong thermal reading for any caller that expects "observability's temperature" to mean device heat

- **Status: Confirmed** by direct code read, `core/observability.py:114-117`:
  `@property def temperature(self) -> float: """Get current temperature
  (from model config)."""; return MODEL_CONFIG.get("temperature", 0.2)`.
  Found while scoping TODO.md 4.1 (daemon control redesign /
  `PENDING_ISH_DECISIONS.md` item 2), which folds in item 4
  (`core/observability.py`'s wrap) specifically because the new
  resource-gating logic needs real CPU/mem/temp/queue-depth
  introspection — this property returns 0.2 regardless of actual
  device state, which would silently defeat any thermal gate built on
  top of it without a caller happening to notice the value never
  changes.
- **Not fixed** — out of this scoping pass's scope (read-only
  investigation, no code changes made). The real device-temperature
  accessors already exist and are correctly named:
  `core/thermal.py`'s `get_current_temp_c()` /
  `ThermalManager.get_current_temp_c()` (built in 7.4 sub-task 1) and
  `core/resource_gate.py`'s `read_current_temp_c()`. 4.1's
  implementation must source thermal state from one of those, never
  from `observability.State.temperature` — flagged explicitly in the
  4.1 sub-task A handoff below so this isn't rediscovered mid-build.

### [NEW-107] `core/observability.py`'s `State.cpu_usage` and `State.memory_usage` report this process's own per-process figures (`psutil.Process(os.getpid())` / `/proc/<pid>/status` `VmRSS`), not system-wide CPU% or RAM headroom — same "sounds like a system reading, isn't one" shape as `NEW-106`, on the two other signals 4.1's resource gating needs

- **Status: Confirmed** by direct code read, `core/observability.py:147-155`
  (`cpu_usage`, via `self._process.cpu_percent()`) and `:124-145`
  (`memory_usage`, via `self._process.memory_info()`/`/proc/<pid>/status`
  fallback) — both scoped to `os.getpid()`, i.e. whatever process
  imports `observability` (the daemon, a CLI invocation, a test), never
  the whole device. TODO.md's 7.4 entry already flagged this exact
  pattern for observability's memory figure specifically ("per-process
  RSS, not system headroom") when sourcing 7.4's own gate signals;
  this generalizes the same finding to `cpu_usage` and confirms it's
  still true as of this round.
- **Not fixed** — out of this scoping pass's scope. Real system-wide
  signals already exist and should be reused rather than duplicated:
  `core/resource_gate.py`'s `read_meminfo()`/`compute_headroom_bytes()`
  for RAM, and `core/sysmon.py`'s `SystemMonitor` (`/proc/stat`-delta
  CPU%, already used by the TUI) for system-wide CPU — `sysmon`'s
  sampler thread is never started by the daemon today, which is itself
  part of 4.1 sub-task A's scope (a rolling sampler, not a cold
  instantaneous read, since `/proc/stat` CPU% requires two samples over
  time).

## Found during Track 3 Phase 5a / 7.4 sub-task A (rolling CPU sampler + resource snapshot + `/status` wiring), 2026-08-09 — NOT fixed, logged only

### [NEW-108] `/proc/stat` (and `/proc/uptime`, `/proc/loadavg`) are `Permission denied` for a non-root Termux process on this specific device/Android build — `core/sysmon.py`'s pre-existing `_read_cpu_proc()` (and now `core/resource_gate.py`'s new rolling CPU sampler, built to the same `/proc/stat`-delta approach per this sub-task's own spec) silently return `0.0` for CPU% unconditionally, with no way to get a real reading unless `psutil` is installed (it currently is not)

- **Status: Confirmed** by direct on-device reproduction, independent of
  any code from this sub-task:
  ```
  $ cat /proc/stat
  cat: /proc/stat: Permission denied
  $ cat /proc/uptime
  cat: /proc/uptime: Permission denied
  $ cat /proc/loadavg
  cat: /proc/loadavg: Permission denied
  $ python3 -c "from core.sysmon import SystemMonitor; m = SystemMonitor(); print(m._read_cpu_proc())"
  0.0
  $ python3 -c "import psutil"
  ModuleNotFoundError: No module named 'psutil'
  ```
  `core/resource_gate.py`'s new `sample_cpu_percent()`/`get_current_cpu_percent()`
  hit the identical `PermissionError` from the identical `open("/proc/stat")`
  call (this sub-task's spec explicitly required reusing `core/sysmon.py`'s
  existing `/proc/stat`-delta approach rather than inventing a different
  one). **Correction (code-review, 2026-08-09):** this entry originally
  claimed the two functions "correctly log-and-degrade to `0.0` rather than
  raising or silently returning a wrong non-zero value" — that overclaimed;
  `0.0` is itself a wrong value in this situation, indistinguishable from a
  genuinely idle reading when it actually means "couldn't measure," which
  is the dangerous direction for a signal later consumed by dispatch gating
  (sub-task C) and a >90%-CPU shutdown tripwire (sub-task D). This has now
  been fixed in the same round: `sample_cpu_percent()`/
  `get_current_cpu_percent()`/`ResourceSnapshot.cpu_percent` all return/type
  `Optional[float]`, returning `None` (not `0.0`) whenever the read fails or
  is otherwise unmeasurable — matching the existing `Optional[...]`/`None`
  pattern this same snapshot already used for `temperature_c`/
  `battery_percent`. Confirmed live via `python main.py --status`, which
  printed
  `⚠  resource_gate: cold-start CPU sample failed, treating as unavailable: [Errno 13] Permission denied: '/proc/stat'`
  and now `"resources": {"cpu_percent": null, ...}`.
- **Impact:** on this device, system-wide CPU% is not obtainable via the
  `/proc/stat` approach at all — not a bug introduced by this round, but a
  pre-existing limitation of `core/sysmon.py`'s CPU-reading strategy that
  this round's rolling sampler (built to the same approach, per its own
  spec) necessarily inherits. `core/resource_gate.py`'s CPU% signal will
  read `None` on this device today regardless of actual load (previously
  read a misleading `0.0`, now fixed per the correction above); the RAM,
  temperature, queue-depth, and battery signals in the same snapshot are
  unaffected and read real values (confirmed in the same `--status` run:
  `ram_headroom_bytes`, `temperature_c: 37.0`, `battery_percent: 74` all
  populated). 7.4 sub-task D's planned 20-minute sustained->90%-CPU
  tripwire (Track 3 Phase 5a) cannot fire on this device as specified
  until the underlying `/proc/stat` permission restriction is resolved —
  its CPU leg would never see a real reading to trip on (it will now
  correctly see `None`/"unmeasurable" rather than a misleading `0.0`,
  which at least prevents it from misreading "unmeasurable" as "idle").
- **Not fixed** (the underlying `/proc/stat` permission restriction) — out
  of this sub-task's scope (signal-sourcing/wiring only, no new
  CPU-reading strategy). Two directions worth considering
  when this is picked up: (1) install `psutil` (`pip install psutil`) and
  confirm whether it can obtain CPU% on this device through a different
  syscall path than a direct `/proc/stat` open (untested this round —
  `psutil` is not currently installed, and adding it wasn't in this
  sub-task's scope); (2) if `psutil` hits the same restriction, some other
  Android-specific CPU-load signal (e.g. `dumpsys cpuinfo` via
  `termux-api`/`sh -c`, similar in shape to the `termux-battery-status`
  fallback this same sub-task's battery signal already depends on) would
  need to be evaluated as a replacement/supplement to the `/proc/stat`
  approach specifically for this class of device.

### [NEW-109] `main.py --status` (this sub-task's new CLI wire-up) surfaces two pre-existing `core/observability.py` bugs to a user-facing command for the first time: `daemon.pid` is `null` while `daemon.uptime_seconds` simultaneously reports a large non-zero value, and `memory.usage`/`health.memory_usage` report the *CLI process's own* RSS, not the daemon's

- **Status: Confirmed** by direct live output, `python main.py --status`
  run with no daemon running:
  ```
  "daemon": {
    "pid": null,
    "uptime_seconds": 3713
  },
  ...
  "memory": {
    "usage": { "rss_mb": 38.9, "vms_mb": 0 },
    ...
  }
  ```
  Root cause (by code read): `State.daemon_pid` (`core/observability.py`)
  returns `self._process.pid` only when `HAS_PSUTIL` is true; `psutil` is
  not installed on this device (see NEW-108), so `self._process` is
  `None`, the attribute access raises `AttributeError`, and the broad
  `except (ImportError, AttributeError, TypeError, ValueError)` swallows
  it back to `None` — silently, with no indication anywhere in the output
  that this is "psutil absent" rather than "no daemon running".
  Meanwhile `State.uptime` reads `daemon_started_at` directly from the
  SQLite state store, which is stale from a previous daemon run and never
  cleared, so it keeps reporting an old uptime figure indefinitely after
  that daemon has exited. `State.memory_usage`/`State.cpu_usage` are the
  same per-process (`os.getpid()`) figures NEW-107 already flagged —
  this finding just notes that wiring `status()` to a real CLI command
  (this sub-task's own change) is what makes that pre-existing confusion
  reachable by a user for the first time, not something introduced by
  this round's `get_resource_snapshot()` addition (which reports true
  system-wide figures alongside it, under a separate `"resources"` key,
  specifically to give a correct point of comparison).
- **Not fixed** — out of this sub-task's scope (`--status` was required
  to be display-only, wiring an existing `status()` method, not a bug-fix
  pass over `core/observability.py`'s own logic). Flagging per CLAUDE.md
  rule 8.

### [NEW-110] `tests/test_new19_patch_failed_repeat_escalation.py` calls real, unmocked `git status`/`git diff` against the live repo and hits a genuine interactive `confirm()` prompt whenever the working tree has any uncommitted changes — 3 spurious failures/hangs under pytest's captured stdin, unrelated to whatever change actually dirtied the tree

- **Status: Confirmed** by code-reviewer during Phase 4.1 sub-task A's
  review, via bisection: the full test suite is green on a clean working
  tree, and the same 3 tests in
  `tests/test_new19_patch_failed_repeat_escalation.py` start
  failing/hanging as soon as ANY file (not specific to sub-task A's own
  changes) is modified and left uncommitted — the tests are exercising
  real `git status`/`git diff` output against whatever the actual repo
  state happens to be, and that code path includes an interactive
  `confirm()` call that pytest's captured stdin can't answer, so it hangs
  rather than failing cleanly.
- **Impact:** any task's working tree being dirty at test-run time
  (normal mid-task state — uncommitted changes are the expected condition
  right up until a commit) produces 3 spurious failures in this file that
  have nothing to do with the actual change under test, and can look like
  a real regression to whoever is running the suite.
- **Not fixed** — out of scope for Phase 4.1 sub-task A (a pre-existing
  test-design flaw: this file should mock `git status`/`git diff`
  and the `confirm()` call rather than depending on live repo/tree state
  at all). Flagging per CLAUDE.md rule 8.
- **Cross-reference (2026-08-11, project-architect consolidation
  pass):** this is the same underlying bug as `NEW-39` (first logged
  2026-07-30, reconfirmed 2026-08-09) — identical 3 tests, identical
  `check_git_and_offer_commit()`/`git_status_paths()`/`confirm()` call
  chain, identical dirty-tree trigger. Not merged into `NEW-39` since
  both already exist as separate entries, but should be fixed together,
  once, in `tests/test_new19_patch_failed_repeat_escalation.py`. No
  currently open/upcoming `TODO.md` item's stated scope covers repairing
  this existing flaky/hanging test (`U.20`/`U.21` cover lint backlog and
  *missing* coverage, not this) — stays open and unattached pending a
  dedicated pickup.

## Found while implementing Phase 4.1 sub-task B (interactive-session TUI+GUI signal), 2026-08-10 — NOT fixed, logged only

### [NEW-111] `gui/server.py`'s module-level `PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("CODEY_GUI_PORT", "8888"))` reads `sys.argv[1]` unconditionally at import time and raises an uncaught `ValueError` if argv[1] isn't an integer — makes the module unimportable from any context that has its own argv (e.g. `pytest tests/`, whose `sys.argv[1]` is `"tests/"`)

- **Status: Confirmed** by direct reproduction while writing this
  sub-task's `tests/test_gui_clients_signal.py` (which needs to import
  `gui/server.py` to test `_write_gui_clients_count()`):
  ```
  $ python3 -m pytest tests/test_gui_clients_signal.py -q
  gui/server.py:28: in <module>
      PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("CODEY_GUI_PORT", "8888"))
  ValueError: invalid literal for int() with base 10: 'tests/'
  ```
- **Impact:** `gui/server.py` can only ever be imported (not just run as
  `__main__`) from a process whose own `sys.argv[1]`, if present, happens
  to be a valid integer — this is surprising for a module that otherwise
  looks like ordinary importable code (its actual entry point is guarded
  by `if __name__ == "__main__":` further down, but the argv read at line
  28 is not). Worked around in this sub-task's own test file by
  save/restoring `sys.argv` around the import rather than fixing the
  module itself (out of scope for this sub-task — signal-sourcing/testing
  only, no daemon/process-lifecycle logic touched in `gui/server.py`
  beyond the new `_write_gui_clients_count()` addition).
- **Not fixed** — the port-override read should be gated behind
  `if __name__ == "__main__":` (or read only from `CODEY_GUI_PORT`, with
  the positional-argv override moved to the `__main__` block) rather than
  running at module import time. Flagging per CLAUDE.md rule 8.

### [NEW-112] `core/daemon.py`'s `_handle_command`'s actual enqueue branches (`self.planner.add_tasks(enriched)` for a multi-step plan, `self.state.add_task(prompt)` for the single-task fallback) have zero live callers today — the socket `command` handler's only real caller anywhere in the shipped system is `core/planner_service.py:_request_daemon_plan()`, and it always sends `{"plan_only": True}`, which takes an early `return` (`core/daemon.py:209-242`) before either enqueue branch ever runs

- **Status: Confirmed**, found scoping 4.1 sub-task C. Repo-wide search
  for every caller of the daemon's `"command"` socket cmd:
  `core/planner_service.py:84-88` (`send_command("command", {"prompt":
  prompt, "no_plan": False, "plan_only": True}, timeout=185)`) is the
  only live call site. `gui/server.py`'s WebSocket `"command"` message
  type (`gui/server.py:275-278`) is unrelated — it spawns a `main.py`
  subprocess (`run_codey()`) directly, never touching the daemon socket
  at all. `codeyOS`'s own `send_command()` helper is only ever invoked
  with `"task"` (read-only lookup) and `"cancel"`. `ccos/plugins/system/
  daemon_control/daemon_control.py` deliberately does not wrap `command`
  at all (its own docstring already says why). No test exercises
  `_handle_command`'s enqueue branches either.
- **Impact:** in the *live* system, `_handle_command`'s prompt goes to
  the daemon socket exactly once per interactive-CLI prompt, purely as a
  synchronous planning-oracle RPC (get plan text back for `main.py`'s
  `_run_with_plan()` to execute locally step-by-step via `run_agent()`)
  — never to genuinely enqueue work onto the daemon's own SQLite task
  queue for the daemon itself to execute later. The "queue-only" framing
  in `PENDING_ISH_DECISIONS.md` item 2 (`"command" becomes queue-only`)
  assumed `command` was live's actual "submit work to the daemon" path;
  it isn't, today. It's real, intended-future functionality per
  `daemon_control.py`'s own docstring ("the real 'submit a new prompt
  for the daemon to execute' entry point... genuinely useful"), just not
  wired to any current caller.
- **Not a blocker, reshapes 4.1 sub-task C's scope rather than being
  fixed standalone** — see WORK_QUEUE.md Track 3 item 2, sub-task C: the
  `plan_only=True` synchronous RPC path is kept as-is (exempt from the
  new interactive-session-active gate, since the caller of that RPC IS
  the interactive session asking on its own behalf, not the daemon doing
  unrelated background work); the enqueue branches are stripped of their
  synchronous planner call and made to enqueue the raw prompt, with
  planning deferred to the pull side (`_process_planner_tasks`) so a
  future live caller of the enqueue path benefits from the intended
  "queue-only" behavior once one exists.

### [NEW-113] `Daemon.__init__`'s `self.server.planner = self.planner` (`core/daemon.py:684`) is dead code — its comment says "so `_handle_command` can queue steps," but `_handle_command` (post-4.1-sub-task-C restructuring) no longer reads `self.planner`/`server.planner` at all

- **Status: Confirmed** by direct code read. `DaemonServer` (the class
  `_handle_command` actually belongs to) spans `core/daemon.py:156-620`.
  Every use of the bare name `self.planner` in the file — lines 682/684
  (the assignment itself, inside `Daemon.__init__`, a *different* class)
  and lines 1097-1184 (`_process_planner_tasks()`, also on `Daemon`, e.g.
  `self.planner.get_next_task()`, `self.planner.add_tasks()`) — falls
  outside `DaemonServer`'s line range entirely; there are zero `self.
  planner` references inside `DaemonServer` itself. A repo-wide search
  for `server.planner` (`grep -rn "server\.planner" --include=*.py`)
  finds exactly one hit in the whole repo — the assignment at line 684 —
  and zero reads anywhere. `_handle_command` (`core/daemon.py:194-272`,
  the method the stale comment names) only touches `self.state` and, on
  the `plan_only=True` path, calls `send_plan_request_async()` directly;
  it never references `self.planner` or `server.planner` in any form.
  The attribute is assigned once at daemon startup and never consulted
  again by anything.
- **Impact:** cosmetic/maintainability only — a future reader following
  the comment would look for `_handle_command` using `self.planner` and
  not find it, and could waste time either reverse-engineering why the
  wiring exists or (worse) assuming it still matters and preserving it
  across a later refactor that has no reason to.
- **Not fixed** — out of scope for 4.1 sub-task C (docs-only round per
  code-reviewer's request); flagging per CLAUDE.md rule 8. Removing the
  dead assignment (and its comment) is a trivial follow-up whenever
  `core/daemon.py` is next touched for something in this area.

### [NEW-114] 4.1 sub-task C's new "expand a queued task into an N-step plan" path (`_process_planner_tasks()`, `core/daemon.py:~1166-1193`) has a crash window between `add_tasks()` creating the new multi-step rows and `complete_task()` marking the superseded raw row `done`, with no reaper/watchdog anywhere in the codebase to recover an orphaned `running` row if the daemon dies in that gap

- **Status: Confirmed** by direct code read, raised by code-reviewer
  building on this sub-task's own flagged concern. Sequence at
  `core/daemon.py:1157-1192`: `try_claim_task()` first sets the raw row's
  status to `running` (line 1157); then, if `needs_planning`, planning
  runs and — when it yields >1 step — `self.planner.add_tasks(enriched)`
  (line 1184) creates the new expanded rows; only *after* that does
  `self.state.complete_task(db_task["id"], ...)` (line 1189) mark the
  original raw row `done`. A daemon crash between those two calls leaves
  the raw row permanently `running` with the new rows already created and
  eligible for normal dispatch — i.e. real work is not lost, but the
  stale raw row itself is never cleaned up. Verified no reaper exists:
  `core/daemon.py`'s only code that inspects `running`-status age is
  `_handle_health()` (lines 302-308), which computes a `stuck_tasks` list
  purely for read-only reporting in the `/health` response — it never
  resets, re-queues, or otherwise acts on a stuck row. `core/state.py`
  has no method that updates a `running` row back to `pending`/`done` on
  a timeout basis at all (its only status-transition writes are the
  `pending`-scoped claim update and the explicit `complete_task()`
  `done`-write). No watchdog tick in `_main_loop()`
  (`core/daemon.py:927-969`, the same loop that runs the 7B model and
  embed-server watchdogs) touches task-queue rows either.
- **Impact:** bounded but real — an orphaned `running` raw row is inert
  (nothing dispatches it, nothing marks it failed) and permanently
  visible as "stuck" in `/health`'s reporting with no automated recovery;
  a human has to notice and manually intervene (e.g. via a direct DB
  fix) to clear it. The *absence of any stale-`running` reaper* is
  pre-existing and not specific to this path — a crash mid-`_execute_task()`
  for an ordinary (non-expanded) task already strands a `running` row the
  same way, with nothing in the codebase to recover it either. What this
  sub-task's restructuring newly introduces is the *specific crash
  window*: before this sub-task, a raw task's `running` state was always
  cleared by the same code path that executed it (no separate step in
  between); now there's a distinct "supersede and mark done" step
  (`add_tasks()` then `complete_task()`) that a crash can land inside,
  making this the first dispatch path whose correctness actually depends
  on a reaper that doesn't exist.
- **Not fixed** — out of scope for 4.1 sub-task C (docs-only round per
  code-reviewer's request); flagging per CLAUDE.md rule 8. A future fix
  would need a general stale-`running`-row reaper (there isn't one for
  any task today, not just this path) or a narrower fix reordering the
  two writes so the raw row is marked `done` atomically with (or before)
  `add_tasks()`, whichever a later round decides is the right shape.

### [NEW-115] `core/resource_gate.py`'s module docstring still claims the module is "NOT wired into `core/daemon.py`... yet" — stale after 7.4 sub-tasks A/C/D all landed and wired it in

- **Status: Confirmed** by direct code read during 4.1 sub-task D. The
  module docstring (`core/resource_gate.py:6-13`) reads: "This module is
  the 'single authority' for model-load admission decisions... It is
  NOT wired into `core/daemon.py`, `core/loader_v2.py`,
  `core/planner_loader.py`, or `main.py` yet — that migration is
  sub-tasks 2-5..." and closes with "Nothing in this module is wired
  into a live process yet." Both statements are wrong as of this round:
  sub-task A's CPU/thermal sampling is ticked from `core/daemon.py`'s
  `_main_loop()` watchdog, sub-task C's `can_dispatch_task()` gates
  `_process_planner_tasks()`, and sub-task D's `should_trip_shutdown()`
  drives `_trigger_shutdown()` from the same watchdog tick — all three
  are live in the daemon process today.
- **Impact:** cosmetic/maintainability only — a future reader trusting
  this docstring could wrongly conclude the gate has no live-process
  effect and skip the mandatory code-reviewer/live-verifier scrutiny
  this category of change actually requires (CLAUDE.md rule 4).
- **Not fixed** — out of scope for 4.1 sub-task D (this round's
  reviewer-requested scope is the sparse-history trip bug fix only);
  flagging per CLAUDE.md rule 8. Fixing this is a small, self-contained
  doc update whenever `core/resource_gate.py` is next touched.

### [NEW-116] `ccos/plugins/system/daemon_control/daemon_control.py`'s module docstring miscounts the socket protocol's handler total and cites a `daemon_shutdown()` helper that no longer exists

- **Status: Confirmed** by direct code read during 4.1 sub-task D. The
  docstring (`ccos/plugins/system/daemon_control/daemon_control.py:5-17`)
  says "core/daemon.py's socket protocol registers 7 handlers total; two
  are deliberately left unwrapped here" and names `shutdown`
  (`core/daemon.py's daemon_shutdown()`) as one of them. Sub-task D
  retired the socket `shutdown` command entirely and deleted the
  `daemon_shutdown()` helper (the daemon now shuts itself down only via
  the autonomous `should_trip_shutdown()` tripwire, routed through
  `_trigger_shutdown()`), so both the "7 handlers" count and the
  `daemon_shutdown()` reference are now wrong — the protocol registers 6
  handlers, and the `{"cmd": "shutdown"}` case now falls through to the
  socket's generic "Unknown command" response rather than reaching a
  named handler.
- **Impact:** cosmetic/maintainability only today (no code here calls
  the retired handler), but is exactly the kind of stale capability-
  surface description this plugin's own manifest/docstring exists to
  keep accurate for agent-driven planning — a future reader or an
  agent-tool-designer pass could reasonably (and wrongly) plan around a
  `shutdown` capability that no longer has anything behind it.
- **Not fixed** — out of scope for 4.1 sub-task D; the correct scope is
  sub-task E (updating this plugin/manifest to reflect the socket
  protocol's retirement of `shutdown`), which has not started yet.
  Flagging per CLAUDE.md rule 8 rather than fixing ad hoc here.

### [NEW-117] `core/recursive.py`'s `get_adaptive_depth()` has a stale `temp_critical` fallback/docstring (80°C) that no longer matches the real committed default (90°C) in `utils/config.py`'s `THERMAL_CONFIG`

- **Status: Confirmed** by direct code read while fixing the
  `CODEY_TEMP_CRITICAL_C` warning-text consumer list (4.1 sub-task D,
  code-reviewer round-2 finding). `core/recursive.py:176`'s docstring
  reads "temp >= temp_critical (80°C) → force depth 0 (no recursion)"
  and its actual code at line 188, `cfg.get("temp_critical", 80)`, uses
  `80` as the fallback default if the key were ever missing from
  `THERMAL_CONFIG`. `utils/config.py:105` sets the real committed default
  to `90`, not `80` — both the documented number and the code's own
  fallback disagree with the config value that is actually in effect on
  every normal run (the `.get()` fallback only matters if the key is
  ever absent, but the docstring's `80°C` is unconditionally wrong/
  misleading regardless).
- **Impact:** low under normal operation (the real `THERMAL_CONFIG`
  dict always has the `temp_critical` key set, so `cfg.get(...)`'s stale
  `80` fallback is never actually exercised) but directly misleading to
  a reader — including a reader following the `CODEY_TEMP_CRITICAL_C`
  override warning in `utils/config.py`, which now explicitly names
  `get_adaptive_depth()` as a consumer to check. The first thing such a
  reader sees there is the wrong number.
- **Not fixed** — out of scope for this round (a comment/warning-text
  fix only); the correct fix is updating both the docstring and the
  `.get()` fallback in `core/recursive.py` to `90` (or better, importing
  the real default rather than hardcoding either number a second time).
  Flagging per CLAUDE.md rule 8 rather than fixing ad hoc here.

## Found during live-verification of Phase 4.1 sub-tasks C and D, 2026-08-10 — docs/logging-only round, NOT fixed

### [NEW-118] `core/daemon.py`'s watchdog tick does not short-circuit after `_trigger_shutdown()` fires — the same tick that decides to shut down still runs the model-load watchdog immediately afterward

- **Status: Confirmed**, found live during 4.1 sub-task D live-verification
  and confirmed by direct code read afterward. `_trigger_shutdown()`
  (`core/daemon.py:717-740`) only sets `self.running = False` (line 738)
  and closes the socket server; it does not raise, `return`, or otherwise
  interrupt the caller. `_main_loop()`'s `while self.running:` guard
  (line 938) is only re-evaluated at the *top of the next* iteration —
  so calling `_trigger_shutdown()` from inside a watchdog tick (line 999)
  does not stop the rest of that same tick from executing. Verbatim log
  evidence from the live-verification run, all within roughly one second:
  ```
  08:32:48,116 - WARNING - Autonomous shutdown tripwire fired: ...
  08:32:48,117 - INFO - Daemon shutdown triggered
  08:32:48,119 - INFO - Loading model: qwen2.5-coder-7b-instruct-q4_k_m.gguf
  08:32:48,158 - ERROR - Resource gate denied primary model load: ...
  08:32:48,698 - INFO - Embed server stopped
  ```
  After the trip fires at line 999, execution falls through to the 7B
  model watchdog (`self._watchdog_check_model()`, line 1031) and the
  embed-server watchdog (lines 1033-1042) in the *same* tick, both of
  which run unconditionally regardless of the trip decision just made.
  In this run it was harmless only because the resource gate
  independently denied the 7B load attempt for its own reasons.
- **Impact:** on a device/config where that post-trip load attempt were
  instead *admitted* (e.g. thermal already cooling by the time
  `_watchdog_check_model()` runs, or a config where the shutdown and
  admission thresholds diverge), the daemon would start loading a model
  after already deciding to shut down, then unload it moments later via
  `_main_loop()`'s `finally:` block (`core/daemon.py:980-1013`) as part
  of the same shutdown sequence — the exact "orphaned process holding
  real RAM, gate slot reaped as dead" failure class that the `finally:`
  block's own existing comment already warns about, now demonstrated as
  reachable through a path (the autonomous shutdown tripwire) that did
  not exist before 4.1 sub-task D. This round's live-verification run
  did not hit the bad outcome, so this is not itself a regression in
  sub-task D's own live-verification criterion — it's a gap the new
  tripwire code path exposes in the surrounding loop structure, not in
  `should_trip_shutdown()`/`_trigger_shutdown()` themselves.
- **Shape of a fix (described, not implemented — left for whoever picks
  this up):** `break`, `return`, or `continue` immediately after the
  `self._trigger_shutdown()` call at `core/daemon.py:999` would all
  correctly skip the remainder of the tick while still reaching
  `_main_loop()`'s `finally:` block on the way out — `finally:` blocks
  run regardless of which of these three exits a loop iteration via, so
  the choice among them is a style/clarity call for the implementing
  round, not a correctness one.
- **Not fixed** — this was a docs/logging-only verification round per
  the task's own scope; no implementation code was touched. Flagging per
  CLAUDE.md rule 8.

### [NEW-119] The resource gate's cold-start CPU-sample-failure warning (`core/resource_gate.py:382`) fires roughly twice per ~0.5s daemon tick on this device, not once per 30s watchdog cycle — a much higher log-volume cost than the existing NEW-108 finding described

- **Status: Confirmed** by direct code read of `core/resource_gate.py`
  and `core/daemon.py`, not just log-volume inference. The message text
  observed live (`resource_gate: cold-start CPU sample failed...
  Permission denied: '/proc/stat'`) matches
  `core/resource_gate.py:382` inside `get_current_cpu_percent()`, which
  is distinct from the already-known, lower-frequency CPU-sample warning
  at `core/daemon.py:970` (`"resource_gate CPU sample failed: {e}"`)
  that fires once per 30s watchdog cycle. `get_current_cpu_percent()`
  only takes its "cold-start" branch (lines 374-386) when
  `get_cpu_history()` is empty; tracing why it's always empty on this
  device: `sample_cpu_percent()` (`core/resource_gate.py:296-334`, the
  function the 30s watchdog tick calls) reads `/proc/stat` at line 316
  and, on this device, that always raises (`NEW-108`, `Permission
  denied` unconditionally) — the `except` branch at line 317-319 returns
  `None` immediately, before line 331's `_cpu_history.append(...)` is
  ever reached. So `_cpu_history` never gets a single entry on this
  device, meaning `get_current_cpu_percent()` takes the cold-start
  branch (and re-attempts, and re-fails, and re-warns) on every call,
  forever — "cold-start" here does not mean "only until the first
  reading," it means "every call, permanently," on this specific
  hardware. Call-site trace: `get_current_cpu_percent()` is called from
  `get_resource_snapshot()` (`core/resource_gate.py:587`), which
  `core/daemon.py`'s new `_check_dispatch_gate()` (`core/daemon.py:1107-
  1122`) calls once per invocation; `_check_dispatch_gate()` itself is
  called twice per `_process_planner_tasks()` iteration — once from the
  planner-task branch (`core/daemon.py:1171`) and once from the direct-
  command branch (`core/daemon.py:1219`) — so up to 2 of these WARNING
  lines can fire per ~0.5s main-loop tick, consistent with the observed
  live-verification volume: 112 WARNING lines and 114 INFO
  ("dispatch deferred") lines separately counted in ~40s of one test
  (~80 ticks at 0.5s), i.e. roughly 1.4-2 WARNING lines/tick, not a
  single combined 112 total as an earlier draft of this entry implied.
  `/proc/stat` being unconditionally unreadable on this device is the
  already-Confirmed `NEW-108`; this finding is specifically about the
  *frequency* at which that already-known condition now gets re-logged
  at WARNING level, now that 4.1 sub-task C's per-task dispatch gate
  calls the CPU-sampling code path on this cadence — a new consumer of
  an old, already-known-unreadable signal, not a new unreadability.
- **Impact:** log-volume/noise concern, not a correctness bug — up to
  two WARNING lines per ~0.5s main-loop tick, forever on this device,
  for a condition (`/proc/stat` unreadable) that is permanent and
  already known — a cadence roughly 60-120x higher than the pre-existing
  30s watchdog-cycle CPU sample. Makes real daemon logs harder to scan
  for actually-actionable warnings.
- **Not fixed** — out of scope for this docs-only verification round.
  A future fix could downgrade this specific message to `debug`-level
  after the first occurrence per daemon run, or cache the "CPU
  unmeasurable on this device" fact once (module-level, similar to how
  `NEW-108` is already documented as a permanent condition) rather than
  re-attempting and re-warning every tick. Flagging per CLAUDE.md rule 8.

### [NEW-120] A task that fails at the model-load step is persisted with `status=done`, not `status=failed`, because `run_agent()` returns an error string instead of raising

- **Status: Confirmed** by direct code read, newly observed during 4.1
  sub-task C live-verification (pre-existing behavior, not introduced by
  sub-task C's diff). `core/daemon.py:1266-1271`:
  ```python
  result = await asyncio.wait_for(
      self.executor._execute_task(description),
      timeout=timeout,
  )
  self.state.complete_task(db_task["id"], result)
  ```
  `_execute_task()` (`core/task_executor.py:96`) delegates to
  `run_agent()` (`core/agent.py:951`). The daemon-side half of this is
  independently confirmed by direct code read: `core/daemon.py:1266-1271`
  awaits `_execute_task()` and, on any normal (non-exception) return,
  unconditionally calls `self.state.complete_task(db_task["id"], result)`
  — the `except asyncio.TimeoutError` / `except Exception` branches at
  lines 1272-1275 (which route to `self.state.fail_task(...)`) only run
  if `_execute_task()`/`run_agent()` actually raises. Confirmed live:
  the sub-task C verification task (`echo
  LIVE_VERIFY_SUBTASK_C_MARKER...`, chained to a model-load step that the
  resource gate denied) ended up `status=done` in the real
  `~/.codeyOS/state.db`, not `status=failed` — meaning whatever
  `run_agent()` did on that resource-gate denial did not raise all the
  way up through `_execute_task()`, matching the pattern already
  observed elsewhere in this module of in-band failures being returned
  as strings rather than raised (e.g. `core/agent.py:489`'s `return
  "[ERROR] " + error_msg` convention). This round did not trace the
  exact line inside `run_agent()`'s model-load path that produces that
  non-raising behavior for this specific denial — the daemon-side
  consequence (that `complete_task()` fires regardless) is the
  independently-confirmed part of this finding; the precise mechanism
  inside `run_agent()` is inferred from the observed outcome plus this
  module's general error-string convention, not read line-by-line for
  this exact path.
- **Impact:** anything that inspects `task_queue.status` to decide
  whether a task genuinely succeeded (a future retry/alerting mechanism,
  `/health`, a human skimming task history) cannot distinguish a real
  success from an in-band agent failure without also parsing the
  `result` text for error markers — `status=done` alone is not reliable
  evidence of success for any task that goes through this path.
- **Not fixed** — out of scope for this docs-only verification round;
  predates 4.1 sub-task C and is not something that sub-task's diff
  introduced. A future fix would need `_process_planner_tasks()` (or
  `run_agent()` itself) to distinguish an in-band failure result from a
  genuine success before choosing `complete_task()` vs. `fail_task()` —
  not scoped here. Flagging per CLAUDE.md rule 8.

### [NEW-121] `codeydOS` has no daemon-only startup mode — `start` always launches both `plannd` and the main daemon together, forcing concurrent multi-model RAM/swap pressure even for tests that only need the daemon

- **Status: Confirmed** by direct code read. `codeydOS`'s dispatcher
  (`codeydOS:453-458`) unconditionally calls `start_plannd() ||
  true` followed by `start_daemon()` for the `start` subcommand — there
  is no flag or subcommand to launch the daemon alone. During this
  round's live-verification of sub-tasks C and D, this forced the
  verifier to hand-build a daemon-only harness by manually copying
  `start_daemon()`'s exact commands out of the script rather than using
  `./codeydOS start` directly, after an earlier attempt in this same
  session using the real `start` subcommand caused real concurrent-
  model-load RAM pressure. This is the same underlying pattern already
  Confirmed in `NEW-14` (full 3-model `codeydOS start` stack pushes this
  ~10.8GB device into severe swap pressure within seconds) and
  `NEW-18`/`NEW-21` — `NEW-14`'s own write-up already floated "consider
  whether the daemon-only / plannd-optional lighter path used
  successfully here should become a documented, supported 'lite' mode"
  as a candidate follow-up, but no prior entry names the *absence of a
  daemon-only launch mode* as its own finding; this one does.
- **Impact:** reproducibility/testing-ergonomics gap, not a production
  bug — every live-verification session that only needs the daemon
  (not the full stack) currently has to either accept the RAM risk of
  the full `codeydOS start`, or hand-roll a harness by reading and
  copying script internals, which is easy to get subtly wrong and has
  to be redone from scratch each time the script's internals change.
- **Not fixed** — out of scope for this docs-only verification round.
  A future fix could add a `codeydOS start --daemon-only` (or similar)
  subcommand that calls `start_daemon()` without `start_plannd()`,
  formalizing the harness this project has now hand-built at least
  twice. Flagging per CLAUDE.md rule 8.

### [NEW-122] Correction to `NEW-116`: the socket protocol registers 7 handlers post-sub-task-D, not 6 as `NEW-116` stated

- **Status: Confirmed** by direct read of `core/daemon.py`'s
  `_register_default_handlers()` (lines 176-182) during 4.1 sub-task E.
  `NEW-116` correctly identified that the stale docstring's "7 handlers"
  count and `daemon_shutdown()` reference were wrong after sub-task D,
  but its own replacement figure ("the protocol registers 6 handlers")
  is also wrong — it undercounts by one. The actual registration list is
  `ping`, `command`, `status`, `health`, `task`, `cancel`,
  `release_model_slot` — 7 handlers today (`shutdown` retired, dropping
  the pre-D total of 8 to 7, not 6). `release_model_slot` (registered at
  `core/daemon.py:182`, added for 7.4 sub-task 4/NEW-69 well before this
  round) appears to be what `NEW-116`'s count missed.
- **Impact:** cosmetic/maintainability only — same category as `NEW-116`
  itself; correcting per CLAUDE.md rule 6 rather than letting a wrong
  replacement number stand once `NEW-116`'s underlying doc gets fixed.
- **Fixed** as part of 4.1 sub-task E
  (`ccos/plugins/system/daemon_control/daemon_control.py`'s docstring and
  `manifest.json`'s description now state the count as 7, spell out
  which 5 of the 7 handlers this plugin wraps vs. which 2
  (`command`, `release_model_slot`) it deliberately doesn't, and
  distinguish those 2 non-handler capabilities
  (`daemon_check_pid_file`/`daemon_is_running`) that call `core.daemon`
  functions directly rather than going through a socket handler at all).

### [NEW-123] Sub-task E disposition for `NEW-113` and `NEW-115`: confirmed still open, out of `daemon_control` plugin's two files, not touched by this round

- **Status:** both re-confirmed accurate during 4.1 sub-task E's file
  reads, not fixed by this round because both live outside
  `ccos/plugins/system/daemon_control/`'s two files (the plugin module
  and its manifest), which is this sub-task's actual scope.
  - `NEW-113` (`Daemon.__init__`'s `self.server.planner = self.planner`
    wiring, `core/daemon.py:684` — dead code post sub-task C's
    `_handle_command` restructuring): still present, unchanged. A
    one-line removal (or comment correction) whenever `core/daemon.py`
    is next touched for an unrelated reason.
  - `NEW-115` (`core/resource_gate.py`'s module docstring still claiming
    the module "is NOT wired into `core/daemon.py`... yet"): still
    present, unchanged. Same disposition — a small, self-contained
    doc-only fix whenever that module is next touched.
  - Flagging both explicitly per CLAUDE.md rule 8 rather than silently
    leaving them unmentioned in this round's write-up, even though
    neither required a code change here.

### [NEW-124] `core/planner_service.py`'s module docstring/comments say the daemon planner is "0.5B or remote" — the actual model is 1.5B (upgraded from 0.5B per `utils/config.py:407`'s own comment)

- **Status:** Confirmed, found during 7.3 scoping (task classifier + tier
  config), not fixed — doc-only, outside that scoping pass's no-code-
  changes mandate.
- **Evidence:** `core/planner_service.py:7` ("Daemon planner (0.5B or
  remote) via Unix socket") and `:23` (matching comment) both say 0.5B.
  `core/planner_client.py:4` correctly says "1.5B model on port 8081."
  `utils/config.py:405-411`'s comment block on `PLANNER_MODEL_PATH` is
  explicit: "Qwen2.5-Coder-1.5B runs as a dedicated planning +
  summarization model on port 8081 ... Upgraded from 0.5B for better
  code-aware planning and task decomposition." `planner_service.py` was
  not updated when that upgrade landed.
- **Impact:** cosmetic/maintainability only — doesn't affect behavior,
  since no code branches on the string, but it's exactly the kind of
  stale-model-size doc that 7.3's new `(domain, role, tier) → model`
  config table needs to get right the first time (it will need to name
  this model precisely). Worth fixing in the same pass that adds the
  tier config table, not before.
- **Status: CLOSED, 2026-08-23.** M1-D's planner collapse rewrote
  `core/planner_service.py`'s module docstring; it now correctly says
  "Daemon planner (primary Qwen3.5-4B, thinking mode, or a remote...)"
  and explicitly notes the prior "0.5B or remote" text was stale even
  before M1-D, since the model had already been upgraded to 1.5B.
  Confirmed by direct code read.

### [NEW-125] The 7B coder model and the planner's "large tier" escalation path are the same physical model today — a role/tier overlap worth naming before 7.3's tier config formalizes roles

- **Status:** Suspected (architecturally implied by existing code, not
  independently load-tested this pass).
- **Evidence:** `core/planner_service.py:get_plan()`'s fallback ladder
  attempt 2 calls `core.orchestrator.plan_tasks()`, which drives planning
  through `recursive_infer()` — the same 7B coder model
  (`MODEL_PATH`/`PRIMARY_SERVER_PORT`) used for the `coder` role's actual
  execution, not a distinct "planner-large" model. So today, informally,
  the coding domain's `planner` role has two tiers (1.5B on port 8081;
  7B-as-planner via the orchestrator fallback) and the second of those is
  physically identical to the `coder` role's model.
- **Impact:** not a bug — it's intentional fallback behavior — but 7.3's
  `(domain, role, tier) → model` config table will need to either (a)
  represent this literally (planner's large tier and coder's tier both
  point at the same model reference, which is fine and should just be
  written that way, not treated as an error), or (b) decide the fallback
  ladder becomes tier escalation instead and collapse the redundancy.
  Logged so 7.3's implementation sub-tasks don't quietly paper over which
  of those two it's choosing.

### [NEW-126] `classify_tier()` resolves to "large" for substantially all realistic planner prompts under current `_action_kws` — its log-only output will disagree with the executed ladder by default

- **Status:** Confirmed (direct code read + interactive check of
  `core.model_tiers.classify_tier()`'s decision rule against
  `core.orchestrator._action_kws`/`COMPLEX_SIGNALS`).
- **Evidence:** `classify_tier()`'s heuristic (TODO.md 7.3 sub-task C,
  `core/model_tiers.py`) is `needs_large = score.has_action or
  score.length > 150 or score.signal_count >= 2`. `_action_kws`
  (`core/orchestrator.py`) includes common verbs any real coding request
  is likely to contain — create, write, fix, run, add, update, check,
  read, show me, and more. In practice this means `has_action` is true for
  nearly any genuine planning prompt, so `classify_tier()` returns
  `"large"` for nearly all traffic. Meanwhile `planner_service.get_plan()`'s
  existing fallback ladder (unchanged by sub-task C) always tries the
  small/daemon 1.5B planner first regardless of the classifier's answer.
- **Impact:** not a defect in sub-task C's own scope — C is decide-and-log
  only, and threshold tuning is explicitly sub-task E's job, blocked on
  7.4. But it does mean the log line's practical signal is weak as
  currently thresholded: it will say "would select 'large'" next to a
  ladder that ran the 1.5B on nearly every request, so logs collected
  under C's current thresholds alone won't be sufficient evidence for
  choosing E's real thresholds later. Mitigated partially in this same
  round by having the log line also emit `score.has_action`/`length`/
  `signal_count`, so the raw signal is still recoverable from the logs
  even though the derived tier string itself is close to constant.
  Flagged for whoever tunes E's thresholds, not fixed here.
- **Second, structurally distinct gap (added on code-reviewer's pass):**
  `classify_tier()`'s planner branch can only ever return `"large"` or
  `"small"` — there is no code path that returns `"remote"`, even when
  `CODEY_BACKEND_P` is set to a remote backend and
  `tiers_for_role("coding", "planner")` includes a `"remote"` entry.
  `planner_service.py:_request_daemon_plan()` DOES actually route to the
  remote backend under that config (see its `is_remote_planner_backend()`
  branch). So under a remote-planner setup this isn't just "weak
  discriminating value" as the paragraph above states for the
  small-vs-large case — the logged tier structurally cannot ever describe
  what's executing, because `"remote"` is not a reachable return value at
  all today. Whoever extends `classify_tier()` for sub-task E needs to add
  a remote-aware branch (e.g. checking `cfg.is_remote_planner_backend()`
  before the small/large heuristic), not just retune the existing
  thresholds. `tests/test_planner_service_classify_tier.py`'s use of
  `"remote"` as one of three mocked return values in
  `TestDaemonPlanPathUnaffectedByClassifier` exercises `get_plan()`'s
  indifference to whatever `classify_tier()` returns — it is not evidence
  that `"remote"` is a real output of today's `classify_tier()`.
- **Rule-6 correction (2026-08-23, found while scoping the 3-tier
  coding-task dispatch):** this entry's framing — `classify_tier()`
  "skews toward large," a weak-but-nonzero discriminating signal — no
  longer holds and should be read as **stronger than stated**, not
  merely confirmed. Post-M1-D, `core/model_tiers.py`'s `_PLANNER_TIERS`
  table contains only a `"large"` entry for the local backend (plus
  `"remote"` under a remote backend) — there is no `"small"` tier left
  for the `planner` role at all, since M1-D collapsed the dedicated
  small-model planner server onto the single shared model. `classify_tier()`'s
  own early-return guard (`if "small" not in available: return
  "large"...`) therefore fires **unconditionally** in every config that
  exists today, local or remote. The `_score_message()` call beneath that
  guard is not "skewed toward large" — it is **dead code**, contributing
  zero discriminating signal, for a reason (no small tier exists to
  select) that is independent of and predates `_action_kws`' keyword
  coverage. Whoever builds the 3-tier coding-task dispatch (a separate,
  newer effort — see `CODEY_MASTER_PLAN.md` §6.8, Ish's direction
  2026-08-23) should not treat `classify_tier()` as reusable signal for
  that purpose; the live signal actually worth reusing is
  `core.orchestrator._score_message()`'s raw fields directly, not
  `classify_tier()`'s wrapper around them.

### [NEW-127] `core/agent.py`'s inline `_action_kws` list has already drifted out of sync with `core/orchestrator.py`'s module-level `_action_kws`, despite the "keep in sync" comment on both — 7.3 sub-task A left this untouched by design, logging per CLAUDE.md rule 8 since it wasn't otherwise tracked as a Confirmed finding

- **Status:** Confirmed (direct read of both lists).
- **Where found:** while doing TODO.md 7.3 sub-task D (test-coverage-gap
  pass over sub-tasks A/B/C's combined surface). Sub-task A
  (`core/orchestrator.py`) extracted `_score_message()`/`ScoreResult` out
  of `is_complex()`, and both its own docstring/comment and
  WORK_QUEUE.md's Track 3 item 3 sub-task A scope note explicitly left
  `core/agent.py`'s separate, pre-existing duplicate `_action_kws` list
  untouched as out of scope, on the assumption the two lists were "kept
  in sync" per the comment above `core/orchestrator.py`'s copy
  (`# Action keywords that indicate a task (not a question) / # Keep in
  sync with _action_kws in core/agent.py`). Checking directly during D
  shows that assumption no longer holds: `core/agent.py`'s inline copy
  (`core/agent.py:1309-1373`, inside `run_agent()`) has six entries not
  present in `core/orchestrator.py`'s module-level `_action_kws`
  (`core/orchestrator.py:92-145`) — `"verify"`, `"test"`, `"validate"`,
  `"confirm"`, `"complete"`, `"finish"` — added under a comment there
  ("Planner step verbs — daemon steps like 'verify the output' must use
  shell, not return plain text answers") with no corresponding update
  ever made to `orchestrator.py`'s list.
- **Impact:** `core.orchestrator._score_message()`'s `has_action` field —
  now also consumed by `core.model_tiers.classify_tier()` (sub-task C) as
  one of three signals routing a message to the "large" tier — will
  disagree with `core/agent.py`'s own QA/smalltalk `_has_action` gate on
  any message containing one of the six drifted words and nothing else
  from either list. Verified directly, not assumed — a first attempted
  example ("test the output") turned out to score `True` on both lists
  because "output" independently appears in `orchestrator.py`'s own list,
  so it was discarded as not actually demonstrating divergence. Confirmed
  real examples:
  ```
  >>> from core.orchestrator import _score_message
  >>> _score_message("verify the results").has_action
  False
  >>> _score_message("test the login flow").has_action
  False
  ```
  `core/agent.py`'s `_has_action` would be `True` for both (via its
  `"verify"`/`"test"` entries), while `orchestrator.py`'s
  `_score_message()` — and therefore `classify_tier()` — scores both
  `False`. This was already latent
  before 7.3 (the two lists backed unrelated decisions — QA/smalltalk
  gating in `agent.py` vs. orchestration-need in `orchestrator.py`), but
  7.3 sub-task C gave `orchestrator.py`'s copy a second consumer
  (tier classification) without addressing the drift, so the blast radius
  of the two lists disagreeing is larger now than when the "keep in sync"
  comment was written.
- **Not fixed here:** collapsing the two lists into one shared list would
  pull `core/agent.py` into a refactor sub-task A explicitly scoped out
  ("A does not attempt to collapse that pre-existing two-copy
  duplication... a separate, larger refactor not asked for here"), and
  this task (sub-task D) is unit-tests-only per its own scope. Logged per
  CLAUDE.md rule 8 rather than silently left untracked, since it was
  previously mentioned only in TODO.md/WORK_QUEUE.md's sub-task-A scope
  notes ("left untouched, out of this sub-task's one-file scope") — a
  scoping note about what wasn't done, not a Confirmed/Suspected finding
  in this log — and not as a discovered divergence with a measured
  behavioral impact until this check.

### [NEW-128] `is_complex()`'s `length > 300` branch is unreachable-as-distinct — it has the exact same body as the `elif length > 150` branch immediately below it

- **Status:** Confirmed (direct code read + reproduced).
- **Where found:** while adding `is_complex()` threshold-boundary tests
  for TODO.md 7.3 sub-task D (test-coverage-gap pass over sub-tasks
  A/B/C). Pre-existing — not introduced by sub-task A's `_score_message()`
  extraction, confirmed by the fact that A's refactor preserved
  `is_complex()`'s control flow verbatim (per its own scope: "`is_complex()`
  itself keeps its exact current behavior and return type").
- **Evidence:** `core/orchestrator.py`'s `is_complex()`:
  ```python
  if score.length > 300:
      return score.signal_count >= 2
  elif score.length > 150:
      return score.signal_count >= 2
  else:
      return score.signal_count >= 3
  ```
  Both the `if` and first `elif` branches evaluate `score.signal_count >=
  2` — identical bodies — so the `length > 300` branch can never produce a
  result the `elif length > 150` branch wouldn't already produce for the
  same input (any message with `length > 300` also satisfies `length >
  150`). Reproduced directly:
  ```
  >>> from core.orchestrator import is_complex
  >>> is_complex("x"*301 + " create build")   # length > 300, 2 signals
  True
  >>> is_complex("x"*151 + " create build")   # length > 150, 2 signals
  True
  ```
  Both return the same result for every signal_count value — the `if`
  branch is dead code in the sense that no test or caller can distinguish
  it from the `elif` branch.
- **Impact:** not a functional bug (the two branches happening to agree
  means no wrong answers result), but it reads as though `length > 300`
  was meant to have its own threshold (e.g. a looser one, `signal_count >=
  1`) and was never filled in, or as though the branch is dead weight left
  over from an earlier version of the thresholds. Either way it's
  misleading to a future reader tuning these thresholds (e.g. for 7.3
  sub-task E's tier-threshold work) who might assume the `> 300` split is
  doing something the code doesn't actually do.
- **Not fixed here:** this task (sub-task D) is unit-tests-only, no
  production-logic changes permitted per its own scope, and CLAUDE.md rule
  8 requires logging rather than silently fixing. Whoever next touches
  `is_complex()`'s thresholds should either give the `> 300` branch a
  distinct condition or collapse it into the `> 150` branch explicitly.

## Found during 7.4 (Phase 5a) scoping pass, 2026-08-11 (project-architect, desk-only, no code changed) — NOT fixed, logged only

### [NEW-129] `resource_gate.can_admit()`'s thermal-refusal leg and `should_trip_shutdown()`'s sustained-thermal-trip leg deliberately share one config value (`THERMAL_CONFIG["temp_critical"]`), so a device/test config that makes the shutdown tripwire reachable simultaneously denies admission of the very model whose slot-release the tripwire is supposed to be proven safe for

- **Status: Confirmed** by direct code read, `core/resource_gate.py:1017-1018`
  (`can_admit()`) and `:1441` (`should_trip_shutdown()`) both execute
  `THERMAL_CONFIG.get("temp_critical", 90)` — the same key, no per-caller
  override. This is a deliberate, documented design choice from Phase 4.1
  sub-task D (`WORK_QUEUE.md` ~line 1409-1413: "`THERMAL_CONFIG` already
  has the right threshold for the thermal leg... is the correct value to
  reuse, not a new number"), not an accident — logged here because it
  produces a real, structural verification gap, not because the sharing
  itself was unintentional.
- **Concrete effect, already observed live**: Phase 4.1 sub-task D's
  2026-08-10 live-verification (`WORK_QUEUE.md` ~line 1527-1575) had to
  set `CODEY_TEMP_CRITICAL_C=36` to make the sustained-thermal shutdown
  tripwire reachable in a practical test session. That same lowered
  threshold independently denied the primary 7B model's own admission
  through `can_admit()`'s thermal leg, so the primary model never held a
  gate slot during that run — the tripwire's "no leaked slot on shutdown"
  claim is confirmed only for the embed-server model (which was resident
  and exempt from `can_admit()`'s reservation path), not for the primary
  model, and structurally cannot be under the current design: any
  `temp_critical` value low enough to make the tripwire reachable in a
  short test session is also low enough to deny the primary model's own
  admission through the same threshold.
- **Scope note**: this is a gap in Phase 4.1 (daemon control redesign,
  item 2)'s shutdown-tripwire verification, not in 7.4 (Phase 5a, the
  resource gate itself) — 7.4's own admission→release cycle is exercised
  via `release_model_slot` and the normal watchdog/SIGTERM shutdown
  paths, neither of which requires lowering `temp_critical`, so this does
  NOT block 7.4's live-verification. It also does not block 7.3 (task
  classifier/tier config) sub-task E.
- **Not fixed here** — out of scope for a desk-only scoping pass; NEW-119
  through NEW-128 correction/logging precedent applies (log per rule 8,
  don't silently fix). Fix direction, for whoever picks this up: either a
  separate `CODEY_SHUTDOWN_TEMP_CRITICAL_C` env-overridable threshold
  distinct from admission's `temp_critical` (simplest, but a device that
  is genuinely at 90°C should probably deny admission AND be closer to
  tripping shutdown — decoupling them numerically doesn't have an obvious
  "correct" pair of values without a real thermal-behavior study), or a
  test harness that gets a primary model resident via a path other than
  lowering `temp_critical` (e.g. admit it first at a normal temperature,
  then only lower `temp_critical` afterward to trigger the trip against
  an already-resident model) — the second option needs no code change,
  only a different live-test sequencing, and is likely the cheaper fix.

### [NEW-130] `WORK_QUEUE.md`'s 7.3 sub-task E scoping note (written 2026-08-10) claims "`release_model_slot` has never fired on a real request" — contradicted by `NEW-104`'s own verbatim evidence, written the day before, from 7.4's round-18 live-verification

- **Status: Confirmed**, a documentation self-contradiction, not a code
  bug — corrected in place in `WORK_QUEUE.md` per CLAUDE.md rule 6 rather
  than left standing. `NEW-104` (`NEW_ISSUES.md`, filed 2026-08-09)
  describes, with real PIDs: "with the daemon already holding a `primary`
  slot, `main.py --init` was gate-denied, asked the daemon to
  `release_model_slot`, the daemon stopped its own copy and released the
  slot" — i.e. `release_model_slot` genuinely fired and genuinely
  released a real, resident model's slot, the day before the 7.3
  scoping note (dated 2026-08-10) claimed it never had.
- **What round 18 actually verified, precisely** (see NEW-131 below for
  the distinct, still-open half): the **primary role's** slot-release
  mechanism — reservation, admission, `release_model_slot` firing on a
  real request, retry-and-reload — was exercised end-to-end using a
  **substitute model** (Qwen3-4B via `CODEY_TEST_PRIMARY_ARCH`) at a
  **test-only `n_ctx=2048`**, confirmed by `LIVE_TEST_QUEUE.md`'s own
  round-18 update ("the substitute primary model actually get[ting]
  admitted") and by `cost_bytes: 3067704480` in `NEW-104`'s captured slot
  read, which matches the substitute's KV-cache shape at `n_ctx=2048`,
  not the real 7B's. This is real, solid evidence the *mechanism* works —
  it is not evidence the *production model at its production `n_ctx`*
  has ever gone through it.
- **Fixed in docs**: `WORK_QUEUE.md`'s 7.3 sub-task E note corrected in
  place, 2026-08-11, to reflect this distinction rather than the flatly
  wrong "never fired" claim.

### [NEW-131] The real production primary model (Qwen2.5-Coder-7B, `~/models/qwen2.5-coder-7b/qwen2.5-coder-7b-instruct-q4_k_m.gguf`) at the real production default `n_ctx` (32768) has never been run through `can_admit()` live — a pure-arithmetic desk check (no model spawn) run this round found it is NOT hard-rejected, only denied by current live headroom, contrary to the implicit worry raised by the substitute's earlier hard-rejection at the same `n_ctx`

- **Status: Confirmed**, computed directly via
  `core/resource_gate.estimate_model_load_cost()`/`can_admit()` against
  the real 7B file and a real, live `/proc/meminfo` read (no model
  spawned — pure arithmetic, safe per this task's own no-live-load
  scope), 2026-08-11:
  ```
  model_bytes: 4683073536
  kv_cache_bytes: 1879048192
  overhead_bytes: 268435456
  total: 6830557184  (~6514MiB)
  GateDecision(admitted=False, hard_reject=False,
    reason="model 'primary' cost estimate (6514MiB) x headroom_factor (1.25)
    = 8143MiB, which exceeds current headroom (5574MiB)",
    estimated_cost_bytes=6830557184, headroom_bytes=5845012480,
    device_ceiling_bytes=6973872537)
  ```
  `free -h` at the moment of this calculation: `total 10Gi, used 5.1Gi,
  free 1.2Gi, buff/cache 4.5Gi, available 5.5Gi; swap total 11Gi, used
  1.6Gi, free 10Gi`.
- **Why this matters, exact numbers not adjectives** (per this project's
  own verification-wording-precision practice): `estimated_cost_bytes`
  (6830557184, ~6514MiB) is **136MiB (~2.1%) under** `device_ceiling_bytes`
  (6973872537, ~6650MiB) — `hard_reject=False`, but only just. The real
  production config is NOT structurally inadmissible on this device,
  unlike what round 18's substitute-model hard-rejection at the same
  `n_ctx=32768` could easily be misread to imply (the substitute's
  36-layer/8-KV-head shape costs MORE than the real 7B's 28-layer/4-KV-head
  shape at the same `n_ctx`, per `TODO.md`'s own round-18 write-up — this
  is the documented reason the two models' admissibility at the same
  `n_ctx` cannot be inferred from one another). But a 2.1% margin against
  the hard-reject ceiling is itself a finding: a marginally-lower-RAM
  device, or any future bump to the fixed overhead constant
  (`spec.compute_overhead_bytes`), would flip this specific config from
  admissible-in-principle to hard-rejected. The real 7B was denied just
  now only by *transient* headroom (other processes/buff-cache using RAM
  at calculation time), the same class of denial sub-task 5's CLI
  recovery path already handles — but the *budget check* (headroom x
  1.25 margin, not the hard ceiling) is the one actually blocking
  admission right now, and it needs ~8143MiB (~7.95GiB) of `MemAvailable`
  at load time to clear.
- **Historical-peak check (desk-only, `PROJECT_LOG.md` grep, no new live
  run)**: the highest `MemAvailable`/`available` figure ever recorded in
  this project's own live-test history is **~7.6GiB** (round 13's
  post-teardown daemon-only state, `PROJECT_LOG.md` ~line 3221 —
  `used 2.9Gi / available 7.6Gi`, with `plannd` not running). That is
  **~350MiB short** of the ~7.95GiB the budget check needs. No historical
  `free -h` capture in this project's logs has ever reached the bar this
  config needs to clear. This does not prove the bar is unreachable
  (round 13's 7.6GiB was a post-teardown snapshot, not a maximally-clean
  boot state, and `can_admit()` was called with the default
  `reserved_bytes=0` above — the optimistic case; if the embed server is
  resident during a real attempt, its registered slot cost would subtract
  further from headroom) — but it means the scoped live-verifier pass
  below has a real, evidenced chance of coming back as a denial even
  under the most favorable realistic conditions this device has ever
  shown, not just a hypothetical one.
- **What's still genuinely unverified**: whether the real 7B, at real
  `n_ctx=32768`, can actually be **admitted and spawned** end-to-end
  (load-through-gate) on this device under favorable-but-realistic
  headroom (e.g. daemon-only harness, `plannd` not running, no other
  model resident, embed server not yet loaded) — the arithmetic above
  says it's possible in principle but close to both the hard ceiling and
  the historical headroom peak; no live spawn has ever confirmed it
  either way. This is the one concrete live-verification gap left in
  7.4's core cycle for the *production* config specifically (round 18
  already covers the *mechanism* via the substitute).
- **Sharper product question for Ish, answerable without any live run**:
  the shipped default `n_ctx=32768` requires ~7.95GiB of `MemAvailable`
  to pass its own gate's budget check on a 10GiB device — a bar this
  project's own live-test history has never once reached. Is 32768 the
  right production default for this device, or should the production
  default itself be lowered (with `CODEY_N_CTX` staying as the
  test/override mechanism it already is)? This directly conditions 7.3
  sub-task E's tier thresholds and is a product decision, not an
  implementation detail — not resolved here.
- **Not fixed here** — a desk-only arithmetic check, logged per rule 8;
  the live spawn-and-confirm pass itself is scoped into `TODO.md`/
  `WORK_QUEUE.md`'s 7.4 entries as the next concrete live-verifier task,
  with this historical-peak caveat carried into that scoping so a denial
  result isn't mistaken for a broken gate.

### [NEW-132] The device's ~4:1 zram compression ratio, cited as supporting evidence for a swap-aware resource-gate budget, was measured on ordinary Android app anon pages at idle — not on model weights, and may not hold for them

- **Confidence: Suspected** — a reasoning gap identified during
  2026-08-11 scoping of the swap-aware resource-gate budget check
  (`TODO.md` 7.4a / `WORK_QUEUE.md` Track 3 item 1b, Ish's 2026-08-11
  decision to make `can_admit()`'s budget check swap-aware), not
  confirmed or refuted by any live measurement.
- **Where found:** `TODO.md`'s 7.4 diagnostic follow-up entry
  (2026-08-11) captured `/sys/block/zram0/mm_stat` showing roughly
  2.48GiB of logical data compressed into ~608MiB of physical RAM
  (~4:1) at device idle. That capture reflects whatever Android's own
  app processes had swapped out at that moment — ordinary anonymous
  memory pages, not model-weight pages.
- **Why this matters:** the primary model files this project loads are
  already quantized (Q4_K_M) — high-entropy, pre-compressed data.
  Compressing already-compressed data typically yields a far worse
  ratio than compressing ordinary process memory (closer to 1:1 is
  plausible, though not measured). If a swap-aware budget check is
  built assuming the observed ~4:1 ratio generalizes to model pages,
  it would significantly over-estimate how much usable headroom
  `SwapTotal`/`SwapFree` actually represents for this specific
  workload — the exact over-estimate failure mode that check exists to
  avoid, with a real consequence (thrash, RSS collapse, or Samsung's
  `slmk` low-memory-killer intervening, per `getprop
  ro.slmk.swap_free_low_percentage` = `10`, i.e. `SwapFree` below ~10%
  of `SwapTotal`/~1.2GiB on this device).
- **Not fixed here** — no live measurement was taken (this finding
  itself came from a desk-only scoping pass, no model load run).
  `TODO.md`'s 7.4a entry, sub-task E, scopes the actual measurement
  (sampling `/sys/block/zram0/mm_stat` during a real model load) as
  part of that item's live-verification pass — this entry exists so
  the assumption isn't silently carried into an implementation before
  it's checked.

### [NEW-133] Ish's 2026-08-11 `MAX_CONCURRENT_MODEL_BUDGET_BYTES` figure (8.80GiB) is arithmetically below the 8.855GiB raw sum it was explicitly derived from, by ~0.055GiB

- **Status: RESOLVED (2026-08-11, scoping-only correction, no code
  written yet — sub-tasks A/B/C1 remain unimplemented).** Flagged to Ish
  directly; his answer: **round up slightly instead, so the full
  3-model case stays admissible, with any remaining margin applied
  elsewhere (the swap-budget check, C2's `MAX_SWAP_ASSIST_BYTES`) rather
  than as a deduction on this ceiling, if a margin is still wanted at
  all.** Corrected value: `MAX_CONCURRENT_MODEL_BUDGET_BYTES = 8.90GiB`
  (9,556,302,233 bytes) — the raw sum (9,508,400,807 bytes / 8.855GiB)
  rounded up to the next 0.05GiB, giving a positive margin of
  47,901,426 bytes (~45.7MiB) *above* the raw sum instead of ~0.055GiB
  below it. This makes the exact three-model-concurrent scenario the
  ceiling was derived from admissible again, resolving the "this
  ceiling denies the case it was computed from" problem this finding
  identified. **Carried-forward caveat, not fully closed by the number
  alone**: the raw sum's embed term (0.328GiB) is a floor estimate with
  no computable KV-cache term (see decision 2 in `TODO.md` 7.4a) — if
  the embed model's real resident cost is undercounted by more than the
  ~45.7MiB margin this correction adds, the admissibility this fix
  restores could be lost again at the same threshold. This must be
  documented in the constant's own code comment (see `TODO.md` 7.4a's
  C1 sub-item 1) and re-checked against sub-task E's live pass rather
  than assumed permanently settled. Every occurrence of the old 8.80GiB
  figure updated to 8.90GiB in `TODO.md` 7.4a (C1 sub-items 1, 3, 7 and
  the "Ish's decisions" block) and `WORK_QUEUE.md`'s item 1b entry; the
  historical 8.80GiB figure and its "minus ~0.06GiB" framing are kept
  visible in both docs as the original decision, per CLAUDE.md rule 6,
  not erased.
- **Original finding — Confidence: Confirmed** — plain arithmetic on numbers computed live
  in the same 2026-08-11 session via this project's own
  `estimate_model_load_cost()`, not an estimate or a re-derivation.
- **Where found:** scoping pass for `TODO.md` 7.4a / `WORK_QUEUE.md`
  Track 3 item 1b sub-task C1, recording Ish's direct decision on the
  new named cumulative concurrent-model-budget ceiling.
- **The numbers:** 7B primary at `n_ctx=32768` = 6.361GiB; 1.5B planner
  at `n_ctx=32768` = 2.166GiB; embed model floor estimate (file +
  overhead only, no computable KV term) = 0.328GiB. Raw sum =
  6.361 + 2.166 + 0.328 = **8.855GiB**. Ish's stated final ceiling is
  **8.80GiB**, explicitly described as "the raw sum minus ~0.06GiB, for
  a slight safety margin" — but 8.80 is *below* 8.855 by ~0.055GiB, not
  above it with margin subtracted from headroom. Under a literal
  `concurrent_committed_bytes + candidate_cost > MAX_CONCURRENT_MODEL_BUDGET_BYTES`
  check, the exact three-model-concurrent scenario the ceiling was
  computed from would itself be denied by a few tens of MiB.
- **Why this matters:** if the intent was "this ceiling should
  comfortably admit all three models running at once," the constant as
  given doesn't do that — it needs a small upward correction (e.g. to
  something above 8.855GiB, with the "slight safety margin" framing
  applied to a different baseline, or accepting that headroom/thermal
  checks and not this ceiling are what's meant to gate the marginal
  byte). If the intent was "8.80GiB, and it's fine if the full
  three-model case is right at or just past the edge," the constant is
  correct as given and this is expected, not a bug — but that's not
  what "minus ~0.06GiB for a slight safety margin" reads as on its own.
- **Resolved, see the "Status: RESOLVED" block at the top of this
  entry** — this was a numeric question for Ish, not a wiring decision
  open to project-architect's own scoping judgement; Ish answered it
  directly and the corrected 8.90GiB value is now what `TODO.md` 7.4a's
  C1 sub-item 7 and `WORK_QUEUE.md`'s item 1b specify for the
  implementer to use.

## Found while fixing the NEW-81 bug that C1's `MAX_CONCURRENT_MODEL_BUDGET_BYTES` ceiling activated, 2026-08-11 — NOT fixed, logged only

### [NEW-134] Post-C1, a slot leaked during the PENDING window (reserved, then never confirmed resident) now permanently consumes fixed-ceiling budget, not just a self-healing live-headroom figure — narrower than NEW-81's mechanism, but the same crash-window class as NEW-82/NEW-114

- **Status: Confirmed by design gap, not yet a live bug** (same posture
  as NEW-81/NEW-82 before them — the module was still not fully daemon-
  wired at the time this was written). Logged per this task's own
  instruction and CLAUDE.md rule 8 (found while fixing NEW-81, out of
  that fix's scope, not silently fixed or dropped).
- **What's actually true (corrected from the mechanism as originally
  described to project-architect for this task — verified directly
  against `core/resource_gate.py` and `core/loader_v2.py` before writing
  this, not assumed):** `reserve_slot()`'s own PID default
  (`if pid is None: pid = os.getpid()`, `core/resource_gate.py`) means a
  freshly-reserved PENDING slot is registered under the **calling
  process's own PID** (e.g. the long-lived daemon), never literally
  `pid=None` — so the framing "ghost PENDING slots registered `pid=None`"
  that this task was originally asked to log is not what the code does;
  logging it as such would be a false entry, so it's corrected here
  instead (CLAUDE.md rule 6). The real, narrower gap: between
  `reserve_slot()` admitting a PENDING slot (attributed to the daemon's
  PID) and `confirm_resident_and_mark_slot(..., pid=child_pid)` rebinding
  it to the real subprocess (the NEW-81 fix, this same round), the slot
  is attributed to the daemon — if the real child process dies inside
  that specific window, PID-liveness reaping won't notice (it's still
  checking the daemon's own, still-alive, PID). In the normal case this
  window is already bounded by `load_primary()`'s/`PlannerLoader.load()`'s
  `try`/`finally` (any exception releases the slot; see
  `.claude/agent-memory/code-reviewer/resource_gate_subtask2_confirm_mark_slot_leak.md`),
  and a daemon `SIGKILL` in that same window is correctly reaped (the
  slot's pid IS the daemon's own PID, and the daemon really did die) —
  so this is narrower than NEW-82's general "no TTL on PENDING slots"
  framing, not a new instance of it.
- **What's new post-C1 specifically:** before C1, an unreaped leaked
  PENDING slot only skewed `total_reserved_bytes()`'s live,
  self-healing, MemAvailable-relative headroom figure (bad, but
  transient relative to actual memory pressure). After C1, the same leak
  also permanently consumes part of the fixed
  `MAX_CONCURRENT_MODEL_BUDGET_BYTES` ceiling via
  `_sum_committed_bytes()`/`total_committed_bytes()` (PENDING + RESIDENT,
  summed against a constant, not a live figure) — a leak in this specific
  window now has a permanent-budget-consumption consequence it didn't
  have before C1 landed.
- **Cross-references:** NEW-82 (general PENDING-slot TTL/leak gap, this
  is a narrower instance of the same underlying class, not a duplicate);
  NEW-114 (4.1 sub-task C's "crash window with no reaper" finding — same
  finding *shape*, different subsystem: a state transition with no
  recovery path if the process dies mid-transition).
- **Where found:** while implementing this task's mandated NEW-81 fix
  (TODO.md 7.4a sub-task C1's code-reviewer-required bug-fix round,
  2026-08-11) — reading `reserve_slot()`'s actual PID-default behavior to
  confirm the fix's own correctness surfaced this narrower, real gap
  along the way; not otherwise in scope for that fix, and not fixed
  here.
- **Fix direction, if picked up later:** either the TTL-on-PENDING
  approach NEW-82 already proposes, or having `reserve_slot()` itself
  eagerly reap PENDING slots older than a bound at read time (it already
  reaps dead-PID slots at the same point) — either would also close this
  narrower window, not just the general one.

## Found while code-reviewing TODO.md 7.4a sub-task C2 (swap-assisted admission wiring), 2026-08-11 — flagged by implementer as out-of-scope for C2's own mandate, NOT fixed, logged only

### [NEW-135] `compute_swap_assisted_headroom_bytes()` has no `reserved_bytes`-style deduction — two concurrently-pending swap-assisted admissions can each independently claim the same 768MiB `MAX_SWAP_ASSIST_BYTES` cap against the same live `SwapFree` figure

- **Status update, 2026-08-25 (later same day) — mandatory rule-4
  code-reviewer pass complete: APPROVED, no changes required.** Reviewer
  independently confirmed: lock coverage complete (the swap-claim sum sits
  inside `reserve_slot()`'s existing lock, mirroring the pre-existing
  RAM-side `reserved_bytes` pattern); the one real gap
  (`can_dispatch_task()`'s separate consumer not going through the locked
  path) is honestly disclosed, not hidden, and treated as an acceptable
  disclosed limitation rather than a blocking defect — logged separately as
  `NEW-187` per rule 8 rather than left as prose only; no leak on slot
  release (the PENDING-only filter naturally excludes RESIDENT/removed
  slots); no double-counting between RAM `reserved_bytes` and swap
  `reserved_swap_bytes` (confirmed separate, additive axes); the new
  regression test `test_new135_reserve_slot_wiring_actually_uses_
  persisted_pending_claim` was independently re-verified by the reviewer
  (hand-reverted the wiring line, reran, confirmed it fails without the
  fix); `MAX_SWAP_ASSIST_BYTES` (6.50GiB, M1-F) confirmed unchanged; full
  suite independently rerun by the reviewer: 669 passed, 1 skipped,
  matching the implementing session's own count. **This finding is now
  FIXED and code-reviewer-approved** for the `reserve_slot()`/
  `can_admit()` path; not live-verified (no live component by design —
  this is admission-accounting logic, not a model-load test).
- **Status update, 2026-08-25 — FIXED for the `reserve_slot()`/`can_admit()`
  path, code-complete and self-tested, NOT yet mandatory-code-reviewer-
  approved (rule 4).** `compute_swap_assisted_headroom_bytes()` gained a
  `reserved_swap_bytes` parameter (subtracted from the policy cap
  `max_swap_usage_bytes`, not from live `SwapFree` — see the function's own
  docstring for why); `can_admit()` gained the same parameter, threaded
  straight through; `GateDecision` gained `swap_bytes_claimed` (a
  magnitude, not just the `admitted_via_swap` boolean, so it can be summed
  — this also directly satisfies `NEW-136`'s fix-direction note, see that
  entry). `reserve_slot()` now computes the real PENDING-only sum of other
  slots' `swap_bytes_claimed` inside its own existing lock (mirroring the
  RAM-side `reserved`/`committed` sums it already computed there) and
  passes it through, then persists the admitted decision's own claim onto
  the new slot record — closing the exact double-claim race this finding
  describes for any caller going through `reserve_slot()`. A new
  `total_reserved_swap_bytes()` helper mirrors `total_reserved_bytes()` for
  any direct `can_admit()` caller outside `reserve_slot()` (none exist in
  this codebase today). Eight new regression tests in
  `tests/test_resource_gate.py` (prefixed `test_new135_`), including one
  that reproduces the exact pre-fix double-admission and confirms it is
  now refused, and one (`..._wiring_actually_uses_persisted_pending_claim`,
  added after advisor review) that pre-loads a PENDING slot's claim via
  `register_slot()` with no hand-fed `reserved_swap_bytes` — confirmed to
  fail if `reserve_slot()`'s own wiring line is deleted, proving the fix is
  actually connected in production and not just correct in isolation.
  Full suite: 669 passed, 1 skipped (was 661/1 before this
  round). **Also stale-corrected while in this entry (rule 6):** the
  2026-08-11 note below cites `MAX_SWAP_ASSIST_BYTES` values (768MiB, then
  a hypothetical 10GiB) that predate M1-F's 2026-08-24 re-derivation to
  6.50GiB — left in place as the original record, not edited, since
  correcting it in place would misrepresent what was actually known at the
  time; this note is the current, accurate figure. **NOT fixed**:
  `can_dispatch_task()`'s separate swap-assist consumer (it registers no
  slot, so this accounting mechanism has nothing to sum against on that
  side — see `can_admit()`'s own docstring, "Caveats carried forward"
  section, for the explicit statement of this residual gap). **Needs the
  mandatory rule-4 code-reviewer pass before this can be marked done** —
  this touches the resource gate's admission accounting directly.
- **Status update, 2026-08-11 (same session as TODO.md 7.4a sub-item F) —
  still Confirmed, blast radius widens with the F recalibration.** This
  finding's worst-case double-count was bounded by whatever
  `MAX_SWAP_ASSIST_BYTES` is at the time — today (768MiB) that's a ≤768MiB
  overlap; if `can_admit()`'s cap is raised to 10GiB per 7.4a-F, the same
  structural gap allows a ≤10GiB overlap between two racing PENDING
  admissions. `can_dispatch_task()`'s side of this is unaffected by F (its
  own `DISPATCH_MAX_SWAP_ASSIST_BYTES` stays at 768MiB per F's explicit
  dispatch/admission split), but `can_admit()`'s side is not — this is not
  a new bug introduced by F, but F meaningfully changes how much this
  existing gap can actually cost if it fires. Not fixed as part of F
  (same reasoning as this entry's own "not a same-day fix" note below);
  flagged so whoever eventually revisits `reserve_slot()`'s concurrency
  handling has the current real number, not the stale 768MiB one.
- **Status: Confirmed** — verified directly against `core/resource_gate.py`.
  `compute_headroom_bytes(meminfo, reserved_bytes=0)` accepts a
  `reserved_bytes` parameter specifically so a second concurrent admission
  attempt sees the first one's already-claimed RAM subtracted out (see its
  own docstring). `compute_swap_assisted_headroom_bytes(meminfo,
  max_swap_usage_bytes, slmk_floor_gate_multiplier=...)` has no equivalent
  parameter — it reads live `SwapFree` and `MAX_SWAP_ASSIST_BYTES` fresh on
  every call, with no way for `can_admit()` to tell it "768MiB of this cap
  is already spoken for by another PENDING slot." Two model loads racing
  through `reserve_slot()` at (nearly) the same time, both failing the
  plain-RAM `required > headroom` check, could each independently be told
  the full 768MiB swap-assist cap is available and each be admitted via
  swap — the combined real swap usage could exceed what
  `MAX_SWAP_ASSIST_BYTES` was sized to authorize as a single-load ceiling.
- **Why this wasn't fixed in C2 itself:** doing so would change sub-task
  B's own function signature (`compute_swap_assisted_headroom_bytes()`),
  which C2's mandate is to wire, not redesign — flagged rather than
  silently expanded in scope, per CLAUDE.md rule 8.
- **Where found:** implementer flagged this directly in C2's own PR
  description; code-reviewer independently re-verified by reading both
  functions' signatures and docstrings side by side before logging it here
  (not taken on the implementer's word alone).
- **Fix direction, if picked up later:** give
  `compute_swap_assisted_headroom_bytes()` a `reserved_swap_bytes`-style
  parameter mirroring `compute_headroom_bytes()`'s existing
  `reserved_bytes`, and have `can_admit()`/`reserve_slot()` pass through
  the same already-committed-swap-usage figure the RAM-side check already
  tracks (or a dedicated swap-side equivalent, if the two shouldn't share
  one accounting figure) — likely a `reserve_slot()`-adjacent sub-task of
  its own, not a same-day fix.

### [NEW-136] `GateDecision.admitted_via_swap` is not persisted into the slot record — `register_slot()`/`list_slots()` give a later reader no way to tell which resident slots were swap-admitted

- **Status update, 2026-08-25 (later same day) — mandatory rule-4
  code-reviewer pass complete: APPROVED, no changes required**, as part of
  the same review that approved `NEW-135` (see that entry's own updated
  status for the full reviewer findings — the two fixes shipped in one
  change and were reviewed together). **This finding is now FIXED and
  code-reviewer-approved**; not live-verified (no live component by
  design).
- **Status update, 2026-08-25 — FIXED, code-complete and self-tested, NOT
  yet mandatory-code-reviewer-approved (rule 4).** Fixed as a magnitude
  rather than a bare boolean, per this entry's own fix-direction note and
  because `NEW-135`'s fix needed a magnitude to sum, not just a flag (a
  bool alone can't be summed to recover how much swap a set of PENDING
  slots collectively claimed). `register_slot()` gained a
  `swap_bytes_claimed: int = 0` parameter, persisted onto every slot
  record; `reserve_slot()` passes `decision.swap_bytes_claimed` through
  automatically. A later reader can derive the old boolean trivially
  (`slot["swap_bytes_claimed"] > 0`) if only the flag is wanted — this
  entry's own fix-direction note anticipated the field being useful for
  "which resident slot is the best unload candidate under memory
  pressure" reasoning; that consumer is not built yet (no live
  thermal/swap-pressure responder exists today) but the data it would need
  is now recorded. See `NEW-135`'s own updated entry for the shared
  implementation and test details (`core/resource_gate.py`,
  `tests/test_resource_gate.py`'s `test_new135_*` tests, one of which
  directly asserts the persisted field). **Needs the mandatory rule-4
  code-reviewer pass before this can be marked done.**
- **Status: Confirmed** — verified directly against `core/resource_gate.py`.
  `register_slot()`'s parameter list (`model_id`, `cost_bytes`, `pid`,
  `port`, `threads`, `status`, `state_dir`) has no `admitted_via_swap` (or
  equivalent) field, and the slot dicts `list_slots()` returns carry
  nothing derived from it either. `GateDecision.admitted_via_swap` exists
  only on the transient return value of `can_admit()`/`reserve_slot()` at
  admission time — once a slot is registered, that distinction is lost.
  A later reader (a live-verification pass, a daemon status command, a
  future thermal/swap-pressure responder trying to decide which resident
  slot is the best unload candidate) has no way to ask "which of my
  currently-resident slots got here via swap assist, and are therefore the
  ones most likely to be thrashing / worth unloading first under memory
  pressure" without re-deriving it from scratch.
- **Why this wasn't fixed in C2 itself:** C2's mandate is `can_admit()`
  wiring; touching `register_slot()`'s schema is exactly the kind of
  "second separate schema change" TODO.md's C2 scoping note already
  warned against doing piecemeal (see C1+C2's shared `GateDecision` field
  addition, done once, not twice) — flagged rather than silently expanded,
  per CLAUDE.md rule 8.
- **Where found:** implementer flagged this directly in C2's own PR
  description; code-reviewer independently re-verified by reading
  `register_slot()`'s full parameter list and `list_slots()`'s return
  shape before logging it here (not taken on the implementer's word
  alone).
- **Fix direction, if picked up later:** add an `admitted_via_swap`-style
  field to the slot record schema (likely alongside whichever sub-task
  next needs to reason about resident-slot provenance for
  unload/routing decisions — sub-task D or a live-verification follow-up
  are the natural homes), and have `reserve_slot()` pass its own
  `GateDecision.admitted_via_swap` result through to `register_slot()`/
  `mark_resident()` at the point it already has that decision in hand.

### [NEW-137] Sub-task E live pass: real production `n_ctx=32768` never actually reaches the swap-assisted admission branch at any live headroom observed this session — `MAX_SWAP_ASSIST_BYTES=768MiB` is too small to close the observed deficit at the shipped default

- **Status update, 2026-08-11 (same day, later session) — Confirmed,
  superseded by TODO.md 7.4a sub-item F (recalibration), pending live
  verification, NOT resolved.** Ish increased this device's real swap
  capacity to ~16.0GiB (`SwapTotal`, confirmed via
  `/sys/block/zram0/disksize`=17,179,869,184 bytes) and directly decided
  to raise `MAX_SWAP_ASSIST_BYTES` close to the formula's live-computed
  ceiling (~10.69GiB this session) rather than just patch this finding's
  gap. Project-architect scoped a recommended new value,
  `MAX_SWAP_ASSIST_BYTES = 10GiB` for `can_admit()` (see TODO.md 7.4a-F
  for the full derivation) — by arithmetic, this should make the real
  `n_ctx=32768` case reachable at essentially any live `MemAvailable`
  this device currently shows (`headroom_bytes + min(10GiB,
  gated_swap_free) >= required_bytes` holds even at `headroom_bytes=0`,
  since `gated_swap_free`≈10.69GiB already exceeds the 10GiB cap and
  `required`≈8143MiB is well under 10GiB). **This is arithmetic, not a
  live observation — this finding stays Confirmed/open until a fresh
  live-verification pass actually re-runs sub-task E's procedure at
  `n_ctx=32768` with the new cap in place and reports a real
  `admitted=True, admitted_via_swap=True` result, not an assumed one.**
  Not implemented yet as of this note — `core/resource_gate.py` still
  reads `MAX_SWAP_ASSIST_BYTES=768MiB` on disk; the recalibration is
  scoping only pending implementer + code-reviewer + live-verifier per
  TODO.md 7.4a-F's explicit follow-up plan.
- **Status: Confirmed**, live-measured 2026-08-11. At the real, unmodified
  production default (`n_ctx=32768`, `CODEY_N_CTX` unset), a live dry-run
  of `can_admit()` against the real primary `ModelSpec` and live
  `/proc/meminfo` on this device (`MemAvailable` ranging ~6.6-6.8GiB
  across several samples this session) computed `required≈8143MiB` vs.
  `headroom≈6761-6787MiB` (deficit ≈1356-1382MiB). Swap-assist can only
  ever contribute `MAX_SWAP_ASSIST_BYTES=768MiB` at most (`combined
  headroom≈7517-7555MiB`), which is still short of `required` by
  ~600-650MiB — `can_admit()` returns `admitted=False,
  admitted_via_swap=False` at 32768 in every live sample taken this
  session, i.e. the swap-assist path is reached (correctly, since
  `required > headroom` on RAM alone) but never actually flips the
  outcome at this device's currently-observed memory conditions.
  Verbatim: `GateDecision(admitted=False, hard_reject=False, reason="model
  'primary' cost estimate (6514MiB) x headroom_factor (1.25) = 8143MiB,
  which exceeds current headroom (6761MiB)", estimated_cost_bytes=
  6830557184, headroom_bytes=7089922048, device_ceiling_bytes=6973870080,
  budget_ceiling_exceeded=False, admitted_via_swap=False)`.
- **What this means for sub-task E's mandate:** the live pass could not
  exercise swap-assisted admission at the real 32768 default without
  either (a) waiting for a more favorable natural memory state that never
  occurred during this session's observation window, or (b) an env-var
  deviation. `CODEY_N_CTX=16384` was used instead (explicitly permitted by
  this pass's own instructions as a config-override lever) — confirmed via
  live dry-run to land in the swap-admitted band
  (`admitted=True, admitted_via_swap=True`, `required=7023MiB` vs.
  `headroom≈6378-6521MiB`, `combined_headroom≈7146-7289MiB`) and used for
  the actual spawn. **This means sub-task E's live pass validates the
  swap-assisted-admission *mechanism* end-to-end (real gate, real spawn,
  real inference, real teardown) but NOT the production `n_ctx=32768`
  case specifically** — that combination was not reachable this session.
  See TODO.md 7.4a sub-task E's own write-up for the full run.
- **Fix direction, if picked up later:** either accept `MAX_SWAP_ASSIST_BYTES=768MiB`
  as deliberately conservative (it only ever closes gaps up to ~750MiB,
  which this session's data suggests is smaller than the typical deficit
  at 32768 on this device under normal load), or revisit the constant with
  this session's real deficit figures in hand (Ish's call, not assumed
  here — this is exactly the kind of calibration TODO.md's own C2 write-up
  said sub-task E's live pass should inform). Not fixed here — this entry
  is the calibration data point, not a proposed new value.

### [NEW-138] (RE-REVISED after a second advisor review, same session — see history below) Live-observed llama-server RSS (~6.58-6.96GiB at `n_ctx=16384`, once tracking began) exceeds the gate's own declared cost estimate (5.6GiB); the file/anon RSS split is UNMEASURED, not quantifiable from this run's data

- **Status: Confirmed** for the raw RSS-vs-declared-cost gap; **the
  anon/file split figure in an earlier draft of this entry was withdrawn
  — do not use it.** This entry has now been corrected twice in the same
  session (rule 6): first for a unit-conversion error (kB vs GiB), then
  for an unsupported subtraction assuming full weight-file residency.
  Both corrections are recorded here rather than silently overwritten.
- **The measured facts**: `cost = estimate_model_load_cost(spec)` at
  `n_ctx=16384` returned `model_bytes=4683073536` (4.36GiB),
  `kv_cache_bytes=939524096` (0.94GiB), `overhead_bytes=268435456`
  (0.27GiB) → total 5891033088 bytes (5.6GiB). The spawned
  `llama-server` process (PID 513, launched with `--mmap`, confirmed via
  this run's own driver output: `mmap=enabled, mlock=disabled`) reported
  `VmRSS=7300956 kB` at first sample (correctly converted: 7,300,956 KiB
  × 1024 = 7,476,178,944 bytes ≈ **6.96GiB**, NOT the ~7.13GiB an earlier
  draft of this entry stated from a bad kB→GiB conversion), settling to
  a **~6.58-6.96GiB** range for the rest of the observed window (see
  TODO.md 7.4a sub-task E's own corrected step 6 for the full sample
  list and the separate finding that RSS sampling itself only began
  ~22s into the load, missing the earliest and riskiest part of the
  window).
- **Why the file/anon split cannot be quantified from this run**: an
  earlier draft of this entry subtracted the full 4.36GiB `model_bytes`
  (weight file size) from peak RSS to estimate an anon-memory residual —
  this assumes the entire weight file was resident, which this run's own
  data contradicts. Baseline `/proc/meminfo` `Cached: 5662696 kB`
  (5.40GiB); `free -h` during/after the load showed `buff/cache` at only
  ~2.8-3.0GiB — **below the 4.36GiB weight-file size**, meaning at most
  ~2.8-3.0GiB of the mmap'd file (and every other cached file on the
  system, further reducing the true figure) was actually resident, not
  the full 4.36GiB. This implies the true anonymous-memory share of RSS
  is LARGER than a naive "peak minus model_bytes" subtraction would
  suggest, not smaller — but this run's monitor sampled only aggregate
  `VmRSS` (via `/proc/<pid>/status`'s `VmRSS:` line), not the
  `RssAnon`/`RssFile`/`RssShmem` breakdown the same file also exposes,
  and the process is gone — **this cannot be reconstructed after the
  fact for this run.** The correct, honest statement is: **a real RSS
  gap above the gate's declared cost exists and is measured; how much of
  it is anonymous (unreclaimable, budget-relevant) vs. file-backed
  (reclaimable) is NOT measured and remains open.**
- **Candidate cause, not verified**: `--embedding --pooling mean` present
  on this run's actual launch command line (visible in the live `ps aux`
  capture) — an internal embedding-batch allocation not represented at
  all in `estimate_model_load_cost()`'s three-term model.
- **Fix direction, if picked up later**: a future harness sampling
  `/proc/<pid>/status`'s `RssAnon`/`RssFile`/`RssShmem` lines (not just
  `VmRSS`) during a load would directly answer the anon/file split this
  run could not. Separately, `NEW-138`'s underlying harness gap (PID only
  available after `load_primary()` returns, so RSS tracking necessarily
  starts late) is worth fixing for any future live pass that wants full
  load-window coverage — `LlamaServer.start()`'s own log line
  (`llama-server PID: N`) prints before health-check completes and could
  be scraped earlier, or the harness could poll for the child process by
  other means.
- **Where found:** sub-task E's live monitor and its two-pass advisor
  review, same session, 2026-08-11.
- **Addendum, 2026-08-11, sub-task F's case (a) live-verification pass**:
  reproduced at a SECOND, higher `n_ctx` — at `n_ctx=32768`, peak observed
  `VmRSS` was 7714.4MiB against a declared cost of 6514MiB, a **~1200MiB
  (~1.17GiB) overshoot**, larger than the ~843-900MiB overshoot observed
  at `n_ctx=16384`. The harness that produced this reading also had the
  PID-acquisition gap closed (poll `loader.get_pid()` from a monitor
  thread starting at t=0, not wait for `load_primary()` to return — see
  TODO.md 7.4a-F's "G" write-up, Step 0), so this is a more complete
  sample of the load window than sub-task E's own 16384 run, not just a
  second data point at a different `n_ctx` — same open question (how much
  of the overshoot is anon vs. file-backed) remains unanswered; this
  pass's harness sampled `RssAnon`/`RssFile`/`RssShmem` for case (b2) but
  not case (a) (case (a) was written and run before that harness
  improvement landed mid-session — see case (b2)'s own write-up for the
  first run that does have the split).

### [NEW-139] `--mmap` on the spawned `llama-server` process means quantized-weight zram-compression ratio is structurally unmeasurable via this project's current live-test harness — the question `can_admit()`'s own docstring poses about weight-page compression remains open, not answered by sub-task E's live pass

- **Status: Confirmed**, discovered on advisor review of sub-task E's live
  pass (2026-08-11), before the pass's first-draft write-up (which
  incorrectly claimed the ~3.6:1 zram ratio observed during the run
  "carries over to quantized 7B model weight pages") shipped — corrected
  in place per CLAUDE.md rule 6, this entry records the underlying
  structural finding separately so it isn't lost inside E's own
  corrected write-up.
- **The finding**: `core/loader_v2.py`'s `LlamaServer` launches
  `llama-server` with `--mmap` (confirmed live this session:
  `7B model: mmap=enabled, mlock=disabled`, both this run's driver
  output and the live `ps aux` command-line capture). Under `--mmap`,
  GGUF weight pages are file-backed mappings — clean pages reclaimed
  directly back to the model file on disk under memory pressure, never
  written to swap/zram (this is standard Linux VM behavior for
  file-backed vs. anonymous pages, not something specific to this
  codebase). This means **the entire model-weight-compression question
  `compute_swap_assisted_headroom_bytes()`'s own docstring and TODO.md
  7.4a's scoping text raised — "quantized weight pages may compress far
  less favorably than the ~4:1 idle-anon-page ratio" — cannot be
  answered by observing zram `mm_stat` during a normal `--mmap` load at
  all**, regardless of how careful the sampling is. Any zram delta
  observed during such a load is necessarily some other anonymous
  memory (other processes, or the server's own non-weight allocations)
  being swapped under the pressure the load creates, not weight pages.
- **Where found:** cross-referencing this run's own driver output/`ps
  aux` capture (`--mmap` flag) against `core/resource_gate.py`'s
  docstring language about the open compression-ratio question, during
  advisor review of sub-task E's first-draft results.
- **Fix direction, if picked up later:** answering the original question
  would need a launch configuration where weight pages are anonymous —
  not `--mlock` alone (mlock just pins file-backed pages resident, it
  doesn't make them anonymous/swap-eligible), but genuinely disabling
  the mmap load path if `llama-server`/`llama.cpp` exposes one, or
  accepting the question as effectively moot for this project's actual
  shipped configuration (if `--mmap` is permanently how this project
  loads models, quantized weight pages structurally never reach zram
  under normal operation, making the original compression-ratio concern
  inapplicable to this codebase's real behavior rather than merely
  unmeasured). Ish's call on which framing to adopt — not decided here.

### [NEW-140] TODO.md 7.4a sub-task F's 10GiB `MAX_SWAP_ASSIST_BYTES` recalibration makes the exact historical `NEW-21` SINGLE-MODEL swap-distress device state admissible again via swap-assist at the real production `can_admit()` call shape — not previously flagged, only the concurrent 3-model consequence was

- **Status update, 2026-08-25 — "scenario 3" (the low-swap-headroom
  single-model case this finding's title describes) CLOSED per `NEW-159`'s
  bar; the finding's OTHER content is unaffected and stays Confirmed.**
  This finding is really two things: (1) the general observation that a
  raised `MAX_SWAP_ASSIST_BYTES` re-admits the historical `NEW-21` device
  state via swap-assist for a single model load — a live, generic
  mechanism finding, not tied to any specific retired model, still fully
  applicable to Qwen3.5-4B and unaffected by this closure; and (2) the
  specific worked numeric example below, computed against the retired
  7B's `cost.total_bytes=6,830,557,184` and the superseded 10GiB cap. Item
  (2)'s exact figures are stale (7B retired, cap re-derived to 6.50GiB by
  M1-F) and item (1)'s live mechanism has not been re-measured against
  Qwen3.5-4B's real cost — that re-measurement is exactly what M1-E's own
  entry means by "still needs its own re-check against these live
  numbers." What CAN close today, per `NEW-159`'s bar (M1-D code-read +
  M1-E live pass, both done): the worked numbers below are retired-model
  arithmetic, not evidence about current behavior, and must not be read as
  still describing the shipped system. The general mechanism (1) is left
  open as a live, standing concern — not closed by this update — since
  nothing about swap-assist's admit-under-distress behavior changed with
  the model swap.
- **Status update, 2026-08-26 — re-measured against real Qwen3.5-4B cost
  figures, per this update's own stated requirement. Item (1)'s general
  mechanism is CONFIRMED, not resolved, and the concrete outcome is WORSE
  than the stale retired-7B example below, not merely "still applicable."
  See `NEW-188` for the full re-derivation, real numbers, and the fresh
  worked example that replaces the stale one below as the current-model
  evidence. `NEW-140` stays OPEN; `NEW-188`'s existence does not close
  this entry — `NEW-188` is the up-to-date restatement of exactly this
  finding's item (1), not a separate, independent issue.**
- **Status update, 2026-08-26 — the live low-swap-headroom single-model
  pass this finding's "Required addition to the live-verification plan"
  called for HAS now been run, live, against the real, unmodified
  `python3 main.py --no-resume` path (M1-E's established precedent),
  under Ish's explicit "natural-state-only" scope choice for this round
  (no deliberately-induced memory pressure). Result is genuinely mixed,
  not a clean close — read both axes, don't collapse them into one:**
  - **Axis (a), swap-assist mechanism activation on the real device under
    real ambient conditions — CONFIRMED, for the first time.** `free -h`
    before/after: `4.2Gi used, 806Mi free, 6.3Gi available` →
    `3.2Gi used, 5.2Gi free, 7.3Gi available`; `ps aux | grep
    llama-server` clean before and after; model stopped via `main.py`'s
    own graceful `/exit` (no residual PID, rule 3 never engaged). Real
    `/proc/meminfo` at the exact moment `reserve_slot()` ran:
    `MemTotal=11,623,120,896` (10.826GiB), `MemFree=611,188,736`,
    `MemAvailable=6,476,886,016` (6.0321GiB), `SwapTotal=17,179,865,088`
    (16.000GiB), `SwapFree=15,478,288,384` (14.415GiB, 90.1% free). Real
    `GateDecision`, all fields: `admitted=True hard_reject=False
    reason="model 'primary' cost estimate (4968MiB) x headroom_factor
    (1.25) = 6210MiB exceeds RAM-only headroom (6177MiB), but is covered
    by RAM + swap-assisted headroom (12833MiB, of which 6656MiB is
    swap-assisted) — admitted via swap assist"
    estimated_cost_bytes=5,209,547,936 headroom_bytes=6,476,886,016
    device_ceiling_bytes=6,973,872,537 budget_ceiling_exceeded=False
    admitted_via_swap=True swap_bytes_claimed=35,048,904`. Ambient
    `MemAvailable` (6.0321GiB) sat only ~35MiB below the real required
    cost threshold (6.0647GiB, cost×1.25) — a small, real, UNFORCED
    shortfall from ordinary system drift between two meminfo reads
    seconds apart, not anything induced. This is the first of three live
    attempts (this one, plus the 32768 and 16384 sessions `NEW-137`/
    sub-task E ran) to actually land inside the swap-assist branch at
    all; the prior two only ever exercised the healthy-RAM path.
    **Corroboration worth noting: the live `estimated_cost_bytes`
    (5,209,547,936) matches `NEW-188`'s desk-only re-derivation
    (5,209,547,936) exactly** — the first real-production confirmation
    that `NEW-188`'s arithmetic input was correct, not just internally
    consistent.
  - **Axis (b), the compound low-RAM-AND-low-swap `NEW-21`-shaped
    distress state this finding and `NEW-188` actually worry about — NOT
    reproduced, stays open.** `SwapFree` was 14.415GiB of 16.0GiB total —
    90% free, nowhere near exhausted. The `NEW-21` fixture this finding
    and `NEW-188` are built on used `SwapFree≈6.8GiB` of an 8GiB total —
    genuine compound distress, not just a low-`MemAvailable` moment. In
    this live run, the operand that actually bound was
    `MAX_SWAP_ASSIST_BYTES`'s 6.50GiB cap headroom, not swap scarcity —
    only ~33MiB of a possible several-GiB swap-assist budget was leaned
    on. Do not describe this run as "the low-swap-headroom pass `NEW-140`
    called for" without this `SwapFree` caveat in the same sentence —
    that framing would overclaim what was actually observed.
  - **New device-behavior fact, not previously logged**: this is the
    THIRD consecutive live session (this one, plus the two `NEW-137`/
    sub-task E sessions) in which this device's real swap pool has been
    found healthy (≥90% free) during an actual model load, never once
    presenting the compound low-swap state naturally. That is itself
    informative about this device's real usage pattern, not proof the
    risk is unreachable — three observations is a small sample and this
    round explicitly excluded any attempt to induce the state.
  - **Conclusion — 7.4a's checkbox stays UNCHECKED, but the residual is
    now narrower than it was.** The prior wording ("solely blocked on the
    still-never-run live low-swap-headroom single-model verification
    pass") is now inaccurate — that pass has been run. What remains open
    is specifically the compound low-RAM+low-swap state, not general
    swap-assist activation (which is now confirmed live). Per this
    project's own `NEW-141` precedent ("close on the decision rather than
    on a fix"), whether to (a) authorize a future round to deliberately
    induce the compound state, or (b) accept the residual as a standing,
    documented, low-probability-on-this-device risk and close 7.4a on
    that decision, is Ish's call, not a default either direction — logged
    as `CODEY_MASTER_PLAN.md` §8 Q10. `NEW-140` and `NEW-188` both stay
    OPEN pending that decision.
- **Status update, 2026-08-26 — Ish answered §8 Q10: "accept the residual
  as a standing documented risk for now."** Option (b) above. **Status:
  OPEN, but no further live-verification work is planned against it** —
  a deliberate distinction, not a downgrade to Confirmed-and-forgotten.
  Axis (a) (general swap-assist activation on this device) is closed by
  the 2026-08-26 live pass above. Axis (b) (the compound low-RAM-AND-
  low-swap `NEW-21`-shaped distress state) — this finding's remaining
  live content — was never reproduced across three consecutive live
  sessions and is now accepted as a standing, documented,
  low-probability-on-this-device risk by Ish's explicit decision, rather
  than pursued with a fourth deliberately-induced attempt. Left OPEN
  rather than marked Resolved because the underlying arithmetic (the
  exact `NEW-21` fixture is admissible via swap-assist under the current
  6.50GiB cap) is real and undisputed — this decision stops the chase,
  it does not refute the finding. 7.4a is CLOSED in
  `CODEY_MASTER_PLAN.md` on this same decision — see its Appendix A entry
  and §8 Q10 for Ish's exact wording.
- **Status: Confirmed** — found during code-reviewer's mandatory pass on
  sub-task F (CLAUDE.md rule 4), independently re-derived, not just taken
  from the implementer's own disclosure (which correctly flagged it in
  `tests/test_resource_gate.py`'s `test_new21_production_call_shape_
  swap_assist_may_now_admit`, but had no tool to log it here itself —
  logging it is this review's job per rule 8).
- **The finding**: at the exact `NEW-21` fixture shape (`SwapTotal=8.0GiB`,
  `SwapFree=6.8GiB`, `MemTotal=10.8GiB`, `MemFree=2.2GiB`, primary 7B at
  the real production `n_ctx=32768` default) and `reserve_slot()`'s real
  call shape (`enable_swap_assist` left unset, resolving to the
  default-ON path), `can_admit()` now ADMITS via swap-assist at 3 of the
  4 `MemAvailable` points in `NEW-21`'s own plausible range
  (3.5/5.0/6.5GiB), and only denies at the 2.2GiB floor (`MemAvailable
  == MemFree`, i.e. no reclaimable cache at all). Independently
  re-verified live against the real `can_admit()`/`_new21_meminfo()`/
  `_new21_primary_spec()` code (not just trusting the test's own
  assertions):
  ```
  2.2 admitted=False via_swap=False cost=6830557184 headroom=2362232012
      reason: cost 8143MiB exceeds current headroom (2253MiB)
  3.5 admitted=True  via_swap=True  cost=6830557184 headroom=3758096384
      reason: 8143MiB exceeds RAM-only headroom (3584MiB), but covered by
      RAM + swap-assisted headroom (8909MiB, of which 5325MiB is
      swap-assisted) — admitted via swap assist
  5.0 admitted=True  via_swap=True  ... swap-assisted headroom 10445MiB,
      5325MiB swap-assisted
  6.5 admitted=True  via_swap=True  ... swap-assisted headroom 11981MiB,
      5325MiB swap-assisted
  ```
  The 5325MiB swap contribution at every admitted point matches the
  fixture's own `gated_swap_free = SwapFree - 2*slmk_floor = 6.8 -
  2*0.8 = 5.2GiB` term (the `min(10GiB, 5.2GiB)` operand binding, not the
  10GiB cap itself) — confirms this isn't an artifact of the new 10GiB
  ceiling alone, but of the combination of the raised ceiling with a
  `SwapFree`/`SwapTotal` ratio this device's real swap increase now
  produces routinely.
- **Why this is a genuine gap in TODO.md 7.4a sub-task F's own
  follow-up live-verification plan, not just a restatement of an
  already-flagged risk**: sub-task F's write-up (TODO.md, "Concurrent-
  admission consequence" paragraph) explicitly worked through and
  flagged the analogous consequence for a SECOND, concurrently-admitted
  model (primary already resident, planner reserving next) reaching
  `NEW-14`/`NEW-21`-shaped conditions, and its "Required follow-up" item
  3(b) mandates a fresh live-verification pass specifically covering
  that concurrent case at `n_ctx=32768`. It does NOT separately call out
  that the SAME `NEW-21` device state is now also admissible for a
  SINGLE model load with nothing else resident — item 3(a)'s
  "single primary-model load" case, as written, does not specify testing
  it under low-swap-headroom conditions; a live-verifier following that
  item literally could satisfy it entirely under a healthy `MemAvailable`
  state (as sub-task E's own 16384 run happened to be) and never actually
  exercise the low-headroom branch this finding identifies, even though
  it is a single-model scenario within scope of item 3(a)'s own stated
  purpose.
- **Required addition to the live-verification plan** (not fixed here —
  this is a finding, not a redesign; TODO.md 7.4a-F's own instruction
  was "do not change either ceiling" as part of this pass): item 3(a)'s
  "single primary-model load ... at the REAL production `n_ctx=32768`
  default" case must explicitly include a run where the device's live
  `SwapFree`/`MemAvailable` are LOW at the moment of the load — not just
  a healthy-state confirmation that the mechanism works, the way sub-task
  E's 16384 run was. If this device's real live state doesn't naturally
  present a low-swap-headroom moment during that pass (as was already
  true for sub-task E's 32768 attempt, per `NEW-137`), the live-verifier
  must say so explicitly and not silently substitute a healthy-state run
  as if it covered the same case — same honesty standard `NEW-137`/
  `NEW-138` already held themselves to.
- **Where found:** code-reviewer's mandatory sub-task F review,
  2026-08-11, cross-checking `test_new21_production_call_shape_swap_
  assist_may_now_admit` (`tests/test_resource_gate.py`) against a live
  Python re-run of the same fixture through the real `can_admit()`.

## Found during TODO.md 7.4a sub-task F's required live-verification pass, 2026-08-11 (live-verifier, delegated per Ish's explicit authorization) — NOT fixed here, logged only

### [NEW-141] Real concurrent primary+planner load at `n_ctx=32768` (new 10GiB `MAX_SWAP_ASSIST_BYTES` cap) reproduces `NEW-14`'s swap-distress shape with only 2 models, in ~6s (faster, fewer models than `NEW-14`'s original 3-model/~40s observation) — live-verifier's pre-declared rate-trip abort criterion correctly fired and stopped it

- **Status update, 2026-08-25 — CLOSED per `NEW-159`'s own stated bar.**
  `NEW-159` set two conditions before this could close: M1-D's code read
  confirming the retired paths are actually gone (done, 2026-08-23,
  code-reviewer-approved) and M1-E's live pass (done, 2026-08-23, "fully
  live-verified"). Re-confirmed directly against HEAD this round, not
  assumed from the prior code-read: `core/planner_loader.py` does not
  exist on disk, and `_evict_planner_and_confirm_free()` is absent from
  `core/loader_v2.py` (only referenced in a historical comment at line
  978-979 explaining its deletion). This finding's own reproduction
  required calling `core.planner_loader.PlannerLoader.load()` directly — a
  module that no longer exists, so the exact code path this finding
  exercised is now structurally unreachable, not merely superseded by a
  policy decision. Closing on the configuration no longer existing is
  consistent with this entry's own §4.3 framing ("close on the decision
  rather than on a fix"). Not fixed by new arithmetic — nothing to
  re-derive, since there is no longer a second concurrent model class for
  this scenario to apply to.
- **Status: Confirmed** — directly observed, live, tracked-PID teardown
  clean afterward.
- **Where found:** sub-task F's case (b2) live-verification pass, run via
  a dedicated harness calling `core/loader_v2.py:ModelLoader.
  load_primary()` then, while the primary stayed genuinely resident,
  `core/planner_loader.py:PlannerLoader.load()` directly (NOT
  `ensure_planner()`, which evicts the primary first — see the separate
  structural finding below). Both real production code paths, not mocked.
- **The finding**: with the primary 7B resident at `n_ctx=32768`
  (`MemAvailable`=1819MiB, `SwapFree`=13712MiB, primary `RssAnon`=
  6263.3MiB), calling `PlannerLoader.load()` triggered a real, fast,
  substantial swap-out event: in the ~6s between t+12.7s and t+18.7s,
  `SwapFree` dropped 2209MiB in a single 3s sample interval (from
  13525MiB to 11319MiB), the primary's own `RssAnon` collapsed from
  6263.3MiB to 3071.5MiB (a ~3192MiB anonymous-page swap-out, not RSS
  simply being freed — `RssFile` also dropped, from 720.9MiB to 0.9MiB,
  a separate mmap-reclaim signal), and zram `mm_stat`'s `orig_data_size`
  rose by +2.13GB in the same interval — mutually consistent readings,
  not an artifact of any single sample. This closely matches `NEW-14`'s
  documented distress shape ("3 concurrent models hit 7.5-8.5GiB swap in
  ~40s") but was produced by only **2** concurrently-loading models
  (primary + planner, no daemon/embed stack) within **~6 seconds**, not
  ~40 — a faster, lower-threshold reproduction than `NEW-14`'s own
  finding.
- **Why this matters for sub-task F specifically**: this is the real,
  live confirmation of the concurrent-admission risk sub-task F's own
  scoping text flagged as a predicted-but-unverified side effect of
  raising `MAX_SWAP_ASSIST_BYTES` to 10GiB ("this recalibration... now
  permits admitting up to ~8.9GiB of declared model cost... at
  arbitrarily low live `MemAvailable`... recreating conditions `NEW-14`
  already found caused real distress"). That prediction is now directly
  observed, not just arithmetic.
- **What stopped it**: the live-verification harness's pre-declared
  rate-trip abort criterion (SwapFree drop >1.5GiB within one 3s sample
  interval — added specifically because sub-task E's own static floor
  criteria, reused unchanged for this pass's case (a), never fired and
  would not have fired here either: `SwapFree` stayed >10GiB above the
  2×slmk floor throughout). The rate criterion fired correctly and the
  harness tore down both processes via tracked PIDs (SIGTERM, then
  SIGKILL after a 3s grace period — no `pkill -f`, CLAUDE.md rule 3
  honored) within seconds; the device returned to a clean, healthy state
  immediately after (`free -h` available 6.3Gi, `ps aux | grep
  llama-server` empty, gate state store `[]`).
- **Not fixed here** — this is a live-verification finding about the
  real consequence of sub-task F's already-landed recalibration, not a
  new bug in the recalibration's own arithmetic (which sub-task F's own
  scoping already predicted this exact outcome). Candidate follow-ups for
  a future pass (not scoped here, Ish's call): (a) whether the
  concurrent-admission path this finding required deliberately bypassing
  production orchestration (`PlannerLoader.load()` called directly,
  skipping `ensure_planner()`'s sequential-swap eviction — see the
  structural finding below) to even reach should stay unreachable via any
  shipped code path, in which case this finding is evidence the existing
  sequential-swap guard is doing real, load-bearing safety work and
  should not be relaxed; (b) whether `MAX_SWAP_ASSIST_BYTES`'s 10GiB
  value (or `MAX_CONCURRENT_MODEL_BUDGET_BYTES`'s 8.90GiB, which was
  explicitly computed to admit the full 3-model stack) should be
  reconsidered now that this pass has live evidence, not just arithmetic,
  of the risk they jointly re-open; (c) the abort criterion set used here
  (static SwapFree floor + static MemAvailable floor + SwapFree rate-trip)
  is offered as a validated starting point for any future pass probing
  this same territory — the rate-trip term was necessary; the two static
  floors, again, never fired.

### [NEW-142] `core/planner_loader.py`'s `ensure_planner()` (the real production entry point `core/plannd.py:get_plan()` calls) evicts the primary model BEFORE ever reserving a slot for the planner — the concurrent-admission consequence TODO.md 7.4a sub-task F's own scoping flagged is structurally UNREACHABLE via any shipped orchestration path, only via calling `PlannerLoader.load()` directly

- **Status: Confirmed** — read directly from `core/planner_loader.py`
  (`ensure_planner()` → `_evict_primary_and_confirm_free()`, called before
  `self.load()`) and confirmed live during sub-task F's case (b)
  live-verification pass, 2026-08-11.
- **The finding**: Ish's sequential-swap decision ("the primary 7B model
  and this 1.5B planner must never be resident at the same time on this
  device," `core/planner_loader.py`'s own module docstring) is enforced
  at the `ensure_planner()`/`ensure_model()` orchestration layer, not at
  `reserve_slot()`/`can_admit()` (the resource gate itself has no
  knowledge of or opinion on this constraint — it would admit a
  concurrent planner reservation if asked, as `NEW-141`'s own b1 dry-run
  directly confirmed). This means a live-verifier — or any future
  caller — following the actual shipped production call path
  (`core/plannd.py:get_plan()` → `ensure_planner()`) would NEVER be able
  to observe the concurrent-admission scenario TODO.md 7.4a sub-task F's
  own scoping explicitly required live-verifying ("primary + planner
  loaded sequentially via real `reserve_slot()` calls... observing
  whether the second load is actually admitted via swap-assist at low
  real `MemAvailable`"), because `ensure_planner()` unloads the primary
  first, unconditionally, before the planner's own `reserve_slot()` call
  is ever reached.
- **Why this matters, both ways**: (1) it means today's real, shipped
  system is NOT actually exposed to the concurrent-residency risk
  `NEW-141` demonstrates — the sequential-swap guard genuinely prevents
  it in normal operation, a real existing safety property worth stating
  plainly, not just implicitly relying on. (2) it means sub-task F's own
  scoping instruction, taken literally ("via a real `reserve_slot()`/
  `load()` call sequence"), could only be satisfied by calling the
  lower-level `PlannerLoader.load()` method directly, bypassing the
  `ensure_planner()` orchestration wrapper that exists specifically to
  prevent this state — a deliberate, documented choice this pass made
  (see TODO.md 7.4a-F's "G" write-up, case (b) intro), not a
  shipped/supported code path. A future reader must not conclude
  concurrent primary+planner residency is a tested or supported
  production state from this pass's b1/b2 evidence — it is explicitly
  not, and remains actively prevented by `ensure_planner()`/
  `ensure_model()`'s own eviction logic.
- **Not fixed here** — not a bug, a structural fact about the existing
  sequential-swap guard's scope, surfaced because sub-task F's own
  concurrent-admission scoping did not anticipate it. No code change
  proposed; flagged so this pass's own evidence isn't misread later.
- **Where found:** sub-task F's case (b) live-verification pass,
  2026-08-11, direct read of `core/planner_loader.py` while scoping how
  to actually reach the concurrent-admission call shape.
- **Status: CLOSED, 2026-08-23 — closed on a code read, exactly as
  required above, never on the §1.4 decision.** M1-D deleted
  `core/planner_loader.py` in full (322 lines, including
  `ensure_planner()`) and deleted `core/loader_v2.py`'s
  `_evict_planner_and_confirm_free()` — the "obvious survivor to check"
  this finding named. Confirmed gone by direct code read; no
  evict-then-load sequence bypassing the gate's reserve path survives.

### [NEW-143] Primary 7B `estimated_cost_bytes` at `n_ctx=32768` sits only ~137MiB under `device_ceiling_bytes` (`hard_reject` threshold) — a small margin, not itself a bug

- **Status: Confirmed** (arithmetic, directly read from a live
  `GateDecision`), logged as a margin observation, not a defect.
- **Where found:** sub-task F's case (a) live-verification dry-run,
  2026-08-11: `estimated_cost_bytes=6,830,557,184` (6514MiB) vs.
  `device_ceiling_bytes=6,973,870,080` (6650MiB, from
  `compute_device_ceiling_bytes()` with `DEVICE_CEILING_USABLE_
  FRACTION=0.60`, unchanged/untouched by sub-task F) — a margin of
  ~143,312,896 bytes (~137MiB).
- **Why this matters**: this margin is a per-model HARD ceiling
  (`hard_reject=True` means "retrying later cannot change the outcome" —
  `core/loader_v2.py`'s own `LOAD_OUTCOME_GATE_DENIED_HARD` comment), not
  the swap-assisted headroom sub-task F actually recalibrated. A
  marginally larger model file (e.g. a different quantization, or the
  same file plus metadata growth from a future GGUF format revision), or
  any future change to `DEVICE_CEILING_USABLE_FRACTION`, could flip the
  real production `n_ctx=32768` default to a **permanent, non-swap-
  fixable** `hard_reject` — a materially different failure mode than
  anything sub-task F's own recalibration addresses (which only ever
  affects the swap-assisted-headroom branch, not this hard ceiling).
- **Not fixed here** — flagged as a margin worth monitoring, not a
  defect; no code change proposed. `compute_device_ceiling_bytes()`'s own
  basis was explicitly out of scope for sub-task F per that item's own
  "Explicitly out of scope" list.

### [NEW-144] `EmbedServer.start()` treats "port is bound" as "stale, kill and replace" with no health check first — a healthy embed server started by a DIFFERENT process gets killed and respawned by any other process that calls `start_embed_server()`

- **Status: Confirmed** — read directly, `core/embed_server.py:57-81`
  (`EmbedServer.start()`).
- **Where found:** scoping pass for Ish's 2026-08-11 "embed model always
  resident" decision (new TODO.md item, see WORK_QUEUE.md cross-ref),
  while tracing every call site of `start_embed_server()`
  (`core/daemon.py`'s `_main_loop` at startup and its 30s watchdog;
  `core/inference.py:_start_server()`, called on every `infer()` — i.e.
  every interactive turn in the TUI/CLI process, a DIFFERENT OS process
  than the daemon).
- **The bug, exactly:** `start()`'s only "already running, do nothing"
  fast path is `self.process and self.process.poll() is None and
  self._check_health()` — `self.process` is this specific `EmbedServer`
  Python object's own `subprocess.Popen` handle, which is `None` in any
  process that didn't itself spawn the embed server. Falling through,
  `start()` next checks `_port_is_bound()` alone (a raw TCP-connect
  check, deliberately not `_check_health()` — see that method's own
  docstring, written for a *different* purpose: detecting a foreign
  occupant that accepts a connection but never answers `/health`). If
  the port is bound — which it will be, correctly, whenever the daemon's
  embed server is already up and healthy — `start()` unconditionally
  logs "Stale process ... replacing" and calls `_kill_port_occupant()`,
  which resolves the real owning PID via `/proc` scan and `os.kill(pid,
  9)`s it, then spawns a brand new embed server in its place. There is
  no health check anywhere in this path that would let a second process
  recognize "this occupant is fine, leave it alone."
- **Concrete impact:** under `codey-start` (daemon + TUI both up, the
  normal product entry point), the daemon's `_main_loop` starts a
  healthy embed server at daemon startup. The very next time the TUI
  process runs `infer()` (i.e. the user's first prompt), `inference.py:
  _start_server()` calls `start_embed_server()` in the TUI's own
  process — which has no memory of the daemon's `Popen` object — sees
  the port bound, and kills + respawns the daemon's embed server. This
  repeats on every subsequent `infer()` call too, since the TUI's own
  freshly-spawned copy is likewise not the daemon's tracked object
  either way (a fresh `EmbedServer()`/module attribute is not created
  per call, but the singleton was already correctly caching *its own*
  spawn in a prior call — the destructive branch only fires the very
  first time a given process calls `start()` against an embed server it
  didn't itself spawn, which is still every single time codey-start's
  TUI process's first turn runs). Net effect: at least one unnecessary
  embed-server kill+respawn cycle (~1-2s per this module's own health-
  wait loop shape) per `codey-start` session, and a live PID/port
  churn event that this module's own extensive `_find_port_occupant_pid`
  /`_kill_port_occupant` commentary was written to guard *against*
  (foreign occupants), not something this project intends to trigger
  against its own daemon's own healthy process.
- **Why this matters for the new "always resident" decision:** this bug
  makes "always resident, never spun down except at Codey shutdown"
  structurally false today even before any new code is written — the
  TUI process itself tears the daemon's embed server down and back up
  on its own first inference call. Any sub-task implementing the
  always-on lifecycle decision must either fix this (single source of
  truth: only the process that "owns" the embed lifecycle start/stop's
  it; every other process only health-checks) or explicitly design
  around it — it cannot be left as-is and still satisfy the decision's
  own stated intent.
- **Not fixed here** — scoping-only pass, no code changed. Flagged as a
  likely-blocking prerequisite for the new TODO.md item's sub-task A
  (embed-server lifecycle change), not a standalone fix task.

## Found during TODO.md 7.4b implementation, 2026-08-11 — NOT fixed, logged only

### [NEW-145] `**net regression, not a neutral no-op**`: under `codey-start`, the coder almost always loads at the BACKGROUND 16384 ceiling even for the interactive TUI session — the daemon's own eager preload wins the race against the TUI's session-file write, so sub-task C's "full context while interactively used" case is not actually realized on the normal product entry path, and the interactive user now gets LESS context than before this round, not the same or more

- **Status: Confirmed** — read directly, `core/daemon.py`'s `_main_loop`
  (`_preload_primary_model()` call, line ~918) and `main.py`'s `main()`
  (`_write_tui_pid_file()` at line 1923, called only right before `repl()`
  starts). `codey-start` (`codey-start:47-65`) always starts the daemon
  first, then launches the TUI in the foreground.
- **Sequence, concretely:** `codey-start` starts the daemon → the daemon's
  `_main_loop` calls `_preload_primary_model()` → `ensure_model()` →
  `ModelLoader.load_primary()`, which (per this round's TODO.md 7.4b
  sub-task C change) reads `core.resource_gate.is_interactive_session_active()`
  at that instant. No TUI session pid file exists yet (the TUI process
  hasn't started, let alone reached `_write_tui_pid_file()`), so this
  evaluates False and the daemon spawns the 7B server at
  `utils.config.CODER_BACKGROUND_N_CTX` (16384). The TUI then starts,
  writes its session pid file, and on its own first `infer()` call also
  reaches `load_primary()` — which now correctly computes `n_ctx=32768`
  (interactive session active) for its own `resource_gate.ModelSpec`, but
  `LlamaServer.start()` (`core/loader_v2.py:211-230`) hits its
  `_is_port_in_use()` reuse branch first ("already running on port,
  using existing server", `self.process` left `None`) and reuses the
  daemon's already-spawned 16384-context server instead of respawning at
  32768 — the loader then releases its own gate reservation (the
  established "didn't spawn it, don't double-account" pattern) and never
  gets a 32768-context server at all.
- **Net effect:** under the normal product entry point (`codey-start`),
  Ish's 2026-08-11 decision 3 ("coder runs at full max context when the
  user is actively using it interactively") is not actually realized —
  the interactive session ends up running at the smaller
  `CODER_BACKGROUND_N_CTX` ceiling the whole time, because the daemon's
  own eager preload structurally always wins this race (it starts before
  the TUI process even exists). The mirror case (TUI's own `load_primary()`
  call landing first, e.g. a bare `codeyOS` invocation with no daemon
  running yet) does NOT have this problem — a solo TUI session with no
  daemon preloading ahead of it evaluates `is_interactive_session_active()`
  True and gets the full 32768 context correctly.
- **This is a net regression for the `codey-start` user, not a neutral
  no-op, and not merely "decision 3 unrealized":** before this round,
  `core/loader_v2.py:LlamaServer._spawn_locked()` had no interactive/
  background branch at all — every server it spawned (daemon preload
  included) used the unconditional `str(MODEL_CONFIG["n_ctx"])`, i.e.
  32768. So before this round, the daemon's own preload under
  `codey-start` already spawned the coder at 32768, and the TUI's first
  `infer()` reused that same 32768 server. After this round, the SAME
  race (daemon preloads before the TUI's session file exists) now
  resolves to the daemon spawning at 16384, and the TUI reuses THAT
  server instead. Net result for the ordinary `codey-start` interactive
  user: this round measurably SHRANK their real context from 32768 to
  16384 — the opposite of decision 3's stated intent, not just a
  same-as-before gap this round failed to close.
- **Why not fixed as part of 7.4b sub-task C:** TODO.md's own sub-task C
  write-up explicitly names `is_interactive_session_active()` (the exact
  signal 7.4 sub-task C already built) as the mechanism to reuse, "do not
  build a second detection mechanism" — implemented literally per that
  instruction. Fixing this race (e.g. having the daemon skip/defer its
  own eager preload when it suspects a TUI is about to attach, or having
  the TUI force a respawn at its own ceiling instead of reusing an
  under-provisioned server) is a real design decision beyond this
  sub-task's literal scope, and risks reintroducing exactly the kind of
  self-race CLAUDE.md rule 4 warns about if done without its own review
  pass.

- **Status update, 2026-08-11 (project-architect, scoping only — no code
  changed yet): Ish's fix decision given directly in-session.** Remove
  `core/daemon.py`'s eager coder preload entirely — only the embed model
  (7.4b sub-task A) stays always-resident; the coder loads lazily on
  first real request (interactive or background), so
  `is_interactive_session_active()` is evaluated at actual spawn time
  instead of guessed wrong at daemon startup. Accepted tradeoff: first
  real coder request after daemon start pays full load latency
  (~11-16s, this session's own live-test evidence), not a workaround to
  design around.
  **Scope also had to widen past the literal `_preload_primary_model()`
  call site**, found while scoping (not yet implemented): `core/daemon.py`'s
  30s watchdog (`_watchdog_check_model()`, line ~752) also calls
  `loader.ensure_model()` **unconditionally** on every tick, with no
  distinction between "was loaded and died — restart it" and "never
  loaded, nobody has asked yet — leave it alone." Left as-is, this
  watchdog becomes NEW-145's SAME failure shape under a wider exposure
  window than the bug being fixed: a persistent daemon (the normal
  `codey-start`/`codeyOS` steady state — `codey-start:48`'s
  `is_daemon_running` check skips daemon startup entirely when one is
  already up) sits with no TUI session registered, the watchdog's first
  tick (~30s after daemon start, or ~30s after the daemon's last
  restart) calls `ensure_model()` with `is_interactive_session_active()`
  False, spawns the coder at 16384, and a TUI attaching minutes or hours
  later reuses that same under-provisioned server via
  `LlamaServer.start()`'s port-in-use reuse branch — exactly like the
  original bug, just via the watchdog instead of the startup preload,
  and on the MORE common "already-running daemon" path, not just the
  "cold `codey-start`" path this issue was originally filed against.
  **Full scoped fix description (both call sites, one round, ready for
  implementer) written into TODO.md's 7.4b sub-task C section** — see
  the "NEW-145 fix" amendment there for the exact mechanism (a new
  `ModelLoader.was_ever_loaded()`-style signal the watchdog gates on
  before calling `ensure_model()`). **Status: still OPEN — not resolved
  by preload removal alone (would only narrow the window, not close it,
  per CLAUDE.md rule 6 this is stated explicitly rather than let a
  partial fix be read as a full one) — scoped and ready for
  implementer**, mandatory `code-reviewer` pass per CLAUDE.md rule 4
  (real daemon-startup/watchdog process-lifecycle behavior change).
- **Not fixed here.** Flagged for live-verifier (this sub-task's own
  scoping requires a live-verifier pass) — expect a live session under
  `codey-start` to show the coder loaded at 16384, not 32768, and do not
  read that as a regression of THIS round's own wiring; it is this
  documented race, not a bug in the interactive/background branch logic
  itself (that logic's unit tests, `tests/test_74b_planner_and_coder_n_ctx.py`,
  confirm the branch computes the correct value in isolation).

### [NEW-146] `core/daemon.py`'s embed-server watchdog (and its own startup call) could still hit `NEW-144`'s kill-and-replace path against a healthy embed server orphaned by a PREVIOUS daemon incarnation that crashed without a graceful shutdown

- **Status: Suspected** — not reproduced live this pass (would require
  deliberately crashing a daemon process without triggering its `finally:`
  shutdown path, which CLAUDE.md rule 2's RAM-discipline posture and this
  task's scope don't call for).
- **Reasoning:** `core/embed_server.py`'s `_embed_server` singleton is
  per-process. A NEW daemon process (e.g. after a crash/`kill -9` that
  bypassed `core/daemon.py`'s graceful-shutdown `finally:` block, which is
  the only thing that calls `stop_embed_server()`) starts with a fresh
  `EmbedServer()` object — `self.process is None`, `self._started =
  False`. If a healthy embed server from the PRIOR daemon incarnation is
  still alive and bound to the port, both the new daemon's own startup
  call (`_main_loop`, `start_embed_server()`) and its 30s watchdog
  (`is_running()` returning `False` because the new singleton has no
  memory of the old process, then `start_embed_server()`) would call
  `EmbedServer.start()` directly — which is `NEW-144`'s exact kill-and-
  replace path, this time triggered by the daemon's OWN calls, not
  `core/inference.py`'s.
- **Why this is different from what 7.4b sub-task A fixed:** sub-task A's
  fix (this round) only added a health-check-only guard to
  `core/inference.py:_start_server()` — the daemon's own calls are, by
  this item's own design, meant to be the one true "owner" that starts/
  stops the embed server unconditionally (see `core/daemon.py`'s
  `_main_loop`/`finally:` block, already the correct mechanism for a
  SINGLE daemon incarnation's own lifecycle). This finding is narrower:
  it's specifically about a daemon RESTART inheriting a still-alive
  orphan from a crashed prior incarnation, a case this round's own
  sub-task A scoping did not name and this round did not fix.
- **Not fixed here** — narrow edge case (requires an ungraceful daemon
  crash specifically), out of TODO.md 7.4b sub-task A's stated scope
  (that scope is `core/inference.py:_start_server()` specifically). Not a
  standalone fix task yet; log only.

### [NEW-147] `core/observability.py`'s `context_size` property and `core/memory_v2.py`/`core/summarizer.py`/`core/tokens.py`'s context-budgeting reads all still read the unconditional `MODEL_CONFIG["n_ctx"]` (32768), not adjusted for TODO.md 7.4b sub-task C's new interactive-vs-background coder ceiling

- **Status: Suspected** — read directly (`core/observability.py:122`,
  `core/memory_v2.py:38`, `core/summarizer.py:168,189`,
  `core/tokens.py:48`), not exercised live against an actual
  background-dispatched 16384-context server.
- **`context_size` (`core/observability.py:122`):** a pure status-display
  property (`MODEL_CONFIG.get("n_ctx", 4096)`) — cosmetic staleness only,
  `codeyOS --status` would report the interactive ceiling (32768) even
  during a daemon-dispatched background task actually running at 16384.
  Low-severity.
- **The other three are a real functional concern, not just cosmetic:**
  `core/memory_v2.py`'s `CTX_TOTAL`, `core/summarizer.py`'s compression-
  trigger/target budgets, and `core/tokens.py`'s `max_ctx` all use
  `MODEL_CONFIG["n_ctx"]` as the assumed token budget for prompt
  construction / context-compression decisions for the coder role,
  regardless of which n_ctx the actually-spawned server was given. A
  daemon-dispatched background task now genuinely CAN run against a
  16384-context server (sub-task C), but these three modules would still
  budget prompt construction against 32768 — risking an actual
  server-side truncation/overflow for a background task whose prompt (or
  accumulated conversation/memory context) is built assuming 16384 more
  tokens of room than the spawned server actually has.
- **`core/memory_v2.py`'s `CTX_TOTAL` specifically is harder to fix than a
  simple call-site swap:** it's `CTX_TOTAL = MODEL_CONFIG["n_ctx"]`, a
  MODULE-LEVEL constant evaluated once at import time — the same shape
  `NEW-102` already found broken for `main.py`'s `--ctx` flag (import
  order means it's bound before any later override could reach it). A
  per-load interactive/background signal can't reach a module-level
  constant at all without restructuring it into something re-read per
  call (a property/function, not a plain constant) — a future fix here
  should account for that structural gap, not assume it's a one-line
  `MODEL_CONFIG["n_ctx"]` → `some_dynamic_n_ctx()` substitution. See
  `NEW-102` for the closely-related existing finding on this same
  constant.
- **Why not fixed here:** TODO.md 7.4b sub-task C's own write-up scopes
  the wiring to `core/loader_v2.py:load_primary()` and its `main.py`/
  `core/daemon.py` call sites only — it does not mention memory/
  summarizer/token-budget consumers, and threading the same interactive/
  background signal through all of them (so a background-dispatched
  task's OWN prompt construction budgets against 16384, not 32768) is a
  materially larger change than this sub-task's literal scope, needing
  its own design pass (which of these call sites can even observe
  "am I running in a background-dispatched task right now" cheaply,
  vs. re-deriving the coder's actual `n_ctx` some other way).
- **Not fixed here** — flagged as a real functional gap, not fixed as
  part of this round.

### [NEW-148] `main.py`'s one-shot automation flags (`--init`, `--tdd`, `--fix`) call `load_primary()` before `_write_tui_pid_file()` runs (that only happens on the `repl()`/interactive-chat path) — so TODO.md 7.4b sub-task C's interactive-vs-background branch treats these foreground, human-invoked, single-shot CLI runs as "background," giving them the smaller 16384 ceiling instead of full context

- **Status: Suspected** — read directly, `main.py:1787-1861` (the
  `--init`/`--tdd`/`--fix` branches, each calling
  `_load_primary_with_gate_recovery(loader)` well before line 1923's
  `_write_tui_pid_file()`, which only runs on the shared tail path into
  `repl()`). Not exercised live this pass.
- **Concretely:** these three flags are synchronous, foreground,
  human-invoked CLI runs — not daemon background dispatch, the case
  `CODER_BACKGROUND_N_CTX` was scoped for — but because
  `core.resource_gate.is_interactive_session_active()` is driven purely
  by the TUI-session-pid-file mechanism (`utils.config.TUI_SESSIONS_DIR`),
  and that file is only written on the `repl()` path, these three flags'
  own `load_primary()` calls will see no active TUI session and fall
  into the smaller 16384-token background ceiling — even though they are
  exactly the kind of interactive, user-driven usage Ish's decision 3
  meant to give full context.
- **Why not fixed here:** TODO.md 7.4b sub-task C explicitly directs
  reusing `is_interactive_session_active()` exactly as-is ("do not build
  a second detection mechanism") — implemented literally per that
  instruction. Moving `_write_tui_pid_file()` earlier in `main()` (before
  these three branches) would be a real behavior change beyond this
  sub-task's scope, and could have its own side effects (e.g. making the
  daemon defer background dispatch for the full duration of a `--fix`
  run, which is arguably correct but is a separate decision this task
  was not asked to make).
- **Not fixed here** — logged for scoping into a future round.

### [NEW-149] Even after NEW-145's lazy-load fix (both call sites gated), `core/loader_v2.py:LlamaServer.start()`'s port-in-use reuse branch (`:211-230`) means whichever caller spawns the coder server FIRST wins the context size for that server's entire life — a background daemon-dispatched task that loads first at 16384 leaves a later-attaching interactive TUI stuck at 16384 too, with no respawn

- **Status: Confirmed** — read directly, `core/loader_v2.py:211-230`:
  `LlamaServer.start()` checks `_is_port_in_use()` before spawning, and
  if something is already answering on the port, logs "already running
  on port, using existing server," leaves `self.process` at `None`, and
  returns without ever re-evaluating or respawning at the caller's own
  `n_ctx`. This is the exact mechanism NEW-145 itself already identified
  for the daemon-preload-vs-TUI case; it is not specific to the preload
  path and is not closed by removing the preload — it's inherent to the
  reuse branch itself, and applies symmetrically to a background
  daemon-dispatched task or the watchdog's own restart landing first,
  followed by an interactive TUI attaching second.
- **Not this round's fix:** Ish's 2026-08-11 decision only covers
  removing the eager preload (NEW-145's fix, see above and TODO.md 7.4b
  sub-task C); it does not direct a fix for "whoever spawns first also
  fixes the context ceiling for the server's whole life," which is a
  separate, real design decision (e.g. forcing a respawn when a later
  caller needs a larger ceiling than the resident server has) that
  risks its own self-race class if built without a dedicated review
  pass — logged here, not silently fixed or dropped, per CLAUDE.md
  rule 8.

## Found during the NEW-102/bug_002 config-live-read fix round, 2026-08-13 — NOT fixed, logged only

### [NEW-150] `tests/test_new19_patch_failed_repeat_escalation.py`'s three `_in_subtask=False` tests run real (unmocked) `git status`/`ask_confirm()` calls against the actual working tree and fail with `OSError: reading from stdin` whenever the file they touch (`main.py`) already has a real, unrelated, pre-existing uncommitted diff at test-run time

- **Status: Confirmed** — traced directly. `core/agent.py:671`'s
  `check_git_and_offer_commit()` (called from the real, unmocked
  `run_agent()` path these three tests exercise, since they pass
  `_in_subtask=False`) calls `git_status_paths(files_touched)` scoped to
  `["main.py"]` (`core/agent.py:688`). If that returns anything other
  than `"Nothing to commit."`, it prints the status and calls
  `ask_confirm()` (`core/agent.py:694`), which tries to read a real
  interactive `y/n` answer from stdin — `pytest -q`'s captured stdin has
  none, producing `OSError: pytest: reading from stdin while output is
  captured!`. Reproduced directly: with `main.py` clean (matching `HEAD`,
  the tests' implicit assumption), all 5 tests in the file pass; the
  moment `main.py` has ANY real uncommitted diff (verified using this
  round's own unrelated `--ctx` guard fix as the diff), the 3 tests using
  `_in_subtask=False` fail with this exact `OSError`, while the 2 tests
  using `_in_subtask=True` (which never reaches
  `check_git_and_offer_commit()`'s real git-status branch, per
  `core/agent.py`'s own escalation gating) keep passing.
- **Not fixed here** — out of this round's scope (this round touches
  `utils/config.py`/`core/loader_v2.py`/`core/planner_loader.py`/
  `core/memory_v2.py`/`main.py`'s `--ctx` handling, not `core/agent.py`'s
  git-commit-offer flow or this test file). Confirmed NOT caused by this
  round's actual code change (the `--ctx` guard's logic has no
  relationship to `check_git_and_offer_commit()`) — it's a pre-existing
  test-isolation gap that any future round touching `main.py` mid-session
  (uncommitted) will trip again, deterministically, not flakily. Fix
  direction: mock `core.githelper.git_status_paths`/`utils.logger.confirm`
  (or the whole `check_git_and_offer_commit` call) in this test file,
  matching how `tests/test_new19_patch_failed_repeat_escalation.py`'s own
  `_in_subtask=True` tests already avoid the real git path, rather than
  relying on the ambient working tree happening to be clean for `main.py`
  at test-run time.

### [NEW-151] Process violation, self-found: commit `5687dcf` (this same round) swept in TWO already-implemented, rule-4-category process-lifecycle changes (`core/daemon.py`'s NEW-145 lazy-coder-load/watchdog-gate fix, `core/embed_server.py`/`core/inference.py`'s NEW-144 embed cross-process health-check fix) without the `code-reviewer` approval — or, for the daemon change, the `live-verifier` pass — that TODO.md's own 7.4b sub-tasks A/C explicitly mark mandatory before landing

- **Status: Confirmed**, self-caught on review (advisor-prompted) before
  reporting the round done, not found by a later audit. This was scoped
  as a config-only task (`utils/config.py`'s n_ctx constants, `main.py`'s
  `--ctx` guard) but the commit that carried the fix (`5687dcf`) was
  built by staging every file in the working tree at once, including six
  files this round never read, reviewed, or was asked to touch:
  `core/daemon.py` (116-line diff — TODO.md 7.4b sub-task C's NEW-145
  fix: deletes `_preload_primary_model()`, adds a `was_ever_loaded()`
  gate to `_watchdog_check_model()`), `core/embed_server.py` (adds
  `EmbedServer.is_healthy()`) and `core/inference.py` (30-line diff —
  TODO.md 7.4b sub-task A's NEW-144 fix: `_start_server()` now
  health-checks the embed server before calling `start()`, instead of
  calling `start_embed_server()` unconditionally), plus their matching
  test files (`tests/test_daemon_model_watchdog.py`,
  `tests/test_loader_resource_gate.py`).
- **Why this matters, concretely:** `TODO.md`'s own 7.4b sub-task A
  (line ~2231) and sub-task C (line ~2483) both state, in the same
  document this round read and edited, "**Mandatory `code-reviewer`
  pass**" (rule 4 — real daemon-startup/watchdog and embed
  start/kill-logic changes) — sub-task C additionally requires a
  **mandatory `live-verifier` pass** (its own text: "unit tests cannot
  show this fix worked, NEW-145 was only ever found under the real entry
  point"). Neither happened before `5687dcf`. This is exactly the
  category CLAUDE.md rule 4 exists for, and exactly the mistake rule 8
  exists to make sure doesn't get silently absorbed into "the round is
  done."
- **What is and isn't actually at risk:** the full test suite is clean
  post-commit (673 passed, 1 skipped, 0 failed, verified after this
  round's own changes), so nothing is *known* broken. But "unit tests
  pass" is explicitly not the bar CLAUDE.md rule 4/7 sets for this
  category — a code-reviewer pass exists to catch exactly the kind of
  self-race this project has been bitten by before (see CLAUDE.md's own
  cited example: "a daemon reading its own preemptively-written PID as
  evidence a duplicate was running"), which a passing unit-test suite
  would not surface. This code is now live in `main` and will be
  exercised by the next real `codey-start` session with no gate having
  caught it first.
- **Not fixed here** — logged instead of reverted, per CLAUDE.md rule 6
  ("correct the record," not silently rewrite history) and because a
  `git revert`/force-push against already-pushed history is itself a
  destructive operation this project's rules caution against taking
  unprompted. Fix direction: a genuine `code-reviewer` pass on
  `core/daemon.py`'s `_watchdog_check_model()`/`was_ever_loaded()` change
  and `core/embed_server.py`/`core/inference.py`'s health-check-only
  change, followed by the live-verification `TODO.md`'s sub-task C
  already specifies verbatim (fresh `codey-start`, confirm no
  `llama-server` on port 8080 until first real request, confirm the
  resulting server's actual `-c` flag, confirm the watchdog does not
  spawn one during a ≥30s idle window) — treat both sub-tasks A and C as
  still open pending exactly that, not as done because the code merely
  exists in `main` now. See `TODO.md`'s 7.4b sub-tasks A/C for the
  matching status note.

## Found during the retroactive `code-reviewer` pass on NEW-151's daemon change, 2026-08-13

### [NEW-152] `core/loader_v2.py`'s `ModelLoader._ever_loaded` (the NEW-145 watchdog gate) was set True on BOTH a genuine coder spawn AND the port-in-use adoption branch, never reset — sticky-True after the daemon's first adoption meant the watchdog gate stopped protecting against eager background-ceiling respawns on the normal `codey-start` steady state

- **Status: Confirmed** — found by a retroactive `code-reviewer` pass
  (prompted by `NEW-151`, the process violation of landing this change
  without review), fixed the same round. **The fix itself has NOT yet
  had its own mandatory rule-4 `code-reviewer` pass — the `code-reviewer`
  subagent was not invocable in the session that built this fix (no
  Task/subagent-launch tool available); the diff was instead reviewed by
  project-architect directly against `.claude/agents/code-reviewer.md`'s
  own checklist. That is not a substitute for the real pass.** Do not
  read "found by code-reviewer" as "the fix is code-reviewer-approved."
  Reproduction traced directly against `core/loader_v2.py`'s pre-fix
  `load_primary()` (~line 788-790) and `core/daemon.py`'s pre-fix
  `_watchdog_check_model()` (~line 777): (1) TUI spawns the coder
  interactively (e.g. 32768 ctx); (2) daemon later dispatches a
  background task → `load_primary()` hits the port-in-use adoption
  branch (`self._server.process is None`) → the old combined
  `_ever_loaded` flag goes True; (3) TUI session ends, coder process
  exits, port frees; (4) next watchdog tick: `was_running` correctly
  reads False, but the old `was_ever_loaded()` was still True (sticky,
  never reset by `unload()`) — the NEW-145 gate did NOT fire; (5) falls
  through to `ensure_model()`, `is_interactive_session_active()` now
  False (TUI gone) → coder respawns at the 16384 background ceiling
  instead of doing nothing; (6) TUI reattaches, reuses the
  already-running 16384 server via `LlamaServer.start()`'s reuse
  branch — reproducing NEW-145's original symptom through adoption
  instead of the deleted eager preload. Step (2)-(4) is the *normal*
  `codey-start` steady state (TUI-spawns/daemon-adopts), not an edge
  case, so this gap was reachable on essentially every real session,
  not a rare race.
- **Fix, `core/loader_v2.py`/`core/daemon.py`:** replaced the single
  `_ever_loaded`/`was_ever_loaded()` (spawned-OR-adopted) with
  `_ever_spawned`/`was_ever_spawned()` (genuine-spawn-only — adoption no
  longer sets it). The watchdog gate (`core/daemon.py:777`) now reads
  `if not was_running and not loader.was_ever_spawned(): return`.
  Crash-restart coverage for coder loads the daemon's own loader
  genuinely spawned (background-dispatched loads) is unconditional and
  unchanged. **Deliberate, documented reduction:** a TUI-spawned coder
  the daemon's loader has only ever ADOPTED is no longer restarted by
  the watchdog if it crashes while the TUI is still attached — the
  daemon doesn't own that process's lifecycle (same argument
  `load_primary()`'s reuse branch already makes about residency
  accounting) and the TUI's own next `infer()` call reloads it; this is
  the direct fix for the false-positive respawn above, not a separate
  regression. Full case-by-case breakdown lives on
  `was_ever_spawned()`'s own docstring in `core/loader_v2.py`. Residual,
  NOT fixed by this change (adjacent to `NEW-149`, not expanded here):
  once the daemon HAS genuinely spawned a background coder at least
  once, `_ever_spawned` stays sticky-True — a later tick can still
  respawn it at 16384 after it stops, and a later-attaching TUI reuses
  that server; only the pure-adoption case is fixed.
- **Verified:** `python -m pytest tests/test_daemon_model_watchdog.py
  tests/test_loader_resource_gate.py -q` → 37 passed; full suite
  `python -m pytest -q` → 742 passed, 1 skipped, 0 failed. Reviewed by
  project-architect against `.claude/agents/code-reviewer.md`'s
  checklist (kill-by-PID not pattern, no self-referential guard, no
  silently-swallowed exceptions, `loaded_ok`/`finally` teardown still
  intact, no GUI/network surface touched) as a stopgap only — **the
  mandatory rule-4 `code-reviewer` subagent pass has NOT run** (not
  invocable in this session, no Task/subagent-launch tool available) and
  is still outstanding, same as **live-verification**, which is also
  still outstanding (see `TODO.md`'s 7.4b sub-task C, which already
  specifies the exact pass/fail evidence to capture, now extended to
  also cover the adoption/exit/respawn sequence above). This is
  code-complete/test-verified only. Do not treat `NEW-145`/sub-task C as
  closed, and do not treat this fix as "code-reviewer approved," until
  both the real `code-reviewer` pass and that live pass run.

### [NEW-153] `core/embed_server.py`'s `start()` has a TOCTOU: a concurrent `is_healthy()` False result during the daemon's own up-to-30s post-spawn health-wait can cause a caller to kill-and-restart the daemon's own still-initializing embed server via `_kill_port_occupant()`

- **Status: Confirmed** (logged only, not fixed — outside this round's
  scope). Found during the same retroactive `code-reviewer` pass as
  `NEW-152`. `EmbedServer.start()`'s "already running" fast path only
  checks `self.process` (this Python object's own spawned handle); a
  different process's `is_healthy()` check racing against the daemon's
  own in-flight startup health-wait (up to 30s) can read a not-yet-ready
  health endpoint as unhealthy and fall through to
  `_kill_port_occupant()`, killing and respawning the daemon's own
  legitimately-starting embed server. Self-recovering (embed is
  optional — BM25 fallback exists — and the kill is by tracked PID, so
  CLAUDE.md rule 3 is satisfied), but more reachable now than before
  `NEW-145`'s fix: removing the daemon's eager coder preload means
  embed's first real cross-process health check now happens earlier
  relative to daemon startup, shrinking the window less busy with other
  startup work and making the race more likely to actually land during
  it.

### [NEW-154] `core/daemon.py`'s own embed watchdog (~line 996) checks `get_embed_server().is_running()` while `core/inference.py`'s NEW-144 fix uses `is_healthy()` — two different liveness primitives answering the same underlying "is embed up" question

- **Status: Suggestion** (logged only, not fixed — outside this round's
  scope). Found during the same retroactive `code-reviewer` pass as
  `NEW-152`. Not a known bug today — `is_running()` (process-alive) and
  `is_healthy()` (process-alive AND answering `/health`) will usually
  agree — but worth a one-line note for whoever next touches embed
  lifecycle: pick one primitive as the canonical "is embed up" check for
  both the watchdog and inference's pre-flight, or document why they
  intentionally differ (e.g. the watchdog caring about "is the process
  alive at all" vs. inference caring about "is it ready to actually
  answer a request").

### [NEW-155] `NEW-152`'s fix narrows the watchdog gate to genuine-spawn-only, but `_ever_spawned` is still sticky-True forever once set — a background coder the daemon genuinely spawned once can still be respawned at the 16384 background ceiling on a later tick and leave a later-attaching interactive TUI stuck at it, same mechanism as `NEW-149`

- **Status: Confirmed**, self-documented in `was_ever_spawned()`'s own
  docstring (`core/loader_v2.py`) at fix time, cross-referenced here per
  CLAUDE.md rule 8 rather than left only as a sub-clause of the `NEW-152`
  fix note. `NEW-152`'s fix closes the pure-adoption case (a coder this
  loader has only ever adopted, never spawned, no longer triggers an
  eager respawn) but does not touch the case where this loader HAS
  genuinely spawned a coder at least once: `_ever_spawned` stays True for
  the rest of the process's lifetime (by design — that stickiness is the
  crash-restart mechanism for genuine spawns), so a later watchdog tick
  can still call `ensure_model()` and respawn that coder at the smaller
  16384 background ceiling after it stops, and a later-attaching
  interactive TUI would reuse that under-provisioned server via
  `LlamaServer.start()`'s reuse branch (`core/loader_v2.py:211-230`) —
  the exact "first spawner wins the context size" mechanism `NEW-149`
  already names. Not fixed here; `NEW-149`'s own resolution (if one is
  ever scoped) should account for this reachable path through it too.

### [NEW-162] `NEW-158`'s "the flag is not passed, so it's off" framing may not hold on the installed build — this binary's own `--help` text states `--jinja` defaults to enabled, and `--reasoning-format` defaults to `auto`, not `none`

- **Status: Suspected.** Found 2026-08-23 while scoping M1-B/C/D, by
  running `~/llama.cpp/build/bin/llama-server --help` on the exact binary
  `NEW-158` examined (`version: 1 (91d2fc3)`, matching §5.1's commit
  `91d2fc38`). The literal help text reads: `--jinja, --no-jinja ...
  (default: enabled)` and `--reasoning-format FORMAT ... (default: auto)`,
  and a separate `-rea, --reasoning [on|off|auto]` flag also defaults to
  `auto`.
- **Why this doesn't simply overturn `NEW-158`:** `--help` output is the
  parser's stated default, not a proof of runtime behavior with this
  specific model and command line — rule 12 cuts both ways here. It is
  equally possible that `(default: enabled)` is accurate and `_spawn_locked()`'s
  omission of `--jinja` has always been a no-op (in which case `NEW-158`'s
  claim that thinking mode is "inert" without the flag needs downgrading
  per rule 6), or that some other part of the spawn command, an older
  llama.cpp default baked into this build's actual code path, or the
  model's own template negotiation overrides the help text's stated
  default. **Neither has been checked against a live spawn** — `NEW-158`
  was itself desk-only (GGUF header read, no load), and so is this entry.
- **Impact on M1-C:** the task cannot start from "add `--jinja` because
  it's currently off" as a settled premise. It must first capture the
  actual request/response behavior of a live spawn (with the real
  `--reasoning-format` value made explicit — `deepseek` for split
  `reasoning_content`, not the `auto`/`none`/`deepseek-legacy` alternatives
  also listed in `--help` — since `auto`'s behavior against this specific
  hybrid model's template is itself unverified) before concluding whether
  `--jinja`/`--reasoning-format` are additions or no-ops. Either outcome is
  fine; guessing which one is true and skipping the check is not.
- **Fix direction:** M1-C's live-verification step (deferred to M1-E per
  this round's scoping) settles this with a real spawn and a captured
  request/response pair, ideally one with `--jinja` explicit and one
  without, on the same model. Until then this stays Suspected on both
  sides.
- **Not fixed this round** — logged during M1-B/C/D scoping, resolution
  belongs to M1-C's live-verification step (folds into M1-E under this
  round's plan).
- **Status: CLOSED, 2026-08-23, with a caveat — resolved as far as this
  round can, M1-E.** A true A/B (flags present vs. absent) was not
  feasible without a code change, since `--jinja`/`--reasoning-format` are
  hardcoded in `_spawn_locked()`, not env-toggleable — the strict
  "off vs. on" comparison from this finding's original framing was never
  run. What *was* run is response-shape evidence with the flags present:
  `reasoning_content` genuinely appears separate from `content` when
  `enable_thinking: true` is set (same evidence that closes `NEW-158`).
  That is enough to say the flags demonstrably do something — they are
  not no-ops — which is the question this finding actually turned on.
  Closing on that basis rather than leaving it open for an A/B this round
  has no way to run.

### [NEW-163] `core/lora_import.py`'s `rollback_to_backup()` copies the saved backup weights onto whatever `cfg.MODEL_PATH` currently names — after a swap, that name is the fine-tuned file's path, so a rollback writes base weights into the fine-tuned file's name rather than restoring the original base file
- **Found by:** the implementer fixing `NEW-161`'s sibling asymmetry bug
  (M1-B/C/D round, this session, fixing `swap_to_finetuned_model()`'s
  "primary" branch to keep `cfg.MODEL_PATH`/`cfg.PLANNER_MODEL_PATH` in
  sync with the "secondary" branch, per code-reviewer's required-fix
  finding on the M1-D diff). Not introduced by that fix — pre-existing —
  but newly exposed once "primary" swaps and rollbacks became symmetric
  with "secondary," which is what made the pattern visible enough to
  name precisely.
- **Mechanism:** `rollback_to_backup()` restores a backup by copying it
  over the path `cfg.MODEL_PATH` (or `cfg.PLANNER_MODEL_PATH`) *currently*
  holds. After `swap_to_finetuned_model()` succeeds, that path has already
  been mutated to point at the fine-tuned file under
  `~/models/codey-finetuned/`. A subsequent rollback therefore overwrites
  the fine-tuned file's on-disk name with the original base weights,
  rather than restoring `cfg.MODEL_PATH`/`cfg.PLANNER_MODEL_PATH` back to
  the original base file's own path. The config pointer ends up correct
  (it's reset to the pre-swap value elsewhere in the rollback path), but
  the file left on disk under the fine-tuned name is now silently the
  base model, not the fine-tune it was named for.
- **Impact:** a failed swap that triggers rollback leaves a file on disk
  whose name and contents disagree — anyone inspecting
  `~/models/codey-finetuned/` after a rollback, or a future swap that
  reuses that path expecting the fine-tuned weights, gets the base model
  instead. Rated Suspected pending a live rollback reproduction — the
  code read is direct, but the actual on-disk end-state after a real
  failure-triggered rollback has not been executed and observed this
  round.
- **Not fixed this round** — out of scope for the M1-D lora_import.py
  fix, which only addressed the `MODEL_PATH`/`PLANNER_MODEL_PATH` config
  sync asymmetry, not this separate on-disk file-identity issue. Needs
  its own scoped task.

### [NEW-164] `core/plannd.py`'s `get_plan()` (local backend, thinking-mode path): `PLANNER_MAX_TOKENS=1024` is confirmed too small for real thinking-mode reasoning on this device — the trace alone consumes the whole budget, `message.content` comes back empty, and planning silently degrades to unplanned execution with no visible error
- **Status: Confirmed** — live-reproduced during M1-E (2026-08-23), not
  a theoretical risk. `core/plannd.py` line ~427's comment area is where
  the request is built with `chat_template_kwargs: {"enable_thinking":
  true}` and `max_tokens=PLANNER_MAX_TOKENS`.
- **Reproduction, verbatim from the live session:** the real
  `PLANNER_PROMPT` (9,786 chars, 2,425 prompt tokens) sent with
  `enable_thinking: true` and `max_tokens=1024` returned:
  ```json
  "finish_reason": "length",
  "message": {
      "content": "",
      "reasoning_content": "The user wants me to: ... [4632 chars, never
        reaches an answer]"
  },
  "usage": {"completion_tokens": 1024, "prompt_tokens": 2425}
  ```
  Server log confirms `n_decoded = 1024` at release — generation stopped
  only because it hit `max_tokens`, never a natural stop token. This is
  not a parsing bug: `parse_steps("")` correctly returns `[]`, and
  `get_plan()` correctly returns `None` on an empty answer. The defect is
  upstream — the budget itself is wrong for this model's real reasoning
  verbosity on this device's real prompts.
- **Mechanism:** `--reasoning-format deepseek` (M1-C) correctly splits
  `<think>` content into `reasoning_content`, separate from `content` —
  confirmed working exactly as designed (this resolves `NEW-158`/
  `NEW-162`'s mechanical question). But `max_tokens` caps *total*
  generated tokens, reasoning included. A 1024-token ceiling, sized
  originally for the retired 1.5B model with no thinking mode at all, is
  the wrong number for a model that now spends a variable, sometimes
  large, fraction of its budget on a reasoning trace before ever writing
  an answer.
- **Impact:** every planning request is now at risk of silently
  returning no plan, with the daemon falling through to whatever
  unplanned-execution path exists — not a crash, not a loud failure,
  exactly the failure shape rule 5/rule 12 exist to prevent from going
  unnoticed. Reproduced on a real device, not inferred.
- **Compounding, separately confirmed bug — `NEW-165` below.**
- **Status: CLOSED, 2026-08-23, landed as `4cbf9a8`.** `PLANNER_MAX_TOKENS`
  raised 1024→2048 (later recalibration context: `NEW-167`), and a
  `utils.logger.warning()` now fires with diagnostic detail (prompt
  token estimate, `max_tokens` used, `reasoning_content` length)
  whenever a thinking-mode response comes back empty after
  `finish_reason == "length"` — replacing the old fully-silent
  `return None`. Live-verified same session: two different real
  thinking-mode planning prompts on this device both returned non-empty,
  usable plans (`finish_reason: "stop"`, 167 and 203 of the 2048-token
  budget used). Not proven for a prompt that drives the reasoning trace
  to the full budget — that scenario was never exercised, stated
  honestly rather than assumed covered.

### [NEW-165] `core/plannd.py`'s `get_plan()` (local backend) uses a hardcoded `urllib.request.urlopen(req, timeout=60)` — shorter than this device's real prompt-processing time for the planner's actual prompt size, so a request can be cancelled server-side before generation even starts, independent of and prior to `NEW-164`'s token-budget issue
- **Status: Confirmed** — live-reproduced during M1-E (2026-08-23).
- **Reproduction:** loading the model via the production
  `core.loader_v2.get_loader().ensure_model()` path and calling the real
  `core.plannd.get_plan()` returned `None`. Server log showed why:
  prompt processing on the real `PLANNER_PROMPT` (~2,425 tokens) at this
  device's measured ~23-26 tokens/second prefill rate takes over 60
  seconds by itself, before a single output token is generated:
  ```
  0.48.430.067 I slot print_timing: id 3 | task 0 | prompt processing,
    n_tokens = 1024, progress = 0.42, t = 41.24 s / 24.83 tokens/s
  1.07.212.746 W srv  stop: cancel task, id_task = 0
  1.11.913.807 I slot release: id 3 | task 0 | stop processing:
    n_tokens = 1536, truncated = 0
  ```
  `get_plan()`'s `except Exception` catches the resulting timeout
  exception and returns `None` — the exact same silent-failure shape as
  `NEW-164`, via a different mechanism (HTTP client timeout, not an
  empty-content answer), and one that fires *first* in the request
  lifecycle, before `NEW-164`'s scenario would even get a chance to
  manifest on a slower path.
- **Impact:** on this device, in the state measured, a planning request
  can fail this way even before addressing `NEW-164` — fixing the
  token budget alone is not sufficient if the timeout still cuts the
  request off mid-prefill. Both need fixing together, or the timeout
  fix should land first since it gates whether `NEW-164`'s scenario is
  even reachable.
- **Status: CLOSED, 2026-08-23, landed as `4cbf9a8`.** The flat `timeout=60`
  replaced with `compute_planner_timeout()`, a formula derived from
  measured device rates rather than a constant that goes stale the next
  time the token budget changes; `core/daemon.py`'s two outer
  `asyncio.wait_for` timeouts now derive from the same formula plus a
  buffer, so raising the inner timeout doesn't just relocate the
  cancellation one layer up. Post-fix live re-verification then found
  the formula's own rate constants were not actually conservative
  floors (`NEW-167`, also closed same session), and a second review pass
  found a further, previously-unnoticed client-side socket timeout in
  `core/planner_service.py` that was shorter than everything above it
  (`NEW-169`, also closed same session) — see those entries for the full
  three-layer discovery. No premature cancellation was observed in
  either of the real prompts tested live.

### [NEW-166] `PLANNER_MAX_TOKENS` is shared between `core/plannd.py`'s local-backend `get_plan()` and its untouched `_get_plan_remote()` (OpenRouter/UnlimitedClaude) — raising it for NEW-164 silently doubles the remote backend's generation budget too, with no corresponding change to that path's own `timeout=60`
- **Status:** Confirmed — found by the implementer fixing `NEW-164`
  (raising `PLANNER_MAX_TOKENS` 1024→2048), flagged rather than silently
  worked around, since the fix's file scope explicitly excluded
  `_get_plan_remote()`.
- **Mechanism:** both functions read the same module-level
  `utils.config.PLANNER_MAX_TOKENS` constant. `NEW-164`'s fix reasoned
  about the new value (2048) purely in terms of the local backend's
  measured token rates and `core/daemon.py`'s outer timeout budget —
  `_get_plan_remote()`'s own hardcoded `timeout=60` (line ~312) was
  deliberately left alone as a different backend/latency profile, but
  its `max_tokens` payload value rose anyway as a side effect of sharing
  the constant.
- **Impact:** a remote-backend planning call can now request twice the
  generation length in the same 60-second window that was calibrated
  (implicitly, never explicitly derived) for the old 1024-token budget.
  Whether this is actually a problem depends on the remote provider's
  real token-per-second rate, which has not been measured or checked —
  rated Confirmed on the mechanism (the shared constant, verified by
  direct code read), Suspected on the practical impact (unverified
  whether it actually causes remote-path timeouts or budget overruns).
- **Not fixed this round** — out of scope for the NEW-164 fix, which was
  fenced to the local-backend path only. Needs its own scoped decision:
  either split `PLANNER_MAX_TOKENS` into local/remote-specific constants,
  or confirm the remote provider's real rate makes 2048 safe within its
  existing 60s timeout and document that explicitly rather than leaving
  it coincidental.

### [NEW-167] `NEW-165`'s fix used `PLANNER_MIN_PREFILL_TPS=20`/`PLANNER_MIN_GEN_TPS=4` as "conservative floors below M1-E's measured range," but live re-verification measured real rates roughly half of both — the timeout formula would under-budget a harder prompt whose reasoning trace approaches the full token budget
- **Status: Confirmed, live-reproduced.** Found during the required
  post-fix live-verification pass for `NEW-164`/`NEW-165` (2026-08-23),
  same session that also confirmed `NEW-164` resolved.
- **Evidence, server log ground truth (`~/.codeyOS/llama-server.log`):**
  cold-cache prompt processing measured `94.04 ms/token = 10.63
  tokens/second` (task 0, the only cold-prefill measurement — later
  calls in the same load cycle benefited from a cache hit and don't
  measure prefill). Thinking-mode generation measured `2.15-2.74
  tokens/second` across three separate completions (465.47ms/tok,
  2.74 tok/s cache-hit call; 2.71 tok/s second cache-hit call). Both are
  roughly **half** of the constants' assumed floors (`PLANNER_MIN_PREFILL_TPS
  =20`, `PLANNER_MIN_GEN_TPS=4`) and of M1-E's own originally-cited range
  (23-26 tok/s prefill, 4.87 tok/s generation) — M1-E's numbers describe
  this device under different conditions (likely a different concurrent
  load, or non-thinking generation, which independently measured faster
  at 5.7-7.0 t/s in that same round) and should not be treated as this
  device's floor for a cold-cache, thinking-mode call.
- **Impact:** `compute_planner_timeout()`'s formula (`prompt_tokens/20 +
  max_tokens/4 + 30`) computed `665.0s` for a 2,460-estimated-token
  prompt at `PLANNER_MAX_TOKENS=2048`. At the *actually measured* rates,
  a request that consumed its full 2048-token budget (the exact scenario
  `NEW-164` exists to describe) would cost roughly `2424/10.63 +
  2048/2.15 ≈ 228s + 953s ≈ 1181s` — nearly double the computed timeout.
  Neither test prompt run in this round actually drove generation that
  far (both stopped naturally at 167/2048 and 203/2048 tokens), so the
  under-budget timeout was not directly exercised, but the arithmetic
  shows `NEW-165`'s premature-cancellation failure mode would recur on a
  harder prompt at the new numbers, not just the old ones.
- **Fix, applied same session:** `PLANNER_MIN_PREFILL_TPS` lowered
  20→10 and `PLANNER_MIN_GEN_TPS` lowered 4→2, matching the real
  measured floor rather than an assumed one, with the live-verification
  numbers recorded in the constants' own comment as provenance (rule 12
  — cite the artifact that was actually measured, not a family-resemblant
  prior figure from a different call shape).
- **Status: CLOSED, 2026-08-23** — recalibrated in the same round that
  found it, before commit.

### [NEW-168] `core/plannd.py`'s new "plan may be truncated — consider increasing max_tokens" diagnostic (added for `NEW-164`) fires as a false positive whenever the last parsed step ends in an alphabetic character, independent of whether `finish_reason` actually indicates truncation
- **Status: Suspected** — observed as a side-effect during `NEW-164`'s
  live-verification pass (2026-08-23), not the subject of that pass, not
  investigated to a root cause.
- **Evidence:** three live thinking-mode planning calls this round all
  printed `[plannd] plan may be truncated — consider increasing
  max_tokens`, even though all three had `finish_reason: "stop"` (a
  natural stop token, not a length cutoff) and used well under half
  their `max_tokens=2048` budget (167 and 203 completion tokens
  observed). The warning appears to trigger on some heuristic about the
  final character of the last parsed step (e.g., "...error in the loop"
  ends in "p", an alphabetic character) rather than on the actual
  `finish_reason`/`usage.completion_tokens` the response already
  carries.
- **Impact:** this is exactly the diagnostic path `NEW-164`'s fix
  introduced specifically to make real truncation visible — a false
  positive here trains whoever reads the logs to ignore the warning,
  defeating its purpose. Not yet confirmed whether it ever correctly
  identifies a true truncation case, or is unconditionally noisy.
- **Not fixed this round** — found live, outside the scope of the
  `NEW-164`/`NEW-165` fix's own verification pass. Needs its own look at
  wherever this heuristic lives in `core/plannd.py`'s `parse_steps()` or
  its caller, ideally replacing the character-ending heuristic with a
  direct check against the response's own `finish_reason`/
  `usage.completion_tokens` fields, which `get_plan()` already has
  available at the call site.

### [NEW-169] `core/planner_service.py:129`'s `_request_daemon_plan()` uses a hardcoded client-side socket `timeout=185` — untouched by NEW-164/165/167, shorter than every server-side timeout in the chain those fixes built, and the real live caller's own timeout, making the whole formula-based mechanism moot for actual production use
- **Status: Confirmed** — found by code-reviewer while sanity-checking
  the `NEW-167` recalibration's practical effect (2026-08-23), by tracing
  one hop past `send_plan_request_async()`'s two call sites (which the
  earlier `NEW-164`/`NEW-165` review correctly verified) out to
  `send_command()`, the separate client-side socket helper that wraps
  the whole RPC from *outside* the daemon process — a distinct call
  graph the earlier review's grep did not extend to.
- **Mechanism:** `core/planner_service.py`'s `_request_daemon_plan()`
  calls `send_command("command", {...}, timeout=185)`. `send_command()`
  (`core/daemon.py`) opens a Unix domain socket to the daemon and calls
  `sock.settimeout(185)` — a client-side timeout on the entire RPC round
  trip. If the daemon hasn't responded within 185s, the client raises
  `socket.timeout` -> `ConnectionError`, and falls through to "Attempt 2:
  in-process orchestrator" (`planner_service.py` ~line 86), regardless of
  what's happening inside the daemon/plannd/llama-server chain.
- **This is the real, live call path, not a hypothetical:** `main.py`'s
  `_try_daemon_plan()` -> `core.planner_service._request_daemon_plan()`
  -> `send_command(timeout=185)`. `core/daemon.py`'s own docstring names
  this RPC the interactive CLI's planning-oracle call and states it is
  the sole live caller of the `command` socket verb — matching the
  pre-existing `NEW-112` finding, independently confirmed via repo-wide
  grep.
- **Impact:** the three timeouts in the actual chain, nested, are:
  1. `core/plannd.py`'s `urlopen()` to llama-server — formula-based,
     `NEW-165`/`167`, ~1296.5s for a full 2048-token plan at the
     recalibrated constants.
  2. `core/daemon.py`'s `asyncio.wait_for` around the RPC handler —
     `inner_timeout + 30.0`, ~1326.5s.
  3. `core/planner_service.py`'s client-side socket timeout — **still a
     flat 185s, untouched by any of the above.**
  Layer 3 is strictly outermost and shortest. For any real planning call
  needing more than 185s — now virtually guaranteed for a full-budget
  plan, and true even under the *original*, pre-`NEW-167` constants
  (~693s for the same case) — the client gives up long before either
  server-side fix could matter. **The formula-timeout mechanism this
  project has iterated on three times (`NEW-164`, `NEW-165`, `NEW-167`)
  does not prevent premature cancellation for its one real caller.**
- **Not caught earlier because:** the `NEW-164`/`NEW-165` review's
  verification grepped for callers of `send_plan_request_async` (the
  async function inside the daemon process itself) and confirmed exactly
  two call sites, both inside `core/daemon.py` — correct as far as it
  went, but it never extended to `send_command()`, a separate helper
  wrapping the RPC from outside the daemon process entirely.
- **Fix, applied same session:** `_request_daemon_plan()`'s `timeout=185`
  replaced with a value derived from the same `compute_planner_timeout()`
  formula the rest of the chain uses (the function has access to the
  same prompt), plus the outer buffer already used at the daemon layer,
  so all three layers are now consistently derived from one real number
  rather than three independently-guessed ones.
- **Status: CLOSED, 2026-08-23** — fixed in the same round it was found.

### [NEW-170] `core/planner_service.py:_request_daemon_plan()`'s broken-import fallback (`socket_timeout = 1400.0`) is itself a flat constant in a chain whose entire point is eliminating flat constants — safe only up to ~3060 estimated prompt tokens
- **Status: Suspected** — found by code-reviewer's final pass on the
  `NEW-169` fix (2026-08-23), narrow-trigger, not live-reproduced.
- **Mechanism:** when the `try`/`except Exception` around
  `compute_planner_timeout()`'s inputs fails (e.g. a broken
  `core.plannd`/`core.tokens`/`utils.config` import in the CLI process
  specifically — the daemon-side computation can succeed independently),
  `_request_daemon_plan()` falls back to a hardcoded `socket_timeout =
  1400.0`. Past roughly 3060 estimated prompt tokens (where
  `compute_planner_timeout(prompt_tokens, PLANNER_MAX_TOKENS=2048) +
  30.0 + 10.0` would exceed 1400.0), this flat fallback would again be
  shorter than the daemon's own formula-derived outer timeout for the
  same request — reproducing `NEW-169`'s exact bug shape at the tail,
  just with a much narrower trigger condition (an import failure, not
  the every-request case `NEW-169` was).
- **Impact:** low likelihood (requires a broken import specifically on
  the CLI side while the daemon side works, AND a prompt long enough to
  exceed the fallback's implicit budget) but real if both hold.
- **Not fixed this round** — flagged per rule 8 rather than silently
  patched; a durable fix would need the fallback to also be prompt-length-aware
  (or accept that an import failure this specific is rare enough that a
  generous flat ceiling is an acceptable degraded mode, and just raise it
  further) — a design call, not obviously worth a fourth round of the
  same fix pattern without Ish weighing in.

### [NEW-171] `tests/test_planner_service_daemon_socket_timeout.py`'s `test_request_daemon_plan_socket_timeout_exceeds_daemon_outer_timeout` re-derives `compute_planner_timeout(...) + 30.0` inline rather than calling into `core/daemon.py`'s own computation — can't detect drift if daemon's `+30.0` buffer changes later
- **Status: Suspected** — found by code-reviewer's final pass on the
  `NEW-169` fix (2026-08-23), test-quality gap, not a production defect.
- **Impact:** if a future change alters `core/daemon.py`'s outer-timeout
  buffer (currently `inner_timeout + 30.0`) without a corresponding
  change to this test's own re-derivation of the same formula, the test
  would keep passing while silently testing a stale expectation — the
  same "self-contained reimplementation instead of exercising the real
  code" trap this project has caught in prior reviews (e.g. the M1-B/C/D
  round's negative-control checks were added specifically to guard
  against this).
- **Not fixed this round** — cosmetic test-quality issue, not blocking.
  A future touch of this test file should prefer importing/calling
  `core/daemon.py`'s real computation (or a shared helper both files
  call) over a hand-copied formula, if one becomes available.

### [NEW-172] `core.planner_service.get_plan()` has zero production callers — its Attempt-2 orchestrator fallback and 7.3 sub-task C's `classify_tier()` log-only block are unreachable outside the test suite

- **Status:** Confirmed (exhaustive caller-graph check while scoping "Task 1
  of the 3-tier coding-task dispatch — easy-tier skip", 2026-08-24).
- **Evidence:** `planner_service.get_plan()`'s own docstring claims "Both
  main.py and core/agent.py should go through this module" — untrue for
  either as the code stands:
  - `main.py:410-416`'s `_try_daemon_plan()` imports and calls
    `_request_daemon_plan()` directly (`from core.planner_service import
    _request_daemon_plan`), never `get_plan()` itself — skipping straight
    past Attempt 1's wrapper and never reaching Attempt 2
    (`orchestrator.plan_tasks()`) or the tier-classification block above
    both.
  - `core/agent.py:1295`'s `get_plan(user_message, read_codeymd())` call is
    `core.planner.get_plan()` — a different module, different signature
    (`user_message, system_context -> str`), unrelated to
    `planner_service.get_plan()`.
  - `core/daemon.py:240`'s `plan_only=True` RPC path (the daemon's own
    planning entry point) calls `core.plannd.get_plan()` directly, not
    `planner_service`.
  - `core/task_executor.py:137` calls `run_agent(..., no_plan=True,
    _in_subtask=True)` — planning is explicitly bypassed for daemon-queued
    steps, so this path never plans at all, let alone through
    `planner_service`.
  - Grepped `--include=*.py --include=*.sh --include=*.js --include=*.html`
    repo-wide plus `importlib`/`getattr(...get_plan...)` for dynamic
    dispatch: no hit outside `planner_service.py` itself and its own test
    file (`tests/test_planner_service_classify_tier.py`,
    `tests/test_planner_service_daemon_socket_timeout.py`).
- **Impact:** `tests/test_planner_service_classify_tier.py` passes and
  exercises real code — but a green suite over an orphaned function is not
  evidence the function is wired into any live path. This is what made
  7.3 sub-task C look integrated when it isn't reachable in production.
  Any future task assuming `get_plan()` is "the" dispatch point (as the
  now-corrected 3-tier easy-tier scoping pass did) will produce code that
  never executes. See `NEW-126`'s rule-6 correction below for the direct
  consequence to that sub-task's own log evidence.
- **Also note (not fixed here):** `main.py:488-491`'s comment above the
  `is_complex()` gate still says "skip 1.5B planner" / "7B agent" — stale
  post-M1-D terminology naming a model layout that no longer exists.
  M-lane docs cleanup, not part of this finding's fix.
- **Not fixed this round** — this is a design question (consolidate
  `planner_service.get_plan()`'s two callers into the real ladder, or
  delete the orphaned function and its dead Attempt-2/classify_tier code)
  that overlaps `CODEY_MASTER_PLAN.md` §6.8 item 4.3's "migrate both
  existing call paths onto one boundary" — flagged for Ish, not silently
  fixed or silently dropped.

### [NEW-126] rule-6 correction (2026-08-24): the log-only mitigation this entry claimed never held — `classify_tier()`'s call site is itself unreachable in production

- **Status:** Confirmed — direct consequence of `NEW-172`.
- **Evidence:** the original entry's stated mitigation was: "the raw
  signal breakdown is included below specifically so these logs remain
  useful evidence for tuning sub-task E's thresholds later." That
  `info(...)` call lives inside `core.planner_service.get_plan()`, one
  level below the `classify_tier()` call. `NEW-172` establishes
  `get_plan()` has no production caller. Therefore this log line cannot
  have fired outside `tests/test_planner_service_classify_tier.py`'s own
  real-classifier tests — there is no persistent daemon log file to check
  either way (`utils/logger.py`'s `_log_to_file()` only writes once
  `setup_file_logging()` is called, which only happens in
  `core/daemon.py`'s own daemon-mode startup, a code path that never
  calls `planner_service.get_plan()`), so this is a structural conclusion
  from the caller graph, not a search of a log file that turned out empty.
- **Correction:** downgrade the earlier framing ("skews toward large,
  weak-but-nonzero discriminating signal, logs remain useful evidence")
  one step further than the 2026-08-23 correction already did. It is not
  just that `classify_tier()`'s decision rule is dead code beneath a
  guard that always returns early — the *log line reporting that
  decision* has never executed in any real session. Whoever picks up 7.3
  sub-task E should not expect any historical log evidence to exist for
  tuning thresholds; none was ever produced.

### [NEW-173] `core/plannd.py:parse_steps()`'s truncation heuristic (NEW-168) has two callers, both local and remote backends — the "same block, cheap to fold in" premise in the medium/hard tiering brief was wrong

- **Status:** Confirmed (upgraded from NEW-168's original "Suspected") —
  found while reconciling the two 3-tier scoping passes (2026-08-24).
- **Root cause, now pinned down exactly:** `core/plannd.py:213-215` —
  `if last and last[-1] not in ".!?)" and last[-1].isalpha(): print("[plannd]
  plan may be truncated...")` — fires on the last parsed step's final
  character, independent of `finish_reason`/`usage.completion_tokens`.
  `parse_steps()` has exactly two callers: `core/plannd.py:368` (inside
  `_get_plan_remote()`) and `core/plannd.py:510` (inside local `get_plan()`).
  Both are affected by the same false-positive.
- **Why this blocks a cheap fold-in:** fixing this properly requires
  `finish_reason`/`usage`, which exist only in each caller's scope, not
  inside `parse_steps()` itself. A real fix means either changing
  `parse_steps()`'s signature/return (touching the remote path, which
  `NEW-166` explicitly said to leave alone when `NEW-164`'s local-only
  budget fix landed) or duplicating a finish_reason check in both callers.
  Neither is "the same block already being edited" — the medium/hard
  tiering work only touches local `get_plan()`'s payload/parameter
  surface, not `parse_steps()` or `_get_plan_remote()`.
- **Decision (this round):** fenced out of the medium/hard tier task as
  its own scoped fix. Suggested shape for that future task: remove the
  character-heuristic print from `parse_steps()` entirely, and add a
  proper `finish_reason`/`usage.completion_tokens`-based truncation check
  independently in each of `get_plan()` and `_get_plan_remote()`, since
  they have different response shapes/budgets and NEW-166 already
  establishes they must not share a change silently.

### [NEW-174] `core/orchestrator.py:is_complex()`'s `length > 300` branch is byte-identical to its `length > 150` branch — dead differentiation

- **Status:** Confirmed — found while deriving a medium/hard tier split
  condition from `is_complex()`'s existing thresholds (2026-08-24).
- **Evidence:** `core/orchestrator.py`'s `is_complex()`:
  ```
  if score.length > 300:
      return score.signal_count >= 2
  elif score.length > 150:
      return score.signal_count >= 2
  else:
      return score.signal_count >= 3
  ```
  The `length > 300` and `length > 150` branches return the exact same
  expression. The comment above them ("Scale threshold by message length
  — longer messages need fewer signals") implies the `>300` branch was
  meant to require fewer signals than the `>150` branch (e.g. `>= 1`), but
  it never was written that way — there is no live behavioral difference
  between a 200-char and a 3000-char complex message today.
- **Not fixed this round** — outside scope of the medium/hard tiering
  task that surfaced it; flagging since any future consumer reading this
  comment (including the medium/hard tier split, which deliberately reuses
  `length > 300` as an existing, already-defined boundary — see
  `CODEY_MASTER_PLAN.md` Appendix A's tiering item) should not assume the
  code enforces the comment's stated intent.

### [NEW-175] Two live planning mechanisms never touched by any tier system: `core/agent.py:1271`'s `plan_tasks()` fallback and `core/planner.py:get_plan()`'s explicit `--plan` path

- **Status:** Confirmed — found while scoping which entry points the
  medium/hard tier split's `enable_thinking` parameter can reach
  (2026-08-24).
- **Evidence:**
  - `core/agent.py:1271` (`if is_complex(user_message) and not _in_subtask
    and not no_plan:`) calls `core.orchestrator.plan_tasks()` — a fully
    separate, in-process mechanism using `recursive_infer` against the
    primary model, with no daemon RPC and no `chat_template_kwargs`
    threading. This fires whenever `run_agent()` is invoked with
    `no_plan=False` (its default per `core/agent.py:956`) outside a
    subtask — concretely, at `main.py:589` (the "no plan available, daemon
    plan failed" fallback at the end of the same function that gates
    `_try_daemon_plan`) and at any other direct `run_agent()` call that
    doesn't set `no_plan=True`. It only fires today as a fallback of last
    resort once the daemon/`plannd` path has already failed/returned
    nothing, or when a caller bypasses `main.py`'s dispatch gate entirely.
  - `core/planner.py:get_plan()` (used only via the explicit `--plan` CLI
    flag at `core/agent.py:1287`) uses `core.inference_v2.infer()` directly
    — plain, no thinking mode, no daemon, genuinely orthogonal to the
    plannd/daemon planning ladder.
- **Impact:** a real (if minority) fraction of planning traffic — the
  daemon-unavailable fallback and the explicit `--plan` flag — will
  silently ignore whatever tier system ships for the primary daemon path,
  since neither mechanism has an `enable_thinking`/tier hook today.
- **Not fixed this round** — explicitly fenced out of the medium/hard tier
  task's scope (see the reconciled brief handed to implementer,
  2026-08-24); logged here so it isn't silently dropped. Future tiering
  work covering these two paths would need to either add thinking-mode
  control to `core/orchestrator.py:plan_tasks()`'s `recursive_infer` call,
  or accept that both stay full-capability-by-default (arguably the safer
  default for a last-resort/explicit path anyway).

### [NEW-176] `tests/test_orchestration.py:167`'s `TestScoreMessage` docstring still references `core.model_tiers.classify_tier()`, deleted as dead code by `NEW-172`'s fix
- **Status: Confirmed, trivial.** Found by the implementer fixing
  `NEW-172` (2026-08-24), while grepping the repo for leftover references
  to the deleted `classify_tier()`/`get_plan()` pair. A stale comment,
  not a call — `TestScoreMessage`'s behavior is unaffected, it does not
  actually invoke `classify_tier()`.
- **Not fixed this round** — out of the deletion task's file scope
  (a test file the task wasn't asked to touch). One-line comment fix
  whenever `tests/test_orchestration.py` is next edited for any reason.

### [NEW-177] `tests/test_new19_patch_failed_repeat_escalation.py`'s `_in_subtask=False` tests silently assume `main.py` is git-clean at test-run time — any uncommitted diff to `main.py` makes them fail with a captured-stdin `OSError`, unrelated to what they're actually testing
- **Status: Confirmed** — reproduced independently twice (implementer,
  then code-reviewer from scratch) during the `NEW-172` deletion task
  (2026-08-24).
- **Mechanism:** these tests exercise `core/agent.py`'s escalation path,
  which calls `check_git_and_offer_commit()` → `git_status_paths(["main.py"])`
  → real `git status` output, then `ask_confirm()`. The moment `main.py`
  has ANY uncommitted diff — content-independent, confirmed by dirtying
  only `main.py` against an otherwise fully-stashed clean tree — the
  status string is no longer `"Nothing to commit."`, `ask_confirm()`
  proceeds to read stdin, and under pytest's captured-output mode that
  raises `OSError` instead of the test's intended assertion running at
  all.
- **Impact:** any task that legitimately needs to touch `main.py` and
  run the test suite before committing (a normal, common state during
  active development — this exact project's own workflow leaves diffs
  uncommitted through a code-reviewer pass before every commit) will see
  these 3 tests fail for a reason unrelated to their actual subject. This
  has already happened at least twice this session alone. Not previously
  logged as its own finding — each time it was correctly diagnosed as
  pre-existing/unrelated and worked around, but never given a ticket, so
  the same diagnosis had to be redone from scratch each time.
- **Not fixed this round** — needs its own scoped task: mock
  `git_status_paths()`/`check_git_and_offer_commit()`'s git call in these
  specific tests (matching how other tests in this suite already isolate
  from real git state), rather than relying on the working tree happening
  to be clean when the suite runs.

### [NEW-178] `core/daemon.py`'s pull-side planning path (`_plan_claimed_task`, reached via `needs_planning=1` from `_handle_command`'s `plan_only=False` branch) has no way to carry a `tier` value through — the tasks table has no tier column, so a claimed task can only ever plan at the `tier="hard"` default
- **Status: Confirmed, low impact.** Found by the implementer building
  Task B of the 3-tier planning dispatch (2026-08-24), while threading
  `tier` through the socket-RPC planning path.
- **Mechanism:** `_plan_claimed_task(self, prompt: str)` has no `data`
  dict to read a `tier` field from — its only caller passes
  `db_task["description"]` from SQLite, and the tasks table schema has
  no tier column to carry a value through from wherever the task was
  originally enqueued. The implementer added `tier: str = "hard"` as a
  plain parameter default rather than plumbing a real value, which is
  honest about the gap rather than silently pretending it's handled.
- **Impact, bounded:** per the pre-existing `NEW-112` finding, this
  entire pull-side path (`plan_only=False`'s enqueue-then-plan-later
  flow, `needs_planning=1`) has **zero live production callers today** —
  it is real, intended future functionality, not currently reachable.
  So this gap cannot manifest in current production traffic; it becomes
  relevant only if/when `NEW-112`'s dormant path is ever activated.
- **Not fixed this round** — fixing it properly means adding a `tier`
  column to the tasks table schema (or an equivalent side-channel), which
  is real schema-migration work disproportionate to a currently-dead code
  path. Whoever activates `NEW-112`'s pull-side path should address this
  at the same time, not before.

### [NEW-179] `MAX_CONCURRENT_MODEL_BUDGET_BYTES >= compute_device_ceiling_bytes()` was never documented as a required ordering, or tested — M1-F's own first-pass re-derivation violated it
- **Status: Confirmed, caught and fixed within the same round (M1-F,
  2026-08-24) before landing.** `core/resource_gate.py`'s
  `MAX_CONCURRENT_MODEL_BUDGET_BYTES` (the SUM-of-concurrently-declared-
  models budget check) and `compute_device_ceiling_bytes()` (the absolute
  per-model physical ceiling, rule 12) are independent checks, but the
  former has always needed to sit AT OR ABOVE the latter — otherwise the
  budget check can refuse a single model that `hard_reject` would
  otherwise admit, inverting rule 12's "hard_reject is the absolute
  per-model bound" into "budget is the real bound, tighter than the
  documented physical one." The retired 8.90GiB value satisfied this by a
  wide margin (~0.82 vs. ~0.60 of MemTotal) and its own comment even
  observed the relationship ("well above DEVICE_CEILING_USABLE_FRACTION,
  this is INTENTIONAL") — but never stated it as a *requirement*, and no
  test pinned it.
- **Mechanism:** M1-F's re-derivation for the single-model architecture
  (§1.4/M1-D) first computed a value (5.25GiB) from the concurrent raw sum
  alone (interactive primary + embed, ~5.18GiB, rounded up with margin),
  without checking it against `compute_device_ceiling_bytes()`
  (~6.48-6.50GiB on this device). Running the existing test suite
  immediately caught this: `test_hard_ceiling_boundary_flips_hard_reject`,
  `test_primary_model_admitted_under_idle_conditions`, and
  `test_new21_naive_check_without_margin_would_have_admitted` all failed —
  each builds a model just under the device ceiling on an otherwise-idle
  device and asserts admission, and each was refused with
  `budget_ceiling_exceeded` instead.
- **Fixed within the same round:** re-derived to 7.00GiB, chosen to clear
  the live device ceiling (~6.4949GiB) by a real margin (~0.505GiB, not
  the ~6MiB an intermediate 6.50GiB candidate would have left) as well as
  the concurrent raw sum. Full reasoning in
  `core/resource_gate.py`'s `MAX_CONCURRENT_MODEL_BUDGET_BYTES` comment.
  New regression test `test_max_concurrent_budget_at_least_device_ceiling`
  in `tests/test_resource_gate.py` now pins the invariant directly so a
  future re-derivation cannot silently re-break it.
- **Logged per rule 8** even though fixed the same round, because the gap
  (the ordering requirement existing undocumented and untested for the
  entire lifetime of this constant, since TODO.md 7.4a) is itself the
  finding, independent of this round's specific near-miss.

### [NEW-180] Embed model's real resident RSS has never been measured — `MAX_CONCURRENT_MODEL_BUDGET_BYTES`'s embed term remains a floor estimate, not a measurement
- **Status: Confirmed gap, not a bug.** Checked directly during M1-F
  (2026-08-24, `NEW-156`'s re-derivation): searched this project's live-
  test history (`PROJECT_LOG.md`, M1-E's entry) for a real measured embed
  RSS figure and found none. Every derivation of
  `MAX_CONCURRENT_MODEL_BUDGET_BYTES` back to TODO.md 7.4a sub-task C1 has
  used the same floor estimate — `EMBED_MODEL_PATH`'s file size (80.2MiB)
  + `DEFAULT_COMPUTE_OVERHEAD_BYTES` (256MiB) = 352,542,080 bytes
  (~0.328GiB) — because the embed model_id has no `KNOWN_MODEL_ARCHS`
  entry, so `estimate_model_load_cost()` cannot compute a KV term for it,
  and `core/embed_server.py` launches it at a fixed `-c 2048` unrelated to
  whatever `n_ctx` the coder's own ModelSpec uses.
- **Impact:** `MAX_CONCURRENT_MODEL_BUDGET_BYTES` (7.00GiB as of M1-F)
  carries real margin above both the interactive concurrent raw sum
  (~1.4GiB) and the device ceiling (~0.505GiB), so this gap is not
  currently load-bearing for the single-model architecture's realistic
  cases the way it was for the tighter, now-superseded 5.20-5.25GiB
  candidates M1-F considered and rejected before settling on 7.00GiB.
  Still open because the underlying number this floor estimate stands in
  for has simply never been checked against reality.
- **Not fixed this round** — measuring real embed RSS needs a live
  embed-server spawn/measure/kill cycle (rule 2 discipline: `free -h`
  before/after, PID tracked and killed individually, confirmed unloaded),
  out of scope for M1-F's arithmetic-only re-derivation. Natural pairing
  for a future round that already needs a live embed-server cycle for
  another reason, rather than a dedicated round just for this.
- **Status update, 2026-08-26 — first real measurement taken, one of
  this finding's two claims closes, the other stays open.** Live-verifier
  ran a real `codey-start` launch with a background `/proc/<pid>/status`
  sampler polling the embed `llama-server` PID (31070) from the moment it
  appeared. First two samples, ~9s and ~11.3s after daemon start, both
  plateaued at `VmRSS 191,252 kB` / `RssAnon 98,516 kB` / `RssFile 92,336
  kB` / `VmSwap 0 kB` — i.e. **186.77 MiB (195,842,048 bytes) real
  resident, pre-eviction.** That is *lower* than the floor estimate this
  finding's own text describes (352,542,080 bytes / 336.2 MiB), the
  figure every derivation of `MAX_CONCURRENT_MODEL_BUDGET_BYTES`/
  `MAX_SWAP_ASSIST_BYTES` back to 7.4a sub-task C1 has used — meaning the
  floor over-reserves relative to reality, and those constants carry MORE
  real margin than assumed, not less. A reassuring direction, not a
  correction that shrinks anything.
  - **CLOSING** the narrow claim this entry's title makes — "real embed
    RSS has never been measured" is no longer true; it has now been
    measured once, directly, via `/proc/status`, with a clean pre-launch
    baseline and no confounds.
  - **NOT closing** the constants' own "never validated against reality"
    caveat, and deliberately so. A third sample, 25s after the second
    (once the coder began loading), showed the SAME embed process's
    `VmRSS` collapse to 3,052 kB with 98,184 kB pushed to `VmSwap` — the
    resident figure this finding just measured is not stable; it moved
    ~60x under exactly the memory pressure the gate exists to manage, in
    ~25-28s (faster than `NEW-14`'s previously reported ~40s eviction
    window — see `NEW-14`, same phenomenon, sharper timing). One
    idle-plateau sample at a fixed `-c 2048` on one build, on one device,
    under one set of ambient conditions, is enough to retire "unmeasured"
    but not enough to retire "unvalidated" — a second or third
    independent sample (different ambient pressure, different time of
    day) would be needed before treating 186.77 MiB as representative
    rather than a single anecdote that happened to land on the low side.
  - **Net status: PARTIALLY CLOSED.** The measurement-exists claim is
    resolved; the representativeness/validation claim stays open and is
    re-titled in spirit (not renumbered) as "real embed RSS has been
    measured once; not yet validated as representative across
    conditions."

### [NEW-181] `CODEY_MASTER_PLAN.md`/`PROJECT_LOG.md`'s M1-F status language went briefly stale — said "not code-reviewer-approved" after the approval had actually happened
- **Status: Confirmed, process-integrity, not safety-relevant on its own —
  corrected the same round it was found.** Found during a 2026-08-25 audit
  cross-checking `CODEY_MASTER_PLAN.md` against actual repo state, which
  flagged an apparent contradiction: commit `2eae89f` ("M1-F: re-derive
  stale resource-gate constants...")'s message states a code-reviewer pass
  happened and approved the change, while that same commit's diff to
  `CODEY_MASTER_PLAN.md`/`PROJECT_LOG.md` says "not code-reviewer-approved."
  **Re-checked against this session's own actual chronology (the audit
  agent, running fresh with no session memory, couldn't see this): the
  commit message was correct.** The real sequence was (1) project-architect
  scoped and implemented M1-F, writing the docs' "self-reviewed, not
  code-reviewer-approved" status language as accurate *at that point*, (2)
  the mandatory code-reviewer subagent then ran and approved (with one
  fix — `PROJECT_LOG.md`'s "Files touched" line was missing
  `tests/test_loader_resource_gate.py`), (3) that one fix was applied and
  `2eae89f` was committed — meaning the review had already happened by
  commit time, but the docs' broader "not code-reviewer-approved" status
  sentences were never updated to match, only the one specific line the
  reviewer flagged was. The commit message describing an approval that had
  genuinely just occurred was accurate; the docs it carried forward were
  the stale side.
- **Impact:** low, transient — the actual constants and tests were never
  in question, and the gap was self-corrected within the same task once
  spotted (not left standing across sessions). Recorded because rule 6
  (correct the record when a claim doesn't hold up) applies even to a
  same-round, same-session slip, and because `MAX_CONCURRENT_MODEL_BUDGET_
  BYTES`/`MAX_SWAP_ASSIST_BYTES` are rule-4-category constants (gate
  model-load admission on a device that has crashed from bad concurrent
  loads before) — worth being precise about their review status even for
  a few minutes of doc lag.
- **Fixed same round**: `CODEY_MASTER_PLAN.md` (§4.2's M1-F entry, §6.2's
  M1-F entry, and Appendix A's `M1-F` checkbox) and `PROJECT_LOG.md` (new
  2026-08-25 entry layered on top of the 2026-08-24 one, left in place as
  an honest record of what was true at the time it was written) now all
  correctly read **code-complete, code-reviewer-approved 2026-08-25, not
  live-verified**. Commit history itself is not amended (git safety
  protocol, no rewriting a published commit) — `2eae89f`'s message stands
  as-is, and it was accurate at the time it was written. Nothing about
  M1-F's actual constants or tests was ever in question — only the
  tracked docs' status language briefly lagged the real approval by one
  editing pass within the same round.

### [NEW-182] `core/context.py`'s prompt-scanning auto-preload (`auto_load_from_prompt`, called unconditionally from `core/agent.py:1265`) now preloads any file named in a `detect_filenames()`-matchable path, in ANY bare single-shot task prompt — making "did the model call `read_file` before editing" structurally unmeasurable this way at HEAD, though it was NOT a confound for the original `NEW-30` A/B pass (a different-era regex bug, since fixed, made that one shape safe then, not now)
- **Status:** Confirmed (mechanism traced and reproduced directly; scope
  of which prompt shapes it affects is narrower than the live-verifier's
  initial framing — see below).
- **What's Confirmed:** M1-G's G2 test (this round, 2026-08-25) reused
  `TaskExecutor._execute_task` with a bare `"Add a docstring to the
  shutdown function in <path>."`-style prompt naming a real, existing
  file. `core/context.py:97`'s `load_file()` — reached via
  `auto_load_from_prompt()` — preloads that file's full content into
  `core.memory_v2`'s working memory *before* the model runs at all
  (`✓ Loaded: fixture_b_small.py (432 chars)` appears in the archived
  `.live_verify_scratch/m1g_g2_output.log` before any inference). Once
  preloaded, the model has no need to call `read_file` itself — draws 1-2
  never did. This makes "did it read before it patched" unmeasurable with
  this prompt shape: not calling `read_file` isn't a discipline failure
  here, it's the correct response to content already being visible.
- **What's also Confirmed, correcting the live-verifier's broader framing:**
  the *original* 2026-07-31 `NEW-30` third-pass A/B test
  (`.live_verify_scratch/ab_driver.py`, 3 draws per arm, the exact
  `"Previous context: ...\n\nYour task (step 2/2): Edit <path>..."`
  daemon-step-template `case1_prompt` shape — verified this is the real
  A/B cycle's own driver, not `driver.py`'s separate single-draw
  `case1_anchor`/`case2_control`/`case3_new49` trials, which are a
  different script) was checked directly against the archived
  `.live_verify_scratch/ab_output.log` from that actual run: no
  `✓ Loaded:` line appears anywhere in the log, and the fixed arm's model
  explicitly called `read_file` on `.live_verify_scratch/case1_anchor.py`
  in all 3 draws before `patch_file`. So the original pass's model
  genuinely called `read_file` itself, un-preloaded, in the run actually
  scored. That pass's 0/3 (pre-fix) vs. 3/3 (post-fix) differential is a
  paired A/B comparison under a constant condition either way, so even if
  preload had fired identically in both arms it could not explain a
  0/3-vs-3/3 gap — **no rule-6 downgrade of the original `NEW-30` fix is
  warranted from this finding.**
- **Root cause of why the old run escaped the confound — traced, not
  guessed:** the live-verifier's original hypothesis (re-run the same
  `case1_prompt` shape today to avoid the preload) does **not** hold at
  HEAD, and the reason is `NEW-62` — a fix landed the *same day*
  (`4625e43`, 2026-07-31) as the archived A/B pass, for a bug in
  `detect_filenames()`'s regex. The pre-fix regex
  (`r"(?:\.{0,2}/)?[\w\-/]+\.(?:py|...)"`) matched
  `.live_verify_scratch/case1_anchor.py` but **stripped the leading dot**
  from the directory segment, producing `live_verify_scratch/case1_anchor.py`
  (verified directly: `re.findall()` with the pre-fix pattern against the
  exact `case1_prompt` text returns exactly this dot-stripped string) —
  which then fails `detect_filenames()`'s own existence check (the
  directory literally starts with a dot on disk), so the match gets
  silently dropped and `auto_load_from_prompt()` preloads nothing. The
  post-fix regex (in `core/context.py` at HEAD) preserves the leading dot
  and the same string now passes the existence check — confirmed by a
  direct call to `auto_load_from_prompt()` on the identical prompt text
  today, which prints `✓ Loaded: case1_anchor.py (151 chars)`. Also ruled
  out: the `used < total * 0.5` context-usage gate at
  `core/agent.py:1263-1264` was checked directly (`core.tokens.get_context_usage`)
  and evaluates `True` today (3759/65536) — the gate was not, and is not,
  what blocked preload; it is entirely `NEW-62`'s regex fix.
- **Consequence for G2b, corrected from this round's first pass: re-running
  `case1_prompt` verbatim today will NOT avoid the auto-preload confound
  — it will hit the identical confound as G2, because the exact bug that
  used to make this shape "safe" (`NEW-62`) has since been fixed.** G2b
  as originally scoped in this round's first docs pass is **not viable
  as written** and needs a different design — e.g. a prompt that refers
  to the target file without a `detect_filenames()`-matchable path (so
  the model must locate it itself), or an explicit, clearly-labeled
  harness-side bypass of `auto_load_from_prompt()` for that one call. Not
  designed this round — flagged as the open next step (see
  `CODEY_MASTER_PLAN.md`'s M1-G entry).
- **Practical upshot:** any bare single-shot prompt that names an
  existing file in a form `detect_filenames()` matches — daemon-step
  shape or not — will be preloaded before inference under the current
  (post-`NEW-62`) code, making read-before-patch sequencing structurally
  unmeasurable via `_execute_task`-style tests naming a real path
  directly. A viable re-test needs either a path `detect_filenames()`
  won't match, or an explicit, honestly-labeled ablation of the preload
  step.
- **Cross-references:** `NEW-30` (the original read-before-patch fix and
  its three prior live-verify passes), `NEW-60` (workspace-boundary bug
  that invalidated two of those earlier passes, unrelated mechanism),
  `NEW-62` (the dot-path regex fix that is the actual mechanism here).
- **2026-08-25 update (second desk-only round) — narrowed, not closed.**
  A viable G2b design now exists and is pre-registered in
  `CODEY_MASTER_PLAN.md`'s M1-G entry (§4.2 and Appendix A): a fixture
  whose extension (`.cfg`) is not in `detect_filenames()`'s alternation
  list, referenced by exact path in a prompt matching `ab_driver.py`'s
  `case1_prompt` daemon-step shape. Confirmed empirically (not by regex
  reasoning) that `detect_filenames()`/`auto_load_from_prompt()` both
  return `[]` for this exact prompt. Also confirmed, and this is the
  reason for `NEW-185`, filed at the end of this ledger: for a real `.py`
  target, **no** phrasing
  that names the file by path avoids the preload — `.py` is a full-match
  extension, matched in any syntactic position, so a non-matching
  extension is the only deterministic escape found. This does not close
  `NEW-182` — the underlying mechanism (any bare prompt naming a real
  `.py`/`.json`/etc. file by path gets preloaded) is unchanged and still
  makes read-before-patch unmeasurable for that fixture domain; it only
  narrows the practical impact by identifying one fixture domain
  (non-full-match extensions) where the confound is avoidable. The
  redesigned G2b itself has **not been run** — this is a design-only
  update.
- **2026-08-25 update (third round, live G2b run) — narrowed further to
  "measurable and clean on one data point," still NOT closed.** G2b ran
  live: precondition gate 5/5 passed fresh (not reused from the desk-only
  check), `free -h` before `5.6Gi used, 598Mi free, 4.9Gi available`,
  after `5.2Gi used, 2.9Gi free, 5.4Gi available`, `ps aux | grep
  llama-server` clean before/after, `loader.get_pid()` returned `None`
  after unload. All 3 draws: grounding 3/3 (every `old_str` an exact
  substring of the fixture's real content), sequencing 3/3 (a qualifying
  `read_file` precedes the first qualifying `patch_file` in every draw's
  trace). Direct confirmation the preload was absent *during* the run,
  not just predicted: the `✓ Loaded: case_g2b_anchor.cfg` marker never
  appears in any draw; the only load-adjacent marker is `ℹ Read
  .live_verify_scratch/case_g2b_anchor.cfg (106 chars)`, which appears
  *after* the model's own `read_file` call in every draw. **This narrows
  the finding to "measurable and clean on one data point," not "fixed" or
  "closed"** — it rests on N=3, a single fixture domain (`.cfg`, chosen
  because it accidentally avoids `detect_filenames()`'s extension match
  per `NEW-185`'s truncation bug, not because the preload mechanism
  itself changed), and the fixture's content-trap corroboration (an
  unspaced `timeout=30` designed so a guessed value would plausibly come
  out spaced and fail the patch) never actually fired in any draw — no
  draw ever produced a failed patch attempt, so the sequencing result
  rests on tool-call trace order plus the precondition gate's
  payload-level confirmation that the fixture's content was absent from
  the pre-inference payload, not on a caught bad guess. This is real but
  weaker evidence than the original G2b design anticipated. **The
  underlying mechanism this finding is actually about —
  `auto_load_from_prompt()` unconditionally preloading any `.py`/`.json`/
  etc. (full-extension-match) file named in a bare prompt — is completely
  unchanged and still confounds read-before-patch measurement for real
  coding-target extensions.** Separately, G2's own result (same round as
  the original finding) already measured **grounding 3/3 in the
  `.py`-under-preload domain itself** — the one axis that is actually
  live when preload fires (sequencing is moot once content is already in
  context) — so between G2 and G2b, both applicable axes now have a real
  measurement in their respective domains; only `.py`/`.json`-domain
  *sequencing specifically* remains genuinely unmeasurable, and has no
  reachable test design at HEAD short of fixing `core/context.py` (out of
  scope here) or an explicit harness-side preload bypass (not built).
  This finding stays **Confirmed and open** — it is a standing
  methodology-gap finding independent of any one task's status; see
  `CODEY_MASTER_PLAN.md`'s M1-G entry for how this fed into that item's
  own close decision.

### [NEW-183] `core/plannd.py`'s `PLANNER_PROMPT` now has `NEW-50`'s exact original regression-guard test prompt embedded twice as worked content (a VIOLATION block and a full worked EXAMPLE, both showing the identical correct answer) — this specific test prompt can no longer cleanly discriminate "leak genuinely fixed" from "model matched an in-prompt example"
- **Status:** Confirmed (both blocks read directly at HEAD `fe39a35`,
  line numbers verified against the live file, not assumed from an older
  citation).
- **Detail:** `NEW-50`'s test prompt is `"Fix the off-by-one error in the
  loop in core/legacy_calc.py"`, correct answer `"1. Edit
  core/legacy_calc.py: fix the off-by-one error in the loop"`. Verified
  present verbatim in `core/plannd.py` at two places:
  - `core/plannd.py:60-66` — the VIOLATION block, contrasting a wrong
    Create-based plan against this exact correct Edit-based one.
  - `core/plannd.py:171-177` — a full worked EXAMPLE with the identical
    user prompt and identical correct one-line plan.
  Traced via `git log -L`: both blocks were added in commit `d674a0c`
  (2026-07-30), the day *before* `NEW-50` was filed (2026-07-31) using
  this exact prompt as its test case. `NEW_ISSUES.md`'s own `NEW-50` text
  records a 1/3 leak on the 1.5B model *despite* this counter-example
  already being live at the time — so it is not evidence-free to test
  this same prompt against a new model and call a clean result
  meaningful; the M1-G G3 live pass's 5/5 clean result (this round,
  2026-08-25) is real evidence the leak isn't reproducing on Qwen3.5-4B,
  not circular. Going forward, however, this specific prompt is a weaker
  discriminator than it used to be, precisely because its own correct
  answer is now sitting in the prompt twice as a worked example — a
  model could produce the right output by matching either worked block
  rather than by correctly reasoning about Edit-vs-Create from scratch.
- **Recommendation, not yet scoped as a task:** any *future* re-test of
  this same worked-example-leak concern (verbatim content leaking from
  one of `PLANNER_PROMPT`'s examples into an unrelated request) should
  use a fresh Edit-vs-Create test prompt that has no matching worked
  block anywhere in `PLANNER_PROMPT`, to keep the test meaningful as a
  discriminator.
- **Cross-references:** `NEW-50` (the original finding), `CODEY_MASTER_PLAN.md`
  §4.2's M1-G entry (G3 test writeup and result).

### [NEW-184] `CODEY_MASTER_PLAN.md` Appendix A's `M1-F` item contradicted itself on review status in the same entry
- **Status:** Confirmed, already self-corrected in this same editing pass
  (fixed below, in this round's docs update — logged per rule 8 rather
  than silently dropped).
- **Detail:** Appendix A's `M1-F` checkbox item said, in the same
  paragraph, both "code-reviewer-approved 2026-08-25" and, one sentence
  later, "Mandatory code-reviewer pass still outstanding" — a direct
  contradiction. Commit `fe39a35` ("M1-F review status was stale") had
  already fixed this exact class of staleness elsewhere in the same
  round (see the preceding entry above, `2eae89f`/`fe39a35`'s own
  writeup) but missed this one trailing sentence in the Appendix A
  checkbox item specifically. Same category as `NEW-181`: docs status
  language lagging an approval that had actually already happened.
- **Fixed same round (this M1-G docs-processing round, 2026-08-25):** the
  stray "Mandatory code-reviewer pass still outstanding" sentence removed
  from Appendix A's `M1-F` item; it now consistently reads
  code-complete, code-reviewer-approved 2026-08-25, not live-verified.

### [NEW-185] `core/context.py`'s `detect_filenames()` regex silently truncates several extensions to a shorter listed extension instead of failing to match
- **Status:** Confirmed (reproduced directly via `re.findall`, not
  reasoned from the pattern alone).
- **Detail:** found while designing M1-G's redesigned G2b test (see
  `CODEY_MASTER_PLAN.md`'s M1-G entry, 2026-08-25 second round). The
  extension alternation in `detect_filenames()`'s regex
  (`core/context.py:189`) is
  `py|json|js|ts|sh|yaml|yml|toml|txt|md|html|css|cpp|c|h|rs|go|rb|java`.
  Several real extensions are literal superstrings of a shorter listed
  alternative — `cfg` contains `c`, `pyi`/`pyx` contain `py`, `tsx`
  contains `ts`, `jsx` contains `js`, `hpp` contains `h`. Because the
  regex has no extension-boundary anchor, `re.findall` matches the
  shorter alternative and silently drops the trailing characters instead
  of failing to match or matching the full real extension. Verified
  directly: `re.findall(pattern, ".../case_g2b_anchor.cfg ...")` returns
  `.../case_g2b_anchor.c` (not `.cfg`, not "no match").
- **Consequence:** in practice this is usually self-neutralizing —
  `detect_filenames()` also requires the (truncated) path to exist on
  disk, and a `.cfg` file's truncated `.c` sibling usually does not
  exist, so the file is silently *not* preloaded (this is exactly the
  property M1-G's G2b test exploits deliberately). But the failure mode
  runs the other way too, silently: if a repo happens to contain both
  `foo.cfg` and a same-stem `foo.c` (or `foo.pyi`/`foo.py`,
  `foo.tsx`/`foo.ts`, etc.), a prompt naming `foo.cfg` will silently
  preload `foo.c`'s content instead — the wrong file, with no error or
  warning surfaced anywhere.
- **Not fixed this round** — out of scope for the M1-G test-design task
  that found it; logged per rule 8. A real fix would add a
  word-boundary/end-of-extension anchor (e.g. `(?:py|...|c|...)\b` or an
  explicit negative lookahead against the other listed extensions) so the
  regex either matches the full real extension or doesn't match at all.
- **Cross-references:** `NEW-62` (an earlier, different `detect_filenames()`
  regex bug — the leading-dot stripping bug, unrelated mechanism but same
  function), `CODEY_MASTER_PLAN.md`'s M1-G / G2b entry (where this was
  found and where the precondition-gate mitigation for G2b's own fixture
  is spelled out).

### [NEW-186] `TaskExecutor`/executor path emits duplicate post-completion `note_save` calls after a patch has already succeeded, on some draws but not others
- **Status:** Confirmed (observed directly in raw tool-call traces), but
  the underlying cause and its relationship to any other tracked finding
  is Suspected only — not confirmed either way.
- **What's Confirmed:** in M1-G's G2b live run (2026-08-25, `.cfg`
  fixture, `ab_driver.py`-shaped daemon-step prompt, N=3), draws 1 and 2
  each emitted two identical `note_save` calls back-to-back after the
  target patch had already succeeded and the task was otherwise complete;
  draw 3 emitted only one. All three draws' actual file edits were
  correct and identical regardless — this is wasted/duplicated
  post-completion tool activity, not a correctness bug in the edit
  itself.
- **What's Suspected, not Confirmed:** the live-verifier who found this
  flagged it as possibly related to `NEW-168`/`NEW-173`'s "`[plannd] plan
  may be truncated`" false-positive category (a task-completion
  recognition problem), but explicitly declined to assert the
  connection. That prior finding lives in the planner's plan-parsing path
  (`core/plannd.py`); this one is a duplicate tool-call emission in the
  executor path (`TaskExecutor._execute_task` and whatever loop decides a
  task is "done" and stops issuing tool calls) — plausibly the same root
  category (the system not reliably recognizing "this step is finished")
  but a different code path, and not verified to be the same mechanism.
  Recorded as a **separate finding**, cross-referenced, not folded into
  `NEW-168`/`NEW-173`, per the live-verifier's own stated uncertainty.
- **Not investigated further or fixed this round** — out of scope for
  M1-G's docs-closeout pass. A follow-up would need to look at what
  signal (if any) tells the executor loop a task is complete and why that
  signal fires twice on 2/3 draws here but once on the third.
- **Cross-references:** `NEW-168`/`NEW-173` (possible, unconfirmed,
  related "task completion recognition" category in the planner path),
  `CODEY_MASTER_PLAN.md`'s M1-G / G2b entry (where this was observed).

### [NEW-187] `can_dispatch_task()`'s separate swap-assist consumer bypasses `reserve_slot()`'s locked PENDING-swap accounting — `NEW-135`'s fix does not cover this path
- **Status: FIXED and CODE-REVIEWER-APPROVED, 2026-08-26 (confirmatory
  pass).** Independent re-review confirmed both required changes from the
  round below: the except-branch sets `swap_assist_enabled = False` on a
  `total_reserved_swap_bytes()` read failure (no permissive `0`
  substitution); control flow verified sound (no dead/unreachable
  reference, no `NameError` path); the renamed
  `test_can_dispatch_task_new187_reserved_swap_read_failure_fails_closed`
  genuinely exercises the real call site and asserts the safe outcome;
  docstring/this entry's "never writes" wording correction confirmed
  accurate. Test runs independently reproduced:
  `tests/test_resource_gate.py -q` → 200 passed;
  `tests/ -q --ignore=tests/test_restoricon_core` → 671 passed, 1
  skipped. **Not live-verified (no live component by design).** Closes
  `NEW-187`'s own review chain — does not by itself close 7.4a, which
  still has `NEW-140`'s remaining content / `NEW-188`'s live-verification
  gap open.
- **Status update, 2026-08-26 (later same day) — mandatory rule-4
  code-reviewer pass: CHANGES REQUESTED, then fixed and re-verified.**
  The reviewer found the original fix's read-failure fallback
  (`reserved_swap_for_dispatch = 0` on any exception from
  `total_reserved_swap_bytes()`) failed in the WRONG direction — treating
  an unreadable ledger as "no other in-flight claims" is the MORE
  permissive reading, exactly backwards for a gate, and inconsistent with
  (a) the sibling `CODEY_SWAP_ASSIST_ADMISSION` handler a few lines above
  in the same function, which explicitly fails toward disabled/restrictive,
  and (b) `reserve_slot()`'s own read of this identical ledger, which has
  no try/except and fails closed (propagates, admission refused) rather
  than substituting a permissive default. Given `NEW-188` (found in the
  same round) shows the swap-distress admission margin has already
  widened from 3-of-4 to 4-of-4 at real Qwen3.5-4B cost, the reviewer
  judged this the wrong moment to accept a permissive fail-safe direction
  as a low-priority nit. **Fixed**: the except-branch now sets
  `swap_assist_enabled = False` (skip the swap branch for this dispatch
  tick, byte-for-byte the pre-D2 RAM-only outcome) instead of substituting
  `reserved_swap_for_dispatch = 0`, matching the sibling handler's
  pattern exactly. `tests/test_resource_gate.py`'s
  `test_can_dispatch_task_new187_reserved_swap_read_failure_falls_back_to_zero`
  (which had pinned the unsafe direction, asserting `decision.allowed is
  True` on a read failure) was renamed to
  `test_can_dispatch_task_new187_reserved_swap_read_failure_fails_closed`
  and now asserts `decision.allowed is False` /
  `decision.dispatched_via_swap is False` on the same `OSError` injection.
  **Reviewer also flagged the docstring/this entry's original "never
  writes to it" framing as inaccurate**: `total_reserved_swap_bytes()`
  calls `list_slots(reap_dead=True)` by default, and `list_slots()` DOES
  mutate the shared slot store under lock when reaping (drops dead-PID
  entries) — so `can_dispatch_task()` does write to the shared state file
  on every call where the swap branch is reached, at daemon-tick
  frequency (far more often than `reserve_slot()`'s own reaping, which
  only happens at load-admission time). The one-directional design itself
  is still correct (dispatch never registers a durable PENDING claim a
  racing `reserve_slot()` would sum against), but the docstring's wording
  has been corrected from "reading, never writing" to "never registers a
  durable claim, though its reaping side-effect does mutate the shared
  store." Full suite re-run after the fix: `200 passed` in
  `tests/test_resource_gate.py` alone (full-repo count not re-verified in
  this entry; see `PROJECT_LOG.md`'s corresponding entry for the
  full-suite figure at the time of this fix). **`NEW-187` is now
  code-complete and incorporates the reviewer's required changes — still
  needs a follow-up confirmatory code-reviewer pass on the corrected diff
  before 7.4a can close**, since a code-reviewer subagent applying its own
  requested fix and self-approving is not equivalent to an independent
  re-review.
- **Status update, 2026-08-26 (earlier same day, superseded by the fix
  above) — CODE-COMPLETE, NOT YET CODE-REVIEWER-APPROVED.** `can_dispatch_
  task()` (`core/resource_gate.py`, the `if swap_assist_enabled:` branch
  starting around what is now line 2549) now reads `total_reserved_swap_
  bytes()` — the exact ledger `NEW-135`'s fix populates on `reserve_
  slot()`, already documented on that function as usable by "any direct
  caller that isn't `reserve_slot()`" — and passes it as `compute_swap_
  assisted_headroom_bytes()`'s `reserved_swap_bytes` parameter, so a
  dispatch decision's own `DISPATCH_MAX_SWAP_ASSIST_BYTES` (768MiB) cap
  shrinks by however much a concurrently-PENDING `reserve_slot()`
  admission has already claimed against the shared live `SwapFree`
  figure. Two new tests added (`tests/test_resource_gate.py`):
  `test_can_dispatch_task_new187_deducts_reserve_slot_pending_swap_claim`
  and (originally) `test_can_dispatch_task_new187_reserved_swap_read_
  failure_falls_back_to_zero` — the latter's name and assertion were
  corrected by the fix above. Full suite at this point: `671 passed, 1
  skipped`. **This fix is deliberately ONE-DIRECTIONAL, not a full close
  of the underlying race**: `can_dispatch_task()` never registers a slot
  and commits no durable PENDING claim of its own — a dispatch decision
  leaves nothing in the ledger for a racing `reserve_slot()` call to sum
  against, unlike two `reserve_slot()` callers racing each other
  (`NEW-135`'s original symmetric case). `can_dispatch_task()` also runs
  already-resident models (task execution against an already-loaded
  model), not a new model load, so there is no analogous "commit" on its
  side to protect against in the first place — this asymmetry is judged
  the correct closing state for this gap, not a deferred half-measure.
- **Status: Confirmed** — found by code-reviewer during the mandatory
  rule-4 pass on `NEW-135`/`NEW-136`'s fix (commits `3513661`/`f7511bb`),
  2026-08-25. Disclosed by the implementer in `can_admit()`'s own
  docstring ("Caveats carried forward" section) and in `NEW-135`'s own
  entry, not discovered independently by the reviewer — but per rule 8
  this still needs its own tracked entry rather than living only as prose
  inside a fix that is otherwise closed.
- **The gap:** `NEW-135`'s fix closes the double-claim race for any
  caller going through `reserve_slot()` — it computes the real
  PENDING-only sum of other slots' `swap_bytes_claimed` inside
  `reserve_slot()`'s own lock. `can_dispatch_task()` (7.4a sub-task D2)
  is a separate `can_admit()` consumer that decides dispatch eligibility
  without registering a slot at all — since this accounting mechanism is
  keyed off persisted slot records, `can_dispatch_task()` has nothing to
  sum against and cannot participate in the new locked accounting.
- **Why this is a real, if currently low-priority, gap and not a
  restatement of NEW-135's original scope:** a caller reaching
  `can_dispatch_task()` concurrently with a `reserve_slot()` admission (or
  with another `can_dispatch_task()` call) could theoretically still
  independently claim the same swap-assist headroom that `NEW-135`'s fix
  now protects on the `reserve_slot()` side — the structural double-claim
  `NEW-135` fixed for one path still exists, unfixed, on this other path.
  Reviewer judged this an acceptable disclosed limitation, not a blocking
  defect, for this round's approval — but "acceptable to ship disclosed"
  is not the same as "closed."
- **Not fixed here** — logging only, per this task's explicit scope
  (documentation/status-recording pass, no code changes). No live
  reproduction attempted; this is a code-level structural gap
  identified by reading, same as `NEW-135`'s own original discovery
  method.
- **Fix direction, if picked up later:** either give
  `can_dispatch_task()` a way to register/track its own pending swap
  claim against the same accounting `reserve_slot()` now maintains, or
  determine (and document) that `can_dispatch_task()`'s call pattern in
  practice makes the race unreachable — this would need to be checked
  against `can_dispatch_task()`'s actual callers, the same way `NEW-112`
  checked the command handler's enqueue branches for real live callers.
- **Cross-references:** `NEW-135`, `NEW-136` (the fix this gap was found
  during review of), `NEW-112` (precedent for checking whether a
  consumer path has real live callers before treating a gap as
  practically reachable).

## Found during 7.4a closeout re-verification, 2026-08-26 (project-architect, desk-only arithmetic re-derivation against already-measured M1-E/M1-F figures, no live model load) — NOT fixed here, logged only

### [NEW-188] `NEW-140`'s general mechanism re-measured against real Qwen3.5-4B cost — the exact historical `NEW-21` swap-distress device state is now admissible via swap-assist at ALL FOUR `MemAvailable` points in `NEW-21`'s own plausible range, not 3 of 4 as the stale retired-7B figures showed

- **Status: Confirmed** — computed directly against the real, current
  `core/resource_gate.py` functions (`can_admit()`, `estimate_model_load_
  cost()`), not re-derived by hand or assumed from the retired-model
  numbers. This is the re-measurement `NEW-140`'s own 2026-08-25 status
  update and M1-E's entry both called for but had not yet been done.
- **Inputs used, all read from this codebase's own already-recorded
  figures, none newly measured live (per this task's explicit desk-only
  scope):**
  - Real Qwen3.5-4B interactive cost at full production `n_ctx=65536`
    (`core/resource_gate.py`'s own M1-F derivation comment, ~line 1503-1510,
    and `tests/test_resource_gate.py`'s `test_qwen35_4b_total_cost_
    reconciles_with_master_plan_table` at `n_ctx=32768` for the same
    model/arch): `ModelSpec(model_id="primary", size_bytes=2_740_937_888,
    n_ctx=65536)` → `estimate_model_load_cost()` gives
    `total_bytes=5,209,547,936` (4.8518GiB), matching M1-F's own recorded
    figure exactly.
  - `REQUIRED_HEADROOM_FACTOR=1.25` (unchanged) → required =
    `6,511,934,920` bytes (6.0647GiB).
  - `MAX_SWAP_ASSIST_BYTES=6.50GiB` (M1-F, 2026-08-24, current value).
  - The exact `NEW-21` fixture shape `NEW-140`'s own worked example used:
    `MemTotal=10.8GiB, MemFree=2.2GiB, SwapTotal=8.0GiB, SwapFree=6.8GiB`,
    `MemAvailable` swept across `NEW-21`'s own stated plausible range
    (2.2/3.5/5.0/6.5GiB).
- **The finding, live-called against the real `can_admit()` (not a mock,
  though no model was loaded — pure in-process function call against a
  synthetic meminfo dict, matching this task's explicit "deskwork against
  already-measured figures" scope):**
  ```
  2.2 admitted=True  via_swap=True  cost=5209547936 headroom=2362232012
      swap_claimed=4149702908
      reason: cost 4968MiB x 1.25 = 6210MiB exceeds RAM-only headroom
      (2253MiB), but covered by RAM + swap-assisted headroom (7578MiB,
      of which 5325MiB is swap-assisted) — admitted via swap assist
  3.5 admitted=True  via_swap=True  cost=5209547936 headroom=3758096384
      swap_claimed=2753838536  ... swap-assisted headroom 8909MiB,
      5325MiB swap-assisted
  5.0 admitted=True  via_swap=True  cost=5209547936 headroom=5368709120
      swap_claimed=1143225800  ... swap-assisted headroom 10445MiB,
      5325MiB swap-assisted
  6.5 admitted=True  via_swap=False cost=5209547936 headroom=6979321856
      swap_claimed=0
      reason: within headroom (with margin) and device ceiling
  ```
  Every one of the four `MemAvailable` points in `NEW-21`'s own plausible
  range now admits — including the 2.2GiB floor point (`MemAvailable ==
  MemFree`, no reclaimable cache at all), which was the ONE point that
  still denied for the retired 7B (`NEW-140`'s original worked example:
  "admitted=False ... reason: cost 8143MiB exceeds current headroom
  (2253MiB)"). At 6.5GiB the load is now admitted on RAM alone, with no
  swap assist needed at all, because Qwen3.5-4B's required cost
  (6.0647GiB) is smaller than the retired 7B's (7.951GiB) and now sits
  just BELOW the top of `NEW-21`'s own plausible `MemAvailable` range.
- **Why this is a genuinely worse outcome, not just "still applicable" as
  the 2026-08-25 status update phrased it before this re-measurement**:
  `NEW-140`'s original worked example (retired 7B) had exactly one safety
  net left in `NEW-21`'s plausible range — the 2.2GiB floor, where
  `MemAvailable` equals `MemFree` with zero reclaimable cache, i.e. the
  worst-case reading of `NEW-21`'s own reported state. That floor case now
  ALSO admits for the real, shipped Qwen3.5-4B model. The device-grounded
  swap contribution itself is unchanged (`gated_swap_free = SwapFree -
  2*slmk_floor = 6.8 - 1.6 = 5.2GiB`, matching the 5325MiB swap-assisted
  figure at every non-6.5GiB point above, exactly as `NEW-140`'s own
  derivation already established for the retired 7B) — what changed is
  that Qwen3.5-4B's smaller required cost (6.0647GiB vs. the 7B's
  7.951GiB) needs less RAM+swap to clear, so it clears at every point this
  fixture sweeps, not just three of four.
- **What this does NOT establish**: this fixture's `SwapTotal=8.0GiB` is
  itself a stale, historical number from when `NEW-21` was originally
  observed (2026-07-29) — the real device's `SwapTotal` has since grown to
  ~16.00GiB (Ish's zram increase, confirmed live by M1-F's 2026-08-24
  session, `core/resource_gate.py` ~line 1697). This finding is therefore
  the same kind of synthetic-worst-case check `NEW-140`'s own retired-7B
  example already was (and that the existing `test_new21_production_
  call_shape_swap_assist_may_now_admit` test in `tests/test_resource_
  gate.py` still is, unmodified, still pinned to the retired 7B's
  `primary-7b`/`QWEN25_7B_ARCH` spec) — not a claim that this exact
  `SwapTotal=8.0GiB` condition can recur on the live device today. The
  device-grounded mechanism it demonstrates (a raised swap-assist cap
  making a historically-distress-causing device shape admissible) is
  real and current; the specific `SwapTotal` operand in the fixture is
  not. No live reproduction was attempted here, consistent with this
  task's explicit desk-only scope (rule 12/rule 5: computed against real
  functions and real recorded cost figures, not guessed or paraphrased).
- **Conclusion for `NEW-140`'s item (1) (the general mechanism)**: STAYS
  OPEN, with the severity assessment upgraded from "still applicable,
  unmeasured against the current model" to "measured against the current
  model, and the outcome is a wider admission window (4/4 vs. 3/4) than
  the retired model's own numbers showed." Does not close clean and does
  not close with a caveat — this is a live-verification gap (`NEW-140`'s
  own "Required addition to the live-verification plan" item, still not
  done) that a desk-only arithmetic pass cannot itself close; it can only
  confirm the mechanism is real and current, which it has now done.
- **Recommended follow-up, not performed here (out of this round's
  explicit desk-only scope)**: (1) update or add a `test_new21_...`-style
  fixture in `tests/test_resource_gate.py` using the real `primary`/
  `QWEN35_4B_ARCH` spec instead of the retired `primary-7b`/
  `QWEN25_7B_ARCH` one, so the pinned regression test reflects the
  currently-shipped model rather than stale arithmetic; (2) the live
  low-swap-headroom single-model verification pass `NEW-140` originally
  called for (its "Required addition to the live-verification plan"
  section) has still never been run — this remains the one thing that
  would actually confirm or refute real-world risk, not just the
  mechanism's arithmetic reachability.
- **Cross-references:** `NEW-140` (the finding this re-measures; stays
  open, not superseded), `NEW-21` (the original swap-distress
  observation this fixture shape is grounded in), `NEW-14` (related
  concurrent-model distress observation), M1-E/M1-F (the real cost/cap
  figures this re-derivation used verbatim, not re-measured live).
- **Status update, 2026-08-26 — the live pass this entry's own "Required
  follow-up" item (2) called for HAS now been run** (see `NEW-140`'s own
  2026-08-26 status update for the full verbatim numbers — not repeated
  here to avoid drift between two copies of the same figures). Summary:
  real production `reserve_slot()` call, ambient (not induced) device
  state, DID land inside the swap-assist branch for the first time
  (`admitted_via_swap=True`, `swap_bytes_claimed=35,048,904` bytes), and
  the live `estimated_cost_bytes` (5,209,547,936) matched this entry's own
  desk-derived figure exactly — real-production confirmation that this
  entry's arithmetic inputs were correct. However `SwapFree` was 90.1%
  free (14.415GiB of 16.0GiB) at the time — nowhere near the `NEW-21`
  fixture's `SwapFree≈6.8GiB`-of-8GiB compound-distress shape this entry
  re-measures against — so this entry's core concern (does the WIDENED
  4-of-4 admission window in this entry's own worked example actually
  occur on a device that is ALSO short on swap, not just short on RAM)
  remains unobserved live. Follow-up item (2) is therefore partially
  discharged: the mechanism's live reachability is now confirmed;
  admission under genuine compound distress is not. Follow-up item (1)
  (a `primary`/`QWEN35_4B_ARCH` regression fixture in
  `tests/test_resource_gate.py`, replacing the stale retired-7B one) is
  still not done. **`NEW-188` stays OPEN.** Whether the remaining
  compound-distress gap needs a deliberately-induced future live pass or
  can be accepted as a standing documented risk is Ish's call — logged as
  `CODEY_MASTER_PLAN.md` §8 Q10.
- **Status update, 2026-08-26 — Ish answered §8 Q10: "accept the residual
  as a standing documented risk for now."** **Status: OPEN, but no
  further live-verification work is planned against the compound-distress
  question** — same distinction as `NEW-140`'s parallel update: this is a
  risk-acceptance decision, not a fix or a refutation, so the finding
  itself is not marked Resolved. The live reachability of the general
  swap-assist mechanism is confirmed (see `NEW-140`'s 2026-08-26 update);
  admission under genuine compound low-RAM-AND-low-swap distress remains
  unobserved and is now accepted as a standing risk rather than chased
  further. Follow-up item (1) above (the stale `primary-7b`/
  `QWEN25_7B_ARCH` regression fixture in `tests/test_resource_gate.py`
  should be replaced with a `primary`/`QWEN35_4B_ARCH` one) is
  **unaffected by this decision and still outstanding** — it is a
  test-accuracy cleanup, not a live-verification question, and is not
  what Ish's decision addresses. 7.4a is CLOSED in `CODEY_MASTER_PLAN.md`
  on this decision — see its Appendix A entry and §8 Q10 for Ish's exact
  wording.

## Found during the mandatory rule-4 code-reviewer pass on Track B / Phase B1 (Restoricon Core), 2026-08-26 — one blocking defect FIXED same round, three non-blocking findings logged only

### [NEW-189] `crm_service.py`'s `get_project()`/`list_projects()` had no `has_permission()` gate at all — FIXED same round
- **Status: FIXED, 2026-08-26.** Reviewer proved with a fake zero-
  permission actor object (`has_permission()` returning `False`
  unconditionally) that `crm.get_project(1, actor)` and
  `crm.list_projects(actor)` both returned full project data with no
  `PermissionError` — unlike every other entity's read path in the same
  file (`get_customer()`/`list_customers()` call `has_permission()` or
  `can_access_customer()` before touching the database; `get_project()`/
  `list_projects()` only special-cased `ROLE_CUSTOMER`/`ROLE_TECHNICIAN`
  narrowing, with no base gate for any other actor). Not live-exploitable
  under the shipped role matrix (all of `admin`/`manager`/`sales`/
  `project_manager`/`ai_agent` happen to carry `PERM_READ_ALL_PROJECTS`),
  but the check's absence meant a hypothetical future role, or a bug
  elsewhere that produced an actor object outside `ROLE_PERMISSIONS`
  entirely, would fall through to full, unfiltered project access with
  zero enforcement — exactly the scenario the reviewer's fake actor
  reproduced directly.
- **Fix**: both methods now raise `PermissionError` unless the actor
  holds at least one of `PERM_READ_ALL_PROJECTS`,
  `PERM_READ_ASSIGNED_PROJECTS`, or `PERM_READ_OWN_PROJECTS` (added
  `PERM_READ_OWN_PROJECTS` to the file's import block, previously
  unused there), checked before any database read. Verified the fix
  closes the reviewer's exact reproduction: a fake zero-permission actor
  now gets `PermissionError` from both methods (reproduced directly,
  not just claimed). `tests/test_restoricon_core/` full suite:
  `11 passed`; full repo suite: `482 passed, 1 skipped`
  (`--ignore=tests/test_resource_gate.py`) + `200 passed`
  (`tests/test_resource_gate.py`) = consistent with the previously
  reported `682 passed, 1 skipped` total.
- **Not yet independently re-reviewed** — this fix needs its own
  confirmatory code-reviewer pass before Phase B1 can be considered
  code-reviewer-approved as a whole, per this project's standard
  reject-and-loop-back pipeline (the same pattern `NEW-187` just went
  through).

### [NEW-190] `RESTORICON_API_HOST` env var can silently bind the REST API to `0.0.0.0` with no warning or guard
- **Status: Confirmed, not fixed — logged only, non-blocking per the
  reviewer's verdict.** `restoricon_core/api/server.py:25`:
  `DEFAULT_HOST = os.getenv("RESTORICON_API_HOST", "127.0.0.1")` — the
  default is the safe loopback address, but nothing prevents
  `RESTORICON_API_HOST=0.0.0.0` (or any other interface) from silently
  exposing the token-authenticated CRM API beyond localhost, with no
  startup warning distinguishing "explicitly configured for a LAN
  deployment" from "accidentally exported/inherited from a shell
  profile." Same shape as this project's own prior GUI-server finding
  (`C-2`, `2026-07-29` — see that round's entries) about unguarded
  bind-address configuration.
- **Suggested direction, not applied**: log a startup warning whenever
  the resolved bind host is not `127.0.0.1`/`localhost`, so a
  non-loopback bind is visible in the logs rather than silent.

### [NEW-191] `restoricon_core/api/routes.py:244`'s 500 handler leaks raw exception text to the client
- **Status: Confirmed, not fixed — logged only, non-blocking per the
  reviewer's verdict.** `except Exception as ex: return 500, {...},
  {"error": f"Internal server error: {str(ex)}"}` returns the raw
  Python exception string in the HTTP response body for any unhandled
  server-side error — a standard information-disclosure smell (can leak
  file paths, SQL fragments, internal state) even though this server is
  loopback-only by default (see `NEW-190`, which is exactly why this
  isn't purely academic if the bind address is ever widened).
- **Suggested direction, not applied**: return a generic error message
  to the client and log the real exception (with traceback) server-side
  only.

### [NEW-192] Only `admin`/`customer` roles hold `PERM_SIGN_CONTRACTS` — `manager`/`sales`/`project_manager` cannot sign contracts
- **Status: FIXED, 2026-08-26 — deliberate placeholder policy, per Ish's
  own explicit direction** ("create the logical contract-signing
  workflow. i will change it later if needed. as most policy and
  procedures for the company are in the development phase. but we need
  to finish Codey-OS"). `restoricon_core/auth.py`'s `ROLE_PERMISSIONS`
  matrix now grants `PERM_SIGN_CONTRACTS` to `ROLE_ADMIN` (unchanged),
  `ROLE_MANAGER` (new), `ROLE_SALES` (new), `ROLE_PROJECT_MANAGER` (new),
  and `ROLE_CUSTOMER` (unchanged) — the company-side roles plausibly
  involved in closing/managing a job, plus the customer as the other
  signing party. Deliberately still withheld from `ROLE_TECHNICIAN` (not
  a signing role in this business) and `ROLE_AI_AGENT` (an autonomous
  agent should not hold binding-signature authority by default — a
  judgment call, not something Ish specified, flagged here per rule 5 so
  it's visible if that default needs revisiting). Documented in
  `auth.py`'s own comment above `PERM_SIGN_CONTRACTS` as an explicit
  placeholder, not a final business rule — Restoricon's real signing
  workflow and procedures are still being developed, and Ish has said
  this will likely change. `tests/test_restoricon_core/` — `11 passed`,
  no regression. **Not yet independently code-reviewed** — this is an
  RBAC-matrix edit in `auth.py`, the same file `NEW-189`'s review
  covered; per this project's standard practice for anything touching
  auth, a follow-up confirmatory pass is warranted before treating this
  as done, even though the underlying business-rule decision itself was
  made by Ish directly and is not in question.

### [NEW-193] Several Restoricon Core entities have `POST` routes but no corresponding `GET` routes yet
- **Status: Confirmed, not fixed — logged only, non-blocking per the
  reviewer's verdict, likely just incomplete Phase B1 scope rather than
  a defect.** Reviewer noted during the `restoricon_core/api/routes.py`
  read-through that some entities' route registration is currently
  write-only. Not enumerated exhaustively in this entry — a future round
  extending the REST API surface should audit `routes.py` against the
  full entity list in `CODEY_MASTER_PLAN.md`'s Phase B1/Appendix C spec
  and fill in the missing read routes as part of that work, not as a
  standalone fix.

### [NEW-194] `get_project()`/`list_projects()`'s narrowing logic (customer isolation, technician-assignment filter, financial-field redaction) is keyed on `actor.role` identity, not on the permission that passed `NEW-189`'s new top-level gate
- **Status: Confirmed, not fixed — logged only, non-blocking, does not
  reopen `NEW-189`.** Found by code-reviewer during `NEW-189`'s
  confirmatory pass, 2026-08-26. `NEW-189`'s fix added a top-level check
  requiring at least one of `PERM_READ_ALL_PROJECTS`/
  `PERM_READ_ASSIGNED_PROJECTS`/`PERM_READ_OWN_PROJECTS` before either
  method touches the database — but everything BELOW that gate (the
  customer-isolation check, the technician-assigned-employee filter, and
  the financial-field/notes/subcontractors redaction for customers) is
  still keyed on `actor.role == ROLE_CUSTOMER`/`== ROLE_TECHNICIAN`
  identity, not on which of the three permissions the actor actually
  holds. A constructed actor with `role="nobody"` and `has_permission()`
  returning `True` only for `"read:own_projects"` passes the new
  top-level gate (satisfying `NEW-189`'s fix), then falls through every
  narrowing branch below it (none of which match `role == ROLE_CUSTOMER`
  or `== ROLE_TECHNICIAN`) and receives an UNFILTERED `get_project()`/
  `list_projects()` result — another customer's project, full financials,
  full notes, full subcontractors, with no customer-isolation check at
  all.
- **Not live-exploitable under the shipped role matrix** — only
  `ROLE_CUSTOMER` currently holds `PERM_READ_OWN_PROJECTS` and only
  `ROLE_TECHNICIAN` currently holds `PERM_READ_ASSIGNED_PROJECTS`, so no
  actor construction reachable through this codebase's own actor-creation
  paths can currently produce the role/permission mismatch the
  reproduction used. Same "one matrix edit away" shape `NEW-189` itself
  used to justify non-Critical status for its own (now-fixed) gap — this
  is the same class of latent risk, one layer deeper.
- **Fix direction, if picked up later**: re-key the narrowing logic
  (customer isolation, technician filter, financial redaction) on the
  specific permission the actor holds (`PERM_READ_OWN_PROJECTS` →
  customer-shaped narrowing, `PERM_READ_ASSIGNED_PROJECTS` → technician-
  shaped narrowing, `PERM_READ_ALL_PROJECTS` → no narrowing) rather than
  on `actor.role` identity, so the permission model and the data-shaping
  logic can't drift apart the way `NEW-189` and this finding both show
  they currently can. Not fixed here — same file, same category as
  `NEW-189`, but a distinct code change or Ish's confirmation that
  role-identity keying is intentional (roles and permissions are meant to
  move together, and `has_permission()` alone is not meant to be load-
  bearing for shaping) is enough of a design question that it should not
  be silently changed in a confirmatory-review round.
- **Cross-references:** `NEW-189` (the fix this was found reviewing;
  does not reopen it — this is a distinct, deeper gap).

### [NEW-195] Real interactive coder session hung on a trivial "ping" prompt for 700+ seconds while swap climbed steadily — but the same window had a confirmed, uncontrolled confound (an active phone call, other app use, and screen standby on the test device), so this data cannot currently attribute the cause to Codey-OS

- **Status: Confirmed observation of the raw symptom (a 700+ second
  non-completion with climbing swap); Suspected but NOT reliably
  attributable to a Codey-OS-side cause** — downgraded from an initial
  stronger framing after Ish reported, after this round's data was
  captured, that the device was under real concurrent load for the
  entire observed window: **"the phones screen went off because i wasnt
  using it and i made a call and did other things while the live test
  were running which might be effecting things also."** This was not
  known to live-verifier at capture time and was not controlled for.
  Found 2026-08-26 during a real `codey-start` full-stack
  live-verification pass scoped to check 7.4b-A/C and `NEW-180`.
- **Raw sequence, as observed (unaffected by the confound question —
  these are the literal timings/readings):** daemon started, embed
  server resident immediately (PID 31070); ~9-12s later `free -h` showed
  `Mem: 8.7Gi used, 83Mi free, 1.8Gi available` — the tightest ambient
  window observed in the whole session. The coder then loaded
  successfully as a genuine cold interactive spawn (on-disk evidence:
  `~/.codeyOS/llama-server.log:1`'s spawn line carries `-c 65536`
  verbatim, corroborated by `ps`). A trivial prompt sent immediately
  after never completed: the "Thinking..." counter passed 700+ seconds
  with no response. Over that ~12-minute window, `free -h` showed swap
  climbing steadily from 1.8Gi used to 4.3-4.5Gi used (SwapFree dropping
  from ~14Gi to ~10.5-10.7Gi of 15Gi total — still comfortably free by
  `NEW-21`/`NEW-140`'s low-swap standard, never approaching a compound
  low-RAM-AND-low-swap state), while the coder process's own RSS share
  of total RAM fell from 45.2% to 25.7%. Live-verifier judged this a
  thrashing/distress signature at the time and aborted rather than
  layering a second load attempt on top of already-degraded conditions,
  per this round's explicit device-safety-first instruction; the session
  was never allowed to resolve naturally.
- **The confound, stated plainly:** for the entire observed hang window,
  the test device was concurrently handling an active phone call and
  other app activity, and the screen went into standby from disuse. A
  phone-call app and any other foreground apps compete directly for the
  same RAM/CPU the resident models were using; screen-off/standby can
  trigger Android's own Doze/App Standby power management, which
  throttles CPU scheduling and can deprioritize or evict background
  processes. Any of these — independently or combined — could fully
  explain 700+ seconds of stalled inference and climbing swap with **no
  Codey-OS-side bug required at all.**
- **What this finding can and cannot currently support:** it CANNOT
  currently distinguish between (a) a genuine Codey-OS/llama.cpp-side
  thrashing bug under swap pressure, and (b) ordinary resource
  contention from unrelated concurrent phone usage plus Android
  power-management effects on a session that was supposed to be running
  isolated. Both remain open possibilities, roughly equally weighted
  given what's known — this is NOT framed as "probably an internal bug,
  root cause merely undiagnosed," which was this entry's original,
  now-corrected framing (rule 6: corrected the same round it was
  found, before being committed to the record with the stronger claim
  standing).
- **What is NOT affected by the confound, and stays as independently
  solid evidence:** the swap-claim data point below is a structural
  resource-gate fact recorded at admission time, not a timing
  observation over the hang window, and is not plausibly explained away
  by concurrent phone usage the way the multi-minute stall's cause is.
  Post-teardown, `~/.codeyOS/resource_gate_state.json` retained a stale
  `"resident"` slot for this exact session (see `NEW-196` for why it's
  stale) showing `"model_id": "primary", "cost_bytes": 5209547936,
  "pid": 31292, "swap_bytes_claimed": 472718792` (copy preserved at
  `docs/archive/live-evidence/2026-08-26-7.4b-codey-start/
  resource_gate_state.json`). Per `core/resource_gate.py`,
  `swap_bytes_claimed` is only set nonzero when `admitted_via_swap
  =True` — so a swap-assisted admission is inferred with high
  confidence, though (unlike the previous live pass, which captured the
  `GateDecision` line directly) the `GateDecision` itself was not
  captured this session, only this persisted downstream value. Taking
  that at face value: **472,718,792 bytes (~450.9 MiB) claimed from swap
  headroom**, roughly 13x the 35,048,904-byte claim in the previous live
  pass that fed `7.4a`/§8 Q10's 2026-08-26 risk-acceptance decision
  (`CODEY_MASTER_PLAN.md` §8 Q10), under the tightest `MemAvailable`
  (~1.8GiB) of any session so far. This admission fact stands regardless
  of what caused the subsequent hang, and is logged for Ish's awareness
  alongside `NEW-140`/`NEW-188` without reopening §8 Q10's resolution —
  `SwapFree` never dropped below roughly 70% free, so `NEW-21`/`NEW-140`/
  `NEW-188`'s specific low-RAM-AND-low-swap fixture shape was still not
  met.
- **7.4b-C impact — unaffected by the confound:** whatever the cause,
  the abort itself is a real, structural fact: 7.4b-C's
  background/daemon-dispatch context branch (expected `n_ctx=16384`) was
  never reached this round because live-verifier aborted before a second
  load could be attempted. This stays true and continues to block that
  half of 7.4b-C regardless of how the hang's root cause resolves.
- **Not fixed, not root-caused this round.** Recommended next step,
  revised given the confound: **re-run this same test with the phone
  device NOT concurrently used for any other purpose for the entire
  duration** — no calls, no other apps in the foreground, screen kept on
  or its state explicitly monitored — before treating the original
  700+-second observation as evidence of anything Codey-OS-side. A
  desk-only investigation (inference call path, llama-server's own log
  for this PID) can still be useful in parallel but should not be
  treated as chasing a confirmed internal bug until a clean re-run
  either reproduces or fails to reproduce the hang.
- **Process note for future live-verify rounds (not implemented this
  round):** Ish has enabled ADB on the test device and wants future
  live-verify passes to use it to monitor other apps opening/closing and
  screen/standby state for the full duration of a live test, specifically
  to rule this class of confound in or out going forward (e.g.
  `dumpsys`/`logcat` for foreground-app changes, power state for
  screen/Doze). Building that monitoring harness is scoped as its own
  separate piece of work, not something attempted inline in this
  docs-only round.
- **Cross-references:** `NEW-14` (original swap-distress precedent,
  ~40s eviction window vs. this round's related ~25-28s embed-eviction
  observation under `NEW-180`), `NEW-21` (the specific compound low-RAM-
  AND-low-swap fixture shape this round approached but did not fully
  meet), `NEW-140`/`NEW-188` (the swap-assist-admits-into-distress
  mechanism the admission fact above provides new evidence about,
  independent of the hang confound), `NEW-180` (the embed-eviction data
  point gathered in the same session), `CODEY_MASTER_PLAN.md` §8 Q10
  (the risk-acceptance decision the admission fact should inform,
  without unilaterally reopening it).
- **Status update, 2026-08-26 — clean(er) re-run: same scenario did NOT
  hang, but the re-run is NOT a clean single-variable test, so this
  stays OPEN, downgraded further rather than closed.** A second
  `codey-start` full-stack pass sent the same trivial "ping" prompt under
  the same interactive scenario, this time monitored throughout by
  `tools/adb_confound_monitor.py` (see `NEW-198`). Wakefulness stayed
  `Awake` the entire ~22.7-minute window — no screen-off/standby this
  time, unlike the original capture — but foreground activity briefly
  flipped to the Samsung launcher twice, including a ~3-second blip
  bracketing the exact moment the prompt was sent (`PING_SENT_AT` =
  11:32:48). Live-verifier did not deliberately switch apps and does not
  know the cause; the blip is too brief relative to the run's 324.8s
  total to plausibly explain that duration, but it means this round is
  not a perfectly confound-free control either — a materially better
  one than the original capture, not a perfect one.
- **The response this time: 542 tokens in 324.8s (160.7s prefill over
  4156 tokens + 164.0s eval, 3.31 tok/s), then a correct stop to ask for
  shell-command confirmation** (the model interpreted "ping" as a
  request to run the shell `ping` command — a reasonable tool-use
  reading, not a bug). This was NOT a same-scenario, same-conditions
  re-run in one respect that matters: `NEW-197` raised
  `MODEL_CONFIG["n_threads"]` 4→6 between the original capture and this
  re-test, so the confound-reduction and the thread-count increase both
  changed at once. The measured generation speedup at 6 threads (roughly
  1.2-2.9x per `NEW-197`'s own numbers) is the same order of magnitude
  as the difference between 700+s of non-completion and this run's 325s
  — a competing, equally plausible explanation for why this run
  finished when the original didn't. This round's data cannot isolate
  which of (confound removed) or (threads raised) — or some mix of
  both — is responsible.
- **What this DOES establish, stated precisely:** 542 tokens of output
  at this device's real measured throughput (160.7s prefill + 164.0s
  eval ≈ 325s) is this scenario's normal cost at `n_threads=6`. A longer
  thinking block, or the same prompt at the original `n_threads=4`
  (roughly 2x slower per `NEW-197`), would plausibly put >700s of
  non-completion inside a scenario's ordinary generation time with no
  internal defect required — i.e., part of the original 700+s
  observation may simply have been normal (if slow) generation that
  live-verifier aborted before it could finish, independent of the
  phone-call/screen-standby confound. This reasoning does NOT require
  claiming "the clean re-run didn't reproduce it, so the original was
  the confound" — that framing conflates two changed variables and is
  not supported by this round's evidence alone.
- **Decision: stays OPEN, framing downgraded further rather than
  resolved/closed-as-non-reproduced.** Marking this Resolved would
  overclaim what a two-variable re-test can show. What has firmed up:
  the original 700+s stall is no longer the project's only data point on
  this scenario's normal duration, and nothing in either session
  currently requires a Codey-OS-internal defect to explain the delay —
  but a properly isolated re-run (same `n_threads`, verified zero
  foreground-app flips for the entire window) has still never been done.
  Recommended next step if this is picked up again: hold `n_threads`
  fixed at whatever the current production value is and use the
  confound monitor for the full window with zero flips, so a future
  result isolates one variable at a time.
- **Cross-references, added this round:** `NEW-197` (the concurrent
  thread-count change that confounds this re-test's interpretation),
  `NEW-198` (the ADB confound monitor's stdout-buffering bug, fixed
  same round it was found, which very nearly caused this exact re-test
  to be misjudged as confound-free in real time).

### [NEW-196] Live occurrence of `NEW-40`'s documented SIGTERM/cleanup asymmetry: a mid-generation `SIGTERM` left a stale `"resident"` slot entry in `resource_gate_state.json` after a real `codey-start` teardown

- **Status: Confirmed, live-reproduced** — not a new defect, a real,
  concrete occurrence of an already-documented gap (`NEW-40`). Found
  2026-08-26 during the same `codey-start` live-verification round as
  `NEW-195`. Teardown required live-verifier to `kill -TERM` three stuck
  TUI-side PIDs (31204, 31185, 31042) directly before running
  `codey-stop` itself — the coder's hung generation (`NEW-195`) had left
  the TUI session unresponsive to normal shutdown. `codey-stop`'s own
  kill logic (`codey-stop:34,38`, see this round's addendum to `NEW-103`)
  is a blanket `pkill -9 -f "llama-server"` / `pkill -9 -f
  "gui/server.py"` — live-verifier did not blindly trust this: it
  verified a clean pre-launch baseline (`ps aux | grep llama-server`
  empty before `codey-start` ran) that specifically licensed this run's
  blanket kill as safe (nothing foreign could have been hit this
  particular time, since nothing foreign was running), then independently
  cross-checked via `ps` afterward that all 7 tracked PIDs were actually
  gone. This does NOT close `NEW-99`/`NEW-103` — it documents one
  instance handled carefully, not a general guarantee.
- **The stale-state finding itself:** after teardown completed,
  `~/.codeyOS/resource_gate_state.json` retained
  `{"slot_id": "50885b5887b5442fb416bc699999f301", "model_id": "primary",
  "cost_bytes": 5209547936, "pid": 31292, ..., "status": "resident", ...,
  "swap_bytes_claimed": 472718792}` for a PID (31292) that was confirmed
  gone via `ps` — a stale `"resident"` slot for a process that no longer
  exists. `main.py`'s own `_sigterm_handler` docstring already documents
  the exact mechanism: `SIGTERM` arriving mid-generation hits a window
  that isn't guarded the way the model-load `try/except
  (KeyboardInterrupt, SystemExit)` sites are, per `NEW-40`'s original
  finding (the REPL's steady-state wait catches `SIGINT` but not the
  `SystemExit` `SIGTERM` raises). This round's `SIGTERM` landed during
  active generation (the hung request from `NEW-195`), not at an idle
  `input()` wait, but the same underlying asymmetry — cleanup code that
  depends on an exception guard `SIGTERM` doesn't always reach —
  produced the same class of outcome: a slot release that never ran.
- **Impact:** a stale resident slot could cause a future `can_admit()`
  call to under-count available headroom (treating memory as claimed
  when the process holding it is gone) until the gate's own dead-PID
  reaping logic (`_pid_alive()`-based) clears it on a later cycle — not
  confirmed to have caused a live over/under-admission this round, since
  no second load was attempted after teardown.
- **Not fixed this round** — live-verification only, per this round's
  scope. Fix direction is `NEW-40`'s own: extend `SIGTERM` cleanup
  coverage to generation-in-progress code paths, not just the four
  existing model-load guards and the idle `input()` wait.
- **Cross-references:** `NEW-40` (the documented gap this is a live
  occurrence of), `NEW-99`/`NEW-103` (the blanket-`pkill` teardown
  pattern this round's `codey-stop` kill relied on, verified safe in
  this specific instance only), `NEW-195` (the hung generation whose
  mid-flight `SIGTERM` triggered this).
- **Status update, 2026-08-26 — did NOT recur in the same day's
  follow-up round; not closed, just not re-observed.** The `NEW-195`
  re-test round's own teardown was reported clean (`codey-stop` reported
  "no llama-server processes remain," tracked-PID `ps` grep empty,
  `git status` clean). This coordinating session independently checked
  `~/.codeyOS/resource_gate_state.json` after that round's teardown
  (verification per this round's own instruction not to infer from
  "teardown clean" alone) and found it is now `[]` — empty, no stale
  `"resident"` slot, mtime matching that round's final-teardown
  timestamp. This is real evidence the specific stale-slot outcome did
  not repeat this time, most plausibly because that round's teardown
  path did not need to fight a hung mid-generation `SIGTERM` the way
  `NEW-195`'s original capture did (this round's "ping" request
  completed normally in 324.8s before the session was torn down, rather
  than being killed mid-flight). This does NOT close `NEW-196` — the
  underlying `SIGTERM`-during-generation cleanup gap (`NEW-40`'s own
  scope) is unchanged in the code; this round simply didn't exercise the
  same failure window, since nothing was killed mid-generation this
  time.

## Found/actioned outside the live-verify round above, 2026-08-26 — Ish's direct request, applied same session

### [NEW-197] `MODEL_CONFIG["n_threads"]` raised 4 → 6 per Ish's request — not yet live-benchmarked
- **Status: Code-complete, not yet live-verified.** Ish, while the
  `NEW-195`/`NEW-196` live pass was being triaged: "you could change the
  llm cores from 4 to 6 which will speed up inference." `utils/
  config.py`'s `MODEL_CONFIG["n_threads"]` changed `4 → 6` — confirmed
  this device has 8 real cores (`nproc` → 8). `THERMAL_CONFIG[
  "original_threads"]` (same file) derives from `MODEL_CONFIG.get(
  "n_threads", 4)` at import time, so `core/thermal.py`'s post-throttle
  restore target moves with this change automatically — no second edit
  needed there. No test in `tests/` pins the old value of 4 (checked via
  grep before editing). Full suite re-run after the change: `671 passed,
  1 skipped` (`tests/`, excluding `tests/test_restoricon_core/`).
- **Not yet measured**: (1) actual inference speedup at 6 threads vs. the
  prior 4 — not benchmarked this round; (2) how much SOONER
  `core/thermal.py`'s 10-minute sustained-inference throttle now fires,
  since more active threads plausibly generates more heat faster — also
  not benchmarked. Both need a live pass before this change can be
  considered validated rather than merely applied.
- **Deliberately NOT live-tested in the same session this was applied,
  and this ordering matters**: `NEW-195` (logged moments before this
  entry) found that the device's live-verify sessions can be
  meaningfully confounded by uncontrolled concurrent phone usage (calls,
  other apps, screen standby). Live-benchmarking a CPU/thermal-sensitive
  change like this one on top of an already-confounded measurement
  environment would produce a SECOND set of numbers with the same
  reliability problem `NEW-195` just surfaced. **Recommended**: fold this
  benchmark into whatever future round re-runs `NEW-195`'s hang/thrashing
  test under controlled conditions (phone not otherwise in use for the
  duration) — that round should capture speedup-at-6-threads and
  time-to-throttle-at-6-threads as part of the same clean session, not as
  a separate live pass.
- **Cross-references:** `NEW-195` (the confound this change was
  deliberately not tested against), `core/thermal.py` (the throttle
  logic whose behavior this change may shift).
- **Status update, 2026-08-26 (clean(er) re-run + real benchmark
  numbers). Split status, per the same one-claim-closes/one-stays-open
  shape as `NEW-180`:**
  - **Speedup axis: directionally confirmed with real numbers, but NOT a
    controlled measurement — stays open.** Real `print_timing` lines from
    `~/.codeyOS/llama-server.log` at `n_threads=6`: interactive run
    (`n_ctx=65536`, cold 4156-token prompt) — prefill 25.86 tok/s, eval
    3.31 tok/s; background-dispatch run (`n_ctx=16384`,
    prefix-cache-assisted) — prefill 31.03/16.65 tok/s, eval 5.45/6.25
    tok/s across two calls. Against M1-E-fix's `n_threads=4` baseline
    (10.63 tok/s prefill, 2.15-2.74 tok/s eval, 2026-08-23): prefill is
    roughly 2.4-2.9x faster, eval roughly 1.2-2.9x faster. **This is NOT
    a clean A/B**: no same-session `n_threads=4` control was captured
    (reverting mid-round was out of scope), the two runs differ in
    `n_ctx` and prefix-cache state, and — most importantly — the prefill
    ratio (2.4-2.9x) is well above what a 1.5x thread increase (4→6)
    should linearly produce; a superlinear jump like that is a sign the
    two baselines aren't comparable (different prompt lengths, cache
    states, or ambient load), not evidence threads alone overdelivered.
    Directionally, more threads plausibly helped — but this data cannot
    stand as validation of a specific speedup factor.
  - **Time-to-throttle axis: NOT measured at all — stays open.** The log
    showed one `⚠ Thermal: Continuous inference for 5.3 min` line,
    short of `core/thermal.py`'s 10-minute threshold, but the daemon
    itself restarted between the background-dispatch and interactive
    phases (PID 31928 → 13586 → 15870), which almost certainly reset
    this counter — neither phase individually sustained inference for
    close to 10 minutes, and nothing in the log shows `_current_threads`
    ever being reduced. No evidence either way on whether `n_threads=6`
    reaches the throttle threshold faster than the old baseline of 4.
  - **Net: `NEW-197` stays OPEN.** Not because the change is suspected
    wrong — 671/1 suite still passes and the directional numbers are
    consistent with a real speedup — but because neither of the two
    things this entry originally flagged as unmeasured (controlled
    speedup, time-to-throttle) has actually been measured yet. A future
    round should capture a same-session `n_threads=4` vs `6` A/B on an
    identical prompt/`n_ctx`, plus a genuine 10+ minute sustained-load
    run without an intervening daemon restart, before this closes.

### [NEW-198] `tools/adb_confound_monitor.py`'s stdout was fully buffered (not line-buffered) when redirected to a file, meaning the monitor's own real-time confound detection silently failed during the exact live-verify round it was built to protect

- **Status: Confirmed, Fixed same round.** Found by the coordinating
  (project-architect) session, not live-verifier, while reviewing this
  round's raw report: the `NEW-195` re-test round redirected the
  monitor's stdout to a file for a background live session, and the file
  stayed empty for the run's full ~22.7-minute duration — Python
  defaults to full buffering (not line buffering) on `sys.stdout` when
  it isn't a TTY. Live-verifier initially read "empty stdout" as "no
  confound detected in real time" and only caught the actual ~19s and
  ~3s foreground-activity flips afterward, by separately inspecting the
  monitor's JSONL log file, which used its own explicit `f.flush()` on
  every write and therefore stayed accurate throughout. This is not a
  theoretical risk: it is the exact mechanism by which this monitor,
  built and reviewed the immediately prior round specifically to protect
  live-verify sessions from false negatives, nearly produced one during
  its very next real use.
- **Reproduction (before/after, both empirically run, not just read):**
  redirected the monitor's stdout to a file and inspected the file's
  content mid-run, before the process exited. Before the fix, the file
  stayed empty until the process exited (or was killed) and its stdio
  buffer flushed on close. After the fix, lines appeared in the file in
  real time, matching the monitor's own polling interval.
- **Fix:** `tools/adb_confound_monitor.py:109-110`, added
  `sys.stdout.reconfigure(line_buffering=True)` and
  `sys.stderr.reconfigure(line_buffering=True)` immediately after
  argument parsing in `main()`, before any output is produced.
- **Verification tier, stated precisely per this project's
  code-complete/reviewer-approved/live-verified distinction:** fixed and
  empirically verified (the before/after redirected-stdout test above),
  full suite re-run clean (671 passed, 1 skipped). **No `code-reviewer`
  subagent pass has been run on this change** — it is a 2-line
  diagnostic-tooling fix with no process-lifecycle, kill-logic, or
  RAM-sensitive content (CLAUDE.md rule 4 does not apply; the monitor
  only reads via `adb shell dumpsys`/`logcat`, spawns nothing, kills
  nothing), so it does not require rule 4's mandatory pass, but it also
  has not had a code-hygiene or general review pass — mark as
  code-complete + empirically verified, not reviewer-approved.
- **Impact if left unfixed:** any future live-verify round relying on
  this monitor's live stdout for real-time confound awareness (as
  opposed to post-hoc JSONL inspection) would silently get a false "no
  confound" signal for the entire session whenever stdout is redirected
  to a file rather than a live TTY — exactly the mode a background
  monitoring process normally runs in.
- **Cross-references:** `NEW-195` (the round this bug was found in the
  middle of; the JSONL-file fallback is what saved that round's
  confound-detection accuracy despite this bug).

### [NEW-199] Piped (non-TTY) stdin does not reliably resolve the shell-command confirmation prompt during a scripted `/exit` — testing-harness limitation, not a claimed production defect

- **Status: Suspected, scoped as a testing-harness constraint only.**
  Found 2026-08-26 during the `NEW-195` re-test round: live-verifier
  scripted a `/exit` via piped (non-TTY) stdin to close out the second
  interactive test session, and it did not resolve the pending
  shell-command confirmation prompt (`Run shell command: 'ping -c 1
  google.com'?`) that the "ping" interpretation had left open.
  Live-verifier's own root-cause guess — that the confirmation gate
  reads via a mechanism that doesn't resolve cleanly from non-TTY piped
  stdin — is explicitly unverified, not diagnosed further this round,
  and is reported here as a hypothesis, not a finding.
- **Why this is scoped as Suspected/harness-only rather than a
  production bug claim:** real interactive users run this product from
  an actual terminal (a TTY), not from a script piping canned input over
  stdin; there is no evidence yet that this affects any real usage path.
  It matters here only because it is a live-verify testing-harness
  constraint worth knowing about for future scripted test sessions —
  teardown in this specific round was still accomplished cleanly via
  direct `kill -TERM` on the tracked PIDs rather than via the piped
  `/exit`, so it did not block or corrupt this round's results.
- **Not investigated further this round** — out of scope for a
  docs-reconciliation pass. A future round that wants to build more
  scripted/automated live-verify tooling should check whether the
  confirmation-prompt read path (`input()` vs. some other read) behaves
  differently under piped stdin before relying on scripted `/exit` to
  close out sessions with a pending confirmation.
- **Cross-references:** `NEW-195` (the round this was found during).

## Found during the lease/registry item's implementation, 2026-08-26 — confirmed by direct read (rule 12), not fixed (a platform constraint, not a code defect)

### [NEW-200] `/proc/net/tcp`/`/proc/net/tcp6` are `PermissionError` for EVERY caller on this device, including reads of the caller's own sockets — `resolve_port_owner_pid()`'s primary path cannot succeed here in production for a truly-unregistered foreign process
- **Status: Confirmed, not fixable within this project's control — a
  device/OS platform constraint, documented rather than worked around
  further.** Confirmed by direct read (CLAUDE.md rule 12 — "never assume,
  read the artifact"), not inferred from `core/embed_server.py`'s
  pre-existing, more tentative comment ("can be unreadable on SOME
  Termux/Android configurations"). Reproduced directly against this real
  device: `open("/proc/net/tcp")` raises `PermissionError: [Errno 13]
  Permission denied` for this project's own Termux process — even a
  process reading about its OWN sockets via `/proc/<own_pid>/net/tcp`
  gets the identical `PermissionError`. This is Android's own per-app
  network-state hardening (SELinux policy denying unprivileged apps read
  access to the global socket table), not something Termux, this
  project's install steps, or root-less configuration can change.
  Cross-checked that `ss`, `netstat`, and `lsof` (all installed via
  `android-tools`/similar packages) fare no better on this device: `ss`
  fails with "Cannot open netlink socket: Permission denied"; `netstat`
  reports "no support for `AF INET (tcp)` on this system" and shows only
  processes it can already identify by other means; `lsof -i` returns
  empty. No available userspace tool on this device can map an arbitrary
  port to its owning PID without root.
- **What IS confirmed readable on this device**: `/proc/<pid>/fd` for any
  same-UID process (verified directly against a real running Termux
  process) — so `_pid_owning_inode()`'s half of the mechanism (given an
  inode number) genuinely works here. The broken half is specifically
  discovering the LISTEN-state inode for a given port in the first place,
  which is what `/proc/net/tcp` was for.
- **Practical consequence for the lease/registry item's own goal
  (`NEW-104`)**: `NEW-104`'s original "true foreign adoption — a resident
  server with no pre-existing resource-gate slot to fall back to" case
  CANNOT be resolved to a real PID on this device via
  `resolve_port_owner_pid()` alone. `core/loader_v2.py`'s new
  `_reconcile_adopted_slot()` and `core/embed_server.py`'s existing
  adoption path both correctly degrade to "leave the gate as blind as
  before" in this specific sub-case (best-effort by design, never
  blocking) — this is NOT a crash or an incorrect-admission bug, but it
  does mean this specific code path is effectively dead weight on THIS
  device today, functioning only as intended portability for a rooted
  device or a non-Android deployment where `/proc/net/tcp` is genuinely
  readable. The two cases that DO work on this device today don't depend
  on this scan at all: (1) a server this process itself registered
  earlier (`find_resident_slot()`, pure resource-gate-store read, no OS
  call), and (2) `embed_server.py`'s own `_find_pid_via_registered_slot()`
  fallback (same pattern, pre-existing).
- **Not fixed — nothing to fix in this project's own code.** The
  `resolve_port_owner_pid()`/`_pid_owning_inode()` implementation is
  correct and safe as written (degrades to `None`, never crashes, never
  falls back to a name-based kill per rule 3) — it is simply unable to
  succeed via its primary path on this specific device for the one case
  it was added to newly cover. Documented directly in
  `resolve_port_owner_pid()`'s own docstring so a future reader doesn't
  have to rediscover this by reading `NEW_ISSUES.md` first.
- **If this ever needs to actually work on this device**: the only
  avenues not yet explored are (a) a rooted device (out of this project's
  scope — Ish's own device, not something to request), or (b) an
  Android-specific API (e.g. `dumpsys` variants, `ConnectivityManager`,
  or similar) that might expose per-app socket ownership through a path
  this project hasn't checked — not investigated this round, flagged as
  a possible future direction only if this specific gap ever becomes
  load-bearing rather than best-effort.
- **Cross-references:** `NEW-104` (the finding this was meant to fully
  close — stays only partially closed, see the lease/registry item's own
  `CODEY_MASTER_PLAN.md` entry for the precise scope), `NEW-146` (embed
  server adoption, which works today via the registered-slot fallback,
  unaffected by this gap), `core/embed_server.py`'s own pre-existing
  comment on `_find_port_occupant_pid()` (which had already flagged this
  as a possibility, now confirmed as fact on this specific device).

## Found during the lease/registry item's mandatory rule-4 code-reviewer pass, 2026-08-26 — all three latent, not currently reachable, logged per rule 8 rather than dropped

### [NEW-201] `find_resident_slot()` + `register_slot()` is a TOCTOU double-registration race — not currently reachable, but the exact anti-pattern `reserve_slot()`'s own docstring already documents avoiding
- **Status: Confirmed as a real latent gap, Suspected as ever-reachable
  in the current codebase — not fixed, logged only.** Both
  `core/loader_v2.py`'s `_reconcile_adopted_slot()` and
  `core/embed_server.py`'s `start()` (adoption branch) call
  `find_resident_slot()` (one lock acquisition, read-only) and, if it
  returns `None`, later call `register_slot()` (a SEPARATE lock
  acquisition) to write a new slot. Two concurrent callers could both see
  `None` from their own `find_resident_slot()` read before either one's
  `register_slot()` write lands, and both then register a slot for the
  same real PID/port — a double-count in `_sum_committed_bytes()`. This
  is the identical read-then-write-not-atomically shape `reserve_slot()`'s
  own docstring (`core/resource_gate.py`, ~line 3201) already documents
  as the anti-pattern its own PENDING-swap-sum logic was written to avoid
  (see `NEW-135`'s fix).
- **Confirmed NOT currently reachable**, by the reviewer, not assumed:
  `loader_v2.py`'s path is gated on `resolve_port_owner_pid()` succeeding,
  which needs `/proc/net/tcp` — confirmed dead on this device (`NEW-200`),
  and `_reconcile_adopted_slot()` has no registered-slot fallback to
  succeed via instead. `embed_server.py`'s `start()` is only ever called
  from the daemon's single `async def _main_loop` — sequential coroutine
  ticks on one thread, not concurrent callers; no other process calls
  `start()` today.
- **Fix direction, if/when this becomes reachable** (a rooted device
  where `resolve_port_owner_pid()` works, or a future second caller of
  `embed_server.start()`): an atomic `register_slot_if_absent()` that does
  the find-then-append inside a SINGLE `_LockedState` acquisition, instead
  of two separate ones with a gap between them.
- **Cross-references:** `NEW-135` (the precedent this gap should have
  matched but doesn't yet), `NEW-200` (why this is currently unreachable
  via the `loader_v2.py` path specifically).

### [NEW-202] `find_resident_slot()` filters on `status == RESIDENT`; `embed_server.py`'s older `_find_pid_via_registered_slot()` fallback does not — a status-filter divergence between two functions answering the same question
- **Status: Confirmed as a real divergence, currently empty/harmless —
  not fixed, logged only.** `find_resident_slot()` (new this round) only
  returns a slot whose `status` is `SLOT_STATUS_RESIDENT`. `core/
  embed_server.py`'s pre-existing `_find_pid_via_registered_slot()`
  filters only on `model_id`+`port`, with no status check at all — a
  PENDING slot for the embed model would satisfy it just as readily as a
  RESIDENT one.
- **Confirmed currently harmless**, by the reviewer: every
  `model_id="embed"` slot-write site in the codebase was grepped, and all
  of them pass `status=SLOT_STATUS_RESIDENT` explicitly — there is no
  live code path today that would leave a PENDING `model_id="embed"` slot
  around for `_find_pid_via_registered_slot()` to wrongly match against.
- **Fix direction, if/when a PENDING embed slot ever becomes possible**:
  add the same `status == SLOT_STATUS_RESIDENT` filter to
  `_find_pid_via_registered_slot()` that `find_resident_slot()` already
  has, so the two functions answering the same underlying question ("is
  a specific model's server really resident") agree.
- **Cross-references:** none — self-contained, found and fully scoped in
  the same review pass.

### [NEW-203] `EmbedServer.stop()`'s docstring asserts an adopted server always has `self.process is None` — a real edge case makes that false, though the resulting behavior stays safe
- **Status: Confirmed as an inaccurate docstring claim; the actual
  runtime behavior in the edge case is still safe — not fixed, logged
  only.** `stop()`'s docstring states an adopted server (`start()`'s new
  adoption branch) always has `self.process is None`, since adoption by
  definition means this object never spawned a `Popen` for it. The
  reviewer traced a real edge case where this is false: if THIS object's
  OWN earlier spawn already died (so `self.process` still holds a stale,
  dead `Popen` handle that hasn't been cleared yet) and adoption of a
  DIFFERENT, healthy occupant then occurs before that stale `self.process`
  gets reset to `None`, the object ends up in a state the docstring didn't
  anticipate: an adopted (not-owned) real server, but a non-`None`
  `self.process` pointing at the object's own dead previous spawn.
- **Why this stays safe despite the inaccurate invariant**: `stop()`'s
  kill logic targets `self.process`'s own PID — in this edge case, that
  PID belongs to the object's own already-dead prior spawn, not the
  really-adopted server, so `stop()` harmlessly no-ops against a PID
  that's already gone (or, worst case, sends a signal to a dead/reaped
  PID that raises `ProcessLookupError`, already handled) rather than
  ever mistakenly killing the real adopted server it doesn't own.
- **Not fixed** — this is a documentation-accuracy issue, not a behavior
  bug; the reviewer's own framing was "the stated invariant is inaccurate
  and should be corrected in a follow-up," not "this needs a code fix."
  Fix direction: clear `self.process = None` explicitly at the point a
  prior spawn is confirmed dead (rather than only inside `stop()`'s own
  cleanup), or correct the docstring's wording to describe the actual
  invariant instead of the intended-but-not-quite-true one.
- **Cross-references:** none — self-contained, found and fully scoped in
  the same review pass.


## Found during the 2026-08-26 Phase A1 "concurrency test" scoping (§6.2 of `CODEY_MASTER_PLAN.md`) — desk-only, vendored llama.cpp source read (`~/llama.cpp` commit `91d2fc38`) + real production log evidence, NO model loaded this round, NOT fixed, logged only

### [NEW-204] `llama-server` has been running every real production launch with 4 concurrent slots (`kv_unified=true`) the whole time — the master plan's "no flag is set anywhere" framing was factually true but its implied conclusion ("concurrency is off/untested") was wrong

- **Status: Confirmed, from both source and real verbatim log output —
  not a hypothesis.** `core/loader_v2.py`'s `_spawn_locked()` (~line 351)
  never passes `-np`/`--parallel`, and neither the repo nor the live shell
  environment sets `LLAMA_ARG_N_PARALLEL` (grepped, both empty). But this
  build's own default for that flag is **not** 1 — `~/llama.cpp/tools/
  server/server.cpp:146-151` resolves the unset/`-1` value to
  `params.n_parallel = 4, params.kv_unified = true` for any non-router
  launch (i.e. every real launch this project makes, since `-m <path>` is
  always passed). This is not just a source-code claim: `~/.codeyOS/
  llama-server.log:20` (the most recent real `codey-start` coder launch,
  2026-08-26) prints `initializing, n_slots = 4, n_ctx_slot = 65536,
  kv_unified = 'true'` verbatim, and every logged embed-server launch in
  `~/.codeyOS/embed-server.log` shows the identical `n_slots = 4, ...
  kv_unified = 'true'` pattern (at `n_ctx_slot = 2048`). Every live-verify
  pass this project has ever run against the real loader has therefore
  been exercising a 4-slot server, not the single-consumer server the
  rest of the documentation assumed.
- **Impact:** this settles the "is `--parallel`/multi-slot serving even
  real and available" half of the Phase A1 concurrency test by code-read
  plus already-existing log evidence, with no new live pass required for
  that half. It does NOT settle the actual open question, which is
  behavioral, not existential — see the plan's Phase A1 concurrency-test
  entry for the reframed remaining ask (an oversubscription test, not a
  bare "does it start" test).
- **Not fixed** — nothing to fix; this is a documentation/framing
  correction (rule 6) plus a live-evidence pointer, not a code defect.
- **Cross-references:** `NEW-205` (the memory-accounting consequence of
  this same default), the master plan's §6.2 Phase A1 "Concurrency test"
  row and Appendix A checklist entry (corrected this round per rule 6).

### [NEW-205] `core/resource_gate.py`'s `QWEN35_4B_ARCH.recurrent_state_bytes` constant assumes 1 sequence slot; real production launches run at `n_parallel=4` today, so every cost estimate since M1-A has undercounted the SSM/recurrent-state term by ~150.75MiB

- **Status: Confirmed by source-tracing the vendored llama.cpp
  allocator, not measured (the measured number is unavailable at this
  project's current log verbosity — see below); the multiplier itself
  (×4, not some other factor) is confirmed exactly, not estimated.**
  `core/resource_gate.py`'s `QWEN35_4B_ARCH.recurrent_state_bytes`
  (~line 1043) is `((4-1) × (4096 + 2×16×128) + 128×4096) × 4 × 24` =
  `52,690,944` bytes — the single-slot figure §5.1 already documents as
  "source-derived, not measured." But `~/llama.cpp/src/llama-model.cpp:
  2137/2156` passes `recurrent_rs_size = max(1, cparams.n_seq_max)` into
  the hybrid-memory constructor as `mem_size`, and `~/llama.cpp/src/
  llama-memory-recurrent.cpp:99-100` allocates `n_rows = mem_size × (1 +
  n_rs_seq)` — i.e. the recurrent-state buffer scales linearly with
  `n_seq_max` (`= n_parallel`, `common.cpp:1594`), not fixed at 1.
  `n_rs_seq` is `params.speculative.need_n_rs_seq()`
  (`common.cpp:1595`), which returns 0 unless a speculative-decoding
  draft model is configured (`common.h:388-394`) — confirmed 0 for this
  project's actual spawn command, since `_spawn_locked()` never passes
  any `--draft`/`--model-draft` flag. Per `NEW-204`, real production
  launches already run at `n_parallel=4` by the binary's own default, so
  the real recurrent-state cost today is `52,690,944 × 4 = 210,763,776`
  bytes (~201.02MiB), not the ~50.25MiB the gate assumes — an existing,
  present-tense undercount of `158,072,832` bytes (~150.75MiB) in every
  cost estimate `estimate_model_load_cost()` has produced since M1-A
  (2026-08-22), including the ones M1-F's `MAX_CONCURRENT_MODEL_BUDGET_
  BYTES` (7.00GiB) and `MAX_SWAP_ASSIST_BYTES` (6.50GiB) derivations
  relied on.
- **Attention/KV term is NOT affected — checked and ruled out, not just
  assumed clean.** `~/llama.cpp/src/llama-context.cpp:286-297`: when
  `kv_unified=true` (today's default, per `NEW-204`), `cparams.n_ctx_seq
  = cparams.n_ctx` — the full-attention KV buffer is sized once by the
  `-c` value regardless of `n_parallel`, not multiplied by slot count.
  §5.1's `32,768 bytes/token × n_ctx` KV table is unaffected by this
  finding.
- **Not measured — could not be closed by log evidence this round.**
  llama.cpp's own `RS buffer size` / `KV self size` log lines
  (`llama-memory-recurrent.cpp:115`, similar in the attention path) are
  emitted via `LLAMA_LOG_INFO`, which `~/llama.cpp/common/log.cpp:441-
  452`'s `common_get_verbosity()` maps to `LOG_LEVEL_TRACE` — a finer
  tier than this project's current spawn verbosity (`verbosity = 3`,
  confirmed from `~/.codeyOS/llama-server.log:10`), so neither existing
  log file contains these lines. Getting the real measured number needs
  a live pass with raised verbosity (`-lv`), which was out of this
  round's desk-only scope.
- **Impact:** ~150.75MiB is a real, already-incurred bite against
  M1-F's calibrated margins — roughly 30% of `MAX_CONCURRENT_MODEL_
  BUDGET_BYTES`'s ~0.505GiB device-ceiling margin and roughly 34% of
  `MAX_SWAP_ASSIST_BYTES`'s ~0.435GiB margin above the interactive
  worst-case required cost (both figures per §5.1's M1-F entry). Neither
  margin is eliminated, but both are meaningfully thinner than currently
  documented once this term is included.
- **Fix direction, not done this round (out of scope by the task's own
  instruction):** make `recurrent_state_bytes` (or its consumer in
  `estimate_model_load_cost()`) scale by the actual `n_parallel` the
  loader's spawn command will produce (today, always 4, since nothing
  overrides the binary's auto-default) instead of hardcoding the
  1-slot figure. Should be measured live (raised verbosity or an RSS
  delta comparison) rather than re-derived by formula a second time,
  per this project's own standing preference for measurement over
  arithmetic once a live pass is available to get it.
- **Cross-references:** `NEW-204` (why `n_parallel=4` is already active
  today, not a hypothetical future setting), `NEW-180` (embed RSS also
  unmeasured — same "small undercount against untested margins"
  category), §5.1's own recurrent-state derivation and M1-F's constant
  derivations in `CODEY_MASTER_PLAN.md`.

## Found during the 2026-08-26 Phase A1 concurrency test (§6.2 of `CODEY_MASTER_PLAN.md`, `NEW-204`/`NEW-205`'s scoped follow-on) — REAL live-verifier pass against the actual `codey-start` full stack, NOT fixed, logged only

### [NEW-206] The real `llama-server`, running its own already-active `n_parallel=4, kv_unified=true` default (`NEW-204`), fails EVERY in-flight request — not gracefully, not by queuing or truncating — when two concurrent requests' combined context oversubscribes the shared KV pool, after a long, expensive fragmentation-driven retry cascade

- **Status: Confirmed, directly observed** — real server logs
  (`~/.codeyOS/llama-server.log`), real raw HTTP responses, real
  `/slots` polls, real `free -h` before/during/after. Not inferred, not
  a mock, not a desk derivation. **Scope deviation disclosed by the
  live-verifier and preserved here rather than hidden:** the test ran
  against `codey-start`'s real binary and code path but with
  `CODEY_N_CTX` overridden to `8192` (a pre-existing, explicitly
  permitted override — precedent `U.31`/`NEW-95`/7.4a), not production's
  actual `65536` ceiling, because reaching oversubscription at 65536
  would need ~40+ minutes of prefill per rung at this device's measured
  prefill rate. **This proves the mechanism exists and fails hard at
  n_ctx=8192 under genuine over-capacity combined demand; it does NOT
  prove the exact failure timing/cascade shape is identical at
  n_ctx=65536, and — more importantly, confirmed by reading the
  allocator source rather than assumed — it does NOT prove the same
  hard failure also triggers below 100% combined capacity (via
  fragmentation) or during generation rather than prefill**, which are
  the shapes that would actually matter for realistic production loads
  well under 65536. See "not proven" below for the full reasoning,
  including why "pool-size-independent" is true of the underlying
  contiguity mechanism but does not mean this test proved the
  consequential (under-capacity) case.
- **Proven, this round:**
  - **Genuine concurrency is real, not serialized** — a smoke test
    before the main test fired two tiny `/completion` calls with
    distinct canary strings; a mid-flight `/slots` poll showed both
    with `"is_processing": true` on two DIFFERENT slots (2 and 3)
    simultaneously. This directly confirms the 4-slot server actually
    interleaves work rather than silently queuing behind the scenes.
  - **Oversubscription fails hard, not gracefully.** Two prompts sized
    via the server's own `/tokenize` endpoint (not estimated) at 4245
    and 4246 tokens (combined 8491 against the 8192-token pool — over
    100% before any generation even started), `n_predict: 300` each,
    fired genuinely concurrently. Real log:
    ```
    init_batch: failed to prepare attention ubatches
    decode: failed to find a memory slot for batch of size 509
    srv decode: failed to find free space in the KV cache, retrying with smaller batch size ...
    (cascading retries: 509 → 256 → 128 → ... → 1, over several minutes)
    srv decode: Context size has been exceeded. off = 207, n_batch = 1, ret = 1
    srv send_error: task id = 28, error: Context size has been exceeded.
    slot release: id 0 | task 28 | stop processing: n_tokens = 4253, truncated = 0
    slot release: id 1 | task 27 | stop processing: n_tokens = 4241, truncated = 0
    srv update_slots: decode() failed: Context size has been exceeded.
    ```
    BOTH raw HTTP responses were `{"error":{"code":500,"message":
    "Context size has been exceeded.","type":"server_error"}}`. Total
    wall time ~6m32s for EACH request; both curls returned within 13ms
    of each other (genuinely simultaneous failure, not one timing out
    after the other). Task 28/slot 0 reached 4253/4253 tokens (100% of
    its own prompt consumed before failing); task 27/slot 1 reached
    3733/4241 (88%). **Neither request produced any partial output —
    both errored before generation began**, so there is no
    truncation-and-continue behavior and no cross-request content
    leakage (there was nothing produced by either to leak).
  - **The failure mechanism is fragmentation-driven, not a simple
    linear sum-exceeds-capacity check.** The server spent over 12
    minutes cascading through shrinking batch-size retries
    (509→256→128→...→1) before giving up entirely and failing BOTH
    in-flight requests — not just the one that nominally pushed the
    pool over, and not with any partial/serialized recovery.
  - **No corruption, no hang, no crash, no deadlock, no RAM pressure.**
    `free -h` stayed flat/stable throughout (~8.1–8.3GiB used, no
    upward trend, no thrashing) — this is a pure llama.cpp
    request-admission/scheduling behavior, not a resource-exhaustion
    symptom.
- **Not proven / explicitly out of scope this round — corrected after
  reading the actual allocator source (`~/llama.cpp/src/llama-kv-
  cache.cpp:894-1084`), not asserted from the log shape alone, per rule
  12:** the test's combined prompt size (8491 tokens) already exceeded
  the pool (8192) before generation started — a genuine, trivial
  over-capacity condition that fails on **any** pool size, since demand
  exceeding total capacity fails regardless of how large that capacity
  is. Reading `find_slot()`'s `cont=true` branch confirms the deeper
  mechanism IS a contiguity requirement, not a simple linear
  sum-check — it walks the cache looking for `n_test` (the full batch
  size, for contiguous/prefill allocation) *contiguous* free cells, and
  returns failure if none exist even when the *total* count of free
  cells elsewhere in the cache would be sufficient (lines 1005-1084).
  This makes the mechanism itself genuinely pool-size-independent in
  principle. **But this test did not actually exercise that
  distinction** — because combined demand already exceeded total
  capacity, this specific run cannot separate "failed because sum
  really was too large" (trivial, same at any pool size, arguably not
  even a distinct finding worth escalating on its own) from "failed
  because free space was fragmented even though the sum would have
  fit" (the real, more consequential production risk that would apply
  to two moderate requests comfortably under 65536's nominal capacity).
  **The 65536 re-run this finding calls for should specifically target
  combined-under-100%-but-fragmented conditions**, not just re-run the
  same over-100% scenario at a bigger pool — that would only re-confirm
  the trivial case. Separately, both test prompts consumed effectively
  100% of their own share on **prefill**, before their `n_predict: 300`
  generation budget was even reached — this test never exercised the
  case of two requests that fit fine at admission and only collide
  later, during generation, which is a distinct failure surface (a
  request could plausibly get partial output before dying, unlike this
  round's all-or-nothing prefill-time failure) and the more realistic
  daemon+TUI shape. Treat "hard, all-in failure exists and is real
  under over-capacity combined demand" as confirmed; treat "the same
  hard failure also happens under FRAGMENTED-but-under-capacity or
  DURING-GENERATION conditions" as the two genuinely open questions a
  65536 re-run needs to target, not "does it reproduce at 65536" in the
  abstract.
- **Confound addressed explicitly, not silently omitted (rule 5):** an
  ADB wakefulness/foreground-activity monitor ran throughout. Two brief
  (~3s each) foreground flips occurred at test-window-relative t+70s and
  t+73s (Messaging app → launcher/recents → back to Termux); Ish
  independently and unprompted confirmed he used the phone briefly
  during the run, corroborating rather than contradicting the ADB
  capture. **This does not implicate the finding.** The actual failure
  (both requests erroring) did not occur until roughly 12+ minutes into
  the test, after the long retry cascade — the retry-cascade log
  timestamps show ~11+ minutes of continued, uninterrupted server
  processing between the t+70-73s blips and the actual failure event.
  A 3-second foreground interruption cannot explain a definitive
  server-side error that manifests 11+ minutes later with no
  intervening gap in server activity. This finding is confound-
  independent and should not be hedged on that account, though the
  confound is recorded here per rule 5's verbatim-record requirement.
- **Impact — this is not a routine resource-gate accounting bug like
  most recent findings (`NEW-135`/`NEW-136`/`NEW-187`/`NEW-205`); it is
  a discovery about `llama.cpp`'s real-world behavior under a condition
  §1.4's single-shared-model architecture decision implicitly assumed
  would work.** §1.4 (2026-08-22) settled "one model serves every role"
  partly on the open question of whether one `llama-server` can
  transparently serve multiple simultaneous consumers (§8 Q3, struck
  through as answered but explicitly noting the concurrency test as the
  remaining unresolved piece). This result shows that, at least at
  n_ctx=8192 under genuine combined-demand-exceeds-total-capacity
  conditions, the answer is: no graceful degradation, no queuing, no
  serialization, no truncation-and-continue — a hard failure of every
  in-flight request after an expensive delay. **What this proves is
  narrower than "concurrency is unsafe in general" — it proves the
  system has no admission control preventing that specific bad outcome
  once combined demand genuinely exceeds the shared pool, and that
  when it does happen, the failure mode is maximally bad (both die,
  after 12 minutes) rather than one request being rejected cleanly up
  front.** Whether the SAME hard-failure behavior also triggers well
  UNDER the nominal capacity (via KV-cache fragmentation, confirmed as
  a real contiguity-based mechanism in `find_slot()`'s source — see
  above) or DURING generation rather than at prefill — the two shapes
  that would actually threaten a plausible real scenario like an
  interactive TUI session and a background daemon task each running a
  moderate-sized prompt well within 65536's combined room — is NOT yet
  tested. That gap, not "does the same number reproduce at 65536," is
  what a follow-up live pass needs to target. Either way, the finding
  already shows the shared-server architecture has no built-in
  admission protection against oversubscription today — an outcome
  that needs either a design response in front of the shared server or
  an explicit accepted-risk decision before the concurrency-test
  checkbox in Appendix A can be considered handled.
- **Not fixed, no code changed this round** — by the live-verifier's own
  scope and rule 1's escalation path; see `CODEY_MASTER_PLAN.md` §8 Q11
  for the options laid out for Ish's decision.
- **Cross-references:** `NEW-204` (confirms `n_parallel=4,
  kv_unified=true` is the real active default this finding was tested
  against), `NEW-205` (the separate, unrelated memory-accounting
  consequence of the same default), §1.4 and §8 Q3 (the architecture
  decision this finding bears on), §6.2's Phase A1 "Concurrency test"
  row and Appendix A checklist entry (updated this round, still
  unchecked).

### [NEW-207] `can_dispatch_task()`'s `interactive_active` refusal is checked only once, at task-claim time — an already-claimed background task can keep running (up to the 1800s task timeout) alongside a human-opened interactive session for the rest of its execution, undermining the check's own stated intent

- **Status: Confirmed, from reading the real control flow, not
  inferred.** `core/resource_gate.py::can_dispatch_task()`'s own
  docstring states its check 1 exists so the daemon "never do[es]
  daemon-initiated background work while a human is watching the
  TUI/GUI." `core/daemon.py::_process_planner_tasks()` (~lines
  1201-1228) calls `self._check_dispatch_gate()` (which evaluates
  `can_dispatch_task()`) exactly once, immediately before
  `try_claim_task()`, and then `await`s the entire task body
  (`asyncio.wait_for(self.executor._execute_task(...), timeout=timeout)`,
  `timeout` defaulting to 1800s) with no re-check of
  `is_interactive_session_active()` anywhere inside that await. A task
  correctly refused admission while a human session is active is
  therefore the only case this gate covers; a task claimed while NO
  interactive session existed keeps running, unmonitored against this
  check, for up to 1800s — if a human opens a TUI/GUI session partway
  through, the background task's own inference calls continue running
  concurrently against the shared server anyway, exactly the situation
  the gate's own docstring says should never happen.
- **Found during:** the 2026-08-26 §8 Q11 concurrency-fix design/
  scoping round (`CODEY_MASTER_PLAN.md` §8 Q11), while enumerating the
  concurrency pairs actually reachable against the real
  `core/daemon.py` control flow, as an input to that design — not a
  new bug search of its own. Logged per rule 8 rather than silently
  fixed or dropped, since it was found outside that round's assigned
  scope (which was to design the admission-check-plus-queue fix for
  `NEW-206`, not to re-harden `can_dispatch_task()`'s own existing
  gate).
- **Relationship to `NEW-206`'s fix:** the §8 Q11 admission-check design
  (once implemented) makes this overlap SAFE — a background task's
  in-flight inference calls would hold a context-budget reservation
  the same as any other caller, so an interactive request racing it
  would correctly queue rather than both dying — but that fix does not
  restore this gate's own stated intent of never running background
  work concurrently with an active interactive session at all. The two
  are complementary, not the same fix: NEW-206's fix prevents the
  crash; this gap is a separate, narrower policy question (should a
  long-running background task actually pause or abort when a human
  opens a session mid-task) that nothing in the §8 Q11 design addresses.
- **Not fixed this round** — found during design work, not itself in
  scope; not queue-level urgent (the §8 Q11 fix removes the actual
  crash risk this gap could otherwise contribute to), but a real,
  confirmed gap against the gate's own documented intent.
- **Cross-references:** `core/resource_gate.py::can_dispatch_task()`
  and its docstring, `core/daemon.py::_process_planner_tasks()`
  (~lines 1178-1237), `NEW-206`/§8 Q11 (the round this was found
  during).

## Found during the mandatory rule-4 code-reviewer pass on §8 Q11's context-budget admission fix, 2026-08-27 — Confirmed, safe-direction (under-admits, never over-admits), not fixed this round

### [NEW-208] `reserve_context_budget()`'s combined-usage sum double-counts every admitted request for its ENTIRE in-flight duration (not just the brief TOCTOU window it was designed to close), quietly reducing how much real concurrency the §8 Q11 fix actually admits
- **Status: Confirmed, directly traced through the actual code, not
  inferred.** `reserve_context_budget()` (`core/resource_gate.py:4293+`)
  sums three figures against the ceiling: (a) the live `/slots`-reported
  occupancy (the authoritative real-occupancy signal), (b) every OTHER
  outstanding reservation in the local ledger, and (c) this request's own
  new estimate. `release_context_budget()` (`core/resource_gate.py:4463+`)
  is only ever called from a `finally` block AFTER the HTTP call it
  guards has fully returned — i.e. after the request's entire
  prompt+generation lifetime, not shortly after admission. For that
  entire lifetime, the SAME request is counted in the sum TWICE: once via
  its still-outstanding local reservation record (b), and once via
  `/slots`' own real `n_prompt_tokens` figure (a), since the server has
  been actively processing it — and therefore visible in `/slots` — for
  as long as it's been running.
- **The function's own docstring reasoning is self-contradicting, not
  just imprecise.** `release_context_budget()`'s docstring
  (`core/resource_gate.py:4470-4481`) argues release-on-HTTP-return is
  correct because "this ledger was never meant to track occupancy for a
  request's whole lifetime — only to close the TOCTOU gap between an
  admission check and that request actually reaching the server" — but
  the actual release timing (on HTTP-return, i.e. after the whole
  lifetime) is exactly what makes the ledger DO hold the reservation for
  the request's whole lifetime, contradicting the stated design intent
  in the same docstring. The header comment above this section
  (`core/resource_gate.py:~3946`, "only job is to close the TOCTOU
  window between one caller's admission...") states the same intent the
  actual release timing doesn't achieve.
- **Not a safety bug — fails in the safe direction.** This causes the
  gate to systematically UNDER-admit relative to real available headroom
  (never over-admit), so it cannot reopen `NEW-206`'s original cascade —
  the worst-case consequence is unnecessary queuing/waiting for requests
  that would have actually fit. But it quietly undercuts the stated
  purpose of pairing (c)'s admission gate with (b)'s queue specifically
  to PRESERVE real concurrency, not fall back to de facto serialization.
  At the documented ~8-9% typical single-request footprint (per §8 Q11's
  own design-round measurement against `_build_draft_prompt()`) and the
  15% `CONTEXT_BUDGET_SAFETY_MARGIN_FRACTION`, this could roughly halve
  the number of genuinely-concurrent requests the gate actually admits
  compared to what the design intends — every admitted in-flight request
  effectively reserves double its own real footprint against the shared
  ceiling for as long as it runs.
- **Not fixed this round** — reviewer's own judgment, endorsed here: a
  code fix is not mandatory before this fix can be considered done,
  since the direction is safe; logging it (this entry) is the required
  action per rule 8, not a code change. Fix direction for a future
  round, if the reduced-concurrency cost turns out to matter in
  practice: release the local reservation once `/slots` first shows the
  request's own footprint reflected in the live poll (rather than
  waiting for the whole HTTP call to return), so the local ledger only
  ever covers the true TOCTOU gap between admission and the request
  first appearing in `/slots` — closer to what both docstrings already
  claim the design does.
- **Cross-references:** `NEW-206` (the finding this fix addresses), §8
  Q11 (the design/decision record and implementation status), `core/
  inference_hybrid.py::ChatCompletionBackend.infer()` and `core/
  plannd.py::get_plan()` (the two call sites whose `finally`-block
  release timing produces this).

## Found during Phase B2 scoping (§6.4 of `CODEY_MASTER_PLAN.md`) — desk-only, read `~/Aigentik-CLI`'s real code/data and `restoricon_core/`'s real schema, did NOT touch `~/Aigentik-CLI`, NOT fixed, logged only

### [NEW-209] `restoricon_core`'s schema has no table for four of the five real data shapes in `~/Aigentik-CLI/data/*.json` — the plan's "migrate data/*.json into the Core's schema" undersells the actual scope

- **Status:** Confirmed (read `restoricon_core/database.py`'s full
  `CREATE TABLE` list and `~/Aigentik-CLI/data/*.json`'s real contents
  directly, per rule 12 — not inferred from the plan's brief description).
- **Mechanism:** the Core's schema (`restoricon_core/database.py`) has
  exactly 12 tables: `users`, `api_tokens`, `customers`, `leads`,
  `opportunities`, `projects`, `estimates`, `contracts`, `documents`,
  `invoices`, `communication_history`, `audit_log`. Aigentik-CLI's local
  store is not one file per shape — grepping every `readFileSync`/
  `writeFileSync` site in the repo (not just `data/`'s current contents)
  finds **ten call-site modules**, two of which write files that don't
  exist on disk yet (`do-not-contact.js` → `data/do-not-contact.json`,
  `queue.js` → `data/pending.json` — both real code paths, just never
  triggered on this device so far): `contacts.js`, `calendar.js`
  (`calendar.json` + `schedule-config.json`), `email-rules.js`,
  `sms-rules.js`, `do-not-contact.js`, `queue.js`,
  `subcontractor-recruiter.js` (`subcontractors.json`),
  `customer-module.js` (`customers.json`), and `index.js`/
  `owner-command.js` (both write `profile.json`, 6 combined call sites).
  `config.paths.conversations_dir` is configured but referenced by zero
  `.js` files — dead config, not an active store. Step 3 of Phase B2
  ("replace local writes with Core API write-through") is scoped
  per-module, not per-file — the five *shapes* below sit under those ten
  modules, not the reverse:
  1. `contacts.json` (200 real records) — a generic rolodex shape
     (name/aliases/phones/emails/relationship/type/trade/license/
     insurance/crew_size/history) with **no clean Core table**: it mixes
     personal contacts and subcontractor-shaped fields in one file, and
     neither `customers` (which requires split `first_name`/`last_name`
     and a constrained `status` enum) nor any subcontractor table (there
     isn't one) fits without translation.
  2. `customers.json` — Aigentik's own lead/customer pipeline, richer
     than Core's `customers`+`leads` combined: it carries
     restoration-specific insurance/claim fields (`insurance_related`,
     `insurance_company`, `claim_number`, `adjuster`, `incident_date`)
     and an `escalation_status`/`dnc_status` pair with **no Core column
     anywhere**.
  3. `subcontractors.json` — qualification/recruitment pipeline data
     (license, insurance, `qualification_status`, `recruitment_step`).
     **The Core schema has no subcontractors table at all** — this is
     Compliance/Procurement domain territory (plan §6.7, Phase B5a),
     not yet built.
  4. `calendar.json` / `schedule-config.json` — appointments and working
     hours. **The Core schema has no appointments/calendar table at
     all** — this is Operations/Calendar-Scheduling (plan §6.5, Phase
     B3), not yet built.
  5. `email-rules.json` / `sms-rules.json` (automation rules),
     `profile.json` (business identity), and the Do-Not-Contact list
     (`do-not-contact.js`'s own store, `data/do-not-contact.json` — a
     genuinely separate store, not merely the `dnc_status` field already
     present on `customers.json` records) — **no Core table for any of
     these three**; rules map conceptually to the not-yet-built
     Automated Workflows (Phase B3), profile has no
     `business_profile`-equivalent table in the current schema at all,
     and DNC has no equivalent list/flag mechanism at the Core level
     either.
  Only `contacts.json` and `customers.json` have any partial overlap
  with existing Core tables (`customers`/`leads`, via
  `crm_service.py::create_customer()`/`create_lead()`), and even that
  overlap requires field-level translation, not a straight import.
- **Impact:** Phase B2's migration step (plan §6.4 step 2) cannot be a
  single generic "load `data/*.json`, write to Core" script. Only
  contacts/customers have a real (translated) destination today;
  subcontractors, calendar/appointments, rules, and profile have none.
  Either B2's scope narrows to contacts+customers only (deferring the
  rest until the relevant Core schema exists in later phases), or B2
  itself must add the missing tables (`subcontractors`, `appointments`,
  `automation_rules`, `business_profile`) before it can claim a full
  migration — this is a real scope decision, not an implementation
  detail, and is called out explicitly in the B2 task list below rather
  than assumed away.
- **Not fixed this round** — desk/design scope only, per this round's
  explicit instruction not to write integration code.
- **Cross-references:** plan §6.4 (Phase B2), §6.5 (Phase B3, Operations/
  calendar), §6.7 (Phase B5a, Compliance/subcontractors),
  `restoricon_core/database.py` (full schema), `restoricon_core/
  services/crm_service.py` (`create_customer`/`create_lead`, the only
  two write paths that currently exist for any of this data).

### [NEW-210] `~/Aigentik-CLI/config.json` (gitignored, untracked) holds live plaintext secrets — Gmail app password and a Vertex AI API key — that must never enter the `Codey-Aigentik` fork's git history

- **Status:** Confirmed (read the real, live `config.json` directly).
- **Mechanism:** `~/Aigentik-CLI/.gitignore` correctly excludes both
  `config.json` and `data/` from git, and `git ls-files` in
  `~/Aigentik-CLI` confirms neither is tracked (`config.json.example` —
  a placeholder — is the only tracked config file, 55 files tracked
  total). A normal `git clone`/fork of `~/Aigentik-CLI`'s existing
  history therefore does **not** carry secrets or business data, which
  is good, but it also means `Codey-Aigentik`'s own eventual working
  copy needs its own `config.json` created fresh (or copied out-of-band,
  never committed) — this is a real step B2's task list must call out
  explicitly, not an outcome of the fork operation itself.
- **Impact:** none yet — this is a "make sure future work doesn't get
  this wrong" finding, not an active leak. Flagged so the follow-up
  implementer round doesn't assume `git clone` alone produces a working
  `Codey-Aigentik` config.
- **Not fixed this round** — nothing to fix; `.gitignore` is already
  correct. Logged per rule 8 as a scope note for the B2 implementation
  round.
- **Cross-references:** plan §6.4 (Phase B2), `~/Aigentik-CLI/.gitignore`,
  `~/Aigentik-CLI/config.json.example`.

### [NEW-211] `~/Aigentik-CLI/config.json`'s local-model port (`llama.host` = `http://127.0.0.1:8080`) is the exact same default port Codey-OS's shared llama-server binds — Phase B2 step 4 ("point at the shared model layer") is a real admission-control fix, not a no-op or a simple config change

- **Status:** Confirmed (read both artifacts directly, per rule 12 — did
  not assume from either project's docs).
- **Mechanism:** `~/Aigentik-CLI/llama.js`'s `chatLocal()` POSTs straight
  to `${config.llama.host}/v1/chat/completions`, and `config.json`'s live
  value is `http://127.0.0.1:8080`. Codey-OS's own primary server port
  (`utils/config.py:15`, `PRIMARY_SERVER_PORT = int(os.environ.get(
  "CODEY_PRIMARY_PORT", "8080"))`) defaults to the identical `8080`. If
  Codey-OS's daemon already has its shared `llama-server` resident on
  `:8080` when Aigentik-CLI (or its `Codey-Aigentik` fork) fires a local
  chat request, `chatLocal()` would silently land on that same real
  server and get a real response — **but entirely outside
  `core/resource_gate.py`'s admission control**: no lease acquired, no
  slot reserved, no participation in the `reserve_context_budget()`/
  `wait_and_reserve_context_budget()` machinery §8 Q11 just built to
  prevent exactly the oversubscription failure mode `NEW-206` found
  (hard failure of concurrent in-flight requests under combined context
  pressure). A same-port collision that happens to "work" today is not
  the same thing as being "pointed at the shared model layer" — it's an
  unmediated bypass of every admission mechanism Phase A1 built.
- **Impact:** Phase B2's plan-language step 4 ("point its model calls at
  the shared model layer, a config change") undersells the real work.
  The correct fix is not editing `config.llama.host` to a different
  value — it's routing Aigentik-CLI's model calls through whatever
  admission-aware surface the Core/A1 exposes (a Core API endpoint that
  itself acquires a lease before proxying to `llama-server`, or an
  equivalent lease-acquisition step Aigentik-CLI's Node process performs
  before calling `:8080` directly), so a real inbound-email/SMS handling
  cycle can't be the concurrent request that reproduces `NEW-206`/
  `NEW-208`'s known failure modes in production. This is called out
  explicitly in the B2 task list rather than left as a "config change."
- **Not fixed this round** — desk/design scope only, per this round's
  explicit instruction not to write integration code.
- **Cross-references:** plan §6.4 (Phase B2 step 4), §8 Q11 (the
  admission-control mechanism this must route through), `NEW-206`/
  `NEW-208` (the failure modes an unmediated port collision could
  reproduce), `~/Aigentik-CLI/llama.js::chatLocal()`, `utils/
  config.py:15` (`PRIMARY_SERVER_PORT`).

## Found during the B2/NEW-209 schema-expansion round (2026-08-27) — building `restoricon_core`'s subcontractors/appointments/automation_rules/business_profile/do_not_contact tables per Ish's decision to expand scope now — code complete + self-tested, NOT yet code-reviewed, NOT committed

### [NEW-212] `customers`/`leads` (and now the five new B2 tables) have no `external_id` column to anchor an idempotent re-run of the future Aigentik-CLI migration script — a real obstacle for B2's data-migration step, not fixed here
- **Status: Confirmed, not fixed — logged only, out of this round's
  scope** (this round's task was schema/models/service/RBAC only, not the
  migration script itself — see plan §6.4 task 3). **Correction, found
  during the mandatory code-reviewer pass, per rule 6:** this entry
  originally claimed all five `NEW-209` tables got an `external_id`
  column — false, confirmed directly against `restoricon_core/database.py`'s
  actual DDL. Only THREE of the five (`subcontractors`, `appointments`,
  `automation_rules`) have an `external_id TEXT UNIQUE` column. The other
  two were a deliberate, defensible design choice, not an oversight:
  `business_profile` is a singleton (no external key needed — there is
  only ever one row), and `do_not_contact` uses its own natural
  idempotency key (`UNIQUE(type, value)`) instead. `customers` and
  `leads` — the two tables Phase B1 already built, which B2's migration
  step 3 will also need to write into (`data/contacts.json`,
  `data/customers.json`) — have no `external_id`-style column at all,
  and unlike `business_profile`/`do_not_contact`, have no natural
  alternative idempotency key either.
- **Impact:** without it, re-running the contacts/customers migration
  script (e.g. after a partial failure, or to pick up new records) will
  either silently duplicate every previously-migrated customer/lead, or
  the migration script will need to do its own fragile match-by-name-and-
  email de-duplication instead of a simple upsert.
- **Suggested direction, not applied**: add `external_id TEXT UNIQUE
  NULLABLE` to `customers` and `leads` before B2's migration script
  (task 3) is written, so all entities the migration touches share the
  same idempotency mechanism.
- **Cross-references:** plan §6.4 (Phase B2 task 3), `restoricon_core/
  database.py` (`customers`/`leads` DDL, and the five new tables' own
  `external_id` columns for comparison).

### [NEW-213] Three of the five new B2 tables create a second, non-authoritative representation of data an existing table already denormalizes onto itself
- **Status: Confirmed, not fixed — logged only, non-blocking; flagged so
  it isn't silently discovered as "duplication" later and assumed to be
  an oversight.**
  - `projects.subcontractors_json` (`database.py`, Phase B1) already
    stores a denormalized list of subcontractor names per project. The
    new `subcontractors` table (this round) is the real per-subcontractor
    record (qualification pipeline, insurance, licensing, etc.) — the two
    are not meant to be the same thing, but nothing currently keeps
    `projects.subcontractors_json`'s names in sync with the
    `subcontractors` table's `company_name`/`id` values. A future round
    should either populate `projects.subcontractors_json` from real
    `subcontractors.id` references or replace it with a join table.
  - `communication_history.channel` already accepts the value
    `'appointment'` (Phase B1). The new `appointments` table (this round)
    is the actual appointment record; a `communication_history` row with
    `channel='appointment'` is presumably meant to log the *event* of an
    appointment being scheduled/confirmed/cancelled, not duplicate the
    appointment's own data — but no code in either direction currently
    creates one from the other.
- **Suggested direction, not applied**: decide, in whichever round wires
  B2's write-through replacement (`calendar.js`/`subcontractor-
  recruiter.js`), whether `communication_history` rows should be emitted
  automatically from `SchedulingService`/`CRMService`'s subcontractor
  methods (mirroring `crm_service.py`'s existing audit-log-on-mutation
  pattern, but for the comms trail instead), and whether
  `projects.subcontractors_json` should be deprecated in favor of a real
  foreign-key relationship.
- **Cross-references:** `restoricon_core/database.py` (`projects.
  subcontractors_json`, `communication_history.channel` CHECK
  constraint, and the new `subcontractors`/`appointments` DDL), plan
  §6.4 (Phase B2 task 4).

### [NEW-214] `ROLE_SALES`/`ROLE_PROJECT_MANAGER` hold `PERM_LOG_COMMUNICATION` but no `PERM_READ_DNC` — the two roles most likely to be about to contact someone can't check `AutomationService.is_blocked()` before doing so
- **Status: FIXED, same round.** Trivial and obviously-correct given the
  finding, so fixed directly rather than deferred: `PERM_READ_DNC` and
  `PERM_READ_AUTOMATION_RULES` added to both `ROLE_SALES`'s and
  `ROLE_PROJECT_MANAGER`'s grants in `restoricon_core/auth.py`'s
  `ROLE_PERMISSIONS`. New regression test added,
  `test_sales_and_project_manager_can_check_is_blocked`
  (`tests/test_restoricon_core/test_operations_services.py`), confirming
  both roles can call `is_blocked()` without a `PermissionError`.
  `tests/test_restoricon_core/`: 38 passed (up from 37).
- **Original finding, found during the mandatory code-reviewer pass on
  the B2 schema-expansion round. `AutomationService.is_blocked()`
  requires `PERM_READ_DNC` before checking whether a contact identifier
  is on the do-not-contact list. `restoricon_core/auth.py`'s
  `ROLE_PERMISSIONS` matrix (this same round's own additions) granted
  `admin`/`manager` the new DNC permissions, but `ROLE_SALES` and
  `ROLE_PROJECT_MANAGER` — the two roles that already held the
  pre-existing `PERM_LOG_COMMUNICATION` from Phase B1, i.e. the roles
  most plausibly about to actually contact a customer or lead — were not
  given `PERM_READ_DNC` in this round's grants.
- **Why this is a real gap and not just an unused permission**: a
  `sales`/`project_manager` actor calling `is_blocked()` before sending
  an outreach would get a `PermissionError` instead of a real answer,
  which — depending on how a future caller handles that exception —
  could either wrongly block a legitimate contact attempt (fails safe)
  or, worse, get caught by a broad `except`/ignored and silently skip
  the DNC check entirely (fails unsafe) if a future caller isn't written
  carefully. Neither outcome is what a day-one-or-never compliance
  control (per this project's own framing of the Communication History
  and DNC list) should do.
- **Not currently live-exploitable** — same "one caller away" shape as
  `NEW-189`/`NEW-194`: `is_blocked()` has no caller anywhere yet, and
  `restoricon_core/api/` (the HTTP layer) was not touched this round, so
  none of this round's new services are reachable outside direct Python
  calls (e.g. from tests). The gap is real but dormant until B2's
  write-through-replacement step (task 4, wiring `Codey-Aigentik`'s own
  `calendar.js`/outreach code to call the Core) gives it a live caller.
- **Not fixed this round** — logging only, per rule 8, exactly the
  category this finding itself is about (a permission-matrix gap found
  by reading, before it became reachable, rather than after).
- **Fix direction**: add `PERM_READ_DNC` (and likely `PERM_READ_
  AUTOMATION_RULES`, for the same "about to act on communication rules"
  reasoning) to `ROLE_SALES`/`ROLE_PROJECT_MANAGER`'s grants in
  `ROLE_PERMISSIONS`, before B2's task 4 gives `is_blocked()` a real
  caller.
- **Cross-references:** `NEW-189`/`NEW-194` (the same "gap found before
  a live caller exists" shape from Phase B1's own review), `restoricon_
  core/auth.py`'s `ROLE_PERMISSIONS` matrix, `restoricon_core/services/
  automation_service.py::is_blocked()`.

### [NEW-215] `~/Aigentik-CLI/data/contacts.json` is not customer/lead data — it's an Android-contacts phonebook sync with no destination table in `restoricon_core`
- **Status: Confirmed** — read directly, not assumed (rule 12).
  `contacts.json` (201 real records as of 2026-08-27) has fields `id,
  name, aliases, phones, emails, address, relationship, type, notes,
  instructions, reply_behavior, business_name, trade, ..., source,
  first_seen, last_contact, contact_count, history`; every record's
  `source` field reads `"android_contacts"`, and its `type` field takes
  values `person` (199), `subcontractor` (1), `unknown` (1) — not
  `customer`/`lead`. It's the general phonebook `contacts.js` uses to
  identify inbound callers/texters and cross-reference
  `contact_id`/`contact_external_id` on other records (subcontractors,
  appointments), not a CRM customer source. `restoricon_core` has no
  table modeling this shape today (not `customers`, not any of the five
  B2 tables).
- **Impact:** the originally-assumed "contacts.json → `crm_service`"
  migration mapping (per the round's kickoff framing) is wrong. A
  migration script cannot write `contacts.json` into `customers` without
  fabricating fields that aren't there (first_name/last_name split,
  customer_type, status) and, worse, would misrepresent 199 phonebook
  entries with `type: "person"` as CRM customers.
- **Not fixed here** — this round is scoping only, per rule 8.
- **Suggested direction, not applied**: either (a) treat `contacts.json`
  as out of scope for the CRM migration entirely (it's an
  identification/lookup table, not business data Restoricon Core needs
  to own), or (b) if Ish wants it preserved, define a new `contacts`
  table matching its real shape as its own migration task, separate from
  the customer/subcontractor/appointment migration. Needs an explicit
  scope decision from Ish before any migration script touches this file.
- **Cross-references:** plan §6.4 (Phase B2 task 3), `~/Aigentik-CLI/
  contacts.js`, `restoricon_core/models.py` (no `Contact` dataclass
  exists).

### [NEW-216] `~/Aigentik-CLI/data/schedule-config.json` (business scheduling defaults) has no destination table in `restoricon_core`
- **Status: Confirmed** — read directly. Top-level shape is
  `working_hours, default_duration_minutes, buffer_minutes,
  booking_window_days, duration_by_relationship` — a singleton
  configuration object, structurally similar to `profile.json` →
  `business_profile`, but there is no equivalent table for it. It isn't
  appointment data itself (that's `calendar.json` → `appointments`,
  already covered) — it's the *rules* Aigentik-CLI's scheduler uses to
  decide what slots to offer.
- **Impact:** this file would be silently dropped by a migration script
  that only handles the five files with existing table destinations,
  losing the actual scheduling policy (working hours, buffer, booking
  window) with no record of it in Restoricon Core.
- **Not fixed here** — logged per rule 8 rather than improvising a
  schema addition.
- **Suggested direction, not applied**: add a `scheduling_config`
  singleton table (same `id INTEGER PRIMARY KEY CHECK(id = 1)` pattern
  as `business_profile`) in a future schema-expansion round, once Ish
  confirms this data is in scope for B2.
- **Cross-references:** plan §6.4 (Phase B2 task 3), `restoricon_core/
  database.py` (`business_profile` DDL for the singleton-table pattern
  to reuse), `~/Aigentik-CLI/data/schedule-config.json`.

### [NEW-217] `subcontractors`/`appointments`/`automation_rules` services have `create_*` (INSERT-only) but no lookup-by-`external_id` method, so a second migration run would hit `sqlite3.IntegrityError` on the `UNIQUE(external_id)` constraint instead of upserting or skipping
- **Status: Confirmed**, and in-scope work for the migration-script task
  about to be spec'd (not deferred to the ledger) — noted here per rule
  8 for visibility since it was found during this round's read, but the
  fix (adding `get_subcontractor_by_external_id` /
  `get_appointment_by_external_id` / `get_rule_by_external_id`, or
  equivalent, to the three service modules) is being handed to
  implementer as part of the migration task itself, not left open.
  `upsert_business_profile` (`automation_service.py:217`) and
  `add_to_do_not_contact` (`automation_service.py:285`) are already
  idempotent by design and don't need this.
- **Cross-references:** `restoricon_core/services/crm_service.py`
  (`create_subcontractor`, no `external_id` lookup),
  `restoricon_core/services/scheduling_service.py`
  (`create_appointment`, same gap), `restoricon_core/services/
  automation_service.py` (`create_rule`, same gap),
  `restoricon_core/database.py` lines 252-253/309/343 (the
  `UNIQUE` constraints that make the second run fail hard today).
- **Update, Phase B2 task 2, 2026-08-27:** closed. `get_subcontractor_by_
  external_id` (`crm_service.py`), `get_appointment_by_external_id`
  (`scheduling_service.py`), and `get_automation_rule_by_external_id`
  (`automation_service.py`) were added and are used by
  `restoricon_core/migrate_aigentik.py`'s skip-if-exists idempotency
  check.

## Found during Phase B2 task 2 migration-script implementation, 2026-08-27

### [NEW-218] `create_subcontractor`/`create_appointment`/`create_rule` unconditionally overwrite `created_at`/`updated_at` with the current timestamp, discarding any caller-supplied value
- **Status: Confirmed** — read directly. All three methods do
  `now = utc_now_iso(); obj.created_at = now; obj.updated_at = now`
  before the `INSERT`, then bind `now, now` for the two timestamp
  columns regardless of what was set on the passed-in dataclass
  instance. `create_user`/`create_customer`/etc. follow the same
  pattern elsewhere in the codebase, so this isn't unique to the three
  new services — it's the established convention for every `create_*`
  method in `restoricon_core`.
- **Impact on this round's migration script
  (`restoricon_core/migrate_aigentik.py`):** real historical timestamps
  from Aigentik-CLI's source JSON (e.g. `email-rules.json`'s
  `2026-02-22T03:07:55.570Z` for an email rule created six months before
  this migration ran) end up as the migration's own run timestamp for
  `created_at`/`updated_at` instead. **Corrected mechanism (per
  code-reviewer, 2026-08-27):** this isn't the service layer discarding
  a caller-supplied value — `migrate_aigentik.py`'s own
  `map_subcontractor`/`map_appointment`/`map_rule` functions never read
  `rec.get("created_at")` from the source JSON at all (grepped, zero
  occurrences), so no historical value ever reaches `create_*` to be
  discarded. A full fix needs two changes, not one: the mapper functions
  would need to read and pass through the source timestamp, *and* the
  three `create_*` methods would need an override parameter to accept
  it instead of always stamping `now`. Other timestamp-bearing fields
  that live in their own dedicated columns (`last_contact_at`,
  `next_followup_at`, `setup_date`) are unaffected and do carry the real
  source values through correctly — only the two columns every table
  shares are clobbered.
- **Not fixed here** — fixing it means changing the signatures/bodies of
  three (or, given the pattern is universal, potentially every)
  `create_*` service method to accept and preserve an explicit
  `created_at`/`updated_at` when the caller supplies one, which is a
  service-layer behavior change well beyond this task's scope (a
  migration script consuming the existing services as-is). Documented
  as a known, accepted limitation in `migrate_aigentik.py`'s own module
  docstring.
- **Suggested direction, not applied**: (1) add an optional
  `created_at`/`updated_at` override parameter (or accept them only when
  already set non-default on the passed dataclass) to the affected
  `create_*` methods, and (2) update `migrate_aigentik.py`'s mapper
  functions to actually read the source JSON's timestamp field and pass
  it through — both changes are needed together, scoped and reviewed as
  their own small task before any future migration round that needs
  historically-accurate timestamps preserved.
- **Cross-references:** `restoricon_core/services/crm_service.py`
  (`create_subcontractor`), `restoricon_core/services/
  scheduling_service.py` (`create_appointment`), `restoricon_core/
  services/automation_service.py` (`create_rule`), `restoricon_core/
  migrate_aigentik.py` (module docstring's "Known limitations" section).

## Found during Phase B2 task 4a route-wiring scoping, 2026-08-27

### [NEW-219] `automation_service.py` has no single get-rule-by-id method — a new write-only route
- **Status: Confirmed** — read directly. The service exposes
  `create_rule`, `list_rules`, `get_automation_rule_by_external_id`
  (internal-only, keyed on Aigentik's string id, not the Core's integer
  `id`), and `record_rule_match(rule_id, actor)`. There is no
  `get_rule(rule_id, actor)`. Task 4a's spec (§6.4) wires
  `POST /api/v1/automation-rules/{id}/match`, which means an HTTP caller
  can mutate a rule by integer id but has no route to read that same
  rule back by id afterward (only `list_rules`, unfiltered by id) — the
  same "write-only routes" class `NEW-193` already names, just found in
  a new module.
- **Not fixed here** — task 4a's scope is wiring routes to the CRUD
  surface the service already exposes, not adding new service methods.
  Adding `get_rule(rule_id, actor)` to `AutomationService` plus a
  `GET /api/v1/automation-rules/{id}` route is a small, self-contained
  follow-up, cheap to do whenever `NEW-193`'s broader write-only-routes
  cleanup happens (or sooner, standalone).
- **Cross-reference:** `restoricon_core/services/automation_service.py`,
  `CODEY_MASTER_PLAN.md` §6.4 task 4a route table.

### [NEW-220] `is_blocked`/`remove_from_do_not_contact` cannot distinguish "not on the list" from "malformed identifier" over HTTP
- **Status: Confirmed, safety-relevant** — read directly.
  `is_blocked(identifier, actor)` and
  `remove_from_do_not_contact(identifier, actor)` both call
  `classify_identifier(identifier)` first and return bare `False` if it
  returns `None` (i.e. the identifier didn't parse as an email or phone
  number) — the exact same `False` they'd return for a validly-formed
  identifier that legitimately isn't on the do-not-contact list. An HTTP
  caller (the planned `GET /api/v1/do-not-contact/check` and
  `POST /api/v1/do-not-contact/remove` routes, §6.4 task 4a) has no way
  to tell "this contact is safe to reach out to" from "this input never
  got checked because it was malformed" — on a suppression list that
  gap is a false-negative risk, not just an API-ergonomics one.
- **Not fixed here** — fixing it at the route layer would mean
  duplicating `classify_identifier()`'s parsing logic in `routes.py` to
  detect the malformed case before calling the service method, which
  this task's scope (route wiring only, no service-layer logic
  duplication) explicitly excludes. The clean fix is in the service
  layer: change `is_blocked`/`remove_from_do_not_contact` to raise
  `ValueError` (already handled globally as 400 by `routes.py`) instead
  of returning `False` when `classify_identifier` fails — its own small,
  reviewable task.
- **Cross-reference:** `restoricon_core/services/automation_service.py`
  (`classify_identifier`, `is_blocked`, `remove_from_do_not_contact`).

### [NEW-221] `Model(**json_body)` raises uncaught `TypeError` on unrecognized JSON keys, falling through to 500 instead of 400
- **Status: Confirmed, pre-existing** — read directly. All eight of
  `routes.py`'s current POST routes construct a dataclass directly from
  the parsed request body (e.g. `Customer(**json_body)`,
  `Contract(**json_body)`). Python raises `TypeError` for either an
  unexpected keyword or a missing required positional field, and
  `handle_request`'s `except` chain only catches `PermissionError` and
  `ValueError` as 4xx — `TypeError` falls to the generic
  `except Exception` branch and returns 500 with an internal error
  string, misrepresenting a client input error as a server fault. Not
  new — true of every existing POST route before this round — but task
  4a's five new POST routes (`subcontractors`, `appointments`,
  `automation-rules`, `business-profile`, `do-not-contact`) will inherit
  the same pattern by matching established convention, so it is being
  logged now rather than silently carried forward unnoted.
- **Not fixed here** — fixing it means either catching `TypeError`
  alongside `ValueError` in `handle_request`'s except chain (simplest,
  but risks masking a genuine internal `TypeError` bug as a 400) or
  validating each dataclass's fields before construction (more correct,
  more code, one change per resource) — a real design decision that
  affects all thirteen POST routes at once, not a one-line fix scoped to
  task 4a alone.
- **Cross-reference:** `restoricon_core/api/routes.py`
  (`handle_request`'s `except PermissionError` / `except ValueError` /
  `except Exception` chain).

### [NEW-222] `GET /api/v1/subcontractors/{id}/qualification` falls through to the generic by-id handler and returns 400 instead of 404
- **Status: Confirmed, pre-existing, found during code-reviewer's pass
  on task 4a's routes** — read directly. `routes.py` only defines a
  `POST .../{id}/qualification` route (line ~275); there is no matching
  `GET` route for that path. Because the generic
  `if path.startswith("/api/v1/subcontractors/") and method == "GET":`
  branch (line ~286) matches on prefix alone, a `GET` to
  `/api/v1/subcontractors/{id}/qualification` falls into it instead of
  404ing as "no such route." That branch then does
  `sub_id = int(path.split("/")[-1])`, which tries to parse the literal
  string `"qualification"` as an integer, raises `ValueError`, and
  `handle_request`'s exception chain turns that into a 400
  ("bad request") rather than the more accurate 404 ("no such
  endpoint/resource"). Not introduced by task 4a — the same
  prefix-matching pattern is used for `appointments/{id}/status` too and
  would misbehave identically on `GET .../{id}/status`.
- **Not fixed here** — task 4a's scope was wiring the routes in the spec
  table (§6.4), not hardening the generic by-id handler's path matching.
  A real fix would tighten the by-id branch's match condition (e.g.
  reject paths with more than one segment after the collection name, or
  check the trailing segment is purely numeric before attempting
  `int()`) — small, but touches routing logic shared by every
  by-id GET across the router, so it deserves its own scoped pass rather
  than a one-line patch buried in this round.
- **Cross-reference:** `restoricon_core/api/routes.py` (subcontractors
  `GET .../{id}` generic branch, and the analogous `appointments`
  `GET .../{id}` branch which has the same shape).

### [NEW-223] Task 4a review's "838 passed" figure came from an
unscoped `pytest` invocation picking up `ccos/tests/`, not a real
discrepancy in what's passing
- **Status: Confirmed, root-caused, resolved same-day, process note
  only — no code defect.** Ish flagged the code-reviewer's cited "838
  passed" figure (task 4a review) as inconsistent with the 770 figure
  this project's convention (`python -m pytest tests/ -q`) produces and
  the number that actually landed in `PROJECT_LOG.md`/
  `CODEY_MASTER_PLAN.md` for this round. Verified directly: `python -m
  pytest tests/ --collect-only -q` → 771 collected (770 passed, 1
  skipped); `python -m pytest ccos/tests/ --collect-only -q` → 68
  collected; running bare `pytest --collect-only -q` from the repo root
  (no path argument, picks up both `tests/` and `ccos/tests/`) → 839
  collected. 771 + 68 = 839, one off from the reviewer's cited 838 —
  consistent with a transient single-test collection difference (e.g. a
  skip/xfail counted differently), not a hidden divergent number.
- **Cause**: the reviewer's re-run of the suite used a bare `pytest`
  invocation instead of this project's established `python -m pytest
  tests/ -q` (CCOS's suite is intentionally kept separate — see the repo
  structure notes in `CLAUDE.md`), so it silently included `ccos/tests/`
  as well. No committed doc ended up with the wider/wrong number — the
  finalize round independently re-ran the correct scoped command and
  recorded 770 verbatim — so nothing needs correcting in
  `PROJECT_LOG.md`/`CODEY_MASTER_PLAN.md`.
- **Action**: none required beyond this record. Noting here so a future
  round doesn't mistake a scope difference for a regression or a
  fabricated number if it resurfaces.
- **Cross-reference:** `PROJECT_LOG.md`'s task-4a entry (has the correct
  770/1 figure, unaffected).

## Found during Phase B2 task 4 (write-through pilot module selection) scoping, 2026-08-27 — desk-only, read `~/Aigentik-CLI`'s real code, `restoricon_core/services/crm_service.py`, `restoricon_core/models.py`, and `restoricon_core/database.py` directly per rule 12; not fixed, logged only

### [NEW-224] `subcontractor-recruiter.js`'s `updateSubcontractor()` has no
Core-side destination — it is not a viable first write-through pilot
as-is
- **Status: Confirmed.** `crm_service.py` exposes exactly four
  subcontractor operations: `create_subcontractor`, `get_subcontractor`,
  `get_subcontractor_by_external_id`, `list_subcontractors` (filters:
  `qualification_status`, `primary_trade` only), and
  `update_subcontractor_qualification` (sets `qualification_status`
  +optionally `recruitment_step` only). There is no general
  partial-update method or route. `subcontractor-recruiter.js`'s
  `updateSubcontractor(id, updates)` is called from `index.js` (twice,
  merging LLM-extracted fields like `company_name`, `primary_trade`,
  `years_in_business`, `license_number`, insurance flags, and
  `qualification_data` deltas mid-SMS-conversation) and from
  `owner-command.js` (status-only updates, which *would* map to
  `update_subcontractor_qualification`, but the module's other call
  sites don't). Task 4a (`c30d755`'s route round) explicitly declined to
  add by-external-id/general-update routes as "an unrequested feature"
  since no caller needed them yet — task 4 (write-through) is that
  caller, so that decision needs revisiting when subcontractors' turn in
  the write-through sequence comes up.
- **Action**: not fixed here. Consequence for this round: subcontractors
  is deferred as the pilot module; `do-not-contact.js` was selected
  instead (see `CODEY_MASTER_PLAN.md` §6.4's updated task 4 entry) — its
  4 functions map 1:1 onto the 4 already-shipped do-not-contact routes
  with no general-update need. When subcontractors' write-through is
  scoped later, this finding is the blocker to resolve first: either add
  a general `update_subcontractor(id, **fields)` service method + PATCH-
  style route (mandatory code-reviewer pass, rule 4's "or security"
  clause), or have the JS caller compose only the specific fields each
  existing route supports and drop the free-form merge semantics
  (behavior change, needs Ish's sign-off since it changes what the live
  recruiting conversation can record).
- **Cross-reference:** `CODEY_MASTER_PLAN.md` §6.4 task 4 (write-through
  replacement, per-module list); `restoricon_core/services/crm_service.py`
  lines 940-1123; `~/Aigentik-CLI/subcontractor-recruiter.js` (lines with
  `updateSubcontractor(` calls in `index.js`/`owner-command.js`).

### [NEW-225] `restoricon_core`'s Core API has never been started against
a real persistent DB or received a real network call from any external
process
- **Status: Confirmed, not a defect — a verification-tier fact worth
  recording explicitly.** `restoricon_core/database.py`'s
  `DEFAULT_DB_PATH` (`~/.codey_restoricon/core.db`) does not exist on
  disk; no `restoricon_core/api/server.py` process was found in `ps aux`
  at scoping time. All existing test coverage (`tests/
  test_restoricon_core/test_api.py`) uses a `:memory:` DB and a real
  `ThreadingHTTPServer` bound to a free port within the same test
  process — a real HTTP roundtrip, but never against the production DB
  path, never with a second, separate OS process (like a Node.js CLI)
  as the caller.
- **Action**: none required as a fix; this is context for whoever
  live-verifies the do-not-contact write-through pilot (task 4, first
  slice) — that verification will be the first time the Core API is
  started against its real DB path and called from outside the Python
  test process, which is a meaningfully bigger step than "another unit
  test passed" and should be recorded as such rather than folded into
  ordinary code-reviewer sign-off.
- **Cross-reference:** `CODEY_MASTER_PLAN.md` §6.4 task 4's pilot spec;
  `restoricon_core/database.py:16`; `restoricon_core/api/server.py`
  (`DEFAULT_PORT = 8770`, confirms `NEW-211`'s `:8080` collision finding
  is unrelated to this port).
- **Update, 2026-08-27, after the do-not-contact.js pilot round —
  partly discharged, not closed.** `tools/provision_ai_agent_auth.py`
  (new this round) has now actually connected to
  `~/.codey_restoricon/core.db` at its real, default path and created
  the schema + one real `ai_agent`-role user + token in it — the "does
  not exist on disk" half of this finding no longer holds; verified via
  `ls -la ~/.codey_restoricon/` showing a real `core.db` file. But the
  second half still holds exactly as written: `ps aux` still shows no
  `restoricon_core/api/server.py` process, and every HTTP test the
  do-not-contact pilot's implementer/reviewer ran (18 new + 122 full
  suite in `~/Codey-Aigentik`) went through a separate locally-started
  scratch/`:memory:` Core server, not the real DB path. The Core API
  server has still never served a request against its real persistent
  DB from an external process. Leave open; will close only once a
  server process bound to the real DB path actually answers a real
  external request (the still-pending production cutover, Ish's call).

## Found during Phase B2 task 4 (write-through pilot) implementation, 2026-08-27 — implementer's own report, confirmed by project-architect; not fixed, logged only

### [NEW-226] Three `~/Codey-Aigentik` doc files still describe
do-not-contact as a local JSON file — stale after this round's
write-through change
- **Status: Confirmed.** `docs/architecture.md:148`, `docs/commands.md:87`,
  and `docs/data-files.md:18` (all in `~/Codey-Aigentik`) describe
  do-not-contact as stored in `data/do-not-contact.json`. As of this
  round's write-through pilot, `do-not-contact.js` no longer reads or
  writes any local file — it calls the Restoricon Core API exclusively
  (Core-only, no local fallback, by design). These three doc lines are
  now factually wrong.
- **Action:** none taken this round — doc staleness only, no code or
  behavior affected. Fix is a small, low-risk doc edit whenever
  `~/Codey-Aigentik`'s docs next get a pass; no code-reviewer needed
  (docs-only change).
- **Cross-reference:** `CODEY_MASTER_PLAN.md` §4's Phase B2 task 4 pilot
  entry; `~/Codey-Aigentik/do-not-contact.js` (this round's diff).

### [NEW-227] `tools/provision_ai_agent_auth.py` accumulates tokens on
repeated reruns — no revocation step
- **Status: Confirmed, low severity, already self-documented.** The
  script's own docstring states it plainly: "Idempotent: re-running with
  the same `--username` reuses the existing user and issues it a new
  token (old tokens for that user are left valid/expiring on their own
  schedule — this script does not revoke anything)." Each rerun against
  the same `--username` therefore leaves behind one more live,
  never-revoked bearer token for the `ai_agent` user, with no cleanup
  path.
- **Action:** none taken this round — logged per rule 8 since it's a
  real loose end even though it's disclosed, not hidden, behavior. A
  future pass could add a `--revoke-existing` flag or a token-expiry
  policy in `restoricon_core/auth.py`, but that's new scope, not a bug
  fix, and wasn't part of this round's pilot task.
- **Cross-reference:** `tools/provision_ai_agent_auth.py` (docstring and
  `provision()`); `restoricon_core/auth.py::AuthService.create_token`.

(The third item scoped for this round — whether `NEW-225`'s status
needed updating now that the Core DB exists — is handled as an update
appended directly to `NEW-225` itself above, not as a new numbered
finding, since it's a status change to an existing entry rather than a
new fact.)
