---
name: telemetry-batch-new354-360-361-362-round2-main-py-inverted-mechanism
description: Round 2 of the NEW-354/360/361/362 batch — coordinator fixed the stale NEW-24 ledger citation but the replacement main.py message got the NEW-91 mechanism backwards
metadata:
  type: feedback
---

Follow-up to [[telemetry_batch_new354_360_361_362_main_py_stale_ledger_citation]].
Coordinator correctly fixed round 1's finding: corrected NEW-24 and NEW-84's
stale `NEW_ISSUES.md` status headers to FIXED (both genuinely fixed
2026-08-09, verified independently against `core/lora_import.py` and
`core/loader_v2.py`'s own inline comments), and rewrote `main.py`'s
`--import-lora` success message to cite `NEW-91` instead.

But the replacement message itself introduced a NEW factual bug — same
"trust a citation without tracing the mechanism" failure class, one level
deeper. It said: "rollback overwrites **this backup file** in place and
deletes it, permanently destroying the fine-tuned checkpoint... save a
separate copy [of the backup] first if you want to keep it."

Traced the actual code and this is backwards:
- `create_backup_before_import()` copies the **pre-finetune original**
  model to the backup path, before import.
- `swap_to_finetuned_model()` mutates `cfg.MODEL_PATH` to point at the
  **new fine-tuned file's own path** (a different file on disk).
- `rollback_to_backup()` does `shutil.copy2(backup, original_path)` where
  `original_path = cfg.MODEL_PATH` (now the fine-tuned file) — this
  **overwrites the fine-tuned checkpoint's bytes**, then `backup.unlink()`
  **deletes the backup** (the old pre-finetune copy).

So the backup is deleted, not overwritten; the fine-tuned file is
overwritten, not deleted — two different files, two different operations,
and the message's own remedial advice ("save a copy of the backup to
keep the fine-tuned checkpoint") doesn't achieve what it claims, since the
backup never contained fine-tuned bytes at all. `NEW_ISSUES.md`'s own
NEW-91 entry (lines 5487-5502) states the mechanism correctly — the
coordinator didn't re-derive it from the ledger text it was citing, wrote
a plausible-sounding but backward paraphrase instead.

**Lesson — this is the SAME bug class as round 1, one layer deeper.**
Round 1: a message cited a stale ledger status without checking current
code. Round 2: the ledger status was fixed, but the new message paraphrasing
the correct (already-verified) NEW-91 text still got the mechanism backward.
When a diff writes prose describing "which file does X to which other
file," don't accept it as self-evidently correct just because the cited
finding is real and confirmed-open — trace the actual copy2()/unlink()
argument order (source vs destination) yourself and match every noun in
the sentence to the specific file it's actually about. A message can cite
a totally correct, non-stale finding and still be wrong.

Verified via advisor() catching it — I had confirmed all the underlying
mechanics (copy2 args, cfg.MODEL_PATH mutation, NEW-91 ledger text) in the
same review pass but hadn't yet cross-checked the new prose sentence
word-by-word against those facts before drafting a verdict. Cheap check
that would have caught it directly: map each noun phrase in the new
message ("this backup file", "the fine-tuned checkpoint") to the specific
variable/file it corresponds to in the traced code, before accepting the
sentence as accurate.
