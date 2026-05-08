import { apiFetch } from "@/lib/api";
import type { AdminProject, AdminUser, CreateMembershipRequest, CreateProjectRequest, Project } from "@/types/project";

export function listProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/projects");
}

export function getProject(projectId: string): Promise<Project> {
  return apiFetch<Project>(`/projects/${encodeURIComponent(projectId)}`);
}

export function listAdminUsers(): Promise<AdminUser[]> {
  return apiFetch<AdminUser[]>("/admin/users");
}

export function createAdminProject(request: CreateProjectRequest): Promise<AdminProject> {
  return apiFetch<AdminProject>("/admin/projects", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function assignProjectMembership(projectId: string, request: CreateMembershipRequest): Promise<unknown> {
  return apiFetch(`/admin/projects/${encodeURIComponent(projectId)}/memberships`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}
