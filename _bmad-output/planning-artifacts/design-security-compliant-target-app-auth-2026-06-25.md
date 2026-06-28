# Design Note: Security-Compliant Target-App Authentication (Epic 25)

**Date:** 2026-06-25
**Epic:** 25
**Status:** Approved for Implementation

## 1. Goal
Design a secure, compliant authentication mechanism for target applications that replaces the prohibited session capture method (which read employee cookies). The new mechanism relies on **dedicated test accounts** and **automated login**.

## 2. Login-Automation Mechanism Spike: Browser-Use vs Scripted

We evaluated two methods to perform the automated login:

### A. Browser-Use-Driven Login (LLM Agent)
- **Pros:** Highly resilient to login page UI changes.
- **Cons:** Slow (adds 30s-1m to startup), consumes LLM tokens, higher failure rate due to hallucinations, potential struggles with precise MFA/TOTP flows.
- **Verdict:** REJECTED for the primary path. Login is a predictable, deterministic hurdle.

### B. Scripted Playwright Routine
- **Pros:** Fast (< 5s), deterministic, 100% reliable if selectors are correct, supports robust TOTP generation (e.g., via `pyotp`).
- **Cons:** Requires maintenance if the Identity Provider (IdP) completely changes its DOM (rare for Entra/Okta).
- **Verdict:** **ACCEPTED.** We will use a scripted Playwright harness that knows how to navigate standard IdPs (like Azure Entra ID / basic auth forms) given the credentials and URL.

## 3. Credential Storage Model

We must store test account credentials securely without leaking them to logs, scripts, or the LLM.

- **Storage Level:** Database table `TestAccountCredential`.
- **Scope:** Unique per `(project_id, environment_name, role)`.
- **Fields:**
  - `id` (UUID, PK)
  - `project_id` (UUID, FK)
  - `environment_name` (String)
  - `role` (String)
  - `username` (EncryptedText)
  - `password` (EncryptedText)
  - `totp_secret` (EncryptedText, nullable)
- **Encryption Mechanism:** Reuse the existing per-user Fernet `EncryptedText` SQLAlchemy custom type (same as provider keys).
- **Leak Prevention:** The credentials will only be decrypted in memory by the execution runner (Playwright login script) and are explicitly scrubbed from any generated `storageState.json` logs.

## 4. Per-App Login Hint Shape

To aid the scripted Playwright routine, we will store a lightweight configuration per environment (or project):
- `login_url`: The start URL for authentication.
- `login_mechanism`: Enum (`ENTRA_ID`, `BASIC_FORM`, `CUSTOM_OAUTH`).
- Optional selectors (if `BASIC_FORM`): `username_selector`, `password_selector`, `submit_selector`.

## 5. IT Asks and Security Sign-Off

To implement this, we require the following from IT and Group Security:

1. **Dedicated QA Accounts:** Provision dedicated QA test accounts per app-role in Azure/Entra, strictly scoped to test/UAT data (non-privileged where possible). Confirm these can be used by an automated test harness.
2. **MFA Resolution:** Resolve MFA/Conditional Access for these accounts by either:
   - **(a) MFA Exemption:** Fully exempt the account so login is a scriptable username/password form.
   - **(b) TOTP Seed:** Provide a TOTP seed we can store encrypted and compute codes from via `pyotp` during the scripted login.
   - *Push-MFA and biometrics cannot be automated.*
3. **Security Sign-Off:** Confirm that storing these dedicated test-account credentials encrypted at rest (using Fernet) is an acceptable replacement for the forbidden session capture.
4. **External Apps:** For external targets, confirm whether a dedicated username/password login exists or if 3rd-party OAuth (Google/Apple) is strictly required (which may necessitate specialized test accounts).

## 6. Implementation Sequence

This design dictates the implementation of Stories 25-2 through 25-7:
- **25-2:** Clean up and remove the forbidden session capture surface.
- **25-3:** Build the `TestAccountCredential` DB model and admin API.
- **25-4:** Build the scripted Playwright auto-login engine.
- **25-5:** Wire the generated `storageState` from the auto-login engine into Sarah and Jack.
- **25-6:** Extend the auto-login engine for external apps.
- **25-7:** Update documentation and run live validation.
