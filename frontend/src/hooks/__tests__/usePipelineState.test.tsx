import { describe, it, expect, beforeEach, vi, Mock } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { usePipelineState } from "../usePipelineState";
import { apiFetch } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    kind: string;
    status: number;
    constructor(kind: string, message: string, status: number) {
      super(message);
      this.kind = kind;
      this.status = status;
    }
  },
}));

describe("usePipelineState reload persistence", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("identity survives a simulated reload", async () => {
    const mockThreadResponse = {
      current_step: 2,
      status: "processing",
      messages: [
        {
          id: "m1",
          sender: "agent",
          agent_name: "Bob",
          content: "I am working on it.",
          created_at: "2026-04-16T10:00:00Z",
          message_type: "text",
        },
      ],
    };

    (apiFetch as Mock).mockResolvedValueOnce(mockThreadResponse);

    const { result } = renderHook(() =>
      usePipelineState({ projectId: "p1", threadId: "t1" })
    );

    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });

    expect(result.current.currentAgent).toBe("Bob");
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]?.agentName).toBe("Bob");
  });
});
