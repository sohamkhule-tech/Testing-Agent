# Project Overview

## Document Metadata

| Field | Value |
|---|---|
| Document | Project Overview |
| Document ID | SDD-PROJ-001 |
| Version | 1.0 |
| Status | Draft |
| Owner | Platform Architecture Team |
| Last Updated | 2026-07-20 |
| Review Frequency | Quarterly or on major milestone completion |

## Project Vision

The platform aims to become the standard AI-powered functional testing layer for web applications — a tool that any QA engineer, developer, or product team can point at a web application and receive a comprehensive, executable test suite in minutes instead of weeks.

Long-term, the platform evolves into a production-grade, multi-tenant service that integrates into the wider SDLC toolchain: triggering test runs from CI/CD pipelines, filing defects in Jira, notifying teams via Slack, and providing a central inventory of application structure that grows smarter with every run.

## Problem Statement

Functional testing of modern web applications faces several persistent challenges:

**Manual testing does not scale.** QA teams spend the majority of each release cycle manually verifying the same workflows. Regression cycles grow longer as applications grow more complex. Teams are forced to choose between coverage and velocity.

**Test automation is expensive.** Writing and maintaining automated UI tests requires specialised scripting knowledge. Page Object Models, selector strategies, and test data management each demand significant engineering investment. Test suites become brittle — a single DOM change can break hundreds of tests — and the maintenance burden grows faster than the test coverage.

**Automation expertise is scarce.** Many teams have deep domain knowledge but limited automation experience. The gap between "knowing what to test" and "being able to automate it" is a bottleneck that slows delivery.

**Existing AI testing tools are opaque.** Current generation tools treat testing as a black box — they generate tests but offer little visibility into why certain tests were created, how selectors were resolved, or whether the output can be trusted. This lack of transparency makes it difficult for QA teams to adopt AI-assisted testing with confidence.

This platform addresses these problems by combining AI reasoning with deterministic execution, producing transparent, reviewable, and maintainable test artefacts that teams can trust and iterate on.

## Project Objectives

| Objective | Description |
|---|---|
| Reduce manual testing effort | Automate functional test creation so QA teams focus on edge cases and exploratory testing instead of regression script authoring |
| Increase automation coverage | Enable teams to achieve meaningful coverage without proportional engineering investment |
| Produce reusable test assets | Generate Page Object Models and test scripts that teams can maintain, extend, and check into their own repositories |
| Improve testing consistency | Eliminate variability in test quality by using structured inventory data and deterministic code generation rather than individual script authoring |
| Enable AI-assisted test generation | Let non-specialists describe test intent in natural language and receive production-quality automated tests |
| Accelerate feedback loops | Shrink the gap between "a change is merged" and "the regression results are known" |

## Scope

| In Scope | Out of Scope (MVP) |
|---|---|
| AI-assisted functional test generation | Mobile application testing (iOS, Android) |
| Web application crawling and structure discovery | Performance / load testing |
| Playwright script generation | Security / penetration testing |
| Page Object Model generation | Desktop application testing |
| Structured test reporting (HTML, JSON, Excel) | Production-grade multi-tenancy |
| Single-application, single-user execution | CI/CD integration (Phase 2+) |
| Local or same-host execution | Real-device / cloud browser grid (Phase 2+) |
| Support for standards-compliant HTML applications | Heavily custom / canvas-rendered UIs (Phase 2+) |

## Target Users

- **QA Engineers** — create automated test suites by providing a URL, credentials, and a natural-language prompt; review and approve generated test cases before execution
- **Test Automation Engineers** — extend and customise generated Page Object Models and scripts; integrate outputs into existing test frameworks
- **Developers** — quickly validate that new features work as expected before handing off to QA; understand application structure through the generated inventory
- **Technical Architects** — evaluate the platform for adoption within their organisation; review the architecture and integration points
- **Internal Product Teams** — use the platform during internal pilot programmes to validate the tool against real-world applications before wider rollout

## Expected Benefits

### Business

- Faster release cycles through reduced regression testing lead time
- Lower cost per test case through automation of script generation
- Improved product quality through broader and more consistent test coverage
- Reduced dependency on scarce automation engineering resources

### Engineering

- Applications are automatically documented through the generated Inventory (pages, forms, APIs, navigation flows)
- Teams receive maintainable Page Object Models and test scripts, not opaque AI output
- Test assets are versioned and reusable across releases

### QA

- Shift from script authoring to test design and exploratory testing
- Natural-language test creation lowers the barrier to automation
- Transparent, reviewable test cases with clear selector resolution and scope boundaries
- Excel-based workflow for test case review and annotation familiar to most QA teams

