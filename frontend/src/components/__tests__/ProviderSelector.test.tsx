import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ProviderSelector } from "../ProviderSelector";
import type { ProviderOption } from "@/types/provider";

const mockProviders: ProviderOption[] = [
  {
    id: "claude",
    name: "Claude (Anthropic)",
    description: "Anthropic's Claude model",
    qualityRank: 2,
    securityLevel: "enterprise",
    credentialFields: [
      { name: "api_key", label: "API Key", type: "password", required: true },
    ],
  },
  {
    id: "on-premises",
    name: "On-Premises LLM",
    description: "Internal infrastructure · Company API key",
    qualityRank: 5,
    securityLevel: "highest",
    credentialFields: [
      { name: "api_key", label: "API Key", type: "password", required: true },
    ],
  },
];

describe("ProviderSelector", () => {
  it("renders provider options with correct rankings", () => {
    render(<ProviderSelector options={mockProviders} onSelect={vi.fn()} />);

    expect(screen.getByText(/Claude \(Anthropic\)/)).toBeInTheDocument();
    expect(screen.getByText(/On-Premises LLM/)).toBeInTheDocument();
    expect(screen.getByText(/Second quality/i)).toBeInTheDocument();
    expect(screen.getByText(/Varied quality/i)).toBeInTheDocument();
  });

  it("shows security level badges", () => {
    render(<ProviderSelector options={mockProviders} onSelect={vi.fn()} />);

    expect(screen.getByText(/Strong secure/i)).toBeInTheDocument();
    expect(screen.getByText(/Most secure/i)).toBeInTheDocument();
  });

  it("shows credential fields when provider selected", () => {
    render(<ProviderSelector options={mockProviders} onSelect={vi.fn()} />);

    // Click on Claude provider
    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    // Should show credential form
    expect(screen.getByPlaceholderText(/Enter API Key/i)).toBeInTheDocument();
  });

  it("shows credential fields for on-premises provider", () => {
    render(<ProviderSelector options={mockProviders} onSelect={vi.fn()} />);

    // Click on On-Premises provider
    fireEvent.click(screen.getByText(/On-Premises LLM/));

    // Should show API key field
    expect(screen.getByPlaceholderText(/Enter API Key/i)).toBeInTheDocument();
  });

  it("shows 'key on file' hint when api_key_configured is true (Task 10 — no pre-fill)", () => {
    const onPremDefaults = {
      api_key_configured: true,
    };

    render(
      <ProviderSelector
        options={mockProviders}
        onPremDefaults={onPremDefaults}
        onSelect={vi.fn()}
      />,
    );

    // Click on On-Premises provider
    fireEvent.click(screen.getByText(/On-Premises LLM/));

    // Should show "Key on file" placeholder, NOT pre-fill the value
    const apiKeyInput = screen.getByPlaceholderText(
      /Key on file/i,
    ) as HTMLInputElement;
    expect(apiKeyInput.value).toBe("");
  });

  it("validates required fields before submitting", async () => {
    const onSelect = vi.fn();

    render(<ProviderSelector options={mockProviders} onSelect={onSelect} />);

    // Click on Claude provider
    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    // Click start without entering credentials
    fireEvent.click(screen.getByRole("button", { name: /Start/i }));

    // Should show validation error
    await waitFor(() => {
      expect(screen.getByText(/API Key is required/i)).toBeInTheDocument();
    });

    // onSelect should not have been called
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("calls onSelect with provider and credentials when valid", async () => {
    const onSelect = vi.fn();

    render(<ProviderSelector options={mockProviders} onSelect={onSelect} />);

    // Click on Claude provider
    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    // Enter API key
    const apiKeyInput = screen.getByPlaceholderText(/Enter API Key/i);
    fireEvent.change(apiKeyInput, { target: { value: "my-api-key-12345" } });

    // Click start
    fireEvent.click(screen.getByRole("button", { name: /Start/i }));

    // onSelect should be called with provider and credentials
    await waitFor(() => {
      expect(onSelect).toHaveBeenCalledWith("claude", {
        api_key: "my-api-key-12345",
      });
    });
  });

  it("disables interaction when disabled prop is true", () => {
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
        disabled={true}
      />,
    );

    // Cards should have disabled styling
    const claudeCard = screen
      .getByText(/Claude \(Anthropic\)/)
      .closest("div.border");
    expect(claudeCard).toHaveClass("opacity-50");
  });

  it("disables providers not in enabledProviders list", () => {
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
        enabledProviders={["claude"]}
      />,
    );

    // Claude should be enabled (in list)
    const claudeCard = screen.getByText(/Claude \(Anthropic\)/).closest("div.border");
    expect(claudeCard).not.toHaveClass("opacity-40");
    expect(claudeCard).not.toHaveClass("cursor-not-allowed");

    // On-Premises should be disabled (not in list)
    const onPremCard = screen.getByText(/On-Premises LLM/).closest("div.border");
    expect(onPremCard).toHaveClass("border-slate-200");
    expect(onPremCard).toHaveClass("bg-slate-100");
    expect(onPremCard).toHaveClass("opacity-40");
    expect(onPremCard).toHaveClass("cursor-not-allowed");
  });

  it("shows tooltip for disabled provider", () => {
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
        enabledProviders={["claude"]}
      />,
    );

    // The card div (not the text node) carries the title attribute
    const onPremCard = screen.getByText(/On-Premises LLM/).closest("div.border");
    expect(onPremCard).toHaveAttribute(
      "title",
      "Your project cannot choose this provider. Please contact your administrator if something is wrong."
    );
  });

  it("allows clicking enabled provider when enabledProviders is empty (backward compat)", () => {
    const onSelect = vi.fn();

    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={onSelect}
        enabledProviders={[]}
      />,
    );

    // Both providers should be clickable (empty list = all enabled)
    const claudeCard = screen.getByText(/Claude \(Anthropic\)/);
    const onPremCard = screen.getByText(/On-Premises LLM/);

    expect(claudeCard.closest("div.border")).not.toHaveClass("cursor-not-allowed");
    expect(onPremCard.closest("div.border")).not.toHaveClass("cursor-not-allowed");

    // Click Claude
    fireEvent.click(claudeCard);
    expect(screen.getByPlaceholderText(/Enter API Key/i)).toBeInTheDocument();
  });

  it("allows clicking provider when enabledProviders is undefined (backward compat)", () => {
    const onSelect = vi.fn();

    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={onSelect}
        // enabledProviders prop omitted
      />,
    );

    // Both providers should be clickable
    const claudeCard = screen.getByText(/Claude \(Anthropic\)/);
    fireEvent.click(claudeCard);

    // Credential form should appear
    expect(screen.getByPlaceholderText(/Enter API Key/i)).toBeInTheDocument();
  });

  it("applies disabled styling when both disabled prop and enabledProviders restrict", () => {
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
        disabled={true}
        enabledProviders={["claude"]}
      />,
    );

    // Claude is enabled by enabledProviders but disabled by prop
    const claudeCard = screen.getByText(/Claude \(Anthropic\)/).closest("div.border");
    expect(claudeCard).toHaveClass("opacity-50");

    // On-Premises is disabled by both
    const onPremCard = screen.getByText(/On-Premises LLM/).closest("div.border");
    expect(onPremCard).toHaveClass("opacity-40");
  });

  it("renders all provider icons for enabled providers", () => {
    const providers: ProviderOption[] = [
      {
        id: "claude",
        name: "Claude (Anthropic)",
        description: "Anthropic's Claude model",
        qualityRank: 2,
        securityLevel: "enterprise",
        credentialFields: [
          { name: "api_key", label: "API Key", type: "password", required: true },
        ],
      },
      {
        id: "gemini",
        name: "Gemini (Google)",
        description: "Google's Gemini model",
        qualityRank: 1,
        securityLevel: "cloud",
        credentialFields: [
          { name: "api_key", label: "API Key", type: "password", required: true },
        ],
      },
      {
        id: "browser-use-cloud",
        name: "Browser Use",
        description: "Browser automation specialist",
        qualityRank: 4,
        securityLevel: "good",
        credentialFields: [
          { name: "api_key", label: "API Key", type: "password", required: true },
        ],
      },
    ];

    render(
      <ProviderSelector
        options={providers}
        onSelect={vi.fn()}
        enabledProviders={["claude", "browser-use-cloud"]}
      />,
    );

    // Claude should be enabled
    const claudeCard = screen.getByText(/Claude \(Anthropic\)/).closest("div.border");
    expect(claudeCard).not.toHaveClass("opacity-40");

    // Gemini should be disabled
    const geminiCard = screen.getByText(/Gemini \(Google\)/).closest("div.border");
    expect(geminiCard).toHaveClass("opacity-40");

    // Browser Use should be enabled
    const browserCard = screen.getByText(/Browser Use/).closest("div.border");
    expect(browserCard).not.toHaveClass("opacity-40");
  });
});
