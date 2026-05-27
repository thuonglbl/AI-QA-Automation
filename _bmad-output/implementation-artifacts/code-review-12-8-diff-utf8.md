diff --git a/README.md b/README.md
index ff466fa..f567e11 100644
--- a/README.md
+++ b/README.md
@@ -187,6 +187,7 @@ OpenAPI documentation is available at:
 - Node.js 20+ (OK with 26.1.0)
 - Docker (prefer Rancher Desktop 1.22.2)
 - `uv` (OK with 0.11.13)
+- PostgreSQL 18 with pgAdmin 4 (latest 9.15)
 
 ### Database Setup
 
diff --git a/_bmad-output/implementation-artifacts/sprint-status.yaml b/_bmad-output/implementation-artifacts/sprint-status.yaml
index 6beea89..7c8dbe4 100644
--- a/_bmad-output/implementation-artifacts/sprint-status.yaml
+++ b/_bmad-output/implementation-artifacts/sprint-status.yaml
@@ -89,6 +89,7 @@ development_status:
   12-5-project-scoped-artifact-service: done
   12-6-frontend-login-project-selection-and-api-client-foundation: done
   12-7-refactor-existing-pipeline-from-workspace-paths-to-project-context: done
+  12-8-bugfix-admin-routing-and-dashboard: review
   epic-12-retrospective: done
   epic-6: backlog
   6-1-script-runner-pipeline-stage: backlog
diff --git a/_bmad-output/planning-artifacts/epics.md b/_bmad-output/planning-artifacts/epics.md
index 52ab5d2..936c49a 100644
--- a/_bmad-output/planning-artifacts/epics.md
+++ b/_bmad-output/planning-artifacts/epics.md
@@ -776,6 +776,25 @@ So that multi-user project collaboration works without breaking the current agen
 **And** legacy `workspace/` assumptions are isolated behind compatibility adapters or removed where safe
 **And** existing completed functionality from Epics 3ΓÇô5 remains operational after the refactor
 
+### Story 12.8: Bugfix - Admin Routing and Dashboard Enhancements
+
+As an admin,
+I want to be routed directly to an administrative dashboard when logging in,
+So that I can bypass project selection and manage users and projects effectively.
+
+**Acceptance Criteria:**
+
+**Given** an authenticated user with the 'admin' role logs in
+**When** the frontend routes the user
+**Then** the admin bypasses the Project Picker and goes straight to the Admin Dashboard
+**Given** the admin is on the Admin Dashboard
+**When** they view the interface
+**Then** there is a functional "Logout" button
+**And** the admin's email, display name, and role are displayed next to the "Logout" button
+**And** there is a vertical list on the left showing projects with create, edit name, and delete buttons
+**And** there is a vertical list on the right showing users and the projects they belong to
+**And** there are buttons to assign projects to members and remove users from projects
+
 ## Epic 6: Test Execution & Reporting (Agent Jack)
 
 Jack runs test scripts across Chrome/Firefox/Edge, generates execution reports with pass/fail per test per browser. Pipeline completes end-to-end. User sees final results.
