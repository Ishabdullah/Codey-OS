# Handoff to Codex — 2026-10-08

**This is a one-time, dated snapshot, not a maintained document.** Its job
is to get a fresh agent (Codex, or any non-Claude tool) oriented fast. The
project's actual source of truth is the three ledgers below — read them,
don't trust this file's details once they drift. Delete this file once
you've read it and started working; don't keep it updated.

## Read these first, in this order

1. **`CODEY_OS_MASTER_BLUEPRINT.md` §1 (executive summary) then §21** —
   the current work register and the dependency-ordered roadmap. This is
   the authoritative "what's next" document as of this session. A 2026-10-06
   census verified current-state architecture against source; §21 is what
   to work from for anything that census touched.
2. **`CLAUDE.md`** — the project's non-negotiable rules (RAM discipline,
   no name-pattern kills, mandatory code-review on process-lifecycle
   changes, rule-8 "log everything found, never silently fix or drop,"
   rule-12 "never assume, read the artifact"). Read it fully before
   touching anything — several of this session's near-misses were exactly
   the failure modes these rules exist to prevent.
3. **`PROJECT_LOG.md`** — reverse-chronological round record. Read the top
   few entries for what just happened; the newest entry at the top names
   what's next.
4. **`NEW_ISSUES.md`** — append-only findings ledger (`NEW-###` IDs).
   Authoritative for any individual finding's status. Tail of the file =
   most recent findings.
5. **`CODEY_MASTER_PLAN.md`** — older authoritative-rules-and-history doc.
   Partially superseded by the blueprint for anything the census touched;
   still correct for project history/rules not covered there.

`AGENTS.md` is a short pointer file at the same material, written for
non-Claude agents generally — worth a glance, but it's stale (predates the
2026-10-06 blueprint/census work) and doesn't mention
`CODEY_OS_MASTER_BLUEPRINT.md` yet. Treat this handoff and the blueprint as
more current than `AGENTS.md` until someone updates it.

## Exact state as of this commit

Last commits on `main`: `c5c62c1` (ledgers) then `aa39770` (code) — WP2.1
slice 5. **Note: `fd5c1ed` ("docs: rewrite README from current
implementation audit") landed after that, from a different session/agent
("Qwen Code" per git config) — not reviewed or authored by this session.
Another agent may be concurrently active on this repo; run `git status
--short` and `git log --oneline -10` before assuming the tree matches this
snapshot, and see CLAUDE.md's "Working alongside another agent" section
before writing to any of the three tracking docs.**

**P0 and P1 (CODEY_OS_MASTER_BLUEPRINT.md §21) are fully closed.** This
session worked through WP1.1–WP1.7a sequentially, then moved into P2.

**P2 / WP2.1 (the Action Gateway) is in progress, slices 1-5 done:**
- `core/action_gateway.py` — new module, three authority classes
  (`READ`/`ACT`/`HIGH_IMPACT`). Ish's finalized policy: `HIGH_IMPACT` with
  no confirmation path available fails closed (refuses + audits, never
  falls through). `allow_self_modification=True` also counts as a
  confirmation path (a fix mid-session after a real regression was caught).
- Gated so far: `core/preferences.py`'s CODEY.md write (slice 1), shell
  exec via `tools/shell_tools.py` (slice 2), the model's
  `write_file`/`patch_file`/`append_file` tools (slice 3),
  `tool_peer_delegate` (slice 4), `run_agent()`'s natural-language
  peer-delegation dispatch (slice 5).
- **Full DoD is far from met.** Of ~42 known write-primitive files, only 3
  are gated. Entire categories remain untouched: CCOS capability
  invocation (deliberately deferred — low real traffic), git writes,
  outbound HTTP, DB writes, message/email sends, `note_save`/
  `note_forget`, device actions.

**Strongest next-slice candidate, already scoped by evidence (not yet
implemented): `NEW-848` (Confirmed, High).** `core/peer_cli.py`'s
`execute_parked_escalation()` (~line 502-539) is a peer-dispatch call site
with **no confirmation guard of any kind** — unlike `escalate()`, which
already has one and is correctly left alone. The project-architect's own
assessment: this may be a bigger gap than anything slices 4-5 already
closed. The established pattern to follow (see `core/agent.py`'s
`tool_peer_delegate` and the `run_agent()` gate for exact shape): classify
as `HIGH_IMPACT`, call the existing `ActionGateway.gate_exec()` with
`confirm_available=False`, same mandatory code-review gate.

Other open findings worth knowing about before touching peer-delegation
code again: `NEW-849` (a fourth unguarded dispatch, `main.py`'s `/peer`
slash command, lower priority — interactive only), `NEW-847` (a privacy
prompt that now fires for a guaranteed-no-op dispatch — a real UX
regression, not yet fixed), `NEW-844`/`NEW-837` (an audit-outcome
ambiguity in `gate_exec` when post-dispatch bookkeeping fails after a real
execution — latent, not yet reachable in production).

## Process this session used — worth continuing, not just the code state

This session used a strict hub-and-spoke pattern for every change: a
scoping pass (reading the actual live code, never trusting blueprint prose
without checking — the blueprint was found stale on exact mechanisms
*multiple* times this session) → implementation → **mandatory adversarial
review before any commit** touching process control, security, or
concurrency → ledger updates (blueprint status line + `PROJECT_LOG.md`
entry + any `NEW-###` findings) → commit code and ledgers as **separate**
commits. Whatever tool/agent picks this up next should keep that shape —
it caught several real regressions this session before they shipped:

- A missing `--depth 1` flag that would have hung indefinitely on a
  shallow git clone (found by literally reproducing the failure, not
  re-reading a diff).
- A policy conflict where the new gateway silently broke the documented
  `--allow-self-mod` flag whenever combined with `--yolo` (found via live
  reproduction against the real repo).
- A false claim in a code comment about daemon-reachability that
  contradicted the actual control flow one line away.
- Two cases where a test accidentally triggered a *real* side effect
  against this actual repo (a real git commit via the self-modification
  checkpoint mechanism; a real model load via a recursion path that
  bypasses the usual mock point) — both self-caught, correctly undone, and
  logged as gotchas for future test authors (`NEW-842`, `NEW-851`).

**Two rules that mattered repeatedly and are easy to skip by accident:**
- Before writing to `CODEY_OS_MASTER_BLUEPRINT.md`/`NEW_ISSUES.md`/
  `PROJECT_LOG.md`, run `git status --short` immediately before saving —
  another agent may have written to the same file since you last read it.
- Never `git add -A`/`git commit -a`. Stage exact file paths.
- This device has ~10.8GB RAM and has crashed from concurrent model loads.
  `free -h` before any live model-load test; one load cycle at a time;
  never kill a process by bare name pattern — track and kill the specific
  PID your own code spawned.

## If you're not sure what to do next

Fix `NEW-848` using the exact pattern already established in
`core/agent.py` (`tool_peer_delegate`'s gate, slice 4) and
`core/action_gateway.py` (`gate_exec`). Then keep working down `CODEY_OS_MASTER_BLUEPRINT.md`
§21's roadmap in order, logging and fixing adjacent small findings as they
come up rather than letting them pile into an unmanaged backlog — that's
been the explicit standing instruction for this entire session.
