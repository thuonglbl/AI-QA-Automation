import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App, { artifactNoticeTypeFor } from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProjectProvider } from "@/contexts/ProjectContext";

const websocketMock = vi.hoisted(() => ({
  projectIds: [] as Array<string | null>,
  threadIds: [] as Array<string | null>,
  sentMessages: [] as unknown[],
  messageQueue: [] as unknown[],
  messages: [] as unknown[],
  isLoaded: true,
  isConnectedOverride: null as boolean | null,
}));

vi.mock("@/hooks/useWebSocket", () => ({
  useWebSocket: (params: {
    projectId?: string | null;
    threadId?: string | null;
  }) => {
    const projectId = params?.projectId ?? null;
    const threadId = params?.threadId ?? null;
    websocketMock.projectIds.push(projectId);
    websocketMock.threadIds.push(threadId);
    return {
      isConnected:
        websocketMock.isConnectedOverride !== null
          ? websocketMock.isConnectedOverride
          : Boolean(projectId || threadId),
      error: null,
      lastMessage: null,
      messageQueue: websocketMock.messageQueue,
      messages: websocketMock.messages,
      isLoaded: websocketMock.isLoaded,
      consumeMessages: (count: number) => {
        websocketMock.messageQueue = websocketMock.messageQueue.slice(count);
      },
      sendMessage: (message: unknown) => {
        // Mirror the real hook: messages are only sent when a project/thread
        // scope is active, and the active scope ids are attached to the payload.
        if (!projectId && !threadId) return;
        let payload = message as Record<string, unknown> | unknown;
        if (typeof message === "object" && message !== null) {
          payload = { ...(message as Record<string, unknown>) };
          if (projectId) {
            (payload as Record<string, unknown>).projectId = projectId;
            (payload as Record<string, unknown>).project_id = projectId;
          }
          if (threadId) {
            (payload as Record<string, unknown>).threadId = threadId;
            (payload as Record<string, unknown>).thread_id = threadId;
          }
        }
        websocketMock.sentMessages.push(payload);
      },
      reconnect: vi.fn(),
      onRawEvent: vi.fn(),
    };
  },
}));

const pipelineStateMock = vi.hoisted(() => ({
  currentStep: 1,
  status: "idle",
  messages: [] as unknown[],
  isLoaded: true,
  updateFromMessage: vi.fn(),
  addUserMessage: vi.fn(),
}));

vi.mock("@/hooks/usePipelineState", () => ({
  usePipelineState: () => ({
    currentStep: pipelineStateMock.currentStep,
    status: pipelineStateMock.status,
    messages: pipelineStateMock.messages,
    isLoaded: pipelineStateMock.isLoaded,
    updateFromMessage: pipelineStateMock.updateFromMessage,
    addUserMessage: pipelineStateMock.addUserMessage,
  }),
}));

// Tracks the per-project starter-thread bootstrap (GET/POST /threads).
const threadMock = vi.hoisted(() => ({
  existing: [] as Array<Record<string, unknown>>,
  created: [] as Array<Record<string, unknown>>,
  postedProjectIds: [] as Array<string | null>,
  postCount: 0,
}));

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) =>
        name.toLowerCase() === "content-type" ? "application/json" : null,
    },
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  } as unknown as Response);
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

const secondProject = {
  ...project,
  id: "project-2",
  name: "Finance Automation",
};

function mockFetchForUser(projects: Array<Record<string, unknown>>) {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();

      if (url === "/auth/status") {
        return jsonResponse({
          authenticated: true,
          id: "user-1",
          email: "member@example.com",
          name: "Member",
          role: "user",
        });
      }
      if (url === "/api/projects") {
        return jsonResponse(projects);
      }
      if (url.startsWith("/api/projects/") && url.endsWith("/artifacts")) {
        return jsonResponse([]);
      }
      if (url.startsWith("/api/projects/") && url.endsWith("/artifacts/tree")) {
        return jsonResponse({ folders: [], files: [] });
      }
      if (url === "/api/threads") {
        if (method === "POST") {
          const body = init?.body ? JSON.parse(String(init.body)) : {};
          threadMock.postCount += 1;
          threadMock.postedProjectIds.push(body.project_id ?? null);
          const now = new Date(
            2026,
            0,
            1,
            0,
            0,
            threadMock.postCount,
          ).toISOString();
          const thread = {
            id: `thread-${body.project_id ?? "unbound"}-${threadMock.postCount}`,
            user_id: body.user_id ?? "user-1",
            project_id: body.project_id ?? null,
            title: null,
            is_archived: false,
            created_at: now,
            updated_at: now,
            current_step: 1,
            status: "start",
          };
          threadMock.created.push(thread);
          return jsonResponse(thread);
        }
        return jsonResponse([...threadMock.existing, ...threadMock.created]);
      }
      return jsonResponse({}, 404);
    },
  );
}

