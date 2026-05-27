import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ProviderSelector } from "../ProviderSelector";
import type { ProviderOption } from "@/types/provider";

const mockProviders: ProviderOption[] = [
  {
    id: "claude",
    name: "Claude (Anthropic)",
    qualityRank: 2,
    securityLevel: "enterprise",
    credentialFields: [{ name: "api_key", label: "API Key", type: "password", required: true }],
  },
  {
    id: "on-premises",
    name: "On-Premises LLM",
    qualityRank: 4,
    securityLevel: "highest",
    credentialFields: [
      { name: "api_key", label: "API Key", type: "password", required: true },
    ],
  },
];

describe("ProviderSelector", () => {
  it("renders provider options with correct rankings", () => {
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByText(/Claude \(Anthropic\)/)).toBeInTheDocument();
    expect(screen.getByText("On-Premises LLM")).toBeInTheDocument();
    expect(screen.getByText("2nd Choice")).toBeInTheDocument();
    expect(screen.getByText("4th Choice")).toBeInTheDocument();
  });

  it("shows security level badges", () => {
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByText("Enterprise")).toBeInTheDocument();
    expect(screen.getByText("Highest Security")).toBeInTheDocument();
  });

  it("shows credential fields when provider selected", () => {
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
      />
    );

    // Click on Claude provider
    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    // Should show credential form
    expect(screen.getByLabelText(/API Key/)).toBeInTheDocument();
  });

  it("shows credential fields for on-premises provider", () => {
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
      />
    );

    // Click on On-Premises provider
    fireEvent.click(screen.getByText("On-Premises LLM"));

    // Should show API key field
    expect(screen.getByLabelText(/API Key/)).toBeInTheDocument();
  });

  it("pre-fills on-premises defaults when provided", () => {
    const onPremDefaults = {
      api_key: "default-key-123",
    };

    render(
      <ProviderSelector
        options={mockProviders}
        onPremDefaults={onPremDefaults}
        onSelect={vi.fn()}
      />
    );

    // Click on On-Premises provider
    fireEvent.click(screen.getByText("On-Premises LLM"));

    // Should pre-fill defaults
    const apiKeyInput = screen.getByLabelText(/API Key/) as HTMLInputElement;
    expect(apiKeyInput.value).toBe("default-key-123");
  });

  it("validates required fields before submitting", async () => {
    const onSelect = vi.fn();

    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={onSelect}
      />
    );

    // Click on Claude provider
    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    // Click start without entering credentials
    fireEvent.click(screen.getByText(/Test Connection/));

    // Should show validation error
    await waitFor(() => {
      expect(screen.getByText(/API Key is required/)).toBeInTheDocument();
    });

    // onSelect should not have been called
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("calls onSelect with provider and credentials when valid", async () => {
    const onSelect = vi.fn();

    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={onSelect}
      />
    );

    // Click on Claude provider
    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    // Enter API key
    const apiKeyInput = screen.getByLabelText(/API Key/);
    fireEvent.change(apiKeyInput, { target: { value: "my-api-key-12345" } });

    // Click start
    fireEvent.click(screen.getByText(/Test Connection/));

    // onSelect should be called with provider and credentials
    await waitFor(() => {
      expect(onSelect).toHaveBeenCalledWith("claude", { api_key: "my-api-key-12345" });
    });
  });

  it("disables interaction when disabled prop is true", () => {
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
        disabled={true}
      />
    );

    // Cards should have disabled styling
    const claudeCard = screen.getByText(/Claude \(Anthropic\)/).closest("div.border");
    expect(claudeCard).toHaveClass("opacity-50");
  });


});
