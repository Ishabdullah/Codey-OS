# V-C3: gateway, REPL confirm, daemon, peers, egress, kill identity (WP2.1 G15z verify, stage S1)

Verifier: independent (did not write the code under test). Subject: `git archive HEAD` (b230ce9) at `$G15Z_OUT/C/snap`
(`G15Z_OUT=/data/data/com.termux/files/usr/tmp/g15z_verify/VC3`). Control snapshot: `snap_census` = 941ec3f (the hunter base) where a pre-fix
reproduction was cheap. Rows: `docs/wp2_1_g15z_verify_C3.tsv` (145 rows; the TSV is the authority). Raw outputs: `$G15Z_OUT/C/out/` (`rows.jsonl`, `b*.txt`, `b*.json`,
`ops3_*.txt`); harness: `$G15Z_OUT/C/harness/` (`vc3.py` installs the recording fakes, `run_final.sh` re-runs everything). Status: COMPLETE.
Evidence tier: **independently re-probed on a snapshot with recording fakes and disposable fixtures; NOT live-verified** (no real tty, daemon, peer, network, model or store).

## Summary

| verdict | count |
| --- | --- |
| PASS | 120 (112 re-verified closures/negative results + 8 harness, control, inventory or code-read rows: CANARY, CANARY2, REPL.no_spawn, CONTROL-ACT, PEER-06, TDD-02, DEVBR-01, D-10) |
| ACCEPTED-RESIDUAL | 18 |
| FAIL | 5 |
| INCONCLUSIVE | 2 |
| BLOCKED-BY-SAFETY | 0 |

New defensive probes: 39 rows (cap 40; REPL.pipey_real_confirm and NEW983-01..03 were added after the first advisor review). Random previously-clean re-checks: 10 rows (seeded `random.Random(20261024)` over a 20-row pool of hunter B/C clean rows: K04, FT09, FT04, FT17, FT01, FT05, FT15, IA-04, M12, FT19).
Controls: every PASS that guards a fixed finding carries a CONTROL in its `observed` text (a positive control in the same fixture, e.g. literal-True executes, a matching-identity fixture signals, a tty `y` answer writes; or the same probe on 941ec3f where it reproduced the original weakness: REPL unprompted core writes, yolo manifest/bench-lock/config writes, peer Enter=Yes, `.qwen/settings.json` 12 dangerous entries, `--tdd` forced confirm-off, kill/exfil commands labelled ACT, `setup_dr_key.py` printing the DR key into captured stdout and rewriting config, `provision_ai_agent_auth.py` mutating the DB before any confirmation).

**No regression of a shipped fix was found.** Every fixed family re-verified closed at HEAD with the stated caveat. The 5 FAIL rows are 4 root causes the register does not claim fixed (2 are already register-open: KILL-08/DSHELL.service stop and FIX-01; REPL.pipey_real_confirm is register-open as NEW-1074; GW-10b is new, LOW), not regressions.

## Rows by family

| family | rows | verdicts |
| --- | --- | --- |
| --tdd / --fix / process_boundary | 4 | FAIL 1, PASS 3 |
| HIGH_IMPACT refusal in confirm-less modes | 3 | PASS 3 |
| HIGH_IMPACT refusal in confirm-less modes (daemon shell) | 7 | ACCEPTED-RESIDUAL 1, FAIL 1, PASS 5 |
| HIGH_IMPACT refusal in confirm-less modes (self-mod unlock) | 3 | ACCEPTED-RESIDUAL 3 |
| REPL/confirm-less HIGH_IMPACT file writes | 8 | FAIL 1, PASS 7 |
| ask_confirm / peer default-No / interactivity | 12 | PASS 12 |
| audit coalescing | 2 | PASS 2 |
| audit coalescing (concurrency) | 1 | PASS 1 |
| audit ledger | 1 | PASS 1 |
| audit ledger / state tamper | 1 | PASS 1 |
| audit row shape | 1 | PASS 1 |
| audit secret masking | 4 | FAIL 1, PASS 3 |
| audit-file append atomicity | 1 | PASS 1 |
| ccos call_capability gating | 8 | ACCEPTED-RESIDUAL 1, PASS 7 |
| control | 1 | PASS 1 |
| daemon IPC / dispatch gate | 11 | ACCEPTED-RESIDUAL 5, PASS 6 |
| dashboard/API state mutation (Restoricon native authority) | 2 | PASS 2 |
| gateway call-site matrix | 1 | PASS 1 |
| gateway confirm semantics | 26 | ACCEPTED-RESIDUAL 1, PASS 25 |
| harness | 3 | PASS 3 |
| kill / process identity | 14 | FAIL 1, PASS 13 |
| network client egress mediation | 8 | ACCEPTED-RESIDUAL 3, INCONCLUSIVE 1, PASS 4 |
| notification / device boundaries | 5 | ACCEPTED-RESIDUAL 3, PASS 2 |
| operator scripts | 1 | ACCEPTED-RESIDUAL 1 |
| operator scripts (G15i) | 3 | INCONCLUSIVE 1, PASS 2 |
| previously-clean row re-check (random) | 10 | PASS 10 |
| undo / checkpoint / prune gateway | 4 | PASS 4 |

