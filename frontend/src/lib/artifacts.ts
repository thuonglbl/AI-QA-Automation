/**
 * Typed client wrappers and interfaces for the artifact tree API.
 * Task 10.2 — replaces the flat artifact list with the folder-structured tree.
 */
import { apiFetch } from "@/lib/api";
import type { Artifact } from "@/components/conversations/ProjectSidebar";

/** A single browse folder from the tree API. */
export interface ArtifactTreeFolder {
  name: string;
  prefix: string | null;
  required: boolean;
  is_empty: boolean;
  /** Entries are typed as Artifact[] so they remain assignable to onSelectArtifact. */
  entries: Artifact[];
}

/** Full tree response from GET /projects/{id}/artifacts/tree. */
export interface ArtifactTree {
  project_id: string;
  folders: ArtifactTreeFolder[];
}

/**
 * Fetch the artifact tree for the given project.
 * Returns the 4 browse folders (requirements, test_cases, test_scripts, reports)
 * even when empty, with entries grouped by logical folder and creator/updater
 * display names resolved server-side.
 */
export async function fetchArtifactTree(projectId: string): Promise<ArtifactTree> {
  return apiFetch<ArtifactTree>(`/projects/${projectId}/artifacts/tree`);
}

/**
 * Create a new version of an artifact (edit).
 */
export async function updateArtifactContent(
  projectId: string,
  artifactId: string,
  content: string,
  encoding: "text" | "base64" = "text",
): Promise<Artifact> {
  return apiFetch<Artifact>(`/projects/${projectId}/artifacts/${artifactId}/versions`, {
    method: "POST",
    body: JSON.stringify({ content, content_encoding: encoding }),
  });
}

/**
 * Delete an artifact and all its versions.
 */
export async function deleteArtifact(projectId: string, artifactId: string): Promise<void> {
  return apiFetch<void>(`/projects/${projectId}/artifacts/${artifactId}`, {
    method: "DELETE",
  });
}
