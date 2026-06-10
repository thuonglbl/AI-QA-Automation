# Sprint Change Proposal — 2026-06-08

**Author:** Thuong
**Date:** 2026-06-08
**Scope Classification:** Minor–Moderate (direct implementation by Developer, no architecture replan required)

---

## Section 1: Issue Summary

### Problem Statement

Four new requirements have been identified that were not included in the original plan. They relate to the Admin Dashboard "Create Project" form and the user-facing Alice provider selection screen:

1. **Jira Base URL field** — The Create Project form currently has only `Confluence Base URL` (required). Admin must be able to optionally provide a Jira Base URL. Both Confluence and Jira are optional individually, but **at least one must be provided**. If neither is provided and the admin clicks "Create project", an error is shown: "No link to extract requirement."

2. **Provider enable/disable checkboxes on project** — The Create Project form needs 5 checkboxes to enable or disable providers at the project level: Browser Use, Claude, Gemini, ChatGPT, On Premises. At least one provider must be enabled. If no provider is selected and the admin clicks "Create project", an error is shown: "No provider to execute."

3. **Projects list enhancements** — The Projects panel must display the Jira link (if set) alongside the existing Confluence link. When a project has enabled providers, the icon for each enabled provider is shown (using icons from `frontend/public/provider-icons/`).

4. **User-facing provider disable enforcement** — When a provider is disabled at the project level, users on Alice Step 1 cannot select that provider. Disabled providers appear greyed out, are not clickable, and on hover show the tooltip: "Your project cannot choose this provider. Please contact administrator if something wrong."

### When Discovered

Identified during sprint execution when reviewing the Admin Dashboard UI against real-world admin workflows and Alice Step 1 provider selection against project-level configuration needs.

### Evidence

Screenshots provided showing current Create Project form (Confluence Base URL is required, no Jira field, no provider checkboxes) and Alice Step 1 provider list (all 5 providers always selectable regardless of project configuration).

---

## Section 2: Impact Analysis

### Epic Impact

| Epic | Impact |
|------|--------|
| **Epic 8 — Admin Dashboard** | Story 8.3 and 8.5 must be updated: Create Project validation logic changes, project list display changes, edit project form changes |
| **Epic 9 — Provider Setup / Alice Step 1** | ProviderSelector must respect project-level enabled_providers; disabled providers get greyed-out state + tooltip |
| **No impact** | Epic 7 (threads), Epic 10 (artifacts), Epic 11–15 (pipeline agents), Epic 16 (workspace shell) are unaffected |

### Story Impact

| Story | Change Type |
|-------|-------------|
| Story 8.3: Admin Project Management | Update — validation logic changes (at-least-one-link rule, at-least-one-provider rule); DB schema adds `jira_base_url` and `enabled_providers` |
| Story 8.5: Admin Dashboard UI Layout | Update — Create Project form adds Jira URL field + provider checkboxes; Projects list shows Jira link + provider icons |
| Story 9.3 / Alice ProviderSelector | Update — ProviderSelector receives `enabled_providers` from project context; disabled providers are visually locked with tooltip |

### Artifact Conflicts

| Artifact | Change Required |
|----------|-----------------|
| `src/ai_qa/db/models.py` | Add `jira_base_url: str | None` and `enabled_providers: list[str]` (JSON column) to `Project` model |
| `alembic/versions/` | New migration: add `jira_base_url` (VARCHAR 512 nullable) and `enabled_providers` (JSON, default `[]`) to `projects` table |
| `src/ai_qa/api/admin.py` | Update `ProjectCreateRequest`, `ProjectUpdateRequest`, `AdminProjectResponse` — add fields; update validation to enforce at-least-one-link and at-least-one-provider |
| `frontend/src/types/project.ts` | Add `jira_base_url: string | null` and `enabled_providers: string[]` to `Project`, `AdminProject`, `CreateProjectRequest` |
| `frontend/src/lib/projects.ts` | Pass new fields in `createAdminProject` and `updateAdminProject` API calls |
| `frontend/src/components/admin/AdminDashboard.tsx` | Add Jira URL state + field; add provider checkboxes; update validation; update project list display |
| `frontend/src/components/ProviderSelector.tsx` | Accept `enabledProviders: string[]` prop; render disabled state + tooltip for unlisted providers |
| `frontend/src/types/provider.ts` | No structural change needed (provider IDs already typed) |
| PRD | Minor update to FR16 / Story 8.3 description |
| Epics | Story 8.3 and 8.5 acceptance criteria update |
| UX Design Spec | Minor update to admin Create Project form specification and Alice provider selection disabled state |
| Architecture | No structural change — JSON column is a standard extension; no new service or component |

