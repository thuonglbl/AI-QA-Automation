import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProjectProvider } from "@/contexts/ProjectContext";

const websocketMock = vi.hoisted(() => ({
  projectIds: [] as Array<string | null>,
  sentMessages: [] as unknown[],
  messageQueue: [] as unknown[],
  messages: [] as unknown[],
  isLoaded: true,
  isConnectedOverride: null as boolean | null,
}));

vi.mock("@/hooks/useWebSocket", () => ({
  useWebSocket: (projectId: string | null) => {
    websocketMock.projectIds.push(projectId);
    return {
      isConnected: websocketMock.isConnectedOverride !== null ? websocketMock.isConnectedOverride : Boolean(projectId),
      error: null,
      lastMessage: null,
      messageQueue: websocketMock.messageQueue,
      messages: websocketMock.messages,
      isLoaded: websocketMock.isLoaded,
      clearMessageQueue: () => {
        websocketMock.messageQueue = [];
      },
      sendMessage: (message: unknown) => {
        websocketMock.sentMessages.push(
          typeof message === "object" && message !== null && projectId
            ? { ...message, projectId, project_id: projectId }
            : message,
        );
      },
      reconnect: vi.fn(),
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

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) => name.toLowerCase() === "content-type" ? "application/json" : null
    },
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body))
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

function mockFetchForUser(projects: unknown[]) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url === "/auth/status") {
      return jsonResponse({ authenticated: true, email: "member@example.com", name: "Member", role: "user" });
    }
    if (url === "/api/projects") {
      return jsonResponse(projects);
    }
    return jsonResponse({}, 404);
  });
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

