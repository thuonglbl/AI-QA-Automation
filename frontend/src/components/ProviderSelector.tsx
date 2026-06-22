import { useEffect, useRef, useState, type ReactElement } from "react";
import type { ProviderOption, ProviderCredentials } from "@/types/provider";
import { apiFetch, getSafeApiErrorMessage } from "@/lib/api";
import { MessageTime } from "@/components/MessageTime";

interface SubmittedSelection {
  providerId: string;
  providerName: string;
  credentials: Record<string, string>;
}

interface ProviderSelectorProps {
  options: ProviderOption[] | null;
  onPremDefaults?: {
    server_url?: string;
    api_key_configured: boolean;
  };
  onSelect: (providerId: string, credentials: Record<string, string>) => void;
  disabled?: boolean;
  submittedSelection?: SubmittedSelection | null;
  /** Provider IDs enabled at the project level. Empty/undefined = all enabled. */
  enabledProviders?: string[];
  /** Provider IDs that already have a stored key — clicking auto-connects, no prompt. */
  configuredProviders?: string[];
  /** Provider whose stored key just failed — re-prompt for a new key. */
  invalidProvider?: string | null;
  /** Increments on each failure so a repeat failure of the same provider re-clears. */
  invalidAttempt?: number;
  /** ISO timestamp of Alice's provider-prompt message; rendered as hh:mm:ss beside "Alice". */
  messageTimestamp?: string;
  /** ISO timestamp of the user's submitted-selection marker; rendered beside "You". */
  selectionTimestamp?: string;
}

const QUALITY_TAGS: Record<number, string> = {
  1: "Best quality",
  2: "Second quality",
  3: "Third quality",
  4: "Fourth quality",
  5: "Varied quality",
};

const SECURITY_TAGS: Record<string, string> = {
  cloud: "Normal secure",
  enterprise: "Strong secure",
  highest: "Most secure",
  good: "Good secure",
};

const QUALITY_TAG_STYLES: Record<number, string> = {
  1: "bg-[#f0fdf4] text-[#16a34a]",
  2: "bg-[#fffbeb] text-[#d97706]",
  3: "bg-[#f5f3ff] text-[#7c3aed]",
  4: "bg-[#f1f5f9] text-[#64748b]",
  5: "bg-[#eff6ff] text-[#2563eb]",
};

const SECURITY_TAG_STYLES: Record<string, string> = {
  cloud: "bg-[#f1f5f9] text-[#64748b]",
  enterprise: "bg-[#eff6ff] text-[#2563eb]",
  highest: "bg-[#f0fdf4] text-[#16a34a]",
  good: "bg-[#ccfbf1] text-[#0f766e]",
};

const PROVIDER_LOGOS: Record<string, ReactElement> = {
  "browser-use-cloud": (
    <img src="/provider-icons/browser-use.png" alt="Browser Use Cloud" className="w-5 h-5 object-contain" />
  ),
  claude: (
    <img src="/provider-icons/anthropic.svg" alt="Anthropic / Claude" className="w-5 h-5 object-contain" />
  ),
  "claude-sso": (
    <img src="/provider-icons/anthropic.svg" alt="Anthropic / Claude (SSO)" className="w-5 h-5 object-contain" />
  ),
  gemini: (
    <img src="/provider-icons/google-gemini.svg" alt="Google / Gemini" className="w-5 h-5 object-contain" />
  ),
  openai: (
    <img src="/provider-icons/openai.svg" alt="OpenAI / ChatGPT" className="w-5 h-5 object-contain" />
  ),
  "on-premises": (
    <img src="/provider-icons/on-premises.png" alt="On-Premises" className="w-5 h-5 object-contain" />
  ),
};

