# Antigravity — read `CLAUDE.md`

**This project's ground rules live in one file: [`CLAUDE.md`](CLAUDE.md).
Read it. Everything in it applies to you unchanged.**

This file used to be a full parallel copy of those rules. It differed
from `CLAUDE.md` by 29 diff lines out of ~15.8KB — every one of them a
name substitution, a heading level, or the wording of rule 10's
mechanism — while carrying a standing obligation to keep two ~16KB files
byte-consistent by hand. That obligation was the drift risk, not a
design. Collapsed 2026-09-02 by Ish's decision (`U.38` step 5; see
`NEW-289` for the measurement).

## The only tool-specific differences

1. **Rule 10 (check before creating a subagent).** `CLAUDE.md` states the
   policy tool-neutrally. Your mechanism is `define_subagent`: check
   whether an already-defined agent fits the job before defining a new
   one. Claude Code's is listing `.claude/agents/`. Same rule, same
   reason — subagent sprawl makes the pipeline harder to reason about.
2. **The coordinator in the hub-and-spoke pipeline is you** wherever
   `CLAUDE.md` says "Claude / the coordinator." The pipeline itself —
   architect scopes → implementer builds → **code-reviewer approves
   before every commit** → live-verifier confirms on-device — is
   identical and has no shortcuts for small-looking changes.
3. **`LIVE_TEST_QUEUE.md`** holds model-load steps deferred for Ish to
   run himself. Not run live by you either.

Nothing else differs. If you find something in `CLAUDE.md` that genuinely
cannot apply to you, that is a doc bug — say so and get it fixed
tool-neutrally, don't fork the rules again.
