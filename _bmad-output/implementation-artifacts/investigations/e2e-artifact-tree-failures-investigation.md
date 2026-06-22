# Investigation: E2E suite — 3 artifact-tree failures (Epic 10)

## Hand-off Brief

1. **What happened.** A full E2E run (57 tests) produced 3 failures, all in the Epic 10 artifact-tree
   sidebar specs; all three are **test-side defects**, not product regressions (Confirmed).
2. **Where the case stands.** Root cause Confirmed for all three: two failures come from the non-sticky
   auto-open expanding the most-recently-created project (always `projectTwo`), so the tests' explicit
   click toggles an already-open project **closed**; the third is an over-broad `getByText` that matches
   both the sidebar `<span>` and the preview `<h3>` after the preview opens.
3. **What's needed next.** Apply the three locator/flow fixes to the two spec files (no product change),
   then re-run the suite to confirm green.

## Case Info

| Field            | Value                                                                                  |
| ---------------- | -------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                    |
| Date opened      | 2026-06-11                                                                             |
| Status           | Concluded                                                                              |
| System           | Windows 11; Playwright (chromium), `workers: 1`, `retries: 0` (local); frontend Vite   |
| Evidence sources | `_bmad-output/test-artifacts/results.xml`, frontend source, e2e specs, git log         |

## Problem Statement

User report (verbatim): "có bug khi chạy toàn bộ e2e, hãy điều tra và fix. Kết quả trong file results.xml."
Premise (treated as hypothesis): the failures indicate a product bug. **Evidence contradicts** — the
product behaves per its ACs; the three failing assertions encode stale test assumptions.

## Evidence Inventory

| Source                     | Status    | Notes                                                                     |
| -------------------------- | --------- | ------------------------------------------------------------------------- |
| results.xml                | Available | 57 tests, 3 failures, 0 errors; exact `file:line` + error per failure     |
| ProjectSidebar.tsx         | Available | auto-open + project toggle + artifact name `<span>`                       |
| ArtifactPreview.tsx        | Available | preview header renders artifact name as `<h3>`                            |
| App.tsx                    | Available | active thread = most-recent thread; `activeProjectId` derived from it     |
| projects.py                | Available | `/projects` ordered by `Project.name`                                     |
| playwright traces/videos   | Partial   | Referenced in results.xml; not opened (source trace was sufficient)       |

## Confirmed Findings

### Finding 1: The active project (auto-opened) is always `projectTwo`

**Evidence:** `frontend/src/App.tsx:330-334` (active thread = most-recently updated/created thread),
`frontend/src/App.tsx:361-362` (`activeProjectId = activeThread.project_id`),
`frontend/src/App.tsx:307-321` (one starter thread per project, created in `projects` list order),
`src/ai_qa/api/projects.py:111` (`/projects` ordered by `Project.name`).

**Detail:** Both failing specs create `projectOne` then `projectTwo` with names `…ProjA/Proj One` and
`…ProjB/Proj Two`. Ordered by name, `projectTwo` is last in `/projects`, so its starter thread is created
last and is the most-recent → `activeProjectId = projectTwo`.

### Finding 2: The sidebar auto-opens the active project; clicking it again toggles it closed

**Evidence:** `frontend/src/components/conversations/ProjectSidebar.tsx:359-370` (one-shot non-sticky
auto-open sets `openProjectId = activeProjectId`), `:429-435` (`handleProjectClick`: clicking the
already-open project sets `openProjectId = null`).

**Detail:** On load `projectTwo` is auto-expanded. The tests then call
`page.getByText(projectTwo.name).click()` expecting to *expand* it, but the click **collapses** it,
hiding the report artifact they then wait for → 15 s timeout, "element(s) not found".

### Finding 3: Report-kind artifacts render correctly for the open project

**Evidence:** `story-10-2 [P1] AC2 — mixed kinds` passed (results.xml lines 9-10): it creates a `report`
kind `report.md` and asserts it visible — green. So the failure is not a report→folder mapping bug.

