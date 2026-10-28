# Worlds: disposable Restoricon dev stores (WP2.2)

A **world** is a throwaway, empty Restoricon store (state dir, SQLite DB,
document store, action-gateway audit path and a dev API port) that lives
outside `~/.codeyOS`. Development and testing run on a world, never on the
live store (`CLAUDE.md` rule 0(b): data integrity is the binding constraint).
WP2.2 makes that enforced in code rather than a convention.

This is a **seatbelt against mistakes, not a security boundary** (NEW-1069 is
the unscheduled OS-boundary work package).

## Quick start

```
python3 -m tools.world create dev1            # prints the dir and a port (18770-18999)
eval "$(python3 -m tools.world env dev1)"     # exports the world's variables into THIS shell
python3 -m restoricon_core.api.server --port "$RESTORICON_API_PORT"   # dev API, no --world flag
python3 -m tools.world list [--json]
python3 -m tools.world destroy dev1           # dry run: prints what would go, exits 2
python3 -m tools.world destroy dev1 --yes     # deletes it
```

Exit codes: 0 ok, 2 refusal/validation, 1 unexpected. `destroy` never prompts
(it cannot hang a script or a shell tool) and never signals a process: stop a
world's services with their normal PID-tracked stop first (rule 3). It refuses
while a PID file in the world's `state/` names a live PID or the world's port
accepts a connection.

## Layout

The worlds root is `CODEY_WORLDS_ROOT` (absolute) or, by default,
`<passwd home>/.codeyOS-worlds` (a sibling of `~/.codeyOS`, never inside it).
It is created 0700 with a `.codey-worlds-root` marker.

```
<root>/.codey-worlds-root        marker (list/destroy require it)
<root>/<NAME>/world.json         manifest: name, port, root, dev/ino of the dir
<root>/<NAME>/state/             = CODEY_STATE_DIR
<root>/<NAME>/state/restoricon.db                 = RESTORICON_DB_PATH
<root>/<NAME>/state/restoricon_documents/         = RESTORICON_DOC_STORE_PATH
<root>/<NAME>/state/action_gateway_audit.jsonl    = CODEY_ACTION_GATEWAY_AUDIT (created lazily)
```

`NAME` matches `[a-z0-9][a-z0-9_-]{0,39}`; `production`, `live`, `default`,
`restoricon`, `codeyos` and `worlds` are reserved. Worlds are **empty**
(schema only); no live data is ever copied in.

`env NAME` prints exactly: `CODEY_STATE_DIR`, `RESTORICON_DB_PATH`,
`RESTORICON_DOC_STORE_PATH`, `CODEY_ACTION_GATEWAY_AUDIT`,
`RESTORICON_API_HOST=127.0.0.1`, `RESTORICON_API_PORT`, and
`RESTORICON_WORLD_NAME` (informational only: nothing treats it as
authorization). It prints no token and never `--world production`.

## What a world isolates

State dir (`CODEY_STATE_DIR`: pid, socket, log, `state.db`, `config.json`
resolution), the Restoricon DB, the document store, the action-gateway audit
path and the API port. Because the world has its own `config.json` location,
the live `~/.codeyOS/config.json` is not read by processes started with the
world's variables.

## What a world does NOT do

- **Not an OS-level boundary (NEW-1069).** Code running as your user can still
  open `~/.codeyOS/restoricon.db` by other means: opaque script execution
  (`python3 -c ...`, accepted residual G15b-19), editing source, raw
  `sqlite3` calls. Aigentik and litestream read live by design.
- **Manifest and marker are mistake guards**, not authentication. The manifest
  binds to the world dir's device/inode so a copied `world.json` is refused,
  but a same-uid process can forge one. Keep **only worlds** in the worlds
  root: sibling directories are not protected from each other.
- `HOME` is not changed, so tools using `Path.home()` still see the real home
  (only the variables above are redirected). Aigentik is not repointed.
- **Ports are advisory.** `create` picks the first port in 18770-18999 not
  recorded by another world and bindable at that moment; another process can
  still take it before you start. The server then fails loudly; this is not a
  safety property.
- Import-time state in other modules (NEW-855, NEW-1011) still goes to
  `~/.codeyOS` when `CODEY_STATE_DIR` is unset: mitigated in worlds only, via
  the exported `CODEY_STATE_DIR`; the lazy-init refactor is parked.
- **Hardlinks (NEW-1112 item 4):** the post-open inode check is tested only
  with symlink swaps; `os.link` is absent on this Termux Python, so hardlink
  detection is untested on this device. Same-process fd reuse and a
  swap-to-nonexistent-live 0-byte creation are also reviewer-accepted
  residuals (NEW-1112 items 2-3).

## The fail-closed default and `--world production`

There is no default DB path. `DatabaseManager()` with no path and no
`RESTORICON_DB_PATH` raises `WorldConfigError`; a path (explicit or via the
env) that classifies as the live store raises `LiveStoreRefused` unless
`production=True`. The same holds for `restoricon_core.api.server`,
`migrate_aigentik`, `backfill_wo_351695937` and `tools/provision_ai_agent_auth`
(exit 2 before any bind, banner or connection). An unclassifiable path is
also a refusal (`WorldConfigError`), never silently allowed.

Production is authorized only by the argument `--world production` (the
`production=True` keyword in code). `core/service_lifecycle.py` adds it only
on a positive match of the configured DB to the live store; operators type it
by hand for the CLIs. It is never an environment variable. A production open
prints one `PRODUCTION open of live store` line to stderr.

## Protected-path pattern `restoricon.db*` (T-PROT)

`core/protected_paths.py` protects `restoricon.db*` only when the file sits
directly in a state-dir root (`CODEY_STATE_DIR`, `$CODEY_STATE_DIR`,
`$HOME/.codeyOS`). Consequences, pinned by tests:

- **Inside a world session** (env exported) the world's `restoricon.db*` is a
  protected root: agent file and shell tools are denied it, exactly like live.
  `$HOME/.codeyOS` stays a root too, so live is still denied.
- **Outside a world session** the world DB is an ordinary file to the agent
  tools (it is disposable, empty, never live-derived). The pattern was
  deliberately not widened and `protected_paths` was not changed.

## Troubleshooting

- `refusing to open live Restoricon store ... (pass --world production)`:
  the path is the live store. Use a world, or (operators only) `--world production`.
- `WorldConfigError ... RESTORICON_DB_PATH`: nothing to open. Run
  `eval "$(python3 -m tools.world env NAME)"` or pass `--db`.
- `refused: ...` from `tools.world`: a name, root, marker or manifest check
  failed; nothing was changed. A broken world is listed as `state: broken`
  and must be removed by hand (there is no force flag).
- Port in use at server start: pick another world or stop the other process
  (by PID, never by name).

## Tiers (rule 7)

Code-complete and code-reviewer-approved; the refusal of the live store
(S3) and a production start were live-verified by Ish on 2026-10-28.
`tests/test_wp22_s5_cross_surface.py` asserts the cross-surface pair (refused
on Python, CLIs, server, file tools and shell; a world session opens its own
DB but not live; only `production=True` opens live) against tmp fixtures,
never the real store. The S4 world tool's own attended check is a separate
step.
