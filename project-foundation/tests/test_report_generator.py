import pytest
from pathlib import Path
from datetime import datetime

from app.execution.report_generator import ReportGenerator
from app.schemas.execution import (
    ArtifactSummary,
    ExecutionConfig,
    ExecutionMetrics,
    ExecutionStatus,
    ExecutionSummary,
    FailureSummary,
    TestResult,
)


@pytest.mark.unit
class TestReportGenerator:
    def create_sample_summary(self) -> ExecutionSummary:
        return ExecutionSummary(
            execution_id="test-exec-001",
            status=ExecutionStatus.COMPLETED,
            start_time=datetime.now().isoformat(),
            end_time=datetime.now().isoformat(),
            duration_seconds=30.5,
            config=ExecutionConfig(),
            metrics=ExecutionMetrics(
                total_tests=3,
                tests_passed=2,
                tests_failed=1,
                tests_skipped=0,
                pass_rate=66.67,
                fail_rate=33.33,
                total_duration_seconds=30.5,
                average_duration_ms=150.0,
                slowest_tests=[{"title": "Slow test", "duration_ms": 500}],
            ),
            test_results=[
                TestResult(title="Test 1", status="passed", duration_ms=100, file="tests/a.spec.ts"),
                TestResult(title="Test 2", status="passed", duration_ms=200, file="tests/b.spec.ts"),
                TestResult(
                    title="Test 3",
                    status="failed",
                    duration_ms=150,
                    file="tests/c.spec.ts",
                    error_message="Timeout exceeded",
                ),
            ],
            failure_summary=FailureSummary(
                total_failures=1,
                failure_type_counts={"timeout": 1},
                flaky_tests=[],
            ),
            artifacts=ArtifactSummary(
                screenshots_count=2,
                videos_count=0,
                traces_count=1,
                logs_count=3,
                total_size_bytes=1024,
            ),
        )

    def test_generate_execution_json(self, temp_dir: Path):
        gen = ReportGenerator()
        summary = self.create_sample_summary()

        path = gen._generate_execution_json(summary, temp_dir)
        assert path.exists()
        assert path.name == "execution-summary.json"

    def test_generate_execution_markdown(self, temp_dir: Path):
        gen = ReportGenerator()
        summary = self.create_sample_summary()

        path = gen._generate_execution_markdown(summary, temp_dir)
        assert path.exists()
        assert path.name == "execution-summary.md"

        content = path.read_text(encoding="utf-8")
        assert "Test Execution Report" in content
        assert "[PASS]" in content or "[FAIL]" in content
        assert "## Summary" in content
        assert "## Failure Reasons" in content
        assert "## Recommendations" in content

    def test_generate_junit_xml(self, temp_dir: Path):
        gen = ReportGenerator()
        summary = self.create_sample_summary()

        path = gen._generate_junit_xml(summary, temp_dir)
        assert path.exists()
        assert path.name == "junit.xml"

        content = path.read_text()
        assert "testsuites" in content
        assert "testcase" in content
        assert "failure" in content
        assert "Playwright Tests" in content

    def test_generate_failure_report_json(self, temp_dir: Path):
        gen = ReportGenerator()
        summary = self.create_sample_summary()

        path = gen._generate_failure_report_json(summary, temp_dir)
        assert path.exists()
        assert "failure" in path.name

    def test_generate_metrics_report_json(self, temp_dir: Path):
        gen = ReportGenerator()
        summary = self.create_sample_summary()

        path = gen._generate_metrics_report_json(summary, temp_dir)
        assert path.exists()
        assert path.name == "metrics-report.json"

    def test_generate_artifacts_index(self, temp_dir: Path):
        gen = ReportGenerator()
        summary = self.create_sample_summary()

        path = gen._generate_artifacts_index(summary, temp_dir)
        assert path.exists()
        assert path.name == "artifacts-index.json"

    def test_generate_html_dashboard(self, temp_dir: Path):
        gen = ReportGenerator()
        summary = self.create_sample_summary()

        path = gen._generate_html_dashboard(summary, temp_dir)
        assert path.exists()
        assert path.name == "dashboard.html"

        content = path.read_text()
        assert "Test Execution Report" in content
        assert "66.7" in content or "66.67" in content
        assert "Test 3" in content

    def test_generate_all_reports(self, temp_dir: Path):
        gen = ReportGenerator()
        summary = self.create_sample_summary()

        reports = gen.generate_reports(summary, temp_dir)
        assert len(reports) >= 7
        assert "execution-summary.json" in reports
        assert "execution-summary.md" in reports
        assert "junit.xml" in reports
        assert "dashboard.html" in reports
        assert "failure-report.json" in reports
        assert "metrics-report.json" in reports
        assert "artifacts-index.json" in reports

    def test_escape_xml(self):
        gen = ReportGenerator()
        assert gen._escape_xml("<hello>") == "&lt;hello&gt;"
        assert gen._escape_xml('quote"') == "quote&quot;"

    def test_escape_html(self):
        gen = ReportGenerator()
        assert gen._escape_html("<script>") == "&lt;script&gt;"
        assert gen._escape_html("safe text") == "safe text"
