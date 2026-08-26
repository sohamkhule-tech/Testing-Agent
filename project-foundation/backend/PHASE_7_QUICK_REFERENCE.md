# Phase 7 - Quick Reference Guide

## Quick Start

### Running Code Generation

```bash
# Phase 7 is automatically invoked in the workflow after Human Review
# The workflow will:
# 1. Load approved-test-plan.json
# 2. Generate complete Playwright project
# 3. Validate generated code
# 4. Save to artifacts/generated-tests/playwright/
```

### Generated Project Usage

```bash
# Navigate to generated project
cd artifacts/generated-tests/playwright/

# Install dependencies
npm install

# Install Playwright browsers
npx playwright install

# Run all tests
npm test

# Run in headed mode
npm run test:headed

# Run specific browser
npm run test:chrome
npm run test:firefox
npm run test:webkit

# View report
npm run report

# Debug mode
npm run test:debug
```

---

## File Structure Reference

### Configuration Files
- `package.json` - npm dependencies and scripts
- `playwright.config.ts` - Playwright configuration (browsers, retries, reporters)
- `tsconfig.json` - TypeScript strict configuration
- `.env.example` - Environment variables template (copy to `.env`)
- `.gitignore` - Git ignore rules

### Code Files
- `pages/BasePage.ts` - Base page class (extend this for all pages)
- `pages/[Module]Page.ts` - Module-specific page objects
- `tests/[module].spec.ts` - Test specifications per module
- `fixtures/base.fixture.ts` - Base fixtures
- `fixtures/auth.fixture.ts` - Authentication fixture (if auth required)
- `utils/waits.ts` - Wait utilities
- `utils/helpers.ts` - Helper functions
- `utils/constants.ts` - Shared constants
- `utils/logger.ts` - Logging utility
- `data/test-data.json` - Test data

### Empty Directories (Generated at Runtime)
- `reports/` - HTML/JSON/JUnit reports
- `screenshots/` - Screenshots on failure
- `traces/` - Playwright traces
- `test-results/` - Test execution results

---

## Component API Reference

### CodeGenerationAgent

```python
from app.agents import CodeGenerationAgent
from app.llm import OpenAIClient

llm_client = OpenAIClient()
agent = CodeGenerationAgent(llm_client)

result = await agent.execute({
    "run_id": "abc-123",
    "workspace_path": "/path/to/workspace",
    "approved_test_plan_path": "/path/to/approved-test-plan.json",
    "base_url": "http://localhost:3000",  # Optional
    "overwrite": True,  # Optional
})

# Result contains:
# - status: Generation status
# - project_path: Path to generated project
# - files_generated: Number of files created
# - page_objects_count: Number of page objects
# - test_files_count: Number of test files
# - scenarios_implemented: Number of scenarios
# - validation_status: Validation result
# - duration_seconds: Generation time
```

### CodeGenerationService

```python
from app.services import CodeGenerationService
from app.llm import OpenAIClient

llm_client = OpenAIClient()
service = CodeGenerationService(llm_client)
await service.initialize()

summary = await service.generate_tests(
    run_id="abc-123",
    workspace_path="/path/to/workspace",
    base_url="http://localhost:3000",
)

# Validate inputs before generation
is_valid, errors = await service.validate_generation_input(workspace_path)

# Check generation status
status = await service.get_generation_status(workspace_path)
```

### PromptBuilder

```python
from app.core import PromptBuilder
from app.schemas.review import ApprovedTestPlan

builder = PromptBuilder()

# Build complete generation prompt
prompt = builder.build_generation_prompt(
    approved_plan=approved_plan,
    base_url="http://localhost:3000"
)

# Build file-specific prompt
context = {"module_name": "Login", "scenarios": [...]}
prompt = builder.build_file_generation_prompt("page_object", context)
```

### TemplateManager

```python
from app.core import TemplateManager

manager = TemplateManager()

# Get templates
package_json = manager.get_package_json_template()
playwright_config = manager.get_playwright_config_template()
tsconfig = manager.get_tsconfig_template()
base_page = manager.get_base_page_template()
readme = manager.get_readme_template()

# Substitute variables
template = "Hello {name}"
result = manager.substitute_variables(template, {"name": "World"})
```

### ArtifactWriter

```python
from app.core import ArtifactWriter
from pathlib import Path

writer = ArtifactWriter()

# Create project structure
project_path = Path("/path/to/project")
writer.create_project_structure(project_path)

# Write files
writer.write_config_file(project_path, "package.json", content)
writer.write_page_object(project_path, "LoginPage", code)
writer.write_test_file(project_path, "login", code)
writer.write_fixture_file(project_path, "auth.fixture", code)
writer.write_utility_file(project_path, "helpers", code)
writer.write_data_file(project_path, "test-data.json", data_dict)
writer.write_documentation(project_path, "README.md", content)

# Write metadata
metadata_path = writer.write_metadata(project_path, metadata)

# Create .gitignore
writer.create_gitignore(project_path)
```

