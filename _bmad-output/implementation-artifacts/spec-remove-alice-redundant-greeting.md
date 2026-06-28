---
title: 'Remove redundant Alice greeting message'
type: 'chore'
created: '2026-06-26'
status: 'done'
route: 'one-shot'
---

# Remove redundant Alice greeting message

## Intent

**Problem:** Alice opened every `handle_start` run with the generic bubble "I'll help you configure the AI provider and model for this project." before any useful content (project selection / model assignments), adding noise to the chat.

**Approach:** Delete the unconditional `send_message` greeting at the top of `AliceAgent.handle_start`; the method now begins directly at its context guard, so the first message a user sees is the real configuration UI. No path that a user actually reaches loses its only output. Stale "show greeting" test comment corrected.

## Suggested Review Order

- The deletion — `handle_start` now starts at the context guard, no greeting bubble.
  [`alice.py:959`](../../src/ai_qa/agents/alice.py#L959)

- Stale comment corrected to match the new flow (no greeting).
  [`test_alice.py:885`](../../tests/test_agents/test_alice.py#L885)
