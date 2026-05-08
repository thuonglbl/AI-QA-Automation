import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProjectProvider } from "@/contexts/ProjectContext";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

const project = {
  id: "project-1",
  name: "Shared QA Project",
  description: "Collaborative project",
  created_by_user_id: null,
  current_user_role: "member",
  membership_count: 1,
  memberships: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderApp() {
  return render(
    <AuthProvider>
      <ProjectProvider>
        <App />
      </ProjectProvider>
    </AuthProvider>,
  );
}

describe("App auth and project gates", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.stubGlobal("WebSocket", vi.fn());
  });

  it("shows the login flow instead of the pipeline for unauthenticated users", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input) === "/auth/status") {
        return jsonResponse({ authenticated: false });
      }
      return jsonResponse({}, 404);
    });

    renderApp();

    expect(await screen.findByText(/sign in to access/i)).toBeInTheDocument();
    expect(screen.queryByText(/Browser Use Cloud/i)).not.toBeInTheDocument();
  });

  it("shows the project picker before the pipeline for authenticated users", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/auth/status") {
        return jsonResponse({ authenticated: true, email: "member@example.com", name: "Member", role: "user" });
      }
      if (url === "/api/projects") {
        return jsonResponse([project]);
      }
      return jsonResponse({}, 404);
    });

    renderApp();

    expect(await screen.findByRole("heading", { name: /choose where this run belongs/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /shared qa project/i })).toBeInTheDocument();
    expect(screen.queryByText(/Browser Use Cloud/i)).not.toBeInTheDocument();
  });

  it("hides admin management for standard users after project selection", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/auth/status") {
        return jsonResponse({ authenticated: true, email: "member@example.com", name: "Member", role: "user" });
      }
      if (url === "/api/projects") {
        return jsonResponse([project]);
      }
      return jsonResponse({}, 404);
    });

    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: /shared qa project/i }));

    expect(await screen.findByText(/Browser Use Cloud/i)).toBeInTheDocument();
    expect(screen.queryByText(/admin management/i)).not.toBeInTheDocument();
  });

  it("shows admin management for admin users after project selection", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/auth/status") {
        return jsonResponse({ authenticated: true, email: "admin@example.com", name: "Admin", role: "admin" });
      }
      if (url === "/api/projects") {
        return jsonResponse([{ ...project, current_user_role: null }]);
      }
      if (url === "/api/admin/users") {
        return jsonResponse([]);
      }
      return jsonResponse({}, 404);
    });

    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: /shared qa project/i }));

    await waitFor(() => expect(screen.getByText(/admin management/i)).toBeInTheDocument());
  });
});
