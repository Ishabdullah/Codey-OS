"""
System Info Plugin — Reads detailed system information.
"""

import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List


def get_system_info() -> Dict[str, Any]:
    """Get comprehensive system information."""
    info = {
        "hostname": platform.node(),
        "os": platform.system(),
        "os_release": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "uptime": _get_uptime(),
        "cpu": _get_cpu_info(),
        "memory": _get_memory_info(),
        "disk": _get_disk_info(),
        "load": _get_load(),
        "timestamp": time.time(),
    }
    return info


def list_processes(limit: int = 20) -> List[Dict[str, Any]]:
    """List running processes."""
    processes = []
    try:
        result = subprocess.run(
            ["ps", "aux", "--sort=-pcpu"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines()[1:limit + 1]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append({
                    "user": parts[0],
                    "pid": parts[1],
                    "cpu": parts[2],
                    "mem": parts[3],
                    "command": parts[10][:100],
                })
    except Exception:
        pass
    return processes


def _get_uptime() -> str:
    try:
        result = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        try:
            uptime_secs = float(Path("/proc/uptime").read_text().split()[0])
            hours = int(uptime_secs // 3600)
            minutes = int((uptime_secs % 3600) // 60)
            return f"{hours}h {minutes}m"
        except Exception:
            return "unknown"


def _get_cpu_info() -> Dict[str, Any]:
    info = {"cores": os.cpu_count(), "model": "unknown", "freq_mhz": 0}
    try:
        content = Path("/proc/cpuinfo").read_text()
        for line in content.splitlines():
            if line.startswith("model name") or line.startswith("Hardware"):
                info["model"] = line.split(":", 1)[1].strip()
                break
    except Exception:
        pass
    try:
        freq = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq").read_text().strip()
        info["freq_mhz"] = int(freq) // 1000
    except Exception:
        pass
    return info


def _get_memory_info() -> Dict[str, Any]:
    info = {"total_mb": 0, "available_mb": 0, "used_mb": 0}
    try:
        content = Path("/proc/meminfo").read_text()
        for line in content.splitlines():
            if line.startswith("MemTotal"):
                info["total_mb"] = int(line.split()[1]) // 1024
            elif line.startswith("MemAvailable"):
                info["available_mb"] = int(line.split()[1]) // 1024
        info["used_mb"] = info["total_mb"] - info["available_mb"]
    except Exception:
        pass
    return info


def _get_disk_info() -> List[Dict[str, Any]]:
    disks = []
    try:
        result = subprocess.run(["df", "-h"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6 and not any(x in parts[0] for x in ["tmpfs", "devtmpfs"]):
                disks.append({
                    "device": parts[0],
                    "total": parts[1],
                    "used": parts[2],
                    "available": parts[3],
                    "mount": parts[5],
                })
    except Exception:
        pass
    return disks


def _get_load() -> Dict[str, float]:
    try:
        load = os.getloadavg()
        return {"1min": load[0], "5min": load[1], "15min": load[2]}
    except Exception:
        return {"1min": 0, "5min": 0, "15min": 0}


def install():
    """Plugin install hook — no dependencies needed."""
    return True


def uninstall():
    """Plugin uninstall hook."""
    return True


def test():
    """Plugin test — verify system info works."""
    info = get_system_info()
    assert isinstance(info, dict), "Expected dict"
    assert "hostname" in info, "Missing hostname"
    assert "cpu" in info, "Missing cpu"
    assert "memory" in info, "Missing memory"
    assert info["cpu"]["cores"] > 0, "CPU cores should be > 0"
    return True
