---
title: 'AI Server Connection Module'
slug: 'ai-server-connection-module'
created: '2026-03-10'
status: 'completed'
stepsCompleted: [1, 2, 3, 4]
tech_stack: ['Python 3.14.3', 'httpx 0.28.1 + httpx[http2]', 'httpcore 1.0.9', 'PyYAML 6.0.3']
files_to_modify: ['check_connection.py', 'config.yaml (new)', 'config.example.yaml (new)', 'requirements.txt (new)', '.gitignore (modify)', 'ai_connection/ (new module)']
code_patterns: ['Clean Slate - no existing patterns or conventions']
test_patterns: ['No test framework yet']
---

# Tech-Spec: AI Server Connection Module

**Created:** 2026-03-10

## Overview

`check_connection.py` cannot connect to the on-premise AI server. After investigation, the server performs SSL renegotiation twice then closes the connection with an empty reply. This affects all Python HTTP clients (requests, httpx, http.client) and even curl on Windows (schannel). The user needs a working connection to the LLM API with dynamic configuration for R&D purposes.
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
- User is on corporate VPN in office
- No test framework, no config system, no module structure yet

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `check_connection.py` | Current connection script (broken) — to be rewritten |

### Files to Modify/Create

| File | Action | Purpose |
| ---- | ------ | ------- |
| `check_connection.py` | Rewrite | Use `httpx` with HTTP/2, load config from file |
| `.gitignore` | Modify | Append `config.yaml`, `__pycache__/`, `*.pyc`, `.env` to existing rules |
| `config.example.yaml` | Create | Template config with placeholder values (committed) |
| `config.yaml` | Create | Dynamic config: endpoint, model, API key (gitignored) |
| `requirements.txt` | Create | Pin dependencies for reproducible setup |
| `ai_connection/` | Create | Connection module package |

### Technical Decisions

- **Root Cause Analysis (updated 2026-03-10 after spike):**
  - **Original hypothesis DISPROVEN:** ALPN/HTTP2 mismatch was NOT the cause
  - **Actual root cause: Network/firewall blocking HTTPS from the office**
  - [INTERNAL_FIREWALL] (FortiClient running on machine) allows TCP+TLS handshake but drops application data
  - Server cert is legitimate (GandiCert/DigiCert, `*.domain`) — no TLS interception
  - [INTERNAL_VPN] [REDACTED_LOCATION] creates correct routes (`XXX.XXX.XXX.0/24 → wg2`) but WireGuard tunnel has 100% packet loss ([INTERNAL_FIREWALL] likely blocks WireGuard data plane)
  - **Status: BLOCKED — IT ticket submitted to whitelist domain or fix VPN tunnel**
  - **Tested and ruled out:** HTTP/2, HTTP/1.1, TLS 1.2, TLS 1.3, client certificates ([INTERNAL_FIREWALL]), browser-like headers, JA3 fingerprint (curl_cffi), truststore, legacy renegotiation, both server IPs, no SNI, Node.js, OpenSSL s_client, .NET WebRequest, PowerShell, alternative ports (4000/8443/8080)
  - **When IT resolves:** Re-run spike (Task 1.5) to validate connectivity, then proceed to Phase 2
- **Connection investigation findings:**
  - DNS resolves OK
  - TCP connection succeeds (without VPN)
  - TLS handshake succeeds (TLSv1.3 + TLSv1.2, both tested)
  - HTTP port 80 returns 302 redirect to HTTPS (without VPN)
  - HTTPS: server sends close_notify after TLS renegotiation × 2 (schannel) or immediately (OpenSSL)
  - Browser also fails ("didn't send any data")
  - [INTERNAL_FIREWALL] processes active: [INTERNAL_FIREWALL]_ESNAC, [INTERNAL_FIREWALL]_VPN, [INTERNAL_FIREWALL]_SSLVPN, [INTERNAL_FIREWALL]_Tray
  - [INTERNAL_FIREWALL] SSL inspection CA installed in root store
