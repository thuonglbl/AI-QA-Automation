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
  it("renders expanded by default when not completed", () => {
    render(<ThinkingBubble trace={mockTrace} />);
    expect(screen.getByText(/Alice's thought/i)).toBeInTheDocument();
    expect(screen.getByText(/Success/i)).toBeInTheDocument();
    expect(screen.getByText(/bob/i)).toBeInTheDocument();
  });

  it("collapses when clicked", () => {
    render(<ThinkingBubble trace={mockTrace} />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    expect(screen.queryByText(/Success/i)).not.toBeInTheDocument();
  });

  it("renders initially collapsed when isCompleted is true", () => {
    render(<ThinkingBubble trace={mockTrace} isCompleted={true} />);
    expect(screen.queryByText(/Success/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Complete/i)).toBeInTheDocument();
  });
});
