export interface ProjectMembershipSummary {
  id: string;
  user_id: string;
  role: string;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  confluence_base_url: string | null;
  jira_base_url: string | null;
  enabled_providers: string[];
  created_by_user_id: string | null;
  current_user_role: string | null;
  membership_count: number;
  memberships: ProjectMembershipSummary[];
  created_at: string;
  updated_at: string;
}

export interface AdminProject {
  id: string;
  name: string;
  description: string | null;
  confluence_base_url: string | null;
  jira_base_url: string | null;
  enabled_providers: string[];
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminUserProjectMembership {
  id: string;
  project_id: string;
  project_name: string;
  role: string;
  created_at: string;
  updated_at: string;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  project_memberships: AdminUserProjectMembership[];
}

export interface CreateProjectRequest {
  name: string;
  description?: string | null;
  confluence_base_url?: string | null;
  jira_base_url?: string | null;
  enabled_providers: string[];
}

export interface CreateMembershipRequest {
  user_id: string;
  role: "member" | "owner";
}

export interface CreateAdminUserRequest {
  email: string;
  display_name: string;
  role: "admin" | "standard";
  initial_password: string;
}

export interface E2ETestRunResult {
  exit_code: number;
  passed: boolean;
  report_available: boolean;
  stdout: string;
  stderr: string;
}
