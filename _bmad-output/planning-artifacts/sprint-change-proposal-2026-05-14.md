# Sprint Change Proposal - Admin Dashboard Refinements

**Date:** 2026-05-14
**Trigger:** Admin dashboard testing revealed missing APIs, UI/UX issues, and new requirements for user management and synchronization.

## Section 1: Issue Summary

- **Problem Statement:** During testing of the newly implemented Admin Dashboard (Story 12.8), several functional and UX gaps were identified. These include missing backend APIs for project Edit/Delete actions, non-dismissing success notifications, a confusing "Manage Membership" UI, and the presence of self-registration on the login screen (which should be admin-only). Additionally, a new requirement emerged to support syncing users from Oracle sharedERP.
- **Context:** Story 12.8 successfully implemented the routing and basic layout, but left several UI components as non-functional stubs. The original Epic 12 did not fully detail the user assignment UX or explicitly prohibit self-registration.
- **Evidence:** Frontend error "Backend API endpoint not yet implemented for this action", manual testing feedback regarding the login screen, and the request for a disabled "Sync" button for future Oracle ERP integration.

## Section 2: Impact Analysis

- **Epic Impact:** Epic 12 needs an additional story to wrap up the administrative foundation. Epic 11 (currently deferred) will expand to include the Oracle ERP sync feature.
- **Story Impact:** 
  - Story 12.2 and 12.6 updated to explicitly remove self-registration.
  - New Story 12.9 created for the dashboard refinements.
  - New Story 11.2 created for the Oracle ERP integration.
- **Artifact Conflicts:** `epics.md` and `sprint-status.yaml` required updates to reflect the new stories and modified requirements.
- **Technical Impact:** Requires implementing `PUT` and `DELETE` endpoints for projects, modifying the React frontend to restructure the User card for project assignment, adding a User Creation form, and adjusting the login screen component.

## Section 3: Recommended Approach

- **Selected Approach:** Direct Adjustment (New Story 12.9) + Backlog Addition (New Story 11.2)
- **Rationale:** Creating a new Story 12.9 is cleaner than reopening the completed 12.8. It clearly scopes the remaining work needed to finalize the admin dashboard before moving on to Epic 6. The Oracle ERP sync is deferred to Epic 11 as it is a production integration feature, keeping the current sprint focused.
- **Effort Estimate:** Low for 12.9 (frontend UI tweaks + standard CRUD endpoints), Medium for 11.2 (integration).
- **Risk Level:** Low.

## Section 4: Detailed Change Proposals

*(These changes have already been applied to `epics.md` and `sprint-status.yaml` following user approval)*

- **Story 12.2 & 12.6:** Updated to enforce admin-only user creation and remove self-registration.
- **Story 12.9 (Added to Epic 12):**
  - Fix Edit/Delete project APIs.
  - 3-second auto-hide for success notifications.
  - Replace "Manage Membership" with "Create User" form.
  - Restructure project assignment into the User list cards (with `+` and `x` buttons).
  - Add disabled "Sync existing company's users" button with tooltip.
  - Remove "Create account" link from login screen.
- **Story 11.2 (Added to Epic 11):** 
  - Sync Company Users via Oracle sharedERP (Deferred).

## Section 5: Implementation Handoff

- **Change Scope:** Minor (for immediate implementation of 12.9).
- **Handoff Recipient:** Developer Agent
- **Responsibilities:** The Developer agent should use `bmad-quick-dev` or `bmad-dev-story` to implement Story 12.9. 
- **Success Criteria:** All Acceptance Criteria in Story 12.9 are met, and the admin dashboard functions flawlessly without placeholder errors.
