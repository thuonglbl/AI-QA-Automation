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
  created_by_user_id: string | null;
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
}

export interface CreateProjectRequest {
  name: string;
  description?: string | null;
}

export interface CreateMembershipRequest {
  user_id: string;
  role: "member" | "owner";
}
