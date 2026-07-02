import { useEffect, useMemo, useState } from "react";
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
  Gauge,
  RefreshCw,
  ArrowLeft,
} from "lucide-react";
import { UserBadge } from "@/components/auth/UserBadge";
import { AppVersion } from "@/components/AppVersion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  createAdminProject,
  createAdminUser,
  deleteAdminProject,
  deleteAdminUser,
  listAdminUsers,
  updateAdminProject,
  updateAdminUser,
  runE2ETests,
  getE2EStatus,
  downloadE2EReport,
  listDiscoveredModels,
  syncModelsAndBenchmarks,
  getAdminConfig,
} from "@/lib/projects";
import { getSafeApiErrorMessage, API_BASE_PATH } from "@/lib/api";
import { BROWSER_TIMEZONE, TIMEZONE_OPTIONS } from "@/lib/timezone";
import { LANGUAGE_OPTIONS } from "@/lib/language";
import { useProject } from "@/hooks/useProject";
import { useAuth } from "@/hooks/useAuth";
import type {
  AdminUser,
  E2ETestRunResult,
  DiscoveredModel,
  ModelSyncResult,
  AdminConfig,
  ProjectEnvironment,
  UpdateAdminUserRequest,
} from "@/types/project";

/**
 * Editor for a project's named target environments (name + URL rows). Project-wide
 * and admin-managed: Sarah picks one when generating scripts; Jack (future) picks one
 * to run against. All optional — add/remove/edit rows freely; blanks are dropped on save.
 */
/** Trim rows and drop any with a blank name or URL before sending to the API. */
export function cleanEnvironments(envs: ProjectEnvironment[]): ProjectEnvironment[] {
  return envs
    .map((e) => ({
      name: e.name.trim(),
      url: e.url.trim(),
      login_type: e.login_type || "standard",
      login_hint: (e.login_hint || "").trim(),
    }))
    .filter((e) => e.name && e.url);
}

