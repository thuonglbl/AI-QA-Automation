import { useState, useCallback } from "react";
import { X, KeyRound, Loader2, CheckCircle2, AlertCircle, Save } from "lucide-react";
import {
  upsertTestCredential,
  testLogin,
  listTestCredentials,
} from "@/lib/testCredentials";

export interface SarahInputsRequest {
  needsUrl: boolean;
  /** Project-wide target environments (name + URL + login_type) the admin configured. When
   *  present, Sarah asks the user to PICK one instead of typing a URL. */
  environments: { name: string; url: string; login_type?: string }[];
  /** The distinct roles required by the test cases being generated.
   *  When present, Sarah only asks for sessions for these specific roles. */
  roles?: string[];
}

/** A captured (environment, role) session slot the current user already owns. */
export interface SarahSessionSlot {
  environment: string;
  role: string;
  /** ISO expiry; a session past this is treated as not captured (auto-login ignores it). */
  expires_at?: string | null;
}

interface SarahInputsFormProps {
  request: SarahInputsRequest;
  /** App roles configured for the project. Sarah shows the capture status of each so the
   *  tester can import a session before the live exploration runs. */
  appRoles: string[];
  /** The current user's captured sessions (non-secret slots) for this project. */
  sessions: SarahSessionSlot[];
  /** Re-start Sarah's step with the chosen target environment.
   *
   *  Both fields come from the SAME selected environment object so they stay consistent.
   *  The environment NAME is the authoritative key the backend uses to resolve the captured
   *  session (sessions are keyed by env name); the URL drives the live explore navigation.
   *  When the project has no environments the user types a free-text URL and `environment`
   *  is an empty string. */
  onSubmit: (payload: { environment: string; targetUrl: string }) => void;
  disabled?: boolean;
  /** Project ID needed to save credentials and trigger test login. */
  projectId?: string;
}

type LoginStatus = "idle" | "saving" | "saved" | "testing" | "connected" | "failed";

interface CredentialPopupState {
  role: string;
  username: string;
  password: string;
  totp: string;
  status: LoginStatus;
  error: string | null;
}

/**
 * Collects the inputs Sarah needs to drive the real app with browser-use: the target
 * environment (picked from the project's configured environments, or a free-text URL when
 * none are configured). The backend explore now rehydrates the captured session server-side,
 * so no Chrome path / CDP URL is asked here. For the selected environment, the form shows the
 * capture status of each project role. "Generate scripts" still works even without a
 * captured session — the run falls back to vision / LLM-only.
 */
