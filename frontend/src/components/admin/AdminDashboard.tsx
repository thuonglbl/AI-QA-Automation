import { useEffect, useState, useMemo } from "react";
import { Plus, Shield, UserPlus, Users, LogOut, Settings, X } from "lucide-react";
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
} from "@/lib/projects";
import { getSafeApiErrorMessage } from "@/lib/api";
import { useProject } from "@/hooks/useProject";
import { useAuth } from "@/hooks/useAuth";
import type { AdminUser } from "@/types/project";

export function AdminDashboard() {
  const { projects, reloadProjects } = useProject();
  const { user, logout } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(true);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [confluenceBaseUrl, setConfluenceBaseUrl] = useState("");
  const [createUserEmail, setCreateUserEmail] = useState("");
  const [createUserDisplayName, setCreateUserDisplayName] = useState("");
  const [createUserPassword, setCreateUserPassword] = useState("");
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editProjectName, setEditProjectName] = useState("");
  const [editProjectDescription, setEditProjectDescription] = useState("");
  const [editProjectConfluenceBaseUrl, setEditProjectConfluenceBaseUrl] = useState("");
  const [selectedProjectByUserId, setSelectedProjectByUserId] = useState<Record<string, string>>( {});
  const [status, setStatus] = useState<string | null>(null);
  const [errors, setErrors] = useState<{id: number, msg: string}[]>([]);
  const [isBusy, setIsBusy] = useState(false);
  const [errorIdCounter, setErrorIdCounter] = useState(0);

  const addError = (msg: string) => {
    setErrors(prev => [...prev, { id: errorIdCounter, msg }]);
    setErrorIdCounter(prev => prev + 1);
  };

  const dismissError = (id: number) => {
    setErrors(prev => prev.filter(e => e.id !== id));
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
    
    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await createAdminProject({ 
        name: trimmedName, 
        description: description.trim() || null,
        confluence_base_url: confluenceBaseUrl.trim()
      });
      setName("");
      setDescription("");
      setConfluenceBaseUrl("");
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
        initial_password: createUserPassword,
      });
      setCreateUserEmail("");
      setCreateUserDisplayName("");
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
  }

  function cancelEditingProject() {
    setEditingProjectId(null);
    setEditProjectName("");
    setEditProjectDescription("");
    setEditProjectConfluenceBaseUrl("");
  }

  async function handleEditProject(event: React.FormEvent<HTMLFormElement>, project: (typeof projects)[number]) {
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
        confluence_base_url: editProjectConfluenceBaseUrl.trim(),
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
      (project) => !project.memberships?.some((membership) => membership.user_id === targetUser.id),
    );
    const selectedProjectId = selectedProjectByUserId[targetUser.id];
    const availableProject = availableProjects.find((project) => project.id === selectedProjectId) ?? availableProjects[0];
    if (!availableProject) {
      addError("No available projects to assign.");
      return;
    }
    setIsBusy(true);
    setErrors([]);
    setStatus(null);
    try {
      await assignProjectMembership(availableProject.id, { user_id: targetUser.id, role: "member" });
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

  async function handleRemoveUserFromProject(projectId: string, targetUser: AdminUser) {
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

  const projectsByUserId = useMemo(() => {
    const map = new Map<string, typeof projects>();
    projects.forEach(p => {
      p.memberships?.forEach(m => {
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
        projects.filter((project) => !project.memberships?.some((membership) => membership.user_id === u.id)),
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
            <div className="text-sm font-semibold text-slate-900">{(user as any)?.display_name || user?.name}</div>
            <div className="text-xs text-slate-500">{user?.email} · <span className="text-blue-600 font-medium">{user?.role}</span></div>
          </div>
          <div className="w-px h-8 bg-slate-200 hidden md:block" />
          <Button
            variant="outline"
            size="sm"
            onClick={() => { Promise.resolve(logout()).catch(console.error); }}
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
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Admin Dashboard</h1>
        </div>
        
        <div aria-live="polite" className="space-y-3 mb-6">
          {status && <p className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-800 shadow-sm">{status}</p>}
          {errors.map((err) => (
            <div key={err.id} className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-800 shadow-sm flex justify-between items-start">
              <span>{err.msg}</span>
              <button type="button" onClick={() => dismissError(err.id)} className="text-red-500 hover:text-red-700 font-bold ml-2 focus:outline-none" aria-label="Dismiss error">
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
                    <div key={proj.id} className="flex flex-col rounded-lg border border-slate-100 bg-slate-50 p-4 hover:border-slate-300 transition-colors">
                      {editingProjectId === proj.id ? (
                        <form onSubmit={(event) => handleEditProject(event, proj)} className="space-y-3">
                          <div>
                            <Label htmlFor={`edit-project-name-${proj.id}`} className="text-slate-700">Project name</Label>
                            <Input id={`edit-project-name-${proj.id}`} value={editProjectName} onChange={(e) => setEditProjectName(e.target.value)} required className="mt-1.5" />
                          </div>
                          <div>
                            <Label htmlFor={`edit-project-description-${proj.id}`} className="text-slate-700">Description</Label>
                            <Textarea id={`edit-project-description-${proj.id}`} value={editProjectDescription} onChange={(e) => setEditProjectDescription(e.target.value)} rows={2} className="mt-1.5" />
                          </div>
                          <div>
                            <Label htmlFor={`edit-project-confluence-${proj.id}`} className="text-slate-700">Confluence Base URL</Label>
                            <Input id={`edit-project-confluence-${proj.id}`} value={editProjectConfluenceBaseUrl} onChange={(e) => setEditProjectConfluenceBaseUrl(e.target.value)} required className="mt-1.5" />
                          </div>
                          <div className="flex gap-2">
                            <Button type="submit" size="sm" disabled={isBusy} className="h-7 text-xs">Save</Button>
                            <Button type="button" variant="outline" size="sm" onClick={cancelEditingProject} disabled={isBusy} className="h-7 text-xs">Cancel</Button>
                          </div>
                        </form>
                      ) : (
                        <>
                          <div className="flex justify-between items-start mb-2">
                            <div className="font-semibold text-slate-900">{proj.name}</div>
                            <div className="flex gap-2">
                              <Button variant="outline" size="sm" onClick={() => startEditingProject(proj)} disabled={isBusy} className="h-7 text-xs" aria-label={`Edit ${proj.name}`}>Edit</Button>
                              <Button variant="destructive" size="sm" onClick={() => handleDeleteProject(proj)} disabled={isBusy} className="h-7 text-xs" aria-label={`Delete ${proj.name}`}>Delete</Button>
                            </div>
                          </div>
                          {proj.description && <div className="text-sm text-slate-600 mb-2">{proj.description}</div>}
                          {proj.confluence_base_url && (
                            <div className="text-xs text-slate-500 mb-2 break-all">
                              <a href={proj.confluence_base_url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">{proj.confluence_base_url}</a>
                            </div>
                          )}
                          <div className="text-xs text-slate-500">
                            {proj.memberships?.length || 0} member(s)
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                  {projects.length === 0 && <div className="text-sm text-slate-500 italic text-center py-4">No projects found.</div>}
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
                    <Label htmlFor="admin-project-name" className="text-slate-700">Project name</Label>
                    <Input id="admin-project-name" value={name} onChange={(e) => setName(e.target.value)} required minLength={1} className="mt-1.5 focus-visible:ring-blue-500" />
                  </div>
                  <div>
                    <Label htmlFor="admin-project-description" className="text-slate-700 block">Description</Label>
                    <Textarea id="admin-project-description" value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1.5 focus-visible:ring-blue-500" rows={3} />
                  </div>
                  <div>
                    <Label htmlFor="admin-project-confluence" className="text-slate-700 block">Confluence Base URL *</Label>
                    <Input id="admin-project-confluence" value={confluenceBaseUrl} onChange={(e) => setConfluenceBaseUrl(e.target.value)} required className="mt-1.5 focus-visible:ring-blue-500" />
                  </div>
                  <Button id="create-project-button" type="submit" disabled={isBusy} className="w-full bg-blue-600 hover:bg-blue-700 text-white">Create project</Button>
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
                      const userProjects = projectsByUserId.get(u.id) || [];
                      const assignableProjects = assignableProjectsByUserId.get(u.id) || [];
                      return (
                        <li key={u.id} className="rounded-lg border border-slate-100 bg-slate-50 p-4 hover:border-slate-300 transition-colors">
                          <div className="font-semibold text-slate-900">{u.display_name}</div>
                          <div className="text-sm text-slate-600 mb-2">{u.email}</div>
                          <div className="flex items-center gap-2 mt-1 mb-3">
                            <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${u.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-slate-200 text-slate-700'}`}>
                              {u.role}
                            </span>
                            <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${u.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                              {u.is_active ? "active" : "inactive"}
                            </span>
                          </div>
                          <div className="flex items-center justify-between mb-2">
                            <div className="text-xs text-slate-700 font-medium">Projects</div>
                            <div className="flex items-center gap-2">
                              <select
                                value={selectedProjectByUserId[u.id] ?? ""}
                                onChange={(e) => setSelectedProjectByUserId((prev) => ({ ...prev, [u.id]: e.target.value }))}
                                disabled={isBusy || !u.is_active || assignableProjects.length === 0}
                                aria-label={`Select project for ${u.display_name}`}
                                className="h-7 max-w-36 rounded-md border border-slate-300 bg-white px-2 text-xs disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                <option value="">Select project...</option>
                                {assignableProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                              </select>
                              <Button type="button" variant="outline" size="sm" onClick={() => handleAssignUserToProject(u)} disabled={isBusy || !u.is_active || assignableProjects.length === 0} className="h-7 w-7 p-0" aria-label={`Assign project to ${u.display_name}`}>
                                <Plus className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </div>
                          {userProjects.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {userProjects.map(up => (
                                <span key={up.id} className="inline-flex items-center gap-1 bg-white border border-slate-200 text-slate-600 px-2 py-1 rounded text-xs">
                                  {up.name}
                                  <button type="button" onClick={() => handleRemoveUserFromProject(up.id, u)} disabled={isBusy} className="text-red-500 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-50 font-bold ml-1" title="Remove user from project" aria-label={`Remove ${up.name} from ${u.display_name}`}>×</button>
                                </span>
                              ))}
                            </div>
                          ) : (
                            <div className="text-xs text-slate-500 italic">No projects</div>
                          )}
                        </li>
                      );
                    })}
                    {users.length === 0 && <li className="text-sm text-slate-500 italic text-center py-4">No users found.</li>}
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
                    <Label htmlFor="create-user-email" className="text-slate-700">Email</Label>
                    <Input id="create-user-email" type="email" value={createUserEmail} onChange={(e) => setCreateUserEmail(e.target.value)} required className="mt-1.5 focus-visible:ring-blue-500" />
                  </div>
                  <div>
                    <Label htmlFor="create-user-display-name" className="text-slate-700 block">Display Name</Label>
                    <Input id="create-user-display-name" value={createUserDisplayName} onChange={(e) => setCreateUserDisplayName(e.target.value)} required className="mt-1.5 focus-visible:ring-blue-500" />
                  </div>
                  <div>
                    <Label htmlFor="create-user-password" className="text-slate-700 block">Initial Password</Label>
                    <Input id="create-user-password" type="password" value={createUserPassword} onChange={(e) => setCreateUserPassword(e.target.value)} required minLength={8} className="mt-1.5 focus-visible:ring-blue-500" />
                  </div>
                  <Button id="create-user-button" type="submit" disabled={isBusy} className="w-full bg-slate-800 hover:bg-slate-900 text-white mt-2">Create user</Button>
                  <div className="space-y-1">
                    <Button type="button" variant="outline" disabled aria-describedby="sync-users-help" className="w-full">Sync existing company's users</Button>
                    <p id="sync-users-help" className="text-xs text-slate-500">This feature is not available at the moment, please add manually.</p>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
