# Blind Hunter Code Review Prompt

You are the Blind Hunter. You receive NO project context — diff only.
Please review the following code changes adversarially.
Output findings as a Markdown list.

## Diff Output:
warning: in the working copy of '_bmad-output/test-artifacts/automation-summary.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of '_bmad-output/test-artifacts/results.xml', LF will be replaced by CRLF the next time Git touches it
diff --git a/_bmad-output/implementation-artifacts/sprint-status.yaml b/_bmad-output/implementation-artifacts/sprint-status.yaml
index 412760f..6c3dc2f 100644
--- a/_bmad-output/implementation-artifacts/sprint-status.yaml
+++ b/_bmad-output/implementation-artifacts/sprint-status.yaml
@@ -36,7 +36,7 @@
 # - Dev moves story to 'review', then runs code-review (fresh context, different LLM recommended)
 
 generated: 2026-05-29T00:14:09.493182
-last_updated: 2026-06-11T19:00:00.000000
+last_updated: 2026-06-11T21:30:00.000000
 project: ai qa automation
 project_key: NOKEY
 tracking_system: file-system
@@ -147,9 +147,9 @@ development_status:
   10-7-realtime-artifact-refresh-ux: done
   10-8-open-artifact-update-delete-notice: done
   epic-10-retrospective: optional
-  epic-11: backlog
-  11-1-mcp-client-foundation-for-confluence-and-jira: backlog
-  11-2-bob-confluence-url-intake-and-pipeline-trigger: backlog
+  epic-11: in-progress
+  11-1-mcp-client-foundation-for-confluence-and-jira: ready-for-dev
+  11-2-bob-confluence-url-intake-and-pipeline-trigger: ready-for-dev
   11-3-confluence-content-retrieval-and-parsing: backlog
   11-4-jira-requirements-retrieval: backlog
   11-5-input-quality-detection-before-generation: backlog
diff --git a/_bmad-output/test-artifacts/automation-summary.md b/_bmad-output/test-artifacts/automation-summary.md
index f34e77a..599f65c 100644
--- a/_bmad-output/test-artifacts/automation-summary.md
+++ b/_bmad-output/test-artifacts/automation-summary.md
@@ -1,6 +1,6 @@
 ---
-stepsCompleted: ['step-01-preflight-and-context', 'step-02-identify-targets', 'step-03-orchestrate', 'step-03c-aggregate', 'step-04-validate-and-summarize', 'step-01-preflight-and-context-9-7', 'step-02-identify-targets-9-7', 'step-03-generate-tests-9-7', 'step-04-validate-and-summarize-9-7', 'step-01-preflight-and-context-10-2', 'step-02-identify-targets-10-2', 'step-03-generate-tests-10-2', 'step-04-validate-and-summarize-10-2']
-lastStep: 'step-04-validate-and-summarize-10-2'
+stepsCompleted: ['step-01-preflight-and-context', 'step-02-identify-targets', 'step-03-orchestrate', 'step-03c-aggregate', 'step-04-validate-and-summarize', 'step-01-preflight-and-context-9-7', 'step-02-identify-targets-9-7', 'step-03-generate-tests-9-7', 'step-04-validate-and-summarize-9-7', 'step-01-preflight-and-context-10-2', 'step-02-identify-targets-10-2', 'step-03-generate-tests-10-2', 'step-04-validate-and-summarize-10-2', 'step-02-identify-targets-expansion']
+lastStep: 'step-02-identify-targets-expansion'
 lastSaved: '2026-06-11'
 inputDocuments:
   - _bmad/tea/config.yaml
@@ -395,3 +395,27 @@ tests/unit/test_artifact_service.py
 - **E2E:** 7 new tests created covering AC1, AC2, AC3 and all frozen contract regression guards
 - **Mode:** Sequential single-agent execution
 - **Execution Mode Resolved:** Sequential (subagent probe returned false)