export function ProviderSelector({
  options,
  onPremDefaults,
  onSelect,
  disabled = false,
  submittedSelection,
  enabledProviders,
  configuredProviders,
  invalidProvider,
  invalidAttempt,
  messageTimestamp,
  selectionTimestamp,
}: ProviderSelectorProps) {
  const [selectedProvider, setSelectedProvider] = useState<string | null>(
    submittedSelection?.providerId || null,
  );
  const [credentials, setCredentials] = useState<Record<string, string>>(
    submittedSelection?.credentials || {},
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [ssoStatus, setSsoStatus] = useState<"idle" | "waiting">("idle");
  const [ssoError, setSsoError] = useState<string | null>(null);
  const ssoPollRef = useRef<number | null>(null);

  const isReadOnly = !!submittedSelection;
  const displayProvider = submittedSelection?.providerId || selectedProvider;
  const displayCredentials = submittedSelection?.credentials || credentials;
  const selectedOption = options?.find((p) => p.id === displayProvider);

  const handleProviderClick = (providerId: string) => {
    setSelectedProvider(providerId);
    setCredentials({});
    setErrors({});
    setSsoError(null);
    setSsoStatus("idle");
    if (ssoPollRef.current !== null) {
      window.clearTimeout(ssoPollRef.current);
      ssoPollRef.current = null;
    }

    const opt = options?.find((p) => p.id === providerId);
    // Key already on file (and not the one that just failed) → skip the prompt and
    // auto-connect with the stored key (backend resolves it from user_secrets). SSO
    // providers use their own Login button, never this path.
    if (
      opt?.authMethod !== "sso" &&
      providerId !== invalidProvider &&
      configuredProviders?.includes(providerId)
    ) {
      onSelect(providerId, {});
      return;
    }

    // Task 10: never pre-fill the api_key — show "Key on file" hint instead
    if (providerId === "on-premises" && onPremDefaults?.server_url) {
      setCredentials({ server_url: onPremDefaults.server_url });
    }
  };

  // A stored key just failed: select that provider and clear the stale value so the
  // user enters a fresh key (placeholder switches to the "invalid" message below).
  // Keyed on invalidAttempt too, so a REPEAT failure of the same provider re-clears
  // (the invalidProvider value alone would be unchanged and the effect wouldn't run).
  useEffect(() => {
    if (invalidProvider) {
      setSelectedProvider(invalidProvider);
      setCredentials({});
      setErrors({});
    }
  }, [invalidProvider, invalidAttempt]);

  // Claude SSO login: open the IdP tab, then poll until the backend reports the
  // token was stored, and proceed exactly like a normal provider "Start".
  const handleSsoLogin = async () => {
    if (!selectedProvider || disabled) return;
    setSsoError(null);
    setSsoStatus("waiting");
    try {
      const { authorize_url, state } = await apiFetch<{
        authorize_url: string;
        state: string;
        mode: string;
      }>("/auth/claude-sso/start", { method: "POST" });

      window.open(authorize_url, "_blank", "noopener,noreferrer");

      const startedAt = Date.now();
      const poll = async () => {
        let authenticated = false;
        try {
          const res = await apiFetch<{ authenticated: boolean }>(
            `/auth/claude-sso/status?state=${encodeURIComponent(state)}`,
          );
          authenticated = res.authenticated;
        } catch (_e) {
          // Transient error while the popup is open — keep polling until timeout.
        }
        if (authenticated) {
          ssoPollRef.current = null;
          setSsoStatus("idle");
          onSelect(selectedProvider, {});
          return;
        }
        if (Date.now() - startedAt > 5 * 60 * 1000) {
          ssoPollRef.current = null;
          setSsoStatus("idle");
          setSsoError("SSO login timed out. Please try again.");
          return;
        }
        ssoPollRef.current = window.setTimeout(() => void poll(), 1500);
      };
      ssoPollRef.current = window.setTimeout(() => void poll(), 1500);
    } catch (e) {
      setSsoStatus("idle");
      setSsoError(getSafeApiErrorMessage(e));
    }
  };

  const handleCredentialChange = (name: string, value: string) => {
    setCredentials((prev: Record<string, string>) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const isInvalidProvider = !!selectedProvider && selectedProvider === invalidProvider;

  // Placeholder for the api_key input. A provider with a key on file auto-connects
  // (handleProviderClick), so the credential form only ever renders when there is
  // NO key on file (fresh entry) or the stored key just failed (invalid) — both
  // require a key, hence no "leave blank to reuse" affordance here.
  const apiKeyPlaceholder = isInvalidProvider
    ? "Your API key is invalid - Please input a new one"
    : selectedProvider === "on-premises"
      ? "Please input your company API key"
      : "Please input your personal API key";

  const validateCredentials = (): boolean => {
    if (!selectedOption) return false;
    const newErrors: Record<string, string> = {};
    for (const field of selectedOption.credentialFields) {
      const value = credentials[field.name as keyof ProviderCredentials];
      if (field.required && (!value || value.trim() === "")) {
        newErrors[field.name] = `${field.label} is required`;
      }
      if (field.name === "server_url" && value && !value.startsWith("http")) {
        newErrors[field.name] = "Please enter a valid URL starting with http:// or https://";
      }
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleStart = () => {
    if (!selectedProvider || !validateCredentials()) return;
    onSelect(selectedProvider, credentials);
  };

  return (
    <div className="w-full flex flex-col gap-3">
      {/* Alice Provider Options - Left aligned */}
      <div className="self-start w-[40%] min-w-0">
        <div className="text-[11px] font-semibold text-[#3b82f6] mb-1">
          Alice
          <MessageTime timestamp={messageTimestamp} fallbackToNow />
        </div>
        <div className="p-4 bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-sm text-[#0f172a] leading-relaxed">
          Which AI provider would you like to use? Each has different quality and security trade-offs:
          <div className="mt-1.5 mb-2 text-[11px] text-[#64748b]">
            Benchmark: OnlineMind2Web (March 2026) ·{" "}
            <a
              href="https://browser-use.com/benchmarks"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#2563eb] underline hover:text-[#1d4ed8]"
            >
              View Benchmarks
            </a>
          </div>
          {/* Provider Options */}
          <div className="flex flex-col gap-1.5 mb-1">
            {options?.map((provider) => {
              const isAdminEnabled =
                !enabledProviders?.length || enabledProviders.includes(provider.id);
              const isClickable = !disabled && isAdminEnabled;
              const disabledByAdmin = !isAdminEnabled;

              return (
                <div
                  key={provider.id}
                  data-testid={`provider-card-${provider.id}`}
                  onClick={() => isClickable && handleProviderClick(provider.id)}
                  title={
                    disabledByAdmin
                      ? "Your project cannot choose this provider. Please contact your administrator if something is wrong."
                      : undefined
                  }
                  className={`border rounded-lg px-3.5 py-2.5 transition-all flex justify-between items-center gap-2 ${
                    disabledByAdmin
                      ? "border-slate-200 bg-slate-100 opacity-40 cursor-not-allowed"
                      : selectedProvider === provider.id
                        ? "border-[#3b82f6] bg-[#eff6ff] cursor-pointer"
                        : "border-[#e2e8f0] hover:border-[#3b82f6] hover:bg-[#eff6ff] cursor-pointer"
                  } ${disabled && !disabledByAdmin ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[#64748b] flex-shrink-0">
                      {PROVIDER_LOGOS[provider.id] ?? null}
                    </span>
                    <div className="flex flex-col gap-0.5 min-w-0">
                      <span className="font-semibold text-[13px]">{provider.name}</span>
                      <span className="text-[11px] text-[#64748b] truncate">{provider.description}</span>
                    </div>
                  </div>
                  <div className="flex flex-col gap-0.5 items-end flex-shrink-0">
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-semibold whitespace-nowrap ${QUALITY_TAG_STYLES[provider.qualityRank]}`}>
                      {QUALITY_TAGS[provider.qualityRank]}
                    </span>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-semibold whitespace-nowrap ${SECURITY_TAG_STYLES[provider.securityLevel]}`}>
                      {SECURITY_TAGS[provider.securityLevel]}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Credential Form - Right aligned (User message style) */}
      {selectedOption && (
        <div className="self-end w-[40%] min-w-0">
          <div className="text-[11px] font-semibold text-[#64748b] mb-1 text-right">
            You
            <MessageTime timestamp={selectionTimestamp} fallbackToNow />
          </div>
          <div className={`p-4 rounded-2xl rounded-br-sm text-sm leading-relaxed ${isReadOnly ? "bg-[#1e40af] text-white" : "bg-[#3b82f6] text-white"}`}>
            {isReadOnly ? (
              <div className="space-y-3">
                <div className="space-y-2">
                  <div className="font-medium">{submittedSelection?.providerName}</div>
                  {selectedOption?.credentialFields?.map((field) => (
                    <div key={field.name} className="text-xs text-white/80">
                      <span className="text-white/60">{field.label}:</span>{" "}
                      {field.type === "password" ? "••••••••" : displayCredentials[field.name]}
                    </div>
                  ))}
                </div>
              </div>
            ) : selectedOption.authMethod === "sso" ? (
              <div className="space-y-3">
                <p className="text-sm text-white/90">
                  Sign in with your company account. A new browser tab will open for SSO login.
                </p>
                <button
                  onClick={handleSsoLogin}
                  disabled={disabled || ssoStatus === "waiting"}
                  data-testid="sso-login-button"
                  className="px-5 py-2.5 rounded-full bg-[#1e40af] text-white text-sm font-medium hover:bg-[#1e3a8a] disabled:opacity-50 disabled:cursor-not-allowed transition-all whitespace-nowrap"
                >
                  {ssoStatus === "waiting" ? "Waiting for SSO login…" : "Login SSO"}
                </button>
                {ssoError && <p className="text-xs text-red-200">{ssoError}</p>}
              </div>
            ) : (
              <div className="flex items-start gap-2">
                <div className="flex-1 space-y-3">
                  {selectedOption.credentialFields?.map((field) => {
                    return (
                      <div key={field.name}>
                        <input
                          type={field.type}
                          data-testid={`credential-input-${field.name}`}
                          placeholder={
                            field.name === "api_key"
                              ? apiKeyPlaceholder
                              : field.placeholder || `Enter ${field.label}`
                          }
                          value={credentials[field.name] || ""}
                          onChange={(e) =>
                            handleCredentialChange(field.name, e.target.value)
                          }
                          disabled={disabled}
                          className={`w-full px-4 py-2.5 rounded-full border text-sm text-[#0f172a] placeholder:text-[#94a3b8] outline-none transition-all ${
                            errors[field.name]
                              ? "border-red-400 focus:border-red-500"
                              : "border-[#e2e8f0] focus:border-[#3b82f6] focus:ring-2 focus:ring-[#3b82f6]/10"
                          }`}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleStart();
                          }}
                        />
                        {errors[field.name] && (
                          <p className="text-xs text-red-200 mt-1">
                            {errors[field.name]}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
                <button
                  onClick={handleStart}
                  disabled={disabled}
                  className="px-5 py-2.5 rounded-full bg-[#1e40af] text-white text-sm font-medium hover:bg-[#1e3a8a] disabled:opacity-50 disabled:cursor-not-allowed transition-all whitespace-nowrap"
                >
                  Start
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
