"""Installed launcher: three path values are data, never startup authority."""

import sys
from pathlib import Path


def main(argv=None):
    values = sys.argv[1:] if argv is None else argv
    if len(values) != 3 or any(not isinstance(value, str) or not value or "\0" in value or len(value.encode()) > 4096 for value in values):
        raise ValueError("Invalid daemon path snapshot")
    # Validate before importing daemon's established bootstrap dependencies.
    from core.daemon import main as guarded_main
    from core.daemon_config import DaemonPaths

    guarded_main(paths=DaemonPaths(*(Path(value) for value in values)))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
