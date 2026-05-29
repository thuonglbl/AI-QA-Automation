import { createContext, useContext, useCallback, useEffect, useState, type ReactNode } from "react";
import type { AuthStatus, AuthUser } from "@/lib/auth";
import { checkAuthStatus, logout as logoutApi } from "@/lib/auth";

interface AuthContextType {
  isAuthenticated: boolean;
  user: AuthUser | null;
  isLoading: boolean;
  error: string | null;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setAuthStatus: (status: AuthStatus) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authStatus, setAuthStatus] = useState<AuthStatus>({
    authenticated: false,
    user: null,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const status = await checkAuthStatus();
      setAuthStatus(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to check auth status");
      setAuthStatus({ authenticated: false, user: null });
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleLogout = useCallback(async () => {
    await logoutApi();
    setAuthStatus({ authenticated: false, user: null });
  }, []);

  // Check auth status on mount and listen for global auth errors
  useEffect(() => {
    refresh();

    let timeoutId: number | undefined;
    const handleAuthError = () => {
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      timeoutId = window.setTimeout(() => {
        refresh();
      }, 300);
    };
    
    window.addEventListener("auth-error", handleAuthError);
    return () => {
      window.removeEventListener("auth-error", handleAuthError);
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [refresh]);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: authStatus.authenticated,
        user: authStatus.user,
        isLoading,
        error,
        logout: handleLogout,
        refresh,
        setAuthStatus,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthContext(): AuthContextType {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuthContext must be used within an AuthProvider");
  }
  return context;
}
