---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation-skipped', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
inputDocuments:
  - product-brief-browser-use-custom.md
  - product-brief-browser-use-custom-distillate.md
  - secret-brief-internal.md
documentCounts:
  briefs: 3
  research: 0
  brainstorming: 0
  projectDocs: 0
classification:
  projectType: developer_tool
  domain: general (QA Test Automation)
  complexity: medium
  projectContext: greenfield
workflowType: 'prd'
---

# Product Requirements Document - AI QA Automation

**Author:** Thuong
**Date:** 2026-04-03

## Executive Summary

AI QA Automation is an AI-powered pipeline that transforms natural-language QA test cases documented in on-premises Confluence into executable Playwright test scripts — without requiring testers to write code. Built on the open-source browser-use framework and large language models, it eliminates the manual handoff between test documentation and test automation, enabling QA teams to shift from verification (does the code work?) to validation (are we testing the right things?).

The tool is purpose-built for company's on-premises enterprise environment, connecting to internal Confluence via an existing MCP server and leveraging an approved Claude Enterprise license. Manual QA testers — who have zero coding skills — continue documenting test cases exactly as they do today. The pipeline reads their work and generates portable, human-readable Playwright scripts automatically.

This is a strategic response to competitive pressure: competitors are already applying AI to QA automation, and company's SDET talent shortage makes manual test-to-code translation an unsustainable bottleneck. The tool preserves workforce investment by evolving tester roles upward, not eliminating them.

### What Makes This Special

**Custom-built for company's infrastructure.** Every major AI testing competitor (Mabl, Functionize, TestRigor, Katalon) is cloud-only. None supports on-premises Jira Data Center or Confluence Server. For Swiss enterprise clients in banking, pharma, and government — where data sovereignty is non-negotiable — these tools are simply not available. AI QA Automation runs entirely on existing on-premises infrastructure.

**Zero adoption friction.** Testers change nothing about their workflow. They write requirements in Confluence as they always have. The AI reads what they've already written. No new tools, no training, no code.

**Multi-LLM cost optimization.** Start with Claude Enterprise (proven, already licensed), migrate to on-premises LLMs (DeepSeek 670b, Qwen 3.5) for 60-80% cost reduction while keeping all data on-premises.

**Verification → Validation shift.** By automating routine script generation, QA engineers focus on higher-value work: complex test design, exploratory testing, and validating that the right things are being tested.

## Project Classification

- **Project Type:** Developer Tool (AI-powered QA automation pipeline)
- **Domain:** QA Test Automation
- **Complexity:** Medium — AI/LLM integration, on-premises enterprise constraints, multi-LLM strategy
- **Project Context:** Greenfield — new tool, starting from PoC phase

## Success Criteria

### User Success

- Manual QA testers save measurable time by eliminating the wait for automation engineers to translate their Confluence test cases into code
- Testers experience the "aha moment" when their documented test case automatically becomes a runnable Playwright script — no code interaction required
- Zero workflow disruption: testers continue writing in Confluence exactly as before

### Business Success

- **20% reduction** in manual test-to-code translation effort within Milestone 1
- QA automation engineers freed from routine translation, redirected to complex test design, exploratory testing, and validation
- Reduced dependency on scarce SDET talent — manual testers contribute to automation output directly
- Competitive parity maintained as competitors adopt similar AI-QA tooling

### Technical Success

- **PoC threshold: 70%** of generated Playwright scripts execute correctly without manual intervention
- End-to-end pipeline (MCP → Claude → browser-use → Playwright) completes without manual steps
- AI correctly interprets structured natural-language test cases from Confluence
- Incremental quality improvement across milestones (70% PoC → higher baselines post-Milestone 1)

### Measurable Outcomes

| Metric | PoC Target | Milestone 1 Target |
| --- | --- | --- |
| Script execution success rate | 70% | To be baselined |
| Translation effort reduction | Demonstrated feasibility | 20% reduction |
| Pipeline completion | Runs end-to-end | Runs with human-in-the-loop review |
| Manual tester code interaction | Zero | Zero |

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Problem-solving MVP — prove the pipeline works end-to-end on a representative Confluence space. No polish, no edge cases, no multi-user support. One question: can AI read test cases and generate working Playwright scripts?

