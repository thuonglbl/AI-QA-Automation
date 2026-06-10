import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ProviderConfigPanel } from "../ProviderConfigPanel";
import type { ProviderConfigResponse } from "@/types/provider";

const configuredThread: ProviderConfigResponse = {
  configured: true,
  source: "thread",
  provider: "claude",
  provider_name: "Claude (Anthropic)",
  endpoint: "https://***",
  test_result: "success",
  tested_at: "2026-06-10T10:00:00Z",
  agents: [
    { agent: "alice", model: "claude-3-5-sonnet", temperature: 0.7, rationale: "Chosen for config" },
    { agent: "bob", model: "claude-3-opus", temperature: 0.5, rationale: "Chosen for vision" },
  ],
};

const configuredSaved: ProviderConfigResponse = {
  configured: true,
  source: "saved",
  provider: "openai",
  provider_name: "OpenAI",
  endpoint: "https://***",
  test_result: "success",
  tested_at: null,
  agents: [],
};

const notConfigured: ProviderConfigResponse = {
  configured: false,
  source: "none",
  provider: null,
  provider_name: null,
  endpoint: null,
  test_result: null,
  tested_at: null,
  agents: [],
};

describe("ProviderConfigPanel", () => {
  it("renders provider name for a configured thread snapshot", () => {
    render(
      <ProviderConfigPanel
        config={configuredThread}
        onChangeConfig={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Claude (Anthropic)")).toBeInTheDocument();
    expect(screen.getByText(/this thread/)).toBeInTheDocument();
  });

  it("renders agent models and rationales", () => {
    render(
      <ProviderConfigPanel
        config={configuredThread}
        onChangeConfig={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText(/alice/i)).toBeInTheDocument();
    expect(screen.getByText(/claude-3-5-sonnet/)).toBeInTheDocument();
    expect(screen.getByText(/Chosen for config/)).toBeInTheDocument();

    expect(screen.getByText(/bob/i)).toBeInTheDocument();
    expect(screen.getByText(/claude-3-opus/)).toBeInTheDocument();
    expect(screen.getByText(/Chosen for vision/)).toBeInTheDocument();
  });

  it("shows 'saved (project default)' source label", () => {
    render(
      <ProviderConfigPanel
        config={configuredSaved}
        onChangeConfig={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText(/saved \(project default\)/)).toBeInTheDocument();
  });

  it("shows 'not configured' message when configured is false", () => {
    render(
      <ProviderConfigPanel
        config={notConfigured}
        onChangeConfig={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText(/No provider configured yet/)).toBeInTheDocument();
  });

  it("never displays a secret sentinel value", () => {
    const configWithSecretAttempt: ProviderConfigResponse = {
      ...configuredThread,
      provider_name: "Claude",
      endpoint: "https://***",
    };
    const { container } = render(
      <ProviderConfigPanel
        config={configWithSecretAttempt}
        onChangeConfig={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const SECRET_SENTINEL = "sk-SUPER-SECRET-API-KEY";
    expect(container.innerHTML).not.toContain(SECRET_SENTINEL);
    expect(container.innerHTML).not.toContain("api_key");
    expect(container.innerHTML).not.toContain("credential_reference");
  });

  it("calls onChangeConfig when 'Change configuration' is clicked", () => {
    const onChangeConfig = vi.fn();
    render(
      <ProviderConfigPanel
        config={configuredThread}
        onChangeConfig={onChangeConfig}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("change-config-btn"));
    expect(onChangeConfig).toHaveBeenCalledOnce();
  });

  it("calls onClose when 'Close' button is clicked", () => {
    const onClose = vi.fn();
    render(
      <ProviderConfigPanel
        config={configuredThread}
        onChangeConfig={vi.fn()}
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByText("Close"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when overlay backdrop is clicked", () => {
    const onClose = vi.fn();
    render(
      <ProviderConfigPanel
        config={configuredThread}
        onChangeConfig={vi.fn()}
        onClose={onClose}
      />,
    );

    const dialog = screen.getByRole("dialog");
    fireEvent.click(dialog);
    expect(onClose).toHaveBeenCalledOnce();
  });
});
