# Project Log: Codey-v3 + CCOS

Reverse-chronological. Add a new entry at the top after every meaningful
change, decision, or Qwen task completion.

---

## 2026-07-30 — Round 6 (NEW-5) live-verification: genuine mid-load SIGINT confirmed handled, FULLY LIVE-VERIFIED

**What was verified:** live-verifier independently reproduced a genuine
mid-load `SIGINT` against `main.py`'s `repl()` to confirm commit
`eed29dc`'s fix (a `try/except (KeyboardInterrupt, SystemExit)` around
`loader.load_primary()` that calls the existing `shutdown()` and returns
cleanly) actually closes `NEW_ISSUES.md` [NEW-5], and that this closes
code-reviewer's one open Warning on this fix — that live-verification
output wasn't yet recorded when it approved the diff.

**Baseline `free -h`:**
```
               total        used        free      shared  buff/cache   available
Mem:            10Gi       4.2Gi       892Mi        11Mi       5.7Gi       6.3Gi
Swap:           11Gi       2.0Gi         9Gi
```

**Test 1 — genuine mid-load SIGINT, via `pty.fork()` (tracked child PID
30600, not `timeout`, not a name-pattern kill):** `llama-server`'s own
child PID (30603) confirmed in its own process group (`preexec_fn=
os.setsid`). `SIGINT` sent directly to PID 30600 at t=0.88s, before
`llama-server` finished loading:
```
CHILD_PID=30600
ℹ  Loading model: qwen2.5-coder-7b-instruct-q4_k_m.gguf
ℹ  Starting llama-server...

>>> SENDING SIGINT to 30600 at t=0.88s
ℹ  7B model: mmap=enabled, mlock=disabled
ℹ  llama-server PID: 30603, logging to /data/data/com.termux/files/home/.codeyOS/llama-server.log

Interrupted during model load, cleaning up...
ℹ  Stopping model server...
```
Post-interrupt check:
```
ps -eo pid,ppid,pgid,comm | grep -E "python|llama"   -> (empty, no matches)
free -h
               total        used        free      shared  buff/cache   available
Mem:            10Gi       3.3Gi       4.3Gi        16Mi       3.2Gi       7.3Gi
Swap:           11Gi       2.2Gi       9.8Gi
```
No leak, no orphan — process fully reaped, RAM recovered. (An earlier
attempt, backgrounded via `setsid ... &` with stdin redirected from
`/dev/null`, was voided by live-verifier itself as inconclusive: the
model loaded fast enough that the process hit an immediate EOF on
`/dev/null` stdin and exited on its own before the `SIGINT` command ever
ran. Reported transparently as void, not counted as a pass.)

**Test 2 — regression check, normal-completion cycle** (sequenced after
Test 1's model confirmed fully unloaded, per the one-model-load-cycle-
at-a-time rule): model loaded fully, one real inference message sent
("what is 2+2? answer in one word"), model responded "4" (`Chat
completions (stream): 2 tokens in 12.3s (16.1 t/s)`), clean `/exit`:
```
/exit
Session saved. Goodbye!
ℹ  Stopping model server...
```
Post-exit check:
```
ps -eo pid,ppid,pgid,comm | grep -E "python|llama"   -> (empty)
free -h
               total        used        free      shared  buff/cache   available
Mem:            10Gi       2.7Gi       6.0Gi       7.0Mi       2.1Gi       7.8Gi
Swap:           11Gi       2.3Gi       9.7Gi
```
Peak RAM during inference reached 9.0/10.8GB per live monitor; device
stayed responsive, no swap thrashing.

**Overall verdict:** fix confirmed working under a genuine `SIGINT`
during model load; no regression on the normal completion path.

**Docs updated:** `NEW_ISSUES.md` [NEW-5] moved to **Resolved**, citing
`eed29dc` and this live-verification. `PROJECT_PLAN.md` Round 6 entry
upgraded from "code complete, code-reviewer approved" to **code
complete, code-reviewer approved, and independently live-verified**, per
Ground Rule 7 — this closes code-reviewer's open Warning about missing
live-verification output.

**Round 6 (NEW-5) is now fully closed.** Of the user's original
four-item punch list, NEW-3, NEW-1, and NEW-5 are now all done; NEW-2
remains as Round 7, the hardest and final item. `NEW_ISSUES.md` [NEW-6]
(same unguarded `load_primary()` pattern at three sibling call sites in
`main.py`) remains open, Suspected, unscoped — not part of this round.

---

## 2026-07-29 — Round 6 (NEW-5): guard against `KeyboardInterrupt` during model load in `repl()`, CODE COMPLETE

**What changed:** `main.py`'s `repl()` (commit `eed29dc`, ~line
1267-1274) now wraps the `loader.load_primary()` call in a
`try/except (KeyboardInterrupt, SystemExit)` that prints an interrupted-
during-load message, calls the existing `shutdown()` (`main.py` ~line
125-144, unchanged), and returns cleanly — closing `NEW_ISSUES.md`
[NEW-5]'s root cause (a `KeyboardInterrupt` during model load previously
propagated straight out of `load_primary()` uncaught, since
`core/loader_v2.py`'s own handler is `except Exception`, which does not
catch `BaseException` subclasses, and `llama-server` is spawned via
`preexec_fn=os.setsid`, insulating it from terminal signal delivery and
leaving it a genuine indefinite orphan with no other teardown path):
```python
if not is_remote_backend():
    loader = get_loader()
    try:
        loader.load_primary()
    except (KeyboardInterrupt, SystemExit):
        console.print("\n[dim]Interrupted during model load, cleaning up...[/dim]")
        shutdown()
        return
```
Reuses the existing scoped-PID `shutdown()` path unchanged — no new kill
logic introduced. Scoped to just the `repl()` call site, the one
actually live-reproduced in Round 6's root-cause investigation;
`NEW_ISSUES.md` [NEW-6] tracks the same pattern at three other call
sites as a separate, unscoped follow-up.

**Review:** code-reviewer approved, with one Warning: live-verification
output for this fix wasn't yet recorded in `PROJECT_LOG.md`. That Warning
is closed in the entry above this one.

**Verification status at commit time:** CODE COMPLETE, code-reviewer-
approved — not yet live-verified (see entry above for the live-verifier
pass that closes this out).

---

## 2026-07-29 — Round 5 (NEW-1) live-verification: full `pytest tests/` suite confirmed clean, FULLY LIVE-VERIFIED

**What was verified:** live-verifier ran the full test suite (not just
`tests/test_memory.py`, which is all code-reviewer had re-run in Round
5's original approval) to confirm commit `c65be95`'s fix fully closes
`NEW_ISSUES.md` [NEW-1] (orphaned real 7B `llama-server` from
`tests/test_memory.py::TestMemoryCompressSummary::test_compress_summary_handles_inference_failure`
running unmocked).

**Result:** `pytest tests/ -q` → **253 passed in 0.43s** (previously
~42s, consistent with the hidden real 7B model load this fix removes).
No orphan `llama-server` process remained after the run, confirmed via
`ps -eo pid,ppid,comm | grep llama` (deliberately not `pgrep -af`, which
has a false-positive self-match issue in this shell environment — the
wrapper's own command-line text matches the `llama` pattern and gives a
misleading "still running" hit). `free -h` was stable before/after (563Mi
free → 816Mi free; swap unchanged at 1.6Gi).

**Docs updated:** `NEW_ISSUES.md` [NEW-1] moved from "fix committed,
pending full-suite live verification" to **Resolved**. `PROJECT_PLAN.md`
Round 5 entry upgraded from "CODE COMPLETE, not yet fully live-verified"
to **FULLY LIVE-VERIFIED**, per Ground Rule 7.

**Round 5 is fully closed.** Next up: Round 6, scoping `NEW_ISSUES.md`
[NEW-5] (`llama-server` possibly outliving `gui/start.sh`'s parent on a
mid-load TERM kill) — currently Suspected on a single observation, not
yet reproduced.

---

## 2026-07-29 — Round 5 (NEW-1): mock inference in unmocked `test_compress_summary_handles_inference_failure`, CODE COMPLETE (not yet fully live-verified)

**What changed:** `tests/test_memory.py`'s
`TestMemoryCompressSummary::test_compress_summary_handles_inference_failure`
(commit `c65be95`) previously called `self.memory.compress_summary(...)`
with zero mocking, despite its name/docstring claiming to test the
inference-failure path. This meant every plain `pytest tests/` run
triggered `core/memory_v2.py:600-627`'s `compress_summary()` →
`core/inference_v2.py:65-94`'s `infer()` → `get_loader().ensure_model()`,
spawning a real local 7B `llama-server` subprocess that nothing in the
test tracked or cleaned up, leaving it orphaned after the suite ended —
`NEW_ISSUES.md` [NEW-1], root-cause Confirmed in Round 5's diagnostic
investigation (2026-07-29, decisive PPID-capture proof; see entry below).
The fix patches `core.inference_v2.infer` (not `core.memory_v2.infer`,
which would be a no-op since `compress_summary` does a local `from
core.inference_v2 import infer` inside the function body) to return the
real failure-return convention (`"[ERROR] ..."`), and asserts the actual
fallback behavior: last 4 messages returned unchanged, summary left
untouched.

**Review:** code-reviewer approved. Independently re-ran both the
targeted test and the full `tests/test_memory.py` file, confirmed no
orphan `llama-server` process after either run.

**Verification status:** CODE COMPLETE, code-reviewer-approved — **not
yet fully live-verified.** code-reviewer's re-run was scoped to
`tests/test_memory.py` only, not the full `pytest tests/` suite. A
live-verifier pass confirming a full `pytest tests/` run no longer
produces the orphan `llama-server` is pending and will be logged in a
follow-up entry once it completes. Per Ground Rule 7, this is not marked
fully live-verified until that pass confirms it.

**Result:** `NEW_ISSUES.md` [NEW-1] updated to "fix committed (`c65be95`),
pending full-suite live verification" — not marked Resolved yet.

---

## 2026-07-29 — Round 4 (NEW-3): disable aiohttp access logger on GUI server, code complete

**What changed:** `gui/server.py`'s `web.run_app()` call (commit
`efe9f5c`) now passes `access_log=None`, closing `NEW_ISSUES.md` [NEW-3]
— the dormant risk that the GUI session token (`?token=...` on `/ws`
upgrades) would be written to aiohttp's default access log at INFO level
if `logging.basicConfig()` is ever configured for the GUI process in the
future. Nothing configures a handler today, so this was never currently
exploitable, but the fix removes the risk outright rather than relying on
that staying true. One-line diff:
```
- web.run_app(make_app(), host=HOST, port=PORT, print=lambda *_: None)
+ web.run_app(make_app(), host=HOST, port=PORT, print=lambda *_: None, access_log=None)
```

**Review:** code-reviewer approved. Confirmed `access_log` is a genuine
documented `aiohttp` kwarg (installed aiohttp 3.14.3), and verified no
other log call site in `gui/server.py` could leak the token.

**Verification:** no live-verification performed for this fix
specifically — scoped as a negative/absence assertion with no new
live-session behavior to exercise; already covered by Round 2 (C-2)'s
prior full live-verification of normal GUI start (2026-07-29 entry
below).

**Result:** Round 4 (NEW-3) is now fully closed — code-complete,
code-reviewer-approved. `NEW_ISSUES.md` [NEW-3] marked Resolved. No open
items remain under Round 4 itself.

---

## 2026-07-29 — Round 3 (NEW-4): opt-in `--dashboard-only` mode for `gui/start.sh`, fully live-verified

**What changed:** `gui/start.sh` (commit `ea954eb`) gained an opt-in
`--dashboard-only` flag (or `CODEY_GUI_DASHBOARD_ONLY=1` env var) that
skips `main.py`'s eager 7B model load entirely and just serves the GUI/
dashboard, waiting on the GUI server's own PID instead. Default (no-flag)
behavior is byte-for-byte unchanged: still chains into `main.py` after
starting `gui/server.py`. Reuses the existing trap/kill logic unchanged —
no second kill path introduced. Addresses `NEW_ISSUES.md` [NEW-4], found
during Round 2's live-verification pass (2026-07-29, entry below).

**Review:** code-reviewer approved. One non-blocking suggestion noted:
the new arg-parsing loop makes the last non-flag positional arg win
instead of the first — latent (no current caller passes multiple
positional args), not required to fix before merge.

**Verification (real, live, RAM-monitored — not mocked):**

- Default path: real model-load cycle triggered as before. `free -h`:
  8.3Gi used during load → 3.1Gi used after teardown. `main.py` and
  `llama-server` both confirmed running during the test, confirmed
  unloaded after stop.
- `--dashboard-only` path: `pgrep` confirmed no `main.py` or
  `llama-server` process ever started; `curl` to the dashboard endpoint
  returned 200. Teardown by tracked PID clean in both paths — no
  pattern-based kill used.
- Single model-load cycle run this round, confirmed unloaded afterward
  per RAM-discipline rule (only the default path loads a model at all).

**New finding logged, not fixed:** during the default-path live
verification, implementer observed the spawned `llama-server` child (a
tracked PID) briefly outliving `gui/start.sh`'s parent process after a
`TERM` sent while the 7B model was still mid-load, before implementer
killed it directly by that same PID. Rated **Suspected** by implementer's
own assessment — observed under an aggressive test-timeout kill
specifically during the load window, not reproduced a second time, may
not be reproducible in a normal session. code-reviewer confirmed this is
unrelated to the `--dashboard-only` diff itself (lives entirely in
`main.py`'s own model-spawn/kill path, untouched by this change, and
unreachable in `--dashboard-only` mode since `main.py` never runs there).
Logged as `NEW_ISSUES.md` [NEW-5] (Suspected).

**Result:** Round 3 (NEW-4) is now fully closed — code-complete,
code-reviewer-approved, and live-verified on both paths. No open items
remain under Round 3 itself.

---

## 2026-07-29 — Round 2 (C-2) live-verification: real `gui/start.sh` launch path, fully live-verified

**What changed:** No code changes — this is a live-verifier pass closing
the one open item left after the C-2 GUI-security fixes (see entry
directly below), upgrading status from "code-reviewer-verified against a
live scratch instance" to **fully live-verified through the real
daemon-managed GUI launch path**.

**Method:** launched via the actual `gui/start.sh` invocation (not a
scratch `gui/server.py` instance). Since `main.py`'s REPL requires open
stdin, a held-open FIFO + detached holder process fed stdin so the launch
could proceed without orphaning the REPL — a test-harness technique only,
no code change.

**Verification (real, live, RAM-monitored):**

- Baseline `free -h` (before launch): Mem 4.0Gi used, 3.9Gi free, 6.6Gi
  available.
- Model load confirmed: 7B (`qwen2.5-coder-7b-instruct-q4_k_m.gguf`)
  loaded, `llama-server` PID 25675, `/health` → 200.
- Bind address confirmed loopback-only. `ss`/`netstat` unavailable on
  this Android build, so verified via direct connectivity instead:
  `127.0.0.1:8888` → 200; the device's real LAN IP, both
  `192.168.1.111:8888` and `192.168.1.111:8080` → connection refused.
- WS auth re-checked against the **real served token** (fetched live via
  curl from the actual served `index.html`, not reused from any prior
  test): missing Origin → 403; correct Origin + wrong token → 403;
  correct Origin + missing token → 403; correct Origin + correct token →
  101 Switching Protocols, followed by a real metrics broadcast frame
  showing the 7B model online.
- Teardown: all 4 real processes (`gui/server.py` PID 25672,
  `llama-server` PID 25675, `main.py` PID 25673, `start.sh` wrapper PID
  25669) plus the test's own FIFO-holder helper (PID 25612) killed
  individually by tracked PID, confirmed gone via `ps` — no
  pattern-based kill used.
- Final `free -h`: Mem 3.4Gi used, 5.2Gi free, 7.2Gi available —
  healthier than the pre-launch baseline.
- Single model-load cycle, confirmed unloaded afterward. No second cycle
  run.

**Result:** C-2 is now **fully live-verified**, not just
code-reviewer-verified on a scratch instance. All three C-2 sub-tasks
(`d29468f`, `ca94ab5`, `1198ba1`) plus this live pass close out Round 2
in full — no open items remain.

**New finding logged, not a security issue:** `gui/start.sh`
unconditionally chains into `main.py`, which eagerly loads the 7B model
with zero user interaction — running the GUI "just to check the
dashboard" always costs a full model load. Directly observed live during
this pass. Logged as `NEW_ISSUES.md` [NEW-4] (Confirmed).

---

## 2026-07-29 — Round 2 (audit finding C-2, GUI server security): loopback bind, Origin allowlist, session token

**What changed:** Three sequenced sub-tasks, each committed and
code-reviewer-approved separately, closing out `Codey-OS-audit.md`'s
[C-2] (GUI server: unauthenticated command execution, bound to `0.0.0.0`
by default, no WebSocket Origin check):

1. **`d29468f`** — `gui/server.py`'s default bind host changed from
   `0.0.0.0` to `127.0.0.1`. `CODEY_GUI_HOST` env var override preserved
   for deliberate LAN use. Reviewed and approved standalone, with an
   explicit note in the commit that C-2 isn't resolved until sub-tasks 2
   and 3 land (no auth/Origin check yet at this point).
2. **`ca94ab5`** — `handle_ws` now rejects any WebSocket handshake unless
   the `Origin` header exactly matches `http://localhost:<port>` or
   `http://127.0.0.1:<port>` (port read from a module-level `PORT` global,
   hoisted so the allowlist and `web.run_app` can never disagree on which
   port is actually bound). Missing Origin is rejected, not exempted.
   First submission was rejected by code-reviewer for allowing
   missing-Origin through; resubmission with strict
   reject-if-missing-or-mismatched was approved.
3. **`1198ba1`** — per-process session token
   (`secrets.token_urlsafe(32)`, generated once at server startup)
   required as a `token` query param on the `/ws` upgrade request,
   checked via timing-safe `secrets.compare_digest`, independently ANDed
   with the Origin check, both checked before `ws.prepare()` so a
   rejected request never completes the WS handshake. Token is embedded
   in `index.html` for the browser client. `GET /` (`handle_index`)
   deliberately left ungated by the token — code-reviewer concurred this
   is correct given loopback-only bind (post sub-task 1), Origin isn't a
   real boundary against a same-machine actor, and gating `/` would
   require a second token-distribution channel with no real security
   benefit.

**Verification — code-reviewer-verified against a live scratch instance,
NOT a live-verifier pass through the daemon-managed GUI startup path.**
No live-verifier agent was run this round. Verification consisted of
code-reviewer independently running a real `gui/server.py` instance on a
scratch port and curl-testing all four token/Origin combinations against
it directly: no-token → 403, wrong-token → 403, correct-token +
correct-Origin → 101 (handshake succeeds), correct-token + bad-Origin →
403. Teardown was clean and PID-tracked. This is stronger evidence than a
mock/unit test, but it did not exercise the actual daemon-driven
`codeydOS`/`codey-start` GUI-launch path (env var propagation, the real
PID-file-coordinated startup sequence) — that remains unconfirmed. Mark
C-2 **code-reviewer-verified (live scratch instance), not fully
live-verified**, not "code complete only."

