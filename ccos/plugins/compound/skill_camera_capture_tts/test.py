#!/usr/bin/env python3
"""Test for compound skill: skill.camera_capture_tts"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def test_skill_import():
    """Verify the skill module imports cleanly."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("skill", str(Path(__file__).parent / "pipeline.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "run"), "Missing run() function"
    assert hasattr(mod, "test"), "Missing test() function"
    print("[PASS] Skill module imports correctly")


def test_skill_self_test():
    """Run the skill's built-in self-test."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("skill", str(Path(__file__).parent / "pipeline.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    passed, msg = mod.test()
    assert passed, f"Self-test failed: {msg}"
    print(f"[PASS] Self-test: {msg}")


def test_skill_execution():
    """Execute the skill and verify output structure."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("skill", str(Path(__file__).parent / "pipeline.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.run("test input")
    assert isinstance(result, dict), "Expected dict result"
    assert "success" in result, "Missing success field"
    assert "steps_completed" in result, "Missing steps_completed"
    print(f"[PASS] Execution: {result['steps_completed']} steps, success={result['success']}")


if __name__ == "__main__":
    test_skill_import()
    test_skill_self_test()
    test_skill_execution()
    print("\nAll compound skill tests passed!")