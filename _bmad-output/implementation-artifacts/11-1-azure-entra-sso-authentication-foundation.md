# 11-1: Azure Entra ID SSO Authentication Foundation

## Header

```yaml
story_id: 11.1
story_key: 11-1-azure-entra-sso-authentication-foundation
epic: Epic 11 - Azure Entra ID SSO Integration
status: ready-for-dev
created_by: BMad Story Agent
updated_by: BMad Story Agent
created_at: 2026-04-20
updated_at: 2026-04-20
---
story_title: Azure Entra ID SSO Authentication Foundation
epic_title: Azure Entra ID SSO Integration
epic_description: QA engineers authenticate using their existing Azure Entra ID (Azure AD) credentials through the company's SSO infrastructure. This replaces the insecure shared `.env` approach with proper per-user authentication and authorization.
```

## Requirements

### User Story

**As a** QA engineer (Minh),
**I want** to authenticate via Azure Entra ID SSO instead of shared `.env` credentials,
**So that** my API keys and access are isolated and secure per my corporate identity.

### Acceptance Criteria (BDD)

**Scenario 1: Unauthenticated access redirects to login**
```gherkin
Given the FastAPI server is running
When an unauthenticated user accesses any protected endpoint
Then they are redirected to Azure Entra ID login page
```

**Scenario 2: Successful authentication issues JWT token**
```gherkin
Given a user completes Azure Entra ID authentication
When the auth callback is processed
Then a JWT session token is issued with user identity (email, name, groups)
And the token expires after configurable duration (default: 8 hours)
```

**Scenario 3: Authenticated requests have user context**
```gherkin
Given an authenticated user
When they access protected API endpoints
Then their identity is available to the pipeline via request.state.user
And audit logs capture "who" performed each action (NFR9)
```

**Scenario 4: Per-user configuration isolation**
```gherkin
Given the current .env configuration system
When SSO is enabled
Then per-user configuration is stored in isolated location: workspace/users/{user_email}/
And API keys are no longer read from shared .env but from user-specific config
```

**Scenario 5: Frontend SSO integration**
```gherkin
Given the React frontend
When SSO is integrated
Then login page shows "Sign in with Microsoft" button
And post-login, Agent Alice recognizes the user by name
```

### Dependencies

- Epic 2 (FastAPI server foundation) - COMPLETED
- Epic 2 (React frontend) - COMPLETED  
- Epic 9 (Audit logging foundation) - PENDING (soft dependency, can mock)

### Blocks

- Story 6-1: Script Runner Pipeline Stage (requires authenticated user context for audit)
- All future stories requiring user identification in audit logs

## Developer Context

### Critical Architecture Requirements

**Security Requirements (from Epic 11):**
- Use `fastapi-azure-auth` or `msal` library for Azure Entra ID integration
- Token validation against Azure JWKS endpoint
- No shared credentials in `.env` for user-isolated data
- Session middleware with HttpOnly cookies
- CSRF protection for authentication endpoints

**Architecture Pattern (from architecture.md):**
- FastAPI with async endpoints
- WebSocket support for real-time chat
- Pydantic models for all data exchange
- Module dependency rule: `api` → `agents` → `pipelines` → lower layers

### File Structure Requirements

```
src/ai_qa/
├── api/
│   ├── __init__.py
│   ├── server.py          # Update: Add auth middleware
│   ├── routes.py          # Update: Add auth routes
│   ├── websocket.py       # Update: Authenticate WebSocket connections
│   ├── schemas.py         # Update: Add auth-related schemas
│   └── auth/              # NEW: Authentication module
│       ├── __init__.py
│       ├── azure.py       # Azure Entra ID integration
│       ├── middleware.py  # Auth middleware for FastAPI
│       └── session.py     # Session management
├── config.py              # Update: Add Azure auth config
└── models.py              # Update: Add User model

frontend/src/
├── components/
│   └── auth/
│       └── MicrosoftLoginButton.tsx  # NEW
├── hooks/
│   └── useAuth.ts                    # NEW: Auth state management
└── lib/
    └── auth.ts                       # NEW: Auth utilities
```

### Technical Requirements

**Azure Entra ID Integration:**
- Register application in Azure Portal (if not already done)
- Configure redirect URIs: `http://localhost:8000/auth/callback` (dev), production URL
- Required scopes: `openid`, `profile`, `email`, `User.Read`
- Enable ID token issuance

**Backend Implementation:**
1. Add `fastapi-azure-auth` to dependencies
2. Create auth configuration in `config.py`:
   - `azure_tenant_id`
   - `azure_client_id`
   - `azure_client_secret` (for confidential client)
   - `azure_redirect_uri`
3. Implement auth router with endpoints:
   - `GET /auth/login` - Initiate OAuth flow
   - `GET /auth/callback` - Handle Azure callback
   - `POST /auth/logout` - Clear session
   - `GET /auth/me` - Get current user info
