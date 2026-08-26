"""
Regression tests for Allure result de-duplication and long-path safety.

Guards against:
- Synthetic fallback results being written on top of REAL allure-playwright
  results (duplicate test cases: 20 logical tests showing as 40).
- ``force_rebuild``-style generation replacing real results with synthetic ones.
- Windows MAX_PATH (>260) failures silently causing real results to be treated
  as absent and never deleted, leaving both result sets behind.
- Retry attempts inflating the logical test count.
"""

import json
from pathlib import Path

import pytest

from app.execution.allure_report_generator import (
    _is_synthetic_result_name,
    _long_path,
)


def _result_dir(tmp_path: Path, name: str = "allure-results") -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _real_result(path: Path, name: str, status: str = "failed") -> None:
    """A result shaped like the official allure-playwright reporter output."""
    data = {
        "uuid": name.split("-")[0],
        "historyId": "h-" + name,
        "testCaseId": "tc-" + name,
        "name": name,
        "fullName": f"file.spec.ts#Login Module {name}",
        "status": status,
        "stage": "finished",
        "start": 1_000_000,
        "stop": 1_001_000,
        "steps": [{"name": "Fixture \"browser\"", "status": "passed", "stage": "finished", "start": 1_000_000, "stop": 1_000_500, "steps": [], "attachments": [], "parameters": []}],
        "attachments": [],
        "parameters": [],
        "labels": [
            {"name": "language", "value": "JavaScript"},
            {"name": "framework", "value": "Playwright"},
        ],
    }
    _long_path(path / f"{name}-result.json").write_text(json.dumps(data), encoding="utf-8")


def _synthetic_results(directory: Path, count: int) -> None:
    for i in range(count):
        data = {
            "uuid": f"syn-{i}",
            "historyId": f"syn-{i}",
            "testCaseId": f"syn-{i}",
            "name": f"Synthetic Test {i}",
            "fullName": f"file.spec.ts#Synthetic Test {i}",
            "status": "failed",
            "stage": "finished",
            "start": 1,
            "stop": 1000,
            "steps": [{"name": "Execute Test", "status": "failed", "stage": "finished", "start": 1, "stop": 1000, "steps": [], "attachments": [], "parameters": []}],
            "labels": [{"name": "framework", "value": "playwright"}],
        }
        _long_path(directory / f"{i:04d}-result.json").write_text(json.dumps(data), encoding="utf-8")


def _fallback_tests(count: int = 20) -> list[dict]:
    return [
        {
            "name": f"Test {i}",
            "file": "tests/login-module.spec.ts",
            "duration_ms": 100,
            "status": "failed" if i else "passed",
        }
        for i in range(count)
    ]


def _count_result_files(directory: Path) -> int:
    return len([p for p in directory.glob("*-result.json") if p.is_file()])


class _FakeRun:
    """Runs the allure CLI without launching a subprocess.

    Writes an index.html so generate() reports success and inspects the
    temptation path."""

    def __init__(self, output_path: Path):
        self.output_path = output_path

    def __call__(self, *args, **kwargs):
        self.output_path.mkdir(parents=True, exist_ok=True)
        (self.output_path / "index.html").write_text("<html></html>", encoding="utf-8")
        return 0, "", ""


class TestSyntheticNameDiscriminator:
    def test_counter_names_are_flagged(self):
        assert _is_synthetic_result_name("0000-result.json")
        assert _is_synthetic_result_name("0019-result.json")
        assert _is_synthetic_result_name("99-result.json")

    def test_uuid_names_are_not_flagged(self):
        assert not _is_synthetic_result_name("0d74b4de-79cc-4500-bcea-f5bb8356bef5-result.json")
        assert not _is_synthetic_result_name("0d74b4de-79cc-4500-bcea-f5bb8356bef5-container.json")
        assert not _is_synthetic_result_name("categories.json")


