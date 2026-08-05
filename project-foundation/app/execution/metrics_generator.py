import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logging import LoggerMixin
from app.schemas.execution import ExecutionMetrics


class MetricsGenerator(LoggerMixin):

    def __init__(self) -> None:
        super().__init__()

    def generate_metrics(
        self,
        test_results: list[dict[str, Any]],
        total_duration: float,
    ) -> ExecutionMetrics:
        total_tests = len(test_results)

        if total_tests == 0:
            return ExecutionMetrics(
                total_tests=0,
                tests_passed=0,
                tests_failed=0,
                tests_skipped=0,
                tests_flaky=0,
                pass_rate=0.0,
                fail_rate=0.0,
                average_duration_ms=0.0,
                total_duration_seconds=total_duration,
                slowest_tests=[],
                fastest_tests=[],
            )

        passed = sum(1 for t in test_results if t.get("status") == "passed")
        failed = sum(1 for t in test_results if t.get("status") == "failed")
        skipped = sum(1 for t in test_results if t.get("status") == "skipped")
        flaky = sum(1 for t in test_results if t.get("is_flaky", False))

        pass_rate = (passed / total_tests) * 100 if total_tests > 0 else 0.0
        fail_rate = (failed / total_tests) * 100 if total_tests > 0 else 0.0

        durations = [
            t.get("duration_ms", 0)
            for t in test_results
            if t.get("status") != "skipped"
        ]
        average_duration = sum(durations) / len(durations) if durations else 0.0
        median_duration = sorted(durations)[len(durations) // 2] if durations else 0.0

        sorted_by_duration = sorted(
            test_results,
            key=lambda t: t.get("duration_ms", 0),
            reverse=True,
        )

        slowest_tests_list = [
            {
                "title": t.get("title"),
                "duration_ms": t.get("duration_ms"),
                "file": t.get("file"),
                "status": t.get("status"),
            }
            for t in sorted_by_duration[:10]
        ]

        fast_tests = sorted(
            [t for t in test_results if t.get("status") != "skipped"],
            key=lambda t: t.get("duration_ms", 0),
        )
        fastest_tests_list = [
            {
                "title": t.get("title"),
                "duration_ms": t.get("duration_ms"),
                "file": t.get("file"),
                "status": t.get("status"),
            }
            for t in fast_tests[:10]
        ]

        failure_distribution = self.calculate_failure_distribution(test_results)
        browser_stats = self._calculate_browser_stats(test_results)
        module_stats = self._calculate_module_stats(test_results)
        health = self.calculate_test_health(test_results)

        metrics = ExecutionMetrics(
            total_tests=total_tests,
            tests_passed=passed,
            tests_failed=failed,
            tests_skipped=skipped,
            tests_flaky=flaky,
            pass_rate=round(pass_rate, 2),
            fail_rate=round(fail_rate, 2),
            average_duration_ms=round(average_duration, 2),
            total_duration_seconds=round(total_duration, 2),
            slowest_tests=slowest_tests_list,
            fastest_tests=fastest_tests_list,
            failure_distribution=failure_distribution,
            browser_stats=browser_stats,
            module_stats=module_stats,
            health_score=round(health["health_score"], 1),
            health_status=health["status"],
        )

        self.logger.info(
            "metrics_generated",
            total=total_tests,
            passed=passed,
            failed=failed,
            pass_rate=f"{pass_rate:.1f}%",
            health=metrics.health_status,
        )

        return metrics

    def calculate_failure_distribution(
        self,
        test_results: list[dict[str, Any]],
    ) -> dict[str, int]:
        distribution: dict[str, int] = {}
        for test in test_results:
            if test.get("status") == "failed":
                analysis = test.get("failure_analysis", {})
                failure_type = analysis.get("failure_type", "unknown")
                distribution[failure_type] = distribution.get(failure_type, 0) + 1
        return distribution

    def _calculate_browser_stats(
        self,
        test_results: list[dict[str, Any]],
    ) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for test in test_results:
            browser = test.get("browser", "unknown")
            if browser not in stats:
                stats[browser] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
            stats[browser]["total"] += 1
            status = test.get("status", "skipped")
            if status in stats[browser]:
                stats[browser][status] += 1
        return stats

    def _calculate_module_stats(
        self,
        test_results: list[dict[str, Any]],
    ) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for test in test_results:
            file_path = test.get("file", "unknown")
            module = file_path.split("/")[-1] if "/" in file_path else file_path
            module = module.replace(".spec.ts", "").replace(".test.ts", "")
            if module not in stats:
                stats[module] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
            stats[module]["total"] += 1
            status = test.get("status", "skipped")
            if status in stats[module]:
                stats[module][status] += 1
        return stats

    def calculate_test_health(self, test_results: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(test_results)
        if total == 0:
            return {"health_score": 0, "status": "unknown", "issues": [], "recommendations": []}

        passed = sum(1 for t in test_results if t.get("status") == "passed")
        failed = sum(1 for t in test_results if t.get("status") == "failed")
        flaky = sum(1 for t in test_results if t.get("is_flaky", False))

        health_score = (passed / total) * 100

        if flaky > 0:
            flaky_penalty = min((flaky / total) * 20, 20)
            health_score -= flaky_penalty

        health_score = max(0, min(100, health_score))

        if health_score >= 90:
            status = "excellent"
        elif health_score >= 75:
            status = "good"
        elif health_score >= 50:
            status = "fair"
        else:
            status = "poor"

        issues: list[str] = []
        if failed > 0:
            issues.append(f"{failed} test(s) failing")
        if flaky > 0:
            issues.append(f"{flaky} flaky test(s)")
        if health_score < 75:
            issues.append("Test suite health below target")

        return {
            "health_score": round(health_score, 1),
            "status": status,
            "issues": issues,
            "recommendations": self._get_health_recommendations(health_score, failed, flaky),
        }

    def _get_health_recommendations(
        self,
        health_score: float,
        failed: int,
        flaky: int,
    ) -> list[str]:
        recommendations: list[str] = []
        if failed > 0:
            recommendations.append("Fix failing tests to improve reliability")
        if flaky > 0:
            recommendations.append("Investigate and stabilize flaky tests")
        if health_score < 50:
            recommendations.append("Review test suite architecture")
            recommendations.append("Consider refactoring problematic tests")
        if not recommendations:
            recommendations.append("Maintain current test quality")
        return recommendations

    def generate_metrics_file(
        self,
        metrics: ExecutionMetrics,
        output_path: Path,
    ) -> Path:
        metrics_path = output_path / "execution-metrics.json"
        metrics_path.write_text(
            json.dumps(metrics.model_dump(), indent=2, default=str),
            encoding="utf-8",
        )
        self.logger.info("metrics_file_generated", path=str(metrics_path))
        return metrics_path