### Finding 4: The preview renders the artifact name as an `<h3>`, duplicating the sidebar `<span>`

**Evidence:** `frontend/src/components/artifacts/ArtifactPreview.tsx:222` (`<h3>{artifact.name}</h3>`),
`frontend/src/components/conversations/ProjectSidebar.tsx:509` (`<span class="truncate">{artifact.name}</span>`),
`frontend/src/App.tsx:1281` (chat hidden when preview open, **sidebar stays mounted**), `:1644-1646`
(preview rendered alongside the sidebar).

**Detail:** After the test clicks the artifact (story-10-2 line 438), `onSelectArtifact` opens the
preview. `getByText("Exact Name.md")` now matches both the sidebar `<span>` and the preview `<h3>` →
Playwright strict-mode violation (2 elements). The pre-click assertion (line 433) passes because only the
`<span>` exists then.

## Deduced Conclusions

### Deduction 1: Failures 1 & 3 are caused by the auto-open toggle, not artifact loading

**Based on:** Findings 1, 2, 3.

**Reasoning:** If `projectTwo` were collapsed, clicking it would open it and fetch its tree (the working
load path proven by AC2). The only way a click on `projectTwo` ends with the report **not** visible is if
the click closed an already-open `projectTwo`. Combined with Finding 1 (`projectTwo` is auto-opened), the
click toggles it closed.

**Conclusion:** Deterministic test defect — both specs assume `projectTwo` starts collapsed. It does not.

### Deduction 2: Failure 2 is a regression introduced by Story 10-3, surfaced in a 10-2 test

**Based on:** Finding 4 + git log (`9321e0f story 10-2 code, e2e, test done` predates
`1852886 feat(10-3): artifact read and preview access`).

**Reasoning:** When the 10-2 frozen-labels test was written and green, no `ArtifactPreview` existed, so a
click left only the sidebar `<span>` → 1 match. Story 10-3 added the preview `<h3>`. The 10-2 test's broad
`getByText` was never updated, so the post-click assertion now matches 2 nodes.

**Conclusion:** Test defect — over-broad locator; the preview opening is the success state.

## Hypothesized Paths

### Hypothesis 1: Failures are a product regression (user's premise)

**Status:** Refuted.

**Resolution:** Product behaves per ACs — auto-open of the active project (AC3) and the preview `<h3>`
header (10-3) are intended. AC2 proves report artifacts load/render. All three failures trace to stale
test assertions. No product code is implicated.

## Source Code Trace

| Element       | Detail                                                                                              |
| ------------- | --------------------------------------------------------------------------------------------------- |
| Error origin  | `story-10-2-…spec.ts:386`, `:442`; `story-10-7-…spec.ts:366`                                        |
| Trigger       | E2E click on `projectTwo` (already auto-open) / click on artifact (opens preview)                   |
| Condition     | `projectTwo` is the most-recent-thread project → auto-opened; preview `<h3>` duplicates sidebar span |
| Related files | `ProjectSidebar.tsx:359-370,429-435,509`; `ArtifactPreview.tsx:222`; `App.tsx:330-334,361-362,1644` |

## Conclusion

**Confidence:** High — Confirmed root cause for all three; deterministic (not flake/parallelism). All
fixes are test-side.

- **Failure 1** (`story-10-2:386`, AC3 non-sticky): click on auto-opened `projectTwo` toggles it closed.
- **Failure 2** (`story-10-2:442`, frozen labels): `getByText` matches sidebar `<span>` + preview `<h3>`.
- **Failure 3** (`story-10-7:366`, non-active events): same toggle-closed bug as Failure 1.

## Recommended Next Steps

### Fix direction (test-side only)

1. **Failures 1 & 3 — deterministic open of `projectTwo`.** Click `projectOne` first, then `projectTwo`.
   This forces a fresh open+fetch of `projectTwo` regardless of which project the auto-open expanded, with
   no visibility-check race. The report then renders; `projectOne` stays listed.
