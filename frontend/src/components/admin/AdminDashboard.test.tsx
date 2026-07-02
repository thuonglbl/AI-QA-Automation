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
  jira_base_url: null,
  enabled_providers: ["claude", "gemini"],
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
        if (url === "/api/admin/discovered-models") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        if (url === "/api/admin/model-scores") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
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

    // Admin now creates a project with NAME ONLY (config moved to project admin).
    fireEvent.change(screen.getByLabelText(/project name/i), {
      target: { value: "New Project" },
    });
    // Spy on window.setTimeout so we can capture the 3 s auto-dismiss callback
    // and invoke it immediately — no real waiting, no fake-timer deadlock.
    // The spy must be installed BEFORE the click so it intercepts the timeout
    // that the useEffect schedules when setStatus("Project created successfully.")
    // is called inside the async handler.
    let dismissCallback: (() => void) | null = null;
    const originalSetTimeout = window.setTimeout;
    const setTimeoutSpy = vi
      .spyOn(window, "setTimeout")
      .mockImplementation(((fn: any, delay?: number, ...args: any[]) => {
        if (typeof fn === "function" && delay === 3000) {
          // Capture the dismiss callback but don't actually schedule it.
          dismissCallback = fn;
          return 0 as any;
        }
        // All other timeouts (e.g. RTL's internal polling) run normally.
        return originalSetTimeout(fn, delay, ...args) as any;
      }) as any);

    fireEvent.click(screen.getByRole("button", { name: /create project/i }));

    // Wait for the banner with real timers (so findBy can poll normally).
    expect(
      await screen.findByText(/project created successfully/i),
    ).toBeInTheDocument();

    // The useEffect has now called our spy with the dismiss callback.
    // Invoke it manually inside act() so React processes the setState.
    expect(dismissCallback).not.toBeNull();
    const { act } = await import("@testing-library/react");
    await act(async () => {
      dismissCallback!();
    });
    expect(
      screen.queryByText(/project created successfully/i),
    ).not.toBeInTheDocument();

    setTimeoutSpy.mockRestore();


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

    const deleteButton = await screen.findByRole("button", { name: /delete admin project/i });
    fireEvent.click(deleteButton);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/projects/project-1",
        expect.objectContaining({ method: "DELETE" }),
      ),
    );



    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "new.user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/name \(optional\)/i), {
      target: { value: "New User" },
    });
    // Admin may only create project_admin / standard users (not another admin).
    fireEvent.change(screen.getByLabelText(/^role$/i), {
      target: { value: "project_admin" },
    });
    // Selecting Project Admin reveals the required project picker (Story 15.3); the
    // chosen project_id rides the create-user POST body.
    fireEvent.change(screen.getByLabelText(/^project$/i), {
      target: { value: "project-1" },
    });
    // Pick a deterministic timezone (the default is the env's browser zone).
    fireEvent.change(screen.getByLabelText(/timezone/i), {
      target: { value: "UTC" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sync user/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/users",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            email: "new.user@example.com",
            display_name: "New User",
            role: "project_admin",
            timezone: "UTC",
            conversation_language: "en",
            project_id: "project-1",
          }),
        }),
      ),
    );

    // Membership management has moved to the Project Admin dashboard — the admin
    // Users panel no longer offers per-user project assignment.
    const userCard = screen
      .getByText("Member User")
      .closest("li") as HTMLElement;
    expect(
      within(userCard).queryByRole("combobox", {
        name: /select project for member user/i,
      }),
    ).not.toBeInTheDocument();
    expect(
      within(userCard).queryByRole("button", { name: /assign project/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByTitle("User menu"));
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
    // The dashboard must NOT falsely report "User created successfully". A 409 now maps
    // to kind "conflict" in the API client, which surfaces the display-safe server
    // `detail` ("User already exists") instead of the generic fallback.
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
        if (url === "/api/admin/discovered-models") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        if (url === "/api/admin/model-scores") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
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
    fireEvent.change(screen.getByLabelText(/name \(optional\)/i), {
      target: { value: "Existing User" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sync user/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/users",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    // The duplicate-email 409 detail is display-safe and now surfaced to the user.
    const banner = await screen.findByText("User already exists");
    expect(banner).toBeInTheDocument();

    // No false success and no leaked internals (stack traces, raw DB errors).
    expect(
      screen.queryByText(/user created successfully/i),
    ).not.toBeInTheDocument();
    expect(banner.textContent).not.toMatch(/traceback|integrityerror|sql/i);
  });

  it("surfaces a safe error when creating a duplicate project (409) and does not report success", async () => {
    // Story 8.3 AC2 / Story 15.1 AC4: a duplicate project name is rejected with 409
    // { detail: "Project name already exists" }. The dashboard must NOT falsely report
    // "Project created successfully". A 409 now maps to kind "conflict" in the API
    // client, which surfaces the display-safe server `detail` instead of the generic copy.
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
        if (url === "/api/admin/discovered-models") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        if (url === "/api/admin/model-scores") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
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
    fireEvent.click(screen.getByRole("button", { name: /create project/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/projects",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    // The duplicate-name 409 detail is display-safe and now surfaced to the user.
    const banner = await screen.findByText("Project name already exists");
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
      if (url === "/api/admin/discovered-models") return jsonResponse([]);
      if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
      if (url === "/api/admin/model-scores") return jsonResponse([]);
      if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
      return jsonResponse({}, 404);
    }

    it("renders the Run E2E Tests button", async () => {
      renderDashboard(defaultFetch);

      await screen.findByRole("heading", { name: /admin dashboard/i });
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
        if (url === "/api/admin/discovered-models") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        if (url === "/api/admin/model-scores") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        return jsonResponse({}, 404);
      });

      await screen.findByRole("heading", { name: /admin dashboard/i });
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
            status: "completed",
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
        status: "completed",
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
          return jsonResponse({
            status: "running",
            exit_code: null,
            passed: null,
            report_available: false,
            stdout: "",
            stderr: "",
          });
        if (url === "/api/admin/tests/e2e/status") return jsonResponse(e2eResult);
        if (url === "/api/admin/discovered-models") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        if (url === "/api/admin/model-scores") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        return jsonResponse({}, 404);
      });

      await screen.findByRole("heading", { name: /admin dashboard/i });
      fireEvent.click(screen.getByRole("button", { name: /run e2e tests/i }));

      await waitFor(() =>
        expect(screen.getByText(/all tests passed/i)).toBeInTheDocument(),
      );
      expect(screen.queryByText(/tests are running/i)).not.toBeInTheDocument();
    });

    it("shows failed result when E2E tests fail", async () => {
      const e2eResult = {
        status: "completed",
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
          return jsonResponse({
            status: "running",
            exit_code: null,
            passed: null,
            report_available: false,
            stdout: "",
            stderr: "",
          });
        if (url === "/api/admin/tests/e2e/status") return jsonResponse(e2eResult);
        if (url === "/api/admin/discovered-models") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        if (url === "/api/admin/model-scores") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        return jsonResponse({}, 404);
      });

      await screen.findByRole("heading", { name: /admin dashboard/i });
      fireEvent.click(screen.getByRole("button", { name: /run e2e tests/i }));

      await waitFor(() =>
        expect(screen.getByText(/tests failed/i)).toBeInTheDocument(),
      );
      expect(screen.getByText(/exit code 1/i)).toBeInTheDocument();
    });

    it("shows download button when report is available", async () => {
      const e2eResult = {
        status: "completed",
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
          return jsonResponse({
            status: "running",
            exit_code: null,
            passed: null,
            report_available: false,
            stdout: "",
            stderr: "",
          });
        if (url === "/api/admin/tests/e2e/status") return jsonResponse(e2eResult);
        if (url === "/api/admin/discovered-models") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        if (url === "/api/admin/model-scores") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        return jsonResponse({}, 404);
      });

      await screen.findByRole("heading", { name: /admin dashboard/i });
      fireEvent.click(screen.getByRole("button", { name: /run e2e tests/i }));

      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: /download zip/i }),
        ).toBeInTheDocument(),
      );
    });

    it("hides download button when report is not available", async () => {
      const e2eResult = {
        status: "completed",
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
          return jsonResponse({
            status: "running",
            exit_code: null,
            passed: null,
            report_available: false,
            stdout: "",
            stderr: "",
          });
        if (url === "/api/admin/tests/e2e/status") return jsonResponse(e2eResult);
        if (url === "/api/admin/discovered-models") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        if (url === "/api/admin/model-scores") return jsonResponse([]);
        if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
        return jsonResponse({}, 404);
      });

      await screen.findByRole("heading", { name: /admin dashboard/i });
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

// These tests use the same global-fetch spy pattern as the suite above (real
// apiFetch + AuthProvider). They previously used file-wide vi.mock() which
// vitest 4 hoists across the whole file, stubbing apiFetch and breaking the
// fetch-spy tests above.
const jiraProject = {
  ...project,
  id: "project-jira",
  name: "Test Project",
  confluence_base_url: null,
  jira_base_url: "https://jira.example.com",
  enabled_providers: ["claude", "gemini"],
  memberships: [],
  membership_count: 0,
};

function mockAdminFetch(projects: unknown[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url === "/auth/status")
      return jsonResponse({
        authenticated: true,
        email: "admin@example.com",
        name: "Admin User",
        role: "admin",
      });
    if (url === "/api/projects") return jsonResponse(projects);
    if (url === "/api/admin/users") return jsonResponse([]);
    if (url === "/api/admin/discovered-models") return jsonResponse([]);
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    if (url === "/api/admin/model-scores") return jsonResponse([]);
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    return jsonResponse({}, 404);
  });
}

