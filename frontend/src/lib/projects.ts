import { apiFetch } from "@/lib/api";
import type {
  AdminProject,
  AdminUser,
  CreateAdminUserRequest,
  CreateMembershipRequest,
  CreateProjectRequest,
  Project,
} from "@/types/project";

export function listProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/projects");
}

export function getProject(projectId: string): Promise<Project> {
  return apiFetch<Project>(`/projects/${encodeURIComponent(projectId)}`);
}

export function listAdminUsers(): Promise<AdminUser[]> {
  return apiFetch<AdminUser[]>("/admin/users");
}

export function createAdminUser(request: CreateAdminUserRequest): Promise<AdminUser> {
  return apiFetch<AdminUser>("/admin/users", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function createAdminProject(request: CreateProjectRequest): Promise<AdminProject> {
  return apiFetch<AdminProject>("/admin/projects", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function updateAdminProject(projectId: string, request: CreateProjectRequest): Promise<AdminProject> {
  return apiFetch<AdminProject>(`/admin/projects/${encodeURIComponent(projectId)}`, {
    method: "PUT",
    body: JSON.stringify(request),
  });
}

export function deleteAdminProject(projectId: string): Promise<void> {
  return apiFetch<void>(`/admin/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });
}

export function assignProjectMembership(projectId: string, request: CreateMembershipRequest): Promise<unknown> {
  return apiFetch(`/admin/projects/${encodeURIComponent(projectId)}/memberships`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function removeProjectMembership(projectId: string, userId: string): Promise<void> {
  return apiFetch<void>(
    `/admin/projects/${encodeURIComponent(projectId)}/memberships/${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
}
