"""
Operational Metrics for Persistence Operations

Exposes counters, gauges, and latency tracking for every
persistence backend.  Designed to be consumed by structured
logs and exported to monitoring systems (Prometheus, StatsD, etc.).

Usage::

    from app.persistence.metrics import persistence_metrics

    persistence_metrics.filesystem_writes.inc()
    persistence_metrics.pg_write_latency.observe(0.042)
    persistence_metrics.dual_write_failures.inc()
    persistence_metrics.connection_failures.inc()

All metrics are thread-safe (via ``threading.Lock``) for single-process
async usage.  For multi-worker deployments, aggregate via structured
logs or a metrics backend.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


class Counter:
    """Thread-safe counter.

    Args:
        name: Metric name (for log/serialisation).
        help_: Human-readable description.
    """

    def __init__(self, name: str, help_: str = "") -> None:
        self._name = name
        self._help = help_
        self._value = 0
        self._lock = threading.Lock()

    def inc(self, amount: int = 1) -> None:
        with self._lock:
            self._value += amount

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

    def snapshot(self) -> dict[str, Any]:
        return {"name": self._name, "value": self.value, "type": "counter"}


class Gauge:
    """Thread-safe gauge (up/down value).

    Args:
        name: Metric name.
        help_: Human-readable description.
    """

    def __init__(self, name: str, help_: str = "") -> None:
        self._name = name
        self._help = help_
        self._value = 0.0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        with self._lock:
            return self._value

    def snapshot(self) -> dict[str, Any]:
        return {"name": self._name, "value": self.value, "type": "gauge"}


class LatencyTracker:
    """Tracks operation latency with min/max/avg/count.

    Args:
        name: Metric name.
        help_: Human-readable description.
    """

    def __init__(self, name: str, help_: str = "") -> None:
        self._name = name
        self._help = help_
        self._count = 0
        self._total = 0.0
        self._min = float("inf")
        self._max = 0.0
        self._lock = threading.Lock()

    def observe(self, seconds: float) -> None:
        with self._lock:
            self._count += 1
            self._total += seconds
            if seconds < self._min:
                self._min = seconds
            if seconds > self._max:
                self._max = seconds

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    @property
    def avg(self) -> float:
        with self._lock:
            return self._total / self._count if self._count else 0.0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self._name,
                "count": self._count,
                "total_seconds": round(self._total, 4),
                "avg_seconds": round(self._total / self._count, 4) if self._count else 0.0,
                "min_seconds": round(self._min, 4) if self._count else 0.0,
                "max_seconds": round(self._max, 4),
                "type": "latency",
            }

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, *args):
        self.observe(time.monotonic() - self._start)


@dataclass
class PersistenceMetrics:
    """Aggregate of all persistence metrics.

    Every metric is a public attribute.  Snapshots return all values.
    """

    filesystem_writes: Counter = field(default_factory=lambda: Counter("fs_writes"))
    filesystem_write_latency: LatencyTracker = field(
        default_factory=lambda: LatencyTracker("fs_write_latency")
    )

    pg_writes: Counter = field(default_factory=lambda: Counter("pg_writes"))
    pg_write_latency: LatencyTracker = field(
        default_factory=lambda: LatencyTracker("pg_write_latency")
    )

    dual_write_attempts: Counter = field(
        default_factory=lambda: Counter("dual_write_attempts")
    )
    dual_write_failures: Counter = field(
        default_factory=lambda: Counter("dual_write_failures")
    )

    retry_attempts: Counter = field(default_factory=lambda: Counter("retry_attempts"))
    retry_success: Counter = field(default_factory=lambda: Counter("retry_success"))
    retry_exhaustion: Counter = field(
        default_factory=lambda: Counter("retry_exhaustion")
    )

    connection_failures: Counter = field(
        default_factory=lambda: Counter("connection_failures")
    )
    consistency_failures: Counter = field(
        default_factory=lambda: Counter("consistency_failures")
    )

    pool_utilization: Gauge = field(default_factory=lambda: Gauge("pool_utilization"))
    active_connections: Gauge = field(
        default_factory=lambda: Gauge("active_connections")
    )

    pending_retries: Gauge = field(default_factory=lambda: Gauge("pending_retries"))

    def snapshot(self) -> dict[str, Any]:
        """Return all metric values as a flat dictionary.

        Suitable for health check endpoints or log emission.
        """
        result: dict[str, Any] = {}
        for field_name in self.__dataclass_fields__:
            metric = getattr(self, field_name)
            if hasattr(metric, "snapshot"):
                result[field_name] = metric.snapshot()
            else:
                result[field_name] = metric
        return result


# Module-level singleton
persistence_metrics = PersistenceMetrics()
