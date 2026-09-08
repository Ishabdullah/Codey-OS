---
name: new414_lora_rollback_new91_163_batch_approved
description: NEW-414 except-pass narrowing + NEW-91/163 LoRA rollback data-loss fix — both APPROVED, no findings
metadata:
  type: project
---

Round covering `ccos/core/device_manager.py`/`ccos/core/goal_engine.py`
(NEW-414, 8-site except-narrowing) and `core/lora_import.py`
(NEW-91/NEW-163, rollback-destroys-finetune fix) plus a new regression
test `tests/test_new91_new163_rollback_preserves_finetune.py`. **Both
items APPROVED** — everything the implementer claimed was independently
verified true, nothing overclaimed, nothing silently expanded in scope.

**NEW-414 (except-pass narrowing):** grepped all `except` lines in both
files myself and independently cross-checked line numbers/types against
each site's actual code (regex `.group(1)`-on-None → AttributeError,
`line.split(":",1)[1]`-with-no-colon → IndexError, etc.) — every narrowed
type was correct and not just plausible-sounding. The 3 left as bare
`except Exception as e` (device_manager.py `_detect_storage` `df -h`
parsing; goal_engine.py `_save_queue`/`_load_queue`) now log via
`warning()` instead of silently swallowing — genuinely non-narrowable
(shell-tool output format varies by platform; queue-file corruption can
fail many distinct ways). Pure hygiene pass — no behavior change beyond
exception specificity + added log lines, confirmed by reading every diff
hunk.

**Self-reported gaps were honest, not silent-drops:** `NEW-415`
(`goal_engine.py:345`, `device_manager.py:369` — 2 more bare-except sites
NEW-414's original "8 total" count missed) and `NEW-416`
(`device_manager.py:227`/`:300` catch `(PermissionError, OSError,
Exception)` — `Exception` makes the tuple functionally bare, a worse
version of NEW-414's own complaint) were both independently confirmed via
`grep -n "except" <files>` — the exact line numbers described are still
unfixed as claimed, correctly logged as new findings rather than either
silently expanded into this round's scope or silently left off the
ledger.

**NEW-91/NEW-163 (LoRA rollback fix):** pre-fix `rollback_to_backup()`
restored a backup onto whatever `cfg.MODEL_PATH`/`PLANNER_MODEL_PATH`
*currently* named — after `swap_to_finetuned_model()`, that's the
fine-tuned file's own path, so rollback silently overwrote/destroyed the
fine-tuned checkpoint. Fix derives the original path by reversing
`create_backup_before_import()`'s `<stem>.backup<suffix>` naming
(`backup.stem[:-len(".backup")]`), and resets both config pointers to
that original path post-restore. Traced the naming inverse by hand
including edge cases (original filename itself containing "backup",
e.g. `backup_model.gguf` → `backup_model.backup.gguf` → strips correctly
since only the trailing `.backup` on `.stem` is stripped) — correct.
Fallback path (non-`create_backup_before_import()`-shaped backup name)
correctly reproduces the pre-fix pointer-based behavior but logs a
`warning()` flagging the exact NEW-91/163 risk rather than silently
reintroducing it unlabeled.

**Regression test genuinely fails pre-fix**: negative-controlled myself
via `git stash push -- core/lora_import.py` (not `git checkout`, which
would have collided with rule about wiping uncommitted diffs — see
[[git_checkout_path_wipes_uncommitted_diff]]) — reran the new test file,
watched `test_rollback_after_swap_restores_base_and_preserves_finetune`
fail with a real sha256 checksum mismatch showing the fine-tuned file's
contents overwritten, `git stash pop` restored the fix cleanly. Real
regression coverage, not a vacuous pass — uses actual file bytes/sha256,
not mocks, for the exact fine-tuned-file-destroyed assertion.

**NEW-417 (dead test uncovering the bug) verified by direct
reproduction**: `python ccos/plugins/coding/finetune/test.py` really does
raise `ImportError: cannot import name 'create_backup_before_import'`
at the top-level import — `finetune.py`'s own docstring claims these are
"wrapped" but the actual `from core.lora_import import (...)` block only
imports `validate_lora_adapter`. This is a legitimate root-cause finding
(the one pre-existing test that would have caught NEW-91/163 was never
running, isn't pytest-discovered since it lives outside `tests/` and is
invoked as a standalone script) — correctly logged as Confirmed, not
Suspected, since it was directly reproduced rather than inferred.

**NEW-91/163 ledger cross-reference and rule-6 correction verified
honest**: read both original entries in full. NEW-163's original text
did claim "the config pointer ends up correct (it's reset to the
pre-swap value elsewhere in the rollback path)" — I independently
confirmed via the diff that pre-fix code had NO such reset anywhere
(`cfg.MODEL_PATH = original_path` did not exist before this round's fix),
so the correction downgrading that claim to false is accurate, not
face-saving.

Full suites independently run by me (not trusted from implementer
report): `python -m pytest ccos/tests/ -q` → `111 passed` (exact match),
`python -m pytest tests/ -q` → `1510 passed, 1 skipped in 245.02s`
(exact match to claim). `git diff --stat` on `NEW_ISSUES.md` is
110 insertions / 0 deletions — purely additive append-only ledger, no
history rewriting, consistent with this project's established ledger
convention.

No new findings from this review. Nothing to flag beyond what NEW-415/
416/417/418 already logged.
