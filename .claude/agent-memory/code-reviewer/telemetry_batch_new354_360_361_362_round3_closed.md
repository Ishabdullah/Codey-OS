---
name: telemetry-batch-new354-360-361-362-round3-closed
description: Round 3 (final) of NEW-354/360/361/362 batch — main.py NEW-91 message mechanism corrected and verified accurate; NEW-24 round citation fixed; NEW-363 filed for PENDING_ISH_DECISIONS.md staleness. APPROVED.
metadata:
  type: feedback
---

Follow-up to [[telemetry_batch_new354_360_361_362_round2_main_py_inverted_mechanism]].

Round 3 fixed the inverted-mechanism bug found in round 2. Re-traced
`core/lora_import.py` fresh (not from memory of round 2's trace) to
confirm the new `main.py` message:

- `results.get('model_path')` genuinely equals `cfg.MODEL_PATH` at
  message-print time: `swap_to_finetuned_model()` sets
  `cfg.MODEL_PATH = model_file` (the fine-tuned output path) on the
  primary branch, and `import_lora_adapter()` sets
  `results["model_path"] = str(output_path)` (same path) right before
  setting `results["success"] = swap_success`. The message only prints
  under `results.get("success")`, so the two are guaranteed equal at
  print time — the variable reference in the message is correct, not
  just plausible.
- `rollback_to_backup()` does `shutil.copy2(backup, original_path)`
  where `original_path = cfg.MODEL_PATH` (the fine-tuned checkpoint) —
  overwrites it with backup (pre-finetune) bytes — then
  `backup.unlink()` deletes the backup. New message text ("rollback
  overwrites the fine-tuned checkpoint at {model_path} in place with
  the backed-up base weights and then deletes the backup file") now
  matches this exactly, reversing round 2's inverted claim.

Also verified: `NEW-24`'s corrected status header ("FIXED 2026-08-09,
round 5") is literally supported by `PROJECT_LOG.md`'s round 5 entry
(2026-08-09), which contains an explicit "**NEW-24 fixed**:" line and,
in the same paragraph, discovers `NEW-84` (fixed separately, round 9,
2026-08-09) — both round numbers in the corrected ledger text check out
against primary source, not just cross-referenced ledger prose.

New `NEW-363` entry (`PENDING_ISH_DECISIONS.md:53-61` staleness) was
read against the actual current text of that file
(`sed -n '45,65p' PENDING_ISH_DECISIONS.md`) and the finding's
"Mechanism" paragraph is a verbatim-accurate description of what that
passage still says today (cites `NEW-24` as "Confirmed, unresolved",
describes a `load_secondary()`/`AttributeError` failure mode that no
longer exists in `core/lora_import.py`) — not an overclaim, correctly
cross-references `NEW-91` as the real current risk instead.

Diff scope unchanged from round 2 (same 5 files:
`main.py`/`NEW_ISSUES.md`/`docs/telemetry_layer_design.md`/
`telemetry/cli.py`/`tests/test_telemetry_cli.py`) — no scope creep.
`main.py` parses; `tests/test_telemetry_cli.py` 26/26 passing.

**Verdict: APPROVED, closed.** Two full review rounds (main.py message
mechanism inverted, then fixed) is itself the useful data point: even a
correctly-cited, previously-verified ledger finding (`NEW-91`) can get
mangled in paraphrase when a coordinator writes new prose describing
"which file does what to which other file" — always map every noun
phrase to its actual variable/file before accepting such a sentence,
every single time, not just on first pass.
