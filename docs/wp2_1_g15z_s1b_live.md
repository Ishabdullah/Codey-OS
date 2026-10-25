# WP2.1 G15z stage S1b - live pty verification (2026-10-24)

Tree: HEAD b230ce9 + approved-uncommitted S2 units. Full rows (verbatim pty
excerpts, per-row evidence): `docs/wp2_1_g15z_s1b_live.tsv` (62 rows: 59 PASS,
3 FAIL, 0 BLOCKED-BY-SAFETY, 0 INCONCLUSIVE). Harness (scratch, not in repo):
`/data/data/com.termux/files/usr/tmp/s1b/` (h.py = pty runner; c1/c2/c23/c4*/c5/c6* = checks).

Method: every check ran a fresh interpreter as a `pty.fork` child (real controlling
tty, TIOCSWINSZ 50x250, SIGINT reset to default) or, for no-tty cases, a
`start_new_session=True` pipe child / a pty-slave-on-stdio child with `setsid` and no
ctty. Per-check disposable HOME, CODEY_STATE_DIR, CODEY_ACTION_GATEWAY_AUDIT,
CODEY_CONFIG_PATH, RESTORICON_DB_PATH, GIT_CONFIG_GLOBAL; proxy vars removed from env.
No model loaded (llama-server absent before and after). Tokens and the fake private key
are replaced in the TSV by `<TOKEN len= sha256=>` / `<FAKE-PRIV len= sha256=>` markers.

