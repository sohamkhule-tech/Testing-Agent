"""E2E verification driver for the Allure fix (Phase 9).

Generates a real project via the fixed TemplateEngine, installs deps,
executes Playwright with the fixed runner, and generates the Allure report.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))

RUN_ID = "9c2d968d-6cc3-4523-b194-8c6a078ab0ec"
BASE = Path(__file__).resolve().parent.parent / "storage" / "runs" / RUN_ID / "artifacts" / "generated-tests"
PROJECT = BASE / "playwright"


def make_ir():
    """Minimal IR matching the schema used by TemplateEngine."""
    from app.schemas.ir import (
        ActionIR, AssertionIR, ElementIR, EnvironmentIR, FlowStepIR,
        LocatorStrategy, MetadataIR, ModuleIR, NavigationIR, PageIR,
        TestFlowIR, CodeGenerationIR, AssertionType, ActionType,
    )

    el = ElementIR(
        id="email-input",
        name="Email Input",
        locator_strategy=LocatorStrategy.CSS,
        locator_value="body",
    )
    page = PageIR(
        page_id="login-page",
        name="Login Page",
        description="Login page",
        elements=[el],
    )
    flow = TestFlowIR(
        flow_id="login-smoke",
        name="login smoke test",
        description="verify login page loads",
        steps=[
            FlowStepIR(
                step_order=1,
                description="open page",
                navigation=NavigationIR(target="https://example.com"),
            ),
            FlowStepIR(
                step_order=2,
                description="email visible",
                assertions=[AssertionIR(
                    step_order=2,
                    assertion_type=AssertionType.VISIBLE,
                    element_id="email-input",
                    description="email visible",
                )],
            ),
        ],
    )
    module = ModuleIR(
        module_id="login-module",
        name="Login Module",
        description="Login module",
        pages=["login-page"],
        flows=[flow],
    )
    return CodeGenerationIR(
        metadata=MetadataIR(generator="verify_allure_e2e"),
        environment=EnvironmentIR(base_url="https://example.com", browsers=["chromium"]),
        pages=[page],
        modules=[module],
    )


async def main() -> None:
    from app.generators.template_engine import TemplateEngine
    from app.execution.allure_report_generator import AllureReportGenerator
    from app.execution.playwright_runner import PlaywrightRunner
    from app.schemas.execution import ExecutionConfig

    print("=== STEP 1: generate project via fixed TemplateEngine ===")
    engine = TemplateEngine(run_id=RUN_ID)
    files = engine.generate_project(make_ir(), PROJECT)
    pkg = json.loads((PROJECT / "package.json").read_text(encoding="utf-8"))
    assert "allure-playwright" in pkg["devDependencies"], "allure-playwright missing!"
    assert "allure-commandline" in pkg["devDependencies"], "allure-commandline missing!"
    cfg = (PROJECT / "playwright.config.ts").read_text(encoding="utf-8")
    assert "'allure-playwright'" in cfg and "ALLURE_RESULTS_DIR" in cfg
    print(f"OK: {len(files)} files generated; allure deps + reporter present")

    print("=== STEP 2: npm install (real) ===")
    import subprocess
    r = subprocess.run(["npm", "install"], cwd=PROJECT, shell=True,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("npm install failed")
    for dep in ["allure-playwright", "allure-commandline"]:
        assert (PROJECT / "node_modules" / dep).exists(), f"{dep} not installed!"
        version = json.loads((PROJECT / "node_modules" / dep / "package.json").read_text(encoding="utf-8"))["version"]
        print(f"OK: node_modules/{dep} installed, version {version}")

    print("=== STEP 3: execute via fixed PlaywrightRunner ===")
    runner = PlaywrightRunner()
    config = ExecutionConfig(browser=None, headless=True)
    # browser=None -> BrowserType.ALL? force chromium only for speed
    from app.schemas.execution import BrowserType
    config.browser = BrowserType.CHROMIUM
    result = await runner.run_tests(project_path=PROJECT, config=config)
    print(f"playwright exit code: {result['return_code']}")
    print(f"tests parsed: {result['test_results']['summary']}")
    allure_results = PROJECT / "allure-results"
    result_files = list(allure_results.glob("*.json")) if allure_results.exists() else []
    print(f"allure-results exists: {allure_results.exists()}, json files: {len(result_files)}")
    if not result_files:
        print("STDOUT tail:", result["stdout"][-1500:])
        print("STDERR tail:", result["stderr"][-1500:])
        raise SystemExit("no allure results produced")

    print("=== STEP 4: generate Allure report ===")
    gen = AllureReportGenerator()
    report = gen.generate(
        results_dir=allure_results,
        output_path=BASE / "execution-artifacts" / "reports" / "allure-report",
        project_path=PROJECT,
        environment={"Base URL": "https://example.com"},
    )
    print(f"generator status: {report['status']} error: {report.get('error')}")
    index_html = BASE / "execution-artifacts" / "reports" / "allure-report" / "index.html"
    print(f"index.html exists: {index_html.exists()}")

    if report["status"] != "generated" or not index_html.exists():
        raise SystemExit("report generation failed")

    print("=== E2E FILESYSTEM VERIFICATION PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
