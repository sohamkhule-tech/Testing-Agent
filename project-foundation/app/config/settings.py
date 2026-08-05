"""
Application Configuration Module

Provides centralized configuration management using Pydantic Settings.
Supports environment-based configuration with validation.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application-level settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="AI-Testing-Platform", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    environment: Literal["development", "testing", "staging", "production"] = Field(
        default="development", description="Environment"
    )
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Log level")

    # API
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_workers: int = Field(default=4, description="Number of workers")
    api_reload: bool = Field(default=False, description="Auto-reload on code changes")

    # Security
    secret_key: str = Field(default="change-me-in-production", description="Secret key")
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000"], description="CORS allowed origins"
    )
    api_key_header: str = Field(default="X-API-Key", description="API key header name")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated origins string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


class LLMSettings(BaseSettings):
    """LLM Provider settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI / Ollama
    openai_api_key: str = Field(default="", description="OpenAI API key (use 'ollama' for local Ollama)")
    openai_base_url: str | None = Field(default=None, description="Custom base URL (e.g. http://localhost:11434/v1 for Ollama)")
    openai_model: str = Field(default="gpt-4", description="Model name (e.g. llama3, mistral for Ollama)")
    openai_temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperature")
    openai_max_tokens: int = Field(default=4096, gt=0, description="Max tokens")
    openai_timeout: int = Field(default=900, gt=0, description="Request timeout")

    # Provider
    llm_provider: Literal["openai", "ollama", "azure", "anthropic"] = Field(
        default="openai", description="LLM provider"
    )
    llm_retry_attempts: int = Field(default=3, ge=1, description="Retry attempts")
    llm_retry_delay: int = Field(default=2, ge=1, description="Retry delay in seconds")
    llm_max_concurrent: int = Field(default=10, ge=1, description="Max concurrent requests")


class StorageSettings(BaseSettings):
    """Storage configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    storage_type: Literal["local", "s3", "azure"] = Field(
        default="local", description="Storage type"
    )
    storage_base_path: Path = Field(default=Path("./storage"), description="Base storage path")
    artifacts_path: Path = Field(
        default=Path("./storage/artifacts"), description="Artifacts path"
    )
    logs_path: Path = Field(default=Path("./storage/logs"), description="Logs path")
    temp_path: Path = Field(default=Path("./storage/temp"), description="Temp path")

    # Artifact settings
    artifact_max_size_mb: int = Field(default=100, gt=0, description="Max artifact size in MB")
    artifact_retention_days: int = Field(default=30, gt=0, description="Retention period")
    artifact_compression: bool = Field(default=True, description="Enable compression")

    @field_validator("storage_base_path", "artifacts_path", "logs_path", "temp_path", mode="after")
    @classmethod
    def create_directories(cls, v: Path) -> Path:
        """Ensure directories exist."""
        v.mkdir(parents=True, exist_ok=True)
        return v


class PlaywrightSettings(BaseSettings):
    """Playwright configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    playwright_browser: Literal["chromium", "firefox", "webkit"] = Field(
        default="chromium", description="Browser type"
    )
    playwright_headless: bool = Field(default=True, description="Headless mode")
    playwright_timeout: int = Field(default=30000, gt=0, description="Default timeout (ms)")
    playwright_viewport_width: int = Field(default=1920, gt=0, description="Viewport width")
    playwright_viewport_height: int = Field(default=1080, gt=0, description="Viewport height")


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    log_format: Literal["json", "text"] = Field(default="json", description="Log format")
    log_file_enabled: bool = Field(default=True, description="Enable file logging")
    log_file_rotation: str = Field(default="10MB", description="Log file rotation size")
    log_file_retention: int = Field(default=30, description="Log retention days")
    log_correlation_enabled: bool = Field(default=True, description="Enable correlation IDs")


class ContractSettings(BaseSettings):
    """Contract validation settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    contract_validation_enabled: bool = Field(default=True, description="Enable validation")
    contract_schema_path: Path = Field(default=Path("./contracts"), description="Schema path")
    contract_strict_mode: bool = Field(default=True, description="Strict validation mode")

    @field_validator("contract_schema_path", mode="after")
    @classmethod
    def create_schema_directory(cls, v: Path) -> Path:
        """Ensure schema directory exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="DATABASE_",
    )

    url: str = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/testing_platform",
        description="Database connection URL",
    )
    pool_size: int = Field(default=10, ge=1, description="Connection pool size")
    max_overflow: int = Field(default=20, ge=0, description="Maximum pool overflow connections")
    echo: bool = Field(default=False, description="Echo SQL statements")
    connect_timeout: int = Field(default=10, ge=1, le=60, description="Connection timeout in seconds")


class PersistenceSettings(BaseSettings):
    """Persistence feature flags and configuration.

    All flags default to ``False`` so the application continues
    operating exactly as before (filesystem-only).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="PERSISTENCE_",
    )

    filesystem_enabled: bool = Field(default=True, description="Enable filesystem persistence")
    postgres_enabled: bool = Field(default=False, description="Enable PostgreSQL persistence")
    dual_write_enabled: bool = Field(default=False, description="Write to both backends simultaneously")
    database_read_enabled: bool = Field(default=False, description="Read from PostgreSQL instead of filesystem")


class PromptSettings(BaseSettings):
    """Prompt management settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    prompt_base_path: Path = Field(default=Path("./prompts"), description="Prompts base path")
    prompt_cache_enabled: bool = Field(default=True, description="Enable prompt caching")
    prompt_versioning_enabled: bool = Field(default=True, description="Enable versioning")

    @field_validator("prompt_base_path", mode="after")
    @classmethod
    def create_prompt_directory(cls, v: Path) -> Path:
        """Ensure prompt directory exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v


class Settings(BaseSettings):
    """Master settings combining all configuration."""

    app: AppSettings = Field(default_factory=AppSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    playwright: PlaywrightSettings = Field(default_factory=PlaywrightSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    contract: ContractSettings = Field(default_factory=ContractSettings)
    prompt: PromptSettings = Field(default_factory=PromptSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app.environment == "production"

    @property
    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.app.environment == "testing"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns:
        Settings: Application settings

    Note:
        This function is cached to ensure single settings instance.
    """
    return Settings()


# Convenience exports
settings = get_settings()