describe("App auth and Alice project resolution", () => {
  beforeEach(() => {
    window.localStorage?.clear();
    vi.restoreAllMocks();
    websocketMock.projectIds = [];
    websocketMock.sentMessages = [];
    websocketMock.messageQueue = [];
    websocketMock.messages = [];
    websocketMock.isLoaded = true;
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

  it("routes standard users directly to Alice and shows the no-access message for zero projects", async () => {
    mockFetchForUser([]);

    renderApp();

    expect(await screen.findByText("You do not have access to any project yet. Please contact an administrator to assign you to a project.")).toBeInTheDocument();
    expect(screen.queryByText(/Which AI provider would you like to use/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/choose where this run belongs/i)).not.toBeInTheDocument();
  });

  it("auto-selects the only project inside Alice before showing provider options", async () => {
    mockFetchForUser([project]);

    renderApp();

    expect(await screen.findByText("You have only one project called Shared QA Project. Auto proceed with this project.")).toBeInTheDocument();
    expect(await screen.findByText(/Which AI provider would you like to use/i)).toBeInTheDocument();
    expect(screen.getByText(/Browser Use Cloud/i)).toBeInTheDocument();
    expect(screen.queryByText(/choose where this run belongs/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/admin dashboard/i)).not.toBeInTheDocument();
  });

  it("lets users choose from multiple projects in Alice and records the selected project as a right-aligned user message", async () => {
    mockFetchForUser([project, secondProject]);

    renderApp();

    expect(await screen.findByText("Please select one project to proceed")).toBeInTheDocument();
    expect(screen.queryByText(/Which AI provider would you like to use/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Finance Automation" }));

    expect(await screen.findByText(/Which AI provider would you like to use/i)).toBeInTheDocument();
    const userMessage = (await screen.findAllByText("Finance Automation")).find((element) =>
      element.closest("div")?.className.includes("bg-[#3b82f6]"),
    );
    expect(userMessage).toBeDefined();
    expect(within(userMessage?.closest("div")?.parentElement as HTMLElement).getByText("You")).toBeInTheDocument();
  });

  it("does not treat a stored project id as resolved before Alice confirms the current session selection", async () => {
    window.localStorage.setItem("ai-qa-selected-project-id", project.id);
    mockFetchForUser([project, secondProject]);

    renderApp();

    expect(await screen.findByText("Please select one project to proceed")).toBeInTheDocument();
    expect(screen.queryByText(/Which AI provider would you like to use/i)).not.toBeInTheDocument();
    expect(websocketMock.projectIds).not.toContain(project.id);
  });

  it("uses the selected project id for the websocket connection and provider start payload", async () => {
    mockFetchForUser([project, secondProject]);

    renderApp();

    fireEvent.click(await screen.findByRole("button", { name: "Finance Automation" }));

    expect(await screen.findByText(/Which AI provider would you like to use/i)).toBeInTheDocument();
    await waitFor(() => expect(websocketMock.projectIds).toContain("project-2"));

    fireEvent.click(screen.getByText(/Browser Use Cloud/i));
    fireEvent.change(screen.getByPlaceholderText("Enter your Browser Use API key..."), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    await waitFor(() => expect(websocketMock.sentMessages).toHaveLength(1));
    const payload = websocketMock.sentMessages[0] as {
      projectId: string;
      project_id: string;
      inputData: { projectId: string; project_id: string };
    };
    expect(payload.projectId).toBe("project-2");
    expect(payload.project_id).toBe("project-2");
    expect(payload.inputData.projectId).toBe("project-2");
    expect(payload.inputData.project_id).toBe("project-2");
  });

  it("shows admin dashboard directly for admin users, bypassing project selection", async () => {
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

    await waitFor(() => expect(screen.getByText(/admin dashboard/i)).toBeInTheDocument());
    expect(screen.queryByText(/choose where this run belongs/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Please select one project to proceed/i)).not.toBeInTheDocument();
  });
});

describe("Bob confirm parent URL popup", () => {
  beforeEach(() => {
    window.localStorage?.clear();
    vi.restoreAllMocks();
    websocketMock.projectIds = [];
    websocketMock.sentMessages = [];
    websocketMock.messageQueue = [];
    websocketMock.isLoaded = true;
    websocketMock.isConnectedOverride = null;
    pipelineStateMock.currentStep = 1;
    pipelineStateMock.status = "idle";
    pipelineStateMock.messages = [];
    pipelineStateMock.isLoaded = true;
  });

  it("shows the confirm-parent popup when Bob sends the is_confirm_parent signal", async () => {
    mockFetchForUser([project]);
    websocketMock.isConnectedOverride = true;
    
    const { rerender } = renderApp();

    // 1. Advance past Alice step (Step 1)
    expect(await screen.findByText(/Which AI provider would you like to use/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Browser Use Cloud/i));
    fireEvent.change(screen.getByPlaceholderText("Enter your Browser Use API key..."), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    // 2. Simulate being on the Bob step (step 2) and status review_request
    // We update the hoisted mock state and trigger a re-render or wait for it to be picked up
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
          suggested_page: "https://test.atlassian.net/wiki/spaces/TEST/pages/123/Requirements"
        },
        timestamp: new Date().toISOString()
      }
    ];

    // Re-mount the app so the new mock values are read by usePipelineState.
    // Instead of unmount(), we use rerender() to preserve ProjectContext state!
    rerender(
      <AuthProvider>
        <ProjectProvider>
          <App />
        </ProjectProvider>
      </AuthProvider>
    );

    // Verify popup appears with correct suggested URL
    expect(await screen.findByText(/I found the below link contains all requirements/i)).toBeInTheDocument();
    
    const input = screen.getByPlaceholderText("Enter the correct page URL...") as HTMLInputElement;
    expect(input.value).toBe("https://test.atlassian.net/wiki/spaces/TEST/pages/123/Requirements");

    // Edit URL and click OK
    fireEvent.change(input, { target: { value: "https://test.atlassian.net/wiki/spaces/TEST/pages/999/New" } });
    fireEvent.click(screen.getByRole("button", { name: "OK" }));

    // Verify correct message was sent via WebSocket.
    // handleBobApproveParent sends type="approve" step=2 with data.confirmed_page_name.
    await waitFor(() => {
      const lastMessage = websocketMock.sentMessages[websocketMock.sentMessages.length - 1] as any;
      expect(lastMessage?.type).toBe("approve");
    });
    const sent = websocketMock.sentMessages[websocketMock.sentMessages.length - 1] as any;
    expect(sent.step).toBe(2);
    expect(sent.projectId).toBe(project.id);
    expect(sent.data.confirmed_page_name).toBe("https://test.atlassian.net/wiki/spaces/TEST/pages/999/New");
  });
});
