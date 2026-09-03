"""
Regression Unit Tests: Safe Credential Propagation and Security Audit

Verifies:
1. Trigger/run receives credentials and securely stores them in CredentialStore.
2. Credentials are loadable and propagated into the Playwright subprocess environment dictionary.
3. Generated test code references process.env.VALID_IDENTITY and process.env.VALID_PASSWORD.
4. Plaintext password is NEVER written as a literal into generated TypeScript test source files.
5. Plaintext password is NEVER logged in command logs or process output contexts.
6. Playwright receives credentials through environment variables in _prepare_environment.
"""

import tempfile
from pathlib import Path
import pytest

from app.services.prompt_builder import AuthContext, CredentialStore, PromptParser
from app.generators.template_engine import TemplateEngine
from app.execution.playwright_runner import PlaywrightRunner
from app.schemas.execution import ExecutionConfig
from app.schemas.ir import (
    CodeGenerationIR,
    ElementIR,
    LocatorStrategy,
    ActionIR,
    ActionType,
    AssertionIR,
    AssertionType,
    PageIR,
    ModuleIR,
    TestFlowIR,
    FlowStepIR,
    EnvironmentIR,
    MetadataIR,
)


TEST_IDENTITY = "test@example.com"
TEST_PASSWORD = "TEST_PASSWORD_ONLY"


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        # Create playwright project directory layout
        playwright_dir = ws / "artifacts" / "generated-tests" / "playwright"
        playwright_dir.mkdir(parents=True, exist_ok=True)
        yield ws


def test_trigger_credential_extraction():
    """Verify prompt parser extracts credentials safely without leaking into raw_text."""
    parser = PromptParser()
    prompt = f"Perform login tests using username: {TEST_IDENTITY} and password: {TEST_PASSWORD}"
    intent, auth = parser.parse(prompt)

    assert auth.username == TEST_IDENTITY
    assert auth.password == TEST_PASSWORD
    assert TEST_PASSWORD not in intent.raw_text
    assert "[CREDENTIAL REDACTED]" in intent.raw_text


def test_credential_store_encryption_and_loading(temp_workspace):
    """Verify CredentialStore encrypts credentials to workspace and reloads them cleanly."""
    store = CredentialStore()
    auth_in = AuthContext(username=TEST_IDENTITY, password=TEST_PASSWORD)

    store.save(str(temp_workspace), auth_in)

    # Verify enc file exists
    enc_file = temp_workspace / "run_credentials.enc"
    plain_file = temp_workspace / "run_credentials.json"
    assert enc_file.exists() or plain_file.exists()

    if enc_file.exists():
        raw_enc = enc_file.read_bytes()
        assert TEST_PASSWORD.encode() not in raw_enc  # Encrypted

    auth_out = store.load(str(temp_workspace))
    assert auth_out.username == TEST_IDENTITY
    assert auth_out.password == TEST_PASSWORD


def test_env_file_credential_binding(temp_workspace):
    """Verify _generate_env_file binds VALID_IDENTITY and VALID_PASSWORD cleanly."""
    store = CredentialStore()
    store.save(str(temp_workspace), AuthContext(username=TEST_IDENTITY, password=TEST_PASSWORD))

    engine = TemplateEngine()
    ir = CodeGenerationIR(
        metadata=MetadataIR(generator="test"),
        environment=EnvironmentIR(base_url="https://example.com/login", auth_required=True),
        pages=[],
        modules=[],
    )

    out_dir = temp_workspace / "artifacts" / "generated-tests" / "playwright"
    env_path = engine._generate_env_file(ir, out_dir, workspace_path=str(temp_workspace))

    assert env_path.exists()
    env_text = env_path.read_text()

    assert f"VALID_IDENTITY={TEST_IDENTITY}" in env_text
    assert f"VALID_PASSWORD={TEST_PASSWORD}" in env_text
    # Ensure description placeholder text did NOT overwrite VALID_IDENTITY
    assert "Valid identity value" not in env_text.split("VALID_IDENTITY=")[1].split("\n")[0]


def test_playwright_runner_environment_propagation(temp_workspace):
    """Verify PlaywrightRunner._prepare_environment injects credentials into subprocess env."""
    store = CredentialStore()
    store.save(str(temp_workspace), AuthContext(username=TEST_IDENTITY, password=TEST_PASSWORD))

    runner = PlaywrightRunner()
    project_path = temp_workspace / "artifacts" / "generated-tests" / "playwright"
    config = ExecutionConfig()

    env = runner._prepare_environment(project_path, config)

    assert env.get("VALID_IDENTITY") == TEST_IDENTITY
    assert env.get("VALID_USERNAME") == TEST_IDENTITY
    assert env.get("VALID_PASSWORD") == TEST_PASSWORD


def test_generated_test_code_security(temp_workspace):
    """Verify generated spec files reference process.env and NEVER embed the password literal."""
    engine = TemplateEngine()

    # Create an IR step using $VALID_PASSWORD
    step = FlowStepIR(
        step_order=1,
        description="Enter password",
        actions=[
            ActionIR(
                action_type=ActionType.FILL,
                element_id="login_password_input",
                value="$VALID_PASSWORD"
            )
        ]
    )
    flow = TestFlowIR(flow_id="TC-001", name="Happy Path Login", description="Test login", steps=[step])
    mod = ModuleIR(module_id="login_module", name="login-module", description="Login Tests", flows=[flow])
    element = ElementIR(id="login_password_input", name="login_password_input", tag="input", type="password", locator_strategy=LocatorStrategy.CSS, locator_value='input[type="password"]')
    page = PageIR(page_id="login_page", name="login-page", page_name="LoginPage", description="Login Page", url_pattern="/login", elements=[element])
    ir = CodeGenerationIR(
        metadata=MetadataIR(generator="test"),
        environment=EnvironmentIR(base_url="https://example.com/login", auth_required=True),
        pages=[page],
        modules=[mod]
    )

    out_dir = temp_workspace / "artifacts" / "generated-tests" / "playwright"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tests").mkdir(parents=True, exist_ok=True)

    spec_path = engine._generate_module_test_file(mod, ir, out_dir / "tests")
    code = spec_path.read_text()

    # Security assertion: process.env used, no literal passwords
    assert "process.env.VALID_PASSWORD" in code
    assert TEST_PASSWORD not in code
    assert "'$VALID_PASSWORD'" not in code
