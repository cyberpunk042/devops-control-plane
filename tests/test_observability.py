"""
Tests for observability — health checks + metrics.
"""

import json

from click.testing import CliRunner

from src.core.observability.health import (
    ComponentHealth,
    SystemHealth,
    check_circuit_breakers,
    check_retry_queue,
    check_system_health,
)
from src.core.observability.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
)
from src.core.reliability.circuit_breaker import (
    CircuitBreakerRegistry,
    CircuitState,
)
from src.core.reliability.retry_queue import RetryQueue
from src.main import cli

# ── Health Check Tests ───────────────────────────────────────────────


class TestComponentHealth:
    def test_defaults(self):
        c = ComponentHealth(name="test")
        assert c.status == "unknown"

    def test_to_dict(self):
        c = ComponentHealth(name="test", status="healthy", message="ok")
        d = c.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "healthy"


class TestSystemHealth:
    def test_all_healthy(self):
        h = SystemHealth()
        h.add(ComponentHealth(name="a", status="healthy"))
        h.add(ComponentHealth(name="b", status="healthy"))
        assert h.status == "healthy"

    def test_degraded_if_any_degraded(self):
        h = SystemHealth()
        h.add(ComponentHealth(name="a", status="healthy"))
        h.add(ComponentHealth(name="b", status="degraded"))
        assert h.status == "degraded"

    def test_unhealthy_if_any_unhealthy(self):
        h = SystemHealth()
        h.add(ComponentHealth(name="a", status="degraded"))
        h.add(ComponentHealth(name="b", status="unhealthy"))
        assert h.status == "unhealthy"

    def test_to_dict(self):
        h = SystemHealth()
        h.add(ComponentHealth(name="a", status="healthy"))
        d = h.to_dict()
        assert "status" in d
        assert "components" in d
        assert len(d["components"]) == 1


class TestCircuitBreakerHealth:
    def test_healthy_no_breakers(self):
        reg = CircuitBreakerRegistry()
        result = check_circuit_breakers(reg)
        assert result.status == "healthy"

    def test_healthy_all_closed(self):
        reg = CircuitBreakerRegistry()
        reg.get_or_create("shell")
        reg.get_or_create("docker")
        result = check_circuit_breakers(reg)
        assert result.status == "healthy"
        assert "2" in result.message

    def test_unhealthy_open_circuit(self):
        reg = CircuitBreakerRegistry(default_threshold=1)
        cb = reg.get_or_create("shell")
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        result = check_circuit_breakers(reg)
        assert result.status == "unhealthy"

    def test_degraded_half_open(self):
        reg = CircuitBreakerRegistry(default_threshold=1, default_timeout=0.01)
        cb = reg.get_or_create("shell")
        cb.record_failure()
        import time

        time.sleep(0.02)
        cb.allow_request()  # → HALF_OPEN
        result = check_circuit_breakers(reg)
        assert result.status == "degraded"


class TestRetryQueueHealth:
    def test_healthy_empty(self):
        q = RetryQueue(max_attempts=3, base_delay=0.001)
        result = check_retry_queue(q)
        assert result.status == "healthy"
        assert "empty" in result.message.lower()

    def test_healthy_with_pending(self):
        q = RetryQueue(max_attempts=3, base_delay=0.001)
        q.enqueue("r1", action_id="a1", adapter="shell")
        result = check_retry_queue(q)
        assert result.status == "healthy"
        assert "pending" in result.message.lower()

    def test_degraded_with_exhausted(self):
        q = RetryQueue(max_attempts=1, base_delay=0.001)
        q.enqueue("r1", action_id="a1", adapter="shell")  # exhausted immediately
        result = check_retry_queue(q)
        assert result.status == "degraded"


class TestSystemHealthAggregation:
    def test_full_check(self):
        cb_reg = CircuitBreakerRegistry()
        retry_q = RetryQueue(max_attempts=3, base_delay=0.001)
        health = check_system_health(cb_registry=cb_reg, retry_queue=retry_q)
        assert health.status == "healthy"
        assert len(health.components) == 2

    def test_check_with_none_components(self):
        health = check_system_health()
        assert health.status == "healthy"
        assert len(health.components) == 0


