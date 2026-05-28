import { apiFetch } from "@/lib/api";

export interface AuthUser {
  id?: string;
  email: string;
  name: string;
  display_name?: string;
  givenName?: string;
  familyName?: string;
  role?: string;
  is_active?: boolean;
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
  is_active?: boolean;
}

export function normalizeUser(data: AuthProfileResponse | AuthStatusResponse): AuthUser | null {
  if (!data.email) return null;
  const displayName = "display_name" in data ? data.display_name : data.name;
  return {
    id: "id" in data ? data.id : undefined,
    email: data.email,
    name: displayName || data.name || data.email,
    display_name: displayName,
    givenName: "given_name" in data ? data.given_name : undefined,
    familyName: "family_name" in data ? data.family_name : undefined,
    role: data.role,
    is_active: "is_active" in data ? data.is_active : undefined,
  };
}

// API client that includes credentials. Kept for existing callers that need raw Response access.
export async function fetchWithAuth(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = localStorage.getItem("aiqa_access_token");
  return fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      ...(token ? { "Authorization": `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
}

// Check authentication status
export async function checkAuthStatus(): Promise<AuthStatus> {
  try {
    const data = await apiFetch<AuthStatusResponse>("/status", { authRoute: true });
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
    const data = await apiFetch<AuthProfileResponse>("/me", { authRoute: true });
    return normalizeUser(data);
  } catch {
    return null;
  }
}

// Logout
export async function logout(): Promise<void> {
  try {
    localStorage.removeItem("aiqa_access_token");
    await apiFetch<{ success: boolean }>("/logout", { method: "POST", authRoute: true });
  } catch {
    // Ignore errors
  }
}