+
+## Expansion — Artifact Management Stories 10.3 to 10.8
+
+### Target Identification
+**Backend API Endpoints:**
+- `artifacts.py`: GET `{id}/content`, PUT/DELETE `{id}`, POST `{id}/versions`
+- `websocket.py`: Artifact Change Events
+
+**Frontend Testable Flows:**
+- View Artifact, Edit/Delete Artifact, Realtime Sync, Notifications
+
+### Test Level Assignment
+- **E2E (Playwright)**: Artifact interaction flows (View, Edit, Delete, Sync)
+- **API (Pytest)**: Artifact endpoints (Data validation, auth)
+- **Component (Vitest)**: ReviewContent, ArtifactViewer (UI states)
+- **Integration (Pytest)**: S3/SeaweedFS storage, WS broadcast
+
+### Priority Assignment
+- **P0**: Artifact Read/Write/Delete (Data integrity)
+- **P1**: Realtime refresh, Version history (Core UX)
+- **P2**: UI notices, Empty states (Visual state)
+
+### Coverage Plan Summary
+**Scope:** Selective expansion for new Artifact features.
diff --git a/_bmad-output/test-artifacts/results.xml b/_bmad-output/test-artifacts/results.xml
index b67c86a..ec8ba7d 100644
--- a/_bmad-output/test-artifacts/results.xml
+++ b/_bmad-output/test-artifacts/results.xml
@@ -1,172 +1,6 @@
-<testsuites id="" name="" tests="49" failures="0" skipped="0" errors="0" time="417.546031">
-<testsuite name="story-10-7-artifact-refresh.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="3" failures="0" skipped="0" time="24.25" errors="0">
-<testcase name="Story 10.7 Realtime Artifact Refresh › [P0] artifact tree refreshes on change event for the displayed project" classname="story-10-7-artifact-refresh.spec.ts" time="8.732">
-</testcase>
-<testcase name="Story 10.7 Realtime Artifact Refresh › [P0] chat state preserved during artifact tree refresh" classname="story-10-7-artifact-refresh.spec.ts" time="7.221">
-</testcase>
-<testcase name="Story 10.7 Realtime Artifact Refresh › [P0] non-active-thread project events handled without disrupting active chat" classname="story-10-7-artifact-refresh.spec.ts" time="8.297">
-</testcase>
-</testsuite>
-<testsuite name="story-10-8-artifact-notice.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="3" failures="0" skipped="0" time="37.378" errors="0">
-<testcase name="Story 10.8 Open Artifact Update/Delete Notice › [P1] non-disruptive notice shown on artifact update while viewing" classname="story-10-8-artifact-notice.spec.ts" time="8.459">
-</testcase>
-<testcase name="Story 10.8 Open Artifact Update/Delete Notice › [P1] non-disruptive notice shown on artifact deletion while viewing" classname="story-10-8-artifact-notice.spec.ts" time="8.113">
-</testcase>
-<testcase name="Story 10.8 Open Artifact Update/Delete Notice › [P1] ignoring artifact notice preserves all chat state" classname="story-10-8-artifact-notice.spec.ts" time="20.806">
-</testcase>
-</testsuite>
-<testsuite name="story-7-1-auth.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="2" failures="0" skipped="0" time="13.337" errors="0">
-<testcase name="Story 7.1 local login and authenticated session foundation › [P0] authenticates a registered user through the real backend and applies the token to current-user calls" classname="story-7-1-auth.spec.ts" time="6.681">
-</testcase>
-<testcase name="Story 7.1 local login and authenticated session foundation › [P0] rejects invalid credentials with a safe consistent error message" classname="story-7-1-auth.spec.ts" time="6.656">
-</testcase>
-</testsuite>
-<testsuite name="story-7-2-project-membership.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="3" failures="0" skipped="0" time="13.784" errors="0">
-<testcase name="Story 7.2 project membership access for standard users › standard user sees only active assigned projects from the real backend" classname="story-7-2-project-membership.spec.ts" time="6.842">
-</testcase>
-<testcase name="Story 7.2 project membership access for standard users › standard user with zero projects gets an empty list and sees the no-access state" classname="story-7-2-project-membership.spec.ts" time="6.573">
-</testcase>
-<testcase name="Story 7.2 project membership access for standard users › unauthenticated project list requests are rejected by the real backend" classname="story-7-2-project-membership.spec.ts" time="0.369">
-</testcase>
-</testsuite>
-<testsuite name="story-7-3-project-selection.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="3" failures="0" skipped="0" time="20.418" errors="0">
-<testcase name="Story 7.3 Alice Agent Project Selection Logic › [P0] should show no-access message and halt flow when user has zero accessible projects" classname="story-7-3-project-selection.spec.ts" time="6.261">
-</testcase>
-<testcase name="Story 7.3 Alice Agent Project Selection Logic › [P0] should auto-bind project when user has exactly 1 accessible project" classname="story-7-3-project-selection.spec.ts" time="6.957">
-</testcase>
-<testcase name="Story 7.3 Alice Agent Project Selection Logic › [P0] should bind a thread per project and skip the chooser for multiple accessible projects (superseded by Story 7.7)" classname="story-7-3-project-selection.spec.ts" time="7.2">
-</testcase>
-</testsuite>
-<testsuite name="story-7-3-thread-creation.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="2" failures="0" skipped="0" time="9.12" errors="0">
-<testcase name="Story 7.3 Thread Creation and RBAC › [P0] should create a new thread via New Conversation button" classname="story-7-3-thread-creation.spec.ts" time="7.82">
-</testcase>
-<testcase name="Story 7.3 Thread Creation and RBAC › [P2] should deny access to threads owned by other users via API" classname="story-7-3-thread-creation.spec.ts" time="1.3">
-</testcase>
-</testsuite>
-<testsuite name="story-7-5-conversation-history.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="1" failures="0" skipped="0" time="14.568" errors="0">
-<testcase name="Story 7.5 Conversation History and Thread Resume › [P0] should list user&apos;s conversation history and resume a thread" classname="story-7-5-conversation-history.spec.ts" time="14.568">
-</testcase>
-</testsuite>
-<testsuite name="story-7-6-membership-removal.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="2" failures="0" skipped="0" time="4.068" errors="0">
-<testcase name="Story 7.6 Membership Removal Access Enforcement › [P0] hides threads of a removed project but keeps unbound and still-member threads (AC1)" classname="story-7-6-membership-removal.spec.ts" time="1.562">
-</testcase>
-<testcase name="Story 7.6 Membership Removal Access Enforcement › [P0] denies every project-scoped thread endpoint with a generic 404 and no detail leak (AC2)" classname="story-7-6-membership-removal.spec.ts" time="2.506">
-</testcase>
-</testsuite>
-<testsuite name="story-7-7-workspace-shell.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="4" failures="0" skipped="0" time="23.608" errors="0">
-<testcase name="Story 7.7 standard user workspace shell routing › [P0][AC1][AC2][AC3] single-project user lands directly in the workspace shell on a bound thread (no chooser)" classname="story-7-7-workspace-shell.spec.ts" time="7.794">
-</testcase>
-<testcase name="Story 7.7 standard user workspace shell routing › [P0][AC2][AC3] multi-project user gets one starter thread per project and never sees the chooser" classname="story-7-7-workspace-shell.spec.ts" time="5.475">
-</testcase>
-<testcase name="Story 7.7 standard user workspace shell routing › [P0][AC4] zero-project user sees the no-access message and no thread is created" classname="story-7-7-workspace-shell.spec.ts" time="5.339">
-</testcase>
-<testcase name="Story 7.7 standard user workspace shell routing › [P0][AC5] admin user is routed to the admin dashboard, bypassing the workspace shell" classname="story-7-7-workspace-shell.spec.ts" time="5">
-</testcase>
-</testsuite>
-<testsuite name="story-8-1-admin-routing.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="3" failures="0" skipped="0" time="19.224" errors="0">
-<testcase name="Story 8.1 admin dashboard routing and access control › [P0][AC1] admin logs in and is routed directly to the admin dashboard, bypassing the provider/chooser flow" classname="story-8-1-admin-routing.spec.ts" time="4.925">
-</testcase>
-<testcase name="Story 8.1 admin dashboard routing and access control › [P0][AC2] a standard user navigating directly to /admin stays in the workspace shell and never sees the admin dashboard" classname="story-8-1-admin-routing.spec.ts" time="7.522">
-</testcase>
-<testcase name="Story 8.1 admin dashboard routing and access control › [P1][AC2] a standard user with zero projects at /admin sees the no-access workspace message, not the admin dashboard" classname="story-8-1-admin-routing.spec.ts" time="6.777">
-</testcase>
-</testsuite>
-<testsuite name="story-8-2-admin-user-management.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="2" failures="0" skipped="0" time="21.468" errors="0">
-<testcase name="Story 8.2 admin user management › [P0][AC1][AC2] admin creates a user via the dashboard form and it appears in the Users Management list" classname="story-8-2-admin-user-management.spec.ts" time="10.531">
-</testcase>
-<testcase name="Story 8.2 admin user management › [P0][AC2] submitting a duplicate email surfaces a safe error banner and creates no second user" classname="story-8-2-admin-user-management.spec.ts" time="10.937">
-</testcase>
-</testsuite>
-<testsuite name="story-8-3-admin-project-management.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="2" failures="0" skipped="0" time="19.697" errors="0">
-<testcase name="Story 8.3 admin project management › [P0][AC1][AC2][AC3] admin creates a project, sees it in the Projects list, then renames it" classname="story-8-3-admin-project-management.spec.ts" time="12.792">
-</testcase>
-<testcase name="Story 8.3 admin project management › [P0][AC4] admin deletes a project — it disappears from the dashboard and from an affected member&apos;s accessible list" classname="story-8-3-admin-project-management.spec.ts" time="6.905">
-</testcase>
-</testsuite>
-<testsuite name="story-8-4-project-membership-assignment.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="2" failures="0" skipped="0" time="16.386" errors="0">
-<testcase name="Story 8.4 project membership assignment › [P0][AC1][AC2] admin assigns a project to a user — chip appears, the option leaves the per-user select, and the member can see it" classname="story-8-4-project-membership-assignment.spec.ts" time="8.216">
-</testcase>
-<testcase name="Story 8.4 project membership assignment › [P0][AC3] admin removes a user from a project — chip disappears, the option returns, and the member loses access" classname="story-8-4-project-membership-assignment.spec.ts" time="8.17">
-</testcase>
-</testsuite>
-<testsuite name="story-8-5-admin-dashboard-ui-layout.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="3" failures="0" skipped="0" time="16.585" errors="0">
-<testcase name="Story 8.5 admin dashboard UI layout › [P0][AC2][AC5] layout shows Projects on the left and Users Management + Create User on the right with disabled Sync button" classname="story-8-5-admin-dashboard-ui-layout.spec.ts" time="5.141">
-</testcase>
-<testcase name="Story 8.5 admin dashboard UI layout › [P0][AC1] nav shows admin email and role near Logout; clicking Logout returns to the login screen" classname="story-8-5-admin-dashboard-ui-layout.spec.ts" time="5.825">
-</testcase>
-<testcase name="Story 8.5 admin dashboard UI layout › [P0][AC3][AC4] user card shows assigned-project chip with × remove control and enabled assign select + button for the unassigned project" classname="story-8-5-admin-dashboard-ui-layout.spec.ts" time="5.619">
-</testcase>
-</testsuite>
-<testsuite name="story-8-6-admin-e2e-execution.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="1" failures="0" skipped="0" time="1.716" errors="0">
-<testcase name="Story 8.6 Admin E2E test execution and report viewing › Admin sees the trigger E2E tests control on the dashboard" classname="story-8-6-admin-e2e-execution.spec.ts" time="1.716">
-</testcase>
-</testsuite>
-<testsuite name="story-9-4-dynamic-model-discovery.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="5" failures="0" skipped="0" time="69.576" errors="0">
-<testcase name="Story 9.4 Dynamic Model Discovery (live, all providers) › [P1] Browser Use Cloud: discovery wires real models into the review UI" classname="story-9-4-dynamic-model-discovery.spec.ts" time="16.713">
-<properties>
-<property name="slow" value="">
-</property>
-</properties>
-</testcase>
-<testcase name="Story 9.4 Dynamic Model Discovery (live, all providers) › [P1] Anthropic / Claude: discovery wires real models into the review UI" classname="story-9-4-dynamic-model-discovery.spec.ts" time="11.091">
-<properties>
-<property name="slow" value="">
-</property>
-</properties>
-</testcase>
-<testcase name="Story 9.4 Dynamic Model Discovery (live, all providers) › [P1] Google / Gemini: discovery wires real models into the review UI" classname="story-9-4-dynamic-model-discovery.spec.ts" time="9.382">
-<properties>
-<property name="slow" value="">
-</property>
-</properties>
-</testcase>
-<testcase name="Story 9.4 Dynamic Model Discovery (live, all providers) › [P1] OpenAI / ChatGPT: discovery wires real models into the review UI" classname="story-9-4-dynamic-model-discovery.spec.ts" time="12.032">
-<properties>
-<property name="slow" value="">
-</property>
-</properties>
-</testcase>
-<testcase name="Story 9.4 Dynamic Model Discovery (live, all providers) › [P1] On-Premises: discovery wires real models into the review UI" classname="story-9-4-dynamic-model-discovery.spec.ts" time="20.358">
-<properties>
-<property name="slow" value="">
-</property>
-</properties>
-</testcase>
-</testsuite>
-<testsuite name="story-9-5-provider-enable-disable.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="4" failures="0" skipped="0" time="23.029" errors="0">
-<testcase name="Story 9.5 Provider Enable/Disable Enforcement › [P0][FR16c] Admin creates project with selected providers, user cannot select disabled providers" classname="story-9-5-provider-enable-disable.spec.ts" time="8.238">
-</testcase>
-<testcase name="Story 9.5 Provider Enable/Disable Enforcement › [P1][FR16d] Disabled provider shows tooltip on hover" classname="story-9-5-provider-enable-disable.spec.ts" time="7.517">
-</testcase>
-<testcase name="Story 9.5 Provider Enable/Disable Enforcement › [P1][FR16c] Backward compatibility: all providers enabled allows all providers" classname="story-9-5-provider-enable-disable.spec.ts" time="6.908">
-</testcase>
-<testcase name="Story 9.5 Provider Enable/Disable Enforcement › [P2][FR16c] Admin can update project to change enabled providers" classname="story-9-5-provider-enable-disable.spec.ts" time="0.366">
-</testcase>
-</testsuite>
-<testsuite name="story-9-7-saved-config.spec.ts" timestamp="2026-06-10T17:52:05.634Z" hostname="chromium" tests="4" failures="0" skipped="0" time="40.326" errors="0">
-<testcase name="Story 9.7 Saved Provider Configuration and Rotation Behavior › [P0][AC1][AC2] Second thread shows explicit saved-config prompt without auto-narration" classname="story-9-7-saved-config.spec.ts" time="10.16">
-<properties>
-<property name="slow" value="">
-</property>
-</properties>
-</testcase>
-<testcase name="Story 9.7 Saved Provider Configuration and Rotation Behavior › [P0][AC2] &apos;Use saved configuration&apos; completes Step 1 without re-entering the API key" classname="story-9-7-saved-config.spec.ts" time="10.15">
-<properties>
-<property name="slow" value="">
-</property>
-</properties>
-</testcase>
-<testcase name="Story 9.7 Saved Provider Configuration and Rotation Behavior › [P1][AC2] &apos;Choose a different provider&apos; reveals the ProviderSelector" classname="story-9-7-saved-config.spec.ts" time="10.31">
-<properties>
-<property name="slow" value="">
-</property>
-</properties>
-</testcase>
-<testcase name="Story 9.7 Saved Provider Configuration and Rotation Behavior › [P1][AC2] Gear inspect affordance shows saved provider and agent models without exposing secrets" classname="story-9-7-saved-config.spec.ts" time="9.706">
-<properties>
-<property name="slow" value="">
-</property>
-</properties>
+<testsuites id="" name="" tests="1" failures="0" skipped="0" errors="0" time="117.149591">
+<testsuite name="story-10-3-artifact-preview.spec.ts" timestamp="2026-06-11T12:30:47.322Z" hostname="chromium" tests="1" failures="0" skipped="0" time="23.727" errors="0">
+<testcase name="Story 10.3 Artifact Read and Preview Access › Renders markdown, code, and image artifacts with creator metadata" classname="story-10-3-artifact-preview.spec.ts" time="23.727">
 </testcase>
 </testsuite>
 </testsuites>
