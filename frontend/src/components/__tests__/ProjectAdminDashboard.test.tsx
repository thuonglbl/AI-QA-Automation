import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { AssignableUser, ProjectAdminProject } from "@/types/project";

const project: ProjectAdminProject = {
  id: "p1",
  name: "Alpha",
  description: null,
  confluence_base_url: "https://confluence.example.com",
  jira_base_url: null,
  enabled_providers: ["openai"],
  environments: [{ name: "Test 1", url: "https://t1.app" }],
  app_roles: ["Admin"],
  created_by_user_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  memberships: [
    { id: "m1", user_id: "u2", role: "member", created_at: "x", updated_at: "x" },
    { id: "m2", user_id: "u4", role: "project_admin", created_at: "x", updated_at: "x" },
  ],
};
const member: AssignableUser = {
  id: "u2",
  email: "member@example.com",
  display_name: "Member Two",
  role: "standard",
  is_active: true,
};
const newcomer: AssignableUser = {
  id: "u3",
  email: "new@example.com",
  display_name: "New Three",
  role: "standard",
  is_active: true,
};
// A non-member platform admin — must never appear in the assign dropdown.
const adminUser: AssignableUser = {
  id: "u5",
  email: "admin@example.com",
  display_name: "Admin Five",
  role: "admin",
  is_active: true,
};
// A project_admin who is already a member — its remove button must be disabled.
const padminMember: AssignableUser = {
  id: "u4",
  email: "pa-member@example.com",
  display_name: "PA Four",
  role: "project_admin",
  is_active: true,
};

const updateProjectConfig = vi.fn().mockResolvedValue(project);
const addProjectMember = vi.fn().mockResolvedValue({});
const removeProjectMember = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/projectAdmin", () => ({
  listAdministeredProjects: () => Promise.resolve([project]),
  listAssignableUsers: () => Promise.resolve([member, newcomer, adminUser, padminMember]),
  updateProjectConfig: (...args: unknown[]) => updateProjectConfig(...args),
  addProjectMember: (...args: unknown[]) => addProjectMember(...args),
  removeProjectMember: (...args: unknown[]) => removeProjectMember(...args),
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: {
      role: "project_admin",
      email: "pa@example.com",
      name: "PA",
      display_name: "Project Admin",
    },
    logout: vi.fn(),
  }),
}));

import { ProjectAdminDashboard } from "../admin/ProjectAdminDashboard";

describe("ProjectAdminDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists the administered project and populates its config (no login type / accounts)", async () => {
    render(<ProjectAdminDashboard />);
    expect(await screen.findByRole("option", { name: "Alpha" })).toBeInTheDocument();
    // Config form is populated from the selected project via an effect (async).
    expect(
      await screen.findByDisplayValue("https://confluence.example.com"),
    ).toBeInTheDocument();
    // app role "Admin" appears (chip in the editor).
    expect(screen.getAllByText("Admin").length).toBeGreaterThan(0);
    // Removed: login-type selector + test-login accounts section.
    expect(screen.queryByLabelText(/login type/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/test-login accounts/i)).not.toBeInTheDocument();
  });


  it("saves configuration via the project-admin API", async () => {
    render(<ProjectAdminDashboard />);
    await screen.findByRole("option", { name: "Alpha" });
    // Wait until the config form has been populated from the project (effect-driven),
    // otherwise the save guard sees empty providers and short-circuits.
    await screen.findByDisplayValue("https://confluence.example.com");
    fireEvent.click(screen.getByRole("button", { name: /Save configuration/i }));
    await waitFor(() => expect(updateProjectConfig).toHaveBeenCalledTimes(1));
    expect(updateProjectConfig).toHaveBeenCalledWith(
      "p1",
      expect.objectContaining({
        confluence_base_url: "https://confluence.example.com",
        enabled_providers: ["openai"],
        app_roles: ["Admin"],
      }),
    );
  });

  it("only offers standard non-members in the assign dropdown", async () => {
    render(<ProjectAdminDashboard />);
    await screen.findByRole("option", { name: "Alpha" });
    // u3 is a standard non-member → assignable.
    expect(screen.getByRole("option", { name: /New Three/i })).toBeInTheDocument();
    // u2 is already a member → excluded.
    expect(
      screen.queryByRole("option", { name: /Member Two \(member@example.com\)/i }),
    ).not.toBeInTheDocument();
    // u5 is a non-member but an admin → excluded (project_admins can only assign standard users).
    expect(
      screen.queryByRole("option", { name: /Admin Five/i }),
    ).not.toBeInTheDocument();
  });

  it("removes a standard member via the project-admin API", async () => {
    render(<ProjectAdminDashboard />);
    await screen.findByRole("option", { name: "Alpha" });
    fireEvent.click(
      await screen.findByRole("button", { name: /Remove member Member Two/i }),
    );
    await waitFor(() => expect(removeProjectMember).toHaveBeenCalledWith("p1", "u2"));
  });

  it("hides the remove button for a project_admin member but shows it for a standard member", async () => {
    render(<ProjectAdminDashboard />);
    await screen.findByRole("option", { name: "Alpha" });
    // Standard member → remove button present and enabled.
    expect(
      await screen.findByRole("button", { name: /Remove member Member Two/i }),
    ).toBeEnabled();
    // project_admin member → no remove button at all (not merely disabled).
    expect(
      screen.queryByRole("button", { name: /Remove member PA Four/i }),
    ).not.toBeInTheDocument();
  });
});