### Technical Impact

- **Database:** 1 new migration. `jira_base_url` is nullable VARCHAR(512). `enabled_providers` is a JSON array column with default `[]` representing a list of provider ID strings (e.g., `["claude", "gemini"]`). Both nullable with safe defaults — backward compatible.
- **Backend:** Validation logic in `ProjectCreateRequest` adds two cross-field validators: (a) at least one of `confluence_base_url`/`jira_base_url` must be non-empty, (b) `enabled_providers` must have at least one entry. `ProjectUpdateRequest` inherits the same.
- **API surface:** `AdminProjectResponse` and the user-facing project response (`Project` type) must expose `jira_base_url` and `enabled_providers` — no secrets involved.
- **Frontend:** The `ProviderSelector` component needs to accept an `enabledProviders` prop. The `ProjectPicker` / thread project context must pass `enabled_providers` down to Alice's config step.
- **Tests:** `test_admin_rbac_api.py` needs updating — existing tests send `confluence_base_url` only; new validation rejects requests with no link at all, so tests must be updated to satisfy the new at-least-one-link rule.

---

## Section 3: Recommended Approach

**Recommendation: Direct Adjustment** — modify and add stories within the existing plan. No rollback or MVP scope reduction required.

### Rationale

- The change is additive. No existing functionality is removed or restructured.
- Database schema change is backward safe (nullable column + JSON default).
- Frontend change is confined to `AdminDashboard.tsx` and `ProviderSelector.tsx`.
- The at-least-one-link validation replaces the current "confluence required" constraint — this is a relaxation, not a tightening, for existing data (existing projects have a confluence URL so they remain valid).
- Provider disable enforcement in Alice is a UI-layer concern only — it does not affect pipeline execution logic.

### Effort Estimate

| Area | Estimate |
|------|----------|
| DB migration | 30 min |
| Backend validation + response schema | 1.5 h |
| Frontend: AdminDashboard form + project list | 2 h |
| Frontend: ProviderSelector disabled state | 1 h |
| Test updates | 1.5 h |
| **Total** | **~6.5 h** |

### Risk Assessment

- **Low risk overall.** The only breaking change is the at-least-one-link validation on the backend — existing projects are unaffected since they were created with a Confluence URL. New test cases cover the at-least-one-provider requirement.
- The `enabled_providers` field defaults to `[]` for existing projects — the user-side provider selection must treat an empty list as "all providers enabled" to preserve backward compatibility for pre-existing projects.

---

## Section 4: Detailed Change Proposals

---

### Change 1 — DB Model: Add `jira_base_url` and `enabled_providers` to Project

**File:** `src/ai_qa/db/models.py`

```
OLD (Project model, partial):
    confluence_base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")

NEW:
    confluence_base_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    jira_base_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    enabled_providers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
```

**Rationale:** `confluence_base_url` changes from `NOT NULL default ""` to nullable to support projects that provide only a Jira URL. `jira_base_url` is a new optional field. `enabled_providers` is a JSON array of provider ID strings controlled by the admin.

---

### Change 2 — Alembic Migration

**File:** New file `alembic/versions/{rev}_add_jira_url_and_enabled_providers_to_project.py`

```python
def upgrade() -> None:
    op.alter_column("projects", "confluence_base_url", nullable=True)
    op.add_column("projects", sa.Column("jira_base_url", sa.String(512), nullable=True))
    op.add_column("projects", sa.Column("enabled_providers", sa.JSON(), nullable=False,
                                        server_default="[]"))

def downgrade() -> None:
    op.drop_column("projects", "enabled_providers")
    op.drop_column("projects", "jira_base_url")
    op.alter_column("projects", "confluence_base_url", nullable=False)
```

---

### Change 3 — Backend: `ProjectCreateRequest` and `ProjectUpdateRequest`

**File:** `src/ai_qa/api/admin.py`

