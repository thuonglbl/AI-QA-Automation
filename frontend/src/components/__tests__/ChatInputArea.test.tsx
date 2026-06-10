import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ChatInputArea } from "../ChatInputArea";
import type { ChatInputAreaProps } from "@/types/pipeline";

const defaultProps: ChatInputAreaProps = {
  state: "start",
  stepNumber: 1,
  isLastStep: false,
  inputConfig: {
    fields: [
      {
        name: "url",
        label: "Confluence URL",
        type: "url" as const,
        required: true,
        placeholder: "Enter URL",
      },
    ],
  },
  disabledReason: "Enter Confluence URL to start",
  onStart: vi.fn(),
  onApprove: vi.fn(),
  onReject: vi.fn(),
  onSubmitFeedback: vi.fn(),
  onContinue: vi.fn(),
};

describe("ChatInputArea", () => {
  describe("Start State (AC 1, 7)", () => {
    it("renders input fields and Start button", () => {
      render(<ChatInputArea {...defaultProps} />);

      expect(screen.getByLabelText(/Confluence URL/i)).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Start/i }),
      ).toBeInTheDocument();
    });

    it("disables Start button when required fields are empty", () => {
      render(<ChatInputArea {...defaultProps} />);

      const startButton = screen.getByRole("button", { name: /Start/i });
      expect(startButton).toBeDisabled();
    });

    it("enables Start button when required fields are filled", () => {
      render(<ChatInputArea {...defaultProps} />);

      const input = screen.getByLabelText(/Confluence URL/i);
      fireEvent.change(input, { target: { value: "https://example.com" } });

      const startButton = screen.getByRole("button", { name: /Start/i });
      expect(startButton).toBeEnabled();
    });

    it("calls onStart with input values when Start is clicked", () => {
      const onStart = vi.fn();
      render(<ChatInputArea {...defaultProps} onStart={onStart} />);

      const input = screen.getByLabelText(/Confluence URL/i);
      fireEvent.change(input, { target: { value: "https://example.com" } });

      const startButton = screen.getByRole("button", { name: /Start/i });
      fireEvent.click(startButton);

      expect(onStart).toHaveBeenCalledWith({ url: "https://example.com" });
    });

    it("shows validation error for invalid input", () => {
      const inputConfig = {
        fields: [
          {
            name: "email",
            label: "Email",
            type: "text" as const,
            required: true,
            validation: (value: string) =>
              value.includes("@") ? null : "Invalid email",
          },
        ],
      };

      render(<ChatInputArea {...defaultProps} inputConfig={inputConfig} />);

      const input = screen.getByLabelText(/Email/i);
      fireEvent.change(input, { target: { value: "invalid" } });

      const startButton = screen.getByRole("button", { name: /Start/i });
      fireEvent.click(startButton);

      expect(screen.getByText(/Invalid email/i)).toBeInTheDocument();
    });
  });

  describe("Processing State (AC 2)", () => {
    it("renders disabled overlay with working message", () => {
      render(<ChatInputArea {...defaultProps} state="processing" />);

      expect(screen.getByText(/Agent is working/i)).toBeInTheDocument();
    });

    it("does not render input controls", () => {
      render(<ChatInputArea {...defaultProps} state="processing" />);

      expect(
        screen.queryByLabelText(/Confluence URL/i),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Start/i }),
      ).not.toBeInTheDocument();
    });
  });

  describe("Review State (AC 3, 6, 8)", () => {
    it("renders Approve and Reject buttons", () => {
      render(<ChatInputArea {...defaultProps} state="review" />);

      expect(
        screen.getByRole("button", { name: /Approve/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Reject/i }),
      ).toBeInTheDocument();
    });

    it("calls onApprove when Approve is clicked", () => {
      const onApprove = vi.fn();
      render(
        <ChatInputArea
          {...defaultProps}
          state="review"
          onApprove={onApprove}
        />,
      );

      const approveButton = screen.getByRole("button", { name: /Approve/i });
      fireEvent.click(approveButton);

      expect(onApprove).toHaveBeenCalled();
    });

    it("calls onReject when Reject is clicked", () => {
      const onReject = vi.fn();
      render(
        <ChatInputArea {...defaultProps} state="review" onReject={onReject} />,
      );

      const rejectButton = screen.getByRole("button", { name: /Reject/i });
      fireEvent.click(rejectButton);

      expect(onReject).toHaveBeenCalled();
    });

    it("renders max 2 buttons (AC 6)", () => {
      render(<ChatInputArea {...defaultProps} state="review" />);

      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeLessThanOrEqual(2);
    });

    it("positions primary action (Approve) on the right (AC 6)", () => {
      render(<ChatInputArea {...defaultProps} state="review" />);

      const buttons = screen.getAllByRole("button");
      // Approve should be the second (rightmost) button
      expect(buttons[1]).toHaveTextContent(/Approve/i);
    });
  });

  describe("Reject Feedback State (AC 4)", () => {
    it("renders textarea and Submit button", () => {
      render(<ChatInputArea {...defaultProps} state="reject_feedback" />);

      expect(
        screen.getByPlaceholderText(/Describe what needs to be changed/i),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Submit/i }),
      ).toBeInTheDocument();
    });

    it("disables Submit button when feedback is empty", () => {
      render(<ChatInputArea {...defaultProps} state="reject_feedback" />);

      const submitButton = screen.getByRole("button", { name: /Submit/i });
      expect(submitButton).toBeDisabled();
    });

    it("enables Submit button when feedback is entered", () => {
      render(<ChatInputArea {...defaultProps} state="reject_feedback" />);

      const textarea = screen.getByPlaceholderText(
        /Describe what needs to be changed/i,
      );
      fireEvent.change(textarea, {
        target: { value: "Please fix this issue" },
      });

      const submitButton = screen.getByRole("button", { name: /Submit/i });
      expect(submitButton).toBeEnabled();
    });

    it("calls onSubmitFeedback with feedback text when Submit is clicked", () => {
      const onSubmitFeedback = vi.fn();
      render(
        <ChatInputArea
          {...defaultProps}
          state="reject_feedback"
          onSubmitFeedback={onSubmitFeedback}
        />,
      );

      const textarea = screen.getByPlaceholderText(
        /Describe what needs to be changed/i,
      );
      fireEvent.change(textarea, {
        target: { value: "Please fix this issue" },
      });

      const submitButton = screen.getByRole("button", { name: /Submit/i });
      fireEvent.click(submitButton);

      expect(onSubmitFeedback).toHaveBeenCalledWith("Please fix this issue");
    });

    it("shows character count", () => {
      render(<ChatInputArea {...defaultProps} state="reject_feedback" />);

      const textarea = screen.getByPlaceholderText(
        /Describe what needs to be changed/i,
      );
      fireEvent.change(textarea, { target: { value: "Test feedback" } });

      expect(screen.getByText(/13\/1000/i)).toBeInTheDocument();
    });
  });

  describe("Done State (AC 5)", () => {
    it("renders Continue button", () => {
      render(<ChatInputArea {...defaultProps} state="done" />);

      expect(
        screen.getByRole("button", { name: /Continue/i }),
      ).toBeInTheDocument();
    });

    it("shows Completed button for final step", () => {
      render(
        <ChatInputArea
          {...defaultProps}
          state="done"
          stepNumber={5}
          isLastStep={true}
        />,
      );

      expect(screen.getByText(/Completed/i)).toBeInTheDocument();
    });

    it("calls onContinue when Continue is clicked", () => {
      const onContinue = vi.fn();
      render(
        <ChatInputArea
          {...defaultProps}
          state="done"
          onContinue={onContinue}
        />,
      );

      const continueButton = screen.getByRole("button", { name: /Continue/i });
      fireEvent.click(continueButton);

      expect(onContinue).toHaveBeenCalled();
    });

    it("renders max 1 button for done state (AC 6)", () => {
      render(<ChatInputArea {...defaultProps} state="done" />);

      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeLessThanOrEqual(1);
    });
  });

  describe("Focus Management (AC 9)", () => {
    it("focuses primary action on state change to start", async () => {
      render(
        <ChatInputArea
          {...defaultProps}
          state="start"
          inputConfig={{
            fields: [
              { name: "test", label: "Test", type: "text", required: false },
            ],
          }}
        />,
      );

      const startButton = screen.getByRole("button", { name: /Start/i });
      await waitFor(() => {
        expect(document.activeElement).toBe(startButton);
      });
    });

    it("focuses feedback textarea on reject_feedback state", async () => {
      render(<ChatInputArea {...defaultProps} state="reject_feedback" />);

      const textarea = screen.getByPlaceholderText(
        /Describe what needs to be changed/i,
      );
      await waitFor(() => {
        expect(document.activeElement).toBe(textarea);
      });
    });
  });

  describe("Accessibility (AC 7, 15)", () => {
    it("has aria-live for state announcements", () => {
      const { container } = render(
        <ChatInputArea {...defaultProps} state="start" />,
      );

      const liveRegion = container.querySelector('[aria-live="polite"]');
      expect(liveRegion).toBeInTheDocument();
    });

    it("associates labels with inputs", () => {
      render(<ChatInputArea {...defaultProps} />);

      const input = screen.getByLabelText(/Confluence URL/i);
      // Label htmlFor should match input id
      expect(input).toHaveAttribute("id");
    });

    it("shows validation error message for invalid inputs", () => {
      const inputConfig = {
        fields: [
          {
            name: "test",
            label: "Test",
            type: "text" as const,
            required: false,
            validation: (value: string) =>
              value.length < 3 ? "Must be at least 3 characters" : null,
          },
        ],
      };

      render(<ChatInputArea {...defaultProps} inputConfig={inputConfig} />);

      // Enter invalid value (less than 3 chars)
      const input = screen.getByLabelText(/Test/i);
      fireEvent.change(input, { target: { value: "ab" } });

      // Click Start
      const startButton = screen.getByRole("button", { name: /Start/i });
      fireEvent.click(startButton);

      // Error message should appear
      expect(
        screen.getByText(/Must be at least 3 characters/i),
      ).toBeInTheDocument();
    });
  });
});
