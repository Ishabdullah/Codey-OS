---
name: u39-db-path-reconcile-litestream-approved
description: U.39 NEW-455/456/457 — DEFAULT_DB_PATH repoint + init_schema flag + litestream live-DB fix — APPROVED r1
metadata:
  type: project
---

U.39 (3 commits) fixing NEW-455/456/457. APPROVED round 1, 462 passed.

- `restoricon_core/database.py`: `DEFAULT_DB_PATH` fallback `~/.codey_restoricon/core.db` -> `~/.codeyOS/restoricon.db`
  (matches `utils/config.py:get_restoricon_api_config` default line 704 and `lib/service_manager.sh:244` fallback `$DAEMON_DIR/restoricon.db`).
- New `DatabaseManager.__init__(db_path, init_schema=True)`. All 4 callers verified single positional / keyword — no positional-misread risk
  (server.py, provision_ai_agent_auth.py, migrate_aigentik x2). `init_schema=False` opens no connection (lazy get_connection), `:memory:` branch untouched.
- `migrate_aigentik.main()` passes `init_schema=args.apply`.
- `core/setup_litestream.py`: db_path now `get_restoricon_api_config()["db_path"]` (function-scoped import, no cycle — config.py only imports json/os/shutil/pathlib/typing).
  `get_restoricon_api_config` DOES honor RESTORICON_DB_PATH (line 702), so removing the explicit env read is NOT a regression. GCS replica prefix `restoricon/core_db` -> `restoricon/restoricon_db` (only 2 lines changed in yml; old GCS data untouched).
- install.sh: `google-cloud-storage==2.11.0` — matches requirements.txt line 84 exactly. `age` already present in all 5 pkg-manager branches, no dup.

**Behavior change worth remembering (non-blocking):** a dry run (`migrate_aigentik --db-path X` without `--apply`) against a *fresh nonexistent* DB path with non-empty source will now raise "no such table" instead of silently creating schema. Against the live production DB (which has schema) it works fine — that's the real workflow. Arguably desired behavior.

**Out of scope, still stale:** `~/.codey_restoricon/documents` in install.sh:190, core/backup_documents.py:68 (doc blob store, genuinely separate from the DB — does not affect this diff's risk).
