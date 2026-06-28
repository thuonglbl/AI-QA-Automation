/** Typed client for the project-admin API (`/project-admin/...`). */
import { apiFetch } from "@/lib/api";
import type {
  AdminProject,
  AssignableUser,
  ProjectAdminProject,
  ProjectEnvironment,
} from "@/types/project";

export interface ProjectConfigPayload {
  confluence_base_url: string | null;
  jira_base_url: string | null;
  enabled_providers: string[];
  environments: ProjectEnvironment[];
  app_roles: string[];
}

/** Projects the current user administers (platform admin sees all). */
export function listAdministeredProjects(): Promise<ProjectAdminProject[]> {
  return apiFetch<ProjectAdminProject[]>("/project-admin/projects");
}

/** Active users that can be assigned as members (display-safe). */
export function listAssignableUsers(): Promise<AssignableUser[]> {
  return apiFetch<AssignableUser[]>("/project-admin/users");
}

export function updateProjectConfig(
  projectId: string,
  payload: ProjectConfigPayload,
): Promise<AdminProject> {
  // The PUT /config endpoint returns AdminProjectResponse (no memberships), so the FE type
  // must be AdminProject — not the richer ProjectAdminProject — to match the actual payload.
  return apiFetch<AdminProject>(`/project-admin/projects/${projectId}/config`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function addProjectMember(
  projectId: string,
  userId: string,
  role = "member",
): Promise<unknown> {
  return apiFetch(`/project-admin/projects/${projectId}/members`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, role }),
  });
}

export function removeProjectMember(projectId: string, userId: string): Promise<void> {
  return apiFetch<void>(`/project-admin/projects/${projectId}/members/${userId}`, {
    method: "DELETE",
  });
}