```
OLD:
class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    confluence_base_url: str = Field(min_length=1, max_length=512)

NEW:
class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    confluence_base_url: str | None = Field(default=None, max_length=512)
    jira_base_url: str | None = Field(default=None, max_length=512)
    enabled_providers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def at_least_one_link(self) -> "ProjectCreateRequest":
        conf = (self.confluence_base_url or "").strip()
        jira = (self.jira_base_url or "").strip()
        if not conf and not jira:
            raise ValueError("No link to extract requirement. Please provide Confluence URL, Jira URL, or both.")
        self.confluence_base_url = conf or None
        self.jira_base_url = jira or None
        return self

    @model_validator(mode="after")
    def at_least_one_provider(self) -> "ProjectCreateRequest":
        if not self.enabled_providers:
            raise ValueError("No provider to execute. Please enable at least one provider.")
        return self
```

**Rationale:** Cross-field validators enforce the two new business rules. Existing `name_must_not_be_blank` and `normalize_description` validators are preserved unchanged.

---

### Change 4 — Backend: `AdminProjectResponse` and user-facing Project response

**File:** `src/ai_qa/api/admin.py` (and the user-facing projects route if it has a separate response schema)

```
OLD:
class AdminProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    confluence_base_url: str | None
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime

NEW:
class AdminProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    confluence_base_url: str | None
    jira_base_url: str | None          # NEW
    enabled_providers: list[str]        # NEW (empty = all providers enabled)
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
```

The user-facing `ProjectResponse` (used by `GET /api/projects`) must also expose `jira_base_url` and `enabled_providers` so Alice can enforce disabled providers.

---

### Change 5 — Frontend Types: `project.ts`

**File:** `frontend/src/types/project.ts`

```
OLD (Project interface):
  confluence_base_url: string | null;

NEW (Project interface):
  confluence_base_url: string | null;
  jira_base_url: string | null;              // NEW
  enabled_providers: string[];               // NEW

OLD (CreateProjectRequest):
  confluence_base_url: string;

NEW (CreateProjectRequest):
  confluence_base_url?: string | null;
  jira_base_url?: string | null;             // NEW
  enabled_providers: string[];               // NEW
```

---

### Change 6 — Frontend: `AdminDashboard.tsx` — Create Project Form

**Section:** Create Project form (`<form onSubmit={handleCreateProject}>`)

```
OLD fields:
  - Project name (required)
  - Description (optional)
  - Confluence Base URL (required, HTML required attribute)

NEW fields:
  - Project name (required)
  - Description (optional)
  - Confluence Base URL (optional — label changes to "Confluence Base URL")
  - Jira Base URL (optional — new field below Confluence)
  - Hint text between the two URL fields:
      "At least one of Confluence or Jira URL is required."
  - Provider checkboxes section (label: "Enabled Providers"):
      ☐ Browser Use  ☐ Claude  ☐ Gemini  ☐ ChatGPT  ☐ On Premises
      At least one must be checked.

OLD validation (frontend):
  if (!trimmedName) → error "Project name is required"

NEW validation (frontend, before calling API):
  if (!trimmedName) → error "Project name is required"
  if (!confluenceUrl && !jiraUrl) → error "No link to extract requirement."
  if (enabledProviders.length === 0) → error "No provider to execute."
```

**State additions:**

```typescript
const [jiraBaseUrl, setJiraBaseUrl] = useState("");
const PROVIDER_OPTIONS = [
  { id: "browser-use-cloud", label: "Browser Use" },
  { id: "claude",            label: "Claude" },
  { id: "gemini",            label: "Gemini" },
  { id: "openai",            label: "ChatGPT" },
  { id: "on-premises",       label: "On Premises" },
];
const [enabledProviders, setEnabledProviders] = useState<string[]>([]);
```

**Rationale:** Frontend validation gives immediate feedback before the API call. Backend validation remains as the authoritative guard.

---

### Change 7 — Frontend: `AdminDashboard.tsx` — Projects List Display

**Section:** Project card display (`editingProjectId !== proj.id` branch)

```
OLD display:
  - Project name
  - Description (if present)
  - Confluence link (if present)
  - Member count

NEW display:
  - Project name
  - Description (if present)
  - Confluence link (if present)
  - Jira link (if present) — same style as Confluence link, blue anchor, opens in new tab
  - Provider icon row: for each id in proj.enabled_providers, render
      <img src={`/provider-icons/${iconFileName}`} alt={providerName} className="w-4 h-4" />
    using the same PROVIDER_LOGOS mapping as ProviderSelector.tsx
    (if enabled_providers is empty, show nothing — backward compat for old projects)
  - Member count
```