## Original-finding map (what closed, by slice)

| finding | slice | verdict | rows |
| --- | --- | --- | --- |
| gate_exec/gate_write/gate_append literal-True approval, one callback call, callback exception/EOF/interrupt fail closed without leaking text, HIGH refusal without confirm path, row shape | G15j (NEW-1027) | PASS | GW-01..GW-07, GW-16..GW-19 |
| G15b-37: REPL/tty HIGH NEW-file and append prompt, no tty = refuse without reading stdin, a piped `y` cannot approve the G15j callback, `--allow-self-mod` still prompts, prompt escapes ANSI/markup/newline/RLO and shows head+tail | G15j | PASS for new-file/append; the LEGACY patch/overwrite prompts still accept a piped `y` (FAIL, register-open NEW-1074) | REPL.*, SELFMOD.repl_*, CF-02..CF-05, REPL.pipey_real_confirm |
| G15b-27/28/29/33/34/35 HIGH writes refused in `--yolo`/daemon/`--fix` config (manifest.json, bench lock, repo config.json, launcher, audit ledger path) | G15e | PASS (941ec3f control wrote them) | CONFIRMLESS.yolo, CONFIRMLESS.daemon, CLEAN.* |
| G15b-36 `--yolo --allow-self-mod` / ALLOW_SELF_MOD=1 / daemon+self-mod unlock HIGH writes (DENY tier still refuses) | accepted residual D-1 | ACCEPTED-RESIDUAL | SELFMOD.yolo_selfmod, .yolo_envselfmod, .daemon_selfmod |
| ask_confirm `[y/N]` hint, Enter = No, EOF/Ctrl-C = No | G15d Unit A / G15j | PASS | CF-01 |
| G15b-46 peer escalation default-No; qwen allow-list trimmed; `peer_delegate` never dispatches; parked escalations never dispatch | G15d Unit A | PASS (941ec3f Enter=Yes control) | PEER-01..PEER-06, EG-01 |
| G15b-45 `is_interactive_environment` fail-open on isatty error; main.py predicates | G15d Unit C | PASS; dead `CODEY_DAEMON_MODE` signal remains | PEER-04, CONF-01, D-09 |
| G15b-47 `--tdd` confirm-less | D-9 / NEW-1029 | PASS (--tdd half); `--fix` half OPEN | TDD-01, TDD-02, FIX-01, PB-01 |
| G15b-44 daemon IPC `peer_uid` is None, chmod-after-bind window | queued | ACCEPTED-RESIDUAL | D-01, D-02, D-03 |
| daemon dispatch gate (every IPC handler gateway-mediated, never HIGH), malformed/oversized/unauthenticated frames, idle connections | WP2.1 | PASS | D-04, D-05, D-06 |
| K02/K03/K05 kill identity (recycled PID, uid, boot id, zombie, pid 1, bool, malformed stat), no kill by name pattern in production code, supervisor stops only owned Popen | NEW-983 | PASS | KILL-01..KILL-06, CLEAN.K04 |
| NEW-983 foreign-kill refusals: exe != LLAMA_SERVER_BIN, argv lookalike, duplicate/`--model=`/relative `-m`, planted cwd, unreadable `/proc/net/tcp`, PID recycled between reads | NEW-983 | PASS | NEW983-01..NEW983-03 |
| env/flag flips: `CODEY_ACTION_GATEWAY_AUDIT=/dev/null`, `CODEY_SELF_IMPROVE`, `CODEY_LINTER` (as classifier strings: SELFLAUNCH-01; at the call sites: FLIP-01..03; `CODEY_LLAMA_SERVER` and `--lora-force-adopt` as classifier strings only, see limits) | spec V-C3 | PASS | SELFLAUNCH-01, FLIP-01..FLIP-03 |
| shell kill/exfil/publish/tamper/self-launch commands refused in confirm-less shell and in the daemon shell | G15c/G15d/G15e | PASS (941ec3f control: ACT) | KILL-07, EGRESS-01, SELFLAUNCH-01, TAMPER-01, DSHELL.* |
| G15b-21 operator scripts refuse without a human (no ctty), DB/config bytes unchanged | G15i-B | PASS (no-tty legs only) | OPS-01, OPS-02 |
| G15b-48 audit ledger masking, fail-closed marker | G15h-B | PASS for the 7 probed shapes; mid-line env-prefix gap | GW-08..GW-10b |
| audit coalescing (ACT only, refusals/HIGH/READ never suppressed, LRU bound, thread-safe) | WP2.1 | PASS | GW-11..GW-13 |
| ccos `call_capability`: HIGH refused, unclassified refused, lookalike names unclassified, handlers cannot lower, collisions disable both, args never audited | WP2.1 group 4 / G15g | PASS | CC-01..CC-05, CC-07, CC-08 |
| undo / checkpoint rollback / prune gated HIGH, literal-True only | WP2.1 groups 11/14b | PASS | UN-01..UN-04 |
| Restoricon native business authority (not the gateway, by decision) | WP2.1 group 7 | PASS | DASH-01, DASH-02 |
| microphone HIGH gate | WP2.1 group 12 | PASS | VOICE-01 |
| remote backend egress, manifest endpoint dispatch, device bridge | C:N01/N03/N08 | ACCEPTED-RESIDUAL (INTENTIONAL / dormant) | EG-02, EG-03, CC-06, DEVBR-02, DEVBR-03 |
| production gate call-site matrix | WP2.1 | PASS | SITE-01 |

