import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectPicker } from "@/components/projects/ProjectPicker";

const selectProject = vi.fn();
const reloadProjects = vi.fn();
const clearSelectedProject = vi.fn();

vi.mock("@/hooks/useProject", () => ({
  useProject: vi.fn(() => ({
    projects: [],
    selectedProjectId: null,
    selectProject,
    isLoadingProjects: false,
    projectError: null,
    reloadProjects,
    selectedProject: null,
    isProjectReady: false,
    clearSelectedProject,
  })),
}));

const { useProject } = await import("@/hooks/useProject");

function project(overrides = {}) {
  return {
    id: "project-1",
    name: "Shared QA Project",
    description: "Collaborative project",
    confluence_base_url: "https://confluence.example.com",
    created_by_user_id: null,
    current_user_role: "member",
    membership_count: 2,
    memberships: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("ProjectPicker", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows accessible projects and allows selecting one", () => {
    vi.mocked(useProject).mockReturnValue({
      projects: [project()],
      selectedProjectId: null,
      selectProject,
      isLoadingProjects: false,
      projectError: null,
      reloadProjects,
      selectedProject: null,
      isProjectReady: false,
      clearSelectedProject,
    } as ReturnType<typeof useProject>);

    render(<ProjectPicker />);

    expect(
      screen.getByRole("heading", { name: /choose where this run belongs/i }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /shared qa project/i }));

    expect(selectProject).toHaveBeenCalledWith("project-1");
  });

  it("shows an empty state when the user has no projects", () => {
    vi.mocked(useProject).mockReturnValue({
      projects: [],
      selectedProjectId: null,
      selectProject,
      isLoadingProjects: false,
      projectError: null,
      reloadProjects,
      selectedProject: null,
      isProjectReady: false,
      clearSelectedProject,
    } as ReturnType<typeof useProject>);

    render(<ProjectPicker />);

    expect(
      screen.getByRole("heading", { name: /no projects assigned yet/i }),
    ).toBeInTheDocument();
  });
});
