import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminEmail =
  process.env.ADMIN_EMAIL ?? process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

if (!adminPassword) {
  throw new Error(
    "Story 8.1 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
  );
}



type AdminProject = {
  id: string;
  name: string;
  description: string | null;
};

async function registerStandardUser(
  request: APIRequestContext,
  user: { email: string; displayName: string; password: string },
) {
  return createStandardUser(request, user);
}

async function createAdminProject(
  request: APIRequestContext,
  token: string,
  name: string,
): Promise<AdminProject> {
  const response = await request.post(`${apiBaseUrl}/api/admin/projects`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name,
      description: `${name} description`,
      confluence_base_url: `https://confluence.example.test/${encodeURIComponent(name)}`,
      enabled_providers: ["on-premises"],
    },
  });
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<AdminProject>;
}

async function assignMembership(
  request: APIRequestContext,
  token: string,
  projectId: string,
  userId: string,
) {
  const response = await request.post(
    `${apiBaseUrl}/api/admin/projects/${projectId}/memberships`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { user_id: userId, role: "member" },
    },
  );
  expect(response.ok()).toBeTruthy();
}

test.describe("Story 8.1 admin dashboard routing and access control", () => {
  let createdUserIds: string[] = [];
  let createdProjectIds: string[] = [];

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.removeItem("ai-qa-selected-project-id");
      window.localStorage.removeItem("ai-qa-thread-id");
      window.localStorage.removeItem("ai-qa-thread-user-id");
      window.localStorage.removeItem("aiqa_access_token");
    });
  });

  test.afterEach(async ({ request }) => {
    if (createdUserIds.length === 0 && createdProjectIds.length === 0) return;
    try {
      const adminToken = await getAdminToken();
      for (const projectId of createdProjectIds) {
        await request.delete(`${apiBaseUrl}/api/admin/projects/${projectId}`, {
          headers: { Authorization: `Bearer ${adminToken}` },
        });
      }
      for (const userId of createdUserIds) {
        await request.delete(`${apiBaseUrl}/api/admin/users/${userId}`, {
          headers: { Authorization: `Bearer ${adminToken}` },
        });
      }
    } catch (e) {
      console.error(`Cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      createdUserIds = [];
      createdProjectIds = [];
    }
  });

  test("[P0][AC1] admin logs in and is routed directly to the admin dashboard, bypassing the provider/chooser flow", async ({
    page,
  }) => {
    const adminToken = await getAdminToken();
    expect(adminToken).toBeTruthy();

    await page.goto("/");
    await page.getByLabel("Email").fill(adminEmail);
    await page.getByLabel("Password").fill(adminPassword as string);
    await page.getByRole("button", { name: "Sign In" }).click();

    // Admin lands on the dashboard; the standard workspace provider step and
    // the project chooser are never shown.
    await expect(page.getByText(/admin dashboard/i)).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeHidden();
    await expect(
      page.getByText("Please select one project to proceed"),
    ).toBeHidden();
  });

  test("[P0][AC2] a standard user navigating directly to /admin stays in the workspace shell and never sees the admin dashboard", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();

    const user = userFactory.create({
      email: `story-8-1-standard-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 8.1 Standard User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const project = await createAdminProject(
      request,
      adminToken,
      `S8.1 Member ${Date.now()}`,
    );
    createdProjectIds.push(project.id);
    await assignMembership(request, adminToken, project.id, registeredUser.id);

    // Log in as the standard user from the root page.
    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(user.displayName)).toBeVisible();

    // Now attempt to reach the admin dashboard directly via URL.
    await page.goto("/admin");

    // The render-switch SPA serves the same <App />, which falls through to the
    // workspace shell because role !== "admin". The admin dashboard must NOT
    // render; the standard workspace (Alice provider step) does.
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/admin dashboard/i)).toBeHidden();
    await expect(
      page.getByText("Please select one project to proceed"),
    ).toBeHidden();
  });

  test("[P1][AC2] a standard user with zero projects at /admin sees the no-access workspace message, not the admin dashboard", async ({
    page,
    request,
    userFactory,
  }) => {
    const user = userFactory.create({
      email: `story-8-1-zero-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 8.1 Zero Project User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(user.displayName)).toBeVisible();

    await page.goto("/admin");

    await expect(
      page.getByText(
        "You do not have access to any project yet. Please contact an administrator to assign you to a project.",
      ),
    ).toBeVisible();
    await expect(page.getByText(/admin dashboard/i)).toBeHidden();
  });
});
