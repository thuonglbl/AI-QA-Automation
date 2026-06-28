"""Azure Entra ID OIDC user-login router (SSO-first authentication, Epic 23).

A single "Sign in with SSO" entry point. Three modes behind one validation
contract (see ``_bmad-output/planning-artifacts/design-sso-first-auth-spike-2026-06-25.md``):

* **real (topology A)** — ``msal`` confidential-client code->token exchange +
  ``python-jose`` ID-token validation against the tenant JWKS. Backend egress to
  ``login.microsoftonline.com`` (needs an IT proxy on air-gapped UAT).
* **bundled-JWKS** — same as real but validate against ``azure_sso_jwks`` so the
  backend never fetches keys (the topology-B validation half).
* **mock IdP (dev/CI/E2E)** — when the tenant/client/secret triple is empty the
  router serves a built-in login form that mints an app-signed token. No
  Microsoft, no network. Mirrors ``claude_sso.py``.

Scope of THIS story (23.2): log in a user whose ``User`` row **already exists**
(matched by email). First-login auto-provisioning + Azure app-role -> platform-role
mapping is story 23.3, which extends ``_complete_login`` below. Local password
login (``/auth/login``) coexists until story 23.6 removes it.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.service import (
    PROJECT_ADMIN_ROLE,
    STANDARD_ROLE,
    get_user_by_email,
    map_app_roles,
    normalize_email,
    primary_role,
)
from ai_qa.config import AppSettings
from ai_qa.db.models import ProjectMembership, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/sso", tags=["sso"])

DbSessionDependency = Depends(get_db_session_dependency)

# In-flight login state keyed by an opaque ``state`` token. Process-local (single
# worker dev/E2E). A multi-worker real-OAuth deployment would move this to a shared
# store; the mock flow does not need one.
_FLOW_TTL_SECONDS = 600
_RESERVED_SCOPES = {"openid", "profile", "email", "offline_access"}


class _Flow:
    """Transient per-login state (PKCE/msal flow dict + creation time)."""

    __slots__ = ("data", "created_at")

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.created_at = time.time()


_FLOWS: dict[str, _Flow] = {}


def _reap_expired() -> None:
    now = time.time()
    stale = [s for s, flow in _FLOWS.items() if now - flow.created_at > _FLOW_TTL_SECONDS]
    for state in stale:
        _FLOWS.pop(state, None)


def _settings(request: Request) -> AppSettings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, AppSettings):
        return settings
    return AppSettings()


def _is_real_mode(settings: AppSettings) -> bool:
    """Real Entra mode requires the confidential-client triple; else mock IdP."""
    return bool(
        settings.azure_sso_tenant_id
        and settings.azure_sso_client_id
        and settings.azure_sso_client_secret
    )


def _authority(settings: AppSettings) -> str:
    return settings.azure_sso_authority.replace("{tenant}", settings.azure_sso_tenant_id)


def _resolve_redirect_uri(settings: AppSettings, request: Request) -> str:
    if settings.azure_sso_redirect_uri:
        return settings.azure_sso_redirect_uri
    return f"{str(request.base_url).rstrip('/')}/auth/sso/callback"


def _graph_scopes(settings: AppSettings) -> list[str]:
    """Scopes for msal (reserved OIDC scopes are added by msal automatically)."""
    return [s for s in settings.azure_sso_scopes.split() if s.lower() not in _RESERVED_SCOPES]


# --- claim extraction -------------------------------------------------------


def _claim_email(claims: dict[str, Any]) -> str:
    raw = claims.get("preferred_username") or claims.get("upn") or claims.get("email") or ""
    return normalize_email(str(raw)) if raw else ""


def _claim_name(claims: dict[str, Any]) -> str:
    return str(claims.get("name") or "").strip()


# --- session / cookie -------------------------------------------------------


def _session_payload_from_claims(user: User, claims: dict[str, Any]) -> dict[str, Any]:
    """Build the session dict for an authenticated user from validated claims.

    Identity (name/given/family/groups) comes from the token; the platform
    ``role``/``user_id``/``timezone`` come from the matched ``User`` row.
    """
    return {
        "user_id": str(user.id),
        "email": user.email,
        "name": _claim_name(claims) or user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "timezone": user.timezone,
        "given_name": claims.get("given_name"),
        "family_name": claims.get("family_name"),
        "groups": claims.get("groups") or [],
    }


def _login_redirect(session_manager: SessionManager, token: str) -> RedirectResponse:
    """Redirect to the SPA root with the app session cookie set (303 POST->GET safe)."""
    response = RedirectResponse(url="/", status_code=303)
    cookie_settings = session_manager.get_cookie_settings()
    cookie_settings.update({"samesite": "lax", "domain": None})
    response.set_cookie(value=token, **cookie_settings)
    return response


def _error_redirect(code: str) -> RedirectResponse:
    """Redirect back to the SPA login screen with a safe error code (no secrets)."""
    return RedirectResponse(url=f"/?sso_error={code}", status_code=303)


# --- user matching / provisioning / role derivation (23.3) ------------------


def _claim_oid(claims: dict[str, Any]) -> str | None:
    oid = str(claims.get("oid") or "").strip()
    return oid or None


def _match_user(db: Session, oid: str | None, email: str) -> User | None:
    """Match by the stable Entra ``oid`` first, then by normalized email."""
    if oid:
        matched = db.execute(select(User).where(User.azure_oid == oid)).scalar_one_or_none()
        if matched is not None:
            return matched
    return get_user_by_email(db, email)


def _domain_allowed(settings: AppSettings, email: str) -> bool:
    domain = settings.azure_sso_allowed_email_domain.strip().lower()
    return not domain or email.endswith("@" + domain)


def _effective_roles(db: Session, user: User, azure_roles: set[str]) -> set[str]:
    """Token-derived roles UNION a membership-conferred ``project_admin``.

    An in-app ``ProjectMembership(role="project_admin")`` confers the platform
    project_admin role even with no Azure ``project-admin`` grant (Thuong 2026-06-25),
    so a pre-assigned project-admin works on their first login. The platform ``admin``
    role comes only from Azure.
    """
    roles = set(azure_roles)
    has_pa_membership = (
        db.execute(
            select(ProjectMembership.id)
            .where(
                ProjectMembership.user_id == user.id,
                ProjectMembership.role == PROJECT_ADMIN_ROLE,
            )
            .limit(1)
        ).first()
        is not None
    )
    if has_pa_membership:
        roles.add(PROJECT_ADMIN_ROLE)
    return roles or {STANDARD_ROLE}


def _provision_user(
    db: Session, claims: dict[str, Any], email: str, oid: str | None, azure_roles: set[str]
) -> User:
    """Create an identity-only User on first SSO login (no password)."""
    user = User(
        email=email,
        display_name=_claim_name(claims) or email.split("@", 1)[0],
        azure_oid=oid,
        role=primary_role(azure_roles),
        is_active=True,
        timezone="UTC",
    )
    db.add(user)
    db.flush()  # assign PK without committing; commit happens after role is finalized
    return user


def _resync_identity(user: User, claims: dict[str, Any], oid: str | None) -> None:
    """Refresh identity fields owned by Azure. Never touch memberships/secrets/timezone."""
    name = _claim_name(claims)
    if name:
        user.display_name = name
    if oid and not user.azure_oid:
        user.azure_oid = oid


def _complete_login(
    db: Session,
    settings: AppSettings,
    session_manager: SessionManager,
    claims: dict[str, Any],
    access_token: str | None = None,
) -> RedirectResponse:
    """Match-or-provision the user, derive role(s), and mint the app session.

    Identity + derived role(s) are re-synced every login; project memberships,
    per-user secrets, and timezone are preserved (Azure does not own them).
    When ``access_token`` is present (real Entra mode), best-effort fetches the
    Azure avatar (story 23.4) — never blocks login.
    """
    email = _claim_email(claims)
    if not email:
        logger.warning("SSO callback produced no usable email claim")
        return _error_redirect("invalid_token")

    oid = _claim_oid(claims)
    azure_roles = map_app_roles(claims.get("roles"))
    provisioning_on = settings.azure_sso_enabled and settings.azure_sso_auto_provision

    try:
        user = _match_user(db, oid, email)
        if user is None:
            if not provisioning_on:
                logger.info("SSO login for unprovisioned email (provisioning off)")
                return _error_redirect("not_provisioned")
            if not _domain_allowed(settings, email):
                return _error_redirect("domain_not_allowed")
            user = _provision_user(db, claims, email, oid, azure_roles)
        elif not user.is_active:
            return _error_redirect("not_provisioned")
        else:
            _resync_identity(user, claims, oid)

        # Best-effort Azure avatar (23.4) — never blocks login; air-gapped UAT (no
        # Graph egress) simply leaves it null and the FE shows initials.
        if access_token and settings.azure_sso_enabled:
            avatar = _fetch_graph_avatar(access_token)
            if avatar:
                user.avatar = avatar

        # Effective role set + derived primary persisted to User.role so the existing
        # single-role surface (rbac/admin/projects/App.tsx) keeps working. Membership
        # confers project_admin and must never be downgraded below it.
        effective = _effective_roles(db, user, azure_roles)
        user.role = primary_role(effective)
        db.commit()
        db.refresh(user)
    except Exception as exc:  # never leave a half-created user / never 500 the login
        db.rollback()
        logger.warning("SSO provisioning/re-sync failed: %s", type(exc).__name__)
        return _error_redirect("provision_failed")

    payload = _session_payload_from_claims(user, claims)
    payload["roles"] = sorted(effective)
    session = session_manager.create_session(payload)
    token = session_manager.encode_session(session)
    logger.info("SSO login succeeded for user %s (roles=%s)", user.id, sorted(effective))
    return _login_redirect(session_manager, token)


# --- real-mode (topology A) helpers -----------------------------------------


def _build_msal_app(settings: AppSettings) -> Any:
    import msal

    return msal.ConfidentialClientApplication(
        settings.azure_sso_client_id,
        authority=_authority(settings),
        client_credential=settings.azure_sso_client_secret,
    )


def _validate_with_jwks(settings: AppSettings, id_token: str) -> dict[str, Any] | None:
    """Validate an ID token against the tenant JWKS (or a bundled JWKS).

    Used for the bundled-JWKS / browser-token path. The real msal exchange path
    already validates the token cryptographically; this keeps a single explicit
    validation contract (issuer/audience/exp/signature) available either way.
    """
    import json

    import httpx
    from jose import jwt

    try:
        if settings.azure_sso_jwks:
            jwks = json.loads(settings.azure_sso_jwks)
        else:
            url = f"{_authority(settings)}/discovery/v2.0/keys"
            resp = httpx.get(url, timeout=15.0)
            resp.raise_for_status()
            jwks = resp.json()
        claims: dict[str, Any] = jwt.decode(
            id_token,
            jwks,
            algorithms=["RS256"],
            audience=settings.azure_sso_client_id,
            options={"verify_at_hash": False},
        )
        return claims
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("SSO JWKS validation failed: %s", type(exc).__name__)
        return None
    except Exception as exc:  # jose raises JWTError subclasses; never leak details
        logger.warning("SSO ID-token validation rejected: %s", type(exc).__name__)
        return None


# --- avatar (23.4) ----------------------------------------------------------

# Microsoft Graph photo endpoint + a hard size guard so a surprise large blob can
# never bloat the row / response. ~512KB of raw photo is far more than a thumbnail.
_GRAPH_PHOTO_URL = "https://graph.microsoft.com/v1.0/me/photo/$value"
_MAX_AVATAR_BYTES = 512 * 1024


def _fetch_graph_avatar(access_token: str) -> str | None:
    """Best-effort fetch of the Graph profile photo, returned as a ``data:`` URI.

    Backend egress to ``graph.microsoft.com`` (blocked on air-gapped UAT). Any
    failure/egress-block/oversize returns None so login degrades to initials. The
    bytes are never logged.
    """
    import base64

    import httpx

    try:
        resp = httpx.get(
            _GRAPH_PHOTO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None
        content = resp.content
        if not content or len(content) > _MAX_AVATAR_BYTES:
            return None
        mime = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except httpx.HTTPError as exc:
        logger.info("Graph avatar fetch failed: %s", type(exc).__name__)
        return None


# --- routes -----------------------------------------------------------------


@router.get("/login")
async def sso_login(request: Request) -> RedirectResponse:
    """Begin the SSO login. Redirects to Entra (real) or the mock IdP form."""
    _reap_expired()
    settings = _settings(request)

    if _is_real_mode(settings):
        redirect_uri = _resolve_redirect_uri(settings, request)
        try:
            msal_app = _build_msal_app(settings)
            # Force the account picker so a cached PERSONAL Microsoft account in the
            # browser is never used silently, and bias home-realm discovery to the
            # corporate domain so the user lands on the company IdP, not login.live.com.
            auth_kwargs: dict[str, Any] = {
                "redirect_uri": redirect_uri,
                "prompt": "select_account",
            }
            allowed_domain = settings.azure_sso_allowed_email_domain.strip()
            if allowed_domain:
                auth_kwargs["domain_hint"] = allowed_domain
            flow = msal_app.initiate_auth_code_flow(_graph_scopes(settings), **auth_kwargs)
        except Exception as exc:  # network/config failure must not 500 the login
            logger.warning("SSO authorize-url build failed: %s", type(exc).__name__)
            return _error_redirect("idp_unreachable")
        state = str(flow.get("state") or "")
        if not state or "auth_uri" not in flow:
            return _error_redirect("idp_unreachable")
        _FLOWS[state] = _Flow(flow)
        return RedirectResponse(url=flow["auth_uri"], status_code=303)

    # Mock IdP mode: redirect to the built-in login form (root-relative so the dev
    # Vite proxy forwards it to the backend with the app-origin cookie).
    import secrets as _secrets

    state = _secrets.token_urlsafe(24)
    _FLOWS[state] = _Flow({"mock": True})
    return RedirectResponse(
        url=f"/auth/sso/authorize?{urlencode({'state': state})}", status_code=303
    )


@router.get("/authorize", response_class=HTMLResponse)
async def sso_mock_authorize(request: Request, state: str) -> HTMLResponse:
    """Render the built-in mock IdP login form (dev/CI/E2E only)."""
    settings = _settings(request)
    if _is_real_mode(settings):
        return HTMLResponse(status_code=404, content="Mock IdP disabled (real Entra configured)")
    flow = _FLOWS.get(state)
    if flow is None or not flow.data.get("mock"):
        return HTMLResponse(status_code=400, content="Unknown or expired SSO state")

    domain = settings.azure_sso_allowed_email_domain.strip()
    domain_hint = f"Use a @{domain} email." if domain else "Sign in with your corporate account."
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in with SSO</title>
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
 <form class="card" method="post" action="/auth/sso/callback" data-testid="sso-form">
   <h1>Sign in with SSO</h1>
   <p>{domain_hint}</p>
   <input type="hidden" name="state" value="{state}">
   <label for="email">Corporate email</label>
   <input id="email" name="email" type="email" autocomplete="username"
     placeholder="you@company.com" data-testid="sso-email" required>
   <button type="submit" data-testid="sso-submit">Sign in</button>
   <div class="org">CORP · AI QA Automation</div>
 </form>
</body></html>"""
    return HTMLResponse(content=html)