\ No newline at end of file
warning: in the working copy of '_bmad-output/implementation-artifacts/11-1-mcp-client-foundation-for-confluence-and-jira.md', LF will be replaced by CRLF the next time Git touches it
diff --git a/_bmad-output/implementation-artifacts/11-1-mcp-client-foundation-for-confluence-and-jira.md b/_bmad-output/implementation-artifacts/11-1-mcp-client-foundation-for-confluence-and-jira.md
new file mode 100644
index 0000000..2490ccf
--- /dev/null
+++ b/_bmad-output/implementation-artifacts/11-1-mcp-client-foundation-for-confluence-and-jira.md
@@ -0,0 +1,348 @@
+---
+baseline_commit: 9d878c5
+---
+
+# Story 11.1: MCP Client Foundation for Confluence and Jira
+
+Status: ready-for-dev
+
+<!-- markdownlint-disable MD033 MD041 -->
+<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
+
+## Story
+
+As a system developer,
+I want a shared MCP client for Confluence and Jira access,
+so that Bob can retrieve source requirements through the approved on-premises MCP server.
+
+## Acceptance Criteria
+
+### AC1 — MCP client resolves the current user's encrypted MCP key at execution time
+
+**Given** Bob needs to access Confluence or Jira
+**When** the MCP client initializes
+**Then** it uses the current user's encrypted MCP key resolved at execution time
+**And** it connects to the configured on-premises MCP server URL from system configuration.
+
+### AC2 — Client discovers available Confluence and Jira tools on connect
+
+**Given** the MCP server is reachable
+**When** the client connects
+**Then** it discovers available Confluence and Jira tools where supported
+**And** unavailable tools are reported as actionable capability errors.
+
+### AC3 — Retry logic covers MCP connection and transient failures
+
+**Given** MCP connection, authentication, or transient errors occur
+**When** Bob attempts MCP access
+**Then** retry logic uses max 3 attempts with safe backoff
+**And** failures raise custom MCP errors with user-safe messages and no secret leakage.
+
+---
+
+## ⚠️ CRITICAL: This is an EXTEND story — NOT a greenfield MCP build
+
+The MCP client, Confluence reader, retry logic, and per-user secret infrastructure were **already built** across Epics 3 and 9. Story 11-1 exists to **extend the existing foundation** with:
+
+1. **Jira capability** — `JiraReader` pipeline stage (parallel to `ConfluenceReader`) so Bob can retrieve Jira issues via the same MCP server.
+2. **Formal capability detection** — `MCPClient.check_required_tools()` that returns a list of missing tools, enabling ConfluenceReader and JiraReader to report actionable errors rather than silently failing when a tool is absent.
+3. **`JiraIssue` model** — structured data model for Jira issue content (parallel to `ConfluencePage`).
+
+**Do NOT:**
+- Rebuild `MCPClient` (already at `src/ai_qa/mcp/client.py`) — extend only
+- Rebuild `ConfluenceReader` (already at `src/ai_qa/pipelines/confluence_reader.py`) — do not touch unless adding capability-check call
+- Rebuild `SECRET_TYPE_MCP` or the secret-resolution pattern — already in `src/ai_qa/secrets/__init__.py` and Bob agent
+- Add a new transport or auth mechanism — Bearer token via `Authorization` header is the only supported transport
+- Add async patterns to pipeline stage models — `ConfluencePage`, `JiraIssue` are pure Pydantic (sync)
+
+### What ALREADY EXISTS (reuse — do not recreate)
+
+| Capability | Where it lives today | Status |
+| --- | --- | --- |
+| `MCPClient` with retry + tool cache | [src/ai_qa/mcp/client.py](src/ai_qa/mcp/client.py) — `__init__(server_url, auth_token, settings)`, `connect()`, `list_tools()`, `call_tool()`, `discover_capabilities()` | ✅ done |
+| `ConnectionManager` + `MCPConnection` | [src/ai_qa/mcp/connection.py](src/ai_qa/mcp/connection.py) — pooled by URL+token key, Streamable HTTP + SSE fallback | ✅ done |
+| `Tool`, `ToolCache`, `ToolResult` | [src/ai_qa/mcp/tools.py](src/ai_qa/mcp/tools.py) — TTL-based tool caching (5 min default) | ✅ done |
+| `MCPError` hierarchy | [src/ai_qa/exceptions.py](src/ai_qa/exceptions.py) — `MCPConnectionError`, `MCPAuthenticationError`, `MCPToolError`, `MCPTimeoutError` | ✅ done |
+| `SECRET_TYPE_MCP = "mcp"` | [src/ai_qa/secrets/__init__.py](src/ai_qa/secrets/__init__.py) — canonical secret type for MCP PAT | ✅ done |
+| Per-user secret resolution | `get_user_secret(db, user_id, SECRET_TYPE_MCP)` in [src/ai_qa/secrets/service.py](src/ai_qa/secrets/service.py) — used by Bob agent | ✅ done |
+| `mcp_server_url`, `mcp_tool_prefix`, `mcp_max_retries`, `mcp_retry_backoff` | [src/ai_qa/config.py](src/ai_qa/config.py) — AppSettings fields | ✅ done |
+| `ConfluenceReader` + `CONFLUENCE_TOOLS` | [src/ai_qa/pipelines/confluence_reader.py](src/ai_qa/pipelines/confluence_reader.py) — full MCP-backed reader | ✅ done |
+| `ConfluencePage` model | [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py) — `page_id`, `title`, `content`, `space_key`, `url`, `retrieved_at`, etc. | ✅ done |
+| `Project.jira_base_url` DB field | [src/ai_qa/db/models.py](src/ai_qa/db/models.py) — stored, not yet used by any reader | ✅ exists (to be consumed) |
+| `StageResult` | [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py) — all pipeline stages return this | ✅ done |
+
+---
+
+## Tasks / Subtasks
+
+- [ ] **Task 1 — Add `JiraIssue` model to pipeline models (AC1/AC2)**
+  - [ ] 1.1 Open [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py). After the `ConfluencePage` class, add `JiraIssue(BaseModel)` with fields: `issue_key: str` (e.g., `"PROJ-123"`), `summary: str`, `description: str | None`, `acceptance_criteria: str | None`, `status: str | None`, `labels: list[str] = []`, `project_key: str`, `url: str`, `retrieved_at: datetime`, `issue_type: str | None = None`, `reporter: str | None = None`, `assignee: str | None = None`. Add a `tz_aware` validator on `retrieved_at` matching the same pattern as `ConfluencePage`.
+  - [ ] 1.2 Export `JiraIssue` from `src/ai_qa/pipelines/__init__.py` (or wherever `ConfluencePage` is exported — match the same export location).
+
+- [ ] **Task 2 — Create `JiraReader` pipeline stage (AC1/AC2/AC3)**
+  - [ ] 2.1 Create `src/ai_qa/pipelines/jira_reader.py`. Model the class structure on `ConfluenceReader` — same `__init__(mcp_client, jira_base_url, settings)` signature shape.
+  - [ ] 2.2 Declare `JIRA_TOOLS: list[str] = ["jira_get_issue", "jira_search_issues", "jira_get_project"]` as a class constant. Respect `mcp_tool_prefix` from `AppSettings` (same `_get_tool_name()` helper pattern as `ConfluenceReader`).
+  - [ ] 2.3 Implement `_parse_issue_ref(ref: str) -> str` — a private static/class method that extracts a Jira issue key from:
+    - Plain issue key: `"PROJ-123"` → `"PROJ-123"`
+    - Jira Cloud URL: `https://company.atlassian.net/browse/PROJ-123` → `"PROJ-123"`
+    - Jira Data Center URL: `https://jira.company.com/browse/PROJ-123` → `"PROJ-123"`
+    - Invalid input → raise `ValueError` with a clear message
+  - [ ] 2.4 Implement `async read_issue(issue_ref: str) -> StageResult` — parses the ref via `_parse_issue_ref()`, calls `self._mcp_client.call_tool(self._get_tool_name("jira_get_issue"), {"issue_key": issue_key, "userPrompt": "...", "llmReasoning": "..."})`, maps the tool result to `JiraIssue`, returns `StageResult(success=True, data=issue, metadata={...})`. On `MCPToolError` or non-success `ToolResult`: return `StageResult(success=False, error=err_msg, metadata={...})` — do NOT re-raise; let callers decide.
+  - [ ] 2.5 Implement `async check_tool_availability() -> list[str]` — calls `self._mcp_client.list_tools()`, returns the names in `JIRA_TOOLS` that are absent from the discovered tool list. Returns empty list when all tools are present. Raises `MCPConnectionError` if `list_tools()` raises. This method is called by the caller (Bob) before the first read to surface actionable "Jira not available" errors — not called automatically inside `read_issue`.
+  - [ ] 2.6 Map tool result fields defensively: Jira MCP tool responses may nest content in `"fields"`, `"body"`, or flat keys depending on the server version — use `result.data.get("fields", result.data)` or similar and guard all optional field accesses. Acceptance criteria text lives in `fields.description` or `fields.customfield_XXXXX` — extract whatever is present; fall back to `None` gracefully.
+
+- [ ] **Task 3 — Add `check_required_tools()` to `MCPClient` (AC2)**
+  - [ ] 3.1 Open [src/ai_qa/mcp/client.py](src/ai_qa/mcp/client.py). Add method `async check_required_tools(required_tools: list[str]) -> list[str]` — calls `self.list_tools()`, returns names from `required_tools` not found in the discovered tool names. Returns empty list when all present. Raises whatever `list_tools()` raises (caller handles). No caching bypass — relies on the existing `ToolCache` TTL.
+  - [ ] 3.2 Update `ConfluenceReader` to expose a parallel `check_tool_availability() -> list[str]` method that delegates to `self._mcp_client.check_required_tools(CONFLUENCE_TOOLS)`. Keep the `CONFLUENCE_TOOLS` list as-is — do NOT change existing Confluence logic beyond adding this one method.
+
+- [ ] **Task 4 — Unit tests (AC1/AC2/AC3)**
+  - [ ] 4.1 Create `tests/pipelines/test_jira_reader.py`. Use `unittest.mock.AsyncMock` + `MagicMock` to mock `MCPClient`. Do NOT instantiate a real MCPClient or open a network connection.
+  - [ ] 4.2 Test `_parse_issue_ref()`:
+    - `"PROJ-123"` → `"PROJ-123"`
+    - `"https://company.atlassian.net/browse/PROJ-123"` → `"PROJ-123"`
+    - `"https://jira.company.com/browse/PROJ-123"` → `"PROJ-123"`
+    - Empty string → `ValueError` with `match=`
+    - Garbage input (no issue key pattern) → `ValueError` with `match=`
+  - [ ] 4.3 Test `read_issue()` happy path: mock `call_tool` to return `ToolResult.from_data({...})` with a realistic Jira payload; assert returned `StageResult.success is True` and `StageResult.data` is a `JiraIssue` with correct fields.
+  - [ ] 4.4 Test `read_issue()` error path: mock `call_tool` to raise `MCPToolError("tool not found")`; assert returned `StageResult.success is False` and error message is non-empty.
+  - [ ] 4.5 Test `check_tool_availability()`: mock `list_tools()` to return a tool list missing `"jira_search_issues"`; assert the return value is `["jira_search_issues"]` (the missing one). Then mock it to return all `JIRA_TOOLS` present; assert return is `[]`.
+  - [ ] 4.6 Add unit test for `MCPClient.check_required_tools()` in `tests/unit/test_mcp_client_capabilities.py` (new file). Mock `list_tools()` to return a subset; assert the missing names are returned. Test with empty `required_tools` → always returns `[]`.
+  - [ ] 4.7 Add unit test for `ConfluenceReader.check_tool_availability()` in `tests/pipelines/test_jira_reader.py` (same file is fine, or extract) — delegate asserts that `check_required_tools(CONFLUENCE_TOOLS)` is called.
+
+- [ ] **Task 5 — Full gate + DoD**
+  - [ ] 5.1 Run `uv run ruff check .` and `uv run mypy src` — clean.
+  - [ ] 5.2 Run `uv run pytest tests/pipelines/test_jira_reader.py tests/unit/test_mcp_client_capabilities.py -v` — all green.
+  - [ ] 5.3 **No DB migration required** — `Project.jira_base_url` already exists in schema. Confirm `uv run alembic upgrade head` is a no-op.
+  - [ ] 5.4 **Frontend not touched** — no `frontend/` changes expected; skip `npm run typecheck` unless a type was incidentally affected.
+  - [ ] 5.5 Update Dev Agent Record with file list, commands run, and outputs.
+
+---
+
+## Dev Notes
+
+### What this story is actually building
+
+The existing Epic 3 work built a generic `MCPClient` and a `ConfluenceReader`. Epic 9 added per-user MCP secret storage. This story's job is:
+
+1. **`JiraReader`** — a Jira-specific pipeline stage that wraps `MCPClient.call_tool()` for `jira_get_issue` and friends, same as `ConfluenceReader` wraps Confluence tools. It must handle Jira's nested `fields` response structure and extract `summary`, `description`, `acceptance_criteria`, `labels`, `status`.
+2. **`check_required_tools()`** on `MCPClient` — a first-class API for callers to ask "is Jira/Confluence available?" before attempting reads. Returns a list of missing tool names so the caller can surface user-friendly errors.
+3. **`JiraIssue` model** — Pydantic model for Jira issue data, consumed by Task 4 of Epic 11 (JiraReader output) and later by Bob agent.
+
+### MCPClient instantiation pattern (DO NOT change)
+
+Bob agent already resolves the MCP PAT at runtime and passes it to `MCPClient`:
+
+```python
+# From src/ai_qa/agents/bob.py — existing pattern, do not copy-paste into JiraReader
+mcp_pat = get_user_secret(db, user_id, SECRET_TYPE_MCP)  # decrypted at runtime
+settings = AppSettings()
+client = MCPClient(auth_token=mcp_pat, settings=settings)
+await client.connect()
+reader = ConfluenceReader(client, confluence_base_url=project.confluence_base_url)
+```
+
+`JiraReader` follows the same constructor shape: `JiraReader(mcp_client, jira_base_url, settings)`. Secret resolution is the **caller's** responsibility (Bob agent), not the reader's. The reader never touches `UserSecret` or `get_user_secret`.
+
+### `check_required_tools()` sketch
+
+```python
+# In src/ai_qa/mcp/client.py — add to MCPClient class
+async def check_required_tools(self, required_tools: list[str]) -> list[str]:
+    """Return names from required_tools that are absent on the MCP server.
+    
+    Empty list means all required tools are present.
+    Raises MCPConnectionError / MCPAuthenticationError if list_tools() fails.
+    """
+    if not required_tools:
+        return []
+    available = {t.name for t in await self.list_tools()}
+    return [name for name in required_tools if name not in available]
+```
+
+Respects `mcp_tool_prefix` because `list_tools()` returns the server's actual tool names (already prefixed), and `_get_tool_name()` in the readers adds the prefix when calling. The comparison should be against **prefixed** names when a prefix is configured. Readers should pass prefixed names to `check_required_tools()`:
+
+```python
+# In JiraReader.check_tool_availability()
+prefixed = [self._get_tool_name(t) for t in JIRA_TOOLS]
+return await self._mcp_client.check_required_tools(prefixed)
+```
+
+### `JiraIssue` model sketch
+
+```python
+# In src/ai_qa/pipelines/models.py — add after ConfluencePage
+class JiraIssue(BaseModel):
+    issue_key: str          # e.g. "PROJ-123"
+    summary: str
+    description: str | None = None
+    acceptance_criteria: str | None = None  # from fields.description or custom field
+    status: str | None = None
+    labels: list[str] = []
+    project_key: str
+    url: str
+    retrieved_at: datetime
+    issue_type: str | None = None
+    reporter: str | None = None
+    assignee: str | None = None
+```
+
+### `JiraReader` response mapping — defensive field access
+
+Jira MCP tool responses vary by server type (Cloud vs Data Center) and MCP server implementation. Map defensively:
+
+```python
+# After call_tool returns ToolResult with .data = dict
+raw = tool_result.data or {}
+fields = raw.get("fields", raw)  # DC wraps in "fields"; Cloud may be flat
+return JiraIssue(
+    issue_key=raw.get("key", "") or issue_key,
+    summary=fields.get("summary", ""),
+    description=fields.get("description") or None,
+    acceptance_criteria=fields.get("acceptance_criteria") or None,
+    status=(fields.get("status") or {}).get("name") if isinstance(fields.get("status"), dict) else fields.get("status"),
+    labels=fields.get("labels") or [],
+    project_key=(fields.get("project") or {}).get("key", "") if isinstance(fields.get("project"), dict) else fields.get("project", ""),
+    url=self._jira_base_url.rstrip("/") + "/browse/" + issue_key,
+    retrieved_at=datetime.now(tz=timezone.utc),
+    issue_type=(fields.get("issuetype") or {}).get("name") if isinstance(fields.get("issuetype"), dict) else None,
+    reporter=(fields.get("reporter") or {}).get("displayName") if isinstance(fields.get("reporter"), dict) else None,
+    assignee=(fields.get("assignee") or {}).get("displayName") if isinstance(fields.get("assignee"), dict) else None,
+)
+```
+
+### `_parse_issue_ref()` sketch
+
+```python
+import re
+
+_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b")
+
+@classmethod
+def _parse_issue_ref(cls, ref: str) -> str:
+    """Extract Jira issue key from a URL or bare key string."""
+    stripped = ref.strip()
+    if not stripped:
+        raise ValueError("Issue reference must not be empty")
+    match = _ISSUE_KEY_RE.search(stripped)
+    if not match:
+        raise ValueError(f"No Jira issue key found in: {stripped!r}")
+    return match.group(1)
+```
+
+This handles Cloud URLs, DC URLs, and plain issue keys. The regex requires uppercase project key + dash + digits (standard Jira format).
+
+### Error handling contract
+
+`read_issue()` must NOT re-raise MCP errors — it returns `StageResult(success=False, error=...)`. This is consistent with `ConfluenceReader.read_page()` behavior. The Bob agent is responsible for surfacing errors to the user.
+
+`check_tool_availability()` MAY raise `MCPConnectionError` / `MCPAuthenticationError` because being unable to list tools is a hard infrastructure failure, not a soft "tool not present" signal.
+
+Never include raw exception messages, stack traces, or auth token fragments in `StageResult.error` — always use sanitized user-safe wording:
+- `MCPToolError` → "Jira tool not available on the MCP server"  
+- `MCPConnectionError` → "Could not connect to MCP server"
+- `MCPAuthenticationError` → "MCP authentication failed — check your MCP credential configuration"
+
+### Retry coverage
+
+`MCPClient.call_tool()` and `MCPClient.list_tools()` already implement retry (max 3, exponential backoff via tenacity in `src/ai_qa/mcp/client.py`). `JiraReader` does NOT add its own retry layer — the client handles it. Do NOT add `@retry` decorators in the reader.
+
+### Anti-patterns to avoid (FORBIDDEN)
+
+- Re-implementing connection pooling, auth, or retry in `JiraReader` — these live in `MCPClient`
+- Calling `get_user_secret()` inside `JiraReader` — secret resolution belongs in the agent layer (Bob)
+- Silently swallowing `MCPConnectionError` / `MCPAuthenticationError` in `read_issue()` — only catch `MCPToolError` and non-success `ToolResult` for soft failure
+- Mutating `ConfluenceReader` logic (other than adding `check_tool_availability()`)
+- `# type: ignore` / global lint disables
+- Bare `except Exception:` — use specific MCP error types
+- `asyncio.run()` inside JiraReader — it's an async class; `await` is correct
+
+### Testing approach
+
+Use `unittest.mock.AsyncMock` for `MCPClient` methods that are `async def`. Example:
+
+```python
+from unittest.mock import AsyncMock, MagicMock, patch
+from ai_qa.mcp.tools import ToolResult, Tool
+
+mock_client = MagicMock()
+mock_client.call_tool = AsyncMock(return_value=ToolResult.from_data({
+    "key": "PROJ-123",
+    "fields": {"summary": "Login fails", "description": "Steps: ...", ...}
+}))
+mock_client.list_tools = AsyncMock(return_value=[
+    Tool(name="jira_get_issue", description="", parameters=[], returns=""),
+    Tool(name="jira_search_issues", description="", parameters=[], returns=""),
+    # "jira_get_project" intentionally absent to test missing-tool detection
+])
+```
+
+No `@pytest.mark.asyncio` required if using `anyio` or the project's existing pytest-asyncio config — check `tests/conftest.py` for the existing marker setup and match it exactly.
+
+### Project Structure Notes
+
+**New files:**
+- `src/ai_qa/pipelines/jira_reader.py` — new pipeline stage
+- `tests/pipelines/test_jira_reader.py` — new unit test file
+- `tests/unit/test_mcp_client_capabilities.py` — new unit test file
+
+**Modified files:**
+- `src/ai_qa/pipelines/models.py` — add `JiraIssue` model
+- `src/ai_qa/pipelines/__init__.py` — export `JiraIssue` (if `ConfluencePage` is exported there)
+- `src/ai_qa/mcp/client.py` — add `check_required_tools()` method
+- `src/ai_qa/pipelines/confluence_reader.py` — add `check_tool_availability()` method (one method, no other changes)
+
+No new packages required. No DB migration. No frontend changes.
+
+### Previous-story intelligence
+
+No prior Epic 11 story exists. Relevant brownfield context:
+- **Epic 3** (done): Built the original MCP client + Confluence reader. These files are production code — do not refactor them beyond the targeted additions described above.
+- **Epic 9** (done): Added `SECRET_TYPE_MCP`, `get_user_secret()`, and runtime secret resolution in Bob agent. The per-user MCP PAT flow is complete — this story only extends it to also support Jira reads.
+- **Epic 10** (in-progress): Unrelated to MCP; no conflicts expected.
+
+### Full gate notes
+
+Full `uv run pytest` produces ~17 failures in orphaned legacy tests (pre-existing — see [backend-test-suite-orphaned-legacy-tests.md](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/backend-test-suite-orphaned-legacy-tests.md)). Only verify the 11-1-touched test files are clean, not the full suite baseline.
+
+### References
+
+- [Source: _bmad-output/planning-artifacts/epics.md#Story-11.1] — full ACs
+- [Source: _bmad-output/planning-artifacts/architecture.md#MCP-Integration] — MCP SDK decision, `src/ai_qa/mcp/` location, Jira M1 scope
+- [Source: src/ai_qa/mcp/client.py] — `MCPClient.__init__`, `connect()`, `list_tools()`, `call_tool()`, `discover_capabilities()`
+- [Source: src/ai_qa/mcp/connection.py] — `ConnectionManager`, Bearer token auth pattern
+- [Source: src/ai_qa/mcp/tools.py] — `Tool`, `ToolResult`, `ToolCache`
+- [Source: src/ai_qa/pipelines/confluence_reader.py] — `ConfluenceReader` structure, `CONFLUENCE_TOOLS`, `_get_tool_name()`, `StageResult` usage pattern
+- [Source: src/ai_qa/pipelines/models.py] — `ConfluencePage` (reference model), `StageResult`
+- [Source: src/ai_qa/secrets/__init__.py] — `SECRET_TYPE_MCP`
+- [Source: src/ai_qa/secrets/service.py] — `get_user_secret()` API
+- [Source: src/ai_qa/exceptions.py] — `MCPError` hierarchy
+- [Source: src/ai_qa/config.py] — `mcp_server_url`, `mcp_tool_prefix`, `mcp_max_retries`, `mcp_retry_backoff`
+- [Source: src/ai_qa/db/models.py] — `Project.jira_base_url` (already in schema)
+- [Source: project-context.md] — `uv` only; Ruff + Mypy strict; no global lint disables; no bare `except`; never `python3`
+
+### Definition of Done
+
+- [ ] `JiraIssue` Pydantic model added to `src/ai_qa/pipelines/models.py` with all required fields.
+- [ ] `JiraReader` class created at `src/ai_qa/pipelines/jira_reader.py` with `JIRA_TOOLS`, `_parse_issue_ref()`, `read_issue()`, and `check_tool_availability()`.
+- [ ] `MCPClient.check_required_tools()` added; `ConfluenceReader.check_tool_availability()` added.
+- [ ] Unit tests pass: `tests/pipelines/test_jira_reader.py` and `tests/unit/test_mcp_client_capabilities.py`.
+- [ ] `uv run ruff check .` and `uv run mypy src` — clean.
+- [ ] `uv run alembic upgrade head` is a no-op (confirmed no schema changes).
+
+---
+
+## Dev Agent Record
+
+### Agent Model Used
+
+{{agent_model_name_version}}
+
+### Debug Log References
+
+### Completion Notes List
+
+- Ultimate context engine analysis completed — comprehensive developer guide created.
+
+### File List
+
+### Change Log
warning: in the working copy of '_bmad-output/implementation-artifacts/11-2-bob-confluence-url-intake-and-pipeline-trigger.md', LF will be replaced by CRLF the next time Git touches it
diff --git a/_bmad-output/implementation-artifacts/11-2-bob-confluence-url-intake-and-pipeline-trigger.md b/_bmad-output/implementation-artifacts/11-2-bob-confluence-url-intake-and-pipeline-trigger.md
new file mode 100644
index 0000000..4bf6473
--- /dev/null
+++ b/_bmad-output/implementation-artifacts/11-2-bob-confluence-url-intake-and-pipeline-trigger.md
@@ -0,0 +1,325 @@
+---
+baseline_commit: 9d878c5
+---
+
+# Story 11.2: Bob Confluence URL Intake and Pipeline Trigger
+
+Status: ready-for-dev
+
+<!-- markdownlint-disable MD033 MD041 -->
+<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
+
+## Story
+
+As a QA user,
+I want to start requirements extraction by giving Bob a Confluence page URL,
+so that the QA automation pipeline begins from existing documented test cases.
+
+## Acceptance Criteria
+
+### AC1 — Bob asks for the Confluence URL trigger when it starts (Jira optional, gated)
+
+**Given** a thread is bound to a project and Alice configuration is ready
+**When** Bob starts
+**Then** Bob asks for a Confluence page URL as the required pipeline trigger
+**And** Bob optionally allows a Jira URL or Jira ticket reference if Jira extraction is enabled.
+
+### AC2 — Confluence URL is validated against configured rules before extraction
+
+**Given** the user submits a Confluence URL
+**When** Bob validates the input
+**Then** the URL is accepted only if it matches the configured Confluence URL rules
+**And** invalid URLs produce a clear correction message **without starting extraction**.
+
+### AC3 — Missing preconditions block extraction with a recovery action
+
+**Given** required project/thread context, provider configuration, or MCP credential status is missing
+**When** the user attempts to start Bob extraction
+**Then** Bob blocks extraction and explains the required recovery action.
+
+---
+
+## ⚠️ CRITICAL: This is an EXTEND story — add an intake gate to the EXISTING Bob agent
+
+`BobAgent` already exists and already runs a full Confluence extraction flow ([src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py)). The problem this story fixes: **Bob jumps straight into MCP extraction with no upfront gate.** `handle_start()` immediately transitions to `PROCESSING`, connects to the MCP server, and only fails *later* with a vague space-key error if the URL is unusable. There is no check that Alice configured the thread, no check that an MCP credential exists, and no early URL-rule validation.
+
+Story 11.2 inserts a **pre-extraction intake gate** at the very top of `handle_start()` — runs **before** `transition_to(PROCESSING)` and **before any MCP connection**:
+
+1. **Precondition check (AC3)** — project/thread context present, Alice provider config ready, MCP credential configured. Any miss → block with a recovery message; do not start.
+2. **Confluence URL-rule validation (AC2)** — validate the submitted URL; invalid → clear correction message; do not start (user can resubmit).
+3. **Optional Jira intake (AC1)** — if Jira is enabled for the project, accept and lightly validate a Jira URL/ticket reference; stash it for later retrieval (Story 11.4). If Jira is disabled, silently ignore any Jira input.
+
+**Do NOT:**
+
+- Rebuild or rewrite the existing extraction flow (`process()`, `_extract_descendants()`, `handle_approve()`, `handle_reject()`) — they stay as-is. You are **prepending a gate**, not refactoring extraction.
+- Implement actual Jira retrieval — that is **Story 11.4**. This story only *accepts and validates* a Jira reference at intake.
+- Implement Confluence content retrieval/parsing changes — that is **Story 11.3** (already built). Do not touch parsing.
+- Resolve/decrypt the MCP secret just to check it exists. Use the **status** API (`get_secret_status(...).configured`) — never `get_user_secret()` for the precondition check.
+- Add a new config setting or DB column for "URL rules." The project's existing `confluence_base_url` **is** the configured rule (instance allow-list of one). No migration.
+- Add async patterns / network calls inside the gate. The gate is **pure, synchronous validation** (DB reads + regex/urlparse). No MCP, no `await` on network.
+
+### What ALREADY EXISTS (reuse — do not recreate)
+
+| Capability | Where it lives today | Status |
+| --- | --- | --- |
+| `BobAgent` lifecycle (`handle_start`, `process`, `_extract_descendants`, `handle_approve/reject`) | [src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py) | ✅ done |
+| `_resolve_mcp_pat()` — decrypts MCP PAT at runtime (used inside extraction) | [src/ai_qa/agents/bob.py:42](src/ai_qa/agents/bob.py) | ✅ done — reuse for extraction, NOT for the gate |
+| `ConfluenceURLParser.is_valid_confluence_url()`, `extract_page_id()`, `extract_space_key()` | [src/ai_qa/pipelines/confluence_reader.py:63](src/ai_qa/pipelines/confluence_reader.py) | ✅ done — reuse for URL validation |
+| `get_secret_status(db, user_id, secret_type) -> SecretStatus` (`.configured` bool, **never decrypts**) | [src/ai_qa/secrets/service.py:90](src/ai_qa/secrets/service.py) | ✅ done — use for AC3 MCP check |
+| `SECRET_TYPE_MCP = "mcp"` | [src/ai_qa/secrets/__init__.py:18](src/ai_qa/secrets/__init__.py) | ✅ done |
+| `PipelineContext` (`user_id`, `user_email`, `project_id`, `thread_id`, `artifact_service`, `agent_run_id`) | [src/ai_qa/pipelines/context.py:11](src/ai_qa/pipelines/context.py) | ✅ done |
+| `Thread.provider_name`, `Thread.provider_base_url`, `Thread.agent_configs` (Alice readiness signal) | [src/ai_qa/threads/models.py:33](src/ai_qa/threads/models.py) | ✅ done |
+| `BaseAgent._load_agent_config()` populates `self._provider_config` / `self._agent_config` from the thread | [src/ai_qa/agents/base.py:99](src/ai_qa/agents/base.py) | ✅ done |
+| `Project.confluence_base_url`, `Project.jira_base_url` | [src/ai_qa/db/models.py:51](src/ai_qa/db/models.py) | ✅ done — `jira_base_url` set ⇒ Jira enabled |
+| `BaseAgent._format_error_message()` — 3-part UX-DR12 (What happened / Why / What to do) | [src/ai_qa/agents/base.py:400](src/ai_qa/agents/base.py) | ✅ done — match this format for recovery messages |
+| `AgentState` (`START`, `PROCESSING`, `REVIEW_REQUEST`, `DONE`, `ERROR`) + `transition_to`, `send_message` | [src/ai_qa/agents/base.py:32](src/ai_qa/agents/base.py) | ✅ done |
+| WebSocket start dispatch: `_handle_action` → `agent.handle_start(message["inputData"])` | [src/ai_qa/api/websocket.py:313](src/ai_qa/api/websocket.py) | ✅ done — `confluence_url`, `jira_url`, `mcp_pat` arrive here |
+| Frontend Bob start: `handleBobStart()` + `AGENTS.Bob.inputConfig.fields` (`confluence_url`, `jira_url`, `mcp_pat`) | [frontend/src/App.tsx:883](frontend/src/App.tsx), [frontend/src/types/pipeline.ts:179](frontend/src/types/pipeline.ts) | ✅ exists — `jira_url` is collected but NOT yet sent |
+
+---
+
+## Tasks / Subtasks
+
+- [ ] **Task 1 — Add the precondition check to `BobAgent` (AC3)**
+  - [ ] 1.1 Open [src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py). Add a private method `_check_preconditions() -> list[str]` that returns a list of human-readable recovery messages (empty list = all good). It performs **synchronous DB reads only** — no MCP, no secret decryption. Check, in order:
+    - **Project/thread context:** `self.project_context` is not `None` and has non-`None` `project_id`, `user_id`, and `thread_id`. Missing → append a recovery message (e.g. "Start Bob from inside an active project thread.").
+    - **Provider configuration (Alice ready):** read the `Thread` fresh from `db` (do not trust possibly-stale `self._provider_config`); require `thread.provider_name` is set **and** `thread.agent_configs` contains a `"bob"` entry with a non-empty model (`raw.get("model") or raw.get("model_name")`). Missing → recovery message pointing the user back to Alice ("Complete provider/model setup with Alice before starting Bob.").
+    - **MCP credential status:** `get_secret_status(db, self.project_context.user_id, SECRET_TYPE_MCP).configured` is `True`. Not configured → recovery message ("Add your MCP key in provider configuration, then retry."). **Use `get_secret_status`, never `get_user_secret` / `_resolve_mcp_pat` here** — the gate must not decrypt.
+  - [ ] 1.2 Import `get_secret_status` from `ai_qa.secrets.service` (alongside the existing `get_user_secret` import). `SECRET_TYPE_MCP` is already imported. Lazy-import `Thread` from `ai_qa.threads.models` inside the method (match the existing lazy-import pattern Bob uses for `Project`).
+
+- [ ] **Task 2 — Add Confluence URL-rule validation to `BobAgent` (AC2)**
+  - [ ] 2.1 Add `_validate_confluence_url(self, url: str, confluence_base_url: str | None) -> str | None`. Returns `None` when the URL is accepted, otherwise a single clear correction string. Rules (in order):
+    - Empty/blank after strip → "A Confluence page URL is required to start extraction."
+    - `ConfluenceURLParser.is_valid_confluence_url(url)` is `False` → correction listing the accepted formats (reuse the format hints already in `ConfluenceReader.read_page`).
+    - If `confluence_base_url` is configured: the submitted URL's host must equal the configured base URL's host (case-insensitive `urlparse(...).netloc`). Mismatch → "This URL is not part of the project's configured Confluence instance ({configured_host})." This is the "configured Confluence URL rules" — the project's `confluence_base_url` is the allow-list.
+    - Neither a page id nor a space key is extractable (`extract_page_id` and `extract_space_key` both `None`) → "Could not find a page ID or space key in the URL — point to a specific Confluence page."
+  - [ ] 2.2 Keep validation **pure** (regex + `urlparse` + the existing parser). No `await`, no MCP. The accepted URL is the one the existing `process()` already consumes via `input_data["confluence_url"]`.
+
+- [ ] **Task 3 — Add optional Jira intake to `BobAgent` (AC1)**
+  - [ ] 3.1 Add `_validate_jira_ref(self, jira_ref: str | None, jira_base_url: str | None) -> str | None`. Behavior:
+    - Jira **disabled** (`jira_base_url` is falsy): return `None` and ignore any provided `jira_ref` (Jira is optional; never block Confluence extraction on it — see Story 11.4 AC3).
+    - Jira **enabled** + `jira_ref` empty/absent: return `None` (Jira is optional).
+    - Jira **enabled** + `jira_ref` provided: light format check only — accept a bare issue key (`^[A-Z][A-Z0-9_]+-\d+$`) **or** an http(s) URL whose host matches `jira_base_url`'s host. On mismatch return a correction string. **Do not retrieve anything** — retrieval is Story 11.4.
+  - [ ] 3.2 Stash the accepted Jira reference for later stories: set `self._jira_ref: str | None` in `__init__` (default `None`) and assign it in `handle_start` after validation passes. This is carry-forward state only; nothing consumes it yet.
+
+- [ ] **Task 4 — Wire the gate into `handle_start` (AC1/AC2/AC3)**
+  - [ ] 4.1 At the **very top** of `BobAgent.handle_start`, before `self.phase = "confirm_parent"` and before `transition_to(PROCESSING)`:
+    - Run `self._check_preconditions()`. If non-empty → `send_message` a blocking message in the 3-part UX-DR12 format (combine the recovery reasons under **What to do**), do **not** transition to `PROCESSING`, and `return`. Do not connect MCP.
+    - Resolve the submitted Confluence URL: `confluence_url = (input_data.get("confluence_url") or "").strip()`, falling back to `project.confluence_base_url` only if you choose to pre-fill — but an empty result must still hit the "URL required" correction. Read `project` once (`db.get(Project, project_id)`) to obtain both `confluence_base_url` and `jira_base_url`.
+    - Run `_validate_confluence_url(...)`. If it returns a message → `send_message` the correction (`message_type="error"`), do **not** transition to `PROCESSING`, and `return` (the START input form stays so the user can resubmit). **Do not** start extraction.
+    - Run `_validate_jira_ref(input_data.get("jira_url"), jira_base_url)`. If it returns a message → send the correction and `return` (same no-start behavior). Otherwise stash `self._jira_ref`.
+  - [ ] 4.2 Only after all gates pass, fall through to the **existing** extraction logic (`self.phase = "confirm_parent"` → `transition_to(PROCESSING)` → `self.process(...)`). Leave that block unchanged.
+  - [ ] 4.3 Decide blocking-state semantics and keep them consistent: for AC2/AC3 the agent must **not** enter `PROCESSING`. Prefer leaving the state at `START` (re-submittable) rather than `ERROR`, so the frontend keeps showing the input form. If you transition at all, document why. Verify the frontend renders the correction message and still allows resubmission (it reads `START` state to show `renderStartState`).
+
+- [ ] **Task 5 — Frontend: send the Jira reference and gate the field on Jira-enabled (AC1)**
+  - [ ] 5.1 [frontend/src/App.tsx](frontend/src/App.tsx) `handleBobStart` (~line 883): include `jira_url` in `inputData` when present (read from the same source the input form/`bobState` uses). Today only `mcp_pat` + `confluence_url` are sent; `jira_url` is dropped.
+  - [ ] 5.2 Show the optional Jira field **only when Jira is enabled** for the selected project (`selectedProject?.jira_base_url`). Keep this minimal — gate visibility where the Bob start fields are rendered (`ChatInputArea` start state / `AGENTS.Bob.inputConfig`). Do not over-engineer a new settings flow.
+  - [ ] 5.3 If the start payload TS type changes, update the matching interface in `frontend/src/types/` and run `npm run typecheck` (per full-stack-sync rule). If no type changed, skip.
+
+- [ ] **Task 6 — Unit tests (AC1/AC2/AC3)**
+  - [ ] 6.1 Extend [tests/test_agents/test_bob.py](tests/test_agents/test_bob.py) (same dir/file as existing Bob tests; reuse the `bob_agent` + `mock_project_context` fixtures). Match the existing style: `@pytest.mark.asyncio`, `unittest.mock` `AsyncMock`/`MagicMock`, `patch("ai_qa.agents.bob.<symbol>")`. (Project runs `asyncio_mode = "auto"` but existing tests still mark explicitly — match them.)
+  - [ ] 6.2 **AC3 preconditions — each blocks without MCP:** patch `ai_qa.agents.bob.MCPClient` and assert it is **never instantiated** (`assert mock_mcp_client_class.call_count == 0`) for: (a) missing thread provider config, (b) MCP status not configured. Drive the MCP status via the `db.scalar`/`get_secret_status` path — point `get_secret_status` (patch `ai_qa.agents.bob.get_secret_status`) at a `SecretStatus(configured=False, ...)`. Assert a blocking message was sent and state did not advance to `PROCESSING`.
+  - [ ] 6.3 **AC2 URL rules:** unit-test `_validate_confluence_url` directly (no async needed): empty → required message; `"not a url"` / `"https://evil.com/x"` → invalid/format message; valid-format but wrong host vs configured base → host-mismatch message; valid cloud + matching host → `None`. Plus one `handle_start` test: invalid URL → correction sent, `MCPClient` not instantiated, no `PROCESSING`.
+  - [ ] 6.4 **AC1 Jira intake:** unit-test `_validate_jira_ref`: disabled project + any ref → `None`; enabled + `"PROJ-123"` → `None`; enabled + matching-host URL → `None`; enabled + foreign-host URL → correction; enabled + garbage → correction. One `handle_start` test asserting `self._jira_ref` is stashed when valid and Jira enabled.
+  - [ ] 6.5 **Happy-path regression:** confirm a valid start with all preconditions met still reaches the existing `confirm_parent` flow (reuse the pattern from `test_bob_handle_start_confirm_parent`, but with preconditions satisfied via the mocks). Ensure existing Bob tests still pass — the gate must not break `test_bob_handle_start_confirm_parent` / `_review_markdown` / `_error` (those patch `process` directly; verify their mocked contexts satisfy the new gate, or adjust the fixture's thread/secret mocks centrally).
+
+- [ ] **Task 7 — Full gate + DoD**
+  - [ ] 7.1 `uv run ruff check .` and `uv run mypy src` — clean.
+  - [ ] 7.2 `uv run pytest tests/test_agents/test_bob.py -v` — all green (new + existing).
+  - [ ] 7.3 **No DB migration** — no schema change. Confirm `uv run alembic upgrade head` is a no-op.
+  - [ ] 7.4 If `frontend/` was touched: `cd frontend && npm run typecheck` clean. Otherwise skip.
+  - [ ] 7.5 Update the Dev Agent Record (file list, commands run, outputs).
+
+---
+
+## Dev Notes
+
+### Where the gate lives and what it must NOT do
+
+The gate is **synchronous, pure validation** that runs at the top of `handle_start` before any state transition. It performs DB reads (`Thread`, `Project`, secret status) and string validation only. It does **not** open an MCP connection, decrypt secrets, or call any agent LLM. The existing extraction path below it is untouched.
+
+Current `handle_start` (the part you prepend to):
+
+```python
+# src/ai_qa/agents/bob.py — existing, DO NOT rewrite the body below the gate
+async def handle_start(self, input_data: dict[str, Any]) -> None:
+    self.phase = "confirm_parent"
+    await self.transition_to(AgentState.PROCESSING)
+    try:
+        result = await self.process(input_data)   # connects to MCP, etc.
+    ...
+```
+
+After this story:
+
+```python
+async def handle_start(self, input_data: dict[str, Any]) -> None:
+    # --- 11.2 intake gate (NEW) — runs before any MCP/processing ---
+    blockers = self._check_preconditions()                  # AC3
+    if blockers:
+        await self.send_message(self._format_blocked_message(blockers), message_type="error")
+        return  # no PROCESSING, no MCP
+
+    project = self._load_project()                          # db.get(Project, project_id), once
+    confluence_url = (input_data.get("confluence_url") or "").strip()
+    url_err = self._validate_confluence_url(                # AC2
+        confluence_url, project.confluence_base_url if project else None
+    )
+    if url_err:
+        await self.send_message(url_err, message_type="error")
+        return  # clear correction, no extraction
+
+    jira_err = self._validate_jira_ref(                     # AC1 (optional)
+        input_data.get("jira_url"), project.jira_base_url if project else None
+    )
+    if jira_err:
+        await self.send_message(jira_err, message_type="error")
+        return
+    self._jira_ref = (input_data.get("jira_url") or "").strip() or None
+
+    # --- existing extraction flow (UNCHANGED) ---
+    self.phase = "confirm_parent"
+    await self.transition_to(AgentState.PROCESSING)
+    ...
+```
+
+### AC3 — what "provider configuration ready" means in code
+
+Alice persists provider/model selection on the **thread**: `Thread.provider_name` + `Thread.agent_configs` (a JSON dict keyed by lowercase agent name; `agent_configs["bob"]` holds `{"model": ..., "temperature": ...}` written by the 9.7+ `_save_configuration`). See [src/ai_qa/agents/base.py:113-136](src/ai_qa/agents/base.py) for how the base agent reads it. The precondition check should read the `Thread` **fresh** from the DB rather than relying on `self._provider_config`/`self._agent_config` (those are loaded once at `set_project_context` time and can be stale if Alice configured after the cached agent was created — agents are cached per `(user_id, project_id, step)`).
+
+```python
+# Inside _check_preconditions (sketch)
+reasons: list[str] = []
+ctx = self.project_context
+if not ctx or not ctx.project_id or not ctx.user_id or not ctx.thread_id:
+    return ["Start Bob from inside an active project thread."]  # nothing else is reachable
+
+db = ctx.artifact_service.db if ctx.artifact_service else None
+if db is None:
+    return ["The backend storage service is unavailable — contact support."]
+
+from ai_qa.threads.models import Thread
+thread = db.get(Thread, ctx.thread_id)
+bob_cfg = (thread.agent_configs or {}).get("bob") if thread else None
+bob_model = (bob_cfg.get("model") or bob_cfg.get("model_name")) if isinstance(bob_cfg, dict) else None
+if not thread or not thread.provider_name or not bob_model:
+    reasons.append("Complete provider and model setup with Alice before starting Bob.")
+
+from ai_qa.secrets.service import get_secret_status
+if not get_secret_status(db, ctx.user_id, SECRET_TYPE_MCP).configured:
+    reasons.append("Add your MCP key in provider configuration, then retry.")
+return reasons
+```
+
+`(thread.agent_configs or {})` uses the `.items()`/empty-dict-fallback rule for JSON columns from project-context. Guard `bob_cfg` with `isinstance(..., dict)` to tolerate the legacy flat-string shape (see base.py:128-131).
+
+### AC2 — the "configured Confluence URL rules"
+
+There is **no** dedicated allow-list setting. The project's `confluence_base_url` is the configuration: an accepted URL must (1) be a structurally valid Confluence URL per `ConfluenceURLParser.is_valid_confluence_url`, (2) live on the **same host** as the configured base URL (when one is set), and (3) expose a page id or space key so extraction can proceed. Compare hosts with `urlparse(url).netloc.lower()`; if `confluence_base_url` is empty, skip the host rule (can't enforce what isn't configured) but keep format + identifier rules.
+
+```python
+@staticmethod
+def _host(url: str) -> str:
+    from urllib.parse import urlparse
+    return (urlparse(url).netloc or "").lower()
+```
+
+Reuse the accepted-format hint text already present in `ConfluenceReader.read_page` ([confluence_reader.py:298-303](src/ai_qa/pipelines/confluence_reader.py)) so the correction message lists the same three URL shapes.
+
+### AC1 — Jira is optional and must never block Confluence
+
+Jira-enabled = `project.jira_base_url` is set (no feature flag exists; confirmed in config + DB models). If Jira is disabled, ignore any `jira_url` the frontend sends — do not error. If enabled, accept a bare issue key (`^[A-Z][A-Z0-9_]+-\d+$`) or a same-host URL; otherwise return a correction. **No retrieval** — Story 11.4 owns calling MCP Jira tools and uses the `JiraReader` being added in Story 11.1. Carry the validated reference on `self._jira_ref` for that later consumer; nothing reads it in this story.
+
+> Cross-story note: `JiraReader` / `_parse_issue_ref` (Story 11.1, `ready-for-dev`) may not be merged when you implement 11.2. **Do not import or depend on `JiraReader` here.** Use a small local regex for the bare-key check. If 11.1 has merged, you may still keep the local check — intake validation is intentionally lightweight and independent of retrieval.
+
+### Error / messaging contract
+
+All blocking and correction messages go through `send_message(..., message_type="error")` and follow the 3-part UX-DR12 shape (**What happened / Why / What to do**) — same structure as `BaseAgent._format_error_message`. Add a small `_format_blocked_message(reasons: list[str]) -> str` that renders the precondition reasons as the **What to do** bullet list. Never include secret values, tokens, tracebacks, or raw config dicts in any message (security rule). The MCP precondition reports only "configured / not configured" — it never reflects the secret itself.
+
+### Do NOT regress these existing behaviors
+
+- The existing `confirm_parent` → `_extract_descendants` → paginated `review_markdown` flow must still work end-to-end once the gate passes. The gate is additive.
+- `process()` still resolves the MCP PAT via `_resolve_mcp_pat()` at extraction time (decryption stays in the extraction path, not the gate). Leave it.
+- Existing tests `test_bob_handle_start_confirm_parent`, `test_bob_handle_start_review_markdown`, `test_bob_handle_start_error` patch `process` directly. With the new gate, these now also need preconditions satisfied (thread provider config + MCP status configured) to reach `process`. Update the shared `mock_project_context`/`mock_db` fixture once so the default mock represents a fully-configured, MCP-ready thread, OR satisfy per-test. The current `mock_db` returns a `Thread(provider_name="claude")` but **no `agent_configs`** and `db.scalar` returns `None` (so MCP status = not configured) — both will now block. Fix centrally in [tests/conftest.py](tests/conftest.py) so the happy-path default passes the gate, then add explicit negative tests that override.
+
+### Frontend touch (minimal)
+
+`handleBobStart` ([App.tsx:883](frontend/src/App.tsx)) currently sends only `mcp_pat` + `confluence_url` (from `selectedProject?.confluence_base_url`). Add `jira_url` to the payload when present, and only surface the Jira input when `selectedProject?.jira_base_url` is set. The `confluence_url`/`jira_url`/`mcp_pat` fields already exist in `AGENTS.Bob.inputConfig` ([pipeline.ts:186-211](frontend/src/types/pipeline.ts)). Keep this change surgical; the backend gate is the source of truth for validation.
+
+### Project Structure Notes
+
+**Modified files:**
+
+- `src/ai_qa/agents/bob.py` — add `_check_preconditions()`, `_validate_confluence_url()`, `_validate_jira_ref()`, `_load_project()` helper, `_format_blocked_message()`, `self._jira_ref` field; prepend the gate to `handle_start`. No change to `process()`/`_extract_descendants()`/`handle_approve()`/`handle_reject()`.
+- `tests/test_agents/test_bob.py` — add gate tests; reuse fixtures.
+- `tests/conftest.py` — adjust `mock_db`/`mock_project_context` so the default mock is a fully-Alice-configured, MCP-configured thread (so existing happy-path tests still reach `process`).
+- `frontend/src/App.tsx` — send `jira_url`; gate Jira field on `jira_base_url`.
+- `frontend/src/components/ChatInputArea.tsx` and/or `frontend/src/types/pipeline.ts` — conditional Jira field visibility (only if needed for 5.2).
+
+**New files:** none required. **No DB migration. No new packages.**
+
+### Previous-story intelligence
+
+- **Story 11.1** (`ready-for-dev`, not yet implemented) — adds `JiraReader`, `JiraIssue`, `MCPClient.check_required_tools()`, `ConfluenceReader.check_tool_availability()`. 11.2 does **not** depend on these (intake validation is independent of retrieval). Keep the Jira reference check self-contained.
+- **Epic 3** (done) — built `MCPClient`, `ConfluenceReader`, `ConfluenceURLParser`. Production code; reuse, don't refactor.
+- **Epic 9** (done) — built `SECRET_TYPE_MCP`, `get_user_secret`, `get_secret_status`, runtime secret resolution in Bob. The MCP precondition reuses `get_secret_status` (status-only).
+- **Epic 10** (in-progress) — artifact storage/sync; `PipelineContext.artifact_service` carries the `db` Bob uses. No conflicts.
+
+### Git intelligence (recent work patterns)
+
+Recent commits center on Epic 10 artifact events (`9d878c5 feat(api): emit project-scoped artifact change events`, `1852886 feat(10-3): artifact read and preview access`) and the 3.12→3.14 upgrade (`39db313`). None touch Bob intake — no merge-conflict risk for this story. The established pattern for agent precondition failures is the 3-part UX-DR12 message via `send_message(message_type="error")` (see Bob's existing `_resolve_mcp_pat` raises and `BaseAgent._format_error_message`). Follow it.
+
+### Testing approach
+
+- `asyncio_mode = "auto"` is set in [pyproject.toml](pyproject.toml), but existing Bob tests still annotate `@pytest.mark.asyncio` — match them for consistency.
+- Mock the MCP layer by patching `ai_qa.agents.bob.MCPClient`; assert `call_count == 0` to prove the gate blocked before any connection.
+- Patch `ai_qa.agents.bob.get_secret_status` to return a `SecretStatus(...)` with `configured=True/False`. Import: `from ai_qa.secrets.service import SecretStatus`.
+- For `_validate_confluence_url` / `_validate_jira_ref`, call them directly (pure, sync) — fastest, no event loop needed (a plain `def test_...`).
+- Drive the `Thread`/`Project` via the existing `mock_db.get` side-effect (it already routes `Thread` and falls through to `MagicMock()` for `Project`). Add `agent_configs={"bob": {"model": "x"}}` to the mocked `Thread` for the happy path.
+
+### References
+
+- [Source: _bmad-output/planning-artifacts/epics.md#Story-11.2] — the three ACs
+- [Source: _bmad-output/planning-artifacts/architecture.md#Agents] — Alice (Config) → Bob (Extract) flow; Bob composes `confluence_reader` + `content_parser`
+- [Source: src/ai_qa/agents/bob.py] — `handle_start`, `process`, `_resolve_mcp_pat`, `_extract_descendants` (the flow being gated)
+- [Source: src/ai_qa/agents/base.py] — `AgentState`, `transition_to`, `send_message`, `_load_agent_config`, `get_llm_config`, `_format_error_message`
+- [Source: src/ai_qa/pipelines/confluence_reader.py#ConfluenceURLParser] — `is_valid_confluence_url`, `extract_page_id`, `extract_space_key`, accepted-format hints
+- [Source: src/ai_qa/secrets/service.py] — `get_secret_status`, `SecretStatus(configured=...)`
+- [Source: src/ai_qa/secrets/__init__.py] — `SECRET_TYPE_MCP`
+- [Source: src/ai_qa/pipelines/context.py] — `PipelineContext` fields
+- [Source: src/ai_qa/threads/models.py] — `Thread.provider_name`, `agent_configs` (Alice readiness)
+- [Source: src/ai_qa/db/models.py] — `Project.confluence_base_url`, `Project.jira_base_url` (Jira-enabled signal)
+- [Source: src/ai_qa/api/websocket.py] — `_handle_action` → `handle_start(inputData)`; `confluence_url`/`jira_url`/`mcp_pat` arrive here
+- [Source: frontend/src/App.tsx#handleBobStart] — start payload Bob sends
+- [Source: frontend/src/types/pipeline.ts#AGENTS.Bob] — input fields
+- [Source: tests/test_agents/test_bob.py] — existing Bob test patterns + fixtures
+- [Source: project-context.md] — `uv` only; Ruff + Mypy strict; no `# type: ignore`; no bare `except`; JSON-column `.items()`/empty-dict fallback; never `python3`; security (no secret/config logging)
+
+### Definition of Done
+
+- [ ] `_check_preconditions()` blocks start (no MCP connection) when project/thread context, Alice provider config, or MCP credential status is missing, with a UX-DR12 recovery message (AC3).
+- [ ] `_validate_confluence_url()` rejects empty / malformed / wrong-host / identifier-less URLs with a clear correction and **does not start extraction**; accepts a valid same-host page URL (AC2).
+- [ ] `_validate_jira_ref()` accepts a valid issue key or same-host Jira URL when Jira is enabled, ignores Jira input when disabled, and never blocks Confluence extraction (AC1); accepted reference stashed on `self._jira_ref`.
+- [ ] The gate runs before `transition_to(PROCESSING)`; the existing `confirm_parent`/extraction flow is unchanged and still reachable on the happy path.
+- [ ] Frontend sends `jira_url` when present and only shows the Jira field when `jira_base_url` is configured.
+- [ ] New + existing Bob tests pass: `uv run pytest tests/test_agents/test_bob.py -v`.
+- [ ] `uv run ruff check .` and `uv run mypy src` — clean. `frontend` typecheck clean if touched.
+- [ ] `uv run alembic upgrade head` is a no-op (no schema change).
+
+---
+
+## Dev Agent Record
+
+### Agent Model Used
+
+{{agent_model_name_version}}
+
+### Debug Log References
+
+### Completion Notes List
+
+- Ultimate context engine analysis completed — comprehensive developer guide created.
+
+### File List
+
+### Change Log
warning: in the working copy of 'frontend/e2e/story-10-3-artifact-preview.spec.ts', LF will be replaced by CRLF the next time Git touches it
diff --git a/frontend/e2e/story-10-3-artifact-preview.spec.ts b/frontend/e2e/story-10-3-artifact-preview.spec.ts
new file mode 100644
index 0000000..a4a6cd1
--- /dev/null
+++ b/frontend/e2e/story-10-3-artifact-preview.spec.ts
@@ -0,0 +1,219 @@
+import process from "node:process";
+import type { APIRequestContext } from "@playwright/test";
+import { test, expect } from "../support/fixtures";
+import { createStandardUser, getAdminToken } from "../support/helpers/users";
+
+const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
+const adminPassword =
+  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;
+
+if (!adminPassword) {
+  throw new Error(
+    "Story 10.3 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
+  );
+}
+
+type AdminProject = {
+  id: string;
+  name: string;
+  description: string | null;
+};
+
+type ArtifactResponse = {
+  id: string;
+  project_id: string;
+  kind: string;
+  name: string;
+  current_version: number;
+  created_at: string;
+  updated_at: string;
+};
+
+async function registerStandardUser(
+  request: APIRequestContext,
+  user: { email: string; displayName: string; password: string },
+) {
+  return createStandardUser(request, user);
+}
+
+async function createAdminProject(
+  request: APIRequestContext,
+  token: string,
+  name: string,
+): Promise<AdminProject> {
+  const response = await request.post(`${apiBaseUrl}/api/admin/projects`, {
+    headers: { Authorization: `Bearer ${token}` },
+    data: {
+      name,
+      description: `${name} description`,
+      confluence_base_url: `https://confluence.example.test/${encodeURIComponent(name)}`,
+      enabled_providers: ["on-premises"],
+    },
+  });
+  expect(response.ok()).toBeTruthy();
+  return response.json() as Promise<AdminProject>;
+}
+
+async function assignMembership(
+  request: APIRequestContext,
+  token: string,
+  projectId: string,
+  userId: string,
+) {
+  const response = await request.post(
+    `${apiBaseUrl}/api/admin/projects/${projectId}/memberships`,
+    {
+      headers: { Authorization: `Bearer ${token}` },
+      data: { user_id: userId, role: "member" },
+    },
+  );
+  expect(response.ok()).toBeTruthy();
+}
+
+async function createArtifact(
+  request: APIRequestContext,
+  token: string,
+  projectId: string,
+  kind: string,
+  name: string,
+  content: string,
+  content_encoding: "text" | "base64" = "text"
+): Promise<ArtifactResponse> {
+  const response = await request.post(
+    `${apiBaseUrl}/api/projects/${projectId}/artifacts`,
+    {
+      headers: { Authorization: `Bearer ${token}` },
+      data: { kind, name, content, content_encoding },
+    },
+  );
+  expect(response.ok()).toBeTruthy();
+  return response.json() as Promise<ArtifactResponse>;
+}
+
+test.describe("Story 10.3 Artifact Read and Preview Access", () => {
+  let createdUserIds: string[] = [];
+  let createdProjectIds: string[] = [];
+
+  test.beforeEach(async ({ page }) => {
+    await page.addInitScript(() => {
+      window.localStorage.removeItem("ai-qa-selected-project-id");
+      window.localStorage.removeItem("ai-qa-thread-id");
+      window.localStorage.removeItem("ai-qa-thread-user-id");
+      window.localStorage.removeItem("aiqa_access_token");
+    });
+  });
+
+  test.afterEach(async ({ request }) => {
+    if (createdUserIds.length === 0 && createdProjectIds.length === 0) return;
+    try {
+      const adminToken = await getAdminToken();
+      for (const projectId of createdProjectIds) {
+        await request.delete(`${apiBaseUrl}/api/admin/projects/${projectId}`, {
+          headers: { Authorization: `Bearer ${adminToken}` },
+        });
+      }
+      for (const userId of createdUserIds) {
+        await request.delete(`${apiBaseUrl}/api/admin/users/${userId}`, {
+          headers: { Authorization: `Bearer ${adminToken}` },
+        });
+      }
+    } catch (e) {
+      console.error(`Cleanup failed: ${e instanceof Error ? e.message : e}`);
+    } finally {
+      createdUserIds = [];
+      createdProjectIds = [];
+    }
+  });
+
+  test("Renders markdown, code, and image artifacts with creator metadata", async ({
+    page,
+    request,
+    userFactory,
+  }) => {
+    const adminToken = await getAdminToken();
+    const user = userFactory.create({
+      email: `story-10-3-user-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
+      displayName: "Story 10.3 Preview User",
+      password: "secretpassword",
+      role: "standard",
+    });
+    const registeredUser = await registerStandardUser(request, user);
+    createdUserIds.push(registeredUser.id);
+
+    const project = await createAdminProject(
+      request,
+      adminToken,
+      `S10.3 Preview ${Date.now()}-${Math.random().toString(36).slice(2)}`,
+    );
+    createdProjectIds.push(project.id);
+    await assignMembership(request, adminToken, project.id, registeredUser.id);
+
+    // Create artifacts of different kinds
+    await createArtifact(
+      request,
+      adminToken,
+      project.id,
+      "requirements",
+      "Markdown Test.md",
+      "# Markdown Header\nThis is a test of markdown rendering."
+    );
+
+    await createArtifact(
+      request,
+      adminToken,
+      project.id,
+      "playwright_script",
+      "Code Test.ts",
+      "// A typescript comment\nconst x = 1;"
+    );
+
+    // 1x1 transparent PNG base64
+    const transparentPngBase64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
+    await createArtifact(
+      request,
+      adminToken,
+      project.id,
+      "screenshot",
+      "Image Test.png",
+      transparentPngBase64,
+      "base64"
+    );
+
+    // Login
+    await page.goto("/");
+    await page.getByLabel("Email").fill(user.email);
+    await page.getByLabel("Password").fill(user.password);
+
+    const threadPost = page.waitForResponse(
+      (response) =>
+        new URL(response.url()).pathname.endsWith("/api/threads") &&
+        response.request().method() === "POST",
+    );
+
+    await page.getByRole("button", { name: "Sign In" }).click();
+    await expect(page.getByText(user.displayName)).toBeVisible({ timeout: 15_000 });
+    await threadPost;
+
+    // Verify Markdown
+    await page.getByText("Markdown Test.md").click();
+    await expect(page.getByRole("heading", { name: "Markdown Header", exact: true })).toBeVisible({ timeout: 15_000 });
+    await expect(page.getByText("created by admin")).toBeVisible(); // Since created via admin token
+    await page.getByRole("button", { name: "Close preview" }).click();
+
+    // Verify Code
+    await page.getByText("Code Test.ts").click();
+    await expect(page.getByRole("heading", { name: "Code Test.ts", exact: true })).toBeVisible({ timeout: 15_000 });
+    // Prism tokenizes code, so exact string match is hard, but we can verify the text content exists
+    const codeArea = page.locator("code");
+    await expect(codeArea).toContainText("const x = 1;");
+    await page.getByRole("button", { name: "Close preview" }).click();
+
+    // Verify Image
+    await page.getByText("Image Test.png").click();
+    await expect(page.getByRole("heading", { name: "Image Test.png", exact: true })).toBeVisible({ timeout: 15_000 });
+    const img = page.getByRole("img", { name: "Image Test.png" });
+    await expect(img).toBeVisible();
+    await expect(img).toHaveAttribute("src", /^data:image\/png;base64,/);
+    await page.getByRole("button", { name: "Close preview" }).click();
+  });
+});
warning: in the working copy of 'tests/integration/test_artifact_service_integration.py', LF will be replaced by CRLF the next time Git touches it
diff --git a/tests/integration/test_artifact_service_integration.py b/tests/integration/test_artifact_service_integration.py
new file mode 100644
index 0000000..0ad5fc1
--- /dev/null
+++ b/tests/integration/test_artifact_service_integration.py
@@ -0,0 +1,229 @@
+"""Integration tests for AC3: thread_id propagation and no-bypass import guard.
+
+Story 10-5 acceptance criteria:
+  AC3-a: Artifacts saved via PipelineArtifactAdapter carry the thread_id from
+          PipelineContext — no artifact should land in a second project's query.
+  AC3-b: OutputWriter must not be importable from any production path — it was
+          deleted as part of this story so any lingering reference is a bug.
+"""
+
+from __future__ import annotations
+
+from typing import cast
+from uuid import uuid4
+
+import pytest
+from sqlalchemy import Table, create_engine
+from sqlalchemy.orm import sessionmaker
+from sqlalchemy.pool import StaticPool
+
+from ai_qa.artifacts.service import ArtifactService
+from ai_qa.artifacts.storage import LocalArtifactStorage
+from ai_qa.db.base import Base
+from ai_qa.db.models import Artifact, ArtifactVersion, Project, User
+from ai_qa.pipelines.artifact_adapter import PipelineArtifactAdapter
+from ai_qa.pipelines.context import PipelineContext
+from ai_qa.threads.models import AgentRun, Thread
+
+
+# ---------------------------------------------------------------------------
+# Shared helpers
+# ---------------------------------------------------------------------------
+
+
+def _build_engine():
+    engine = create_engine(
+        "sqlite+pysqlite:///:memory:",
+        connect_args={"check_same_thread": False},
+        poolclass=StaticPool,
+    )
+    Base.metadata.create_all(
+        engine,
+        tables=cast(
+            "list[Table]",
+            [
+                User.__table__,
+                Project.__table__,
+                Thread.__table__,
+                AgentRun.__table__,
+                Artifact.__table__,
+                ArtifactVersion.__table__,
+            ],
+        ),
+    )
+    return engine
+
+
+# ---------------------------------------------------------------------------
+# AC3-a: cross-project read leak-canary
+# ---------------------------------------------------------------------------
+
+
+def test_cross_project_read_isolation_canary(tmp_path) -> None:
+    """[AC3] Artifact written in project-A is invisible to project-B adapter.
+
+    This is the leak-canary: if PipelineArtifactAdapter's load_* methods ever
+    return data from a foreign project, a real privacy/isolation regression has
+    been introduced and this test will fail loudly.
+    """
+    engine = _build_engine()
+    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
+    session = session_factory()
+    try:
+        user = User(
+            email="tester@example.com",
+            display_name="tester",
+            password_hash="hash",
+            role="standard",
+            is_active=True,
+        )
+        project_a = Project(name="ProjectA", created_by_user=user)
+        project_b = Project(name="ProjectB", created_by_user=user)
+        session.add_all([user, project_a, project_b])
+        session.commit()
+
+        thread_a = Thread(project_id=project_a.id, user_id=user.id)
+        thread_b = Thread(project_id=project_b.id, user_id=user.id)
+        session.add_all([thread_a, thread_b])
+        session.flush()
+        run_a = AgentRun(thread_id=thread_a.id, status="running")
+        run_b = AgentRun(thread_id=thread_b.id, status="running")
+        session.add_all([run_a, run_b])
+        session.commit()
+
+        storage = LocalArtifactStorage(root=tmp_path)
+        service = ArtifactService(session, storage)
+
+        ctx_a = PipelineContext(
+            project_id=project_a.id,
+            user_id=user.id,
+            user_email=user.email,
+            artifact_service=service,
+            agent_run_id=run_a.id,
+            thread_id=thread_a.id,
+        )
+        ctx_b = PipelineContext(
+            project_id=project_b.id,
+            user_id=user.id,
+            user_email=user.email,
+            artifact_service=service,
+            agent_run_id=run_b.id,
+            thread_id=thread_b.id,
+        )
+
+        adapter_a = PipelineArtifactAdapter(ctx_a)
+        adapter_b = PipelineArtifactAdapter(ctx_b)
+
+        # Write a requirement into project-A only
+        saved = adapter_a.save_requirement_page(
+            "requirements/page-001.md", "# Project A secret"
+        )
+        # Verify thread_id forwarding (AC1)
+        assert saved.thread_id == thread_a.id, (
+            "thread_id not forwarded — AC1 regression"
+        )
+        assert saved.project_id == project_a.id
+
+        # project-B adapter must not see project-A's artifacts
+        b_requirements = adapter_b.load_requirement_markdown()
+        assert b_requirements == [], (
+            "Cross-project read leak detected: project-B can see project-A artifacts"
+        )
+
+        # project-A adapter CAN see its own artifacts
+        a_requirements = adapter_a.load_requirement_markdown()
+        assert len(a_requirements) == 1
+        assert a_requirements[0].content == "# Project A secret"
+
+    finally:
+        session.close()
+    engine.dispose()
+
+
+def test_thread_id_stamped_on_all_adapter_save_methods(tmp_path) -> None:
+    """[AC1] Every adapter save method forwards thread_id to ArtifactService.
+
+    Validates that requirements, test-cases, scripts, metadata, and image
+    artifacts all carry the thread_id from PipelineContext.
+    """
+    engine = _build_engine()
+    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
+    session = session_factory()
+    try:
+        user = User(
+            email="tester@example.com",
+            display_name="tester",
+            password_hash="hash",
+            role="standard",
+            is_active=True,
+        )
+        project = Project(name="ThreadTest", created_by_user=user)
+        session.add_all([user, project])
+        session.commit()
+
+        thread = Thread(project_id=project.id, user_id=user.id)
+        session.add(thread)
+        session.flush()
+        run = AgentRun(thread_id=thread.id, status="running")
+        session.add(run)
+        session.commit()
+
+        storage = LocalArtifactStorage(root=tmp_path)
+        service = ArtifactService(session, storage)
+
+        ctx = PipelineContext(
+            project_id=project.id,
+            user_id=user.id,
+            user_email=user.email,
+            artifact_service=service,
+            agent_run_id=run.id,
+            thread_id=thread.id,
+        )
+        adapter = PipelineArtifactAdapter(ctx)
+
+        req = adapter.save_requirement_page("req.md", "# Req")
+        tc = adapter.save_test_case("tc.json", '{"title": "T1"}')
+        script = adapter.save_script("script.spec.ts", "test('x', () => {})")
+        meta = adapter.save_metadata("meta.json", {"ok": True})
+
+        for artifact in (req, tc, script, meta):
+            assert artifact.thread_id == thread.id, (
+                f"artifact kind={artifact.kind!r} missing thread_id"
+            )
+    finally:
+        session.close()
+    engine.dispose()
+
+
+# ---------------------------------------------------------------------------
+# AC3-b: no-bypass import guard — OutputWriter must not be importable
+# ---------------------------------------------------------------------------
+
+
+def test_output_writer_is_not_importable() -> None:
+    """[AC2] OutputWriter class must not exist in any importable production module.
+
+    If this test fails it means output_writer.py was re-introduced or OutputWriter
+    was re-exported somewhere — both of which are regressions.
+    """
+    import importlib
+    import importlib.util
+
+    # The file was deleted; the module must not be findable
+    spec = importlib.util.find_spec("ai_qa.pipelines.output_writer")
+    assert spec is None, (
+        "ai_qa.pipelines.output_writer still exists on the module path — "
+        "OutputWriter deletion is incomplete"
+    )
+
+
+def test_output_writer_not_in_pipelines_namespace() -> None:
+    """[AC2] OutputWriter must not appear in the pipelines package __all__."""
+    import ai_qa.pipelines as pipelines_pkg
+
+    assert not hasattr(pipelines_pkg, "OutputWriter"), (
+        "OutputWriter is still exported from ai_qa.pipelines — remove from __all__"
+    )
+    assert "OutputWriter" not in getattr(pipelines_pkg, "__all__", []), (
+        "OutputWriter is still in ai_qa.pipelines.__all__"
+    )
