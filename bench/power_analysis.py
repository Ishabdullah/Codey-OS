"""WP1.3a: required sample size for bench/gate.py's promotion decision.

The gate (bench/gate.py) decides on an exact McNemar test over discordant
task-rep pairs (base-only wins `b` vs candidate-only wins `c`), plus a
bootstrap CI on the paired pass-rate gain. This module answers the
question Ish raised as decision 3: the 30-pair figure in the old plan was
never a derived requirement, it was a cost estimate. This derives the
actual `n` the McNemar test needs to reach a stated power, as a function
of two inputs nobody has measured yet (NEW-762: the result ledger is
empty, so there is no empirical discordance rate):

- pd    = p01 + p10, the probability a given pair is discordant at all
          (one of base/candidate passes, the other fails)
- delta = p01 - p10, the true difference in win rates the gate must
          detect to promote

Formula (Connor, 1987 / Lachin, 1992 -- standard asymptotic McNemar
sample size, no continuity correction):

    n = (z_{alpha/2} * sqrt(pd) + z_power * sqrt(pd - delta**2))**2 / delta**2

Caveat that does not go away with a bigger n: the gate's pairing unit is
(task, rep), not independent problem instances. With 8 frozen tasks, n=30
is ~4 reps per task, not 30 different problems -- reps of the same task
share correlated noise (same prompt, same systematic failure mode), which
means the independence assumption behind this formula is optimistic. More
frozen tasks, not just more reps, is the real fix for that; this module
only derives n under the formula's stated assumptions.
"""
from __future__ import annotations

import math

Z_ALPHA = {0.05: 1.959964, 0.01: 2.575829}  # two-sided
Z_POWER = {0.80: 0.841621, 0.90: 1.281552, 0.95: 1.644854}


def required_n(pd: float, delta: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """Pairs needed to detect `delta` at the stated discordance rate `pd`."""
    if not (0 < pd <= 1):
        raise ValueError("pd must be in (0, 1]")
    if not (0 < abs(delta) < pd):
        raise ValueError("abs(delta) must be in (0, pd)")
    za = Z_ALPHA[alpha]
    zb = Z_POWER[power]
    n = (za * math.sqrt(pd) + zb * math.sqrt(pd - delta ** 2)) ** 2 / delta ** 2
    return math.ceil(n)


# Scenarios spanning plausible discordance/effect combinations -- there is
# no empirical estimate to anchor on (NEW-762), so this is a table, not a
# single number. Each row's psi (odds ratio of discordant wins) column
# frames delta in a more interpretable way: psi=3 means the candidate
# wins 3 discordant pairs for every 1 it loses.
SCENARIOS = [
    (0.15, 0.08),
    (0.20, 0.10),
    (0.25, 0.15),
    (0.30, 0.15),
    (0.30, 0.20),
    (0.40, 0.20),
]


def scenario_table(alpha: float = 0.05, power: float = 0.80):
    rows = []
    for pd, delta in SCENARIOS:
        p01 = (pd + delta) / 2
        p10 = (pd - delta) / 2
        psi = p01 / p10
        rows.append({
            "pd": pd, "delta": delta, "psi": psi,
            "n": required_n(pd, delta, alpha, power),
        })
    return rows


if __name__ == "__main__":
    print(f"{'pd':>5} {'delta':>6} {'psi':>6} {'n_required':>11}")
    for row in scenario_table():
        print(f"{row['pd']:>5.2f} {row['delta']:>6.2f} {row['psi']:>6.2f} {row['n']:>11d}")
