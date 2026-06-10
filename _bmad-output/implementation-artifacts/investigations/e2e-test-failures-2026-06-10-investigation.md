# Investigation: E2E Test Failures – 2026-06-10

## Hand-off Brief

1. **What happened.** Three E2E tests failed in the full Playwright run: two `failures` (strict mode violation and missing heading) and one `error` (timeout on a nonexistent `data-testid`). All three are test-locator mismatches against the current UI — no production logic is broken.
2. **Where the case stands.** Root cause Confirmed for all three issues via direct source inspection of `AdminDashboard.tsx` and test files.
3. **What's needed next.** Fix the three test locators — each is a one-line change in the corresponding `.spec.ts` file.

## Case Info

| Field            | Value                                                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                                                     |
| Date opened      | 2026-06-10                                                                                                              |
| Status           | Concluded                                                                                                               |
| System           | Windows 11 / Node 26.1.0 / Playwright 1.60.0 / Chromium                                                                 |
| Evidence sources | `_bmad-output/test-artifacts/results.xml`, `frontend/e2e/*.spec.ts`, `frontend/src/components/admin/AdminDashboard.tsx` |

## Problem Statement

Full E2E run completed with 45 tests: 2 failures, 1 error. All three defective tests reside in Story 8.3, 8.5, and 10.8 specs. The tests' locators do not match the current UI structure.

## Evidence Inventory

| Source                                                                 | Status    | Notes                                     |
| ---------------------------------------------------------------------- | --------- | ----------------------------------------- |
| `_bmad-output/test-artifacts/results.xml`                              | Available | 45 tests, 2 failures, 1 error             |
| `frontend/e2e/story-10-8-artifact-notice.spec.ts`                      | Available | Lines 427, 433                            |
| `frontend/e2e/story-8-3-admin-project-management.spec.ts`              | Available | Line 177                                  |
| `frontend/e2e/story-8-5-admin-dashboard-ui-layout.spec.ts`             | Available | Line 135                                  |
| `frontend/src/components/admin/AdminDashboard.tsx`                     | Available | Lines 44–786 inspected                    |

## Timeline of Events

| Time                 | Event                                                    | Source           | Confidence |
| -------------------- | -------------------------------------------------------- | ---------------- | ---------- |
| 2026-06-10T08:34:58Z | Full Playwright run started (45 tests)                   | results.xml      | Confirmed  |
| 2026-06-10T08:34:58Z | story-10-8 test 3 fails – strict mode violation heading  | results.xml:28   | Confirmed  |
| 2026-06-10T08:34:58Z | story-8-3 test 1 errors – timeout on nonexistent testId  | results.xml:148  | Confirmed  |
| 2026-06-10T08:34:58Z | story-8-5 test 1 fails – heading "Projects" not found    | results.xml:208  | Confirmed  |

## Confirmed Findings

### Finding 1: Strict mode violation – "Generated Script" heading (story-10-8)

**Evidence:** `results.xml:34-36`; `frontend/e2e/story-10-8-artifact-notice.spec.ts:427`

**Detail:** `getByRole("heading", { name: "Generated Script" })` resolves to **2 elements**:

- `<h3>Generated Script.py</h3>` (sidebar artifact item — partial match because `.py` suffix still contains the name)
- `<h1>Generated Script</h1>` (preview panel heading — exact match)

Playwright strict mode rejects multi-element resolution. The test at line 433 has the same problem (`toBeHidden` call).

**Fix:** Add `{ exact: true }` to both locators at lines 427 and 433:

```ts
page.getByRole("heading", { name: "Generated Script", exact: true })
```

---

### Finding 2: Nonexistent `data-testid="enabled-provider-checkbox"` (story-8-3)

**Evidence:** `results.xml:153`; `frontend/e2e/story-8-3-admin-project-management.spec.ts:177`; `frontend/src/components/admin/AdminDashboard.tsx:770-785`

**Detail:** No element in the codebase carries `data-testid="enabled-provider-checkbox"`. The Create Project form renders provider checkboxes as bare `<input type="checkbox">` elements inside `<label>` elements (one per provider: Browser Use, Claude, Gemini, ChatGPT, On Premises) with no `data-testid` attribute anywhere.

**Fix:** Replace `getByTestId("enabled-provider-checkbox")` with a role-based locator targeting one specific provider:

