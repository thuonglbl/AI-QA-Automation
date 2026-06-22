import { apiFetch } from "@/lib/api";
import type {
  AutoCaptureSessionRequest,
  CaptureSessionRequest,
  SessionMatrix,
  SessionStatus,
} from "@/types/session";

/** The project's env×role matrix + the current user's captured sessions. */
export function listSessions(projectId: string): Promise<SessionMatrix> {
  return apiFetch<SessionMatrix>(`/projects/${encodeURIComponent(projectId)}/sessions`);
}

/** Capture the current user's session from a debug browser over CDP (SSO / manual). */
export function captureSession(
  projectId: string,
  request: CaptureSessionRequest,
): Promise<SessionStatus> {
  return apiFetch<SessionStatus>(
    `/projects/${encodeURIComponent(projectId)}/sessions/capture`,
    { method: "POST", body: JSON.stringify(request) },
  );
}

/** Backend-drive the login for a PASSWORD project and save this user's session. */
export function autoCaptureSession(
  projectId: string,
  request: AutoCaptureSessionRequest,
): Promise<SessionStatus> {
  return apiFetch<SessionStatus>(
    `/projects/${encodeURIComponent(projectId)}/sessions/auto-capture`,
    { method: "POST", body: JSON.stringify(request) },
  );
}

/** Delete the current user's captured session for (environment, role). */
export function deleteSession(
  projectId: string,
  environment: string,
  role: string,
): Promise<void> {
  const query = new URLSearchParams({ environment, role }).toString();
  return apiFetch<void>(
    `/projects/${encodeURIComponent(projectId)}/sessions?${query}`,
    { method: "DELETE" },
  );
}
