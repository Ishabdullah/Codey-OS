---
name: wp2_3a_sandbox_ccos_allowed_dirs_removal_approved
description: WP2.3a — removed ccos/ from Sandbox.ALLOWED_DIRS (self-modification hole, decision 5) — APPROVED
metadata:
  type: project
---

Round: removed `str(Path(__file__).parent.parent)` (the `ccos/` repo dir) from
`ccos/core/sandbox.py`'s `ALLOWED_DIRS`, per Ish's decision 5 — a sandbox
that can write to the capability layer governing it is a self-modification
hole, to be granted later behind the promotion gate, not inherited from a
pre-gate config default. APPROVED, clean pass.

**Verification done, not just trusted:**
- Grepped all `Sandbox(` construction sites repo-wide: only
  `ccos/tests/test_skill_recombiner.py`, `test_improvement_loop.py`,
  `test_ccos.py`, `test_sandbox_path_validation.py` — all use
  `tempfile.TemporaryDirectory()`/`tmpdir`-scoped paths, never the real
  `ccos/` dir, so removal is a true no-op for them. Ran all four files:
  28 passed.
- Checked the *other* `ALLOWED_DIRS` entry (`~/.local/share/ccos`, a data
  dir, untouched by this diff) isn't confused with the removed one — it's
  a different thing (data dir, not `ccos/core` source) and decision 5 only
  targets the source/capability-layer path.
- Confirmed the new invariant test (`test_ccos_dir_is_not_in_allowed_dirs`)
  checks *resolved* paths (`Path(d).resolve()`), so it would still catch a
  symlink or a renamed variable pointing back at the same real directory —
  not just a source-text grep that a refactor could dodge.
- Checked `capability_optimizer.py`'s default `_data_base` (defaults to
  `ccos/data`, inside the repo) and `skill_recombiner.py`'s `__file__`-based
  paths — neither touches `ALLOWED_DIRS` and both are out of this diff's
  scope; noted but not a blocker since the sandbox has no live callers.

**Gotcha for future sandbox rounds:** this repo's `Sandbox.ALLOWED_DIRS`
has two conceptually different entries — the repo-source `ccos/` dir (now
removed, decision 5) and a `~/.local/share/ccos` *data* dir (left in).
Don't conflate the two when reasoning about "self-modification hole" scope
— only the source/capability-layer one is the hole decision 5 names.