- **Python version:** 3.14.3 (target — upgrade from current 3.13.12)
- **SSL verification:** `verify_ssl: false` is required because the corporate on-premise server uses an internal CA certificate not present in Python's `certifi` trust store. Future improvement: add corporate CA bundle to trust store and re-enable verification.
- **Encoding strategy:** Set `PYTHONUTF8=1` environment variable to handle Unicode output on Windows (replaces cp1252 default). This is the single encoding strategy — do NOT also use ASCII-safe workarounds.
- **httpx.Client lifecycle:** Use `AIClient` as a context manager (`__enter__`/`__exit__`) wrapping a persistent `httpx.Client` instance for HTTP/2 connection reuse. Provide explicit `close()` method for non-context-manager usage.
- **API endpoints (OpenAI-compatible via LLM proxy):**
  - Health check: `GET {base_url}/health`
  - Chat completions: `POST {base_url}/v1/chat/completions` (use `json=` parameter for auto Content-Type)
  - List models: `GET {base_url}/v1/models`
- **Config path resolution:** Triple fallback: (1) explicit path parameter, (2) `AI_CONFIG_PATH` env var, (3) `Path(__file__).parent.parent / "config.yaml"`. This ensures it works when imported from tests, other modules, or different CWDs.

## Implementation Plan

### Tasks

#### Phase 1: Validate Hypothesis (MUST PASS before Phase 2)

- [ ] Task 1: Install HTTP/2 dependencies
  - File: (terminal)
  - Action: Run `pip install httpx[http2]` to install `h2`, `hpack`, `hyperframe` packages
  - Notes: `httpx` 0.28.1 already installed, this adds HTTP/2 protocol support on Python 3.13.12.

- [ ] Task 1.5: Spike — Validate connection hypothesis (DECISION GATE)
  - File: (terminal, inline script)
  - Action: Run two minimal tests to prove `httpx[http2]` fixes the connection:
    ```python
    import httpx
    client = httpx.Client(http2=True, verify=False)
    headers = {"Authorization": "Bearer <YOUR_API_KEY>"}

    # Test 1: Health check (GET)
    r1 = client.get("domain/health", headers=headers)
    print("Health:", r1.status_code, r1.text)

    # Test 2: Chat completion (POST) — proves the actual API path works
    r2 = client.post("domain/v1/chat/completions",
                     headers=headers,
                     json={"model": "inference-deepseekr1-70b",
                           "messages": [{"role": "user", "content": "Hello"}]})
    print("Chat:", r2.status_code, r2.text[:200])
    ```
  - **IF SUCCESS (HTTP responses received from both tests):** Proceed to Phase 2.
  - **IF FAIL (same empty reply / connection closed):** STOP. Hypothesis is wrong. Investigate alternatives:
    1. Contact IT team about mTLS / client certificate requirements
    2. Test from a different network / machine
    3. Check if WAF or reverse proxy is blocking non-browser clients
    4. Try with explicit client certificate if IT provides one
  - Notes: This is the most critical task. Do NOT proceed to Phase 2 if this fails.

#### Phase 2: Build Module (only after Phase 1 passes)

- [ ] Task 2a: Update `.gitignore`
  - File: `.gitignore` (modify, project root)
  - Action: **Append** the following lines to the existing `.gitignore` (do NOT overwrite — existing rules include `prompt.txt`, `_bmad`, `.claude`):
    ```
    # Python
    __pycache__/
    *.pyc
    .env

    # Secrets
    config.yaml
    ```
  - Notes: MUST be done BEFORE `config.yaml` to prevent accidental commit of API keys. The existing `check_connection.py` already has an API key in git history — coordinate with key owner to rotate it after module is working.

- [ ] Task 2b: Create `requirements.txt`
  - File: `requirements.txt` (new, project root)
  - Action: Create with pinned dependencies:
    ```
    httpx[http2]>=0.28.1
    PyYAML>=6.0.3
    ```
  - Notes: Enables reproducible setup on other machines via `pip install -r requirements.txt`.

