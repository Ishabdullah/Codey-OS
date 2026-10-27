# WP2.1 group 15, slice G15a: census report 1

Written 2026-10-22 by the G15a implementer; round 2 (2026-10-22) applied the
code-reviewer's W1/W2/S1 findings and the opt-in gate decision below, and regenerated
every output from HEAD (tool version 2). This is a mechanical first run, not a
classification. It owns no finding IDs and no completion status; WP2.1 is OPEN.
No review claim: `tools/wp21_census.py` and its tests have not been through
code-reviewer. Counts below are candidate rows, not bypass counts.

## Provenance

- Snapshot: `git archive` of HEAD `941ec3fb076d97e6e0998c0ea98eee086e6b0915`
  (full hash and the sha256 of all 332 scanned files are in
  `docs/wp21_census/941ec3fb/run_meta.json`, together with the pattern-set hash,
  Python version 3.14.6 and tool version 2).
- Foreign in-progress edits excluded by construction (scan reads the archive, not
  the working tree). `run_meta.json` lists the dirty paths (including
  `core/process_boundary.py` and `tools/shell_tools.py`, whose HEAD content was
  scanned while the working tree differs); the row TSVs deliberately carry no
  dirty column so `scan.tsv` is a pure function of the revision (`run_meta.json`
  is not: its dirty list reflects the tree at run time). The three foreign test
  files and `.claude/` (including an untracked `.claude/settings.local.json`
  that appeared during the session and was not created by the tool) are dirty
  but outside scan scope. Nothing was modified or staged.
- Run time about 3 s, parse failures: 0.

## Counts (first run)

Total rows 1,433: 919 Python (AST), 159 shell/launcher/workflow text, 355
manifest (round 1 was 1,427 / 913; the +6 are the W1 fix, below). Dispositions seeded: 1,427 UNKNOWN, 5 READ_NOEFFECT, 1 GATED. Rows with
no disposition (not covered by the register): 0, because every row starts as
UNKNOWN. UNMEDIATED rows: 0, meaning "nobody has classified anything yet", not
"none exist". The real position is **1,427 of 1,433 rows are unclassified.**

By category: sqlite_write 334, fs_write 287 (was 281), network 58, exec_spawn 48,
sql_dynamic 78, dyn_code 31, env_mut 30, kill 19, credential 11, sqlite_conn 14,
sqlite_exec 9, plus shell 159 and manifest 355 (kinds, not Python categories).

By top directory (all kinds): ccos 535 (355 are manifest rows), core 324 (was 319),
restoricon_core 304, root 113 (was 112; 107 shell: launchers and install/setup scripts, 6
Python), tools 39 (26 Python, 13 `setup_skills.sh`), lib 37, telemetry 29,
pipeline 25, bench 14, utils 11, .github 2.

By class per directory: core has the only seeded rows (1 GATED, 5 READ_NOEFFECT,
318 UNKNOWN); every other directory is 100% UNKNOWN. "Top directories by
unmediated rows": undefined until classification; by unclassified Python
candidate rows the order is core (324), restoricon_core (304), ccos Python
(180), tools (26), telemetry (29), pipeline (25), bench (14), utils (11).

The kill rows (19) include the five `os.kill(pid, 0)` liveness probes (seeded
READ_NOEFFECT) and, new versus the spec's 9, the `*.kill/*.terminate` attribute
forms on Popen-like objects in `ccos/core/plugin_manager.py`,
`core/embed_server.py`, `core/loader_v2.py`, `core/process_identity.py`,
`core/voice.py`.

## Mechanical seeds (and why so few)

- 5 READ_NOEFFECT: `os.kill(pid, 0)` with a literal 0 signal (`core/daemon.py`,
  `core/embed_server.py`, `core/resource_bus.py`, `core/resource_gate.py` x2).
  This matches the five probe sites the spec enumerates (the spec's prose says six but lists five).
  Real signal senders
  (`process_identity.py`, `loader_v2.py`, owned `killpg` paths) stay UNKNOWN.
- 1 GATED: `core/symbolic_graph.py::SymbolicGraph.clear.<locals>.clear_graph`,
  `*.execute`, via the one-level helper rule (its only reference is the
  `execute=` thunk of a `gate_exec`).
- The spec's sizing probe found 22 of 703 rows lexically gated. This tool finds
  1, because it deliberately treats only the thunk keyword (`gate_exec(execute=)`,
  `persist_coalesced(write=)`) as the mediated body. During development the first
  version seeded `core/lora_import.py::_confirm_on_tty` (the `confirm=` prompt
  callback, not an effect mediated by the gate); that was a false seed and the
  rule was narrowed. The 22 figure is not reproduced and not reconciled here: it
  used an unknown scanner. Do not assume mediation from the spec's 22.
- Nothing is marked GATED/NATIVE_AUTHORITY/BOOKKEEPING on a "module is
  probably fine" basis.

## restoricon_core handling (the spec's 210 SQL rows)

This tool finds 304 rows in `restoricon_core/`: 223 constant-SQL write rows
(`sqlite_write`), 67 `sql_dynamic`, 7 `fs_write`, 5 `network`, 1 `sqlite_conn`, 1
`sqlite_exec`. The spec's "210 of 223" does not reconcile (different scanner;
`PRAGMA`/`CREATE` handling, dynamic-SQL treatment and exclusions may differ). Not
investigated further. Per the spec's cross-track note, the register holds these
at qualname/count level: 192 `file::qualname::category` entries with an
expected count, class UNKNOWN. The coverage check fails when any count changes
or a new qualname appears; `gate_restoricon=False` (library option) downgrades
those to warnings if Ish prefers the "scan-reported but not gated" option. The
real authority gate for restoricon (`BUSINESS_MUTATION_AUTHORITY`,
`tests/test_business_mutation_authority_coverage.py`) was not re-evaluated.

