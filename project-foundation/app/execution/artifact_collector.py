import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logging import LoggerMixin
from app.schemas.execution import ArtifactSummary


class ArtifactCollector(LoggerMixin):

    def __init__(self) -> None:
        super().__init__()

    def collect_artifacts(
        self,
        project_path: Path,
        output_path: Path
    ) -> ArtifactSummary:
        self.logger.info(
            "collecting_artifacts",
            project_path=str(project_path),
            output_path=str(output_path)
        )

        output_path.mkdir(parents=True, exist_ok=True)

        reports_dir = output_path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        screenshots_dir = output_path / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        videos_dir = output_path / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        traces_dir = output_path / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = output_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        metrics_dir = output_path / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        failure_dir = output_path / "failure-analysis"
        failure_dir.mkdir(parents=True, exist_ok=True)

        screenshots = self._collect_screenshots(project_path, screenshots_dir)
        videos = self._collect_videos(project_path, videos_dir)
        traces = self._collect_traces(project_path, traces_dir)
        console_logs = self._collect_console_logs(project_path, logs_dir)
        self._copy_playwright_report(project_path, reports_dir)
        self._copy_json_report(project_path, output_path)
        self._copy_junit_report(project_path, output_path)
        self._collect_execution_logs(project_path, logs_dir)
        self._copy_metadata(project_path, output_path)

        total_size = self._calculate_directory_size(output_path)

        summary = ArtifactSummary(
            screenshots_count=len(screenshots),
            videos_count=len(videos),
            traces_count=len(traces),
            logs_count=len(console_logs),
            total_size_bytes=total_size,
            artifacts_path=str(output_path),
        )

        self.logger.info(
            "artifacts_collected",
            screenshots=summary.screenshots_count,
            videos=summary.videos_count,
            traces=summary.traces_count,
            logs=summary.logs_count,
            total_size_mb=total_size / (1024 * 1024)
        )

        return summary

    def _collect_screenshots(
        self,
        project_path: Path,
        screenshots_dir: Path
    ) -> list[Path]:
        collected = []
        seen_names: set[str] = set()
        test_results_dir = project_path / "test-results"

        if test_results_dir.exists():
            for screenshot_file in test_results_dir.rglob("*.png"):
                sanitized_name = self._sanitize_filename(screenshot_file.name)
                dest = screenshots_dir / sanitized_name
                if dest.name not in seen_names:
                    shutil.copy2(screenshot_file, dest)
                    collected.append(dest)
                    seen_names.add(dest.name)

        for sf in project_path.rglob("screenshot*.png"):
            if sf.parent != screenshots_dir and not sf.parent.name == "test-results":
                sanitized_name = self._sanitize_filename(sf.name)
                dest = screenshots_dir / sanitized_name
                if dest.name not in seen_names:
                    shutil.copy2(sf, dest)
                    collected.append(dest)
                    seen_names.add(dest.name)

        return collected

    def _collect_videos(
        self,
        project_path: Path,
        videos_dir: Path
    ) -> list[Path]:
        collected = []
        test_results_dir = project_path / "test-results"

        if test_results_dir.exists():
            for video_file in test_results_dir.rglob("*.webm"):
                sanitized_name = self._sanitize_filename(video_file.name)
                dest = videos_dir / sanitized_name
                shutil.copy2(video_file, dest)
                collected.append(dest)

        return collected

    def _collect_traces(
        self,
        project_path: Path,
        traces_dir: Path
    ) -> list[Path]:
        collected = []
        test_results_dir = project_path / "test-results"

        if test_results_dir.exists():
            for trace_file in test_results_dir.rglob("trace.zip"):
                parent_name = self._sanitize_filename(trace_file.parent.name)
                dest = traces_dir / f"{parent_name}-trace.zip"
                shutil.copy2(trace_file, dest)
                collected.append(dest)

        return collected

    def _collect_console_logs(
        self,
        project_path: Path,
        logs_dir: Path
    ) -> list[Path]:
        collected = []
        test_results_dir = project_path / "test-results"

        if test_results_dir.exists():
            for log_file in test_results_dir.rglob("*.log"):
                sanitized_name = self._sanitize_filename(log_file.name)
                dest = logs_dir / sanitized_name
                shutil.copy2(log_file, dest)
                collected.append(dest)

        return collected

    def _copy_playwright_report(
        self,
        project_path: Path,
        reports_dir: Path
    ) -> None:
        playwright_report = project_path / "playwright-report"
        if playwright_report.exists() and playwright_report.is_dir():
            dest = reports_dir / "playwright-report"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(playwright_report, dest)
            self.logger.debug("playwright_html_report_copied", dest=str(dest))

    def _copy_json_report(self, project_path: Path, output_path: Path) -> None:
        results_file = project_path / "test-results" / "results.json"
        if results_file.exists():
            dest = output_path / "reports" / "results.json"
            shutil.copy2(results_file, dest)
            self.logger.debug("json_report_copied", dest=str(dest))

    def _copy_junit_report(self, project_path: Path, output_path: Path) -> None:
        junit_file = project_path / "test-results" / "junit.xml"
        if junit_file.exists():
            dest = output_path / "reports" / "junit.xml"
            shutil.copy2(junit_file, dest)
            self.logger.debug("junit_report_copied", dest=str(dest))

    def _collect_execution_logs(
        self,
        project_path: Path,
        logs_dir: Path
    ) -> None:
        for log_file in project_path.rglob("*.log"):
            if log_file.parent != logs_dir:
                sanitized_name = self._sanitize_filename(log_file.name)
                dest = logs_dir / sanitized_name
                shutil.copy2(log_file, dest)

    def _copy_metadata(self, project_path: Path, output_path: Path) -> None:
        for pattern in ["*.json", "*.yaml", "*.yml"]:
            for f in project_path.glob(pattern):
                if f.name == "package.json" or f.parent == output_path:
                    continue
                dest = output_path / "reports" / f.name
                shutil.copy2(f, dest)

    def _sanitize_filename(self, filename: str) -> str:
        invalid_chars = '<>:"/\\|?*'
        for c in invalid_chars:
            filename = filename.replace(c, "_")
        return filename

    def _calculate_directory_size(self, directory: Path) -> int:
        total_size = 0
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size

    def create_artifact_index(
        self,
        artifacts_path: Path,
        test_results: list[dict[str, Any]]
    ) -> Path:
        index: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "artifacts_path": str(artifacts_path),
            "tests": [],
        }

        for test in test_results:
            test_title = test.get("title", "Unknown")
            test_file = test.get("file", "")

            test_artifacts: dict[str, Any] = {
                "test_title": test_title,
                "test_file": test_file,
                "status": test.get("status"),
                "screenshots": [],
                "videos": [],
                "traces": [],
                "logs": [],
            }

            test_slug = test_title.lower().replace(" ", "-").replace("/", "-")

            screenshots_dir = artifacts_path / "screenshots"
            if screenshots_dir.exists():
                for screenshot in screenshots_dir.glob(f"*{test_slug}*.png"):
                    test_artifacts["screenshots"].append(str(screenshot.relative_to(artifacts_path)))

            videos_dir = artifacts_path / "videos"
            if videos_dir.exists():
                for video in videos_dir.glob(f"*{test_slug}*.webm"):
                    test_artifacts["videos"].append(str(video.relative_to(artifacts_path)))

            traces_dir = artifacts_path / "traces"
            if traces_dir.exists():
                for trace in traces_dir.glob(f"*{test_slug}*.zip"):
                    test_artifacts["traces"].append(str(trace.relative_to(artifacts_path)))

            logs_dir = artifacts_path / "logs"
            if logs_dir.exists():
                for log_entry in logs_dir.glob(f"*{test_slug}*"):
                    test_artifacts["logs"].append(str(log_entry.relative_to(artifacts_path)))

            index["tests"].append(test_artifacts)

        index_path = artifacts_path / "artifact-index.json"
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

        self.logger.info("artifact_index_created", path=str(index_path))
        return index_path

    def collect_execution_metadata(
        self,
        project_path: Path,
        output_path: Path,
        execution_result: dict[str, Any]
    ) -> Path:
        metadata = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "project_path": str(project_path),
            "command": execution_result.get("command", ""),
            "return_code": execution_result.get("return_code"),
            "duration_seconds": execution_result.get("duration_seconds", 0),
            "browser": execution_result.get("browser", "unknown"),
            "start_time": execution_result.get("start_time"),
            "end_time": execution_result.get("end_time"),
        }

        metadata_path = output_path / "execution-metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        self.logger.debug("execution_metadata_collected", path=str(metadata_path))
        return metadata_path

    def collect_network_logs(
        self,
        project_path: Path,
        output_path: Path
    ) -> list[Path]:
        collected = []
        test_results_dir = project_path / "test-results"

        if test_results_dir.exists():
            for har_file in test_results_dir.rglob("*.har"):
                sanitized_name = self._sanitize_filename(har_file.name)
                dest = output_path / "logs" / sanitized_name
                shutil.copy2(har_file, dest)
                collected.append(dest)

        return collected
