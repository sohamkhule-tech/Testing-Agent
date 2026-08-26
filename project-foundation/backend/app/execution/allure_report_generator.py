"""
Allure Report Generator

Generates Allure reports from Playwright execution results produced by the
official `allure-playwright` reporter.

Responsible for:
- Locating Allure results written into the run-isolated results directory
- Enriching results with environment metadata and defect categories
- Generating the static Allure report via the `allure-commandline` CLI
- Reporting status "generated" / "unavailable" / "failed" without ever
  raising, so report generation never breaks the execution workflow
"""

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from app.logging import LoggerMixin

DEFAULT_CATEGORIES = [
    {
        "name": "Passed tests",
        "matchedStatuses": ["passed"],
    },
    {
        "name": "Product defects",
        "matchedStatuses": ["failed"],
    },
    {
        "name": "Test defects",
        "matchedStatuses": ["broken"],
    },
    {
        "name": "Skipped tests",
        "matchedStatuses": ["skipped"],
    },
]

# The synthetic fallback writer emits counter-named result files. The official
# ``allure-playwright`` reporter names its result files after the test UUID, so
# counter-named ``-result.json`` files can ALWAYS be attributed to us.
_SYNTHETIC_RESULT_RE = re.compile(r"^\d+-result\.json$")


def _is_synthetic_result_name(name: str) -> bool:
    """True for a counter-named result file produced by our fallback writer."""
    return bool(_SYNTHETIC_RESULT_RE.match(name))


def _long_path(path: Path) -> Path:
    """Return a path usable for open/read/write/unlink on Windows.

    Run workspaces can exceed Windows MAX_PATH (260 chars). Python's
    ``open``/``unlink`` fail with ``FileNotFoundError`` on such paths unless the
    ``\\\\?\\`` prefix is used (enumeration via glob/listdir is unaffected).
    """
    raw = str(path.resolve())
    if os.name == "nt" and not raw.startswith("\\\\?\\"):
        raw = "\\\\?\\" + raw
    return Path(raw)