## What the scanner cannot see

- Reachability/mediation: it enumerates candidates; callers across modules and
  dynamic dispatch are invisible, except the one-level reverse-reference rule.
- Name-based matching: `*.attr` calls resolve only by attribute name, so
  `x.kill()`/`.terminate()` on non-process objects and `.execute(arg)` on
  non-SQL objects (78 `sql_dynamic` rows) are false-positive-prone; `str.replace`
  is excluded by argument count, `.write()` on file handles is not matched at all
  (the `open(...,'w')` row is the boundary).
- **From-import receiver hole (W1), found by code-reviewer after round 1, now
  fixed.** In round 1, an attribute call whose receiver was a from-imported
  NAME (`from utils.config import NOTES_FILE as N; N.write_text(..)`) resolved to
  `utils.config.NOTES_FILE.write_text`, which does not start with `*.`, so the
  attribute-method rules (`ATTR_FS`, `KILL_ATTR`, `.open(mode)`) never fired and
  the call produced no row. Six real sites were missed: `main.py:462` mkdir
  (`TUI_SESSIONS_DIR`), `core/checkpoint.py:29` mkdir (`CHECKPOINT_DIR`,
  import-time), `core/embeddings.py:172` and `core/symbolic_graph.py:99`
  (`STATE_DB_FILE.parent.mkdir`), `core/notes.py:35` (`_NOTES_FILE.parent.mkdir`)
  and `core/notes.py:36` `write_text`. Fix (`_receiver_is_from_import_value`): a
  call rooted at a from-imported Name whose source module is not in
  `sys.stdlib_module_names` and whose resolved dotted name matches no
  module-function pattern is classified as the unknown-receiver `*.<attr>` form.
  The stdlib exclusion and the no-pattern-match condition guarantee no existing
  row is re-labelled or double-counted (`os.remove`, `shutil.copy2`,
  `subprocess.run`, `google.cloud...` keep their single row). Re-run on HEAD:
  exactly those six rows appear (all `fs_write`) and nothing else; total 1,427 ->
  1,433. Residual: a stdlib-rooted from-import used as a value receiver
  (`from tempfile import tempdir; tempdir.x()`) is still invisible; a local
  variable shadowing a from-imported name is still treated as the import
  (file-wide alias table, as before).
- Row-key ordinal positionality (S1): the key's ordinal numbers same-callee
  calls within one qualname in source order. Swapping two identical-callee calls
  in one function gives identical keys, so a register decision can silently
  follow the swap. A hash of the first argument's source text was considered
  and NOT adopted (it would stay stable under line shifts and reordering of
  unrelated statements, but it rewrites every existing register key, turns any
  argument edit into stale+new rows, and cannot tell identical-argument calls
  apart). Document-only: a diff that reorders same-callee calls inside one
  function needs those rows' dispositions re-checked by hand.
- Parse failures (W2): a file that does not parse contributes zero rows. The
  coverage check now reports `parse-failure` as a failure for any production
  boundary file (downgraded to a warning only for a dirty/foreign path, under the
  same rule as other findings). `tests/**` is never scanned, so it cannot trip it.
- Aliasing: imports are resolved file-wide (`import x as y`, `from x import y as
  z`), but `env = os.environ`, `getattr(subprocess, "run")`-style indirection
  with constant names, and `functools.partial` are not tracked; SQL held in
  non-module-level variables is `sql_dynamic`.
- Env census sees only direct `os.environ[...]/get/getenv` reads; wrapper
  helpers (for example `_env_bool("X")`) and names built dynamically show as
  `<dynamic>` (4 sites) or not at all.