function renderApp() {
  return render(
    <AuthProvider>
      <ProjectProvider>
        <App />
      </ProjectProvider>
    </AuthProvider>,
  );
}

describe("App auth and workspace shell routing", () => {
  beforeEach(() => {
    window.localStorage?.clear();
    vi.restoreAllMocks();
    websocketMock.projectIds = [];
    websocketMock.threadIds = [];
    websocketMock.sentMessages = [];
    websocketMock.messageQueue = [];
    websocketMock.messages = [];
    websocketMock.isLoaded = true;
    websocketMock.isConnectedOverride = null;
    pipelineStateMock.currentStep = 1;
    pipelineStateMock.status = "idle";
    pipelineStateMock.messages = [];
    pipelineStateMock.isLoaded = true;
    threadMock.existing = [];
    threadMock.created = [];
    threadMock.postedProjectIds = [];
    threadMock.postCount = 0;
  });

  it("shows the login flow instead of the pipeline for unauthenticated users", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input) === "/auth/status") {
        return jsonResponse({ authenticated: false });
      }
      return jsonResponse({}, 404);
    });

    renderApp();

    // SSO-only login screen (Epic 23): a single "Sign in with SSO" button, no pipeline.
    expect(
      await screen.findByRole("button", { name: /sign in with sso/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Browser Use Cloud/i)).not.toBeInTheDocument();
  });

  it("shows the no-access message and creates no thread for zero accessible projects (AC4)", async () => {
    mockFetchForUser([]);

    renderApp();

    expect(
      await screen.findByText(
        "You do not have access to any project yet. Please contact an administrator to assign you to a project.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Which AI provider would you like to use/i),
    ).not.toBeInTheDocument();
    // No starter thread is created when there are no accessible projects.
    expect(threadMock.postCount).toBe(0);
  });

  it("ensures a starter thread for the single project and lands on Alice's provider step, no chooser (AC1/AC2)", async () => {
    mockFetchForUser([project]);

    renderApp();

    await waitFor(() => {
      expect(
        screen.getByText(/Which AI provider would you like to use/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/Browser Use Cloud/i)).toBeInTheDocument();
    // The chooser is gone entirely.
    expect(
      screen.queryByText(/Please select one project to proceed/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/admin dashboard/i)).not.toBeInTheDocument();
    // Exactly one starter thread, bound to the only project.
    await waitFor(() => expect(threadMock.postCount).toBe(1));
    expect(threadMock.postedProjectIds).toEqual([project.id]);
  });

  it("ensures one starter thread per project for multi-project users and never renders the chooser (AC2)", async () => {
    mockFetchForUser([project, secondProject]);

    renderApp();

    // Lands directly on the provider step for the active thread's bound project.
    await waitFor(() =>
      expect(
        screen.getByText(/Which AI provider would you like to use/i),
      ).toBeInTheDocument(),
    );
    // The "select a project" chooser is never rendered.
    expect(
      screen.queryByText(/Please select one project to proceed/i),
    ).not.toBeInTheDocument();
    // One starter thread per accessible project (both lacked a thread).
    await waitFor(() => expect(threadMock.postCount).toBe(2));
    expect(new Set(threadMock.postedProjectIds)).toEqual(
      new Set([project.id, secondProject.id]),
    );
  });

  it("does not create duplicate starters for projects that already have a thread (AC2)", async () => {
    threadMock.existing = [
      {
        id: "existing-thread-1",
        user_id: "user-1",
        project_id: project.id,
        title: null,
        is_archived: false,
        created_at: "2026-01-02T00:00:00Z",
        updated_at: "2026-01-02T00:00:00Z",
        current_step: 1,
        status: "start",
      },
    ];
    mockFetchForUser([project, secondProject]);

    renderApp();

    await waitFor(() =>
      expect(
        screen.getByText(/Which AI provider would you like to use/i),
      ).toBeInTheDocument(),
    );
    // Only the project without a thread gets a new starter.
    await waitFor(() => expect(threadMock.postCount).toBe(1));
    expect(threadMock.postedProjectIds).toEqual([secondProject.id]);
  });

  it("scopes the websocket by the active thread once a starter is bound (AC3)", async () => {
    mockFetchForUser([project]);

    renderApp();

    await waitFor(() =>
      expect(
        screen.getByText(/Which AI provider would you like to use/i),
      ).toBeInTheDocument(),
    );
    // The websocket connects via the thread id (thread-scoped), not a project chooser.
    await waitFor(() =>
      expect(
        websocketMock.threadIds.some((id) => id && id.startsWith("thread-")),
      ).toBe(true),
    );
  });

  it("creates an additional project-bound thread when New Conversation (+) is clicked (AC1/AC3)", async () => {
    mockFetchForUser([project]);

    renderApp();

    // Wait for the per-project starter bootstrap to settle (one thread).
    await waitFor(() => expect(threadMock.postCount).toBe(1));
    expect(threadMock.postedProjectIds).toEqual([project.id]);

    // The per-project "+" action lives in the sidebar's Conversations folder.
    const newConversationButton = await screen.findByTitle("New Conversation");
    fireEvent.click(newConversationButton);

    // A fresh thread is created, bound to the same project, with no chooser.
    await waitFor(() => expect(threadMock.postCount).toBe(2));
    expect(threadMock.postedProjectIds).toEqual([project.id, project.id]);
    expect(
      screen.queryByText(/Please select one project to proceed/i),
    ).not.toBeInTheDocument();
  });

  it("shows admin dashboard directly for admin users, bypassing the workspace shell (AC5)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/auth/status") {
        return jsonResponse({
          authenticated: true,
          id: "admin-1",
          email: "admin@example.com",
          name: "Admin",
          role: "admin",
        });
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

    await waitFor(() =>
      expect(screen.getByText(/admin dashboard/i)).toBeInTheDocument(),
    );
    expect(
      screen.queryByText(/Please select one project to proceed/i),
    ).not.toBeInTheDocument();
    // Admins never enter the thread/project flow.
    expect(threadMock.postCount).toBe(0);
  });

  it("lands a multi-role (admin+standard) user on the workspace with entitled dashboard links, and switches view on click (Epic 23)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/auth/status") {
        return jsonResponse({
          authenticated: true,
          id: "multi-1",
          email: "boss@example.com",
          name: "Boss",
          role: "admin",
          roles: ["admin", "standard"],
        });
      }
      if (url === "/api/projects") {
        return jsonResponse([{ ...project, current_user_role: null }]);
      }
      if (url === "/api/admin/users") return jsonResponse([]);
      if (url.endsWith("/artifacts")) return jsonResponse([]);
      if (url.includes("/artifacts/tree")) return jsonResponse({ folders: [], files: [] });
      if (url === "/api/threads") return jsonResponse([]);
      if (url === "/api/admin/discovered-models") return jsonResponse([]);
      if (url === "/api/admin/model-scores") return jsonResponse([]);
      return jsonResponse({}, 404);
    });

    renderApp();

    // Default landing = workspace (NOT the admin dashboard) for a user who also
    // holds the standard role — even though they are an admin.
    const userMenuButton = await screen.findByTitle("User menu");
    fireEvent.click(userMenuButton);
    const adminLink = await screen.findByRole("button", {
      name: "Admin Dashboard",
    });
    expect(adminLink).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Project Admin Dashboard" }),
    ).toBeInTheDocument();
    // The admin dashboard heading is not shown until they navigate.
    expect(
      screen.queryByRole("heading", { name: /admin dashboard/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(adminLink);

    // Clicking the link switches the view to the Admin Dashboard.
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /admin dashboard/i }),
      ).toBeInTheDocument(),
    );
    // And it offers a way back to the workspace.
    fireEvent.click(screen.getByTitle("User menu"));
    expect(
      screen.getByRole("button", { name: /back to workspace/i }),
    ).toBeInTheDocument();
  });

  it("shows no dashboard links for a standard-only user (Epic 23)", async () => {
    mockFetchForUser([project]);
    renderApp();
    await waitFor(() =>
      expect(
        screen.getByText(/Which AI provider would you like to use/i),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTitle("User menu"));
    expect(
      screen.queryByRole("button", { name: "Admin Dashboard" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Project Admin Dashboard" }),
    ).not.toBeInTheDocument();
  });

  it("keeps a standard user in the workspace shell when navigating directly to /admin, never rendering the admin dashboard (Story 8.1 AC2)", async () => {
    // Represent a direct /admin URL entry. The SPA is a render-switch with no
    // router, so the path is irrelevant — the same <App /> renders and falls
    // through to the workspace shell because role !== "admin".
    window.history.pushState({}, "", "/admin");

    // Standard user (role: "user") with one accessible project.
    mockFetchForUser([project]);

    renderApp();

    // Lands on the standard workspace (Alice provider step), not the dashboard.
    await waitFor(() =>
      expect(
        screen.getByText(/Which AI provider would you like to use/i),
      ).toBeInTheDocument(),
    );
    // The admin dashboard is never rendered for a non-admin at /admin.
    expect(screen.queryByText(/admin dashboard/i)).not.toBeInTheDocument();

    // Restore the path so it does not leak into sibling tests.
    window.history.pushState({}, "", "/");
  });

  it("shows the no-access workspace message for a standard user at /admin with zero projects, not the admin dashboard (Story 8.1 AC2)", async () => {
    window.history.pushState({}, "", "/admin");

    // Standard user with no accessible projects.
    mockFetchForUser([]);

    renderApp();

    // The zero-project no-access message renders (workspace shell), never the
    // admin dashboard.
    expect(
      await screen.findByText(
        "You do not have access to any project yet. Please contact an administrator to assign you to a project.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/admin dashboard/i)).not.toBeInTheDocument();
    // No admin-only flow side effects: no starter thread is bootstrapped.
    expect(threadMock.postCount).toBe(0);

    window.history.pushState({}, "", "/");
  });
});

describe("Bob confirm parent URL popup", () => {
  beforeEach(() => {
    window.localStorage?.clear();
    vi.restoreAllMocks();
    websocketMock.projectIds = [];
    websocketMock.threadIds = [];
    websocketMock.sentMessages = [];
    websocketMock.messageQueue = [];
    websocketMock.isLoaded = true;
    websocketMock.isConnectedOverride = null;
    pipelineStateMock.currentStep = 1;
    pipelineStateMock.status = "idle";
    pipelineStateMock.messages = [];
    pipelineStateMock.isLoaded = true;
    // Fresh spy so we can assert exactly what was echoed to the chat this test.
    pipelineStateMock.addUserMessage = vi.fn();
    threadMock.existing = [];
    threadMock.created = [];
    threadMock.postedProjectIds = [];
    threadMock.postCount = 0;
  });

  it("shows the confirm-parent popup when Bob sends the is_confirm_parent signal", async () => {
    mockFetchForUser([project]);
    websocketMock.isConnectedOverride = true;

    const { rerender } = renderApp();

    // 1. Advance past Alice step (Step 1) - lands directly on provider step.
    expect(
      await screen.findByText(/Which AI provider would you like to use/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Browser Use Cloud/i));
    fireEvent.change(
      screen.getByPlaceholderText(/personal API key/i),
      {
        target: { value: "test-key" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    // 2. Simulate being on the Bob step (step 2) and status review_request
    pipelineStateMock.currentStep = 2;
    pipelineStateMock.status = "review_request";

    // Inject a Bob message asking to confirm parent into the live queue
    websocketMock.messageQueue = [
      ...websocketMock.messageQueue,
      {
        id: "msg-1",
        sender: "agent",
        agentName: "Bob",
        metadata: {
          is_confirm_parent: true,
          suggested_page:
            "https://test.atlassian.net/wiki/spaces/TEST/pages/123/Requirements",
        },
        timestamp: new Date().toISOString(),
      },
    ];

    rerender(
      <AuthProvider>
        <ProjectProvider>
          <App />
        </ProjectProvider>
      </AuthProvider>,
    );

    // Verify popup appears with correct suggested URL
    expect(
      await screen.findByText(
        /I found the link below with all the requirements/i,
      ),
    ).toBeInTheDocument();

    const input = screen.getByPlaceholderText(
      /Enter a parent page URL, or leave blank to skip/i,
    ) as HTMLInputElement;
    expect(input.value).toBe(
      "https://test.atlassian.net/wiki/spaces/TEST/pages/123/Requirements",
    );

    // Edit URL and click OK
    fireEvent.change(input, {
      target: {
        value: "https://test.atlassian.net/wiki/spaces/TEST/pages/999/New",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "OK" }));

    // Verify correct message was sent via WebSocket.
    // handleBobApproveParent sends type="approve" step=2 with data.confirmed_page_name.
    await waitFor(() => {
      const lastMessage = websocketMock.sentMessages[
        websocketMock.sentMessages.length - 1
      ] as Record<string, unknown>;
      expect(lastMessage?.type).toBe("approve");
    });
    const sent = websocketMock.sentMessages[
      websocketMock.sentMessages.length - 1
    ] as Record<string, unknown>;
    expect(sent.step).toBe(2);
    // Thread-scoped: the active thread id is attached to the payload.
    expect(String(sent.thread_id)).toMatch(/^thread-/);
    expect((sent.data as Record<string, unknown>).confirmed_page_name).toBe(
      "https://test.atlassian.net/wiki/spaces/TEST/pages/999/New",
    );
    // Regression: the submitted URL must be echoed as a user chat bubble so it
    // stays visible after the confirm-parent panel unmounts.
    expect(pipelineStateMock.addUserMessage).toHaveBeenCalledWith(
      "https://test.atlassian.net/wiki/spaces/TEST/pages/999/New",
    );

    // And it must survive the chat render filter — the link the bug actually
    // lived in. Simulate the hook appending the echoed bubble, then assert it
    // renders as a "You" bubble instead of being filtered/collapsed away.
    pipelineStateMock.messages = [
      {
        id: "user-parent-echo",
        sender: "user",
        content: "https://test.atlassian.net/wiki/spaces/TEST/pages/999/New",
        timestamp: new Date().toISOString(),
        messageType: "text",
      },
    ];
    rerender(
      <AuthProvider>
        <ProjectProvider>
          <App />
        </ProjectProvider>
      </AuthProvider>,
    );
    expect(
      await screen.findByText(
        "https://test.atlassian.net/wiki/spaces/TEST/pages/999/New",
      ),
    ).toBeInTheDocument();
  });

  it("shows a Continue button on a resume_available message and sends a resume start action", async () => {
    mockFetchForUser([project]);
    websocketMock.isConnectedOverride = true;

    const { rerender } = renderApp();

    // Advance past Alice onto the Bob step.
    expect(
      await screen.findByText(/Which AI provider would you like to use/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Browser Use Cloud/i));
    fireEvent.change(screen.getByPlaceholderText(/personal API key/i), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    // Bob step reset to "start" by the reconciler, with a resume_available message.
    pipelineStateMock.currentStep = 2;
    pipelineStateMock.status = "start";
    pipelineStateMock.messages = [
      {
        id: "msg-resume-1",
        sender: "system",
        content:
          "⚠ The previous run was interrupted because the server restarted. " +
          "Click Continue to resume from where it stopped, or start this step again.",
        timestamp: new Date().toISOString(),
        messageType: "warning",
        metadata: { resume_available: true },
      },
    ];
    rerender(
      <AuthProvider>
        <ProjectProvider>
          <App />
        </ProjectProvider>
      </AuthProvider>,
    );

    const continueBtn = await screen.findByRole("button", { name: "Continue" });
    fireEvent.click(continueBtn);

    // handleBobContinue sends type="start" step=2 with inputData.resume === true.
    await waitFor(() => {
      const last = websocketMock.sentMessages[
        websocketMock.sentMessages.length - 1
      ] as Record<string, unknown>;
      expect(last?.type).toBe("start");
    });
    const sent = websocketMock.sentMessages[
      websocketMock.sentMessages.length - 1
    ] as Record<string, unknown>;
    expect(sent.step).toBe(2);
    expect((sent.inputData as Record<string, unknown>).resume).toBe(true);
  });

  it("sends a skip action when the parent link is left blank", async () => {
    mockFetchForUser([project]);
    websocketMock.isConnectedOverride = true;

    const { rerender } = renderApp();

    expect(
      await screen.findByText(/Which AI provider would you like to use/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Browser Use Cloud/i));
    fireEvent.change(screen.getByPlaceholderText(/personal API key/i), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    pipelineStateMock.currentStep = 2;
    pipelineStateMock.status = "review_request";
    websocketMock.messageQueue = [
      ...websocketMock.messageQueue,
      {
        id: "msg-skip-1",
        sender: "agent",
        agentName: "Bob",
        metadata: {
          is_confirm_parent: true,
          suggested_page:
            "https://test.atlassian.net/wiki/spaces/TEST/pages/123/Requirements",
        },
        timestamp: new Date().toISOString(),
      },
    ];

    rerender(
      <AuthProvider>
        <ProjectProvider>
          <App />
        </ProjectProvider>
      </AuthProvider>,
    );

    // With a suggested page present, the button still reads OK. Clear the field
    // so it becomes a Skip action, then click it.
    const input = (await screen.findByPlaceholderText(
      /Enter a parent page URL, or leave blank to skip/i,
    )) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "Skip" }));

    await waitFor(() => {
      const last = websocketMock.sentMessages[
        websocketMock.sentMessages.length - 1
      ] as Record<string, unknown>;
      expect(last?.type).toBe("approve");
    });
    const sent = websocketMock.sentMessages[
      websocketMock.sentMessages.length - 1
    ] as Record<string, unknown>;
    expect(sent.step).toBe(2);
    expect((sent.data as Record<string, unknown>).action).toBe("skip");
    expect((sent.data as Record<string, unknown>).confirmed_page_name).toBeUndefined();
    // Regression: the skip action is echoed as a user chat bubble too.
    expect(pipelineStateMock.addUserMessage).toHaveBeenCalledWith("Skip");
  });
});

describe("provider selection persists a restorable, secret-free marker", () => {
  beforeEach(() => {
    window.localStorage?.clear();
    vi.restoreAllMocks();
    websocketMock.projectIds = [];
    websocketMock.threadIds = [];
    websocketMock.sentMessages = [];
    websocketMock.messageQueue = [];
    websocketMock.messages = [];
    websocketMock.isLoaded = true;
    websocketMock.isConnectedOverride = true;
    pipelineStateMock.currentStep = 1;
    pipelineStateMock.status = "idle";
    pipelineStateMock.messages = [];
    pipelineStateMock.isLoaded = true;
    // Fresh spy so we can assert exactly what was persisted this test.
    pipelineStateMock.addUserMessage = vi.fn();
    threadMock.existing = [];
    threadMock.created = [];
    threadMock.postedProjectIds = [];
    threadMock.postCount = 0;
  });

  it("records a provider_selection marker (id + name, no credentials) on select", async () => {
    mockFetchForUser([project]);

    renderApp();

    expect(
      await screen.findByText(/Which AI provider would you like to use/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Browser Use Cloud/i));
    fireEvent.change(screen.getByPlaceholderText(/personal API key/i), {
      target: { value: "super-secret-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    await waitFor(() => {
      expect(pipelineStateMock.addUserMessage).toHaveBeenCalledWith(
        expect.stringContaining("Browser Use Cloud"),
        "info",
        expect.objectContaining({
          type: "provider_selection",
          providerId: "browser-use-cloud",
          providerName: "Browser Use Cloud",
        }),
      );
    });

    // The marker must never carry the credentials (no secret leakage into history).
    const markerCall = pipelineStateMock.addUserMessage.mock.calls.find(
      (c: unknown[]) =>
        (c[2] as { type?: string } | undefined)?.type === "provider_selection",
    );
    expect(markerCall?.[2]).not.toHaveProperty("credentials");
    expect(JSON.stringify(markerCall)).not.toContain("super-secret-key");
  });
});

describe("artifactNoticeTypeFor", () => {
  it("maps the backend past-tense 'deleted' to the delete notice", () => {
    expect(artifactNoticeTypeFor("deleted")).toBe("delete");
  });

  it("accepts a defensive 'delete' alias", () => {
    expect(artifactNoticeTypeFor("delete")).toBe("delete");
  });

  it("maps 'updated' and 'created' to the update notice", () => {
    expect(artifactNoticeTypeFor("updated")).toBe("update");
    expect(artifactNoticeTypeFor("created")).toBe("update");
  });

  it("defaults unknown or missing change types to the update notice", () => {
    expect(artifactNoticeTypeFor("moved")).toBe("update");
    expect(artifactNoticeTypeFor(undefined)).toBe("update");
  });
});

describe("16.6 AC3 — Accessibility", () => {
  it("renders a skip to main content link and a main landmark", async () => {
    mockFetchForUser([]);
    renderApp();
    
    // Wait for the app to render past loading state
    await waitFor(() => {
      expect(screen.queryByText(/Loading.../)).not.toBeInTheDocument();
    });
    
    // Check for skip link
    const skipLink = await screen.findByRole("link", { name: /Skip to main content/i });
    expect(skipLink).toBeInTheDocument();
    expect(skipLink).toHaveAttribute("href", "#main-content");
    
    // Check for main landmark
    const mainRegion = await screen.findByRole("main");
    expect(mainRegion).toHaveAttribute("id", "main-content");
  });
});
