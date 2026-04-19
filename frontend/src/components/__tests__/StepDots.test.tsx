import React from 'react';
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StepDots } from "../StepDots";

describe("StepDots", () => {
  it("renders with correct accessibility attributes", () => {
    render(<StepDots currentStep={3} completedSteps={2} />);
    const progressbar = screen.getByRole("progressbar");
    expect(progressbar).toBeInTheDocument();
    expect(progressbar).toHaveAttribute("aria-valuenow", "3");
    expect(progressbar).toHaveAttribute("aria-valuemax", "5");
  });

  it("renders correct number of dots", () => {
    const { container } = render(<StepDots currentStep={1} completedSteps={0} />);
    const dots = container.querySelectorAll('.rounded-full');
    expect(dots).toHaveLength(5);
  });
});