# ── Metrics Tests ────────────────────────────────────────────────────


class TestCounter:
    def test_increment(self):
        c = Counter(name="requests")
        c.inc()
        c.inc(5)
        assert c.value == 6

    def test_to_dict(self):
        c = Counter(name="requests")
        c.inc(10)
        d = c.to_dict()
        assert d["type"] == "counter"
        assert d["value"] == 10


class TestGauge:
    def test_set(self):
        g = Gauge(name="active_connections")
        g.set(42.0)
        assert g.value == 42.0

    def test_inc_dec(self):
        g = Gauge(name="queue_size")
        g.inc()
        g.inc(3.0)
        g.dec()
        assert g.value == 3.0

    def test_to_dict(self):
        g = Gauge(name="active")
        g.set(5.0)
        d = g.to_dict()
        assert d["type"] == "gauge"
        assert d["value"] == 5.0


class TestHistogram:
    def test_observe(self):
        h = Histogram(name="duration")
        h.observe(10.0)
        h.observe(20.0)
        h.observe(30.0)
        assert h.count == 3
        assert h.total == 60.0
        assert h.mean == 20.0

    def test_min_max(self):
        h = Histogram(name="duration")
        h.observe(5.0)
        h.observe(100.0)
        h.observe(50.0)
        assert h.min == 5.0
        assert h.max == 100.0

    def test_p95(self):
        h = Histogram(name="duration")
        for i in range(100):
            h.observe(float(i))
        # p95 should be around 95
        assert h.p95 >= 94.0

    def test_empty(self):
        h = Histogram(name="duration")
        assert h.count == 0
        assert h.mean == 0.0
        assert h.min == 0.0
        assert h.max == 0.0
        assert h.p95 == 0.0

    def test_to_dict(self):
        h = Histogram(name="duration")
        h.observe(10.0)
        d = h.to_dict()
        assert d["type"] == "histogram"
        assert d["count"] == 1


class TestMetricsRegistry:
    def test_counter_get_or_create(self):
        reg = MetricsRegistry()
        c1 = reg.counter("requests")
        c2 = reg.counter("requests")
        assert c1 is c2

    def test_gauge_get_or_create(self):
        reg = MetricsRegistry()
        g1 = reg.gauge("active")
        g2 = reg.gauge("active")
        assert g1 is g2

    def test_histogram_get_or_create(self):
        reg = MetricsRegistry()
        h1 = reg.histogram("duration")
        h2 = reg.histogram("duration")
        assert h1 is h2

    def test_labels_create_separate_metrics(self):
        reg = MetricsRegistry()
        c1 = reg.counter("requests", adapter="shell")
        c2 = reg.counter("requests", adapter="docker")
        assert c1 is not c2

    def test_timer_context(self):
        import time

        reg = MetricsRegistry()
        with reg.timer("op_duration"):
            time.sleep(0.01)  # 10ms minimum
        h = reg.histogram("op_duration")
        assert h.count == 1
        assert h.total > 0  # recorded some duration

    def test_to_dict(self):
        reg = MetricsRegistry()
        reg.counter("requests").inc()
        reg.gauge("active").set(3.0)
        reg.histogram("duration").observe(10.0)
        d = reg.to_dict()
        assert len(d["counters"]) == 1
        assert len(d["gauges"]) == 1
        assert len(d["histograms"]) == 1

    def test_reset(self):
        reg = MetricsRegistry()
        reg.counter("a")
        reg.gauge("b")
        reg.histogram("c")
        reg.reset()
        assert reg.to_dict() == {"counters": [], "gauges": [], "histograms": []}


# ── CLI Health Command Tests ─────────────────────────────────────────


class TestHealthCLI:
    def test_health_command(self, tmp_path):
        config = tmp_path / "project.yml"
        config.write_text("name: test\nmodules: []\n")
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "health"])
        assert result.exit_code == 0
        assert "Health" in result.output

    def test_health_json(self, tmp_path):
        config = tmp_path / "project.yml"
        config.write_text("name: test\nmodules: []\n")
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config), "health", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "healthy"
        assert "components" in data