**Follow-up issue logged, not fixed:** `NEW_ISSUES.md` [NEW-3]
(Suspected) — code-reviewer flagged that `web.run_app()` is called
without `access_log=None`, so aiohttp's default `AccessLogger` would log
the full request line (including the `/ws?token=...` query string) at
INFO level if any future change configures a `logging` handler for this
process. Currently dormant/not exploitable: nothing in the repo calls
`logging.basicConfig()` for the GUI process and `gui/start.sh` doesn't
redirect stdout/stderr to a persistent file, so Python's default
`lastResort` handler drops the INFO-level line today. Suggested fix
(not applied, out of scope): `access_log=None` on `web.run_app()`, or
move the token off the query string entirely.

---

## 2026-07-29 — Round 1 live-verification follow-up: H-4 self-race fix, C-1 short QA prompt

**What changed:**

1. **H-4 self-race (`core/daemon.py`'s `check_pid_file()`).** Round 1's
   H-4 fix made `codeydOS` write the daemon's own PID into `PID_FILE`
   immediately after spawning it. But `check_pid_file()` — called by
   `main()` on every daemon startup, before `Daemon()` is even
   constructed — did `os.kill(pid, 0)` against whatever PID was in the
   file. A process can always signal itself, so the daemon now always
   found its own freshly-written PID, concluded a duplicate was running,
   and exited immediately with "Daemon is already running." This is why
   live verification of Round 1 failed both times. Fix: added
   `if pid == os.getpid(): return False` before the `os.kill` aliveness
   check — one line, nothing else in the function changed.
2. **C-1 follow-up (`prompts/system_prompt.py` / `prompts/layered_prompt.py`).**
   Direct measurement showed `get_system_prompt()` (priority 0,
   `required=True`, included even when `lightweight=True`) is 8,352
   characters of pure tool-calling-format enforcement — irrelevant to a
   QA/smalltalk turn that's already separately told not to use tools via
   `is_qa`. Added `get_qa_system_prompt()` — a ~280-char identity block
   with no tool-format instructions — and switched
   `_build_draft_prompt()`'s `identity` layer to use it when
   `lightweight=True`, leaving `get_system_prompt()`/`_SYSTEM_PROMPT_BODY`
   byte-for-byte unchanged for the full path.

**Verification (real, live, RAM-monitored — not mocked):**

- **H-4:** `codeydOS start` succeeded cleanly (no more false "already
  running"). A concurrent `codeydOS start` issued while the first
  instance was still loading the 7B model correctly printed "Main daemon
  is already running (PID: 7918)" and did **not** kill the loading
  instance — `pgrep -fa "llama-server.*8080"` showed exactly one PID
  (7926) once loading finished. Mid-task the whole Claude Code session
  crashed and restarted (confirmed via `ps` showing a fresh `--resume`
  process); this killed the daemon and its children as a side effect of
  losing the process group, not a code defect — no error/crash trace in
  `codeyOS.log`, just the log stopping mid-stream. Step 3 of the
  verification plan (`codeydOS stop` + `free -h`) was therefore not
  re-run as a clean stop cycle afterward, since nothing depending on
  `stop_daemon()` was touched by this fix; post-crash state showed no
  orphaned processes and no PID file, so cleanup was confirmed by other
  means.
- **C-1:** Char counts — full prompt 10,148 chars, lightweight prompt now
  **849 chars** (was 8,947 before this fix), saving **9,299 chars**
  (previously only 1,201 were saved). Live one-session test via
  `python3 main.py --no-resume` (model loaded once, three turns in the
  same warm session): `hello` → first token at ~14.0s after send;
  `what can you do?` → first token at ~15.3s after send, both plain text
  with no `<tool>` tags (confirms the separate `is_qa` "don't use tools"
  behavior is untouched by this fix). A real coding request in the same
  session ("add a docstring to the `shutdown` function in `main.py`")
  correctly took the full/non-lightweight path — `[Recursive] Draft
  (1/2)`, file loaded into context (2,667 tokens), a `patch_file` tool
  call was generated and the recursive review accepted it at quality
  8/10. Both QA turns' ~14-20s time-to-first-token is a large
  improvement over Round 1's unverified ~166-186s baseline, though that
  baseline was measured cold (fresh model load per invocation) while
  this test was warm (one session, model loaded once) — the two numbers
  aren't a clean apples-to-apples isolation of the char-count savings
  alone, but the qualitative result (QA responses in ~15s instead of
  minutes) is real and observed, not inferred.
- **Unrelated observation, not in scope for this task:** on the coding
  turn, after the recursive review accepted the draft, the harness logged
  "Malformed tool call — JSON parse failed, retrying" and regenerated an
  identical `patch_file` call with `old_str: ""`. `git diff main.py`
  afterward showed no change was actually applied to `shutdown()` —
  the patch appears to have silently no-op'd (likely `patch_file` doesn't
  handle an empty `old_str` as "insert" the way the model assumed). This
  predates both fixes in this task and lives in the recursive
  critique/refine or `patch_file` tool-execution path, not in
  `prompts/system_prompt.py`, `layered_prompt.py`, or `daemon.py` — flagged
  for a future task, not fixed here.

---

## 2026-07-29 — Audit Round 1 fixes (C-1, H-1, H-4): tiered prompt, scoped process kills, PID-file race closed

**What changed:** Three causally-linked fixes from `Codey-OS-audit.md`,
scoped exactly to C-1/H-1/H-4 and nothing else:

1. **C-1 (system prompt cost / silent hang).** `core/agent.py`'s `is_qa`
   QA/smalltalk classification (previously computed at the old line ~1405,
   *after* the system prompt was already built) was moved earlier, before
   `build_recursive_prompt()` is called, and threaded through as a new
   `lightweight: bool` parameter. `prompts/layered_prompt.py`'s
   `_build_draft_prompt()` now skips the `repo_map`, `retrieval`, `skills`,
   `files`, and `symbolic_graph` blocks' *code paths* entirely (not just
   their output) when `lightweight=True` — `retrieve()` and
   `load_relevant_skills()` are never called for QA turns. `identity`,
   `notes`, `prefs`, `project`, and the conditional `capabilities` block
   are unchanged for both paths. The draft-prompt cache key now includes
   `lightweight` so a cached full prompt is never served for a QA request
   or vice versa. Separately, added a visible elapsed-time indicator during
   prompt processing: `core/inference_v2.py`'s `_infer_chat()` spawns a
   1 Hz ticker thread showing `⤁ Thinking... (Ns, processing N-token
   prompt)` (uses `core.tokens.estimate_messages_tokens`), stopped cleanly
   the instant the first real token arrives via a new `on_first_token`
   callback threaded through `core/inference_hybrid.py`'s
   `ChatCompletionBackend.infer()`/`_infer_streaming()` and
   `core/inference_openrouter.py`'s `OpenRouterBackend` (same signature,
   for interface parity — both local and remote streaming backends now
   support it).
2. **H-1 (blanket `pkill` kills unrelated model servers).** Removed
   `main.py`'s `subprocess.run(["pkill", "-9", "-f", "llama-server"], ...)`
   shutdown fallback entirely. `core/loader_v2.py`'s `ModelLoader` gained
   `get_pid()`, returning the actual spawned PID (or `None`). `main.py`'s
   `shutdown()` now captures that PID before calling `unload()`; only if
   `unload()` itself raises does it fall back to
   `os.killpg(os.getpgid(pid), SIGKILL)` on that one captured PID — never a
   name-pattern kill.
3. **H-4 (daemon-start PID-file race).** `codeydOS`'s `start_daemon()` now
   writes `$PID_FILE` immediately after capturing `DAEMON_PID=$!`, from the
   shell itself, atomically (`echo > "${PID_FILE}.tmp"; mv` into place) —
   before the `sleep 1` / health check / orphan pre-kill steps. This closes
   the window where a concurrent `codeydOS start` during the 7B's ~15-40s
   load could see no/stale PID file, pass the top-of-function guard, and
   run its own `pkill -9 -f "llama-server.*8080"`, killing the *first*
   instance's still-loading model server. `core/daemon.py:676`'s own
   `write_pid_file()` call is untouched — it's now a harmless, idempotent
   second write. Also added PID-file cleanup on the "daemon failed to
   start" path, since writing the file earlier introduced a new failure
   mode (a stale PID left behind by a failed start) that didn't exist
   before.

**Why:** These three findings were confirmed causally linked in the
audit's own session-log evidence: a ~2,500-token system prompt on even
"hello" takes 140-173s of silent prompt processing on-device (C-1) with no
progress feedback, which reads as a hang and invites an impatient retry;
that retry can race a daemon start (H-4) or trigger a client-side
disconnect that later gets compounded by an over-broad shutdown kill
(H-1) — together producing the "Codey doesn't respond" / `[ERROR] Chat
completions inference failed` symptom pattern recorded in this morning's
session files.

**Verification performed:**
- `python3 -m pytest tests/ -q` → **253/253 passed** (run twice across the
  session, both clean).
- Mocked confirmation (no model load) that the lightweight path never
  calls `core.retrieval.retrieve`, `core.skills.load_relevant_skills`, or
  `core.project.get_repo_map` — patched all three to return a sentinel
  string and confirmed it appears in the non-lightweight output but never
  in the lightweight output, and `.called` is `False` for all three
  mocks in the lightweight case, `True` in the full-path case.
- Direct classification check: reproduced `core/agent.py`'s `is_qa` logic
  standalone — `is_qa("hello")` → `True`, `is_qa("add a function to
  core/agent.py")` → `False`, matching required zero-regression behavior
  for the non-QA path.
- `ast.parse()` clean on all 8 touched files; `bash -n codeydOS` clean.
- **Not performed:** live wall-clock before/after timing for C-1, live
  orphan-survival test for H-1, live daemon-race reproduction for H-4 — a
  Termux crash occurred mid-task during live testing (see below), and
  after investigating I chose not to re-attempt further live model loads
  this session. This is an honest gap, not a claimed-but-skipped step —
  flagged explicitly rather than silently left off.

