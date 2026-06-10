import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, test, vi } from "vitest";
import { AdminDashboard } from "@/components/admin/AdminDashboard";
import { ProjectProvider } from "@/contexts/ProjectContext";
import { AuthProvider } from "@/contexts/AuthContext";
import { ApiError, getSafeApiErrorMessage } from "@/lib/api";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

const project = {
  id: "project-1",
  name: "Admin Project",
  description: null,
  confluence_base_url: "https://confluence",
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
  role: "standard",
  is_active: true,
  project_memberships: [
    {
      id: "membership-1",
      project_id: "project-1",
      project_name: "Admin Project",
      role: "member",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const adminUser = {
  id: "admin-1",
  email: "super.admin@example.com",
  display_name: "Super Admin",
  role: "admin",
  is_active: true,
  project_memberships: [],
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
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((input, init) => {
        const url = String(input);
        if (url === "/auth/status")
          return jsonResponse({
            authenticated: true,
            email: "admin@example.com",
            name: "Admin User",
            role: "admin",
          });
        if (url === "/api/projects")
          return jsonResponse([project, assignableProject]);
        if (url === "/api/admin/users") return jsonResponse([adminUser, user]);
        if (url === "/api/admin/projects" && init?.method === "POST")
          return jsonResponse(project);
        if (url === "/api/admin/users" && init?.method === "POST")
          return jsonResponse({
            ...user,
            id: "user-2",
            email: "new.user@example.com",
            display_name: "New User",
          });
        if (url === "/api/admin/projects/project-1" && init?.method === "PUT")
          return jsonResponse({ ...project, name: "Updated Project" });
        if (
          url === "/api/admin/projects/project-1" &&
          init?.method === "DELETE"
        )
          return Promise.resolve(new Response(null, { status: 204 }));
        if (
          url === "/api/admin/projects/project-2/memberships" &&
          init?.method === "POST"
        )
          return jsonResponse({ id: "membership-2" });
        if (
          url === "/api/admin/projects/project-1/memberships/user-1" &&
          init?.method === "DELETE"
        )
          return Promise.resolve(new Response(null, { status: 204 }));
        if (url === "/auth/logout" && init?.method === "POST")
          return jsonResponse({ success: true });
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
    // AC1 (Story 8.5) unit gap: nav identity block renders email + role alongside
    // the display name.  Scope to the <nav> so the email regex does not also match
    // the "super.admin@example.com" admin-user card in the users list.
    const nav = screen.getByRole("navigation");
    const identityNode = within(nav).getByText(/admin@example\.com/);
    expect(identityNode).toBeInTheDocument();
    expect(identityNode.textContent).toMatch(/admin/); // role rendered in same node
    expect(
      (await screen.findAllByText("member@example.com")).length,
    ).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText(/project name/i), {
      target: { value: "New Project" },
    });
    fireEvent.change(screen.getByLabelText(/confluence base url/i), {
      target: { value: "https://confluence" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create project/i }));
    expect(
      await screen.findByText(/project created successfully/i),
    ).toBeInTheDocument();

    await waitFor(
      () =>
        expect(
          screen.queryByText(/project created successfully/i),
        ).not.toBeInTheDocument(),
      { timeout: 3500 },
    );

    fireEvent.click(
      screen.getByRole("button", { name: /edit admin project/i }),
    );
    fireEvent.change(
      screen.getByLabelText(/project name/i, {
        selector: "input#edit-project-name-project-1",
      }),
      { target: { value: "Updated Project" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/projects/project-1",
        expect.objectContaining({ method: "PUT" }),
      ),
    );

    fireEvent.click(
      screen.getByRole("button", { name: /delete admin project/i }),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/projects/project-1",
        expect.objectContaining({ method: "DELETE" }),
      ),
    );

    expect(screen.queryByText(/manage membership/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /sync existing company's users/i }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "This feature is not available at the moment, please add manually.",
      ),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "new.user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/display name/i), {
      target: { value: "New User" },
    });
    fireEvent.change(screen.getByLabelText(/^role$/i), {
      target: { value: "admin" },
    });
    fireEvent.change(screen.getByLabelText(/initial password/i), {
      target: { value: "initial-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create user/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/users",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            email: "new.user@example.com",
            display_name: "New User",
            role: "admin",
            initial_password: "initial-secret",
          }),
        }),
      ),
    );

    const adminCard = screen
      .getByText("Super Admin")
      .closest("li") as HTMLElement;
    expect(within(adminCard).queryByText("Projects")).not.toBeInTheDocument();
    expect(
      within(adminCard).queryByRole("combobox", { name: /select project/i }),
    ).not.toBeInTheDocument();
    expect(
      within(adminCard).queryByRole("button", { name: /assign project/i }),
    ).not.toBeInTheDocument();

    const userCard = screen
      .getByText("Member User")
      .closest("li") as HTMLElement;
    expect(within(userCard).getByText("Projects")).toBeInTheDocument();
    expect(within(userCard).getByText("Admin Project")).toBeInTheDocument();
    expect(screen.queryByText(/register/i)).not.toBeInTheDocument();

    fireEvent.change(
      within(userCard).getByRole("combobox", {
        name: /select project for member user/i,
      }),
      { target: { value: "project-2" } },
    );
    fireEvent.click(
      within(userCard).getByRole("button", {
        name: /assign project to member user/i,
      }),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/projects/project-2/memberships",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    fireEvent.click(
      within(userCard).getByRole("button", {
        name: /remove admin project from member user/i,
      }),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/projects/project-1/memberships/user-1",
        expect.objectContaining({ method: "DELETE" }),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: /logout/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/auth/logout",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("surfaces a safe error when creating a duplicate user (409) and does not report success", async () => {
    // AC2: a duplicate email is rejected with 409 { detail: "User already exists" }.
    // The dashboard must show a safe message via getSafeApiErrorMessage and must NOT
    // falsely report "User created successfully". A 409 maps to kind "server" in the
    // API client, so the rendered banner shows the generic safe fallback (no internals leaked).
    const postBody = JSON.stringify({ detail: "User already exists" });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((input, init) => {
        const url = String(input);
        if (url === "/auth/status")
          return jsonResponse({
            authenticated: true,
            email: "admin@example.com",
            name: "Admin User",
            role: "admin",
          });
        if (url === "/api/projects") return jsonResponse([]);
        if (url === "/api/admin/users" && init?.method === "POST")
          return Promise.resolve(
            new Response(postBody, {
              status: 409,
              headers: { "content-type": "application/json" },
            }),
          );
        if (url === "/api/admin/users") return jsonResponse([]);
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

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "existing.user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/display name/i), {
      target: { value: "Existing User" },
    });
    fireEvent.change(screen.getByLabelText(/initial password/i), {
      target: { value: "another-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create user/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/users",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    // The banner shows exactly what handleCreateUser passes to addError:
    // getSafeApiErrorMessage of the thrown 409 ApiError.
    const expectedMessage = getSafeApiErrorMessage(
      new ApiError("server", "Something went wrong. Please try again.", 409),
    );
    const banner = await screen.findByText(expectedMessage);
    expect(banner).toBeInTheDocument();

    // No false success and no leaked internals (stack traces, raw DB errors).
    expect(
      screen.queryByText(/user created successfully/i),
    ).not.toBeInTheDocument();
    expect(banner.textContent).not.toMatch(/traceback|integrityerror|sql/i);
  });

  it("surfaces a safe error when creating a duplicate project (409) and does not report success", async () => {
    // Story 8.3 AC2: a duplicate project name is rejected with 409
    // { detail: "Project name already exists" }. The dashboard must show a safe
    // message via getSafeApiErrorMessage and must NOT falsely report "Project
    // created successfully". A 409 maps to kind "server" in the API client, so the
    // rendered banner shows the generic safe fallback (no backend internals leaked).
    const postBody = JSON.stringify({ detail: "Project name already exists" });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((input, init) => {
        const url = String(input);
        if (url === "/auth/status")
          return jsonResponse({
            authenticated: true,
            email: "admin@example.com",
            name: "Admin User",
            role: "admin",
          });
        if (url === "/api/projects") return jsonResponse([]);
        if (url === "/api/admin/projects" && init?.method === "POST")
          return Promise.resolve(
            new Response(postBody, {
              status: 409,
              headers: { "content-type": "application/json" },
            }),
          );
        if (url === "/api/admin/users") return jsonResponse([]);
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

    fireEvent.change(screen.getByLabelText(/project name/i), {
      target: { value: "Existing Project" },
    });
    fireEvent.change(screen.getByLabelText(/confluence base url/i), {
      target: { value: "https://confluence" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create project/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/projects",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    // The banner shows what handleCreateProject passes to addError:
    // getSafeApiErrorMessage of the thrown 409 ApiError.
    const expectedMessage = getSafeApiErrorMessage(
      new ApiError("server", "Something went wrong. Please try again.", 409),
    );
    const banner = await screen.findByText(expectedMessage);
    expect(banner).toBeInTheDocument();

    // No false success and no leaked internals.
    expect(
      screen.queryByText(/project created successfully/i),
    ).not.toBeInTheDocument();
    expect(banner.textContent).not.toMatch(/traceback|integrityerror|sql/i);
  });

  describe("E2E Test Execution", () => {
    function renderDashboard(
      fetchImpl: (
        input: RequestInfo | URL,
        init?: RequestInit,
      ) => Promise<Response>,
    ) {
      vi.spyOn(globalThis, "fetch").mockImplementation(fetchImpl);
      render(
        <AuthProvider>
          <ProjectProvider>
            <AdminDashboard />
          </ProjectProvider>
        </AuthProvider>,
      );
    }

    function defaultFetch(
      input: RequestInfo | URL,
      _init?: RequestInit,
    ): Promise<Response> {
      const url = String(input);
      if (url === "/auth/status")
        return jsonResponse({
          authenticated: true,
          email: "admin@example.com",
          name: "Admin",
          role: "admin",
        });
      if (url === "/api/projects") return jsonResponse([]);
      if (url === "/api/admin/users") return jsonResponse([]);
      return jsonResponse({}, 404);
    }

    it("renders the Run E2E Tests button", async () => {
      renderDashboard(defaultFetch);

      await screen.findByText("Admin");
      expect(
        screen.getByRole("button", { name: /run e2e tests/i }),
      ).toBeInTheDocument();
    });

    it("shows loading state while tests run and disables button", async () => {
      let resolveE2E!: (value: Response) => void;
      const e2ePromise = new Promise<Response>((resolve) => {
        resolveE2E = resolve;
      });

      renderDashboard((input, init) => {
        const url = String(input);
        if (url === "/auth/status")
          return jsonResponse({
            authenticated: true,
            email: "admin@example.com",
            name: "Admin",
            role: "admin",
          });
        if (url === "/api/projects") return jsonResponse([]);
        if (url === "/api/admin/users") return jsonResponse([]);
        if (url === "/api/admin/tests/e2e" && init?.method === "POST")
          return e2ePromise;
        return jsonResponse({}, 404);
      });

      await screen.findByText("Admin");
      const runButton = screen.getByRole("button", { name: /run e2e tests/i });
      fireEvent.click(runButton);

      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: /running e2e tests/i }),
        ).toBeDisabled(),
      );
      expect(screen.getByText(/tests are running/i)).toBeInTheDocument();

      // Resolve test to clean up
      resolveE2E(
        new Response(
          JSON.stringify({
            exit_code: 0,
            passed: true,
            report_available: false,
            stdout: "",
            stderr: "",
          }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        ),
      );
    });

    it("shows passed result after successful E2E run", async () => {
      const e2eResult = {
        exit_code: 0,
        passed: true,
        report_available: false,
        stdout: "5 passed",
        stderr: "",
      };

      renderDashboard((input, init) => {
        const url = String(input);
        if (url === "/auth/status")
          return jsonResponse({
            authenticated: true,
            email: "admin@example.com",
            name: "Admin",
            role: "admin",
          });
        if (url === "/api/projects") return jsonResponse([]);
        if (url === "/api/admin/users") return jsonResponse([]);
        if (url === "/api/admin/tests/e2e" && init?.method === "POST")
          return jsonResponse(e2eResult);
        return jsonResponse({}, 404);
      });

      await screen.findByText("Admin");
      fireEvent.click(screen.getByRole("button", { name: /run e2e tests/i }));

      await waitFor(() =>
        expect(screen.getByText(/all tests passed/i)).toBeInTheDocument(),
      );
      expect(screen.queryByText(/tests are running/i)).not.toBeInTheDocument();
    });

    it("shows failed result when E2E tests fail", async () => {
      const e2eResult = {
        exit_code: 1,
        passed: false,
        report_available: false,
        stdout: "1 passed, 2 failed",
        stderr: "AssertionError",
      };

      renderDashboard((input, init) => {
        const url = String(input);
        if (url === "/auth/status")
          return jsonResponse({
            authenticated: true,
            email: "admin@example.com",
            name: "Admin",
            role: "admin",
          });
        if (url === "/api/projects") return jsonResponse([]);
        if (url === "/api/admin/users") return jsonResponse([]);
        if (url === "/api/admin/tests/e2e" && init?.method === "POST")
          return jsonResponse(e2eResult);
        return jsonResponse({}, 404);
      });

      await screen.findByText("Admin");
      fireEvent.click(screen.getByRole("button", { name: /run e2e tests/i }));

      await waitFor(() =>
        expect(screen.getByText(/tests failed/i)).toBeInTheDocument(),
      );
      expect(screen.getByText(/exit code 1/i)).toBeInTheDocument();
    });

    it("shows download button when report is available", async () => {
      const e2eResult = {
        exit_code: 0,
        passed: true,
        report_available: true,
        stdout: "",
        stderr: "",
      };

      renderDashboard((input, init) => {
        const url = String(input);
        if (url === "/auth/status")
          return jsonResponse({
            authenticated: true,
            email: "admin@example.com",
            name: "Admin",
            role: "admin",
          });
        if (url === "/api/projects") return jsonResponse([]);
        if (url === "/api/admin/users") return jsonResponse([]);
        if (url === "/api/admin/tests/e2e" && init?.method === "POST")
          return jsonResponse(e2eResult);
        return jsonResponse({}, 404);
      });

      await screen.findByText("Admin");
      fireEvent.click(screen.getByRole("button", { name: /run e2e tests/i }));

      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: /download zip/i }),
        ).toBeInTheDocument(),
      );
    });

    it("hides download button when report is not available", async () => {
      const e2eResult = {
        exit_code: 0,
        passed: true,
        report_available: false,
        stdout: "",
        stderr: "",
      };

      renderDashboard((input, init) => {
        const url = String(input);
        if (url === "/auth/status")
          return jsonResponse({
            authenticated: true,
            email: "admin@example.com",
            name: "Admin",
            role: "admin",
          });
        if (url === "/api/projects") return jsonResponse([]);
        if (url === "/api/admin/users") return jsonResponse([]);
        if (url === "/api/admin/tests/e2e" && init?.method === "POST")
          return jsonResponse(e2eResult);
        return jsonResponse({}, 404);
      });

      await screen.findByText("Admin");
      fireEvent.click(screen.getByRole("button", { name: /run e2e tests/i }));

      await waitFor(() =>
        expect(screen.getByText(/all tests passed/i)).toBeInTheDocument(),
      );
      expect(
        screen.queryByRole("button", { name: /download zip/i }),
      ).not.toBeInTheDocument();
    });
  });
});