Icon filename mapping (same as `ProviderSelector.tsx`):

```
"browser-use-cloud" → browser-use.png
"claude"            → anthropic.svg
"gemini"            → google-gemini.svg
"openai"            → openai.svg
"on-premises"       → on-premises.png
```

---

### Change 8 — Frontend: `AdminDashboard.tsx` — Edit Project Form

The inline edit form must also gain the same Jira URL and provider checkbox fields, pre-populated from the existing project data. The same frontend validation applies on save.

```
editProjectJiraBaseUrl state variable added
editEnabledProviders state variable added
startEditingProject() populates both from proj.jira_base_url and proj.enabled_providers
```

---

### Change 9 — Frontend: `ProviderSelector.tsx` — Disabled Provider State

**Prop addition:**

```
OLD:
interface ProviderSelectorProps {
  options: ProviderOption[] | null;
  onPremDefaults?: { api_key: string };
  onSelect: (...) => void;
  disabled?: boolean;
  submittedSelection?: SubmittedSelection | null;
}

NEW:
interface ProviderSelectorProps {
  options: ProviderOption[] | null;
  onPremDefaults?: { api_key: string };
  onSelect: (...) => void;
  disabled?: boolean;
  submittedSelection?: SubmittedSelection | null;
  enabledProviders?: string[];   // NEW — empty or undefined = all enabled (backward compat)
}
```

**Rendering logic:**

```
OLD provider card click handler:
  onClick={() => !disabled && handleProviderClick(provider.id)}
  className: opacity-50 if disabled

NEW provider card:
  const isProviderEnabled = !enabledProviders?.length || enabledProviders.includes(provider.id);
  const isClickable = !disabled && isProviderEnabled;

  onClick={() => isClickable && handleProviderClick(provider.id)}
  className: add "opacity-40 cursor-not-allowed bg-slate-50" if !isProviderEnabled
  title / tooltip: if !isProviderEnabled →
    "Your project cannot choose this provider. Please contact administrator if something wrong."

  Wrap the provider card in a <div title={...}> for hover tooltip (use Shadcn Tooltip component
  for accessibility, or a plain title attribute as minimum viable implementation).
```

**Rationale:** Empty `enabledProviders` array (old projects) means all providers are enabled — no behavioral change for existing sessions.

---

### Change 10 — Provider context propagation to ProviderSelector

The `enabledProviders` value must flow from the bound project to `ProviderSelector`. The project's `enabled_providers` is already returned by `GET /api/projects` (after Change 4). It is available in the frontend's `ProjectContext` / Alice agent step.

The Alice component or the parent that renders `ProviderSelector` must pass `project.enabled_providers` as the `enabledProviders` prop.

---

### Change 11 — PRD update: FR16 / Story 8.3

**File:** `_bmad-output/planning-artifacts/prd.md`

```
OLD (FR16 in Functional Requirements → Administration):
  FR16: Admin can create, read, update, and delete users and projects...
  Story 8.3 AC (partial):
    "And a missing or blank Confluence Base URL is rejected with a clear validation message"

NEW addition to FR16:
  FR16b: When creating or editing a project, admin must provide at least one of Confluence Base URL
  or Jira Base URL; submitting with neither shows the error "No link to extract requirement."
  FR16c: Admin must enable at least one AI provider per project; submitting with none selected
  shows the error "No provider to execute." Enabled providers restrict which providers users
  of that project can select in Alice Step 1.
  FR16d: The Projects list displays the Jira link (if present) and icons of enabled providers.
```

---

### Change 12 — Epics update: Story 8.3 and 8.5 acceptance criteria

**File:** `_bmad-output/planning-artifacts/epics.md`

**Story 8.3: Admin Project Management — updated ACs**

