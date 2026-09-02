---
name: service-manager-aigentik-orphan-cwd-changes-requested
description: lib/service_manager.sh svc_find_orphans_by_cwd orphan-kill for Codey-Aigentik — round 1 CHANGES REQUESTED (cwd-alone ownership weaker than logged precedent; committed PROJECT_LOG entry falsely claims approval)
metadata:
  type: project
---

Round 1 review 2026-09-02 of uncommitted net-new `svc_find_orphans_by_cwd()` +
rewritten `start/stop/status_aigentik` in `lib/service_manager.sh`.

## Verdict: CHANGES REQUESTED

### Blocker 1 (code) — cwd-alone ownership regresses from the project's own written method
`svc_find_orphans_by_cwd` finds candidates via `pgrep node` / `/proc` fallback,
keeps only PIDs whose `/proc/PID/cwd` == canonical Aigentik dir, then TERM/KILLs.
PROJECT_LOG.md ~line 182 (committed, teardown disclosure) records the project's
standard for this exact problem: `/proc/*/cmdline` **exact entrypoint match PLUS
a session-unique path**, `PPid: 1` as reparent confirmation. Shipping a
single-factor gate + SIGKILL in Rule 4 territory is a block. Fix: thread the
entrypoint basename (`index.js`/`main.py` — caller already computes `$entrypoint`)
as a 3rd arg, add a cmdline substring check in the existing per-PID loop. Also
makes the pgrep-vs-/proc candidate divergence moot and the header's Rule 3 claim true.

### Blocker 2 (doc, rule 6/7/5) — committed PROJECT_LOG entry claims approval that never happened
`2026-09-01 — Service Manager: Prevent Orphaned Codey-Aigentik Processes` entry
(committed ~bbca994) says "code-reviewer approved, live-verified on-device
(19/19 passed)" for code that was uncommitted and unreviewed until this review.
`19/19` is a unit-test pass sold as live verification. "Live On-Device
Verification" bullets claim real rogue-process kills in `~/Codey-Aigentik` with
zero verbatim output / no `free -h`. Must be retracted to "code-complete,
under review".

### Required test fix
`test_start_and_stop_aigentik_cleans_orphans` never asserts a fresh instance
started — orphan-died + "0 remaining" both hold if `start_aigentik` launched
nothing. Add: read `$AIGENTIK_PID_FILE` after start, `kill -0` it.

## Resolved / not blocking
- `exec nohup $entrypoint` PID capture is CORRECT — verified with throwaway:
  `$!` = real process PID (coreutils nohup execs, doesn't fork; subshell exits →
  reparented). Genuinely fixes the subshell-PID bug from the teardown disclosure.
- Killing tracked instance's own node children: latent only — current index.js
  uses execSync (python3/termux-contact-list), no node workers. Warning: any
  future `child_process.fork` → start's already-running path kills workers,
  leaves parent.
- `stop_aigentik` no tracked-PID exclusion: fine, `svc_stop_by_pid` runs first.
- kill-loop `kill -0`→`kill -9` TOCTOU: same shape as pre-existing
  `svc_stop_by_pid`, Suggestion (see [[new83_embed_server_kill_by_pid_approved]]).
- Concurrent `codey-start` race: B reads empty PID file → scan catches A's
  just-spawned node → kills it → A's failed `kill -0` does `rm -f PID_FILE`
  deleting B's entry → manufactured orphan. Low likelihood (manual entry point);
  Warning, worth a guard.
- `/proc` fallback branch: dead/untested on this device (pgrep present). Log to
  NEW_ISSUES, don't block.
- NEW_ISSUES.md unmodified — nothing logged despite rule-8-worthy sub-findings.
- Commit scoping: stage only `lib/service_manager.sh` + the test by name; the two
  tracked `*.pid` files churn from unrelated plugin runs.

## Round 2 (2026-09-02): APPROVED
- Two-factor gate added: `svc_find_orphans_by_cwd` 3rd arg `entrypoint_token`;
  match is `case " $proc_cmd " in *" $tok "*|*"/$tok "*`. Verified: matches
  `node index.js` and `node /path/index.js`, rejects `node decoy.js`. Token
  comes from fixed whitelist (`svc_detect_entrypoint_script`) so no glob-meta risk.
- Empty-token → cwd-only path retained only for the 2-arg mechanism test; all 3
  real call sites guard (`start` on `$entrypoint`, `stop`/`status` on `$entry_script`)
  and fall back to PID-file-only report. `svc_stop_by_pid` still runs before the
  guard in `stop`, so tracked PID is always killed.
- New negative test `..._requires_entrypoint_match` (real vs decoy node) proves it;
  start/stop test now asserts fresh PID file holds a live distinct PID whose
  cmdline contains index.js, and that it's gone post-stop. 20/20 pass, bash -n clean.
- PROJECT_LOG entry corrected with explicit Rule 6 note; false approved/live-verified
  claims removed. NEW-268 (concurrent start race, comment at spawn site, no lock this
  round), NEW-269 (dead /proc fallback + unanchored =~), NEW-270 (python3 per
  status/stop call), NEW-271 (proc_filter hardcoded `node` misses py/sh entrypoints)
  all logged. All acceptable as out-of-scope-logged.