```ts
await page.getByRole("checkbox", { name: /Browser Use/i }).check();
```

(or any other provider name — test just needs at least one enabled)

---

### Finding 3: "Projects" section header is a `<div>`, not a heading element (story-8-5)

**Evidence:** `results.xml:213-215`; `frontend/e2e/story-8-5-admin-dashboard-ui-layout.spec.ts:135`; `frontend/src/components/admin/AdminDashboard.tsx:471-473`

**Detail:** The admin dashboard "Projects" section header is rendered as:

```html
<div class="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
  <Shield /> Projects
</div>
```

This is a `<div>` — it has no heading ARIA role. `getByRole("heading", { name: "Projects" })` finds nothing.

**Fix:** Use a text-based locator instead:

```ts
await expect(page.getByText("Projects").first()).toBeVisible();
```

Or add `data-testid="projects-section-heading"` to the `<div>` in `AdminDashboard.tsx` and use `getByTestId`.

## Deduced Conclusions

### Deduction 1: No production regressions — purely test-locator drift

**Based on:** Findings 1, 2, 3

**Reasoning:** All three failures are test code issues (wrong locator strategy) against a UI that has no `data-testid` on the provider checkboxes and no semantic heading element for the "Projects" card title. The 42 passing tests confirm the underlying features work correctly.

**Conclusion:** Zero production impact; only the three test locators need updating.

## Hypothesized Paths

### Hypothesis 1: story-8-3 test was written before `data-testid` was removed/never added

**Status:** Confirmed

**Theory:** The test was authored expecting a `data-testid="enabled-provider-checkbox"` that was either planned but never implemented, or was removed during a UI refactor.

**Resolution:** Direct grep of entire `frontend/src` returned zero matches for `enabled-provider-checkbox`.

## Missing Evidence

None — root cause is Confirmed for all three issues.

## Source Code Trace

| Element       | Detail                                                                                                                                          |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Error origin  | `story-10-8-artifact-notice.spec.ts:427` / `story-8-3-admin-project-management.spec.ts:177` / `story-8-5-admin-dashboard-ui-layout.spec.ts:135` |
| Trigger       | Playwright strict mode + element-not-found assertion                                                                                            |
| Condition     | Locators in tests do not match current DOM structure in `AdminDashboard.tsx`                                                                    |
| Related files | `frontend/src/components/admin/AdminDashboard.tsx:471-473,770-785`                                                                              |

## Conclusion

Confidence: High

All three failures are Confirmed test-locator mismatches. The production code is correct; the tests reference selectors that don't exist (`data-testid="enabled-provider-checkbox"`) or use the wrong ARIA role (`heading` for a `<div>`), or use a non-strict name that hits two elements. Three targeted one-line fixes resolve all failures.

## Recommended Next Steps

### Fix direction

| # | File | Line | Current locator | Fix |
| - | ---- | ---- | --------------- | --- |
| 1 | `frontend/e2e/story-10-8-artifact-notice.spec.ts` | 427, 433 | `{ name: "Generated Script" }` | Add `exact: true` |
| 2 | `frontend/e2e/story-8-3-admin-project-management.spec.ts` | 177 | `getByTestId("enabled-provider-checkbox")` | `getByRole("checkbox", { name: /Browser Use/i })` |
| 3 | `frontend/e2e/story-8-5-admin-dashboard-ui-layout.spec.ts` | 135 | `getByRole("heading", { name: "Projects" })` | `getByText("Projects").first()` |

### Diagnostic

None needed — root cause is fully Confirmed from static analysis.

## Reproduction Plan

Run the single failing tests in isolation:

```powershell
npx playwright test e2e/story-10-8-artifact-notice.spec.ts --grep "preserves all chat state"
npx playwright test e2e/story-8-3-admin-project-management.spec.ts --grep "creates a project"
npx playwright test e2e/story-8-5-admin-dashboard-ui-layout.spec.ts --grep "disabled Sync button"
```

## Side Findings

- `story-8-5-admin-dashboard-ui-layout.spec.ts:139`: `getByText("Users Management")` — this one will work because it uses `getByText`, not `getByRole("heading")`. Consistent with the `<div>` pattern.
- The `Users Management` section header (AdminDashboard.tsx:807-809) uses the same non-semantic `<div>` pattern as "Projects". Other tests that already use `getByText("Users Management")` are safe.