### Future AI Capabilities

- Self-healing selectors that adapt to DOM changes without human intervention (Phase 2)
- Cross-page workflow generation that reasons about complex user journeys (Phase 2)
- Visual regression detection layered on top of functional test screenshots (Production)
- API-level test generation from discovered runtime endpoints (Production)

## Project Principles

**Specification First.** Every feature is defined by a written specification before any implementation begins. Specifications are the source of truth — code follows them, not the reverse.

**AI Assists, Humans Control.** AI generates test cases, scripts, and page objects, but humans review and approve them. The platform is a tool for QA engineers, not a replacement for their judgement.

**Deterministic Execution.** AI agents never execute tests. AI generates artefacts; deterministic services execute them. This boundary ensures that a defect in the AI layer never affects live test execution, and a Playwright crash never corrupts agent state.

**Reusable Artifacts.** Every output — the Application Inventory, Page Object Models, test scripts — is designed to be reused, versioned, and maintained by humans. The platform generates engineer-friendly assets, not opaque artefacts.

**Modular Design.** The system is built as a pipeline of specialised agents and services, each with a single responsibility. This makes the platform testable, debuggable, and extensible without cascading changes.

**Incremental Delivery.** The platform ships in three tiers: MVP (prove the concept end-to-end), Phase 2 (harden and expand), and Production (enterprise-scale). No tier builds capability that belongs in a later tier.

**Transparency.** Every decision the AI makes — which pages were discovered, which selectors were chosen, why a test case was created — is surfaced in a structured, auditable form. The platform is designed to be trusted, not treated as a black box.

## High-Level Functional Flow

```
QA Engineer provides: URL + Credentials + Testing Prompt
                           ↓
              Platform crawls the application
              and discovers its structure
                           ↓
              Platform designs test cases
              based on the discovered inventory
                           ↓
              Platform generates Playwright
              test scripts and Page Object Models
                           ↓
              Platform executes the tests
              against the live application
                           ↓
              Platform produces a structured
              report with results and artefacts
```

This flow represents the end-to-end process from the user's perspective. The internal multi-agent pipeline that powers each step is described in `docs/02-ARCHITECTURE.md` and the reference architecture documents.

## Success Criteria

The MVP is successful when it can:

- Accept a target application URL, credentials, and a natural-language testing prompt
- Crawl the application and discover its page structure, forms, navigation flows, and runtime API calls
- Produce a structured, versioned Application Inventory that humans can inspect and validate
- Generate meaningful test cases across multiple categories (happy path, validation, error-path)
- Produce Playwright test scripts and Page Object Models that compile and run without modification
- Execute the generated tests against the live application
- Produce a structured report (HTML, JSON, and Excel) with pass/fail outcomes, screenshots, and execution details
- Support repeated runs against the same application without re-crawling (inventory reuse)

## Project Roadmap Summary

| Phase | Focus | Duration |
|---|---|---|
| **MVP (Current)** | Single-application, single-user, local execution. 5 consolidated AI agents. SQLite. End-to-end pipeline from crawl to report. | Weeks 1–14 |
| **Phase 2** | PostgreSQL migration, concurrent runs, JWT auth. Agent decomposition begins. Self-healing introduced. Human review gate. | Weeks 15–20 |
| **Production** | Full 12-agent architecture. Containerised services. Multi-tenant isolation. Cloud deployment. CI/CD, Jira, Slack integrations. | Weeks 21–28+ |
| **Ecosystem** | BrowserStack, visual testing, API testing, accessibility testing modules. | Weeks 29+ |

See `docs/03-ROADMAP.md` for the detailed milestone breakdown.

## Related Documents

| Document | Purpose |
|---|---|
| `docs/00-AI_CONTEXT.md` | AI onboarding — first document every AI agent reads before implementation |
| `docs/02-ARCHITECTURE.md` | Maintained architecture summary and system design |
| `docs/03-ROADMAP.md` | Detailed milestone timeline and delivery plan |
| `docs/04-PROJECT_STATE.md` | Current implementation status and progress tracking |
| `docs/05-CODING_STANDARDS.md` | Code style, conventions, and error handling guidelines |
| `docs/06-ADR.md` | Architecture Decision Records |
| `docs/specs/` | Feature specifications (source of truth for implementation) |
| `docs/contracts/` | Data contracts defining cross-module interfaces |
| `docs/references/Executive-Architecture-Design-Document-MVP.docx` | Full architecture reference |
| `docs/references/Agentic-AI-Testing-Platform-SDD-HLD-MVP-5-Agent-Revision.docx` | SDD & HLD reference |
