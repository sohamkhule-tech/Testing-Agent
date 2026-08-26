from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    INSTALLING = "installing"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class BrowserType(str, Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"
    ALL = "all"


class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    FLAKY = "flaky"
    TIMEOUT = "timeout"


class FailureType(str, Enum):
    LOCATOR_NOT_FOUND = "locator_not_found"
    TIMEOUT = "timeout"
    ASSERTION_FAILED = "assertion_failed"
    NETWORK_ERROR = "network_error"
    AUTH_FAILED = "auth_failed"
    NAVIGATION_ERROR = "navigation_error"
    UNEXPECTED_DIALOG = "unexpected_dialog"
    BROWSER_CRASH = "browser_crash"
    ENVIRONMENT_ERROR = "environment_error"
    MISSING_ELEMENT = "missing_element"
    UNKNOWN = "unknown"


class ExecutionConfig(BaseModel):
    browser: BrowserType | None = Field(default=None)
    base_url: str | None = Field(default=None)
    headless: bool = Field(default=True)
    parallel_execution: bool = Field(default=True)
    max_workers: int = Field(default=4)
    retries: int = Field(default=0)
    retry_flaky_only: bool = Field(default=False)
    timeout_ms: int = Field(default=60000)
    screenshot_on_failure: bool = Field(default=True)
    video_on_failure: bool = Field(default=True)
    trace_on_failure: bool = Field(default=True)
    is_ci: bool = Field(default=False)
    test_file: str | None = Field(default=None)
    grep: str | None = Field(default=None)


class TestResult(BaseModel):
    __test__ = False  # Prevent pytest collection

    title: str = Field(default="")
    file: str | None = Field(default=None)
    line: int = Field(default=0)
    status: str = Field(default="skipped")
    duration_ms: float = Field(default=0.0)
    retry_count: int = Field(default=0)
    error_message: str | None = Field(default=None)
    error_stack: str | None = Field(default=None)
    failure_analysis: dict[str, Any] | None = Field(default=None)
    is_flaky: bool = Field(default=False)
    annotations: list[dict[str, Any]] | None = Field(default=None)
    was_retried: bool = Field(default=False)
    retry_failed: bool = Field(default=False)
    original_status: str | None = Field(default=None)
    screenshots: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)
    traces: list[str] = Field(default_factory=list)
    browser: str | None = Field(default=None)


class ExecutionMetrics(BaseModel):
    total_tests: int = Field(default=0)
    tests_passed: int = Field(default=0)
    tests_failed: int = Field(default=0)
    tests_skipped: int = Field(default=0)
    tests_flaky: int = Field(default=0)
    pass_rate: float = Field(default=0.0)
    fail_rate: float = Field(default=0.0)
    average_duration_ms: float = Field(default=0.0)
    total_duration_seconds: float = Field(default=0.0)
    slowest_tests: list[dict[str, Any]] = Field(default_factory=list)
    fastest_tests: list[dict[str, Any]] = Field(default_factory=list)
    failure_distribution: dict[str, int] = Field(default_factory=dict)
    browser_stats: dict[str, dict[str, int]] = Field(default_factory=dict)
    module_stats: dict[str, dict[str, int]] = Field(default_factory=dict)
    health_score: float = Field(default=0.0)
    health_status: str = Field(default="unknown")


class FailureAnalysis(BaseModel):
    failure_type: FailureType = Field(default=FailureType.UNKNOWN)
    root_cause: str = Field(default="")
    severity: str = Field(default="medium")
    recommendation: str = Field(default="")
    affected_test: str = Field(default="")
    affected_page: str | None = Field(default=None)
    is_flaky: bool = Field(default=False)


class FailureSummary(BaseModel):
    total_failures: int = Field(default=0)
    failure_analyses: list[dict[str, Any]] = Field(default_factory=list)
    failure_type_counts: dict[str, int] = Field(default_factory=dict)
    flaky_test_count: int = Field(default=0)
    flaky_tests: list[str] = Field(default_factory=list)


class RetryInfo(BaseModel):
    test_title: str = Field(default="")
    attempt_number: int = Field(default=0)
    max_retries: int = Field(default=0)
    status: TestStatus = Field(default=TestStatus.SKIPPED)
    duration_ms: float = Field(default=0.0)
    error: str | None = Field(default=None)


class RetrySummary(BaseModel):
    total_retries: int = Field(default=0)
    tests_retried: int = Field(default=0)
    passed_after_retry: int = Field(default=0)
    failed_after_retry: int = Field(default=0)
    retry_success_rate: float = Field(default=0.0)
    retry_details: list[RetryInfo] = Field(default_factory=list)


class ArtifactSummary(BaseModel):
    screenshots_count: int = Field(default=0)
    videos_count: int = Field(default=0)
    traces_count: int = Field(default=0)
    logs_count: int = Field(default=0)
    total_size_bytes: int = Field(default=0)
    artifacts_path: str | None = Field(default=None)


class ExecutionSummary(BaseModel):
    execution_id: str = Field(default="")
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    start_time: str | None = Field(default=None)
    end_time: str | None = Field(default=None)
    duration_seconds: float = Field(default=0.0)
    config: ExecutionConfig | None = Field(default=None)
    test_results: list[TestResult] = Field(default_factory=list)
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    failure_summary: FailureSummary | None = Field(default=None)
    retry_summary: RetrySummary | None = Field(default=None)
    artifacts: ArtifactSummary = Field(default_factory=ArtifactSummary)
    report_paths: dict[str, str] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    summary: ExecutionSummary | None = Field(default=None)
    error_message: str | None = Field(default=None)
    duration_seconds: float = Field(default=0.0)


class ExecutionRequest(BaseModel):
    run_id: str = Field(default="")
    workspace_path: str = Field(default="")
    project_path: str = Field(default="")
    config: ExecutionConfig = Field(default_factory=ExecutionConfig)
    env_vars: dict[str, str] = Field(default_factory=dict)
