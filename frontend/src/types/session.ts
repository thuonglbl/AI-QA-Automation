/**
 * Per-user captured browser-session types (project-scoped). Full-stack sync with the
 * sessions API (`src/ai_qa/api/sessions.py`). The session blob itself is NEVER sent to the
 * client — only this non-secret status (timestamps, auth method, cookie count).
 */
import type { ProjectEnvironment } from "@/types/project";

/** How a captured session was obtained (mirrors the backend AUTH_METHODS). */
export type SessionAuthMethod = "SSO_MANUAL" | "PASSWORD" | "API_TOKEN" | "SSO_TOTP";

/** Non-secret status of one captured session. */
export interface SessionStatus {
  environment: string;
  role: string;
  auth_method: string;
  captured_at: string;
  expires_at: string | null;
  last_validated_at: string | null;
  cookie_count: number;
}

/** The project's (environment × role) matrix + the current user's captured sessions. */
export interface SessionMatrix {
  environments: ProjectEnvironment[];
  app_roles: string[];
  /** "SSO" (manual debug-browser capture) or "PASSWORD" (backend auto-login). */
  login_type: string;
  captured: SessionStatus[];
}

/** Capture from a user-launched debug browser over CDP (SSO / manual). */
export interface CaptureSessionRequest {
  environment: string;
  role: string;
  auth_method?: string;
  cdp_url?: string;
}

/** Backend-driven login for a PASSWORD project's (environment, role). */
export interface AutoCaptureSessionRequest {
  environment: string;
  role: string;
  chrome_path: string;
  headless?: boolean;
}
