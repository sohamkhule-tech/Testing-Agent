"""
Custom Exception Hierarchy

Defines application-specific exceptions for different error scenarios.
"""

from typing import Any


class PlatformException(Exception):
    """Base exception for all platform errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize platform exception.

        Args:
            message: Error message
            error_code: Optional error code for categorization
            details: Optional additional error details
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.extra = kwargs


# ===========================================
# Configuration Exceptions
# ===========================================


class ConfigurationError(PlatformException):
    """Raised when configuration is invalid or missing."""

    pass


class EnvironmentError(ConfigurationError):
    """Raised when environment variables are invalid."""

    pass


class SettingsValidationError(ConfigurationError):
    """Raised when settings validation fails."""

    pass


# ===========================================
# Validation Exceptions
# ===========================================


class ValidationError(PlatformException):
    """Base exception for validation errors."""

    pass


class SchemaValidationError(ValidationError):
    """Raised when schema validation fails."""

    def __init__(
        self,
        message: str,
        schema_name: str | None = None,
        validation_errors: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize schema validation error.

        Args:
            message: Error message
            schema_name: Name of the schema that failed
            validation_errors: List of validation error messages
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.schema_name = schema_name
        self.validation_errors = validation_errors or []


class ContractValidationError(ValidationError):
    """Raised when contract validation fails."""

    def __init__(
        self,
        message: str,
        contract_name: str | None = None,
        contract_version: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize contract validation error.

        Args:
            message: Error message
            contract_name: Name of the contract
            contract_version: Version of the contract
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.contract_name = contract_name
        self.contract_version = contract_version


class ContractNotFoundError(ContractValidationError):
    """Raised when a contract file is not found."""

    def __init__(
        self,
        message: str,
        contract_name: str | None = None,
        contract_path: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, contract_name=contract_name, **kwargs)
        self.contract_path = contract_path


class InputValidationError(ValidationError):
    """Raised when input validation fails."""

    pass


# ===========================================
# Storage Exceptions
# ===========================================


class StorageError(PlatformException):
    """Base exception for storage-related errors."""

    pass


class ArtifactNotFoundError(StorageError):
    """Raised when artifact cannot be found."""

    def __init__(self, message: str, artifact_id: str | None = None, **kwargs: Any) -> None:
        """
        Initialize artifact not found error.

        Args:
            message: Error message
            artifact_id: ID of the missing artifact
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.artifact_id = artifact_id


class ArtifactUploadError(StorageError):
    """Raised when artifact upload fails."""

    pass


class ArtifactDownloadError(StorageError):
    """Raised when artifact download fails."""

    pass


class StorageQuotaExceededError(StorageError):
    """Raised when storage quota is exceeded."""

    pass


class ArtifactSizeExceededError(StorageError):
    """Raised when artifact size exceeds limit."""

    def __init__(
        self, message: str, size: int, max_size: int, **kwargs: Any
    ) -> None:
        """
        Initialize artifact size exceeded error.

        Args:
            message: Error message
            size: Actual artifact size
            max_size: Maximum allowed size
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.size = size
        self.max_size = max_size


# ===========================================
# LLM Exceptions
# ===========================================


class LLMError(PlatformException):
    """Base exception for LLM-related errors."""

    pass


class LLMProviderError(LLMError):
    """Raised when LLM provider encounters an error."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize LLM provider error.

        Args:
            message: Error message
            provider: LLM provider name
            model: Model name
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.provider = provider
        self.model = model


class LLMRateLimitError(LLMError):
    """Raised when LLM rate limit is exceeded."""

    pass


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""

    pass


class LLMTokenLimitError(LLMError):
    """Raised when token limit is exceeded."""

    def __init__(
        self, message: str, tokens_used: int, token_limit: int, **kwargs: Any
    ) -> None:
        """
        Initialize LLM token limit error.

        Args:
            message: Error message
            tokens_used: Number of tokens used
            token_limit: Token limit
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.tokens_used = tokens_used
        self.token_limit = token_limit


class LLMInvalidResponseError(LLMError):
    """Raised when LLM response is invalid or cannot be parsed."""

    pass


# ===========================================
# Retry Exceptions
# ===========================================


class RetryError(PlatformException):
    """Base exception for retry-related errors."""

    pass


class MaxRetriesExceededError(RetryError):
    """Raised when maximum retry attempts are exceeded."""

    def __init__(
        self, message: str, attempts: int, max_attempts: int, **kwargs: Any
    ) -> None:
        """
        Initialize max retries exceeded error.

        Args:
            message: Error message
            attempts: Number of attempts made
            max_attempts: Maximum allowed attempts
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.attempts = attempts
        self.max_attempts = max_attempts


class RetryableError(RetryError):
    """Raised when operation can be retried."""

    pass


class NonRetryableError(RetryError):
    """Raised when operation cannot be retried."""

    pass


# ===========================================
# Graph/Workflow Exceptions
# ===========================================


class GraphError(PlatformException):
    """Base exception for graph/workflow errors."""

    pass