4. Create auth middleware to protect routes
5. Update WebSocket endpoint to authenticate connections

**Frontend Implementation:**
1. Create login page with "Sign in with Microsoft" button
2. Implement auth state management (React Context or Zustand)
3. Add auth token storage (HttpOnly cookie handled by backend)
4. Update API client to include credentials
5. Update WebSocket connection to include auth
6. Modify AgentTopBar to show authenticated user name

**User Configuration Isolation:**
- Change workspace structure from:
  ```
  workspace/
  ├── configuration/
  ├── requirements/
  └── ...
  ```
  To:
  ```
  workspace/
  ├── users/
  │   └── {user_email_hash}/
  │       ├── configuration/
  │       ├── requirements/
  │       ├── testcases/
  │       ├── testscripts/
  │       └── report/
  └── shared/          # For truly shared resources if any
  ```
- Update all file path references to include user context
- User email should be hashed (SHA-256) for filesystem safety

### Testing Requirements

**Unit Tests:**
- Token validation logic
- Session creation/expiry
- User model serialization

**Integration Tests:**
- OAuth flow (mock Azure responses)
- Protected route access (authenticated vs unauthenticated)
- WebSocket authentication

**Manual Testing:**
- Actual Azure Entra ID login flow
- Token refresh behavior
- Session timeout handling

### Library Framework Requirements

**Primary:**
- `fastapi-azure-auth` ^6.0 - Azure AD integration for FastAPI
- `python-jose` ^3.3 - JWT handling (if needed beyond fastapi-azure-auth)
- `msal` ^1.28 - Microsoft Authentication Library (alternative)

**Frontend:**
- `@azure/msal-react` ^3.0 - React MSAL integration
- `@azure/msal-browser` ^4.0 - Browser MSAL client

### Migration Requirements

**From Shared `.env` to Per-User Config:**
1. Keep `.env` for server-level config only (MCP server URL, non-user secrets)
2. Remove user-specific config from `.env`:
   - `ANTHROPIC_API_KEY` → move to user config
   - `ON_PREMISES_AI_SERVER_KEY` → move to user config
   - LLM parameters → can remain global or per-user (design decision needed)
3. Create migration path for existing users (one-time import from `.env`)

### Configuration Changes

`.env` changes:
```bash
# Azure Entra ID (NEW)
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret  # If confidential client
AZURE_REDIRECT_URI=http://localhost:8000/auth/callback

# Session (NEW)
SESSION_SECRET_KEY=random-secret-for-signing-cookies
SESSION_EXPIRE_HOURS=8

# Remove or mark as deprecated:
# ANTHROPIC_API_KEY=  # Now per-user
# ON_PREMISES_AI_SERVER_KEY=  # Now per-user
```

### Security Considerations

1. **Token Storage**: Never store tokens in localStorage - use HttpOnly cookies
2. **CSRF Protection**: Implement state parameter in OAuth flow
3. **PKCE**: Use PKCE extension for OAuth (handled by msal)
4. **Token Validation**: Always validate JWT signature against Azure JWKS
5. **Session Security**: Secure, HttpOnly, SameSite=Strict cookies
6. **User Enumeration**: Prevent username enumeration in error messages
7. **Group Claims**: Verify group membership if needed for authorization

### Implementation Sequence

1. **Phase 1**: Backend auth infrastructure
   - Azure AD app registration (or confirm existing)
   - Config updates
   - Auth module with login/callback endpoints
   - Auth middleware

2. **Phase 2**: Frontend auth integration
   - MSAL React setup
   - Login page
   - Auth context/provider
   - Protected route wrapper

3. **Phase 3**: User isolation
   - User-specific workspace paths
   - Config loading from user directories
   - Migration utility (if needed)

4. **Phase 4**: Integration
   - WebSocket auth
   - Audit log user identification
   - Agent Alice personalization

## Project Context Reference

**From architecture.md:**
- FastAPI async server with WebSocket support
- React 18+ frontend with TypeScript
- Module boundaries: `api` depends on `config`, `models`, `agents`
- Pydantic models for all data exchange

**From PRD:**
- Swiss banking/pharma/government clients require enterprise SSO
- Azure Entra ID is standard corporate identity provider
- Security is non-negotiable (NFR6: API keys never committed)
- Audit logging must capture "who" (FR25, NFR9)

## Story Completion Status

```yaml
status: ready-for-dev
completion_notes: |
  Ultimate context engine analysis completed.
  
  This is a BLOCKER story that must be completed before:
  - Story 6-1 (Script Runner) - requires authenticated user for audit
  - All future audit-dependent features
  
  Critical success factors:
  1. Proper Azure Entra ID integration with token validation
  2. Per-user configuration isolation (security requirement)
  3. HttpOnly cookie session management
  4. Frontend auth state management
  
  Developer has all information needed for implementation.
```
