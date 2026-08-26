"""
Critical regression tests for execution false-positive prevention.

BACKGROUND:
A critical bug was discovered where unexecuted tests were reported as "passed"
when Playwright failed to execute. This created 100% pass rates for runs where
0 tests actually executed.

ROOT CAUSE:
The fallback parser in workflow.py hardcoded status="passed" when parsing
generated .spec.ts files after Playwright execution failed.

THESE TESTS MUST NEVER FAIL.
They protect against the most dangerous false-positive scenario in the platform.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.api.routes.workflow import _parse_test_results_from_folders


@pytest.mark.unit
class TestFalsePositivePrevention:
    """Critical tests ensuring unexecuted tests are NEVER reported as passed."""

    def test_unexecuted_tests_marked_as_not_executed_not_passed(self, temp_dir: Path):
        """
        CRITICAL TEST #1: Spec file existence must NEVER produce status="passed".
        
        When Playwright fails and produces no results.json, the fallback parser
        discovers test names from .spec.ts files for diagnostics. These tests
        were NEVER EXECUTED and must be marked "not_executed", NEVER "passed".
        """
        # Simulate generated project with spec file but no execution results
        pw_dir = temp_dir / "playwright"
        tests_dir = pw_dir / "tests"
        tests_dir.mkdir(parents=True)
        
        # Create a spec file with 3 tests
        spec_content = '''
test("Test 1: Valid login", async ({ page }) => {
  await expect(page).toHaveTitle("Dashboard");
});

test("Test 2: Invalid credentials", async ({ page }) => {
  await expect(errorMessage).toBeVisible();
});

test("Test 3: Empty fields", async ({ page }) => {
  await expect(validationError).toBeVisible();
});
'''
        (tests_dir / "login.spec.ts").write_text(spec_content)
        
        # Simulate empty test-results (Playwright never ran)
        test_results_dir = temp_dir / "test-results"
        test_results_dir.mkdir(parents=True)
        
        # Parse results using fallback
        results = _parse_test_results_from_folders(test_results_dir, pw_dir)
        
        # CRITICAL ASSERTIONS
        assert len(results) == 3, "Should discover 3 tests from spec file"
        
        for test in results:
            # THE MOST IMPORTANT ASSERTION IN THE ENTIRE TEST SUITE
            assert test["status"] != "passed", (
                f"CRITICAL BUG: Test '{test['name']}' marked as PASSED but was NEVER EXECUTED! "
                "This is a false positive that undermines all test validity."
            )
            
            assert test["status"] == "not_executed", (
                f"Test '{test['name']}' must be marked 'not_executed' when no execution results exist"
            )
            
            assert test["error"] is not None, (
                f"Test '{test['name']}' must have an error message explaining it wasn't executed"
            )
            
            assert "never actually run" in test["error"].lower() or "not executed" in test["error"].lower(), (
                f"Error message must clearly state test was not executed: {test['error']}"
            )
            
            assert test["duration"] is None, (
                f"Test '{test['name']}' must not have a fabricated duration"
            )

    def test_real_playwright_results_are_authoritative(self, temp_dir: Path):
        """
        CRITICAL TEST #2: When results.json exists, use ONLY those results.
        
        If Playwright actually executed and produced results.json, those statuses
        are authoritative. Do not override with fallback parsing.
        """
        pw_dir = temp_dir / "playwright"
        tests_dir = pw_dir / "tests"
        tests_dir.mkdir(parents=True)
        
        # Create spec file
        (tests_dir / "test.spec.ts").write_text(
            'test("Should fail", async ({ page }) => { });'
        )
        
        # Create REAL Playwright results.json
        test_results_dir = temp_dir / "test-results"
        test_results_dir.mkdir(parents=True)
        
        results_json = {
            "suites": [{
                "file": "tests/test.spec.ts",
                "specs": [{
                    "title": "Should fail",
                    "file": "tests/test.spec.ts",
                    "line": 1,
                    "tests": [{
                        "title": "Should fail",
                        "results": [{
                            "status": "failed",
                            "duration": 1234,
                            "error": {"message": "Assertion failed"}
                        }]
                    }]
                }]
            }]
        }
        
        import json
        (test_results_dir / "results.json").write_text(json.dumps(results_json))
        
        # Parse results
        results = _parse_test_results_from_folders(test_results_dir, pw_dir)
        
        # CRITICAL ASSERTIONS
        assert len(results) == 1
        assert results[0]["status"] == "failed", (
            "Real Playwright result must be preserved exactly"
        )
        assert results[0]["duration"] == 1234
        assert "Assertion failed" in str(results[0]["error"])
        
        # Must NOT have been overridden by spec file parser
        assert results[0]["status"] != "not_executed"
        assert results[0]["status"] != "passed"

    def test_zero_execution_does_not_produce_passed_tests(self, temp_dir: Path):
        """
        CRITICAL TEST #3: When 0 tests execute, 0 tests should be marked passed.
        
        This test represents the exact scenario from the audit:
        - Playwright return_code: -128 (infrastructure error)
        - Execution duration: ~0.008s
        - results.json: missing
        - 20 spec tests exist
        
        Expected: 0 passed, 20 not_executed
        """
        pw_dir = temp_dir / "playwright"
        tests_dir = pw_dir / "tests"
        tests_dir.mkdir(parents=True)
        
        # Create 20 tests exactly like the audit scenario
        spec_content = "\n".join([
            f'test("Test {i}: Login scenario", async ({{ page }}) => {{ }});'
            for i in range(1, 21)
        ])
        (tests_dir / "login-module.spec.ts").write_text(spec_content)
        
        # Simulate infrastructure failure (no results)
        test_results_dir = temp_dir / "test-results"
        test_results_dir.mkdir(parents=True)
        
        # Parse results
        results = _parse_test_results_from_folders(test_results_dir, pw_dir)
        
        # CRITICAL ASSERTIONS - The Audit Scenario
        assert len(results) == 20, "Should discover all 20 tests"
        
        passed_count = sum(1 for t in results if t["status"] == "passed")
        not_executed_count = sum(1 for t in results if t["status"] == "not_executed")
        
        assert passed_count == 0, (
            f"AUDIT BUG REPRODUCED: {passed_count}/20 tests marked as PASSED when 0 executed! "
            "This is the exact false-positive bug that was discovered in production."
        )
        
        assert not_executed_count == 20, (
            f"All 20 tests must be marked 'not_executed', got {not_executed_count}"
        )

    def test_mixed_results_not_overridden_by_fallback(self, temp_dir: Path):
        """
        CRITICAL TEST #4: Real results (10 passed, 5 failed, 5 skipped) must not
        become "20 passed" via fallback parsing.
        """
        pw_dir = temp_dir / "playwright"
        tests_dir = pw_dir / "tests"
        tests_dir.mkdir(parents=True)
        
        # Create 20 tests in spec file
        (tests_dir / "test.spec.ts").write_text("\n".join([
            f'test("Test {i}", async ({{ page }}) => {{ }});'
            for i in range(1, 21)
        ]))
        
        # Create REAL Playwright results with mixed statuses
        test_results_dir = temp_dir / "test-results"
        test_results_dir.mkdir(parents=True)
        
        import json
        
        def make_test(idx: int, status: str):
            return {
                "title": f"Test {idx}",
                "results": [{"status": status, "duration": 100}]
            }
        
        results_json = {
            "suites": [{
                "file": "tests/test.spec.ts",
                "specs": [{
                    "title": f"Test {i}",
                    "file": "tests/test.spec.ts",
                    "tests": [make_test(
                        i,
                        "passed" if i <= 10 else "failed" if i <= 15 else "skipped"
                    )]
                } for i in range(1, 21)]
            }]
        }
        
        (test_results_dir / "results.json").write_text(json.dumps(results_json))
        
        # Parse results
        results = _parse_test_results_from_folders(test_results_dir, pw_dir)
        
        # CRITICAL ASSERTIONS
        passed = [r for r in results if r["status"] == "passed"]
        failed = [r for r in results if r["status"] == "failed"]
        skipped = [r for r in results if r["status"] == "skipped"]
        
        assert len(passed) == 10, "Must preserve real passed count"
        assert len(failed) == 5, "Must preserve real failed count"
        assert len(skipped) == 5, "Must preserve real skipped count"
        
        # Must NOT be overridden by spec file fallback
        assert len(results) == 20
        assert not any(r["status"] == "not_executed" for r in results), (
            "Real results exist - must not use fallback status"
        )

    def test_infrastructure_failure_scenario_no_false_positives(self, temp_dir: Path):
        """
        CRITICAL TEST #5: Playwright process failure must never result in passed tests.
        
        Simulates:
        - return_code: -128 (infrastructure error)
        - No results.json
        - Generated tests exist
        
        Expected: All tests marked not_executed, ZERO passed
        """
        pw_dir = temp_dir / "playwright"
        tests_dir = pw_dir / "tests"
        tests_dir.mkdir(parents=True)
        
        # Multiple spec files
        for module in ["login", "dashboard", "settings"]:
            (tests_dir / f"{module}.spec.ts").write_text(
                f'test("{module} test", async ({{ page }}) => {{ }});'
            )
        
        # No results directory (Playwright failed to start)
        test_results_dir = temp_dir / "test-results"
        # Intentionally don't create the directory - simulates complete failure
        
        # Parse results
        results = _parse_test_results_from_folders(test_results_dir, pw_dir)
        
        # CRITICAL ASSERTIONS
        assert len(results) == 3, "Should discover 3 tests from spec files"
        
        for test in results:
            assert test["status"] == "not_executed", (
                f"Infrastructure failure must result in 'not_executed', not '{test['status']}'"
            )
            assert test["status"] != "passed", (
                "CRITICAL: Infrastructure failure produced passed test!"
            )

    def test_empty_results_json_triggers_fallback_correctly(self, temp_dir: Path):
        """
        CRITICAL TEST #6: Corrupted/empty results.json should fall back without
        marking tests as passed.
        """
        pw_dir = temp_dir / "playwright"
        tests_dir = pw_dir / "tests"
        tests_dir.mkdir(parents=True)
        
        (tests_dir / "test.spec.ts").write_text(
            'test("Example test", async ({ page }) => { });'
        )
        
        # Create empty/corrupted results.json
        test_results_dir = temp_dir / "test-results"
        test_results_dir.mkdir(parents=True)
        (test_results_dir / "results.json").write_text("{}")
        
        # Parse results
        results = _parse_test_results_from_folders(test_results_dir, pw_dir)
        
        # Should fall back to spec file parsing
        assert len(results) == 1
        assert results[0]["status"] == "not_executed", (
            "Empty results.json should trigger fallback with not_executed status"
        )
        assert results[0]["status"] != "passed"


@pytest.mark.unit
class TestAllureReportFalsePositivePrevention:
    """Ensure Allure report generator never creates synthetic passed results."""

    def test_allure_converts_not_executed_to_skipped(self):
        """
        Allure doesn't have a "not_executed" status, so it must be converted to
        "skipped" with a clear message, NEVER to "passed".
        """
        from app.execution.allure_report_generator import AllureReportGenerator
        from pathlib import Path
        import tempfile
        import json
        
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "allure-results"
            results_dir.mkdir()
            
            # Simulate not_executed tests
            not_executed_tests = [
                {
                    "name": "Test 1",
                    "file": "tests/test.spec.ts",
                    "status": "not_executed",
                    "duration": None,
                    "error": "Test was never executed",
                }
            ]
            
            generator = AllureReportGenerator()
            generator._write_fallback_results(results_dir, not_executed_tests)
            
            # Check generated Allure result
            result_files = list(results_dir.glob("*-result.json"))
            assert len(result_files) == 1
            
            with open(result_files[0]) as f:
                allure_result = json.load(f)
            
            # CRITICAL ASSERTIONS
            assert allure_result["status"] == "skipped", (
                f"not_executed must become 'skipped' in Allure, got '{allure_result['status']}'"
            )
            assert allure_result["status"] != "passed", (
                "CRITICAL: not_executed test marked as PASSED in Allure!"
            )
            
            # Must have clear message
            assert "statusDetails" in allure_result
            msg_lower = allure_result["statusDetails"]["message"].lower()
            assert "not executed" in msg_lower or "never executed" in msg_lower, (
                f"Status details must explain test was not executed: {allure_result['statusDetails']['message']}"
            )

    def test_allure_hooks_not_passed_for_unexecuted_tests(self):
        """
        Before Hooks and After Hooks must not show "passed" when test wasn't executed.
        """
        from app.execution.allure_report_generator import AllureReportGenerator
        from pathlib import Path
        import tempfile
        import json
        
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "allure-results"
            results_dir.mkdir()
            
            not_executed_tests = [{
                "name": "Unexecuted test",
                "file": "tests/test.spec.ts",
                "status": "not_executed",
                "duration": None,
                "error": "Not executed",
            }]
            
            generator = AllureReportGenerator()
            generator._write_fallback_results(results_dir, not_executed_tests)
            
            with open(list(results_dir.glob("*-result.json"))[0]) as f:
                result = json.load(f)
            
            # Check steps
            before_hook = next(s for s in result["steps"] if "Before" in s["name"])
            after_hook = next(s for s in result["steps"] if "After" in s["name"])
            
            assert before_hook["status"] != "passed", (
                "Before Hooks must not show 'passed' for unexecuted test"
            )
            assert after_hook["status"] != "passed", (
                "After Hooks must not show 'passed' for unexecuted test"
            )
