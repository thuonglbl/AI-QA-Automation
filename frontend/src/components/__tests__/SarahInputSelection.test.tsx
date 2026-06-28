import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SarahInputSelection } from "../agents/SarahInputSelection";
import type { TestCaseInput } from "@/types/testcase";

function makeEntry(overrides: Partial<TestCaseInput> = {}): TestCaseInput {
  return {
    artifact_id: "abc-123",
    name: "tc-login.json",
    title: "Login with valid credentials",
    source_requirement_name: "Login requirement",
    source_url: "https://confluence.example.com/login",
    confidence_level: "high",
    from_current_thread: true,
    default_selected: true,
    preview: "Verify the user can log in with valid credentials.",
    ...overrides,
  };
}

describe("SarahInputSelection", () => {
  describe("Rendering — single entry", () => {
    it("renders test case title", () => {
      render(
        <SarahInputSelection testCases={[makeEntry()]} onConfirm={vi.fn()} />,
      );
      expect(
        screen.getByText(/Login with valid credentials/i),
      ).toBeInTheDocument();
    });

    it("shows 'This conversation' badge for current-thread entry", () => {
      render(
        <SarahInputSelection testCases={[makeEntry()]} onConfirm={vi.fn()} />,
      );
      expect(screen.getByText("This conversation")).toBeInTheDocument();
    });

    it("does not show 'This conversation' badge for other-thread entry", () => {
      render(
        <SarahInputSelection
          testCases={[makeEntry({ from_current_thread: false })]}
          onConfirm={vi.fn()}
        />,
      );
      expect(
        screen.queryByText("This conversation"),
      ).not.toBeInTheDocument();
    });

    it("shows HIGH confidence badge for high-confidence entry", () => {
      render(
        <SarahInputSelection testCases={[makeEntry()]} onConfirm={vi.fn()} />,
      );
      const badge = screen.getByText("HIGH");
      expect(badge.className).toMatch(/green/);
    });

    it("shows MEDIUM amber badge", () => {
      render(
        <SarahInputSelection
          testCases={[makeEntry({ confidence_level: "medium" })]}
          onConfirm={vi.fn()}
        />,
      );
      const badge = screen.getByText("MEDIUM");
      expect(badge.className).toMatch(/amber/);
    });

    it("shows LOW red badge", () => {
      render(
        <SarahInputSelection
          testCases={[makeEntry({ confidence_level: "low" })]}
          onConfirm={vi.fn()}
        />,
      );
      const badge = screen.getByText("LOW");
      expect(badge.className).toMatch(/red/);
    });

    it("does not render a confidence badge when confidence_level is null", () => {
      render(
        <SarahInputSelection
          testCases={[makeEntry({ confidence_level: null })]}
          onConfirm={vi.fn()}
        />,
      );
      expect(screen.queryByText("HIGH")).not.toBeInTheDocument();
      expect(screen.queryByText("MEDIUM")).not.toBeInTheDocument();
      expect(screen.queryByText("LOW")).not.toBeInTheDocument();
    });

    it("renders source requirement name as text when no source_url", () => {
      render(
        <SarahInputSelection
          testCases={[makeEntry({ source_url: null })]}
          onConfirm={vi.fn()}
        />,
      );
      expect(screen.getByText(/Login requirement/i)).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: /Login requirement/i }),
      ).not.toBeInTheDocument();
    });

    it("renders source requirement name as external link when source_url present", () => {
      render(
        <SarahInputSelection testCases={[makeEntry()]} onConfirm={vi.fn()} />,
      );
      const link = screen.getByRole("link", { name: /Login requirement/i });
      expect(link).toHaveAttribute("href", "https://confluence.example.com/login");
      expect(link).toHaveAttribute("target", "_blank");
    });

    it("shows preview toggle button when preview is present", () => {
      render(
        <SarahInputSelection testCases={[makeEntry()]} onConfirm={vi.fn()} />,
      );
      expect(
        screen.getByRole("button", { name: /Show preview/i }),
      ).toBeInTheDocument();
    });

    it("expands and collapses preview on toggle", () => {
      render(
        <SarahInputSelection testCases={[makeEntry()]} onConfirm={vi.fn()} />,
      );
      const toggle = screen.getByRole("button", { name: /Show preview/i });
      fireEvent.click(toggle);
      expect(
        screen.getByText(/Verify the user can log in with valid credentials\./i),
      ).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Hide preview/i }));
      expect(
        screen.queryByText(/Verify the user can log in with valid credentials\./i),
      ).not.toBeInTheDocument();
    });

    it("does not show preview toggle when preview is absent", () => {
      render(
        <SarahInputSelection
          testCases={[makeEntry({ preview: null })]}
          onConfirm={vi.fn()}
        />,
      );
      expect(
        screen.queryByRole("button", { name: /Show preview/i }),
      ).not.toBeInTheDocument();
    });
  });

  describe("Rendering — multiple entries", () => {
    const two = [
      makeEntry({ artifact_id: "id-1", title: "Login", from_current_thread: true }),
      makeEntry({ artifact_id: "id-2", title: "Search", from_current_thread: false }),
    ];

    it("shows count of current-thread entries in header", () => {
      render(<SarahInputSelection testCases={two} onConfirm={vi.fn()} />);
      expect(screen.getByText(/1 from this conversation/i)).toBeInTheDocument();
    });

    it("shows selection counter", () => {
      render(<SarahInputSelection testCases={two} onConfirm={vi.fn()} />);
      // Both default_selected=true by default, so 2 of 2
      expect(screen.getByText(/2 of 2 selected/i)).toBeInTheDocument();
    });
  });

  describe("Checkbox interaction", () => {
    it("unchecking an entry removes it from the selection count", () => {
      render(
        <SarahInputSelection
          testCases={[makeEntry({ artifact_id: "id-1" })]}
          onConfirm={vi.fn()}
        />,
      );
      expect(screen.getByText(/1 of 1 selected/i)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("checkbox"));
      expect(screen.getByText(/0 of 1 selected/i)).toBeInTheDocument();
    });

    it("Select All selects all entries", () => {
      render(
        <SarahInputSelection
          testCases={[
            makeEntry({ artifact_id: "id-1", default_selected: false }),
            makeEntry({ artifact_id: "id-2", title: "Search", default_selected: false }),
          ]}
          onConfirm={vi.fn()}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /^All$/i }));
      expect(screen.getByText(/2 of 2 selected/i)).toBeInTheDocument();
    });

    it("Select None deselects all entries", () => {
      render(
        <SarahInputSelection
          testCases={[
            makeEntry({ artifact_id: "id-1" }),
            makeEntry({ artifact_id: "id-2", title: "Search" }),
          ]}
          onConfirm={vi.fn()}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /^None$/i }));
      expect(screen.getByText(/0 of 2 selected/i)).toBeInTheDocument();
    });
  });

  describe("Confirm button", () => {
    it("calls onConfirm with selected artifact IDs", () => {
      const onConfirm = vi.fn();
      render(
        <SarahInputSelection
          testCases={[makeEntry({ artifact_id: "abc-123" })]}
          onConfirm={onConfirm}
        />,
      );
      fireEvent.click(
        screen.getByRole("button", { name: /Confirm & Generate/i }),
      );
      expect(onConfirm).toHaveBeenCalledWith(["abc-123"]);
    });

    it("shows an enabled Skip button (not Confirm) when nothing is selected", () => {
      render(
        <SarahInputSelection
          testCases={[makeEntry({ default_selected: false })]}
          onConfirm={vi.fn()}
          onSkip={vi.fn()}
        />,
      );
      expect(
        screen.queryByRole("button", { name: /Confirm & Generate/i }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^Skip/i })).not.toBeDisabled();
    });

    it("calls onSkip (not onConfirm) when Skip is clicked with nothing selected", () => {
      const onConfirm = vi.fn();
      const onSkip = vi.fn();
      render(
        <SarahInputSelection
          testCases={[makeEntry({ default_selected: false })]}
          onConfirm={onConfirm}
          onSkip={onSkip}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: /^Skip/i }));
      expect(onSkip).toHaveBeenCalledTimes(1);
      expect(onConfirm).not.toHaveBeenCalled();
    });

    it("Confirm button is enabled when at least one entry is selected", () => {
      render(
        <SarahInputSelection
          testCases={[makeEntry({ default_selected: true })]}
          onConfirm={vi.fn()}
        />,
      );
      expect(
        screen.getByRole("button", { name: /Confirm & Generate/i }),
      ).not.toBeDisabled();
    });

    it("Confirm button is disabled when prop disabled=true even with selection", () => {
      render(
        <SarahInputSelection
          testCases={[makeEntry()]}
          onConfirm={vi.fn()}
          disabled={true}
        />,
      );
      expect(
        screen.getByRole("button", { name: /Confirm & Generate/i }),
      ).toBeDisabled();
    });

    it("Confirm sends only the selected subset when user deselects one", () => {
      const onConfirm = vi.fn();
      render(
        <SarahInputSelection
          testCases={[
            makeEntry({ artifact_id: "id-1", title: "Login" }),
            makeEntry({
              artifact_id: "id-2",
              title: "Search",
              default_selected: true,
            }),
          ]}
          onConfirm={onConfirm}
        />,
      );
      // Uncheck first entry (use aria-label which matches title exactly)
      fireEvent.click(screen.getByRole("checkbox", { name: "Login" }));
      fireEvent.click(
        screen.getByRole("button", { name: /Confirm & Generate/i }),
      );
      expect(onConfirm).toHaveBeenCalledWith(["id-2"]);
    });
  });

  describe("Empty state", () => {
    it("renders empty-state message when testCases is empty", () => {
      render(<SarahInputSelection testCases={[]} onConfirm={vi.fn()} />);
      expect(
        screen.getByText(/No test cases available/i),
      ).toBeInTheDocument();
    });
  });
});
