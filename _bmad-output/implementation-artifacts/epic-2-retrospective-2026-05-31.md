# Epic 2 Retrospective

## Epic Summary

Epic 2 delivered the first complete working pipeline layer for the product. It added the backend application shell, real-time WebSocket support, admin user management, the shared agent lifecycle, and the chat UI components that make the pipeline interactive.

## What Went Well

- FastAPI backend with CORS, REST endpoints, and a `/ws` WebSocket endpoint was established successfully.
- Admin user management was integrated with secure responses and the correct admin-only access model.
- The `BaseAgent` lifecycle pattern (`Start → Processing → ReviewRequest → Done`) was implemented and became the anchor for all later agents.
- Frontend components such as the agent top bar, step dots, chat messages, and state-aware input area proved the intended user flow.
- Dynamic provider configuration and Alice’s model discovery architecture were set up to allow real provider selection and reasoning transparency.

## Challenges

- Synchronizing WebSocket status updates with frontend state required careful contract design and testing.
- Admin and standard user flows had to be kept separate while still using shared API infrastructure.
- The chat UI had to support multiple interaction modes (start, processing, review, reject feedback, done), which increased the complexity of the input and message components.

## Key Insights

- A shared agent state machine is essential for consistent UX and makes downstream agent orchestration simpler.
- Real-time communication is only as good as the message schema; early alignment on `AgentMessage` and status semantics avoided many integration issues.
- Security and privacy must be baked into admin routes from the beginning: safe user lists and no secret leakage are non-negotiable.

## Action Items

- Document the WebSocket message contract and the current state/value mapping clearly for frontend/backend developers.
- Add end-to-end tests covering the admin user list, user creation, and membership response shape.
- Continue validating accessibility across the pipeline UI components, especially review and reject workflows.
- Harden the approval/reject workflow around reject feedback so state transitions remain deterministic.

## Next Epic Preview

Epic 3 moves from UI and pipeline shell into real data acquisition: secure MCP integration, Confluence content extraction, markdown parsing, output persistence, and Bob’s paginated review workflow.
