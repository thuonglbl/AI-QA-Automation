import { apiFetch, API_BASE_PATH } from "@/lib/api";
import type {
  AdminProject,
  AdminUser,
  CreateAdminUserRequest,
  CreateMembershipRequest,
  CreateProjectRequest,
  DiscoveredModel,
  E2ETestRunResult,
  ModelSyncResult,
  Project,
  UpdateAdminUserRequest,
} from "@/types/project";

export function getUserProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/projects");
}

export function getProject(projectId: string): Promise<Project> {
  return apiFetch<Project>(`/projects/${encodeURIComponent(projectId)}`);
}

export function listAdminUsers(): Promise<AdminUser[]> {
  return apiFetch<AdminUser[]>("/admin/users");
}

export function createAdminUser(
  request: CreateAdminUserRequest,
): Promise<AdminUser> {
  return apiFetch<AdminUser>("/admin/users", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function updateAdminUser(
  userId: string,
  request: UpdateAdminUserRequest,
): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/admin/users/${encodeURIComponent(userId)}`, {
    method: "PUT",
    body: JSON.stringify(request),
  });
}

export function deleteAdminUser(userId: string): Promise<void> {
  return apiFetch<void>(`/admin/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
}

export function createAdminProject(
  request: CreateProjectRequest,
): Promise<AdminProject> {
  return apiFetch<AdminProject>("/admin/projects", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function updateAdminProject(
  projectId: string,
  request: CreateProjectRequest,
): Promise<AdminProject> {
  return apiFetch<AdminProject>(
    `/admin/projects/${encodeURIComponent(projectId)}`,
    {
      method: "PUT",
      body: JSON.stringify(request),
    },
  );
}

export function deleteAdminProject(projectId: string): Promise<void> {
  return apiFetch<void>(`/admin/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });
}

export function assignProjectMembership(
  projectId: string,
  request: CreateMembershipRequest,
): Promise<unknown> {
  return apiFetch(
    `/admin/projects/${encodeURIComponent(projectId)}/memberships`,
    {
      method: "POST",
      body: JSON.stringify(request),
    },
  );
}

export function removeProjectMembership(
  projectId: string,
  userId: string,
): Promise<void> {
  return apiFetch<void>(
    `/admin/projects/${encodeURIComponent(projectId)}/memberships/${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
}

export function listDiscoveredModels(): Promise<DiscoveredModel[]> {
  return apiFetch<DiscoveredModel[]>("/admin/discovered-models");
}

/**
 * Trigger the admin "Sync models and benchmarks" action: discover models from every
 * configured provider and refresh their benchmark scores from llm-stats.com. Long-running
 * (mirrors the E2E runner) — uses a 15-minute abort timeout.
 */
export async function syncModelsAndBenchmarks(): Promise<ModelSyncResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 900000); // 15 minutes
  try {
    return await apiFetch<ModelSyncResult>("/admin/models/sync", {
      method: "POST",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Start an E2E run. Returns immediately (the run executes in the background on the
 * server); the result arrives via {@link getE2EStatus} polling. Returning fast
 * avoids the reverse-proxy timeout that severed the old synchronous request.
 */
export async function runE2ETests(): Promise<E2ETestRunResult> {
  return await apiFetch<E2ETestRunResult>("/admin/tests/e2e", {
    method: "POST",
  });
}

/** Poll the current/last E2E run state (poll while status === "running"). */
export async function getE2EStatus(): Promise<E2ETestRunResult> {
  return await apiFetch<E2ETestRunResult>("/admin/tests/e2e/status", {
    cache: "no-store",
  });
}

/**
 * Trigger a browser download of the Playwright HTML report zip from the backend.
 * Uses a dynamic anchor element so the browser prompts a Save dialog.
 */
export async function downloadE2EReport(): Promise<void> {
  let token: string | null = null;
  try {
    token = localStorage.getItem("aiqa_access_token");
  } catch (e) {
    console.error("Failed to read token from localStorage:", e);
  }

  if (!token) {
    throw new Error("Cannot download report: Authentication token is missing.");
  }

  const url = `${API_BASE_PATH}/admin/tests/e2e/report`;
  const response = await fetch(url, {
    credentials: "include",
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    throw new Error(
      `Failed to download report: ${response.status} ${response.statusText}`,
    );
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = "playwright-report.zip";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(objectUrl);
}
