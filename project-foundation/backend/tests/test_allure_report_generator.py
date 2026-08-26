import json
from pathlib import Path

import pytest

from app.execution.allure_report_generator import (
    DEFAULT_CATEGORIES,
    AllureReportGenerator,
)


@pytest.mark.unit
class TestAllureReportGenerator:
    def test_generate_unavailable_when_no_results_dir(self, temp_dir: Path, monkeypatch):
        generator = AllureReportGenerator()
        called = {"count": 0}

        def fail_if_run(*a, **kw):
            called["count"] += 1

        monkeypatch.setattr(
            "app.execution.allure_report_generator.subprocess.run",
            fail_if_run,
        )

        result = generator.generate(
            results_dir=temp_dir / "allure-results",
            output_path=temp_dir / "allure-report",
        )

        assert result["status"] == "unavailable"
        assert "No Allure results found" in result["error"]
        assert called["count"] == 0

    def test_generate_unavailable_when_empty_results_dir(self, temp_dir: Path):
        generator = AllureReportGenerator()
        results_dir = temp_dir / "allure-results"
        results_dir.mkdir(parents=True)

        result = generator.generate(
            results_dir=results_dir,
            output_path=temp_dir / "allure-report",
        )

        assert result["status"] == "unavailable"

    def test_generate_success(self, temp_dir: Path, monkeypatch):
        generator = AllureReportGenerator()
        results_dir = temp_dir / "allure-results"
        results_dir.mkdir(parents=True)
        (results_dir / "111-result.json").write_text("{}")

        class FakeResult:
            returncode = 0
            stdout = "Report generated"
            stderr = ""

        def fake_run(*args, **kwargs):
            output_path = next(
                Path(part)
                for part in args[0].split('"')
                if str(temp_dir / "allure-report") in part
            )
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "index.html").write_text("<html></html>", encoding="utf-8")
            return FakeResult()

        monkeypatch.setattr(
            "app.execution.allure_report_generator.subprocess.run",
            fake_run,
        )

        result = generator.generate(
            results_dir=results_dir,
            output_path=temp_dir / "allure-report",
            project_path=temp_dir,
            environment={"Base URL": "http://example.com", "Browser": "chromium"},
        )

        assert result["status"] == "generated"
        assert result["report_path"] == str(temp_dir / "allure-report")
        assert result["results_path"] == str(results_dir)

    def test_generate_synthesizes_results_from_playwright_fallback(self, temp_dir: Path, monkeypatch):
        generator = AllureReportGenerator()
        results_dir = temp_dir / "allure-results"

        class FakeResult:
            returncode = 0
            stdout = "Report generated"
            stderr = ""

        def fake_run(*args, **kwargs):
            output_path = next(
                Path(part)
                for part in args[0].split('"')
                if str(temp_dir / "allure-report") in part
            )
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "index.html").write_text("<html></html>", encoding="utf-8")
            return FakeResult()

        monkeypatch.setattr(
            "app.execution.allure_report_generator.subprocess.run",
            fake_run,
        )

        result = generator.generate(
            results_dir=results_dir,
            output_path=temp_dir / "allure-report",
            project_path=temp_dir,
            fallback_test_results=[
                {
                    "title": "logs in successfully",
                    "file": "tests/login.spec.ts",
                    "status": "passed",
                    "duration_ms": 1200,
                    "browser": "chromium",
                }
            ],
        )

        assert result["status"] == "generated"
        result_files = list(results_dir.glob("*-result.json"))
        assert len(result_files) == 1
        data = json.loads(result_files[0].read_text(encoding="utf-8"))
        assert data["name"] == "logs in successfully"
        assert data["status"] == "passed"
        assert {"name": "browser", "value": "chromium"} in data["labels"]

    def test_generate_writes_environment_and_categories(self, temp_dir: Path):
        generator = AllureReportGenerator()
        results_dir = temp_dir / "allure-results"
        results_dir.mkdir(parents=True)
        (results_dir / "111-result.json").write_text("{}")

        generator._write_environment_file(
            results_dir,
            {"Base URL": "http://example.com", "Browser": "chromium", "Blank": ""},
        )
        generator._write_categories_file(results_dir)

        env_file = results_dir / "environment.properties"
        categories_file = results_dir / "categories.json"

        assert env_file.exists()
        content = env_file.read_text(encoding="utf-8")
        assert "Base URL=http://example.com" in content
        assert "Browser=chromium" in content
        assert "Blank=" not in content

        assert categories_file.exists()
        categories = json.loads(categories_file.read_text(encoding="utf-8"))
        assert categories == DEFAULT_CATEGORIES

    def test_generate_skips_environment_and_categories_when_unavailable(self, temp_dir: Path):
        generator = AllureReportGenerator()
        results_dir = temp_dir / "allure-results"
        results_dir.mkdir(parents=True)

        result = generator.generate(
            results_dir=results_dir,
            output_path=temp_dir / "allure-report",
            environment={"Browser": "chromium"},
        )

        assert result["status"] == "unavailable"
        assert not (results_dir / "environment.properties").exists()
        assert not (results_dir / "categories.json").exists()

    def test_generate_failure_nonzero_exit(self, temp_dir: Path, monkeypatch):
        generator = AllureReportGenerator()
        results_dir = temp_dir / "allure-results"
        results_dir.mkdir(parents=True)
        (results_dir / "111-result.json").write_text("{}")

        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "allure: command not found"

        monkeypatch.setattr(
            "app.execution.allure_report_generator.subprocess.run",
            lambda *a, **kw: FakeResult(),
        )

        result = generator.generate(
            results_dir=results_dir,
            output_path=temp_dir / "allure-report",
        )

        assert result["status"] == "failed"
        assert "exited with code 1" in result["error"]

    def test_generate_failure_on_exception(self, temp_dir: Path, monkeypatch):
        generator = AllureReportGenerator()
        results_dir = temp_dir / "allure-results"
        results_dir.mkdir(parents=True)
        (results_dir / "111-result.json").write_text("{}")

        def boom(*a, **kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "app.execution.allure_report_generator.subprocess.run",
            boom,
        )

        result = generator.generate(
            results_dir=results_dir,
            output_path=temp_dir / "allure-report",
        )

        assert result["status"] == "failed"
        assert "boom" in result["error"]

    def test_has_results(self, temp_dir: Path):
        generator = AllureReportGenerator()
        assert generator._has_results(temp_dir / "missing") is False

        results_dir = temp_dir / "allure-results"
        results_dir.mkdir(parents=True)
        assert generator._has_results(results_dir) is False

        (results_dir / "222-container.json").write_text("{}")
        assert generator._has_results(results_dir) is True
