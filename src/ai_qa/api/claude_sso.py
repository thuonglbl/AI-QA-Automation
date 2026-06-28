"""Claude enterprise SSO login flow (OAuth Authorization-Code + PKCE).

This router implements the "Login SSO" provider option for Alice. The user
clicks "Login SSO", a browser tab opens an identity-provider (IdP) login page,
they authenticate with their company email + password, and on success the tool
stores the resulting token as the per-user ``claude_sso`` secret — never
returned to the frontend.

Two modes, switched by ``settings.claude_sso_authorize_url``:

* **Mock IdP (default, empty url)** — the backend serves its own ``/authorize``
  login form. Used for local dev and E2E (Playwright fills the form with
  ``TEST_CLAUDE_SSO_EMAIL`` / ``TEST_CLAUDE_SSO_PASSWORD``). After a successful
  mock login the server stores the configured enterprise license key
  (``claude_sso_enterprise_api_key``, falling back to ``ANTHROPIC_API_KEY``) so
  the pipeline can make real Claude calls.
* **Real OAuth (url set)** — ``/start`` builds the real authorization URL
  (PKCE S256); the IdP redirects back to ``/callback`` with a ``code`` which is
  exchanged for an access token at ``claude_sso_token_url``.

Flow state (PKCE verifier, owning user, authenticated flag) is kept in a
short-TTL in-memory store keyed by an opaque ``state``. This is process-local;
it is sufficient for the single-worker dev/E2E server. A multi-worker
deployment of the real-OAuth path would move this to a shared store.
"""

import base64
import hashlib
import logging
import secrets as _secrets
import time

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user
from ai_qa.config import AppSettings
from ai_qa.db.models import User
from ai_qa.secrets import SECRET_TYPE_CLAUDE_SSO
from ai_qa.secrets.service import set_user_secret

logger = logging.getLogger(__name__)

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)

router = APIRouter(prefix="/auth/claude-sso", tags=["claude-sso"])

# Flow state TTL: an SSO login must complete within this window.
_FLOW_TTL_SECONDS = 600
# How long a completed flow remains pollable by /status before it is reaped.
_DONE_TTL_SECONDS = 120


class _SsoFlow:
    """In-flight SSO login state keyed by an opaque ``state`` token."""

    __slots__ = ("user_id", "code_verifier", "created_at", "authenticated")

    def __init__(self, user_id: object, code_verifier: str) -> None:
        self.user_id = user_id
        self.code_verifier = code_verifier
        self.created_at = time.time()
        self.authenticated = False


_FLOWS: dict[str, _SsoFlow] = {}


def _reap_expired() -> None:
    """Drop flows older than their TTL so the store cannot grow unbounded."""
    now = time.time()
    stale = [
        state
        for state, flow in _FLOWS.items()
        if now - flow.created_at > (_DONE_TTL_SECONDS if flow.authenticated else _FLOW_TTL_SECONDS)
    ]
    for state in stale:
        _FLOWS.pop(state, None)


def _pkce_pair() -> tuple[str, str]:
    """Return a (code_verifier, code_challenge) PKCE pair using S256."""
    verifier = base64.urlsafe_b64encode(_secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _settings(request: Request) -> AppSettings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, AppSettings):
        return settings
    return AppSettings()


def _resolved_token(settings: AppSettings) -> str:
    """Resolve the credential to store after a successful mock login.

    Uses the server-side enterprise license key, falling back to the standard
    ANTHROPIC_API_KEY env so a local dev with that set gets a working demo.
    """
    import os

    return (settings.claude_sso_enterprise_api_key or os.getenv("ANTHROPIC_API_KEY", "")).strip()


class SsoStartResponse(BaseModel):
    """Response for POST /start — the URL the frontend opens in a new tab."""

    authorize_url: str
    state: str
    mode: str  # "mock" | "oauth"


class SsoStatusResponse(BaseModel):
    """Response for GET /status — whether the SSO login has completed."""

    authenticated: bool


