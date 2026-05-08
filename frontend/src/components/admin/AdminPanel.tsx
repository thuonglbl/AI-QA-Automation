import { useEffect, useState } from "react";
import { Shield, UserPlus, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { assignProjectMembership, createAdminProject, listAdminUsers } from "@/lib/projects";
import { getSafeApiErrorMessage } from "@/lib/api";
import { useProject } from "@/hooks/useProject";
import type { AdminUser } from "@/types/project";

export function AdminPanel() {
  const { projects, reloadProjects } = useProject();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [projectId, setProjectId] = useState("");
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<"member" | "owner">("member");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    void listAdminUsers().then(setUsers).catch((err) => setError(getSafeApiErrorMessage(err)));
  }, []);

  async function handleCreateProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    setStatus(null);
    try {
      await createAdminProject({ name, description: description || null });
      setName("");
      setDescription("");
      setStatus("Project created successfully.");
      await reloadProjects();
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAssignMembership(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    setStatus(null);
    try {
      await assignProjectMembership(projectId, { user_id: userId, role });
      setStatus("Membership assignment saved.");
      await reloadProjects();
    } catch (err) {
      setError(getSafeApiErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <section className="border-t border-slate-200 bg-slate-50 p-5" aria-labelledby="admin-panel-title">
      <div className="mb-4 flex items-center gap-2 text-slate-900">
        <Shield className="h-5 w-5 text-blue-600" />
        <h2 id="admin-panel-title" className="text-lg font-bold">Admin management</h2>
      </div>
      <div aria-live="polite" className="space-y-2">
        {status && <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{status}</p>}
        {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      </div>
      <div className="mt-4 grid gap-5 lg:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2 font-semibold"><Users className="h-4 w-4" /> Users</div>
          <div className="max-h-64 space-y-2 overflow-auto">
            {users.map((user) => (
              <div key={user.id} className="rounded-xl bg-slate-50 p-3 text-sm">
                <div className="font-semibold text-slate-900">{user.display_name}</div>
                <div className="text-slate-600">{user.email}</div>
                <div className="mt-1 text-xs text-slate-500">{user.role} · {user.is_active ? "active" : "inactive"}</div>
              </div>
            ))}
          </div>
        </div>

        <form onSubmit={handleCreateProject} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2 font-semibold"><UserPlus className="h-4 w-4" /> Create project</div>
          <Label htmlFor="admin-project-name">Project name</Label>
          <Input id="admin-project-name" value={name} onChange={(e) => setName(e.target.value)} required minLength={1} className="mt-1 min-h-11" />
          <Label htmlFor="admin-project-description" className="mt-3 block">Description</Label>
          <Textarea id="admin-project-description" value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1" />
          <Button id="create-project-button" type="submit" disabled={isBusy} className="mt-4 min-h-11 w-full">Create project</Button>
        </form>

        <form onSubmit={handleAssignMembership} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 font-semibold">Assign membership</div>
          <Label htmlFor="membership-project">Project</Label>
          <select id="membership-project" value={projectId} onChange={(e) => setProjectId(e.target.value)} required className="mt-1 min-h-11 w-full rounded-md border border-slate-300 px-3">
            <option value="">Select project</option>
            {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
          <Label htmlFor="membership-user" className="mt-3 block">User</Label>
          <select id="membership-user" value={userId} onChange={(e) => setUserId(e.target.value)} required className="mt-1 min-h-11 w-full rounded-md border border-slate-300 px-3">
            <option value="">Select active user</option>
            {users.filter((user) => user.is_active).map((user) => <option key={user.id} value={user.id}>{user.email}</option>)}
          </select>
          <Label htmlFor="membership-role" className="mt-3 block">Role</Label>
          <select id="membership-role" value={role} onChange={(e) => setRole(e.target.value as "member" | "owner")} className="mt-1 min-h-11 w-full rounded-md border border-slate-300 px-3">
            <option value="member">Member</option>
            <option value="owner">Owner</option>
          </select>
          <Button id="assign-membership-button" type="submit" disabled={isBusy} className="mt-4 min-h-11 w-full">Assign user</Button>
        </form>
      </div>
    </section>
  );
}
