---
title: 'Fix Bitbucket secret-scanner false positive in story 13-4 spec'
type: 'bugfix'
created: '2026-06-17'
status: 'done'
route: 'one-shot'
---

## Intent

**Problem:** Bitbucket secret scanning flagged commit `579e9edca9b` for a "Basic auth" credential leak at `_bmad-output/implementation-artifacts/13-4-browser-sso-session-compatibility.md:109`. The text was a documentation example describing patterns a hardcoded-secret detector should flag (`"Basic …"`, `"Bearer …"`), not a real credential.

**Approach:** Rephrase the example strings on line 109 using prose notation (`Bearer-type or Basic-type`) and RFC 3986 angle-bracket placeholder format (`<scheme>://<user>:<pass>@<host>`) so no scanner-triggering literal remains while preserving the technical meaning.

## Suggested Review Order

1. [`_bmad-output/implementation-artifacts/13-4-browser-sso-session-compatibility.md:109`](_bmad-output/implementation-artifacts/13-4-browser-sso-session-compatibility.md) — the only changed line; confirm prose replaces the `"Basic …"` / `"Bearer …"` quoted literals.
