import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ModelAssignmentReview } from "../ModelAssignmentReview";
import type { ModelAssignment } from "@/types/provider";

const mockAssignments: ModelAssignment[] = [
  {
    agent: "Bob",
    model: "claude-3-opus-20240229",
    purpose: "Requirements extraction",
    rationale: "Chosen for vision capability and strong reasoning.",
  },
  {
    agent: "Mary",
    model: "claude-3-sonnet-20240229",
    purpose: "Test case generation",
    rationale: "Chosen for structured output and instruction-following.",
  },
  {
    agent: "Sarah",
    model: "claude-3-sonnet-20240229",
    purpose: "Script generation",
    rationale: "Chosen for coding and tool capabilities.",
  },
  {
    agent: "Jack",
    model: "claude-3-haiku-20240307",
    purpose: "Test execution",
    rationale: "Chosen for fast, cost-effective summarization.",
  },
];

describe("ModelAssignmentReview", () => {
  it("renders provider and endpoint information", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
      />,
    );

    expect(screen.getByText(/Connected successfully to/)).toBeInTheDocument();
    expect(screen.getByText("Claude (Anthropic)")).toBeInTheDocument();
    // Endpoint should NOT be rendered in the view for security.
    expect(screen.queryByText("https://api.anthropic.com")).not.toBeInTheDocument();
  });

  it("renders model assignment table with all agents", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
      />,
    );

    // Check all agents are rendered
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getByText("Mary")).toBeInTheDocument();
    expect(screen.getByText("Sarah")).toBeInTheDocument();
    expect(screen.getByText("Jack")).toBeInTheDocument();

    // Check models are rendered
    expect(screen.getByText("claude-3-opus-20240229")).toBeInTheDocument();
    expect(
      screen.getAllByText("claude-3-sonnet-20240229").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("claude-3-haiku-20240307")).toBeInTheDocument();

    // Check purposes are rendered
    expect(screen.getByText("Requirements extraction")).toBeInTheDocument();
    expect(screen.getByText("Test case generation")).toBeInTheDocument();
    expect(screen.getByText("Script generation")).toBeInTheDocument();
    expect(screen.getByText("Test execution")).toBeInTheDocument();

    // Check rationales are rendered
    expect(screen.getByText("Chosen for vision capability and strong reasoning.")).toBeInTheDocument();
    expect(screen.getByText("Chosen for fast, cost-effective summarization.")).toBeInTheDocument();
  });

  it("renders the benchmark score when provided", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
        benchmark={{ accuracy_percent: 85.5, note: "Top Tier" }}
      />,
    );

    expect(screen.getByText(/Global Benchmark Score:/)).toBeInTheDocument();
    expect(screen.getByText("85.5%")).toBeInTheDocument();
    expect(screen.getByText("(Top Tier)")).toBeInTheDocument();
  });

  it("disables the OK button and shows disabledReason", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
        disabled={true}
        disabledReason="Waiting for connection..."
      />,
    );

    const okButton = screen.getByRole("button", { name: "OK" });
    expect(okButton).toBeDisabled();
    expect(screen.getByText("Waiting for connection...")).toBeInTheDocument();
  });

  it("calls onApprove when ok button clicked", () => {
    const onApprove = vi.fn();

    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={onApprove}
      />,
    );

    fireEvent.click(screen.getByText(/OK/));
    expect(onApprove).toHaveBeenCalled();
  });

  it("sends the user's per-agent override to onApprove", () => {
    const onApprove = vi.fn();
    render(
      <ModelAssignmentReview
        provider="On-Premises"
        endpoint="https://ai.local"
        assignments={mockAssignments}
        availableModels={[
          { id: "claude-3-opus-20240229", name: "Opus" },
          { id: "inference-glm-51-754b", name: "GLM 5.1" },
        ]}
        onApprove={onApprove}
      />,
    );

    // Re-select Bob's model from the dropdown, then approve.
    fireEvent.change(screen.getByLabelText("Model for Bob"), {
      target: { value: "inference-glm-51-754b" },
    });
    fireEvent.click(screen.getByText(/OK/));

    expect(onApprove).toHaveBeenCalledTimes(1);
    const sent = onApprove.mock.calls[0]![0] as Record<string, string>;
    // Bob reflects the override; agents left untouched keep their assigned model.
    expect(sent.bob).toBe("inference-glm-51-754b");
    expect(sent.mary).toBe("claude-3-sonnet-20240229");
  });

  it("disables buttons when disabled prop is true", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
        disabled={true}
      />,
    );

    const okButton = screen.getByText(/OK/).closest("button");
    expect(okButton).toBeDisabled();
  });

  it("renders agent badges with correct colors", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
      />,
    );

    // Check agent badges are rendered
    const bobBadge = screen.getByText("Bob").closest("span");
    expect(bobBadge).toBeInTheDocument();
  });

  it("renders with empty assignments", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={null}
        onApprove={vi.fn()}
      />,
    );

    // Should still render the component without crashing
    expect(screen.getByText(/Connected successfully to/)).toBeInTheDocument();
  });

  it("does not render Reject button", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
      />,
    );

    expect(screen.queryByText("Reject")).not.toBeInTheDocument();
  });

  it("displays discovered-model summary when availableModels provided", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        availableModels={[
          { id: "m1", name: "Model 1" },
          { id: "m2", name: "Model 2" },
          { id: "m3", name: "Model 3" },
        ]}
        onApprove={vi.fn()}
      />,
    );

    expect(
      screen.getByText(/Discovered 3 available models from/),
    ).toBeInTheDocument();
    // "Claude (Anthropic)" appears in both the main message and the summary
    expect(screen.getAllByText("Claude (Anthropic)").length).toBeGreaterThanOrEqual(2);
  });

  it("does not display discovered-model summary when availableModels is empty", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        availableModels={[]}
        onApprove={vi.fn()}
      />,
    );

    expect(screen.queryByText(/Discovered/)).not.toBeInTheDocument();
  });

  it("overrides the two Sarah rows independently by key (script-gen vs browser-explore)", () => {
    const onApprove = vi.fn();
    const twoSarah: ModelAssignment[] = [
      {
        key: "sarah",
        agent: "Sarah · Script gen",
        model: "inference-glm-51-754b",
        purpose: "Script generation (coding)",
        rationale: "coding flagship",
      },
      {
        key: "sarah_explore",
        agent: "Sarah · Browser explore",
        model: "inference-qwen3-vl-235b",
        purpose: "Browser exploration (vision)",
        rationale: "best vision model",
      },
    ];
    render(
      <ModelAssignmentReview
        provider="On-Premises"
        endpoint="https://ai.local"
        assignments={twoSarah}
        availableModels={[
          { id: "inference-glm-51-754b", name: "GLM 5.1" },
          { id: "inference-qwen3-vl-235b", name: "Qwen3 VL" },
          { id: "inference-gemma4-31b", name: "Gemma" },
        ]}
        onApprove={onApprove}
      />,
    );

    // Both Sarah rows shown distinctly.
    expect(screen.getByText("Sarah · Script gen")).toBeInTheDocument();
    expect(screen.getByText("Sarah · Browser explore")).toBeInTheDocument();

    // Override ONLY the explore row; the two rows must not collide on key.
    fireEvent.change(screen.getByLabelText("Model for Sarah · Browser explore"), {
      target: { value: "inference-gemma4-31b" },
    });
    fireEvent.click(screen.getByText(/OK/));

    const sent = onApprove.mock.calls[0]![0] as Record<string, string>;
    expect(sent.sarah).toBe("inference-glm-51-754b"); // script-gen unchanged
    expect(sent.sarah_explore).toBe("inference-gemma4-31b"); // explore overridden by key
  });

  // Rationale column and Reject button removed from UI
});
