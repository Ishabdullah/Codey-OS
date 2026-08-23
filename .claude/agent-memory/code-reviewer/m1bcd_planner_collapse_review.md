---
name: m1bcd-planner-collapse-review
description: M1-B/C/D (config repoint, --jinja/--reasoning-format spawn flags, planner-server collapse) — CHANGES REQUESTED on M1-D only, closes §4.4's 3-item debt
metadata:
  type: project
---

Reviewed the combined M1-B (utils/config.py repoint to Qwen3.5-4B,
QWEN_MMAP/QWEN_MLOCK rename)/M1-C (`--jinja --reasoning-format deepseek`
added to `core/loader_v2.py:_spawn_locked()`'s cmd list)/M1-D (planner
server collapse: `core/planner_loader.py` deleted, ~9 files + `codeydOS`
touched) diff.

**Verdict: M1-B APPROVED. M1-C APPROVED. M1-D CHANGES REQUESTED** (one
required fix, below) **— otherwise clean.** Both live suite runs
independently reproduced verbatim: `tests/` → 645 passed, 1 skipped;
`ccos/tests` → 68 passed — exact match to the round's own claim, not just
"tests pass."

**The one required fix — `core/lora_import.py:swap_to_finetuned_model()`,
"primary" branch (~line 330-345).** The "secondary" branch (383-395)
mutates BOTH `cfg.MODEL_PATH` and `cfg.PLANNER_MODEL_PATH` together (and
rolls both back together on failure) — its own new comment asserts this
"kept in sync" invariant now that both roles share one physical server.
But the "primary" branch only mutates `cfg.MODEL_PATH`, never touching
`cfg.PLANNER_MODEL_PATH`. Net effect: a "primary" swap leaves
`PLANNER_MODEL_PATH` pointing at the old file while `MODEL_PATH` points at
the new one — the two names silently diverge, exactly the failure mode
the brief asked to rule out. Real consequence, not just bookkeeping:
`import_lora_adapter()`'s "secondary" branch later reads
`cfg.PLANNER_MODEL_PATH` as `base_model` for an on-device LoRA merge — a
stale value means merging onto the wrong base file. Zero test coverage on
this module (`tests/` has no `test_lora*` file at all) means nothing would
catch this. Fix: mirror the secondary branch — set/rollback both config
names together in the primary branch too.

**§4.4's 3-item debt, this review's actual job — all three closed:**

1. **7.4b sub-task A** (`EmbedServer.is_healthy()` +
   `core/inference.py:_start_server()`) — **APPROVED.** Traced the call
   site: `if not _embed.is_healthy(): _embed.start()` correctly guards
   against NEW-144's kill-and-replace bug (`start()`'s own "already
   running" fast path only recognizes `self.process`, blind to a
   different-process-owned healthy server). `is_healthy()` is a real
   stateless `/health` HTTP GET — not a self-referential PID/file check,
   no race-with-self risk. The `except Exception: pass` around the whole
   block is justified and documented (embed is optional, BM25 fallback
   remains).
2. **NEW-152 fix** (`_ever_spawned`/`was_ever_spawned()` in
   `core/loader_v2.py`, consumed by `core/daemon.py`'s
   `_watchdog_check_model()`) — already reviewed and approved in a prior
   session (see [[new152_ever_spawned_narrowing_approved]]). Re-grepped
   both files: the flag/method are still present, byte-for-byte in the
   same shape, untouched by this round's diff. Confirmed clean, nothing
   new to re-review.
3. **`a030bbf` (M1-A) confirmatory sign-off** — **APPROVED, and now
   written down** (the log had REJECT→fix→re-review-corrections but never
   a final verdict line, exactly as flagged). Independently re-derived
   `recurrent_state_bytes = ((4-1)*(4096+2*16*128) + 128*4096) * 4 * 24 =
   52,690,944` by reading the actual llama.cpp source at the pinned
   commit (`~/llama.cpp`, `91d2fc387529940230555abd297a8b5e99737d3f`):
   `llama-hparams.cpp`'s `n_embd_r()` (conv term,
   `(d_conv-1)*(d_inner+2*n_group*d_state)`) + `n_embd_s()` (state term,
   `ssm_d_state*ssm_d_inner` for the Mamba-shaped branch) together give the
   per-layer bytes, and `llama-model.cpp:2153-2155` confirms
   `recurrent_type_k`/`recurrent_type_v` are `GGML_TYPE_F32` (4 bytes).
   Independently computed value matched the committed constant exactly —
   this is the strongest verification in this whole review because it's a
   from-source re-derivation, not a re-read of the same claim.

**Resolved the one thing that could have flipped M1-C's verdict —
`enable_thinking`'s actual default, read from the real GGUF template, not
assumed.** Dumped `tokenizer.chat_template` from
`~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf` directly (`pip
install gguf`, `gguf.GGUFReader`). The generation-prompt tail reads:
```
{%- if enable_thinking is defined and enable_thinking is true %}
    {{- '<think>\n' }}
{%- else %}
    {{- '<think>\n\n</think>\n\n' }}
{%- endif %}
```
i.e. **thinking is OFF by default** — when `enable_thinking` isn't passed
in `chat_template_kwargs`, the template inserts an already-closed, empty
`<think></think>` block into the prompt itself, so the model generates
answer content directly with no reasoning trace at all. This means
`core/inference.py`'s streaming coder path, `core/summarizer.py`'s
`_call_05b` (max_tokens=160), and the orchestrator's `recursive_infer`
fallback — none of which set `enable_thinking` — are NOT at risk of a
thinking trace eating their token budget or leaking into
`inference.py`'s SSE delta parser (which reads `delta.content` only
anyway, belt-and-suspenders). Only `core/plannd.py:get_plan()` explicitly
sets `chat_template_kwargs: {"enable_thinking": true}`, and it correctly
reads `message.content` only (verified against the actual diff, not the
implementer's claim) with no `reasoning_content` fallback. **Lesson for
future Qwen3.5/hybrid-template reviews: don't assume a `--reasoning-format`
server flag implies thinking mode is active — the chat template's own
`enable_thinking is defined` check is the actual on/off switch, and it's
one `gguf.GGUFReader` dump away from being read directly instead of
inferred from `--help` text or family resemblance (rule 12).**

**Confirmed, not just accepted: no `--parallel`/`-np` flag in
`_spawn_locked()`'s cmd list** — llama-server runs single-slot by
default, so the three roles now sharing port 8080 (coder streaming,
plannd's thinking-mode planning request, summarizer's micro-summary)
genuinely serialize/queue rather than running concurrently the way the
old two-server (8080+8081) design did. Not a bug — no corruption risk,
requests are independent HTTP round-trips — but a real behavior change
worth naming explicitly per the brief's item (c), since a background
plan/summarize request can now head-of-line-block behind an in-flight
interactive coding generation.

**Confirmed clean via independent grep, not the implementer's count
alone:** all three `pkill -9 -f "llama-server.*8081"` sites in `codeydOS`
are gone (only `8080`-pattern pkills remain); `register_slot(model_id=
'planner')` and its paired `_release_plannd_slot()` release are both
deleted together (no register-without-release leak introduced); no live
`.py` import of `core.planner_loader`/`PLANND_SERVER_PORT`/
`get_planner_loader`/`get_planner_n_ctx` survives anywhere in the repo
(only comments/docstrings citing the old names for history — checked file
by file, not just a repo-wide count).

**Findings logged, not blocking:**
- **Warning (rule 11 — should be escalated, not filed away):**
  `install.sh` is untouched and still downloads/verifies the retired
  Qwen2.5-Coder-7B + 1.5B files under the old `~/models/qwen2.5-coder-7b/`
  paths — it never creates, downloads, or verifies
  `~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf`, the path
  `utils/config.py`'s `MODEL_PATH` now hardcodes as its default. This is
  not pre-existing staleness the diff merely didn't touch — before M1-B,
  `MODEL_PATH`'s default pointed at a file `install.sh` actually produced;
  after this diff it doesn't. **This diff creates the fresh-clone break**,
  squarely inside rule 11's "in the same task" mandate, even though the
  round's own docs pre-frame it as deferred debt. Doesn't block approval
  of the reviewed files' correctness; does block the round being closed
  as complete.
- Suggestion: any device that ran `codeydOS start` before this upgrade
  may have a persisted `model_id="planner"`/`status=RESIDENT` slot in the
  on-disk resource_gate state store with no code left that specifically
  targets it for release — `total_reserved_bytes()` already excludes
  RESIDENT so admission math isn't inflated (per
  [[resource_gate_new97_plannd_registration_approved]]), and a dead-PID
  reap on any future `reserve_slot(reap_dead=True)` call would clear it
  eventually, but it's not actively closed. Not reproduced on this
  device (`list_slots(reap_dead=False)` returned `[]`) — a live-side
  migration note, not a code defect.
- Suggestion: `gui/index.html`'s static `roleLabel` map (`{agent: '7B',
  planner: '0.5B', embed: 'EMB'}`) and `DEFAULT_MODELS` initial state
  (`Qwen2.5-Coder-7B`/`Qwen2.5-0.5B`) are stale labels, cosmetic only,
  overwritten by real server data once the first status message arrives
  — pre-existing, not introduced or worsened by this round's actual
  `gui/server.py`/`gui/index.html` port-8081 fixes (which are correct and
  complete — independently grepped for any other 8081/planner-port
  reference, found none live).

See also [[m1a_qwen35_hybrid_arch_ssm_underestimate]] (the arithmetic this
sign-off closes) and [[new152_ever_spawned_narrowing_approved]] (the fix
re-confirmed unchanged here).