class NodeExecutionError(GraphError):
    """Raised when graph node execution fails."""

    def __init__(
        self, message: str, node_name: str | None = None, **kwargs: Any
    ) -> None:
        """
        Initialize node execution error.

        Args:
            message: Error message
            node_name: Name of the failed node
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.node_name = node_name


class AgentExecutionError(NodeExecutionError):
    """Raised when an agent fails during execution."""

    def __init__(
        self, message: str, agent_name: str | None = None, **kwargs: Any
    ) -> None:
        """
        Initialize agent execution error.

        Args:
            message: Error message
            agent_name: Name of the agent that failed
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.agent_name = agent_name
class GraphStateError(GraphError):
    """Raised when graph state is invalid."""

    pass


class GraphConfigurationError(GraphError):
    """Raised when graph configuration is invalid."""

    pass


# ===========================================
# Prompt Exceptions
# ===========================================


class PromptError(PlatformException):
    """Base exception for prompt-related errors."""

    pass


class PromptNotFoundError(PromptError):
    """Raised when prompt template is not found."""

    def __init__(
        self, message: str, prompt_name: str | None = None, **kwargs: Any
    ) -> None:
        """
        Initialize prompt not found error.

        Args:
            message: Error message
            prompt_name: Name of the missing prompt
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.prompt_name = prompt_name


class PromptRenderError(PromptError):
    """Raised when prompt template rendering fails."""

    pass


class PromptVersionError(PromptError):
    """Raised when prompt version is invalid or incompatible."""

    pass


# ===========================================
# Business Logic Exceptions
# ===========================================


class BusinessError(PlatformException):
    """Base exception for business logic errors."""

    pass


class ResourceNotFoundError(BusinessError):
    """Raised when requested resource is not found."""

    def __init__(
        self,
        message: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize resource not found error.

        Args:
            message: Error message
            resource_type: Type of resource
            resource_id: ID of the resource
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.resource_type = resource_type
        self.resource_id = resource_id


class ResourceConflictError(BusinessError):
    """Raised when resource conflict occurs."""

    pass


class OperationNotAllowedError(BusinessError):
    """Raised when operation is not allowed in current state."""

    pass


# ===========================================
# External Service Exceptions
# ===========================================


class ExternalServiceError(PlatformException):
    """Base exception for external service errors."""

    pass


class PlaywrightError(ExternalServiceError):
    """Raised when Playwright encounters an error."""

    pass


class BrowserError(ExternalServiceError):
    """Raised when browser operation fails."""

    pass


class ServiceError(ExternalServiceError):
    """Raised when a service-level operation fails."""

    pass


class NetworkError(ExternalServiceError):
    """Raised when network operation fails."""

    pass


class ExecutionError(ExternalServiceError):
    """Raised when test execution fails."""

    pass


# ===========================================
# HTTP Exceptions (for FastAPI)
# ===========================================


class HTTPExceptionBase(PlatformException):
    """Base class for HTTP exceptions."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize HTTP exception.

        Args:
            message: Error message
            status_code: HTTP status code
            headers: Optional response headers
            **kwargs: Additional error details
        """
        super().__init__(message, **kwargs)
        self.status_code = status_code
        self.headers = headers


class BadRequestError(HTTPExceptionBase):
    """HTTP 400 Bad Request."""

    def __init__(self, message: str = "Bad request", **kwargs: Any) -> None:
        super().__init__(message, status_code=400, **kwargs)


class UnauthorizedError(HTTPExceptionBase):
    """HTTP 401 Unauthorized."""

    def __init__(self, message: str = "Unauthorized", **kwargs: Any) -> None:
        super().__init__(message, status_code=401, **kwargs)


class ForbiddenError(HTTPExceptionBase):
    """HTTP 403 Forbidden."""

    def __init__(self, message: str = "Forbidden", **kwargs: Any) -> None:
        super().__init__(message, status_code=403, **kwargs)


class NotFoundError(HTTPExceptionBase):
    """HTTP 404 Not Found."""

    def __init__(self, message: str = "Not found", **kwargs: Any) -> None:
        super().__init__(message, status_code=404, **kwargs)


class ConflictError(HTTPExceptionBase):
    """HTTP 409 Conflict."""

    def __init__(self, message: str = "Conflict", **kwargs: Any) -> None:
        super().__init__(message, status_code=409, **kwargs)


class UnprocessableEntityError(HTTPExceptionBase):
    """HTTP 422 Unprocessable Entity."""

    def __init__(self, message: str = "Unprocessable entity", **kwargs: Any) -> None:
        super().__init__(message, status_code=422, **kwargs)


class InternalServerError(HTTPExceptionBase):
    """HTTP 500 Internal Server Error."""

    def __init__(self, message: str = "Internal server error", **kwargs: Any) -> None:
        super().__init__(message, status_code=500, **kwargs)


class ServiceUnavailableError(HTTPExceptionBase):
    """HTTP 503 Service Unavailable."""

    def __init__(self, message: str = "Service unavailable", **kwargs: Any) -> None:
        super().__init__(message, status_code=503, **kwargs)
