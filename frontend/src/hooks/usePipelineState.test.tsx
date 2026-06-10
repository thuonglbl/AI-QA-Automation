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
