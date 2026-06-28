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
  captured: SessionStatus[];
}

/**
 * Upload a client-captured Playwright `storageState` blob (UAT path). The tester captures
 * the blob on their own machine and uploads it over authenticated HTTPS, because the remote
 * backend cannot reach the laptop's browser over CDP.
 */
export interface ImportSessionRequest {
  environment: string;
  role: string;
  auth_method?: string;
  storage_state: Record<string, unknown>;
}

/**
 * A short-lived signed token that authorizes a single client-side session upload to the
 * token-auth import endpoint. Minted per (project, environment, role); the auto-upload helper
 * carries it as a bearer credential. Not a user secret — a one-shot, time-boxed convenience.
 */
export interface ImportTokenResponse {
  token: string;
  expires_in: number;
}

/** Reachability of one configured project environment (no request body; server reads its own envs). */
export interface EnvConnectionStatus {
  name: string;
  url: string;
  reachable: boolean;
  status_code: number | null;
  detail: string;
}