**Incident during this task (relevant to H-1/H-4's own subject matter):**
Mid-task, while starting a standalone 1.5B "unrelated server" for the H-1
repro, Termux crashed. After recovery, `free -h` twice showed RAM cratering
to <200 MB free / ~2.5 GB available with 6+ GB in swap, both times traced
to a live 7B `llama-server` process running with `PPID 1` (orphaned,
no PID file, not started by me) — once right after the crash, once again
immediately after a routine `pytest tests/` run (both within the same
uninterrupted shell command as the pytest invocation, so nothing else of
mine could have interleaved). **Root cause NOT confirmed** — a follow-up
static investigation (grep across `tests/*.py` for
`llama-server|LlamaServer|subprocess|Popen|get_loader|ensure_model`, full
read of `tests/test_hybrid_inference.py`, check of every `core.agent`
import site, module-level `core/*.py` scan, and a check for
cron/boot-script/pytest-plugin mechanisms) found **no code path** that
explains it. The timing correlation is real and reproduced; the causal
claim is not — corrected in `NEW_ISSUES.md` NEW-1 after initially
overstating this as "confirmed." Matches the audit's original L-6 at
**Suspected** confidence, not upgraded. Both orphaned processes were
killed individually by their own PID (`kill -TERM -<pid>`, process-group
scoped, matching the H-1 fix's own discipline), RAM recovered cleanly both
times (confirmed via `free -h` before/after). No blanket kill was used at
any point during cleanup.

**Outcome:** All three targeted findings (C-1, H-1, H-4) fixed and
statically/mock-verified; existing test suite green; one new issue (NEW-1)
found and logged, not fixed, per task scope. `main` (the stray empty file
noted in the audit as L-2) and `=3.9.0` (L-1) were left untouched — out of
scope for this task.

Inference-ticker plumbing (`core/inference_v2.py`, `core/inference_hybrid.py`,
`core/inference_openrouter.py`) accepted without diff review, given
cost/thoroughness tradeoff — flagging in case a ticker-related bug surfaces
later.

**Next action:** Live verification is still the open item — mock/unit
checks confirm the mechanism is wired correctly, not that the live symptom
is actually gone. Next: a single, careful test cycle (`free -h` before and
after), with `pytest tests/` kept away from it entirely — NEW-1 (pytest
possibly spawning a real model server) is unconfirmed but not ruled out,
and stacking that risk on top of a live daemon/model test is exactly the
kind of compounding that caused this session's crash. After live
verification: Round 2 — C-2 (GUI server security: unauthenticated command
execution, `0.0.0.0` default bind, no WebSocket Origin check).

---

## 2026-07-27 — Corrected audit verified, deletion list finalized

**What changed:** Qwen's corrected audit came back with a fixed method
(substring search catching lazy imports + non-Python references). Spot-
checked the key claims: confirmed `core/inference.py` is genuinely used
(lazy import at `core/inference_v2.py:157`, HTTP fallback backend);
confirmed `test_optimize_me` files under `ccos/data/staging/` and
`ccos/data/versions/` have zero references anywhere and are absent from
`ccos/data/capabilities.json` (which only lists real registered
capabilities); confirmed `core/recovery.py` is documented as an intended
feature (`CHANGELOG.md:846`, `docs/architecture.md:155`) but never actually
imported — correctly left as UNCLEAR rather than forced into a guess. This
round of Qwen's work holds up under independent verification.

**Verification performed:** Direct `grep`/`cat` against actual source for
`inference_v2.py:157`, repo-wide `test_optimize_me` search, contents of
`capabilities.json`, and doc references for `recovery.py`.

**Outcome — final counts:** 113 USED, 9 UNUSED (5 confirmed-safe:
`ccos/data/staging/test_optimize_me/*` x2, `ccos/data/versions/test_optimize_me/*`
x2, `test_patch.txt`; the empty `ccos/plugins/research/__init__.py` also
still UNUSED), 15 UNCLEAR (needs human decision — includes
`core/observability.py`, `core/recovery.py`, `codey3`/`codeyd3` no-ext
duplicates, and all root-level/docs/ orphaned markdown files).

**Next action:** Confirm with Ish the small "safe to delete now" list (5-6
files, all independently verified), then go through the UNCLEAR list
together in batches before any further deletion.

---

## 2026-07-27 — Full repo audit returned, but contains real errors — correction sent

**What changed:** Qwen returned a full 137-file audit (108 USED, 12 UNUSED,
17 UNCLEAR, plus non-Python files). Independently spot-checked 7 of the 12
"confirmed UNUSED" files against actual source. **4 were wrong:**
`core/githelper.py`, `prompts/critique_prompts.py`, and `tools/kb_semantic.py`
are all actually used via lazy imports inside function bodies (not caught
by Qwen's scan method), and `tools/setup_skills.sh` is a documented setup
command referenced in 4 doc files plus a runtime warning — Qwen's method
only checked Python imports, missed shell-script/doc references.
Also caught: `ccos/data/versions/` and `ccos/data/staging/` were flagged as
unused artifact dirs, but `capability_optimizer.py` actively writes to and
reads from both as CCOS's live rollback/version-preservation mechanism —
confirmed by grep, and consistent with CCOS's documented design philosophy.
3 of the 12 (`core/inference.py`, `core/observability.py`,
`core/recovery.py`) did check out as genuinely unused.

**Why this matters:** This is the third time in this project Qwen's
self-reported findings have needed independent correction (after the
fabricated daemon-Kernel claim, and the two README incidents). The specific
failure mode here — missing lazy/deferred imports inside function
bodies — is a real methodological gap, not random noise, and this
codebase uses that pattern heavily (likely deliberately, to reduce startup
cost). This blind spot would have caused real deletions of load-bearing
code (git integration, retrieval fallback, prompt critique step) if acted
on without verification.

**Verification performed:** Direct `grep -rn` against the actual
`Codey-V3-main` source (re-extracted from the uploaded zip) for each of the
7 spot-checked files, cross-referencing exact line numbers where lazy
imports occur.

**Outcome:** Sent Qwen a correction prompt: (1) shows it the exact evidence
of what it missed, (2) requires it to re-run the audit with a method that
catches lazy imports and non-Python references, (3) requires it to
re-check every UNUSED classification in the full repo, not just the ones
caught, (4) specifically asks it to distinguish the staging/versions
*mechanism* (load-bearing, keep) from the specific `test_optimize_me`
sample files inside those dirs (possibly genuinely stale, needs its own
check).

**Next action:** Get corrected audit back. Independently spot-check a
sample of the corrected list again before agreeing on a deletion list —
given the error rate so far, do not skip verification on the next round
either.

---

## 2026-07-27 — Full repo cleanup audit requested (before any deletion)

**What changed:** Resolved `symbolic_graph.py` question — confirmed real,
load-bearing (691 lines, imported by `agent.py`, `memory_v2.py`,
`finetune_prep.py`, exporter, `layered_prompt.py`). Keeping it. This
surfaced a bigger concern: doing a "delete what's unused" pass by
inference risks repeating the same mistake that apparently dropped
`symbolic_graph.py` from v4 without a deliberate decision.

**Why:** Ish wants a clean repo/directory with only working code, but
agreed cleanup should be audit-first, human-reviewed, then deletion —
not inferred and executed in one pass.

**Verification performed:** N/A — this entry documents kicking off the
audit step, not its results.

**Outcome:** Sent Qwen a read-only, evidence-required audit prompt
covering the whole Codey-OS repo (core/, ccos/, docs/, tests/, config,
assets). Must cite actual grep/import evidence for every USED/UNUSED
classification; ambiguous cases go to UNCLEAR for human review, not
guessed.

**Next action:** Get audit results back, review UNCLEAR items with Ish,
agree on a deletion list, then execute cleanup as its own reviewed step
before starting Phase 1 (RAG retrieval migration).

---

## 2026-07-29 — Phase 3 Sub-step C complete (README rewrite); real process gap discovered

**What changed:** README.md rewritten (commit `314450a`, 143 insertions,
365 deletions). **Discovery:** the file at `README.md` was never actually
a project-facing README — it was, verbatim in structure (12 sections,
6-layer diagram, module/persistence tables, "THIS IS NOT FOR USE" origin),
the internal CCOS architecture document shared at the very start of this
project, sitting at that filename the whole time. Explains why the
earlier branding sub-task (literal string swaps only) never caught how
structurally wrong it was — it was never asked to look at structure.

**Real safety-relevant fix caught along the way:** the old content's
"Key System Properties" table flatly claimed "Self-improving: Yes" —
directly contradicting Section 5's gated-by-default design. Correctly
replaced with an honest "present but gated" framing rather than carried
forward.

**All 3 required completeness checks fulfilled:**
1. Section-by-section accounting of all 12 old sections + License, each
   with keep/merge/drop and a stated reason — nothing silently lost.
2. Cross-check against real project history: 4 of 6 items confirmed
   present (entry points, dashboard, backend flexibility, rename
   mention); items 5-6 surfaced the process gap below instead.
3. Independent code audit (not just doc cross-checking): found
   `docs/commands.md` missing 12 real slash commands and ~13 real CLI
   flags confirmed live in `main.py`'s actual dispatch/argparse, plus one
   possibly-stale flag (`--rollback`). Correctly left unfixed (out of
   this task's scope) but flagged clearly, and softened the new README's
   own description of `docs/commands.md` so it doesn't inherit the
   overclaim.

**Real process gap found — my responsibility, not Claude Code CLI's:**
the audit confirmed `PROJECT_PLAN.md` and `PENDING_ISH_DECISIONS.md` do
not exist anywhere in the actual Codey-OS repo. I maintained
`PROJECT_PLAN.md`/`PROJECT_LOG.md` faithfully throughout this entire
project but only ever handed them back as downloadable files — never
instructed adding them to git. `PENDING_ISH_DECISIONS.md` was told to
Ish to commit after Phase 2, but that was never confirmed and apparently
never happened. Given the very first stated preference for this whole
project was keeping a project plan and log file updated in step with the
work, this should have been version-controlled from early on.

**Verification performed:** Reviewed real checks — `codey-start`/
`codey-stop` read in full, env var names confirmed against
`utils/config.py`, all 10 capability domains cross-checked against
`ccos/plugins/*/manifest.json` (exact match with master vision Section
3), all 11 docs-index links confirmed to exist under real post-rename
filenames.

**Outcome:** Phase 3 is now fully, genuinely complete — Sub-steps A, B,
and C all done and verified. Two tracked, non-blocking loose threads:
`docs/architecture.md`'s missing CCOS-layer content (already known),
`docs/commands.md`'s incompleteness (newly found, worth a dedicated
pass).

**Next action:** Fix the process gap — commit `PROJECT_PLAN.md`,
`PROJECT_LOG.md`, and `PENDING_ISH_DECISIONS.md` into the actual repo for
real this time. Then decide on the entry-point retirement questions, or
move to reviewing `PENDING_ISH_DECISIONS.md`/the deferred coding-agent
wrap.

---

## 2026-07-29 — Phase 3 Sub-step C started (final Phase 3 item): README rewrite

**What changed:** Sent the README rewrite task, using
`CODEY_OS_MASTER_VISION.md` Section 3 as primary source (maintained and
accurate throughout this project) rather than re-auditing from scratch.
Required reading the current README first — the branding rename already
fixed literal names, but the structural framing likely still describes
an earlier "standalone coding agent" state, not what Codey-OS actually
is now. Explicit instruction not to overclaim deferred/gated work
(self-improvement, the unwrapped coding-agent core) as fully built.
Every Quick Start command required to be spot-checked against real
source, not assumed — same discipline as the original v4 README
incident that started this whole project's verification culture.

**Next action:** Get results back, verify the spot-checks, then Phase 3
is entirely complete.

---

## 2026-07-29 — Sub-step B complete (dashboard); cleanup task surfaces real production-path bug

**Dashboard (commit `03182e9`):** Shared `core/dashboard_data.py` module,
imported by both TUI and GUI — matches the reasoning requested (avoids
duplicating capability-call logic in two places, cites the master
vision's explicit warning against this). GUI's `get_ram()` now sources
from the same shared path instead of its own separate `/proc/meminfo`
parsing — fixes divergence at the root. Verified via simultaneous TUI+GUI
capture showing matching `ram_total`, only expected timing-drift on
`ram_used`. No 7B process spawned (OpenRouter-only, as scoped). 253+67
tests pass (1 pre-existing sandbox failure, confirmed unrelated via
`git stash`). Zero orphaned processes after stop.

**Cleanup task (commit `dd49c1d`) — found a real, significant bug, not
just noise:** `SkillRecombiner` and `CapabilityOptimizer` (Section-5-gated
self-improvement modules) hardcoded their output paths to the *live
production* `ccos/plugins/compound/` and `ccos/data/staging|versions/`
trees, and their own tests used seed names colliding with real plugin
names (`skill.info_processes`, `skill.camera_capture_tts`,
`test.optimize_me`) — meaning every test run silently wrote test
artifacts into production plugin source, and regenerated the very
"confirmed dead" files just deleted in Part 1. This explains why
`test_optimize_me` kept reappearing throughout this project — it wasn't
leftover noise, it was being actively regenerated by test runs. Fixed via
injectable `plugin_base`/`data_base` params (production behavior
unchanged, tests now isolated to temp dirs) — confirmed with Ish directly
before fixing rather than either silently patching or leaving broken.

**Bonus find:** `Sandbox.__init__`'s `allowed_dirs` parameter was dead
code — `_validate_path` ignored it, always checked a hardcoded
module-level constant instead. Fixed so parameterized sandbox testing
actually works — relevant given the sandbox is explicitly part of the
safety model.

**Note for Phase 4 (not urgent, just context):** this doesn't touch
Section 5's actual gating — the daemon path to these modules remains
confirmed unreachable, this was their own test suite, not live
activation. But it does mean `SkillRecombiner`/`CapabilityOptimizer`
writing to live plugin directories is now validated as working correctly
with proper path injection — useful groundwork already sitting in place
whenever self-improvement activation is eventually deliberately decided.

**`.gitignore` additions confirmed correct, not just expedient:**
verified `capabilities.json` is fully rebuilt from plugin manifests on
every `plugin_manager.load()` call (overwrites from scratch, discards
prior stats) — meaning "always revert before commit" was technically
correct behavior all along, not a workaround. `reflections.jsonl`
confirmed pure append-only log. Neither carries real state lost by
untracking.

**Verification performed:** Full suite re-run post-fix at established
baseline; confirmed previously-noisy files no longer reappear in
`git status`; `git status --ignored` shows only expected entries.

**Outcome:** Phase 3's checklist is now clear for Sub-step C (README
rewrite) — both Sub-step A and B complete, and the working tree will
finally stay clean by default going forward instead of needing manual
discarding every task.

**Next action:** Push to GitHub, then write Sub-step C (README rewrite).

---

## 2026-07-29 — Recurring working-tree noise cleanup queued (behind Sub-step B)

**What changed:** Ish noticed Claude Code CLI repeatedly having to note
"staged only my files, left unrelated pre-existing changes untouched"
across nearly every task. Traced to two distinct things: (1) genuinely
regenerated CCOS runtime state (`capabilities.json`, `reflections.jsonl`)
that's been manually `git checkout --`-ed before every commit this whole
project instead of being gitignored once, permanently; (2) the confirmed-
safe-to-delete list from the very first repo audit (`test_optimize_me`
staging/version files, `test_patch.txt`) — paused early on to focus on
the unification work and never actually executed.

**Outcome:** Wrote a 3-part cleanup task — execute the overdue deletions,
investigate (not just silence) why two compound-skill pipeline files keep
getting touched before deciding whether to gitignore them too, then add
appropriate `.gitignore` entries. Queued behind the in-progress
Sub-step B dashboard task — not sent yet, don't want to interrupt
mid-work.

**Next action:** Send this once Sub-step B's task completes and is
verified.

---

## 2026-07-29 — Phase 3 Sub-step B started: unified dashboard

**What changed:** Sent the task to wire `thermal_monitor`+`observability`
capabilities into the actual live TUI status bar and GUI metrics —
currently two separate direct-access code paths (`core/sysmon.py`'s
`render()` for TUI, `gui/server.py`'s own `get_ram()`/`get_model_status()`
for GUI), neither routed through the CCOS capability layer we built in
Phase 2. Deliberately scoped to use the OpenRouter backend for all live
testing — this task doesn't need the local 7B at all, so avoiding the RAM
ceiling entirely rather than working carefully around it. Left the
shared-module-vs-direct-calls architecture as a real design decision for
Claude Code CLI to make and justify, and explicitly preserved existing
visual output — this is about the data source, not a UI redesign.

**Next action:** Get results back, verify the actual "same source, same
values" proof (not just that each interface individually still works),
then move to Sub-step C (README rewrite).

---

## 2026-07-29 — CODEY-OS RENAME COMPLETE (all 5 sub-tasks, commit 94b7b9b)

**What changed:** Final sweep fixed 22 files. Real interactive
verification (via a delayed-FIFO technique to get genuine stdin
interaction) confirmed `main.py`'s in-session `/help` command now prints
correct current commands — precisely distinguished from `main.py --help`
(the argparse flag), which was already correct, a distinction a cruder
check would have missed. `docs/commands.md` read in full and rewritten
properly (section headers were built entirely around old names), not
mechanically sed'd. `docs/architecture.md`'s ASCII box diagram
re-centered after the name-length change. Three deliberate holdouts, all
correctly reasoned: `core/memory_v2.py`'s intentional backward-compat
filename (from sub-task 4); `CODEY_OS_MASTER_VISION.md` and `QWEN.md`
both correctly left alone as legitimate historical narration (describing
what got replaced), with the master vision specifically respected as
requiring deliberate revision per its own stated rule, not a silent
mechanical edit.

**Verification performed:** Reviewed the full corrected-grep before/after
(23 files → 3 justified holdouts), the real `/help` output, the
`docs/commands.md` rewrite scope, and the honest final assessment
correctly distinguishing "rename complete" from a separate, unrequested
scope (`docs/tools-embedding-pipeline.md`'s prose still narrates
"Codey-V3" throughout — a content-accuracy question, not a
stale-reference one, correctly not folded in without being asked).

**Outcome: the Codey-OS branding rename is genuinely, fully complete.**
Summary across all 5 sub-tasks: shared path-constant foundation,
`codey3`→`codeyOS`/`codeyd3`→`codeydOS` file renames with corrected
self-contamination, `.codey-v3`→`.codeyOS` state directory, ~320 cosmetic
occurrences swept, docs filename fixed, new CHANGELOG entry added, and
finally the lowercase command-name gap closed. Along the way: fixed the
`codey3`/`codeyd3` daemon-detection mismatch bug, the GUI Ctrl+C crash,
3 checkpoint-system bugs (`is_core_file()` scope, `git add -A`
over-staging, test isolation), the broken shebang issue, and the
orphaned-`llama-server`-on-stop bug — all real, verified fixes found
along the way, not just branding.

**Two things tracked for later, not blocking:**
1. `docs/tools-embedding-pipeline.md`'s content still needs a prose pass
   (optional future "sub-task 6" if wanted).
2. The telemetry dedup-key collision bug (found during sub-task 3,
   diagnosed, not fixed — separate from rename work).

**Next action:** Push to GitHub. Then resume the actual Phase 3 work —
Sub-step B (wiring `thermal_monitor`/`observability` into a real live
TUI+GUI dashboard), the last item on Phase 3's checklist before deciding
what's next (`PENDING_ISH_DECISIONS.md` review, or the big deferred
coding-agent wrap bundling items 7/9).

---

## 2026-07-29 — Rename sub-task 5 sent: lowercase command-name sweep

**What changed:** Sent a corrected-grep-pattern task specifically closing
the gap found in sub-task 4 — `main.py --help` printing a nonexistent
command is the priority item, verified via actual command output this
time, not just source-text confirmation. `docs/commands.md` flagged for
a real read-through pass, not a mechanical find-replace, given it's
reportedly written entirely around the old names throughout.

**Next action:** Get results back, verify the corrected grep comes back
clean and `main.py --help`'s actual output is correct, then the Codey-OS
rename is genuinely complete.

---

## 2026-07-29 — Sub-task 4 complete; my own verification grep had a gap — sub-task 5 needed

**What changed:** All 4 sub-task 4 items done cleanly — docs filename
rename, additive CHANGELOG entry (confirmed zero deletions to existing
content), `lora_import.py`'s output filenames, `memory_v2.py`'s detection
list (kept both old and new filenames deliberately, for backward
compatibility with any existing project already using the old name — good
reasoning). 320 tests pass, known sandbox failure only, no telemetry
flake this run.

**Real gap found in my own task design, not a shortcut taken:** the
final verification grep I specified only covered the capitalized
"Codey-V3" brand family — it never included the literal lowercase command
names (`codey3`, `codeyd2`, `codeyd3`) as search terms, so it was
structurally incapable of catching them. Claude Code CLI caught this
explicitly and named it as a flaw in the grep pattern itself, rather than
silently passing verification on a technicality or unilaterally expanding
scope to fix a much larger surface area without asking first.

**What's actually still wrong:** `docs/commands.md` is "entirely still
written around" the old `codeyd2`/`codey3` names; `docs/architecture.md`'s
ASCII tree; and most seriously, **`main.py`'s actual printed `--help`
banner tells users to run `codey-v3 ...`, a command that no longer
exists** since the real binaries were renamed to `codeyOS`/`codeydOS` in
sub-task 2. Also scattered lowercase mentions in `core/checkpoint.py`,
`core/daemon_config.py`, `core/finetune_prep.py`, `core/notes.py`,
`PRIVACY.md`, and several more docs files.

**Decision:** approved a sub-task 5 to close this gap — genuinely needed,
not optional cleanup, given the `main.py` help-text issue actively
misleads users right now.

**Next action:** Write and send sub-task 5 (lowercase command-name
sweep, prioritizing user-facing text).

---

## 2026-07-29 — Rename sub-task 4 (final) sent

**What changed:** Sent the last sub-task — docs filename rename, new
additive CHANGELOG entry (existing entries untouched), and the two
remaining functional filename references (`lora_import.py`'s generated
output names, `memory_v2.py`'s auto-detection list). Required a final
repo-wide grep that should now show only the 4 explicitly-untouched
historical docs, nothing else — the real completion check for the whole
4-part rename.

**Next action:** Get results back, verify the final grep shows a
genuinely clean state, then the Codey-OS rename is complete.

---

## 2026-07-29 — Sub-task 3 complete and verified; found a genuine pre-existing telemetry bug along the way

**What changed:** 77 files, text-only (176 lines, in=out). Correctly
treated live grep as authoritative over the original audit's file list
(which turned out ~40 files stale) rather than following a possibly-
outdated catalog mechanically. Bundled fixes confirmed: GUI version
badge corrected to real value (`3.0.0`, no new plumbing added since none
existed); `CODEY_NAME` constant updated but deliberately left unwired
(not obviously safe without knowing intended use — good restraint);
`setup_repo.sh`'s `REPO_NAME` updated with reasoning given for why a
technically-functional value was in scope; both `HTTP-Referer`/`X-Title`
headers confirmed via grep, not just claimed.

**Test discrepancy investigated and resolved:** flagged that test
failures went from 1 known to 2, including a never-before-seen test name.
Requested rigorous bisection rather than accepting the "matches known
issue" claim at face value. Result: confirmed via direct evidence —
zero diff on `telemetry_engine.py`/`test_telemetry.py` between the
sub-task-3 commit and its parent, reproduced the identical failure on
the unmodified parent commit, then 5 clean runs proving genuine
intermittency. Root cause: `record_execution()`'s dedup key
(`f"exec_{timestamp_ms}_{id(record) % 10000}"`) can collide under fast
back-to-back calls, and `INSERT OR IGNORE` silently drops the duplicate
row instead of raising — non-deterministic because `id()` reflects live
memory addresses, dependent on interpreter allocator state from
whatever ran earlier in the same process. Correctly NOT fixed in this
task (real code bug, out of scope for a text-only sub-task) — filed as
a genuine, separate, pre-existing bug for later (fix: use `uuid.uuid4()`
or an atomic counter instead of the timestamp+id() scheme).

**Outcome:** Sub-task 3 confirmed clean. New known bug added to tracking
(telemetry dedup-key collision) — low priority, not blocking, not part
of the rename work.

**Next action:** Sub-task 4 — the last piece of the rename. Reduced
scope given sub-tasks 2/3 already covered more than originally planned
(HTTP headers, clone-target directory, voice.py's config dir all already
done): remaining items are `docs/codey-v2-tools-embed.md`'s filename
rename, a new CHANGELOG.md entry for the Codey-OS rename (historical
entries stay untouched), `core/lora_import.py`'s generated output
filenames (`codey-v3-finetuned-*.gguf` → `codeyOS-finetuned-*.gguf`),
and `core/memory_v2.py`'s live filename-detection list (`codey-v3.md` →
`codeyOS.md`).

---

## 2026-07-29 — Rename sub-task 3 sent: cosmetic branding sweep

**What changed:** Sent the third of 4 sequenced sub-tasks — the bulk of
occurrences (~320), but structurally simple text-only changes across
docstrings, GUI text, README/PRIVACY/MODEL_COMPARISON, and current-state
docs. Bundled in the two approved adjacent fixes that fit naturally here:
`gui/index.html`'s hardcoded `v2.0.0` version badge bug, and the two
OpenRouter `HTTP-Referer` headers pointing at the wrong repo URL.
Explicitly excluded historical docs (`CHANGELOG.md`, `TODO.md`,
`AUDIT_REPORT.md`, `docs/version-history.md`) and the
`docs/codey-v2-tools-embed.md` filename rename, both deferred to
sub-task 4. Required distinguishing legitimate historical/v1 mentions
from missed occurrences in the final grep review, not just a blind
find-replace count.

**Next action:** Get results back, verify the grep review and test
suite, then sub-task 4 (bundled misc: docs filename rename, new
CHANGELOG entry, generated output filenames, remaining config
directories).

---

## 2026-07-29 — Both issues fixed and verified (commits ed92484, 14bc42c)

**Part 1 (shebang):** Root cause was NOT what I guessed (CRLF corruption)
— genuinely investigated and reported honestly rather than forced to fit
my hypothesis. Real cause: `#!/usr/bin/env` doesn't resolve on this
device because Termux's `termux-exec` LD_PRELOAD shim wasn't active in
the shell context these scripts ran from. Fixed by hardcoding the real
Termux bash path across 8 files (`codeydOS`, `codeyOS`, `codey-start`,
`codey-stop`, `gui/start.sh`, `install.sh`, `setup.sh`,
`setup_repo.sh`), matching the convention already used elsewhere in the
repo. Verified: all run directly without the `bash` prefix now.

**Part 2 (orphaned llama-server):** Two compounding gaps found. (1)
`llama-server` spawned with `os.setsid` (deliberate, survives terminal
closure) but `core/daemon.py`'s shutdown path never called the loader's
`unload()` — fixed, mirroring the existing embed-server-stop pattern. (2)
`codeydOS`'s existing `pkill -f llama-server` safety sweep only ran on
the successful-stop path — the "no PID file"/"stale PID file" early-
return branches (hit exactly during crash/OOM-kill recovery) skipped it
entirely, letting orphans accumulate silently. Fixed by adding the sweep
to both early-return branches. **This plausibly explains the
unexplained high baseline RAM (8.3/10.8GB) observed in our very first
live test session this project, before anything had been deliberately
started** — can't confirm retroactively, but the causal story fits.

**Verification performed:** Two full local-backend start/stop cycles
checked via real `ps aux` (not just daemon status), plus a direct,
targeted test of the specific stale-PID-file code path that was broken.
Mid-verification, Termux crashed from loading both local models at once
— honestly disclosed rather than hidden, and the crash became unplanned
real-world proof the fix works (no orphans survived it). Correctly chose
not to repeat the risky local-backend load further given known RAM
constraints, using the evidence already gathered instead.

**Outcome:** Both blocking issues resolved. Confirmed clean working tree,
no processes left running, pushed to GitHub (`9e86a9c..147aafd` then
this round's commits).

**Next action:** Resume the branding rename at sub-task 3 (cosmetic
branding sweep) — this was paused pending both the checkpoint-system fix
and these two issues, both now resolved.

---

## 2026-07-29 — OpenRouter backend verified working; two new issues found and dispatched

**What changed:** OpenRouter setup confirmed genuinely working end to
end — real log lines confirming actual routing, real tool-call parsing
tested (shell + list_dir calls), zero 7B `llama-server` process spawned,
RAM stayed flat throughout. Notably, Claude Code CLI caught that my task
instructions (leave `CODEY_BACKEND_P` unset) would have actually broken
the "planner stays local" goal — `utils/config.py:194` defaults the
planner backend to inherit `CODEY_BACKEND` when unset — checked in before
deviating rather than following a flawed instruction blindly. Set
`CODEY_BACKEND_P="local"` explicitly instead. Free-tier model confirmed
usable but slow (1-5.5 tok/s) — honestly disclosed, not glossed over.

**Two new issues found, not yet root-caused:**
1. `codeydOS`/`codeyOS`/`codey-start` fail with `bad interpreter:
   /usr/bin/env` on direct invocation (`./codeydOS`), only working via
   `bash codeydOS`. Likely shebang corruption (classic CRLF-injection
   symptom) from the extensive sed-based edits during sub-task 2's rename
   — needs confirming via `cat -A`, not assumed.
2. An orphaned 7B `llama-server` process was found running despite the
   daemon reporting "stopped." Possibly explains the mysteriously high
   baseline RAM (8.3/10.8GB used) observed in an early test session this
   project, before any model had been deliberately started — flagged as
   a real hypothesis to check, not confirmed yet.

**Outcome:** Sent a combined investigate-then-fix task — Part 1 (shebang)
scoped as higher priority since it affects the entry points we're
actively working on; Part 2 (orphaned process) scoped as investigate
first, only implement a fix if it turns out simple, otherwise report back
before attempting anything bigger.

**Next action:** Get results back, verify both fixes (or Part 2's
findings if no simple fix exists), then resume the branding rename at
sub-task 3.

---

## 2026-07-29 — OpenRouter backend setup task sent

**What changed:** Sent a task to wire OpenRouter as the default backend
for the 7B agent role specifically (planner stays local, per the
established RAM-scoping decision), and — more importantly — to actually
prove it works end to end (real message, real tool-call test, confirmed
no local 7B process spawns, RAM stays low) rather than just setting env
vars and assuming it works. Ish is setting `OPENROUTER_API_KEY` directly
in his own shell, not shared through the task prompt or this
conversation — the task only checks for its presence, never its value.

**Next action:** Get results back, verify the end-to-end proof
specifically (not just config confirmation), then this becomes the
default testing environment going forward — no more RAM-crash risk for
routine verification work.

---

## 2026-07-29 — Checkpoint system fixed and verified (commit 147aafd)

**What changed:** All 3 bugs fixed with real behavioral verification, not
just code review claims: `is_core_file()` narrowed to
`core/`/`tools/`/`utils/`/`prompts/` (tested against real paths including
a good edge case — `ccos/core/agent.py` correctly excluded, confirming
proper directory-scope checking, not naive string matching); `git add -A`
replaced with staging only the triggering file (proven via a real temp
git repo with both a core and unrelated file dirtied, confirmed only the
core file got committed); `test_improvement_loop.py`'s two tests rewired
to isolated temp-backed instances instead of real singletons (proven via
`git status --porcelain` on `ccos/data/` coming back empty after running
just those two tests). Full suite clean at established baseline (253 +
rest of ccos/tests, same sole pre-existing sandbox failure);
`test_self_modification.py` 8/8 confirms the safety net itself still
functions. Correctly left `ccos/data/*` mutations from
`test_capability_optimizer`/`test_auto_improvement_loop` alone — those
exercise Section-5-gated modules' own tests, out of scope here.

**Outcome:** Checkpoint system hygiene fixed. Rename sequence cleared to
resume at sub-task 3.

---

## 2026-07-29 — Checkpoint system fix task sent (3 bugs)

**What changed:** Sent a task fixing all three diagnosed bugs: narrowing
`is_core_file()`'s scope from "entire repo root" to the intended
`core/`/`tools/`/`utils/`/`prompts/` patterns, fixing `_create_git_commit()`
to stage only the triggering file instead of `git add -A`, and fixing
`test_improvement_loop.py`'s two singleton-mutating test functions to use
temp fixtures like the rest of the suite. Explicit instruction to
preserve the checkpoint mechanism's actual protective function — this is
a scoping/hygiene fix, not a removal of the safety net.

**Next action:** Get results back, verify the checkpoint mechanism still
protects genuine core-file writes while no longer over-triggering, then
resume the rename sequence at sub-task 3 (cosmetic branding sweep).

---

## 2026-07-29 — Autonomous commit diagnosis complete: Section 5 clean, root cause found

**What changed:** Full diagnosis of the `7389766` autonomous commit and
the broader checkpoint pattern. **Section 5 gating confirmed genuinely
intact** — `codeydOS`/`codeyOS`/`codey-start`/`codey-stop`/
`core/daemon.py` have zero references to `ccos`/`goal_engine`/
`auto_improvement_loop`/`capability_optimizer`/`skill_recombiner`;
`core/` has zero imports from `ccos/` (consistent with the original
zero-cross-import finding from the start of this whole project); `ccos/`
importing from `core/` traces only to the intentional Phase 1/2
capability-wrapper plugins we built ourselves, not the gated
self-improvement engines.

**Root cause identified:** `is_core_file()`'s check uses `CODE_DIR` =
the entire repo root (`utils/config.py`), not just
`core/`/`tools/`/`utils/`/`prompts/` — so because Codey is self-hosted,
literally any file write anywhere in the repo counts as "core" and
triggers `_require_checkpoint()`. This fully explains why
`install.sh`/`setup.sh` (not core Python files) triggered checkpointing.
Confirmed via the exact commit-message format matching
`_require_checkpoint`'s `reason=f"Self-modification: {path.name}"`
string construction, fired on a real test fixture file
(`test_patch.txt`, used by `tests/test_patch.py`).

**Historical corroboration:** timeline traced back 16+ occurrences to
March 2026, always tied to the coding agent's own scratch-file writes.
Independently verified against something we witnessed directly —
`hello.py`/`app.py` checkpoint commits from March correspond exactly to
the live end-to-end test session earlier this project where we watched
Codey create and edit those exact files in real time. Strong, genuine
cross-check, not just an assertion.

**Secondary finding:** `ccos/data/*` mutations in these commits trace to
a real, separate test-isolation bug — `ccos/tests/test_improvement_loop.py`'s
`test_lifecycle_manager`/`test_improvement_with_real_plugin` call real
singleton getters instead of temp fixtures, mutating live CCOS state
during normal test runs. Unrelated to the checkpoint mechanism itself,
correctly identified as a distinct bug.

**Decision: fix all three identified bugs now**, given accumulated
evidence (this is the 2nd/3rd/4th documented instance of the `git add
-A` issue specifically causing real friction) rather than deferring
again: (1) narrow `is_core_file()`'s scope to the intended patterns, (2)
fix `git add -A` to stage only the triggering file, (3) fix
`test_improvement_loop.py`'s test isolation.

**Verification performed:** Reviewed the full technical reasoning —
internally consistent, cross-checks against independently-known project
history, correctly distinguishes the checkpoint-scope bug from the
Section 5 question rather than conflating them. Did not independently
re-run `git log` myself (no live device access), but the specificity and
historical corroboration give strong confidence.

**Outcome:** Rename sequence (sub-tasks 3/4) was correctly paused
pending this diagnosis — now cleared to resume once the fix task below
lands.

**Next action:** Send the fix task for all 3 bugs, then resume sub-tasks
3/4 once verified.

---

## 2026-07-29 — Sub-task 2 confirmed complete, but flagged a live autonomous commit — rename sequence PAUSED

**What changed:** Sub-task 2 (file renames, constant flip, cross-refs)
confirmed genuinely complete and correctly verified — real daemon
detection tested via `codeydOS status` reading actual live socket data
(uptime, memory, task queue, PID), not just path matching. 253+67 tests
pass, same known sandbox failure. All work correctly bundled across 3
autonomous checkpoint commits (`9e86a9c`, `e6becca`, `7389766`).

**Escalation raised, correctly:** the last of those three commits
(`7389766`) fired **live, during Claude Code CLI's own verification
testing** — while running `codey-start` to test the renamed daemon, not
as an immediate side effect of an explicit file edit. It wrote
`install.sh`/`setup.sh` changes to the repo autonomously. Claude Code CLI
correctly identified this as worth stopping for rather than deciding
unilaterally (per `QWEN.md`'s rule) and flagged it as a possible
`CODEY_OS_MASTER_VISION.md` Section 5 concern (self-improvement gated off
from live execution) rather than just noise.

**Why this needs real diagnosis, not a quick dismissal:** `install.sh`/
`setup.sh` are bash scripts, not `core/`/`tools/`/`utils/`/`prompts/`
Python files — they don't match the previously-traced
`core/checkpoint.py` trigger pattern (fires from `core/filesystem.py`'s
checkpointed write tools on core Python file edits). A daemon *starting
up* shouldn't normally hit that path. Two live possibilities: (a) the
already-known mechanism firing on a legitimate-but-new trigger during
startup, with its already-known `git add -A` over-scoping bug sweeping in
unrelated dirty files as collateral — mundane, explicable, matches a bug
we already know exists; or (b) a genuinely different, previously
unidentified autonomous commit mechanism — which would be a real Section
5 concern if it traces back to any of the CCOS self-improvement modules
(`goal_engine`, `auto_improvement_loop`, `capability_optimizer`,
`skill_recombiner`) being reachable from the daemon startup path.

**Decision: pausing the rename sequence (sub-tasks 3/4 on hold).** Sent a
read-only diagnostic task: examine the actual commit contents, trace
every call site of `create_checkpoint()`/`_require_checkpoint()` across
the whole codebase (not just the ones already known), confirm whether any
Section 5-gated module is reachable from daemon startup, build a full
checkpoint-commit timeline, and report — no fixes yet, diagnosis first.

**Next action:** Get diagnosis back. Do not resume sub-tasks 3/4 until
this is understood and, if needed, addressed.

---

## 2026-07-29 — Rename sub-task 2 sent: actual file renames + cross-references

**What changed:** Sent the second of 4 sequenced sub-tasks — flips the
constant values (`.codey-v3`→`.codeyOS` etc.), renames `codey3`→`codeyOS`
and `codeyd3`→`codeydOS` via `git mv`, fixes the self-contamination
already inside those two files (leftover `codey2` references from the
prior rename), and updates every cross-reference found by the audit
(`codey-start`/`codey-stop`, `install.sh`, `setup.sh`'s independent
pre-existing bug, `.claude`/`.qwen` permission files, clone-target
directory in docs/tools). Explicitly scoped away from cosmetic text
(sub-task 3) and historical docs (never touched, per audit
recommendation).

**Next action:** Get results back, verify the real daemon-detection test
specifically (not just path matching) and review the grep-remainder list
before moving to sub-task 3 (cosmetic branding sweep).

---

## 2026-07-28/29 — Termux crash during sub-task 1; contradiction raised and resolved with direct evidence

**What changed:** Termux crashed mid-session. Recovery check found no
orphaned processes (clean), and `git log` showed no sub-task 1 commit —
initially concluded sub-task 1 never ran and needed a fresh attempt.
Discarded unrelated runtime noise (`ccos/data/*`, `test_patch.txt`,
already on the known-safe-to-delete list) via `git checkout -- .`, pushed
2 pending commits.

**Contradiction raised:** when re-sent, Claude Code CLI reported
sub-task 1 was "already done" in commit `9e86a9c` (the same checkpoint
commit already reviewed during the GUI-crash-fix task, which that
session explicitly said only contained the GUI fix's diff). Flagged this
as inconsistent rather than accepting it, requested raw `git show`
evidence.

**Resolved:** `git show 9e86a9c --stat` and `git show 9e86a9c --
utils/config.py` confirmed the commit genuinely contains the exact
sub-task 1 diff — verbatim matching the inline comments from the
original task prompt (`"will become .codeyOS in sub-task 2"` etc.), not
paraphrased or reconstructed. Reconciled the timeline: sub-task 1 was
dispatched and completed successfully after the GUI-fix session ended;
`core/checkpoint.py` auto-committed it (same recurring pattern, 4th
occurrence now); the commit was already pushed to `origin/main` before
the crash occurred. The crash interrupted Claude Code CLI's ability to
report back cleanly, not the actual work — nothing was lost.

**Verification performed:** Direct `git show` output reviewed line by
line, not summarized. All 11 constants confirmed present with exact
specified values; daemon confirmed to still write to identical real
locations (`~/.codey-v3/codey-v3.pid` etc.) — genuinely
behavior-preserving as required. Test suite baseline unchanged (253 +
67 passed, 1 pre-existing sandbox failure, same as always).

**Decisions:** Leave the misleading commit message as-is (already
pushed, matches established precedent of not rewriting pushed history).
No action needed on the sandbox test or the lazily-created `.sock` file
observation — both correctly identified as pre-existing/expected.

**Recurring pattern update:** this is the 4th time
`core/checkpoint.py`'s auto-commit has fired and produced a generic,
content-mismatched message during real work. Given it's now caused a
genuine investigative detour (this session), the case for actually fixing
the underlying `git add -A` over-scoping is stronger than before — still
not blocking, but worth prioritizing sooner rather than later.

**Outcome:** Sub-task 1 confirmed genuinely complete and correct, already
pushed. No rework needed.

**Next action:** Write and send sub-task 2 (actual file renames +
cross-references).

---

## 2026-07-28 — Rename sub-task 1 sent: shared path-constant foundation

**What changed:** Sent the first of 4 sequenced sub-tasks. Deliberately
behavior-preserving — builds the shared constant in `utils/config.py` and
updates the 9 core files confirmed by the audit to independently hardcode
`~/.codey-v3`, but keeps the actual string values unchanged and doesn't
touch any bash scripts or cosmetic text yet. Verification requires
confirming the daemon still writes to the exact same real location as
before — nothing should actually change from a user's perspective at
this stage, only the internal structure.

**Next action:** Get results back, verify no regressions, then sub-task 2
(actual file renames + cross-references).

---

## 2026-07-28 — GUI crash fixed + comprehensive branding audit complete (93 files, 463 occurrences)

**GUI crash fix (commit `d71ed43`):** Root cause confirmed exactly as
traced. `metrics_loop()` independently verified (not assumed) to NOT
share the bug — its `except Exception` correctly doesn't catch
`CancelledError` (BaseException in Python 3.8+), so it already propagates
cleanly. Fix: `handle_ws()` now catches `CancelledError`, closes the
socket, re-raises; `on_shutdown` hook added to proactively close all
active connections. `codey-start`'s double `"Stopping GUI server..."`
traced to separate `INT`+`EXIT` traps both firing — consolidated to
`EXIT` only. Live verification: real SIGINT sent to `gui/server.py`
during active 7B generation, confirmed clean exit, no traceback — honest
disclosure that a full interactive-TUI Ctrl+C wasn't scriptable in this
environment, so the exact underlying code path was tested directly
instead. 253+67 tests pass, 1 pre-existing sandbox failure unchanged.

**Recurring pattern worth noting:** the self-modification checkpoint
system (`core/checkpoint.py`) auto-committed again during this task
(3rd occurrence this project) with a generic message, sweeping in the
uncommitted fix — handled correctly (amended since unpushed, per
established precedent), but three occurrences suggests the underlying
`git add -A` over-scoping bug (flagged, deferred, back during the
quality-gate work) may be worth actually fixing rather than continuing
to defer. Not urgent, just noting the accumulating friction.

**Branding audit (read-only, no changes):** 93 files, 463 occurrences of
Codey-v2/v3 branding and naming cataloged and categorized. Key findings:
- **`codey3`/`codeyd3` themselves already contain leftover stale
  `codey2`/`CODEY_V2_DIR` references from the previous rename** — the
  exact bug pattern we're trying to avoid is already live in current
  code today.
- **Two genuinely separate active bugs found, unrelated to branding:**
  `setup.sh` references a `codeyd2` file that doesn't exist (broken
  today, independent of any rename); `gui/index.html` shows a hardcoded
  `v2.0.0` version badge while the real version (`utils/config.py`) is
  `3.0.0` — active, user-visible.
- **Highest-value insight:** 15+ files independently hardcode
  `~/.codey-v3` rather than importing a shared constant — the actual
  structural root cause of the recurring stale-rename bug class (this is
  the third instance of this exact failure mode found this project).
- Also found: dead `CODEY_NAME` constant in `utils/config.py` (defined,
  never referenced); `docs/codey-v2-tools-embed.md`'s filename itself is
  stale even though its content is entirely about v3; `core/voice.py`
  uses a different base dir (`~/.config/codey-v3/`) than everything else;
  `core/memory_v2.py` has a live filename-detection list including
  `codey-v3.md` (functional, not cosmetic); `core/lora_import.py`
  generates output files named `codey-v3-finetuned-*.gguf`; two
  OpenRouter `HTTP-Referer` headers point at `github.com/codey-v3`.
- Historical docs (`CHANGELOG.md`, `TODO.md`, `AUDIT_REPORT.md`,
  `docs/version-history.md`'s v1.0.0 entry) correctly identified as
  legitimate history, not live branding — recommended leaving alone and
  adding a new entry for the Codey-OS rename instead of rewriting the
  past. Confirmed no unexpected original-Codey (v1) branding found
  elsewhere.

**Decisions made:**
1. Adopt the shared-constant architectural fix (one path constant module,
   imported everywhere) rather than mechanically renaming 15+ hardcoded
   copies — directly addresses the root cause.
2. Clone-target directory (`~/codey-v3`, no dot) → `~/Codey-OS`, matching
   the real repo/folder name already in use throughout this project.
3. Bundle the two adjacent active bugs (setup.sh's broken reference, GUI
   version badge) into the rename work now rather than as separate tasks.
4. PID file naming: adopted the audit's refined recommendation — keep
   `plannd.pid`/`gui-server.pid` as-is (already generic/unversioned,
   never had version baked in), only rename `codey-v3.pid` →
   `codeyOS.pid`. Avoids inventing new names where none existed before.

**Execution plan — sequenced, not one giant sweep:** given 93 files and
the demonstrated risk of partial/inconsistent renames in this exact
codebase, breaking into verifiable sub-tasks: (1) shared-constant
foundation + core entry points, (2) file renames + cross-references, (3)
cosmetic branding sweep, (4) bundled bug fixes + misc (docs filename,
CHANGELOG entry, generated filenames, config dirs, HTTP headers).

**Next action:** Write and send sub-task 1 (shared-constant foundation).

---

## 2026-07-28 — GUI crash found (real bug, first interactive use); branding rename scoped as audit-first

**What changed:** During the first real interactive `codey-start`
session, Ctrl+C during active generation crashed the GUI server —
traced to `gui/server.py:handle_ws()` having no `asyncio.CancelledError`
handling around its WebSocket receive loop, and no `on_shutdown` hook to
proactively close active connections. Root cause confirmed via direct
code reading, not guessed — matches the observed
`GracefulExit`→`CancelledError`→`InvalidStateError` traceback chain
exactly. Also noted: "Stopping GUI server..." printed twice (likely a
trap double-registration in `codey-start`, needs its own root-cause
check) and the still-outstanding "Codey-v2 daemon" stale string (known,
unfixed since Phase 2 item 4).

**Sent:** a direct fix task (root cause was clear enough to skip a
separate diagnosis round) — add explicit cancellation handling + an
`on_shutdown` hook, check `metrics_loop()` for the same issue (bare
`except Exception` doesn't catch `CancelledError` in Python 3.8+), and
root-cause the duplicate shutdown message.

**Branding decision:** Ish confirmed a full rename — `codey3`→`codeyOS`,
`codeyd3`→`codeydOS`, all "Codey-v2"/"V2"/"V3" branding→"Codey-OS"
throughout, including internal paths (`~/.codey-v3`,
`codey-v3.pid`/`.sock`). Given this codebase has already produced two
separate stale-rename bugs this project (the `.codey-v2`/`.codey-v3`
mismatch we fixed, the `codeyd2`/`codeyd4` mismatch found in the old v4
README), and given `codey-start`/`codey-stop` (written last task)
literally shell out to `codeyd3` by name — **scoped this as audit-first,
same pattern as the earlier repo cleanup audit.** Sent a read-only
cataloging task before any rename executes, with a proposed (not fixed)
new path convention (`~/.codeyOS/`) for Claude Code CLI to confirm or
refine once it sees the full picture.

**Next action:** Get both reports back — GUI crash fix results, and the
branding audit catalog. Review the audit together before writing the
actual rename execution task.

---

## 2026-07-28 — Phase 3 Sub-step A complete: codey-start/codey-stop

**What changed:** `codey-start`/`codey-stop` created (commit `4477a5c`).
Design reasoning: daemon deliberately persists after TUI exit (that's
daemon mode's entire purpose — avoiding repeated model-load cost);
`codey-start`'s cleanup trap only tears down what it uniquely started
(the GUI), matching the existing "additive, not destructive" pattern
already present in `codeyd3`/`codey3`.

**Claim independently verified, not just trusted:** the report said
`codey-start` coordinates GUI lifecycle through a PID file "`codey3`
already checks" — this required `codey3` to have pre-existing
GUI-awareness despite being reported as unchanged (zero diff). Checked
directly: confirmed `codey3` genuinely already has this exact
`GUI_PID_FILE="$DAEMON_DIR/gui-server.pid"` mechanism built in (lines
397-415) — matches something observed much earlier too (the live
end-to-end test transcript showed `codey3` auto-starting a GUI
unprompted). Claim holds; skepticism this time confirmed accuracy rather
than catching an error.

**Verification performed:** Reviewed real process-state evidence
throughout — actual daemon PIDs, `ps aux` confirming all 3 model servers
live, `curl`/PID-file checks confirming GUI actually stopped on TUI exit
while daemon remained running (the intended split), final `codey-stop`
sweep confirmed zero orphaned `llama-server` processes, `free -h` showed
memory properly reclaimed (5.1Gi free, up from 4.0Gi baseline).
`codey3`/`codeyd3`/`ccos_main.py`/`gui/start.sh` confirmed byte-for-byte
unchanged.

**Minor open item:** a race-condition fix (orphan-check running before a
killed process fully exits) was syntax-checked but not live-tested, per
RAM discipline — honestly disclosed, not claimed as verified. Worth
confirming on a future live run, low priority.

**Outcome:** Phase 3 Sub-step A complete.

**Next action:** Sub-step B — wire `thermal_monitor` + `observability`
capabilities into an actual live TUI+GUI dashboard, the literal "Unified
system dashboard" requirement.

---

## 2026-07-28 — Phase 3 Sub-step A started: codey-start/codey-stop

**What changed:** Checked `gui/server.py`'s startup mechanics
(`python gui/server.py [port]`, matches `gui/start.sh`'s existing
pattern). Scoped the new scripts as thin orchestrators shelling out to
existing mechanisms (`codeyd3 start`/`stop`, `gui/server.py`'s existing
invocation) rather than reimplementing daemon/GUI startup logic — lower
risk, less duplication.

**Design question raised:** whether the daemon should keep running after
the TUI session exits (daemon mode's whole purpose) or be tied to the
TUI's lifecycle — leaned toward "daemon persists, `codey-stop` is the
explicit way to bring everything down" but asked Claude Code CLI to
reason through it and report, not just implement my lean unquestioned.

**Outcome:** Sent the task with strong RAM discipline reminders (checking
`free -h` before/between start-stop cycles, since this loads the real 7B
model) and required real process-state verification (not just trusting
script output) at each step — daemon running, GUI actually listening,
clean shutdown with zero orphaned processes at the end.

**Next action:** Get results back, verify the 4 existing entry points are
untouched and the daemon-persistence design reasoning makes sense, before
moving to Sub-step B (dashboard data parity).

---

## 2026-07-28 — codey3/codeyd3 mismatch confirmed fixed

**What changed:** Directory variables corrected exactly as specified
(commit `5cc29ee`). Header comments updated to reflect Codey-OS naming.
Repo-wide grep found only 2 remaining `.codey-v2` references, both in
`CHANGELOG.md`/`TODO.md` documenting the historical rename itself, not
live code — correctly left untouched.

**Verification performed:** Reviewed strong evidence — not just a path
comparison, but real end-to-end proof: started the daemon, confirmed live
PID file/socket in `~/.codey-v3`, reproduced `codey3`'s exact detection
logic standalone (confirmed positive), then ran `codey3 status` for real
and got back live daemon stats (PID, uptime, memory, task queue) over the
actual Unix socket — proof the CLI now genuinely talks to the real daemon
instead of silently falling through to standalone mode. Daemon stopped
cleanly afterward, confirmed no leftover processes.

**Outcome:** Foundational fix confirmed. Phase 3's `codey-start`/
`codey-stop` can now be built without inheriting broken daemon detection.

**Next action:** Write Phase 3 Sub-step A — `codey-start`/`codey-stop`
orchestration scripts.

---

## 2026-07-28 — Found a real bug while scoping Phase 3: codey3/codeyd3 directory mismatch

**What changed:** While reading `gui/start.sh`/`codeyd3`/`codey3` to
scope the `codey-start`/`codey-stop` orchestrator, found `codey3` (CLI
client) uses `DAEMON_DIR="$HOME/.codey-v2"` while `codeyd3` (daemon
manager) uses `DAEMON_DIR="$HOME/.codey-v3"` — confirmed against
`core/daemon.py:40` (`SOCKET_FILE = DAEMON_DIR / "codey-v3.sock"`) that
`.codey-v3` is the real, correct directory. This means `codey3`'s
`is_daemon_running()` check has likely never been able to find the real
daemon `codeyd3 start` actually starts — always looking in the wrong
directory, silently falling through to standalone mode instead of
connecting via socket. Same class of bug as the `codeyd2`/`codeyd4`
naming mismatch caught in the old v4 README, and the `core`/`ccos/core`
path-shadowing bug from Phase 1 — leftover version-rename residue. Both
scripts' header comments also still say "Codey-v2"/"codey2"/"codeyd2".

**Why this matters for Phase 3:** building `codey-start` on top of these
scripts without fixing this first would bake the same broken
daemon-detection into the new unified entry point.

**Outcome:** Sent a small, precise fix task — correct the three
directory variables, clean up stale header comments, repo-wide grep to
confirm no other `.codey-v2` references remain, verify `codey3` actually
detects the running daemon post-fix.

**Next action:** Get fix confirmed, then write Phase 3 Sub-step A's
actual orchestration task (`codey-start`/`codey-stop`).

---

## 2026-07-28 — observability.py wrap complete; Phase 3 scoped

**What changed:** 15 capabilities wrapped for `core/observability.py`
(commit `5f297fe`). Confirmed no real overlap with `thermal_monitor` —
different mechanism (process-specific via `psutil.Process(pid)`/`/proc`
fallback vs. system-wide via `/proc`/thermal-zones/battery), correctly
kept independent. Correctly collapsed 3 identical "get everything"
functions (`get_full_status`/`to_dict`/`status()`) into one
`full_status` capability rather than exposing duplicate names for the
same call. `reset_state()` included with sound reasoning (zero current
callers, nothing to protect).

**Verification performed:** Capability count 69→84 (+15, exact). Real
live values checked for consistency against facts already established
earlier in this project: `context_size=32768` matches the known 7B
model's context window; `temperature=0.7` correctly understood as model
sampling temperature (a typical default), not device thermal temp — a
different concept from `thermal_monitor`'s reading, reinforcing the
no-overlap finding rather than contradicting it. Zero diff on
`core/observability.py`. Sandbox test remains sole pre-existing failure.

**Outcome:** The `observability.py` gap flagged during Phase 2's closing
reflection is now closed. Suggested bundling `observability.py`'s
`/status` CLI wiring with `recovery.py`'s `agent.py` failure-path wiring
(item 9's deferral) into one future wiring pass, since they're the same
kind of leftover work — noted, deferred alongside item 7 as planned, no
action needed now.

**Phase 3 scoped:** expanded the plan's Phase 3 section into two
sub-steps per `CODEY_OS_MASTER_VISION.md` Section 6a — (A) build
`codey-start`/`codey-stop` as new orchestration scripts alongside the
existing fragmented entry points, not yet replacing them; (B) wire
`thermal_monitor` + `observability` (both now built) into both the TUI
and GUI for actual dashboard data parity, the literal "Unified system
dashboard" requirement. Retiring the old entry points comes after both
are proven stable, same incremental philosophy as Phase 1/2.

**Next action:** Write Phase 3 Sub-step A's first task —
`codey-start`/`codey-stop` orchestration scripts.

---

## 2026-07-28 — Closing the observability.py gap (found in Phase 2 reflection)

**What changed:** Re-confirmed `core/observability.py`'s interface —
all read-only `State` properties, zero mutating operations, zero current
callers. Lower risk than the last several Phase 2 items. Flagged a
potential overlap with `thermal_monitor` (Phase 2 item 4)'s
`cpu_usage`/`memory_usage` data, since both may be reading similar
system-resource information.

**Outcome:** Sent as its own small task, following the item 9
(`recovery.py`) pattern — standalone wrap now, actual `/status` CLI
wiring deferred separately. Agreed order with Ish: this task, then Phase
3, then a batch review of `PENDING_ISH_DECISIONS.md`.

**Next action:** Get results back, check the thermal_monitor overlap
finding specifically, then move to Phase 3.

---

## 2026-07-28 — Phase 2 COMPLETE: peer CLI escalation (item 10), consolidated pending decisions

**What changed:** Final Phase 2 item complete (commit `ef57fed`). Found
and correctly reasoned about the real consent mechanism —
`PeerCLIManager.confirm()` is a blocking interactive terminal prompt with
no automated-call equivalent, so the entire risky invocation path
(`escalate`/`confirm`/`call`/all of `peer_shell.py`) was left completely
untouched rather than worked around. 4 safe read-only capabilities
exposed instead. Confirmed explicitly: no real external CLI (Claude Code,
Qwen, Gemini) was invoked during testing — only `shutil.which` checks and
one caught local exec failure (broken `claude` shebang in this
environment).

**Verification performed:** Capability count 65→69 (+4, exact). Zero diff
on all 4 protected files. Sandbox test remains sole pre-existing failure.
Reviewed the specific, plausible environment detail (broken `claude`
CLI shebang causing a caught `FileNotFoundError`, correctly distinguished
from a real invocation) as a good sign of genuine testing, not
fabrication.

**Two things acted on from the closing reflection:**
1. Created `PENDING_ISH_DECISIONS.md` — consolidates every
   deliberately-unwrapped, risk-flagged capability from across Phase 2
   (fine-tuning's model-swap trio, daemon's `shutdown`/`command`, peer
   CLI's `escalate`/`confirm`/`call`) into one reviewable place, instead
   of scattered across individual manifest descriptions. Good, actionable
   suggestion, implemented immediately rather than left as a future
   to-do.
2. **Real gap found:** `core/observability.py` was listed in the master
   vision alongside `recovery.py` as "complete but disconnected, needs
   wiring," but only `recovery.py` ever got a slot in Phase 2's 10-item
   list. `observability.py`'s `/status` wrap fell through the cracks
   entirely — noted in `PENDING_ISH_DECISIONS.md` section 4, needs its
   own task.

**Outcome:** Phase 2 complete — 9 of 10 original items fully wrapped
(item 7 deliberately deferred, logged separately, not lost). Consistent
risk-tiered judgment held across the whole phase: fine-tuning, daemon,
and peer-escalation all correctly identified their genuinely dangerous
functions and left them unwrapped with real, specific reasoning rather
than following the "wrap everything" pattern mechanically once real risk
appeared.

**Next action:** Push to GitHub. Then: decide whether to tackle the
`observability.py` gap, review `PENDING_ISH_DECISIONS.md` as a batch, or
move into Phase 3 (retiring old fragmented entry points) — worth a fresh
discussion rather than assuming the next step.

---

## 2026-07-28 — Phase 2 item 10 started: peer CLI escalation (final item, strongest safety framing)

**What changed:** Confirmed `core/peer_cli.py`/`core/peer_shell.py`'s
real interfaces — `run_peer`/`run_direct`/`run_prompted`/`run_positional`
actually spawn real subprocess/pexpect sessions with external CLI tools
(Claude Code, Qwen, Gemini). Highest external-consequence wrap yet — real
time and potentially real API usage, not just device resources.

**Outcome:** Sent the task with the strongest safety constraint of any
Phase 2 item: default to NOT invoking a real peer CLI during automated
testing at all, verify dispatch/argument-construction logic only. Required
checking whether the master vision's noted consent mechanism (for sharing
file contents externally) actually exists in code and is preserved
through the capability layer. Asked for a closing reflection on the
capability-wrapping pattern itself, since this closes out the original
Phase 2 list.

**Next action:** Get results back — check the consent-mechanism finding
specifically, and confirm explicitly that no real external CLI was
invoked during testing, before accepting.

---

## 2026-07-28 — Phase 2 item 9 complete: error recovery

**What changed:** 4 capabilities wrapped
(`classify_error`/`get_fallback`/`execute_strategy`/`record_outcome`).
Overlap resolution matched exactly what was asked, with additional
justification found independently: `StrategySwitcher`'s tracking is
in-memory only, capped at 100 entries, zero callers — confirming
`StrategyTracker` (disk-persisted, already live) is the correct target.
`recovery_record_outcome` routes through `StrategyTracker.record_attempt()`
at the plugin layer only, `core/recovery.py` untouched.

**Notable finds:** honestly documented a real pre-existing bug in
`recovery.py`'s own classification logic ("command not found"
misclassifies as `file_not_found`) rather than hiding or working around
it silently. Used a throwaway strategy name for testing the tracking
routing, explicitly reset afterward to avoid skewing real stats — good
hygiene, not explicitly requested.

**Verification performed:** Reviewed reported evidence — capability
count 61→65 (+4, exact). `classify_error` tested against real exception
message strings. `execute_strategy` correctly tested live only for the
safe mkdir path; pip-install/pytest-isolation paths correctly left
unexecuted, only their fallback-lookup logic exercised. Zero diff on all
3 protected files. Sandbox test remains sole pre-existing failure.

**Outcome:** Phase 2 item 9 complete, standalone scope (not wired into
`agent.py`'s failure path, deferred with item 7). 9 total capability
domains wrapped now.

**Next action:** Item 10 — peer CLI escalation, the last item in the
original Phase 2 list. Check real interface
(`core/peer_cli.py`/`core/peer_shell.py`) before writing the prompt —
likely needs its own risk framing given this delegates to real external
CLI tools and the master vision notes it requires explicit user consent
before file contents are shared externally.

---

## 2026-07-28 — Phase 2 item 9 started: error recovery (overlap confirmed, standalone scope)

**What changed:** Independently confirmed the `recovery.py`/
`strategy_tracker.py` overlap by comparing method sets directly —
genuinely real, not a false alarm. `StrategyTracker` (used by
`learning.py`, disk-persisted) and `StrategySwitcher` (unused anywhere)
both track strategy success rates per error type. `recovery.py`'s unique
value is its actual recovery actions (`classify_error`/`get_fallback`/
`execute_strategy` — real pip-install/file-search/mkdir logic), not its
tracking.

**Outcome:** Sent the task scoped as standalone-only (no wiring into
`agent.py`'s failure path — deferred to bundle with item 7). Required
investigating whether the capability's tracking should use
`recovery.py`'s own mechanism as-is or route through the already-used,
already-persisted `strategy_tracker.py` instead — explicitly without
modifying `core/recovery.py`'s source, since that's outside this task's
boundary (plugin layer only). Strong caution given around not running
`execute_strategy`'s pip-install/shell paths for real during testing
unless clearly safe/idempotent.

**Next action:** Get results back, check the tracking-mechanism decision
and reasoning, verify `execute_strategy` testing was appropriately
cautious.

---

## 2026-07-28 — Phase 2 item 8 complete: daemon interaction

**What changed:** 7 safe capabilities exposed (`system.daemon_*`).
`shutdown` and `command` correctly left unwrapped — reasoning matched
the fine-tuning task's risk framing exactly (agent-triggered daemon kill
mid-planning; agent-triggered real inference as a planning side effect).
`cancel` included as a moderate-risk, scoped exception (single task ID,
doesn't touch the daemon process), same tier as the finetune backup/
rollback functions.

**Verification performed:** Clever, safe testing approach — started a
bare `core.daemon.DaemonServer` (not the full `Daemon` class) on a temp
socket in a background thread, avoiding any model load while still
exercising the real socket/command-dispatch layer. This directly
confirmed (not just assumed) that the socket protocol layer is lightweight
independent of model loading — it's `Daemon.__init__`/`_main_loop` that
pulls in the 7B, not the server layer itself. Real responses captured for
all 7 capabilities. Capability count 54→61 (+7, exact). Zero diff on all
3 protected files. Sandbox test remains sole pre-existing failure.

**Outcome:** Phase 2 item 8 complete. 7 of 10 Phase 2 items done (with
item 7 deferred, not counted against this), plus Phase 1's pilot — 8
total capability domains wrapped.

**Next action:** Item 9 is error recovery
(`core/recovery.py`/`core/strategy_tracker.py`) — has a similar shape
question to item 7. Master vision already established `core/recovery.py`
is complete-but-disconnected (needs a call site in `agent.py`'s
tool-failure path to actually activate automatically) — wrapping it as a
standalone CCOS capability (agent-callable on demand) is straightforward
and fits the established pattern, but *wiring it into agent.py's live
failure-handling path* is a deeper agent.py change, arguably belonging
with item 7's deferred coding-agent work. Also still open: the possible
overlap between `recovery.py`'s own success-rate tracking and
`strategy_tracker.py`, flagged back when `recovery.py` was first
diagnosed. Need Ish's input on scope before writing item 9's prompt.

---

## 2026-07-28 — Phase 2 item 8 started: daemon interaction (risk-tiered again)

**What changed:** Confirmed the daemon's full socket command set (7
handlers: `ping`, `status`, `health`, `task`, `cancel`, `command`,
`shutdown`). Identified the same risk-class split as the fine-tuning
task: `shutdown` kills the running daemon Codey-OS depends on, `command`
is the real task-submission entry point (triggers actual model inference
via the daemon). Applied the same "flag for explicit decision rather than
wrap mechanically" framing that worked well for the model-swap functions.

**Outcome:** Sent the task with explicit risk tiers and instruction to
check daemon running-state before testing rather than assuming/starting
fresh.

**Next action:** Get results back, check the shutdown/command exposure
decision specifically before accepting.

---

## 2026-07-28 — Item 7 deferred (not skipped): recursive self-refinement bundled into future coding-agent wrap

**Decision:** Confirmed with Ish — item 7 doesn't fit the previous 6
items' pattern (standalone utility wrap). It's part of the still-unwrapped
primary "Coding agent (core intelligence)" capability from the master
vision, deeply embedded in `core/agent.py`'s live tool-calling flow via
`core/recursive.py`. Deferring it to be tackled together with that larger,
more important wrap later — explicitly logged here so it doesn't get
silently dropped from the plan.

**Testing note for later, captured now so it's not lost:** when this
eventually gets tackled, avoid loading the real 7B model for routine
testing — already caused one RAM crash during the earlier planner-fix
verification (device was at 8.3/10.8 GB used at idle before the 7B even
loaded). Codey-OS can't run a full coding-agent-sized model for testing
purposes on top of its own already-running stack (7B + 1.5B + embedding)
without real OOM risk. Consider swapping in a much smaller model (e.g.
the existing 1.5B planner model, or something smaller still) purely to
exercise the self-refinement/tool-calling mechanics during development,
reserving real 7B end-to-end testing for deliberate, careful, one-at-a-
time sessions like the ones already done.

**Outcome:** Moving to item 8 (daemon mode) next, per Ish's choice of
option 1.

**Next action:** Check `core/daemon.py`'s real interface, write item 8's
prompt.

---

## 2026-07-28 — Phase 2 item 6 complete: task queue

**What changed:** Path-addressable design implemented exactly as
suggested, with sound independent reasoning (avoiding an in-memory cache
as a redundant second source of truth). 7 capabilities exposed;
`plan_tasks()` correctly left internal to `orchestrator.py`.

**Verification performed:** Capability count 47→54 (+7, exact).
Real disk-persistence proof via actual JSON read-back after a fresh
reload. Confirmed cleanup — only the 2 pre-existing unrelated session
files remain in `~/.codey_sessions/`. Zero diff on all 3 protected files.
Sandbox test remains sole pre-existing failure.

**Outcome:** Phase 2 item 6 complete. 6 of 10 Phase 2 items done, plus
Phase 1's pilot — 7 total capability domains wrapped.

**Next action:** Item 7 is different in kind from everything so far —
"Recursive self-refinement" isn't a separate utility file, it's
`core/recursive.py`'s draft/critique/refine inference loop (already
touched once during the earlier quality-gate fix), deeply embedded in
`core/agent.py`'s live tool-calling flow and requiring the actual 7B
model to do anything meaningful. Doesn't obviously fit the
"thin-wrapper-around-a-utility-function" pattern the previous 6 items
used — it's closer to being part of the *coding agent itself* (still
listed as unwrapped/"needs wrapping as the primary capability" in the
master vision) than a peripheral capability. Flagging this to Ish before
writing a prompt rather than mechanically forcing the established pattern
onto something that may not fit it.

---

## 2026-07-28 — Phase 2 item 6 started: task queue (new architectural shape)

**What changed:** Confirmed `core/taskqueue.py`'s real interface — a
stateful, instance-based `TaskQueue` class with disk persistence
(`~/.codey_sessions/queue_*.json`), architecturally different from every
previous wrap (not a singleton, not pure functions). Flagged the design
question explicitly: capabilities should likely operate on queues by
path (create/add/mark/status, loading from disk each call) rather than
holding an in-memory instance across stateless capability calls, given
`TaskQueue.load()`/`.save()` already exist for exactly this. Confirmed
`core/orchestrator.py:8` imports `TaskQueue` directly for its own
internal session management — instructed to check how, so the capability
wrap doesn't duplicate or conflict with that internal usage.

**Outcome:** Sent the task with explicit instruction to avoid leaving
test queue files behind in `~/.codey_sessions/` (real session data lives
there) and to prove real disk persistence, not in-memory-only behavior.

**Next action:** Get results back, verify the persistence claim and
cleanup specifically, then item 7 (recursive self-refinement).

---

## 2026-07-28 — Backup/rollback capabilities complete; real safety discovery caught

**What changed:** `coding.finetune_create_backup` and
`coding.finetune_rollback_backup` added (commit `43c5ba7`). During
verification, discovered that `rollback_to_backup` reloads the model via
`core.loader_v2.get_loader()`, which binds the model path at import time
— meaning a plain `cfg.MODEL_PATH` monkeypatch alone would NOT have
prevented it from touching the real model despite pointing config at a
throwaway path. This wasn't something explicitly asked for in the task —
it was caught by actually tracing the code path rather than trusting the
surface-level safety instruction to be sufficient. Correctly dual-patched
both `cfg.MODEL_PATH` and `loader_v2.get_loader` (no-op fake loader),
restored both in a `finally` block.

**Verification performed:** Reviewed reported evidence — SHA-256
checksums confirmed the backup was byte-identical to the dummy original,
and rollback restored original content exactly after the dummy was
deliberately corrupted. 8/8 plugin tests pass. Capability count 45→47
exact. Zero diff on `core/lora_import.py` and callers.
`ccos/data/capabilities.json` correctly reverted before commit, per
established discipline.

**Outcome:** Fine-tuning capability (item 5) now fully complete with the
lower-risk backup/rollback functions included per Ish's decision; the
three genuinely dangerous functions (swap/merge/import) remain
deliberately unwrapped. Confirmed all work through this point pushed to
GitHub.

**Next action:** Item 6 — task queue (`core/taskqueue.py`).

---

## 2026-07-28 — Backup/rollback capabilities added per Ish's decision

**What changed:** Ish decided to add both `create_backup_before_import`
and `rollback_to_backup` to the finetune plugin — lower risk than the
actual swap/merge functions (file-copy only), real safety value (agent
can protect current model state before something risky). The three
higher-risk functions (`swap_to_finetuned_model`, `merge_lora_with_llama_cpp`,
`import_lora_adapter`) remain deliberately unwrapped, unchanged from the
previous decision.

**Outcome:** Sent a small, targeted follow-up — same safety framing
(throwaway dummy files only, never real `~/models/` files), required
real before/after evidence for the backup→rollback cycle, expected
capability count 45→47.

**Also confirmed:** Ish pushing all Phase 2 item 5 work to GitHub now.

**Next action:** Get backup/rollback results back, verify, then item 6 —
task queue (`core/taskqueue.py`).

---

## 2026-07-28 — Phase 2 item 5 complete: fine-tuning export, deliberately partial scope

**What changed:** 7 safe capabilities wrapped (`coding.finetune_curate_examples`,
`_export_dataset`, `_generate_notebook`, `_print_instructions`,
`_prepare_data`, `_validate_adapter`, `_adapter_info`) — all generative
or read-only. The 5 functions that directly manipulate the live model
file (swap/merge/backup/rollback/import) were deliberately left
unexposed, per the safety framing given. Reasoning offered went beyond
what was asked: an agent-callable swap risks triggering a live-model
replacement as a side effect of planning, not just deliberate human
action — a materially different risk class from git's mutating
capabilities (which have cheap undo via git itself; a bad model swap
only has this module's own bespoke backup/rollback).

**Verification performed:** Reviewed reported evidence — capability count
38→45 (+7, exact match). Real negative result for a nonexistent adapter
path, real positive result + correct metadata for a throwaway dummy
adapter, real generated `.jsonl`/Jupyter notebook output (nbformat 4, 2
cells) in a throwaway location, and notably `prepare_finetune_data` run
for real against this device's actual (empty) history, honestly returning
`{"error": "No examples found"}` rather than a dressed-up success. Zero
diff on all protected source files. Sandbox test remains the sole
pre-existing failure.

**Outcome:** Phase 2 item 5 complete. 6 of 10 Phase 2 capabilities now
wrapped. Open question sent back to Ish: whether
`create_backup_before_import`/`rollback_to_backup` (lower-risk, file-copy
only) should be added later — undecided, not blocking.

**Next action:** Push to GitHub, then item 6 — task queue
(`core/taskqueue.py`).

---

## 2026-07-28 — Phase 2 item 5 started: fine-tuning export/import (elevated risk tier)

**What changed:** Confirmed real interfaces for `core/finetune_prep.py`
(low-risk, generative — dataset/notebook export) and `core/lora_import.py`
(higher-risk — includes `swap_to_finetuned_model`,
`create_backup_before_import`/`rollback_to_backup`,
`merge_lora_with_llama_cpp`, which directly manipulate the actual active
model file). This is the first Phase 2 capability with real-world
destructive potential beyond a throwaway test artifact — explicit
instruction given to never test mutating `lora_import.py` functions
against the real `~/models/` files, and to consider deliberately NOT
exposing the model-swapping functions as agent-callable capabilities yet,
pending an explicit decision, rather than wrapping mechanically just
because the pattern has held for the previous four.

**Outcome:** Sent the task with strong safety framing and an explicit
request for judgment on which functions deserve to be directly
agent-callable at all, given what they can do to a live install.

**Next action:** Get results back — check carefully whether the
model-swapping functions were tested safely (throwaway files only) or
appropriately left unwrapped, before accepting.

---

## 2026-07-28 — Phase 2 item 4 (thermal/system monitoring) complete — count discrepancy was my own error

**What changed:** `thermal_monitor` plugin completed as a new plugin
(commit `0aac59e`) — correctly not extending `system_info`, given
meaningfully different lifecycle (background-thread sampler + throttle
state vs. one-shot lookups). 8 capabilities registered, not 5 — the
5/8 gap flagged for investigation turned out to be my own tallying
error (miscounted the report's own table, missing that one row listed
two bundled capability names — `thermal_start_inference` /
`_end_inference` — as if it were one). Claude Code CLI's number (38) was
correct from the start; my expected "35" was wrong arithmetic on my part.

**Verification performed:** Requested and reviewed a full reconciliation:
`git log -p -- ccos/data/capabilities.json` confirmed only 2 commits ever
touched that file (initial add + one checkpoint that only modified
timestamps/use-counts, never keys) — direct confirmation the
`git checkout --` discipline before testing has held throughout, no stale
registry accumulation anywhere. Real per-plugin capability counts summed
directly from every manifest.json, reconciling to 38 exactly.

**Correction owned:** flagged this as a possible contamination issue
before checking my own math — it wasn't. Worth the check anyway; it
produced real confirmation of registry hygiene that we didn't have
before, distinct from the arithmetic itself being wrong.

**Outcome:** Phase 2 item 4 complete and reconciled. 5 of 10 Phase 2
capabilities now wrapped, past the halfway point. Pushed to GitHub
(`9d9d8b8..0aac59e`).

**Next action:** Item 5 — fine-tuning export
(`core/finetune_prep.py`, `core/lora_import.py`).

---

## 2026-07-28 — Phase 2 item 4 started: system monitoring + thermal management

**What changed:** Confirmed real interfaces for `core/sysmon.py`
(`SystemMonitor.snapshot`/`.render()`/`.start()`/`.stop()`) and
`core/thermal.py` (`start_inference`/`end_inference`/`get_thermal_status`/
`is_throttled`/`get_current_threads`). Noted `SystemMonitor.snapshot` is
exactly the data source the master vision's "Unified system dashboard"
requirement needs — explicitly flagged in the task so the capability gets
designed as structured data, not just TUI-formatted text, since GUI will
need it too eventually.

**Outcome:** Sent the task with a real design judgement call — extend
`system_info` or create a new plugin (leaning new, given `system_info` is
currently only one-shot lookups vs. this being live background-thread
state) — plus a question about whether monitor lifecycle control
(start/stop) belongs as a capability at all, given the monitor is
presumably already running as part of normal operation.

**Next action:** Get results back, verify real live values were actually
shown (not mocked), continue to item 5 (fine-tuning export) after.

---

## 2026-07-28 — Phase 2 item 3 (voice interface) complete; GitHub push gap discovered

**What changed:** Prior diagnostic findings (dependencies) confirmed still
persisted, no reinstall needed. `install.sh` gap closed —
`pyttsx3`/`espeak`/`termux-api` now declared (were missing; `rich` already
was). Architectural decision: extended the existing `tts_speech` plugin
with STT (from `core/voice.py`) rather than creating a new plugin —
reasoned from the established one-plugin-per-domain pattern. TTS kept on
`tts_speech`'s existing richer 4-engine fallback rather than duplicating
`core/voice.py`'s narrower Termux-only implementation.

**Real independent bug found and fixed:** `manifest.json`'s
`implementation: "tts:speak"` pointed at the entry-point filename, not the
plugin's registered name (`tts_speech`) — `plugin_manager.call_capability()`
looks up by registered name, so this capability could never have resolved
correctly even with all dependencies present. Reproduced the failure
pre-fix and success post-fix. This is likely the real core of "TTS broken
on both sides," beyond the missing-dependency explanation found earlier.

**Verification performed:** Reviewed reported evidence — capability delta
28→30 reconciles exactly (2 net new: `speech.stt_available`, `speech.stt`;
existing `speech.tts`/`speech.tts_engines` were already registered, just
broken). Real TTS test produced an actual 123KB `.wav` file via the
capability layer. STT capability confirmed wired correctly (no exceptions)
but true transcription honestly disclosed as unverifiable in this headless
environment (no real mic/Termux:API audio service attached) — appropriately
scoped limitation, not glossed over. `core/voice.py` confirmed zero diff;
existing callers (`main.py`, `core/plannd.py`) untouched. Vestigial code
(the now-superseded-for-CCOS-use TTS half of `core/voice.py`) correctly
flagged, not deleted.

**Outcome:** Phase 2 item 3 complete. 3 of 10 Phase 2 capabilities now
wrapped (static analysis, git integration, voice interface), plus the
Phase 1 pilot (RAG retrieval) — 4 total CCOS-wrapped capabilities from
`core/` so far.

**Urgent, separate issue raised:** Ish checked GitHub and found nothing
has been pushed — all work since the Codey-OS repo was created (Phase 1
pilot through voice interface, 6+ commits) exists only in local git
history on-device. Real risk of total loss if anything happens to the
device before this is pushed. Asked Ish to run `git status` / `git log
origin/main..HEAD` / `git remote -v` to confirm the gap and commit count,
then `git push origin main`.

**Resolved:** confirmed 10 commits were unpushed
(`37f6532`..`9d9d8b8`), pushed successfully — `bb7ddc2..9d9d8b8 main ->
main` on GitHub. No more local-only risk. Noted a second "Codey checkpoint"
auto-commit (`371a354`) in the unpushed log, alongside the one already
investigated (`263b096`) — expected/consistent with the known
`core/checkpoint.py` mechanism, will keep recurring on core-file writes
until the `git add -A` over-scoping bug is eventually fixed (still a
low-priority open item, not blocking).

**Standing practice going forward:** push after each completed/verified
task rather than letting commits accumulate — will prompt for this at
natural checkpoints rather than assuming it happens automatically.

---

## 2026-07-28 — Phase 2 item 3 started: voice interface (check + wrap)

**What changed:** Structured this task in two parts given the unresolved
history: (1) re-verify Qwen's earlier diagnostic findings (both TTS
implementations were dependency-only failures, got both working
temporarily — `rich`+`espeak`/`termux-api` for `core/voice.py`,
`pyttsx3`+`espeak` for `tts_speech` — never committed to `install.sh`
since that was a read-only diagnostic task), reinstall if drifted, close
the `install.sh` gap this time; (2) wrap voice as a CCOS capability.

**Key framing given for Part 2:** this isn't a clean "pick A over B" —
`tts_speech` is already a proper CCOS plugin, `core/voice.py` isn't
wrapped at all yet, and `core/voice.py` uniquely owns STT. Suggested
(not mandated) that extending the existing `tts_speech` plugin to also
expose STT may be architecturally cleaner than creating a second speech
plugin, matching the one-plugin-per-domain pattern already established.
Required reasoning to be reported either way, and required flagging any
now-redundant code rather than unilaterally deleting it.

**Next action:** Get results back — check Part 1's dependency-persistence
findings specifically before accepting Part 2's wrap as verified.

---

## 2026-07-28 — Phase 2 item 2 (git integration) complete, one honest gap noted

**What changed:** 16 of 17 `core/githelper.py` functions registered as
capabilities (commit `4921c24`). `uses_conventional_commits` correctly
left internal — verified via grep it's only called by
`generate_commit_message`, not independently useful. `get_conflict_sections`
kept as a capability after verifying it's called independently from
`main.py:549/611`, not just as `detect_conflicts`'s internal helper.

**Verification performed:** Reviewed reported evidence — capability math
reconciles exactly (12 baseline → 28, matching established count), real
mutating-operation test used a throwaway repo only (never this actual
repo), with specific concrete evidence (real commit hashes `2f470b1` on
top of `8147828`) rather than vague claims — a good signal of genuine
execution. Zero diff confirmed on all 4 protected files. Sandbox test
remains the sole pre-existing failure.

**Known gap, disclosed not hidden:** 2 of the 16 registered capabilities
were never actually invoked during testing — `generate_commit_message`
(calls `core.inference_v2.infer()`, would require loading the 7B model,
correctly out of scope per the no-7B constraint) and `git_push` (skipped
to avoid network-call ambiguity with no configured remote). Both
reasonable, disclosed decisions — but means "16 capabilities" isn't quite
"16 verified end-to-end," it's 14 proven + 2 registered-but-untested.
`git_push` specifically could be tested offline (two throwaway local
repos, one as a bare "remote") without any real network dependency — not
done, flagged as a low-priority follow-up, not blocking.

**Outcome:** Phase 2 item 2 complete. Moving to item 3.

**Next action:** Item 3 is voice interface (`core/voice.py`) — but this
has an unresolved open item from earlier: TTS is broken on both
`core/voice.py` and `ccos/plugins/speech/tts_speech`, with a "pick one,
fix, verify, remove the other" decision still pending (Ish confirmed both
broken during install; root cause was missing deps, not code bugs, per
earlier diagnosis — deps have likely since been installed as part of
normal `install.sh` runs, worth re-checking current state before deciding).
Need Ish's input on how to sequence this before writing item 3's prompt —
resolve TTS choice first, or wrap what already works (STT + whichever TTS
implementation, deferring the pick/removal decision) and treat TTS
consolidation as its own follow-up.

---

## 2026-07-28 — Phase 2 item 2 started: git integration capability wrap

**What changed:** Confirmed `core/githelper.py`'s real interface — 17
functions, split into read-only (status/log/diff/branches/conflict
detection/commit-message generation) vs. mutating (commit/push/branch
create/checkout/merge) — a meaningfully different shape than the previous
two single-purpose wraps. Confirmed existing callers untouched
requirement against `main.py:464`, `core/orchestrator.py:302`,
`core/agent.py:666`.

**Outcome:** Sent the task with explicit instruction to judge which
functions deserve top-level capability status vs. remain internal helpers
(not a mechanical wrap-everything), and a hard requirement that any
mutating-operation testing use a throwaway repo, never this actual
Codey-OS repository.

**Next action:** Get results back, verify plugin/capability count
reconciliation and the throwaway-repo test evidence specifically before
accepting.

---

## 2026-07-28 — Path shadowing bug fixed; Phase 2 item 1 (static analysis) fully complete

**What changed:** Both fixes implemented (commit `fe00218`) — `_pathutil.py`
now removes any existing occurrence of the repo root and re-inserts at
`sys.path[0]` unconditionally (position, not just presence);
`test_ccos.py` delegates to the shared helper instead of its own
duplicate path logic. Correction on my assumed file layout: no separate
`test_plugin_manager.py` exists — the plugin-load assertion lives inside
`test_ccos.py`'s own `test_plugin_manager()` function, strengthened there
to `assert loaded == len(plugins)` with a detailed failure dict.

**Verification performed:** Reviewed rigorous isolation testing — reverted
the `_pathutil.py` fix alone and reproduced the exact original failure
(`loaded 6`, matching `ModuleNotFoundError` messages for both
`rag_retrieval` and `static_analysis`), proving it was necessary and
sufficient on its own; the `test_ccos.py` change was confirmed as
consistency/hygiene rather than strictly load-bearing. Restored both,
reconfirmed clean state. No independent device-level re-run this round,
but the specificity and self-correcting rigor here (isolating which fix
actually mattered, correcting my wrong filename assumption rather than
silently complying) gives strong confidence.

**Outcome:** Final reconciled state — 8/8 plugins loaded, 12 capabilities
(9 baseline + 1 `rag_retrieval` + 2 `static_analysis`), sandbox test
remains the sole pre-existing, unrelated failure. Phase 2 item 1 is
cleanly, fully done — implementation + the infrastructure bug it exposed.

**Next action:** Begin Phase 2 item 2 — git integration
(`core/githelper.py`).

---

## 2026-07-28 — Real bug found: core/ vs ccos/core shadowing blocks plugin loading

**What changed:** Follow-up investigation on the "loaded 6, 11
capabilities" discrepancy from the static_analysis report found a real,
pre-existing bug, not a rounding quirk. Root cause: `ccos/tests/test_ccos.py`'s
own `sys.path.insert(0, str(Path(__file__).parent.parent))` resolves to
`ccos/` itself (not repo root), putting `ccos/core` ahead of the real
`core/` on `sys.path`. Any plugin importing from outside `ccos/`
(`rag_retrieval`, `static_analysis`, and every future Phase 2 wrap) then
silently fails to load when the CCOS suite runs via the documented
`PYTHONPATH=. python3 ccos/tests/test_ccos.py` command — `ModuleNotFoundError`
resolved against the wrong `core`.

**Verification performed (by Claude Code CLI, reviewed):** Confirmed via
direct reproduction (`pm.load_all()` succeeds standalone, fails under
`test_ccos.py`'s path setup) and via bisection — checked out commit
`81a6b5f` (pathutil fix, pre-dating static_analysis) in a throwaway
worktree and reproduced "loaded 6" there too, proving this predates Phase
2's changes and isn't something newly introduced. Also correctly
identified that `test_plugin_manager.py` only asserts `loaded >= 1`,
letting a 6-of-8 partial load pass silently — a real test-suite gap, not
just a code gap. Confirmed the "12 capabilities" figure from the earlier
report was contaminated by stale persisted state
(`ccos/data/capabilities.json`) from manual test runs outside the broken
path context, now reverted — true reconciled count is 9 (baseline) + 1
(`rag_retrieval`) + 2 (`static_analysis`) = 12 once loading is actually
fixed to 8/8.

**Correctly did NOT fix in that task** — flagged back instead, since the
fix touches `_pathutil.py`/`test_ccos.py`, both explicitly out of that
task's declared scope. Right call per the ground rules.

**Decision:** Fix now, before continuing to Phase 2 item 2 — this bug
compounds across every remaining out-of-`ccos` capability wrap (nearly
all of them) if left unfixed.

**Outcome:** Sent a 3-part fix: (1) `test_ccos.py` delegates to the shared
`_pathutil.ensure_repo_root_on_path()` instead of its own duplicate path
logic, (2) hardened `_pathutil.py` to guarantee repo root is at
`sys.path[0]` (position, not just presence) so this class of bug can't
recur from some other future path-inserting code, (3) strengthened
`test_plugin_manager.py` so a partial load no longer silently passes.
Required proving the strengthened test can actually fail (not just pass
trivially).

**Next action:** Get fix results back, verify 8/8 plugins load and 12
capabilities register cleanly, then resume Phase 2 at item 2 (git
integration).

---

## 2026-07-28 — Phase 2 started: static analysis capability wrap

**What changed:** Confirmed real `core/linter.py` interface
(`run_linter`, `run_all_linters`, `check_syntax`, `format_issues`,
`get_available_linters`) and its four existing callers (`core/agent.py`
x2, `tools/patch_tools.py`, `main.py`) against actual source before
writing the task.

**Outcome:** Sent the first Phase 2 capability-wrap prompt — static
analysis as `coding.lint` (new `coding` category), using the now-fixed
`_pathutil.py` helper from the start. Required a real end-to-end test
(write a throwaway file with an actual lint issue, confirm it's detected
through the plugin, clean up after). Existing callers explicitly
protected from changes.

**Next action:** Get results back, verify, continue to item 2 (git
integration) once confirmed clean.

---

## 2026-07-28 — Phase 1 fully complete: pathutil helper verified

**What changed:** `ccos/plugins/_pathutil.py` implemented and verified.
Design is stronger than requested — anchors the walk-upward search at the
helper's own fixed file location (`ccos/plugins/`, always 2 levels below
repo root) rather than the caller's, which correctly sidesteps caller-
nesting-depth entirely rather than needing to solve for it directly.
`test.py`'s bootstrapping problem (can't `import ccos.*` before `ccos` is
on `sys.path`) solved via `importlib.util.spec_from_file_location` on a
fixed sibling-relative path — correctly distinguished from the original
bug since this relative reference targets a structurally-fixed distance
(every plugin's `test.py` to `_pathutil.py`), not the ambiguous repo-root
distance that caused the original problem.

**Verification performed:** Reviewed the code and reasoning directly — 
technically sound and internally consistent, no live device re-run this
round. Notably rigorous on their end: confirmed the one pre-existing CCOS
test suite failure (sandbox test) predates this change via `git stash`
rather than just asserting it; correctly left `test_patch.txt` (on our
known safe-to-delete list) untouched as out of scope for this task.

**Outcome:** Commit `81a6b5f`. Phase 1 (pilot + pathutil follow-up) is now
fully complete and the shared pattern is proven and reusable.

**Next action:** Begin Phase 2 — wrap the next capability using the fixed
shared pattern. Plan's stated order starts with static analysis
(`core/linter.py`) — simplest remaining capability, single function, no
complex state, good next step to keep momentum before the more involved
ones (daemon, self-refinement, peer CLI escalation).

---

## 2026-07-28 — Phase 1 pilot verified successful; shared pathutil follow-up sent

**What changed:** RAG retrieval pilot completed and reported. Independently
cross-checked the claimed baseline (6 plugins/9 capabilities before, 7/10
after) against the original repo audit from earlier in this project
(system_info: 2 capabilities, camera_capture: 2, tts_speech: 2, three
compound skills: 3 = exactly 9/6) — matched precisely, strong confidence
signal this report is accurate, not fabricated.

**Real finding from the pilot:** every existing plugin's `test.py` uses a
relative `.parent` chain that happens to land on `ccos/` rather than the
true repo root — harmless for ccos-internal plugins, but for any plugin
importing from top-level `core/`/`tools/`/`utils/`/`pipeline/`, this
silently shadows the real `core` package with `ccos/core` (same package
name, genuine naming collision). Fixed locally with `parents[4]` for this
one plugin, but correctly flagged as needing a systemic fix since 9 of the
10 remaining capabilities in the master vision live under those exact
directories.

**Verification performed:** Manual reconstruction of the plugin/capability
baseline from the original repo audit, matched exactly. Technical
coherence check on the `core`/`ccos/core` naming collision explanation —
consistent with known repo structure. No live device access to re-run the
actual verification commands directly this round.

**Outcome:** Sent a small, scoped follow-up task — shared
`ccos/plugins/_pathutil.py` helper using walk-upward repo-root resolution
(not another hardcoded index, so it stays correct regardless of a future
plugin's nesting depth), applied to the existing `rag_retrieval` plugin to
prove it works, before Phase 2 wraps the remaining capabilities.

**Next action:** Get pathutil helper results back, verify, then proceed to
Phase 2 — wrapping the next capability using the now-fixed shared pattern.

---

## 2026-07-28 — Phase 1 pilot started: wrapping RAG retrieval as first CCOS plugin

**What changed:** `~/test` manual-testing directory deleted (redoable
later when needed). Returning to the main Codey-OS unification plan after
the two side-fix detours. Confirmed `core/retrieval.py`'s real interface
(`retrieve()`, `retrieve_for_error()`, `retrieval_status()`, etc.) and the
actual CCOS plugin pattern from the real `system_info` plugin (manifest.json
structure, thin implementation module, `test.py` convention,
`plugin_manager._discover()` auto-scanning — no manual registration step).

**Outcome:** Sent the Phase 1 pilot prompt — wrap `core/retrieval.py` as a
CCOS plugin (category TBD: new `knowledge` or reuse the existing empty
`ccos/plugins/research/`), thin adapter only, existing direct-call path
left untouched (retiring it is Phase 3, not now). Explicit requirement to
verify actual discovery + registration + invocation, not just that files
exist, plus an honest assessment of whether the pattern was clean to
repeat 9 more times.

**Next action:** Get results back, verify independently, then use this as
the template for the remaining capabilities in Section 3 of the master
vision.

---

## 2026-07-28 — Quality gate fix reported; autonomous commit + possible orphaned process flagged

**What changed:** Claude Code CLI reported all 4 required changes for the
quality-gate fix (issue #2/#3) implemented and verified — user_message
threaded into the critique prompt (confirmed via prompt-construction
inspection), Fix B implemented as an opt-in `return_confidence` param on
`recursive_infer()` returning `(draft, low_confidence, quality)` when
True, backward-compatible for existing plain-str callers
(`core/orchestrator.py` untouched). Mocked tests for both low-confidence
(2/10, floor 4.0) and normal (9/10) paths behaved as designed. Full suite:
253 passed, 0 failed.

**Two more urgent findings surfaced during this same report, not yet
resolved:**

1. **A background "Codey checkpoint" process autonomously committed to
   git** (commit `263b096`, message "Codey checkpoint: Self-modification:
   test_patch.txt") without being invoked by Ish or the CLI session. It
   swept in the 4 legitimate fix files plus unrelated pre-existing dirty
   changes (`.qwen/settings.json`, `ccos/data/*`, two
   `ccos/plugins/compound/*/pipeline.py` files) that were never reviewed.
   This directly touches `CODEY_OS_MASTER_VISION.md` Section 6's stated
   non-goal of activating autonomous self-modification by default —
   `core/checkpoint.py` (a real, active module, confirmed in the earlier
   repo audit as imported by `main.py`'s "self-mod commands") appears to
   be doing exactly that, unprompted. **Not resolved — do not know what
   triggers it, on what schedule/condition, or what else it may have
   silently committed before this was noticed.** Correctly not
   amended/reset (would be destructive) — but this needs its own
   investigation before being dismissed as just a commit-hygiene issue.
2. **Possible orphaned `llama-server` process (PID 30408)** — Claude Code
   CLI's report cut off mid-sentence describing a manual test that
   "accidentally escaped its mock context," possibly spawning a real
   model server unintentionally during what was meant to be a mocked
   test. Given known tight RAM (8.3/10.8 GB used at idle in an earlier
   session), this needs an immediate check, not a deferred one.

**Verification performed:** None yet on the fix itself — no local copy of
the post-change repo to independently re-diff, unlike earlier findings in
this project. Flagged as a real limitation rather than treated as
verified.

**Decision:** Paused before accepting the fix as done or deciding what to
do about the stray commit. Priority order: (1) confirm/kill the possible
orphaned process immediately, (2) investigate `core/checkpoint.py`'s
autonomous commit trigger before deciding how to handle the commit itself
or continuing further work, (3) come back to independently verifying the
quality-gate fix once the above is resolved.

**Update — checkpoint mechanism investigated, de-escalated:** traced the
trigger directly. `core/checkpoint.py`'s `create_checkpoint()` is only
called synchronously from `core/filesystem.py:_require_checkpoint()`
(lines 196/247/302), which fires whenever Codey's own file-write/patch/
delete tools touch a file matching `core/*.py`, `tools/*.py`, `utils/*.py`,
or `prompts/*.py`. **This is not a background daemon or autonomous
self-improvement (not Section 5 territory)** — it's a deliberate,
synchronous rollback-safety feature: checkpoint before modifying core
files. It only fired because the quality-gate fix touched exactly those
patterns, via Codey's own agent tooling.

Two real but minor bugs found in the mechanism itself, not anything
alarming: (1) the git commit logic uses `git add -A` (stages the entire
working tree) instead of scoping to the specific `files_modified` passed
in — this is why unrelated dirty files got swept into the commit; (2) the
commit message (`f"Self-modification: {path.name}"`) only reflects a
single filename even when multiple files are involved. Both are small,
well-understood, fixable — candidates for a future small cleanup task,
not urgent.

**Resolution:** RAM confirmed fully resolved — the orphaned process was a
real 7B model accidentally loaded during an early manual test (escaped
its intended mock context), self-caught and killed by Claude Code CLI,
RAM verified recovered to 3.6Gi, all subsequent verification used mocked
`infer()` calls exclusively. No further action needed.

**Commit decision:** leave `263b096` as-is — do not amend/rewrite, since
this repo pushes to GitHub and rewriting a possibly-already-pushed commit
risks diverging history for no real benefit. The content is verified
correct; this log entry is the accurate record of what happened, serving
as the "proper description" instead.

**Residual gap, not blocking:** Fix A's completeness-check verification
confirmed the critique *prompt* is now correctly constructed (includes
user's original request + new completeness instruction), but this is
construction-level, not a live model call proving a real critique
actually downgrades an incomplete draft. Reasonable given RAM constraints
this session — worth confirming with a real end-to-end run next time the
7B is loaded, same way the planner fix was validated live earlier.

**Open question sent to Ish:** whether any of the mocked verification
scripts were added as permanent tests under `tests/`, or were one-off
manual checks with no lasting regression protection — pending answer,
not blocking.

**Side-thread closed.** Both reliability issues found during the earlier
end-to-end test (#2 quality-gate completeness, #3 max-depth floor) are
now fixed and reasonably verified, with the two residual gaps above noted
for later, not urgent. Returning focus to the main Codey-OS unification
plan — Phase 1 pilot capability wrapping — per the standing instruction
not to let side-quest reliability fixes become the primary thread.

---

## 2026-07-28 — Quality-review gate root cause traced; fix prompt sent

**What changed:** Traced issues #2/#3 from the end-to-end test directly
(no diagnostic round needed — found via direct code reading). Root cause
of #2: `_build_critique_prompt()` in `prompts/layered_prompt.py` never
receives the original user request — its own docstring confirms this
("critique: unused" for user_message) — so the critique step can only
judge draft coherence, not task completeness. Confirmed `recursive_infer()`
already receives `user_message` from its caller in `core/agent.py`
(~line 1481), just doesn't thread it through internally — small, precise
fix, not a redesign. Root cause of #3 confirmed directly: max-depth
fallback in `core/recursive.py` accepts the draft "even if quality didn't
pass," no floor.

**Decision:** Ish chose both A (show result with honest caveat) and B
(ask how to proceed) for low-confidence handling, combined.

**Verification performed:** Direct source trace only — this fix prompt
was written without a separate diagnostic round since root cause was
already conclusively found by reading the code directly.

**Outcome:** Sent a scoped fix prompt covering: (1) thread `user_message`
into the critique phase + update critique instructions to require
completeness-checking, not just correctness, (2) add a
`LOW_CONFIDENCE_FLOOR` (4.0/10) at max depth with caveat+confirm flow
before executing any tool call from a low-confidence draft, reusing the
existing `ask_confirm` pattern. Explicitly required Fix B's integration
plan be reported before implementation (real design decision on signal
mechanism between `recursive_infer()` and its caller). Scoped tightly to
avoid drifting from the main Codey-OS unification work — explicit file
boundaries given.

**Next action:** Get results back — integration plan, diffs, verification
output (especially confirming normal single-action tasks don't get
unnecessary caveats/prompts added), commit hash. Verify independently
before considering resolved. After this, return focus to the main
Codey-OS unification plan (Phase 1: pilot capability wrapping) rather than
continuing to chase reliability issues found during testing — track any
further findings but don't let them become the primary thread.

---

## 2026-07-28 — First real end-to-end test: fixes confirmed, several new issues surfaced

**What changed:** Ish ran a full manual session through `codey3` with the
7B model loaded (restarted after the earlier RAM crash, tested in a
separate `~/test` directory). This is the first genuine end-to-end
validation since the planner routing fix.

**Confirmed working (the actual fixes from this project):**
- Conversational messages ("hello", "what can you do for me?") correctly
  skipped the planner and got plain-text responses — validates both the
  `is_complex()` gate and the pre-existing `is_qa` mechanism working
  together as hypothesized.
- File creation, patching, and shell execution tool calls all functioned
  end-to-end (write_file, patch_file, shell, note_save all fired
  correctly at least once).
- Real error recovery observed live: a `ModuleNotFoundError: No module
  named 'flask'` was caught, triggered an auto-retry, saved a note, ran
  `pip install Flask`, and retried successfully — confirms error-recovery
  behavior works for at least this class of error (separate from the
  still-disconnected `core/recovery.py` — this appears to be a different,
  already-wired mechanism; worth clarifying the relationship later).

**New issues surfaced (not previously known, not yet fixed):**
1. **Recursive draft/critique loop frequently produces no tool call on
   first attempt** — "No tool call found for action step — forcing tool
   retry" fired 7 times in one session, on nearly every action. Real
   latency/reliability cost, not cosmetic.
2. **Quality-review step accepted wrong output at 9/10 twice in a row** —
   when asked to edit+run app.py, the model's "draft" was just the prose
   "Patched app.py" with no actual patch tool call, and Review scored it
   9/10 "Accepted" both times. Only corrected after Ish explicitly called
   out the mistake.
3. **Max-depth fallback accepts arbitrarily low quality** — hit
   "[Recursive] Max depth — using draft (quality 2/10)" and used it
   anyway, producing visibly garbled output ("Very gooDoned."). No quality
   floor once retries are exhausted.
4. **Model claimed success when the result demonstrably failed** — said
   "Done, the script has been executed" for the Flask app; browser then
   showed "site can't be reached." Only acknowledged a problem after Ish
   reported the failure, not proactively.
5. **`is_qa` gate may be over-eager for implicit action requests** —
   "what files exist in the current directory?" got a non-answer
   ("run `ls -la` yourself") instead of the tool actually being run. This
   is a direct side effect of the same conversational-detection mechanism
   we just confirmed working correctly for genuine chat — worth tuning,
   not reverting.

**Verification performed:** Full manual transcript reviewed line-by-line
against what was claimed vs. what actually happened at each step —
several claimed successes ("Done," "executed," "stopped") had no
corresponding tool call visible in the transcript, or were later
contradicted by observed behavior (browser unreachable).

**Decision:** Did NOT mark these as "everything fixed" despite Ish's
initial read — the two specific fixes from this project are validated
working, but the broader session surfaced five new, real reliability
issues in the core recursive agent loop that need their own honest
tracking, not folded into "fixed" status.

**Tooling note:** Ish now has a Claude subscription and will run future
prompts through Claude Code CLI instead of Qwen CLI where preferred.
Prompt-writing and independent verification discipline continue
unchanged regardless of which CLI executes them.

**Next action:** Decide with Ish how to prioritize the 5 new issues
above — likely candidates for the next round of diagnosis-then-fix
prompts, same pattern as the planner routing work. Not urgent to fix
immediately, but should not be lost track of.

---

## 2026-07-27 — RAM crash during prompt 05 verification; low-footprint testing established

**What changed:** Qwen crashed while verifying the planner fix — starting
the full daemon (`codeyd3 start`) loads the 7B model, and device RAM was
already at 8.3/10.8 GB used at idle *before* the 7B load even began,
leaving almost no headroom for the model + its 32k-token context cache.

**Investigation:** Found `codeyd3` has no lighter-weight start option —
`start` always launches both the 1.5B planner and 7B agent together.
However, `start_plannd()` is a genuinely standalone shell function
underneath, invoking `llama-server` directly for just the 1.5B model
(500MB) on port 8081. This means the planner-routing verification we
actually need doesn't require the 7B at all:
- `is_complex()` gate: pure Python logic, no model needed
- `Edit` template presence: string content check, no model needed
- Planner actually producing a correct `Edit` step: only needs the 1.5B
  planner, callable directly via `get_plan()`, not the full CLI/7B

**Outcome:** Sent a resume prompt that: (1) checks for orphaned processes
from the crash and confirms what was already committed before restarting
work, (2) explicitly forbids starting the 7B for this verification round,
(3) walks through testing each piece at the lightest weight that actually
proves it — direct Python calls for the routing logic, a manually-started
standalone 1.5B-only planner for the Edit-step generation check. The
original task's conversational-CLI tests (which do need the full 7B) are
deferred to a separate, careful, RAM-aware session rather than attempted
here.

**Open item for later:** the high idle RAM baseline (8.3/10.8 GB before
any model load) is worth investigating on its own at some point — could be
Termux/Android overhead, or something else running — but not blocking
right now since the lightweight testing approach avoids the problem
entirely for this task.

**Next action:** Get resume results back — confirm prior commit state,
routing logic test results, Edit-template planner output, pytest results.
Full end-to-end CLI testing (including the conversational-mode
verification from prompt 06) happens later, deliberately, one careful run
at a time, not bundled into routine verification.

---

## 2026-07-27 — Planner diagnosis verified; fix prompt sent (fresh context)

**What changed:** Independently re-verified Qwen's planner diagnosis
against actual source: `aiohttp` confirmed already correctly declared in
`requirements.txt` (lines 7, 73) and `install.sh` (line 145) — the gap was
just not-yet-installed, no code fix needed. `core/plannd.py`'s
`PLANNER_PROMPT` confirmed to only have `Create`/`Run` templates, no
`Edit` template. `core/agent.py:1256` confirmed to gate its own planning
behind `is_complex()`; `main.py`'s `_run_with_plan` confirmed to call the
1.5B daemon planner unconditionally with no equivalent gate. Root cause
is structural (routing mismatch + missing prompt template), not a model-
capability problem — concluded the shelved fine-tuned 0.5B model
wouldn't have avoided this on its own, since the issue is which tasks get
routed to the planner and what templates it has, not model quality at the
routing layer.

**Decision:** Ish wants both fixes done together in one task (the
`is_complex()` gate + the `Edit` template addition), executed in a fresh
Qwen context window.

**Verification performed:** Direct grep against `requirements.txt`,
`install.sh`, `core/plannd.py`, `core/orchestrator.py`, and `core/agent.py`
confirming every specific claim in Qwen's diagnosis report.

**Outcome:** Sent a self-contained fresh-context prompt with both fixes,
the exact current `PLANNER_PROMPT` text included so Qwen doesn't have to
rediscover it, explicit instruction to re-verify line numbers/text before
editing (since fresh context + prior diagnosis could have drifted), and a
4-part verification requirement (original failing case, a case that should
still plan correctly, a case needing a real `Edit` step, full pytest run)
before considering this done.

**Next action:** Get results back, verify diffs and test output
independently before treating this as resolved.

---

## 2026-07-27 — First live test surfaces two issues: missing aiohttp, bad planner output

**What changed:** Ran `codeyd3 start`/`status` — confirmed all three model
servers live (7B on 8080, planner on 8081, embedding on 8082, verified via
`curl` health check and `ps aux`). First live end-to-end test through
`codey3` ("add a docstring to the speak function in core/voice.py")
surfaced two problems:
1. `ModuleNotFoundError: No module named 'aiohttp'` on GUI server startup
   — same pattern as the earlier `rich` gap, a real dependency never
   installed.
2. The 1.5B planner produced two consecutive bad plans: one describing
   overwriting `core/voice.py` with an unrelated toy implementation, one
   inventing an entirely different filename (`docstring_speak.py`)
   unrelated to the actual task, with what looks like leaked internal
   prompt text inside the plan itself. Ish interrupted both runs during
   the drafting phase.

**Verification performed:** Traced the actual write-safety path in
`tools/file_tools.py:tool_write_file` — confirmed `confirm_write` defaults
to `True` in `utils/config.py` and does prompt before overwriting an
existing file. Since `core/voice.py` already exists, this gate would have
fired before any real damage — Ish's interrupt happened during drafting,
before execution reached the write step. So the file was never actually at
risk this run, though the underlying plan quality is still a real problem.

**Outcome:** Sent Qwen a two-part prompt: (1) fix the aiohttp gap +
update install.sh per the ground rule, (2) read-only diagnosis of the
planner issue — reproduce the exact prompt/response sent to the 1.5B
model, check what context it's actually given about the target file,
check for repeat-attempt consistency, and identify whether a simpler
single-step classification should have applied instead of full
multi-step planning. Explicitly no fix proposed yet — diagnosis first.

**Open question this raises:** possible connection to the earlier decision
to skip the custom fine-tuned 0.5B planner in favor of the generic 1.5B —
worth revisiting once the diagnosis comes back, since a fine-tune built
specifically for this planning task might not have this problem.

**Next action:** Get Part 1 + Part 2 results back, verify independently
before deciding on any fix.

---

## 2026-07-27 — Correction: UnlimitedClaude is real, not fabricated

**What changed:** Earlier in this project (README rewrite phase), Qwen
added "UnlimitedClaude" as a peer CLI escalation partner with a GitHub
link; I flagged it as fabricated and had Ish revert it. The Codey-OS
install output just surfaced "UnlimitedClaude" again as a legitimate
backend option (alongside OpenRouter), which prompted a direct code check.
**Correction: UnlimitedClaude is real** — confirmed in
`core/inference_openrouter.py`, `core/plannd.py`, `core/planner_service.py`,
`utils/config.py`, and `install.sh`. It's a Claude-API cloud backend
(same role as OpenRouter, Claude-specific), not literally invented. Ish
confirmed: "similar to OpenRouter, just another provider for Claude API."
My original error wasn't the name itself — it was calling it fabrication
without checking the actual source first. (The GitHub-link/peer-CLI
framing Qwen originally used may still have been a miscategorization —
UnlimitedClaude is backend routing, not peer-CLI-style task escalation —
but the underlying feature is genuinely real.)

**Why this exists in Codey-OS without any work needed:** Codey-OS is
built from Codey-v3, which has always had this feature. It was apparently
dropped somewhere in the Codey-v4 branch (another item alongside
`symbolic_graph.py` that went missing in v4 without a deliberate decision
visible anywhere) — irrelevant now since v4 is retired and Codey-OS never
lost it in the first place.

**Verification performed:** Direct grep across v3 source confirming all
5 file references, cross-checked against the actual `install.sh` runtime
output Ish pasted.

**Outcome:** `CODEY_OS_MASTER_VISION.md` Section 3 updated — the old
"OpenRouter cloud fallback" row is now "Cloud backend fallback," covering
both OpenRouter and UnlimitedClaude accurately.

**Next action:** Waiting on `codeyd3 start` / `codeyd3 status` output to
confirm the daemon and model servers are actually live.

---

## 2026-07-27 — v4 removal, model path verification, install.sh ground rule

**What changed:**
- Corrected an earlier mistake: v4's actual installed commands are
  `codey4`/`codeyd4` (confirmed at `install.sh:272-273`), not `codeyd2`/
  `codey2` as its README's Quick Start section claimed — that README text
  was wrong before we touched it, and I failed to verify it against
  `install.sh` when doing the earlier literal README rewrite. Noted for
  awareness, not re-litigated.
- Confirmed real collision risk between Codey-v4 and Codey-OS: different
  commands and PID directories (`~/.codey-v4/` vs `~/.codey-v3/`, no
  conflict), but **identical model server ports (8080/8081/8082)** — the
  two must never run simultaneously. Rule: always `codeyd4 stop` before
  `codeyd3 start`.
- Ish confirmed removing Codey-v4 from device (repo stays on GitHub,
  untouched, per earlier decision). Nothing lost — all useful findings
  already captured in this log and the master vision doc.
- Verified `install.sh`'s expected model paths against Ish's actual
  `~/models/` layout: 7B agent and embedding model match exactly by path
  and filename (will be detected, not re-downloaded). Planner model does
  NOT match — Codey-OS's `install.sh` expects a generic
  `Qwen2.5-Coder-1.5B-Instruct` at `~/models/qwen2.5-coder-1.5b/`, but
  Ish's device has `~/models/qwen2.5-0.5b/`, which — discovered via
  comparing v3 vs v4 install.sh — is actually **`Ishymoto/qwen2.5-0.5b-
  codey-planner-gguf`, a custom fine-tune Ish made specifically for
  Codey's planning task**, used by v4 but not currently wired into
  Codey-OS's install.sh at all.
- **Decision: skip the fine-tuned model for now, use the generic 1.5B**
  that Codey-OS's `install.sh` already expects. No `install.sh` changes
  needed for models — it'll download only the ~1GB 1.5B model, since 7B
  and embedding are already present and will be detected.
- Sent Qwen a small prompt to add a formal ground rule to `QWEN.md`: any
  task that adds a dependency or setup step must update `install.sh` in
  the same task, so a fresh clone always stays fully installable.

**Verification performed:** Direct grep against `install.sh` in both v3
and v4 source for command names, PID/state directories, model server
ports, and model directory/filename/URL variables.

**Outcome:** Path forward is clear — run `install.sh` as-is (no changes
needed), remove `~/Codey-v4` from device after stopping its daemon, and
the custom fine-tuned planner model is shelved for a future revisit, not
lost or discarded from the repo history.

**Open item for future revisit (not urgent):** the custom fine-tuned 0.5B
planner model (`Ishymoto/qwen2.5-0.5b-codey-planner-gguf`) is real,
existing work — worth reconsidering wiring it into Codey-OS later even
though we're going generic for now.

**Next action:** Ish to remove `~/Codey-v4` after confirming `codeyd4` is
stopped, then run `install.sh` in `~/Codey-OS`. Report back any errors +
final status.

---

## 2026-07-27 — TTS diagnosis verified; discovered Codey-OS was never installed

**What changed:** Qwen's TTS diagnosis came back — neither implementation
had a code bug; both were missing dependencies (`core/voice.py` needed
`rich` + `espeak`/`termux-api`; `tts_speech` needed any one of its 4 engine
backends). Both work once deps are installed. Spot-checked the key claim
(`rich` missing) against `utils/logger.py` (confirmed imports
`rich.console.Console`) and `requirements.txt` (confirms `rich>=14.0.0` is
a core dependency) — checks out. Incidentally reconfirmed the
`psutil`-skipped-on-Termux / `/proc` fallback detail from the earlier
`observability.py` read, via `requirements.txt`'s own comments.

**Important context surfaced:** Ish clarified `~/Codey-OS`'s `install.sh`
was never actually run — only Codey-v4 was ever installed on-device. This
explains why base deps like `rich` were missing. Model servers (7B agent,
0.5B planner, embedding encoder) are also not yet running for this repo.

**Verification performed:** Direct grep against `utils/logger.py` and
`requirements.txt` in the local v3 source.

**Outcome:** TTS decision paused, not abandoned — `core/voice.py` owns
STT (no CCOS equivalent exists) and CLI integration, so it survives
regardless; still deciding whether to keep its own TTS engine or swap in
`tts_speech`'s broader 4-engine fallback chain. Bigger priority right now:
get `install.sh` actually run on-device before more capability-wrapping
work, since most of that work will need live model servers to test
against properly.

**Next action:** Ish running `./install.sh` directly in Termux (not
delegated to Qwen — interactive, does model downloads/pkg installs).
Report back any errors + final status output. Then resume the TTS
decision and move into real capability-wrapping work.

---

## 2026-07-27 — Grounding step verified: QWEN.md in place

**What changed:** Qwen confirmed `CODEY_OS_MASTER_VISION.md` present at
repo root, generated a real structure snapshot, created `QWEN.md` with
project identity, authoritative-spec pointer, ground rules (lazy-import
lesson, no-fabrication requirement, no scope creep), and known open items.
Committed as `37f6532`.

**Verification performed:** Independently recomputed file counts directly
against the local Codey-V3-main source (`find <dir> -name "*.py" | wc -l`
per directory). All numbers matched exactly: `core/` 55, `ccos/` 55,
`pipeline/` 25, `tests/` 17, `tools/` 6, `utils/` 4, `prompts/` 4, repo-wide
total 169 Python files. Only trivial discrepancies: Qwen's "27 modules" for
`ccos/core/` vs. my direct count of 17 `.py` files there (likely counting
recursively including `memory/` subdir, not fabricated), and a 1-file
difference in total file count (216 vs 215, likely just a timing artifact
of when QWEN.md itself was created relative to the count). Nothing
indicates invented content this round.

**Outcome:** Grounding step complete and trustworthy. Foundation is in
place for the next phase of actual unification work.

**Next action:** Decide and write prompt 2. Candidates: (a) resolve the
TTS decision (test both `core/voice.py` and `tts_speech`, pick one, fix it,
remove the other), or (b) begin the real unification work — wrapping the
first v3 capability as a CCOS-registered plugin. Given TTS is small,
self-contained, and was explicitly flagged by Ish, doing it first is a good
low-risk second win before tackling the bigger unification work.

---

## 2026-07-27 — Master Vision signed off; first Qwen prompt issued (grounding)

**What changed:** `CODEY_OS_MASTER_VISION.md` finalized and signed off by
Ish after two revision rounds (resolved `recovery.py`/`observability.py`
as keep-and-wire-up after full code review; added unified GUI/TUI
dashboard requirement and `codey-start`/`codey-stop` unified entry points;
confirmed TTS broken on both implementations, deferred pick-one-and-fix
decision). This document is now canonical — nothing going forward should
conflict with it without an explicit, logged decision to revise it.

**Why this matters for how we work from here:** Ish wants every future
Qwen prompt scoped small enough to execute correctly in a fresh context,
but large enough to avoid excessive prompt-count. First prompt is
deliberately non-code: save the master vision into the repo (done manually
by Ish) and have Qwen generate `QWEN.md` — a grounding file every future
fresh Qwen session reads first, pointing to the master vision as
authoritative and encoding the specific lessons learned this project
(lazy-import blind spot, no-fabrication requirement, no scope creep beyond
the current task).

**Verification performed:** N/A yet — this entry documents issuing the
prompt, not its results.

**Outcome:** Sent Qwen prompt 1 of the restructuring sequence — grounding
only, no code changes. Ish to place `CODEY_OS_MASTER_VISION.md` in
`~/Codey-OS` repo root before running it.

**Next action:** Get QWEN.md + structure snapshot + commit confirmation
back, verify independently, then write prompt 2 (start of actual
unification work — likely: resolve `core/voice.py` vs `tts_speech`
TTS decision, or begin wrapping the first real capability, TBD based on
what makes sense once grounding is confirmed in place).

---

## 2026-07-27 — Repo created: Codey-OS

**What changed:** New GitHub repo `Ishabdullah/Codey-OS` created, seeded
from Codey-v3, remote repointed. This is now the active working directory
on Termux (`~/Codey-OS`). Codey-v4 repo left as-is on GitHub (no action) —
kept as the read-only reference source for pulling migration pieces from
(`~/Codey-v4` on device, untouched).

**Why:** Codey-v4 didn't fit as the project name once the base shifted to
v3+CCOS. Decided against reusing/renaming the existing Codey-v3 repo to
keep its history intact as a clean fallback reference.

**Verification performed:** Confirmed via `git remote -v` inside
`~/Codey-OS` that origin points to `https://github.com/Ishabdullah/Codey-OS.git`
(both fetch and push) — verified directly by Ish, not just claimed.

**Outcome:** Working directory is `~/Codey-OS`. Qwen now operates here,
with `~/Codey-v4` available to read from but not write to.

**Next action:** Write and run the Phase 1 Qwen prompt — pilot migration
of RAG retrieval as the first CCOS plugin, pulling the implementation
pattern from `~/Codey-v4/core/embedding_service.py` and
`~/Codey-v4/core/retrieval.py`.

---

## 2026-07-20 — Project pivot: v4 retired, building forward from v3+CCOS

**Decision:** After auditing both codebases, agreed to stop developing
Codey-v4's Kernel layer and instead build the pluggable-OS vision on top of
Codey-v3, which already contains CCOS.

**What led here:**
- Fixed a blocking syntax error in v4's `core/kernel.py` (unclosed `try`,
  duplicate dead code, missing `import logging`). Verified fix compiles
  and instantiates cleanly.
- Two-pass audit of v4's 12 claimed capabilities: only RAG retrieval and
  the three-model architecture were confirmed routed through the Kernel;
  error recovery and peer CLI escalation were partial; the remaining 8
  were still direct-call, unmigrated from v2 behavior.
- Rewrote v4's README.md to match verified findings. Caught and reverted
  two rounds of Qwen introducing unverified content not in the source of
  truth (a fictional "UnlimitedClaude" peer CLI, an invented fourth model
  at port 8083) — final version replaced via literal find-and-replace with
  a `git diff` required as proof.
- Audited Codey-v3's CCOS subsystem: all 19 core modules present, compile
  clean, **68/68 tests pass** across 7 suites (test_ccos, 
  test_agent_orchestrator, test_goal_engine, test_project_engine,
  test_telemetry, test_improvement_loop, test_skill_recombiner).
- Confirmed `ccos/` and `core/` in v3 have zero imports between them —
  fully independent systems today.
- Confirmed v3's `core/` is nearly identical to v4's `core/`, minus v4's
  Kernel additions, plus one file v4 dropped: `symbolic_graph.py` (open
  question — see plan).

**Outcome:** New PROJECT_PLAN.md created for Codey-v3+CCOS as the active
project. v4's Kernel classes (`ServiceRegistry`, `ManagerRegistry`,
`DecisionEngine`, `PolicyEngine`) are not being carried forward as the
long-term routing mechanism — CCOS's `capability_registry`,
`plugin_manager`, `tool_router`, and `agent_orchestrator` supersede them.
v4's service-adapter files (`coding_service.py` etc.) are kept as a
reference pattern for wrapping `core/` functions as pluggable units.

**Next action:** Confirm open questions in plan section 5 (symbolic_graph.py
disposition, project naming, Phase 1 pilot choice), then write the Phase 1
Qwen prompt to wrap RAG retrieval as the first CCOS plugin.

---

## Template for future entries

```
## YYYY-MM-DD — <short title>

**What changed:**

**Why:**

**Verification performed:** (tests run, diffs checked, compile checks —
be specific; do not accept a Qwen summary alone as verification)

**Outcome:**

**Next action:**
```
