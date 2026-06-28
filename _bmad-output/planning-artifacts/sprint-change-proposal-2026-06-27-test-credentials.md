# Sprint Change Proposal — Test Credentials Redesign

- **Date**: 2026-06-27
- **Author**: Dev (BMAD correct-course)
- **Trigger source**: User feedback after observing that Project Admins hold test account passwords and Sarah's UI behavior.
- **Change scope classification**: **Moderate** — Backlog reorganization and adjustments to recent epic implementations.
- **Mode**: Batch

---

## Section 1 — Issue Summary

### What triggered it
The user observed the following issues with the current Test Credentials implementation (Epic 25):
1. **Security Policy Violation**: The Project Admin dashboard requires admins to input usernames, passwords, and TOTP secrets for test accounts. This violates the security policy that passwords must be kept by the individual users.
2. **UI Disconnect in Sarah**: The Sarah UI currently says "Not logged in" because it only looks for manually captured sessions, ignoring the auto-login credentials until execution time.
3. **Role Over-asking**: When Sarah asks for credentials, it asks for all roles defined in the project (e.g., 8 roles), even if the generated test cases only involve a subset of them (e.g., 4 roles).
4. **SSO vs Username/Password**: The current auto-login routine uses a generic browser-use prompt. However, some applications strictly use SSO, while others might use standard forms. The system needs to know which type of login is expected to handle it reliably.

### The core insight
- **Test Accounts** must be moved from Project-level configuration (managed by Project Admin) to **User-level Secrets** (managed by each individual user). 
- The Project Admin dashboard should only configure the **Login Type** and an optional **Login Hint** for the project/environment. Expanding the `login_type` enum (`standard`, `sso_microsoft`, `sso_google`, etc.) protects against LLM unreliability by allowing the backend to bypass AI entirely for standard forms, and gives explicit instructions for complex SSO flows.
- The UI in Sarah/Jack needs to dynamically filter the required roles based on the actual test cases being executed, and prompt the user to input their secrets if missing.

---

## Section 2 — Impact Analysis

### Epic Impact
- **Epic 25 (Security-Compliant Target-App Authentication)**: Needs revision. 
  - Story 25-3 (Test-account credential store) must be refactored to store credentials at the user-level (User Secrets) rather than the project-level.
  - Story 25-5 (Wire into Sarah explore + Jack run) must be updated to dynamically extract required roles from test cases and prompt the user for input.
  - The Project Admin UI must be stripped of credential inputs and replaced with a `login_type` configuration.

### Artifact Conflicts
- **PRD**: Needs updating to reflect that test credentials are user-owned secrets, and Project Admins only configure the authentication strategy (SSO vs Standard).
- **Epics**: Epic 25 description and related stories need updates to reflect the user-secret model and dynamic role filtering.
- **Architecture/Design Notes**: `design-security-compliant-target-app-auth-2026-06-25.md` needs to be updated to change `TestAccountCredential` to a user-scoped entity and introduce the `login_type` configuration.

---

## Section 3 — Recommended Approach

### The Mechanism
1. **Remove Test Accounts from Project Admin**: Strip all username/password/TOTP inputs from `TestCredentialsEditor.tsx` and the corresponding backend models/endpoints. **Crucially, write a DB migration to drop the existing project-level `test_account_credentials` table from the schema.**
2. **Add Login Type & Hint**: Add an expanded `login_type` enumeration (`standard`, `sso_microsoft`, `sso_google`, `sso_apple`, `sso_generic`, `custom`) and an optional `login_hint` field to the Project or Environment configuration in the Project Admin dashboard. This allows the backend to use fast, raw Playwright for `standard` forms, and gives local/weaker LLMs exact instructions for handling complex SSO flows via `browser-use`.
3. **User-level Secrets**: Implement a UI for individual users to input their test accounts when needed (e.g., when launching Sarah). Store these securely as user-scoped secrets, reusable across threads for that user.
4. **Dynamic Role Filtering**: Modify the `SarahInputsForm` logic to parse the selected test cases, extract the distinct roles required, and only prompt the user for sessions/credentials for those specific roles.

### Effort / Risk / Timeline
- **Effort**: Moderate. Requires migrating the recently added `TestAccountCredential` logic to a user-secret model and tweaking the UI/auto-login logic.
- **Risk**: Low-Medium. Aligns perfectly with standard security practices. The dynamic role parsing requires accurate extraction from the test cases.
- **Timeline**: Integrated into the current sprint, replacing/updating the remaining Epic 25 tasks.

---

## Section 4 — Detailed Change Proposals

### 4.1 PRD Updates
- Update the Administration section to explicitly state that Project Admins configure `login_type` (SSO vs Standard) but do NOT manage test credentials.
- Update the execution flow to specify that users manage their own test credentials as reusable user secrets.

### 4.2 Architecture/Design Updates
- Modify `design-security-compliant-target-app-auth-2026-06-25.md`:
  - `TestAccountCredential` scope changes from `(project_id, environment, role)` to `(user_id, project_id, environment, role)`.
  - Add `login_type` to Environment configuration.

### 4.3 Story Adjustments
- Rewrite Story 25-3 to implement user-scoped `TestAccountCredential` and Project Admin `login_type` configuration. **This MUST include writing a DB migration to remove the existing project-level `test_account_credentials` table from the DB schema.**
- Rewrite Story 25-5 to implement dynamic role filtering in `SarahInputsForm` based on test cases.

---

## Section 5 — Implementation Handoff

- **Scope**: Moderate.
- **Route to**: Product Owner / Developer agents for backlog reorganization and implementation.
- **Immediate next step**: Approval of this proposal, followed by artifact updates and `bmad-create-story` for the revised Epic 25 stories.
