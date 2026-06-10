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
    "Story 7.7 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
  );
}

type RegisteredUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
};

type LoginResult = {
  access_token: string;
  user: RegisteredUser;
};

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

test.describe("Story 7.7 standard user workspace shell routing", () => {
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

  test("[P0][AC1][AC2][AC3] single-project user lands directly in the workspace shell on a bound thread (no chooser)", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();

    const user = userFactory.create({
      email: `story-7-7-one-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.7 One Project User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const project = await createAdminProject(
      request,
      adminToken,
      `S7.7 Solo ${Date.now()}`,
    );
    createdProjectIds.push(project.id);
    await assignMembership(request, adminToken, project.id, registeredUser.id);

    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(user.displayName)).toBeVisible();

    // Lands directly on Alice's provider step for the bound thread. No chooser.
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText("Please select one project to proceed"),
    ).toBeHidden();
    // The bound project is shown in the sidebar (implicit project context).
    await expect(page.getByText(project.name)).toBeVisible();

    // The starter thread persists across reloads: the workspace shell, not the
    // chooser, comes back. AC3 (project implicit from active thread).
    await page.reload();
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText("Please select one project to proceed"),
    ).toBeHidden();
  });

  test("[P0][AC2][AC3] multi-project user gets one starter thread per project and never sees the chooser", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();

    const user = userFactory.create({
      email: `story-7-7-multi-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.7 Multi Project User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const projectOne = await createAdminProject(
      request,
      adminToken,
      `S7.7 Proj One ${Date.now()}`,
    );
    createdProjectIds.push(projectOne.id);
    await assignMembership(
      request,
      adminToken,
      projectOne.id,
      registeredUser.id,
    );

    const projectTwo = await createAdminProject(
      request,
      adminToken,
      `S7.7 Proj Two ${Date.now()}`,
    );
    createdProjectIds.push(projectTwo.id);
    await assignMembership(
      request,
      adminToken,
      projectTwo.id,
      registeredUser.id,
    );

    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(user.displayName)).toBeVisible();

    // No chooser, direct to provider step.
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText("Please select one project to proceed"),
    ).toBeHidden();

    // Both accessible projects are present in the sidebar.
    await expect(page.getByText(projectOne.name)).toBeVisible();
    await expect(page.getByText(projectTwo.name)).toBeVisible();

    // The backend has exactly one thread per accessible project for this user.
    const userLogin = await request.post(`${apiBaseUrl}/auth/login`, {
      data: { email: user.email, password: user.password },
    });
    expect(userLogin.ok()).toBeTruthy();
    const token = ((await userLogin.json()) as LoginResult).access_token;
    const threadsResponse = await request.get(`${apiBaseUrl}/api/threads`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(threadsResponse.ok()).toBeTruthy();
    const threads = (await threadsResponse.json()) as Array<{
      project_id: string | null;
    }>;
    const boundProjectIds = threads
      .map((t) => t.project_id)
      .filter((id): id is string => Boolean(id));
    expect(boundProjectIds).toContain(projectOne.id);
    expect(boundProjectIds).toContain(projectTwo.id);
    // Exactly one thread per project (no duplicates from the bootstrap).
    expect(
      boundProjectIds.filter((id) => id === projectOne.id),
    ).toHaveLength(1);
    expect(
      boundProjectIds.filter((id) => id === projectTwo.id),
    ).toHaveLength(1);
  });

  test("[P0][AC4] zero-project user sees the no-access message and no thread is created", async ({
    page,
    request,
    userFactory,
  }) => {
    const user = userFactory.create({
      email: `story-7-7-zero-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.7 Zero Project User",
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

    await expect(
      page.getByText(
        "You do not have access to any project yet. Please contact an administrator to assign you to a project.",
      ),
    ).toBeVisible();
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeHidden();

    // No starter thread is created for a user with no accessible projects.
    const userLogin = await request.post(`${apiBaseUrl}/auth/login`, {
      data: { email: user.email, password: user.password },
    });
    expect(userLogin.ok()).toBeTruthy();
    const token = ((await userLogin.json()) as LoginResult).access_token;
    const threadsResponse = await request.get(`${apiBaseUrl}/api/threads`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(threadsResponse.ok()).toBeTruthy();
    expect(await threadsResponse.json()).toEqual([]);
  });

  test("[P0][AC5] admin user is routed to the admin dashboard, bypassing the workspace shell", async ({
    page,
  }) => {
    const adminToken = await getAdminToken();
    expect(adminToken).toBeTruthy();

    await page.goto("/");
    await page.getByLabel("Email").fill(adminEmail);
    await page.getByLabel("Password").fill(adminPassword as string);
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText(/admin dashboard/i)).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeHidden();
    await expect(
      page.getByText("Please select one project to proceed"),
    ).toBeHidden();
  });
});
