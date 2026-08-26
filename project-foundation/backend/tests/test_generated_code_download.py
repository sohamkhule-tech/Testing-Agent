"""
Tests for ``GET /api/v1/runs/{run_id}/generated-code/download``.

Verifies:
- A valid run downloads a ZIP of the COMPLETE generated project
- Generated files are present and the directory structure is preserved
- Invalid runs return 404
- Missing generated project returns 404
- Path traversal / symlink escape is impossible
- Secret files (.env, credential files, key blobs) are excluded
- A placeholder-only .env.example ships with the archive
"""

import io
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.workflow import _build_generated_code_zip
from app.dependencies import get_trigger_service
from app.main import app

client = TestClient(app)

RUN_ID = uuid4()
NONEXISTENT_RUN_ID = uuid4()

ARCHIVE_ROOT = "generated-tests/playwright"


class _FakeTriggerService:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    async def get_run(self, run_id: UUID):
        return SimpleNamespace(workspace_path=str(self.workspace))


def _project_dir(workspace: Path) -> Path:
    return workspace / "artifacts" / "generated-tests" / "playwright"


def _use_fake_workspace(workspace: Path) -> None:
    fake_service = _FakeTriggerService(workspace)
    app.dependency_overrides[get_trigger_service] = lambda: fake_service


def _clear_override() -> None:
    app.dependency_overrides.pop(get_trigger_service, None)


@pytest.fixture
def generated_run(tmp_path: Path):
    """Build a realistic generated Playwright project workspace."""
    workspace = tmp_path / "workspace"
    project = _project_dir(workspace)
    project.mkdir(parents=True)

    (project / "package.json").write_text('{"name": "playwright-tests"}', encoding="utf-8")
    (project / "playwright.config.ts").write_text("import { defineConfig } from '@playwright/test';", encoding="utf-8")
    (project / "tsconfig.json").write_text("{}", encoding="utf-8")
    (project / "README.md").write_text("# Tests", encoding="utf-8")
    (project / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (project / ".env.example").write_text(
        "BASE_URL=http://localhost:3000\nTEST_USERNAME=testuser\nTEST_PASSWORD=testpass123\n",
        encoding="utf-8",
    )
    # A REAL environment file with live credentials — must never ship.
    (project / ".env").write_text(
        "BASE_URL=http://localhost:3000\nTEST_USERNAME=admin\nTEST_PASSWORD=SuperSecret!2024\n",
        encoding="utf-8",
    )

    (project / "pages").mkdir(parents=True, exist_ok=True)
    (project / "tests").mkdir(parents=True, exist_ok=True)
    (project / "fixtures").mkdir(parents=True, exist_ok=True)
    (project / "utils").mkdir(parents=True, exist_ok=True)
    (project / "pages" / "LoginPage.ts").write_text("export class LoginPage {}", encoding="utf-8")
    (project / "tests" / "login.spec.ts").write_text("test('login', async () => {});", encoding="utf-8")
    (project / "fixtures" / "base.fixture.ts").write_text("export const fixture = {};", encoding="utf-8")
    (project / "utils" / "helpers.ts").write_text("export const wait = () => {};", encoding="utf-8")

    # Non-generated outputs that must be excluded.
    (project / "node_modules" / "some-pkg").mkdir(parents=True, exist_ok=True)
    (project / "node_modules" / "some-pkg" / "index.js").write_text("module.exports = 1;", encoding="utf-8")
    (project / "test-results").mkdir(parents=True, exist_ok=True)
    (project / "test-results" / "results.json").write_text("{}", encoding="utf-8")
    (project / "playwright-report").mkdir(parents=True, exist_ok=True)
    (project / "playwright-report" / "index.html").write_text("<html></html>", encoding="utf-8")

    # Files OUTSIDE the playwright project — must never leak into the archive.
    (workspace / "secret.txt").write_text("top secret", encoding="utf-8")
    (workspace / "artifacts" / "generated-tests" / "execution-artifacts" / "results.json").parent.mkdir(
        parents=True, exist_ok=True
    )
    (workspace / "artifacts" / "generated-tests" / "execution-artifacts" / "results.json").write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / "outside-workspace.txt").write_text("outside", encoding="utf-8")

    _use_fake_workspace(workspace)
    yield workspace
    _clear_override()


