import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Shield, LogOut, Settings, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getSafeApiErrorMessage } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import {
  addProjectMember,
  deleteProjectAccount,
  listAdministeredProjects,
  listAssignableUsers,
  listProjectAccounts,
  removeProjectMember,
  updateProjectConfig,
  upsertProjectAccount,
} from "@/lib/projectAdmin";
import { AppRolesEditor, EnvironmentsEditor, cleanEnvironments } from "@/components/admin/AdminDashboard";
import type {
  AssignableUser,
  ProjectAccount,
  ProjectAdminProject,
  ProjectEnvironment,
  ProjectLoginType,
} from "@/types/project";

// Mirrors the Alice provider order (backend PROVIDER_OPTIONS).
const PROVIDER_OPTIONS = [
  { id: "on-premises", label: "On Premises" },
  { id: "claude-sso", label: "Claude (SSO)" },
  { id: "browser-use-cloud", label: "Browser Use" },
  { id: "claude", label: "Claude" },
  { id: "gemini", label: "Gemini" },
  { id: "openai", label: "ChatGPT" },
] as const;

export function ProjectAdminDashboard() {
  const { user, logout } = useAuth();
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
  const [loginType, setLoginType] = useState<ProjectLoginType>("SSO");
  const [memberToAdd, setMemberToAdd] = useState("");

  // Test-login accounts (per environment × role) for the selected project.
  const [accounts, setAccounts] = useState<ProjectAccount[]>([]);
  const [acctEnv, setAcctEnv] = useState("");
  const [acctRole, setAcctRole] = useState("");
  const [acctIdentifier, setAcctIdentifier] = useState("");
  const [acctPassword, setAcctPassword] = useState("");
  const [acctLabel, setAcctLabel] = useState("");

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
    setLoginType(selected.login_type ?? "SSO");
  }, [selected]);

  const reloadAccounts = useCallback(async (projectId: string | null) => {
    if (!projectId) {
      setAccounts([]);
      return;
    }
    try {
      setAccounts(await listProjectAccounts(projectId));
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    }
  }, []);

  useEffect(() => {
    reloadAccounts(selectedId);
  }, [selectedId, reloadAccounts]);

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
        login_type: loginType,
      });
      setStatus("Project configuration saved.");
      await reload();
      // A config save can drop environments/app_roles; refresh the accounts table so it
      // does not keep showing rows bound to an env/role that no longer exists.
      await reloadAccounts(selected.id);
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

  async function handleSaveAccount() {
    if (!selected || !acctEnv || !acctRole || !acctIdentifier.trim()) {
      setError("Environment, role and login identifier are required.");
      return;
    }
    const hasExistingPassword = accounts.some(
      (a) => a.environment === acctEnv && a.role === acctRole && a.has_password,
    );
    if (loginType === "PASSWORD" && !acctPassword.trim() && !hasExistingPassword) {
      setError("A password is required for a password-login project.");
      return;
    }
    setIsBusy(true);
    setError(null);
    try {
      await upsertProjectAccount(selected.id, {
        environment: acctEnv,
        role: acctRole,
        login_identifier: acctIdentifier.trim(),
        password: loginType === "PASSWORD" ? acctPassword || null : null,
        label: acctLabel.trim() || null,
      });
      setAcctIdentifier("");
      setAcctPassword("");
      setAcctLabel("");
      setStatus("Account saved.");
      await reloadAccounts(selected.id);
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDeleteAccount(accountId: string) {
    if (!selected) return;
    setIsBusy(true);
    setError(null);
    try {
      await deleteProjectAccount(selected.id, accountId);
      setStatus("Account removed.");
      await reloadAccounts(selected.id);
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
          <div className="hidden md:block text-right">
            <div className="text-sm font-semibold text-slate-900">
              {(user as { display_name?: string })?.display_name || user?.name}
            </div>
            <div className="text-xs text-slate-500">
              {user?.email} · <span className="text-indigo-600 font-medium">{user?.role}</span>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => Promise.resolve(logout()).catch(console.error)}
            className="flex items-center gap-2 text-slate-600 border-slate-300"
          >
            <LogOut className="w-4 h-4" />
            Logout
          </Button>
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
                    <div>
                      <Label htmlFor="login-type" className="text-slate-700 block mb-1.5">
                        Login type
                      </Label>
                      <select
                        id="login-type"
                        aria-label="Login type"
                        value={loginType}
                        onChange={(e) => setLoginType(e.target.value as ProjectLoginType)}
                        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                      >
                        <option value="SSO">SSO (corporate IdP — capture session manually)</option>
                        <option value="PASSWORD">Username / Password</option>
                      </select>
                    </div>
                    <Button
                      type="submit"
                      disabled={isBusy}
                      className="w-full bg-indigo-600 hover:bg-indigo-700 text-white"
                    >
                      Save configuration
                    </Button>
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
            )}

            {selected && (
              <div className="mt-6 rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="p-5 border-b border-slate-100 font-semibold text-slate-800">
                  Test-login Accounts
                  <span className="ml-2 text-xs font-normal text-slate-400">
                    {loginType === "SSO"
                      ? "SSO — store the email/username only; testers capture their own session."
                      : "Password — stored encrypted; never shown again."}
                  </span>
                </div>
                <div className="p-5 space-y-4">
                  <div className="flex flex-wrap items-end gap-2">
                    <div>
                      <Label className="text-slate-700 block text-xs mb-1">Environment</Label>
                      <select
                        aria-label="Account environment"
                        value={acctEnv}
                        onChange={(e) => setAcctEnv(e.target.value)}
                        className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm"
                      >
                        <option value="">Select…</option>
                        {environments.map((env) => (
                          <option key={env.name} value={env.name}>
                            {env.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <Label className="text-slate-700 block text-xs mb-1">Role</Label>
                      <select
                        aria-label="Account role"
                        value={acctRole}
                        onChange={(e) => setAcctRole(e.target.value)}
                        className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm"
                      >
                        <option value="">Select…</option>
                        {appRoles.map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex-1 min-w-[160px]">
                      <Label className="text-slate-700 block text-xs mb-1">Email / username</Label>
                      <Input
                        aria-label="Account login identifier"
                        value={acctIdentifier}
                        onChange={(e) => setAcctIdentifier(e.target.value)}
                        placeholder="qa-admin@corp"
                      />
                    </div>
                    {loginType === "PASSWORD" && (
                      <div className="min-w-[140px]">
                        <Label className="text-slate-700 block text-xs mb-1">Password</Label>
                        <Input
                          type="password"
                          aria-label="Account password"
                          value={acctPassword}
                          onChange={(e) => setAcctPassword(e.target.value)}
                          placeholder="••••••"
                        />
                      </div>
                    )}
                    <div className="min-w-[120px]">
                      <Label className="text-slate-700 block text-xs mb-1">Label</Label>
                      <Input
                        aria-label="Account label"
                        value={acctLabel}
                        onChange={(e) => setAcctLabel(e.target.value)}
                        placeholder="optional"
                      />
                    </div>
                    <Button
                      type="button"
                      onClick={handleSaveAccount}
                      disabled={isBusy}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white"
                    >
                      Save account
                    </Button>
                  </div>

                  {accounts.length === 0 ? (
                    <div className="text-xs text-slate-500 italic">No accounts yet.</div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-200">
                          <th className="py-2 pr-3">Environment</th>
                          <th className="py-2 pr-3">Role</th>
                          <th className="py-2 pr-3">Login</th>
                          <th className="py-2 pr-3">Password</th>
                          <th className="py-2 pr-3">Label</th>
                          <th className="py-2" />
                        </tr>
                      </thead>
                      <tbody>
                        {accounts.map((a) => (
                          <tr key={a.id} className="border-b border-slate-100">
                            <td className="py-2 pr-3">{a.environment}</td>
                            <td className="py-2 pr-3">{a.role}</td>
                            <td className="py-2 pr-3">{a.login_identifier}</td>
                            <td className="py-2 pr-3">{a.has_password ? "✓" : "—"}</td>
                            <td className="py-2 pr-3 text-slate-500">{a.label ?? ""}</td>
                            <td className="py-2 text-right">
                              <button
                                type="button"
                                onClick={() => handleDeleteAccount(a.id)}
                                disabled={isBusy}
                                aria-label={`Remove account ${a.environment} ${a.role}`}
                                className="text-red-500 hover:text-red-700 font-bold disabled:opacity-50"
                              >
                                ×
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
