---
name: new422-423-finetune-import-and-scan-fallback-default-mismatch
description: NEW-422 (finetune.py prepare_finetune_data import) approved clean; NEW-423 (device_manager.py _scan() fallback) blocked on a "literal defaults mirror the real function" overclaim that was only true for 3 of 5 replaced calls
metadata:
  type: project
---

Round: 2026-09-09 cleanup of NEW-422/NEW-423 in `ccos/plugins/coding/finetune/finetune.py`,
`ccos/core/device_manager.py`, `ccos/tests/test_ccos.py`, `NEW_ISSUES.md`.

**NEW-422 (finetune.py import fix): clean, approved.** Added `prepare_finetune_data` to
the existing `from core.finetune_prep import (...)` block. Verified independently: read
`prepare_finetune_data()`'s full body (core/finetune_prep.py:686-751) — only calls
`DatasetCurator().curate_examples()` (reads state store, no model calls), `export_dataset()`,
`generate_notebook()`, `print_instructions()`. Zero `load_primary`/`unload`/`swap_to_finetuned_model`
hits anywhere in the file. Live import succeeded.

**NEW-423 (device_manager.py `_scan()` fallback): CHANGES REQUESTED.** The fix's own
premise — stated identically in both the ledger entry and the new code comment — is that
"each of the 5 re-called `_detect_*()` functions already declares its own literal
pre-probe default dict/list at the top of its body," and the fallback's hardcoded values
"mirror each `_detect_*()`'s own pre-probe default shape." This is **false for 2 of the 5**:

- `_detect_os()`'s real pre-probe default computes `platform: platform.system()`,
  `arch: platform.machine()`, `release: platform.release()` — not literals. Fallback
  substitutes `"unknown"` for all three.
- `_detect_cpu()`'s real pre-probe default computes `cores: os.cpu_count() or 1` and
  `arch: platform.machine()` — not literals. Fallback substitutes `1` and `"unknown"`.
- `_detect_ram()`, `_detect_storage()`, `_detect_network()` genuinely do have literal
  pre-probe defaults, and match exactly — but these were the two examples the ledger
  entry actually cited (`_detect_ram()`, `_detect_storage()`), i.e. the two that happened
  to confirm the "all 5 are literal" claim. A filtered read that confirms the expectation
  looks like verification and isn't — this is CLAUDE.md rule 12's exact trap, now inside
  ledger prose rather than code.

Substantive angle, not just a doc nit: `platform.system()/machine()/release()` and
`os.cpu_count()` are syscall-backed stdlib introspection — they are not among the things
that can actually raise inside the `try` block (the raisers are `/proc` file reads and
`subprocess` calls). So the fallback discards CPU core count and OS arch/release for zero
safety benefit, purely because the implementer conflated "has a literal default" with "is
cheap/safe to compute directly."

External blast radius: `grep`'d every non-test, non-device_manager.py caller of
`get_profile()`/`is_termux()`/`is_android()`. Six `ccos/demo_*.py` scripts read
`device.get_profile()['cpu']['cores']` directly — key present (no crash), but silently
pinned to `1` under the fallback, i.e. a real (if low-stakes, demo-only) functional
regression, not purely cosmetic.

Required fix, implementer's choice of direction: either (a) have the fallback compute
`platform.machine()`/`platform.system()`/`platform.release()`/`os.cpu_count() or 1`
directly (same stdlib calls the real functions use, still zero risk of the `/proc`-read
failure mode that motivated the fix) and update the new test's exact-dict assertions
accordingly, or (b) keep the literals but correct both the ledger entry and the
`_scan()` code comment to state plainly that the fallback deliberately under-reports
`os.arch/release` and `cpu.cores/arch` (3-of-5 literal parity, not 5-of-5), not "mirrors
each function's own default shape."

Verification performed and clean, worth reusing without redoing:
- Negative control: `git stash` to pre-fix code, patched `_detect_cpu` to raise —
  confirmed `RuntimeError: boom` genuinely propagates out of `DeviceManager()` uncaught.
  `git stash pop` restored cleanly (checked `git status --short` after).
- All in-file consumers (`get_summary`, `has_camera`, `has_microphone`, `has_gpu`,
  `has_speakers`, `is_termux`, `is_android`, `get_capabilities_hints`) use `.get()` with
  defaults — none can `KeyError` on the minimal profile.
- The 4 probes the fallback does NOT re-call (`_detect_gpu`, `_detect_cameras`,
  `_detect_audio` x2, `_detect_connected_devices`) are unchanged by this diff — their
  keys (`gpu`/`cameras`/`microphones`/`speakers`/`connected_devices`) were already `[]`
  literals in the pre-existing fallback, so there is no missing-key gap from this change.
- Full suites match claimed output verbatim: `ccos/tests/` 112 passed;
  `tests/` 1517 passed, 1 skipped (235s).
- The `NEW-403` recurrence note in this same diff is accurate: NEW-403's own status line
  reads "Confirmed — reproduced live, twice, in this round" (not yet fixed), matching the
  note's characterization; the 3 stray `file:test_doc_upload_*` artifacts this round's own
  full-suite run left in repo root were untracked, not committed, correctly treated as
  routine cleanup rather than a new ID.

Reusable pattern for future reviews: when a fix's justification cites "N of the same-shaped
things all behave like X," check *every one* of the N, not just the examples the diff/ledger
happens to quote — the examples chosen to illustrate a claim are exactly where an author's
own confirmation bias is least likely to have been caught.