- Shell/workflow scan is a line regex, not a shell parser (heredoc bodies,
  string contents and comments mid-line produce false positives/negatives).
  JSON manifests: `ccos/data/capabilities.json` is not in HEAD so absent;
  the `authority_listed` flag only checks that the capability name is a key of
  `CAPABILITY_AUTHORITY` (40 names), not the class value or manifest raise-tags.
- Other repos (Codey-Aigentik JS, Private-Codey-Agent) and `tests/` are out of
  scope; root files without a shell shebang are skipped. Plugin `test.py` and
  `demo_*.py` ARE scanned (only `tests/**`, `conftest.py`, `test_*.py` skipped;
  `bench/tasks` fixtures are scanned and included in the 14 bench rows).
- Static only. The dynamic complement (`wp21_audit_trace.py`, spec 2.8) is not
  built in G15a.

## Taxonomy note

The task text says 11 classes; the spec table lists 11 dispositions plus UNKNOWN
(12 values). The tool implements all 12 (`CLASSES`), UNKNOWN being the initial
state.

## Files

- `tools/wp21_census.py` (tool), `tests/test_wp21_census.py` (tests)
- `docs/wp21_census/dispositions.tsv` (register: 1,337 entries = 1,321 seeded
  (1,315 + the 6 W1 rows, all UNKNOWN) + 16 rows for the census tool's own code, which is not in HEAD yet, registered as
  UNKNOWN pending independent classification; until the tool is committed they are
  stale-row warnings, not failures)
- `docs/wp21_census/941ec3fb/{scan,shell_scan,manifest_scan,env_names,cli_flags}.tsv`,
  `run_meta.json`, `summary.json`

## How to re-run

```
HOME=/abs/tmp/home CODEY_STATE_DIR=/abs/tmp/state \
CODEY_ACTION_GATEWAY_AUDIT=/abs/tmp/state/audit.jsonl \
python3 -I tools/wp21_census.py --repo . --rev HEAD --out /abs/tmp/census \
    --register docs/wp21_census/dispositions.tsv --seed --check
```

`--seed` writes `dispositions.seed.tsv` into `--out` (existing register entries
are preserved; only missing keys are added); the tool never writes into the
repo itself. `--source worktree` scans files in place and then treats failures on
dirty paths as warnings. `--strict` makes remaining UNKNOWN rows fail (closure
check; also `WP21_CENSUS_STRICT=1 pytest tests/test_wp21_census.py`). At this
HEAD, `--check --strict` reports 1,427 failures by design. Byte-for-byte
reproducibility: rerun at the same HEAD and compare `scan.tsv` hashes.

## Workflow and limits to know

- `--seed` writes only under `--out`. A developer who adds a boundary must copy
  the new `dispositions.seed.tsv` rows into `docs/wp21_census/dispositions.tsv`
  by hand (existing dispositions are preserved by the merge). Once committed,
  Track B SQL/qualname-count changes under `restoricon_core/` fail the default
  suite unless Ish opts for `gate_restoricon=False`.
- **Gate is opt-in blocking (round 2 decision).**
  `test_repo_head_snapshot_is_covered_by_register` runs in the default suite but
  is WARN-ONLY: a coverage gap becomes a pytest `UserWarning` (visible in the
  warnings summary) and the test passes; it fails only when
  `WP21_CENSUS_GATE=1`. Rationale: the register is >99% UNKNOWN, so it carries
  no safety signal yet and a blocking gate would only fail unrelated commits on
  bookkeeping. Flip it to blocking when classification completes. The STRICT
  closure test (`WP21_CENSUS_STRICT=1`) stays opt-in. Skip entirely with
  `WP21_CENSUS_SKIP_REPO=1`.
  **Superseded 2026-10-27:** the gate is now blocking by default;
  `WP21_CENSUS_GATE` and the warn-only branch were removed from
  `tests/test_wp21_census.py`. STRICT stays opt-in and `WP21_CENSUS_SKIP_REPO=1`
  still skips. The paragraph above is kept as the round-2 history.
- The repo-level coverage test scans the HEAD snapshot, not the working tree
  (spec 2.3 asked for the working tree; the brief forbids reading foreign
  edits) and takes about 4 s. It cannot see a committer's own
  not-yet-committed new rows locally; it catches them after commit. The
  foreign-dirty warn path is unit-tested only.
- `git archive` honors `export-ignore`/`export-subst` attributes (including
  `.git/info/attributes`). Neither `.gitattributes` nor `.git/info/attributes`
  exists at this HEAD; a future one could silently drop or alter scanned files.
- Out-of-scope observation for NEW_ISSUES: `restoricon_core/database.py:1074`
  emits a `SyntaxWarning` (invalid escape `"\S"` inside a SQL comment string);
  the scanner suppresses it, the source defect is not fixed here.
