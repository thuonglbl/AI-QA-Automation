# Case File: sarah-test-credentials

## Hand-off Brief
The test credentials feature currently stores passwords globally at the project level, violating security policies. Furthermore, the UI misleadingly reports "Not logged in" for these credentials because the frontend only checks for manually captured sessions, ignoring auto-login credentials until execution time.

## Case Info
- **Status**: Concluded
- **Scope**: `TestAccountCredential` storage, `listSessions` endpoint, and `auto_login.py` in `ai_qa`.
- **Time Window**: N/A

## Problem Statement
The user reported that credentials entered in the Project Admin dashboard are not retrieved by Sarah (UI shows "Not logged in"). Additionally, the current design violates security by storing user passwords centrally, lacks per-user secret storage, and doesn't explicitly handle SSO vs. Username/Password differences.

## Evidence Inventory
- **Confirmed**: `TestAccountCredential` (in `src/ai_qa/db/models.py`) stores `username` and `password` globally per project. (Violates security policy 1 & 2).
- **Confirmed**: `list_sessions` in `src/ai_qa/api/sessions.py` only lists manually `captured_sessions` for the user, returning nothing for auto-login credentials. This causes the UI in `SarahInputsForm.tsx` to display "Not logged in".
- **Confirmed**: `sarah.py` uses `resolve_or_generate_storage_state` (in `src/ai_qa/sessions/auto_login.py`) which DOES retrieve the `TestAccountCredential` and attempts an automated browser login (via `src/ai_qa/browser/login.py`) if a manual session is not found.
- **Confirmed**: The automated login uses `browser-use` with a prompt to handle "third-party login", but the success of SSO (like for PT Tool) depends heavily on the model and the UI flow.

## Timeline / Causality
1. Project Admin enters credentials. Stored in `TestAccountCredential`.
2. User opens Sarah UI. `list_sessions` is called. It checks `captured_sessions` table, finds nothing. UI shows "Not logged in".
3. User runs Sarah. Sarah attempts auto-login using the Project Admin's stored credentials.
4. If it's an SSO app (PT Tool), the generic browser-use prompt tries to handle it, but it may fail or time out.

## Resolution
The root cause of the "Not logged in" UI is a disconnect between the frontend session check (`list_sessions`) and the backend auto-login capability. The deeper issue is a confirmed architectural design flaw: passwords should not be stored by Project Admins. 

## Final Conclusion
**Confidence**: High
The investigation confirms the user's design and security concerns. The current implementation stores passwords globally and fails to reflect auto-login readiness in the UI. 

## Fix Direction
1. **Security/Storage**: Migrate `TestAccountCredential` to a per-user secret store. Remove it from the Project Admin dashboard.
2. **UI Updates**: Add a button for users to input their own test accounts directly in the Sarah/Test Case UI.
3. **SSO vs Standard**: Differentiate login types in the schema (e.g., `login_type: "sso" | "standard"`) to improve browser automation reliability or prompt the user for manual capture if SSO cannot be automated safely.

## Next Steps
- Trivial fix: N/A
- Scope/plan adjustment: Use `bmad-correct-course` to update the architecture and PRD for test credentials.
- Tracked story: Use `bmad-create-story` to plan the implementation of user-owned test secrets.
