# Roadmap

## Document Metadata

| Field | Value |
|---|---|
| Document | Roadmap |
| Document ID | SDD-ROAD-001 |
| Version | 1.0 |
| Status | Draft |
| Owner | Platform Architecture Team |
| Last Updated | 2026-07-20 |
| Review Frequency | Quarterly or on major milestone completion |

## Roadmap Overview

The roadmap is divided into four phases — Documentation Foundation, MVP, Platform Expansion, and Production Readiness — followed by an ongoing Ecosystem phase. This phased approach was chosen for three reasons:

**Validate before scaling.** The MVP proves the concept end-to-end with the smallest possible investment — a single application, single user, local execution, and the cheapest infrastructure. Every phase after MVP is justified by what is learned in the phase before it.

**Deliver working software early.** The MVP is designed to be shippable by a small team in weeks, not quarters. A fourteen-week delivery target forces disciplined scope management: every feature in the MVP is necessary to close the end-to-end loop; everything else is explicitly deferred.

**Keep architecture evolvable.** Each phase decomposes the previous phase's components into more specialised services. The MVP's five consolidated agents split apart in Phase 2 and reach the full twelve-agent architecture at Production. This means the team is never blocked on an up-front service decomposition that might prove wrong, and the architecture never requires a rewrite — only extraction.

A high-level phase summary is available in `docs/01-PROJECT_OVERVIEW.md`. This document provides the detailed milestone breakdown.

## Guiding Principles

**Deliver working software early.** Every milestone produces a demonstrable, testable outcome. No milestone is considered complete until its output can be verified.

**Validate assumptions before scaling.** Crawl quality, LLM reliability, and selector accuracy are tested against a real pilot application before any Phase 2 investment is made.

**Keep architecture evolvable.** Internal module boundaries are preserved even when agents are consolidated. Splitting an agent in Phase 2 is a mechanical extraction, not a redesign.

**Build reusable foundations.** The Application Inventory, data contracts, and Shared Workspace are built once and reused across all downstream stages. No milestone rebuilds what a previous milestone delivered.

**Specification before implementation.** Every feature is specified, reviewed, and approved before code is written. Specifications are updated to reflect lessons learned, but the principle is never violated.

**Fail fast on risky assumptions.** The highest-risk items — LLM output quality, crawl reliability, selector resolution accuracy — are addressed in the earliest milestones so that corrective action can be taken before downstream dependencies are built.

## Development Phases

### Phase 0 — Documentation Foundation

The current phase. Establish the SDD documentation structure, data contracts, and AI onboarding context so that all subsequent implementation work has a clear specification to follow.

**Deliverables:**
- AI Context document (`00-AI_CONTEXT.md`)
- Project Overview (`01-PROJECT_OVERVIEW.md`)
- Architecture document (`02-ARCHITECTURE.md`)
- Roadmap (`03-ROADMAP.md`)
- Project State tracker (`04-PROJECT_STATE.md`)
- Coding Standards (`05-CODING_STANDARDS.md`)
- All 10 feature specifications (`docs/specs/`)
- All 7 data contracts (`docs/contracts/`)
- OpenAPI specification (`docs/api/openapi.yaml`)
- Agent prompts (`docs/prompts/`)

**Exit Criteria:**
- Every document above has been created and reviewed
- Every specification has been approved
- Every data contract has been defined
- AI_CONTEXT.md has been validated by reading it as the sole onboarding document

### Phase 1 — MVP (Weeks 1–14)

Build and ship the end-to-end pipeline: from user input (URL + credentials + prompt) through crawl, inventory, test design, code generation, execution, and reporting. The MVP runs as a single FastAPI process with SQLite, targets one application at a time, and executes locally.

**Deliverables:**
- Milestones 1–5 (see Milestone Breakdown below)
- Working end-to-end pipeline against a real pilot application
- HTML, JSON, and Excel reports

**Exit Criteria:**
- All five MVP milestones are complete
- End-to-end run succeeds against a real pilot application
- Generated tests compile and execute without modification
- Reports are accurate and viewable
- Pilot QA team has submitted feedback