@router.post("/start", response_model=SsoStartResponse)
async def start_sso(
    request: Request,
    current_user: User = CurrentUserDependency,
) -> SsoStartResponse:
    """Begin an SSO login for the authenticated user.

    Creates a PKCE-protected flow and returns the authorize URL the frontend
    opens in a new browser tab. In mock mode the URL points at this backend's
    built-in login page; in real-OAuth mode it points at the configured IdP.
    """
    _reap_expired()
    settings = _settings(request)
    verifier, challenge = _pkce_pair()
    state = _secrets.token_urlsafe(24)
    _FLOWS[state] = _SsoFlow(user_id=current_user.id, code_verifier=verifier)

    if settings.claude_sso_authorize_url:
        # Real-OAuth mode: an ABSOLUTE external IdP URL the browser opens directly.
        redirect_uri = (
            settings.claude_sso_redirect_uri
            or f"{str(request.base_url).rstrip('/')}/api/auth/claude-sso/callback"
        )
        query = httpx.QueryParams(
            {
                "response_type": "code",
                "client_id": settings.claude_sso_client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "user:inference",
            }
        )
        authorize_url = f"{settings.claude_sso_authorize_url}?{query}"
        return SsoStartResponse(authorize_url=authorize_url, state=state, mode="oauth")

    # Mock mode: a ROOT-RELATIVE path. The frontend opens it against its own origin
    # so the dev Vite proxy forwards it to the backend WITH the app session cookie
    # (the cookie lives on the frontend origin, not the backend's). In production
    # the SPA and API share an origin, so a relative path is correct there too.
    authorize_url = f"/api/auth/claude-sso/authorize?state={state}"
    return SsoStartResponse(authorize_url=authorize_url, state=state, mode="mock")


