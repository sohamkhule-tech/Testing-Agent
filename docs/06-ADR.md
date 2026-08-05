# Architecture Decision Records

## Document Metadata

| Field | Value |
|---|---|
| Document | Architecture Decision Records |
| Document ID | SDD-ADR-001 |
| Version | 1.0 |
| Status | Living Document |
| Owner | Platform Architecture Team |
| Last Updated | 2026-07-20 |
| Review Frequency | Ongoing — updated with each new ADR |

## Purpose

Architecture Decision Records capture the rationale behind every significant architectural choice in this project. They exist to answer one question: **why is the system designed this way?**

ADRs provide:

- **Historical context.** Months after a decision is made, the record explains the problem, the options considered, and the reasoning behind the chosen approach. This prevents future contributors from asking "why did they do it this way?" or repeating discarded alternatives.

- **Future maintainability.** When a decision needs to be revisited — because requirements changed, a new technology emerged, or a constraint was lifted — the ADR provides the foundation for evaluating whether the original reasoning still holds.

- **Onboarding.** New team members and AI agents can read the ADR log to understand the architectural evolution without reverse-engineering the code or interrupting the team.

- **Auditability.** Every architectural decision is traceable to a written record. This is essential for security reviews, compliance requirements, and post-mortem analysis.

- **Consistent evolution.** By requiring a written record for every significant decision, the project avoids accidental architecture — changes that happen without conscious deliberation.

ADRs complement the Architecture document (`docs/02-ARCHITECTURE.md`). The Architecture document describes the current state of the system. ADRs record **why** it became that way.

## What Requires an ADR

Any decision that has a lasting impact on the system's architecture, development process, or operational profile requires an ADR. Examples include:

| Category | Examples |
|---|---|
| **Framework or language** | Adding a new framework, changing the primary language, adopting a new runtime |
| **Database or storage** | Changing the database engine, adding a cache layer, introducing a message queue, changing the storage format |
| **Architecture pattern** | Shifting from monolith to services, adopting event-driven architecture, introducing CQRS or event sourcing |
| **Major dependency** | Adding a significant third-party library that affects the architecture (e.g., an AI framework, a workflow engine) |
| **Deployment strategy** | Changing the deployment target, adopting containers, introducing orchestration |
| **Security model** | Changing authentication or authorisation strategy, adopting a new secrets management approach, modifying the trust boundary |
| **Communication protocol** | Changing how components communicate, introducing an API gateway, adopting gRPC or message passing |
| **Breaking interface change** | Modifying a cross-component contract in a way that requires changes in multiple consumers |
| **LLM strategy** | Changing the LLM provider, the model family, the prompting strategy, or the temperature/retry policy |
| **Agent architecture** | Splitting, merging, or removing an agent; changing how agents are orchestrated |
| **Storage strategy** | Changing the inventory format, the artifact storage approach, or the data retention policy |
| **Development process** | Changing the specification workflow, the review process, or the Definition of Done |

When in doubt, write an ADR. A one-page record is cheap; rediscovering the rationale months later is expensive.

## What Does NOT Require an ADR

| Category | Examples |
|---|---|
| **Bug fixes** | Correcting incorrect behaviour without changing the design |
| **Variable renames** | Improving naming without changing semantics |
| **Refactoring** | Restructuring code without changing external behaviour |
| **Formatting** | Code style changes, linter rule adjustments |
| **Minor optimizations** | Performance improvements that do not change interfaces or behaviour |
| **UI tweaks** | Visual changes, layout adjustments, component reorganisation |
| **Specification changes** | Updating a specification to reflect a clarified requirement |
| **Implementation details** | How a specific function works, which algorithm is used internally |
| **Routine dependency upgrades** | Patch or minor version updates that do not change the public API or behaviour |
| **Test additions** | Adding tests for existing behaviour |

If a change does not affect how the system works, what it depends on, or how it is deployed, it does not require an ADR.

## ADR Lifecycle

Every ADR progresses through the following states:

| Status | Definition |
|---|---|
| **Proposed** | The ADR has been drafted and is under review. No implementation has begun. |
| **Accepted** | The ADR has been reviewed and approved. Implementation may proceed. |
| **Implemented** | The decision has been implemented and verified. The system reflects the ADR. |
| **Superseded** | A later ADR has replaced this decision. The original ADR remains for historical context but is no longer active. |
| **Deprecated** | The decision is no longer recommended for new work but existing implementations remain. |
| **Rejected** | The ADR was reviewed and declined. The record is kept to prevent repeating the analysis. |