### Phase 2 — Platform Expansion (Weeks 15–20)

Harden the platform for broader use. Introduce concurrency, persistent multi-user storage, authentication, agent decomposition, and self-healing.

**Deliverables:**
- Milestone 6 (see Milestone Breakdown below)
- PostgreSQL migration
- JWT authentication
- Self-Healing Agent
- Human review gate before execution
- Incremental crawling (partial refresh)
- Test Design Agent splits into Reasoning + Test Case Generator
- Code Generation Agent splits into Script Generator + POM Generator

**Exit Criteria:**
- Concurrent runs succeed without state corruption
- PostgreSQL migration completes with zero data loss
- Self-healing recovers from known selector-failure scenarios
- Excel review workflow is operational

### Phase 3 — Production Readiness (Weeks 21–28)

Deliver the full twelve-agent architecture as independently deployable, containerised services with multi-tenant isolation and cloud deployment.

**Deliverables:**
- Milestone 7 (see Milestone Breakdown below)
- Full twelve-agent architecture deployed
- Containerised services (Docker + orchestrator)
- API gateway with rate limiting and auth
- Multi-tenant isolation (row-level security)
- Cloud deployment via Terraform (Azure or AWS)

**Exit Criteria:**
- All agents are independently deployable
- Multi-tenant isolation is verified (Tenant A cannot access Tenant B data)
- Cloud deployment is reproducible via Terraform
- Observability stack (logs, metrics, traces) is operational

### Ecosystem (Weeks 29+)

Integrate with the wider SDLC toolchain and add specialised testing capabilities.

**Deliverables:**
- CI/CD pipeline integration (webhook triggers)
- Jira defect filing
- Slack notifications
- BrowserStack cloud grid integration
- Visual regression testing
- API-level test generation from discovered OpenAPI specs
- Accessibility testing (axe-core)
- Performance testing (Lighthouse / k6)

**Exit Criteria:**
- At least two ecosystem integrations are operational
- CI/CD trigger → run → report loop is demonstrated

## Milestone Breakdown

| # | Milestone | Goal | Major Deliverables | Dependencies | Exit Criteria |
|---|---|---|---|---|---|
| **M1** | MVP Skeleton | FastAPI + Next.js scaffolding, SQLite schema, single-application registration, Trigger Agent | Backend scaffold, frontend scaffold, database schema, Trigger Agent (URL validation, credential handling, scope classification), POST /runs endpoint | Phase 0 completion | New run can be created via API; Trigger Agent correctly validates input and resolves crawl strategy |
| **M2** | Understanding Pipeline | AI Crawler Agent producing the Raw Crawl Package; DOM + Runtime API Discovery running in parallel; Inventory Aggregator producing the versioned Application Inventory | AI Crawler Agent (sequential crawl, login heuristic, page-count cap, Playwright network interception), DOM Analyzer Module, Runtime API Discovery Module, Inventory Aggregator | M1 (Trigger Agent + scaffold) | Crawl produces an inspectable Raw Crawl Package; Inventory can be inspected via GET /inventory; DOM and API analysis both complete |
| **M3** | Reasoning & Generation | Ollama + DeepSeek integration; Test Design Agent producing structured test cases with the canonical test_cases.xlsx | LLM client abstraction, Test Design Agent (reasoning half + test-case-generation half), structured-output validation loop, Excel rendering | M2 (Inventory is available) | Test cases are generated from a real application's Inventory; test_cases.xlsx is viewable and accurate |
| **M4** | Code Generation & Execution | Code Generation Agent producing Playwright scripts and POMs; Shared Workspace hand-off; Execution Service running tests end-to-end | Code Generation Agent (script generation + POM generation), Shared Workspace, Execution Service (Playwright Test Runner integration, JSON reporter parsing) | M3 (Test cases are available) | Generated Playwright project compiles without errors; execution produces pass/fail results with screenshots |
| **M5** | Reporting & Pilot | Reporting Service producing HTML, JSON, and Excel reports; first end-to-end run against a real pilot application | Reporting Service (HTML + JSON + annotated Excel reports), pilot feedback collection | M4 (Execution results are available) | End-to-end run succeeds against a pilot application; all three report formats are accurate; pilot feedback is documented |
| **M6** | Phase 2 Hardening | PostgreSQL migration, concurrent runs, JWT auth, agent decomposition begins, Self-Healing Agent | PostgreSQL schema, task queue, JWT authentication, decomposed agents (Reasoning, Test Case Generator, Script Generator, POM Generator), Self-Healing Agent, human review gate | M5 (MVP is complete and stable) | Concurrent runs succeed; self-healing recovers from known selector failures; decomposed agents produce identical output to the consolidated originals |
| **M7** | Production Readiness | Full twelve-agent architecture, containerised services, multi-tenant cloud deployment | 12 independently deployable services, Docker containers, API gateway, Terraform modules (Azure/AWS), multi-tenant isolation, observability stack | M6 (Phase 2 is stable) | All services deploy independently; multi-tenant isolation is verified; cloud deployment is reproducible via Terraform |
| **M8** | Ecosystem Integration | CI/CD, Jira, Slack, BrowserStack, visual/API/accessibility/performance testing | Webhook trigger, Jira connector, Slack notifier, BrowserStack executor, axe-core module, Lighthouse/k6 module | M7 (Production platform is live) | At least two integrations are operational; CI/CD trigger → run → report loop is demonstrated |

