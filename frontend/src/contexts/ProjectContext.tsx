import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, getSafeApiErrorMessage } from "@/lib/api";
import { getUserProjects } from "@/lib/projects";
import { useAuth } from "@/hooks/useAuth";
import type { Project } from "@/types/project";

const SELECTED_PROJECT_KEY = "ai-qa-selected-project-id";

interface ProjectContextType {
  projects: Project[];
  selectedProject: Project | null;
  selectedProjectId: string | null;
  isLoadingProjects: boolean;
  projectError: string | null;
  isProjectReady: boolean;
  selectProject: (projectId: string) => void;
  clearSelectedProject: (message?: string) => void;
  reloadProjects: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, refresh } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    () => localStorage.getItem(SELECTED_PROJECT_KEY),
  );
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );

  const clearSelectedProject = useCallback((message?: string) => {
    localStorage.removeItem(SELECTED_PROJECT_KEY);
    setSelectedProjectId(null);
    if (message) setProjectError(message);
  }, []);

  const selectProject = useCallback(
    (projectId: string) => {
      const projectExists = projects.some(
        (project) => project.id === projectId,
      );
      if (!projectExists) {
        clearSelectedProject(
          "That project is no longer available. Please choose another project.",
        );
        return;
      }
      localStorage.setItem(SELECTED_PROJECT_KEY, projectId);
      setSelectedProjectId(projectId);
      setProjectError(null);
    },
    [clearSelectedProject, projects],
  );

  const reloadProjects = useCallback(async () => {
    if (!isAuthenticated) {
      setProjects([]);
      clearSelectedProject();
      return;
    }

    setIsLoadingProjects(true);
    setProjectError(null);
    try {
      const accessibleProjects = await getUserProjects();
      setProjects(accessibleProjects);
      const storedProjectId = localStorage.getItem(SELECTED_PROJECT_KEY);
      if (
        storedProjectId &&
        !accessibleProjects.some((project) => project.id === storedProjectId)
      ) {
        clearSelectedProject(
          "Your previous project selection is no longer available.",
        );
      }
    } catch (error) {
      setProjects([]);
      clearSelectedProject(
        error instanceof ApiError && error.kind === "auth"
          ? undefined
          : getSafeApiErrorMessage(error),
      );
      if (error instanceof ApiError && error.kind === "auth") {
        await refresh();
      }
    } finally {
      setIsLoadingProjects(false);
    }
  }, [clearSelectedProject, isAuthenticated, refresh]);

  useEffect(() => {
    void reloadProjects();
  }, [reloadProjects]);

  const value = useMemo<ProjectContextType>(
    () => ({
      projects,
      selectedProject,
      selectedProjectId,
      isLoadingProjects,
      projectError,
      isProjectReady: Boolean(selectedProject),
      selectProject,
      clearSelectedProject,
      reloadProjects,
    }),
    [
      clearSelectedProject,
      isLoadingProjects,
      projectError,
      projects,
      reloadProjects,
      selectProject,
      selectedProject,
      selectedProjectId,
    ],
  );

  return (
    <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
  );
}

export function useProjectContext(): ProjectContextType {
  const context = useContext(ProjectContext);
  if (context === undefined) {
    throw new Error("useProjectContext must be used within a ProjectProvider");
  }
  return context;
}
