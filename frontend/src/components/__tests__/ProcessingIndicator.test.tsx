import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ProcessingIndicator } from "../ProcessingIndicator";

describe("ProcessingIndicator", () => {
  it("renders 3 animated dots", () => {
    render(<ProcessingIndicator message="Loading..." />);

    // Check for 3 dots (spans with rounded-full class)
    const dots = document.querySelectorAll(".rounded-full");
    expect(dots.length).toBe(3);
  });

  it("displays the status message", () => {
    const message = "Reading page 3 of 5...";
    render(<ProcessingIndicator message={message} />);

    expect(screen.getByText(message)).toBeInTheDocument();
  });

  it("has animation classes when isActive is true", () => {
    render(<ProcessingIndicator message="Loading" isActive={true} />);

    const dots = document.querySelectorAll(".rounded-full");
    expect(dots[0]).toHaveClass("animate-bounce");
    expect(dots[1]).toHaveClass("animate-bounce");
    expect(dots[2]).toHaveClass("animate-bounce");
  });

  it("stops animation when isActive is false", () => {
    render(<ProcessingIndicator message="Loading" isActive={false} />);

    const dots = document.querySelectorAll(".rounded-full");
    dots.forEach((dot) => {
      expect(dot).not.toHaveClass("animate-bounce");
    });
  });

  it("displays the agent name", () => {
    render(<ProcessingIndicator message="Loading" agentName="Sarah" />);
    expect(screen.getByText("Sarah")).toBeInTheDocument();
  });
});
