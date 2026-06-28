import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { ProviderSelector } from "../ProviderSelector";
import type { ProviderOption } from "@/types/provider";
import { AuthContext } from "@/contexts/AuthContext";
import type { AuthUser } from "@/lib/auth";

/** Render under an AuthContext with a fixed timezone so MessageTime formats deterministically. */
function renderWithTz(tz: string, ui: ReactNode) {
  const user: AuthUser = { email: "t@e.vn", name: "T", timezone: tz };
  return render(
    <AuthContext.Provider
      value={{
        isAuthenticated: true,
        user,
        isLoading: false,
        error: null,
        logout: async () => {},
        refresh: async () => {},
        setAuthStatus: () => {},
      }}
    >
      {ui}
    </AuthContext.Provider>,
  );
}

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

    // Personal providers prompt for a personal API key.
    expect(
      screen.getByPlaceholderText(/personal API key/i),
    ).toBeInTheDocument();
  });

  it("shows credential fields for on-premises provider", () => {
    render(<ProviderSelector options={mockProviders} onSelect={vi.fn()} />);

    // Click on On-Premises provider
    fireEvent.click(screen.getByText(/On-Premises LLM/));

    // On-Premises prompts for the company API key.
    expect(
      screen.getByPlaceholderText(/company API key/i),
    ).toBeInTheDocument();
  });

  it("renders a Login SSO button (not credential inputs) for an SSO provider", () => {
    const ssoProviders: ProviderOption[] = [
      {
        id: "claude-sso",
        name: "Anthropic / Claude (SSO)",
        description: "Cloud · Enterprise SSO login",
        qualityRank: 2,
        securityLevel: "enterprise",
        authMethod: "sso",
        credentialFields: [],
      },
    ];
    render(<ProviderSelector options={ssoProviders} onSelect={vi.fn()} />);

    fireEvent.click(screen.getByTestId("provider-card-claude-sso"));

    expect(screen.getByTestId("sso-login-button")).toBeInTheDocument();
    expect(screen.getByTestId("sso-login-button")).toHaveTextContent(/Login SSO/i);
    // SSO providers must NOT show the api-key text input.
    expect(
      screen.queryByTestId("credential-input-api_key"),
    ).not.toBeInTheDocument();
  });

  it("never pre-fills the on-prem api_key value when the form is shown (Task 10)", () => {
    // No configuredProviders → on-prem shows the form instead of auto-connecting.
    render(
      <ProviderSelector
        options={mockProviders}
        onPremDefaults={{ api_key_configured: true }}
        onSelect={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText(/On-Premises LLM/));

    // Company-key prompt, and the value is NEVER pre-filled.
    const apiKeyInput = screen.getByPlaceholderText(
      /company API key/i,
    ) as HTMLInputElement;
    expect(apiKeyInput.value).toBe("");
  });

  it("auto-connects (no prompt) when a key is already on file", () => {
    const onSelect = vi.fn();
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={onSelect}
        configuredProviders={["claude"]}
      />,
    );

    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    // Clicking immediately connects with the stored key (blank credentials) — no
    // typing, no Start click. (The parent then swaps in the read-only view.)
    expect(onSelect).toHaveBeenCalledWith("claude", {});
  });

  it("does NOT auto-connect a provider with no key on file (shows the prompt)", () => {
    const onSelect = vi.fn();
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={onSelect}
        configuredProviders={["on-premises"]}
      />,
    );

    // Claude has no key on file → prompt shown, onSelect not called on click.
    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByTestId("credential-input-api_key")).toBeInTheDocument();
  });

  it("re-prompts with the invalid-key placeholder when a stored key failed", () => {
    const onSelect = vi.fn();
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={onSelect}
        configuredProviders={["claude"]}
        invalidProvider="claude"
      />,
    );

    // The failed provider is auto-selected and shows the input (no auto-connect),
    // with the "invalid key" placeholder.
    expect(
      screen.getByPlaceholderText(/invalid.*Please input a new one/i),
    ).toBeInTheDocument();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("clears the stale key on a repeat failure of the same provider", () => {
    const props = {
      options: mockProviders,
      onSelect: vi.fn(),
      configuredProviders: ["claude"],
      invalidProvider: "claude",
    };
    const { rerender } = render(<ProviderSelector {...props} invalidAttempt={1} />);

    // User retypes a (still wrong) key.
    const input = screen.getByPlaceholderText(
      /invalid.*Please input a new one/i,
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "still-bad-key" } });
    expect(input.value).toBe("still-bad-key");

    // Same provider fails again → bumped attempt re-clears the input even though
    // invalidProvider is unchanged.
    rerender(<ProviderSelector {...props} invalidAttempt={2} />);
    expect(
      (screen.getByPlaceholderText(/invalid/i) as HTMLInputElement).value,
    ).toBe("");
  });



  it("calls onSelect with provider and credentials when valid", async () => {
    const onSelect = vi.fn();

    render(<ProviderSelector options={mockProviders} onSelect={onSelect} />);

    // Click on Claude provider
    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    // Enter API key
    const apiKeyInput = screen.getByPlaceholderText(/personal API key/i);
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

  it("disables Start button and shows 'enter credentials' when credentials are missing", () => {
    render(<ProviderSelector options={mockProviders} onSelect={vi.fn()} />);
    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    const startBtn = screen.getByRole("button", { name: "Start" });
    expect(startBtn).toBeDisabled();
    expect(screen.getByText("enter credentials")).toBeInTheDocument();

    // Type a credential to enable it
    fireEvent.change(screen.getByPlaceholderText(/personal API key/i), {
      target: { value: "sk-1234" },
    });

    expect(startBtn).not.toBeDisabled();
    expect(screen.queryByText("enter credentials")).not.toBeInTheDocument();
  });

  it("shows 'connection failed, fix and retry' when testing an invalid provider", () => {
    render(
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
        invalidProvider="claude"
      />
    );
    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    // Fill credentials so it's not disabled for missing creds
    fireEvent.change(screen.getByPlaceholderText(/Your API key is invalid/i), {
      target: { value: "sk-wrong" },
    });

    const startBtn = screen.getByRole("button", { name: "Start" });
    // The button shouldn't be disabled (they can retest), but it shows the error
    expect(startBtn).not.toBeDisabled();
    expect(screen.getByText("connection failed, fix and retry")).toBeInTheDocument();
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
    expect(screen.getByPlaceholderText(/personal API key/i)).toBeInTheDocument();
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
    expect(screen.getByPlaceholderText(/personal API key/i)).toBeInTheDocument();
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

  it("renders the Alice prompt time from messageTimestamp (user timezone)", () => {
    renderWithTz(
      "UTC",
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
        messageTimestamp="2026-04-16T10:00:00Z"
      />,
    );

    // No selection yet → only the Alice prompt card is shown, so its time is unique.
    const aliceTime = screen.getByText("10:00:00");
    expect(aliceTime).toBeInTheDocument();
    expect(aliceTime).toHaveAttribute("title");
  });

  it('renders the submitted-selection time beside the "You" header', () => {
    renderWithTz(
      "UTC",
      <ProviderSelector
        options={mockProviders}
        onSelect={vi.fn()}
        submittedSelection={{
          providerId: "claude",
          providerName: "Claude (Anthropic)",
          credentials: { api_key: "secret" },
        }}
        selectionTimestamp="2026-04-16T10:05:00Z"
      />,
    );

    const youTime = screen.getByText("10:05:00");
    expect(youTime).toBeInTheDocument();
    expect(youTime).toHaveAttribute("title");
  });

  it("falls back to a client time on the Alice and You labels when no timestamp is provided", () => {
    // Every sender-labeled bubble must always show an hh:mm:ss; with no backing
    // timestamp, MessageTime's fallbackToNow stamps a frozen client time instead of
    // rendering nothing. After picking a provider, both the Alice prompt and the
    // "You" credential card show a time.
    renderWithTz(
      "UTC",
      <ProviderSelector options={mockProviders} onSelect={vi.fn()} />,
    );

    fireEvent.click(screen.getByText(/Claude \(Anthropic\)/));

    expect(screen.getByText("You")).toBeInTheDocument();
    const times = screen.getAllByText(/^\d{2}:\d{2}:\d{2}$/);
    expect(times.length).toBe(2);
  });
});