**Resource Requirements:** 1 R&D engineer, 1 week. Leverages existing infrastructure (MCP server, Claude Enterprise license, on-prem Chrome with SSO).

### Phase 1 — PoC (MVP)

**Core Journey Supported:** Single engineer runs pipeline manually from IDE against PTP (Personal Travel Plan) Confluence space.

**Must-Have Capabilities:**

- Connect to Confluence via MCP server and retrieve test case content
- Pass test case content to Claude Sonnet 4.6 with generation prompt
- browser-use navigates target application based on LLM instructions
- Output: executable Python Playwright test files
- Basic `.env` configuration (API key, MCP URL, target page)
- README.md with setup and usage instructions
- 70% script execution success rate target

**Explicitly Not in PoC:**

- Error handling beyond basic pipeline failures
- Human-in-the-loop review
- Jira integration
- Multiple LLM support
- Logging, metrics, or reporting
- Confluence content quality validation

### Phase 2 — Milestone 1 (Growth)

- Jira Data Center integration via MCP
- Human-in-the-loop review workflow (side-by-side comparison, approval/rejection)
- On-premises LLMs (DeepSeek 670b, Qwen 3.5) replacing Claude
- Confluence document quality detection and low-confidence flagging
- CLI interface for non-developer users
- Production error handling and structured logging
- Basic metrics: scripts generated, success rate, generation time
- 20% translation effort reduction target

### Phase 3 — Milestone 2+ (Expansion)

- Browser Use Cloud integration for maximum accuracy (78% benchmark) where cloud deployment is acceptable
- Self-healing test maintenance — scripts auto-adapt to UI changes
- CI/CD pipeline integration for automated test execution
- Multi-LLM fallback chain for 60-80% cost optimization
- Batch generation across multiple Confluence spaces
- Metrics dashboard for leadership (ROI, coverage, effort reduction)
- Bidirectional intelligence (AI updates Jira, flags stale docs)
- Web interface for broader team access

### Risk Mitigation Strategy

**Technical Risks:**

| Risk | Severity | Mitigation | Phase |
| --- | --- | --- | --- |
| LLM hallucination (syntactically valid, semantically wrong scripts) | High | Human-in-the-loop review mandatory | Milestone 1 |
| Confluence document quality (unstructured/informal test cases) | High — most concerning | Document quality detection + feedback loop to testers | Milestone 1 |
| browser-use dependency (open-source, still maturing) | Medium | Monitor project health; Playwright native AI ecosystem as fallback | Ongoing |
| MCP server reliability | Low | Already deployed and stable internally | PoC |

**Market Risks:**

| Risk | Mitigation |
| --- | --- |
| Competitors close on-prem gap | Execute fast — first-mover advantage is time-limited |
| "Role elimination" perception causes resistance | Consistent "role evolves, not disappears" messaging |
| PoC results don't generalize beyond pilot space | Test on diverse Confluence content types during M1 |

**Resource Risks:**

| Risk | Mitigation |
| --- | --- |
| Single engineer dependency | Document everything; PoC is bounded to 1 week — low blast radius |
| Milestone 1 still 1 engineer | Acceptable if scope is prioritized; defer Phase 3 features aggressively |
| LLM costs scale unexpectedly | On-prem LLM migration in M1 caps costs at infrastructure level |

## User Journeys

> Journeys are mapped for Milestone 1 (post-PoC operational deployment). PoC is a single R&D engineer effort with no role separation.

### Journey 1: Linh — Manual QA Tester (Happy Path)

**Persona:** Linh, 28, manual QA tester with 4 years experience. Writes thorough, structured test cases in Confluence but has never written code. Assumes AI testing tools are "for developers only."

**Opening Scene:** Linh finishes documenting 12 test cases for a new feature in the PTP Confluence space — covering login, booking flow, and edge cases. Normally, she'd submit a request to the automation team and wait 2-3 weeks.

**Rising Action:** Her team lead mentions AI QA Automation is available. Linh points the tool at her Confluence page and triggers the pipeline. The system reads her plain-language test cases and begins generating Playwright scripts.

**Climax:** Within minutes, 12 Playwright test files appear. She opens one — readable, with step descriptions matching her original test case. She triggers execution: 9 of 12 pass on the first run. She flags the 3 failures for the automation engineer.

**Resolution:** What took 2-3 weeks now takes an afternoon. Linh's documentation work directly produces automation output. Her role hasn't changed, but her impact has multiplied.

### Journey 2: Linh — Manual QA Tester (Edge Case)

**Opening Scene:** Linh generates scripts from an older Confluence page — test cases written informally by a former colleague, with inconsistent formatting, vague steps like "check the page loads correctly," and missing expected results.

**Rising Action:** The pipeline produces incomplete or incorrect scripts. One clicks a nonexistent button. Another asserts a condition Linh never specified. The AI interpreted ambiguous language literally.

**Climax:** In the human-in-the-loop review workflow, Linh sees which test cases produced poor scripts and why — the tool highlights low-confidence generations. The problem is input quality, not the tool.

**Resolution:** Linh rewrites the 4 problematic test cases with clearer steps and explicit expected results, then re-runs. All scripts are accurate. She starts advocating for documentation standards across her team. The tool becomes a forcing function for documentation quality.

### Journey 3: Minh — QA Automation Engineer (Reviewer)

**Persona:** Minh, 32, SDET with 6 years experience in Gatling and Playwright. Skeptical about AI-generated tests. Currently spends 60% of his time translating Confluence test cases into code.

**Opening Scene:** Minh receives notification that Linh generated 12 Playwright scripts. As the designated reviewer in the human-in-the-loop workflow, he validates before scripts enter the test suite.

**Rising Action:** Each script is paired with its source Confluence test case for side-by-side comparison. He reviews selectors, assertions, and test flow logic. 9 are solid. 3 need adjustments: a fragile selector, a missing wait condition, an incorrect assertion.

**Climax:** Minh fixes the 3 scripts in 20 minutes — work that would have taken 2 full days from scratch. He approves all 12.

**Resolution:** The tool gave him leverage, not replacement. He shifts from "code translator" to "quality architect" — spending recovered time on performance testing and exploratory testing.

### Journey 4: Duc — R&D Engineer (Admin)

**Persona:** Duc, 30, R&D engineer who built the PoC. Now maintains the Milestone 1 pipeline — LLM connections, MCP server integration, troubleshooting.

**Opening Scene:** Duc onboards the QA team: configures `.env` with on-premises LLM endpoints (DeepSeek 670b), MCP server URL, SSO credentials, and review workflow permissions.

**Rising Action:** First week: pipeline fails for a Confluence space. Logs show MCP server returns malformed data for pages with embedded macros. Duc adds a preprocessing step.

**Climax:** One month in, Duc migrates from Claude to on-premises DeepSeek. Script quality drops slightly (75% → 68%) but LLM costs drop 70%. He tunes prompt templates and recovers to 72%.

**Resolution:** Pipeline stabilizes. Duc shifts from daily firefighting to weekly monitoring, documents runbooks, trains a junior engineer. Focus moves to Milestone 2 planning.

### Journey 5: Trang — Engineering Leadership (DU Head)

**Persona:** Trang, 45, DU Head and business sponsor. Approved the PoC. Cares about ROI, team productivity, and competitive positioning.

**Opening Scene:** Trang receives the Milestone 1 quarterly report. Question: did the investment pay off?

**Rising Action:** Dashboard shows: 150 scripts generated, 20% reduction in manual translation effort, QA coverage up 30% with same headcount. Two client projects piloting the tool. Cost: one engineer's time plus LLM APIs (now 70% cheaper with on-prem models).

**Climax:** Board presentation: "We're the only Swiss IT consultancy with AI-powered QA automation running entirely on-premises. Banking and pharma clients can't use cloud alternatives." Board approves Milestone 2.

**Resolution:** Trang initiates a pilot with a banking client who rejected every cloud-only vendor. The tool evolves from internal efficiency play to consulting differentiator.

### Journey Requirements Summary

| Journey | Key Capabilities Revealed |
| --- | --- |
| Linh (Happy Path) | Confluence integration, pipeline trigger, Playwright output, execution reporting |
| Linh (Edge Case) | Input quality detection, low-confidence flagging, re-generation workflow, documentation quality feedback |
| Minh (Reviewer) | Human-in-the-loop review UI, side-by-side comparison, script approval/rejection, batch review |
| Duc (Admin) | Configuration management, log monitoring, LLM switching, prompt tuning, operational runbooks |
| Trang (Leadership) | Metrics dashboard, ROI reporting, usage analytics, cost tracking |

## Domain-Specific Requirements

> These requirements apply from Milestone 1 onward. PoC scope is limited to proving end-to-end feasibility — working code only.

### Security & Data Sovereignty

- All data processing remains on-premises — no test case content or generated scripts leave company infrastructure
- Claude Enterprise license covers PoC; on-premises LLMs must provide equivalent data isolation from Milestone 1
- Browser sessions reuse existing SSO authentication — no additional credential storage
- Audit trail required from Milestone 1: log Confluence pages read, scripts generated, and by whom

### Browser Sandboxing

- AI browser agent operates in a sandboxed environment — isolated from production applications
- Agent reads and navigates only — must not submit forms, modify data, or trigger workflows
- Clear permission boundaries per Confluence space and target application

### Script Quality & Hallucination Mitigation

- Human-in-the-loop review mandatory before scripts enter production test suites (Milestone 1)
- Low-confidence generation flagging when input quality is insufficient
- Side-by-side comparison of source test case and generated script for reviewer validation
- No "silent failures" — scripts that look correct but test the wrong thing are more dangerous than visible failures

### Gatling Coexistence

- Playwright scripts coexist with existing Gatling test suites — no migration required
- No auto-conversion of Gatling to Playwright; existing investment remains intact
- New automation defaults to Playwright; Gatling remains for performance and load testing

### Integration Constraints

- MCP server is the single integration point for Confluence and Jira (Milestone 1) access
- Pipeline must handle Confluence content variations: embedded macros, attachments, non-standard formatting

## Developer Tool Specific Requirements

### Technical Architecture

**Runtime & Dependencies:**

- Python 3.12+ with `uv` package manager
- Output: Python Playwright (latest version) test scripts
- Core dependencies: browser-use >= 0.12.5, langchain-anthropic >= 1.3.1, python-dotenv >= 1.2.1
- LLM: Claude Sonnet 4.6 via Anthropic API (temperature 0.0 for deterministic output)

**Pipeline Architecture:**

- MCP server (`internal_MCP_URL`) → reads Confluence test cases
- LLM processes natural-language test cases → generates Playwright Python code
- browser-use framework controls local Chrome instance via active SSO session
- Output: `.py` Playwright test files, executable standalone

**Distribution & Execution:**

- PoC: Clone repo → configure `.env` → run from IDE
- Milestone 1: CLI interface for non-developer users
- Milestone 2+: Web interface for broader team access

### Installation & Configuration

**PoC Setup (minimal):**

1. Clone repository
2. `uv sync` to install dependencies
3. Configure `.env` file:
   - `ANTHROPIC_API_KEY` — Claude Enterprise API key
   - MCP server URL
   - Target Confluence space/page URL
   - SSO configuration
4. Run pipeline from IDE

**Documentation:** Single README.md — setup instructions, configuration reference, basic usage. Minimal, developer-focused.

### Code Output Specifications

**Generated Playwright Scripts:**

- Language: Python
- Framework: Playwright for Python (latest stable)
- Structure: One test file per Confluence test case
- Naming: Derived from test case title in Confluence
- Assertions: Mapped from expected results in test case documentation
- Selectors: Prefer stable selectors (data-testid, role-based) over fragile ones (CSS path, XPath)

### API Surface

**PoC — Minimal Interface:**

- Single entry point: provide Confluence page URL → receive generated Playwright test files
- No programmatic API — direct script execution from IDE
- Configuration via `.env` only

**Milestone 1 — Extended Interface:**

- CLI with commands: `generate`, `validate`, `list-spaces`
- Batch generation: process multiple Confluence pages in sequence
- Output directory configuration
- Dry-run mode for preview without file generation

## Functional Requirements

### Confluence Integration

- FR1: Pipeline can connect to on-premises Confluence via MCP server and authenticate using existing SSO session
- FR2: Pipeline can retrieve test case content from a specified Confluence page URL
- FR3: Pipeline can parse natural-language test cases from Confluence page content
- FR4: Pipeline can handle Confluence content variations including embedded macros and non-standard formatting (Milestone 1)

### Test Script Generation

- FR5: Pipeline can interpret natural-language test case steps and translate them into browser automation actions
- FR6: Pipeline can generate executable Python Playwright test scripts from parsed test cases
- FR7: Pipeline can produce one test file per Confluence test case with naming derived from test case title
- FR8: Pipeline can generate stable selectors (data-testid, role-based) over fragile ones (CSS path, XPath)
- FR9: Pipeline can map expected results from test case documentation into Playwright assertions

### Pipeline Execution

- FR10: Engineer can trigger the pipeline by providing a Confluence page URL
- FR11: Pipeline can execute end-to-end (MCP → LLM → browser-use → Playwright output) without manual intervention
- FR12: Pipeline can control a local Chrome instance via browser-use framework using active SSO login session
- FR13: Pipeline can output generated test files to a configurable output directory

### Configuration

- FR14: System-level service URLs must be configured through environment variables, including Browser Use Cloud URL, Claude API base URL, Gemini API base URL, ChatGPT/OpenAI API base URL, On-Premises API base URL, and MCP server URL. Provider API keys and MCP API keys must not be stored in `.env`; they must be collected from the user and stored securely per user account. Target page URL and SSO options are workflow inputs provided by the user and must not be stored in `.env`.
- FR15: Alice must dynamically validate the selected AI provider and discover available models from the selected provider/server where supported. Engineer-managed LLM parameter tuning is not part of the MVP because available models are dynamic and cannot be safely predetermined.
- FR15a: Alice must only assign downstream agent models from the provider's discovered available model list. If model discovery fails, returns no models, or cannot verify a selected model exists, Alice must block successful configuration review and show an actionable recovery message.
- FR15b: Alice must provide a user-reviewable model-selection rationale for each downstream agent, including provider connection status, discovered models, agent model needs, selected model, and selection rationale.

### Administration

- FR16: Admin can manage users and projects. Admin is not responsible for switching LLM providers for users in the MVP.

### Backlog

- FR17: User can run comparison tests between LLM providers to evaluate output quality. This is deferred to backlog and is not required for the current MVP.

### Removed from MVP

- FR18: Admin prompt-template tuning is removed from the MVP because dynamic provider/model selection makes centralized prompt tuning too complex for this phase.

### Human-in-the-Loop Review (Milestone 1)

- FR19: Reviewer can view generated scripts alongside their source Confluence test cases for side-by-side comparison
- FR20: Reviewer can approve or reject individual generated scripts
- FR21: Reviewer can edit generated scripts before approval
- FR22: Pipeline can flag low-confidence generations for mandatory review

### Jira Integration (Milestone 1)

- FR23: Pipeline can connect to on-premises Jira Data Center via MCP server
- FR24: Pipeline can retrieve test-related requirements from Jira tickets

### Quality & Observability (Milestone 1)

- FR25: Pipeline can log which Confluence pages were read, which scripts were generated, and by whom
- FR26: Pipeline can report script execution success rate
- FR27: Pipeline can detect insufficient input quality and warn before generation

### Reporting (Milestone 1)

- FR28: Leadership can view metrics dashboard showing scripts generated, success rates, and effort reduction
- FR29: Leadership can view LLM cost tracking and comparison data

## Non-Functional Requirements

### Performance

- Pipeline end-to-end generation: within 5 minutes per test case (PoC)
- Individual browser actions: complete within 30 seconds to avoid timeout cascading
- Generated Playwright scripts: execute within standard Playwright timeout defaults (30 seconds per action)
- LLM API latency: dependent on provider SLA; Claude Enterprise typical latency acceptable for batch processing

### Security

- No data transmitted outside company infrastructure — on-prem constraint enforced at all phases
- API keys and credentials in `.env` only — never committed to version control, never logged
- Browser sessions reuse existing SSO — pipeline must not store, cache, or log credentials
- AI browser agent restricted to read-only navigation — no form submissions, data modifications, or write operations during generation
- Milestone 1: audit logging of all pipeline executions (who, when, which page, which scripts)
- Milestone 1: on-premises LLMs eliminate external API data transfer entirely

### Integration Resilience

- MCP server unavailability: fail gracefully with clear error messages
- LLM API: handle rate limits, timeouts, and transient errors with retry logic (max 3 retries)
- browser-use: handle browser crashes or navigation failures without corrupting partial output
- Playwright output: valid standalone Python files — executable with only Playwright as dependency
- `.env` validation: check all required values at startup, fail fast with actionable error messages
