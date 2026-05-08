import { useAuthContext } from "@/contexts/AuthContext";
import type { AuthStatus, AuthUser } from "@/lib/auth";

interface UseAuthReturn {
  isAuthenticated: boolean;
  user: AuthUser | null;
  isLoading: boolean;
  error: string | null;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setAuthStatus: (status: AuthStatus) => void;
}

export function useAuth(): UseAuthReturn {
  const context = useAuthContext();

  // Maintain backward compatibility with setAuthStatus (no-op since state is managed by context)
  const setAuthStatus = () => {
    // Context manages state internally, this is for API compatibility
  };

  return {
    ...context,
    setAuthStatus,
  };
}
