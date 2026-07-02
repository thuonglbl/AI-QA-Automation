# Sprint Change Proposal: Fix Backend Connectivity Check SSL Verification

## Section 1: Issue Summary
Currently, the Project Admin Dashboard validates environment URLs by making a request from the backend server to the target URL (`/projects/{id}/environments/check-connections`).
It was initially suspected that a firewall or DNS issue prevented the backend from reaching internal SSO URLs. However, further investigation revealed that the backend server **can** reach the server, but the connection is dropped because of an SSL Certificate Verification failure (`CERTIFICATE_VERIFY_FAILED`). This happens because internal URLs often use corporate PKI or self-signed certificates that Python's default certificate store does not trust.

As correctly pointed out, we must keep the check on the backend (where the headless UAT browser actually runs). Moving it to the frontend would produce false positives if the backend server truly lacked access.

## Section 2: Impact Analysis
- **Epic/Story Impact**: Modifies the Epic/Story dealing with Project Settings & Validation.
- **Technical Impact**: 
  - **Backend**: We will modify the `httpx.AsyncClient` used in `check_environment_connections` to set `verify=False`. This tells the HTTP client to ignore SSL certificate validation errors when performing the reachability ping. 
  - **Security**: Since this endpoint only performs a basic `GET` request to check if a server is listening and discards the response (without sending any credentials or sensitive data), disabling SSL verification here is perfectly safe and solves the issue for internal URLs.

## Section 3: Recommended Approach
**Option 1: Direct Adjustment (Disable SSL Verification for Reachability Check)**
We will update `src/ai_qa/api/sessions.py` to disable SSL verification for the environment connectivity check.

**Effort estimate:** Low (1 line of code change)  
**Risk level:** Low  
**Justification:** This approach keeps the check exactly where it needs to be (on the server that will run the headless tests), while correctly handling internal corporate URLs that use self-signed certificates.

## Section 4: Detailed Change Proposals

### 1. Update `src/ai_qa/api/sessions.py`
[MODIFY] Add `verify=False` to the `httpx.AsyncClient` context manager.
```diff
    async with httpx.AsyncClient(
-       timeout=_CONNECTION_CHECK_TIMEOUT, follow_redirects=False
+       timeout=_CONNECTION_CHECK_TIMEOUT, follow_redirects=False, verify=False
    ) as http_client:
```

## Section 5: Implementation Handoff
- **Scope**: Minor
- **Route to**: Developer agent for direct implementation
- **Deliverables**: Updated `sessions.py`.
