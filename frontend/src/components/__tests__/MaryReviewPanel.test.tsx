import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MaryReviewPanel } from "../agents/MaryReviewPanel";
import type { MaryReviewCase } from "@/types/testcase";

const SAMPLE_MARKDOWN = [
  "# Login with valid credentials",
  "",
  "## Objective",
  "",
  "Verify user can log in successfully",
  "",
  "## Source Requirement",
  "",
  "[login/requirement.md](https://confluence.example.com/login)",
  "",
  "## Preconditions",
  "",
  "1. User is on the login page",
  "",
  "## Steps",
  "",
  "1. Enter username _(target: username input)_ — Data: testuser",
  "2. Enter password _(target: password input)_ — Data: pass123",
  "3. Click login button _(target: login button)_",
  "",
  "## Expected Results",
  "",
  "1. User is redirected to the dashboard",
].join("\n");

function makeTestCase(overrides: Partial<MaryReviewCase> = {}): MaryReviewCase {
  return {
    title: "Login with valid credentials",
    markdown: SAMPLE_MARKDOWN,
    confidence: 0.85,
    confidence_level: "high",
    confidence_rationale: ["All structural fields present"],
    warnings: [],
    ...overrides,
  };
}

const defaultProps = {
  onApprove: vi.fn(),
  onReject: vi.fn(),
};

