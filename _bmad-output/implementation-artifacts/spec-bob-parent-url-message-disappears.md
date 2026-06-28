---
title: 'Keep the submitted parent-page Confluence URL visible in chat (Bob confirm-parent)'
type: 'bugfix'
created: '2026-06-23'
status: 'done'
route: 'one-shot'
---

# Keep the submitted parent-page Confluence URL visible in chat (Bob confirm-parent)

## Intent

**Problem:** In Bob's confirm-parent step, the user types a Confluence parent-page URL and submits (Start/Enter or OK/Skip), but the URL never appears as a chat bubble — it vanishes the moment the panel unmounts. Root cause (forensically confirmed): `handleBobApproveParent` was the only Bob submit handler that never called `addUserMessage`, so no user bubble was ever created; user-side bubbles can only originate client-side (the backend never echoes user input over WebSocket).

**Approach:** Echo the user's choice with `addUserMessage(trimmed ? trimmed : "Skip")` before `sendMessage`, mirroring `handleBobSelectId` / `handleBobClarifyAnswer`. Also hide the panel on submit (`setBobState({ isConfirmParent: false })`) so a fast double-click can't fire a duplicate approve + duplicate bubble before Bob's processing message flips status — making the handler truly consistent with its sibling.

## Suggested Review Order

1. [App.tsx:1532 — handleBobApproveParent](../../frontend/src/App.tsx#L1532) — the fix: echo bubble + immediate panel-hide; dep array now includes `addUserMessage`.
2. [App.tsx:2243 — default chat bubble render](../../frontend/src/App.tsx#L2243) + [App.tsx:2038 — chat render filter](../../frontend/src/App.tsx#L2038) — context: confirms a plain user URL message (no metadata) passes every filter rule and renders as a "You" bubble.
3. [App.test.tsx:434 — "Bob confirm parent URL popup"](../../frontend/src/App.test.tsx#L434) — regression tests: spy-call asserts (URL echoed / "Skip" echoed) **plus** a render-level assertion that the URL bubble survives the filter — the link the bug actually lived in.
4. [Investigation case file](investigations/bob-parent-url-message-disappears-investigation.md) — full evidence-graded root-cause trace (High confidence).

## Verification

**Commands:** (run in `frontend/`)
- `npm run typecheck` — expected: no errors. ✅
- `npx vitest run src/App.test.tsx` — expected: 17/17 pass (incl. the new render-level regression). ✅
- `npx vitest run` — expected: full suite green (34 files / 352 tests). ✅
- `npx eslint src/App.tsx src/App.test.tsx` — expected: no errors. ✅

**Manual check (live):**
- Bob → enter MCP key → reach the "I found the link below…" parent-page prompt → type a Confluence URL → OK. Expected: a blue "You" bubble with the URL persists between the two "Bob's thought" bubbles and survives a page reload.
