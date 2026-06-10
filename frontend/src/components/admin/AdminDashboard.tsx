import { useEffect, useState, useMemo } from "react";
import {
  Plus,
  Shield,
  UserPlus,
  Users,
  LogOut,
  Settings,
  X,
  FlaskConical,
  Download,
  CheckCircle,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  assignProjectMembership,
  createAdminProject,
  createAdminUser,
  deleteAdminProject,
  listAdminUsers,
  removeProjectMembership,
  updateAdminProject,
  runE2ETests,
  downloadE2EReport,
} from "@/lib/projects";
import { getSafeApiErrorMessage, API_BASE_PATH } from "@/lib/api";
import { useProject } from "@/hooks/useProject";
import { useAuth } from "@/hooks/useAuth";
import type { AdminUser, E2ETestRunResult } from "@/types/project";

export function AdminDashboard() {
  const { projects, reloadProjects } = useProject();
  const { user, logout } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(true);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [confluenceBaseUrl, setConfluenceBaseUrl] = useState("");
  const [jiraBaseUrl, setJiraBaseUrl] = useState("");
  const PROVIDER_OPTIONS = [
    { id: "browser-use-cloud", label: "Browser Use" },
    { id: "claude",            label: "Claude" },
    { id: "gemini",            label: "Gemini" },
    { id: "openai",            label: "ChatGPT" },
    { id: "on-premises",       label: "On Premises" },
  ] as const;
  const [enabledProviders, setEnabledProviders] = useState<string[]>([]);

  const PROVIDER_ICON_FILES: Record<string, string> = {
    "browser-use-cloud": "/provider-icons/browser-use.png",
    "claude":            "/provider-icons/anthropic.svg",
    "gemini":            "/provider-icons/google-gemini.svg",
    "openai":            "/provider-icons/openai.svg",
    "on-premises":       "/provider-icons/on-premises.png",
  };

  function toggleProvider(
    providerId: string,
    current: string[],
    setter: React.Dispatch<React.SetStateAction<string[]>>,
  ) {
    setter(
      current.includes(providerId)
        ? current.filter((p) => p !== providerId)
        : [...current, providerId],
    );
  }
  const [createUserEmail, setCreateUserEmail] = useState("");
  const [createUserDisplayName, setCreateUserDisplayName] = useState("");
  const [createUserRole, setCreateUserRole] = useState<"standard" | "admin">(
    "standard",
  );
  const [createUserPassword, setCreateUserPassword] = useState("");
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editProjectName, setEditProjectName] = useState("");
  const [editProjectDescription, setEditProjectDescription] = useState("");
  const [editProjectConfluenceBaseUrl, setEditProjectConfluenceBaseUrl] =
    useState("");
  const [editProjectJiraBaseUrl, setEditProjectJiraBaseUrl] = useState("");
  const [editEnabledProviders, setEditEnabledProviders] = useState<string[]>([]);
  const [selectedProjectByUserId, setSelectedProjectByUserId] = useState<
    Record<string, string>
  >({});
  const [status, setStatus] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ id: number; msg: string }[]>([]);
  const [isBusy, setIsBusy] = useState(false);
  const [errorIdCounter, setErrorIdCounter] = useState(0);
  const [isRunningE2E, setIsRunningE2E] = useState(false);
  const [e2eResult, setE2eResult] = useState<E2ETestRunResult | null>(null);

  const [isDownloadingReport, setIsDownloadingReport] = useState(false);

  const addError = (msg: string) => {
    setErrors((prev) => [...prev, { id: errorIdCounter, msg }]);
    setErrorIdCounter((prev) => prev + 1);
  };

  const dismissError = (id: number) => {
    setErrors((prev) => prev.filter((e) => e.id !== id));
  };

  useEffect(() => {
    if (!status) return;
    const timeout = window.setTimeout(() => setStatus(null), 3000);
    return () => window.clearTimeout(timeout);
  }, [status]);

  const loadUsers = async () => {
    try {
      const u = await listAdminUsers();
      setUsers(u || []);
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    }
  };

  useEffect(() => {
    setIsLoadingUsers(true);
    loadUsers().finally(() => setIsLoadingUsers(false));
  }, []);

  async function handleCreateProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      addError("Project name is required.");
      return;
    }
    if (!confluenceBaseUrl.trim() && !jiraBaseUrl.trim()) {
      addError("No link to extract requirement. Please provide Confluence URL, Jira URL, or both.");
      return;
    }
    if (enabledProviders.length === 0) {
      addError("No provider to execute. Please enable at least one provider.");
      return;
    }

    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await createAdminProject({
        name: trimmedName,
        description: description.trim() || null,
        confluence_base_url: confluenceBaseUrl.trim() || null,
        jira_base_url: jiraBaseUrl.trim() || null,
        enabled_providers: enabledProviders,
      });
      setName("");
      setDescription("");
      setConfluenceBaseUrl("");
      setJiraBaseUrl("");
      setEnabledProviders([]);
      setStatus("Project created successfully.");
      await reloadProjects();
      await loadUsers();
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreateUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await createAdminUser({
        email: createUserEmail.trim(),
        display_name: createUserDisplayName.trim(),
        role: createUserRole,
        initial_password: createUserPassword,
      });
      setCreateUserEmail("");
      setCreateUserDisplayName("");
      setCreateUserRole("standard");
      setCreateUserPassword("");
      setStatus("User created successfully.");
      await loadUsers();
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  function startEditingProject(project: (typeof projects)[number]) {
    setEditingProjectId(project.id);
    setEditProjectName(project.name);
    setEditProjectDescription(project.description ?? "");
    setEditProjectConfluenceBaseUrl(project.confluence_base_url ?? "");
    setEditProjectJiraBaseUrl(project.jira_base_url ?? "");
    setEditEnabledProviders(project.enabled_providers ?? []);
  }

  function cancelEditingProject() {
    setEditingProjectId(null);
    setEditProjectName("");
    setEditProjectDescription("");
    setEditProjectConfluenceBaseUrl("");
    setEditProjectJiraBaseUrl("");
    setEditEnabledProviders([]);
  }

  async function handleEditProject(
    event: React.FormEvent<HTMLFormElement>,
    project: (typeof projects)[number],
  ) {
    event.preventDefault();
    const trimmedName = editProjectName.trim();
    if (!trimmedName) {
      addError("Project name is required.");
      return;
    }
    if (!editProjectConfluenceBaseUrl.trim() && !editProjectJiraBaseUrl.trim()) {
      addError("No link to extract requirement. Please provide Confluence URL, Jira URL, or both.");
      return;
    }
    if (editEnabledProviders.length === 0) {
      addError("No provider to execute. Please enable at least one provider.");
      return;
    }
    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await updateAdminProject(project.id, {
        name: trimmedName,
        description: editProjectDescription.trim() || null,
        confluence_base_url: editProjectConfluenceBaseUrl.trim() || null,
        jira_base_url: editProjectJiraBaseUrl.trim() || null,
        enabled_providers: editEnabledProviders,
      });
      cancelEditingProject();
      setStatus("Project updated successfully.");
      await reloadProjects();
      await loadUsers();
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDeleteProject(project: (typeof projects)[number]) {
    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await deleteAdminProject(project.id);
      setStatus("Project deleted successfully.");
      await reloadProjects();
      await loadUsers();
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAssignUserToProject(targetUser: AdminUser) {
    if (!targetUser.is_active) {
      addError("Inactive users cannot be assigned to projects.");
      return;
    }
    const availableProjects = projects.filter(
      (project) =>
        !project.memberships?.some(
          (membership) => membership.user_id === targetUser.id,
        ),
    );
    const selectedProjectId = selectedProjectByUserId[targetUser.id];
    const availableProject =
      availableProjects.find((project) => project.id === selectedProjectId) ??
      availableProjects[0];
    if (!availableProject) {
      addError("No available projects to assign.");
      return;
    }
    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await assignProjectMembership(availableProject.id, {
        user_id: targetUser.id,
        role: "member",
      });
      setSelectedProjectByUserId((prev) => ({ ...prev, [targetUser.id]: "" }));
      setStatus("Project assigned successfully.");
      await reloadProjects();
      await loadUsers();
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRemoveUserFromProject(
    projectId: string,
    targetUser: AdminUser,
  ) {
    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await removeProjectMembership(projectId, targetUser.id);
      setStatus("Project unassigned successfully.");
      await reloadProjects();
      await loadUsers();
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRunE2ETests() {
    setIsRunningE2E(true);
    setE2eResult(null);
    setErrors([]);
    setStatus(null);
    try {
      const result = await runE2ETests();
      setE2eResult(result);
      setStatus(
        result.passed
          ? "E2E tests passed!"
          : "E2E tests completed with failures.",
      );
      // AC 2: automatically download the report to the admin's machine when available.
      if (result.report_available) {
        try {
          await downloadE2EReport();
        } catch (err) {
          addError(getSafeApiErrorMessage(err));
        }
      }
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsRunningE2E(false);
    }
  }

  async function handleDownloadReport() {
    setIsDownloadingReport(true);
    try {
      await downloadE2EReport();
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsDownloadingReport(false);
    }
  }



  const projectsByUserId = useMemo(() => {
    const map = new Map<string, typeof projects>();
    projects.forEach((p) => {
      p.memberships?.forEach((m) => {
        if (!map.has(m.user_id)) map.set(m.user_id, []);
        map.get(m.user_id)!.push(p);
      });
    });
    return map;
  }, [projects]);

  const assignableProjectsByUserId = useMemo(() => {
    const map = new Map<string, typeof projects>();
    users.forEach((u) => {
      map.set(
        u.id,
        projects.filter(
          (project) =>
            !project.memberships?.some(
              (membership) => membership.user_id === u.id,
            ),
        ),
      );
    });
    return map;
  }, [projects, users]);

  return (
    <div className="min-h-screen bg-[#f8fafc] flex flex-col">
      {/* Top Navigation for Admin */}
      <nav className="bg-white border-b border-[#e2e8f0] px-6 py-3 flex justify-between items-center z-50 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-md bg-blue-600 flex items-center justify-center text-white font-bold flex-shrink-0">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[15px] font-bold text-[#0f172a] whitespace-nowrap">
              AI <span className="text-blue-600">QA Automation</span>
            </div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Administration
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden md:block text-right">
            <div className="text-sm font-semibold text-slate-900">
              {(user as any)?.display_name || user?.name}
            </div>
            <div className="text-xs text-slate-500">
              {user?.email} ·{" "}
              <span className="text-blue-600 font-medium">{user?.role}</span>
            </div>
          </div>
          <div className="w-px h-8 bg-slate-200 hidden md:block" />
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              Promise.resolve(logout()).catch(console.error);
            }}
            className="flex items-center gap-2 text-slate-600 border-slate-300"
          >
            <LogOut className="w-4 h-4" />
            Logout
          </Button>
        </div>
      </nav>

      <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto w-full">
        <div className="mb-8 flex items-center gap-3">
          <Settings className="w-6 h-6 text-slate-600" />
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Admin Dashboard
          </h1>
        </div>

        <div aria-live="polite" className="space-y-3 mb-6">
          {status && (
            <p className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-800 shadow-sm">
              {status}
            </p>
          )}
          {errors.map((err) => (
            <div
              key={err.id}
              className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-800 shadow-sm flex justify-between items-start"
            >
              <span>{err.msg}</span>
              <button
                type="button"
                onClick={() => dismissError(err.id)}
                className="text-red-500 hover:text-red-700 font-bold ml-2 focus:outline-none"
                aria-label="Dismiss error"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>

        <div className="mt-4 grid gap-6 lg:grid-cols-2">
          {/* Projects and Create Project Column */}
          <div className="flex flex-col gap-6">
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col h-auto md:max-h-[600px]">
              <div className="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
                <Shield className="h-5 w-5 text-blue-500" />
                Projects
              </div>
              <div className="p-5 flex-1 overflow-auto min-h-[300px]">
                <div className="space-y-3">
                  {projects.map((proj) => (
                    <div
                      key={proj.id}
                      className="flex flex-col rounded-lg border border-slate-100 bg-slate-50 p-4 hover:border-slate-300 transition-colors"
                    >
                      {editingProjectId === proj.id ? (
                        <form
                          onSubmit={(event) => handleEditProject(event, proj)}
                          className="space-y-3"
                        >
                          <div>
                            <Label
                              htmlFor={`edit-project-name-${proj.id}`}
                              className="text-slate-700"
                            >
                              Project name
                            </Label>
                            <Input
                              id={`edit-project-name-${proj.id}`}
                              value={editProjectName}
                              onChange={(e) =>
                                setEditProjectName(e.target.value)
                              }
                              required
                              className="mt-1.5"
                            />
                          </div>
                          <div>
                            <Label
                              htmlFor={`edit-project-description-${proj.id}`}
                              className="text-slate-700"
                            >
                              Description
                            </Label>
                            <Textarea
                              id={`edit-project-description-${proj.id}`}
                              value={editProjectDescription}
                              onChange={(e) =>
                                setEditProjectDescription(e.target.value)
                              }
                              rows={2}
                              className="mt-1.5"
                            />
                          </div>
                          <div>
                            <Label
                              htmlFor={`edit-project-confluence-${proj.id}`}
                              className="text-slate-700"
                            >
                              Confluence Base URL
                            </Label>
                            <Input
                              id={`edit-project-confluence-${proj.id}`}
                              value={editProjectConfluenceBaseUrl}
                              onChange={(e) =>
                                setEditProjectConfluenceBaseUrl(e.target.value)
                              }
                              placeholder="https://confluence.company.com"
                              className="mt-1.5"
                            />
                          </div>
                          <div>
                            <Label
                              htmlFor={`edit-project-jira-${proj.id}`}
                              className="text-slate-700"
                            >
                              Jira Base URL
                            </Label>
                            <Input
                              id={`edit-project-jira-${proj.id}`}
                              value={editProjectJiraBaseUrl}
                              onChange={(e) =>
                                setEditProjectJiraBaseUrl(e.target.value)
                              }
                              placeholder="https://jira.company.com"
                              className="mt-1.5"
                            />
                            <p className="text-xs text-slate-400 mt-1">
                              At least one of Confluence or Jira URL is required.
                            </p>
                          </div>
                          <div>
                            <Label className="text-slate-700 block mb-1.5">
                              Enabled Providers
                            </Label>
                            <div className="flex flex-wrap gap-x-4 gap-y-2">
                              {PROVIDER_OPTIONS.map((opt) => (
                                <label
                                  key={opt.id}
                                  className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer"
                                >
                                  <input
                                    type="checkbox"
                                    checked={editEnabledProviders.includes(opt.id)}
                                    onChange={() =>
                                      toggleProvider(opt.id, editEnabledProviders, setEditEnabledProviders)
                                    }
                                    className="rounded border-slate-300 accent-blue-600"
                                  />
                                  {opt.label}
                                </label>
                              ))}
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <Button
                              type="submit"
                              size="sm"
                              disabled={isBusy}
                              className="h-7 text-xs"
                            >
                              Save
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={cancelEditingProject}
                              disabled={isBusy}
                              className="h-7 text-xs"
                            >
                              Cancel
                            </Button>
                          </div>
                        </form>
                      ) : (
                        <>
                          <div className="flex justify-between items-start mb-2">
                            <div className="font-semibold text-slate-900">
                              {proj.name}
                            </div>
                            <div className="flex gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => startEditingProject(proj)}
                                disabled={isBusy}
                                className="h-7 text-xs"
                                aria-label={`Edit ${proj.name}`}
                              >
                                Edit
                              </Button>
                              <Button
                                variant="destructive"
                                size="sm"
                                onClick={() => handleDeleteProject(proj)}
                                disabled={isBusy}
                                className="h-7 text-xs"
                                aria-label={`Delete ${proj.name}`}
                              >
                                Delete
                              </Button>
                            </div>
                          </div>
                          {proj.description && (
                            <div className="text-sm text-slate-600 mb-2">
                              {proj.description}
                            </div>
                          )}
                          {proj.confluence_base_url && (
                            <div className="text-xs text-slate-500 mb-1 break-all">
                              <a
                                href={proj.confluence_base_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-500 hover:underline"
                              >
                                {proj.confluence_base_url}
                              </a>
                            </div>
                          )}
                          {proj.jira_base_url && (
                            <div className="text-xs text-slate-500 mb-1 break-all">
                              <a
                                href={proj.jira_base_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-500 hover:underline"
                              >
                                {proj.jira_base_url}
                              </a>
                            </div>
                          )}
                          {proj.enabled_providers && proj.enabled_providers.length > 0 && (
                            <div className="flex items-center gap-1.5 mb-2">
                              {proj.enabled_providers.map((pid) =>
                                PROVIDER_ICON_FILES[pid] ? (
                                  <img
                                    key={pid}
                                    src={PROVIDER_ICON_FILES[pid]}
                                    alt={pid}
                                    title={
                                      PROVIDER_OPTIONS.find((p) => p.id === pid)?.label ?? pid
                                    }
                                    className="w-4 h-4 object-contain"
                                  />
                                ) : null,
                              )}
                            </div>
                          )}
                          <div className="text-xs text-slate-500">
                            {proj.memberships?.length || 0} member(s)
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                  {projects.length === 0 && (
                    <div className="text-sm text-slate-500 italic text-center py-4">
                      No projects found.
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Create Project moved to left column */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col flex-shrink-0">
              <div className="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
                <UserPlus className="h-5 w-5 text-blue-500" />
                Create Project
              </div>
              <div className="p-5">
                <form onSubmit={handleCreateProject} className="space-y-4">
                  <div>
                    <Label
                      htmlFor="admin-project-name"
                      className="text-slate-700"
                    >
                      Project name
                    </Label>
                    <Input
                      id="admin-project-name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                      minLength={1}
                      className="mt-1.5 focus-visible:ring-blue-500"
                    />
                  </div>
                  <div>
                    <Label
                      htmlFor="admin-project-description"
                      className="text-slate-700 block"
                    >
                      Description
                    </Label>
                    <Textarea
                      id="admin-project-description"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      className="mt-1.5 focus-visible:ring-blue-500"
                      rows={3}
                    />
                  </div>
                  <div>
                    <Label
                      htmlFor="admin-project-confluence"
                      className="text-slate-700 block"
                    >
                      Confluence Base URL
                    </Label>
                    <Input
                      id="admin-project-confluence"
                      value={confluenceBaseUrl}
                      onChange={(e) => setConfluenceBaseUrl(e.target.value)}
                      placeholder="https://confluence.company.com"
                      className="mt-1.5 focus-visible:ring-blue-500"
                    />
                  </div>
                  <div>
                    <Label
                      htmlFor="admin-project-jira"
                      className="text-slate-700 block"
                    >
                      Jira Base URL
                    </Label>
                    <Input
                      id="admin-project-jira"
                      value={jiraBaseUrl}
                      onChange={(e) => setJiraBaseUrl(e.target.value)}
                      placeholder="https://jira.company.com"
                      className="mt-1.5 focus-visible:ring-blue-500"
                    />
                    <p className="text-xs text-slate-400 mt-1">
                      At least one of Confluence or Jira URL is required.
                    </p>
                  </div>
                  <div>
                    <Label className="text-slate-700 block mb-1.5">
                      Enabled Providers
                    </Label>
                    <div className="flex flex-wrap gap-x-4 gap-y-2">
                      {PROVIDER_OPTIONS.map((opt) => (
                        <label
                          key={opt.id}
                          className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={enabledProviders.includes(opt.id)}
                            onChange={() =>
                              toggleProvider(opt.id, enabledProviders, setEnabledProviders)
                            }
                            className="rounded border-slate-300 accent-blue-600"
                          />
                          {opt.label}
                        </label>
                      ))}
                    </div>
                    <p className="text-xs text-slate-400 mt-1">
                      At least one provider must be enabled.
                    </p>
                  </div>
                  <Button
                    id="create-project-button"
                    type="submit"
                    disabled={isBusy}
                    className="w-full bg-blue-600 hover:bg-blue-700 text-white"
                  >
                    Create project
                  </Button>
                </form>
              </div>
            </div>
          </div>

          {/* Users and Assign Membership Column */}
          <div className="flex flex-col gap-6">
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col h-auto md:max-h-[600px]">
              <div className="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
                <Users className="h-5 w-5 text-blue-500" />
                Users Management
              </div>
              <div className="p-5 flex-1 overflow-auto min-h-[300px]">
                {isLoadingUsers ? (
                  <div className="flex justify-center items-center h-full text-slate-500 text-sm">
                    Loading users...
                  </div>
                ) : (
                  <ul className="space-y-3">
                    {users.map((u) => {
                      const isAdminUser = u.role === "admin";
                      const userProjects = u.project_memberships?.length
                        ? u.project_memberships.map((membership) => ({
                            id: membership.project_id,
                            name: membership.project_name,
                          }))
                        : projectsByUserId.get(u.id) || [];
                      const assignableProjects =
                        assignableProjectsByUserId.get(u.id) || [];
                      return (
                        <li
                          key={u.id}
                          className="rounded-lg border border-slate-100 bg-slate-50 p-4 hover:border-slate-300 transition-colors"
                        >
                          <div className="font-semibold text-slate-900">
                            {u.display_name}
                          </div>
                          <div className="text-sm text-slate-600 mb-2">
                            {u.email}
                          </div>
                          <div className="flex items-center gap-2 mt-1 mb-3">
                            <span
                              className={`inline-flex px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${isAdminUser ? "bg-purple-100 text-purple-700" : "bg-slate-200 text-slate-700"}`}
                            >
                              {u.role}
                            </span>
                            <span
                              className={`inline-flex px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${u.is_active ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}
                            >
                              {u.is_active ? "active" : "inactive"}
                            </span>
                          </div>
                          {!isAdminUser && (
                            <>
                              <div className="flex items-center justify-between mb-2">
                                <div className="text-xs text-slate-700 font-medium">
                                  Projects
                                </div>
                                <div className="flex items-center gap-2">
                                  <select
                                    value={selectedProjectByUserId[u.id] ?? ""}
                                    onChange={(e) =>
                                      setSelectedProjectByUserId((prev) => ({
                                        ...prev,
                                        [u.id]: e.target.value,
                                      }))
                                    }
                                    disabled={
                                      isBusy ||
                                      !u.is_active ||
                                      assignableProjects.length === 0
                                    }
                                    aria-label={`Select project for ${u.display_name}`}
                                    className="h-7 max-w-36 rounded-md border border-slate-300 bg-white px-2 text-xs disabled:cursor-not-allowed disabled:opacity-60"
                                  >
                                    <option value="">Select project...</option>
                                    {assignableProjects.map((project) => (
                                      <option
                                        key={project.id}
                                        value={project.id}
                                      >
                                        {project.name}
                                      </option>
                                    ))}
                                  </select>
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleAssignUserToProject(u)}
                                    disabled={
                                      isBusy ||
                                      !u.is_active ||
                                      assignableProjects.length === 0
                                    }
                                    className="h-7 w-7 p-0"
                                    aria-label={`Assign project to ${u.display_name}`}
                                  >
                                    <Plus className="h-3.5 w-3.5" />
                                  </Button>
                                </div>
                              </div>
                              {userProjects.length > 0 ? (
                                <div className="flex flex-wrap gap-1">
                                  {userProjects.map((up) => (
                                    <span
                                      key={up.id}
                                      className="inline-flex items-center gap-1 bg-white border border-slate-200 text-slate-600 px-2 py-1 rounded text-xs"
                                    >
                                      {up.name}
                                      <button
                                        type="button"
                                        onClick={() =>
                                          handleRemoveUserFromProject(up.id, u)
                                        }
                                        disabled={isBusy}
                                        className="text-red-500 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-50 font-bold ml-1"
                                        title="Remove user from project"
                                        aria-label={`Remove ${up.name} from ${u.display_name}`}
                                      >
                                        ×
                                      </button>
                                    </span>
                                  ))}
                                </div>
                              ) : (
                                <div className="text-xs text-slate-500 italic">
                                  No projects
                                </div>
                              )}
                            </>
                          )}
                        </li>
                      );
                    })}
                    {users.length === 0 && (
                      <li className="text-sm text-slate-500 italic text-center py-4">
                        No users found.
                      </li>
                    )}
                  </ul>
                )}
              </div>
            </div>

            {/* Create User replaces the old Manage Membership form */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col flex-shrink-0">
              <div className="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
                <UserPlus className="h-5 w-5 text-blue-500" />
                Create User
              </div>
              <div className="p-5">
                <form onSubmit={handleCreateUser} className="space-y-4">
                  <div>
                    <Label
                      htmlFor="create-user-email"
                      className="text-slate-700"
                    >
                      Email
                    </Label>
                    <Input
                      id="create-user-email"
                      type="email"
                      value={createUserEmail}
                      onChange={(e) => setCreateUserEmail(e.target.value)}
                      required
                      className="mt-1.5 focus-visible:ring-blue-500"
                    />
                  </div>
                  <div>
                    <Label
                      htmlFor="create-user-display-name"
                      className="text-slate-700 block"
                    >
                      Display Name
                    </Label>
                    <Input
                      id="create-user-display-name"
                      value={createUserDisplayName}
                      onChange={(e) => setCreateUserDisplayName(e.target.value)}
                      required
                      className="mt-1.5 focus-visible:ring-blue-500"
                    />
                  </div>
                  <div>
                    <Label
                      htmlFor="create-user-role"
                      className="text-slate-700 block"
                    >
                      Role
                    </Label>
                    <select
                      id="create-user-role"
                      aria-label="Role"
                      value={createUserRole}
                      onChange={(e) =>
                        setCreateUserRole(
                          e.target.value as "standard" | "admin",
                        )
                      }
                      className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      <option value="standard">Standard</option>
                      <option value="admin">Admin</option>
                    </select>
                  </div>
                  <div>
                    <Label
                      htmlFor="create-user-password"
                      className="text-slate-700 block"
                    >
                      Initial Password
                    </Label>
                    <Input
                      id="create-user-password"
                      type="password"
                      value={createUserPassword}
                      onChange={(e) => setCreateUserPassword(e.target.value)}
                      required
                      minLength={8}
                      className="mt-1.5 focus-visible:ring-blue-500"
                    />
                  </div>
                  <Button
                    id="create-user-button"
                    type="submit"
                    disabled={isBusy}
                    className="w-full bg-slate-800 hover:bg-slate-900 text-white mt-2"
                  >
                    Create user
                  </Button>
                  <div className="space-y-1">
                    <Button
                      type="button"
                      variant="outline"
                      disabled
                      aria-describedby="sync-users-help"
                      className="w-full"
                    >
                      Sync existing company's users
                    </Button>
                    <p id="sync-users-help" className="text-xs text-slate-500">
                      This feature is not available at the moment, please add
                      manually.
                    </p>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>

        {/* E2E Test Execution */}
        <div className="mt-6 rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
            <FlaskConical className="h-5 w-5 text-blue-500" />
            E2E Test Execution
          </div>
          <div className="p-5">
            <p className="text-sm text-slate-600 mb-4">
              Trigger a Playwright end-to-end test run in headed mode with slow
              motion so you can observe browser execution live.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                id="run-e2e-tests-button"
                type="button"
                onClick={handleRunE2ETests}
                disabled={isRunningE2E}
                title="Playwright will run locally on the server. Ensure Playwright is installed."
                className="bg-blue-600 hover:bg-blue-700 text-white flex items-center gap-2"
              >
                <FlaskConical className="w-4 h-4" />
                {isRunningE2E ? "Running E2E Tests…" : "Run E2E Tests"}
              </Button>
              {e2eResult?.report_available && (
                <>
                  <Button
                    id="view-e2e-report-button"
                    type="button"
                    variant="outline"
                    onClick={() => {
                      window.open(`${API_BASE_PATH}/admin/tests/e2e/report/view/index.html`, "_blank");
                    }}
                    className="flex items-center gap-2 text-indigo-700 border-indigo-200 hover:bg-indigo-50"
                  >
                    <FlaskConical className="w-4 h-4" />
                    View Report in Browser
                  </Button>
                  <Button
                    id="download-e2e-report-button"
                    type="button"
                    variant="outline"
                    onClick={handleDownloadReport}
                    disabled={isDownloadingReport}
                    className="flex items-center gap-2 text-slate-700"
                  >
                    <Download className="w-4 h-4" />
                    {isDownloadingReport ? "Downloading..." : "Download ZIP"}
                  </Button>
                </>
              )}
            </div>

            {isRunningE2E && (
              <div className="mt-4 flex items-center gap-2 text-sm text-slate-600 animate-pulse">
                <span className="inline-block w-2 h-2 rounded-full bg-blue-500"></span>
                Tests are running — Playwright browser is open with slow motion
                enabled.
              </div>
            )}

            {e2eResult && !isRunningE2E && (
              <div
                className="mt-4 rounded-lg border p-4 space-y-2 text-sm"
                data-testid="e2e-result"
              >
                <div className="flex items-center gap-2 font-semibold">
                  {e2eResult.passed ? (
                    <CheckCircle className="w-5 h-5 text-emerald-600" />
                  ) : (
                    <XCircle className="w-5 h-5 text-red-600" />
                  )}
                  <span
                    className={
                      e2eResult.passed ? "text-emerald-700" : "text-red-700"
                    }
                  >
                    {e2eResult.passed
                      ? "All tests passed"
                      : `Tests failed (exit code ${e2eResult.exit_code})`}
                  </span>
                </div>
                {e2eResult.stdout && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-slate-500 hover:text-slate-700">
                      Show output
                    </summary>
                    <pre className="mt-2 overflow-auto max-h-60 rounded bg-slate-100 p-3 text-xs text-slate-700 whitespace-pre-wrap">
                      {e2eResult.stdout}
                    </pre>
                  </details>
                )}
                {e2eResult.stderr && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-red-500 hover:text-red-700">
                      Show errors
                    </summary>
                    <pre className="mt-2 overflow-auto max-h-40 rounded bg-red-50 p-3 text-xs text-red-700 whitespace-pre-wrap">
                      {e2eResult.stderr}
                    </pre>
                  </details>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
