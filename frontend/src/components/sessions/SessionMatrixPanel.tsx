import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  autoCaptureSession,
  captureSession,
  deleteSession,
  listSessions,
} from "@/lib/sessions";
import type { SessionMatrix, SessionStatus } from "@/types/session";

const DEFAULT_CDP_URL = "http://localhost:9222";

const AUTH_METHOD_LABELS: Record<string, string> = {
  SSO_MANUAL: "Manual (SSO)",
  PASSWORD: "Password",
  API_TOKEN: "API token",
  SSO_TOTP: "SSO + TOTP",
};

interface SessionMatrixPanelProps {
  projectId: string;
  projectName?: string | null;
  open: boolean;
  onClose: () => void;
}

type ActiveForm = { environment: string; role: string; mode: "manual" | "auto" };

const PRIMARY_BTN =
  "px-3 py-1 rounded-md text-xs font-medium bg-orange-600 text-white hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed";
const PLAIN_BTN =
  "px-3 py-1 rounded-md text-xs font-medium border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50";
const DANGER_BTN =
  "px-3 py-1 rounded-md text-xs font-medium border border-red-300 bg-white text-red-600 hover:bg-red-50 disabled:opacity-50";

/**
 * Per-user test-login session manager (project-scoped). Shows the (environment × role)
 * matrix and lets a tester capture / re-capture / delete THEIR own session for each slot:
 * SSO projects capture from a hand-launched debug browser over CDP; PASSWORD projects can
 * additionally auto-login via the backend. The session blob never reaches the client — only
 * non-secret status. Sarah (debug) and Jack (run) rehydrate the captured session server-side.
 */
