---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.11: Display Current Frontend Version in UI

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Frontend-only, small. Inject the `package.json` version at build time via Vite `define` and show it unobtrusively in the app shell, with a safe `dev`/`unknown` fallback. No runtime request.

## Story

As a QA user or administrator,
I want the current frontend version to be visible somewhere in the UI,
so that I can tell which build I am using when reporting issues or confirming a deployment.

## Acceptance Criteria

1. **Single authoritative, build-time source.** Given the frontend is built, when the application bundle is produced, then the version is sourced from a single authoritative place (the frontend `package.json` version, optionally with short build/commit metadata) and injected at build time, so no extra runtime request is needed to read it.

2. **Visible, unobtrusive, in-shell.** Given an authenticated user is in the application shell, when any primary screen is rendered, then the current frontend version is displayed in a consistent, unobtrusive location (e.g. footer, user/account menu, or "About" area) using the App-UI-English-only convention.

3. **Clearly identifiable + non-obstructive + accessible.** Given the version label is shown, when the user reads it, then it is clearly identifiable as the frontend version (e.g. `v1.4.0`), does not overlap or obstruct interactive controls, and meets the project accessibility/contrast baseline.

4. **Safe fallback.** Given the build has no resolvable version or metadata, when the version label would render, then it falls back to a safe placeholder (e.g. `dev` / `unknown`) rather than an empty/broken/error state, and never exposes secrets or internal build paths.

## Tasks / Subtasks

- [ ] **Task 1 — Inject the version at build time (AC: 1, 4)**
  - [ ] In `frontend/vite.config.ts`, read the version from `frontend/package.json` (current value `0.1.0`) and expose it via `define: { __APP_VERSION__: JSON.stringify(pkg.version ?? "dev") }` (and optionally a short commit/build id from an env var, defaulting safely). No `import.meta.env` runtime fetch needed.
  - [ ] Declare the global in `frontend/src/vite-env.d.ts` (`declare const __APP_VERSION__: string;`) so TS strict mode resolves it.
  - [ ] Ensure no secret/internal path is ever injected — version + optional short commit only (AC4).

- [ ] **Task 2 — Version display component (AC: 2, 3, 4)**
  - [ ] Add a small `AppVersion` component (new `frontend/src/components/AppVersion.tsx`) rendering `v{__APP_VERSION__}` with a safe fallback to `dev`/`unknown` when missing/empty.
  - [ ] Place it unobtrusively in the app shell — recommended: the top-nav right cluster near Sessions/Logout (the shell has no footer today) ([frontend/src/App.tsx](frontend/src/App.tsx)). Small muted text, clearly labelled as the frontend version, not overlapping controls.
  - [ ] English-only label; meet contrast/focus baseline (muted slate that still passes AA; it is non-interactive text so no focus ring needed, but ensure it doesn't sit on a low-contrast background).

- [ ] **Task 3 — Tests (AC: 2, 3, 4)**
  - [ ] Add `frontend/src/components/__tests__/AppVersion.test.tsx`: renders the version when `__APP_VERSION__` is defined; renders the `dev`/`unknown` fallback when undefined/empty. Define/undefine the global via `vi.stubGlobal`/`globalThis` per the Vitest pattern.
  - [ ] `npm run typecheck` (must resolve `__APP_VERSION__`) + `npm run lint` + `npm test`; `npm run build` to confirm the define injects.

## Dev Notes

### What exists / what's missing (from research)

- `frontend/package.json` version = `"0.1.0"` (the authoritative source).
- `frontend/vite.config.ts` has NO `define` for a version constant; there is no `import.meta.env.VITE_*` usage anywhere; `vite-env.d.ts` is effectively empty.
- The app shell (`App.tsx`) has a top nav with a right cluster (user name, Sessions, Logout) — the natural home. There is no footer/account-dropdown/About component today, so adding one is optional scope; prefer the existing nav cluster to keep it minimal.

### Recommended approach

Build-time `define` (AC1: no runtime request) + a tiny presentational component with a fallback (AC4). This is the lowest-footprint path and matches the repo's no-extra-deps posture. Reading `package.json` in `vite.config.ts` is standard (import the JSON or `process.env.npm_package_version`); keep it simple and synchronous.

### Source tree components to touch

- `frontend/vite.config.ts` — **UPDATE** (`define: { __APP_VERSION__ }`).
- `frontend/src/vite-env.d.ts` — **UPDATE** (declare the global).
- `frontend/src/components/AppVersion.tsx` — **NEW**.
- `frontend/src/App.tsx` — **UPDATE** (render `AppVersion` in the nav right cluster).
- `frontend/src/components/__tests__/AppVersion.test.tsx` — **NEW**.

### Current behavior to PRESERVE (regression guardrails)

- Tailwind v4 is wired via the `@tailwindcss/vite` plugin (no `postcss.config.js`) — when editing `vite.config.ts`, do not disturb the plugin order `plugins: [react(), tailwindcss()]` ([[project-context]]).
- App-UI-English-only ([[app-ui-english-only]]).
- Don't add a backend endpoint or runtime fetch — AC1 says build-time, no extra request.

### Testing standards summary

- Vitest 4 + RTL; stub `__APP_VERSION__` via `vi.stubGlobal("__APP_VERSION__", "1.2.3")` and clear in `afterEach`. Assert the rendered `v1.2.3` and the fallback path.
- `npm run typecheck` is the real gate (Vite build skips strict errors) — the global declaration must satisfy it.

### Project Structure Notes

- FE-only; no schema/migration; no new dependencies. One new component + a Vite define + a type declaration.

### References

- Epic + ACs: [epics.md#Story-16.11](_bmad-output/planning-artifacts/epics.md:1930)
- `frontend/package.json` (version), `frontend/vite.config.ts`, `frontend/src/App.tsx` (nav cluster), `frontend/src/vite-env.d.ts`
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [[app-ui-english-only]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
