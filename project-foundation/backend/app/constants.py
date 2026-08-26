"""
Constants and Enumerations

Application-wide constants and enum definitions.
"""

from enum import Enum


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class ComponentType(str, Enum):
    """Component types in the system."""

    AGENT = "agent"
    SERVICE = "service"
    GATEWAY = "gateway"
    REPOSITORY = "repository"
    VALIDATOR = "validator"


class AgentType(str, Enum):
    """AI Agent types."""

    TRIGGER = "trigger"
    AI_CRAWLER = "ai_crawler"
    DOM_RUNTIME_DISCOVERY = "dom_runtime_discovery"
    INVENTORY_AGGREGATOR = "inventory_aggregator"
    TEST_DESIGN = "test_design"
    HUMAN_REVIEW = "human_review"
    CODE_GENERATION = "code_generation"
    EXECUTION = "execution"
    REPORTING = "reporting"


class ArtifactType(str, Enum):
    """Artifact types."""

    CRAWL_PACKAGE = "crawl_package"
    DOM_INVENTORY = "dom_inventory"
    APPLICATION_INVENTORY = "application_inventory"
    TEST_CASE = "test_case"
    PLAYWRIGHT_PROJECT = "playwright_project"
    EXECUTION_REPORT = "execution_report"


class RunStatus(str, Enum):
    """Execution run status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class NodeStatus(str, Enum):
    """LangGraph node execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ValidationStatus(str, Enum):
    """Validation status."""

    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"


class LogLevel(str, Enum):
    """Log level."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class HTTPMethod(str, Enum):
    """HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ContentType(str, Enum):
    """Content types."""

    JSON = "application/json"
    TEXT = "text/plain"
    HTML = "text/html"
    XML = "application/xml"
    BINARY = "application/octet-stream"


# Application constants
class Constants:
    """Application-wide constants."""

    # Version
    VERSION = "0.1.0"
    API_VERSION = "v1"

    # Timeouts (seconds)
    DEFAULT_TIMEOUT = 30
    LLM_TIMEOUT = 120
    CRAWLER_TIMEOUT = 300

    # Limits
    MAX_RETRY_ATTEMPTS = 3
    MAX_FILE_SIZE_MB = 100
    MAX_PROMPT_LENGTH = 100000
    MAX_CONTEXT_LENGTH = 128000

    # Defaults
    DEFAULT_PAGE_SIZE = 50
    DEFAULT_BATCH_SIZE = 10

    # Storage
    STORAGE_ROOT = "storage"
    ARTIFACTS_DIR = "artifacts"
    PROMPTS_DIR = "prompts"
    CONTRACTS_DIR = "contracts"
    LOGS_DIR = "logs"

    # HTTP
    DEFAULT_USER_AGENT = "Enterprise-AI-Testing-Platform/0.1.0"

    # Date formats
    DATE_FORMAT = "%Y-%m-%d"
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
    DATETIME_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
