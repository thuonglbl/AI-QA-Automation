import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ExecutionResultDetail } from "../agents/ExecutionResultDetail";
import type { ExecutionResult } from "@/types/execution";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

/** URL-aware fetch mock: artifact /content endpoints return a JSON ArtifactContent envelope
 * (base64 for binary, text for logs) so the component must DECODE it — pointing <img>/<a>
 * at the raw /content URL would not work, which is the bug this drilldown was fixed for. */
function mockContentFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/artifacts/shot-2/content"))
      return jsonResponse({
        artifact_id: "shot-2",
        version: 1,
        content: "iVBORw0KGgo=",
        content_encoding: "base64",
      });
    if (url.includes("/artifacts/trace-2/content"))
      return jsonResponse({
        artifact_id: "trace-2",
        version: 1,
        content: "UEsDBA==",
        content_encoding: "base64",
      });
    if (url.includes("/artifacts/log-1/content"))
      return jsonResponse({
        artifact_id: "log-1",
        version: 1,
        content: "run log line",
        content_encoding: "text",
      });
    return jsonResponse({});
  });
}

const FAILED: ExecutionResult = {
  test_name: "test_search",
  browser: "chromium",
  status: "failed",
  duration_ms: 1500,
  failure_classification: "assertion",
  error_message: "AssertionError: not visible",
  stack_trace: "expect(...).to_be_visible",
  source_script_artifact_id: "script-2",
  source_test_case_artifact_id: "tc-2",
};

beforeEach(() => {
  // jsdom does not implement URL.createObjectURL / revokeObjectURL.
  (URL as unknown as { createObjectURL: () => string }).createObjectURL = vi.fn(
    () => "blob:mock-trace",
  );
  (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = vi.fn();
});

afterEach(() => vi.restoreAllMocks());

describe("ExecutionResultDetail", () => {
  it("decodes the content endpoint for screenshot/trace rather than linking the raw JSON URL", async () => {
    mockContentFetch();
    render(
      <ExecutionResultDetail
        projectId="p1"
        result={FAILED}
        attachment={{ screenshot_id: "shot-2", trace_id: "trace-2", log_id: "log-1" }}
      />,
    );
    expect(screen.getByText(/Classification: assertion/i)).toBeInTheDocument();
    expect(screen.getByText(/AssertionError: not visible/i)).toBeInTheDocument();
    expect(screen.getByText(/expect\(\.\.\.\)\.to_be_visible/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open script/i })).toHaveAttribute(
      "href",
      "/api/projects/p1/artifacts/script-2/content",
    );

    // Screenshot is rendered from a decoded data: URL, NOT the raw /content endpoint.
    const img = await screen.findByRole("img", { name: /screenshot/i });
    expect(img.getAttribute("src")).toMatch(/^data:image\/png;base64,/);
    expect(img.getAttribute("src")).not.toContain("/content");

    // Trace download points at a decoded object URL, not the JSON content endpoint.
    const trace = await screen.findByRole("link", { name: /download trace/i });
    expect(trace).toHaveAttribute("href", "blob:mock-trace");

    // Log renders its decoded text inline after the user opens it.
    fireEvent.click(screen.getByRole("button", { name: /view log/i }));
    expect(await screen.findByText("run log line")).toBeInTheDocument();
  });

  it("renders '(not available)' for missing attachments and provenance", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({}));
    render(
      <ExecutionResultDetail
        projectId="p1"
        result={{ test_name: "test_x", browser: "chromium", status: "failed" }}
        attachment={{}}
      />,
    );
    const notAvailable = screen.getAllByText(/\(not available\)/i);
    // script + test case + screenshot + trace + log all unavailable
    expect(notAvailable.length).toBeGreaterThanOrEqual(4);
  });

  it("shows the per-test role in the header when present", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({}));
    render(
      <ExecutionResultDetail
        projectId="p1"
        result={{ test_name: "test_x", browser: "chromium", status: "passed", role: "Admin" }}
        attachment={{}}
      />,
    );
    expect(screen.getByText(/Admin/)).toBeInTheDocument();
  });
});
