---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.6: Keyboard and Accessibility Support

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> An accessibility baseline exists (ARIA roles/labels, aria-live regions, color+text, autofocus). This story closes the **named a11y gaps**: focus traps in modal/drawer surfaces, keyboard navigation for review-item controls, `aria-expanded`/`aria-controls` on expandables, a main landmark + skip link, and reduced-motion guards.

## Story

As a keyboard or assistive-technology user,
I want the conversational workflow and review panels to be accessible,
so that I can complete the QA automation workflow without relying only on a mouse.

## Acceptance Criteria

1. **Logical, visible, non-trapping focus.** Given the user navigates the application with keyboard only, when they move through chat, controls, review panels, the artifact tree, and dialogs, then focus order is logical, visible, and does not trap the user unexpectedly.

2. **AT communicates meaning.** Given controls, status messages, errors, and dynamic updates are rendered, when assistive technology reads the UI, then labels, roles, ARIA states (incl. `aria-expanded`/`aria-controls` on expandables), and live regions communicate meaning clearly.

3. **Contrast + focus baseline.** Given visual design tokens are applied, when text, icons, buttons, alerts, and review panels are displayed, then contrast and focus states meet the project accessibility baseline (WCAG AA: ≥4.5:1 normal text, ≥3:1 large; visible focus rings).

## Tasks / Subtasks

- [ ] **Task 1 — Focus management for modal/drawer surfaces (AC: 1) [GAP]**
  - [ ] Add focus trap + restore-on-close to dialog-like surfaces lacking it: `ArtifactPreview` and its delete-confirm modal ([frontend/src/components/artifacts/ArtifactPreview.tsx](frontend/src/components/artifacts/ArtifactPreview.tsx)), and any session/about dialogs. Trap Tab within the modal, Esc closes, focus returns to the trigger.
  - [ ] Verify chat/input/review focus order is logical and not trapped during normal flow.

- [ ] **Task 2 — Keyboard nav for review-item controls (AC: 1, 2) [GAP]**
  - [ ] Make the `SarahScriptReviewPanel` per-script status dots keyboard-operable (currently click-only): `tabindex`, arrow-key Prev/Next, Enter/Space to select ([frontend/src/components/agents/SarahScriptReviewPanel.tsx](frontend/src/components/agents/SarahScriptReviewPanel.tsx)). Keep the existing Prev/Next buttons.
  - [ ] Add `aria-expanded` + `aria-controls` to expandable toggles (e.g. `MaryReviewPanel` confidence rationale) and link error banners to their field via `aria-describedby`.

- [ ] **Task 3 — Landmarks, skip link, reduced motion (AC: 1, 3) [GAP]**
  - [ ] Wrap the primary content region in a `<main>` landmark and add a hidden skip-to-main link in the app shell ([frontend/src/App.tsx](frontend/src/App.tsx)).
  - [ ] Add `motion-safe:`/`motion-reduce:` guards (or a `prefers-reduced-motion` media query) to the bounce/slide animations so motion-sensitive users aren't forced into animation (tailwind config + `index.css`).

- [ ] **Task 4 — Contrast + focus baseline audit (AC: 3)**
  - [ ] Spot-check token contrast (slate text on white, agent color dots, amber/red banners, dark code theme) against WCAG AA; fix any token that fails normal-text 4.5:1. Confirm visible focus rings exist on all interactive elements (`focus-visible:ring`).
  - [ ] Confirm color is never the only signal (already true for unsaved indicator + approval caption — keep it).

- [ ] **Task 5 — Tests (AC: 1, 2, 3)**
  - [ ] Add Vitest a11y assertions: focus trap (Tab cycles within modal, Esc restores), arrow-key navigation on the script dots, `aria-expanded` toggles, skip link + `<main>` present.
  - [ ] Where feasible add a Playwright keyboard-only pass for one end-to-end review flow (optional; note if deferred).
  - [ ] `npm run typecheck` + `npm run lint` + `npm test` green.

## Dev Notes

### What already exists (do not rebuild)

- **ARIA roles/labels** — `role="alert"` (ErrorFeedback, ArtifactNotice), `role="region"`/`role="list"`/`role="listitem"`, `aria-label` on Prev/Next, close, toggles, model selects, form fields, image alts.
- **Live regions** — `aria-live="polite"` in `ChatInputArea` and `ProjectAdminDashboard`.
- **Color + text** — unsaved indicator ("● Unsaved changes"), approval caption ("Approved by …") — both color + text, not color alone.
- **Focus** — autofocus on the retry button; `focus-visible:ring` on form fields; tab/enter flow.
- **Design tokens** — Tailwind v4 slate/semantic palette + system font stack; `--radius` in `index.css`.

### The named gaps (from the a11y research)

- No focus trap in modal/drawer surfaces (ArtifactPreview, delete confirm).
- Review-item status dots are click-only (no keyboard/arrow nav).
- Expandables lack `aria-expanded`/`aria-controls`; error banners lack `aria-describedby`.
- No `<main>` landmark, no skip link.
- Animations have no reduced-motion guard.

### Source tree components to touch

- `frontend/src/components/artifacts/ArtifactPreview.tsx` — **UPDATE** (focus trap + restore).
- `frontend/src/components/agents/SarahScriptReviewPanel.tsx`, `MaryReviewPanel.tsx` — **UPDATE** (keyboard nav, aria-expanded/controls).
- `frontend/src/App.tsx` — **UPDATE** (main landmark + skip link).
- `frontend/tailwind.config.js` + `frontend/src/index.css` — **UPDATE** (reduced-motion guards).
- Tests under `frontend/src/components/__tests__/` — **UPDATE/ADD**; optional Playwright `frontend/e2e/`.

### Current behavior to PRESERVE (regression guardrails)

- Existing ARIA labels + `data-testid="thread-{id}"` + frozen `getByText` artifact labels (10-7/10-8) — extend, don't rename.
- Tooltip is mocked in `src/test-setup.ts` (pass-through) — don't rely on hover for a11y info.
- App-UI-English-only ([[app-ui-english-only]]).

### Testing standards summary

- Prefer `getByRole`/`getByLabelText`; assert `aria-expanded`, `toHaveFocus`, focus cycling. happy-dom supports focus + keydown simulation.
- `noUncheckedIndexedAccess` — assert array access in tests with `!`.

### Project Structure Notes

- FE-only; no schema/migration; no new dependencies (a focus-trap can be hand-rolled with refs + keydown, consistent with the repo's no-extra-deps posture — only add a library if the user approves).

### References

- Epic + ACs: [epics.md#Story-16.6](_bmad-output/planning-artifacts/epics.md:1808)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [16-4](16-4-rich-review-panels.md), [16-5](16-5-error-empty-and-recovery-states.md)

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