## FAIL rows (each explained; none is a regression of a shipped fix)

1. **GW-10b (new, LOW; G15b-48 residual not in the register).** Input: `refuse_exec(command=...)` with a secret NOT at line start: `env AIGENTIK_INTERNAL_TOKEN=<48 hex> python3 x` and `FOO=1 AIGENTIK_INTERNAL_TOKEN=<48 hex> python3 x`. Observed: the hex value is written verbatim to the audit ledger (`mask_secrets` `env_secret_assignment` is anchored to line start; `cd x && export OPENROUTER_API_KEY=sk-or-...` IS masked because the `sk-or-` prefix pattern catches it). Control: the line-start form `AIGENTIK_INTERNAL_TOKEN=<hex> python3 x` is masked. Impact: a model-issued shell command that carries an env-prefixed token reaches `~/.codeyOS/action_gateway_audit.jsonl` unmasked; the ledger is same-uid readable. Needs a ledger id.
2. **KILL-08 and DSHELL.service stop (C:K11 siblings; register-open, not claimed fixed).** Input: `python3 core/process_identity.py stop /x/pid svc` and `python3 core/service_lifecycle.py lock-exec all stop` through `shell()` in a confirm-less config (and the first through the daemon's `_daemon_shell`). Observed: classified ACT, executed unconfirmed (spawn recorded; the same commands were ACT at 941ec3f). The bare launchers (`codey-stop`, `./codey-stop`, `codeydOS stop|restart`) ARE now HIGH and blocked; `bash codey-stop`, `bash lib/service_manager.sh stop` are blocked by the protected-path scan inside `shell()`. The stop path is identity-bracketed (KILL-02..05) so it cannot signal a foreign process, but it does stop the daemon/API/tunnel without confirmation in `--yolo`/`--fix`/`--tdd --yolo`/bench. Closest register entry: G15b-21 siblings, NEW-1070.
3. **FIX-01 (G15b-47 `--fix` half; register: STILL OPEN, NEW-1077).** Input: `fixmode.run_and_capture('python3 <file>')` with `main.py --fix` configuration. Observed: ACT, executed with no callback (the model-rewritten file runs unattended). Unchanged from 941ec3f. Needs a policy decision (Ish).
4. **REPL.pipey_real_confirm (G15b-37 / NEW-1074; register-open, LOW, not claimed fixed).** Input: REPL defaults (`confirm_write` True), stdin a pipe carrying `y` lines, `_stdin_is_tty` False, the REAL `utils.logger.confirm` (nothing patched), then `patch_file` on an existing core `.py`, `write_file` overwriting an existing core `.py`, and `write_file` overwriting the existing `codeyOS` launcher. Observed: all three were APPROVED by the piped `y` (one stdin line consumed each) and executed (`Patched ...`, `Written core/zz_pipe_target.py`, `Written codeyOS`; HIGH_IMPACT `allowed` rows) because the legacy `Apply patch?` / `Overwrite X?` prompts have no `isatty()` check and set `human_consented`, which skips the G15j callback. The G15j paths ARE closed: `append_file` on an existing core file and `write_file` of a NEW core file with the same piped input were `[BLOCKED] Human confirmation declined` with zero stdin consumed (also REPL.repl_pipey, CF-04). NEW-1074 (OPEN, LOW) records this: every REPL confirm, including the overwrite and patch prompts, can be satisfied by queued or piped input, and G15j added the `isatty()` guard for the new HIGH file prompt only and NEW-1078 R9 notes the existing-file HIGH overwrite is covered only by the legacy prompt. So the md line "a piped y cannot approve" holds for new-file and append writes only.

## INCONCLUSIVE rows

* **OPS-03**: pty-attached legs of the G15i guards (a human `y`, a script that owns a pty and answers `y`, NEW-1071) are S1b scope and were not run.
* **EG-04 (observation, not a finding):** `tools/kb_semantic.py:115` builds `http://localhost:{port}/v1/embeddings`; every other inference/embedding/health client uses numeric `127.0.0.1`. `localhost` is resolved from the hosts file, not DNS; no resolution to a non-loopback address was shown, so no impact is claimed.

## ACCEPTED-RESIDUAL rows (documented and not claimed fixed; the evidence column states the register position)

SELFMOD.* (G15b-36, D-1); D-01 `peer_uid`/`peer_pid` are `None` on a real asyncio unix server here so the uid rejection never fires (G15b-44, queued; the check itself is correct when a value exists: D-03); D-02 the socket is bound 0o777 under umask 0 and chmod-ed afterwards, protected in practice by the 0o700 parent dir (real `~/.codeyOS` is 0o700, stat only); D-07 `codeyOS --bg` authority laundering (ACT enqueue, same uid); D-09 no writer of `CODEY_DAEMON_MODE`/`CODEY_NON_INTERACTIVE` anywhere (safety rests on `stdin=DEVNULL` at `process_identity.py:598`, D-10, and the daemon's confirm-off config); D-11 relative `CODEY_STATE_DIR` is refused for daemon paths but `audit_path()` still follows it (NEW-1003); OPSCRIPT-01 / DSHELL.operator script-form operator tools run as ACT but self-guard (OPS-01, OPS-02), `tools/encrypt_cloudflare_token.py` also runs unconfirmed (not in G15i scope); GW-20 `confirm_available=True` without a callback executes by design (SITE-01 shows no site passes True without a human step); CC-06/EG-02/EG-05 manifest endpoints and remote backends are not host-validated (N03, N01 INTENTIONAL; the metadata URL was attempted through the recording fake only); EG-03 stdlib forwards `Authorization` on a 302 to another host; VOICE-02 speech text starting with `-` reaches `termux-tts-speak` without `--` (LOW, arg parsed by that tool); DEVBR-02/03 device bridge dormant, auth opt-in, `!=` token compare, unbounded frame (8 MB accepted).

## Observations worth a ledger line (not verdict-changing)

* A `SystemExit` raised by a confirmation callback is a `BaseException`: it propagates out of `gate_exec`/`gate_write`/`gate_append` and out of `prune_checkpoints` with NO refusal row (GW-04, UN-01). Nothing executes, so no authority is gained; the audit trail has a gap. `KeyboardInterrupt`, `EOFError`, `MemoryError`, `RecursionError` and ordinary exceptions refuse with a row and without leaking exception text (GW-03).
* The legacy "Overwrite X?" prompt fires before the DENY-tier refusal, so a human is asked to approve a write that is then refused (REPL.tty_approve, W6). Cosmetic.
* `shell()` applies more escalations (protected-path scan, PATH-shadow) than the bare `classify_shell_command`; the bare classifier alone under-reports (e.g. `python3 main.py --yolo --allow-self-mod x` is ACT bare, blocked effective). Any consumer that trusts the bare classifier (e.g. `core/process_boundary.run_process`) sees the lower label.
* Daemon IPC error replies echo Python exception text to the client (D-04, same-uid client); the handler has no read timeout (D-05).

## Honest coverage limits and what was NOT run

* **Named items from the V-C3 spec that were NOT run (or only partly):** `CODEY_LLAMA_SERVER` and `--lora-force-adopt` were exercised only as classifier/`shell()` strings (SELFLAUNCH-01), not at their consuming sites (`utils/config.py:41` reads `CODEY_LLAMA_SERVER` at import, so a flip needs a child process; the `--lora-force-adopt` `/dev/tty` prompt and the TIOCSTI check of C:M30 are S1b/pty scope); a relative `CODEY_STATE_DIR` was tested through `audit_path()` and the daemon path validator (D-11) but not through a child process; the bench harness and `bench/agents.py` env scrub are V-C2; `/git push` and `/graph clear` confirm predicates were not exercised (only `_init/_voice/_undo_confirmation`, CONF-01); C:M13's `sqlite3 ... delete from actions`, `rm <state.db>` and `rm <age.key>` forms were not run (only the audit-ledger tamper forms, TAMPER-01).
* **Not run:** a real daemon process, real peers (qwen/antigravity were never invoked; `mgr.call` was a recorder), the tunnel, any real network, any model load, the bench, `CODEY_TRAJECTORY`, the live Restoricon DB, a real tty or pty (all `tty_*` modes patch `_stdin_is_tty`/`utils.logger.confirm`/`console.input`; S1b covers real pty behaviour including the `/dev/tty` primitive and the G15i own-pty residual), the Restoricon HTTP server (only the in-process authority function and a static route read), multi-process audit append atomicity (thread-level only: `os.fork` is faked), and `os.posix_spawn` (does not exist on this Python, so the canary has 11, not 12, primitives). `socket.bind` is NOT faked in `vc3.py` (the README pre-flight lists it) and the canary did not cover it: the verifier binds only a scratch AF_UNIX socket and two ephemeral 127.0.0.1 ports in-process (D-01..D-11, DEVBR-03), and the Restoricon API server and the real daemon were never started.
* The two real-process legs are the G15i operator scripts under `setsid` with `env -i`, a disposable DB/config and a shim `age-keygen` (all under the scratch root); everything else ran in-process under the recording fakes. The daemon probes use a real `asyncio` unix server on a scratch socket inside the verifier process (the connect fake passes through only AF_UNIX paths under the scratch root and the one ephemeral loopback port the verifier itself bound for the device-bridge test); the server was stopped in-process, no PID was spawned.
* Real `~/.codeyOS` was only `stat`-listed: sizes and mtimes of every entry (and `plugins/*`) are identical before and after (`out/real_before.txt` vs `out/real_now.txt`, diff clean). `git diff --stat` shows no change to tracked files from this unit; the only files written outside the scratch root are `docs/wp2_1_g15z_verify_C3.md` and `.tsv`.
* The snapshot working tree is mutated by the file-tool probes (`zz_*` files, an appended `codeyOS`, a `config.json`); `reset_snaps.sh` removes them and restores `codeyOS` before EVERY script in the final run. An earlier pass of `b6_*.json` was produced while a stray `snap/config.json` from the b2 runs existed; the final `run_final.sh` regenerates all intermediate JSON (b2, b3 census, b6, ops3) from a clean snapshot, so the TSV is from one clean pass of the whole harness (about 60 s). Several probe fixtures were wrong at first (an undersized AGE key, a snapshot-state fake that broke checkpoint creation, a minimal DB without `sqlite_sequence`, a `config.json` name, `CALLS` not cleared) and were fixed and re-run; every row in the TSV comes from the single last `run_final.sh` pass.
* Controls on 941ec3f exist only where a cheap re-run was possible; the daemon IPC, kill-identity, ccos and egress rows rely on positive controls inside the same fixture.
* The static call-site matrix (SITE-01) and urlopen survey (EG-05) only see literal `gate_*`/`urlopen` calls; getattr/indirect calls are invisible (NEW-1009 class).
* `mask_secrets` was exercised with 7 + 3 shapes here; the 35-shape differential is V-C1 (its O12 row covers the line-start `AIGENTIK_INTERNAL_TOKEN=` form only, so GW-10b, the mid-line env-prefix form, does not conflict with or duplicate any V-C1 row).

## Appendix: hunter-C row reconciliation (C:K01..D05)

Legend: V-C3 row ids are in this unit; "V-C1" = `docs/wp2_1_g15z_verify_C.tsv`; "V-A"/"V-C2" = the shell/classifier and bench units; NOT RUN = not exercised by any V-C3 row (named so that a coordinator does not read silence as coverage).

| hunter row | where it was re-verified |
| --- | --- |
| K01, K07 | KILL-01 (scan), CLEAN.K07 in V-C1 |
| K02 | KILL-04, KILL-05 |
| K03 | KILL-02, KILL-03, NEW983-01 |
| K04 | CLEAN.K04 |
| K05 | NEW983-01, NEW983-02, NEW983-03 (the "no audit row for the foreign-kill signal" INTENTIONAL point was not re-read: NOT RUN) |
| K06 | KILL-06 |
| K08 | PEER-05 |
| K09, K10 | KILL-07 (V-C1 also CLEAN.K10) |
| K11 | KILL-08, DSHELL.service stop (FAIL, register-open) |
| M01, M02, M04 | REPL.*, CONFIRMLESS.*, SELFMOD.* |
| M03 | REPL.* (W3 patch), CONFIRMLESS.* |
| M05, M06, M07 | CONFIRMLESS.* (W5 manifest, W7 bench lock, W8 config.json, W10 launcher); V-C1 M05-M07.*; `.codeyignore` and `ccos/data/capabilities.json` writes are V-C1/V-B2 (NOT RUN here) |
| M08 | REPL.repl_notty, REPL.repl_pipey, REPL.pipey_real_confirm |
| M09 | V-A (shell classifier `sed -i` on the gateway); NOT RUN here |
| M10, M11 | EGRESS-01 |
| M12 | CLEAN.M12, TAMPER-01 |
| M13 | TAMPER-01 for rm/truncate/tee/sed/mv/cp/ln/shred of the audit ledger; `sqlite3 <state.db> 'delete from actions'`, `rm <state.db>`, `rm <age.key>`: NOT RUN here |
| M14, M15, M16, M17, M18 | V-A / V-C1 (D-2 credential reads, daemon pip/python flags); NOT RUN here |
| M19 | DSHELL.* (curl, pkill, git status, find / not individually re-run; V-C1 CLEAN.M19) |
| M20 | TDD-01, TDD-02, FIX-01, PB-01 |
| M21, M22 | V-C2 (bench harness env, evaluator tamper); NOT RUN here |
| M23 | V-C1 M23; CC-03 loads the whole tree under a faked supervisor |
| M24 | NOT RUN (manifest limits are metadata only; unchanged by group 15; the census statement stands) |
| M25, M26 | V-C1 (M25, M25b, M26 FAIL, open); V-C3 CC-04, CC-05, CC-06 add name-lookalike, in-dir collision and endpoint rows |
| M27 | CLEAN.M27 in V-C1; NOT RUN here |
| M28 | CC-03 |
| M29 | CONF-01, PEER-04 (`/git push` and `/graph clear` predicates NOT RUN) |
| M30 | SELFLAUNCH-01 (classification only); the TIOCSTI/pty leg is S1b, NOT RUN |
| M31 | D-01, D-02, D-03 |
| M32 | D-07 |
| N01 | EG-02, EG-03 |
| N02 | EG-04, EG-05 |
| N03 | CC-06 |
| N04 | EG-06 |
| N05 | EG-07 (V-C1 CLEAN.N05 too) |
| N06 | OPSCRIPT-01 (`api.server --host 0.0.0.0` is HIGH); the config-driven bind (`restoricon.api_host`) and tunnel-token config reads: NOT RUN |
| N07 | NOT RUN (GCS backup upload; no egress probe of `core/backup_*.py`) |
| N08 | DEVBR-01..DEVBR-03 (V-C1 CLEAN.N08) |
| N09 | NOT RUN (V-C1 CLEAN.N09: library download paths) |
| N10 | EG-05 (urlopen survey only; no `requests/httpx/socket` scan of telemetry/, codey_estimator/, kb_scraper) |
| N11 | OPSCRIPT-01 (`bash setup_repo.sh|install.sh|setup.sh` blocked in confirm-less `shell()`) |
| N12 | PEER-01, PEER-02, PEER-03, PEER-06 |
| C01..C06, C09..C11 | V-C1 |
| C07, C08 | OPS-01, OPS-02 (no-tty legs) |
| D01 | D-09, D-10 |
| D02 | PEER-04, CONF-01 |
| D03 | GW-15, D-11, FLIP-01 |
| D04 | SELFLAUNCH-01, FLIP-01..03 |
| D05 | V-A (opaque interpreters, accepted NEW-904); NOT RUN here |