test("AdminDashboard project form is name + description only (config moved to project admin)", async () => {
  mockAdminFetch([]);

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  await screen.findByLabelText(/project name/i);
  expect(screen.getByLabelText(/description/i)).toBeInTheDocument();

  // Confluence/Jira/provider editors are no longer in the admin form.
  expect(
    screen.queryByPlaceholderText("https://jira.company.com"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByPlaceholderText("https://confluence.company.com"),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("checkbox", { name: /^claude$/i })).not.toBeInTheDocument();
});

test("AdminDashboard project list no longer shows project config (Jira/providers)", async () => {
  mockAdminFetch([jiraProject]);

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  // The card shows the name + member count, but config is owned by the project admin.
  expect(await screen.findByText("Test Project")).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: /jira\.example\.com/i }),
  ).not.toBeInTheDocument();
});

test("AdminDashboard edit project form is name + description only", async () => {
  mockAdminFetch([jiraProject]);

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  fireEvent.click(await screen.findByRole("button", { name: /edit test project/i }));

  // Name is pre-populated; the Jira field + provider checkboxes are gone.
  expect(await screen.findByDisplayValue("Test Project")).toBeInTheDocument();
  expect(
    screen.queryByDisplayValue("https://jira.example.com"),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("checkbox", { name: /claude/i })).not.toBeInTheDocument();
});

