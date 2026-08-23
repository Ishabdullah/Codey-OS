---
name: m1d-lora-sync-fix-and-round-close-approved
description: M1-D required fix (lora_import.py primary/secondary sync) + rule-11 install.sh gap both verified closed; whole M1-B/C/D round APPROVED for commit
metadata:
  type: project
---

Final confirmation pass on [[m1bcd_planner_collapse_review]]'s one
required fix and its rule-11 install.sh warning. **Verdict: both closed,
combined M1-B+M1-C+M1-D diff APPROVED for commit.**

**Scope discipline confirmed via mtime, not just `git status`.** Since
nothing in this multi-round work is committed yet, `git status --porcelain`
legitimately shows ~20 modified files (the whole round). Diffing against a
commit boundary wasn't possible, so I sorted every dirty file by mtime —
everything before my own prior review's memory-file write timestamp was
untouched since; only `core/lora_import.py`, the new
`tests/test_lora_import_swap_sync.py`, `install.sh`, and `NEW_ISSUES.md`
had later mtimes. **Reusable technique when a round-in-progress has no
commit anchor and a scope claim needs verifying:** `git status --porcelain
| awk '{print $2}' | xargs stat -c '%Y %n' | sort -n` against your own
last-review memory file's mtime as the cutoff.

**lora_import.py fix verified correct via negative control, not just
reading the diff.** Hand-commented-out only the added
`cfg.PLANNER_MODEL_PATH = model_file` line in the "primary" branch (leaving
`cfg.MODEL_PATH = model_file` intact — the split/one-mutation-at-a-time
technique from [[resource_gate_subtask2_leak_fix_round2_approved]]), reran
`tests/test_lora_import_swap_sync.py`: `test_primary_swap_success_syncs_both_paths`
FAILED exactly as expected (asserting `cfg.PLANNER_MODEL_PATH == new_model`),
`test_primary_swap_failure_rolls_back_both_paths` still PASSED — confirming
the implementer's own self-assessment (the rollback test is vacuous against
the pre-fix bug, since old code never touched `PLANNER_MODEL_PATH` in the
primary branch at all, so "restored to original" trivially holds when it
was never mutated). Restored the file from a scratchpad backup afterward,
confirmed `git diff --stat` matched the pre-edit diff exactly and the
2-test file re-passed clean. Vacuous-test acceptance was correct here
because the OTHER test in the same file is a real, non-vacuous regression
guard for the exact bug that was required to fix — this is not "ship an
untested claim," it's "one of two tests earns its keep, log the other's
gap plainly" (which the implementer's own report did).

**NEW-163 (rollback_to_backup() writes base weights onto the fine-tuned
file's path) — read the actual code, agree it's accurate and correctly
deferred.** `core/lora_import.py:467/473/477`: `original = cfg.MODEL_PATH`
(read AFTER a swap already moved it to point at the fine-tuned artifact)
then `shutil.copy2(backup, original_path)` — overwrites the fine-tuned
file's on-disk name with base weights. Pre-existing, untouched by this
diff's hunks (the diff only changed which loader `rollback_to_backup()`
calls, not this variable-naming issue), correctly rated Suspected and
logged rather than silently fixed or dropped (rule 8) — it's a separate,
larger on-disk-file-identity bug from the config-sync symmetry bug that
was actually in scope.

**NEW-162 also landed in this diff's NEW_ISSUES.md hunk and was NOT named
in the fix brief — worth flagging even though it doesn't change the
verdict.** It's about `--jinja`/`--reasoning-format` defaults possibly
differing from `NEW-158`'s "off unless passed" premise that M1-C's
APPROVAL rested on. Read it: it explicitly declines to overturn NEW-158
without a live spawn, routes resolution to M1-E's live-verification step —
rule 6 handled properly, not a silent claim change. **Lesson: a
NEW_ISSUES.md diff hunk on a narrowly-scoped confirmation task can contain
more than the one entry the brief names — always read the WHOLE
NEW_ISSUES.md diff, not just grep for the finding ID you were told about,
because a second entry can quietly re-open an already-approved sub-task's
premise (M1-C here) without technically being wrong to log.**

**install.sh (rule 11) fully re-verified, not re-trusted:**
- `PRIMARY_MODEL_URL` (`unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf`)
  independently `curl -I`'d: 302, `content-disposition` filename matches
  exactly, `x-linked-size: 2740937888` ≈ the claimed ~2.55 GiB.
- Path (`~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf`) matches
  `utils/config.py:7-11`'s `MODEL_PATH` default byte-for-byte.
- `bash -n install.sh` — syntax OK.
- No remaining "1.5B"/"8081" *instructions* — the only two hits left are
  historical/retired-model comments, not live post-install text.
- `core/resource_gate.py:959` `QWEN25_7B_ARCH = ModelArch(n_layers=28,
  n_kv_heads=4, head_dim=128)` independently confirmed as a hardcoded
  architecture-shape constant with zero dependency on an on-disk file path
  — removing the 7B download is safe for `tests/test_resource_gate.py`.
- Minor Suggestion, not blocking: the diff added a dead
  `elif [ -z "$PRIMARY_MODEL_URL" ]` branch (and matching `print_completion()`
  guard) for a variable that's unconditionally set at the top of the file —
  harmless defensive scaffolding not asked for (CLAUDE.md "don't add error
  handling that wasn't asked for"), but truly inert, not worth blocking on.

**Both live suite runs independently reproduced verbatim**, exact match to
implementer's claim: `tests/` → 647 passed, 1 skipped (up from 645+1, the
+2 being the new lora_import test file); `ccos/tests/` → 68 passed
(unchanged).

**Round-close verdict: M1-D required fix correctly resolved. Rule-11
install.sh gap correctly closed. Combined M1-B+M1-C+M1-D diff is ready to
commit.** No blockers found. NEW-162/NEW-163 both correctly Suspected and
logged, neither blocks this round.

See also [[m1bcd_planner_collapse_review]] (the review this closes) and
[[resource_gate_subtask2_leak_fix_round2_approved]] (split-negative-control
technique reused here).
