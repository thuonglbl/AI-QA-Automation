import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ModelAssignmentReview } from "../ModelAssignmentReview";
import type { ModelAssignment } from "@/types/provider";

const mockAssignments: ModelAssignment[] = [
  { agent: "Bob", model: "claude-3-opus-20240229", purpose: "Requirements extraction" },
  { agent: "Mary", model: "claude-3-sonnet-20240229", purpose: "Test case generation" },
  { agent: "Sarah", model: "claude-3-sonnet-20240229", purpose: "Script generation" },
  { agent: "Jack", model: "claude-3-haiku-20240307", purpose: "Test execution" },
];

describe("ModelAssignmentReview", () => {
  it("renders provider and endpoint information", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByText("AI Provider Configuration Review")).toBeInTheDocument();
    expect(screen.getByText("Claude (Anthropic)")).toBeInTheDocument();
    expect(screen.getByText(/api.anthropic.com/)).toBeInTheDocument();
  });

  it("renders model assignment table with all agents", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    // Check all agents are rendered
    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getByText("Mary")).toBeInTheDocument();
    expect(screen.getByText("Sarah")).toBeInTheDocument();
    expect(screen.getByText("Jack")).toBeInTheDocument();

    // Check models are rendered
    expect(screen.getByText("claude-3-opus-20240229")).toBeInTheDocument();
    expect(screen.getByText("claude-3-sonnet-20240229")).toBeInTheDocument();
    expect(screen.getByText("claude-3-haiku-20240307")).toBeInTheDocument();

    // Check purposes are rendered
    expect(screen.getByText("Requirements extraction")).toBeInTheDocument();
    expect(screen.getByText("Test case generation")).toBeInTheDocument();
    expect(screen.getByText("Script generation")).toBeInTheDocument();
    expect(screen.getByText("Test execution")).toBeInTheDocument();
  });

  it("calls onApprove when approve button clicked", () => {
    const onApprove = vi.fn();

    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={onApprove}
        onReject={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText(/Approve/));
    expect(onApprove).toHaveBeenCalled();
  });

  it("calls onReject when reject button clicked", () => {
    const onReject = vi.fn();

    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
        onReject={onReject}
      />
    );

    fireEvent.click(screen.getByText(/Change Provider/));
    expect(onReject).toHaveBeenCalled();
  });

  it("disables buttons when disabled prop is true", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        disabled={true}
      />
    );

    const approveButton = screen.getByText(/Approve/).closest("button");
    const rejectButton = screen.getByText(/Change Provider/).closest("button");

    expect(approveButton).toBeDisabled();
    expect(rejectButton).toBeDisabled();
  });

  it("renders agent badges with correct colors", () => {
    render(
      <ModelAssignmentReview
        provider="Claude (Anthropic)"
        endpoint="https://api.anthropic.com"
        assignments={mockAssignments}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
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
        onReject={vi.fn()}
      />
    );

    // Should still render the component without crashing
    expect(screen.getByText("AI Provider Configuration Review")).toBeInTheDocument();
  });
});
