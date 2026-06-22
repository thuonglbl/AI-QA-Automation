import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SplitPanel } from "../SplitPanel";
import type { ExtractedPage } from "@/types/extraction";

// Mock ReviewContent to avoid react-markdown/mermaid complexity in unit tests
vi.mock("../ReviewContent", () => ({
  ReviewContent: ({ content }: { content: string }) => (
    <div data-testid="review-content">{content}</div>
  ),
}));

// Mock ScrollArea used inside ReviewContent (real one needs ResizeObserver)
vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

function makePage(overrides: Partial<ExtractedPage> = {}): ExtractedPage {
  return {
    page_id: "p1",
    page_title: "Login Flow",
    source_url: "https://example.com/p1",
    raw_html: "<p>source</p>",
    requirement_md: "## Login\n\nRequirement text here",
    warnings: [],
    quality_issues: [],
    source_type: "confluence",
    ...overrides,
  };
}

const defaultProps = {
  onApprove: vi.fn(),
  onSkip: vi.fn(),
  onReject: vi.fn(),
};

describe("SplitPanel", () => {
  describe("AC1 — Source link and source type label", () => {
    it("renders source link with page URL", () => {
      render(
        <SplitPanel
          pages={[makePage({ source_url: "https://example.com/p1" })]}
          {...defaultProps}
        />,
      );
      const link = screen.getByRole("link", { name: /Open Original/i });
      expect(link).toHaveAttribute("href", "https://example.com/p1");
      expect(link).toHaveAttribute("target", "_blank");
    });

    it("labels source link as 'Open in Jira' when source_type is jira", () => {
      render(
        <SplitPanel
          pages={[makePage({ source_type: "jira" })]}
          {...defaultProps}
        />,
      );
      expect(
        screen.getByRole("link", { name: /Open in Jira/i }),
      ).toBeInTheDocument();
    });
  });

  describe("AC1 — Rendered Markdown (Preview/Edit tabs)", () => {
    it("shows Preview tab by default with rendered markdown", () => {
      const page = makePage({ requirement_md: "## Heading\n\nContent" });
      render(<SplitPanel pages={[page]} {...defaultProps} />);

      // Preview tab is active
      const previewBtn = screen.getByRole("button", { name: /Preview/i });
      expect(previewBtn.className).toContain("border-b-2");

      // ReviewContent is rendered with requirement_md
      const preview = screen.getByTestId("review-content");
      expect(preview).toBeInTheDocument();
      expect(preview.textContent).toContain("## Heading");
    });

    it("shows Edit textarea when Edit tab is clicked", () => {
      const page = makePage({ requirement_md: "## Heading" });
      render(<SplitPanel pages={[page]} {...defaultProps} />);

      fireEvent.click(screen.getByRole("button", { name: /Edit/i }));

      const textarea = screen.getByRole("textbox");
      expect(textarea).toBeInTheDocument();
      expect((textarea as HTMLTextAreaElement).value).toContain("## Heading");
    });
  });

  describe("AC1 — Warnings banner", () => {
    it("shows warnings banner when quality_issues present", () => {
      const page = makePage({
        quality_issues: [
          {
            category: "vague_language",
            location: "Login Flow",
            message: "Vague term 'etc.' detected.",
            impact: "Wording forces the model to guess.",
          },
        ],
      });
      render(<SplitPanel pages={[page]} {...defaultProps} />);

      expect(
        screen.getByText(/Quality warnings detected/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Vague term 'etc.' detected/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Wording forces the model to guess/i),
      ).toBeInTheDocument();
    });

    it("shows warnings banner for raw page.warnings", () => {
      const page = makePage({ warnings: ["Gliffy diagram detected"] });
      render(<SplitPanel pages={[page]} {...defaultProps} />);

      expect(screen.getByText(/Gliffy diagram detected/i)).toBeInTheDocument();
    });

    it("does not render warnings banner when page is clean", () => {
      render(<SplitPanel pages={[makePage()]} {...defaultProps} />);
      expect(
        screen.queryByText(/Quality warnings detected/i),
      ).not.toBeInTheDocument();
    });
  });

  describe("AC2 — Multi-item navigation", () => {
    const twoPages = [
      makePage({ page_id: "p1", page_title: "Page One" }),
      makePage({
        page_id: "p2",
        page_title: "Page Two",
        requirement_md: "## Page Two content",
      }),
    ];

    it("shows navigation bar when more than one page", () => {
      render(<SplitPanel pages={twoPages} {...defaultProps} />);
      expect(
        screen.getByRole("button", { name: /Next item/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Previous item/i }),
      ).toBeInTheDocument();
    });

    it("does not show nav bar for a single page", () => {
      render(<SplitPanel pages={[makePage()]} {...defaultProps} />);
      expect(
        screen.queryByRole("button", { name: /Next item/i }),
      ).not.toBeInTheDocument();
    });

    it("Previous is disabled on first page, Next is enabled", () => {
      render(<SplitPanel pages={twoPages} {...defaultProps} />);
      expect(
        screen.getByRole("button", { name: /Previous item/i }),
      ).toBeDisabled();
      expect(
        screen.getByRole("button", { name: /Next item/i }),
      ).not.toBeDisabled();
    });

    it("clicking Next advances to the second page", () => {
      render(<SplitPanel pages={twoPages} {...defaultProps} />);
      expect(screen.getByText(/1 \/ 2/i)).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /Next item/i }));

      expect(screen.getByText(/2 \/ 2/i)).toBeInTheDocument();
    });
  });

  describe("AC2 — Batch scope display and auto-advance", () => {
    const twoPages = [
      makePage({
        page_id: "p1",
        page_title: "P1",
        source_url: "https://example.com/p1",
      }),
      makePage({
        page_id: "p2",
        page_title: "P2",
        source_url: "https://example.com/p2",
        requirement_md: "## P2",
      }),
    ];

    it("calls onApprove with page_id and current markdownContent", () => {
      const onApprove = vi.fn();
      render(
        <SplitPanel pages={twoPages} {...defaultProps} onApprove={onApprove} />,
      );

      fireEvent.click(screen.getByRole("button", { name: /Approved/i }));

      expect(onApprove).toHaveBeenCalledWith("p1", twoPages[0]!.requirement_md);
    });

    it("shows resolved count after approving", () => {
      render(<SplitPanel pages={twoPages} {...defaultProps} />);
      fireEvent.click(screen.getByRole("button", { name: /Approved/i }));
      // After approving p1, "1 resolved" should appear
      expect(screen.getByText(/1 resolved/i)).toBeInTheDocument();
    });

    it("calls onSkip with page_id when Not requirement is clicked", () => {
      const onSkip = vi.fn();
      render(
        <SplitPanel pages={[makePage()]} {...defaultProps} onSkip={onSkip} />,
      );

      fireEvent.click(screen.getByRole("button", { name: /Not requirement/i }));

      expect(onSkip).toHaveBeenCalledWith("p1");
    });
  });

  describe("AC3 — Reject with feedback", () => {
    it("shows feedback textarea when Reject is clicked", () => {
      render(<SplitPanel pages={[makePage()]} {...defaultProps} />);

      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));

      expect(
        screen.getByPlaceholderText(/Describe what needs to be changed/i),
      ).toBeInTheDocument();
    });

    it("keeps Submit Feedback disabled when feedback is empty", () => {
      render(<SplitPanel pages={[makePage()]} {...defaultProps} />);
      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));

      expect(
        screen.getByRole("button", { name: /Submit Feedback/i }),
      ).toBeDisabled();
    });

    it("calls onReject with page_id and feedback text on submit", () => {
      const onReject = vi.fn();
      render(
        <SplitPanel
          pages={[makePage()]}
          {...defaultProps}
          onReject={onReject}
        />,
      );

      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));

      const textarea = screen.getByPlaceholderText(
        /Describe what needs to be changed/i,
      );
      fireEvent.change(textarea, { target: { value: "Add preconditions" } });

      fireEvent.click(screen.getByRole("button", { name: /Submit Feedback/i }));

      expect(onReject).toHaveBeenCalledWith("p1", "Add preconditions");
    });

    it("hides feedback textarea after submission", () => {
      render(<SplitPanel pages={[makePage()]} {...defaultProps} />);
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