An ADR moves from Proposed to Accepted after review by the architecture team. It moves to Implemented when the change is complete and verified. Superseded and Deprecated are set by subsequent ADRs that override or phase out the original decision.

## ADR Numbering

ADRs are numbered sequentially: **ADR-001**, **ADR-002**, **ADR-003**, and so on.

- Numbers are never reused. If an ADR is Rejected, the number is not reassigned.
- Numbers are never renamed. Once an ADR is assigned a number, that number permanently refers to that decision.
- The number is assigned when the ADR is first drafted (Proposed status), not when it is Accepted.
- If two ADRs are drafted concurrently, the first to reach Proposed status receives the lower number.

## ADR Template

Every ADR must follow this structure exactly. Sections marked with * are required; all others are optional but encouraged.

```markdown
### ADR-XXX

*Title:* A short, descriptive name (e.g. "Select Playwright for Browser Automation")

*Status:* Proposed | Accepted | Implemented | Superseded | Deprecated | Rejected

*Date:* YYYY-MM-DD

*Authors:* Name(s) of the person(s) who authored the ADR

---

### Context

What problem prompted this decision? What constraints, requirements, or assumptions
are relevant? What is the current state of the system that makes this decision necessary?

This section should provide enough background that someone reading the ADR in isolation
can understand the situation without reading other documents.

---

### Decision

What was decided? State the decision clearly and unambiguously.

"This ADR decides to adopt Playwright as the browser automation engine for all
UI-level test execution."

---

### Alternatives Considered

What other options were evaluated? Why were they rejected?

List each alternative with a brief explanation of why it was not chosen. This is
the most valuable section for future readers who may wonder "why didn't they use X?"

---

### Consequences

What changes as a result of this decision?

- What must be built or changed?
- What must be removed or deprecated?
- What risks are introduced?
- What opportunities are created?

---

### Trade-offs

What was sacrificed? Every architectural decision involves trade-offs. Be explicit.

- What was prioritised (e.g. speed, cost, maintainability)?
- What was deprioritised (e.g. scalability, flexibility)?
- What is the downside of this decision?

---

### References

- Links to related ADRs (e.g. "Supersedes ADR-012")
- Links to relevant specifications
- Links to external resources (documentation, RFCs, articles)

---

### Future Review

When should this decision be revisited? What conditions would trigger a review?

"Revisit when the pilot application inventory exceeds 100 pages, or when Playwright
releases a breaking change in its test runner interface."
```

## ADR Writing Guidelines

**Be concise.** An ADR should be as short as possible while still capturing the decision context. Most ADRs fit on one to two pages. If an ADR exceeds three pages, consider whether the scope is too broad.

**Describe the problem first.** The reader cannot evaluate the decision without understanding the problem. Context comes before the decision in the template for a reason.

**Explain why, not what.** The decision itself is usually a single sentence. The value of the ADR is in the reasoning — why this option was chosen over the alternatives.

**Explain alternatives thoroughly.** The "Alternatives Considered" section is the most valuable part of any ADR for future readers. Every plausible alternative should be listed with a brief explanation of why it was rejected.

**Be honest about trade-offs.** Every architectural decision involves trade-offs. Explicitly stating what was sacrificed builds trust and helps future readers evaluate whether the trade-off is still appropriate for their context.

**Never describe implementation.** An ADR explains what was decided and why. It does not explain how to implement it. Implementation details belong in specifications, not ADRs.

**Focus on architectural reasoning.** The audience is future architects and technical leads, not current implementers. Write for someone who needs to understand the system's evolution, not someone who needs to build a specific feature.

## Decision Criteria

When evaluating alternatives for an ADR, consider the following criteria. Not all criteria apply to every decision; focus on the ones relevant to the specific context.

