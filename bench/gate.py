"""Promotion gate: the only thing allowed to say "this change is an improvement".

Champion/challenger on paired results from the SAME frozen suite version.
Conservative by construction: with too little data the answer is always "no".
"""
from dataclasses import dataclass, field

from .compare import compare

DEFAULTS = {"min_pairs": 30, "alpha": 0.05, "max_regressions": 0, "min_gain": 0.0}


@dataclass(frozen=True)
class GateDecision:
    promote: bool
    reasons: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def to_dict(self):
        return {"promote": self.promote, "reasons": self.reasons, "stats": self.stats}


def decide(base_rows, cand_rows, **overrides) -> GateDecision:
    cfg = dict(DEFAULTS, **overrides)
    try:
        s = compare(base_rows, cand_rows)
    except ValueError as e:
        return GateDecision(False, [f"not comparable: {e}"])
    why = []
    if s["n"] < cfg["min_pairs"]:
        why.append(f"only {s['n']} paired results (< {cfg['min_pairs']}); cannot distinguish gain from noise")
    if s["cand_only"] <= s["base_only"]:
        why.append("candidate does not win more pairs than the champion")
    if s["p_value"] >= cfg["alpha"]:
        why.append(f"McNemar p={s['p_value']:.4f} >= {cfg['alpha']}")
    if s["ci95"][0] <= cfg["min_gain"]:
        why.append(f"bootstrap CI lower bound {s['ci95'][0]:.3f} <= {cfg['min_gain']}")
    if s["base_only"] > cfg["max_regressions"]:
        why.append(f"{s['base_only']} regressions (> {cfg['max_regressions']} allowed)")
    return GateDecision(not why, why or ["all criteria met"], s)


def no_evaluator() -> GateDecision:
    """Used where no benchmark exists for the thing being changed: never promote."""
    return GateDecision(False, ["no evaluator exists for this target; refusing to promote"])