diff --git a/frontend/src/App.test.tsx b/frontend/src/App.test.tsx
index ecc9454..cfd73d6 100644
--- a/frontend/src/App.test.tsx
+++ b/frontend/src/App.test.tsx
@@ -32,7 +32,7 @@ function renderApp() {
 
 describe("App auth and project gates", () => {
   beforeEach(() => {
-    localStorage.clear();
+    window.localStorage?.clear();
     vi.restoreAllMocks();
     vi.stubGlobal("WebSocket", vi.fn());
   });
@@ -66,7 +66,7 @@ describe("App auth and project gates", () => {
     renderApp();
 
     expect(await screen.findByRole("heading", { name: /choose where this run belongs/i })).toBeInTheDocument();
-    expect(screen.getByRole("button", { name: /shared qa project/i })).toBeInTheDocument();
+    expect(await screen.findByRole("button", { name: /shared qa project/i })).toBeInTheDocument();
     expect(screen.queryByText(/Browser Use Cloud/i)).not.toBeInTheDocument();
   });
 
@@ -87,10 +87,10 @@ describe("App auth and project gates", () => {
     fireEvent.click(await screen.findByRole("button", { name: /shared qa project/i }));
 
     expect(await screen.findByText(/Browser Use Cloud/i)).toBeInTheDocument();
-    expect(screen.queryByText(/admin management/i)).not.toBeInTheDocument();
+    expect(screen.queryByText(/admin dashboard/i)).not.toBeInTheDocument();
   });
 
-  it("shows admin management for admin users after project selection", async () => {
+  it("shows admin dashboard directly for admin users, bypassing project selection", async () => {
     vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
       const url = String(input);
       if (url === "/auth/status") {
@@ -107,8 +107,7 @@ describe("App auth and project gates", () => {
 
     renderApp();
 
-    fireEvent.click(await screen.findByRole("button", { name: /shared qa project/i }));
-
-    await waitFor(() => expect(screen.getByText(/admin management/i)).toBeInTheDocument());
+    await waitFor(() => expect(screen.getByText(/admin dashboard/i)).toBeInTheDocument());
+    expect(screen.queryByText(/choose where this run belongs/i)).not.toBeInTheDocument();
   });
 });
diff --git a/frontend/src/App.tsx b/frontend/src/App.tsx
index 7e747f9..e8ab186 100644
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -7,7 +7,7 @@ import { ModelAssignmentReview } from "@/components/ModelAssignmentReview";
 import { ProcessingIndicator } from "@/components/ProcessingIndicator";
 import { LoginPage } from "@/components/auth/LoginPage";
 import { ProjectPicker } from "@/components/projects/ProjectPicker";
-import { AdminPanel } from "@/components/admin/AdminPanel";
+import { AdminDashboard } from "@/components/admin/AdminDashboard";
 import { useProject } from "@/hooks/useProject";
 import type { ProviderOption, ModelAssignment } from "@/types/provider";
 import type { AgentMessage } from "@/types/pipeline";
@@ -250,6 +250,10 @@ function App() {
     return <LoginPage />;
   }
 
+  if (isAuthenticated && user?.role === "admin") {
+    return <AdminDashboard />;
+  }
+
   if (isAuthenticated && !isProjectReady) {
     return <ProjectPicker />;
   }
@@ -518,7 +522,6 @@ function App() {
               )}
             </div>
           )}
-          {user?.role === "admin" && <AdminPanel />}
         </div>
       </div>
     </div>
diff --git a/frontend/src/components/admin/AdminPanel.test.tsx b/frontend/src/components/admin/AdminPanel.test.tsx
deleted file mode 100644
index 07e86d4..0000000
--- a/frontend/src/components/admin/AdminPanel.test.tsx
+++ /dev/null
@@ -1,71 +0,0 @@
-import { fireEvent, render, screen, waitFor } from "@testing-library/react";
-import { beforeEach, describe, expect, it, vi } from "vitest";
-import { AdminPanel } from "@/components/admin/AdminPanel";
-import { ProjectProvider } from "@/contexts/ProjectContext";
-import { AuthProvider } from "@/contexts/AuthContext";
-
-function jsonResponse(body: unknown, status = 200) {
-  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
-}
-
-const project = {
-  id: "project-1",
-  name: "Admin Project",
-  description: null,
-  created_by_user_id: null,
-  current_user_role: "owner",
-  membership_count: 1,
-  memberships: [],
-  created_at: "2026-01-01T00:00:00Z",
-  updated_at: "2026-01-01T00:00:00Z",
-};
-
-const user = {
-  id: "user-1",
-  email: "member@example.com",
-  display_name: "Member User",
-  role: "user",
-  is_active: true,
-  created_at: "2026-01-01T00:00:00Z",
-  updated_at: "2026-01-01T00:00:00Z",
-};
-
-describe("AdminPanel", () => {
-  beforeEach(() => {
-    localStorage.clear();
-    vi.restoreAllMocks();
-  });
-
-  it("loads users and submits project creation and membership assignment", async () => {
-    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
-      const url = String(input);
-      if (url === "/auth/status") return jsonResponse({ authenticated: true, email: "admin@example.com", name: "Admin", role: "admin" });
-      if (url === "/api/projects") return jsonResponse([project]);
-      if (url === "/api/admin/users") return jsonResponse([user]);
-      if (url === "/api/admin/projects" && init?.method === "POST") return jsonResponse(project);
-      if (url === "/api/admin/projects/project-1/memberships" && init?.method === "POST") return jsonResponse({ id: "membership-1" });
-      return jsonResponse({}, 404);
-    });
-
-    render(
-      <AuthProvider>
-        <ProjectProvider>
-          <AdminPanel />
-        </ProjectProvider>
-      </AuthProvider>,
-    );
-
-    expect((await screen.findAllByText("member@example.com")).length).toBeGreaterThan(0);
-
-    fireEvent.change(screen.getByLabelText(/project name/i), { target: { value: "New Project" } });
-    fireEvent.click(screen.getByRole("button", { name: /create project/i }));
-    expect(await screen.findByText(/project created successfully/i)).toBeInTheDocument();
-
-    fireEvent.change(screen.getByLabelText(/^project$/i), { target: { value: "project-1" } });
-    fireEvent.change(screen.getByLabelText(/^user$/i), { target: { value: "user-1" } });
-    fireEvent.click(screen.getByRole("button", { name: /assign user/i }));
-    expect(await screen.findByText(/membership assignment saved/i)).toBeInTheDocument();
-
-    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/admin/projects/project-1/memberships", expect.objectContaining({ method: "POST" })));
-  });
-});
diff --git a/frontend/src/components/admin/AdminPanel.tsx b/frontend/src/components/admin/AdminPanel.tsx
deleted file mode 100644
index e6e7512..0000000
--- a/frontend/src/components/admin/AdminPanel.tsx
+++ /dev/null
@@ -1,117 +0,0 @@
-import { useEffect, useState } from "react";
-import { Shield, UserPlus, Users } from "lucide-react";
-import { Button } from "@/components/ui/button";
-import { Input } from "@/components/ui/input";
-import { Label } from "@/components/ui/label";
-import { Textarea } from "@/components/ui/textarea";
-import { assignProjectMembership, createAdminProject, listAdminUsers } from "@/lib/projects";
-import { getSafeApiErrorMessage } from "@/lib/api";
-import { useProject } from "@/hooks/useProject";
-import type { AdminUser } from "@/types/project";
-
-export function AdminPanel() {
-  const { projects, reloadProjects } = useProject();
-  const [users, setUsers] = useState<AdminUser[]>([]);
-  const [name, setName] = useState("");
-  const [description, setDescription] = useState("");
-  const [projectId, setProjectId] = useState("");
-  const [userId, setUserId] = useState("");
-  const [role, setRole] = useState<"member" | "owner">("member");
-  const [status, setStatus] = useState<string | null>(null);
-  const [error, setError] = useState<string | null>(null);
-  const [isBusy, setIsBusy] = useState(false);
-
-  useEffect(() => {
-    void listAdminUsers().then(setUsers).catch((err) => setError(getSafeApiErrorMessage(err)));
-  }, []);
-
-  async function handleCreateProject(event: React.FormEvent<HTMLFormElement>) {
-    event.preventDefault();
-    setIsBusy(true);
-    setError(null);
-    setStatus(null);
-    try {
-      await createAdminProject({ name, description: description || null });
-      setName("");
-      setDescription("");
-      setStatus("Project created successfully.");
-      await reloadProjects();
-    } catch (err) {
-      setError(getSafeApiErrorMessage(err));
-    } finally {
-      setIsBusy(false);
-    }
-  }
-
-  async function handleAssignMembership(event: React.FormEvent<HTMLFormElement>) {
-    event.preventDefault();
-    setIsBusy(true);
-    setError(null);
-    setStatus(null);
-    try {
-      await assignProjectMembership(projectId, { user_id: userId, role });
-      setStatus("Membership assignment saved.");
-      await reloadProjects();
-    } catch (err) {
-      setError(getSafeApiErrorMessage(err));
-    } finally {
-      setIsBusy(false);
-    }
-  }
-
-  return (
-    <section className="border-t border-slate-200 bg-slate-50 p-5" aria-labelledby="admin-panel-title">
-      <div className="mb-4 flex items-center gap-2 text-slate-900">
-        <Shield className="h-5 w-5 text-blue-600" />
-        <h2 id="admin-panel-title" className="text-lg font-bold">Admin management</h2>
-      </div>
-      <div aria-live="polite" className="space-y-2">
-        {status && <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{status}</p>}
-        {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
-      </div>
-      <div className="mt-4 grid gap-5 lg:grid-cols-3">
-        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
-          <div className="mb-3 flex items-center gap-2 font-semibold"><Users className="h-4 w-4" /> Users</div>
-          <div className="max-h-64 space-y-2 overflow-auto">
-            {users.map((user) => (
-              <div key={user.id} className="rounded-xl bg-slate-50 p-3 text-sm">
-                <div className="font-semibold text-slate-900">{user.display_name}</div>
-                <div className="text-slate-600">{user.email}</div>
-                <div className="mt-1 text-xs text-slate-500">{user.role} ┬╖ {user.is_active ? "active" : "inactive"}</div>
-              </div>
-            ))}
-          </div>
-        </div>
-
-        <form onSubmit={handleCreateProject} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
-          <div className="mb-3 flex items-center gap-2 font-semibold"><UserPlus className="h-4 w-4" /> Create project</div>
-          <Label htmlFor="admin-project-name">Project name</Label>
-          <Input id="admin-project-name" value={name} onChange={(e) => setName(e.target.value)} required minLength={1} className="mt-1 min-h-11" />
-          <Label htmlFor="admin-project-description" className="mt-3 block">Description</Label>
-          <Textarea id="admin-project-description" value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1" />
-          <Button id="create-project-button" type="submit" disabled={isBusy} className="mt-4 min-h-11 w-full">Create project</Button>
-        </form>
-
-        <form onSubmit={handleAssignMembership} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
-          <div className="mb-3 font-semibold">Assign membership</div>
-          <Label htmlFor="membership-project">Project</Label>
-          <select id="membership-project" value={projectId} onChange={(e) => setProjectId(e.target.value)} required className="mt-1 min-h-11 w-full rounded-md border border-slate-300 px-3">
-            <option value="">Select project</option>
-            {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
-          </select>
-          <Label htmlFor="membership-user" className="mt-3 block">User</Label>
-          <select id="membership-user" value={userId} onChange={(e) => setUserId(e.target.value)} required className="mt-1 min-h-11 w-full rounded-md border border-slate-300 px-3">
-            <option value="">Select active user</option>
-            {users.filter((user) => user.is_active).map((user) => <option key={user.id} value={user.id}>{user.email}</option>)}
-          </select>
-          <Label htmlFor="membership-role" className="mt-3 block">Role</Label>
-          <select id="membership-role" value={role} onChange={(e) => setRole(e.target.value as "member" | "owner")} className="mt-1 min-h-11 w-full rounded-md border border-slate-300 px-3">
-            <option value="member">Member</option>
-            <option value="owner">Owner</option>
-          </select>
-          <Button id="assign-membership-button" type="submit" disabled={isBusy} className="mt-4 min-h-11 w-full">Assign user</Button>
-        </form>
-      </div>
-    </section>
-  );
-}
diff --git a/frontend/src/test-setup.ts b/frontend/src/test-setup.ts
index 4fb2be4..60343c4 100644
--- a/frontend/src/test-setup.ts
+++ b/frontend/src/test-setup.ts
@@ -9,3 +9,27 @@ vi.mock('@/components/ui/tooltip', () => ({
   TooltipProvider: ({ children }: { children: ReactNode }) => children,
   TooltipTrigger: ({ children }: { children: ReactNode }) => children,
 }));
+
+// Mock localStorage
+const localStorageMock = (function () {
+  let store: Record<string, string> = {};
+  return {
+    getItem(key: string) {
+      return store[key] || null;
+    },
+    setItem(key: string, value: string) {
+      store[key] = value.toString();
+    },
+    clear() {
+      store = {};
+    },
+    removeItem(key: string) {
+      delete store[key];
+    },
+  };
+})();
+
+Object.defineProperty(window, 'localStorage', {
+  value: localStorageMock,
+  writable: true,
+});
diff --git a/frontend/src/components/admin/AdminDashboard.test.tsx b/frontend/src/components/admin/AdminDashboard.test.tsx
new file mode 100644
index 0000000..b16258e
--- /dev/null
+++ b/frontend/src/components/admin/AdminDashboard.test.tsx
@@ -0,0 +1,80 @@
+import { fireEvent, render, screen, waitFor } from "@testing-library/react";
+import { beforeEach, describe, expect, it, vi } from "vitest";
+import { AdminDashboard } from "@/components/admin/AdminDashboard";
+import { ProjectProvider } from "@/contexts/ProjectContext";
+import { AuthProvider } from "@/contexts/AuthContext";
+
+function jsonResponse(body: unknown, status = 200) {
+  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
+}
+
+const project = {
+  id: "project-1",
+  name: "Admin Project",
+  description: null,
+  created_by_user_id: null,
+  current_user_role: "owner",
+  membership_count: 1,
+  memberships: [],
+  created_at: "2026-01-01T00:00:00Z",
+  updated_at: "2026-01-01T00:00:00Z",
+};
+
+const user = {
+  id: "user-1",
+  email: "member@example.com",
+  display_name: "Member User",
+  role: "user",
+  is_active: true,
+  created_at: "2026-01-01T00:00:00Z",
+  updated_at: "2026-01-01T00:00:00Z",
+};
+
+describe("AdminDashboard", () => {
+  beforeEach(() => {
+    window.localStorage?.clear();
+    vi.restoreAllMocks();
+  });
+
+  it("loads users and submits project creation and membership assignment", async () => {
+    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
+      const url = String(input);
+      if (url === "/auth/status") return jsonResponse({ authenticated: true, email: "admin@example.com", name: "Admin User", role: "admin" });
+      if (url === "/api/projects") return jsonResponse([project]);
+      if (url === "/api/admin/users") return jsonResponse([user]);
+      if (url === "/api/admin/projects" && init?.method === "POST") return jsonResponse(project);
+      if (url === "/api/admin/projects/project-1/memberships" && init?.method === "POST") return jsonResponse({ id: "membership-1" });
+      if (url === "/auth/logout" && init?.method === "POST") return jsonResponse({ success: true });
+      return jsonResponse({}, 404);
+    });
+
+    render(
+      <AuthProvider>
+        <ProjectProvider>
+          <AdminDashboard />
+        </ProjectProvider>
+      </AuthProvider>,
+    );
+
+    // Wait for auth to load
+    expect(await screen.findByText("Admin User")).toBeInTheDocument();
+    expect(screen.getByText(/admin@example\.com/)).toBeInTheDocument();
+
+    expect((await screen.findAllByText("member@example.com")).length).toBeGreaterThan(0);
+
+    fireEvent.change(screen.getByLabelText(/project name/i), { target: { value: "New Project" } });
+    fireEvent.click(screen.getByRole("button", { name: /create project/i }));
+    expect(await screen.findByText(/project created successfully/i)).toBeInTheDocument();
+
+    fireEvent.change(screen.getByLabelText(/^project$/i), { target: { value: "project-1" } });
+    fireEvent.change(screen.getByLabelText(/^user$/i), { target: { value: "user-1" } });
+    fireEvent.click(screen.getByRole("button", { name: /update membership/i }));
+    expect(await screen.findByText(/membership assignment saved/i)).toBeInTheDocument();
+
+    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/admin/projects/project-1/memberships", expect.objectContaining({ method: "POST" })));
+
+    // Test Logout
+    fireEvent.click(screen.getByRole("button", { name: /logout/i }));
+    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/auth/logout", expect.objectContaining({ method: "POST" })));
+  });
+});
diff --git a/frontend/src/components/admin/AdminDashboard.tsx b/frontend/src/components/admin/AdminDashboard.tsx
new file mode 100644
index 0000000..1aec06a
--- /dev/null
+++ b/frontend/src/components/admin/AdminDashboard.tsx
@@ -0,0 +1,248 @@
+import { useEffect, useState } from "react";
+import { Shield, UserPlus, Users, LogOut, Settings } from "lucide-react";
+import { Button } from "@/components/ui/button";
+import { Input } from "@/components/ui/input";
+import { Label } from "@/components/ui/label";
+import { Textarea } from "@/components/ui/textarea";
+import { assignProjectMembership, createAdminProject, listAdminUsers } from "@/lib/projects";
+import { getSafeApiErrorMessage } from "@/lib/api";
+import { useProject } from "@/hooks/useProject";
+import { useAuth } from "@/hooks/useAuth";
+import type { AdminUser } from "@/types/project";
+
+export function AdminDashboard() {
+  const { projects, reloadProjects } = useProject();
+  const { user, logout } = useAuth();
+  const [users, setUsers] = useState<AdminUser[]>([]);
+  const [name, setName] = useState("");
+  const [description, setDescription] = useState("");
+  const [projectId, setProjectId] = useState("");
+  const [userId, setUserId] = useState("");
+  const [role, setRole] = useState<"member" | "owner">("member");
+  const [status, setStatus] = useState<string | null>(null);
+  const [error, setError] = useState<string | null>(null);
+  const [isBusy, setIsBusy] = useState(false);
+
+  useEffect(() => {
+    void listAdminUsers().then(setUsers).catch((err) => setError(getSafeApiErrorMessage(err)));
+  }, []);
+
+  async function handleCreateProject(event: React.FormEvent<HTMLFormElement>) {
+    event.preventDefault();
+    setIsBusy(true);
+    setError(null);
+    setStatus(null);
+    try {
+      await createAdminProject({ name, description: description || null });
+      setName("");
+      setDescription("");
+      setStatus("Project created successfully.");
+      await reloadProjects();
+    } catch (err) {
+      setError(getSafeApiErrorMessage(err));
+    } finally {
+      setIsBusy(false);
+    }
+  }
+
+  async function handleAssignMembership(event: React.FormEvent<HTMLFormElement>) {
+    event.preventDefault();
+    setIsBusy(true);
+    setError(null);
+    setStatus(null);
+    try {
+      await assignProjectMembership(projectId, { user_id: userId, role });
+      setStatus("Membership assignment saved.");
+      await reloadProjects();
+    } catch (err) {
+      setError(getSafeApiErrorMessage(err));
+    } finally {
+      setIsBusy(false);
+    }
+  }
+
+  function notImplemented() {
+    setError("Backend API endpoint not yet implemented for this action.");
+  }
+
+  return (
+    <div className="min-h-screen bg-[#f8fafc] flex flex-col">
+      {/* Top Navigation for Admin */}
+      <nav className="bg-white border-b border-[#e2e8f0] px-6 py-3 flex justify-between items-center z-50 shadow-sm">
+        <div className="flex items-center gap-3">
+          <div className="w-9 h-9 rounded-md bg-blue-600 flex items-center justify-center text-white font-bold flex-shrink-0">
+            <Shield className="w-5 h-5" />
+          </div>
+          <div>
+            <div className="text-[15px] font-bold text-[#0f172a] whitespace-nowrap">
+              AI <span className="text-blue-600">QA Automation</span>
+            </div>
+            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
+              Administration
+            </div>
+          </div>
+        </div>
+
+        <div className="flex items-center gap-4">
+          <div className="hidden md:block text-right">
+            <div className="text-sm font-semibold text-slate-900">{user?.name}</div>
+            <div className="text-xs text-slate-500">{user?.email} ┬╖ <span className="text-blue-600 font-medium">{user?.role}</span></div>
+          </div>
+          <div className="w-px h-8 bg-slate-200 hidden md:block" />
+          <Button
+            variant="outline"
+            size="sm"
+            onClick={() => logout()}
+            className="flex items-center gap-2 text-slate-600 border-slate-300"
+          >
+            <LogOut className="w-4 h-4" />
+            Logout
+          </Button>
+        </div>
+      </nav>
+
+      <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto w-full">
+        <div className="mb-8 flex items-center gap-3">
+          <Settings className="w-6 h-6 text-slate-600" />
+          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Admin Dashboard</h1>
+        </div>
+        
+        <div aria-live="polite" className="space-y-3 mb-6">
+          {status && <p className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-800 shadow-sm">{status}</p>}
+          {error && <p className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-800 shadow-sm">{error}</p>}
+        </div>
+        
+        <div className="mt-4 grid gap-6 lg:grid-cols-2">
+          {/* Projects List */}
+          <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col h-[500px]">
+            <div className="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
+              <Shield className="h-5 w-5 text-blue-500" /> 
+              Projects
+            </div>
+            <div className="p-5 flex-1 overflow-auto">
+              <div className="space-y-3">
+                {projects.map((proj) => (
+                  <div key={proj.id} className="flex flex-col rounded-lg border border-slate-100 bg-slate-50 p-4 hover:border-slate-300 transition-colors">
+                    <div className="flex justify-between items-start mb-2">
+                      <div className="font-semibold text-slate-900">{proj.name}</div>
+                      <div className="flex gap-2">
+                        <Button variant="outline" size="sm" onClick={notImplemented} className="h-7 text-xs">Edit</Button>
+                        <Button variant="destructive" size="sm" onClick={notImplemented} className="h-7 text-xs">Delete</Button>
+                      </div>
+                    </div>
+                    {proj.description && <div className="text-sm text-slate-600 mb-2">{proj.description}</div>}
+                    <div className="text-xs text-slate-500">
+                      {proj.memberships?.length || 0} member(s)
+                    </div>
+                  </div>
+                ))}
+              </div>
+            </div>
+          </div>
+
+          {/* Users List */}
+          <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col h-[500px]">
+            <div className="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
+              <Users className="h-5 w-5 text-blue-500" /> 
+              Users Management
+            </div>
+            <div className="p-5 flex-1 overflow-auto">
+              <div className="space-y-3">
+                {users.map((u) => {
+                  const userProjects = projects.filter(p => p.memberships?.some(m => m.user_id === u.id));
+                  return (
+                    <div key={u.id} className="rounded-lg border border-slate-100 bg-slate-50 p-4 hover:border-slate-300 transition-colors">
+                      <div className="font-semibold text-slate-900">{u.display_name}</div>
+                      <div className="text-sm text-slate-600 mb-2">{u.email}</div>
+                      <div className="flex items-center gap-2 mt-1 mb-3">
+                        <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${u.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-slate-200 text-slate-700'}`}>
+                          {u.role}
+                        </span>
+                        <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${u.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
+                          {u.is_active ? "active" : "inactive"}
+                        </span>
+                      </div>
+                      <div className="text-xs text-slate-700 font-medium mb-1">Projects:</div>
+                      {userProjects.length > 0 ? (
+                        <div className="flex flex-wrap gap-1">
+                          {userProjects.map(up => (
+                            <span key={up.id} className="inline-flex items-center gap-1 bg-white border border-slate-200 text-slate-600 px-2 py-1 rounded text-xs">
+                              {up.name}
+                              <button type="button" onClick={notImplemented} className="text-red-500 hover:text-red-700 font-bold ml-1" title="Remove user from project">├ù</button>
+                            </span>
+                          ))}
+                        </div>
+                      ) : (
+                        <div className="text-xs text-slate-500 italic">No projects</div>
+                      )}
+                    </div>
+                  );
+                })}
+              </div>
+            </div>
+          </div>
+        </div>
+
+        <div className="mt-6 grid gap-6 lg:grid-cols-2">
+          {/* Create Project */}
+          <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col h-full">
+            <div className="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
+              <UserPlus className="h-5 w-5 text-blue-500" /> 
+              Create Project
+            </div>
+            <div className="p-5">
+              <form onSubmit={handleCreateProject} className="space-y-4">
+                <div>
+                  <Label htmlFor="admin-project-name" className="text-slate-700">Project name</Label>
+                  <Input id="admin-project-name" value={name} onChange={(e) => setName(e.target.value)} required minLength={1} className="mt-1.5 focus-visible:ring-blue-500" />
+                </div>
+                <div>
+                  <Label htmlFor="admin-project-description" className="text-slate-700 block">Description</Label>
+                  <Textarea id="admin-project-description" value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1.5 focus-visible:ring-blue-500" rows={4} />
+                </div>
+                <Button id="create-project-button" type="submit" disabled={isBusy} className="w-full bg-blue-600 hover:bg-blue-700 text-white">Create project</Button>
+              </form>
+            </div>
+          </div>
+
+          {/* Assign Membership */}
+          <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col h-full">
+            <div className="p-5 border-b border-slate-100 flex items-center gap-2 text-slate-800 font-semibold">
+              <Shield className="h-5 w-5 text-blue-500" />
+              Manage Membership
+            </div>
+            <div className="p-5">
+              <form onSubmit={handleAssignMembership} className="space-y-4">
+                <div>
+                  <Label htmlFor="membership-project" className="text-slate-700">Project</Label>
+                  <select id="membership-project" value={projectId} onChange={(e) => setProjectId(e.target.value)} required className="mt-1.5 min-h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500">
+                    <option value="">Select project...</option>
+                    {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
+                  </select>
+                </div>
+                <div>
+                  <Label htmlFor="membership-user" className="text-slate-700 block">User</Label>
+                  <select id="membership-user" value={userId} onChange={(e) => setUserId(e.target.value)} required className="mt-1.5 min-h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500">
+                    <option value="">Select active user...</option>
+                    {users.filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.email}</option>)}
+                  </select>
+                </div>
+                <div>
+                  <Label htmlFor="membership-role" className="text-slate-700 block">Action / Role</Label>
+                  <div className="flex gap-2 mt-1.5">
+                    <select id="membership-role" value={role} onChange={(e) => setRole(e.target.value as "member" | "owner")} className="flex-1 min-h-10 rounded-md border border-slate-300 bg-white px-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500">
+                      <option value="member">Assign as Member</option>
+                      <option value="owner">Assign as Owner</option>
+                    </select>
+                    <Button type="button" variant="outline" onClick={notImplemented} className="min-h-10">Remove User</Button>
+                  </div>
+                </div>
+                <Button id="assign-membership-button" type="submit" disabled={isBusy} className="w-full bg-slate-800 hover:bg-slate-900 text-white mt-2">Update Membership</Button>
+              </form>
+            </div>
+          </div>
+        </div>
+      </main>
+    </div>
+  );
+}