test("AdminDashboard omits obsolete 'project admin' helper copy (Story 15.2)", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url === "/auth/status")
      return jsonResponse({
        authenticated: true,
        email: "admin@example.com",
        name: "Admin User",
        role: "admin",
      });
    if (url === "/api/projects") return jsonResponse([project]);
    if (url === "/api/admin/users") return jsonResponse([user]);
    if (url === "/api/admin/discovered-models") return jsonResponse([]);
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    if (url === "/api/admin/model-scores") return jsonResponse([]);
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    return jsonResponse({}, 404);
  });

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  // A non-admin user row is present and the Create Project form is shown — none of the
  // obsolete "…by the project admin" helper sentences should render anywhere.
  await screen.findByText("Member User");
  expect(
    screen.queryByText(/managed by the project admin/i),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText(/configured by the project admin/i),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText(/membership is managed by the project admin/i),
  ).not.toBeInTheDocument();
});

test("Models & Benchmarks section discovers + syncs scores via the Sync button (no manual form)", async () => {
  const unbenchmarked = {
    model_id: "inference-mysteryco-9-700b",
    display_name: "Mystery",
    supports_vision: false,
    last_seen_at: "2026-06-18T00:00:00Z",
    tier_source: "parsed",
    unbenchmarked: true,
    scores: [],
  };
  const benchmarked = {
    ...unbenchmarked,
    tier_source: "admin",
    unbenchmarked: false,
    scores: [
      {
        id: "s1",
        model_id: "inference-mysteryco-9-700b",
        capability: "global",
        score: 72.5,
        note: "Synced from llm-stats.com on 2026-06-21",
        updated_by_user_id: null,
        updated_at: "2026-06-21T00:00:00Z",
      },
    ],
  };
  const syncResult = {
    providers: [
      {
        provider_id: "on-premises",
        connected: true,
        skipped: false,
        models_found: 1,
        error: null,
      },
      {
        provider_id: "claude",
        connected: false,
        skipped: true,
        models_found: 0,
        error: "No server key configured.",
      },
    ],
    models_discovered: 1,
    models_benchmarked: 1,
    models_unbenchmarked: 0,
    scores_written: 1,
    benchmark_source_available: true,
    warnings: [],
  };
  let discoveredCalls = 0;
  let syncCalled = false;
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url === "/auth/status")
      return jsonResponse({
        authenticated: true,
        email: "admin@example.com",
        name: "Admin User",
        role: "admin",
      });
    if (url === "/api/projects") return jsonResponse([]);
    if (url === "/api/admin/users") return jsonResponse([]);
    if (url === "/api/admin/discovered-models") {
      discoveredCalls += 1;
      // First load shows the unbenchmarked model; after sync it has scores.
      return jsonResponse([discoveredCalls === 1 ? unbenchmarked : benchmarked]);
    }
    if (url === "/api/admin/models/sync" && init?.method === "POST") {
      syncCalled = true;
      return jsonResponse(syncResult);
    }
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    return jsonResponse({}, 404);
  });

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  // The model is listed and flagged unbenchmarked initially.
  const modelCell = await screen.findByText("inference-mysteryco-9-700b");
  const row = modelCell.closest("tr");
  expect(row).not.toBeNull();
  expect(within(row as HTMLElement).getByText("No benchmark")).toBeInTheDocument();

  // The manual scoring form is gone (replaced by the Sync action).
  expect(
    screen.queryByLabelText("Score for inference-mysteryco-9-700b"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText(/How to score — where to get the numbers/i),
  ).not.toBeInTheDocument();

  // Click Sync -> POST fires, result panel renders, table refreshes with scores.
  fireEvent.click(
    screen.getByRole("button", { name: /sync models and benchmarks/i }),
  );

  await waitFor(() => expect(syncCalled).toBe(true));

  const resultPanel = await screen.findByTestId("model-sync-result");
  expect(resultPanel.textContent).toMatch(/Discovered 1 model/i);
  expect(resultPanel.textContent).toMatch(/on-premises/);
  expect(resultPanel.textContent).toMatch(/skipped/);

  // Table refreshed from the second discovered-models load: score shown, flag gone.
  await waitFor(() =>
    expect(screen.queryByText("No benchmark")).not.toBeInTheDocument(),
  );
  expect(screen.getByText("72.5")).toBeInTheDocument();
});

