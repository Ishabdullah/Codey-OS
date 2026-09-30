"""CLI: python -m bench.promote LEDGER CHAMPION_LABEL CHALLENGER_LABEL [--experiments FILE]
Appends the decision to an append-only experiments ledger and exits 0 iff promote."""
import argparse
import json
import sys
import time
from pathlib import Path

from .compare import load
from .gate import decide


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger"); ap.add_argument("champion"); ap.add_argument("challenger")
    ap.add_argument("--experiments", default=str(Path(__file__).parent / "experiments.jsonl"))
    a = ap.parse_args(argv)
    d = decide(load(a.ledger, a.champion), load(a.ledger, a.challenger))
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "champion": a.champion,
           "challenger": a.challenger, **d.to_dict()}
    with open(a.experiments, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(json.dumps(rec, indent=2, default=str))
    return 0 if d.promote else 1


if __name__ == "__main__":
    sys.exit(main())
