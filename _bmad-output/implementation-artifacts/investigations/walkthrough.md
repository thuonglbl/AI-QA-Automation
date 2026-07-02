# Walkthrough: Microsoft Entra Passkey Bypass

This document summarizes the final resolution for the Microsoft Entra login timeouts.

## The Problem
Playwright was timing out after 30 seconds on `login.microsoft.com`. By disabling headless mode, we discovered that Microsoft Entra was triggering a native OS "Sign in with Passkey" (Windows Hello/PIN) popup. Since Playwright cannot interact with native OS dialogs, the automation was permanently blocked waiting for user input.

## The Solution
We implemented a JavaScript injection to trick Microsoft into thinking the browser does not support Passkeys.

### Changes Made
- **Disabled Passkeys:** Added an initialization script (`context.add_init_script`) to Playwright that deletes the `window.PublicKeyCredential` API before the page loads. This forces Microsoft Entra to skip the Passkey prompt and default to standard Password authentication.
- **Robust Submissions:** Upgraded the email and password submit actions to use `.press("Enter")` instead of relying on CSS selectors to find and click the "Sign in" button.
- **Cleaned Up Debug Code:** Reverted `headless=False` back to `headless=True` and removed the debug screenshot capture so the bot can run silently on the server.

## Verification
- Successfully tested locally. The bot now correctly skips the Passkey screen, enters the password, and reaches the authenticated application state.
- Ready to be committed and deployed to UAT.
