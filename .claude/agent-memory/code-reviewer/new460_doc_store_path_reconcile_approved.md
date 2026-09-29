---
name: new460-doc-store-path-reconcile-approved
description: B7-residuals Commit A / NEW-460 — get_restoricon_doc_store_path helper + 3 call-site swaps — APPROVED r1
metadata:
  type: project
---

NEW-460 (B7-residuals Commit A). APPROVED round 1, 462 passed.

- `utils/config.py get_restoricon_doc_store_path()` — byte-for-byte mirrors the `db_path` block of `get_restoricon_api_config` (same `cfg is not None` / isinstance(dict) / nested-not-dict guards, same `str(Path(expanduser(...)).resolve())`). `{}` and malformed dict both fall to default; `None` -> load_user_config(). Default `CODEY_STATE_DIR/"restoricon_documents"` = `~/.codeyOS/restoricon_documents`. Env `RESTORICON_DOC_STORE_PATH`.
- `core/backup_documents.py` in-function `sys.path.insert(0, Path(__file__).parent.parent.resolve())` + `from utils.config import ...` mirrors `core/setup_litestream.py`. repo-root from `core/` is correct. Placed after `get_public_key()` early-returns, right before use — reachable.
- `restoricon_core/api/routes.py:971` lazy `from utils.config import` needs NO manual path insert — server.py already does lazy `from utils.config import` (line 54) and routes.py already lazy-imports MODEL_PATH (line 149). Consistent.
- GCS prefix `restoricon/documents_backup/{relative_path}` and state file `~/.codeyOS/document_upload_state.json` with root-relative (`os.path.relpath(fp, doc_store_path)`) keys — deliberately NOT changed, mirrors U.39 keeping old DB prefix. No orphaning.
- Test `test_doc_store_path_matches_across_sources` checks default, env override, install.sh string, and absence of `.codey_restoricon/documents` in both py call sites. grep confirms zero old-path refs outside test/doc comments.

**Warning (non-blocking, filed):** `backup_documents.py --daemon` calls `do_backup()` in a `while True` loop; the `sys.path.insert(0, ...)` runs every cycle -> unbounded sys.path growth (~1 entry/hr). Suggest guarding `if p not in sys.path` or hoisting to module level.
