import pytest
from pathlib import Path

from app.execution.metrics_generator import MetricsGenerator
from app.schemas.execution import ExecutionMetrics


@pytest.mark.unit
class TestMetricsGenerator:
    def test_generate_metrics_empty(self):
        gen = MetricsGenerator()
        metrics = gen.generate_metrics([], 0)

        assert metrics.total_tests == 0
        assert metrics.tests_passed == 0
        assert metrics.tests_failed == 0
        assert metrics.pass_rate == 0.0

    def test_generate_metrics_all_passed(self):
        gen = MetricsGenerator()
        results = [
            {"title": "T1", "status": "passed", "duration_ms": 100},
            {"title": "T2", "status": "passed", "duration_ms": 200},
        ]

        metrics = gen.generate_metrics(results, 30.0)

        assert metrics.total_tests == 2
        assert metrics.tests_passed == 2
        assert metrics.tests_failed == 0
        assert metrics.pass_rate == 100.0
        assert metrics.total_duration_seconds == 30.0

    def test_generate_metrics_mixed(self):
        gen = MetricsGenerator()
        results = [
            {"title": "T1", "status": "passed", "duration_ms": 100},
            {"title": "T2", "status": "failed", "duration_ms": 200},
            {"title": "T3", "status": "passed", "duration_ms": 150},
            {"title": "T4", "status": "skipped", "duration_ms": 0},
        ]

        metrics = gen.generate_metrics(results, 60.0)

        assert metrics.total_tests == 4
        assert metrics.tests_passed == 2
        assert metrics.tests_failed == 1
        assert metrics.tests_skipped == 1
        assert metrics.pass_rate == 50.0
        assert metrics.fail_rate == 25.0

    def test_generate_metrics_flaky(self):
        gen = MetricsGenerator()
        results = [
            {"title": "T1", "status": "passed", "duration_ms": 100},
            {"title": "T2", "status": "passed", "duration_ms": 200, "is_flaky": True},
        ]

        metrics = gen.generate_metrics(results, 10.0)

        assert metrics.tests_flaky == 1

    def test_generate_metrics_slowest_tests(self):
        gen = MetricsGenerator()
        results = [
            {"title": "Fast", "status": "passed", "duration_ms": 100},
            {"title": "Medium", "status": "passed", "duration_ms": 500},
            {"title": "Slow", "status": "passed", "duration_ms": 1000},
        ]

        metrics = gen.generate_metrics(results, 20.0)

        assert len(metrics.slowest_tests) == 3
        assert metrics.slowest_tests[0]["title"] == "Slow"

    def test_calculate_failure_distribution(self):
        gen = MetricsGenerator()
        results = [
            {"title": "T1", "status": "failed", "failure_analysis": {"failure_type": "timeout"}},
            {"title": "T2", "status": "failed", "failure_analysis": {"failure_type": "timeout"}},
            {"title": "T3", "status": "failed", "failure_analysis": {"failure_type": "assertion_failed"}},
        ]

        dist = gen.calculate_failure_distribution(results)
        assert dist["timeout"] == 2
        assert dist["assertion_failed"] == 1

    def test_calculate_test_health_excellent(self):
        gen = MetricsGenerator()
        results = [
            {"title": "T1", "status": "passed"},
            {"title": "T2", "status": "passed"},
            {"title": "T3", "status": "passed"},
        ]

        health = gen.calculate_test_health(results)
        assert health["status"] == "excellent"
        assert health["health_score"] == 100.0

    def test_calculate_test_health_poor(self):
        gen = MetricsGenerator()
        results = [
            {"title": "T1", "status": "failed"},
            {"title": "T2", "status": "failed"},
            {"title": "T3", "status": "passed"},
        ]

        health = gen.calculate_test_health(results)
        assert health["status"] == "poor"
        assert health["health_score"] < 50

    def test_generate_metrics_file(self, temp_dir: Path):
        gen = MetricsGenerator()
        metrics = ExecutionMetrics(
            total_tests=5,
            tests_passed=4,
            tests_failed=1,
            pass_rate=80.0,
            total_duration_seconds=30.0,
        )

        path = gen.generate_metrics_file(metrics, temp_dir)
        assert path.exists()
        assert path.name == "execution-metrics.json"
