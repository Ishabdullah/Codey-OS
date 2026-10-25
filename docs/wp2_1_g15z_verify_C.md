# V-C1: plugin manifest authority and credential exposure (WP2.1 G15z verify, stage S1)

Verifier: independent (did not write the code under test). Subject: `git archive HEAD` (b230ce9) at `$G15Z_OUT/C/snap`
(`G15Z_OUT=/data/data/com.termux/files/usr/tmp/g15z_verify/VC1`). Controls ran the identical probe on pre-fix snapshots: `snap_before`
= 9a61e94 (plugin and redaction/token-chain controls), `snap_census` = 941ec3f (shell, file-tool and operator-script controls, the hunter-C census base).
Rows: `docs/wp2_1_g15z_verify_C.tsv` (88 rows). Raw results: `$G15Z_OUT/C/out/` (`res_*.json`, `chain_*.txt`, `fail_*.txt`, `ops.txt`). Harness: `$G15Z_OUT/C/harness/`.
Status: COMPLETE (an earlier session cutoff interrupted the run; finished rows were reused, not redone). Tier: verified on disposable fixtures only.

## Summary

| verdict | count |
| --- | --- |
| PASS | 73 |
| ACCEPTED-RESIDUAL | 10 |
| FAIL | 5 |
| BLOCKED-BY-SAFETY | 0 |
| INCONCLUSIVE | 0 |

Every PASS that has a control reproduced the original weakness on the pre-fix snapshot (so the probe can fail); the row text carries the CONTROL result. Rows tagged as new defensive probes: 31 (cap 40).

