import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Shield, LogOut, Settings, X, ArrowLeft } from "lucide-react";
import { UserBadge } from "@/components/auth/UserBadge";
import { AppVersion } from "@/components/AppVersion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getSafeApiErrorMessage } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import {
  addProjectMember,
  listAdministeredProjects,
  listAssignableUsers,
  removeProjectMember,
  updateProjectConfig,
} from "@/lib/projectAdmin";
import { checkConnections } from "@/lib/sessions";
import { AppRolesEditor, EnvironmentsEditor, cleanEnvironments } from "@/components/admin/AdminDashboard";
import type {
  AssignableUser,
  ProjectAdminProject,
  ProjectEnvironment,
} from "@/types/project";
import type { EnvConnectionStatus } from "@/types/session";


// Mirrors the Alice provider order (backend PROVIDER_OPTIONS).
const PROVIDER_OPTIONS = [
  { id: "on-premises", label: "On Premises" },
  { id: "claude-sso", label: "Claude (SSO)" },
  { id: "browser-use-cloud", label: "Browser Use" },
  { id: "claude", label: "Claude" },
  { id: "gemini", label: "Gemini" },
  { id: "openai", label: "ChatGPT" },
] as const;

export function ProjectAdminDashboard({
  onBackToWorkspace,
  onNavigateToAdmin,
}: {
  onBackToWorkspace?: () => void;
  onNavigateToAdmin?: () => void;
} = {}) {
  const { user, logout } = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectAdminProject[]>([]);
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Config form state (synced from the selected project).
  const [confluence, setConfluence] = useState("");
  const [jira, setJira] = useState("");
  const [providers, setProviders] = useState<string[]>([]);
  const [environments, setEnvironments] = useState<ProjectEnvironment[]>([]);
  const [appRoles, setAppRoles] = useState<string[]>([]);
  const [memberToAdd, setMemberToAdd] = useState("");

  // Reachability probe results for the selected project's saved environments.
  const [connChecks, setConnChecks] = useState<EnvConnectionStatus[] | null>(null);
  const [checkingConns, setCheckingConns] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [proj, usr] = await Promise.all([
        listAdministeredProjects(),
        listAssignableUsers(),
      ]);
      setProjects(proj);
      setUsers(usr);
      setSelectedId((prev) => prev ?? (proj[0]?.id ?? null));
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    }
  }, []);

  useEffect(() => {
    setIsLoading(true);
    reload().finally(() => setIsLoading(false));
  }, [reload]);

  useEffect(() => {
    if (!status) return;
    const t = window.setTimeout(() => setStatus(null), 3000);
    return () => window.clearTimeout(t);
  }, [status]);

  const selected = useMemo(
    () => projects.find((p) => p.id === selectedId) ?? null,
    [projects, selectedId],
  );

  // Hydrate the config form ONCE per selected project, keyed by its id. `selected`
  // is a `find()` result whose reference changes on every `reload()` (initial load,
  // StrictMode's double-mount, and after each save / member change), so reacting to
  // the object identity would re-run this on every refetch and clobber the form —
  // wiping in-flight edits the user (or an E2E run) typed before the refetch settled.
  // Guarding on the project id repopulates only when the user actually switches
  // projects; a same-project refetch leaves the live form untouched.
  const hydratedProjectIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selected) {
      hydratedProjectIdRef.current = null;
      return;
    }
    if (hydratedProjectIdRef.current === selected.id) return;
    hydratedProjectIdRef.current = selected.id;
    setConfluence(selected.confluence_base_url ?? "");
    setJira(selected.jira_base_url ?? "");
    setProviders(selected.enabled_providers ?? []);
    setEnvironments(selected.environments ?? []);
    setAppRoles(selected.app_roles ?? []);
    setConnChecks(null);
  }, [selected]);

  const usersById = useMemo(() => new Map(users.map((u) => [u.id, u])), [users]);

  const toggleProvider = (id: string) =>
    setProviders((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));

  async function handleSaveConfig(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    if (!confluence.trim() && !jira.trim()) {
      setError("Provide a Confluence URL, a Jira URL, or both.");
      return;
    }
    if (providers.length === 0) {
      setError("Enable at least one provider.");
      return;
    }
    setIsBusy(true);
    setError(null);
    setStatus(null);
    try {
      await updateProjectConfig(selected.id, {
        confluence_base_url: confluence.trim() || null,
        jira_base_url: jira.trim() || null,
        enabled_providers: providers,
        environments: cleanEnvironments(environments),
        app_roles: appRoles,
      });
      setStatus("Project configuration saved.");
      await reload();
      // On a successful save, automatically probe whether this app server can reach each
      // saved environment so the admin learns immediately if a firewall is blocking it.
      setConnChecks(null);
      setCheckingConns(true);
      try {
        setConnChecks(await checkConnections(selected.id));
      } catch {
        // A failed probe is non-fatal — the configuration is already saved.
      } finally {
        setCheckingConns(false);
      }
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAddMember() {
    if (!selected || !memberToAdd) return;
    setIsBusy(true);
    setError(null);
    try {
      await addProjectMember(selected.id, memberToAdd);
      setMemberToAdd("");
      setStatus("Member added.");
      await reload();
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRemoveMember(userId: string) {
    if (!selected) return;
    setIsBusy(true);
    setError(null);
    try {
      await removeProjectMember(selected.id, userId);
      setStatus("Member removed.");
      await reload();
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  const memberIds = useMemo(
    () => new Set((selected?.memberships ?? []).map((m) => m.user_id)),
    [selected],
  );
  const assignable = useMemo(
    // A project_admin may only assign standard users (admins / project_admins are excluded);
    // a platform admin is unrestricted, mirroring the backend which only gates project_admins.
    () =>
      users.filter(
        (u) => !memberIds.has(u.id) && (user?.role === "admin" || u.role === "standard"),
      ),
    [users, memberIds, user?.role],
  );

  return (
    <div className="min-h-screen bg-[#f8fafc] flex flex-col">
      <nav className="bg-white border-b border-[#e2e8f0] px-6 py-3 flex justify-between items-center shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-md bg-indigo-600 flex items-center justify-center text-white">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[15px] font-bold text-[#0f172a]">
              AI <span className="text-indigo-600">QA Automation</span>
            </div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Project Administration
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center hover:opacity-80 transition-opacity focus:outline-none"
              title="User menu"
            >
              <UserBadge user={user} roleClassName="text-indigo-600" displayRole="Project Admin" />
            </button>

            {userMenuOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setUserMenuOpen(false)}
                />
                <div className="absolute right-0 mt-2 w-56 bg-white rounded-md shadow-lg py-1 border border-slate-200 z-50">
                  {onNavigateToAdmin && (
                    <button
                      onClick={() => {
                        onNavigateToAdmin();
                        setUserMenuOpen(false);
                      }}
                      className="flex w-full items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100"
                    >
                      <Shield className="w-4 h-4" />
                      Admin Dashboard
                    </button>
                  )}
                  {onBackToWorkspace && (
                    <button
                      onClick={() => {
                        onBackToWorkspace();
                        setUserMenuOpen(false);
                      }}
                      className="flex w-full items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100"
                    >
                      <ArrowLeft className="w-4 h-4" />
                      User UI
                    </button>
                  )}
                  <div className="h-px bg-slate-200 my-1" />
                  <div className="px-4 py-2 text-xs text-slate-500">
                    Version: <AppVersion className="inline" />
                  </div>
                  <button
                    onClick={() => {
                      Promise.resolve(logout()).catch(console.error);
                      setUserMenuOpen(false);
                    }}
                    className="flex w-full items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100"
                  >
                    <LogOut className="w-4 h-4" />
                    Logout
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </nav>

      <main className="flex-1 p-6 md:p-8 max-w-5xl mx-auto w-full">
        <div className="mb-6 flex items-center gap-3">
          <Settings className="w-6 h-6 text-slate-600" />
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Project Admin Dashboard</h1>
        </div>

        <div aria-live="polite" className="space-y-3 mb-6">
          {status && (
            <p className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-800">
              {status}
            </p>
          )}
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-800 flex justify-between">
              <span>{error}</span>
              <button type="button" onClick={() => setError(null)} aria-label="Dismiss error">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>

        {isLoading ? (
          <div className="text-sm text-slate-500">Loading…</div>
        ) : projects.length === 0 ? (
          <div className="text-sm text-slate-500 italic">
            You don&apos;t administer any projects yet.
          </div>
        ) : (
          <>
            <div className="mb-6">
              <Label className="text-slate-700 block mb-1.5">Project</Label>
              <select
                aria-label="Select project"
                value={selectedId ?? ""}
                onChange={(e) => setSelectedId(e.target.value)}
                className="w-full max-w-sm rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            {selected && (
              <>
                <div className="grid gap-6 lg:grid-cols-2">
                {/* Configuration */}
                <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
                  <div className="p-5 border-b border-slate-100 font-semibold text-slate-800">
                    Configuration
                  </div>
                  <form onSubmit={handleSaveConfig} className="p-5 space-y-4">
                    <div>
                      <Label className="text-slate-700 block">Confluence Base URL</Label>
                      <Input
                        value={confluence}
                        onChange={(e) => setConfluence(e.target.value)}
                        placeholder="https://confluence.company.com"
                        className="mt-1.5"
                      />
                    </div>
                    <div>
                      <Label className="text-slate-700 block">Jira Base URL</Label>
                      <Input
                        value={jira}
                        onChange={(e) => setJira(e.target.value)}
                        placeholder="https://jira.company.com"
                        className="mt-1.5"
                      />
                      <p className="text-xs text-slate-400 mt-1">
                        At least one of Confluence or Jira URL is required.
                      </p>
                    </div>
                    <div>
                      <Label className="text-slate-700 block mb-1.5">Enabled Providers</Label>
                      <div className="flex flex-wrap gap-x-4 gap-y-2">
                        {PROVIDER_OPTIONS.map((opt) => (
                          <label
                            key={opt.id}
                            className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer"
                          >
                            <input
                              type="checkbox"
                              checked={providers.includes(opt.id)}
                              onChange={() => toggleProvider(opt.id)}
                              className="rounded border-slate-300 accent-indigo-600"
                            />
                            {opt.label}
                          </label>
                        ))}
                      </div>
                    </div>
                    <EnvironmentsEditor environments={environments} onChange={setEnvironments} />
                    <AppRolesEditor roles={appRoles} onChange={setAppRoles} />
                    <Button
                      type="submit"
                      disabled={isBusy}
                      className="w-full bg-indigo-600 hover:bg-indigo-700 text-white"
                    >
                      Save configuration
                    </Button>

                    {/* Per-environment reachability, probed automatically after a save. */}
                    {(checkingConns || connChecks) && (
                      <div className="space-y-1.5" data-testid="env-connection-status">
                        <Label className="text-slate-700 block">Environment connectivity</Label>
                        {checkingConns ? (
                          <p className="text-xs text-slate-500">Checking…</p>
                        ) : (connChecks ?? []).length === 0 ? (
                          <p className="text-xs italic text-slate-500">
                            No saved environments to check.
                          </p>
                        ) : (
                          (connChecks ?? []).map((c) => (
                            <div
                              key={c.name}
                              className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2 text-xs"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-medium text-slate-700">
                                  {c.name}
                                  <span className="ml-2 font-normal text-slate-400">{c.url}</span>
                                </span>
                                {c.reachable ? (
                                  <span className="font-medium text-green-700">✓ Connected</span>
                                ) : (
                                  <span className="font-medium text-red-600">✗ Failed</span>
                                )}
                              </div>
                              {!c.reachable && (
                                <p className="mt-1 text-red-600">
                                  Please contact Administrator to open firewall from this app
                                  server to your app
                                </p>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </form>
                </div>

                {/* Membership */}
                <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
                  <div className="p-5 border-b border-slate-100 font-semibold text-slate-800">
                    Members
                  </div>
                  <div className="p-5 space-y-4">
                    <div className="flex items-center gap-2">
                      <select
                        aria-label="Select user to add"
                        value={memberToAdd}
                        onChange={(e) => setMemberToAdd(e.target.value)}
                        disabled={assignable.length === 0 || isBusy}
                        className="flex-1 rounded-md border border-slate-300 bg-white px-2 py-2 text-sm disabled:opacity-60"
                      >
                        <option value="">Select user…</option>
                        {assignable.map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.display_name} ({u.email})
                          </option>
                        ))}
                      </select>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleAddMember}
                        disabled={!memberToAdd || isBusy}
                        aria-label="Add member"
                        className="h-9"
                      >
                        <Plus className="h-4 w-4" />
                      </Button>
                    </div>

                    {(selected.memberships ?? []).length === 0 ? (
                      <div className="text-xs text-slate-500 italic">No members yet.</div>
                    ) : (
                      <ul className="space-y-1">
                        {(selected.memberships ?? []).map((m) => {
                          const u = usersById.get(m.user_id);
                          // A project_admin may only remove standard members; a platform
                          // admin keeps full control.
                          const removable = user?.role === "admin" || m.role === "member";
                          return (
                            <li
                              key={m.id}
                              className="flex items-center justify-between rounded border border-slate-100 bg-slate-50 px-3 py-2 text-sm"
                            >
                              <span>
                                {u ? `${u.display_name} (${u.email})` : m.user_id}
                                <span className="ml-2 text-[10px] uppercase text-slate-500">
                                  {m.role}
                                </span>
                              </span>
                              {removable && (
                                <button
                                  type="button"
                                  onClick={() => handleRemoveMember(m.user_id)}
                                  disabled={isBusy}
                                  aria-label={`Remove member ${u?.display_name ?? m.user_id}`}
                                  className="text-red-500 hover:text-red-700 font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  ×
                                </button>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
