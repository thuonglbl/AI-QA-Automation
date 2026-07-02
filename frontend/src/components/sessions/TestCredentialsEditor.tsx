import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { X, KeyRound, Save, Play } from "lucide-react";
import { getSafeApiErrorMessage, ApiError } from "@/lib/api";
import {
  listTestCredentials,
  upsertTestCredential,
  deleteTestCredential,
  testLogin,
  TestAccountCredentialResponse,
} from "@/lib/testCredentials";
import { listSessions } from "@/lib/sessions";
import type { ProjectEnvironment } from "@/types/project";
import type { SessionStatus } from "@/types/session";

interface TestCredentialsEditorProps {
  projectId: string;
  environments: ProjectEnvironment[];
  roles: string[];
}

export function TestCredentialsEditor({
  projectId,
  environments,
  roles,
}: TestCredentialsEditorProps) {
  const [credentials, setCredentials] = useState<TestAccountCredentialResponse[]>([]);
  const [sessions, setSessions] = useState<SessionStatus[]>([]);
  const [, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Modal state
  const [activeCell, setActiveCell] = useState<{ env: string; role: string } | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      // Read credentials AND captured sessions so the matrix reflects the same login
      // state Sarah shows (a credential can exist without a session, and vice-versa).
      const [creds, matrix] = await Promise.all([
        listTestCredentials(projectId),
        listSessions(projectId),
      ]);
      setCredentials(creds);
      setSessions(matrix.captured);
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const credFor = (env: string, role: string) =>
    credentials.find((c) => c.environment === env && c.role === role);

  const sessionFor = (env: string, role: string) =>
    sessions.find((s) => s.environment === env && s.role === role);

  const handleOpenCell = (env: string, role: string) => {
    const existing = credFor(env, role);
    setActiveCell({ env, role });
    setUsername(existing?.username ?? "");
    setPassword("");
    setTotp("");
    setError(null);
  };

  const handleSaveOnly = async () => {
    if (!activeCell || !username.trim() || !password.trim()) return;

    setBusy(true);
    setError(null);
    try {
      await upsertTestCredential(projectId, {
        environment: activeCell.env,
        role: activeCell.role,
        username: username.trim(),
        password: password.trim(),
        totp_secret: totp.trim() || null,
      });
      await load();
      setActiveCell(null);
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const handleSaveAndTest = async () => {
    if (!activeCell || !username.trim() || !password.trim()) return;

    setBusy(true);
    setError(null);
    try {
      await upsertTestCredential(projectId, {
        environment: activeCell.env,
        role: activeCell.role,
        username: username.trim(),
        password: password.trim(),
        totp_secret: totp.trim() || null,
      });
      const result = await testLogin(projectId, activeCell.env, activeCell.role);
      if (!result.success) {
        throw new ApiError("server", result.error || "Login test failed.");
      }
      await load();
      setActiveCell(null);
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (credentialId: string) => {
    if (!confirm("Are you sure you want to delete this test credential?")) return;
    setBusy(true);
    setError(null);
    try {
      await deleteTestCredential(projectId, credentialId);
      await load();
      if (activeCell) setActiveCell(null);
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (!environments.length || !roles.length) {
    return (
      <div className="text-sm italic text-slate-500">
        No environments or roles available in this project.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && <div className="text-sm text-red-600">{error}</div>}
      
      <div className="overflow-x-auto rounded-md border border-slate-200">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-slate-50">
              <th className="border-b px-3 py-2 text-left text-xs font-medium text-slate-500">
                Role
              </th>
              {environments.map((env) => (
                <th
                  key={env.name}
                  className="border-b border-l px-3 py-2 text-left text-xs font-medium text-slate-700"
                >
                  {env.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {roles.map((role) => (
              <tr key={role} className="align-top">
                <th className="border-b px-3 py-3 text-left font-medium text-slate-700">
                  {role}
                </th>
                {environments.map((env) => {
                  const cred = credFor(env.name, role);
                  const session = sessionFor(env.name, role);
                  // A session past its TTL cannot be used (auto-login ignores it), so show it
                  // as "expired", not "Captured" — otherwise Jack blocks while the UI says ready.
                  const sessionExpired = !!(
                    session?.expires_at && new Date(session.expires_at).getTime() <= Date.now()
                  );
                  const captured = session && !sessionExpired ? session : null;
                  return (
                    <td key={env.name} className="border-b border-l px-3 py-3">
                      <div className="flex flex-col gap-1.5">
                        {captured && (
                          <div
                            className="flex items-center gap-1.5 text-xs text-emerald-700 font-medium"
                            title={`Login session captured (${captured.cookie_count} cookies)`}
                          >
                            <span className="inline-block w-2 h-2 rounded-full bg-emerald-500" />
                            Captured
                          </div>
                        )}
                        {sessionExpired && (
                          <div
                            className="flex items-center gap-1.5 text-xs text-amber-600 font-medium"
                            title="The captured session has expired; re-save credentials to log in again."
                          >
                            <span className="inline-block w-2 h-2 rounded-full bg-amber-400" />
                            Session expired
                          </div>
                        )}
                        {cred ? (
                          <>
                            <div className="flex items-center gap-1.5 text-xs text-slate-600 font-medium">
                              <KeyRound className="w-3.5 h-3.5" />
                              Credentials saved
                            </div>
                            <div
                              className="text-[11px] text-slate-500 truncate"
                              title={cred.username}
                            >
                              {cred.username}
                            </div>
                            <div className="flex items-center gap-2 mt-1">
                              <button
                                type="button"
                                onClick={() => handleOpenCell(env.name, role)}
                                className="text-xs text-indigo-600 hover:text-indigo-800 hover:underline"
                              >
                                Update
                              </button>
                              <span className="text-slate-300">|</span>
                              <button
                                type="button"
                                onClick={() => handleDelete(cred.id)}
                                className="text-xs text-red-600 hover:text-red-800 hover:underline disabled:opacity-50"
                                disabled={busy}
                              >
                                Delete
                              </button>
                            </div>
                          </>
                        ) : (
                          <>
                            {!session && (
                              <span className="text-xs text-slate-400 italic">Not set</span>
                            )}
                            <button
                              type="button"
                              onClick={() => handleOpenCell(env.name, role)}
                              className="text-xs text-indigo-600 hover:text-indigo-800 hover:underline w-fit"
                            >
                              Set Credentials
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {activeCell && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-900">
                Test Credentials
              </h3>
              <button
                type="button"
                onClick={() => setActiveCell(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <p className="text-sm text-slate-600 mb-5">
              Set credentials for <span className="font-semibold">{activeCell.role}</span> in <span className="font-semibold">{activeCell.env}</span>.
            </p>

            <div className="space-y-4">
              <div>
                <Label htmlFor="cred-username" className="text-slate-700 block mb-1.5">Username</Label>
                <Input
                  id="cred-username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="test.user@company.com"
                  required
                />
              </div>
              <div>
                <Label htmlFor="cred-password" className="text-slate-700 block mb-1.5">Password</Label>
                <Input
                  id="cred-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                />
                <p className="text-xs text-slate-500 mt-1.5">
                  Passwords are encrypted at rest and never returned to the UI.
                </p>
              </div>
              <div>
                <Label htmlFor="cred-totp" className="text-slate-700 block mb-1.5">TOTP Secret (Optional)</Label>
                <Input
                  id="cred-totp"
                  type="password"
                  value={totp}
                  onChange={(e) => setTotp(e.target.value)}
                  placeholder="JBSWY3DPEHPK3PXP"
                />
                <p className="text-xs text-slate-500 mt-1.5">
                  Base32 secret for generating 2FA tokens.
                </p>
              </div>

              <div className="flex justify-end gap-3 mt-6 pt-4 border-t">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setActiveCell(null)}
                  disabled={busy}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy || !username || !password}
                  onClick={handleSaveOnly}
                  className="gap-2"
                >
                  <Save className="w-4 h-4" />
                  Save Only
                </Button>
                <Button
                  type="button"
                  disabled={busy || !username || !password}
                  onClick={handleSaveAndTest}
                  className="gap-2 bg-indigo-600 hover:bg-indigo-700 text-white"
                >
                  <Play className="w-4 h-4" />
                  Save & Test Login
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
