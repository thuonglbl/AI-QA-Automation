import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import { Loader2 } from "lucide-react";
import { apiFetch } from "@/lib/api";

import { normalizeUser } from "@/lib/auth";

interface LoginPageProps {
  onLoginSuccess?: () => void;
}

export function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const { isAuthenticated, isLoading, error: authError, logout, setAuthStatus } = useAuth();
  
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Redirect when authenticated
  useEffect(() => {
    if (isAuthenticated && onLoginSuccess) {
      onLoginSuccess();
    }
  }, [isAuthenticated, onLoginSuccess]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setFormError(null);

    try {
      await logout();
      // Backend returns { access_token, user: UserProfileResponse }
      // UserProfileResponse has display_name (not name), id, email, role, is_active
      const loginResult = await apiFetch<{
        user?: { email?: string; display_name?: string; name?: string; id?: string; role?: string; is_active?: boolean };
        access_token?: string;
      }>("/login", {
        method: "POST",
        authRoute: true,
        safeMessage: "Invalid username or password.",
        body: JSON.stringify({ email, password }),
      });

      if (loginResult.access_token) {
        try {
          localStorage.setItem("aiqa_access_token", loginResult.access_token);
        } catch {}
      } else {
        try {
          localStorage.removeItem("aiqa_access_token");
        } catch {}
      }

      const rawUser = loginResult.user;
      if (!rawUser?.email) {
        throw new Error("Login response did not include a user profile.");
      }

      // Normalise: backend may return display_name instead of name
      const userForNormalize = {
        ...rawUser,
        email: rawUser.email as string,
        name: rawUser.name ?? rawUser.display_name ?? rawUser.email,
      };
      setAuthStatus({ authenticated: true, user: normalizeUser(userForNormalize) });
    } catch {
      setAuthStatus({ authenticated: false, user: null });
      setFormError("Invalid username or password.");
    } finally {
      setIsSubmitting(false);
    }
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
              Sign in to access the AI-powered QA automation platform
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-8 space-y-4">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <p className="text-sm text-surface-500">Checking authentication...</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-surface-700" htmlFor="email">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2 border rounded-md border-surface-300 focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-surface-700" htmlFor="password">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 border rounded-md border-surface-300 focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>

              {(authError || formError) && (
                <div className="p-3 rounded-lg bg-error-light text-error text-sm text-center">
                  {formError || authError}
                </div>
              )}

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full py-2 px-4 bg-primary text-white rounded-md hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 flex items-center justify-center"
              >
                {isSubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                Sign In
              </button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