### CodeValidator

```python
from app.core import CodeValidator
from pathlib import Path

validator = CodeValidator()

# Validate project
project_path = Path("/path/to/project")
is_valid, issues = validator.validate_project(project_path)

# Check validation summary
summary = validator.get_validation_summary()
# Returns:
# {
#   "total_issues": 5,
#   "errors": 0,
#   "warnings": 5,
#   "info": 0,
#   "is_valid": True,
#   "issues": [...]
# }
```

### PlaywrightProjectGenerator

```python
from app.generators import PlaywrightProjectGenerator
from app.core import *

generator = PlaywrightProjectGenerator(
    llm_client=llm_client,
    template_manager=TemplateManager(),
    artifact_writer=ArtifactWriter(),
    code_validator=CodeValidator(),
    prompt_builder=PromptBuilder(),
)

project = await generator.generate_project(
    approved_plan=approved_plan,
    output_path=Path("/path/to/output"),
    base_url="http://localhost:3000",
    overwrite=False,
)

# Project contains:
# - project_path
# - page_objects list
# - test_files list
# - fixtures list
# - utilities list
# - metadata
# - status
```

---

## Workflow Integration

### Adding Code Generation to Workflow

```python
from app.agents import CodeGenerationAgent
from app.workflows import execute_platform_workflow

# Create agent
code_gen_agent = CodeGenerationAgent(llm_client)

# Execute workflow
result = await execute_platform_workflow(
    trigger_agent=trigger_agent,
    crawler_agent=crawler_agent,
    test_design_agent=test_design_agent,
    code_generation_agent=code_gen_agent,  # Pass agent
    request_data={"url": "https://example.com"},
)

# Access code generation results
print(result["code_generation_status"])
print(result["generated_project_path"])
print(result["page_objects_count"])
print(result["test_files_count"])
print(result["validation_status"])
```

### Workflow State Fields

Code generation updates `PlatformWorkflowState` with:
- `generated_project_path` - Path to generated project
- `generated_tests_path` - Path to tests directory
- `code_generation_metadata_path` - Path to metadata JSON
- `page_objects_count` - Number of page objects
- `test_files_count` - Number of test files
- `scenarios_implemented` - Scenarios converted to tests
- `code_generation_status` - Status (completed/failed)
- `code_generation_duration` - Generation time in seconds
- `validation_status` - Validation result (passed/failed)
- `validation_errors` - Number of validation errors
- `validation_warnings` - Number of warnings

---

## Customization

### Custom Templates

```python
class CustomTemplateManager(TemplateManager):
    def get_custom_template(self):
        return """
        // Your custom template here
        """

# Use in generator
generator = PlaywrightProjectGenerator(
    template_manager=CustomTemplateManager(),
    # ... other dependencies
)
```

### Custom Validation Rules

```python
class CustomCodeValidator(CodeValidator):
    def _custom_validation(self, project_path: Path) -> None:
        # Add custom validation logic
        pass
```

### Custom Prompt Building

```python
class CustomPromptBuilder(PromptBuilder):
    def _build_custom_section(self, data) -> str:
        # Add custom prompt sections
        return "Custom content"
```

---

## Error Handling

### Common Issues

**Issue**: Approved test plan not found
```python
# Ensure approved-test-plan.json exists in:
# - workspace/contracts/approved-test-plan.json
# - workspace/review/approved-test-plan.json
```

**Issue**: Validation errors
```python
# Check validation issues
is_valid, issues = validator.validate_project(project_path)
for issue in issues:
    if issue.severity == "error":
        print(f"{issue.file_path}: {issue.message}")
```

**Issue**: LLM generation failure
```python
# Agent handles gracefully and returns error in result
result = await agent.execute(input_data)
if result["status"] == "failed":
    print(f"Generation failed: {result.get('error')}")
```

---

## Best Practices

### 1. Always Validate Inputs
```python
service = CodeGenerationService(llm_client)
is_valid, errors = await service.validate_generation_input(workspace_path)
if not is_valid:
    print(f"Validation errors: {errors}")
    return
```

### 2. Check Validation Status
```python
if result["validation_errors"] > 0:
    print("Generated code has validation errors")
    # Review and fix issues
```

### 3. Review Generated Code
```bash
# Always review generated code before using
cd artifacts/generated-tests/playwright/
cat playwright.config.ts
cat pages/LoginPage.ts
cat tests/login.spec.ts
```

### 4. Customize Configuration
```bash
# Update .env for your application
cp .env.example .env
# Edit .env with actual values
```

### 5. Run Tests Locally First
```bash
npm test -- --project=chromium
# Verify tests pass before CI
```

---

## Troubleshooting

