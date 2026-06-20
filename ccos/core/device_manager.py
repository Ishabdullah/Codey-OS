"""
Device Manager — Body Awareness Module.

Detects and continuously monitors the hardware environment:
OS, CPU, RAM, GPU, storage, cameras, microphones, speakers,
network, and connected USB/Bluetooth devices.

The device profile is the AI's "body model" — it adapts
tool selection and capability availability based on detected hardware.
"""

import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def _run_cmd(cmd: List[str], timeout: int = 5) -> str:
    """Run a command safely and return stdout."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _detect_os() -> Dict[str, str]:
    """Detect operating system details."""
    info = {
        "name": "unknown",
        "platform": platform.system(),
        "arch": platform.machine(),
        "release": platform.release(),
        "is_termux": False,
        "is_android": False,
        "is_ubuntu": False,
    }

    # Check Termux
    if os.environ.get("TERMUX_VERSION") or Path("/data/data/com.termux").exists():
        info["name"] = "termux"
        info["is_termux"] = True
        info["is_android"] = True
        return info

    # Check Android
    if Path("/system/build.prop").exists():
        info["name"] = "android"
        info["is_android"] = True
        return info

    # Check Ubuntu
    try:
        os_release = Path("/etc/os-release")
        if os_release.exists():
            content = os_release.read_text()
            if "ubuntu" in content.lower():
                info["name"] = "ubuntu"
                info["is_ubuntu"] = True
            elif "debian" in content.lower():
                info["name"] = "debian"
            else:
                for line in content.splitlines():
                    if line.startswith("ID="):
                        info["name"] = line.split("=", 1)[1].strip('"').lower()
    except Exception:
        pass

    if info["name"] == "unknown":
        info["name"] = platform.system().lower()

    return info


def _detect_cpu() -> Dict[str, Any]:
    """Detect CPU information."""
    cpu_info = {
        "model": "unknown",
        "cores": os.cpu_count() or 1,
        "arch": platform.machine(),
    }

    try:
        if Path("/proc/cpuinfo").exists():
            content = Path("/proc/cpuinfo").read_text()
            for line in content.splitlines():
                if line.startswith("model name") or line.startswith("Hardware"):
                    cpu_info["model"] = line.split(":", 1)[1].strip()
                    break
            # ARM devices often don't have "model name"
            if cpu_info["model"] == "unknown":
                for line in content.splitlines():
                    if line.startswith("Processor"):
                        cpu_info["model"] = line.split(":", 1)[1].strip()
                        break
    except Exception:
        pass

    # Fallback: use platform
    if cpu_info["model"] == "unknown":
        cpu_info["model"] = platform.processor() or "unknown"

    return cpu_info


def _detect_ram() -> Dict[str, Any]:
    """Detect RAM information."""
    ram = {"total_mb": 0, "available_mb": 0, "total_human": "unknown"}

    try:
        if Path("/proc/meminfo").exists():
            content = Path("/proc/meminfo").read_text()
            for line in content.splitlines():
                if line.startswith("MemTotal"):
                    kb = int(re.search(r"(\d+)", line).group(1))
                    ram["total_mb"] = kb // 1024
                    ram["total_human"] = f"{ram['total_mb'] // 1024}GB" if ram["total_mb"] >= 1024 else f"{ram['total_mb']}MB"
                elif line.startswith("MemAvailable"):
                    kb = int(re.search(r"(\d+)", line).group(1))
                    ram["available_mb"] = kb // 1024
    except Exception:
        pass

    return ram


def _detect_gpu() -> List[Dict[str, str]]:
    """Detect GPU devices."""
    gpus = []

    # Try lspci
    output = _run_cmd(["lspci"])
    if output:
        for line in output.splitlines():
            if any(k in line.lower() for k in ["vga", "3d", "display", "gpu"]):
                gpus.append({"name": line.split(":", 2)[-1].strip() if ":" in line else line, "source": "lspci"})

    # Try nvidia-smi
    nvidia = _run_cmd(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    if nvidia:
        for line in nvidia.splitlines():
            parts = line.split(",")
            gpus.append({
                "name": parts[0].strip(),
                "memory": parts[1].strip() if len(parts) > 1 else "unknown",
                "source": "nvidia-smi",
            })

    # Try /sys/class/drm
    drm_path = Path("/sys/class/drm")
    if drm_path.exists() and not gpus:
        for card in drm_path.glob("card*/device/vendor"):
            try:
                vendor = card.read_text().strip()
                gpus.append({"name": f"GPU (vendor {vendor})", "source": "sysfs"})
            except Exception:
                pass

    return gpus


def _detect_cameras() -> List[Dict[str, Any]]:
    """Detect camera devices."""
    cameras = []

    # Linux video devices
    video_path = Path("/dev")
    try:
        for dev in sorted(video_path.glob("video*")):
            camera = {"path": str(dev), "name": dev.name}
            # Try to get name from sysfs
            dev_num = dev.name.replace("video", "")
            sysfs = Path(f"/sys/class/video4linux/video{dev_num}/name")
            if sysfs.exists():
                try:
                    camera["name"] = sysfs.read_text().strip()
                except (PermissionError, OSError):
                    pass
            cameras.append(camera)
    except (PermissionError, OSError):
        pass

    return cameras


def _detect_audio() -> Dict[str, List[Dict[str, str]]]:
    """Detect audio input/output devices."""
    audio = {"microphones": [], "speakers": []}

    # Check /proc/asound
    asound_cards = Path("/proc/asound/cards")
    if asound_cards.exists():
        try:
            content = asound_cards.read_text()
            for line in content.splitlines():
                match = re.match(r"\s*(\d+)\s+\[.*?\]\s*:\s*(.*)", line)
                if match:
                    card_info = {"id": match.group(1), "name": match.group(2).strip()}
                    audio["microphones"].append(card_info)
                    audio["speakers"].append(card_info)
        except (PermissionError, OSError, Exception):
            pass

    # Try pactl (PulseAudio)
    pactl_sources = _run_cmd(["pactl", "list", "short", "sources"])
    if pactl_sources:
        for line in pactl_sources.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[1]
                if "input" in name or "monitor" not in name.lower():
                    audio["microphones"].append({"name": name, "source": "pulseaudio"})

    pactl_sinks = _run_cmd(["pactl", "list", "short", "sinks"])
    if pactl_sinks:
        for line in pactl_sinks.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                audio["speakers"].append({"name": parts[1], "source": "pulseaudio"})

    return audio


def _detect_storage() -> List[Dict[str, Any]]:
    """Detect storage devices."""
    storage = []

    try:
        output = _run_cmd(["df", "-h"])
        if output:
            for line in output.splitlines()[1:]:  # skip header
                parts = line.split()
                if len(parts) >= 6:
                    filesystem = parts[0]
                    # Skip virtual/temporary filesystems
                    if any(fs in filesystem for fs in ["tmpfs", "devtmpfs", "udev", "none"]):
                        continue
                    storage.append({
                        "device": filesystem,
                        "total": parts[1],
                        "used": parts[2],
                        "available": parts[3],
                        "mount": parts[5] if len(parts) > 5 else "/",
                    })
    except Exception:
        pass

    return storage


def _detect_network() -> Dict[str, Any]:
    """Detect network status."""
    net = {"connected": False, "interfaces": [], "ip": None}

    # Check interfaces
    net_path = Path("/sys/class/net")
    if net_path.exists():
        try:
            for iface in net_path.iterdir():
                name = iface.name
                if name == "lo":
                    continue
                try:
                    operstate = (iface / "operstate").read_text().strip()
                    net["interfaces"].append({"name": name, "state": operstate})
                    if operstate == "up":
                        net["connected"] = True
                except (PermissionError, OSError, Exception):
                    net["interfaces"].append({"name": name, "state": "unknown"})
        except (PermissionError, OSError):
            pass

    # Get IP
    ip_output = _run_cmd(["hostname", "-I"])
    if ip_output:
        net["ip"] = ip_output.split()[0]

    return net


def _detect_connected_devices() -> List[Dict[str, str]]:
    """Detect USB and Bluetooth devices."""
    devices = []

    # USB via lsusb
    lsusb = _run_cmd(["lsusb"])
    if lsusb:
        for line in lsusb.splitlines():
            devices.append({"type": "usb", "name": line.strip(), "source": "lsusb"})

    # Bluetooth
    bt_output = _run_cmd(["bluetoothctl", "devices"])
    if bt_output:
        for line in bt_output.splitlines():
            match = re.match(r"Device\s+([A-F0-9:]+)\s+(.*)", line)
            if match:
                devices.append({
                    "type": "bluetooth",
                    "mac": match.group(1),
                    "name": match.group(2),
                })

    return devices


class DeviceManager:
    """
    Monitors and manages the hardware profile — the AI's 'body'.

    Provides a structured JSON model of all detected hardware,
    and watches for changes (USB plug, device state, etc.).
    """

    def __init__(self):
        self._profile: Dict[str, Any] = {}
        self._last_scan: float = 0
        self._scan()

    def _scan(self):
        """Perform a full hardware scan."""
        import time

        try:
            self._profile = {
                "os": _detect_os(),
                "cpu": _detect_cpu(),
                "ram": _detect_ram(),
                "gpu": _detect_gpu(),
                "cameras": _detect_cameras(),
                "microphones": _detect_audio()["microphones"],
                "speakers": _detect_audio()["speakers"],
                "storage": _detect_storage(),
                "network": _detect_network(),
                "connected_devices": _detect_connected_devices(),
                "scanned_at": time.time(),
            }
        except Exception:
            # Fallback with minimal info
            self._profile = {
                "os": _detect_os(),
                "cpu": _detect_cpu(),
                "ram": _detect_ram(),
                "gpu": [],
                "cameras": [],
                "microphones": [],
                "speakers": [],
                "storage": _detect_storage(),
                "network": _detect_network(),
                "connected_devices": [],
                "scanned_at": time.time(),
            }
        self._last_scan = time.time()

    def refresh(self):
        """Re-scan hardware state."""
        self._scan()

    def get_profile(self) -> Dict[str, Any]:
        """Get the current device profile."""
        return self._profile.copy()

    def get_profile_json(self, indent: int = 2) -> str:
        """Get device profile as formatted JSON."""
        return json.dumps(self._profile, indent=indent, default=str)

    def get_summary(self) -> str:
        """Get a human-readable summary of the device."""
        p = self._profile
        os_info = p.get("os", {})
        cpu = p.get("cpu", {})
        ram = p.get("ram", {})
        cameras = p.get("cameras", [])
        mics = p.get("microphones", [])
        speakers = p.get("speakers", [])
        gpu = p.get("gpu", [])

        lines = [
            f"OS: {os_info.get('name', 'unknown')} ({os_info.get('arch', '?')})",
            f"CPU: {cpu.get('model', 'unknown')} ({cpu.get('cores', '?')} cores)",
            f"RAM: {ram.get('total_human', 'unknown')}",
        ]
        if gpu:
            lines.append(f"GPU: {gpu[0].get('name', 'detected')}")
        else:
            lines.append("GPU: none detected")
        lines.append(f"Cameras: {len(cameras)}")
        lines.append(f"Microphones: {len(mics)}")
        lines.append(f"Speakers: {len(speakers)}")
        net = p.get("network", {})
        lines.append(f"Network: {'connected' if net.get('connected') else 'offline'}")

        return "\n".join(lines)

    def has_camera(self) -> bool:
        return len(self._profile.get("cameras", [])) > 0

    def has_microphone(self) -> bool:
        return len(self._profile.get("microphones", [])) > 0

    def has_gpu(self) -> bool:
        return len(self._profile.get("gpu", [])) > 0

    def has_speakers(self) -> bool:
        return len(self._profile.get("speakers", [])) > 0

    def is_termux(self) -> bool:
        return self._profile.get("os", {}).get("is_termux", False)

    def is_android(self) -> bool:
        return self._profile.get("os", {}).get("is_android", False)

    def get_capabilities_hints(self) -> List[str]:
        """
        Return a list of hardware-derived capability hints.
        Used by the capability registry to filter available plugins.
        """
        hints = []
        if self.has_camera():
            hints.append("camera")
        if self.has_microphone():
            hints.append("microphone")
        if self.has_gpu():
            hints.append("gpu")
        if self.has_speakers():
            hints.append("audio_output")
        net = self._profile.get("network", {})
        if net.get("connected"):
            hints.append("network")
        if shutil.which("ffmpeg"):
            hints.append("ffmpeg")
        if shutil.which("python3"):
            hints.append("python3")
        return hints


# Singleton
_device_manager: Optional[DeviceManager] = None


def get_device_manager() -> DeviceManager:
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager
