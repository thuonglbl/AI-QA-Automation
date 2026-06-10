import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

if (!adminPassword) {
  throw new Error(
    "Story 7.3 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
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

test.describe("Story 7.3 Alice Agent Project Selection Logic", () => {
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

  test("[P0] should show no-access message and halt flow when user has zero accessible projects", async ({
    page,
    request,
    userFactory,
  }) => {
    // 1. Data Setup (No projects assigned)
    const user = userFactory.create({
      email: `story-7-3-zero-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.3 Zero Projects User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    // 2. Login
    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(user.displayName)).toBeVisible({ timeout: 15_000 });

    // 3. The app auto-creates a thread and runs Alice's project-selection flow
    // on login, so there is no separate "New Conversation" click in this state.

    // 4. Verification
    await expect(
      page.getByText(
        "You do not have access to any project yet. Please contact an administrator to assign you to a project.",
      ),
    ).toBeVisible();
    await expect(
      page.getByText(
        "Failed to initialize conversation thread. Please check your connection and try again.",
      ),
    ).not.toBeVisible();
  });

  test("[P0] should auto-bind project when user has exactly 1 accessible project", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();

    // 1. Data Setup (User + 1 Project)
    const user = userFactory.create({
      email: `story-7-3-one-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.3 One Project User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const projectOne = await createAdminProject(
      request,
      adminToken,
      `S7.3 Proj One ${Date.now()}-${Math.random().toString(36).slice(2)}`,
    );
    createdProjectIds.push(projectOne.id);
    await assignMembership(
      request,
      adminToken,
      projectOne.id,
      registeredUser.id,
    );

    // 2. Login
    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(user.displayName)).toBeVisible({ timeout: 15_000 });

    // 3. The app auto-creates a thread and runs Alice's project-selection flow
    // on login, so there is no separate "New Conversation" click in this state.

    // 4. Verification
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("[P0] should bind a thread per project and skip the chooser for multiple accessible projects (superseded by Story 7.7)", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();

    // 1. Data Setup (User + 2 Projects)
    const user = userFactory.create({
      email: `story-7-3-multiple-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.3 Multiple Projects User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const projectOne = await createAdminProject(
      request,
      adminToken,
      `S7.3 Proj One ${Date.now()}-${Math.random().toString(36).slice(2)}`,
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
      `S7.3 Proj Two ${Date.now()}-${Math.random().toString(36).slice(2)}`,
    );
    createdProjectIds.push(projectTwo.id);
    await assignMembership(
      request,
      adminToken,
      projectTwo.id,
      registeredUser.id,
    );

    // 2. Login
    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(user.displayName)).toBeVisible({ timeout: 15_000 });

    // 3. Story 7.7: the project chooser is removed. The app pre-creates one
    //    starter thread per accessible project and lands directly on Alice's
    //    provider step for the active thread's bound project.
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText("Please select one project to proceed"),
    ).toBeHidden();

    // 4. Both accessible projects are listed in the sidebar.
    await expect(page.getByText(projectOne.name)).toBeVisible();
    await expect(page.getByText(projectTwo.name)).toBeVisible();
  });
});