describe("MaryReviewPanel", () => {
  describe("AC1 — Renders test case fields", () => {
    it("renders test case title in header", () => {
      render(
        <MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />,
      );
      expect(screen.getByText(/Login with valid credentials/i)).toBeInTheDocument();
    });

    it("renders objective", () => {
      render(<MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />);
      expect(screen.getByText(/Verify user can log in successfully/i)).toBeInTheDocument();
    });

    it("renders source requirement name", () => {
      render(<MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />);
      expect(screen.getByText(/login\/requirement\.md/i)).toBeInTheDocument();
    });

    it("renders the source requirement as a clickable Markdown link", () => {
      render(<MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />);
      const link = screen.getByRole("link", { name: /login\/requirement\.md/i });
      expect(link).toHaveAttribute("href", "https://confluence.example.com/login");
    });

    it("renders no link when the Markdown has no source link", () => {
      render(
        <MaryReviewPanel
          testCases={[makeTestCase({ markdown: "# Plain case\n\n## Objective\n\nDo a thing" })]}
          {...defaultProps}
        />,
      );
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
    });

    it("renders preconditions", () => {
      render(<MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />);
      expect(screen.getByText(/User is on the login page/i)).toBeInTheDocument();
    });

    it("renders test steps with action and target", () => {
      render(<MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />);
      expect(screen.getByText(/Enter username/i)).toBeInTheDocument();
      expect(screen.getByText(/username input/i)).toBeInTheDocument();
    });

    it("renders expected results", () => {
      render(<MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />);
      expect(
        screen.getByText(/User is redirected to the dashboard/i),
      ).toBeInTheDocument();
    });
  });

  describe("AC1 — Confidence badge", () => {
    it("shows green badge for high confidence", () => {
      render(
        <MaryReviewPanel
          testCases={[makeTestCase({ confidence_level: "high", confidence: 0.9 })]}
          {...defaultProps}
        />,
      );
      const badge = screen.getByText("HIGH");
      expect(badge.className).toMatch(/green/);
      expect(screen.getByText(/score: 0\.90/i)).toBeInTheDocument();
    });

    it("shows amber badge for medium confidence", () => {
      render(
        <MaryReviewPanel
          testCases={[makeTestCase({ confidence_level: "medium", confidence: 0.6 })]}
          {...defaultProps}
        />,
      );
      const badge = screen.getByText("MEDIUM");
      expect(badge.className).toMatch(/amber/);
    });

    it("shows red badge for low confidence", () => {
      render(
        <MaryReviewPanel
          testCases={[makeTestCase({ confidence_level: "low", confidence: 0.3 })]}
          {...defaultProps}
        />,
      );
      const badge = screen.getByText("LOW");
      expect(badge.className).toMatch(/red/);
    });

    it("toggles confidence rationale on each click of 'Why this score'", () => {
      render(
        <MaryReviewPanel
          testCases={[
            makeTestCase({
              confidence_rationale: ["All structural fields present"],
            }),
          ]}
          {...defaultProps}
        />,
      );
      const toggle = screen.getByRole("button", { name: /Toggle confidence rationale/i });

      // Rationale is collapsed by default.
      expect(
        screen.queryByText(/All structural fields present/i),
      ).not.toBeInTheDocument();

      // First click reveals it.
      fireEvent.click(toggle);
      expect(
        screen.getByText(/All structural fields present/i),
      ).toBeInTheDocument();

      // Second click hides it again.
      fireEvent.click(toggle);
      expect(
        screen.queryByText(/All structural fields present/i),
      ).not.toBeInTheDocument();
    });
  });

  describe("AC1 — Low-confidence summary banner", () => {
    it("shows summary banner when at least one case is low confidence", () => {
      render(
        <MaryReviewPanel
          testCases={[
            makeTestCase({ confidence_level: "low" }),
            makeTestCase({ title: "Another case", confidence_level: "high" }),
          ]}
          {...defaultProps}
        />,
      );
      expect(
        screen.getByText(/1 of 2 test case is low confidence/i),
      ).toBeInTheDocument();
    });

    it("does not show summary banner when no low-confidence cases", () => {
      render(
        <MaryReviewPanel
          testCases={[makeTestCase({ confidence_level: "high" })]}
          {...defaultProps}
        />,
      );
      expect(
        screen.queryByText(/low confidence.*review each/i),
      ).not.toBeInTheDocument();
    });
  });

  describe("AC1 — Navigation (multiple test cases)", () => {
    const twoTestCases = [
      makeTestCase({ title: "Test Case One" }),
      makeTestCase({ title: "Test Case Two" }),
    ];

    it("shows navigation bar when more than one test case", () => {
      render(<MaryReviewPanel testCases={twoTestCases} {...defaultProps} />);
      expect(
        screen.getByRole("button", { name: /Next item/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Previous item/i }),
      ).toBeInTheDocument();
    });

    it("does not show nav bar for a single test case", () => {
      render(
        <MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />,
      );
      expect(
        screen.queryByRole("button", { name: /Next item/i }),
      ).not.toBeInTheDocument();
    });

    it("Previous is disabled on first case, Next is enabled", () => {
      render(<MaryReviewPanel testCases={twoTestCases} {...defaultProps} />);
      expect(
        screen.getByRole("button", { name: /Previous item/i }),
      ).toBeDisabled();
      expect(
        screen.getByRole("button", { name: /Next item/i }),
      ).not.toBeDisabled();
    });

    it("clicking Next advances to the second test case", () => {
      render(<MaryReviewPanel testCases={twoTestCases} {...defaultProps} />);
      expect(screen.getByText(/1 \/ 2/i)).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /Next item/i }));

      expect(screen.getByText(/2 \/ 2/i)).toBeInTheDocument();
      expect(screen.getByText(/Test Case Two/i)).toBeInTheDocument();
    });
  });

  describe("AC2 — Approve", () => {
    it("calls onApprove with the current index", () => {
      const onApprove = vi.fn();
      render(
        <MaryReviewPanel
          testCases={[makeTestCase()]}
          {...defaultProps}
          onApprove={onApprove}
        />,
      );

      fireEvent.click(screen.getByRole("button", { name: /Approve/i }));

      expect(onApprove).toHaveBeenCalledWith(0);
    });

    it("shows resolved count after approving", () => {
      render(
        <MaryReviewPanel
          testCases={[makeTestCase(), makeTestCase({ title: "Case 2" })]}
          {...defaultProps}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Approve/i }));
      expect(screen.getByText(/1 resolved/i)).toBeInTheDocument();
    });

    it("calls onApprove(1) when approving the second case (after navigating)", () => {
      const onApprove = vi.fn();
      render(
        <MaryReviewPanel
          testCases={[makeTestCase(), makeTestCase({ title: "Case 2" })]}
          {...defaultProps}
          onApprove={onApprove}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Next item/i }));
      fireEvent.click(screen.getByRole("button", { name: /Approve/i }));
      expect(onApprove).toHaveBeenCalledWith(1);
    });

    it("auto-advances to the next unresolved case after approving (skips resolved)", () => {
      const onApprove = vi.fn();
      render(
        <MaryReviewPanel
          testCases={[
            makeTestCase({ title: "Case Alpha" }),
            makeTestCase({ title: "Case Bravo" }),
            makeTestCase({ title: "Case Charlie" }),
          ]}
          {...defaultProps}
          onApprove={onApprove}
        />,
      );

      // Start on case 0.
      expect(screen.getByText(/1 \/ 3/i)).toBeInTheDocument();
      expect(screen.getByText(/Case Alpha/i)).toBeInTheDocument();

      // Approving case 0 auto-advances the view to the next unresolved case (case 1).
      fireEvent.click(screen.getByRole("button", { name: /Approve/i }));
      expect(onApprove).toHaveBeenCalledWith(0);
      expect(screen.getByText(/2 \/ 3/i)).toBeInTheDocument();
      expect(screen.getByText(/Case Bravo/i)).toBeInTheDocument();

      // Go back to the already-resolved case 0, then approve case 1 again:
      // auto-advance must skip the resolved case 0 and land on the next
      // unresolved case after the current one (case 2).
      fireEvent.click(screen.getByRole("button", { name: /Previous item/i }));
      expect(screen.getByText(/1 \/ 3/i)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Next item/i }));
      fireEvent.click(screen.getByRole("button", { name: /Approve/i }));
      expect(onApprove).toHaveBeenCalledWith(1);
      expect(screen.getByText(/3 \/ 3/i)).toBeInTheDocument();
      expect(screen.getByText(/Case Charlie/i)).toBeInTheDocument();
    });
  });

  describe("disabled prop", () => {
    it("disables Approve, Reject, Prev/Next and Submit Feedback when disabled", () => {
      render(
        <MaryReviewPanel
          testCases={[makeTestCase({ title: "First" }), makeTestCase({ title: "Second" })]}
          {...defaultProps}
          disabled
        />,
      );

      expect(screen.getByRole("button", { name: /Approve/i })).toBeDisabled();
      expect(screen.getByRole("button", { name: /Reject/i })).toBeDisabled();
      // Next is disabled by the disabled prop (even though it is not the last case).
      expect(screen.getByRole("button", { name: /Next item/i })).toBeDisabled();
      // Previous is disabled on the first case regardless, but still disabled.
      expect(screen.getByRole("button", { name: /Previous item/i })).toBeDisabled();
    });

    it("disables the feedback textarea and Submit Feedback once disabled becomes true", () => {
      const { rerender } = render(
        <MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />,
      );

      // Open the feedback input while enabled, then enter feedback.
      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));
      const textarea = screen.getByPlaceholderText(/Describe what needs to be changed/i);
      fireEvent.change(textarea, { target: { value: "Add missing preconditions" } });
      expect(screen.getByRole("button", { name: /Submit Feedback/i })).not.toBeDisabled();

      // A subsequent disabled (e.g. regeneration in flight) must lock the input.
      rerender(<MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} disabled />);
      expect(
        screen.getByPlaceholderText(/Describe what needs to be changed/i),
      ).toBeDisabled();
      expect(screen.getByRole("button", { name: /Submit Feedback/i })).toBeDisabled();
    });
  });

  describe("AC3 — Reject with feedback", () => {
    it("shows feedback textarea when Reject is clicked", () => {
      render(<MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />);

      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));

      expect(
        screen.getByPlaceholderText(/Describe what needs to be changed/i),
      ).toBeInTheDocument();
    });

    it("keeps Submit Feedback disabled when feedback is empty", () => {
      render(<MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />);
      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));

      expect(
        screen.getByRole("button", { name: /Submit Feedback/i }),
      ).toBeDisabled();
    });

    it("calls onReject with index and feedback text on submit", () => {
      const onReject = vi.fn();
      render(
        <MaryReviewPanel
          testCases={[makeTestCase()]}
          {...defaultProps}
          onReject={onReject}
        />,
      );

      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));

      const textarea = screen.getByPlaceholderText(
        /Describe what needs to be changed/i,
      );
      fireEvent.change(textarea, { target: { value: "Add missing preconditions" } });

      fireEvent.click(screen.getByRole("button", { name: /Submit Feedback/i }));

      expect(onReject).toHaveBeenCalledWith(0, "Add missing preconditions");
    });

    it("hides feedback textarea after submission", () => {
      render(<MaryReviewPanel testCases={[makeTestCase()]} {...defaultProps} />);
      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));

      const textarea = screen.getByPlaceholderText(
        /Describe what needs to be changed/i,
      );
      fireEvent.change(textarea, { target: { value: "Fix it" } });
      fireEvent.click(screen.getByRole("button", { name: /Submit Feedback/i }));

      expect(
        screen.queryByPlaceholderText(/Describe what needs to be changed/i),
      ).not.toBeInTheDocument();
    });
  });
});
