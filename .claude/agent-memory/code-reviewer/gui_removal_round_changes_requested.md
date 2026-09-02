---
name: gui-removal-round-changes-requested
description: 2026-09-02 whole-GUI removal round (rule-4) — code sound, blocked on 4 doc/ledger items; keyword-only grep sweeps miss effect-named references
metadata:
  type: project
---

Ish decided 2026-09-02 to remove the browser GUI entirely (Restoricon
Core `/admin` replaces it; a GUI may return later). Round deleted
`gui/index.html`, `gui/server.py`, `lib/gui_launch.sh`, the
`start_gui`/`stop_gui`/`status_gui` arm of `lib/service_manager.sh`,
`utils/config.py`'s `GUI_PID_FILE`/`GUI_CLIENTS_FILE`/`get_gui_config()`,
and `core/resource_gate.py`'s `is_gui_client_connected()`.

**Verdict: CHANGES REQUESTED — code sound, blocked on doc/ledger items
only.** Verified good and worth not re-litigating next round:
- The removal-vs-vestigial-stub call was correct. `is_gui_client_connected()`'s
  last branch (`count > 0` and **no** `gui-server.pid`) returned `True`
  unconditionally. With no writer left, a user who merely `git pull`s
  keeps their old `~/.codeyOS/gui-clients.count` → `is_interactive_session_active()`
  True forever → `can_dispatch_task()` defers ALL daemon background
  dispatch silently. Deleting the read path was necessary, not tidy.
- Both prod callers (`core/daemon.py:1166`, `core/loader_v2.py:1041`) are
  no-arg; zero repo hits for `gui_clients_file=`/`gui_pid_file=`.
- `lib/service_manager.sh` case statement + function boundaries clean
  (`bash -n` passes on all six launchers); 6 `start_all_services` call
  sites (codey x5, codey-start x1) all de-argumented; no orphan EXIT trap
  left behind (the only surviving `trap` is `codeydOS:159`).
- Suite reproduced verbatim: `2 failed, 1068 passed, 1 skipped` (tests/)
  and `107 passed` (ccos/tests) — matched the implementer's claim exactly.
- Audit finding **C-2 is resolved-by-removal** (see [[gui_c2_remediation_sequence]]).

**Reusable lesson — a keyword sweep misses effect-named references.**
A case-insensitive `gui` grep across every launcher returned *empty*, yet
`install.sh:449` still printed `→ browser: http://localhost:8888`. The
line names the *effect* ("browser"), not the thing. On any removal round,
also sweep the port/URL/path constants (`8888`, `localhost:8888`,
`gui-server`, `gui_launch`) — that is what caught it.

**Second reusable lesson — provenance settles a dependency-removal
dispute that offline dep-graph checks can't.** The implementer dropped
`aiohttp` from `requirements.txt` on "its only importer was
`gui/server.py`." True for the **core** section. But
`git log --oneline -S 'aiohttp' -- requirements.txt` + `git blame`
showed the *pipeline*-block entries (Step-2 pip line and the pinned
`aiohttp>=3.9.0`) came from commit `290dd02` (2026-03-29), the same
commit that added `datasets`/`huggingface-hub`/`fsspec==2026.2.0` —
three days **before** `b667248` (2026-04-01) added the GUI core line.
So that block is a hand-maintained transitive-closure list for HF
`datasets`, and an import-graph argument never applied to it.
Corroborated by primary source: installed `fsspec` metadata declares
`aiohttp ...; extra == 'http'`, and `datasets` depends on `fsspec[http]`.
Also left `docs/installation.md:128` contradicting `requirements.txt`.

**Blocking list handed back:** `CODEY_MASTER_PLAN.md:6735-6736`
(authoritative repo map still lists `gui/` and `gui_launch.sh`, deleted
in this same diff, in a file the diff edits 5 times — 6th occurrence of
the stale-doc-shipping-with-its-own-code pattern, see
[[resource_gate_74a_subtaskF_swap_cap_recalibration_stale_status]]);
`install.sh:449`; `docs/installation.md:128` vs `requirements.txt`
aiohttp; and `NEW_ISSUES.md`'s 46 new lines left **unstaged** while the
brief asserted "the full change is STAGED."

**Non-blocking, told them to log:** `/admin` supplies no
interactive-session signal, so `is_interactive_session_active()` is now
TUI-only — a human watching the web dashboard gets background dispatch
on top of them (verified `/admin` in `restoricon_core/api/web_surfaces.py`
reads no CPU/RAM/thermal of its own, so `core/dashboard_data.py`'s new
"shared-by-design for a future surface" docstring is accurate, not
stale-on-arrival). `docs/security.md:92` still describes `gui/server.py`
as live. And their own new **NEW-280** names the wrong gate in its fix
direction: the tests already patch `_is_port_open`, which does not gate
the adopt branch — `_port_is_bound()` at `core/embed_server.py:83` does.
Those two `test_embed_server_*` failures are genuinely pre-existing and
environmental (adopt branch taken against the live embed server on 8082);
`EmbedServer.stop()` never kills an adopted server, so running the full
suite with models resident is safe.

## Round 2 — APPROVED (one required text correction, no re-review)

All four blockers and four warnings fixed; core code byte-identical to
round 1 (`--numstat` unchanged: `core/resource_gate.py` 24/80,
`utils/config.py` 7/46, `codeyOS` 0/7). B-3 resolved the right way —
they **restored** both pipeline `aiohttp` entries (annotated
`# pipeline: transitive via fsspec[http]/datasets`) rather than editing
`docs/installation.md`, so `requirements.txt:42-46` and
`installation.md:125-130` now list identical packages. Ledger work is
unusually good: `NEW-280`'s corrected fix direction says *in the entry*
that the first version named the wrong gate (rule 6 in practice, not
a silent swap), and `NEW-282` records the `/admin` gap with an explicit
fail-closed requirement.

**One defect the fix itself introduced:** `docs/security.md:95` now says
`/admin` "is covered by section 8 rather than here" — `grep -n '^### '`
shows the file only has sections 1-7. Dangling pointer, and the real
gap behind it is that the Core API's web surface has **no** security.md
section at all now that §6 is a tombstone. Flagged as required-before-
commit text fix, not a re-review.

**Process note:** they used `git add -A` (28 paths). It was clean this
time and `.claude/agent-memory/` is legitimately tracked here (66
commits touch it, no `.gitignore` entry), but the standing project rule
is still to stage an explicit file list — verify the staged path list
by hand whenever `add -A` is reported.