// Additional tests for Jira URL and provider management

test("AdminDashboard project form with Jira URL and provider checkboxes", async () => {
  vi.mock("@/lib/api", () => ({
    apiFetch: vi.fn(),
  }));

  // Mock the auth state to return admin user
  vi.mock("@/contexts/AuthContext", () => ({
    useAuth: () => ({
      user: { role: "admin" },
      logout: vi.fn(),
    }),
  }));

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  // Wait for admin dashboard to load
  await screen.findByText(/admin/i);

  // Click on "Create Project" button
  const createButton = screen.getByRole("button", { name: /create project/i });
  fireEvent.click(createButton);

  // Wait for form to appear
  await screen.findByRole("heading", { name: /create project/i });

  // Verify Jira URL field exists
  const jiraUrlInput = screen.getByPlaceholderText(/jira base url/i);
  expect(jiraUrlInput).toBeInTheDocument();

  // Verify provider checkboxes exist
  const providerCheckboxes = [
    /browser use/i,
    /claude/i,
    /gemini/i,
    /chatgpt/i,
    /on premises/i,
  ];
  for (const text of providerCheckboxes) {
    const checkbox = screen.getByRole("checkbox", { name: text });
    expect(checkbox).toBeInTheDocument();
  }

  // Verify validation error when no URL and no providers
  const submitButton = screen.getByRole("button", { name: /create project/i });
  fireEvent.click(submitButton);

  // Should show validation error
  await screen.findByText(/no link to extract requirement/i);
});