Baseline `free -h` (once, before): Mem 10Gi total, 6.0Gi used, 240Mi free, 4.9Gi buff/cache, 4.8Gi available; Swap 15Gi, 2.7Gi used.
After: Mem 6.1Gi used, 771Mi free, 4.7Gi available; Swap 2.7Gi used. (Load avg was 13 from other agents' work.)
Real-path safety: `~/.codeyOS/action_gateway_audit.jsonl` stayed `50348 2026-10-24 11:55:11.609089678 -0400`
before and after; ~/.bashrc, ~/.gitconfig, ~/.ssh/*, repo config.json size+mtime unchanged
(stat list diffed against pre-run baseline). No leftover s1b processes after the run.
Preflight probes: pty child has `/dev/pts/3` as fd 0, is foreground pgrp, `/dev/tty` opens; the setsid/pipe child gets ENOTTY on ttyname and
no /dev/tty (also see 4.*.noctty_ttystdout for the ENXIO path with a tty-looking stdout).

## Verdicts

| Check | Result |
|---|---|
| 1 G15j write/append, new F3 target (install.sh, lib/x.sh), pty | PASS all: prompt shows `(HIGH_IMPACT). [y/N]:`; y writes (write: `Written`, append: `Created`); Enter, n, `zzz` then n all refuse (`[BLOCKED] Human confirmation declined`, audit HIGH_IMPACT/refused); garbage re-prompts once; 697-char path shows head + `...` + tail ending `x.sh`; pre-buffered `y\n` NOT consumed (child still alive 2s later, then `n` refused); fake ~/.bashrc => `[ERROR] Access denied: ... protected path (home-startup)`, no prompt, audit authority HIGH_IMPACT outcome failed (this is the DENY tier, not an out-of-workspace message) |
| 2 same, stdin pipe 'y' | PASS: no prompt, `[BLOCKED] ... declined`, `LEFTOVER_STDIN:b'y\n'` (never read), file absent |
| 3 legacy `Overwrite X?` / `Apply patch?` | PASS: y and yes approve and change the file; n and Enter refuse and leave it unchanged; pipe 'y' does not approve, y left unread |
| 4a provision_ai_agent_auth (--db-path + RESTORICON_DB_PATH disposable) | PASS: n and Enter => rc 2, DB not created; y => rc 0, exactly one token line, DB created, 1 unrevoked row; second y => `Revoked 1 prior token(s)`, 2 rows (old is_revoked=1, new 0), new token differs; setsid+pipes => rc 2 empty stdout no DB; pty stdio without ctty => rc 2 no DB. Disposable audit ledger gained rows (env honoured) |
| 4b setup_dr_key (disposable CODEY_CONFIG_PATH + SHIM age-keygen; probe confirmed both resolved to disposable before any y) | PASS: n/Enter => rc 1 config byte-identical, shim never ran; y => rc 0, pubkey only in config (other keys preserved), fake private key shown once on pty, not in any scratch file; stdout piped => `Refused: stdout is not a terminal`, shim not run; already-configured no --force => no prompt; no-tty variants refused (rc 1) |
| 5 D-4 peer confirm/escalate (fake peer, stubbed call, PATH shims for qwen/claude/codex/agy never invoked) | PASS for Enter/n skip, y proceeds to stub exactly once, piped y skipped unread. FAIL for typeahead (below) |
| 6 /git checkout, /git commit via main.handle_command (tmp repo, fake commit-message generator, inference/loader tripwires; repo toplevel asserted) | checkout PASS all (y switches; Enter/n cancel; pipe/ typeahead y not consumed). commit: Enter-at-prompt commits suggestion (by design), typed message commits it, pipe => `Commit cancelled: no interactive terminal` with no generation, ^C => `Commit cancelled.`. FAIL for stale-Enter typeahead (below) |
| 7 NEW-996 real ^C (`\x03` on master) | Returns False without a traceback and the child exits rc 0 at utils.logger.confirm, Overwrite? and Apply patch? (and at the /git commit input()). ANOMALY below |

## Anomalies and failures (contradict "nothing buffered can approve")

1. **5.escalate.typeahead_y FAIL**: `y\n` written to the pty before the peer prompt appears is
   consumed by `PeerCLIManager.confirm` (console.input, no tcflush) and approves the peer
   dispatch (`STUB_CALLS:1`, `Peer CLI (fakepeer) done`). Code read agrees: core/peer_cli.py
   confirm() has no typeahead flush, unlike utils.logger.confirm / tty_confirm. This is the
   HIGH_IMPACT peer-egress approval.
2. **6.commit.typeahead FAIL**: a stray Enter buffered before the `Press Enter to accept`
   prompt (bare `input()` in main.py handle_command) accepts the suggestion and commits
   (`HEAD_SUBJECT:feat: fake suggested message`). Same cause: no flush. Since Enter is the accept key there, a stale newline equals approval.
3. **7.ctrlc_delay_note FAIL (expectation: prompt return on ^C alone)**: after `\x03` the pty echoes
   `^C` but the child stays blocked (alive after 6s and 8s idle, no RESULT line) until the next
   keypress; then confirm returns False / "Commit cancelled." cleanly. ISIG, ICANON, VINTR=\x03
   were set. SIGINT is flagged but Python's readline wait does not wake; a user must press Enter
   after ^C. Not a bypass (no approval results), a UX/robustness finding.
4. Harness notes (not product bugs): an early run hit racy-git (same-size edit within the same
   second) and slow import under load avg 13; those rows were discarded and re-run.

## NOT proven

- The real /dev/tty on Ish's attended Termux session (pty from Python master, not the Termux app terminal emulator); Ctrl-C and typeahead semantics under the actual Termux app keyboard path.
- `setup_dr_key.py` with the REAL age-keygen (shim only; the DR key creation is PENDING ISH, never run). Real age-keygen output format beyond the shim.
- Real peer binaries (claude/qwen/codex/agy) and the real peer_shell dispatch; only a recording stub of PeerCLIManager.call was exercised.
- `--force` on setup_dr_key, other G15i/S2 guards not listed, LoRA adopt/rollback (NEW-977) live, Aigentik/Core HTTP paths, the live Restoricon DB (never opened).
- /git push, /git merge confirm and the model-backed commit-message generator (faked; no model loaded).
- The ENXIO-for-tty-stdout case for provision/DR used a pty slave with no ctty; the daemon/launcher spawn path was not exercised.
