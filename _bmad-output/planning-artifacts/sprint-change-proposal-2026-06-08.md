# Sprint Change Proposal: Dynamic Model Quota Filtering (Story 9.4)
Date: 2026-06-08

## 1. Issue Summary
* **Triggering Issue**: During testing of Story 9.4, it was discovered that Alice lists all models returned by the provider APIs, including those that the user does not have access to due to quota limits, lack of support, or deprecation.
* **Context**: Alice successfully connects to the provider but naively treats all discovered models as available. She then assigns high-quality models (like Opus or GPT-4) to agents, which subsequently fail at runtime because the user's API key lacks the actual quota or tier to use them.
* **Evidence**: Downstream agent execution errors occur because the assigned model is blocked by the provider API for billing/quota reasons.

## 2. Impact Analysis
* **Epic Impact**: Epic 9 requires adjustments. Specifically, Stories 9.4 and 9.5 need to explicitly handle model availability grouping and halting logic.
* **Artifact Conflicts**: 
  * PRD (FR15a) needs to be updated to define the "Available" vs "Unavailable" model groups and the specific halt message.
  * `epics.md` needs acceptance criteria updates to reflect the new requirements for Story 9.4 and Story 9.5.
* **Technical Impact**: 
  * The `list_models` and `_generate_configuration` logic in `alice.py` will need to differentiate models into two groups.
  * Alice must explicitly block thread progression and output a specific error message if the "Available" group is empty.

## 3. Recommended Approach
* **Path Forward**: Direct Adjustment (Option 1). We will update the existing requirements in Epic 9 and PRD, then adjust the implementation to categorize models correctly.
* **Rationale**: This is a direct refinement of the existing feature. It does not alter the MVP goals but significantly improves the user experience by failing fast and explicitly during configuration, rather than failing during execution.
* **Effort**: Low.
* **Risk**: Low.

## 4. Detailed Change Proposals

### PRD Updates

**Modify FR15a:**
```diff
- FR15a: Alice must only assign downstream agent models from the provider's discovered available model list. If model discovery fails, returns no models, or cannot verify a selected model exists, Alice must block successful configuration review and show an actionable recovery message.
+ FR15a: Alice must only assign downstream agent models from the provider's discovered available model list. Models must be categorized into two distinct groups: "Available" and "Unavailable" (quota exceeded, not supported, outdated). If the "Available" group is empty, Alice must stop the thread and show the exact message: "No available model to proceed. Please check your subscription then create a new thread to continue."
```

### Epic 9 Updates

**Update Story 9.4 Acceptance Criteria:**
```diff
  **Given** provider validation succeeds
  **When** Alice performs model discovery
- **Then** the provider adapter calls `list_models(credentials, base_url)` where supported
- **And** the response is normalized into `DiscoveredModel` values with non-secret metadata
+ **Then** the provider adapter calls `list_models(credentials, base_url)` where supported
+ **And** the response is normalized into `DiscoveredModel` values, categorized clearly into 'Available' and 'Unavailable' (quota exceeded, not supported, outdated)
  
- **Given** model discovery fails, returns no models, or cannot verify selected models
+ **Given** model discovery returns 0 'Available' models (or fails entirely)
  **When** Alice evaluates configuration readiness
- **Then** Alice blocks successful configuration review
- **And** Alice shows actionable recovery guidance
+ **Then** Alice stops the thread
+ **And** Alice shows the message: "No available model to proceed. Please check your subscription then create a new thread to continue."
```

**Update Story 9.5 Acceptance Criteria:**
```diff
  **Given** Alice has discovered available models
  **When** model assignment runs
- **Then** Alice assigns models only from the discovered model list
+ **Then** Alice assigns the most suitable models ONLY from the 'Available' group
  **And** each assignment includes agent name, selected model, selected temperature or runtime parameters, and non-secret selection rationale
```

## 5. Implementation Handoff
* **Scope**: Minor.
* **Assigned To**: Developer Agent.
* **Action Items**:
  1. Update `prd.md` and `epics.md` with the proposed changes.
  2. Implement the grouping logic in `ai_qa/agents/alice.py` and relevant provider adapters to detect and flag "Unavailable" models.
  3. Ensure Alice halts execution with the exact requested string when the available list is empty.
