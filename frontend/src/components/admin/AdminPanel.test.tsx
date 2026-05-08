import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdminPanel } from "@/components/admin/AdminPanel";
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
  memberships: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
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

describe("AdminPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("loads users and submits project creation and membership assignment", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url === "/auth/status") return jsonResponse({ authenticated: true, email: "admin@example.com", name: "Admin", role: "admin" });
      if (url === "/api/projects") return jsonResponse([project]);
      if (url === "/api/admin/users") return jsonResponse([user]);
      if (url === "/api/admin/projects" && init?.method === "POST") return jsonResponse(project);
      if (url === "/api/admin/projects/project-1/memberships" && init?.method === "POST") return jsonResponse({ id: "membership-1" });
      return jsonResponse({}, 404);
    });

    render(
      <AuthProvider>
        <ProjectProvider>
          <AdminPanel />
        </ProjectProvider>
      </AuthProvider>,
    );

    expect((await screen.findAllByText("member@example.com")).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText(/project name/i), { target: { value: "New Project" } });
    fireEvent.click(screen.getByRole("button", { name: /create project/i }));
    expect(await screen.findByText(/project created successfully/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/^project$/i), { target: { value: "project-1" } });
    fireEvent.change(screen.getByLabelText(/^user$/i), { target: { value: "user-1" } });
    fireEvent.click(screen.getByRole("button", { name: /assign user/i }));
    expect(await screen.findByText(/membership assignment saved/i)).toBeInTheDocument();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/admin/projects/project-1/memberships", expect.objectContaining({ method: "POST" })));
  });
});
