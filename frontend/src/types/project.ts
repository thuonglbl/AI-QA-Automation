export interface ProjectMembershipSummary {
  id: string;
  user_id: string;
  role: string;
  created_at: string;
  updated_at: string;
}

/** A named target environment for the app under test (project-wide, admin-managed). */
export interface ProjectEnvironment {
  name: string;
  url: string;
  login_type?: string;
  login_hint?: string;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  confluence_base_url: string | null;
  jira_base_url: string | null;
  enabled_providers: string[];
  environments: ProjectEnvironment[];
  app_roles: string[];
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
  environments: ProjectEnvironment[];
  app_roles: string[];
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

/** An administered project as seen in the Project Admin dashboard (config + members). */
export interface ProjectAdminProject extends AdminProject {
  memberships: ProjectMembershipSummary[];
}

/** Display-safe user summary a project_admin can assign as a member. */
export interface AssignableUser {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
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
  /** IANA timezone the user's message times are localized to. */
  timezone: string;
  conversation_language: string;
  created_at: string;
  updated_at: string;
  project_memberships: AdminUserProjectMembership[];
}

export interface CreateProjectRequest {
  name: string;
  description?: string | null;
  // Config below is owned by the project_admin (set via the project-admin API), so the
  // platform admin's create/update only needs name + description.
  confluence_base_url?: string | null;
  jira_base_url?: string | null;
  enabled_providers?: string[];
  environments?: ProjectEnvironment[];
  app_roles?: string[];
}

export interface CreateMembershipRequest {
  user_id: string;
  role: "member" | "owner" | "project_admin";
}

export interface CreateAdminUserRequest {
  email: string;
  display_name?: string;
  // An admin may only create project_admin / standard users (not another platform admin).
  role: "project_admin" | "standard";
  /** IANA timezone (e.g. "Asia/Ho_Chi_Minh") used to localize the user's message times. */
  timezone: string;
  conversation_language: string;
  /** Required when role is "project_admin": the project the new admin is linked to. */
  project_id?: string | null;
}

export interface UpdateAdminUserRequest {
  display_name: string;
  // Promotion to platform admin is not allowed (only project_admin / standard).
  role: "project_admin" | "standard";
  timezone: string;
  conversation_language: string;
  is_active: boolean;
  /** Legacy single-project link (still accepted for a standard→project_admin promotion). */
  project_id?: string | null;
  /**
   * Full administered-project set for a project_admin (Epic 23). When present it REPLACES
   * the user's project_admin membership set (1..n). Forbidden for a standard user.
   */
  project_ids?: string[] | null;
}

export interface E2ETestRunResult {
  /** The run executes in the background; poll until status is "completed". */
  status: "idle" | "running" | "completed";
  exit_code: number | null;
  passed: boolean | null;
  report_available: boolean;
  stdout: string;
  stderr: string;
}

export type ModelCapability =
  | "global"
  | "reasoning"
  | "vision"
  | "instruction"
  | "coding"
  | "fast";

export interface ModelBenchmarkScore {
  id: string;
  model_id: string;
  capability: string;
  score: number;
  note: string | null;
  updated_by_user_id: string | null;
  updated_at: string;
}

export interface DiscoveredModel {
  model_id: string;
  display_name: string | null;
  supports_vision: boolean | null;
  last_seen_at: string;
  tier_source: "admin" | "curated" | "parsed";
  unbenchmarked: boolean;
  scores: ModelBenchmarkScore[];
}

export interface ModelScoreUpsertRequest {
  model_id: string;
  capability: ModelCapability;
  score: number;
  note?: string | null;
}

/** Per-provider outcome of the admin "Sync models and benchmarks" action. */
export interface ModelSyncProviderResult {
  provider_id: string;
  connected: boolean;
  skipped: boolean;
  models_found: number;
  error: string | null;
}

/** Summary returned after a model + benchmark sync. */
export interface ModelSyncResult {
  providers: ModelSyncProviderResult[];
  models_discovered: number;
  models_benchmarked: number;
  models_unbenchmarked: number;
  scores_written: number;
  benchmark_source_available: boolean;
  warnings: string[];
}
