import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { expect } from "@playwright/test";

/**
 * Helpers for working with EXISTING (real, pre-seeded) projects in the grouped
 * E2E suite.
 *
 * The flow groups (4–7) run against the two real projects configured in the
 * database — "PT Tool" and "PTP Personal Travel Plan" — because those carry the
 * real Confluence/Jira URLs and provider configuration the pipeline needs. The
 * suite never creates or deletes those projects; it looks them up by name and
 * attaches an ephemeral `@example.com` user to them. Deleting that user in
 * teardown cascades away the threads/runs/artifacts it generated (ON DELETE
 * CASCADE), leaving the real project untouched.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";

export const PROJECT_PT_TOOL = "PT Tool";
export const PROJECT_PTP = "PTP Personal Travel Plan";

export type ProjectRecord = {
  id: string;
  name: string;
  confluence_base_url: string | null;
  jira_base_url?: string | null;
  enabled_providers?: string[];
};

/**
 * Look up an existing project by its exact name.
 *
 * `GET /api/projects` returns ALL projects when called with an admin token
 * (see `api/projects.py::list_projects`), and each `ProjectResponse` carries
 * `confluence_base_url`, so this is enough to resolve the id + Confluence root.
 */
export async function getProjectByName(
  request: APIRequestContext,
  adminToken: string,
  name: string,
): Promise<ProjectRecord> {
  const response = await request.get(`${apiBaseUrl}/api/projects`, {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
  expect(response.ok()).toBeTruthy();
  const projects = (await response.json()) as ProjectRecord[];
  const match = projects.find((p) => p.name === name);
  if (!match) {
    throw new Error(
      `Project "${name}" not found. Available: ${projects.map((p) => p.name).join(", ")}`,
    );
  }
  return match;
}

/**
 * Attach a user to a project as a member. Treats an existing membership (409)
 * as success so re-running a group against the same real project is idempotent.
 */
export async function assignMembership(
  request: APIRequestContext,
  adminToken: string,
  projectId: string,
  userId: string,
): Promise<void> {
  const response = await request.post(
    `${apiBaseUrl}/api/admin/projects/${projectId}/memberships`,
    {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: { user_id: userId, role: "member" },
    },
  );
  expect(response.ok() || response.status() === 409).toBeTruthy();
}

/** Remove a user's membership from a project (best-effort; ignores 404). */
export async function removeMembership(
  request: APIRequestContext,
  adminToken: string,
  projectId: string,
  userId: string,
): Promise<void> {
  await request.delete(
    `${apiBaseUrl}/api/admin/projects/${projectId}/memberships/${userId}`,
    { headers: { Authorization: `Bearer ${adminToken}` } },
  );
}

/** Extract the numeric Confluence page id from a page URL (…/pages/<id>/…). */
export function confluencePageId(url: string): string {
  const m = url.match(/\/pages\/(\d+)(?:\/|$)/);
  if (!m) throw new Error(`No /pages/<id>/ in Confluence URL: ${url}`);
  return m[1]!;
}

/**
 * Fetch the user's threads and return the thread id bound to a given project,
 * so a multi-project group can activate the RIGHT project's starter thread.
 */
export async function threadIdForProject(
  request: APIRequestContext,
  userToken: string,
  projectId: string,
): Promise<string> {
  const response = await request.get(`${apiBaseUrl}/api/threads`, {
    headers: { Authorization: `Bearer ${userToken}` },
  });
  expect(response.ok()).toBeTruthy();
  const threads = (await response.json()) as Array<{
    id: string;
    project_id: string | null;
  }>;
  const match = threads.find((t) => t.project_id === projectId);
  if (!match) {
    throw new Error(`No starter thread bound to project ${projectId}.`);
  }
  return match.id;
}
