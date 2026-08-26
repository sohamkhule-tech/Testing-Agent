"""
Capability Registry — tool health tracking.

Tracks per-capability health metrics so the scheduler avoids unhealthy tools.
"""

from __future__ import annotations

from typing import Any

from app.logging import LoggerMixin


class CapabilityRegistry(LoggerMixin):
    """
    Tracks: name, version, healthy, busy, disabled, avg_duration, failure_rate.
    """

    def __init__(self) -> None:
        super().__init__()
        self._caps: dict[str, dict[str, Any]] = {
            "open_page":          {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 2.0,  "failure_rate": 0.0},
            "navigate":           {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 1.5,  "failure_rate": 0.0},
            "discover":           {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 8.0,  "failure_rate": 0.0},
            "capture_screenshot": {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 1.0,  "failure_rate": 0.0},
            "extract_forms":      {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 0.5,  "failure_rate": 0.0},
            "aggregate_inventory": {"version": 1, "healthy": True, "busy": False, "disabled": False, "avg_duration": 1.0,  "failure_rate": 0.0},
            "analyse_structure":  {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 0.5,  "failure_rate": 0.0},
            "design_scenarios":   {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 15.0, "failure_rate": 0.0},
            "generate_playwright": {"version": 1, "healthy": True, "busy": False, "disabled": False, "avg_duration": 60.0, "failure_rate": 0.0},
            "generate_page_objects": {"version": 1, "healthy": True, "busy": False, "disabled": False, "avg_duration": 10.0, "failure_rate": 0.0},
            "generate_tests":     {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 20.0, "failure_rate": 0.0},
            "validate_code":      {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 5.0,  "failure_rate": 0.0},
            "execute_tests":      {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 30.0, "failure_rate": 0.0},
            "collect_results":    {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 1.0,  "failure_rate": 0.0},
            "generate_report":    {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 2.0,  "failure_rate": 0.0},
            "human_review":       {"version": 1, "healthy": True,  "busy": False, "disabled": False, "avg_duration": 0.0,  "failure_rate": 0.0},
            "initialise_workspace": {"version": 1, "healthy": True, "busy": False, "disabled": False, "avg_duration": 1.0,  "failure_rate": 0.0},
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, capability: str) -> dict[str, Any] | None:
        return self._caps.get(capability)

    def is_healthy(self, capability: str) -> bool:
        cap = self._caps.get(capability)
        if cap is None:
            return True  # unknown capabilities are assumed healthy
        return bool(cap.get("healthy")) and not bool(cap.get("disabled"))

    def is_busy(self, capability: str) -> bool:
        cap = self._caps.get(capability)
        return bool(cap.get("busy", False)) if cap else False

    def set_busy(self, capability: str, busy: bool = True) -> None:
        cap = self._caps.get(capability)
        if cap:
            cap["busy"] = busy

    def record_success(self, capability: str, duration: float = 0.0) -> None:
        cap = self._caps.get(capability)
        if cap:
            cap["healthy"] = True
            cap["busy"] = False
            if duration > 0:
                old = cap.get("avg_duration", duration)
                cap["avg_duration"] = round((old + duration) / 2, 2)

    def record_failure(self, capability: str) -> None:
        cap = self._caps.get(capability)
        if cap:
            cap["busy"] = False
            current_rate = cap.get("failure_rate", 0.0)
            cap["failure_rate"] = min(round(current_rate + 0.1, 2), 1.0)
            if cap["failure_rate"] >= 0.5:
                cap["healthy"] = False
                self.logger.warning("capability_marked_unhealthy", capability=capability, failure_rate=cap["failure_rate"])

    def disable(self, capability: str) -> None:
        cap = self._caps.get(capability)
        if cap:
            cap["disabled"] = True
            cap["healthy"] = False

    def enable(self, capability: str) -> None:
        cap = self._caps.get(capability)
        if cap:
            cap["disabled"] = False
            cap["healthy"] = True

    def all_healthy(self) -> list[str]:
        return [name for name, c in self._caps.items() if c.get("healthy") and not c.get("disabled")]

    def unhealthy(self) -> list[str]:
        return [name for name, c in self._caps.items() if not c.get("healthy") or c.get("disabled")]

    def summary(self) -> dict[str, dict[str, Any]]:
        return {name: dict(cap) for name, cap in self._caps.items()}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry_singleton: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = CapabilityRegistry()
    return _registry_singleton
