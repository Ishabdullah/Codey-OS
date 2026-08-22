---
name: m1a-qwen35-hybrid-arch-ssm-underestimate
description: M1-A (core/resource_gate.py learns Qwen3.5-4B's hybrid 8/24 split) — CHANGES REQUESTED on the SSM recurrent_state_bytes constant, which under-estimates 2.05x vs llama.cpp source read on-device
metadata:
  type: project
---

M1-A added `QWEN35_4B_ARCH` (n_layers=32, n_attention_layers=8,
head_dim=256, recurrent_state_bytes), pointed both roles at it, and
added a 4th `CostEstimate.recurrent_state_bytes` term.

**The single most useful discovery of this review: llama.cpp source is
on this device at `~/llama.cpp` (commit 91d2fc38, 2026-07-20), and
`gguf-py/gguf/scripts/gguf_dump.py --no-tensors <file>` works from
there.** Any future claim about KV-cache shape, recurrent-state size,
layer filtering, or cache dtype is directly checkable — rule 12 applies
with no excuse. Key locations:
- `src/models/qwen35.cpp:21-26` — `is_recr_impl[i] = (i+1) %
  full_attention_interval != 0`, so 32 layers / interval 4 → 8 attention
  layers (i=3,7,...,31). Confirms the 8/24 split from source.
- `src/llama-model.cpp:2115-2122` — qwen35 uses `llama_memory_hybrid`
  with `filter_attn = il < n_layer() && !is_recr(il)`, i.e. KV cache
  allocated for the 8 attention layers only.
- `src/llama-model.cpp:2153-2155` — `recurrent_type_k/v = GGML_TYPE_F32`
  (4 bytes), NOT fp16.
- `src/llama-hparams.cpp:183-221` — `n_embd_r() = (d_conv-1) *
  (ssm_d_inner + 2*ssm_n_group*ssm_d_state)`; `n_embd_s() = ssm_d_state
  * ssm_d_inner`. The `2*n_group*d_state` half of the conv term is easy
  to miss.
- `src/llama-memory-recurrent.cpp:100-101` — r/s are 2-D tensors of
  `n_rows = max(1, n_seq_max)`, per filtered layer → the per-slot caveat
  in the code comment is correct.

**Numbers (recompute if any of this is touched):** corrected recurrent
state = `((4-1)*(4096+2*16*128) + 128*4096) * 4 * 24` = 52,690,944
(50.25MiB); the shipped constant is 25,755,648 (24.56MiB) — 2.05x low,
two independent errors (dropped `ssm.group_count=16`, and 2 bytes
instead of 4). Corrected totals: 32768 → 4,135,806,112 (3.852GiB);
65536 → 5,209,547,936 (4.852GiB, x1.25 = 6.065GiB, still under the
~6.49GiB ceiling, so Ish's §8 Q1 answer of 65536 survives the
correction). KV term itself is exactly right: 32,768 bytes/token.

**Verified clean and re-usable as precedent:** all 5 `ModelArch(` call
sites keyword-only (mid-dataclass field insertion safe); `CostEstimate`
has exactly one construction site and every consumer reads
`.total_bytes` (lines 1756-1878) — no hand-rolled 3-term sum anywhere
in the repo; `n_attention_layers if ... is not None else n_layers`
probed live with `n_attention_layers=0` → returns 0, `or` was not used.
Negative control: flipping the 8 to 32 fails
`test_qwen35_4b_hybrid_kv_uses_8_attention_layers_not_32` and
`test_qwen35_4b_total_cost_reconciles_with_master_plan_table`.
Suite claims matched literally: 200 passed (two files), 739 passed /
1 skipped repo-wide.

**Two secondary findings worth remembering as a bug class:**
1. *Coverage collapse from pointing two roles at one object.* Both
   `"primary"` and `"planner"` now resolve to the same `QWEN35_4B_ARCH`
   instance, so every `is`-identity and expected-KV assertion that used
   to discriminate the two roles is now unfalsifiable. Only
   `tests/test_new84_stale_model_path.py:248`'s `kv_cache_bytes != 0`
   still catches a dropped `"planner"` key. Watch for this whenever a
   one-model consolidation lands.
2. *Sequenced-migration interim window.* M1-A alone re-points the arch
   while `utils/config.py` (M1-B) still stats the 7B, so between the two
   commits the gate under-estimates the 7B's KV by 805,306,368 bytes
   (768MiB; ~1.0GiB at the x1.25 factor). Fenced only by §6.2's "do this
   before anything loads" prose. When reviewing any multi-commit
   migration in this project, compute the cost of the intermediate state
   explicitly.

See also [[resource_gate_74a_subtaskC1_round3_fixture_pid_fix_approved]]
and [[u31_codey_n_ctx_override_changes_requested]].

**Round 2 (2026-08-22) — C-1 FIXED and independently re-verified; still
CHANGES REQUESTED, doc-only.** The corrected constant
`((4-1)*(4096 + 2*16*128) + 128*4096) * 4 * 24` = 52,690,944 is right;
totals 4,135,806,112 / 3.852GiB at 32768, 4.852 / 6.065GiB at 65536,
4.815GiB at 32768 x1.25 all reproduce to the digit. All four cited source
lines check out (hparams 204 exact; 220 is the Mamba-branch comment above
the 221 return; model 2153-2155 contains both `GGML_TYPE_F32` args;
memrec 100-101 are the r/s tensor allocations).

**New verification lesson — check the branch, not just the line.**
`n_embd_r()`/`n_embd_s()` each have an EARLIER `n_embd_head_kda != 0`
(Kimi-KDA) branch that returns a *different* conv term (`3*(d_conv-1)*
d_inner` = 36,864, 1.5x the Mamba term) while `n_embd_s` coincidentally
returns the same 524,288. A citation to the Mamba `return` line is only
correct if the model doesn't take the earlier branch. Verified:
`n_embd_head_kda` is set only by `src/models/kimi-linear.cpp`, so qwen35
takes the Mamba path. Also confirmed no `nextn` key in the GGUF → 
n_layer_all=32 → filter_attn=8 / filter_recr=24 exactly.
`n_rs_seq` (in `n_rows = mem_size * (1 + n_rs_seq)`) defaults to 0 and
has no `common/` CLI plumbing, so the per-slot caveat as written is
correct.

**Blocking finding round 2 (5th occurrence of the same pattern):**
`CODEY_MASTER_PLAN.md`'s "Stale constants, do not use without
re-deriving" list still asserted `KNOWN_MODEL_ARCHS` maps `"primary"` →
`QWEN25_7B_ARCH` / `"planner"` → `QWEN25_1_5B_ARCH` as current state, and
called it "the single highest-risk line item in the migration" — in the
same diff that performs that repoint. Same class as sub-tasks C/D/F.
The other two bullets in that list are legitimately still stale (M1-F).

**Rule-5 record errors worth remembering as a class:** a
verification claim can be captured from a *pre-final* version of the file
it audits. PROJECT_LOG's "every `ModelArch(` call ... four, lines 951,
955, 1044, 1052" was written before the retired-models comment block was
inserted: there are five sites (959/963/1015/1071/1079), all four cited
lines land on comment text, and the missing fifth is the new
`QWEN35_4B_ARCH` — the only site passing the new fields. Same drift hit
the W-1 line refs (off 6-9 lines; and `:270` is the `["primary"]`
assertion, which a planner-fallthrough can't reach — the drained one is
`:279`). Always re-resolve file:line claims against the final file.

Negative controls both reproduced via a pytest `-p` plugin that
`dataclasses.replace()`s the arch and re-points both `KNOWN_MODEL_ARCHS`
entries (no source edit needed, since the reviewer can't edit files):
n_attention_layers 8→32 → 2 failed / 189 passed; recurrent_state_bytes →
the old 25,755,648 → 1 failed / 190 passed. Suite claims re-run
literally: 200 passed; 739 passed, 1 skipped, 68 warnings in 135.33s.

**Round 3 (2026-08-22) — APPROVED.** All four doc findings fixed; code
and both test files byte-identical to the certified round-2 blobs
(verified by `git hash-object`: 6cba8b8 / 2d5ae34 / 5c0e21d, matching the
`index` lines of the round-2 diff — a cheap, exact way to certify
"untouched" without re-reading, better than mtime, which burned a prior
round). C-2's stale bullet is now struck-through + CLOSED with the
still-live M1-F bullets explicitly distinguished.

**Lesson on my own precision:** my W-5 correction handed over *pairs*
(225/228, 246/249, 253/254), but only the planner half of each pair is
actually drained. The implementer copied them faithfully, so the log now
says "five assertions" while listing seven refs. Drained set is 228, 249,
254, 279 + new84:247. When correcting someone's line refs, hand back the
exact set the claim covers, not the surrounding context lines.
