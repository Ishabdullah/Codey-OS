---
name: resource-gate-subtask3-daemon-watchdog-outcome-plumbing-approved
description: 7.4 sub-task 3 (daemon.py watchdog/preload/shutdown outcome-aware logging via loader_v2.py LOAD_OUTCOME_* constants) — reviewed and approved, with one doc-accuracy correction required before commit
metadata:
  type: project
---

Reviewed core/daemon.py + core/loader_v2.py + tests/test_daemon_model_watchdog.py
(new) + tests/test_loader_resource_gate.py additions for TODO.md 7.4 sub-task 3
(closes [[resource_gate_subtask2_leak_fix_round2_approved]]'s scope — this is the
daemon-side consumer of that gate-aware loader).

**Approved.** Traced every `return` in `load_primary()`/`ensure_model()` by hand
(not just reading the diff) and confirmed every return point tags
`_last_ensure_outcome`/`_last_ensure_reason` itself — the implementer's claimed
"no stale value from a prior call" fix for SWAP_GUARD-deferred/eviction-failed
paths (which never reach `load_primary()`) holds up. Grepped all 4 existing
callers (core/inference.py, core/inference_v2.py, main.py, core/lora_import.py)
and confirmed none read the new getters — return-type-unchanged claim holds.
Full suite: 453 passed, 1 skipped, 68 warnings in 132.37s (real output, not
paraphrased).

**One doc-accuracy finding (Warning, not blocking):** NEW-88 in NEW_ISSUES.md
claims `core/embed_server.py`'s "own watchdog" has a bare `except Exception:
pass`. False as written — there is no watchdog function inside embed_server.py
itself. The actual bare except:pass is in **core/daemon.py**'s main loop
(the inline "Embed server watchdog" block, ~10 lines after the code this
sub-task fixed), which calls into embed_server.py's public API
(`get_embed_server()`/`start_embed_server()`). Same pattern as
[[new10_sigterm_handler_new40_mischaracterization]] — a plausible-sounding
claim about *which file* contains a bug turns out wrong on direct inspection.
**Lesson: when a finding names a specific file for a bug, verify the bug is
actually IN that file, not just reachable from it or adjacent to code that
was touched in that file.** grep for the actual `except`/`pass` before
trusting a "found in file X" claim.

Second, lower-severity finding: pre-existing (not introduced by this diff)
fail-open swallow in `ensure_model()`'s thermal-restart block — if
`self.unload()` throws there, the outer `except Exception: pass` swallows it
and falls through to tag `LOAD_OUTCOME_ALREADY_LOADED`/return True, which
could now assert "fine" in a case where unload() partially executed. Not
introduced by this diff, but the new outcome-tagging makes the mislabel more
visible/actionable than before. Logged as follow-up, not blocking.