## Specification Roadmap

Specifications are implemented in the following order, aligned to the milestones above:

| Order | Specification | Milestone |
|---|---|---|
| 1 | `001-project-setup.md` | M1 |
| 2 | `002-trigger-agent.md` | M1 |
| 3 | `003-ai-crawler-agent.md` | M2 |
| 4 | `004-dom-runtime-discovery.md` | M2 |
| 5 | `005-inventory-aggregator.md` | M2 |
| 6 | `006-test-design-agent.md` | M3 |
| 7 | `008-code-generation-agent.md` | M4 |
| 8 | `009-playwright-execution.md` | M4 |
| 9 | `010-reporting.md` | M5 |
| 10 | `007-human-review.md` | M6 (Phase 2) |

`007-human-review.md` is specified but deferred to Phase 2 because the MVP explicitly ships without a human-approval gate.

## Dependency Strategy

The implementation order follows a strict dependency chain where each stage produces an artifact that the next stage consumes. The sequencing is intentional:

**Trigger Agent first** because every run begins with input validation and strategy resolution. No downstream component can function without a validated run configuration.

**Crawl before Discovery** because the DOM + Runtime API Discovery Agent operates on the Raw Crawl Package produced by the AI Crawler Agent. There is nothing to analyse until the crawl is complete.

**Discovery before Inventory** because the Inventory Aggregator consumes the outputs of both analysis branches (DOM and API). The Inventory cannot be built until both analyses are finished.

**Inventory before Test Design** because the Test Design Agent receives its context exclusively from the Application Inventory. It never reads raw crawl data.

**Test Design before Code Generation** because the Code Generation Agent translates approved test cases into Playwright scripts. Without test cases, there is nothing to generate.

**Code Generation before Execution** because the Execution Service runs the generated Playwright project from the Shared Workspace. It cannot execute what has not been generated.

**Execution before Reporting** because the Reporting Service consumes execution results to produce reports. Without execution outcomes, there is nothing to report.

**Human review deferred to Phase 2** because the MVP targets trusted internal pilot applications. Adding a human-approval gate before execution would slow the feedback loop during the phase where rapid iteration is most valuable.

## Definition of Done

A milestone is complete only when all of the following criteria are met:

