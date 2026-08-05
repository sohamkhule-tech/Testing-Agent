# AI Context

## Project Summary

This project builds an **AI Agentic Web Application Testing Platform**. A tester provides three inputs — an application URL, credentials, and a natural-language prompt (e.g. "Test Employee Management") — and the platform autonomously crawls the application, discovers its structure, designs test cases, generates Playwright scripts, executes them, and produces a structured report.

The system is built on a **Spec-Driven Development (SDD)** methodology where every feature is defined by a written specification before any implementation begins.

## Project Goal

Build an internal-pilot-grade AI testing platform (MVP) that can take a real web application and produce a useful, reviewable set of automated functional tests with minimal human effort. The MVP targets a single application, single user, local execution, and the cheapest possible infrastructure. Long-term, the platform evolves into a production-grade multi-tenant service.

## Current Development Phase

**Pre-Milestone 1 / Project Scaffolding.** Documentation structure and reference architecture are in place. No implementation has begun. All modules are **Planned**.

**Current Sprint:** Establishing the documentation foundation — folder structure, data contracts, and AI onboarding context.

## High-Level Architecture

This project follows a **multi-agent architecture** with a clear separation between AI agents, deterministic services, and human workflow gates.

**Design Principle:** AI Generates. Services Execute. Humans Approve.

### 🤖 AI Agents (5)

1. **Trigger Agent** — Validates inputs, resolves crawl strategy, initializes run state
2. **AI Crawler Agent** — Crawls the target application and produces raw discovery artifacts
3. **DOM + Runtime Discovery Agent** — Analyzes raw crawl output to extract structured DOM and API information
4. **Test Design Agent** — Reasons about test intent and generates concrete test cases
5. **Code Generation Agent** — Transforms approved test cases into executable Playwright code

### ⚙️ Deterministic Services (3)

1. **Inventory Aggregator Service** — Merges, deduplicates, and normalizes discovery data into the canonical Application Inventory
2. **Execution Service** — Invokes Playwright Test Runner and captures execution results
3. **Reporting Service** — Produces structured reports across multiple output formats

### 👤 Human Workflow (Phase 2)

- **Human Review Workflow Gate** — Human-in-the-loop approval workflow for reviewing and approving generated test cases before execution (introduced in Phase 2)

**Architectural Boundary:** AI agents generate artifacts. Deterministic services process and execute them. AI agents never execute Playwright or modify persistent state directly.

For the full architecture, see `docs/references/Executive-Architecture-Design-Document-MVP.docx`. For a maintained summary, see `docs/02-ARCHITECTURE.md`. For the visual workflow, see `docs/diagrams/Flow_Diagram_Testing_AI_Agent_v3.jpg`.

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| Frontend | Next.js (TypeScript) |
| Browser Automation | Playwright |
| AI Orchestration | LangGraph |
| LLM | DeepSeek R1 Distill Qwen 8B (via Ollama) |
| Database (MVP) | SQLite |
| Database (Phase 2+) | PostgreSQL |
| Configuration | Pydantic BaseSettings |

## Repository Structure

```
agentic-testing-platform/
├── docs/               # All documentation, specs, contracts
├── backend/            # Python/FastAPI application
├── frontend/           # Next.js application
├── raw-crawl-packages/ # Immutable crawl output
├── generated/          # Test cases and reports
├── shared-workspace/   # Code generation → execution hand-off
└── inventories/        # Versioned application inventory
```

## Reference Documents

All AI agents **must** read these before implementation:

| Document | Location |
|---|---|
| Executive Architecture Design Document | `docs/references/Executive-Architecture-Design-Document-MVP.docx` |
| SDD & HLD (5-Agent Revision) | `docs/references/Agentic-AI-Testing-Platform-SDD-HLD-MVP-5-Agent-Revision.docx` |
| Architecture Workflow Diagram | `docs/diagrams/Flow_Diagram_Testing_AI_Agent_v3.jpg` |
| Architecture Decisions | `docs/06-ADR.md` |
| Project State | `docs/04-PROJECT_STATE.md` |
| Coding Standards | `docs/05-CODING_STANDARDS.md` |

## Documentation Strategy

This project follows **Spec-Driven Development (SDD)**:

- Specifications in `docs/specs/` are the **source of truth** for every feature.
- Data contracts in `docs/contracts/` define every cross-module interface.
- The API surface is documented in `docs/api/openapi.yaml`.
- Agent prompts are versioned in `docs/prompts/`.
- Implementation follows approved specifications only; no speculative coding.
- Architecture decisions are recorded in `docs/06-ADR.md` as they are made.