test("Models table sorts by global → reasoning → coding → vision (desc)", async () => {
  const ts = "2026-06-21T00:00:00Z";
  const score = (modelId: string, capability: string, value: number) => ({
    id: `${modelId}-${capability}`,
    model_id: modelId,
    capability,
    score: value,
    note: null,
    updated_by_user_id: null,
    updated_at: ts,
  });
  const mk = (modelId: string, scores: ReturnType<typeof score>[]) => ({
    model_id: modelId,
    display_name: modelId,
    supports_vision: false,
    last_seen_at: ts,
    tier_source: "admin",
    unbenchmarked: false,
    scores,
  });
  // a-high wins on global; m-mid and z-low tie on global(50) so reasoning breaks it.
  const models = [
    mk("z-low", [score("z-low", "global", 50)]),
    mk("a-high", [score("a-high", "global", 90)]),
    mk("m-mid", [score("m-mid", "global", 50), score("m-mid", "reasoning", 80)]),
  ];

  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url === "/auth/status")
      return jsonResponse({
        authenticated: true,
        email: "admin@example.com",
        name: "Admin User",
        role: "admin",
      });
    if (url === "/api/projects") return jsonResponse([]);
    if (url === "/api/admin/users") return jsonResponse([]);
    if (url === "/api/admin/discovered-models") return jsonResponse(models);
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    return jsonResponse({}, 404);
  });

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  await screen.findByText("a-high");
  const order = screen
    .getAllByText(/^(a-high|m-mid|z-low)$/)
    .map((n) => n.textContent);
  expect(order).toEqual(["a-high", "m-mid", "z-low"]);
});

