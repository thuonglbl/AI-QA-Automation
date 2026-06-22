import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { usePipelineState } from "@/hooks/usePipelineState";
import { ApiError } from "@/lib/api";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

describe("usePipelineState thread access denial (Story 7.6 AC3)", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    window.localStorage.clear();
  });

  it("invokes onThreadDenied when a thread fetch is forbidden (membership removed)", async () => {
    apiFetchMock.mockRejectedValue(
      new ApiError("forbidden", "forbidden", 403),
    );
    const onThreadDenied = vi.fn();

    renderHook(() =>
      usePipelineState({
        projectId: "project-1",
        threadId: "thread-1",
        onThreadDenied,
      }),
    );

    await waitFor(() => expect(onThreadDenied).toHaveBeenCalledWith("thread-1"));
  });

  it("invokes onThreadDenied when a thread fetch is not found (generic 404)", async () => {
    apiFetchMock.mockRejectedValue(
      new ApiError("not_found", "not found", 404),
    );
    const onThreadDenied = vi.fn();

    renderHook(() =>
      usePipelineState({
        projectId: null,
        threadId: "thread-1",
        onThreadDenied,
      }),
    );

    await waitFor(() => expect(onThreadDenied).toHaveBeenCalledWith("thread-1"));
  });

  it("does not treat a successful load as a denial", async () => {
    apiFetchMock.mockResolvedValue({
      current_step: 2,
      status: "review_request",
      messages: [],
      agent_runs: [],
    });
    const onThreadDenied = vi.fn();

    const { result } = renderHook(() =>
      usePipelineState({
        projectId: null,
        threadId: "thread-1",
        onThreadDenied,
      }),
    );

    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(onThreadDenied).not.toHaveBeenCalled();
    expect(result.current.currentStep).toBe(2);
  });

  it("does not fire denial for a project-only (no thread) forbidden response", async () => {
    // Without a threadId, a forbidden project conversation must NOT be treated
    // as a thread denial (the thread-denial recovery flow is thread-scoped).
    apiFetchMock.mockRejectedValue(
      new ApiError("forbidden", "forbidden", 403),
    );
    const onThreadDenied = vi.fn();

    const { result } = renderHook(() =>
      usePipelineState({
        projectId: "project-1",
        threadId: null,
        onThreadDenied,
      }),
    );

    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(onThreadDenied).not.toHaveBeenCalled();
  });
});

describe("usePipelineState thread-load mapping (cross-thread bleed fix)", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    window.localStorage.clear();
  });

  it("preserves message_metadata and maps real MessageResponse fields", async () => {
    // GET /threads/{id} returns MessageResponse rows: sender / agent_name /
    // content / message_type / message_metadata / created_at. The thread-load
    // branch must read those exact fields so the chat filter can hide
    // metadata-tagged carrier messages instead of leaking them as raw text.
    apiFetchMock.mockResolvedValue({
      current_step: 2,
      status: "review_request",
      messages: [
        {
          id: "m1",
          sender: "user",
          agent_name: null,
          content: "Hello",
          message_type: "text",
          message_metadata: null,
          created_at: "2026-06-18T10:00:00Z",
        },
        {
          id: "m2",
          sender: "agent",
          agent_name: "Alice",
          content: "Finished model assignment reasoning.",
          message_type: "info",
          message_metadata: { type: "thinking_trace", trace: {} },
          created_at: "2026-06-18T10:00:01Z",
        },
      ],
      agent_runs: [],
    });

    const { result } = renderHook(() =>
      usePipelineState({ projectId: null, threadId: "thread-1" }),
    );

    await waitFor(() => expect(result.current.isLoaded).toBe(true));

    const messages = result.current.messages;
    expect(messages).toHaveLength(2);
    // User message keeps the user side (not mislabeled "agent").
    expect(messages[0]!.sender).toBe("user");
    // Carrier message retains its metadata + real message_type + agent name.
    expect(messages[1]!.sender).toBe("agent");
    expect(messages[1]!.agentName).toBe("Alice");
    expect(messages[1]!.messageType).toBe("info");
    expect(messages[1]!.metadata).toEqual({ type: "thinking_trace", trace: {} });
  });

  it("exposes loadedThreadId set to the loaded thread after load completes", async () => {
    apiFetchMock.mockResolvedValue({
      current_step: 1,
      status: "review_request",
      messages: [],
      agent_runs: [],
    });

    const { result } = renderHook(() =>
      usePipelineState({ projectId: null, threadId: "thread-42" }),
    );

    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(result.current.loadedThreadId).toBe("thread-42");
  });
});
