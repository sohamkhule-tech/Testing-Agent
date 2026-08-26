import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logging import LoggerMixin
from app.schemas.execution import ArtifactSummary


class ArtifactCollector(LoggerMixin):

    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def _to_extended_path(p: Path) -> str:
        """Return a \\?\ prefixed absolute path on Windows to bypass MAX_PATH (260 chars).

        Playwright writes hash-named attachments under playwright-report/data/.
        The full path frequently exceeds 260 chars on deeply nested OneDrive/workspace
        layouts, causing CreateFileW to return ERROR_PATH_NOT_FOUND (WinError 3) for
        every individual file even though the parent directory is reachable.
        The \\?\ prefix switches Windows to the 32 767-char limit.
        """
        if os.name != "nt":
            return str(p)
        resolved = str(p.resolve())
        if resolved.startswith("\\\\?\\"):
            return resolved
        if resolved.startswith("\\\\"):  # UNC path
            return "\\\\?\\UNC\\" + resolved[2:]
        return "\\\\?\\" + resolved

    @staticmethod
    def _copy2_longpath(src: str, dst: str, **_: Any) -> None:
        """shutil copy_function that prefixes both paths for Windows MAX_PATH bypass."""
        if os.name == "nt":
            def _ext(s: str) -> str:
                if s.startswith("\\\\?\\"):
                    return s
                if s.startswith("\\\\"):
                    return "\\\\?\\UNC\\" + s[2:]
                return "\\\\?\\" + s
            src = _ext(os.path.abspath(src))
            dst = _ext(os.path.abspath(dst))
        shutil.copy2(src, dst)

    def collect_artifacts(
        self,
        project_path: Path,
        output_path: Path
    ) -> ArtifactSummary:
        project_path = project_path.resolve()
        output_path = output_path.resolve()
        playwright_report_src = project_path / "playwright-report"
        playwright_report_data = playwright_report_src / "data"

        # Count data files using extended path so MAX_PATH doesn't hide them
        if playwright_report_data.exists():
            try:
                data_file_count = sum(
                    1 for _ in os.scandir(self._to_extended_path(playwright_report_data))
                )
            except OSError:
                data_file_count = -1
        else:
            data_file_count = 0

        self.logger.info(
            "collecting_artifacts",
            run_dir=str(project_path.parent.parent),
            playwright_workspace=str(project_path),
            playwright_report_src=str(playwright_report_src),
            playwright_report_src_exists=playwright_report_src.exists(),
            playwright_report_src_is_dir=playwright_report_src.is_dir() if playwright_report_src.exists() else False,
            playwright_report_data_files=data_file_count,
            destination=str(output_path),
            env_html_report=os.environ.get("PLAYWRIGHT_HTML_REPORT", "(not set)"),
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
                    shutil.copy2(self._to_extended_path(screenshot_file), self._to_extended_path(dest))
                    collected.append(dest)
                    seen_names.add(dest.name)

        for sf in project_path.rglob("screenshot*.png"):
            if sf.parent != screenshots_dir and not sf.parent.name == "test-results":
                sanitized_name = self._sanitize_filename(sf.name)
                dest = screenshots_dir / sanitized_name
                if dest.name not in seen_names:
                    shutil.copy2(self._to_extended_path(sf), self._to_extended_path(dest))
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
                shutil.copy2(self._to_extended_path(video_file), self._to_extended_path(dest))
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
                shutil.copy2(self._to_extended_path(trace_file), self._to_extended_path(dest))
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
                shutil.copy2(self._to_extended_path(log_file), self._to_extended_path(dest))
                collected.append(dest)

        return collected

    def _copy_playwright_report(
        self,
        project_path: Path,
        reports_dir: Path
    ) -> None:
        playwright_report = project_path / "playwright-report"
        dest = reports_dir / "playwright-report"

        self.logger.info(
            "playwright_report_copy_start",
            src=str(playwright_report),
            dst=str(dest),
            src_exists=playwright_report.exists(),
            src_is_dir=playwright_report.is_dir() if playwright_report.exists() else False,
        )

        if not playwright_report.exists() or not playwright_report.is_dir():
            self.logger.warning(
                "playwright_html_report_missing",
                configured_path=str(playwright_report),
                hint=(
                    "Playwright HTML reporter did not create playwright-report/. "
                    "Check that 'html' is in playwright.config.ts reporters and "
                    "PLAYWRIGHT_HTML_REPORT env var matches this path."
                ),
            )
            return

        if dest.exists():
            shutil.rmtree(self._to_extended_path(Path(dest)))

        src_ext = self._to_extended_path(playwright_report)
        dst_ext = self._to_extended_path(dest)
        shutil.copytree(src_ext, dst_ext, copy_function=self._copy2_longpath)
        self.logger.debug("playwright_html_report_copied", dest=str(dest))

    def _copy_json_report(self, project_path: Path, output_path: Path) -> None:
        results_file = project_path / "test-results" / "results.json"
        if results_file.exists():
            dest = output_path / "reports" / "results.json"
            shutil.copy2(self._to_extended_path(results_file), self._to_extended_path(dest))
            self.logger.debug("json_report_copied", dest=str(dest))

    def _copy_junit_report(self, project_path: Path, output_path: Path) -> None:
        junit_file = project_path / "test-results" / "junit.xml"
        if junit_file.exists():
            dest = output_path / "reports" / "junit.xml"
            shutil.copy2(self._to_extended_path(junit_file), self._to_extended_path(dest))
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
                shutil.copy2(self._to_extended_path(log_file), self._to_extended_path(dest))

    def _copy_metadata(self, project_path: Path, output_path: Path) -> None:
        for pattern in ["*.json", "*.yaml", "*.yml"]:
            for f in project_path.glob(pattern):
                if f.name == "package.json" or f.parent == output_path:
                    continue
                dest = output_path / "reports" / f.name
                shutil.copy2(self._to_extended_path(f), self._to_extended_path(dest))

    def _sanitize_filename(self, filename: str) -> str:
        invalid_chars = '<>:"/\\|?*'
        for c in invalid_chars:
            filename = filename.replace(c, "_")
        return filename

    def _calculate_directory_size(self, directory: Path) -> int:
        total_size = 0
        stack = [self._to_extended_path(directory)]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        if entry.is_file(follow_symlinks=False):
                            try:
                                total_size += entry.stat(follow_symlinks=False).st_size
                            except OSError:
                                pass
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
            except OSError:
                pass
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
            "classification": execution_result.get("classification"),
            "stdout": execution_result.get("stdout", "")[:1000] if execution_result.get("stdout") else None,
            "stderr": execution_result.get("stderr", "")[:1000] if execution_result.get("stderr") else None,
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
                shutil.copy2(self._to_extended_path(har_file), self._to_extended_path(dest))
                collected.append(dest)

        return collected
