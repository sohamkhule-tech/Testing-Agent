import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logging import LoggerMixin
from app.schemas.execution import (
    ArtifactSummary,
    ExecutionMetrics,
    ExecutionStatus,
    ExecutionSummary,
    FailureSummary,
    TestResult,
)


class ReportGenerator(LoggerMixin):

    def __init__(self) -> None:
        super().__init__()

    def generate_reports(
        self,
        execution_summary: ExecutionSummary,
        output_path: Path,
    ) -> dict[str, Path]:
        self.logger.info("generating_reports", output_path=str(output_path))
        output_path.mkdir(parents=True, exist_ok=True)

        reports: dict[str, Path] = {}

        reports["execution-summary.json"] = self._generate_execution_json(
            execution_summary, output_path
        )
        reports["execution-summary.md"] = self._generate_execution_markdown(
            execution_summary, output_path
        )
        reports["junit.xml"] = self._generate_junit_xml(execution_summary, output_path)
        reports["failure-report.json"] = self._generate_failure_report_json(
            execution_summary, output_path
        )
        reports["metrics-report.json"] = self._generate_metrics_report_json(
            execution_summary, output_path
        )
        reports["artifacts-index.json"] = self._generate_artifacts_index(
            execution_summary, output_path
        )
        reports["dashboard.html"] = self._generate_html_dashboard(
            execution_summary, output_path
        )

        self.logger.info("reports_generated", count=len(reports))
        return reports

    def _generate_execution_json(
        self,
        execution_summary: ExecutionSummary,
        output_path: Path,
    ) -> Path:
        report_path = output_path / "execution-summary.json"

        data = {
            "execution_id": execution_summary.execution_id,
            "status": execution_summary.status.value,
            "start_time": execution_summary.start_time,
            "end_time": execution_summary.end_time,
            "duration_seconds": execution_summary.duration_seconds,
            "metrics": execution_summary.metrics.model_dump(),
            "summary": {
                "total": execution_summary.metrics.total_tests,
                "passed": execution_summary.metrics.tests_passed,
                "failed": execution_summary.metrics.tests_failed,
                "skipped": execution_summary.metrics.tests_skipped,
                "flaky": execution_summary.metrics.tests_flaky,
                "pass_rate": execution_summary.metrics.pass_rate,
            },
            "failure_summary": (
                execution_summary.failure_summary.model_dump()
                if execution_summary.failure_summary
                else None
            ),
            "retry_summary": (
                execution_summary.retry_summary.model_dump()
                if execution_summary.retry_summary
                else None
            ),
            "artifacts": execution_summary.artifacts.model_dump(),
            "report_paths": execution_summary.report_paths,
            "environment": execution_summary.environment,
            "warnings": execution_summary.warnings,
            "errors": execution_summary.errors,
        }

        report_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        self.logger.debug("execution_json_report_generated", path=str(report_path))
        return report_path

    def _generate_execution_markdown(
        self,
        execution_summary: ExecutionSummary,
        output_path: Path,
    ) -> Path:
        report_path = output_path / "execution-summary.md"
        metrics = execution_summary.metrics

        status_emoji = "[PASS]" if metrics.tests_failed == 0 else "[FAIL]"
        pass_rate_str = f"{metrics.pass_rate:.1f}%"

        slowest = metrics.slowest_tests[0] if metrics.slowest_tests else None
        slowest_str = f"{slowest['title']} ({slowest['duration_ms']}ms)" if slowest else "N/A"

        failure_reasons = ""
        if execution_summary.failure_summary and execution_summary.failure_summary.failure_type_counts:
            for ft, count in sorted(
                execution_summary.failure_summary.failure_type_counts.items(),
                key=lambda x: x[1],
                reverse=True,
            ):
                failure_reasons += f"  - {ft.replace('_', ' ').title()}: {count}\n"

        artifacts_list = ""
        artifacts = execution_summary.artifacts
        if artifacts.screenshots_count > 0:
            artifacts_list += f"  - Screenshots: {artifacts.screenshots_count}\n"
        if artifacts.videos_count > 0:
            artifacts_list += f"  - Videos: {artifacts.videos_count}\n"
        if artifacts.traces_count > 0:
            artifacts_list += f"  - Traces: {artifacts.traces_count}\n"
        if artifacts.logs_count > 0:
            artifacts_list += f"  - Logs: {artifacts.logs_count}\n"

        recommendations = []
        if metrics.tests_failed > 0:
            recommendations.append(f"- Fix {metrics.tests_failed} failing test(s)")
        if metrics.tests_flaky > 0:
            recommendations.append(f"- Stabilize {metrics.tests_flaky} flaky test(s)")
        if metrics.health_score < 75:
            recommendations.append("- Improve test suite health score")
        if not recommendations:
            recommendations.append("- All tests passing, maintain quality")

        report_content = f"""# Test Execution Report

**Status:** {status_emoji} {execution_summary.status.value.upper()}

## Summary

| Metric | Value |
|--------|-------|
| **Total Tests** | {metrics.total_tests} |
| **Passed** | {metrics.tests_passed} |
| **Failed** | {metrics.tests_failed} |
| **Skipped** | {metrics.tests_skipped} |
| **Flaky** | {metrics.tests_flaky} |
| **Pass Rate** | {pass_rate_str} |
| **Duration** | {metrics.total_duration_seconds:.2f}s |

## Slowest Test

{slowest_str}

## Failure Reasons

{failure_reasons if failure_reasons else '  - No failures\n'}
## Artifacts

{artifacts_list if artifacts_list else '  - No artifacts collected\n'}
## Reports

"""

        for report_type, report_path in execution_summary.report_paths.items():
            report_content += f"  - {report_type}: {report_path}\n"

        report_content += f"""
## Recommendations

{chr(10).join(recommendations)}

---

*Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

        report_path.write_text(report_content, encoding="utf-8")
        self.logger.debug("execution_markdown_report_generated", path=str(report_path))
        return report_path

    def _generate_junit_xml(
        self,
        execution_summary: ExecutionSummary,
        output_path: Path,
    ) -> Path:
        report_path = output_path / "junit.xml"
        metrics = execution_summary.metrics
        total_duration_s = metrics.total_duration_seconds

        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<testsuites name="Playwright Tests" tests="{metrics.total_tests}" '
            f'failures="{metrics.tests_failed}" '
            f'skipped="{metrics.tests_skipped}" '
            f'time="{total_duration_s:.3f}">',
            f'  <testsuite name="Execution" tests="{metrics.total_tests}" '
            f'failures="{metrics.tests_failed}" '
            f'skipped="{metrics.tests_skipped}" '
            f'time="{total_duration_s:.3f}">',
        ]

        for test in execution_summary.test_results:
            test_name = test.title
            test_file = test.file or "unknown"
            duration = test.duration_ms / 1000

            xml_lines.append(
                f'    <testcase name="{self._escape_xml(test_name)}" '
                f'classname="{self._escape_xml(test_file)}" '
                f'time="{duration:.3f}">'
            )

            if test.status == "failed":
                error_msg = test.error_message or "Test failed"
                xml_lines.append(
                    f'      <failure message="{self._escape_xml(error_msg[:500])}"/>'
                )
            elif test.status == "skipped":
                xml_lines.append("      <skipped/>")

            xml_lines.append("    </testcase>")

        xml_lines.extend(["  </testsuite>", "</testsuites>"])
        report_path.write_text("\n".join(xml_lines), encoding="utf-8")
        self.logger.debug("junit_xml_generated", path=str(report_path))
        return report_path

    def _generate_failure_report_json(
        self,
        execution_summary: ExecutionSummary,
        output_path: Path,
    ) -> Path:
        report_path = output_path / "failure-report.json"

        failures = []
        for test in execution_summary.test_results:
            if test.status == "failed":
                failures.append({
                    "test": test.title,
                    "file": test.file,
                    "duration_ms": test.duration_ms,
                    "error": test.error_message,
                    "stack_trace": test.error_stack,
                    "failure_analysis": test.failure_analysis,
                    "was_retried": test.was_retried,
                })

        failure_summary = execution_summary.failure_summary
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_failures": len(failures),
            "failure_type_counts": (
                failure_summary.failure_type_counts if failure_summary else {}
            ),
            "flaky_tests": (failure_summary.flaky_tests if failure_summary else []),
            "failures": failures,
        }

        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        self.logger.debug("failure_report_generated", path=str(report_path))
        return report_path

    def _generate_metrics_report_json(
        self,
        execution_summary: ExecutionSummary,
        output_path: Path,
    ) -> Path:
        report_path = output_path / "metrics-report.json"
        metrics = execution_summary.metrics

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics.model_dump(),
            "health": {
                "score": metrics.health_score,
                "status": metrics.health_status,
            },
        }

        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        self.logger.debug("metrics_report_generated", path=str(report_path))
        return report_path

    def _generate_artifacts_index(
        self,
        execution_summary: ExecutionSummary,
        output_path: Path,
    ) -> Path:
        report_path = output_path / "artifacts-index.json"
        artifacts = execution_summary.artifacts

        index: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "artifacts_path": artifacts.artifacts_path,
            "summary": {
                "screenshots": artifacts.screenshots_count,
                "videos": artifacts.videos_count,
                "traces": artifacts.traces_count,
                "logs": artifacts.logs_count,
                "total_size_bytes": artifacts.total_size_bytes,
            },
            "reports": execution_summary.report_paths,
        }

        report_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        self.logger.debug("artifacts_index_generated", path=str(report_path))
        return report_path

    def _generate_html_dashboard(
        self,
        execution_summary: ExecutionSummary,
        output_path: Path,
    ) -> Path:
        report_path = output_path / "dashboard.html"
        metrics = execution_summary.metrics

        pass_rate_color = (
            "#4caf50" if metrics.pass_rate >= 75
            else "#ff9800" if metrics.pass_rate >= 50
            else "#f44336"
        )

        test_rows = ""
        for test in execution_summary.test_results:
            status_class = test.status
            test_rows += f"""
            <tr class="{status_class}">
                <td>{self._escape_html(test.title)}</td>
                <td>{self._escape_html(test.file or 'Unknown')}</td>
                <td>{test.duration_ms:.0f}ms</td>
                <td><span class="badge badge-{status_class}">{status_class.upper()}</span></td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Execution Report - {execution_summary.execution_id}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; padding: 20px; color: #333; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 24px; }}
        .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .header .meta {{ opacity: 0.9; font-size: 14px; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .card {{ background: white; border-radius: 10px; padding: 20px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        .card .value {{ font-size: 36px; font-weight: 700; }}
        .card .label {{ font-size: 12px; color: #888; text-transform: uppercase; margin-top: 4px; }}
        .card.passed .value {{ color: #4caf50; }}
        .card.failed .value {{ color: #f44336; }}
        .card.skipped .value {{ color: #ff9800; }}
        .card.flaky .value {{ color: #9c27b0; }}
        .card.total .value {{ color: #2196f3; }}
        .pass-rate-section {{ text-align: center; padding: 24px; background: white; border-radius: 10px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        .pass-rate-value {{ font-size: 48px; font-weight: 700; color: {pass_rate_color}; }}
        .pass-rate-label {{ font-size: 14px; color: #888; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        th {{ background: #f5f7fa; padding: 12px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: #888; }}
        td {{ padding: 12px 16px; border-top: 1px solid #f0f0f0; font-size: 14px; }}
        tr.passed td {{ border-left: 3px solid #4caf50; }}
        tr.failed td {{ border-left: 3px solid #f44336; background: #fff5f5; }}
        tr.skipped td {{ border-left: 3px solid #ff9800; }}
        .badge {{ font-size: 11px; padding: 3px 8px; border-radius: 12px; font-weight: 600; }}
        .badge-passed {{ background: #e8f5e9; color: #2e7d32; }}
        .badge-failed {{ background: #ffebee; color: #c62828; }}
        .badge-skipped {{ background: #fff3e0; color: #e65100; }}
        .badge-flaky {{ background: #f3e5f5; color: #6a1b9a; }}
        .section-title {{ font-size: 18px; font-weight: 600; margin: 24px 0 12px; }}
        .failure-list {{ background: white; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        .failure-item {{ padding: 12px; border-left: 3px solid #f44336; margin-bottom: 8px; background: #fff5f5; border-radius: 4px; }}
        .failure-item .test-name {{ font-weight: 600; }}
        .failure-item .error-msg {{ font-family: monospace; font-size: 12px; color: #666; margin-top: 4px; white-space: pre-wrap; }}
        .health-bar {{ height: 8px; background: #e0e0e0; border-radius: 4px; margin: 8px 0; overflow: hidden; }}
        .health-fill {{ height: 100%; border-radius: 4px; background: linear-gradient(90deg, #f44336, #ff9800, #4caf50); width: {metrics.health_score}%; }}
        .health-status {{ font-size: 14px; color: {pass_rate_color}; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Test Execution Report</h1>
            <div class="meta">Execution ID: {self._escape_html(execution_summary.execution_id)}</div>
            <div class="meta">Started: {execution_summary.start_time} | Ended: {execution_summary.end_time}</div>
            <div class="meta">Duration: {metrics.total_duration_seconds:.2f}s</div>
        </div>

        <div class="cards">
            <div class="card total">
                <div class="value">{metrics.total_tests}</div>
                <div class="label">Total</div>
            </div>
            <div class="card passed">
                <div class="value">{metrics.tests_passed}</div>
                <div class="label">Passed</div>
            </div>
            <div class="card failed">
                <div class="value">{metrics.tests_failed}</div>
                <div class="label">Failed</div>
            </div>
            <div class="card skipped">
                <div class="value">{metrics.tests_skipped}</div>
                <div class="label">Skipped</div>
            </div>
            <div class="card flaky">
                <div class="value">{metrics.tests_flaky}</div>
                <div class="label">Flaky</div>
            </div>
        </div>

        <div class="pass-rate-section">
            <div class="pass-rate-value">{metrics.pass_rate:.1f}%</div>
            <div class="pass-rate-label">Pass Rate</div>
            <div class="health-bar"><div class="health-fill"></div></div>
            <div class="health-status">{metrics.health_status.title()} (Score: {metrics.health_score})</div>
        </div>

        <div class="section-title">Test Results ({metrics.total_tests})</div>
        <table>
            <thead>
                <tr>
                    <th>Test</th>
                    <th>File</th>
                    <th>Duration</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {test_rows}
            </tbody>
        </table>
    </div>
</body>
</html>"""

        report_path.write_text(html, encoding="utf-8")
        self.logger.debug("html_dashboard_generated", path=str(report_path))
        return report_path

    def _escape_xml(self, text: str) -> str:
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    def _escape_html(self, text: str) -> str:
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
