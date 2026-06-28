import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { SarahInputsForm, type SarahInputsRequest } from "../SarahInputsForm";

const ENVS = [
  { name: "Test 1", url: "https://test1.app" },
  { name: "Production", url: "https://app.example.com" },
];

const withEnvs: SarahInputsRequest = {
  needsUrl: true,
  environments: ENVS,
};

const freeText: SarahInputsRequest = {
  needsUrl: true,
  environments: [],
};

describe("SarahInputsForm", () => {
  it("submits a free-text URL when the project has no environments", () => {
    const onSubmit = vi.fn();
    render(
      <SarahInputsForm
        request={freeText}
        appRoles={[]}
        sessions={[]}
        onSubmit={onSubmit}
      />,
    );

    // No CDP / chrome-path fields, no Admin-Dashboard helper line.
    expect(screen.queryByTestId("sarah-cdp-url")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sarah-chrome-path")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Environments are configured per project in the Admin Dashboard/i),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId("sarah-target-url"), {
      target: { value: "https://app.test/page" },
    });
    fireEvent.click(screen.getByTestId("sarah-inputs-submit"));
    // Free-text path: no configured environment, so the name is empty.
    expect(onSubmit).toHaveBeenCalledWith({
      environment: "",
      targetUrl: "https://app.test/page",
    });
  });

  it("offers an environment dropdown (not a URL field) and submits the chosen env's name + URL", () => {
    const onSubmit = vi.fn();
    render(
      <SarahInputsForm
        request={withEnvs}
        appRoles={[]}
        sessions={[]}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.queryByTestId("sarah-target-url")).not.toBeInTheDocument();
    const select = screen.getByTestId("sarah-environment");

    // Cannot submit until an environment is chosen.
    fireEvent.click(screen.getByTestId("sarah-inputs-submit"));
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(select, { target: { value: "Production" } });
    fireEvent.click(screen.getByTestId("sarah-inputs-submit"));
    // Both the env NAME and its URL come from the SAME selected env object.
    expect(onSubmit).toHaveBeenCalledWith({
      environment: "Production",
      targetUrl: "https://app.example.com",
    });
  });

  it("shows per-role capture status for the selected environment", () => {
    render(
      <SarahInputsForm
        request={withEnvs}
        appRoles={["Admin", "User"]}
        sessions={[{ environment: "Production", role: "Admin" }]}
        onSubmit={vi.fn()}
      />,
    );

    // No status shown until an environment is selected.
    expect(screen.queryByTestId("sarah-session-status")).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId("sarah-environment"), {
      target: { value: "Production" },
    });

    const status = screen.getByTestId("sarah-session-status");
    // Admin has a captured session for Production → "✓ Captured".
    expect(status).toHaveTextContent("Admin");
    expect(status).toHaveTextContent("✓ Captured");
    // User has none → "Not logged in".
    expect(screen.getByText("Not logged in")).toBeInTheDocument();
  });
});