| Criterion | Question |
|---|---|
| **Maintainability** | How easy is this to change, extend, and debug over the system's lifetime? |
| **Scalability** | Does this support the expected growth in users, applications, runs, and data volume? |
| **Reliability** | How resilient is this to failures? What happens when it fails? |
| **Security** | Does this meet the security requirements? What attack surface does it introduce? |
| **Performance** | How does this affect system latency, throughput, and resource usage? |
| **Operational complexity** | How much effort is required to operate, monitor, and troubleshoot this in production? |
| **Developer experience** | How does this affect the team's productivity, onboarding time, and day-to-day workflow? |
| **Cost** | What is the direct and indirect cost of this decision — licenses, infrastructure, team time? |
| **Extensibility** | Does this make it easier or harder to add future capabilities? |
| **AI compatibility** | Does this work well with AI-assisted development and AI agent behaviour? |

## Initial ADR Register

| ADR | Title | Status |
|---|---|---|
| ADR-001 | 5 AI Agents + 3 Deterministic Services Architecture for MVP | Accepted |

---

### ADR-001

**Title:** 5 AI Agents + 3 Deterministic Services Architecture for MVP

**Status:** Accepted

**Date:** 2026-07-23

**Authors:** Platform Architecture Team

---

### Context

The platform must process web applications through multiple stages: discovery, analysis, test design, code generation, execution, and reporting. A fundamental architectural question arose: should all components be implemented as AI agents, or should responsibilities be split between AI-powered reasoning components and deterministic processing components?

Early designs considered:
- A fully AI-driven pipeline (all 9 components as AI agents)
- A hybrid approach distinguishing AI reasoning from deterministic processing
- A minimal AI approach (fewer AI components, more deterministic logic)

The decision impacts technology stack, cost model, error handling patterns, testing strategies, and deployment architecture.

---

### Decision

**The MVP implements a hybrid architecture consisting of:**

**5 AI Agents:**
1. Trigger Agent — Input validation and run orchestration
2. AI Crawler Agent — Application crawling and discovery
3. DOM + Runtime Discovery Agent — DOM analysis and API endpoint discovery
4. Test Design Agent — Test scenario and test case generation
5. Code Generation Agent — Playwright code and Page Object Model generation

**3 Deterministic Services:**
1. Inventory Aggregator Service — Data merging, deduplication, and normalization
2. Execution Service — Playwright test execution and artifact collection
3. Reporting Service — Report generation and analytics

**1 Human Workflow Gate (Phase 2):**
- Human Review Workflow Gate — Human approval workflow for test cases before code generation

**Design Principle:** AI Generates. Services Execute. Humans Approve.

---

### Alternatives Considered

**Alternative 1: All 9 Components as AI Agents**

Implement Inventory Aggregator, Execution, and Reporting as AI agents with LLM inference.

*Rejected because:*
- Unnecessary LLM inference costs for deterministic operations (merge, dedupe, execution orchestration)
- Increased latency for operations that don't benefit from AI reasoning
- Harder to debug and test (non-deterministic behavior in deterministic processes)
- Higher infrastructure complexity (LLM context management for simple operations)

**Alternative 2: Fewer AI Agents (AI Only for Test Design and Code Generation)**

Use AI only for Test Design and Code Generation; make Trigger, Crawler, and DOM Discovery deterministic.

*Rejected because:*
- Crawler benefits from AI for handling dynamic navigation patterns and SPA routing
- DOM Discovery benefits from AI for semantic component classification
- Trigger Agent's scope classification and strategy resolution benefits from AI reasoning
- Would require complex heuristic rules that AI handles more flexibly

**Alternative 3: Separate Human Review as an Agent**

Treat Human Review as an AI agent that assists human reviewers.

*Rejected because:*
- Human Review is fundamentally a human workflow with approval logic, not an AI reasoning task
- Mislabeling it as an "agent" creates architectural confusion
- The UI and approval workflow don't align with the agent pattern

---

### Consequences

**Positive:**
- Clear architectural boundary between AI reasoning and deterministic execution
- Lower cost (no LLM inference for deterministic operations)
- Better debuggability (deterministic services have predictable behavior)
- Easier testing (deterministic services can be unit tested without LLM mocks)
- Clearer deployment strategy (AI agents scale differently from services)
- Technology stack clarity (AI framework for agents, standard services for deterministic logic)

**Negative:**
- Two distinct component types require documentation clarity
- Team members must understand which components are AI agents vs services
- Specifications must clearly distinguish agent specs from service specs

**Requires:**
- Consistent terminology across all documentation
- Clear visual distinction in pipeline diagrams
- Separate prompt engineering for AI agents vs service documentation

---

### Trade-offs

