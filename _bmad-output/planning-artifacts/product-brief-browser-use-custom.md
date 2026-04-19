---
title: "Product Brief: AI QA Automation — AI-Powered QA Test Automation"
status: "complete"
created: "2026-04-03"
updated: "2026-04-03"
inputs: [README.md, user interviews, market research]
---

## Executive Summary

Quality assurance is one of the most labor-intensive functions in software delivery. QA teams typically follow a two-track process: manual testers document test cases in Jira and Confluence, then automation engineers translate those documents into code — a slow, expensive handoff that creates bottlenecks and limits test coverage.

**AI QA Automation** eliminates this handoff entirely. By connecting directly to on-premises Jira and Confluence via an internal MCP server, and leveraging AI through the open-source browser-use framework, the tool reads human-written test requirements and generates executable Playwright test scripts — automatically. QA testers who have never written a line of code can produce automated tests from the requirements they already create.

This is not a theoretical capability. The AI browser automation market has matured rapidly — browser-use achieves 89% task success rates, and leading LLMs score 59-78% on web automation benchmarks. The window of opportunity is now: every major competitor in this space is cloud-only, leaving on-premises enterprise environments entirely unserved. The question is whether we capture this advantage now, or wait for others to close the gap.

## The Problem

Today's QA workflow has a fundamental inefficiency at its core:

1. **Manual QA testers** explore applications and document test cases in Confluence and Jira — a skilled, time-consuming process
2. **Automation QA engineers** read those documents and translate them into Gatling or other test scripts — another skilled, time-consuming process
3. The result: **two specialized roles doing sequential work** to produce a single automated test

This creates three compounding problems:

- **Staffing pressure**: Both manual and automation QA roles require dedicated headcount. Automation engineers are expensive and scarce — and their time is consumed by routine translation work rather than complex test design
- **Speed**: The handoff between documentation and code adds days or weeks of latency to test delivery
- **Coverage gaps**: Limited automation capacity means many documented test cases never get automated, leaving quality risk on the table

## The Solution

AI QA Automation is an AI-powered pipeline that transforms QA requirements directly into executable test scripts:

**Input**: The tool connects to on-premises Confluence through an internal MCP server. Configuration is minimal — an `.env` file with API keys, server URLs, and SSO credentials.

**Processing**: Using the open-source browser-use framework paired with large language models, the tool interprets natural-language test requirements and generates corresponding browser automation actions.

**Output**: Executable Playwright test scripts — the industry standard for browser automation. Scripts are portable, human-readable, and maintainable by any developer. Unlike proprietary test automation platforms, generated scripts survive tool deprecation, vendor changes, or team turnover.

The critical insight: **QA testers continue writing requirements exactly as they do today**. No new tools to learn, no code to write, no workflow disruption. Zero adoption friction for the people who use the tool daily.

## What Makes This Different

The only AI test automation tool that keeps all data on your infrastructure.

Every major AI testing tool on the market today — Mabl, Functionize, TestRigor, Katalon — is **cloud-only**. None supports on-premises Jira Data Center or Confluence Server integration. For Swiss enterprise clients in banking, pharma, and government, where data sovereignty is non-negotiable, these tools are simply not an option.

| Capability | Competitors | AI QA Automation |
| --- | --- | --- |
| On-premises Confluence integration | None | Yes (via internal MCP) |
| Output format | Proprietary/locked-in | Portable Playwright scripts |
| User skill requirement | Low-code (some technical skill) | Zero code (existing QA workflow) |
| Deployment | Cloud SaaS | On-premises capable |
| LLM flexibility | Fixed vendor | Multi-LLM (Claude, DeepSeek, Qwen) |
| Vendor lock-in risk | High | None (standard Playwright output) |

The **multi-LLM strategy** is a deliberate architectural choice: start with Claude (enterprise-licensed, proven quality), migrate to on-premises LLMs (DeepSeek 670b, Qwen 3.5) for cost and security optimization, with Browser Use Cloud as an option for maximum accuracy. This flexibility enables a 60-80% reduction in LLM operating costs once on-premises models are deployed.

