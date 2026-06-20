#!/usr/bin/env python3
"""
CCOS Main Entry Point — Codey Cognitive OS.

Bootstraps the full CCOS system:
1. Detects device (body awareness)
2. Loads capability registry
3. Discovers and loads plugins
4. Demonstrates a working prompt cycle

This is the MVP demo script. Run: python ccos_main.py
"""

import json
import os
import sys
import time
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))


def main():
    from ccos.core.device_manager import get_device_manager
    from ccos.core.capability_registry import get_capability_registry
    from ccos.core.plugin_manager import get_plugin_manager
    from ccos.core.tool_router import get_tool_router
    from ccos.core.planner import get_planner
    from ccos.core.reflection_engine import get_reflection_engine
    from ccos.core.memory.ccos_memory import get_ccos_memory

    print("=" * 60)
    print("  Codey Cognitive OS (CCOS) v0.1.0")
    print("  Self-extending AI Agent Operating System")
    print("=" * 60)
    print()

    # ── Step 1: Device Detection (Body Awareness) ──────────────────
    print("[1/6] Detecting device (body awareness)...")
    device = get_device_manager()
    print(f"  OS:       {device.get_profile()['os']['name']} ({device.get_profile()['os']['arch']})")
    print(f"  CPU:      {device.get_profile()['cpu']['model']} ({device.get_profile()['cpu']['cores']} cores)")
    print(f"  RAM:      {device.get_profile()['ram']['total_human']}")
    print(f"  Camera:   {'yes' if device.has_camera() else 'no'}")
    print(f"  Mic:      {'yes' if device.has_microphone() else 'no'}")
    print(f"  GPU:      {'yes' if device.has_gpu() else 'no'}")
    print(f"  Network:  {'connected' if device.get_profile()['network']['connected'] else 'offline'}")
    print(f"  Hardware hints: {device.get_capabilities_hints()}")
    print()

    # ── Step 2: Load Capability Registry ───────────────────────────
    print("[2/6] Loading capability registry...")
    registry = get_capability_registry()
    print(f"  Registered capabilities: {registry.count()}")
    print()

    # ── Step 3: Discover and Load Plugins ──────────────────────────
    print("[3/6] Discovering plugins...")
    plugins = get_plugin_manager()
    plugin_list = plugins.list_plugins()
    print(f"  Found {len(plugin_list)} plugin(s)")

    print("  Loading plugins...")
    results = plugins.load_all()
    for name, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"    {name}: {status}")
    print()

    # ── Step 4: Show Active Capabilities ───────────────────────────
    print("[4/6] Active capabilities:")
    active = registry.get_active()
    for cap in active:
        print(f"  [{cap.category}] {cap.name}: {cap.description}")
    print()

    # ── Step 5: Demo — System Info Plugin ──────────────────────────
    print("[5/6] Demo: System Info Plugin")
    try:
        result = plugins.call_capability("system.info")
        if isinstance(result, dict):
            print(f"  Hostname:  {result.get('hostname', '?')}")
            print(f"  Uptime:    {result.get('uptime', '?')}")
            mem = result.get("memory", {})
            print(f"  Memory:    {mem.get('used_mb', '?')}MB / {mem.get('total_mb', '?')}MB")
            load = result.get("load", {})
            print(f"  Load:      {load.get('1min', '?')} (1min)")
        else:
            print(f"  Result: {result}")
    except Exception as e:
        print(f"  [ERROR] {e}")
    print()

    # ── Step 6: Demo — Task Planning ──────────────────────────────
    print("[6/6] Demo: Task Planning")
    planner = get_planner()
    demo_requests = [
        "capture a photo from the camera",
        "read system information",
        "speak hello world",
    ]
    for req in demo_requests:
        analysis = planner.analyze_request(req)
        avail = len(analysis["available_capabilities"])
        missing = len(analysis["missing_capabilities"])
        print(f"  '{req}'")
        print(f"    Available: {avail} capability(ies), Missing: {missing}")
        if analysis["missing_capabilities"]:
            print(f"    Need to create: {', '.join(analysis['missing_capabilities'])}")
    print()

    # ── Summary ────────────────────────────────────────────────────
    print("=" * 60)
    print("  CCOS Bootstrap Complete!")
    print(f"  Plugins loaded: {sum(1 for v in results.values() if v)}/{len(results)}")
    print(f"  Capabilities:   {len(active)} active")
    print(f"  Device profile: {device.get_profile()['os']['name']} / {device.get_profile()['cpu']['cores']} cores")
    print("=" * 60)

    # ── Interactive prompt ─────────────────────────────────────────
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        handle_prompt(prompt, plugins, planner, registry)


def handle_prompt(prompt: str, plugins, planner, registry):
    """Process a user prompt through the CCOS pipeline."""
    print(f"\n> {prompt}")
    print("-" * 40)

    # Analyze request
    analysis = planner.analyze_request(prompt)
    device = get_device_manager()

    # Try to route to a capability
    from ccos.core.tool_router import get_tool_router
    router = get_tool_router()
    candidate = router.route(prompt)

    if candidate:
        print(f"  Best tool: {candidate.capability.name} (score: {candidate.score:.1f})")
        print(f"  Reason: {candidate.reason}")

        # Try to execute
        try:
            start = time.time()
            result = plugins.call_capability(candidate.capability.name)
            duration = (time.time() - start) * 1000
            print(f"  Result: {json.dumps(result, indent=2, default=str)[:500]}")
            print(f"  Duration: {duration:.0f}ms")

            # Reflect
            reflection = get_reflection_engine().reflect(
                prompt, success=True,
                capability_used=candidate.capability.name,
                duration_ms=duration,
            )
            if reflection.improvements:
                print(f"  Improvements: {reflection.improvements}")

        except Exception as e:
            print(f"  Error: {e}")
            get_reflection_engine().reflect(prompt, success=False, error=str(e))
    else:
        print("  No capability matched — would fall back to Codey V3 inference")
        missing = planner.get_missing_capabilities(prompt)
        if missing:
            print(f"  Missing capabilities: {missing}")
            print("  → Would trigger plugin creation pipeline")


def get_device_manager():
    from ccos.core.device_manager import get_device_manager
    return get_device_manager()


if __name__ == "__main__":
    main()