test("AdminDashboard project list shows Jira link and provider icons", async () => {
  vi.mock("@/lib/api", () => ({
    apiFetch: vi.fn(),
  }));

  vi.mock("@/contexts/AuthContext", () => ({
    useAuth: () => ({
      user: { role: "admin" },
      logout: vi.fn(),
    }),
  }));


  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  // Wait for admin dashboard to load
  await screen.findByText(/admin/i);

  // Verify Jira link is shown in project card
  const jiraLink = screen.getByRole("link", { name: /jira.example.com/i });
  expect(jiraLink).toBeInTheDocument();
  expect(jiraLink).toHaveAttribute("href", "https://jira.example.com");
  expect(jiraLink).toHaveAttribute("target", "_blank");

  // Verify provider icons are shown
  const providerIcons = screen.getAllByRole("img");
  expect(providerIcons.length).toBeGreaterThan(0);
});

test("AdminDashboard edit project form preserves Jira URL and provider configuration", async () => {
  vi.mock("@/lib/api", () => ({
    apiFetch: vi.fn(),
  }));

  vi.mock("@/contexts/AuthContext", () => ({
    useAuth: () => ({
      user: { role: "admin" },
      logout: vi.fn(),
    }),
  }));


  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  // Wait for admin dashboard to load
  await screen.findByText(/admin/i);

  // Click on edit button for project
  const editButton = screen.getByRole("button", { name: /edit test project/i });
  fireEvent.click(editButton);

  // Wait for edit form to appear
  await screen.findByRole("heading", { name: /edit project/i });

  // Verify Jira URL field is pre-populated
  const jiraUrlInput = screen.getByPlaceholderText(/jira base url/i);
  expect(jiraUrlInput).toHaveValue("https://jira.example.com");

  // Verify provider checkboxes are checked
  const claudeCheckbox = screen.getByRole("checkbox", { name: /claude/i });
  expect(claudeCheckbox).toBeChecked();

  const geminiCheckbox = screen.getByRole("checkbox", { name: /gemini/i });
  expect(geminiCheckbox).toBeChecked();
});
