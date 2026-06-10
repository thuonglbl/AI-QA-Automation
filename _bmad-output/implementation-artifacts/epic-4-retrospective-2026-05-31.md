# Epic 4 Retrospective

## Epic Summary

Epic 4 moved the product from extracted requirements to structured test cases. It introduced the LLM abstraction layer, established the test case extractor pipeline stage, and delivered Mary — the agent that generates and reviews each test case.

## What Went Well

- The LLM abstraction layer was built so all agents can use a single LangChain/LiteLLM-based client.
- The test case extractor stage turned requirement markdown into structured test cases suitable for later automation.
- Mary’s review workflow allowed per-item approval, enable feedback loops, and made generated output inspectable before script generation.
- The sequence of project artifacts from Bob → Mary made the pipeline feel coherent and traceable.

## Challenges

- Generating high-quality structured test cases from natural language is inherently noisy, so prompt design and output validation were both critical.
- The review loop needed careful state management to avoid losing progress when users approved, rejected, or navigated between items.
- Handling malformed or incomplete LLM responses required defensive parsing and user-facing error guidance.

## Key Insights

- A solid LLM abstraction layer reduces future integration risk; Mary can focus on workflow without managing provider-specific details.
- Per-item review improves trust and gives the QA user a concrete opportunity to correct mistakes before scripts are generated.
- Confidence scoring and structured output design are useful guardrails when moving from requirements to executable test cases.

## Action Items

- Continue refining prompt templates and parser rules for the test case extractor.
- Add stronger validation for generated test case structure and explicit fallback behavior for malformed output.
- Document the test case schema clearly so script generation and execution stages can consume it reliably.
- Add more automated tests for Mary’s reject-feedback loop and pagination behavior.

## Next Epic Preview

Epic 5 takes the structured test cases and generates executable Playwright scripts, including browser/vision integration and Sarah’s side-by-side review workflow.