@router.get("/authorize", response_class=HTMLResponse)
async def mock_authorize(
    request: Request,
    state: str,
    current_user: User = CurrentUserDependency,
) -> HTMLResponse:
    """Render the built-in mock IdP login page (dev/E2E only).

    Real-OAuth deployments never reach this endpoint — the authorize URL points
    at the external IdP instead.
    """
    settings = _settings(request)
    if settings.claude_sso_authorize_url:
        raise HTTPException(status_code=404, detail="Mock IdP disabled (real OAuth configured)")
    flow = _FLOWS.get(state)
    if flow is None or flow.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Unknown or expired SSO state")

    domain_hint = (
        f"Use a @{settings.claude_sso_allowed_email_domain} email."
        if settings.claude_sso_allowed_email_domain
        else "Sign in with your company account."
    )
    # Minimal, self-contained login page. data-testid hooks drive the E2E spec.
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Company SSO — Sign in to Claude</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#f1f5f9;margin:0;display:flex;
   min-height:100vh;align-items:center;justify-content:center}}
 .card{{background:#fff;padding:32px;border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.08);
   width:360px}}
 h1{{font-size:18px;margin:0 0 4px}} p{{color:#64748b;font-size:13px;margin:0 0 20px}}
 label{{display:block;font-size:12px;color:#334155;margin:12px 0 4px}}
 input{{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #e2e8f0;
   border-radius:8px;font-size:14px}}
 button{{margin-top:20px;width:100%;padding:11px;border:0;border-radius:8px;background:#2563eb;
   color:#fff;font-size:14px;font-weight:600;cursor:pointer}}
 .org{{font-size:12px;color:#94a3b8;margin-top:16px;text-align:center}}
</style></head>
<body>
 <form class="card" method="post" action="/api/auth/claude-sso/callback" data-testid="sso-form">
   <h1>Sign in with SSO</h1>
   <p>{domain_hint}</p>
   <input type="hidden" name="state" value="{state}">
   <label for="email">Company email</label>
   <input id="email" name="email" type="email" autocomplete="username"
     placeholder="you@company.com" data-testid="sso-email" required>
   <label for="password">Password</label>
   <input id="password" name="password" type="password" autocomplete="current-password"
     placeholder="Password" data-testid="sso-password" required>
   <button type="submit" data-testid="sso-submit">Sign in</button>
   <div class="org">CORP Information Technology Vietnam · Claude Team</div>
 </form>
</body></html>"""
    return HTMLResponse(content=html)


@router.post("/callback", response_class=HTMLResponse)
async def mock_callback(
    request: Request,
    state: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> HTMLResponse:
    """Handle the mock IdP login submission (dev/E2E only).

    Validates the form, stores the enterprise credential as the user's
    ``claude_sso`` secret, and marks the flow authenticated so the SPA's
    ``/status`` poll resolves.
    """
    settings = _settings(request)
    if settings.claude_sso_authorize_url:
        raise HTTPException(status_code=404, detail="Mock IdP disabled (real OAuth configured)")

    flow = _FLOWS.get(state)
    if flow is None or flow.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Unknown or expired SSO state")

    email_norm = email.strip().lower()
    domain = settings.claude_sso_allowed_email_domain.strip().lower()
    if not email_norm or not password.strip():
        return _sso_result_page("Email and password are required.", success=False)
    if domain and not email_norm.endswith("@" + domain):
        return _sso_result_page(f"Only @{domain} accounts are allowed.", success=False)

    token = _resolved_token(settings)
    if token:
        # Store the enterprise credential as the user's claude_sso secret. The
        # email/password are the login gesture only and are never persisted.
        set_user_secret(db, current_user.id, SECRET_TYPE_CLAUDE_SSO, token)
        db.commit()
    else:
        logger.warning(
            "Claude SSO login succeeded for user %s but no enterprise key is configured "
            "(set CLAUDE_SSO_ENTERPRISE_API_KEY); pipeline calls will report not-configured.",
            current_user.id,
        )

    flow.authenticated = True
    return _sso_result_page("Login successful — you can close this tab.", success=True)


@router.get("/callback", response_class=HTMLResponse)
async def oauth_callback(
    request: Request,
    state: str,
    code: str | None = None,
    error: str | None = None,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> HTMLResponse:
    """Handle the real-OAuth IdP redirect (``?code&state``) and exchange the code.

    Only reached when ``claude_sso_authorize_url`` is configured.
    """
    settings = _settings(request)
    if not settings.claude_sso_authorize_url:
        raise HTTPException(status_code=404, detail="Real OAuth not configured")
    flow = _FLOWS.get(state)
    if flow is None or flow.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Unknown or expired SSO state")
    if error or not code:
        return _sso_result_page("SSO login was cancelled or failed.", success=False)

    redirect_uri = (
        settings.claude_sso_redirect_uri
        or f"{str(request.base_url).rstrip('/')}/api/auth/claude-sso/callback"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                settings.claude_sso_token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": settings.claude_sso_client_id,
                    "code_verifier": flow.code_verifier,
                },
            )
        body = resp.json() if resp.status_code == 200 else {}
        access_token = str(body.get("access_token") or "").strip()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Claude SSO token exchange failed: %s", type(exc).__name__)
        access_token = ""

    if not access_token:
        return _sso_result_page("Could not complete SSO sign-in. Please try again.", success=False)

    set_user_secret(db, current_user.id, SECRET_TYPE_CLAUDE_SSO, access_token)
    db.commit()
    flow.authenticated = True
    return _sso_result_page("Login successful — you can close this tab.", success=True)


@router.get("/status", response_model=SsoStatusResponse)
async def sso_status(
    state: str,
    current_user: User = CurrentUserDependency,
) -> SsoStatusResponse:
    """Poll whether the SSO login for ``state`` has completed for this user."""
    flow = _FLOWS.get(state)
    authenticated = bool(flow and flow.user_id == current_user.id and flow.authenticated)
    return SsoStatusResponse(authenticated=authenticated)


def _sso_result_page(message: str, *, success: bool) -> HTMLResponse:
    """Render the post-login result page shown in the popup tab."""
    color = "#16a34a" if success else "#dc2626"
    icon = "✓" if success else "✕"
    testid = "sso-success" if success else "sso-error"
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SSO</title>
<style>body{{font-family:system-ui,sans-serif;background:#f1f5f9;margin:0;display:flex;
 min-height:100vh;align-items:center;justify-content:center}}
 .card{{background:#fff;padding:32px 40px;border-radius:16px;text-align:center;
   box-shadow:0 8px 30px rgba(0,0,0,.08)}}
 .icon{{font-size:32px;color:{color}}} p{{color:#334155;margin-top:12px}}</style></head>
<body><div class="card" data-testid="{testid}">
 <div class="icon">{icon}</div><p>{message}</p></div>
<script>setTimeout(function(){{window.close()}}, 1200);</script>
</body></html>"""
    return HTMLResponse(content=html)


__all__ = ["router"]