test("vision tag follows the vision SCORE, not the gateway supports_vision flag", async () => {
  const ts = "2026-06-21T00:00:00Z";
  const score = (modelId: string, capability: string, value: number) => ({
    id: `${modelId}-${capability}`,
    model_id: modelId,
    capability,
    score: value,
    note: null,
    updated_by_user_id: null,
    updated_at: ts,
  });
  const models = [
    // gpt-oss: gateway flag TRUE but no vision score -> NO vision tag.
    {
      model_id: "inference-gpt-oss-120b",
      display_name: "inference-gpt-oss-120b",
      supports_vision: true,
      last_seen_at: ts,
      tier_source: "admin",
      unbenchmarked: false,
      scores: [score("inference-gpt-oss-120b", "global", 28.3)],
    },
    // gemma: gateway flag FALSE but HAS a vision score -> vision tag shown.
    {
      model_id: "inference-gemma4-31b",
      display_name: "inference-gemma4-31b",
      supports_vision: false,
      last_seen_at: ts,
      tier_source: "admin",
      unbenchmarked: false,
      scores: [
        score("inference-gemma4-31b", "global", 29.4),
        score("inference-gemma4-31b", "vision", 80),
      ],
    },
  ];

  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url === "/auth/status")
      return jsonResponse({
        authenticated: true,
        email: "admin@example.com",
        name: "Admin User",
        role: "admin",
      });
    if (url === "/api/projects") return jsonResponse([]);
    if (url === "/api/admin/users") return jsonResponse([]);
    if (url === "/api/admin/discovered-models") return jsonResponse(models);
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    return jsonResponse({}, 404);
  });

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  const gemmaCell = (await screen.findByText("inference-gemma4-31b")).closest("td")!;
  const gptCell = screen.getByText("inference-gpt-oss-120b").closest("td")!;
  // gemma has a vision score -> tag shown even though its gateway flag is false.
  expect(within(gemmaCell).getByText("vision")).toBeInTheDocument();
  // gpt-oss has no vision score -> tag NOT shown even though its gateway flag is true.
  expect(within(gptCell).queryByText("vision")).not.toBeInTheDocument();
});

test("Create User shows the project picker only for Project Admin (Story 15.3)", async () => {
  mockAdminFetch([project, assignableProject]);

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  // Wait until projects have loaded (they appear in the Projects panel).
  await screen.findByText("Admin Project");
  // Standard role (default): no project picker.
  expect(screen.queryByLabelText(/^project$/i)).not.toBeInTheDocument();

  // Switching to Project Admin reveals a project picker listing the projects.
  fireEvent.change(screen.getByLabelText(/^role$/i), {
    target: { value: "project_admin" },
  });
  const picker = screen.getByLabelText(/^project$/i) as HTMLSelectElement;
  expect(picker).toBeInTheDocument();
  const optionLabels = Array.from(picker.options).map((o) => o.textContent);
  expect(optionLabels).toContain("Admin Project");

  // Switching back to Standard removes it again.
  fireEvent.change(screen.getByLabelText(/^role$/i), {
    target: { value: "standard" },
  });
  expect(screen.queryByLabelText(/^project$/i)).not.toBeInTheDocument();
});

test("Create User blocks Project Admin when no projects exist (Story 15.3)", async () => {
  mockAdminFetch([]);

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  await screen.findByLabelText(/^role$/i);
  fireEvent.change(screen.getByLabelText(/^role$/i), {
    target: { value: "project_admin" },
  });

  expect(
    screen.getByText(/create a project first before adding a project admin/i),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /sync user/i })).toBeDisabled();
});

