# WP1.3a — derived sample size for the promotion gate

**Ish's decision 3 (2026-10-06):** derive a defensible `n` by power
analysis before batching overnight runs. The 30-pair/~13h figure in the
old plan was a cost estimate, never a derived requirement. This is the
derivation. Per the blueprint, "if the answer is 30, that is a valid
outcome" — it is not: under every plausible scenario below, 30 pairs is
**under-powered**, not conservative. That is the real, measured-as-far-as-
it-can-be-measured answer (CLAUDE.md rule 1/5), reported as found rather
than shaded toward the number the old plan already used.

## What the gate actually tests

`bench/gate.py.decide()` runs an **exact McNemar test** over paired
`(task, rep)` results between champion and candidate (`bench/stats.py:
mcnemar_exact`), plus a percentile bootstrap CI on the paired pass-rate
gain. Promotion requires all of: `n >= min_pairs` (default 30),
candidate winning more discordant pairs than it loses, McNemar
`p < alpha` (default 0.05), and the bootstrap CI's lower bound exceeding
`min_gain` (default 0.0).

McNemar's test only has power to detect a gain from the **discordant**
pairs — the ones where champion and candidate disagree. Two quantities
nobody has measured drive the required `n`:

- `pd = p01 + p10` — the probability a pair is discordant at all (either
  model passes, the other fails).
- `delta = p01 - p10` — the true win-rate difference the gate must
  detect to promote.

**There is no empirical estimate for either.** `NEW-762` found the
result ledger empty — no bench run has ever been recorded — so this
derivation is a function of assumptions, not a single calibrated number,
and is presented as a table for that reason.

## Formula

Standard asymptotic McNemar sample size (Connor 1987; Lachin 1992), no
continuity correction:

```
n = (z_{alpha/2} * sqrt(pd) + z_power * sqrt(pd - delta^2))^2 / delta^2
```

Implemented in `bench/power_analysis.py:required_n()`. Reproducible: the
same `(pd, delta, alpha, power)` always yields the same `n`
(`tests/test_bench_power_analysis.py`).

## Scenario table (alpha=0.05, power=0.80, two-sided)

| pd (discordance rate) | delta (true gap) | psi (discordant win ratio) | n required |
|---:|---:|---:|---:|
| 0.15 | 0.08 | 3.29 | 182 |
| 0.20 | 0.10 | 3.00 | 155 |
| 0.25 | 0.15 | 4.00 | 85 |
| 0.30 | 0.15 | 3.00 | 103 |
| 0.30 | 0.20 | 5.00 | 57 |
| 0.40 | 0.20 | 3.00 | 77 |

`psi = p01/p10`: a candidate that wins 3 discordant pairs for every 1 it
loses (`psi=3`) at a 20-30% discordance rate needs **77-155** paired
runs, not 30, to reach 80% power at alpha=0.05 — several times the old
figure, in the opposite direction from what "derive a smaller n" might
suggest.

## The honest recommendation

1. **30 pairs is not defensible under any scenario in this table.**
   The lowest requirement (`n=57`) assumes a fairly large, easy-to-spot
   effect (`psi=5`, 30% of pairs discordant) — an optimistic case for an
   early-stage coding agent.
2. **A real number needs a real `pd` estimate, which needs a pilot run
   — and the pilot must not touch the frozen suite's eligibility for
   training data (`NEW-761`).** Do not enable `CODEY_TRAJECTORY=1` for
   any pilot before WP0.5 lands (per the Oct-6 directive). A pilot can
   still be run with trajectory recording off, reading
   `bench/results.jsonl` directly, since `bench/runner.py`'s labeling
   step — not the run itself — is what creates the leak.
3. **The pairing-unit caveat does not go away with a bigger `n`.** 8
   frozen tasks means `n=100` is ~12 reps/task, not 100 different
   problems; reps of the same task share correlated noise (same prompt,
   same systematic failure mode), so the independence this formula
   assumes is optimistic regardless of which row is chosen. Growing the
   frozen suite's task count, not just its rep count, is the structural
   fix — out of scope for this work package, flagged for whoever scopes
   suite expansion.
4. **Working default, pending a pilot:** treat **`n=100`** (the
   `pd=0.30, delta=0.15` row, rounded up for simulation/bootstrap margin)
   as the batching target until a pilot gives a measured `pd`. At the
   device's own measured throughput (~780-820s/task-rep, this session's
   calibration — see `PROJECT_LOG.md` 2026-10-06), **100 paired runs is
   roughly 22-24 hours of device time per champion/challenger
   comparison** — not cheaper than the old 30-pair/13h estimate, worse.
   This is the number to bring to Ish before committing device time, not
   something to round down to make the old estimate look conservative.

## Reproducing this table

```
python3 bench/power_analysis.py
```
