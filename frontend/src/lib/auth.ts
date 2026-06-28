import { apiFetch } from "@/lib/api";

export interface AuthUser {
  id?: string;
  email: string;
  name: string;
  display_name?: string;
  givenName?: string;
  familyName?: string;
  role?: string;
  /** Full platform role set (Epic 23). Falls back to [role] when only the single role is present. */
  roles?: string[];
  is_active?: boolean;
  /** IANA timezone (set by admin at user creation); used to format message times. */
  timezone?: string;
  /** Backend-served Azure avatar URL (Epic 23); null/absent => initials fallback. */
  avatarUrl?: string | null;
}

export interface AuthStatus {
  authenticated: boolean;
  user: AuthUser | null;
}

interface AuthStatusResponse {
  authenticated: boolean;
  email?: string;
  name?: string;
  role?: string;
  roles?: string[];
  avatar_url?: string | null;
  timezone?: string;
}

interface AuthProfileResponse {
  authenticated?: boolean;
  id?: string;
  email: string;
  display_name?: string;
  name?: string;
  given_name?: string;
  family_name?: string;
  role?: string;
  roles?: string[];
  avatar_url?: string | null;
  is_active?: boolean;
  timezone?: string;
}

export function normalizeUser(
  data: AuthProfileResponse | AuthStatusResponse,
): AuthUser | null {
  if (!data.email) return null;
  const displayName = "display_name" in data ? data.display_name : data.name;
  // Prefer the full role set; fall back to [role] for back-compat with payloads
  // that predate the multi-role model.
  const roles =
    data.roles && data.roles.length > 0
      ? data.roles
      : data.role
        ? [data.role]
        : [];
  return {
    id: "id" in data ? data.id : undefined,
    email: data.email,
    name: displayName || data.name || data.email,
    display_name: displayName,
    givenName: "given_name" in data ? data.given_name : undefined,
    familyName: "family_name" in data ? data.family_name : undefined,
    role: data.role,
    roles,
    is_active: "is_active" in data ? data.is_active : undefined,
    timezone: data.timezone,
    avatarUrl: data.avatar_url ?? null,
  };
}

// API client that includes credentials. Kept for existing callers that need raw Response access.
export async function fetchWithAuth(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  let token = null;
  try {
    token = localStorage.getItem("aiqa_access_token");
  } catch (_e) {}
  return fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
}

// Check authentication status
export async function checkAuthStatus(): Promise<AuthStatus> {
  try {
    const data = await apiFetch<AuthStatusResponse>("/status", {
      authRoute: true,
    });
    if (data.authenticated && data.email) {
      return { authenticated: true, user: normalizeUser(data) };
    }
    return { authenticated: false, user: null };
  } catch {
    return { authenticated: false, user: null };
  }
}

// Get current user info
export async function getCurrentUser(): Promise<AuthUser | null> {
  try {
    const data = await apiFetch<AuthProfileResponse>("/me", {
      authRoute: true,
    });
    return normalizeUser(data);
  } catch {
    return null;
  }
}

// Logout
export async function logout(): Promise<void> {
  try {
    await apiFetch<{ success: boolean }>("/logout", {
      method: "POST",
      authRoute: true,
    });
  } catch {
    // Ignore errors
  } finally {
    try {
      localStorage.removeItem("aiqa_access_token");
    } catch {
      // Ignore
    }
  }
}
