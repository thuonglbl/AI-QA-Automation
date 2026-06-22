"""Captured browser-session storage + resolution.

A captured session is a Playwright ``storageState`` blob (cookies + localStorage taken
AFTER the user logged in) — the reusable proof-of-authentication for Sarah (script debug)
and Jack (run). Stored per-user, encrypted at rest (``CapturedSession``); the blob is a
live credential and never leaves the backend except as a rehydrated browser context.
"""