class TestEndpointRegistration:
    def test_generated_code_download_registered(self):
        paths = app.openapi()["paths"]
        assert "/api/v1/runs/{run_id}/generated-code/download" in paths

    def test_endpoint_has_summary_and_responses(self):
        details = app.openapi()["paths"]["/api/v1/runs/{run_id}/generated-code/download"]["get"]
        assert "summary" in details
        assert "200" in details["responses"]
        assert "404" in details["responses"]


class TestDownloadBehavior:
    def test_valid_run_returns_zip(self, generated_run: Path):
        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/zip")
        disposition = response.headers["content-disposition"]
        assert f"playwright-generated-code-{RUN_ID}.zip" in disposition
        assert response.content.startswith(b"PK")  # ZIP magic bytes

    def test_generated_files_present_in_zip(self, generated_run: Path):
        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        names = set(zipfile.ZipFile(io.BytesIO(response.content)).namelist())

        for expected in (
            f"{ARCHIVE_ROOT}/package.json",
            f"{ARCHIVE_ROOT}/playwright.config.ts",
            f"{ARCHIVE_ROOT}/tsconfig.json",
            f"{ARCHIVE_ROOT}/README.md",
            f"{ARCHIVE_ROOT}/.gitignore",
            f"{ARCHIVE_ROOT}/.env.example",
            f"{ARCHIVE_ROOT}/pages/LoginPage.ts",
            f"{ARCHIVE_ROOT}/tests/login.spec.ts",
            f"{ARCHIVE_ROOT}/fixtures/base.fixture.ts",
            f"{ARCHIVE_ROOT}/utils/helpers.ts",
        ):
            assert expected in names, f"missing {expected}"

    def test_directory_structure_preserved(self, generated_run: Path):
        """Every entry stays under generated-tests/playwright and keeps its tree."""
        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            names = zf.namelist()

        assert names
        for name in names:
            assert name.startswith(ARCHIVE_ROOT + "/"), f"entry escaped archive root: {name}"
            assert not name.startswith("/")
            assert name.split("/") not in ([".", ".."])

        assert f"{ARCHIVE_ROOT}/pages/LoginPage.ts" in names
        assert f"{ARCHIVE_ROOT}/tests/login.spec.ts" in names
        assert f"{ARCHIVE_ROOT}/fixtures/base.fixture.ts" in names

    def test_contents_matched_to_this_run_only(self, generated_run: Path, tmp_path: Path):
        """A second run's files never bleed into this run's archive."""
        other = tmp_path / "other-workspace"
        other_project = _project_dir(other)
        other_project.mkdir(parents=True)
        (other_project / "package.json").write_text('{"name":"OTHER_RUN"}', encoding="utf-8")

        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        names = set(zipfile.ZipFile(io.BytesIO(response.content)).namelist())
        assert f"{ARCHIVE_ROOT}/package.json" in names
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            assert '{"name":"OTHER_RUN"}' not in zf.read(f"{ARCHIVE_ROOT}/package.json").decode()

    def test_invalid_run_returns_404(self):
        _clear_override()
        response = client.get(f"/api/v1/runs/{NONEXISTENT_RUN_ID}/generated-code/download")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_missing_generated_project_returns_404(self, tmp_path: Path):
        workspace = tmp_path / "empty-workspace"
        workspace.mkdir(parents=True)
        _use_fake_workspace(workspace)
        try:
            response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
            assert response.status_code == 404
        finally:
            _clear_override()

    def test_empty_generated_project_returns_404(self, tmp_path: Path):
        workspace = tmp_path / "empty-project-workspace"
        _project_dir(workspace).mkdir(parents=True)
        _use_fake_workspace(workspace)
        try:
            response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
            assert response.status_code == 404
        finally:
            _clear_override()