export function EnvironmentsEditor({
  environments,
  onChange,
}: {
  environments: ProjectEnvironment[];
  onChange: (envs: ProjectEnvironment[]) => void;
}) {
  const update = (index: number, patch: Partial<ProjectEnvironment>) =>
    onChange(environments.map((e, i) => (i === index ? { ...e, ...patch } : e)));
  const remove = (index: number) => onChange(environments.filter((_, i) => i !== index));
  const add = () => onChange([...environments, { name: "", url: "" }]);

  return (
    <div>
      <Label className="text-slate-700 block mb-1.5">Environments</Label>
      <div className="space-y-2">
        {environments.map((env, i) => (
          <div key={i} className="flex gap-2 items-start bg-slate-50 p-2 rounded border border-slate-100">
            <div className="flex-1 space-y-2">
              <div className="flex gap-2">
                <Input
                  aria-label={`Environment name ${i + 1}`}
                  placeholder="Name (e.g. Test 1)"
                  value={env.name}
                  onChange={(e) => update(i, { name: e.target.value })}
                  className="w-32"
                />
                <Input
                  aria-label={`Environment URL ${i + 1}`}
                  placeholder="https://test1.example.com"
                  value={env.url}
                  onChange={(e) => update(i, { url: e.target.value })}
                  className="flex-1"
                />
              </div>
              <div className="flex gap-2 items-center">
                <Label className="text-xs text-slate-500 whitespace-nowrap w-20">Login Type:</Label>
                <select
                  value={env.login_type || "standard"}
                  onChange={(e) => update(i, { login_type: e.target.value })}
                  className="h-8 w-40 rounded-md border border-input bg-background px-3 py-1 text-xs shadow-sm"
                >
                  <option value="standard">Standard Form</option>
                  <option value="sso_microsoft">SSO (Internal)</option>
                  <option value="sso_google">SSO (Google)</option>
                  <option value="sso_apple">SSO (Apple)</option>
                  <option value="sso_generic">SSO (Generic)</option>
                  <option value="custom">Custom Auth</option>
                </select>
                {(env.login_type && env.login_type !== "standard") && (
                  <Input
                    placeholder="Login Hint (e.g. Button Text)"
                    value={env.login_hint || ""}
                    onChange={(e) => update(i, { login_hint: e.target.value })}
                    className="h-8 flex-1 text-xs"
                  />
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => remove(i)}
              aria-label={`Remove environment ${i + 1}`}
              className="text-red-500 hover:text-red-700 p-1 flex-shrink-0 mt-1"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={add}
        className="mt-2 h-7 text-xs"
      >
        <Plus className="h-3.5 w-3.5 mr-1" /> Add environment
      </Button>
      <p className="text-xs text-slate-400 mt-1">
        App-under-test URLs (local, test, integrate, production…). Optional — add or edit
        anytime.
      </p>
    </div>
  );
}

/**
 * Editor for a project's app-under-test roles (Admin/User/…). Chip-style: type a name,
 * Add, remove with ×. These roles (× environments) are the matrix each captured login
 * session is keyed by. Distinct from pipeline-access roles (ProjectMembership.role).
 */
export function AppRolesEditor({
  roles,
  onChange,
}: {
  roles: string[];
  onChange: (roles: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const value = draft.trim();
    if (!value) return;
    if (!roles.some((r) => r.toLowerCase() === value.toLowerCase())) {
      onChange([...roles, value]);
    }
    setDraft("");
  };
  const remove = (index: number) => onChange(roles.filter((_, i) => i !== index));

  return (
    <div>
      <Label className="text-slate-700 block mb-1.5">App roles</Label>
      <div className="flex gap-2">
        <Input
          aria-label="New app role"
          placeholder="e.g. Admin"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          className="flex-1"
        />
        <Button type="button" variant="outline" size="sm" onClick={add} className="h-9 text-xs">
          <Plus className="h-3.5 w-3.5 mr-1" /> Add
        </Button>
      </div>
      {roles.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {roles.map((r, i) => (
            <span
              key={r}
              className="inline-flex items-center gap-1 bg-slate-100 border border-slate-200 text-slate-700 px-2 py-1 rounded text-xs"
            >
              {r}
              <button
                type="button"
                onClick={() => remove(i)}
                aria-label={`Remove role ${r}`}
                className="text-red-500 hover:text-red-700 font-bold ml-1"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <p className="text-xs text-slate-400 mt-1">
        Roles of the app under test (Admin, User…). Optional — each role gets its own
        captured login session later.
      </p>
    </div>
  );
}

// Users Management sort order: platform admin first, then project_admins, then
// standard users, then anything else.
const ROLE_RANK: Record<string, number> = {
  admin: 0,
  project_admin: 1,
  standard: 2,
};

// Synced-models table: rows sort by these capability scores in priority order
// (highest first); chips within a row render in this fixed order for easy column scan.
const SCORE_SORT_ORDER = ["global", "reasoning", "instruction", "coding", "vision", "fast"] as const;

const PROVIDER_LABELS: Record<string, string> = {
  "on-premises": "on premises",
  claude: "claude",
  gemini: "gemini",
  openai: "openAI",
  "browser-use-cloud": "browser use",
};
const getProviderLabel = (provider: string | null) => {
  if (!provider) return "Unknown";
  return PROVIDER_LABELS[provider] || provider;
};

/** How often to poll the E2E run status while a background run is in progress. */
const E2E_POLL_INTERVAL_MS = 3000;
/** Stop polling after this long so the UI can never hang forever on a stuck run. */
const E2E_MAX_POLL_MS = 20 * 60 * 1000;
/** Tolerate this many consecutive poll failures (transient network blips) before giving up. */
const E2E_MAX_POLL_ERRORS = 5;

export function AdminDashboard({
  onBackToWorkspace,
  onNavigateToProjectAdmin,
}: {
  onBackToWorkspace?: () => void;
  onNavigateToProjectAdmin?: () => void;
} = {}) {
  const { projects, reloadProjects } = useProject();
  const { user, logout } = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(true);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  // Project CONFIG (Confluence/Jira/providers/environments/app_roles) and membership are
  // managed by the project_admin in the Project Admin dashboard — the platform admin only
  // creates/edits a project's name + description here.
  const [createUserEmail, setCreateUserEmail] = useState("");
  const [createUserDisplayName, setCreateUserDisplayName] = useState("");
  const [createUserRole, setCreateUserRole] = useState<"standard" | "project_admin">(
    "standard",
  );
  const [createUserTimezone, setCreateUserTimezone] =
    useState<string>(BROWSER_TIMEZONE);
  const [createUserConversationLanguage, setCreateUserConversationLanguage] = useState("en");
  // Selected project for a new project_admin (required when role is project_admin).
  const [createUserProjectId, setCreateUserProjectId] = useState<string>("");
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editProjectName, setEditProjectName] = useState("");
  const [editProjectDescription, setEditProjectDescription] = useState("");
  // Per-user inline edit (project_admin / standard only — the admin row is immutable).
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [editUserDisplayName, setEditUserDisplayName] = useState("");
  const [editUserRole, setEditUserRole] = useState<"standard" | "project_admin">(
    "standard",
  );
  const [editUserTimezone, setEditUserTimezone] =
    useState<string>(BROWSER_TIMEZONE);
  const [editUserConversationLanguage, setEditUserConversationLanguage] = useState("en");
  const [editUserIsActive, setEditUserIsActive] = useState(true);
  // Epic 23 (23.5): the full administered-project set for a project_admin (multi-select).
  // Pre-filled from the user's current project_admin memberships when editing begins.
  const [editUserProjectIds, setEditUserProjectIds] = useState<string[]>([]);
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

  // Sorted view of the users list (never mutate state): role → status → timezone → name.
  const sortedUsers = useMemo(
    () =>
      [...users].sort((a, b) => {
        const ra = ROLE_RANK[a.role] ?? 3;
        const rb = ROLE_RANK[b.role] ?? 3;
        if (ra !== rb) return ra - rb;
        const aActive = a.is_active ? 0 : 1;
        const bActive = b.is_active ? 0 : 1;
        if (aActive !== bActive) return aActive - bActive;
        const tz = (a.timezone ?? "").localeCompare(b.timezone ?? "");
        if (tz !== 0) return tz;
        return a.display_name.localeCompare(b.display_name);
      }),
    [users],
  );

  // --- Model & benchmark sync ---
  const [discoveredModels, setDiscoveredModels] = useState<DiscoveredModel[]>(
    [],
  );
  const [isLoadingModels, setIsLoadingModels] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<ModelSyncResult | null>(null);
  const [adminConfig, setAdminConfig] = useState<AdminConfig | null>(null);

  const [selectedProvider, setSelectedProvider] = useState<string | "all">("all");
  const [sortCapability, setSortCapability] = useState<string | null>(null);

  // Sort by selected capability, fallback to global → reasoning → coding → vision (desc); models without a given
  // score sink (treated as -1), so benchmarked models float to the top.
  const sortedModels = useMemo(() => {
    let filtered = discoveredModels;
    if (selectedProvider !== "all") {
      filtered = filtered.filter((m) => getProviderLabel(m.provider) === selectedProvider);
    }
    const scoreFor = (m: DiscoveredModel, capability: string): number => {
      const found = m.scores.find((s) => s.capability === capability);
      return found ? found.score : -1;
    };
    return [...filtered].sort((a, b) => {
      if (sortCapability) {
        const diff = scoreFor(b, sortCapability) - scoreFor(a, sortCapability);
        if (diff !== 0) return diff;
      }
      for (const capability of SCORE_SORT_ORDER) {
        const diff = scoreFor(b, capability) - scoreFor(a, capability);
        if (diff !== 0) return diff;
      }
      return a.model_id.localeCompare(b.model_id);
    });
  }, [discoveredModels, selectedProvider, sortCapability]);

  const loadDiscoveredModels = async () => {
    try {
      const models = await listDiscoveredModels();
      setDiscoveredModels(models || []);
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    }
  };

  useEffect(() => {
    setIsLoadingModels(true);
    Promise.all([
      loadDiscoveredModels(),
      getAdminConfig().then(setAdminConfig).catch(console.error),
    ]).finally(() => setIsLoadingModels(false));
  }, []);

  const handleSyncModels = async () => {
    setIsSyncing(true);
    setSyncResult(null);
    setErrors([]);
    setStatus(null);
    try {
      const result = await syncModelsAndBenchmarks();
      setSyncResult(result);
      setStatus(
        `Synced ${result.models_discovered} model(s); ${result.models_benchmarked} benchmarked.`,
      );
      await loadDiscoveredModels();
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsSyncing(false);
    }
  };

  async function handleCreateProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      addError("Project name is required.");
      return;
    }

    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await createAdminProject({
        name: trimmedName,
        description: description.trim() || null,
      });
      setName("");
      setDescription("");
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
        display_name: createUserDisplayName.trim() || undefined,
        role: createUserRole,
        timezone: createUserTimezone,
        conversation_language: createUserConversationLanguage,
        ...(createUserRole === "project_admin"
          ? { project_id: createUserProjectId }
          : {}),
      });
      setCreateUserEmail("");
      setCreateUserDisplayName("");
      setCreateUserRole("standard");
      setCreateUserTimezone(BROWSER_TIMEZONE);
      setCreateUserConversationLanguage("en");
      setCreateUserProjectId("");
      setStatus("User synced successfully.");
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
  }

  function cancelEditingProject() {
    setEditingProjectId(null);
    setEditProjectName("");
    setEditProjectDescription("");
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
    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await updateAdminProject(project.id, {
        name: trimmedName,
        description: editProjectDescription.trim() || null,
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

  function startEditingUser(u: AdminUser) {
    setEditingUserId(u.id);
    setEditUserDisplayName(u.display_name);
    setEditUserRole(u.role === "project_admin" ? "project_admin" : "standard");
    setEditUserTimezone(u.timezone || BROWSER_TIMEZONE);
    setEditUserConversationLanguage(u.conversation_language || "en");
    setEditUserIsActive(u.is_active);
    // Pre-check the projects this user already administers (project_admin memberships).
    setEditUserProjectIds(
      u.project_memberships
        .filter((m) => m.role === "project_admin")
        .map((m) => m.project_id),
    );
  }

  function cancelEditingUser() {
    setEditingUserId(null);
    setEditUserDisplayName("");
    setEditUserProjectIds([]);
  }

  async function handleEditUser(
    event: React.FormEvent<HTMLFormElement>,
    u: AdminUser,
  ) {
    event.preventDefault();
    const trimmedName = editUserDisplayName.trim();
    if (!trimmedName) {
      addError("Display name is required.");
      return;
    }
    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      const isProjectAdmin = editUserRole === "project_admin";
      const body: UpdateAdminUserRequest = {
        display_name: trimmedName,
        role: editUserRole,
        timezone: editUserTimezone,
        conversation_language: editUserConversationLanguage,
        is_active: editUserIsActive,
        // Send the full administered-project set whenever the user is a project_admin
        // (covers both promotion and editing an existing project_admin — fixes 16-13).
        ...(isProjectAdmin ? { project_ids: editUserProjectIds } : {}),
      };
      await updateAdminUser(u.id, body);
      cancelEditingUser();
      setStatus("User updated successfully.");
      await loadUsers();
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDeleteUser(u: AdminUser) {
    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await deleteAdminUser(u.id);
      setStatus("User deleted successfully.");
      await loadUsers();
    } catch (err) {
      addError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRunE2ETests() {
    if (isRunningE2E) return; // defense-in-depth beyond the disabled button
    setIsRunningE2E(true);
    setE2eResult(null);
    setErrors([]);
    setStatus(null);
    try {
      // The run executes in the background on the server (a full suite takes
      // minutes). Kick it off, then poll the status endpoint until it finishes —
      // this keeps every request short, so no reverse proxy times it out.
      let result = await runE2ETests();
      const startedAt = Date.now();
      let consecutiveErrors = 0;
      while (result.status === "running") {
        if (Date.now() - startedAt > E2E_MAX_POLL_MS) {
          throw new Error(
            "Timed out waiting for the E2E run. Check the report or the server logs.",
          );
        }
        try {
          result = await getE2EStatus();
          consecutiveErrors = 0;
        } catch (pollErr) {
          // Tolerate transient blips; only fail after several in a row.
          consecutiveErrors += 1;
          if (consecutiveErrors >= E2E_MAX_POLL_ERRORS) throw pollErr;
        }
        if (result.status === "running") {
          await new Promise((resolve) => setTimeout(resolve, E2E_POLL_INTERVAL_MS));
        }
      }
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
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center hover:opacity-80 transition-opacity focus:outline-none"
              title="User menu"
            >
              <UserBadge user={user} roleClassName="text-blue-600" displayRole="Admin" />
            </button>

            {userMenuOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setUserMenuOpen(false)}
                />
                <div className="absolute right-0 mt-2 w-56 bg-white rounded-md shadow-lg py-1 border border-slate-200 z-50">
                  {onNavigateToProjectAdmin && (
                    <button
                      onClick={() => {
                        onNavigateToProjectAdmin();
                        setUserMenuOpen(false);
                      }}
                      className="flex w-full items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100"
                    >
                      <Settings className="w-4 h-4" />
                      Project Admin Dashboard
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
                    {sortedUsers.map((u) => {
                      const isAdminUser = u.role === "admin";
                      const adminProjects = u.project_memberships
                        .filter((m) => m.role === "project_admin")
                        .map((m) => m.project_name);
                      return (
                        <li
                          key={u.id}
                          className="rounded-lg border border-slate-100 bg-slate-50 p-4 hover:border-slate-300 transition-colors"
                        >
                          {editingUserId === u.id ? (
                            <form
                              onSubmit={(event) => handleEditUser(event, u)}
                              className="space-y-3"
                            >
                              <div>
                                <Label
                                  htmlFor={`edit-user-name-${u.id}`}
                                  className="text-slate-700"
                                >
                                  Display Name
                                </Label>
                                <Input
                                  id={`edit-user-name-${u.id}`}
                                  value={editUserDisplayName}
                                  onChange={(e) =>
                                    setEditUserDisplayName(e.target.value)
                                  }
                                  required
                                  className="mt-1.5"
                                />
                              </div>
                              {!isAdminUser && (
                                <div>
                                  <Label
                                    htmlFor={`edit-user-role-${u.id}`}
                                    className="text-slate-700 block"
                                  >
                                    Role
                                  </Label>
                                  <select
                                    id={`edit-user-role-${u.id}`}
                                    aria-label={`Role for ${u.display_name}`}
                                    value={editUserRole}
                                    onChange={(e) => {
                                      const nextRole = e.target.value as
                                        | "standard"
                                        | "project_admin";
                                      setEditUserRole(nextRole);
                                      // Demoting to standard clears the administered set.
                                      if (nextRole === "standard")
                                        setEditUserProjectIds([]);
                                    }}
                                    className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                                  >
                                    <option value="standard">Standard</option>
                                    <option value="project_admin">
                                      Project Admin
                                    </option>
                                  </select>
                                </div>
                              )}
                              {editUserRole === "project_admin" && (
                                <div>
                                  <Label className="text-slate-700 block">
                                    Administered projects
                                  </Label>
                                  <div
                                    role="group"
                                    aria-label={`Administered projects for ${u.display_name}`}
                                    className="mt-1.5 space-y-1.5 rounded-md border border-slate-300 bg-white p-2 max-h-44 overflow-y-auto"
                                  >
                                    {projects.map((proj) => {
                                      const checked = editUserProjectIds.includes(
                                        proj.id,
                                      );
                                      return (
                                        <label
                                          key={proj.id}
                                          className="flex items-center gap-2 text-sm text-slate-700"
                                        >
                                          <input
                                            type="checkbox"
                                            checked={checked}
                                            aria-label={proj.name}
                                            onChange={(e) =>
                                              setEditUserProjectIds((prev) =>
                                                e.target.checked
                                                  ? [...prev, proj.id]
                                                  : prev.filter(
                                                      (id) => id !== proj.id,
                                                    ),
                                              )
                                            }
                                          />
                                          {proj.name}
                                        </label>
                                      );
                                    })}
                                  </div>
                                  {projects.length === 0 && (
                                    <p className="text-xs text-amber-600 mt-1">
                                      Create a project first before assigning a
                                      project admin.
                                    </p>
                                  )}
                                  {projects.length > 0 &&
                                    editUserProjectIds.length === 0 && (
                                      <p className="text-xs text-amber-600 mt-1">
                                        Select at least one project, or set the role
                                        to Standard.
                                      </p>
                                    )}
                                </div>
                              )}
                              <div>
                                <Label
                                  htmlFor={`edit-user-timezone-${u.id}`}
                                  className="text-slate-700 block"
                                >
                                  Timezone
                                </Label>
                                <select
                                  id={`edit-user-timezone-${u.id}`}
                                  aria-label={`Timezone for ${u.display_name}`}
                                  value={editUserTimezone}
                                  onChange={(e) =>
                                    setEditUserTimezone(e.target.value)
                                  }
                                  className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                                >
                                  {TIMEZONE_OPTIONS.map((tz) => (
                                    <option key={tz} value={tz}>
                                      {tz}
                                    </option>
                                  ))}
                                </select>
                              </div>
                              <div>
                                <Label
                                  htmlFor={`edit-user-language-${u.id}`}
                                  className="text-slate-700 block"
                                >
                                  Language
                                </Label>
                                <select
                                  id={`edit-user-language-${u.id}`}
                                  aria-label={`Language for ${u.display_name}`}
                                  value={editUserConversationLanguage}
                                  onChange={(e) =>
                                    setEditUserConversationLanguage(e.target.value)
                                  }
                                  className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                                >
                                  {LANGUAGE_OPTIONS.map((lang) => (
                                    <option key={lang.value} value={lang.value}>
                                      {lang.label}
                                    </option>
                                  ))}
                                </select>
                              </div>
                              {!isAdminUser && (
                                <label className="flex items-center gap-2 text-sm text-slate-700">
                                  <input
                                    type="checkbox"
                                    checked={editUserIsActive}
                                    onChange={(e) =>
                                      setEditUserIsActive(e.target.checked)
                                    }
                                    aria-label={`Active for ${u.display_name}`}
                                  />
                                  Active
                                </label>
                              )}
                              <div className="flex gap-2">
                                <Button
                                  type="submit"
                                  size="sm"
                                  disabled={
                                    isBusy ||
                                    (editUserRole === "project_admin" &&
                                      (projects.length === 0 ||
                                        editUserProjectIds.length === 0))
                                  }
                                  className="h-7 text-xs"
                                >
                                  Save
                                </Button>
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  onClick={cancelEditingUser}
                                  disabled={isBusy}
                                  className="h-7 text-xs"
                                >
                                  Cancel
                                </Button>
                              </div>
                            </form>
                          ) : (
                            <>
                              <div className="flex justify-between items-start">
                                <div className="font-semibold text-slate-900">
                                  {u.display_name}
                                </div>
                                <div className="flex gap-2">
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => startEditingUser(u)}
                                    disabled={isBusy}
                                    className="h-7 text-xs"
                                    aria-label={`Edit user ${u.display_name}`}
                                  >
                                    Edit
                                  </Button>
                                  {!isAdminUser && (
                                    <Button
                                      variant="destructive"
                                      size="sm"
                                      onClick={() => handleDeleteUser(u)}
                                      disabled={isBusy}
                                      className="h-7 text-xs"
                                      aria-label={`Delete user ${u.display_name}`}
                                    >
                                      Delete
                                    </Button>
                                  )}
                                </div>
                              </div>
                              <div className="text-sm text-slate-600 mb-2">
                                {u.email}
                              </div>
                              <div className="flex items-center gap-2 mt-1 mb-3 flex-wrap">
                                <span
                                  className={`inline-flex px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${isAdminUser ? "bg-purple-100 text-purple-700" : "bg-slate-200 text-slate-700"}`}
                                >
                                  {u.role}
                                </span>
                                <span
                                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${u.is_active ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}
                                >
                                  {u.is_active ? (
                                    <CheckCircle className="h-3 w-3" />
                                  ) : (
                                    <XCircle className="h-3 w-3" />
                                  )}
                                  {u.is_active ? "Active" : "Inactive"}
                                </span>
                                {u.timezone && (
                                  <span
                                    className="inline-flex px-2 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-700"
                                    title="User's timezone (message times localized to this)"
                                  >
                                    {u.timezone}
                                  </span>
                                )}
                                {u.conversation_language && (
                                  <span
                                    className="inline-flex px-2 py-0.5 rounded text-[10px] font-medium bg-indigo-50 text-indigo-700"
                                    title="User's preferred conversation language"
                                  >
                                    {LANGUAGE_OPTIONS.find(l => l.value === u.conversation_language)?.label || u.conversation_language}
                                  </span>
                                )}
                                {adminProjects.length > 0 && (
                                  <span className="text-[11px] text-slate-500">
                                    Admin of: {adminProjects.join(", ")}
                                  </span>
                                )}
                              </div>
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

            {/* Sync User form */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col flex-shrink-0">
              <div className="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
                <UserPlus className="h-5 w-5 text-blue-500" />
                Sync User
              </div>
              <div className="p-5">
                <form onSubmit={handleCreateUser} className="space-y-4">
                  <div>
                    <Label
                      htmlFor="create-user-display-name"
                      className="text-slate-700"
                    >
                      Name (Optional)
                    </Label>
                    <Input
                      id="create-user-display-name"
                      type="text"
                      value={createUserDisplayName}
                      onChange={(e) => setCreateUserDisplayName(e.target.value)}
                      className="mt-1.5 focus-visible:ring-blue-500"
                    />
                  </div>
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
                      htmlFor="create-user-role"
                      className="text-slate-700 block"
                    >
                      Role
                    </Label>
                    <select
                      id="create-user-role"
                      aria-label="Role"
                      value={createUserRole}
                      onChange={(e) => {
                        const nextRole = e.target.value as
                          | "standard"
                          | "project_admin";
                        setCreateUserRole(nextRole);
                        if (nextRole !== "project_admin")
                          setCreateUserProjectId("");
                      }}
                      className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      <option value="standard">Standard</option>
                      <option value="project_admin">Project Admin</option>
                    </select>
                  </div>
                  {createUserRole === "project_admin" && (
                    <div>
                      <Label
                        htmlFor="create-user-project"
                        className="text-slate-700 block"
                      >
                        Project
                      </Label>
                      <select
                        id="create-user-project"
                        aria-label="Project"
                        value={createUserProjectId}
                        onChange={(e) => setCreateUserProjectId(e.target.value)}
                        disabled={projects.length === 0}
                        className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:bg-slate-100"
                      >
                        <option value="">Select a project…</option>
                        {projects.map((proj) => (
                          <option key={proj.id} value={proj.id}>
                            {proj.name}
                          </option>
                        ))}
                      </select>
                      {projects.length === 0 && (
                        <p className="text-xs text-amber-600 mt-1">
                          Create a project first before adding a project admin.
                        </p>
                      )}
                    </div>
                  )}
                  <div>
                    <Label
                      htmlFor="create-user-timezone"
                      className="text-slate-700 block"
                    >
                      Timezone
                    </Label>
                    <select
                      id="create-user-timezone"
                      aria-label="Timezone"
                      value={createUserTimezone}
                      onChange={(e) => setCreateUserTimezone(e.target.value)}
                      className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      {TIMEZONE_OPTIONS.map((tz) => (
                        <option key={tz} value={tz}>
                          {tz}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-slate-500 mt-1">
                      Message times are shown to this user in this timezone.
                    </p>
                  </div>
                  <div>
                    <Label
                      htmlFor="create-user-language"
                      className="text-slate-700 block"
                    >
                      Language
                    </Label>
                    <select
                      id="create-user-language"
                      aria-label="Language"
                      value={createUserConversationLanguage}
                      onChange={(e) => setCreateUserConversationLanguage(e.target.value)}
                      className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      {LANGUAGE_OPTIONS.map((lang) => (
                        <option key={lang.value} value={lang.value}>
                          {lang.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button
                    id="create-user-button"
                    type="submit"
                    disabled={
                      isBusy ||
                      (createUserRole === "project_admin" &&
                        (projects.length === 0 || createUserProjectId === ""))
                    }
                  >
                    Sync user
                  </Button>
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
              Trigger a Playwright end-to-end test run on the server. It runs in
              the background and can take a few minutes; the result and report
              appear here when it finishes.
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
                Tests are running on the server — this can take a few minutes.
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

        {/* Model Benchmark Overrides — operator Tier-0 scores for Alice selection */}
        <div className="mt-6 rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
            <Gauge className="h-5 w-5 text-slate-500" />
            <h2 className="text-lg font-semibold text-slate-800">
              Models &amp; Benchmarks
            </h2>
          </div>
          <div className="p-5">
            <p className="mb-4 text-sm text-slate-500">
              Connect to every configured provider, discover their LLM models
              (skipping embedding / speech models), detect vision support, and pull
              fresh benchmark scores for all six capabilities from llm-stats.com — in
              one click. Scores are overwritten on each sync and feed
              Alice&apos;s model selection.
            </p>

            {adminConfig?.enable_model_benchmark_sync && (
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <Button
                  id="sync-models-button"
                  type="button"
                  onClick={handleSyncModels}
                  disabled={isSyncing}
                  className="bg-blue-600 hover:bg-blue-700 text-white flex items-center gap-2"
                >
                  <RefreshCw
                    className={`w-4 h-4 ${isSyncing ? "animate-spin" : ""}`}
                  />
                  {isSyncing
                    ? "Syncing models & benchmarks…"
                    : "Sync models and benchmarks"}
                </Button>
              </div>
            )}

            {isSyncing && (
              <div className="mb-4 flex items-center gap-2 text-sm text-slate-600 animate-pulse">
                <span className="inline-block w-2 h-2 rounded-full bg-blue-500"></span>
                Connecting to providers and fetching benchmark scores…
              </div>
            )}

            {syncResult && !isSyncing && (
              <div
                className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm"
                data-testid="model-sync-result"
              >
                <div className="mb-2 font-medium text-slate-700">
                  Discovered {syncResult.models_discovered} model(s) —{" "}
                  {syncResult.models_benchmarked} benchmarked,{" "}
                  {syncResult.models_unbenchmarked} without scores.
                </div>
                <ul className="space-y-1 text-xs">
                  {syncResult.providers.map((p) => (
                    <li key={p.provider_id} className="flex items-center gap-2">
                      {p.connected ? (
                        <CheckCircle className="h-3.5 w-3.5 text-emerald-600" />
                      ) : (
                        <XCircle
                          className={`h-3.5 w-3.5 ${
                            p.skipped ? "text-slate-400" : "text-red-500"
                          }`}
                        />
                      )}
                      <span className="font-mono text-slate-700">
                        {p.provider_id}
                      </span>
                      <span className="text-slate-500">
                        {p.connected
                          ? `${p.models_found} model(s)`
                          : p.skipped
                            ? "skipped"
                            : "failed"}
                        {p.error ? ` — ${p.error}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
                {!syncResult.benchmark_source_available && (
                  <p className="mt-2 text-xs text-amber-600">
                    Benchmark source unavailable — models discovered but not
                    scored.
                  </p>
                )}
                {syncResult.warnings.length > 0 && (
                  <ul className="mt-2 list-disc pl-5 text-xs text-amber-600">
                    {syncResult.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {isLoadingModels ? (
              <p className="text-sm text-slate-400">Loading models…</p>
            ) : discoveredModels.length === 0 ? (
              <p className="text-sm text-slate-400">
                No models discovered yet — click “Sync models and benchmarks”
                above.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <div className="mb-4 flex items-center space-x-2">
                  <Label className="text-sm font-medium text-slate-700">Filter Provider:</Label>
                  <select
                    value={selectedProvider}
                    onChange={(e) => setSelectedProvider(e.target.value)}
                    className="h-8 rounded-md border border-slate-300 bg-white px-3 py-1 text-sm text-slate-700 shadow-sm"
                  >
                    <option value="all">All</option>
                    <option value="on premises">on premises</option>
                    <option value="claude">claude</option>
                    <option value="gemini">gemini</option>
                    <option value="openAI">openAI</option>
                    <option value="browser use">browser use</option>
                  </select>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                      <th className="py-2 pr-3">Model</th>
                      <th className="py-2 pr-3">Provider</th>
                      <th className="py-2 pr-3">Source</th>
                      {SCORE_SORT_ORDER.map((cap) => (
                        <th
                          key={cap}
                          className="py-2 pr-3 cursor-pointer hover:text-slate-600 select-none"
                          onClick={() => setSortCapability(sortCapability === cap ? null : cap)}
                        >
                          {cap} {sortCapability === cap && "↓"}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedModels.map((m) => (
                      <tr
                        key={m.model_id}
                        className="border-b border-slate-100 align-top"
                      >
                        <td className="py-3 pr-3">
                          <div className="font-mono text-xs text-slate-800">
                            {m.model_id}
                          </div>
                          {m.scores.some((s) => s.capability === "vision") && (
                            <span className="text-[10px] text-emerald-600">
                              vision
                            </span>
                          )}
                        </td>
                        <td className="py-3 pr-3">
                          <span className="text-xs text-slate-600">
                            {getProviderLabel(m.provider)}
                          </span>
                        </td>
                        <td className="py-3 pr-3">
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] ${
                              m.tier_source === "admin"
                                ? "bg-purple-100 text-purple-700"
                                : m.tier_source === "curated"
                                  ? "bg-emerald-100 text-emerald-700"
                                  : "bg-amber-100 text-amber-700"
                            }`}
                          >
                            {m.tier_source === "admin" ? "synced" : m.tier_source}
                          </span>
                          {m.unbenchmarked && (
                            <span className="ml-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] text-amber-600">
                              No benchmark
                            </span>
                          )}
                        </td>
                        {SCORE_SORT_ORDER.map((cap) => {
                          const s = m.scores.find((score) => score.capability === cap);
                          return (
                            <td key={cap} className="py-3 pr-3">
                              {s ? (
                                <span className="text-xs text-slate-600">
                                  <b>{s.score}</b>
                                </span>
                              ) : (
                                <span className="text-xs text-slate-400">—</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
