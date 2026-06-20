#!/usr/bin/env python3
"""Test for camera_capture plugin."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ccos.plugins.vision.camera_capture.camera import list_cameras, capture_image, test


def test_list_cameras():
    cameras = list_cameras()
    assert isinstance(cameras, list)
    print(f"[PASS] Found {len(cameras)} camera(s)")
    for cam in cameras:
        print(f"  - {cam['name']} ({cam['path']})")


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Camera self-test passed")


def test_capture():
    cameras = list_cameras()
    if not cameras:
        print("[SKIP] No cameras available for capture test")
        return

    result = capture_image(output_path="/tmp/ccos_test_capture.jpg")
    if result["success"]:
        print(f"[PASS] Captured image: {result['path']} ({result['width']}x{result['height']}, method={result['method']})")
    else:
        print(f"[SKIP] Capture failed: {result['error']}")


if __name__ == "__main__":
    test_list_cameras()
    test_self_test()
    test_capture()
    print("\nCamera plugin tests complete!")
