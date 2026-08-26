---
name: project-concurrency-test-scoped-new204-205
description: Phase A1 concurrency test scoped 2026-08-26 — mechanism already active in production by default, not a feasibility question; recurrent-state accounting undercount found
metadata:
  type: project
---

2026-08-26: scoped Phase A1's last unstarted item, the "concurrency
test" (`CODEY_MASTER_PLAN.md` §6.2/Appendix A). Desk-only round, no code
touched, per explicit task scope.

**Headline finding, corrects the plan's own prior framing (rule 6):**
"no `--parallel` flag is set anywhere" was true but the implied
conclusion ("concurrency untested/unavailable") was wrong. This
project's vendored llama.cpp (`~/llama.cpp`, commit `91d2fc38`) resolves
the unset `-np`/`--parallel` default to `n_parallel=4, kv_unified=true`
for every real launch (`tools/server/server.cpp:146-151`). Confirmed not
just in source but in real, already-existing production logs —
`~/.codeyOS/llama-server.log:20` and every entry in `~/.codeyOS/
embed-server.log` print `n_slots = 4, ... kv_unified = 'true'` verbatim.
Every live-verify pass this project has ever run has silently already
been exercising a 4-slot server.

Memory-cost tracing through the actual allocator source (not the
`--help` text, not assumption): full-attention KV term does NOT scale
with slot count under `kv_unified=true` (`llama-context.cpp:286-297`,
`n_ctx_seq = n_ctx`, one shared pool). SSM/recurrent state DOES scale
with `n_seq_max` (`llama-model.cpp:2137/2156`,
`llama-memory-recurrent.cpp:99-100`) — at the already-active
`n_parallel=4`, `core/resource_gate.py`'s `recurrent_state_bytes`
constant undercounts by ~150.75MiB (logged `NEW-205`, Confirmed, not
fixed — out of this round's scope).

The genuinely open question was reframed from existential ("does this
work") to behavioral: `kv_unified=true` means the server is 4:1
oversubscribed on *capacity* (each slot advertises full `n_ctx`, but they
share one pool sized by that same `n_ctx`). Nobody has tested what
happens when concurrent requests' combined usage approaches/exceeds that
shared budget. Live-verifier test scoped precisely (2+ concurrent
requests approaching/exceeding 65536 combined tokens, `/slots` +
server-log + `free -h` evidence) but not run this round.

**Why this is worth remembering:** a real, already-active binary default
(`-1` → `4`) had gone unnoticed through many live-verify rounds because
nobody grepped the existing logs for `n_slots`/`kv_unified` — the
answer was sitting in `~/.codeyOS/llama-server.log` the whole time. When
scoping a "does X work" question about a vendored binary, check its own
logs from the last real run before assuming a live test is needed —
rule 12 (read the artifact) applies to log files, not just headers/help
text.

**Advisor course-correction mid-round:** first pass assumed `n_rs_seq=0`
without reading it (rule-12 violation caught before writing docs) and
initially planned to check log files for measured buffer-size lines
without realizing those log at a `LOG_LEVEL_TRACE` tier this project's
current spawn verbosity (`verbosity=3`) filters out. Confirmed `n_rs_seq`
via code (0, since no speculative-decoding flags are ever passed) before
committing the 4x multiplier to the docs. Related: [[feedback_verify_never_assume]].

Next round: live-verifier pass on the oversubscription test described
above (`NEW-204`/`NEW-205`'s cross-referenced plan row has the exact
scoping). `NEW-205`'s fix (scale `recurrent_state_bytes` by actual
`n_parallel`, ideally via a live measurement rather than a second
formula) is separately queued, not bundled with the live pass.
