"""
Pytest Configuration and Fixtures

Provides shared test fixtures and configuration.
"""

import asyncio
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.llm import OpenAIClient
from app.main import app
from app.prompts import PromptLoader
from app.storage import LocalArtifactStorage
from app.validation import ContractValidator


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_client() -> TestClient:
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture(scope="session")
def settings():
    """Get application settings."""
    return get_settings()


@pytest.fixture
async def storage() -> AsyncGenerator[LocalArtifactStorage, None]:
    """Create storage instance."""
    storage = LocalArtifactStorage()
    yield storage
    # Cleanup if needed


@pytest.fixture
async def validator() -> AsyncGenerator[ContractValidator, None]:
    """Create contract validator instance."""
    validator = ContractValidator()
    yield validator


@pytest.fixture
async def prompt_loader() -> AsyncGenerator[PromptLoader, None]:
    """Create prompt loader instance."""
    loader = PromptLoader()
    yield loader


@pytest.fixture
async def llm_client() -> AsyncGenerator[OpenAIClient, None]:
    """Create LLM client instance."""
    client = OpenAIClient()
    yield client


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create temporary directory for tests."""
    return tmp_path


@pytest.fixture
def sample_artifact_data() -> bytes:
    """Sample artifact data for testing."""
    return b'{"test": "data", "value": 123}'


@pytest.fixture
def sample_contract_data() -> dict:
    """Sample contract data for testing."""
    return {
        "$schema": "test-case",
        "test_id": "test-001",
        "name": "Sample Test",
        "steps": [],
    }


# Markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "requires_api_key: Tests requiring API key")