**Prioritized:**
- Cost efficiency (avoid unnecessary LLM calls)
- Debuggability (deterministic services are easier to debug)
- Testing (deterministic services are easier to test)

**Deprioritized:**
- Architectural uniformity (accepting two component types for better cost/performance)
- AI-everywhere approach (using AI only where it adds value)

---

### References

- `docs/02-ARCHITECTURE.md` — Canonical architecture document
- `docs/references/Agentic-AI-Testing-Platform-SDD-HLD-MVP-5-Agent-Revision.docx` — Reference architecture
- All specifications (001-010) now aligned with this decision

---

### Future Review

Revisit this decision when:
- MVP feedback indicates cost/performance issues
- Phase 2 agent decomposition begins (5 agents → 12 agents)
- New AI capabilities make deterministic services candidates for AI enhancement
- Platform scales to production multi-tenancy

---

## Recording Process

The workflow for creating and implementing an ADR follows these steps:

```
Problem identified
       ↓
Evaluate options against decision criteria
       ↓
Architecture review (informal discussion with the team)
       ↓
ADR drafted using the template
       ↓
ADR submitted for review (Proposed status)
       ↓
Reviewed and approved (Accepted status)
       ↓
Implementation proceeds
       ↓
Implementation verified (Implemented status)
       ↓
PROJECT_STATE updated to reflect the completed ADR
```

If the ADR is **Rejected**, the record remains in the register with the rejected status and a brief explanation of why it was declined. This prevents the same analysis from being repeated.

If an ADR is **Superseded**, the new ADR must reference the original ADR it supersedes. The original ADR's status is updated to Superseded.

## Relationship with Other Documents

- **`docs/02-ARCHITECTURE.md`** describes the current state of the system. ADRs record **why** it became that way. When an ADR is Implemented, the Architecture document should be updated to reflect the new state.

- **`docs/specs/`** define **what** will be built. An ADR may be recorded before a specification is written (when the architecture decision precedes the feature) or during implementation (when a decision emerges during development). In either case, the specification implements the ADR's decision.

- **`docs/04-PROJECT_STATE.md`** tracks the status of all project work. When an ADR reaches Implemented status, the PROJECT_STATE document should be updated to reflect the completed architectural change.

- **`docs/00-AI_CONTEXT.md`** lists important architectural decisions as a quick reference. When an ADR is Accepted or Implemented, the AI_CONTEXT decisions list may need to be updated to reflect the new decision.

## AI Instructions

When an AI agent identifies a situation that may require an architectural decision, it must follow this procedure:

1. **Do not silently implement.** If during implementation the AI encounters a situation that requires a decision not covered by existing specifications or ADRs, it must not proceed without recording the decision.

2. **Identify the need for an ADR.** Evaluate whether the situation meets the criteria in "What Requires an ADR." If in doubt, recommend an ADR.

3. **Draft the ADR.** Using the template above, draft the ADR with the Context, Decision, Alternatives Considered, and Consequences sections filled in to the best of the AI's knowledge. Be concise — a draft is sufficient for human review.

4. **Flag for review.** Present the drafted ADR for human review before proceeding with implementation. The ADR should be Proposed at this stage.

5. **Proceed only after acceptance.** Once the ADR is Accepted, implementation may continue. If the ADR is Rejected, do not implement the decision it proposed.

AI agents should not create unnecessary ADRs. Minor implementation choices, bug fixes, and routine changes that do not affect the architecture do not require ADRs. When in doubt, recommend rather than decide.

## Related Documents

| Document | Purpose |
|---|---|
| `docs/00-AI_CONTEXT.md` | AI onboarding — includes a summary of important architectural decisions |
| `docs/01-PROJECT_OVERVIEW.md` | Business context and project objectives |
| `docs/02-ARCHITECTURE.md` | Maintained architecture summary — the current state that ADRs evolve |
| `docs/03-ROADMAP.md` | Delivery strategy — ADRs may affect or be affected by the roadmap |
| `docs/04-PROJECT_STATE.md` | Current implementation status — updated when ADRs are completed |
| `docs/05-CODING_STANDARDS.md` | Engineering conventions — ADRs may introduce new standards |
| `docs/specs/` | Feature specifications — implement decisions recorded in ADRs |
| `docs/contracts/` | Data contracts — may be affected by ADR decisions |
