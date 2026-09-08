---
name: new268-aigentik-flock-lock-changes-requested
description: NEW-268 start_aigentik flock lock + fd-leak fix, daemon/process-lifecycle ledger closeout sub-batch 3 — bash flock code approved, ledger's own rule-8 handling of a self-found stop-vs-start variant is the defect
metadata:
  type: project
---

Reviewed uncommitted diff: `lib/service_manager.sh`,
`tests/test_service_manager_config.py`, `NEW_ISSUES.md` — sub-batch 3
(last in series) of the daemon/process-lifecycle ledger closeout. Batch 1
was [[new409_new70_daemon_lifecycle_batch1_approved]], batch 2 was
[[new74_stop_noop_batch2_changes_requested]]. First bash-flock-heavy
review in this series (usual review depth here is Python) — read the
whole `start_aigentik` body line-by-line rather than skimming.

**Lock placement/coverage — verified real, not just claimed.** Read
`lib/service_manager.sh:259-407` in full. `flock -n 200` (line 326) sits
*before* the tracked-PID check (331), the orphan scan (342-350), every
early-return branch (353-356, 377-380), the spawn (394), and the
pidfile write (396) — all inside the same `(...)` subshell (317-405),
so the lock genuinely covers the entire check→scan→spawn→verify→write
sequence the original race needed unlocked, not a partial subset. The
whole thing is one subshell, so every exit point (`exit 0`/`exit 1`
inside it) auto-releases fd 200 — no explicit unlock code, and none
needed given bash's subshell fd semantics.

**fd-leak claim and its fix — independently reproduced, not trusted on
description.** The implementer's claimed self-caught bug (forked
long-lived node child inherits fd 200, permanently holds the flock for
its whole runtime) is real bash fd-inheritance behavior, not
hypothetical. I ran my own negative control (not just accepted the
implementer's claimed one): copied the file, stripped only the
`200>&-` off the spawn line (`(cd "$a_dir" && exec nohup $entrypoint ...)
&` with no `200>&-`), ran
`test_sequential_restart_after_start_still_reports_already_running`
against that broken version — it failed with exactly the predicted
`another start already in progress` message on the second invocation.
Restored the file, reconfirmed both new tests pass. `200>&-` sits on
the redirection list of the `( cd ... && exec nohup ... ) 200>&- &`
subshell — since that's a separately-forked subshell (not the same
process as the outer lock-holding subshell), the close applies to the
forked child before its own `exec nohup` replaces its image, so the fd
is genuinely gone before the long-lived process starts. No subshell
scoping gotcha here — this is the one case in the diff where a nested
`(...)` boundary is being used correctly, not accidentally.

**Concurrency test — independently negative-controlled, not just
skimmed for plausibility.** Reverted `lib/service_manager.sh` to the
pre-fix `HEAD` version (via `git show HEAD:...`) and ran
`test_concurrent_start_aigentik_no_pid_file_race` 10 times against it:
**10/10 failed**, cleanly and non-flakily, confirming the test is a
real discriminator of the fixed vs. unfixed race, not a test that
happens to pass either way (unlike the false-confidence pattern this
project has hit before, e.g. [[new187_swap_dispatch_fail_closed_round2_approved]]'s
concern about tests that look concurrent but aren't). Restored the
fix, reconfirmed 2/2 pass. The concurrency test genuinely launches two
OS-level subprocesses from two Python threads (`subprocess.run` blocks
inside each thread, which releases the GIL while waiting) — real
process-level concurrency, not an illusion of it.

**Guarded-`exec` degrade-safe comment — verified accurate, not just
plausible.** The comment at line 318-321 claims the `if !
exec 200>"$lock_file" 2>/dev/null` guard is needed because callers
source this under `set -e` and an unguarded `exec` redirection failure
would otherwise abort. Ran
`bash -c 'set -e; ( if ! exec 200>/proc/nonexistent/x 2>/dev/null; then
echo GUARD_WORKED; exit 0; fi; echo REACHED_PAST )'` directly —
printed `GUARD_WORKED`, `rc=0`. Confirms the `if !` construct genuinely
intercepts the redirection failure and prevents `set -e` from aborting
the subshell; the comment's rationale is real, not just plausible-sounding.

**`install.sh`/rule 11 — verified, not assumed.** `apt-cache show
util-linux` and `dpkg -s util-linux` on this device both report
`Essential: yes`; `flock` resolves via `which`. `util-linux` genuinely
ships as part of every Termux bootstrap regardless of `install.sh`'s
`pkg install` line — no `install.sh` change needed, matches the
ledger's own reasoning, independently confirmed rather than taken on
faith.

**Full suite:** independently ran `python -m pytest tests/ -q`,
confirmed literal `1508 passed, 1 skipped in 294.95s` — matches the
implementer's ledger claim exactly (this project's rule 5 standard).
Also ran the two new tests 5x each in isolation with no flakiness.

**The one real defect — a rule-8 handling error, not a code bug.** The
ledger's own note flags `stop_aigentik`/`status_aigentik` as remaining
unlocked and explicitly declines to file a `NEW-###` entry for it,
reasoning "it's a theoretical gap, not a confirmed finding." That
inverts CLAUDE.md rule 8, which exists precisely to cover this case —
"logged to NEW_ISSUES.md (rated Confirmed or **Suspected** based on
actual certainty)... not silently fixed or silently dropped." Suspected
is exactly the right rating for a reasoned-but-unobserved mechanism;
declining to file *because* it's reasoned-not-observed is backwards.
And this isn't vague — I read `stop_aigentik` in full
(`lib/service_manager.sh:409-466`): it runs `svc_stop_by_pid`, then an
unlocked orphan scan (`svc_find_orphans_by_cwd`) that TERM/KILLs
anything matching cwd+entrypoint token that isn't the tracked PID
(437-455). A concurrent `start_aigentik` mid-spawn (after `nohup &` but
before the PID file write, now serialized against *other starts* by
the new flock but not against a concurrent `stop`) presents exactly the
untracked-fresh-child signature `stop_aigentik`'s scan is designed to
kill — the identical failure mechanism as NEW-268 itself, with `stop`
as the second actor instead of another `start`. This should be filed
as a new Suspected finding (next available ID is `NEW-412`) describing
this exact mechanism, not silently omitted with an inverted
Confirmed-only reading of rule 8.

Verdict: **CHANGES REQUESTED (ledger-only)**. `lib/service_manager.sh`
and `tests/test_service_manager_config.py` are both correct and
approved as-is — no code changes needed. Before commit, `NEW_ISSUES.md`
needs the start-vs-stop race filed as a new Suspected `NEW-412` entry
(mechanism as described above) instead of the current "not filed since
theoretical" framing, which contradicts rule 8's own text.
