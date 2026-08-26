"""
ADB-based confound monitor for live-verify sessions.

Not an agent-callable tool (not registered anywhere in core/agent.py's tool
registry) — this is a standalone diagnostic script for a human or a
live-verifier session to run ALONGSIDE a live model-load test, to record
whether the device's screen/wakefulness state or foreground app changed
during the test window.

Origin: NEW-195 (2026-08-26) found that a real codey-start live-verify
session's observed inference hang/thrashing could not be attributed to
Codey-OS with confidence, because the phone was concurrently in active use
(a phone call, other apps, screen standby) for the entire window and this
was not recorded or controlled for at the time. This script exists so a
future live-verify round can positively confirm a clean, uncontended
window (or positively catch a confound if one occurs) instead of relying on
the operator's memory after the fact.

Requires: `adb` (Termux package `android-tools`, already listed in
install.sh) with a device already authorized and visible to `adb devices`.
Uses `adb shell dumpsys power` (wakefulness) and
`adb shell dumpsys activity activities` (foreground activity) — both
read-only, no device state is modified.

Usage:
    python3 tools/adb_confound_monitor.py [--interval SECONDS] [--out PATH]

Runs until Ctrl-C. Appends one JSON line per poll to the output log
(default: a timestamped file under .live_verify_scratch/), each with:
    {"ts": <unix epoch float>, "wakefulness": "Awake"|"Asleep"|...,
     "foreground_activity": "<package>/<activity>" or null,
     "error": "<message>"}   # present only if a poll failed

A wakefulness or foreground_activity CHANGE between consecutive polls is
also printed to stdout immediately, so a live-verifier session watching
this script's own output can see a confound as it happens, not just after
the fact in the log file.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / ".live_verify_scratch"

_WAKEFULNESS_RE = re.compile(r"mWakefulness=(\w+)")
_TOP_ACTIVITY_RE = re.compile(
    r"(?:topResumedActivity|mResumedActivity)=ActivityRecord\{[^ ]+ \S+ (\S+) "
)


def _run_adb(args: list[str], timeout: float = 5.0) -> str:
    result = subprocess.run(
        ["adb"] + args, capture_output=True, text=True, timeout=timeout
    )
    return result.stdout


def poll_once() -> dict:
    reading: dict = {"ts": time.time()}
    try:
        power_out = _run_adb(["shell", "dumpsys", "power"])
        match = _WAKEFULNESS_RE.search(power_out)
        reading["wakefulness"] = match.group(1) if match else None
    except Exception as e:
        reading["wakefulness"] = None
        reading["error"] = f"power poll failed: {e}"

    try:
        activity_out = _run_adb(["shell", "dumpsys", "activity", "activities"])
        match = _TOP_ACTIVITY_RE.search(activity_out)
        reading["foreground_activity"] = match.group(1) if match else None
    except Exception as e:
        reading["foreground_activity"] = None
        existing = reading.get("error", "")
        reading["error"] = (existing + "; " if existing else "") + f"activity poll failed: {e}"

    return reading


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--interval", type=float, default=3.0, help="Seconds between polls (default: 3.0)"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output log path (default: .live_verify_scratch/adb_confound_<timestamp>.jsonl)",
    )
    args = parser.parse_args()

    out_path = args.out
    if out_path is None:
        DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEFAULT_OUT_DIR / f"adb_confound_{int(time.time())}.jsonl"

    try:
        devices_out = _run_adb(["devices"])
    except FileNotFoundError:
        print("ERROR: 'adb' not found on PATH. Install with: pkg install android-tools", file=sys.stderr)
        return 1
    except subprocess.SubprocessError as e:
        print(f"ERROR: 'adb devices' failed or timed out: {e}", file=sys.stderr)
        return 1
    if "device\n" not in devices_out and "\tdevice" not in devices_out:
        print(f"ERROR: no authorized adb device found. `adb devices` output:\n{devices_out}", file=sys.stderr)
        return 1

    print(f"Logging to {out_path} every {args.interval}s. Ctrl-C to stop.")
    last_wakefulness = None
    last_activity = None

    with out_path.open("a") as f:
        try:
            while True:
                reading = poll_once()
                f.write(json.dumps(reading) + "\n")
                f.flush()

                wakefulness = reading.get("wakefulness")
                activity = reading.get("foreground_activity")
                if wakefulness != last_wakefulness:
                    print(f"[{reading['ts']:.1f}] wakefulness: {last_wakefulness} -> {wakefulness}")
                    last_wakefulness = wakefulness
                if activity != last_activity:
                    print(f"[{reading['ts']:.1f}] foreground_activity: {last_activity} -> {activity}")
                    last_activity = activity
                if "error" in reading:
                    print(f"[{reading['ts']:.1f}] poll error: {reading['error']}", file=sys.stderr)

                time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\nStopped. Log written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
