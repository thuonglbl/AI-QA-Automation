/**
 * Story 10-3 (Task 6.2): Focused Vitest coverage for MermaidDiagram.
 *
 * - Renders SVG for a valid chart (mermaid.render is mocked for determinism).
 * - Falls back to <pre> block for an invalid chart (mermaid.render throws).
 * - Shows a "Rendering diagram..." placeholder while async render is in flight.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MermaidDiagram } from "../artifacts/MermaidDiagram";

// Mock the mermaid library for determinism (avoids DOM environment limitations).
vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(),
  },
}));

import mermaid from "mermaid";

const mockMermaid = mermaid as unknown as {
  initialize: ReturnType<typeof vi.fn>;
  render: ReturnType<typeof vi.fn>;
};

describe("MermaidDiagram", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders an SVG for a valid chart", async () => {
    const fakeSvg = '<svg id="mermaid-test"><text>diagram</text></svg>';
    mockMermaid.render.mockResolvedValueOnce({ svg: fakeSvg });

    render(<MermaidDiagram chart="graph TD; A-->B" />);

    // Initially shows placeholder while async render completes
    expect(screen.getByText(/Rendering diagram/i)).toBeInTheDocument();

    // After render resolves, the SVG should be injected
    await waitFor(() => {
      // Either approach: check that the placeholder is gone
      expect(screen.queryByText(/Rendering diagram/i)).not.toBeInTheDocument();
    });

    // The mermaid.render function should have been called with the chart
    expect(mockMermaid.render).toHaveBeenCalled();
    const call = mockMermaid.render.mock.calls[0] as [string, string];
    expect(call[1]).toBe("graph TD; A-->B");
  });

  it("falls back to <pre> block when mermaid.render throws (invalid source)", async () => {
    mockMermaid.render.mockRejectedValueOnce(new Error("Parse error"));

    const invalidChart = "this is not valid mermaid syntax $$$$";
    render(<MermaidDiagram chart={invalidChart} />);

    // After the error, should show the fallback pre block
    await waitFor(() => {
      expect(screen.getByText(/Diagram could not be rendered/i)).toBeInTheDocument();
    });

    // The raw chart source should be shown in a <pre>
    const pre = screen.getByText(invalidChart);
    expect(pre.tagName.toLowerCase()).toBe("pre");
  });

  it("passes the exact chart string to mermaid.render", async () => {
    mockMermaid.render.mockResolvedValueOnce({ svg: "<svg></svg>" });

    const chart = "sequenceDiagram\n  Alice->>Bob: Hello";
    render(<MermaidDiagram chart={chart} />);

    await waitFor(() => {
      expect(mockMermaid.render).toHaveBeenCalled();
    });

    const call = mockMermaid.render.mock.calls[0] as [string, string];
    expect(call[1]).toBe(chart);
  });
});
