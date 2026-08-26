"""
Base Interfaces for Core Components

Defines abstract interfaces following Clean Architecture principles.
"""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

# Type variables for generic interfaces
T = TypeVar("T")
ID = TypeVar("ID")


class IRepository(ABC, Generic[T, ID]):
    """
    Base repository interface for data access.

    Provides CRUD operations abstraction.
    """

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create a new entity."""
        pass

    @abstractmethod
    async def get_by_id(self, entity_id: ID) -> T | None:
        """Get entity by ID."""
        pass

    @abstractmethod
    async def update(self, entity: T) -> T:
        """Update existing entity."""
        pass

    @abstractmethod
    async def delete(self, entity_id: ID) -> bool:
        """Delete entity by ID."""
        pass

    @abstractmethod
    async def exists(self, entity_id: ID) -> bool:
        """Check if entity exists."""
        pass


class IService(ABC):
    """
    Base service interface for business logic.

    Services orchestrate operations across repositories and external services.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize service resources."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup service resources."""
        pass


class IAgent(ABC):
    """
    Base agent interface for AI agents.

    Agents encapsulate AI-powered operations.
    """

    @abstractmethod
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute agent operation.

        Args:
            input_data: Input data for agent

        Returns:
            Agent output data
        """
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Get agent's system prompt."""
        pass


class IValidator(ABC, Generic[T]):
    """
    Base validator interface.

    Validators ensure data integrity and contract compliance.
    """

    @abstractmethod
    async def validate(self, data: T) -> bool:
        """
        Validate data.

        Args:
            data: Data to validate

        Returns:
            True if valid

        Raises:
            ValidationError: If validation fails
        """
        pass

    @abstractmethod
    def get_validation_errors(self) -> list[str]:
        """Get list of validation errors."""
        pass


class IArtifactStorage(ABC):
    """
    Base interface for artifact storage.

    Provides abstraction over storage backends (local, S3, Azure, etc.).
    """

    @abstractmethod
    async def save(
        self, artifact_id: str, content: bytes, metadata: dict[str, Any] | None = None
    ) -> str:
        """
        Save artifact.

        Args:
            artifact_id: Unique artifact identifier
            content: Artifact content
            metadata: Optional metadata

        Returns:
            Storage path or URL
        """
        pass

    @abstractmethod
    async def load(self, artifact_id: str) -> bytes:
        """
        Load artifact content.

        Args:
            artifact_id: Artifact identifier

        Returns:
            Artifact content
        """
        pass

    @abstractmethod
    async def exists(self, artifact_id: str) -> bool:
        """Check if artifact exists."""
        pass

    @abstractmethod
    async def delete(self, artifact_id: str) -> bool:
        """Delete artifact."""
        pass

    @abstractmethod
    async def get_metadata(self, artifact_id: str) -> dict[str, Any]:
        """Get artifact metadata."""
        pass


class IPromptLoader(ABC):
    """
    Base interface for prompt loading and management.

    Handles prompt templates, versioning, and rendering.
    """

    @abstractmethod
    async def load_prompt(self, prompt_name: str, version: str | None = None) -> str:
        """
        Load prompt template.

        Args:
            prompt_name: Name of the prompt
            version: Optional version (defaults to latest)

        Returns:
            Prompt template content
        """
        pass

    @abstractmethod
    async def render_prompt(self, prompt_name: str, variables: dict[str, Any]) -> str:
        """
        Render prompt with variables.

        Args:
            prompt_name: Name of the prompt
            variables: Template variables

        Returns:
            Rendered prompt
        """
        pass


class ILLMClient(ABC):
    """
    Base interface for LLM providers.

    Provides provider-agnostic LLM interaction.
    """

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Generate completion from prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            model: Optional model override for this call
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated completion
        """
        pass

    @abstractmethod
    async def complete_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseModel:
        """
        Generate structured completion conforming to Pydantic model.

        Args:
            prompt: User prompt
            response_model: Pydantic model for response
            system_prompt: Optional system prompt
            model: Optional model override for this call
            **kwargs: Additional parameters

        Returns:
            Parsed Pydantic model instance
        """
        pass

    @abstractmethod
    async def stream_complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Stream completion tokens.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            model: Optional model override for this call
            **kwargs: Additional parameters

        Yields:
            Token chunks
        """
        pass
