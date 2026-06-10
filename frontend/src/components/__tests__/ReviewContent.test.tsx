import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ReviewContent } from "../ReviewContent";

describe("ReviewContent", () => {
  it("renders markdown content", () => {
    render(<ReviewContent content="**Bold text** and *italic*" />);

    // Check bold text is wrapped in strong element
    const boldElement = screen.getByText("Bold text");
    expect(boldElement.tagName.toLowerCase()).toBe("strong");

    // Check italic text is wrapped in em element
    const italicElement = screen.getByText("italic");
    expect(italicElement.tagName.toLowerCase()).toBe("em");
  });

  it("renders code blocks correctly", () => {
    // Basic test to see if standard code block structure handles it
    // since react-syntax-highlighter is complex to mock/test easily via RTL
    const { container } = render(
      <ReviewContent content={`\`\`\`json\n{"foo": "bar"}\n\`\`\``} />,
    );

    // The rendered output will have syntax highlighter elements, we can just check for text
    expect(container.textContent).toContain('"foo"');
    expect(container.textContent).toContain('"bar"');
  });

  it("handles null/empty content gracefully", () => {
    // @ts-expect-error Testing null input
    const { container } = render(<ReviewContent content={null} />);

    // Should not crash and render without errors
    expect(container).toBeInTheDocument();
  });

  it("handles empty string content", () => {
    const { container } = render(<ReviewContent content="" />);

    // Should render without errors
    expect(container).toBeInTheDocument();
  });
});