class TestPathTraversalSafety:
    def test_outside_files_never_in_archive(self, generated_run: Path):
        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()

        joined = "\n".join(names)
        assert "secret.txt" not in joined
        assert "outside-workspace.txt" not in joined
        assert "execution-artifacts" not in joined
        assert ".." not in joined

    def test_absolute_or_traversal_paths_rejected(self, generated_run: Path):
        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
        for name in names:
            assert not os.path.isabs(name)
            assert ".." not in name.replace("\\", "/").split("/")

    def test_excluded_dirs_not_in_archive(self, generated_run: Path):
        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        joined = "\n".join(zipfile.ZipFile(io.BytesIO(response.content)).namelist())
        assert "node_modules" not in joined
        assert "test-results" not in joined
        assert "playwright-report" not in joined

    def test_symlink_escape_is_impossible(self, tmp_path: Path):
        project = _project_dir(tmp_path / "workspace")
        project.mkdir(parents=True)
        (project / "package.json").write_text("{}", encoding="utf-8")

        outside = tmp_path / "leaked.txt"
        outside.write_text("leaked secret", encoding="utf-8")

        link = project / "leak.txt"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform/filesystem")

        data = _build_generated_code_zip(project)
        assert data is not None
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert f"{ARCHIVE_ROOT}/leak.txt" not in names
        assert "leaked" not in "\n".join(names)


class TestSecretExclusion:
    def test_real_env_file_excluded_but_example_included(self, generated_run: Path):
        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        names = set(zipfile.ZipFile(io.BytesIO(response.content)).namelist())

        assert f"{ARCHIVE_ROOT}/.env" not in names
        assert f"{ARCHIVE_ROOT}/.env.example" in names

    def test_env_example_contains_placeholders_not_credentials(self, generated_run: Path):
        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            example = zf.read(f"{ARCHIVE_ROOT}/.env.example").decode("utf-8")

        assert "SuperSecret!2024" not in example
        assert "admin" not in example
        assert "TEST_PASSWORD" in example  # key names preserved

    def test_env_example_synthesized_when_missing(self, tmp_path: Path):
        workspace = tmp_path / "synth-workspace"
        project = _project_dir(workspace)
        project.mkdir(parents=True)
        (project / "package.json").write_text("{}", encoding="utf-8")
        # No .env.example — only a real .env with credentials.
        (project / ".env").write_text(
            "BASE_URL=http://example.com\nTEST_PASSWORD=hunter2secret\nOPENAI_API_KEY=sk-1234567890abcdefghijklmnopqrstuvwxyz\n",
            encoding="utf-8",
        )

        data = _build_generated_code_zip(project)
        assert data is not None
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            assert f"{ARCHIVE_ROOT}/.env.example" in names
            assert f"{ARCHIVE_ROOT}/.env" not in names
            example = zf.read(f"{ARCHIVE_ROOT}/.env.example").decode("utf-8")

        assert "hunter2secret" not in example
        # Key names preserved, values placeholder-only.
        assert "TEST_PASSWORD=<your-value>" in example
        assert "OPENAI_API_KEY=<your-value>" in example

    def test_secret_named_files_excluded(self, generated_run: Path):
        project = _project_dir(generated_run)
        (project / "secrets" / "app-secret.key").parent.mkdir(exist_ok=True)
        (project / "secrets" / "app-secret.key").write_text("-----BEGIN RSA PRIVATE KEY-----", encoding="utf-8")
        (project / "credentials.json").write_text('{"username":"x"}', encoding="utf-8")

        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        joined = "\n".join(zipfile.ZipFile(io.BytesIO(response.content)).namelist())
        assert "app-secret.key" not in joined
        assert "credentials.json" not in joined

    def test_secret_content_scan_excludes_key_blobs(self, tmp_path: Path):
        workspace = tmp_path / "key-workspace"
        project = _project_dir(workspace)
        project.mkdir(parents=True)
        (project / "package.json").write_text("{}", encoding="utf-8")
        (project / "utils").mkdir(parents=True, exist_ok=True)
        (project / "utils" / "leaky.ts").write_text(
            "const key = '-----BEGIN PRIVATE KEY-----\\nMIIE\\n-----END PRIVATE KEY-----';",
            encoding="utf-8",
        )

        data = _build_generated_code_zip(project)
        assert data is not None
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert f"{ARCHIVE_ROOT}/utils/leaky.ts" not in names

    def test_no_metadata_or_marker_files_shipped(self, generated_run: Path):
        project = _project_dir(generated_run)
        (project / "code-generation-metadata.json").write_text('{"internal":"x"}', encoding="utf-8")

        response = client.get(f"/api/v1/runs/{RUN_ID}/generated-code/download")
        joined = "\n".join(zipfile.ZipFile(io.BytesIO(response.content)).namelist())
        assert "code-generation-metadata.json" not in joined
