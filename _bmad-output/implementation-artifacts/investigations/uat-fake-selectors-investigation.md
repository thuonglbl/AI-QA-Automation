# Investigation: UAT Fake Selectors (browser-use fallback)

## Hand-off Brief

1. **What happened.** Jack and Sarah on UAT fail to utilize the user's saved TestAccountCredential. This causes Sarah to fallback to LLM-only selector generation (producing fake `# TODO` selectors) and Jack to abort with a misleading "missing test account" error. 
2. **Where the case stands.** The root cause is confirmed: when the automated headless login (`auto_login.resolve_or_generate_storage_state`) fails on UAT (due to network timeout, firewall, or headless browser blocking), the underlying `BrowserError` is caught and swallowed because `Jack` and `Sarah` do not request it to raise on failure. It silently returns `None`, causing Jack and Sarah to falsely assume the account is missing. Additionally, a critical bug exists in `auto_login.py` where it omits the `user_id` filter when querying the DB, which will break as soon as a second user configures a test account.
3. **What's needed next.** 
    * Fix `auto_login.py` to include `user_id` in the query to prevent `MultipleResultsFound`.
    * Update `Jack` and `Sarah` to properly handle and surface `BrowserError` instead of swallowing it and falsely reporting "missing test account".

## Case Info

| Field            | Value                                                                      |
| ---------------- | -------------------------------------------------------------------------- |
| Ticket           | N/A                                                                        |
| Date opened      | 2026-06-29                                                                 |
| Status           | Concluded                                                                  |
| System           | Local vs UAT (`ai-qa.ai-uat.corpdev.local`)                                |
| Evidence sources | User screenshots, source code trace                                        |

## Problem Statement

Trên môi trường local, account có thể login và lấy được real selectors. Tuy nhiên, trên môi trường UAT (cùng source code), script tạo ra chỉ chứa các fake selectors (`# TODO: Confirm the selector...`) dù account đã được cấu hình trong bảng Test Accounts (và chỉ có 1 user sử dụng).

## Evidence Inventory

| Source   | Status                          | Notes     |
| -------- | ------------------------------- | --------- |
| User Screenshots | Available | Show local vs UAT script generation, Test Account UI, and runner errors. |
| Database Screenshot | Available | Confirms only 1 row exists in `test_account_credentials` on UAT, ruling out `MultipleResultsFound` for this specific user. |
| Source Code | Available | Traced the `auto_login.py`, `jack.py`, and `sarah.py` exception handling. |

## Confirmed Findings

### Finding 1: auto_login failures are silently swallowed

**Evidence:** `src/ai_qa/sessions/auto_login.py:113`
```python
    try:
        new_blob = await generate_session_storage_state(...)
    except BrowserError as exc:
        logger.error("Auto-login failed for role '%s': %s", role, exc)
        if raise_on_failure:
            raise
        return None
```
**Detail:** `Jack` and `Sarah` call this function with `raise_on_failure=False` (default). If the UAT server fails to perform the headless login (e.g. timeout reaching the target app, UAT container cannot reach the OpenAI API, or the target site blocks headless Chromium), `BrowserError` is caught and `None` is returned. Jack sees `None` and displays the misleading message: *"the selected scripts include role(s) with no test account. Configure a test account..."*, making it seem like the account wasn't saved.

### Finding 2: auto_login.py misses the user_id filter (Latent Bug)

**Evidence:** `src/ai_qa/sessions/auto_login.py:64`
```python
    credential = db.execute(
        select(TestAccountCredential).where(
            TestAccountCredential.project_id == project_id,
            TestAccountCredential.environment == environment,
            TestAccountCredential.role == role,
            # MISSING: TestAccountCredential.user_id == user_id
        )
    ).scalar_one_or_none()
```
**Detail:** `TestAccountCredential` is saved per-user. Without filtering by `user_id`, this query will raise a `MultipleResultsFound` exception as soon as a second user configures an account for the same role/environment on UAT.

## Conclusion

**Confidence:** High

The UI shows the account is saved because the UI queries correctly by `user_id`. However, when the backend (Jack/Sarah) attempts to use it, the headless browser login fails (due to UAT environmental restrictions like network/firewall/headless-blocking). Because the backend swallows the `BrowserError`, it falsely concludes the account doesn't exist and outputs a misleading error. 
(There is also a latent bug that will crash the login as soon as a second user is added to UAT).

## Recommended Next Steps

### Fix direction

1. **Fix the Latent Bug:** Add `TestAccountCredential.user_id == user_id` to the query in `src/ai_qa/sessions/auto_login.py`.
2. **Fix the UX Error Swallowing:** Update `Jack` and `Sarah` to pass `raise_on_failure=True` to `resolve_or_generate_storage_state`. Update Jack's error handling to catch `BrowserError` and `ConfigError` separately so he outputs the *real* error (e.g. "Login timeout") instead of falsely claiming the account is missing. 
You can use the `bmad-quick-dev` skill to apply these fixes.
