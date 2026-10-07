"""Paired champion/challenger comparison over ledger rows."""
import json
from pathlib import Path

from .stats import bootstrap_ci, mcnemar_exact, paired_counts


def load(ledger: Path, label: str):
    rows = [json.loads(l) for l in Path(ledger).read_text().splitlines() if l.strip()]
    return [r for r in rows if r["label"] == label]


def _by_key(rows):
    return {(r["task"], r["rep"]): r.get("passed") for r in rows}


def compare(base_rows, cand_rows) -> dict:
    hashes = {r["suite_hash"] for r in base_rows} | {r["suite_hash"] for r in cand_rows}
    if len(hashes) != 1:
        raise ValueError("base and candidate ran on different suite versions")
    a, b = _by_key(base_rows), _by_key(cand_rows)
    keys = sorted(set(a) & set(b))
    if not keys:
        raise ValueError("no overlapping tasks")
    # a grading-harness error (passed is None) is excluded from the comparison
    # itself but must stay visible via "errored" -- never silently dropped.
    errored = sum(1 for k in keys if a[k] is None or b[k] is None)
    keys = [k for k in keys if a[k] is not None and b[k] is not None]
    if not keys:
        raise ValueError("no overlapping tasks without a grading-harness error")
    x, y = [a[k] for k in keys], [b[k] for k in keys]
    bw, cw = paired_counts(x, y)
    lo, hi = bootstrap_ci(x, y)
    n = len(keys)
    return {"n": n, "base_rate": sum(x) / n, "cand_rate": sum(y) / n,
            "base_only": bw, "cand_only": cw,
            "p_value": mcnemar_exact(bw, cw), "ci95": (lo, hi),
            "errored": errored}
