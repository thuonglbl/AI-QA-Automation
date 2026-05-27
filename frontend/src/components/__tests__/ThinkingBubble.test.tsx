import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ThinkingBubble } from "../ThinkingBubble";
import type { ThinkingTrace } from "@/types/provider";

const mockTrace: ThinkingTrace = {
  connection_status: "success",
  available_models: [{ id: "model-1", name: "Model 1" }],
  bootstrap_model: "model-1",
  agent_needs: {},
  assignments: [
    { agent: "bob", rationale: "Needs reasoning" },
  ],
};

describe("ThinkingBubble", () => {
  it("renders collapsed by default", () => {
    render(<ThinkingBubble trace={mockTrace} />);
    expect(screen.getByText(/Alice's Reasoning Process/)).toBeInTheDocument();
    expect(screen.queryByText(/Connection Status/)).not.toBeInTheDocument();
  });

  it("expands when clicked", () => {
    render(<ThinkingBubble trace={mockTrace} />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    expect(screen.getByText(/✅ Success/)).toBeInTheDocument();
    expect(screen.getAllByText(/model-1/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Bob/)).toBeInTheDocument();
    expect(screen.getByText(/Needs reasoning/)).toBeInTheDocument();
  });

  it("renders initially expanded when initialExpanded is true", () => {
    render(<ThinkingBubble trace={mockTrace} initialExpanded={true} />);
    expect(screen.getByText(/✅ Success/)).toBeInTheDocument();
  });
});
