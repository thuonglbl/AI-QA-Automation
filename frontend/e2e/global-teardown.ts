import process from "node:process";
import { request as playwrightRequest } from "@playwright/test";
import type { FullConfig } from "@playwright/test";

/**
 * Global teardown: sweep ALL leftover E2E test data after the whole suite runs.
 *
 * Per-spec `afterEach` hooks only delete IDs captured during a passing test, and
 * they silently no-op when a test crashes mid-body, a worker dies, or the
 * starter-thread bootstrap creates threads in the browser after cleanup already
 * ran. Those orphaned test users keep their threads / agent_runs / messages
 * alive (FK ON DELETE CASCADE means deleting the user removes them all).
 *
 * This teardown is the safety net: it logs in as the admin, then deletes every
 * user and project whose identifier matches a known test pattern. Deleting a
 * test user cascades to its threads, agent_runs, messages, artifacts and audit
 * events; deleting a test project cleans up its memberships and any remaining
 * bound threads.
 *
 * SAFETY: it never deletes the admin account it authenticated with, never
 * deletes any `admin`-role user, and only matches synthetic test identifiers
 * (`@example.com` / `@example.test` emails, `S<n>...` / `Story <n>...` project
 * names). Real accounts and real projects are left untouched.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminEmail =
  process.env.ADMIN_EMAIL ?? process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

// Synthetic test emails registered by the specs.
const TEST_EMAIL_PATTERN = /@example\.(com|test)$/i;
// Synthetic test project names, e.g. "S7.7 Solo ...", "Story 7.2 Assigned ...".
const TEST_PROJECT_NAME_PATTERN = /^(S\d|Story \d)/;

type AdminUser = { id: string; email: string; role: string };
type AdminProject = { id: string; name: string };

export default async function globalTeardown(_config: FullConfig): Promise<void> {
  if (!adminPassword) {
    console.warn(
      "[e2e teardown] No ADMIN_PASSWORD/E2E_ADMIN_PASSWORD set — skipping test-data cleanup.",
    );
    return;
  }

  const context = await playwrightRequest.newContext();
  try {
    const loginResponse = await context.post(`${apiBaseUrl}/auth/login`, {
      data: { email: adminEmail, password: adminPassword },
    });
    if (!loginResponse.ok()) {
      console.warn(
        `[e2e teardown] Admin login failed (${loginResponse.status()}) — skipping cleanup.`,
      );
      return;
    }
    const adminToken = (await loginResponse.json()).access_token as string;
    const authHeaders = { Authorization: `Bearer ${adminToken}` };

    // 1) Delete test users (cascades to their threads / agent_runs / messages).
    let deletedUsers = 0;
    const usersResponse = await context.get(`${apiBaseUrl}/api/admin/users`, {
      headers: authHeaders,
    });
    if (usersResponse.ok()) {
      const users = (await usersResponse.json()) as AdminUser[];
      for (const user of users) {
        const isTestUser = TEST_EMAIL_PATTERN.test(user.email);
        const isProtected =
          user.role === "admin" || user.email === adminEmail;
        if (!isTestUser || isProtected) continue;

        const del = await context.delete(
          `${apiBaseUrl}/api/admin/users/${user.id}`,
          { headers: authHeaders },
        );
        if (del.ok() || del.status() === 404) deletedUsers += 1;
      }
    } else {
      console.warn(
        `[e2e teardown] Could not list users (${usersResponse.status()}).`,
      );
    }

    // 2) Delete test projects (cleans memberships + any remaining bound threads).
    let deletedProjects = 0;
    const projectsResponse = await context.get(`${apiBaseUrl}/api/projects`, {
      headers: authHeaders,
    });
    if (projectsResponse.ok()) {
      const projects = (await projectsResponse.json()) as AdminProject[];
      for (const project of projects) {
        if (!TEST_PROJECT_NAME_PATTERN.test(project.name)) continue;

        const del = await context.delete(
          `${apiBaseUrl}/api/admin/projects/${project.id}`,
          { headers: authHeaders },
        );
        if (del.ok() || del.status() === 404) deletedProjects += 1;
      }
    } else {
      console.warn(
        `[e2e teardown] Could not list projects (${projectsResponse.status()}).`,
      );
    }

    console.log(
      `[e2e teardown] Removed ${deletedUsers} test user(s) and ${deletedProjects} test project(s).`,
    );
  } catch (error) {
    // Never fail the run because of teardown noise; just report it.
    console.warn("[e2e teardown] Cleanup encountered an error:", error);
  } finally {
    await context.dispose();
  }
}