@router.post("/callback")
async def sso_mock_callback(
    request: Request,
    state: str = Form(...),
    email: str = Form(...),
    roles: str = Form(""),
    db: Session = DbSessionDependency,
) -> RedirectResponse:
    """Handle the mock IdP login submission (dev/CI/E2E only).

    ``roles`` is an optional space/comma-separated list of Azure app-role values
    (e.g. ``"admin"`` or ``"project-admin user"``) so dev/E2E can exercise the
    role mapping without a real tenant. Empty => standard (the common case).
    """
    settings = _settings(request)
    if _is_real_mode(settings):
        return _error_redirect("not_found")
    flow = _FLOWS.pop(state, None)
    if flow is None or not flow.data.get("mock"):
        return _error_redirect("state_mismatch")

    email_norm = normalize_email(email)
    if not email_norm:
        return _error_redirect("invalid_token")
    if not _domain_allowed(settings, email_norm):
        return _error_redirect("domain_not_allowed")

    claims = _mock_claims(email_norm, roles)
    session_manager = SessionManager(settings)
    return _complete_login(db, settings, session_manager, claims)


@router.get("/callback")
async def sso_callback(
    request: Request,
    db: Session = DbSessionDependency,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle the real Entra redirect (``?code&state``); exchange + validate."""
    settings = _settings(request)
    session_manager = SessionManager(settings)
    if not _is_real_mode(settings):
        return _error_redirect("not_found")
    if error or not code or not state:
        return _error_redirect("idp_error")
    flow_holder = _FLOWS.pop(state, None)
    if flow_holder is None:
        return _error_redirect("state_mismatch")

    try:
        msal_app = _build_msal_app(settings)
        result = msal_app.acquire_token_by_auth_code_flow(
            flow_holder.data, dict(request.query_params)
        )
    except Exception as exc:  # egress blocked / network / config
        logger.warning("SSO token exchange failed: %s", type(exc).__name__)
        return _error_redirect("idp_unreachable")

    if "error" in result or "id_token_claims" not in result:
        logger.warning("SSO token exchange returned an error")
        return _error_redirect("invalid_token")

    # msal validates the ID token cryptographically during the exchange. When a
    # bundled JWKS is configured (the air-gapped topology-B validation half), also
    # validate explicitly with python-jose so the contract is identical offline.
    claims: dict[str, Any] = result["id_token_claims"]
    if settings.azure_sso_jwks:
        validated = _validate_with_jwks(settings, str(result.get("id_token") or ""))
        if validated is None:
            return _error_redirect("invalid_token")
        claims = validated
    access_token = str(result.get("access_token") or "")
    return _complete_login(db, settings, session_manager, claims, access_token=access_token)


def _mock_claims(email_norm: str, roles: str = "") -> dict[str, Any]:
    """Synthesize ID-token-shaped claims for the mock IdP path.

    ``roles`` (space/comma separated app-role values) becomes the ``roles`` claim
    so the mock flow exercises the same role mapping the real token would.
    """
    local = email_norm.split("@", 1)[0]
    name = local.replace(".", " ").title()
    role_values = [r for r in roles.replace(",", " ").split() if r]
    return {
        "preferred_username": email_norm,
        "email": email_norm,
        "name": name,
        "oid": f"mock-{local}",
        "roles": role_values,
    }


__all__ = ["router"]