class TestDeduplication:

    def test_mixed_results_dedupe_to_real_count(self, tmp_path: Path):
        """20 real + 20 synthetic → after prepare only the 20 real remain."""
        from app.execution.allure_report_generator import AllureReportGenerator

        results = _result_dir(tmp_path)
        real = [
            "Smoke Test - Login Page Load @smoke @critical",
            "Happy Path - Valid Login @happy_path @critical",
            "Negative Test - Empty Username Only @negative @high",
        ]
        for name in real:
            _real_result(results, name)
        _synthetic_results(results, 3)

        gen = AllureReportGenerator()
        gen._prepare_results(results, _fallback_tests(6))

        remaining = sorted(p.name for p in results.glob("*-result.json"))
        assert len(remaining) == len(real)
        for name in real:
            assert any(name in r for r in remaining)
        assert not any(_is_synthetic_result_name(r) for r in remaining)

    def test_real_results_never_replaced_by_fallback(self, tmp_path: Path):
        from app.execution.allure_report_generator import AllureReportGenerator

        results = _result_dir(tmp_path)
        _real_result(results, "Happy Path - Valid Login", status="passed")
        gen = AllureReportGenerator()
        # Force_rebuild-style params must NOT replace real results.
        gen._prepare_results(results, _fallback_tests(20))

        remaining = list(results.glob("*-result.json"))
        assert len(remaining) == 1
        assert "Happy Path - Valid Login" in remaining[0].name

    def test_no_results_synthesizes_from_fallback(self, tmp_path: Path):
        from app.execution.allure_report_generator import AllureReportGenerator

        results = _result_dir(tmp_path)
        gen = AllureReportGenerator()
        gen._prepare_results(results, _fallback_tests(20))

        remaining = sorted(p.name for p in results.glob("*-result.json"))
        assert len(remaining) == 20
        assert all(_is_synthetic_result_name(r) for r in remaining)

    def test_generate_recovers_mixed_run_to_logical_count(self, tmp_path: Path):
        """Full generate() drops synthetic dupes and builds a valid report."""
        from app.execution.allure_report_generator import AllureReportGenerator

        results = _result_dir(tmp_path)
        output = tmp_path / "allure-report"
        real = ["Smoke Test - Login Page Load @smoke @critical",
                "Happy Path - Valid Login @happy_path @critical",
                "Negative Test - Empty Password Only @negative @high"]
        for name in real:
            _real_result(results, name)
        _synthetic_results(results, 3)

        gen = AllureReportGenerator()
        fake_run = _FakeRun(output)
        patcher_run = pytest.MonkeyPatch()
        patcher_run.setattr(gen, "_run_allure_command", fake_run)

        result = gen.generate(
            results_dir=results,
            output_path=output,
            fallback_test_results=_fallback_tests(6),
            force_rebuild=True,
        )
        patcher_run.undo()

        assert result["status"] == "generated"
        remaining = sorted(p.name for p in results.glob("*-result.json"))
        assert len(remaining) == len(real)  # 20 logical → 20 results, NOT 40
        assert output.joinpath("index.html").exists()

    def test_logical_count_not_inflated_by_fallback_attempts(self, tmp_path: Path):
        """20 logical tests → 20 synthetic result files (one per test), even when
        the parsed input describes retried/attempted tests."""
        from app.execution.allure_report_generator import AllureReportGenerator

        results = _result_dir(tmp_path)
        attempts = []
        for i in range(20):
            # Each logical test may have accrued 3 attempts in the parsed data.
            for _attempt in range(3):
                attempts.append({
                    "name": f"Test {i}",
                    "file": "tests/login-module.spec.ts",
                    "duration_ms": 100,
                    "status": "failed" if i else "passed",
                })
        assert len(attempts) == 60

        gen = AllureReportGenerator()
        gen._prepare_results(results, attempts)

        remaining = list(results.glob("*-result.json"))
        assert len(remaining) == 20  # attempts must not inflate logical count


class TestLongPathSafety:
    """Real run workspaces exceed Windows MAX_PATH; I/O must be long-path-safe."""

    def test_deep_path_real_results_are_detected_and_preserved(self, tmp_path: Path):
        import os

        if os.name != "nt":
            pytest.skip("long-path safety is a Windows concern")

        deep = tmp_path
        while len(str(deep)) < 300:
            deep = deep / "segment_of_nested_depth_0123456789"
        _long_path(deep).mkdir(parents=True, exist_ok=True)
        assert len(str(deep / "0d74b4de-79cc-4500-bcea-f5bb8356bef5-result.json")) > 260

        from app.execution.allure_report_generator import AllureReportGenerator

        _real_result(deep, "Happy Path - Valid Login", status="passed")
        _synthetic_results(deep, 1)

        gen = AllureReportGenerator()
        assert gen._has_valid_results(deep) is True, "long-path real result must be read as valid"
        gen._prepare_results(deep, _fallback_tests(5))

        remaining = sorted(p.name for p in _long_path(deep).glob("*-result.json"))
        assert len(remaining) == 1
        assert not _is_synthetic_result_name(remaining[0])
        assert "Happy Path - Valid Login" in remaining[0]

    def test_long_path_unlink_synthetic(self, tmp_path: Path):
        import os

        if os.name != "nt":
            pytest.skip("long-path safety is a Windows concern")

        from app.execution.allure_report_generator import AllureReportGenerator

        deep = tmp_path
        while len(str(deep)) < 300:
            deep = deep / "segment_of_nested_depth_0123456789"
        _long_path(deep).mkdir(parents=True, exist_ok=True)

        _synthetic_results(deep, 1)
        gen = AllureReportGenerator()
        removed = gen._remove_synthetic_results(deep)
        assert removed == 1
        assert not list(_long_path(deep).glob("*-result.json"))

    def test_helper_prefixes_only_on_windows(self, tmp_path: Path):
        import os

        p = _long_path(tmp_path)
        s = str(p)
        if os.name == "nt":
            assert s.startswith("\\\\?\\")
        else:
            assert not s.startswith("\\\\?\\")
