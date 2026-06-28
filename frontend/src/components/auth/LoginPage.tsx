import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import { Loader2 } from "lucide-react";
import { MicrosoftLoginButton } from "@/components/auth/MicrosoftLoginButton";

interface LoginPageProps {
  onLoginSuccess?: () => void;
}

// SSO callback failures redirect back to "/?sso_error=<code>" — map the safe codes
// to friendly English messages (App-UI-English-only). Never echo tokens/secrets.
const SSO_ERROR_MESSAGES: Record<string, string> = {
  not_provisioned:
    "Your account is not provisioned for this platform yet. Contact an administrator.",
  domain_not_allowed: "Your email domain is not allowed to sign in.",
  invalid_token: "SSO sign-in failed to validate your identity. Please try again.",
  state_mismatch: "Your sign-in session expired. Please try again.",
  idp_unreachable: "SSO sign-in could not reach the identity provider. Please try again.",
  idp_error: "SSO sign-in was cancelled or failed. Please try again.",
  not_found: "SSO sign-in is not available in this environment.",
};

function readSsoError(): string | null {
  try {
    const code = new URLSearchParams(window.location.search).get("sso_error");
    if (!code) return null;
    return SSO_ERROR_MESSAGES[code] ?? "SSO sign-in failed. Please try again.";
  } catch {
    return null;
  }
}

export function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const { isAuthenticated, isLoading, error: authError } = useAuth();
  const [ssoError] = useState<string | null>(readSsoError);

  // Redirect when authenticated
  useEffect(() => {
    if (isAuthenticated && onLoginSuccess) {
      onLoginSuccess();
    }
  }, [isAuthenticated, onLoginSuccess]);

  const handleSsoLogin = () => {
    // Full-page navigation to the backend SSO entry point. The browser is then
    // redirected to the corporate IdP (or the built-in mock IdP in dev/CI/E2E),
    // and lands back authenticated with the app session cookie set.
    window.location.assign("/auth/sso/login");
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-50 p-4">
      <Card className="w-full max-w-md shadow-lg">
        <CardHeader className="text-center space-y-4">
          <div className="mx-auto w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="w-8 h-8 text-primary"
            >
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>
          <div>
            <CardTitle className="text-2xl font-bold text-surface-900">
              AI QA Automation
            </CardTitle>
            <CardDescription className="text-surface-500 mt-2">
              Sign in with your corporate account to access the platform
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-8 space-y-4">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <p className="text-sm text-surface-500">
                Checking authentication...
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <MicrosoftLoginButton onClick={handleSsoLogin} />

              {(ssoError || authError) && (
                <div
                  role="alert"
                  className="p-3 rounded-lg bg-error-light text-error text-sm text-center"
                >
                  {ssoError || authError}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
