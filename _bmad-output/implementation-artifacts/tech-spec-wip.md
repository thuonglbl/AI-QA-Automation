---
title: 'AI Server Connection Module'
slug: 'ai-server-connection-module'
created: '2026-03-10'
status: 'ready-for-dev'
stepsCompleted: [1, 2, 3, 4]
tech_stack: ['Python 3.14.3', 'httpx 0.28.1 + httpx[http2]', 'httpcore 1.0.9', 'PyYAML 6.0.3', 'requests 2.32.5 (fallback)']
files_to_modify: ['check_connection.py', 'config.yaml (new)', 'ai_connection/ (new module)']
code_patterns: ['Clean Slate - no existing patterns or conventions']
test_patterns: ['No test framework yet']
---

# Tech-Spec: AI Server Connection Module

**Created:** 2026-03-10

## Overview

### Problem Statement

`check_connection.py` cannot connect to the on-premise AI server at `domain`. After investigation, the server performs SSL renegotiation twice then closes the connection with an empty reply. This affects all Python HTTP clients (requests, httpx, http.client) and even curl on Windows (schannel). The user needs a working connection to the LLM API with dynamic configuration for R&D purposes.

### Solution

Fix the SSL/TLS connection issue (likely Windows schannel incompatibility with server's SSL renegotiation behavior) and create a connection module with dynamic config for endpoint, model, and API key. The module must successfully send messages to the LLM and receive responses.

### Scope

**In Scope:**
- Fix SSL/TLS connection issue on Windows
- Dynamic configuration (endpoint, model, API key) via config file
- Send chat completion requests and receive LLM responses
- Health check and connection diagnostics

**Out of Scope:**
- Multi-provider support (Claude API, etc.) - not needed yet
- Model evaluation/benchmarking logic
- UI/frontend
- The actual project idea (to be defined later)

## Context for Development

### Codebase Patterns

- **Confirmed Clean Slate** — no existing architecture, patterns, or conventions
- Project is in early R&D stage, only `check_connection.py` exists
- `check_connection.py` uses OpenAI-compatible API format (chat/completions endpoint)
- User is on [INTERNAL_VPN] in office
- No test framework, no config system, no module structure yet

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `check_connection.py` | Current connection script (broken) — to be rewritten |

### Files to Modify/Create

| File | Action | Purpose |
| ---- | ------ | ------- |
| `check_connection.py` | Rewrite | Use `httpx` with HTTP/2, load config from file |
| `config.yaml` | Create | Dynamic config: endpoint, model, API key |
| `ai_connection/` | Create | Connection module package |

### Technical Decisions

- **Root Cause Analysis (5 Whys):**
  - Server returns empty reply after SSL renegotiation × 2 → close_notify
  - Curl verbose shows `ALPN: server did not agree on a protocol` — server likely requires HTTP/2 (h2) via ALPN
  - Windows schannel (TLS backend for curl and Python) does NOT support HTTP/2 ALPN negotiation
  - When ALPN mismatch occurs, server renegotiates then rejects the connection
  - **Root cause: ALPN/HTTP2 mismatch — schannel cannot negotiate h2 protocol that server expects**
  - **Fix strategy: Use `httpx[http2]` which uses OpenSSL + h2 library, bypassing schannel limitation**
  - Fallback: rebuild Python with OpenSSL backend, or set `CURL_SSL_BACKEND=openssl`
- **Connection investigation findings:**
  - DNS resolves OK ([REDACTED_IP])
  - TCP connection succeeds
  - TLS handshake succeeds (TLSv1.3, TLS_AES_128_GCM_SHA256)
  - Windows schannel is the TLS backend for both curl and Python
- **Python version:** 3.14.3 (latest stable)
- **Warning:** `urllib3 (2.6.3)` version mismatch with `requests` - may need dependency update
- **Encoding issue:** Vietnamese characters in print statements cause `UnicodeEncodeError` on Windows cp1252

## Implementation Plan

### Tasks

- [ ] Task 0: Upgrade Python to 3.14.3
  - File: (terminal)
  - Action: Download and install Python 3.14.3 from https://www.python.org/downloads/release/python-3143/. Reinstall project dependencies after upgrade.
  - Notes: Current version is 3.13.12. Upgrade required before proceeding with other tasks.

- [ ] Task 1: Install HTTP/2 dependencies
  - File: (terminal)
  - Action: Run `pip install httpx[http2]` to install `h2`, `hpack`, `hyperframe` packages
  - Notes: `httpx` 0.28.1 already installed, this adds HTTP/2 protocol support. Verify compatibility with Python 3.14.3.

- [ ] Task 2: Create config file
  - File: `config.yaml` (new, project root)
  - Action: Create YAML config with the following structure:
    ```yaml
    ai_server:
      base_url: "domain"
      api_key: "api-key"
      model: "inference-deepseekr1-70b"
      timeout: 30
      verify_ssl: false
      http2: true
    ```
  - Notes: YAML chosen for readability. `api_key` can also be overridden by env var `AI_API_KEY` for security. All fields are changeable for R&D flexibility.

- [ ] Task 3: Create connection module package
  - File: `ai_connection/__init__.py` (new)
  - Action: Create package with exports for `AIClient` and `load_config`
  - Notes: Keep minimal — just re-exports

- [ ] Task 4: Create config loader
  - File: `ai_connection/config.py` (new)
  - Action: Create `load_config(path="config.yaml")` function that:
    - Reads YAML config file
    - Allows env var override for `api_key` (`AI_API_KEY`)
    - Returns a typed dict / dataclass with validated config values
    - Raises clear error if config file not found or required fields missing
  - Notes: Use `pyyaml` for parsing. Config path defaults to project root `config.yaml`.

- [ ] Task 5: Create AI client module
  - File: `ai_connection/client.py` (new)
  - Action: Create `AIClient` class that:
    - Accepts config from Task 4
    - Uses `httpx.Client` with `http2=True` and `verify=False` (configurable)
    - Implements `chat(messages: list[dict]) -> dict` — sends chat completion request, returns parsed response
    - Implements `health_check() -> bool` — tests connectivity to server
    - Implements `list_models() -> list[str]` — fetches available models
    - Handles common errors: timeout, connection error, auth error, HTTP error codes
    - Sets `PYTHONUTF8=1` or uses UTF-8 encoding for console output on Windows
  - Notes: OpenAI-compatible API format. Bearer token auth via header.

- [ ] Task 6: Rewrite check_connection.py
  - File: `check_connection.py` (rewrite)
  - Action: Replace current script to:
    - Import from `ai_connection` module
    - Load config from `config.yaml`
    - Run health check
    - Send a test message and print the LLM response
    - Print diagnostic info on failure (URL, status, error type)
    - Use ASCII-safe print statements to avoid Windows cp1252 encoding errors
  - Notes: This becomes the quick validation script for testing connectivity.

### Acceptance Criteria

- [ ] AC1: Given `httpx[http2]` is installed, when importing `httpx` and checking HTTP/2 support, then `h2` module is available and `httpx.Client(http2=True)` initializes without error.

- [ ] AC2: Given a valid `config.yaml` exists, when calling `load_config()`, then it returns a config object with `base_url`, `api_key`, `model`, `timeout`, `verify_ssl`, `http2` fields populated correctly.

- [ ] AC3: Given `AI_API_KEY` env var is set, when calling `load_config()`, then the env var value overrides `api_key` from the YAML file.

- [ ] AC4: Given `config.yaml` is missing or malformed, when calling `load_config()`, then a clear error message is raised indicating the issue.

- [ ] AC5: Given the AI server is reachable and config is valid, when calling `AIClient.chat([{"role": "user", "content": "Hello"}])`, then a non-empty response is returned containing the LLM's reply text.

- [ ] AC6: Given the AI server is reachable, when calling `AIClient.health_check()`, then it returns `True`.

- [ ] AC7: Given the AI server is unreachable or times out, when calling `AIClient.chat(...)`, then a descriptive error is raised (not a raw exception) indicating the failure type (timeout, connection, auth).

- [ ] AC8: Given the complete module is set up, when running `python check_connection.py`, then it loads config, connects to the server, sends a test message, and prints the LLM response to the console without encoding errors.

## Additional Context

### Dependencies

- `httpx[http2]` 0.28.1 — HTTP client with HTTP/2 support via OpenSSL (primary, replaces `requests`)
- `h2` — HTTP/2 protocol library (auto-installed as dependency of `httpx[http2]`)
- `httpcore` 1.0.9 — low-level HTTP transport (already installed)
- `PyYAML` 6.0.3 — YAML config file parsing (already installed)
- `requests` 2.32.5 (fallback only, has urllib3 version mismatch warning)

### Testing Strategy

- **Manual integration test**: Run `python check_connection.py` and verify LLM response is printed
- **Config test**: Modify `config.yaml` (change model name) and re-run to verify dynamic config works
- **Env var test**: Set `AI_API_KEY` env var and verify it overrides YAML config
- **Error test**: Use invalid API key or wrong URL and verify descriptive error messages
- **Encoding test**: Verify no `UnicodeEncodeError` on Windows console output

### Notes

- API Key: shared 2 days ago, likely still valid
- User wants dynamic config because this is R&D — models and endpoints will change frequently
- If `httpx[http2]` does NOT fix the connection, fallback plan: investigate mTLS / client certificate requirement with IT team
- `config.yaml` should be added to `.gitignore` to protect API keys (provide `config.example.yaml` instead)