## Document Hierarchy

Implementation follows this document hierarchy. Each level must be read before proceeding to the next:

```
AI_CONTEXT.md
     ↓
PROJECT_STATE.md
     ↓
ARCHITECTURE.md
     ↓
Specification (docs/specs/)
     ↓
Contract (docs/contracts/)
     ↓
Implementation
```

## Source of Truth

When documents conflict, the following precedence applies. Higher-priority documents override lower-priority ones.

1. **Approved Reference Documents** — Executive Architecture, SDD & HLD
2. **Approved ADRs** — `docs/06-ADR.md`
3. **Architecture** — `docs/02-ARCHITECTURE.md`
4. **Specifications** — `docs/specs/`
5. **Contracts** — `docs/contracts/`
6. **Project State** — `docs/04-PROJECT_STATE.md`
7. **Implementation** — the code itself

## AI Scope

### AI Agents SHOULD

- Read all relevant project documentation before starting work
- Follow specifications exactly as written
- Adhere to coding standards in `docs/05-CODING_STANDARDS.md`
- Update `docs/04-PROJECT_STATE.md` after completing a module
- Record architecture decisions in `docs/06-ADR.md` when a significant choice arises

### AI Agents MUST NOT

- Invent requirements, features, or technologies not found in the reference documents
- Skip reading a specification before implementing the feature it describes
- Change the intended architecture without an approved ADR
- Introduce undocumented technologies or dependencies
- Modify completed modules without explicit approval
- Assume implementation details not present in specifications or contracts

## Current Project Status

| Module | Status |
|---|---|
| Documentation structure | Done |
| AI Context (this document) | Done |
| Project Overview | Scaffolded (empty) |
| Architecture doc | Scaffolded (empty) |
| Roadmap | Scaffolded (empty) |
| Project State | Scaffolded (empty) |
| Coding Standards | Scaffolded (empty) |
| ADR log | Scaffolded (empty) |
| Specifications (10) | Scaffolded (empty) |
| Data contracts (7) | Scaffolded (empty JSON) |
| OpenAPI spec | Scaffolded (minimal) |
| Agent prompts (4) | Scaffolded (empty) |
| All backend/frontend code | Planned |
| Agent implementations | Planned |
| Database schema | Planned |
| Infrastructure | Planned |

## Next Planned Tasks

**Current Sprint Goal:** Complete documentation foundation — populate PROJECT_OVERVIEW.md, ARCHITECTURE.md, ROADMAP.md.

**Next Milestone:** Implement project setup scaffolding (FastAPI + Next.js) per Specification `001-project-setup.md`.

## Important Architectural Decisions

- **5 AI Agents + 3 Deterministic Services** — MVP consolidates responsibilities into 5 AI agents (Trigger, AI Crawler, DOM + Runtime Discovery, Test Design, Code Generation) and 3 deterministic services (Inventory Aggregator Service, Execution Service, Reporting Service)
- **AI Generates, Services Execute** — AI agents perform reasoning and artifact generation only; deterministic services handle data processing, test execution, and reporting
- **Playwright for deterministic browser automation** — Browser automation is handled by services, never by AI agents
- **Structured Inventory is the source of truth** — Application Inventory (produced by Inventory Aggregator Service) is never raw DOM
- **LangGraph for state machine orchestration** — Orchestrates the pipeline flow between AI agents and services
- **SQLite for MVP** (PostgreSQL from Phase 2)
- **Human Review Workflow Gate introduced in Phase 2** — MVP ships without human approval gate; Phase 2 adds the Human Review Workflow for test case approval before execution
- **Agent decomposition** — 5 AI agents at MVP, decomposing to 12 agents at Production

For detailed rationale, refer to `docs/06-ADR.md`.

## AI Workflow

```
1. Read AI_CONTEXT.md                 ← this document
2. Read PROJECT_STATE.md              ← current status
3. Read ARCHITECTURE.md               ← maintained architecture
4. Read relevant Specification        ← docs/specs/
5. Read relevant Contract             ← docs/contracts/
6. Implement                           ← follow Coding Standards
7. Update PROJECT_STATE.md             ← reflect new state
8. Record ADR (if required)            ← docs/06-ADR.md
```

Specifications must be read before any code is written. Never implement from memory or assumption.
