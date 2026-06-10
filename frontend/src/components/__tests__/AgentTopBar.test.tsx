import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AgentTopBar } from "../AgentTopBar";
import { AGENTS } from "../../types/pipeline";

describe("AgentTopBar", () => {
  it("renders agent identity correctly", () => {
    render(<AgentTopBar agent={AGENTS.Alice} status="start" />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });

  it("renders step counter correctly", () => {
    render(<AgentTopBar agent={AGENTS.Bob} status="start" />);
    expect(screen.getByText("Step 2 of 5")).toBeInTheDocument();
    expect(screen.getByText("Requirements Extraction")).toBeInTheDocument();
  });

  it("renders start status correctly", () => {
    render(<AgentTopBar agent={AGENTS.Alice} status="start" />);
    expect(screen.getByText("Start")).toBeInTheDocument();
  });

  it("renders processing status correctly", () => {
    render(<AgentTopBar agent={AGENTS.Alice} status="processing" />);
    expect(screen.getByText("Processing")).toBeInTheDocument();
  });

  it("renders review request status correctly", () => {
    render(<AgentTopBar agent={AGENTS.Alice} status="review_request" />);
    expect(screen.getByText("Review Requested")).toBeInTheDocument();
  });

  it("renders done status correctly", () => {
    render(<AgentTopBar agent={AGENTS.Alice} status="done" />);
    expect(screen.getByText("Done")).toBeInTheDocument();
  });

  it("has banner role for accessibility", () => {
    render(<AgentTopBar agent={AGENTS.Alice} status="start" />);
    expect(screen.getByRole("banner")).toHaveAttribute("role", "banner");
  });
});
