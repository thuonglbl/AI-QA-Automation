import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProjectProvider } from "@/contexts/ProjectContext";

// Mirrors App.test.tsx's hoisted mock conventions: a single shared mock object
// captures the WebSocket scope, the live message queue, and every outbound
// message so assertions can inspect what the App actually sent.
const websocketMock = vi.hoisted(() => ({
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
        // Mirror the real hook: only send when a scope is active.
        if (!projectId && !threadId) return;
        let payload = message as Record<string, unknown> | unknown;
        if (typeof message === "object" && message !== null) {
          payload = { ...(message as Record<string, unknown>) };
          if (threadId) {
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

const threadMock = vi.hoisted(() => ({
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
      if (url === "/api/threads") {
        if (method === "POST") {
          const body = init?.body ? JSON.parse(String(init.body)) : {};
          threadMock.postCount += 1;
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
          return jsonResponse(thread);
        }
        return jsonResponse([]);
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

// Builds a 2-item Sarah script_review WS message (present-all transport, 13.5).
// The two items carry distinct `index` values so we can assert that App threads
// the SECOND item's index (not the array position blindly) to the backend.
function twoItemScriptReviewMessage() {
  const baseTestCase = {
    title: "TC",
    preconditions: [] as string[],
    steps: [] as unknown[],
    expected_results: [] as string[],
  };
  return {
    id: "sarah-review-1",
    sender: "agent",
    agentName: "Sarah",
    timestamp: new Date().toISOString(),
    metadata: {
      type: "script_review",
      scripts: [
        {
          index: 0,
          test_case: { ...baseTestCase, title: "First script" },
          script_content: "print('first')",
          script_language: "python",
          file_path: "first.py",
          confidence: 0.9,
          approved: false,
          status: "pending",
        },
        {
          index: 1,
          test_case: { ...baseTestCase, title: "Second script" },
          script_content: "print('second')",
          script_language: "python",
          file_path: "second.py",
          confidence: 0.4,
          approved: false,
          status: "pending",
        },
      ],
    },
  };
}

async function arriveAtSarahReview() {
  mockFetchForUser([project]);
  websocketMock.isConnectedOverride = true;

  const { rerender } = renderApp();

  // Advance past Alice so a thread is bound (sendMessage requires an active scope).
  expect(
    await screen.findByText(/Which AI provider would you like to use/i),
  ).toBeInTheDocument();

  // Now on Sarah's step (4) in review_request, with the 2-item payload queued.
  pipelineStateMock.currentStep = 4;
  pipelineStateMock.status = "review_request";
  websocketMock.messageQueue = [twoItemScriptReviewMessage()];

  rerender(
    <AuthProvider>
      <ProjectProvider>
        <App />
      </ProjectProvider>
    </AuthProvider>,
  );

  // Both scripts render; navigate to the SECOND one.
  expect(
    await screen.findByText(/Review Script \(1 of 2\)/i),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /next script/i }));
  expect(
    await screen.findByText(/Review Script \(2 of 2\)/i),
  ).toBeInTheDocument();
}

function lastSent() {
  return websocketMock.sentMessages[
    websocketMock.sentMessages.length - 1
  ] as Record<string, unknown>;
}

describe("App WS round-trip — index-addressable script review (13.5/13.6, C23)", () => {
  beforeEach(() => {
    window.localStorage?.clear();
    vi.restoreAllMocks();
    websocketMock.sentMessages = [];
    websocketMock.messageQueue = [];
    websocketMock.messages = [];
    websocketMock.isLoaded = true;
    websocketMock.isConnectedOverride = null;
    pipelineStateMock.currentStep = 1;
    pipelineStateMock.status = "idle";
    pipelineStateMock.messages = [];
    pipelineStateMock.isLoaded = true;
    threadMock.postCount = 0;
  });

  it("approving the SECOND script sends approve with that script's index and the edited content", async () => {
    await arriveAtSarahReview();

    // Edit the second script in the Edit pane so editedContent rides the approve.
    fireEvent.click(screen.getByRole("button", { name: /edit tab/i }));
    const textarea = screen.getByLabelText(
      "Edit script content",
    ) as HTMLTextAreaElement;
    expect(textarea.value).toBe("print('second')");
    fireEvent.change(textarea, { target: { value: "print('edited second')" } });

    fireEvent.click(screen.getByRole("button", { name: /^approve$/i }));

    await waitFor(() => expect(lastSent()?.type).toBe("approve"));
    const sent = lastSent();
    expect(sent.step).toBe(4);
    expect(String(sent.thread_id)).toMatch(/^thread-/);
    const data = sent.data as Record<string, unknown>;
    expect(data.action).toBe("approved");
    // The SECOND item's index (1), not a hardcoded 0.
    expect(data.script_index).toBe(1);
    expect(data.script_content).toBe("print('edited second')");
  });

  it("rejecting the SECOND script sends reject with that script's index and feedback", async () => {
    await arriveAtSarahReview();

    fireEvent.click(screen.getByRole("button", { name: /^reject$/i }));
    const feedback = screen.getByPlaceholderText(/what needs to be changed/i);
    fireEvent.change(feedback, { target: { value: "Use a stable selector" } });
    fireEvent.click(screen.getByRole("button", { name: /submit feedback/i }));

    await waitFor(() => expect(lastSent()?.type).toBe("reject"));
    const sent = lastSent();
    expect(sent.step).toBe(4);
    expect(sent.feedback).toBe("Use a stable selector");
    expect((sent.data as Record<string, unknown>).script_index).toBe(1);
  });

  it("skipping the SECOND script sends approve action=skip with that script's index", async () => {
    await arriveAtSarahReview();

    fireEvent.click(screen.getByRole("button", { name: /^skip$/i }));

    await waitFor(() => expect(lastSent()?.type).toBe("approve"));
    const sent = lastSent();
    expect(sent.step).toBe(4);
    const data = sent.data as Record<string, unknown>;
    expect(data.action).toBe("skip");
    expect(data.script_index).toBe(1);
  });
});
