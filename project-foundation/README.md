# AI Agentic Testing Platform - Project Foundation

Enterprise-grade AI-powered web application testing platform built with FastAPI, LangGraph, and Playwright.

## Architecture

This project follows Clean Architecture principles with clear separation of concerns:

- **🤖 AI Agents (5)**: Trigger, AI Crawler, DOM + Runtime Discovery, Test Design, Code Generation
- **⚙️ Deterministic Services (3)**: Inventory Aggregator, Execution, Reporting
- **👤 Human Workflow (1)**: Human Review Workflow Gate

**Design Principle**: AI Generates. Services Execute. Humans Approve.

## Technology Stack

- **Python 3.12+**
- **FastAPI** - Modern async web framework
- **LangGraph** - AI agent orchestration
- **Pydantic v2** - Data validation
- **Playwright** - Browser automation
- **OpenAI SDK** - LLM integration
- **structlog** - Structured logging
- **pytest** - Testing framework
- **uv** - Fast Python package manager

## Project Structure

```
app/
├── api/              # FastAPI routes and endpoints
├── core/             # Core application logic
├── config/           # Configuration management
├── graph/            # LangGraph state and workflow
├── agents/           # AI agent implementations
├── services/         # Deterministic services
├── prompts/          # LLM system prompts
├── contracts/        # JSON schema contracts
├── models/           # Domain models
├── schemas/          # Pydantic schemas
├── storage/          # Artifact storage
├── validators/       # Contract validators
├── repositories/     # Data access layer
├── llm/              # LLM client abstractions
├── utils/            # Utilities and helpers
├── logging/          # Logging configuration
├── exceptions/       # Custom exceptions
├── middleware/       # FastAPI middleware
└── dependencies/     # Dependency injection

tests/                # Test suite
configs/              # Configuration files
scripts/              # Utility scripts
docs/                 # Documentation
```

## Quick Start

### Prerequisites

- Python 3.12+
- uv (recommended) or pip
- Docker (optional)

### Installation

```bash
# Clone repository
git clone <repository-url>
cd project-foundation

# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium
```

### Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
# - Add OpenAI API key
# - Configure storage paths
# - Adjust logging settings
```

### Running the Application

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test types
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only

# Run with verbose output
pytest -v
```

### Code Quality

```bash
# Format code
black app/ tests/

# Lint code
ruff check app/ tests/

# Type checking
mypy app/
```

## API Documentation

Once the application is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## Key Features

### Configuration Management
- Environment-based configuration
- Type-safe settings with Pydantic
- Secrets management
- Multi-environment support (dev, test, prod)

### Logging
- Structured logging with structlog
- Correlation ID tracking
- Component-level logging
- JSON output format
- File rotation and retention

### Error Handling
- Custom exception hierarchy
- Global exception middleware
- Detailed error responses
- Retry mechanisms with exponential backoff

### Artifact Management
- Multiple format support (JSON, HTML, Markdown, ZIP)
- Size limits and validation
- Compression support
- Retention policies

### Contract Validation
- JSON schema validation
- Contract versioning
- Strict mode enforcement
- Comprehensive error messages

### Prompt Management
- Template-based prompts
- Versioning support
- Caching mechanism
- Dynamic loading

### LLM Abstraction
- Provider-agnostic interface
- Automatic retries
- Token usage tracking
- Timeout handling

## Development Guidelines

### Code Style
- Follow PEP 8
- Use type hints everywhere
- Maximum line length: 100 characters
- Use async/await for I/O operations

### Testing Strategy
- Unit tests for all core logic
- Integration tests for external dependencies
- Fixtures for common test data
- Mock external services

### Git Workflow
- Feature branches from main
- Conventional commits
- Pull request reviews required
- CI/CD validation

### Documentation
- Docstrings for all public APIs
- Type hints for function signatures
- README for each module
- Architecture Decision Records (ADRs)

## Deployment

### Docker

```bash
# Build image
docker build -t ai-testing-platform .

# Run container
docker run -p 8000:8000 --env-file .env ai-testing-platform
```

### Environment Variables

See `.env.example` for all available configuration options.

## Monitoring

- Health check endpoint: `/health`
- Readiness check: `/health/ready`
- Metrics endpoint: `/metrics` (if enabled)

## Security

- API key authentication
- CORS configuration
- Input validation with Pydantic
- Secret management
- Rate limiting (future)

## Performance

- Async I/O operations
- Connection pooling
- Caching strategies
- Efficient artifact storage

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure virtual environment is activated
2. **Playwright errors**: Run `playwright install`
3. **OpenAI errors**: Check API key in `.env`
4. **Port conflicts**: Change `API_PORT` in `.env`

### Logs

- Application logs: `./storage/logs/`
- Access logs: stdout (JSON format)
- Error logs: stderr

## Contributing

1. Fork the repository
2. Create feature branch
3. Implement changes with tests
4. Run quality checks
5. Submit pull request

## License

MIT License - See LICENSE file for details

## Support

- Documentation: `./docs/`
- Issues: GitHub Issues
- Email: team@example.com

---

**Status**: Phase 0 - Project Foundation Complete ✅

**Next Phase**: Agent and Service Implementation
