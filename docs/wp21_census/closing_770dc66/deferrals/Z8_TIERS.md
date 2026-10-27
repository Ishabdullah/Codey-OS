# Z-8 "five group-14 evidence tiers": definition found; DRAFT statement (scratch; unsigned; Ish accepts or requests live runs)

## Where it is defined

The definition IS in the docs, as five SLICES rather than a tier vocabulary:

- `docs/wp2_1_g15z_spec.md` section 6.3 (line 449): "**Z-8** | Group-14 slices 14a, 14a-ext, 14f, 14g, 14i: accept reviewer-approved tier, or request live runs."
- Same spec line 284 (L2-e): "Optional: five group-14 slices without a live run (accept the tier or request)."
- Same spec section 3.1, row "Groups 13/14 (earlier)": "969/970/971 and 14b/c/d/e live-verified; **14a, 14a-ext, 14f, 14g, 14i have no individual live run** (scope doc 6 table; Ish to accept the tier or request runs)"; residual R17 names "the five group-14 slices".
- Confirmed against `docs/wp2_1_group14_scope.md` "Execution status 4": "live verification still missing for 14a, 14a-ext, 14f, 14g, 14i (only 14b, 14c, 14d, 14e have live runs)".

Not to be conflated: `docs/wp2_1_g15b_consolidated.md` 10f uses a five-LEVEL tier vocabulary (code complete < reviewer APPROVED < independently re-probed < live-STYLE < live-verified). That is a different thing; the spec's own 3.0 vocabulary has four levels. This document uses the group-14 SLICE meaning of "five" and states each slice's tier in rule-7 terms.

## Per-slice evidence (from `docs/wp2_1_group14_scope.md` execution-status tables; commits verified present in `git log`)

| slice | scope | commit | code-complete | reviewer | live | notes / honest limits |
|---|---|---|---|---|---|---|
| 14a (NEW-951 partial) | recursive protected-root classification inside the four existing roots | `249b61b` | yes | APPROVED | NO individual live run | no nested `.py` existed so nothing reclassified; residuals NEW-975/986 |
| 14a-ext (NEW-975) | `CORE_CLASSIFICATION_ROOTS` = core, tools, utils, prompts, ccos/plugins, bench; 89 existing files ACT->HIGH (53 plugins, 36 bench) | `96ad7f4` | yes | APPROVED | NO | 66 passed new/changed, 156 related (reviewer run); backup scope (`CORE_PATTERNS`) unchanged on purpose; later broadened by G15e protected-path set |
| 14f (NEW-976/980/981) | generated-artifact boundaries: recombiner staging outside discovery roots + approving GateDecision + HIGH confirm; `execute_compound_skill` always refused; optimizer containment + confirm-gated deploy (dormant) | `96ad7f4` | yes | APPROVED | NO | 16 new tests; `ccos/tests` 177 passed (+ pre-existing `test_plugin_manager` failure identical at HEAD); deploy branch unreachable in production by design; NEW-1096/NEW-1099 (dormant optimizer defects, PROVISIONAL: they exist only in uncommitted, unreviewed NEW_ISSUES text) logged later, OPEN/QUEUE |
| 14g (NEW-982 + NEW-939) | `/init` infer+write in one HIGH gate with real confirm; `write_codeymd` via `Filesystem.write`; `/ignore` via `gate_append` ACT | `96ad7f4` | yes | APPROVED | NO | 21 new tests; 2346 passed across 60 related files; behavior change: `/init`/`--init` refuse under `--yolo`/daemon/non-tty (NEW-991) |
| 14i (NEW-939 low-severity writers + fork 6) | `core/bookkeeping_persist.py`, coalesced session/queue/voice-config saves, `gate_exec(..., coalesce_key=None)` | `3981457` | yes | APPROVED after 3 rounds (round 1 CHANGES REQUESTED) | NO | 154 passed in the final gateway-group run; wider chunks 362, 150, 180, 90; finetune plugin NOT enveloped (NEW-992); repeat saves not individually audited; real REPL session-ledger flow untested (NEW-993) |

Context (not part of the five): 14b, 14c, 14e and 14d have live runs with stated limits (`docs/wp2_1_group14_b_c_e_live_verification.md`, `docs/wp2_1_group14d_live_verification.md`); 14d on disposable stubs.

Later evidence that touches these slices indirectly (not individual live runs of them): G15e rebuilt much of the protected-path classification on top of 14a-ext (`c842d97`, code-complete + reviewer-approved, not live); V-A replay at frozen `770dc66` recorded product refusals for the shell/protected-path rows; none of these exercises 14f's recombiner/optimizer staging or 14g's `/init` gate or 14i's coalescing.

## Draft statement for the closing packet

"Group-14 slices 14a (`249b61b`), 14a-ext, 14f, 14g (`96ad7f4`) and 14i (`3981457`) are recorded at **code-complete + code-reviewer-APPROVED + committed, with no individual live run**. They are carried as R17 (tier honesty) unless Ish requests live runs, which would be agent-runnable under the NEW-971 pty/disposable pattern (no model load). Their known residuals are NEW-975, NEW-986, NEW-990, NEW-991, NEW-992, NEW-993, and provisionally (uncommitted ledger text) NEW-1096 and NEW-1099."

Decision owner: Ish (Z-8). Not signed; nothing in this file upgrades any slice.
