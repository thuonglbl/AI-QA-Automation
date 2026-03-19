---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments: []
date: 2026-03-13
author: [redacted]
---

# Product Brief: AI QA Automation

<!-- Content will be appended sequentially through collaborative workflow steps -->

## Executive Summary

AI QA Automation is an innovative, enterprise-grade automated testing infrastructure powered by a Multi-Agent architecture, designed for organizations with strict data security requirements. We combine the power of on-premises Large Language Models (vLLM, proxied through the company's internal server to the on-premises AI server — with a signed data security commitment) with a customized version of the open-source Browser Use core. For teams requiring advanced LLM capabilities, the system also integrates **Claude Code Enterprise** (Anthropic), operated under a signed Enterprise Security Agreement that contractually governs data handling, retention, and confidentiality. The system empowers Business Analysts and QA Engineers to automatically translate requirements from Confluence or Jira into intelligent, executable test cases. By strategically blending human oversight (Human-in-the-Loop) at critical junctures with AI autonomy, the product radically reduces scripting time, mitigates the brittleness of traditional test automation, and provides a contractually-backed data security posture for internal operations. This approach delivers significant Return on Investment (ROI) by leveraging open-source engines and existing enterprise agreements while avoiding exorbitant additional licensing fees and vendor lock-in associated with commercial SaaS testing platforms.

---

## Core Vision

### Problem Statement

Traditional automation testing requires significant human effort to read and comprehend requirements from documentation (Confluence) or tickets (Jira), manually write test cases, program automation scripts (Selenium, Playwright...), and finally maintain them when the UI changes. This process is time-consuming, expensive, and fragile when requirements shift continuously. While current AI tools can assist in writing code, chaining the entire business flow from "understanding requirements -> generating test cases -> writing automation scripts -> executing tests on the browser" often lacks completeness, fails to ensure data security (even on-premises environments often act as proxies to partner clouds), and misses the necessary interaction and control from QA engineers at critical junctures. Furthermore, without proper constraints, LLMs often suffer from "hallucinations," generating test cases based on non-existent business rules, forcing QAs to spend more time debugging the AI's output than if they had written it themselves.

### Problem Impact

- Bottlenecks in the QA phase slow down product releases (Time-to-market).
- QA engineers spend time on repetitive tasks (writing boilerplate test cases, maintaining scripts) instead of focusing on strategic, edge-case, and exploratory testing.
- Enterprises with strict security requirements face compounding risks: even "on-premises" or private-cloud LLM proxies can leak sensitive data from business documents if sent unmasked.
- Fully autonomous AI agents often get stuck at authentication steps like static CAPTCHAs, OTPs, or MFAs, or fail due to timeouts when waiting for necessary human approvals, causing automation pipelines to collapse.
- Automation test suites become "flaky" and brittle; minor DOM/CSS class changes by developers cause scripts (relying on hardcoded XPaths/Selectors) to break en masse, leading to high maintenance overhead.

### Why Existing Solutions Fall Short

- **Lack of Input Flexibility:** Automated test case generation tools rarely handle unstructured, mixed data from multiple sources like Confluence (Requirements) and Jira (Tickets) effectively. Raw HTML inputs often overwhelm LLM Context Windows.
- **Disconnect Between AI and Automation Tools:** AI can generate test scripts, but execution remains separate, requiring complex environment setups and resulting in disjointed reporting structures.
- **Naïve Data Handling:** Existing tools often blindly send raw, unstructured proprietary data to language models without intermediate sanitization, risking severe data leaks across internal or partner networks.
- **Synchronous Fragility:** When encountering errors or security checkpoints (CAPTCHA, MFA), or requiring QA approvals, existing synchronous automation flows "time-out" and fail, rather than intelligently pausing to accommodate a "human-in-the-loop" reality.

### Proposed Solution

AI QA Automation resolves these issues with a robust Multi-Agent architecture and a dual-LLM strategy with contractually-backed security, customized on top of the Browser Use platform:

**LLM Security Architecture:**

- **On-Premises vLLM path:** The company's internal server acts as a proxy routing requests to the **on-premises AI server ([REDACTED_LOCATION])**. The on-premises AI provider has signed a formal data security commitment with the company, ensuring data residency and confidentiality obligations are legally binding.
- **Claude Code Enterprise path:** For tasks requiring advanced LLM reasoning, the system integrates Claude Code via Anthropic's **Enterprise License**, operated under a signed Enterprise Security Agreement governing data handling, retention policies, and non-use of customer data for model training.

1. **Business Analyst Agent:** Automatically reads data from Confluence or Jira via the company's **Internal MCP (Azure AD connected)**. A **Content Parsing & Chunking Engine** first cleans and structures raw HTML into digestible Markdown chunks to prevent context window overflow. Crucially, a **Data Masking Engine** sanitizes sensitive data (PII, proprietary keywords) *before* it hits any LLM (whether cloud-based Claude or partner-proxy on-premises vLLM), ensuring universal data safety. The Agent then dynamically groups and prioritizes generated MD Test Cases, embedding **Mandatory Traceability Links** to the exact source paragraphs in Jira/Confluence, making bulk review manageable and verifiable for QAs before approval.
2. **Automation Scripter Agent:** Instead of forcing rigid legacy formats (like Cucumber/Gherkin), once MD Test Cases are QA-approved, this agent processes them into an **AI-optimized Goal-Oriented Plan**. This plan is a structured YAML/JSON artifact composed of high-level semantic objectives (e.g., `{ "goal": "Verify login flow", "steps": ["Navigate to /login", "Enter valid credentials", "Assert dashboard is visible"] }`) rather than low-level DOM selectors or hardcoded XPaths. The Executor Agent interprets these goals dynamically at runtime, triggering the next QA Review gate for strategy validation rather than syntax checking. This format is intentionally human-readable to support QA review without programming skills.
3. **Browser Executor Agent:** Takes the Goal-Oriented Plan as input, leveraging the Browser Use Core UI/Backend (via an Adapter interface) to interact with the browser. Crucially, it shifts from brittle DOM-based assertions to **Vision-based/Semantic Assertion**: the AI analyzes screenshots and semantic DOM context to determine Pass/Fail based on visual and logical outcomes rather than CSS selectors. *Known limitations:* visual assertion accuracy depends on LLM quality and UI complexity; highly dynamic UIs or canvas-based rendering may require fallback DOM-level checks. False positive/negative rates will be tracked per test suite and used to tune confidence thresholds. The agent seamlessly updates the Report to the Web UI after each step.
4. **Asynchronous Human-in-the-Loop Core:** QA engineers configure environments and credentials (via a secure Vault) on the Web UI. The system employs **Asynchronous Hibernation**: at approval gates or when encountering MFA/CAPTCHA, the pipeline serializes its full execution state (browser session snapshot, completed steps, pending objectives) to persistent storage and sends an **Asynchronous Ping** (Slack/Teams notification with deep link) prompting the QA to intervene. The pipeline can hibernate for up to **48 hours** before auto-expiry; QA managers are notified after **4 hours** of inactivity. Upon QA intervention via the Web UI, the pipeline resumes from the exact serialized state. If the hibernation deadline is exceeded, the run is marked as `EXPIRED` with a full audit trail for post-mortem analysis.

### Key Differentiators

- **Contractually-Backed Dual-LLM Security Posture:** Rather than relying solely on technical controls, the system's security model is grounded in binding legal agreements at every LLM touchpoint. The on-premises vLLM path routes through the company's internal proxy to the **on-premises AI server ([REDACTED_LOCATION])**, covered by a signed data security commitment. The Claude Code Enterprise path operates under Anthropic's **Enterprise Security Agreement**, which contractually prohibits use of customer data for model training and defines data retention limits. On top of these agreements, a mandatory **Data Masking Engine** sanitizes sensitive data before any content reaches an LLM endpoint — using a two-layer approach: (1) a **rule-based pattern matcher** for deterministic PII (email, NRIC, account numbers, proprietary product codes defined via config), and (2) an **LLM-assisted classifier** for contextual sensitivity detection. Masked tokens are replaced with typed placeholders (e.g., `[EMAIL_1]`) and restored in the final report output. False negative risk is mitigated by a configurable sensitivity threshold; false positive risk is managed by an allowlist for business terms that should not be masked. Seamless integration with the **Internal Azure AD-backed MCP** further hardens the data ingestion pipeline, making this viable for strictly regulated industries. For organizations not using Azure AD, an alternative OIDC/SAML-compatible auth adapter is planned for v2.
- **Open-Core Cost Leverage:** Avoiding reinventing the wheel and massive R&D costs. The system uses an Adapter-Pattern to leverage the existing Browser Use interface and backend agents on the internal repository. This insulates our custom logic, ensuring we pull future upstream updates for free without breaking the system, drastically reducing Total Cost of Ownership (TCO) compared to SaaS alternatives.
- **Goal-Oriented, Vision-Based Execution:** Breaking free from the fragility of traditional TDD scripts and DOM selectors. By merging AI-optimized planning with Semantic/Visual Assertions, the system tests logic and visual states just like a human, inherently healing itself when underlying code structures change without altering the visual output.
- **Asynchronous "Hibernating" Flow & Traceability:** Transforming QA from a "script coder" into an "overseer." The system gracefully pauses (hibernates) during manual QA review gates or when encountering CAPTCHAs/MFAs. Mandatory LLM-to-Source Traceability prevents AI hallucinations.
- **Self-Healing Execution Engine:** Moving beyond brittle XPath/CSS selectors, the customized Browser Executor Agent utilizes visual and semantic DOM understanding to achieve self-healing capabilities when UIs undergo minor modifications, drastically reducing maintenance overhead.
- **Modern & Modular Architecture:** A robust Common Lib layer (Logging, Tracking, Utils, Tests) strictly decoupled from the core Browser Use engine, combined with flexible multi-source inputs (Confluence, Jira, or both concurrently) ensures the system outputs standardized artifacts regardless of input chaos.

## Target Users

### Primary Users

#### Manual QA Engineer ("The Reviewer & Driver")

- **Context & Motivation:** Manual QAs who excel at understanding business logic, edge cases, and user flows but lack deep programming skills for traditional automation frameworks (Selenium, Playwright). They are frustrated by the mind-numbing repetition of executing the same regression tests across multiple browsers and environments.
- **Pain Point:** They are trapped in a manual testing cycle. Their organization rarely approves budgets for expensive, enterprise-grade AI testing SaaS products, leaving them without modern tools. Configuration for existing open-source automation tools is too complex. They also fear being held accountable for AI "hallucinations" if they cannot easily verify the source of AI-generated test plans.
- **Required Skill Level:** Light technical familiarity — the user must be comfortable with Confluence/Jira navigation, reading structured Markdown, and following a Web UI workflow. No scripting or coding skills are required for day-to-day operation. Initial environment setup (Vault configuration, MCP connection) is performed once by a technical team member (DevOps/Lead QA) and does not require ongoing involvement from manual QAs.
- **Success Vision:** A "reviewer-first" platform where manual QAs interact entirely through a Web UI — reviewing AI-generated test plans in plain English (Markdown), approving execution strategies, and intervening at HITL gates. **Contextual Explainability** (traceability links back to exact source requirements) lets them act as the authoritative "Safety Net" without needing to read or write any code. They are the "driver" steering the AI, not the "mechanic" maintaining scripts.

### Secondary Users

#### QA Manager / Project Manager (PM)

- **Context & Motivation:** Needs to ensure product quality and track testing progress to approve releases.
- **Value:** They consume the execution reports and dashboards to gauge build stability without needing to read code. The system provides them with visual proof of test coverage.

#### Client / External Stakeholder

- **Context & Motivation:** Wants assurance that the product being delivered is robust and rigorously tested.
- **Value:** The ability to share video recordings or comprehensive End-to-End (E2E) automated test runs serves as a powerful showcase of the delivery team's technical capability and commitment to quality.

### User Journey

1. **Intake & Review:** The QA Engineer triggers the Business Analyst Agent to read new Confluence requirements or Jira tickets. The QA reviews and approves the Markdown test cases generated by the AI via the simple Web UI, relying on traceability links to verify accuracy.
2. **Asynchronous "Guided" Execution:** The QA initiates the first test run on the primary environment. Instead of staring at a loading screen, the QA moves on to other tasks while the AI executes in the background. If the AI encounters a blocker (e.g., MFA, complex Captcha), it triggers an **Asynchronous Ping (Slack/Teams notification)** prompting the QA to "jump in," resolve the blocker via the UI, and let the AI resume.
3. **Autonomous Scaling:** Once the initial baseline run is verified and successful, the QA Engineer configures the system to autonomously repeat the exact same Goal-Oriented Plan across other browsers or environments (e.g., UAT, Staging), completely freeing them from repetitive cross-testing.
4. **Reporting & Showcase:** The QA Manager reviews the final aggregated reports. The impressive E2E automation run videos and logs are optionally shared with the Client as proof of capability and quality assurance.

---

## Competitive Landscape

### Direct Competitors

| Product | Strength | Gap vs. AI QA Automation |
| --- | --- | --- |
| **Mabl** | Polished low-code UI, self-healing selectors | SaaS-only, sends test data to cloud, no HITL hibernation, expensive per-seat licensing |
| **Testim** | Fast test authoring, AI-assisted locators | Cloud-dependent, limited Confluence/Jira native ingestion, no on-premises LLM option |
| **Functionize** | NLP test creation, Salesforce-friendly | SaaS-only, US data residency risks for EU/[REDACTED_LOCATION] enterprises, no multi-agent orchestration |
| **Launchable** | ML-based test prioritization | Narrows test scope but does not generate or execute tests; complementary, not competitive |
| **Playwright + Copilot** | Developer-grade, open-source, fast | Requires scripting skills, no business-level ingestion from Confluence/Jira, no HITL flow |

### Indirect Competitors

- **Manual QA teams + ChatGPT:** Ad-hoc AI assistance with no systematic pipeline, no traceability, data leakage risk via consumer LLM endpoints.
- **In-house Selenium/Playwright frameworks:** High maintenance burden, no AI generation, brittle selectors — the status quo most target users are trying to escape.

### Sustainable Differentiation

Our defensible moat is the combination of: **data sovereignty via dual-LLM contracts + on-premises deployment** × **end-to-end pipeline from requirements ingestion to browser execution** × **HITL hibernation for enterprise-grade approval flows**. No current competitor addresses all three simultaneously.

---

## Success Metrics

### Phase 1 — Pilot (first 3 months post-MVP)

| Metric | Baseline (current) | Target |
| --- | --- | --- |
| Time to generate test cases from Jira ticket | ~2–4 hours (manual) | < 15 minutes |
| Time to write automation script from test case | ~1–3 hours (manual) | < 5 minutes |
| Test script maintenance effort per sprint | ~20% of QA time | < 5% of QA time |
| Pipeline failure rate due to CAPTCHA/MFA blocks | ~30–50% (existing tools) | < 5% with HITL hibernation |
| QA engineer approval rate on AI-generated test plans | — | > 85% accepted without major edits |

### Phase 2 — Scaled Adoption (months 4–12)

| Metric | Target |
| --- | --- |
| Regression suite automation coverage | > 70% of P1/P2 test cases |
| False positive rate (vision-based assertion) | < 10% per test suite |
| Cross-environment test execution time reduction | > 60% vs. manual parallel runs |
| Data masking false negative incidents | 0 confirmed leaks in audit |

---

## Non-Functional Requirements

### Performance

- Test case generation from a single Jira ticket: **≤ 15 minutes** end-to-end (ingestion → masked → LLM → Markdown output)
- Browser Executor step execution latency: **≤ 3 seconds** per goal step under normal conditions
- Concurrent test pipeline runs supported: **≥ 5 simultaneous** on baseline infrastructure

### Reliability & Availability

- Web UI uptime SLA: **99.5%** during business hours (Mon–Fri, 08:00–20:00 local time)
- Pipeline state persistence: execution state survives server restart; hibernated runs resume correctly after infrastructure restarts
- Maximum acceptable data loss on failure: **zero** — all pipeline states are committed to persistent storage before each step transition

### Security

- All LLM-bound payloads pass through Data Masking Engine before transmission — no exceptions
- Vault credentials encrypted at rest (AES-256) and in transit (TLS 1.3 minimum)
- Azure AD authentication required for all Web UI access; no local username/password accounts
- Audit log of every masking decision, LLM call, and HITL gate action retained for **90 days minimum**

### Scalability

- Architecture must support horizontal scaling of the Browser Executor Agent without pipeline logic changes
- Confluence/Jira MCP ingestion must handle documents up to **500KB** without context window overflow (via chunking engine)

### Maintainability

- Browser Use upstream updates must be consumable without modifying core pipeline logic (enforced by Adapter pattern)
- All agent configurations (LLM endpoint, masking rules, timeout thresholds) configurable via YAML without code changes

---

## Dependency & Risk Assessment

### Browser Use (Open-Source Core)

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Breaking API changes in upstream | Medium | Adapter pattern isolates core logic; upstream changes require only adapter updates, not pipeline rewrites |
| Project abandonment / license change | Low-Medium | Fork strategy: maintain an internal fork at the last stable version; evaluate alternatives (Playwright-agent, Skyvern) at 6-month intervals |
| Insufficient community support for edge cases | Medium | Invest in internal expertise; contribute upstream fixes to reduce divergence |

### Azure AD / MCP Dependency

- **v1 scope:** Azure AD is the sole supported identity provider for MCP integration, reflecting the current client environment.
- **v2 roadmap:** An OIDC/SAML-compatible adapter will extend support to non-Azure AD environments, enabling broader enterprise adoption.
- **Fallback for v1:** If Azure AD connectivity is disrupted, the system enters a **read-only degraded mode** — previously ingested test cases remain accessible but new ingestion is paused until connectivity is restored.

---

## MVP Scope — Version 1.0

### In Scope

- Business Analyst Agent: Confluence + Jira ingestion via Internal MCP, Content Parsing & Chunking Engine, Data Masking Engine (rule-based layer only), Markdown Test Case generation with traceability links
- Automation Scripter Agent: Goal-Oriented Plan generation from approved Markdown test cases
- Browser Executor Agent: Goal-oriented browser execution via Browser Use adapter, vision-based Pass/Fail assertion (with DOM fallback for canvas/dynamic UIs)
- Asynchronous HITL Core: Slack/Teams notification, Web UI intervention, 48-hour hibernation with state serialization
- Web UI: QA review & approval interface, run dashboard, basic report viewer
- Infrastructure: Single-node deployment, Vault integration, Azure AD auth

### Out of Scope for v1.0

- OIDC/SAML alternative auth (v2)
- LLM-assisted Data Masking layer (v2)
- Horizontal scaling of Browser Executor (v2)
- CI/CD pipeline integration (v2)
- Multi-tenant support (future)

### Definition of Done — v1.0

MVP is complete when:

1. A QA engineer can ingest a real Jira ticket, review generated test cases, approve a Goal-Oriented Plan, and execute it on a target environment — **without writing any code**
2. At least one HITL hibernation cycle (MFA gate → notification → QA intervention → resume) completes successfully end-to-end
3. Data Masking Engine passes a security review confirming zero PII in LLM-bound payloads for a representative test dataset
4. Web UI is accessible and functional under Azure AD authentication
5. All P1 success metrics (from above) are measurable — baseline data collected and initial targets validated on pilot project
