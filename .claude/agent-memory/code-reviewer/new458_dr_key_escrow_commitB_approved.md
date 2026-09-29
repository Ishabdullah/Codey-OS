---
name: new458-dr-key-escrow-commitB-approved
description: NEW-458 commit B (DR key escrow) review — approved w/ warnings; secret-to-log negative check, bucket-resolution divergence
metadata:
  type: project
---

NEW-458 commit B (B7-residuals): `core/setup_dr_key.py` (new), `core/backup_secrets.py` (rewrite), `lib/service_manager.sh`, `install.sh`. Reviewed 2026-09-10, APPROVED with warnings.

**Why:** DR (disaster-recovery) age keypair escrow. setup_dr_key.py generates keypair, writes only pubkey to config.restoricon.dr_recipient_pubkey, prints private key to stdout once. backup_secrets.py tars the irrecoverable secrets, age-encrypts to TWO recipients (at-rest + DR), uploads to GCS. Wired one-shot into start_litestream() under `timeout 120`.

**How to apply / what held up:**
- Crux 1 (secret never persisted): clean. `_generate_keypair` raises RuntimeError with only `type(e).__name__` + `from None` — never echoes captured stdout (age-keygen puts AGE-SECRET-KEY on stdout). Verified install.sh does NOT redirect its own output to a log (`grep -nE 'tee|exec [0-9]*>' install.sh` empty), so the "never written to disk" docstring claim holds. setup_dr_key.py invoked ONLY from install.sh line 494 — grep-confirmed, not from any launcher/service_manager path.
- Crux 2-4: fail-closed guard (`_PUBKEY_RE = ^age1[a-z0-9]+$`) runs before mkdtemp/storage.Client; both `-r` args asserted in test; mkdtemp (not $HOME) + explicit chmod 0o600 + try/finally rmtree (test exercises REAL rmtree on upload failure). SIGTERM handler raises SystemExit(1) to force stack unwind so finally runs.
- Crux 5: service_manager wiring — no pid file, no pkill, non-blocking on nonzero exit (else-branch warn). Gated behind `[ -f litestream_bin ] || return 0`. `age` installed by install.sh (all pkg managers) — rule 11 OK, pre-existing dep.
- 471 passed (tests/test_restoricon_core + test_service_manager_config + the 2 new files).

**Non-blocking warnings handed back for NEW-## entries:**
- W1: `get_bucket_name()` in backup_secrets omits the `GCS_BACKUP_BUCKET` env-var precedence that `setup_litestream.py:15-17` honors. Implementer's crux-8 claim "matches how setup_litestream resolves the bucket" is inaccurate — config-file case matches, env-var case diverges.
- W2: adds up-to-120s synchronous blocking call to every `codey-start` (flaky mobile network = 120s startup stall). Consider shorter timeout / backgrounding.
- W3: `backup_secrets.main()` installs a process-global SIGTERM handler with no teardown; in-process test calls leak it into the pytest session.
- W4/W5 (one root cause): `get_at_rest_public_key` catches only CalledProcessError, not OSError (age-keygen missing → uncaught traceback vs clean log; still exits nonzero/safe); and `age-keygen -y` stderr on a malformed identity key is uncaptured and flows to $LITESTREAM_LOG_FILE — could surface key-material fragments into a local log.
- Suggestion: re-tars + re-uploads the same blob path on every start (wasteful).

**Round 2 (2026-09-10) — 4 follow-up fixes APPROVED.** W4/W5: `get_at_rest_public_key` now `subprocess.run([age-keygen,-y], capture_output=True, check=True)`, catches `(CalledProcessError, OSError)`, logs `type(e).__name__` only — no e/e.stderr/e.output/result.stderr path to any log; pubkey regex-validated before use. W1: `get_bucket_name` env `GCS_BACKUP_BUCKET`→config→`codey-os-backups`, byte-identical to setup_litestream.py:15-17. W3: `main()` saves/restores SIGTERM via try/finally; `_run()`'s own work_dir cleanup finally nests inside so tar cleanup precedes signal restore. W2: `timeout 120`→`timeout 60` in service_manager, nothing else in block. Tests: check_output→run mock switch correct (code no longer calls check_output, so old `mock_co.assert_not_called()` was vacuous; `mock_run.assert_not_called()` is real fail-closed guard). happy_path asserts count("-r")==2 + both pubkeys + tar getnames; upload_failure test exercises REAL rmtree. 474 passed. Non-blocking: `signal.signal` from a non-main thread would ValueError, but service_manager runs this as a subprocess (main thread) — fine.
