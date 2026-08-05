import pytest
from pathlib import Path

from app.execution.artifact_collector import ArtifactCollector


@pytest.mark.unit
class TestArtifactCollector:
    def test_collect_artifacts_empty_project(self, temp_dir: Path):
        project_path = temp_dir / "test-project"
        project_path.mkdir()
        output_path = temp_dir / "output"

        collector = ArtifactCollector()
        summary = collector.collect_artifacts(project_path, output_path)

        assert summary.screenshots_count == 0
        assert summary.videos_count == 0
        assert summary.traces_count == 0
        assert summary.logs_count == 0
        assert summary.total_size_bytes == 0
        assert summary.artifacts_path is not None

    def test_collect_screenshots(self, temp_dir: Path):
        project_path = temp_dir / "project"
        project_path.mkdir()
        results_dir = project_path / "test-results"
        results_dir.mkdir(parents=True)
        (results_dir / "screenshot-test-1.png").write_text("mock")
        (results_dir / "screenshot-test-2.png").write_text("mock")

        output_path = temp_dir / "output"
        output_path.mkdir()
        (output_path / "screenshots").mkdir()

        collector = ArtifactCollector()
        screenshots = collector._collect_screenshots(project_path, output_path / "screenshots")

        assert len(screenshots) == 2

    def test_collect_videos(self, temp_dir: Path):
        project_path = temp_dir / "project"
        project_path.mkdir()
        results_dir = project_path / "test-results"
        results_dir.mkdir(parents=True)
        (results_dir / "video-test.webm").write_text("mock")

        output_path = temp_dir / "output"
        output_path.mkdir()
        (output_path / "videos").mkdir()

        collector = ArtifactCollector()
        videos = collector._collect_videos(project_path, output_path / "videos")

        assert len(videos) == 1

    def test_collect_traces(self, temp_dir: Path):
        project_path = temp_dir / "project"
        project_path.mkdir()
        results_dir = project_path / "test-results"
        results_dir.mkdir(parents=True)
        trace_dir = results_dir / "test-name"
        trace_dir.mkdir()
        (trace_dir / "trace.zip").write_text("mock")

        output_path = temp_dir / "output"
        output_path.mkdir()
        (output_path / "traces").mkdir()

        collector = ArtifactCollector()
        traces = collector._collect_traces(project_path, output_path / "traces")

        assert len(traces) == 1

    def test_collect_execution_metadata(self, temp_dir: Path):
        project_path = temp_dir / "project"
        project_path.mkdir()
        output_path = temp_dir / "output"
        output_path.mkdir()

        execution_result = {
            "command": "npx playwright test",
            "return_code": 0,
            "duration_seconds": 10.5,
            "browser": "chromium",
            "start_time": "2024-01-01T00:00:00",
            "end_time": "2024-01-01T00:00:10",
        }

        collector = ArtifactCollector()
        path = collector.collect_execution_metadata(
            project_path, output_path, execution_result
        )

        assert path.exists()

    def test_create_artifact_index(self, temp_dir: Path):
        output_path = temp_dir / "output"
        output_path.mkdir()
        (output_path / "screenshots").mkdir()
        (output_path / "traces").mkdir()
        (output_path / "videos").mkdir()
        (output_path / "logs").mkdir()

        test_results = [
            {"title": "Test 1", "file": "tests/test.spec.ts", "status": "passed"},
            {"title": "Test 2", "file": "tests/test2.spec.ts", "status": "failed"},
        ]

        collector = ArtifactCollector()
        path = collector.create_artifact_index(output_path, test_results)

        assert path.exists()
        assert path.name == "artifact-index.json"

    def test_sanitize_filename(self):
        collector = ArtifactCollector()
        assert collector._sanitize_filename("test<file>.png") == "test_file_.png"
        assert collector._sanitize_filename("normal.png") == "normal.png"
