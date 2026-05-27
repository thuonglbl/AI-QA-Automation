import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdminDashboard } from "@/components/admin/AdminDashboard";
import { ProjectProvider } from "@/contexts/ProjectContext";
import { AuthProvider } from "@/contexts/AuthContext";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

const project = {
  id: "project-1",
  name: "Admin Project",
  description: null,
  created_by_user_id: null,
  current_user_role: "owner",
  membership_count: 1,
  memberships: [
    {
      id: "membership-1",
      user_id: "user-1",
      role: "member",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const assignableProject = {
  ...project,
  id: "project-2",
  name: "Assignable Project",
  memberships: [],
  membership_count: 0,
};

const user = {
  id: "user-1",
  email: "member@example.com",
  display_name: "Member User",
  role: "user",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("AdminDashboard", () => {
  beforeEach(() => {
    window.localStorage?.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("manages projects, users, and per-user memberships", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url === "/auth/status") return jsonResponse({ authenticated: true, email: "admin@example.com", name: "Admin User", role: "admin" });
      if (url === "/api/projects") return jsonResponse([project, assignableProject]);
      if (url === "/api/admin/users") return jsonResponse([user]);
      if (url === "/api/admin/projects" && init?.method === "POST") return jsonResponse(project);
      if (url === "/api/admin/users" && init?.method === "POST") return jsonResponse({ ...user, id: "user-2", email: "new.user@example.com", display_name: "New User" });
      if (url === "/api/admin/projects/project-1" && init?.method === "PUT") return jsonResponse({ ...project, name: "Updated Project" });
      if (url === "/api/admin/projects/project-1" && init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
      if (url === "/api/admin/projects/project-2/memberships" && init?.method === "POST") return jsonResponse({ id: "membership-2" });
      if (url === "/api/admin/projects/project-1/memberships/user-1" && init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
      if (url === "/auth/logout" && init?.method === "POST") return jsonResponse({ success: true });
      return jsonResponse({}, 404);
    });

    render(
      <AuthProvider>
        <ProjectProvider>
          <AdminDashboard />
        </ProjectProvider>
      </AuthProvider>,
    );

    expect(await screen.findByText("Admin User")).toBeInTheDocument();
    expect(screen.getByText(/admin@example\.com/)).toBeInTheDocument();
    expect((await screen.findAllByText("member@example.com")).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText(/project name/i), { target: { value: "New Project" } });
    fireEvent.click(screen.getByRole("button", { name: /create project/i }));
    expect(await screen.findByText(/project created successfully/i)).toBeInTheDocument();

    await waitFor(
      () => expect(screen.queryByText(/project created successfully/i)).not.toBeInTheDocument(),
      { timeout: 3500 },
    );

    fireEvent.click(screen.getByRole("button", { name: /edit admin project/i }));
    fireEvent.change(screen.getByLabelText(/project name/i, { selector: "input#edit-project-name-project-1" }), { target: { value: "Updated Project" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/admin/projects/project-1", expect.objectContaining({ method: "PUT" })));

    fireEvent.click(screen.getByRole("button", { name: /delete admin project/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/admin/projects/project-1", expect.objectContaining({ method: "DELETE" })));

    expect(screen.queryByText(/manage membership/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sync existing company's users/i })).toBeDisabled();
    expect(screen.getByText("This feature is not available at the moment, please add manually.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "new.user@example.com" } });
    fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: "New User" } });
    fireEvent.change(screen.getByLabelText(/initial password/i), { target: { value: "initial-secret" } });
    fireEvent.click(screen.getByRole("button", { name: /create user/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/admin/users", expect.objectContaining({ method: "POST" })));

    const userCard = screen.getByText("Member User").closest("li") as HTMLElement;
    expect(within(userCard).getByText("Projects")).toBeInTheDocument();

    fireEvent.change(within(userCard).getByRole("combobox", { name: /select project for member user/i }), { target: { value: "project-2" } });
    fireEvent.click(within(userCard).getByRole("button", { name: /assign project to member user/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/admin/projects/project-2/memberships", expect.objectContaining({ method: "POST" })));

    fireEvent.click(within(userCard).getByRole("button", { name: /remove admin project from member user/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/admin/projects/project-1/memberships/user-1", expect.objectContaining({ method: "DELETE" })));

    fireEvent.click(screen.getByRole("button", { name: /logout/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/auth/logout", expect.objectContaining({ method: "POST" })));
  });
});
