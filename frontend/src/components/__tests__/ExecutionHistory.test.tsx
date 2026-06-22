import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ExecutionHistory } from "../agents/ExecutionHistory";
import type { ExecutionRunSummary } from "@/types/execution";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

function makeRun(overrides: Partial<ExecutionRunSummary> = {}): ExecutionRunSummary {
  return {
    run_id: "run-1",
    created_at: "2026-06-21T09:00:00Z",
    total: 2,
    passed: 1,
    failed: 1,
    errors: 0,
    skipped: 0,
    success_rate: 50,
    browsers: ["chromium"],
    unavailable_browsers: [],
    ...overrides,
  };
}

afterEach(() => vi.restoreAllMocks());

describe("ExecutionHistory", () => {
  it("lists runs from the executions API", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse([makeRun()]));
    render(<ExecutionHistory projectId="p1" />);
    expect(await screen.findByText(/chromium/i)).toBeInTheDocument();
    expect(screen.getByText(/50%/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no runs", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse([]));
    render(<ExecutionHistory projectId="p1" />);
    expect(await screen.findByText(/No execution runs yet/i)).toBeInTheDocument();
  });

  it("re-queries with the result filter", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() => jsonResponse([makeRun()]));
    render(<ExecutionHistory projectId="p1" />);
    await screen.findByText(/chromium/i);

    fireEvent.change(screen.getByLabelText(/Result filter/i), { target: { value: "failed" } });

    await waitFor(() => {
      const calledFailed = spy.mock.calls.some((c) => String(c[0]).includes("result=failed"));
      expect(calledFailed).toBe(true);
    });
  });

  it("calls onOpenRun when a run is selected", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse([makeRun()]));
    const onOpenRun = vi.fn();
    render(<ExecutionHistory projectId="p1" onOpenRun={onOpenRun} />);
    fireEvent.click(await screen.findByText(/chromium/i));
    expect(onOpenRun).toHaveBeenCalledWith(expect.objectContaining({ run_id: "run-1" }));
  });
});
