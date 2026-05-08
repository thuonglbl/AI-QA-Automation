import { Briefcase, CheckCircle2, FolderKanban, RefreshCw, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProject } from "@/hooks/useProject";

export function ProjectPicker() {
  const { projects, selectedProjectId, selectProject, isLoadingProjects, projectError, reloadProjects } = useProject();

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 px-6 py-10 text-slate-100">
      <section className="mx-auto flex max-w-6xl flex-col gap-8">
        <div className="rounded-[2rem] border border-white/10 bg-white/10 p-8 shadow-2xl shadow-blue-950/40 backdrop-blur-xl">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-300/30 bg-blue-400/10 px-4 py-2 text-sm font-semibold text-blue-100">
                <FolderKanban className="h-4 w-4" /> Project workspace
              </div>
              <h1 className="text-4xl font-bold tracking-tight md:text-5xl">Choose where this run belongs</h1>
              <p className="mt-3 max-w-2xl text-base leading-7 text-slate-300">
                Every agent result is scoped to a shared project. Pick an accessible project before the AI QA pipeline starts.
              </p>
            </div>
            <Button
              id="reload-projects-button"
              type="button"
              variant="secondary"
              onClick={() => void reloadProjects()}
              disabled={isLoadingProjects}
              className="min-h-11 gap-2 bg-white/90 text-slate-900 hover:bg-white"
            >
              <RefreshCw className={`h-4 w-4 ${isLoadingProjects ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </div>

        <div aria-live="polite">
          {projectError && (
            <div className="mb-5 flex items-start gap-3 rounded-2xl border border-amber-300/30 bg-amber-400/10 p-4 text-amber-100">
              <ShieldAlert className="mt-0.5 h-5 w-5 flex-shrink-0" />
              <p>{projectError}</p>
            </div>
          )}

          {isLoadingProjects ? (
            <div className="rounded-3xl border border-white/10 bg-white/10 p-10 text-center text-slate-200 backdrop-blur-xl">
              Loading your accessible projects…
            </div>
          ) : projects.length === 0 ? (
            <div className="rounded-3xl border border-white/10 bg-white/10 p-10 text-center backdrop-blur-xl">
              <Briefcase className="mx-auto mb-4 h-12 w-12 text-blue-200" />
              <h2 className="text-2xl font-bold">No projects assigned yet</h2>
              <p className="mx-auto mt-3 max-w-xl text-slate-300">
                Contact an administrator to be added to a project before running the agent pipeline.
              </p>
            </div>
          ) : (
            <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
              {projects.map((project) => {
                const selected = selectedProjectId === project.id;
                return (
                  <button
                    id={`select-project-${project.id}`}
                    key={project.id}
                    type="button"
                    onClick={() => selectProject(project.id)}
                    className={`group min-h-[220px] rounded-3xl border p-6 text-left shadow-xl transition-all duration-200 focus:outline-none focus:ring-4 focus:ring-blue-300/50 ${
                      selected
                        ? "border-blue-300 bg-blue-500/20 shadow-blue-900/40"
                        : "border-white/10 bg-white/10 shadow-slate-950/20 hover:-translate-y-1 hover:border-blue-300/50 hover:bg-white/15"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-400/20 text-blue-100">
                        <Briefcase className="h-6 w-6" />
                      </div>
                      {selected && <CheckCircle2 className="h-6 w-6 text-emerald-300" />}
                    </div>
                    <h2 className="mt-5 text-xl font-bold text-white">{project.name}</h2>
                    <p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-300">
                      {project.description || "Shared project workspace for generated requirements, test cases, scripts, and reports."}
                    </p>
                    <div className="mt-5 flex flex-wrap gap-2 text-xs font-semibold">
                      <span className="rounded-full bg-white/10 px-3 py-1 text-blue-100">Role: {project.current_user_role || "admin"}</span>
                      <span className="rounded-full bg-white/10 px-3 py-1 text-slate-200">{project.membership_count} members</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
