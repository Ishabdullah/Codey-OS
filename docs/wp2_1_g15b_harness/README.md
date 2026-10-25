# Retained G15b hunter repro harness (941ec3f baseline)

**Not product code. Never import into `tests/`. Do not run casually.**

## Origin and purpose

Copied (Stage S0, Z-3, Ish approved) from the volatile scratch dirs
`/data/data/com.termux/files/usr/tmp/g15b/{A,B,C}` used by the three G15b hunters
(reports: `docs/wp2_1_g15b_hunter_{A,B,C}.md` + `.tsv`), which targeted baseline commit
**941ec3f**. They exist so the G15z verify stage (`docs/wp2_1_g15z_spec.md` section 2)
can re-run the probes on a HEAD snapshot instead of rebuilding them from the TSV `input`
columns.

* `A/` : `harness.py`, `probes.py` (267 shell/daemon probes), `run_probes.py`
* `B/scripts/` : `common.py`, `p1..p17`, `p1b`, `imp_driver`, `imp_child`, `rowcli`, `mkrows_p2`
* `C/` : `h.py`, `p1..p20`, `rows1`, `rows2`, `writeall`
* `g15z_guard.py` : the output-directory guard every script goes through.

The originals were copied, not moved or edited. Only the copies here were changed, and only
to re-point paths (see below). Probe logic is otherwise verbatim.

## The hazard that was removed

In the originals, `A/run_probes.py` opened the committed `docs/wp2_1_g15b_hunter_A.tsv` with
mode `"w"` (truncating it), `B/scripts/common.py` appended to the committed hunter-B TSV,
and `C/h.py` / `C/writeall.py` appended to, then `os.remove`d and rewrote, the committed
hunter-C TSV. Running them from a repo checkout would have destroyed committed evidence.

In these copies every work root and output file comes from `g15z_guard.work_root()` /
`tsv_path()`, which **refuses to run** (exit 2) unless `G15Z_OUT` is set to an absolute path
that resolves outside the repo (so outside `docs/` and every tracked path), is not `HOME` or
an ancestor of `HOME` or of the repo, and is not trivially shallow. Layout:
`$G15Z_OUT/{A,B,C}/{snap,home,state,ws,work,out,logs,hunter_<X>.tsv}`. `snap/` (the tree
under test) must be created by the caller; the scripts treat it as scratch and some
scripts write into it and `rmtree` subdirectories of it, so it must be a disposable copy,
never the real repo. `C/p17.py` previously hard-coded the real repo path in classified
command strings; it now uses the scratch `SNAP`.

Some probe strings still contain real absolute paths (for example `/data/data/com.termux/files/home/restoricon`,
`/data/data/com.termux/files/home/.ssh`, `.../Codey-OS/main.py` in `B/scripts/p6.py`,
`C/p4.py`, `C/p9.py`, `C/p15.py`, `C/p20.py`, and `A/probes.py` `H`). They are inputs to a
classifier or to a recording fake, not write targets. Keep it that way.

## How to run safely (when a verifier does so)

1. Disposable environment, all under one scratch dir outside the repo:
   `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy
   HOME=<scratch>/home CODEY_STATE_DIR=<scratch>/state
   CODEY_ACTION_GATEWAY_AUDIT=<scratch>/state/audit.jsonl G15Z_OUT=<scratch>/out python3 -I ...`
   (`-I` ignores user site and PYTHON* vars; the scripts add their own paths.)
2. Build `$G15Z_OUT/<X>/snap` as a copy of the tree under test (HEAD snapshot), plus the
   `ws`/`home`/`state` directories the script `chdir`s into.
3. Recording fakes only. No real grader, no model load, no network, no real bench run.
   Probe inputs are strings handed to a classifier or fake-recording functions; nothing
   dangerous is executed.
4. Never point `G15Z_OUT` at the repo, and compare the committed
   `docs/wp2_1_g15b_hunter_*.tsv` with `git diff --stat` after any run (must be empty).

## Pre-flight required before trusting any run (recorders are stale)

The recorders were written against **941ec3f**. Spawn and execution paths have since moved
(for example G15d/G15e/G15f/G15i changes, the `TaskExecutor._daemon_shell` route, and any new
`subprocess`/`os`/`socket` use sites). A recorder that no longer covers a primitive will let a
probe really execute. Before importing any module from the snapshot:

1. Confirm every primitive is patched BEFORE the first import of snapshot code:
   `subprocess.run/Popen/call/check_output/check_call`, `os.system/popen/exec*/spawn*/fork/kill/killpg`,
   `socket.socket.connect/bind`, `socket.create_connection`, `urllib.request.urlopen`,
   `http.client.HTTPConnection.connect`, and grep the snapshot for any other spawn
   primitive (`asyncio.create_subprocess_*`, `pty`, `ctypes`, `os.posix_spawn`, `multiprocessing`).
2. Run a canary probe through the same path (a command that would leave a visible
   marker, such as touching a file under `$G15Z_OUT`) and prove the marker does NOT appear and
   the call was recorded.
3. Only then run the real probes. If the canary fails, stop and report; do not push on.
   (`B/scripts/imp_driver.py` imports every module of the snapshot and `C/p6.py`
   starts a real disposable `python3 -I -c time.sleep` process; own and tear down any such
   child by PID only, never by name pattern.)
