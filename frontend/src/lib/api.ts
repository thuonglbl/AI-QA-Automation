export type ApiErrorKind =
  | "auth"
  | "forbidden"
  | "not_found"
  | "validation"
  | "conflict"
  | "network"
  | "server";

export interface ApiRequestOptions extends RequestInit {
  authRoute?: boolean;
  safeMessage?: string;
}

export class ApiError extends Error {
  kind: ApiErrorKind;
  status?: number;
  details?: unknown;

  constructor(
    kind: ApiErrorKind,
    message: string,
    status?: number,
    details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.details = details;
  }
}

export const API_BASE_PATH = import.meta.env.VITE_API_BASE_PATH ?? "/api";

function buildUrl(path: string, authRoute = false): string {
  if (/^https?:\/\//.test(path)) return path;
  if (authRoute)
    return path.startsWith("/auth")
      ? path
      : `/auth${path.startsWith("/") ? path : `/${path}`}`;
  if (path.startsWith(API_BASE_PATH)) return path;
  return `${API_BASE_PATH}${path.startsWith("/") ? path : `/${path}`}`;
}

function safeMessage(kind: ApiErrorKind): string {
  switch (kind) {
    case "auth":
      return "Your session has expired. Please sign in again.";
    case "forbidden":
      return "You do not have access to perform this action.";
    case "not_found":
      return "The requested resource could not be found.";
    case "validation":
      return "Please check the form and try again.";
    case "conflict":
      return "This action conflicts with existing data. Please review and try again.";
    case "network":
      return "Network connection failed. Please try again.";
    default:
      return "Something went wrong. Please try again.";
  }
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return "auth";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 422 || status === 400) return "validation";
  if (status === 409) return "conflict";
  return "server";
}

export async function apiFetch<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const {
    authRoute = false,
    safeMessage: overrideMessage,
    headers,
    ...request
  } = options;
  let token = null;
  try {
    token = localStorage.getItem("aiqa_access_token");
  } catch (_e) {}

  let response: Response;
  try {
    response = await fetch(buildUrl(path, authRoute), {
      ...request,
      credentials: "include",
      headers: {
        ...(request.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
    });
  } catch (error) {
    throw new ApiError(
      "network",
      overrideMessage ?? safeMessage("network"),
      undefined,
      error,
    );
  }

  const contentType = response.headers.get("content-type") ?? "";
  const hasJson = contentType.includes("application/json");
  const payload = hasJson
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");

  if (!response.ok) {
    const kind = kindForStatus(response.status);
    // Only dispatch auth-error for non-auth-route API calls.
    // Auth route calls (login, status, me) returning 401 are expected and should NOT
    // trigger a refresh loop — that would cause infinite recursion.
    if (
      kind === "auth" &&
      !authRoute &&
      !path.includes("/login") &&
      !path.includes("/refresh")
    ) {
      try {
        localStorage.removeItem("aiqa_access_token");
      } catch (_e) {}
      window.dispatchEvent(new Event("auth-error"));
    }
    // For 409/422 the server detail is display-safe and more useful than the generic
    // copy ("Project name already exists", "User already exists", …). Surface it unless
    // the caller passed an explicit overrideMessage (which always wins).
    let message = overrideMessage ?? safeMessage(kind);
    if (
      !overrideMessage &&
      (kind === "conflict" || kind === "validation") &&
      payload &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof (payload as { detail?: unknown }).detail === "string" &&
      (payload as { detail: string }).detail.trim() !== ""
    ) {
      message = (payload as { detail: string }).detail;
    }
    throw new ApiError(kind, message, response.status, payload);
  }

  return payload as T;
}

export function getSafeApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}