### No Page Objects Generated
- Check approved test plan has scenarios
- Verify scenarios have `module` field
- Check LLM response in logs

### Tests Not Found
- Verify tests/ directory has .spec.ts files
- Check test file naming (module-name.spec.ts)
- Ensure test files have `test()` definitions

### Import Errors
- Run `npm install` to install dependencies
- Check TypeScript compilation: `npx tsc --noEmit`
- Verify import paths in generated code

### Validation Warnings
- Review warnings in metadata JSON
- Most warnings are non-critical
- Fix errors before proceeding

---

## Testing

### Run Unit Tests
```bash
pytest tests/test_code_generation.py -v
```

### Test Components Individually
```python
# Test PromptBuilder
builder = PromptBuilder()
prompt = builder.build_generation_prompt(approved_plan)
assert "Playwright" in prompt

# Test TemplateManager
manager = TemplateManager()
template = manager.get_package_json_template()
assert "@playwright/test" in template

# Test ArtifactWriter
writer = ArtifactWriter()
writer.create_project_structure(Path("/tmp/test"))
assert Path("/tmp/test/pages").exists()

# Test CodeValidator
validator = CodeValidator()
is_valid, issues = validator.validate_project(project_path)
assert is_valid
```

---

## Performance Tips

1. **Generation Speed**
   - Typical: 30-60 seconds for 10-20 scenarios
   - LLM calls are the bottleneck
   - Consider caching for repeated generations

2. **Validation Speed**
   - Complete project validation: <5 seconds
   - Validates structure, syntax, imports
   - No TypeScript compilation

3. **File Writing**
   - All file I/O is synchronous
   - Average: <1 second for complete project
   - Uses UTF-8 encoding

---

## Metadata Reference

### code-generation-metadata.json

```json
{
  "generator": "CodeGenerationAgent",
  "model": "gpt-4",
  "timestamp": "2024-01-01T00:00:00Z",
  "duration_seconds": 45.2,
  "version": "1.0.0",
  "project_path": "/path/to/project",
  "files_generated": 18,
  "total_lines_of_code": 2500,
  "page_objects": [
    {
      "name": "LoginPage",
      "file_path": "pages/LoginPage.ts",
      "target_page": "/login",
      "locator_count": 5,
      "action_count": 3,
      "assertion_count": 2
    }
  ],
  "test_files": [
    {
      "name": "login.spec.ts",
      "file_path": "tests/login.spec.ts",
      "test_count": 3,
      "page_objects_used": ["LoginPage"],
      "scenarios_covered": ["login-001", "login-002"]
    }
  ],
  "fixture_count": 2,
  "utility_count": 4,
  "scenarios_implemented": 15,
  "modules_covered": ["Login", "Dashboard"],
  "validation_status": "passed",
  "validation_issues": [],
  "warnings": [],
  "approved_test_plan_path": "/path/to/approved-test-plan.json"
}
```

---

## Environment Configuration

### Required Environment Variables

```env
# Application URL
BASE_URL=http://localhost:3000

# Authentication (if required)
TEST_USERNAME=testuser
TEST_PASSWORD=password123

# Browser Settings
HEADLESS=true
BROWSER=chromium

# Timeouts
ACTION_TIMEOUT=15000
NAVIGATION_TIMEOUT=30000

# Test Configuration
PARALLEL_WORKERS=4
RETRIES=2
```

### Optional Environment Variables

```env
# Reporting
REPORT_OUTPUT=reports/
SCREENSHOT_ON_FAILURE=true
VIDEO_ON_FAILURE=true

# Debugging
DEBUG=true
SLOW_MO=100
```

---

## Integration Examples

### With FastAPI

```python
from fastapi import FastAPI, HTTPException
from app.agents import CodeGenerationAgent

app = FastAPI()

@app.post("/api/generate-tests")
async def generate_tests(request: GenerateTestsRequest):
    try:
        agent = CodeGenerationAgent(llm_client)
        result = await agent.execute({
            "run_id": request.run_id,
            "workspace_path": request.workspace_path,
            "approved_test_plan_path": request.approved_plan_path,
        })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### With CLI

```python
import click
from app.agents import CodeGenerationAgent

@click.command()
@click.option('--workspace', required=True)
@click.option('--base-url', default='http://localhost:3000')
async def generate(workspace, base_url):
    agent = CodeGenerationAgent(llm_client)
    result = await agent.execute({
        "run_id": str(uuid4()),
        "workspace_path": workspace,
        "approved_test_plan_path": f"{workspace}/contracts/approved-test-plan.json",
        "base_url": base_url,
    })
    click.echo(f"Generated {result['files_generated']} files")

if __name__ == '__main__':
    generate()
```

---

**Quick Reference Version**: 1.0  
**Phase**: 7 - Code Generation  
**Updated**: 2026-07-23