2. **Failure 2 — specific locator.** Assert the preview opened via
   `getByRole("heading", { name: "Exact Name.md" })` instead of the ambiguous `getByText`.

### Diagnostic / verification

Re-run `npx playwright test e2e/story-10-2-artifact-tree-browsing.spec.ts e2e/story-10-7-artifact-refresh.spec.ts`
(then the full suite) with backend + Vite running; expect 0 failures.

## Side Findings

- **`story-10-7 [P0]` "non-active-thread" is mislabeled** (Deduced): `projectTwo` is actually the *active*
  project (most-recent thread), so creating the artifact in `projectTwo` exercises an active-project event,
  not a non-active one — overlapping the suite's first 10-7 test. Truly testing the non-active path would
  require creating the artifact in `projectOne`. Out of scope for the green-suite fix; flag for a follow-up
  test-quality pass.

## Follow-up: 2026-06-11

### Fix applied + verified

Test-side fixes applied (no product code touched):

- `story-10-2-…spec.ts` AC3 non-sticky: `click(projectOne)` then `click(projectTwo)` (deterministic open).
- `story-10-2-…spec.ts` frozen labels: post-click assert switched to `getByRole("heading", {name:"Exact Name.md"})`.
- `story-10-7-…spec.ts` non-active events: `click(projectOne)` then `click(projectTwo)` before asserting the report.

Verification: `npx playwright test e2e/story-10-2-artifact-tree-browsing.spec.ts
e2e/story-10-7-artifact-refresh.spec.ts` → **10 passed (2.5m)**. The three formerly-failing tests now
complete in ~2.2-2.8 s (was 27 s timeouts), confirming the toggle-closed root cause. The other 47 suite
tests were already green and untouched. Status: Concluded.

## Follow-up: 2026-06-11 #2

### Deeper fix (side-finding) + e2e sweep — verified via a fan-out workflow

A workflow (`fix-and-sweep-multiproject-e2e`, 3 agents: redesign ∥ sweep → adversarial verify) was run to
(a) properly fix the mislabeled `story-10-7` non-active test and (b) sweep all 17 e2e specs for the same
class of latent bug.

**`story-10-7` non-active test redesigned (now genuinely tests the non-active path):**

- The artifact is now created in `projectOne` (the genuinely NON-active project — `projectTwo` is the
  active one per Finding 1). Previously it was created in `projectTwo` (active), so the old test never
  exercised the non-active path — it overlapped the suite's first 10-7 test (Side Finding above, now
  resolved).
- The active-chat assertion (provider prompt still visible) is the real non-disruption proof; a
  `toHaveCount(0)` sanity check confirms the report isn't auto-shown for a non-active event
  (App.tsx:437 guard). The adversarial verifier flagged the original comment for **overclaiming**
  `toHaveCount(0)` as a proof; the applied version reworded it honestly.
- Deterministic open of `projectOne`: click `projectTwo` (auto-open) first → toggles it closed → click
  `projectOne` → opens cleanly. Avoids the toggle-closed pitfall regardless of auto-open timing.

**Sweep result (17 e2e specs):** only **one** additional latent issue found —
`story-10-8-artifact-notice.spec.ts:253`. Its update-notice test opens the preview (never closing it),
and the catch-branch fallback `getByText("Viewed Requirement.md")` would match both the sidebar `<span>`
and the preview `<h3>` → strict-mode violation. It passes today only because the notice (try-branch)
appears, skipping the catch. **Fixed** by scoping to the sidebar landmark:
`getByRole("complementary").getByText(...)` (the sidebar is the single `<aside>` at `App.tsx:1076`). All
other specs are single-project or correctly written (use `getByRole heading`, close the preview, or never
click an artifact open).

Verification: `npx playwright test e2e/story-10-7-artifact-refresh.spec.ts
e2e/story-10-8-artifact-notice.spec.ts` → **6 passed (48 s)**. Combined with the first follow-up, all
changed specs (10-2, 10-7, 10-8) are green; the 47 untouched tests were already passing. Status: Concluded.