test("Users Management sorts by role/status/name and shows admin projects (Story 15.4)", async () => {
  const ts = "2026-01-01T00:00:00Z";
  const usersFixture = [
    {
      id: "u-zoe",
      email: "zoe@example.com",
      display_name: "Zoe Standard",
      role: "standard",
      is_active: true,
      timezone: "UTC",
      project_memberships: [],
      created_at: ts,
      updated_at: ts,
    },
    {
      id: "u-aaron",
      email: "aaron@example.com",
      display_name: "Aaron Standard",
      role: "standard",
      is_active: false,
      timezone: "UTC",
      project_memberships: [],
      created_at: ts,
      updated_at: ts,
    },
    {
      id: "u-admin",
      email: "admin@example.com",
      display_name: "Platform Admin",
      role: "admin",
      is_active: true,
      timezone: "UTC",
      project_memberships: [],
      created_at: ts,
      updated_at: ts,
    },
    {
      id: "u-pa",
      email: "pa@example.com",
      display_name: "Pat ProjectAdmin",
      role: "project_admin",
      is_active: true,
      timezone: "UTC",
      project_memberships: [
        {
          id: "m1",
          project_id: "p1",
          project_name: "Alpha",
          role: "project_admin",
          created_at: ts,
          updated_at: ts,
        },
      ],
      created_at: ts,
      updated_at: ts,
    },
  ];

  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url === "/auth/status")
      return jsonResponse({
        authenticated: true,
        email: "admin@example.com",
        name: "Admin User",
        role: "admin",
      });
    if (url === "/api/projects") return jsonResponse([]);
    if (url === "/api/admin/users") return jsonResponse(usersFixture);
    if (url === "/api/admin/discovered-models") return jsonResponse([]);
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    if (url === "/api/admin/model-scores") return jsonResponse([]);
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    return jsonResponse({}, 404);
  });

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  await screen.findByText("Platform Admin");

  // Order: admin → project_admin → standard; within standard, active (Zoe) before
  // inactive (Aaron) even though Aaron sorts first alphabetically.
  const names = screen
    .getAllByText(
      /^(Platform Admin|Pat ProjectAdmin|Zoe Standard|Aaron Standard)$/,
    )
    .map((n) => n.textContent);
  expect(names).toEqual([
    "Platform Admin",
    "Pat ProjectAdmin",
    "Zoe Standard",
    "Aaron Standard",
  ]);

  // The project_admin row shows its administered project name.
  expect(screen.getByText(/Admin of: Alpha/i)).toBeInTheDocument();

  // Status is conveyed with text (+icon), not color alone.
  expect(screen.getAllByText("Active").length).toBeGreaterThan(0);
  expect(screen.getByText("Inactive")).toBeInTheDocument();
});

test("Users Management: delete hidden for admin row, PUT/DELETE fire (Story 15.5)", async () => {
  const ts = "2026-01-01T00:00:00Z";
  const adminRow = {
    id: "u-admin",
    email: "admin@example.com",
    display_name: "Platform Admin",
    role: "admin",
    is_active: true,
    timezone: "UTC",
    project_memberships: [],
    created_at: ts,
    updated_at: ts,
  };
  const standardRow = {
    id: "u-std",
    email: "std@example.com",
    display_name: "Stan Dard",
    role: "standard",
    is_active: true,
    timezone: "UTC",
    project_memberships: [],
    created_at: ts,
    updated_at: ts,
  };

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
      if (url === "/api/admin/users") return jsonResponse([adminRow, standardRow]);
      if (url === "/api/admin/users/u-std" && init?.method === "PUT")
        return jsonResponse({ ...standardRow, display_name: "Stan Updated" });
      if (url === "/api/admin/users/u-std" && init?.method === "DELETE")
        return Promise.resolve(new Response(null, { status: 204 }));
      if (url === "/api/admin/discovered-models") return jsonResponse([]);
      if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
      if (url === "/api/admin/model-scores") return jsonResponse([]);
      if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
      return jsonResponse({}, 404);
    });

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  await screen.findByText("Stan Dard");

  // Platform admin row exposes edit controls, but NO delete controls.
  expect(
    screen.queryByRole("button", { name: /edit user platform admin/i }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /delete user platform admin/i }),
  ).not.toBeInTheDocument();

  // The non-admin row has distinct user edit/delete controls (no collision with the
  // project card's "Edit X"/"Delete X" labels).
  const editBtn = screen.getByRole("button", { name: /edit user stan dard/i });
  fireEvent.click(editBtn);

  fireEvent.change(
    screen.getByLabelText(/display name/i, {
      selector: "input#edit-user-name-u-std",
    }),
    { target: { value: "Stan Updated" } },
  );
  fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/users/u-std",
      expect.objectContaining({ method: "PUT" }),
    ),
  );

  const deleteBtn = await screen.findByRole("button", {
    name: /delete user stan dard/i,
  });
  fireEvent.click(deleteBtn);
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/users/u-std",
      expect.objectContaining({ method: "DELETE" }),
    ),
  );
});

