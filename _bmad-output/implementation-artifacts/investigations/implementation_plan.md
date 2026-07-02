# Investigate Local Login Failure

You mentioned the login now fails locally as well, timing out on `login.microsoft.com`. This indicates that Playwright successfully reached Microsoft's login page, entered the email, but then got stuck on a subsequent screen (e.g., password, MFA, or an unexpected prompt) for 30 seconds.

Playwright's `fill()` method handles all special characters (including `#`) perfectly, so the password string itself is not causing a syntax error. The issue is likely that the automated script is either failing to click the "Sign in" button correctly, or Microsoft is showing a screen that the script doesn't know how to handle (like a "More information required" or "Update password" screen).

## Proposed Changes

To figure out exactly what Microsoft is asking for, we will make the browser **visible** locally and improve the reliability of the submit action:

### [MODIFY] [login.py](file:///c:/Users/thuong/source/repos/ai-qa-automation/src/ai_qa/browser/login.py)
1. **Show the Browser:** Change `headless=True` to `headless=False` in `_login_with_playwright`. When you click "Test Login" locally, a real Chrome window will pop up so you can watch exactly what it types and where it gets stuck.
2. **Robust Form Submission:** Change the login steps to use `await input.press("Enter")` instead of trying to find and click the "Sign in" button. Microsoft frequently changes the class and ID of their buttons, but pressing Enter on the password field is universally supported.
3. **Debug Screenshot:** When the 30-second timeout hits, instruct Playwright to save a screenshot of the final stuck screen to the project root (`login_stuck_debug.png`).

## Open Questions
- None. This is a diagnostic step to reveal the hidden Microsoft Entra screen.

## Verification Plan

### Manual Verification
- I will execute these changes.
- You will click **Test Login** on your local machine.
- Watch the browser window that pops up. You will see exactly why Microsoft is refusing the login or what screen it is stuck on.
- Check the root of the project for `login_stuck_debug.png` if it times out.