**No claimed fix regressed.** Closed at HEAD with a reproducing control: entry_point containment (absolute, `..`, symlink, in-dir absolute; both the manager and the supervisor fallback), symlinked plugin/category dir/manifest, duplicate names (both sort orders and across two roots), capability collisions (B:PL-05), the M25 system.info name claim against the real tree, spawn audit (allowed/failed/refused rows, secret-free), cloudflared token argv (child, helper and bash cmdline and `ps` all clean; token only in the child's environ), masking of all 15 original shapes plus 6 G15h-added and 14 further shapes through six sinks, `system.processes`, D-2 credential reads through shell/daemon/file tools, credential-path writes, manifest-write to spawn chain in repl and yolo, operator-script guards (no tty).

## FAIL rows (all five are findings the register does not claim fixed, or a new low gap; none is a regression of a shipped fix)

* **M25b** (G15b-43 rest, OPEN-UNCLAIMED): an evil plugin alone in its own `plugin_dirs` claims `system.info`; `call_capability` dispatches it (READ authority by name). Collision refusal only sees the manager's own dirs. Not reachable through the default manager unless a plugin is planted into `ccos/plugins` (where the collision refusal does fire, row PL-M25 PASS).
* **M26** (C:M26, OPEN-UNCLAIMED): `coding.run_agent` accepts `confirm_shell=False`, `shell_fn`, `yolo=True` kwargs through `call_capability`; inner agent saw them. Global `AGENT_CONFIG` unchanged afterwards. Register says untouched.
* **M07.repl / M07.yolo capabilities_json** (B:PL-04, queued for V-B2): `write_file ccos/data/capabilities.json` succeeds with no prompt in a non-tty REPL and under `--yolo` (not HIGH-classified). Not claimed fixed.
* **NEW.norm.zero_width** (new, LOW): plugin names `agent` and `agent​` both load and stay active; the duplicate key is NFKC+strip+casefold, which does not remove zero-width format characters. Full-width, case and trailing-space variants ARE refused. Impact is name impersonation only (lookups and capability names are exact strings).

## ACCEPTED-RESIDUAL (label means: documented and not claimed fixed; evidence states the register position)

Plugin child inherits the whole environment (G15b-11 plugin side; 69 of 69 names visible to the child, `VC1_CANARY_TOKEN` included; the audit row records `env_policy=inherit-all`); `start_command` arbitrary with an attributable row (R1/NEW-1054); `--yolo --allow-self-mod` unlocks HIGH writes incl. manifest then spawn (G15b-36, D-1); `.codeyignore` writable (intended); `read_file('.env')` allowed (G15b-39); in-dir symlink entry allowed (R6); Cyrillic homoglyph name not caught; own-pty script answering `y` mints a token and prints the DR key to its own pty (NEW-1071; done with disposable DB/config and a shim `age-keygen`).

## Coverage by brief item

* Manifest entry_point escapes, symlinks, duplicate names, capability collisions, spawn audit: PL-01..PL-18 (controls reproduce all).
* Whole-env inheritance: PL-16 (ACCEPTED-RESIDUAL). Spawn row names env keys only: PL-15 (canary values absent, names present).
* Cloudflared token: C05, TOK-env, PROV-fail (stub binary, throwaway age key, fabricated canary, only `lock-exec cloudflared start|stop`; cmdline checks limited to the verifier's own chain plus `ps -A -o pid,args`). Provider failure paths (exit-fast stub, missing binary, corrupt `.age`, age absent): no canary anywhere; the pre-fix snapshot was also clean there (no differential; the failure-path class was latent). Note my "badkey" case degenerated to exit-fast because `age-keygen -o` refused to overwrite.
* Redaction: 16 original-shape rows (O01..O16 plus bearer value), RD.added6, RD.new14, ReDoS (max 0.19 s for `sessions.redact_secrets`, 0.18 s `mask_secrets`, 1.46 s `find_secret` at 1 MB), fail-closed marker, truncation, benign negatives unchanged, C11.
* D-2 credential reads: C02, C03, D05, M14, C04a/b, D1w. Operator scripts: G15i-B.prov, .dr, .pty. M05-M08 and M06: M05-M07.*, M06.*. M23 REPL startup load_all: PASS (two `failed` ACT rows for private_agent and aigentik under a recording Popen).
* 11 previously clean rows re-checked (CLEAN.*: K07, M12, M13, K10, M19, C10, C09, N09, M27, N08, N05): all hold. They were selected by hand (deterministic, not random) from LOW-rated hunter rows.

## Honest limits and what was not run

* Real `aigentik` and `private_agent` manifests were NOT exercised for spawn; M23 used a recording Popen (both would currently fail to start: `agent.py` absent, `aigentik.server` not importable). The real token, `age.key`, `~/.codeyOS` contents and the real tunnel were not touched. Real `~/.codeyOS/plugins/*.pid` and `action_gateway_audit.jsonl` size+mtime verified identical before and after (`out/real_before.txt`; diff clean).
* Not run: C07 real credential mint (only disposable-DB script runs), real DR key creation, C06/N03/N06/N07 network or backup rows, M21 bench env (V-C2), M24, M28, M29-M32 (V-C3), C01 for shell children beyond the plugin child, a trajectory/telemetry/checkpoint sink masking audit (G15h-B documents these as not covered, NEW-1060/1066), and any real-tty prompt (the `/dev/tty` path is only exercised through pty.fork).
* Controls for credential rows use 941ec3f, which predates G15d; they prove the probe can fail, not which later slice fixed which form. The pre-fix snapshot for spawn rows is 9a61e94.
* Shell/credential outputs were scrubbed of ambient environment first (the harness cleared `os.environ` and planted FAKE secrets), so no real value could be printed. The census-snapshot runs executed `cat`, `cp`, `ps aux` etc. inside the scratch HOME only.
* Row-completeness: a non-string `entry_point` is rejected at staging (status broken) with no audit row (by spec; noted in NEW.rows). Re-discovery writes one new refusal row per pass (expected).
* Count of verdicts is by row; grouped rows (C03, C02, M14, D1w, NEW.edge, RD.new14, ...) hide per-member detail, which is in the observed column and the JSON.