```
OLD:
  Given an authenticated admin creates a project
  When the backend validates the project name and Confluence base URL
  Then the project is created and appears in the admin project list
  And duplicate or blank project names are rejected with a clear validation message
  And a missing or blank Confluence base URL is rejected with a clear validation message

NEW:
  Given an authenticated admin creates a project
  When the backend validates the project name, links, and providers
  Then the project is created and appears in the admin project list
  And duplicate or blank project names are rejected with a clear validation message
  And if both Confluence Base URL and Jira Base URL are blank, creation is rejected
    with the error "No link to extract requirement."
  And if no provider checkbox is selected, creation is rejected
    with the error "No provider to execute."
  And the project stores the Jira Base URL (optional) and the list of enabled providers

  --- NEW AC ---
  Given an admin creates a project with only a Jira Base URL (no Confluence URL)
  When the backend validates
  Then the project is created successfully

  Given an admin creates a project with both Confluence and Jira Base URLs
  When the backend validates
  Then both URLs are stored and the project is created successfully
```

**Story 8.5: Admin Dashboard UI Layout — updated ACs**

```
NEW addition:
  Given the admin opens Create Project
  When the form renders
  Then Confluence Base URL and Jira Base URL are both shown as optional fields
  And the label or hint text states at least one URL is required
  And five provider checkboxes are shown: Browser Use, Claude, Gemini, ChatGPT, On Premises
  And submitting with no URL shows "No link to extract requirement."
  And submitting with no provider checked shows "No provider to execute."

  Given a project has a Jira Base URL set
  When the admin views the project card in the Projects list
  Then the Jira URL is shown as a clickable link

  Given a project has enabled providers configured
  When the admin views the project card
  Then an icon for each enabled provider is displayed
```

---

### Change 13 — Tests update

**File:** `tests/api/test_admin_rbac_api.py`

```
Function: test_admin_create_project_requires_confluence_base_url
  OLD: sends {"name": "Blank Confluence", "confluence_base_url": ""} → expects 422
  NEW: rename to test_admin_create_project_requires_at_least_one_link
       sends {"name": "No Links", "enabled_providers": ["claude"]} (no URLs) → expects 422
       also add: sends {"name": "No Providers", "confluence_base_url": "https://mcp"} → expects 422
                 sends {"name": "OK", "confluence_base_url": "https://mcp", "enabled_providers": ["claude"]} → expects 200

All other existing tests that send confluence_base_url only must also add
  "enabled_providers": ["claude"]   (or any non-empty list)
to satisfy the new at-least-one-provider validation.
```

---

## Section 5: Implementation Handoff

**Change Scope: Minor-to-Moderate**
All changes are confined to existing files. No new services, no new routes, no architectural changes. Direct implementation by Developer.

### Handoff Recipients

**Developer** — implement all 13 changes above.

### Implementation Order

1. Change 1 + 2 — DB model and migration (foundation)
2. Change 3 + 4 — Backend validation and response schema
3. Change 13 — Update tests (run and confirm green before frontend)
4. Change 5 + 6 + 7 + 8 — Frontend Admin Dashboard (form + list + edit)
5. Change 9 + 10 — ProviderSelector disabled state and prop wiring
6. Change 11 + 12 — Document updates (PRD + Epics)

### Success Criteria

- [ ] `POST /api/admin/projects` with no URLs returns 422 with message containing "No link to extract requirement"
- [ ] `POST /api/admin/projects` with no providers returns 422 with message containing "No provider to execute"
- [ ] `POST /api/admin/projects` with only `jira_base_url` returns 200
- [ ] Admin Dashboard Create Project form shows Jira URL field and 5 provider checkboxes
- [ ] Submitting Create Project form with no URLs shows client-side error before API call
- [ ] Submitting Create Project form with no providers checked shows client-side error before API call
- [ ] Project card displays Jira link when present
- [ ] Project card displays provider icons for enabled providers
- [ ] Alice Step 1 ProviderSelector greys out providers not in project's `enabled_providers`
- [ ] Hovering over a disabled provider shows the tooltip text exactly: "Your project cannot choose this provider. Please contact administrator if something wrong."
- [ ] Projects with empty `enabled_providers` (old projects) allow all providers in Alice — backward compatible
- [ ] Full test suite passes

---

## Workflow Summary

| Item | Value |
|------|-------|
| Change trigger | 4 new admin + user requirements not in original plan |
| Change scope | Minor–Moderate |
| Artifacts modified | DB model, migration, backend admin API, frontend AdminDashboard, ProviderSelector, types, PRD, Epics |
| Routed to | Developer (direct implementation) |
| Estimated effort | ~6.5 hours |
| Blocking dependency | None — changes are additive |
