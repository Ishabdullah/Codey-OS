"""
Capability Registry — The AI's inventory of what it can do.

The AI does NOT assume abilities exist. It queries this registry
before attempting any task. Each capability tracks its
implementation, dependencies, test function, and current status.

This is the core innovation — the AI's self-knowledge system.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class CapabilityStatus(str, Enum):
    ACTIVE = "active"
    EXPERIMENTAL = "experimental"
    BROKEN = "broken"
    DISABLED = "disabled"


@dataclass
class Capability:
    """A single registered capability."""
    name: str
    description: str
    implementation: str  # path to plugin or module
    category: str = "general"
    dependencies: List[str] = field(default_factory=list)
    hardware_requirements: List[str] = field(default_factory=list)
    test_path: str = ""
    status: CapabilityStatus = CapabilityStatus.ACTIVE
    version: str = "1.0.0"
    registered_at: float = field(default_factory=time.time)
    last_used: float = 0
    use_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration_ms: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total

    def record_use(self, success: bool, duration_ms: float = 0):
        """Record a usage event for performance tracking."""
        self.last_used = time.time()
        self.use_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        # Running average
        if self.use_count == 1:
            self.avg_duration_ms = duration_ms
        else:
            self.avg_duration_ms = (
                self.avg_duration_ms * (self.use_count - 1) + duration_ms
            ) / self.use_count

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class CapabilityRegistry:
    """
    Central registry of all capabilities the AI can use.

    - Register new capabilities (from plugins or core)
    - Query by name, category, or hardware requirements
    - Track performance metrics per capability
    - Persist registry to disk
    """

    def __init__(self, store_path: str = None):
        self._capabilities: Dict[str, Capability] = {}
        self._store_path = store_path or str(
            Path(__file__).parent.parent / "data" / "capabilities.json"
        )
        self._load()

    def register(self, capability: Capability) -> bool:
        """Register a new capability."""
        self._capabilities[capability.name] = capability
        self._save()
        return True

    def unregister(self, name: str) -> bool:
        """Remove a capability."""
        if name in self._capabilities:
            del self._capabilities[name]
            self._save()
            return True
        return False

    def get(self, name: str) -> Optional[Capability]:
        """Get a capability by name."""
        return self._capabilities.get(name)

    def has(self, name: str) -> bool:
        """Check if a capability exists and is active."""
        cap = self._capabilities.get(name)
        return cap is not None and cap.status == CapabilityStatus.ACTIVE

    def query(
        self,
        category: str = None,
        status: CapabilityStatus = None,
        hardware_hints: List[str] = None,
    ) -> List[Capability]:
        """Query capabilities with filters."""
        results = list(self._capabilities.values())

        if category:
            results = [c for c in results if c.category == category]

        if status:
            results = [c for c in results if c.status == status]

        if hardware_hints:
            hint_set = set(hardware_hints)
            results = [
                c for c in results
                if all(h in hint_set for h in c.hardware_requirements)
            ]

        return results

    def get_active(self) -> List[Capability]:
        """Get all active capabilities."""
        return self.query(status=CapabilityStatus.ACTIVE)

    def get_by_category(self, category: str) -> List[Capability]:
        """Get capabilities by category."""
        return self.query(category=category)

    def find_for_task(self, task_description: str, hardware_hints: List[str] = None) -> List[Capability]:
        """
        Find capabilities that might match a task description.
        Uses keyword matching on name and description.
        """
        task_lower = task_description.lower()
        keywords = set(task_lower.split())

        scored = []
        for cap in self._capabilities.values():
            if cap.status not in (CapabilityStatus.ACTIVE, CapabilityStatus.EXPERIMENTAL):
                continue

            # Check hardware requirements
            if hardware_hints:
                hint_set = set(hardware_hints)
                if not all(h in hint_set for h in cap.hardware_requirements):
                    continue

            # Score by keyword overlap
            cap_text = f"{cap.name} {cap.description} {cap.category}".lower()
            cap_words = set(cap_text.split())
            overlap = len(keywords & cap_words)
            if overlap > 0:
                scored.append((overlap, cap))

        scored.sort(key=lambda x: (-x[0], -x[1].success_rate))
        return [cap for _, cap in scored]

    def record_use(self, name: str, success: bool, duration_ms: float = 0):
        """Record usage of a capability."""
        cap = self._capabilities.get(name)
        if cap:
            cap.record_use(success, duration_ms)
            self._save()

    def get_performance_report(self) -> List[Dict[str, Any]]:
        """Get performance report for all capabilities."""
        report = []
        for cap in sorted(self._capabilities.values(), key=lambda c: -c.use_count):
            report.append({
                "name": cap.name,
                "status": cap.status.value,
                "uses": cap.use_count,
                "success_rate": f"{cap.success_rate:.0%}",
                "avg_ms": f"{cap.avg_duration_ms:.0f}",
            })
        return report

    def _save(self):
        """Persist registry to disk."""
        try:
            path = Path(self._store_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                name: cap.to_dict()
                for name, cap in self._capabilities.items()
            }
            path.write_text(json.dumps(data, indent=2, default=str))
        except Exception:
            pass

    def _load(self):
        """Load registry from disk."""
        try:
            path = Path(self._store_path)
            if path.exists():
                data = json.loads(path.read_text())
                for name, cap_data in data.items():
                    cap_data["status"] = CapabilityStatus(cap_data.get("status", "active"))
                    self._capabilities[name] = Capability(**cap_data)
        except Exception:
            pass

    def list_all(self) -> List[Dict[str, Any]]:
        """List all capabilities as dicts."""
        return [cap.to_dict() for cap in self._capabilities.values()]

    def count(self) -> int:
        return len(self._capabilities)


# Singleton
_registry: Optional[CapabilityRegistry] = None


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry
