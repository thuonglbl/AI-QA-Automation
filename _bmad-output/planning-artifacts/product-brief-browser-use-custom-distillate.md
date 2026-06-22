---
title: "Product Brief Distillate: AI QA Automation"
type: llm-distillate
source: "product-brief-browser-use-custom.md"
created: "2026-04-03"
purpose: "Token-efficient context for downstream PRD creation"
---

## Competitive Intelligence

- **Mabl**: AI-driven autonomous test creation, cloud-only SaaS, ML self-healing. No on-prem Jira/Confluence. Tests locked into Mabl platform (no export). Expensive per-seat pricing.
- **Katalon Studio**: Gartner 2025 Visionary, all-in-one (web/mobile/API/desktop). AI is augmentation only — does not generate tests from requirements. Proprietary test format, platform lock-in.
- **Functionize**: Closest competitor — NLP plain-English → tests. SaaS-only, no on-prem, not Playwright-based, proprietary engine. No Jira/Confluence Data Center integration.
- **TestRigor**: Plain-English authoring for non-technical testers. Cloud-hosted only, proprietary format, no export to Playwright. Limited enterprise governance.
- **Playwright AI ecosystem** (ZeroStep, Octomind, Stagehand, Bug0): Emerging tools generating Playwright from NL. Fragmented — no single tool covers full pipeline from requirements to executed tests. All require developer setup. None integrate with on-prem Atlassian.
- **Key gap all competitors share**: Cloud-only. Zero support for on-premises Jira Data Center / Confluence Server. This is the primary whitespace.

## Market Data

- Automation testing market: $36-40B (2025-2026), projected $79-84B by 2031-2034, CAGR 14-17%
- Broader software testing market on trajectory to $112.5B by 2034
- 89% of organizations piloting GenAI-augmented QA (2025); 70%+ enterprise adoption expected by 2026-2027
- AI augmentation projected to reduce manual testing effort by up to 45%
- Market shift from "scripted automation" to "agentic AI testing" — autonomous agents that plan, generate, execute, self-heal
- Atlassian Intelligence (AI in Jira/Confluence) is cloud-only — on-prem users have zero native AI testing integration

## LLM Benchmark Data

- Browser Use Cloud: 78% (proprietary fine-tuned model, highest accuracy, Captcha bypass, self-healing)
- Claude Opus 4.6: 62%
- Gemini 3.1 Pro: 59.3%
- Claude Sonnet 4.6: 59%
- GPT-5: 52.4%
- DeepSeek/Qwen: No benchmark available, positive community feedback
- Source: [https://browser-use.com/posts/ai-browser-agent-benchmark](https://browser-use.com/posts/ai-browser-agent-benchmark)
- **Caveat from review**: browser-use 89% task success rate measures autonomous web task completion, not QA script generation accuracy specifically — do not conflate

## Technical Context

- **Runtime**: Python 3.14+, uv package manager
- **Core deps**: browser-use>=0.12.5, langchain-anthropic>=1.3.1, python-dotenv>=1.2.1
- **PoC LLM**: Claude Sonnet 4.6 via Anthropic API (Enterprise license)
- **MCP server**: Internal, already deployed — reads from on-prem Confluence
- **Browser control**: Connects to local Chrome instance, leverages active SSO login session
- **LLM temperature**: 0.0 (deterministic output for consistency)
- **Current automation tool at company**: Gatling — brief proposes Playwright output instead. Rationale for switch not formally documented but Playwright is industry standard for browser automation and has richer AI ecosystem support
- **Playwright native AI ecosystem** (2026): MCP integration, Planner/Generator/Healer agents — can be leveraged to reduce custom development

## User & Workflow Context

- **Manual QA**: Test manually → document test cases in Confluence (and Jira, for later milestones)
- **Auto QA**: Read documents → write code in Gatling. This is the bottleneck being automated
- **QA skill level**: Manual testers have zero coding skills. This is a hard constraint — the tool must require no code interaction
- **User sentiment from market research**: Non-technical testers want plain-English authoring but distrust black-box AI — they want to understand/edit what's generated. Readable Playwright scripts address this
- **QA talent shortage**: SDET demand far outpaces supply. Codeless tools that let manual testers contribute to automation are a strategic workforce multiplier
- **Adoption risk**: "Reduce staffing costs" messaging signals role elimination → active resistance. Reframed in brief as "role evolves, not disappears" — this framing must be consistent in PRD

## Scope Signals

- **PoC (1 week)**: Confluence only via MCP → Claude → browser-use → Playwright scripts. Minimal config via .env
- **Explicitly out of PoC**: Jira integration, human-in-the-loop review, on-prem LLMs, Browser Use Cloud, self-healing, CI/CD, production error handling
- **Milestone 1 triggers**: PoC feasibility confirmed → add Jira, on-prem LLMs, human-in-the-loop review
- **Milestone 2 triggers**: On-prem quality baseline established → evaluate Browser Use Cloud

## Risks & Open Questions

- **LLM hallucination**: Generated scripts that are syntactically valid but semantically wrong create false confidence. No mitigation strategy defined yet — PRD should address validation workflow
- **Confluence document quality**: Pipeline assumes structured, machine-parseable test cases. If existing documentation is inconsistent/informal, generation quality will degrade. Need to assess actual document quality during PoC
- **browser-use dependency**: Open-source (89k stars, active development) but still maturing. No license audit, maintainability assessment, or fallback plan if abandoned/API changes
- **Security — live browser access**: AI agent with browser access to internal apps could trigger side effects, expose credentials, interact with production data. Needs sandboxing strategy
- **Gatling migration**: Existing Gatling scripts are an asset. No plan for migration or parallel operation period. PRD should clarify whether Playwright replaces or coexists with Gatling
- **Competitive moat durability**: On-prem gap may close as competitors add Data Center support. Defensibility depends on execution speed and deep Atlassian integration

## Rejected Ideas / Decisions

- **Commercialization**: Explicitly not planned. Internal R&D only, gradual internal adoption if successful. Long-term consulting differentiator possible but not a near-term goal
- **Human-in-the-loop in PoC**: Deferred to Milestone 1. PoC is pure feasibility — 1 week is too short for review workflow
- **Jira in PoC**: Deferred to Milestone 1. PoC focuses on Confluence only to reduce scope
- **Starting with on-prem LLMs**: Rejected for PoC — Claude Enterprise already approved and proven. On-prem LLMs (DeepSeek, Qwen) have no QA benchmark data yet

## Opportunity Notes (from review, not in brief)

- **Bidirectional intelligence**: AI test results could auto-update Jira tickets, flag stale Confluence docs, surface coverage gaps back to testers. Transforms from code generator to living QA knowledge system
- **Compliance artifact generation**: Automated test execution produces traceability artifacts. Could auto-generate audit-ready compliance reports (FINMA, GxP) — reframes tool as compliance accelerator for regulated clients
- **Horizontal expansion**: MCP + LLM + browser-use pipeline is domain-agnostic. Same architecture could automate RPA tasks, UAT scripting, data entry workflows from Confluence
- **LLM cost optimization as selling point**: Multi-LLM fallback chain could yield 60-80% cost reduction at scale — quantify this in PRD for board-level ROI discussions
