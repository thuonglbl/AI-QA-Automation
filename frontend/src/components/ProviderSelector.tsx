import { useState } from "react";
import type {
  ProviderOption,
  ProviderCredentials,
} from "@/types/provider";

interface SubmittedSelection {
  providerId: string;
  providerName: string;
  credentials: Record<string, string>;
}

interface ProviderSelectorProps {
  options: ProviderOption[] | null;
  onPremDefaults?: {
    server_url: string;
    api_key: string;
  };
  onSelect: (providerId: string, credentials: Record<string, string>) => void;
  disabled?: boolean;
  submittedSelection?: SubmittedSelection | null;
}

const RANK_ICONS: Record<number, string> = {
  1: "☁️",
  2: "🔷",
  3: "🌐",
  4: "🔒",
};

const TAG_STYLES: Record<number, string> = {
  1: "bg-[#f0fdf4] text-[#16a34a]",
  2: "bg-[#fffbeb] text-[#d97706]",
  3: "bg-[#f1f5f9] text-[#64748b]",
  4: "bg-[#eff6ff] text-[#2563eb]",
};

const TAG_LABELS: Record<number, string> = {
  1: "Best quality",
  2: "Recommended",
  3: "Good",
  4: "Most secure",
};

export function ProviderSelector({
  options,
  onPremDefaults,
  onSelect,
  disabled = false,
  submittedSelection,
}: ProviderSelectorProps) {
  const [selectedProvider, setSelectedProvider] = useState<string | null>(submittedSelection?.providerId || null);
  const [credentials, setCredentials] = useState<Record<string, string>>(submittedSelection?.credentials || {});
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Use submitted selection if available (read-only mode)
  const isReadOnly = !!submittedSelection;
  const displayProvider = submittedSelection?.providerId || selectedProvider;
  const displayCredentials = submittedSelection?.credentials || credentials;
  const selectedOption = options?.find((p) => p.id === displayProvider);

  const handleProviderClick = (providerId: string) => {
    setSelectedProvider(providerId);
    setCredentials({});
    setErrors({});

    // Pre-fill On-Premises defaults if available
    if (providerId === "on-premises" && onPremDefaults) {
      setCredentials({
        server_url: onPremDefaults.server_url,
        api_key: onPremDefaults.api_key,
      });
    }
  };

  const handleCredentialChange = (name: string, value: string) => {
    setCredentials((prev: Record<string, string>) => ({ ...prev, [name]: value }));
    // Clear error when user types
    if (errors[name]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const validateCredentials = (): boolean => {
    if (!selectedOption) return false;

    const newErrors: Record<string, string> = {};

    for (const field of selectedOption.credentialFields) {
      const value = credentials[field.name as keyof ProviderCredentials];
      if (field.required && (!value || value.trim() === "")) {
        newErrors[field.name] = `${field.label} is required`;
      }

      // URL validation for server_url
      if (
        field.name === "server_url" &&
        value &&
        !value.startsWith("http")
      ) {
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
        <div className="text-[11px] font-semibold text-[#3b82f6] mb-1">Alice</div>
        <div className="p-4 bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-sm text-[#0f172a] leading-relaxed">
        Which AI provider would you like to use? Each has different quality and security trade-offs:

        {/* Provider Options */}
        <div className="flex flex-col gap-1.5 mt-2.5 mb-1">
          {options?.map((provider) => (
            <div
              key={provider.id}
              onClick={() => !disabled && handleProviderClick(provider.id)}
              className={`border rounded-lg px-3.5 py-2.5 cursor-pointer transition-all flex justify-between items-center ${
                selectedProvider === provider.id
                  ? "border-[#3b82f6] bg-[#eff6ff]"
                  : "border-[#e2e8f0] hover:border-[#3b82f6] hover:bg-[#eff6ff]"
              } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
            >
              <div className="flex flex-col gap-0.5">
                <span className="font-semibold text-[13px]">
                  {RANK_ICONS[provider.qualityRank]} {provider.name}
                </span>
                <span className="text-[11px] text-[#64748b]">
                  {provider.description}
                </span>
              </div>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${TAG_STYLES[provider.qualityRank]}`}>
                {TAG_LABELS[provider.qualityRank]}
              </span>
            </div>
          ))}
        </div>
        </div>
      </div>

      {/* Credential Form - Right aligned (User message style) */}
      {selectedOption && (
        <div className="self-end w-[40%] min-w-0">
          <div className="text-[11px] font-semibold text-[#64748b] mb-1 text-right">You</div>
          <div className={`p-4 rounded-2xl rounded-br-sm text-sm leading-relaxed ${isReadOnly ? 'bg-[#1e40af] text-white' : 'bg-[#3b82f6] text-white'}`}>
            <div className="space-y-3">
              {isReadOnly ? (
                // Read-only display of submitted selection
                <div className="space-y-2">
                  <div className="font-medium">{submittedSelection?.providerName}</div>
                  {selectedOption?.credentialFields?.map((field) => (
                    <div key={field.name} className="text-xs text-white/80">
                      <span className="text-white/60">{field.label}:</span>{" "}
                      {field.type === "password" ? "••••••••" : displayCredentials[field.name]}
                    </div>
                  ))}
                </div>
              ) : (
                // Editable form
                <>
                  {selectedOption.credentialFields?.map((field) => (
                    <div key={field.name}>
                      <input
                        type={field.type}
                        placeholder={field.placeholder || `Enter ${field.label}`}
                        value={credentials[field.name] || ""}
                        onChange={(e) => handleCredentialChange(field.name, e.target.value)}
                        disabled={disabled}
                        className={`w-full px-4 py-2.5 rounded-full border text-sm text-[#0f172a] placeholder:text-[#94a3b8] outline-none transition-all ${
                          errors[field.name]
                            ? "border-red-400 focus:border-red-500"
                            : "border-[#e2e8f0] focus:border-[#3b82f6] focus:ring-2 focus:ring-[#3b82f6]/10"
                        }`}
                      />
                      {errors[field.name] && (
                        <p className="text-xs text-red-200 mt-1">{errors[field.name]}</p>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
          {!isReadOnly && (
            <div className="flex justify-end mt-2">
              <button
                onClick={handleStart}
                disabled={disabled}
                className="px-5 py-2.5 rounded-full bg-[#2563eb] text-white text-sm font-medium hover:bg-[#1d4ed8] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                Start
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
