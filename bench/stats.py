"""Paired statistics for champion/challenger comparison. Pure stdlib."""
import math
import random
from typing import Sequence


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value. b = base-only wins, c = challenger-only wins."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def paired_counts(base: Sequence[bool], cand: Sequence[bool]):
    if len(base) != len(cand):
        raise ValueError("paired samples must have equal length")
    b = sum(1 for x, y in zip(base, cand) if x and not y)
    c = sum(1 for x, y in zip(base, cand) if y and not x)
    return b, c


def bootstrap_ci(base: Sequence[bool], cand: Sequence[bool], iters: int = 2000,
                 alpha: float = 0.05, seed: int = 0):
    """Percentile bootstrap CI for the paired pass-rate difference (cand - base)."""
    n = len(base)
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    diffs = []
    for _ in range(iters):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(int(cand[i]) - int(base[i]) for i in idx) / n)
    diffs.sort()
    lo = diffs[int((alpha / 2) * iters)]
    hi = diffs[min(iters - 1, int((1 - alpha / 2) * iters))]
    return (lo, hi)
