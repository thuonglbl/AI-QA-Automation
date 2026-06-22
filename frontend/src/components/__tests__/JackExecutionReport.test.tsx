import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { JackExecutionReport } from "../agents/JackExecutionReport";
import type { ExecutionDetail, ExecutionSummary } from "@/types/execution";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

const SUMMARY: ExecutionSummary = {
  run_id: "run-1",
  total: 2,
  passed: 1,
  failed: 1,
  errors: 0,
  skipped: 0,
  duration_ms: 4200,
  browsers: ["chromium"],
  unavailable_browsers: [],
  report_artifact_id: "report-1",
};

const DETAIL: ExecutionDetail = {
  summary: {
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
  },
  results: [
    { test_name: "test_login", browser: "chromium", status: "passed", duration_ms: 1200 },
    {
      test_name: "test_search",
      browser: "chromium",
      status: "failed",
      duration_ms: 1500,
      failure_classification: "assertion",
      error_message: "AssertionError",
      stack_trace: "expect(...).to_be_visible",
      source_script_artifact_id: "script-2",
    },
  ],
  attachments: {
    "test_search::chromium": { screenshot_id: "shot-2", trace_id: null, log_id: "log-1" },
  },
};

afterEach(() => vi.restoreAllMocks());

describe("JackExecutionReport", () => {
  it("renders summary counts + success rate", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse(DETAIL));
    render(<JackExecutionReport projectId="p1" summary={SUMMARY} />);
    expect(screen.getByText(/2 total/i)).toBeInTheDocument();
    expect(screen.getByText(/1 passed/i)).toBeInTheDocument();
    expect(screen.getByText(/50% pass/i)).toBeInTheDocument();
    // results table loads from the detail fetch
    expect(await screen.findByText("test_login")).toBeInTheDocument();
    expect(screen.getByText("test_search")).toBeInTheDocument();
  });

  it("opens the per-test drilldown on row select with linked script + decoded screenshot", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/artifacts/shot-2/content"))
        return jsonResponse({
          artifact_id: "shot-2",
          version: 1,
          content: "iVBORw0KGgo=",
          content_encoding: "base64",
        });
      return jsonResponse(DETAIL);
    });
    render(<JackExecutionReport projectId="p1" summary={SUMMARY} />);
    const row = await screen.findByText("test_search");
    fireEvent.click(row);
    // drilldown shows the linked script + the failure classification
    expect(await screen.findByText(/open script/i)).toBeInTheDocument();
    expect(screen.getByText(/Classification: assertion/i)).toBeInTheDocument();
    // screenshot is decoded to a data: URL (not the raw JSON content endpoint); trace null
    const img = await screen.findByRole("img", { name: /screenshot/i });
    expect(img.getAttribute("src")).toMatch(/^data:image\/png;base64,/);
    expect(screen.getAllByText(/\(not available\)/i).length).toBeGreaterThanOrEqual(1);
  });

  it("surfaces unavailable browsers", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse(DETAIL));
    render(
      <JackExecutionReport
        projectId="p1"
        summary={{
          ...SUMMARY,
          unavailable_browsers: [{ label: "webkit", reason: "not installed" }],
        }}
      />,
    );
    await waitFor(() => expect(screen.getByText(/Unavailable:/i)).toBeInTheDocument());
    expect(screen.getByText(/webkit/i)).toBeInTheDocument();
  });
});