## Who This Serves

**Primary users: Manual QA testers** — professionals skilled in test design and exploratory testing, but without programming experience. They already document thorough test cases in Confluence. This tool makes their existing output directly actionable as automated tests.

**Secondary beneficiaries: QA automation engineers** — freed from routine translation of documented test cases into code, they shift to higher-value work: complex test scenarios, performance testing, exploratory testing, and framework maintenance. Their role evolves, not disappears.

**Stakeholder value: Engineering leadership and board** — QA teams deliver more automated test coverage with existing headcount, faster test delivery cycles, and reduced dependency on scarce automation engineering talent.

## Investment & Timeline

**PoC Phase**: 1 week, 1 R&D engineer

**Pilot project**: A representative internal Confluence space with existing test documentation (see `secret-brief-internal.md` for details).

**Data security**: Claude Enterprise license with corporate security commitments already in place. No additional compliance review required for PoC.

**Business sponsor**: DU Head

**Cost**: Minimal — leverages existing infrastructure (MCP server, Claude Enterprise license, on-premises AI servers for future milestones). Primary investment is R&D engineer time.

## Success Criteria

**PoC Phase — Stage Gate (1 week)**:

| Criterion | Measure | Go/No-Go Threshold |
| --- | --- | --- |
| End-to-end pipeline | MCP → LLM → browser-use → Playwright script | Pipeline executes without manual intervention |
| Script quality | % of generated scripts that execute correctly | To be baselined during PoC |
| Feasibility confirmation | AI correctly interprets natural-language test cases | Demonstrated on pilot Confluence project |

The PoC is a **bounded 1-week experiment**. A clear **go/no-go decision** follows: proceed to Milestone 1 if the pipeline demonstrates feasibility on representative test cases, or stop if fundamental quality or integration barriers emerge.

**Post-PoC Metrics (measured after feasibility is proven)**:

- Reduction in time from documented test case to automated script
- Percentage of generated scripts that pass without manual correction
- Test coverage increase relative to QA team capacity

## Scope

**In scope (PoC — 1 week)**:

- Integration with internal MCP server for Confluence on-premises access
- AI-driven test script generation from natural-language requirements
- Playwright script output
- Configuration via `.env` file (API keys, server URLs, SSO options)
- Evaluation with Claude as the initial LLM

**Deliberately deferred** (enters scope when PoC criteria are met):

| Capability | Phase | Trigger |
| --- | --- | --- |
| Jira integration | Milestone 1 | PoC feasibility confirmed |
| Human-in-the-loop review workflow | Milestone 1 | PoC feasibility confirmed |
| On-premises LLMs (DeepSeek, Qwen) | Milestone 1 | PoC feasibility confirmed |
| Browser Use Cloud integration | Milestone 2 | On-prem quality baseline established |
| Self-healing / test maintenance | Milestone 2+ | Script volume justifies investment |
| CI/CD pipeline integration | Milestone 1+ | Scripts reliably pass review |

## Vision

If the PoC proves feasibility, AI QA Automation follows a staged investment path:

**Milestone 1 — Expand Integration & On-Premises LLMs**: Add Jira integration alongside Confluence. Migrate from Claude to DeepSeek 670b or Qwen 3.5 running on existing on-premises AI infrastructure. This eliminates external API costs and keeps all data on-premises — critical for regulated clients. Add human-in-the-loop review workflow for production use.

**Milestone 2 — Maximum Quality**: Evaluate Browser Use Cloud (78% benchmark accuracy, Captcha bypass, self-healing) for scenarios where accuracy is paramount and cloud deployment is acceptable.

**Long-term**: A mature internal tool that QA teams use daily across client projects — freeing automation engineers for higher-value work while increasing test coverage and delivery speed. As the tool proves its value internally, it becomes a differentiator in consulting offerings: faster delivery, higher quality, competitive cost structure.