- **Specification implemented.** Every feature in the milestone's scope has been implemented per its approved specification.
- **Exit criteria met.** Every exit criterion defined for the milestone has been demonstrated and verified.
- **Documentation updated.** All affected documentation (ARCHITECTURE.md, PROJECT_STATE.md, relevant specs) reflects the new state.
- **ADR recorded (if required).** Any significant architectural decision made during the milestone has been recorded in `docs/06-ADR.md`.
- **PROJECT_STATE updated.** The project state tracker (`docs/04-PROJECT_STATE.md`) reflects the completed milestone and any changes to the status of individual modules.
- **Integration verified.** The milestone's output integrates correctly with the output of all preceding milestones.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **LLM output quality** | Generated test cases or scripts may be incorrect, incomplete, or hallucinated | Structured-output validation with schema enforcement and bounded retry; deterministic fallback templates; reference validation against the real Inventory |
| **Crawl reliability** | The crawler may fail to discover all pages, encounter login walls, or hang on slow applications | Page-count cap, configurable timeout, sequential crawling with per-page error isolation; manual inspection tooling (GET /inventory) to validate crawl quality early |
| **Browser compatibility** | Generated Playwright scripts may behave differently across Chromium, Firefox, and WebKit | MVP targets Chromium only; cross-browser execution is explicitly deferred to Phase 2 |
| **Selector fragility** | Selectors resolved during discovery may break if the application's DOM changes between crawl and execution | Ranked selector candidates (testid > role+name > id > css > text) with confidence scoring; Self-Healing Agent introduced in Phase 2 |
| **Prompt drift** | LLM behaviour may change across model versions or provider updates | Versioned prompt templates in source control; temperature locked to 0.1–0.3; all prompt changes gated through specification review |
| **Inventory growth** | The Application Inventory may grow too large for efficient LLM context windows | Scope-filtered inventory slices per LLM call; capped context size with deterministic summarisation; no agent receives the full raw inventory |
| **Small-model limitations** | DeepSeek R1 Distill Qwen 8B may lack the reasoning capacity for complex scenarios | Narrow, structured-output tasks per agent; bounded corrective retry; deterministic fallback; cross-page workflow generation deferred to Phase 2 |

## Success Metrics

| Metric | Target (MVP) |
|---|---|
| **Milestone completion** | All 5 MVP milestones completed within the 14-week target |
| **Crawl success rate** | Crawl completes without unrecoverable error against the pilot application |
| **Discovery accuracy** | Inventory correctly identifies pages, forms, navigation flows, and API endpoints visible during crawl |
| **Test case quality** | Generated test cases are syntactically valid, reference only real Inventory elements, and cover the requested scope |
| **Script compilation** | Generated Playwright scripts compile without errors on first generation (after retry) |
| **Execution success** | At least one end-to-end run completes from trigger through report against the pilot application |
| **Report accuracy** | HTML, JSON, and Excel reports contain consistent data and match the execution results |
| **Documentation completeness** | All Phase 0 documents are populated and reviewed before M1 implementation begins |

## Future Roadmap

### Phase 2 — Platform Expansion (Weeks 15–20)

Introduces concurrent runs, PostgreSQL, JWT authentication, human review gate, self-healing selectors, and partial-refresh crawling. The five consolidated MVP agents begin decomposing into their specialised originals. The platform becomes suitable for small QA teams with multiple applications.

### Production — Enterprise Readiness (Weeks 21–28)

Full twelve-agent architecture restored as independently deployable, containerised services. Multi-tenant isolation with row-level security. Cloud deployment via Terraform (Azure or AWS). API gateway with rate limiting and observability stack. CI/CD integration begins.

### Ecosystem — Extended Capabilities (Weeks 29+)

BrowserStack cloud grid, visual regression testing, API-level test generation, accessibility testing, performance testing, Jira and Slack integrations. The platform becomes a full SDLC citizen.

For architectural details of how the system evolves through each phase, see `docs/02-ARCHITECTURE.md`.

## Related Documents

| Document | Purpose |
|---|---|
| `docs/00-AI_CONTEXT.md` | AI onboarding — current sprint status and next planned tasks |
| `docs/01-PROJECT_OVERVIEW.md` | High-level phase summary and business roadmap |
| `docs/02-ARCHITECTURE.md` | Architecture evolution across MVP, Phase 2, and Production |
| `docs/04-PROJECT_STATE.md` | Current implementation status and milestone progress tracking |
| `docs/05-CODING_STANDARDS.md` | Coding conventions and quality standards |
| `docs/06-ADR.md` | Architecture Decision Records |
| `docs/specs/` | Feature specifications in implementation order |
| `docs/contracts/` | Data contracts for cross-component interfaces |
