import { API_BASE_PATH, apiFetch } from "@/lib/api";
import type {
  ImportTokenResponse,
  SessionMatrix,
} from "@/types/session";

/** The project's env×role matrix + the current user's captured sessions. */
export function listSessions(projectId: string): Promise<SessionMatrix> {
  return apiFetch<SessionMatrix>(`/projects/${encodeURIComponent(projectId)}/sessions`);
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

/**
 * Mint a short-lived signed upload token for the auto-upload helper. The QA tester downloads
 * a helper pre-configured with this token; the helper captures their logged-in session locally
 * and POSTs it straight to the token-auth import endpoint — no manual file/paste. The token is
 * the auth on that endpoint (typ=session_upload, bound to project+env+role, ~15 min). It is a
 * one-shot convenience credential, never a user secret; if it expires, the tester re-downloads.
 */
export function requestImportToken(
  projectId: string,
  request: { environment: string; role: string },
): Promise<ImportTokenResponse> {
  return apiFetch<ImportTokenResponse>(
    `/projects/${encodeURIComponent(projectId)}/sessions/import-token`,
    { method: "POST", body: JSON.stringify(request) },
  );
}

/**
 * Build the absolute URL of the token-auth import endpoint, matching how `apiFetch` composes
 * request URLs (`API_BASE_PATH` prefix). The helper runs in Node on the tester's machine, so it
 * needs a fully-qualified origin, not a same-origin relative path.
 */
export function importWithTokenUrl(projectId: string): string {
  const base = API_BASE_PATH.startsWith("/") ? API_BASE_PATH : `/${API_BASE_PATH}`;
  return `${location.origin}${base}/projects/${encodeURIComponent(
    projectId,
  )}/sessions/import-with-token`;
}

/** Escape a value for safe embedding inside a Windows batch `set "VAR=..."` assignment. */
function escapeForBatch(value: string): string {
  // Inside quotes, the shell-special chars % and ^ still need escaping; strip CR/LF/quotes
  // (a URL/token/host never legitimately contains them) so a value can't break out of the line.
  return value
    .replace(/[\r\n"]/g, "")
    .replace(/%/g, "%%")
    .replace(/\^/g, "^^")
    .replace(/&/g, "^&");
}

/** Escape a value for safe embedding inside a double-quoted JavaScript string literal. */
function escapeForJs(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/[\r\n]/g, "");
}

/**
 * Fetch the static capture-helper template and inject the auto-upload config at its marker,
 * returning a downloadable Blob. The helper then captures → filters to `cfg.domain` →
 * auto-uploads to `cfg.uploadUrl` with `cfg.token`, falling back to writing session.json on any
 * failure. When the marker is absent (older template) the original file is returned unchanged.
 */
export async function buildConfiguredHelper(
  kind: "cmd" | "mjs",
  cfg: { uploadUrl: string; token: string; domain: string },
): Promise<Blob> {
  const res = await fetch(`${import.meta.env.BASE_URL}capture-session.${kind}`);
  if (!res.ok) {
    throw new Error(`Could not load the capture helper template (HTTP ${res.status}).`);
  }
  const template = await res.text();

  let configured: string;
  if (kind === "cmd") {
    const block =
      `set "AIQA_UPLOAD_URL=${escapeForBatch(cfg.uploadUrl)}"\r\n` +
      `set "AIQA_TOKEN=${escapeForBatch(cfg.token)}"\r\n` +
      `set "AIQA_DOMAIN=${escapeForBatch(cfg.domain)}"`;
    configured = template.replace("rem __AIQA_CONFIG__", block);
  } else {
    const block =
      `process.env.AIQA_UPLOAD_URL = "${escapeForJs(cfg.uploadUrl)}";\n` +
      `process.env.AIQA_TOKEN = "${escapeForJs(cfg.token)}";\n` +
      `process.env.AIQA_DOMAIN = "${escapeForJs(cfg.domain)}";`;
    configured = template.replace("// __AIQA_CONFIG__", block);
  }

  return new Blob([configured], { type: "text/plain" });
}

