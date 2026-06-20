"""
Camera Capture Plugin — Capture images from device cameras.

Uses OpenCV if available, falls back to ffmpeg.
Gracefully reports unavailable if no camera hardware detected.
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def list_cameras() -> List[Dict[str, Any]]:
    """List available camera devices."""
    cameras = []

    # Linux video devices
    try:
        for dev in sorted(Path("/dev").glob("video*")):
            camera = {"path": str(dev), "name": dev.name, "available": True}
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


def capture_image(
    output_path: str = None,
    camera_index: int = 0,
    width: int = 640,
    height: int = 480,
) -> Dict[str, Any]:
    """
    Capture an image from the camera.

    Returns dict with:
    - success: bool
    - path: path to saved image (if successful)
    - error: error message (if failed)
    - method: "opencv" or "ffmpeg"
    """
    if output_path is None:
        output_path = f"/tmp/ccos_capture_{int(time.time())}.jpg"

    # Check camera exists
    cameras = list_cameras()
    if not cameras:
        return {"success": False, "error": "No cameras detected", "path": None, "method": None}

    # Try OpenCV first
    try:
        import cv2
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            return {"success": False, "error": f"Cannot open camera {camera_index}", "path": None, "method": None}

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        # Warm up camera
        for _ in range(5):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            cv2.imwrite(output_path, frame)
            return {
                "success": True,
                "path": output_path,
                "width": frame.shape[1],
                "height": frame.shape[0],
                "method": "opencv",
                "error": None,
            }
        else:
            return {"success": False, "error": "Failed to capture frame", "path": None, "method": "opencv"}

    except ImportError:
        pass  # Fall through to ffmpeg

    # Fallback: ffmpeg
    try:
        device = cameras[0]["path"] if cameras else "/dev/video0"
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "v4l2",
                "-video_size", f"{width}x{height}",
                "-i", device,
                "-frames:v", "1",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and Path(output_path).exists():
            return {
                "success": True,
                "path": output_path,
                "width": width,
                "height": height,
                "method": "ffmpeg",
                "error": None,
            }
        else:
            return {"success": False, "error": result.stderr[:200], "path": None, "method": "ffmpeg"}

    except FileNotFoundError:
        return {"success": False, "error": "Neither OpenCV nor ffmpeg available", "path": None, "method": None}
    except Exception as e:
        return {"success": False, "error": str(e), "path": None, "method": "ffmpeg"}


def install():
    """Check if camera is available."""
    return len(list_cameras()) > 0


def uninstall():
    return True


def test():
    """Test camera detection (not actual capture)."""
    cameras = list_cameras()
    return isinstance(cameras, list)