export function SessionMatrixPanel({
  projectId,
  projectName,
  open,
  onClose,
}: SessionMatrixPanelProps) {
  const [matrix, setMatrix] = useState<SessionMatrix | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [active, setActive] = useState<ActiveForm | null>(null);
  const [cdpUrl, setCdpUrl] = useState(DEFAULT_CDP_URL);
  const [chromePath, setChromePath] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setMatrix(await listSessions(projectId));
    } catch {
      setLoadError("Could not load sessions for this project.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (open && projectId) {
      setActive(null);
      setActionError(null);
      void refresh();
    }
  }, [open, projectId, refresh]);

  if (!open) return null;

  const isPassword = matrix?.login_type === "PASSWORD";
  const environments = matrix?.environments ?? [];
  const roles = matrix?.app_roles ?? [];

  const statusFor = (environment: string, role: string): SessionStatus | undefined =>
    matrix?.captured.find((s) => s.environment === environment && s.role === role);

  function openForm(environment: string, role: string, mode: "manual" | "auto") {
    setActionError(null);
    setCdpUrl(DEFAULT_CDP_URL);
    setChromePath("");
    setActive({ environment, role, mode });
  }

  async function submitForm() {
    if (!active) return;
    if (active.mode === "auto" && !chromePath.trim()) {
      setActionError("Enter the Chrome/Edge executable path.");
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      if (active.mode === "auto") {
        await autoCaptureSession(projectId, {
          environment: active.environment,
          role: active.role,
          chrome_path: chromePath.trim(),
        });
      } else {
        await captureSession(projectId, {
          environment: active.environment,
          role: active.role,
          auth_method: isPassword ? "PASSWORD" : "SSO_MANUAL",
          cdp_url: cdpUrl.trim() || DEFAULT_CDP_URL,
        });
      }
      setActive(null);
      await refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Capture failed — try again.");
    } finally {
      setBusy(false);
    }
  }

  async function removeSession(environment: string, role: string) {
    setBusy(true);
    setActionError(null);
    try {
      await deleteSession(projectId, environment, role);
      await refresh();
    } catch {
      setActionError("Could not delete the session.");
    } finally {
      setBusy(false);
    }
  }

  const ready = matrix && !loading;
  const hasMatrix = environments.length > 0 && roles.length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Test-login sessions"
      onClick={onClose}
    >
      <div
        className="mt-10 flex max-h-[85vh] w-full max-w-3xl flex-col rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-800">Test-login sessions</h2>
            {projectName && <span className="text-xs text-slate-500">{projectName}</span>}
            {matrix && (
              <Badge variant="outline" className="text-xs">
                {isPassword ? "Password login" : "SSO login"}
              </Badge>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-slate-500 hover:bg-slate-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
          {loading && <p className="text-sm text-slate-500">Loading sessions…</p>}
          {loadError && <p className="text-sm text-red-600">{loadError}</p>}
          {actionError && (
            <p className="text-sm text-red-600" role="alert">
              {actionError}
            </p>
          )}

          {ready && !hasMatrix && (
            <p className="text-sm text-slate-500">
              This project has no environments and roles configured yet. Ask a project admin to
              add them in the Project Admin dashboard.
            </p>
          )}

          {ready &&
            hasMatrix &&
            environments.map((env) => (
              <div key={env.name} className="overflow-hidden rounded-md border">
                <div className="border-b bg-slate-50 px-3 py-2">
                  <span className="text-sm font-medium text-slate-700">{env.name}</span>
                  {env.url && <span className="ml-2 text-xs text-slate-400">{env.url}</span>}
                </div>
                <div className="divide-y">
                  {roles.map((role) => {
                    const s = statusFor(env.name, role);
                    const isActive =
                      active?.environment === env.name && active?.role === role;
                    return (
                      <div key={role} className="flex flex-col gap-2 px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="w-28 shrink-0 text-sm text-slate-700">{role}</span>
                          {s ? (
                            <Badge
                              variant="outline"
                              className="border-green-300 bg-green-50 text-xs text-green-700"
                            >
                              Captured · {AUTH_METHOD_LABELS[s.auth_method] ?? s.auth_method} ·{" "}
                              {s.cookie_count} cookie(s)
                            </Badge>
                          ) : (
                            <Badge
                              variant="outline"
                              className="bg-slate-50 text-xs text-slate-500"
                            >
                              Not captured
                            </Badge>
                          )}
                          {s && (
                            <span className="text-xs text-slate-400">
                              {new Date(s.captured_at).toLocaleString()}
                            </span>
                          )}
                          <div className="ml-auto flex items-center gap-2">
                            {isPassword && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => openForm(env.name, role, "auto")}
                                className={PRIMARY_BTN}
                              >
                                Auto-login
                              </button>
                            )}
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => openForm(env.name, role, "manual")}
                              className={PLAIN_BTN}
                            >
                              {s ? "Re-capture" : "Capture"}
                            </button>
                            {s && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => removeSession(env.name, role)}
                                className={DANGER_BTN}
                              >
                                Delete
                              </button>
                            )}
                          </div>
                        </div>

                        {isActive && (
                          <div className="-mx-3 flex flex-col gap-2 border-t bg-slate-50 px-3 pb-2 pt-2">
                            {active.mode === "auto" ? (
                              <>
                                <label
                                  htmlFor="session-chrome-path"
                                  className="text-xs font-medium text-slate-600"
                                >
                                  Chrome/Edge executable path
                                </label>
                                <input
                                  id="session-chrome-path"
                                  value={chromePath}
                                  onChange={(e) => setChromePath(e.target.value)}
                                  placeholder="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
                                  disabled={busy}
                                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                                />
                                <p className="text-xs text-slate-500">
                                  The backend logs in with the project&apos;s stored credential and
                                  captures your session — no password is shown here.
                                </p>
                              </>
                            ) : (
                              <>
                                <label
                                  htmlFor="session-cdp-url"
                                  className="text-xs font-medium text-slate-600"
                                >
                                  Debug-browser CDP URL
                                </label>
                                <input
                                  id="session-cdp-url"
                                  value={cdpUrl}
                                  onChange={(e) => setCdpUrl(e.target.value)}
                                  placeholder={DEFAULT_CDP_URL}
                                  disabled={busy}
                                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                                />
                                <p className="text-xs text-slate-500">
                                  Launch Chrome/Edge with{" "}
                                  <code className="rounded bg-slate-200 px-1">
                                    --remote-debugging-port=9222
                                  </code>
                                  , log in to {env.name}, then capture.
                                </p>
                              </>
                            )}
                            <div className="flex gap-2">
                              <button
                                type="button"
                                disabled={busy}
                                onClick={submitForm}
                                className={PRIMARY_BTN}
                              >
                                {busy
                                  ? "Capturing…"
                                  : active.mode === "auto"
                                    ? "Auto-login & capture"
                                    : "Capture now"}
                              </button>
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => setActive(null)}
                                className={PLAIN_BTN}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