export function SarahInputsForm({
  request,
  appRoles,
  sessions,
  onSubmit,
  disabled = false,
  projectId,
}: SarahInputsFormProps) {
  const [targetUrl, setTargetUrl] = useState("");
  const [selectedEnvName, setSelectedEnvName] = useState("");

  // Credential popup state
  const [popup, setPopup] = useState<CredentialPopupState | null>(null);

  // Track which roles have been successfully connected in this session
  const [connectedRoles, setConnectedRoles] = useState<Record<string, boolean>>({});

  // Track which roles have saved credentials (even if test failed)
  const [savedRoles, setSavedRoles] = useState<Record<string, boolean>>({});

  // Use dynamically filtered roles if provided by the backend; fallback to project appRoles
  const effectiveRoles = request.roles && request.roles.length > 0 ? request.roles : appRoles;

  // When the project defines environments, the user PICKS one (its URL is the target);
  // otherwise we fall back to a free-text URL so Sarah is never a dead end.
  const hasEnvironments = request.environments.length > 0;
  const selectedEnv = request.environments.find((e) => e.name === selectedEnvName);
  const effectiveUrl = hasEnvironments ? (selectedEnv?.url ?? "") : targetUrl.trim();

  const urlOk = !request.needsUrl || effectiveUrl.startsWith("http");
  const canSubmit = !disabled && urlOk;

  const submit = () => {
    if (!canSubmit) return;
    // Send BOTH the env NAME and its URL from the SAME selected env object so they are
    // consistent. With no configured environments the name is empty (free-text URL path).
    onSubmit({
      environment: hasEnvironments ? (selectedEnv?.name ?? "") : "",
      targetUrl: effectiveUrl,
    });
  };

  const isCaptured = (role: string) =>
    !!selectedEnvName &&
    sessions.some(
      (s) =>
        s.environment === selectedEnvName &&
        s.role === role &&
        // A session past its TTL can't be used (auto-login ignores expired sessions),
        // so it must not read as "Captured".
        (!s.expires_at || new Date(s.expires_at).getTime() > Date.now()),
    );

  const isConnected = (role: string) =>
    connectedRoles[`${selectedEnvName}:${role}`] === true;

  const isSaved = (role: string) =>
    savedRoles[`${selectedEnvName}:${role}`] === true;

  const openCredentialPopup = useCallback(
    async (role: string) => {
      if (!projectId || !selectedEnvName) return;

      // Pre-fill username from existing credential if available
      let existingUsername = "";
      try {
        const creds = await listTestCredentials(projectId);
        const match = creds.find(
          (c) => c.environment === selectedEnvName && c.role === role,
        );
        if (match) {
          existingUsername = match.username;
        }
      } catch {
        // Non-fatal: just open with empty fields
      }

      setPopup({
        role,
        username: existingUsername,
        password: "",
        totp: "",
        status: "idle",
        error: null,
      });
    },
    [projectId, selectedEnvName],
  );

  const closePopup = () => setPopup(null);

  /** Save credentials only (no test login). Used for all login types. */
  const handleSaveOnly = async () => {
    if (!popup || !projectId || !selectedEnvName) return;
    if (!popup.username.trim() || !popup.password.trim()) return;

    setPopup((p) => p && { ...p, status: "saving", error: null });
    try {
      await upsertTestCredential(projectId, {
        environment: selectedEnvName,
        role: popup.role,
        username: popup.username.trim(),
        password: popup.password.trim(),
        totp_secret: popup.totp.trim() || null,
      });
      setSavedRoles((prev) => ({
        ...prev,
        [`${selectedEnvName}:${popup.role}`]: true,
      }));
      setPopup((p) => p && { ...p, status: "saved", error: null });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save credentials";
      setPopup((p) => p && { ...p, status: "failed", error: msg });
    }
  };

  /** Save credentials, then test login via browser automation. For Standard Form only. */
  const handleSaveAndTest = async () => {
    if (!popup || !projectId || !selectedEnvName) return;
    if (!popup.username.trim() || !popup.password.trim()) return;

    // Step 1: Save credentials
    setPopup((p) => p && { ...p, status: "saving", error: null });
    try {
      await upsertTestCredential(projectId, {
        environment: selectedEnvName,
        role: popup.role,
        username: popup.username.trim(),
        password: popup.password.trim(),
        totp_secret: popup.totp.trim() || null,
      });
      setSavedRoles((prev) => ({
        ...prev,
        [`${selectedEnvName}:${popup.role}`]: true,
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save credentials";
      setPopup((p) => p && { ...p, status: "failed", error: msg });
      return;
    }

    // Step 2: Test login
    setPopup((p) => p && { ...p, status: "testing" });
    try {
      const result = await testLogin(projectId, selectedEnvName, popup.role);
      if (result.success) {
        setPopup((p) => p && { ...p, status: "connected", error: null });
        setConnectedRoles((prev) => ({
          ...prev,
          [`${selectedEnvName}:${popup.role}`]: true,
        }));
      } else {
        // Credentials are saved even though login test failed
        setPopup((p) =>
          p && {
            ...p,
            status: "failed",
            error: result.error || "Login test failed. Please try again.",
          },
        );
      }
    } catch (err) {
      // Credentials are saved even though login test failed
      const msg = err instanceof Error ? err.message : "Login test failed";
      setPopup((p) => p && { ...p, status: "failed", error: msg });
    }
  };

  const inputClass =
    "w-full px-3 py-2 rounded-lg border border-[#e2e8f0] text-sm outline-none " +
    "focus:border-[#8B5CF6] focus:ring-2 focus:ring-[#8B5CF6]/10";

  const isPopupBusy = popup?.status === "saving" || popup?.status === "testing";

  return (
    <div
      data-testid="sarah-inputs-form"
      className="bg-white border border-[#e2e8f0] rounded-2xl rounded-bl-sm text-[#0f172a] shadow-sm p-5 flex flex-col gap-4"
    >
      <p className="text-sm text-[#334155]">
        Sarah will drive Chrome through your approved test cases against the real
        application to capture real selectors, then generate Playwright scripts.
      </p>

      {request.needsUrl &&
        (hasEnvironments ? (
          <div className="flex flex-col gap-1">
            <label htmlFor="sarah-environment" className="text-xs font-medium text-[#475569]">
              Target environment
            </label>
            <select
              id="sarah-environment"
              data-testid="sarah-environment"
              value={selectedEnvName}
              onChange={(e) => {
                setSelectedEnvName(e.target.value);
              }}
              disabled={disabled}
              className={inputClass}
            >
              <option value="">Select environment…</option>
              {request.environments.map((env) => (
                <option key={env.name} value={env.name}>
                  {env.name} — {env.url}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            <label htmlFor="sarah-target-url" className="text-xs font-medium text-[#475569]">
              Application URL
            </label>
            <input
              id="sarah-target-url"
              type="url"
              data-testid="sarah-target-url"
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              placeholder="https://your-app.example/page"
              disabled={disabled}
              className={inputClass}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
            />
          </div>
        ))}

      {/* Per-role session capture status for the selected environment. The captured
          session is rehydrated server-side during the live exploration. */}
      {hasEnvironments && selectedEnvName && effectiveRoles.length > 0 && (
        <div className="flex flex-col gap-2" data-testid="sarah-session-status">
          <span className="text-xs font-medium text-[#475569]">Login sessions for {selectedEnvName}</span>
          <ul className="flex flex-col gap-1.5">
            {effectiveRoles.map((role) => (
              <li key={role} className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-[#334155]">{role}</span>
                  {isCaptured(role) || isConnected(role) ? (
                    <span className="text-xs font-medium text-green-700 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      {isConnected(role) ? "Connected" : "Captured"}
                    </span>
                  ) : isSaved(role) ? (
                    <span className="text-xs font-medium text-amber-600 flex items-center gap-1">
                      <KeyRound className="w-3.5 h-3.5" />
                      Saved
                    </span>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400">Not logged in</span>
                      {projectId && (
                        <button
                          type="button"
                          onClick={() => openCredentialPopup(role)}
                          className="text-xs text-indigo-600 hover:text-indigo-800 hover:underline font-medium"
                          data-testid={`sarah-set-credentials-${role}`}
                        >
                          Set Credentials
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        onClick={submit}
        disabled={!canSubmit}
        data-testid="sarah-inputs-submit"
        className="self-start bg-[#8B5CF6] text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-[#7c3aed] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        Generate scripts
      </button>

      {/* Standard Form credential popup modal */}
      {popup && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={(e) => {
            if (e.target === e.currentTarget && !isPopupBusy) closePopup();
          }}
        >
          <div
            className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-900">Test Credentials</h3>
              <button
                type="button"
                onClick={closePopup}
                disabled={isPopupBusy}
                className="text-slate-400 hover:text-slate-600 disabled:opacity-50"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-sm text-slate-600 mb-5">
              Set credentials for{" "}
              <span className="font-semibold">{popup.role}</span> in{" "}
              <span className="font-semibold">{selectedEnvName}</span>.
            </p>

            {/* Status banner */}
            {popup.status === "connected" && (
              <div className="flex items-center gap-2 px-3 py-2.5 mb-4 rounded-lg bg-green-50 border border-green-200">
                <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
                <span className="text-sm font-medium text-green-800">
                  Connected — login successful!
                </span>
              </div>
            )}

            {popup.status === "saved" && (
              <div className="flex items-center gap-2 px-3 py-2.5 mb-4 rounded-lg bg-blue-50 border border-blue-200">
                <Save className="w-5 h-5 text-blue-600 flex-shrink-0" />
                <span className="text-sm font-medium text-blue-800">
                  Credentials saved successfully.
                </span>
              </div>
            )}

            {popup.status === "failed" && popup.error && (
              <div className="flex items-start gap-2 px-3 py-2.5 mb-4 rounded-lg bg-amber-50 border border-amber-200">
                <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div className="flex flex-col gap-1">
                  <span className="text-sm font-medium text-amber-800">
                    Credentials saved, but login test failed
                  </span>
                  <span className="text-xs text-amber-700">{popup.error}</span>
                  <span className="text-xs text-slate-500 mt-1">
                    Your credentials are still saved. You can update them or proceed with Generate scripts.
                  </span>
                </div>
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label
                  htmlFor="sarah-cred-username"
                  className="text-sm font-medium text-slate-700 block mb-1.5"
                >
                  Username
                </label>
                <input
                  id="sarah-cred-username"
                  data-testid="sarah-cred-username"
                  value={popup.username}
                  onChange={(e) =>
                    setPopup((p) => p && { ...p, username: e.target.value, status: p.status === "failed" || p.status === "saved" ? "idle" : p.status })
                  }
                  placeholder="test.user@company.com"
                  disabled={isPopupBusy || popup.status === "connected"}
                  className={inputClass}
                />
              </div>
              <div>
                <label
                  htmlFor="sarah-cred-password"
                  className="text-sm font-medium text-slate-700 block mb-1.5"
                >
                  Password
                </label>
                <input
                  id="sarah-cred-password"
                  data-testid="sarah-cred-password"
                  type="password"
                  value={popup.password}
                  onChange={(e) =>
                    setPopup((p) => p && { ...p, password: e.target.value, status: p.status === "failed" || p.status === "saved" ? "idle" : p.status })
                  }
                  placeholder="••••••••"
                  disabled={isPopupBusy || popup.status === "connected"}
                  className={inputClass}
                />
                <p className="text-xs text-slate-500 mt-1.5">
                  Passwords are encrypted at rest and never returned to the UI.
                </p>
              </div>
              <div>
                <label
                  htmlFor="sarah-cred-totp"
                  className="text-sm font-medium text-slate-700 block mb-1.5"
                >
                  TOTP Secret (Optional)
                </label>
                <input
                  id="sarah-cred-totp"
                  data-testid="sarah-cred-totp"
                  type="password"
                  value={popup.totp}
                  onChange={(e) =>
                    setPopup((p) => p && { ...p, totp: e.target.value })
                  }
                  placeholder="JBSWY3DPEHPK3PXP"
                  disabled={isPopupBusy || popup.status === "connected"}
                  className={inputClass}
                />
                <p className="text-xs text-slate-500 mt-1.5">
                  Base32 secret for generating 2FA tokens.
                </p>
                <div className="mt-3 flex items-start gap-2 bg-amber-50 text-amber-800 p-2.5 rounded-md border border-amber-200">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <p className="text-xs leading-relaxed">
                    <strong>Note for Scheduled Tests:</strong> If you leave this blank, the bot will prompt you for an Authenticator code when it hits the MFA screen (Interactive MFA). However, overnight or scheduled runs will timeout since you aren't there to enter the code. To fully automate scheduled tests, please configure the TOTP Secret here.
                  </p>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex justify-end gap-3 mt-6 pt-4 border-t">
                {popup.status === "connected" || popup.status === "saved" ? (
                  <button
                    type="button"
                    onClick={closePopup}
                    className="px-4 py-2 rounded-md text-sm font-medium bg-[#8B5CF6] text-white hover:bg-[#7c3aed] transition-colors"
                  >
                    Done
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={closePopup}
                      disabled={isPopupBusy}
                      className="px-4 py-2 rounded-md text-sm font-medium border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveOnly}
                      disabled={
                        isPopupBusy ||
                        !popup.username.trim() ||
                        !popup.password.trim()
                      }
                      className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      data-testid="sarah-save-credentials"
                    >
                      {popup.status === "saving" ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Saving…
                        </>
                      ) : (
                        <>
                          <Save className="w-4 h-4" />
                          Save
                        </>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveAndTest}
                      disabled={
                        isPopupBusy ||
                        !popup.username.trim() ||
                        !popup.password.trim()
                      }
                      className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium bg-[#8B5CF6] text-white hover:bg-[#7c3aed] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      data-testid="sarah-save-test-login"
                    >
                      {popup.status === "testing" ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Testing login…
                        </>
                      ) : (
                        <>
                          <KeyRound className="w-4 h-4" />
                          Save & Test Login
                        </>
                      )}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