- [ ] Task 3: Create config files
  - File: `config.example.yaml` (new, project root) + `config.yaml` (new, gitignored)
  - Action: Create `config.example.yaml` with placeholder values:
    ```yaml
    ai_server:
      base_url: "https://your-ai-server.example.com"
      api_key: "<REPLACE_WITH_YOUR_API_KEY>"
      model: "your-model-name"
      timeout: 120
      verify_ssl: false
      http2: true
      ca_bundle: ""  # optional: path to corporate CA bundle (e.g. "/path/to/ca-bundle.pem")
    ```
    Then copy to `config.yaml` and fill in real values locally.
  - Notes: YAML chosen for readability. `api_key` can also be overridden by env var `AI_API_KEY`. Default timeout is 120s (LLM reasoning models can be slow). Only `config.example.yaml` is committed.

- [ ] Task 4: Create connection module package
  - File: `ai_connection/__init__.py` (new)
  - Action: Create package with exports for `AIClient` and `load_config`
  - Notes: Keep minimal — just re-exports

- [ ] Task 5: Create config loader
  - File: `ai_connection/config.py` (new)
  - Action: Create `load_config(path=None)` function that:
    - Path resolution priority: (1) explicit `path` parameter, (2) env var `AI_CONFIG_PATH`, (3) default `Path(__file__).resolve().parent.parent / "config.yaml"`
    - Reads YAML config file using `pyyaml`
    - Allows env var override for `api_key` (`AI_API_KEY`)
    - Returns a dataclass with validated config values
    - Validates types: `base_url` (str, no trailing slash), `api_key` (str, non-empty), `model` (str, non-empty), `timeout` (int/float, > 0), `verify_ssl` (bool), `http2` (bool), `ca_bundle` (str, optional — if non-empty, file must exist)
    - Raises clear error if: config file not found, required fields missing, or invalid types/values
  - Notes: Use `pyyaml` for parsing. Triple fallback path resolution ensures it works regardless of CWD or import context.

- [ ] Task 6: Create AI client module
  - File: `ai_connection/client.py` (new)
  - Action: Create `AIClient` class that:
    - Accepts config from Task 5
    - Implements `__enter__`/`__exit__` (context manager) wrapping a persistent `httpx.Client(http2=config.http2, verify=config.ca_bundle or config.verify_ssl, timeout=config.timeout)`
    - Also provides explicit `close()` method for non-context-manager usage
    - Implements `chat(messages: list[dict]) -> dict`:
      - `POST {base_url}/v1/chat/completions` using `json=` parameter (auto Content-Type)
      - Returns parsed response dict
    - Implements `health_check() -> bool`:
      - `GET {base_url}/health`
      - Returns `True` if any HTTP response received
    - Implements `list_models() -> list[str]`:
      - `GET {base_url}/v1/models`
      - Returns list of model ID strings — handle both OpenAI format (`response["data"][].id`) and flat list format for LiteLLM proxy compatibility
    - Handles common errors with descriptive messages:
      - Timeout → "Server did not respond within {timeout}s"
      - Connection error → "Cannot reach server at {base_url}"
      - Auth error (401/403) → "Authentication failed — check API key"
      - Other HTTP errors → status code + response body
  - Notes: OpenAI-compatible API format. Bearer token auth via `Authorization` header. Persistent client reuses HTTP/2 connection for performance.

- [ ] Task 7: Rewrite check_connection.py
  - File: `check_connection.py` (rewrite)
  - Action: Replace current script to:
    - Set `os.environ["PYTHONUTF8"] = "1"` at top of script for Windows Unicode support
    - Import from `ai_connection` module
    - Load config from `config.yaml`
    - Run health check
    - List available models
    - Send a test message and print the LLM response
    - Print diagnostic info on failure (URL, status, error type)
  - Notes: This becomes the quick validation script for testing connectivity. The old file contains a hardcoded API key in git history — note in output to coordinate key rotation.

### Acceptance Criteria

#### Phase 1 Gate

