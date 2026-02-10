"""
Metrics — lightweight counters, gauges, and histograms.

No external dependencies. Designed for in-process use with
optional JSON export. Not a replacement for Prometheus —
just enough for CLI health checks and audit enrichment.
"""

from __future__ import annotations

import builtins
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Counter:
    """Monotonically increasing counter."""

    name: str
    value: int = 0
    labels: dict[str, str] = field(default_factory=dict)

    def inc(self, n: int = 1) -> None:
        self.value += n

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type": "counter", "value": self.value, "labels": self.labels}


@dataclass
class Gauge:
    """Value that can go up and down."""

    name: str
    value: float = 0.0
    labels: dict[str, str] = field(default_factory=dict)

    def set(self, v: float) -> None:
        self.value = v

    def inc(self, n: float = 1.0) -> None:
        self.value += n

    def dec(self, n: float = 1.0) -> None:
        self.value -= n

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type": "gauge", "value": self.value, "labels": self.labels}


@dataclass
class Histogram:
    """Simple histogram tracking min, max, sum, count."""

    name: str
    _values: list[float] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)

    def observe(self, value: float) -> None:
        self._values.append(value)

    @property
    def count(self) -> int:
        return len(self._values)

    @property
    def total(self) -> float:
        return sum(self._values)

    @property
    def mean(self) -> float:
        if not self._values:
            return 0.0
        return self.total / self.count

    @property
    def min(self) -> float:
        return builtins.min(self._values) if self._values else 0.0

    @property
    def max(self) -> float:
        return builtins.max(self._values) if self._values else 0.0

    @property
    def p95(self) -> float:
        if not self._values:
            return 0.0
        sorted_vals = sorted(self._values)
        idx = int(len(sorted_vals) * 0.95)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": "histogram",
            "count": self.count,
            "total": self.total,
            "mean": round(self.mean, 2),
            "min": self.min,
            "max": self.max,
            "p95": self.p95,
            "labels": self.labels,
        }



class MetricsRegistry:
    """Central registry for all metrics."""

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}

    def counter(self, name: str, **labels: str) -> Counter:
        """Get or create a counter."""
        key = f"{name}:{labels}" if labels else name
        if key not in self._counters:
            self._counters[key] = Counter(name=name, labels=labels)
        return self._counters[key]

    def gauge(self, name: str, **labels: str) -> Gauge:
        """Get or create a gauge."""
        key = f"{name}:{labels}" if labels else name
        if key not in self._gauges:
            self._gauges[key] = Gauge(name=name, labels=labels)
        return self._gauges[key]

    def histogram(self, name: str, **labels: str) -> Histogram:
        """Get or create a histogram."""
        key = f"{name}:{labels}" if labels else name
        if key not in self._histograms:
            self._histograms[key] = Histogram(name=name, labels=labels)
        return self._histograms[key]

    def timer(self, name: str, **labels: str) -> TimerContext:
        """Create a timer context that records duration to a histogram."""
        return TimerContext(self.histogram(name, **labels))

    def to_dict(self) -> dict[str, list[dict]]:
        return {
            "counters": [c.to_dict() for c in self._counters.values()],
            "gauges": [g.to_dict() for g in self._gauges.values()],
            "histograms": [h.to_dict() for h in self._histograms.values()],
        }

    def reset(self) -> None:
        """Clear all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()


class TimerContext:
    """Context manager for timing operations."""

    def __init__(self, histogram: Histogram):
        self._histogram = histogram
        self._start: float = 0.0

    def __enter__(self) -> TimerContext:
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000
        self._histogram.observe(elapsed_ms)