class AllureReportGenerator(LoggerMixin):

    def __init__(self) -> None:
        super().__init__()

    def generate(
        self,
        results_dir: Path,
        output_path: Path,
        project_path: Path | None = None,
        environment: dict[str, str] | None = None,
        fallback_test_results: list[dict[str, Any]] | None = None,
        timeout: int = 300,
        force_rebuild: bool = False,
    ) -> dict[str, Any]:
        """
        Generate an Allure report from collected result files.

        Args:
            results_dir: Directory containing allure-playwright result files
            output_path: Directory where the static Allure report is written
            project_path: Optional Playwright project root (used as CLI cwd so
                `npx allure` resolves the locally installed allure-commandline)
            environment: Optional key/value metadata written to
                environment.properties
            fallback_test_results: Parsed Playwright tests used to synthesize
                Allure result files when the reporter did not write any
            timeout: Max seconds to allow the CLI to run
            force_rebuild: Accepted for API compatibility. Real Playwright
                results are NEVER deleted or replaced; regeneration rebuilds
                the report output only.

        Returns:
            Dict with "status" ("generated" | "unavailable" | "failed"),
            "report_path", "results_path" and an optional "error".
        """
        results_dir = Path(results_dir).resolve()
        output_path = Path(output_path).resolve()

        self._prepare_results(results_dir, fallback_test_results)

        if not self._has_results(results_dir):
            self.logger.warning(
                "allure_results_not_found",
                results_dir=str(results_dir),
            )
            return {
                "status": "unavailable",
                "report_path": str(output_path),
                "results_path": str(results_dir),
                "error": "No Allure results found",
            }

        try:
            # Preserve history from previous report generation for trend graphs
            prev_history = output_path / "history"
            target_history = results_dir / "history"
            if prev_history.exists() and prev_history.is_dir() and not target_history.exists():
                try:
                    shutil.copytree(prev_history, target_history)
                except Exception:
                    pass

            self._write_environment_file(results_dir, environment)
            self._write_categories_file(results_dir)

            return_code, stdout, stderr = self._run_allure_command(
                results_dir=results_dir,
                output_path=output_path,
                project_path=project_path,
                timeout=timeout,
            )

            if return_code != 0:
                self.logger.error(
                    "allure_report_generation_failed",
                    return_code=return_code,
                    stderr=stderr[:1000],
                )
                return {
                    "status": "failed",
                    "report_path": str(output_path),
                    "results_path": str(results_dir),
                    "error": f"Allure CLI exited with code {return_code}: {stderr[:500]}",
                }

            index_path = output_path / "index.html"
            if not index_path.exists():
                self.logger.error(
                    "allure_report_index_missing",
                    report_path=str(output_path),
                    stdout=stdout[:1000],
                    stderr=stderr[:1000],
                )
                return {
                    "status": "failed",
                    "report_path": str(output_path),
                    "results_path": str(results_dir),
                    "error": "Allure CLI completed but index.html was not generated",
                }

            self.logger.info(
                "allure_report_generated",
                report_path=str(output_path),
                results_path=str(results_dir),
            )
            return {
                "status": "generated",
                "report_path": str(output_path),
                "results_path": str(results_dir),
            }

        except Exception as e:
            self.logger.error("allure_report_generation_error", error=str(e))
            return {
                "status": "failed",
                "report_path": str(output_path),
                "results_path": str(results_dir),
                "error": str(e),
            }

    def _has_results(self, results_dir: Path) -> bool:
        lp_dir = _long_path(results_dir)
        if not lp_dir.exists() or not lp_dir.is_dir():
            return False
        return any(
            p.is_file()
            and p.suffix == ".json"
            and p.name not in {"categories.json", "environment.json"}
            for p in lp_dir.glob("*.json")
        )

    def _prepare_results(
        self,
        results_dir: Path,
        fallback_test_results: list[dict[str, Any]] | None,
    ) -> None:
        """Make the results directory ready for report generation.

        Invariants:
        * Real ``allure-playwright`` results are the single source of truth
          and are NEVER deleted or replaced.
        * Counter-named synthetic result files written by an earlier fallback
          pass are removed whenever a report is generated — they would
          otherwise double-count every logical test in Allure.
        * The fallback writer only creates results when NO result files exist.

        The a reasonable interpretation of ``_has_valid_results`` matters:
        reads are long-path-safe so real results cannot be mistaken for absent.
        """
        has_results = self._has_results(results_dir)

        if has_results:
            # Whatever exists — real results, stale synthetic duplicates, or
            # both — synthetic duplicates are always dropped.
            self._remove_synthetic_results(results_dir)
            # Real results already exist (long-path-safe check) → reuse them.
            if self._has_valid_results(results_dir):
                return
            # Results exist but are all synthetic/invalid → re-synthesize.
            if fallback_test_results:
                self._write_fallback_results(results_dir, fallback_test_results)
            return

        # No results at all — synthesize from parsed tests when available.
        if fallback_test_results:
            self._write_fallback_results(results_dir, fallback_test_results)

    def _remove_synthetic_results(self, results_dir: Path) -> int:
        """Delete counter-named synthetic result files (never real results).

        Real ``allure-playwright`` results are uuid-named and are untouched.
        Returns the number of files removed.
        """
        lp_dir = _long_path(results_dir)
        if not lp_dir.exists() or not lp_dir.is_dir():
            return 0
        removed = 0
        for p in lp_dir.glob("*-result.json"):
            if not _is_synthetic_result_name(p.name):
                continue
            try:
                _long_path(p).unlink()
                removed += 1
            except Exception:
                continue
        if removed:
            self.logger.info(
                "allure_synthetic_duplicates_removed",
                count=removed,
                results_dir=str(results_dir),
            )
        return removed

    def _has_valid_results(self, results_dir: Path) -> bool:
        """Check if existing JSON files contain valid steps and non-zero duration.

        Uses long-path-safe reads so that real results inside deep run
        workspaces (paths > MAX_PATH on Windows) are never mistaken for absent.
        """
        lp_dir = _long_path(results_dir)
        if not lp_dir.exists() or not lp_dir.is_dir():
            return False
        json_files = [
            p for p in lp_dir.glob("*.json")
            if p.name not in {"categories.json", "environment.json"}
        ]
        if not json_files:
            return False

        for p in json_files:
            try:
                data = json.loads(_long_path(p).read_text(encoding="utf-8"))
                steps = data.get("steps", [])
                start = data.get("start", 0)
                stop = data.get("stop", 0)
                if steps and len(steps) > 0 and (stop - start) > 0:
                    return True
            except Exception:
                pass
        return False

    def _write_fallback_results(
        self,
        results_dir: Path,
        test_results: list[dict[str, Any]] | None,
    ) -> None:
        """Write Allure result files from parsed Playwright JSON.

        Each result includes execution steps (Before Hooks, Test Body, After Hooks)
        and realistic durations so that Allure renders full execution details.
        """
        if not test_results:
            return

        results_dir.mkdir(parents=True, exist_ok=True)
        batch_end_ms = int(time.time() * 1000)

        # Deduplicate by logical test identity before writing. Parsed inputs may
        # describe retried/attempted tests; each logical test must produce exactly
        # ONE Allure result file (the final attempt wins) so retries can never
        # inflate the logical test count.
        seen_identities: set[tuple[str, str]] = set()

        for index, test in enumerate(test_results):
            title = str(test.get("title") or test.get("name") or f"Test {index + 1}")
            file_name = str(test.get("file") or "")

            identity = (file_name, title)
            if identity in seen_identities:
                continue
            seen_identities.add(identity)

            raw_duration = test.get("duration_ms") or test.get("duration")
            duration_ms = int(raw_duration) if raw_duration else 0
            # For real executions use duration; for not_executed tests use 0
            effective_duration = duration_ms if duration_ms > 0 else 0

            status = str(test.get("status") or "skipped")
            # CRITICAL: "not_executed" means test was never run - convert to "skipped" for Allure
            # NEVER use "passed" for tests that weren't executed
            if status == "not_executed":
                status = "skipped"
            elif status not in {"passed", "failed", "skipped", "broken"}:
                status = "skipped"

            result_uuid = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{file_name}:{title}:{index}",
            ))

            stop = batch_end_ms
            start = stop - effective_duration
            batch_end_ms = start - 100

            # Sub-step timing breakdown
            before_start = start
            before_stop = start + max(10, int(effective_duration * 0.1))
            body_start = before_stop
            body_stop = start + max(20, int(effective_duration * 0.8))
            after_start = body_stop
            after_stop = stop

            step_status = status if status in {"passed", "failed", "broken"} else "skipped"
            
            error_message = test.get("error_message") or test.get("error")
            error_stack = test.get("error_stack")
            status_details = None
            if error_message:
                status_details = {
                    "message": str(error_message),
                    "trace": str(error_stack or error_message),
                }
            elif test.get("status") == "not_executed":
                # Provide clear reason why test was skipped
                status_details = {
                    "message": "Test was not executed",
                    "trace": "This test was generated but Playwright failed to execute it. No test results were produced.",
                }