test("editing a project_admin shows a pre-checked multi-select and saves project_ids (Story 23.5)", async () => {
  const ts = "2026-01-01T00:00:00Z";
  const projectOne = { ...project, id: "project-1", name: "Project One" };
  const projectTwo = { ...project, id: "project-2", name: "Project Two" };
  const paUser = {
    id: "u-pa",
    email: "pa@example.com",
    display_name: "Pat Admin",
    role: "project_admin",
    is_active: true,
    timezone: "UTC",
    project_memberships: [
      {
        id: "m-1",
        project_id: "project-1",
        project_name: "Project One",
        role: "project_admin",
        created_at: ts,
        updated_at: ts,
      },
    ],
    created_at: ts,
    updated_at: ts,
  };

  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation((input, init) => {
      const url = String(input);
      if (url === "/auth/status")
        return jsonResponse({
          authenticated: true,
          email: "admin@example.com",
          name: "Admin",
          role: "admin",
        });
      if (url === "/api/projects") return jsonResponse([projectOne, projectTwo]);
      if (url === "/api/admin/users") return jsonResponse([paUser]);
      if (url === "/api/admin/users/u-pa" && init?.method === "PUT")
        return jsonResponse(paUser);
      if (url === "/api/admin/discovered-models") return jsonResponse([]);
      if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
      if (url === "/api/admin/model-scores") return jsonResponse([]);
      if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
      return jsonResponse({}, 404);
    });

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  await screen.findByText("Pat Admin");
  fireEvent.click(screen.getByRole("button", { name: /edit user pat admin/i }));

  // The administered-project multi-select is shown with the current project pre-checked.
  const one = await screen.findByRole("checkbox", { name: "Project One" });
  const two = screen.getByRole("checkbox", { name: "Project Two" });
  expect((one as HTMLInputElement).checked).toBe(true);
  expect((two as HTMLInputElement).checked).toBe(false);

  // Add the second project and save.
  fireEvent.click(two);
  fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/users/u-pa",
      expect.objectContaining({ method: "PUT" }),
    ),
  );
  const putCall = fetchMock.mock.calls.find(
    (c) => c[0] === "/api/admin/users/u-pa" && c[1]?.method === "PUT",
  );
  expect(putCall).toBeTruthy();
  const body = JSON.parse(String(putCall![1]!.body));
  expect(new Set(body.project_ids)).toEqual(
    new Set(["project-1", "project-2"]),
  );
});

test("editing a standard user shows no project picker (Story 23.5)", async () => {
  const ts = "2026-01-01T00:00:00Z";
  const stdUser = {
    id: "u-s",
    email: "s@example.com",
    display_name: "Sam Standard",
    role: "standard",
    is_active: true,
    timezone: "UTC",
    project_memberships: [],
    created_at: ts,
    updated_at: ts,
  };
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url === "/auth/status")
      return jsonResponse({
        authenticated: true,
        email: "admin@example.com",
        name: "Admin",
        role: "admin",
      });
    if (url === "/api/projects")
      return jsonResponse([{ ...project, id: "project-1", name: "Project One" }]);
    if (url === "/api/admin/users") return jsonResponse([stdUser]);
    if (url === "/api/admin/discovered-models") return jsonResponse([]);
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    if (url === "/api/admin/model-scores") return jsonResponse([]);
    if (url === "/api/admin/config") return jsonResponse({ enable_model_benchmark_sync: true });
    return jsonResponse({}, 404);
  });

  render(
    <AuthProvider>
      <ProjectProvider>
        <AdminDashboard />
      </ProjectProvider>
    </AuthProvider>,
  );

  await screen.findByText("Sam Standard");
  fireEvent.click(screen.getByRole("button", { name: /edit user sam standard/i }));
  // No administered-project checkbox for a standard user.
  expect(
    screen.queryByRole("checkbox", { name: "Project One" }),
  ).not.toBeInTheDocument();
});
