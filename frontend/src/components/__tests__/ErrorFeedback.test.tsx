import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ErrorFeedback } from "../ErrorFeedback";
import type { ErrorInfo } from "@/types/pipeline";

describe("ErrorFeedback", () => {
  const mockError: ErrorInfo = {
    type: "NETWORK_ERROR",
    what: "Lost connection to the server",
    why: "Your network connection was interrupted",
    whatToDo: "Check your internet connection and click Retry",
  };

  it("renders 3-part error structure", () => {
    render(<ErrorFeedback error={mockError} onRetry={() => {}} />);

    // What happened
    expect(screen.getByText(mockError.what)).toBeInTheDocument();
    // Why
    expect(screen.getByText(mockError.why)).toBeInTheDocument();
    // What to do
    expect(screen.getByText(mockError.whatToDo)).toBeInTheDocument();
  });

  it('has role="alert" for accessibility', () => {
    render(<ErrorFeedback error={mockError} onRetry={() => {}} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("renders retry button with correct label", () => {
    render(<ErrorFeedback error={mockError} onRetry={() => {}} />);

    const retryButton = screen.getByRole("button", {
      name: /retry this action/i,
    });
    expect(retryButton).toBeInTheDocument();
  });

  it("calls onRetry when retry button is clicked", () => {
    const onRetry = vi.fn();
    render(<ErrorFeedback error={mockError} onRetry={onRetry} />);

    const retryButton = screen.getByRole("button", {
      name: /retry this action/i,
    });
    fireEvent.click(retryButton);

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("retry button has primary button styling", () => {
    render(<ErrorFeedback error={mockError} onRetry={() => {}} />);

    const retryButton = screen.getByRole("button");
    expect(retryButton).toHaveClass("bg-blue-500");
  });

  it("displays error icon", () => {
    render(<ErrorFeedback error={mockError} onRetry={() => {}} />);

    // Alert icon should be present (aria-hidden)
    expect(document.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });

  it("has screen reader text with error type", () => {
    render(<ErrorFeedback error={mockError} onRetry={() => {}} />);

    expect(
      screen.getByText(`Error type: ${mockError.type}`),
    ).toBeInTheDocument();
    expect(screen.getByText(`Error type: ${mockError.type}`)).toHaveClass(
      "sr-only",
    );
  });

  it("applies custom className", () => {
    const { container } = render(
      <ErrorFeedback
        error={mockError}
        onRetry={() => {}}
        className="custom-class"
      />,
    );

    expect(container.firstChild).toHaveClass("custom-class");
  });

  it("renders all error types correctly", () => {
    const errorTypes: ErrorInfo["type"][] = [
      "MCP_TIMEOUT",
      "LLM_FAILURE",
      "NETWORK_ERROR",
      "CONFIG_ERROR",
      "UNKNOWN_ERROR",
    ];

    errorTypes.forEach((type) => {
      const { unmount } = render(
        <ErrorFeedback error={{ ...mockError, type }} onRetry={() => {}} />,
      );

      expect(screen.getByText(`Error type: ${type}`)).toBeInTheDocument();
      unmount();
    });
  });

  it("retry button has autoFocus", () => {
    render(<ErrorFeedback error={mockError} onRetry={() => {}} />);

    const retryButton = screen.getByRole("button");
    expect(retryButton).toHaveFocus();
  });
});
