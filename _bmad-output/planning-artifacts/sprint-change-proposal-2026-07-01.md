# Sprint Change Proposal: Configurable Dynamic Multi-Environment Model Sync

## Section 1: Issue Summary
**Trigger:** A security directive from management restricting the UAT server's outbound firewall strictly to the EntraID destination for SSO.
**Problem:** The UAT server cannot connect to the internet to sync AI model benchmarks. Manually syncing models locally, creating database migrations with the synced values, building a Docker image, and releasing it to UAT is inconvenient and prone to errors. Furthermore, the solution needs to be dynamic to support syncing to multiple target environments (e.g., UAT, PROD) simultaneously with a single click.
**Proposed Solution:** 
1. Add an `ENABLE_MODEL_BENCHMARK_SYNC` environment variable to enable the sync feature locally and disable it on UAT.
2. Add a `SYNC_TARGET_DATABASES` environment variable accepting a JSON array of target environments (e.g., `[{"name": "UAT", "url": "postgresql+asyncpg://..."}, {"name": "PROD", "url": "postgresql+asyncpg://..."}]`).
3. When the user clicks the "Sync models" button locally, the application will sync the primary database, then dynamically parse the JSON array and loop through each configured environment to execute the sync operation there as well.

## Section 2: Impact Analysis
- **Epic Impact:** Epic 9 (or the relevant admin epic) needs to be updated to include the environment variable toggles for the sync feature and the multi-database sync logic.
- **Story Impact:** A new story is needed to implement the `ENABLE_MODEL_BENCHMARK_SYNC` and `SYNC_TARGET_DATABASES` environment variables, along with the JSON parsing and looping logic.
- **Artifact Conflicts:** 
  - **PRD:** Needs a new Non-Functional Requirement stating that specific external-reaching features must be configurable via environment variables due to strict on-premises firewall policies, and defining the dynamic multi-environment sync capability.
  - **Architecture:** The frontend needs to conditionally render the sync button based on `ENABLE_MODEL_BENCHMARK_SYNC`. The backend needs to parse the JSON string, dynamically create temporary SQLAlchemy engines for each target, and handle the sync process across multiple environments.
- **Technical Impact:** 
  - Backend: Add `ENABLE_MODEL_BENCHMARK_SYNC` and `SYNC_TARGET_DATABASES` to Pydantic settings. Return 403 Forbidden if the endpoint is called when disabled. When enabled and syncing, after syncing the primary DB, safely parse `SYNC_TARGET_DATABASES`, and execute the upsert logic for each provided URL. Expose the `ENABLE_MODEL_BENCHMARK_SYNC` setting to the frontend via a config endpoint.
  - Frontend: Hide the sync button in the UI if the setting is false.

## Section 3: Recommended Approach
**Option 1: Direct Adjustment with Dynamic JSON Configuration**
- **Rationale:** By using a JSON array of database connections, the system is future-proofed. If a new environment (e.g., Staging, Pre-Prod, Prod) is added, the user only needs to add a new object to the JSON array in their local `.env` file, without requiring any code changes. This fulfills the requirement of "press 1 button, sync all."
- **Effort Estimate:** Medium
- **Risk Level:** Low

## Section 4: Detailed Change Proposals

### PRD Modifications

**[MODIFY] prd.md**
Section: Non-Functional Requirements -> Security
**NEW:**
- NFR20: External-reaching administrative features (e.g., Sync Model Benchmarks) must be configurable via environment variables (`ENABLE_MODEL_BENCHMARK_SYNC`) to accommodate strict outbound firewall policies in environments like UAT, where only SSO traffic is permitted.
- NFR21: The Model Benchmark Sync feature must dynamically support syncing to multiple remote databases (e.g., UAT, PROD) simultaneously when triggered from a permitted environment, using a JSON-configured `SYNC_TARGET_DATABASES` environment variable.

### Epics Modifications

**[MODIFY] epics.md**
Section: Epic 8: Admin Dashboard and Project Membership Management (or wherever Sync Models is currently documented)
**NEW:**
**Story 8.X: Dynamic Multi-Environment Model Sync Configuration**
As a system administrator,
I want to enable or disable the Model Sync feature and dynamically configure multiple remote target databases via environment variables,
So that I can disable it on restricted environments (UAT) while syncing all environments simultaneously from my local machine with one click.

**Acceptance Criteria:**
**Given** the application starts
**When** the `ENABLE_MODEL_BENCHMARK_SYNC` environment variable is set to `false`
**Then** the frontend hides the "Sync models" button or feature
**And** the backend rejects requests to the sync endpoint with a 403 Forbidden

**Given** the application starts
**When** the `ENABLE_MODEL_BENCHMARK_SYNC` environment variable is set to `true`
**Then** the frontend displays the "Sync models" button
**And** the backend allows the sync operation

**Given** the user clicks the "Sync models" button
**When** `SYNC_TARGET_DATABASES` is configured with a valid JSON array of `{"name": "...", "url": "..."}` objects
**Then** the backend syncs the model benchmark data to the primary database
**And** iterates through the JSON array, dynamically creates a connection for each `url`, and syncs the data to those remote databases
**And** handles errors gracefully if one remote DB fails, without crashing the whole process (or returns a compound status report).

## Section 5: Implementation Handoff
- **Scope:** Minor-Moderate
- **Route to:** Developer agent for direct implementation
- **Responsibilities:** 
  1. Add `ENABLE_MODEL_BENCHMARK_SYNC` and `SYNC_TARGET_DATABASES` to backend settings.
  2. Implement JSON parsing and dynamic multi-database looping logic in the backend sync service.
  3. Expose the `ENABLE_MODEL_BENCHMARK_SYNC` setting to the frontend.
  4. Update the frontend UI to conditionally hide the sync button.