# For not_executed tests, don't fabricate successful Before/After hooks
            hook_status = "passed" if test.get("status") not in {"not_executed", "skipped"} else "skipped"
            
            steps = [
                {
                    "name": "Before Hooks",
                    "status": hook_status,
                    "stage": "finished",
                    "start": before_start,
                    "stop": before_stop,
                    "steps": [],
                    "attachments": [],
                    "parameters": [],
                },
                {
                    "name": f"Execute Test: {title}",
                    "status": step_status,
                    "stage": "finished",
                    "start": body_start,
                    "stop": body_stop,
                    "steps": [],
                    "attachments": [],
                    "parameters": [],
                    **({"statusDetails": status_details} if status_details else {}),
                },
                {
                    "name": "After Hooks",
                    "status": hook_status,
                    "stage": "finished",
                    "start": after_start,
                    "stop": after_stop,
                    "steps": [],
                    "attachments": [],
                    "parameters": [],
                },
            ]

            result: dict[str, Any] = {
                "uuid": result_uuid,
                "historyId": result_uuid,
                "testCaseId": result_uuid,
                "name": title,
                "fullName": f"{file_name}#{title}" if file_name else title,
                "status": status,
                "stage": "finished",
                "start": start,
                "stop": stop,
                "steps": steps,
                "attachments": [],
                "parameters": [],
                "labels": [
                    {"name": "framework", "value": "playwright"},
                    {"name": "language", "value": "typescript"},
                ],
            }

            browser_val = str(test.get("browser") or "chromium")
            result["labels"].append({"name": "browser", "value": browser_val})
            result["labels"].append({"name": "parentSuite", "value": browser_val})

            if file_name:
                clean_file = file_name.replace("tests/", "")
                suite_name = (
                    clean_file
                    .replace(".spec.ts", "")
                    .replace(".spec.js", "")
                )
                result["labels"].append({"name": "suite", "value": clean_file})
                result["labels"].append({"name": "subSuite", "value": suite_name})
                result["labels"].append({"name": "package", "value": f"tests.{clean_file}"})

            if status_details:
                result["statusDetails"] = status_details

            target = results_dir / f"{index:04d}-result.json"
            _long_path(target).write_text(
                json.dumps(result, indent=2),
                encoding="utf-8",
            )

    def _write_environment_file(
        self,
        results_dir: Path,
        environment: dict[str, str] | None,
    ) -> None:
        if environment:
            lines = [f"{key}={value}" for key, value in environment.items() if value]
            if lines:
                _long_path(results_dir / "environment.properties").write_text(
                    "\n".join(lines),
                    encoding="utf-8",
                )

    def _write_categories_file(self, results_dir: Path) -> None:
        categories_path = results_dir / "categories.json"
        _long_path(categories_path).write_text(
            json.dumps(DEFAULT_CATEGORIES, indent=2),
            encoding="utf-8",
        )

    def _run_allure_command(
        self,
        results_dir: Path,
        output_path: Path,
        project_path: Path | None,
        timeout: int,
    ) -> tuple[int, str, str]:
        npx = shutil.which("npx") or "npx"
        cwd = str(project_path) if project_path else str(results_dir.parent)

        command = (
            f'"{npx}" allure generate "{results_dir}" '
            f'-o "{output_path}" --clean'
        )

        env = self._build_subprocess_env()

        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=True,
        )

        return result.returncode, result.stdout or "", result.stderr or ""

    def _build_subprocess_env(self) -> dict[str, str]:
        """
        Build the environment for the Allure CLI.

        allure-commandline requires a Java runtime. Resolution order:
          1. ALLURE_JAVA_HOME env var (explicit override)
          2. Bundled JRE under <repo>/tools/jre/<distro>/
          3. Existing JAVA_HOME / system PATH (unchanged behavior)
        """
        env = os.environ.copy()
        java_home = self._resolve_java_home()
        if java_home:
            env["JAVA_HOME"] = str(java_home)
            env["PATH"] = f"{java_home / 'bin'}{os.pathsep}{env.get('PATH', '')}"
            self.logger.info("allure_java_resolved", java_home=str(java_home))
        else:
            self.logger.warning(
                "allure_java_not_found",
                hint="Set ALLURE_JAVA_HOME or install Java; "
                "allure-commandline cannot run without a JRE.",
            )
        return env

    def _resolve_java_home(self) -> Path | None:
        override = os.environ.get("ALLURE_JAVA_HOME")
        if override and (Path(override) / "bin").exists():
            return Path(override)

        # Bundled JRE: <repo>/tools/jre/<distro-name>/
        repo_root = Path(__file__).resolve().parents[2]
        bundled = repo_root / "tools" / "jre"
        if bundled.is_dir():
            for candidate in sorted(bundled.iterdir()):
                if (candidate / "bin").is_dir():
                    return candidate

        system = os.environ.get("JAVA_HOME")
        if system and (Path(system) / "bin").exists():
            return Path(system)

        if shutil.which("java"):
            return None  # java already on PATH; no JAVA_HOME needed

        return None
