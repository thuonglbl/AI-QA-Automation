import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SarahScriptReviewPanel } from "../agents/SarahScriptReviewPanel";
import type { ScriptReviewItem, ScriptValidationError } from "@/types/testcase";

// Mock SyntaxHighlighter to avoid heavy CSS/web-worker deps in jsdom
vi.mock("react-syntax-highlighter", () => ({
  Prism: ({ children, language }: { children: string; language: string }) => (
    <pre data-testid="syntax-highlighter" data-language={language}>
      {children}
    </pre>
  ),
}));
vi.mock("react-syntax-highlighter/dist/esm/styles/prism", () => ({
  vscDarkPlus: {},
}));

function makeItem(overrides: Partial<ScriptReviewItem> = {}): ScriptReviewItem {
  return {
    index: 0,
    test_case: {
      title: "Login Test",
      objective: "Verify login works",
      preconditions: ["User exists"],
      steps: [
        { number: 1, action: "Enter username", target: "#user", data: "alice" },
        { number: 2, action: "Click submit", target: "#submit" },
      ],
      expected_results: ["Dashboard shown"],
      source_requirement_name: "Login Requirement",
      source_url: "https://confluence.example.com/login",
    },
    script_content: "import playwright\n# TODO: verify selector\n",
    script_language: "python",
    file_path: "login_test.py",
    confidence: 0.85,
    warnings: [],
    approved: false,
    status: "pending",
    error_message: null,
    ...overrides,
  };
}

const noop = vi.fn();

