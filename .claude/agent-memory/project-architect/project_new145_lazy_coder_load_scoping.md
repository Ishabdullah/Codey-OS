---
name: project_new145_lazy_coder_load_scoping
description: NEW-145 (coder eager-preload race shrinking interactive context) scoped 2026-08-11 — fix spans TWO daemon.py call sites, not one; not yet implemented
metadata:
  type: project
---

Ish's 2026-08-11 decision: remove `core/daemon.py`'s eager coder (7B)
preload entirely; only the embed model stays always-resident (7.4b
sub-task A). Coder loads lazily on first real request, accepting
~11-16s first-load latency as a known cost.

Scoping (not implementation) landed in TODO.md's 7.4b sub-task C
section and NEW_ISSUES.md's NEW-145 entry. Two call sites needed, not
one — deleting only `_preload_primary_model()` (the call Ish named)
narrows NEW-145's exposure window but does not close it:

1. `core/daemon.py:_main_loop()` — delete the
   `self._preload_primary_model()` call and the now-dead method itself
   (~824-895); tests in `tests/test_daemon_model_watchdog.py:250-362`
   go with it.
2. `core/daemon.py:_watchdog_check_model()` (30s tick) — calls
   `loader.ensure_model()` UNCONDITIONALLY every tick, with no
   "was loaded and died" vs. "never loaded, nobody asked" distinction.
   Left alone, this reproduces NEW-145's exact failure shape on the
   MORE common already-running-daemon path (`codey-start` skips daemon
   startup when one's already up — the normal steady state). Fix: new
   `ModelLoader._ever_loaded`/`was_ever_loaded()` signal, set at
   `load_primary()`'s existing `self._loaded = True` convergence point
   (~line 779) — this single point already covers BOTH a genuine spawn
   and the port-in-use ADOPTION branch, so "ever loaded" means "ever
   loaded or adopted," not "this loader spawned it." Watchdog gates on
   it before calling `ensure_model()` at all.

**Why:** this is the kind of interaction a stronger reviewer (advisor)
caught twice in this same round — first the watchdog call site itself
(missed on first pass, since Ish's decision text named only the
preload method), then a further-order effect (per-process
`_ever_loaded` state meaning the daemon's OWN loader rarely does a
"genuine" spawn under normal `codey-start` use — it usually adopts the
TUI's server — so the flag has to be set at the adoption point too, or
crash-restart coverage for TUI-spawned coders silently regresses).

**How to apply:** before scoping any daemon-lifecycle fix as "add one
new check at the named call site," grep for ALL callers of the same
underlying method (`ensure_model()`/`load_primary()` here) — a fix
scoped only against the call site the user named is easy to leave
incomplete when a second, less obvious call site (a periodic watchdog,
here) has the same effect through a different trigger. Also flagged
NEW-149 (Confirmed, separate, not this round's job): even after both
call sites are fixed, whichever caller spawns the coder server first
still wins the context size for that server's whole life
(`LlamaServer.start()`'s port-in-use reuse branch,
`core/loader_v2.py:211-230`) — "NEW-145 resolved" must not be read as
"decision 3 fully realized" in every ordering.

Status: scoped only, NOT implemented. Mandatory `code-reviewer` AND
`live-verifier` passes required (CLAUDE.md rule 4) — real
daemon-startup and daemon-watchdog process-lifecycle change.
