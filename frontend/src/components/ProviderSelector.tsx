import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Shield,
  Cloud,
  Building2,
  Lock,
  Check,
  Server,
} from "lucide-react";
import type {
  ProviderOption,
  ProviderCredentials,
  SecurityLevel,
} from "@/types/provider";
import {
  SECURITY_LEVEL_COLORS,
  SECURITY_LEVEL_LABELS,
  QUALITY_RANK_LABELS,
} from "@/types/provider";

interface ProviderSelectorProps {
  options: ProviderOption[] | null;
  onPremDefaults?: {
    server_url: string;
    api_key: string;
  };
  onSelect: (providerId: string, credentials: Record<string, string>) => void;
  disabled?: boolean;
}

const SECURITY_ICONS: Record<SecurityLevel, React.ReactNode> = {
  cloud: <Cloud className="h-4 w-4" />,
  enterprise: <Building2 className="h-4 w-4" />,
  highest: <Lock className="h-4 w-4" />,
};

const RANK_ICONS: Record<number, string> = {
  1: "🥇",
  2: "🥈",
  3: "🥉",
  4: "🏠",
};

export function ProviderSelector({
  options,
  onPremDefaults,
  onSelect,
  disabled = false,
}: ProviderSelectorProps) {
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const selectedOption = options?.find((p) => p.id === selectedProvider);

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
    <div className="space-y-4">
      <p className="text-sm text-surface-600 mb-3">
        Select an AI provider below. Higher quality ranks offer better results,
        while higher security levels keep your data more private.
      </p>

      {/* Provider Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {options?.map((provider) => (
          <Card
            key={provider.id}
            className={`cursor-pointer transition-all hover:shadow-md ${
              selectedProvider === provider.id
                ? "ring-2 ring-primary border-primary"
                : "border-surface-200"
            } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
            onClick={() => !disabled && handleProviderClick(provider.id)}
          >
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg" aria-hidden="true">
                    {RANK_ICONS[provider.qualityRank]}
                  </span>
                  <div>
                    <h4 className="font-semibold text-surface-900">
                      {provider.name}
                    </h4>
                    <p className="text-xs text-surface-500">
                      {QUALITY_RANK_LABELS[provider.qualityRank]}
                    </p>
                  </div>
                </div>
                {selectedProvider === provider.id && (
                  <Check className="h-5 w-5 text-primary" />
                )}
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <Badge
                variant="secondary"
                className={`text-xs ${SECURITY_LEVEL_COLORS[provider.securityLevel]}`}
              >
                <span className="mr-1">{SECURITY_ICONS[provider.securityLevel]}</span>
                {SECURITY_LEVEL_LABELS[provider.securityLevel]}
              </Badge>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Credential Form */}
      {selectedOption && (
        <Card className="mt-4 border-surface-200">
          <CardHeader className="pb-3">
            <h4 className="font-medium text-surface-900">
              Configure {selectedOption.name}
            </h4>
            <p className="text-sm text-surface-500">
              Enter your credentials to connect to {selectedOption.name}
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {selectedOption.credentialFields.map((field) => (
              <div key={field.name} className="space-y-2">
                <Label
                  htmlFor={field.name}
                  className="text-sm font-medium text-surface-700"
                >
                  {field.label}
                  {field.required && (
                    <span className="text-error ml-1">*</span>
                  )}
                </Label>
                <Input
                  id={field.name}
                  type={field.type}
                  placeholder={field.placeholder || `Enter ${field.label}`}
                  value={credentials[field.name] || ""}
                  onChange={(e) =>
                    handleCredentialChange(field.name, e.target.value)
                  }
                  disabled={disabled}
                  className={errors[field.name] ? "border-error" : ""}
                />
                {errors[field.name] && (
                  <p className="text-xs text-error">{errors[field.name]}</p>
                )}
              </div>
            ))}

            <Button
              onClick={handleStart}
              disabled={disabled}
              className="w-full"
            >
              <Server className="h-4 w-4 mr-2" />
              Test Connection & Continue
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Security Notice */}
      <div className="flex items-start gap-2 p-3 bg-surface-50 rounded-lg text-xs text-surface-600">
        <Shield className="h-4 w-4 mt-0.5 flex-shrink-0 text-surface-500" />
        <p>
          Your credentials are stored securely and only used to communicate with
          the AI provider. API keys are never logged or shared.
        </p>
      </div>
    </div>
  );
}