describe("SarahScriptReviewPanel", () => {
  describe("AC1 — Side-by-side layout", () => {
    it("renders test case title on the left", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByText("Login Test")).toBeInTheDocument();
    });

    it("renders source requirement with link", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      const link = screen.getByRole("link", { name: /Open/i });
      expect(link).toHaveAttribute("href", "https://confluence.example.com/login");
    });

    it("renders steps with action and target", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByText(/Enter username/)).toBeInTheDocument();
      expect(screen.getByText(/target: #user/)).toBeInTheDocument();
    });

    it("renders syntax-highlighted script on the right with language=python", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      const hl = screen.getByTestId("syntax-highlighter");
      expect(hl).toHaveAttribute("data-language", "python");
      expect(hl.textContent).toContain("import playwright");
    });

    it("script pane has accessible aria-label (role=region)", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(
        screen.getByRole("region", { name: /Generated Playwright script/i }),
      ).toBeInTheDocument();
    });
  });

  describe("AC2 — Multi-script navigation", () => {
    it("does NOT show Prev/Next when only one script", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.queryByRole("button", { name: /Previous script/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Next script/i })).not.toBeInTheDocument();
    });

    it("shows Prev/Next when multiple scripts", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 }), makeItem({ index: 1, test_case: { ...makeItem().test_case, title: "Second" } })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByRole("button", { name: /Previous script/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Next script/i })).toBeInTheDocument();
    });

    it("Previous is disabled at first item", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 }), makeItem({ index: 1 })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByRole("button", { name: /Previous script/i })).toBeDisabled();
    });

    it("Next is disabled at last item", () => {
      const items = [makeItem({ index: 0 }), makeItem({ index: 1 })];
      render(
        <SarahScriptReviewPanel
          scripts={items}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      // Navigate to last
      fireEvent.click(screen.getByRole("button", { name: /Next script/i }));
      expect(screen.getByRole("button", { name: /Next script/i })).toBeDisabled();
    });

    it("updates i / N counter when navigating", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 }), makeItem({ index: 1 })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByText("1 / 2")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Next script/i }));
      expect(screen.getByText("2 / 2")).toBeInTheDocument();
    });

    it("per-item status dots present for each script", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[
            makeItem({ index: 0, status: "approved" }),
            makeItem({ index: 1, status: "skipped" }),
            makeItem({ index: 2, status: "pending" }),
          ]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      // Three status indicator buttons
      const dots = screen.getAllByRole("button", { name: /Script \d+:/i });
      expect(dots).toHaveLength(3);
    });

    // [C29] status counter text + per-dot aria-labels reflect each script's state
    it("renders the 'N of M reviewed' counter and per-dot status aria-labels", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[
            makeItem({ index: 0, status: "approved" }),
            makeItem({ index: 1, status: "skipped" }),
            makeItem({ index: 2, status: "pending" }),
          ]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      // Counter reflects two resolved (approved + skipped) of three total
      expect(screen.getByText(/2 of 3 reviewed/)).toBeInTheDocument();
      // Each status dot exposes its state via aria-label (color + text, not color alone)
      expect(
        screen.getByRole("button", { name: "Script 1: Approved" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Script 2: Skipped" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Script 3: Pending" }),
      ).toBeInTheDocument();
    });
  });

  describe("AC3 — Warnings visible without hiding script", () => {
    it("shows warnings banner when warnings present", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ warnings: ["Brittle selector: use data-testid"] })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByText(/Brittle selector/)).toBeInTheDocument();
    });

    it("does not show banner when warnings empty", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ warnings: [] })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.queryByText(/Review warnings/)).not.toBeInTheDocument();
    });

    it("script content still rendered when warnings present (AC3: not hidden)", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[
            makeItem({
              warnings: ["SSO setup required"],
              script_content: "playwright_code_here",
            }),
          ]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      // Warnings present
      expect(screen.getByText(/SSO setup required/)).toBeInTheDocument();
      // Script content still rendered (not hidden)
      expect(screen.getByTestId("syntax-highlighter").textContent).toContain(
        "playwright_code_here",
      );
    });
  });

  describe("Confidence badge", () => {
    it("shows High badge for score >= 0.8", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ confidence: 0.92 })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByText(/High 0\.92/)).toBeInTheDocument();
    });

    it("shows Medium badge for 0.5 <= score < 0.8", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ confidence: 0.65 })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByText(/Medium 0\.65/)).toBeInTheDocument();
    });

    it("shows Low badge for score < 0.5", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ confidence: 0.3 })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByText(/Low 0\.30/)).toBeInTheDocument();
    });
  });

  describe("Failed-script placeholder", () => {
    it("shows error banner when error_message is set", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ error_message: "LLM timeout" })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByText("Generation failed")).toBeInTheDocument();
      expect(screen.getByText("LLM timeout")).toBeInTheDocument();
    });
  });

  describe("Approve / Skip / Reject callbacks", () => {
    it("Approve with no edit calls onApprove(index, undefined)", () => {
      const onApprove = vi.fn();
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 })]}
          onApprove={onApprove}
          onReject={noop}
          onSkip={noop}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Approve/i }));
      expect(onApprove).toHaveBeenCalledWith(0, undefined);
    });

    it("Skip calls onSkip with item index", () => {
      const onSkip = vi.fn();
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 })]}
          onApprove={noop}
          onReject={noop}
          onSkip={onSkip}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Skip/i }));
      expect(onSkip).toHaveBeenCalledWith(0);
    });

    it("Reject toggles feedback area and Submit calls onReject", () => {
      const onReject = vi.fn();
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 })]}
          onApprove={noop}
          onReject={onReject}
          onSkip={noop}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));
      // In Preview tab, the only visible textbox is the reject feedback area
      const textarea = screen.getByRole("textbox", { name: "" });
      fireEvent.change(textarea, { target: { value: "Bad selectors" } });
      fireEvent.click(screen.getByRole("button", { name: /Submit Feedback/i }));
      expect(onReject).toHaveBeenCalledWith(0, "Bad selectors");
    });

    it("Submit Feedback is disabled when textarea is empty", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));
      expect(screen.getByRole("button", { name: /Submit Feedback/i })).toBeDisabled();
    });

    it("all action buttons disabled when disabled prop is true", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
          disabled
        />,
      );
      expect(screen.getByRole("button", { name: /Approve/i })).toBeDisabled();
      expect(screen.getByRole("button", { name: /Skip/i })).toBeDisabled();
      expect(screen.getByRole("button", { name: /Reject/i })).toBeDisabled();
    });

    it("preserves reject feedback when navigating to another script and back", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 }), makeItem({ index: 1 })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      
      // Navigate to Reject input on first script
      fireEvent.click(screen.getByRole("button", { name: /Reject/i }));
      const textarea = screen.getByPlaceholderText(/Describe what needs to be changed/i);
      fireEvent.change(textarea, { target: { value: "Feedback for First Script" } });
      expect(textarea).toHaveValue("Feedback for First Script");

      // Navigate to second script
      fireEvent.click(screen.getByRole("button", { name: /Next script/i }));
      expect(screen.queryByPlaceholderText(/Describe what needs to be changed/i)).not.toBeInTheDocument();

      // Navigate back to first script
      fireEvent.click(screen.getByRole("button", { name: /Previous script/i }));
      const restoredTextarea = screen.getByPlaceholderText(/Describe what needs to be changed/i);
      expect(restoredTextarea).toHaveValue("Feedback for First Script");
    });
  });

  // ---------------------------------------------------------------------------
  // 13.6 — Edit tab + unsaved indicator + error banner + approve with edits
  // ---------------------------------------------------------------------------

  describe("13.6 AC1 — Edit tab + per-script edit retention", () => {
    it("Preview and Edit tab buttons are rendered", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByRole("button", { name: /Preview tab/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Edit tab/i })).toBeInTheDocument();
    });

    it("Preview tab is active by default — syntax highlighter visible", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByTestId("syntax-highlighter")).toBeInTheDocument();
      expect(screen.queryByRole("textbox", { name: /Edit script content/i })).not.toBeInTheDocument();
    });

    it("clicking Edit tab shows a textarea seeded with script_content", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ script_content: "original_code" })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Edit tab/i }));
      const textarea = screen.getByRole("textbox", { name: /Edit script content/i });
      expect(textarea).toBeInTheDocument();
      expect((textarea as HTMLTextAreaElement).value).toBe("original_code");
    });

    it("clicking Preview after editing restores the syntax highlighter", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Edit tab/i }));
      expect(screen.queryByTestId("syntax-highlighter")).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Preview tab/i }));
      expect(screen.getByTestId("syntax-highlighter")).toBeInTheDocument();
    });

    it("unsaved-changes indicator absent before any edit", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem()]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.queryByText(/Unsaved changes/i)).not.toBeInTheDocument();
    });

    it("unsaved-changes indicator appears after typing in Edit pane", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ script_content: "original" })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Edit tab/i }));
      const ta = screen.getByRole("textbox", { name: /Edit script content/i });
      fireEvent.change(ta, { target: { value: "modified" } });
      expect(screen.getByText(/Unsaved changes/i)).toBeInTheDocument();
    });

    it("unsaved indicator uses text (not color alone) — AC1 accessibility", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ script_content: "original" })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Edit tab/i }));
      fireEvent.change(
        screen.getByRole("textbox", { name: /Edit script content/i }),
        { target: { value: "changed" } },
      );
      // Both text and aria-label must be present (not color alone)
      expect(screen.getByText(/Unsaved changes/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Unsaved changes/i)).toBeInTheDocument();
    });

    it("AC1 — edit retained when navigating away and back (per-index buffer)", () => {
      const items = [
        makeItem({ index: 0, script_content: "script_zero" }),
        makeItem({ index: 1, script_content: "script_one", test_case: { ...makeItem().test_case, title: "Second" } }),
      ];
      render(
        <SarahScriptReviewPanel
          scripts={items}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      // Edit script 0
      fireEvent.click(screen.getByRole("button", { name: /Edit tab/i }));
      const ta = screen.getByRole("textbox", { name: /Edit script content/i });
      fireEvent.change(ta, { target: { value: "my_edit_on_zero" } });

      // Navigate to script 1
      fireEvent.click(screen.getByRole("button", { name: /Next script/i }));

      // Navigate back to script 0
      fireEvent.click(screen.getByRole("button", { name: /Previous script/i }));

      // Edit must still be present
      const ta2 = screen.getByRole("textbox", { name: /Edit script content/i });
      expect((ta2 as HTMLTextAreaElement).value).toBe("my_edit_on_zero");
    });
  });

  // ---------------------------------------------------------------------------
  // [C10] Edit-buffer pruning on re-present: a new generation resets edited
  // panes, but a sibling approve (full-list re-present, content unchanged) must
  // NOT wipe unsaved edits for not-yet-resolved scripts.
  // ---------------------------------------------------------------------------
  describe("13.6 AC1 — edit buffer survives re-present, resets on regeneration", () => {
    it("a NEW generation (script content changed) resets the edit pane, clears the unsaved badge, and snaps back to Preview", () => {
      const { rerender } = render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0, script_content: "gen_one_code" })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      // Edit script 0 in the Edit pane
      fireEvent.click(screen.getByRole("button", { name: /Edit tab/i }));
      fireEvent.change(
        screen.getByRole("textbox", { name: /Edit script content/i }),
        { target: { value: "my unsaved edit" } },
      );
      expect(screen.getByText(/Unsaved changes/i)).toBeInTheDocument();

      // A brand-new generation arrives: NEW array object, NEW script_content.
      rerender(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0, script_content: "gen_two_code" })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );

      // Edit pruned: unsaved badge gone, tab snapped back to Preview.
      expect(screen.queryByText(/Unsaved changes/i)).not.toBeInTheDocument();
      const hl = screen.getByTestId("syntax-highlighter");
      expect(hl.textContent).toContain("gen_two_code");
      // The stale edit must not survive — the regenerated content is shown.
      expect(hl.textContent).not.toContain("my unsaved edit");
    });

    it("a sibling approve (re-present, edited script content unchanged) does NOT wipe the unsaved edit", () => {
      const first = [
        makeItem({ index: 0, script_content: "script_zero", status: "pending" }),
        makeItem({
          index: 1,
          script_content: "script_one",
          status: "pending",
          test_case: { ...makeItem().test_case, title: "Second" },
        }),
      ];
      const { rerender } = render(
        <SarahScriptReviewPanel
          scripts={first}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      // Edit script 0 (current index)
      fireEvent.click(screen.getByRole("button", { name: /Edit tab/i }));
      fireEvent.change(
        screen.getByRole("textbox", { name: /Edit script content/i }),
        { target: { value: "my_edit_on_zero" } },
      );
      expect(screen.getByText(/Unsaved changes/i)).toBeInTheDocument();

      // Backend re-presents the FULL list after a SIBLING (script 1) approve:
      // a NEW array object, but script 0's content is unchanged.
      const afterSiblingApprove = [
        makeItem({ index: 0, script_content: "script_zero", status: "pending" }),
        makeItem({
          index: 1,
          script_content: "script_one",
          status: "approved",
          approved: true,
          test_case: { ...makeItem().test_case, title: "Second" },
        }),
      ];
      rerender(
        <SarahScriptReviewPanel
          scripts={afterSiblingApprove}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );

      // The unsaved edit on script 0 must survive the sibling re-present.
      expect(screen.getByText(/Unsaved changes/i)).toBeInTheDocument();
      const ta = screen.getByRole("textbox", { name: /Edit script content/i });
      expect((ta as HTMLTextAreaElement).value).toBe("my_edit_on_zero");
    });
  });

  describe("13.6 AC3 — Approve carries edited content", () => {
    it("after editing, Approve calls onApprove(index, editedContent)", () => {
      const onApprove = vi.fn();
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0, script_content: "original" })]}
          onApprove={onApprove}
          onReject={noop}
          onSkip={noop}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Edit tab/i }));
      fireEvent.change(
        screen.getByRole("textbox", { name: /Edit script content/i }),
        { target: { value: "my edited script" } },
      );
      fireEvent.click(screen.getByRole("button", { name: /Approve/i }));
      expect(onApprove).toHaveBeenCalledWith(0, "my edited script");
    });

    it("without editing, Approve calls onApprove(index, undefined) — back-compat", () => {
      const onApprove = vi.fn();
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 })]}
          onApprove={onApprove}
          onReject={noop}
          onSkip={noop}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /Approve/i }));
      expect(onApprove).toHaveBeenCalledWith(0, undefined);
    });
  });

  describe("13.6 AC2 — Validation-error banner", () => {
    const syntaxError: ScriptValidationError = {
      line: 3,
      column: 1,
      message: "Python syntax error: invalid syntax",
      severity: "error",
      code: "syntax",
    };

    it("renders red error banner with line+message when validationErrors provided", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
          validationErrors={{ 0: [syntaxError] }}
        />,
      );
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/Line 3/)).toBeInTheDocument();
      expect(screen.getByText(/Python syntax error/)).toBeInTheDocument();
    });

    it("banner absent when no validationErrors", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("script pane still present when error banner is shown (not hidden)", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0, script_content: "my_script_code" })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
          validationErrors={{ 0: [syntaxError] }}
        />,
      );
      // Alert present
      expect(screen.getByRole("alert")).toBeInTheDocument();
      // Script pane still rendered (Preview mode shows syntax highlighter)
      expect(screen.getByTestId("syntax-highlighter").textContent).toContain("my_script_code");
    });

    it("banner absent for a different script index", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 }), makeItem({ index: 1, test_case: { ...makeItem().test_case, title: "Two" } })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
          validationErrors={{ 1: [syntaxError] }}  // error on script 1, viewing script 0
        />,
      );
      // Currently at index 0 — banner must NOT show
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("validation banner is visually distinct from amber warnings banner", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0, warnings: ["Brittle selector"] })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
          validationErrors={{ 0: [syntaxError] }}
        />,
      );
      // Amber warnings banner
      expect(screen.getByText(/Review warnings/)).toBeInTheDocument();
      // Red validation error banner — separate element
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      // They must be separate nodes
      expect(alert).not.toContain(screen.getByText(/Review warnings/).parentElement);
    });

    it("omits 'Line X:' when error has no line number", () => {
      const noLineError: ScriptValidationError = {
        line: null,
        column: null,
        message: "Script cannot be empty.",
        severity: "error",
        code: "syntax",
      };
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
          validationErrors={{ 0: [noLineError] }}
        />,
      );
      expect(screen.queryByText(/Line/)).not.toBeInTheDocument();
      expect(screen.getByText(/Script cannot be empty/)).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // 13.7 — Approval metadata caption (AC1)
  // ---------------------------------------------------------------------------
  describe("AC1 — Approval metadata caption", () => {
    it("shows 'Approved by ...' caption when script is approved with metadata", () => {
      const approvedItem = makeItem({
        approved: true,
        approved_by: "qa@corp.vn",
        approved_at: "2026-06-13T10:00:00+00:00",
        status: "approved",
      });
      render(
        <SarahScriptReviewPanel
          scripts={[approvedItem]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      // Must use text, not color alone
      expect(screen.getByText(/Approved by qa@corp\.vn/)).toBeInTheDocument();
    });

    it("shows 'Approved' without 'by' when approved_by is null", () => {
      const approvedItem = makeItem({
        approved: true,
        approved_by: null,
        approved_at: "2026-06-13T10:00:00+00:00",
        status: "approved",
      });
      render(
        <SarahScriptReviewPanel
          scripts={[approvedItem]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.getByText(/Approved/)).toBeInTheDocument();
      // "by null" must not appear
      expect(screen.queryByText(/by null/)).not.toBeInTheDocument();
    });

    it("does not render approval caption for a pending item", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ status: "pending", approved: false })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.queryByText(/Approved by/)).not.toBeInTheDocument();
    });

    it("does not render approval caption for a skipped item", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ status: "skipped", approved: false })]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      expect(screen.queryByText(/Approved by/)).not.toBeInTheDocument();
    });

    it("renders gracefully when approved_at is null", () => {
      const approvedItem = makeItem({
        approved: true,
        approved_by: "qa@corp.vn",
        approved_at: null,
        status: "approved",
      });
      render(
        <SarahScriptReviewPanel
          scripts={[approvedItem]}
          onApprove={noop}
          onReject={noop}
          onSkip={noop}
        />,
      );
      // Must still show approved_by without crashing
      expect(screen.getByText(/Approved by qa@corp\.vn/)).toBeInTheDocument();
    });
  });
  
  describe("16.6 AC2 — Keyboard navigation for script dots", () => {
    it("allows arrow keys to navigate between script dots", () => {
      render(
        <SarahScriptReviewPanel
          scripts={[makeItem({ index: 0 }), makeItem({ index: 1 })]}
          onApprove={vi.fn()}
          onReject={vi.fn()}
          onSkip={vi.fn()}
        />
      );
      
      const dots = screen.getAllByRole("button", { name: /^Script \d:/ });
      expect(dots).toHaveLength(2);
      
      // Initially script 1 is selected
      expect(screen.getByText("Review Script (1 of 2) —")).toBeInTheDocument();
      
      // Right arrow on the first dot should select the second script
      fireEvent.keyDown(dots[0]!, { key: "ArrowRight" });
      expect(screen.getByText("Review Script (2 of 2) —")).toBeInTheDocument();
      
      // Left arrow on the second dot should select the first script
      fireEvent.keyDown(dots[1]!, { key: "ArrowLeft" });
      expect(screen.getByText("Review Script (1 of 2) —")).toBeInTheDocument();
    });
  });
});
