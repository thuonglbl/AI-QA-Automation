# Sprint Change Proposal: Admin Field-Level Edit Permissions

## 1. Issue Summary
**Triggering Issue:** Currently, when an Admin logs in via Azure SSO, the system only retrieves the `name` and `email`, but does not get the `timezone` and `language` information. This causes the system to fallback to default values of `UTC` and `en`. However, the "Platform-Admin Immutability" rule in Story 15.5 completely locks down the edit permissions for Admin accounts on the Admin Dashboard screen, preventing Admins from manually correcting their `timezone` and `language`.
**Impact:** Admins cannot change incorrect `timezone` and `language` info caused by the SSO fallback process, negatively affecting user experience (incorrect time display, inappropriate language). 

## 2. Impact Analysis
- **Epic Impact:** Epic 15 (Admin Dashboard — Project-Admin RBAC and User/Project Management) is directly affected.
- **Story Impact:** Story 15.5 ("User Edit and Delete with Platform-Admin Immutability") must be refined.
- **Artifact Conflicts:** 
  - `epics.md`: Needs updates to redefine platform-admin immutability from row-level to field-level.
- **Technical Impact:** 
  - Backend: The `update_user` endpoint in `api/admin.py` needs a conditional logic update to accept updates to `timezone`, `language`, and `display name` for `admin` role targets, but reject updates to `role`, `active status`, and `password`.
  - Frontend: The Admin Dashboard user edit form must enable the Edit button for admin rows, but disable/hide the `role`, `active status`, and `password` fields when the target user is an admin.

## 3. Recommended Approach
**Direct Adjustment:** We will modify Story 15.5 within Epic 15 to introduce field-level immutability. 
- **Rationale:** This is a minor refinement to an existing requirement that does not affect the project timeline or MVP scope. It securely solves the problem by allowing edits to safe preferences while preserving the security goals of platform-admin immutability.
- **Effort Estimate:** Low
- **Risk Level:** Low

## 4. Detailed Change Proposals

### Artifact: `epics.md`

**Story: Story 15.5: User Edit and Delete with Platform-Admin Immutability**

**OLD:**
```markdown
### Story 15.5: User Edit and Delete with Platform-Admin Immutability

As a platform admin,
I want to edit and delete project_admin and standard users,
So that I can manage the user directory while the platform admin account stays protected.

**Acceptance Criteria:**

**Given** a project_admin or standard user
**When** the admin edits it
**Then** a new update-user endpoint updates display name, role (project_admin↔standard only), timezone, active status, and optional password reset, returning a secret-free response

**Given** a role change between project_admin and standard
**When** the update is applied
**Then** standard→project_admin requires a project and creates the project_admin membership; project_admin→standard deletes the user's project_admin membership(s)

**Given** the platform admin account (role=admin)
**When** any actor attempts to edit or delete it
**Then** the action is rejected (403); promoting any user to admin is also rejected

**Given** the current admin
**When** they attempt to deactivate or delete their own account
**Then** the action is rejected to prevent lockout

**Given** a non-admin caller
**When** they call the update or delete user endpoints
**Then** access is denied (403)

**Given** the Users Management list
**When** rows render
**Then** Edit and Delete controls appear for project_admin and standard users but NOT for the platform admin row, with distinct accessible labels
```

**NEW:**
```markdown
### Story 15.5: User Edit and Delete with Platform-Admin Immutability

As a platform admin,
I want to edit and delete project_admin and standard users, and edit basic info for platform admins,
So that I can manage the user directory while the platform admin account's role and security stays protected.

**Acceptance Criteria:**

**Given** a project_admin or standard user
**When** the admin edits it
**Then** a new update-user endpoint updates display name, language, role (project_admin↔standard only), timezone, active status, and optional password reset, returning a secret-free response

**Given** a role change between project_admin and standard
**When** the update is applied
**Then** standard→project_admin requires a project and creates the project_admin membership; project_admin→standard deletes the user's project_admin membership(s)

**Given** the platform admin account (role=admin)
**When** any actor attempts to edit it
**Then** the endpoint allows updating non-security fields (`timezone`, `language`, `display name`)
**And** any attempt to update `role`, `active status`, or `password` is rejected (403)
**And** promoting any user to admin is also rejected
**And** any attempt to delete the account is rejected

**Given** the current admin
**When** they attempt to deactivate or delete their own account
**Then** the action is rejected to prevent lockout

**Given** a non-admin caller
**When** they call the update or delete user endpoints
**Then** access is denied (403)

**Given** the Users Management list
**When** rows render
**Then** Edit controls appear for all users, but Delete controls appear ONLY for project_admin and standard users (NOT for platform admin)
**And** when editing a platform admin, the role, status, and password fields are hidden or disabled in the UI
```

## 5. Implementation Handoff
- **Scope:** Minor (Can be implemented directly by the Developer agent)
- **Handoff Recipients:** Developer Agent (Amelia / `bmad-quick-dev`)
- **Responsibilities:** 
  - Update `epics.md` as outlined above.
  - Implement backend changes in `api/admin.py` to allow partial updates for `admin` accounts.
  - Implement frontend changes in `components/admin/AdminDashboard.tsx` to enable the Edit button for admins and conditionally disable restricted fields.
- **Success Criteria:** Platform Admins can successfully edit `timezone`, `language`, and `display name` for themselves and other admins, but cannot delete admins or change their role/status/password.

## User Review Required
Please review this proposal. If you approve, I will automatically update the `epics.md` file and provide handoff instructions for implementation.