- [ ] AC0: Given `httpx[http2]` is installed, when running the spike script (Task 1.5) against the live server, then HTTP responses are received from both `GET /health` and `POST /v1/chat/completions`. **Any HTTP status code (200, 400, 401, 403, 500) = PASS** — the spike validates transport layer connectivity, not authentication. Only connection-level failures (empty reply, ConnectionError) = FAIL. **If FAIL, do not proceed.**

#### Phase 2

- [ ] AC1: Given `httpx[http2]` is installed, when importing `httpx` and checking HTTP/2 support, then `h2` module is available and `httpx.Client(http2=True)` initializes without error.

- [ ] AC2: Given `.gitignore` exists, when running `git status` after creating `config.yaml`, then `config.yaml` is NOT listed as untracked. `config.example.yaml` IS tracked.

- [ ] AC3: Given a valid `config.yaml` exists, when calling `load_config()`, then it returns a config object with `base_url`, `api_key`, `model`, `timeout`, `verify_ssl`, `http2`, `ca_bundle` fields populated correctly.

- [ ] AC4: Given `AI_API_KEY` env var is set, when calling `load_config()`, then the env var value overrides `api_key` from the YAML file.

- [ ] AC5: Given `config.yaml` is missing or malformed, when calling `load_config()`, then a clear error message is raised indicating the issue.

- [ ] AC6: Given the AI server is reachable and config is valid, when calling `AIClient.chat([{"role": "user", "content": "Hello"}])`, then a non-empty response is returned containing the LLM's reply text.

- [ ] AC7: Given the AI server is reachable, when calling `AIClient.health_check()`, then it returns `True`.

- [ ] AC8: Given the AI server is reachable, when calling `AIClient.list_models()`, then a non-empty list of model name strings is returned.

- [ ] AC9: Given the AI server is unreachable or returns 401/403, when calling `AIClient.chat(...)`, then a descriptive error is raised indicating the failure type (timeout → "Server did not respond", connection → "Cannot reach server", auth → "Authentication failed — check API key").

- [ ] AC10: Given the complete module is set up, when running `python check_connection.py`, then it loads config, connects to the server, sends a test message, and prints the LLM response to the console without encoding errors.

## Additional Context

### Dependencies

- `httpx[http2]` 0.28.1 — HTTP client with HTTP/2 support via OpenSSL (primary)
- `h2` — HTTP/2 protocol library (auto-installed as dependency of `httpx[http2]`)
- `httpcore` 1.0.9 — low-level HTTP transport (already installed)
- `PyYAML` 6.0.3 — YAML config file parsing (already installed)

### Testing Strategy

- **Manual integration test**: Run `python check_connection.py` and verify LLM response is printed
- **Config test**: Modify `config.yaml` (change model name) and re-run to verify dynamic config works
- **Env var test**: Set `AI_API_KEY` env var and verify it overrides YAML config
- **Error test**: Use invalid API key or wrong URL and verify descriptive error messages
- **Encoding test**: Verify no `UnicodeEncodeError` on Windows console output

### Notes

- API Key is provided separately by user — never commit to spec or source control
- User wants dynamic config because this is R&D — models and endpoints will change frequently
- Bruno collection is a separate project on a different machine/country — not a direct reference
- Available models to test: `inference-deepseekr1-70b`, `inference-gpt-oss-120b`
- If spike (Task 1.5) fails, STOP and investigate: mTLS, client cert, WAF, IP allowlist — contact IT team
- **Recommended follow-up:** Add `pytest` to `requirements.txt` and write unit tests for `load_config()` (AC3-AC5 are fully testable offline without server). Low cost, high value for catching config regressions as the project grows.

## Review Notes
- Adversarial review completed: 14 findings total
- 12 real findings fixed, 2 noise skipped (F7: YAML bomb, F12: __del__)
- Resolution approach: auto-fix
- Key fixes: custom exceptions, verify_ssl default True, granular timeouts, JSON error handling, API key redaction in repr, broader gitignore, health check validates status code
- **Critical discovery:** Server requires [INTERNAL_VPN] [REDACTED_LOCATION] + HTTP/2 only (no HTTP/1.1). Use `http1=False, http2=True`.
