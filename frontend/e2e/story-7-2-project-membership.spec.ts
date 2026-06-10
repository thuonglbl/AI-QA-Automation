import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

if (!adminPassword) {
  throw new Error(
    "Story 7.2 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
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

async function login(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<LoginResult> {
  const response = await request.post(`${apiBaseUrl}/auth/login`, {
    data: { email, password },
  });
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<LoginResult>;
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

test.describe("Story 7.2 project membership access for standard users", () => {
  let createdUserIds: string[] = [];
  let createdProjectIds: string[] = [];

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.removeItem("ai-qa-selected-project-id");
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

  test("standard user sees only active assigned projects from the real backend", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();
    const user = userFactory.create({
      email: `story-7-2-member-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.2 Member",
      password: "member-secret-7-2",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const assignedProject = await createAdminProject(
      request,
      adminToken,
      `Story 7.2 Assigned ${Date.now()}`,
    );
    createdProjectIds.push(assignedProject.id);
    const hiddenProject = await createAdminProject(
      request,
      adminToken,
      `Story 7.2 Hidden ${Date.now()}`,
    );
    createdProjectIds.push(hiddenProject.id);
    await assignMembership(
      request,
      adminToken,
      assignedProject.id,
      registeredUser.id,
    );

    const userLogin = await login(request, user.email, user.password);
    const projectsResponse = await request.get(`${apiBaseUrl}/api/projects`, {
      headers: { Authorization: `Bearer ${userLogin.access_token}` },
    });
    expect(projectsResponse.ok()).toBeTruthy();
    const apiProjects = await projectsResponse.json();
    const visibleNames = apiProjects.map(
      (project: { name: string }) => project.name,
    );
    expect(visibleNames).toContain(assignedProject.name);
    expect(visibleNames).not.toContain(hiddenProject.name);
    expect(JSON.stringify(apiProjects)).not.toContain("password_hash");
    expect(
      apiProjects.find(
        (project: { id: string }) => project.id === assignedProject.id,
      ).memberships,
    ).toEqual([]);

    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText(user.displayName)).toBeVisible();
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(hiddenProject.name)).toBeHidden();
  });

  test("standard user with zero projects gets an empty list and sees the no-access state", async ({
    page,
    request,
    userFactory,
  }) => {
    const user = userFactory.create({
      email: `story-7-2-empty-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.2 Empty",
      password: "empty-secret-7-2",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);
    const userLogin = await login(request, user.email, user.password);

    const projectsResponse = await request.get(`${apiBaseUrl}/api/projects`, {
      headers: { Authorization: `Bearer ${userLogin.access_token}` },
    });
    expect(projectsResponse.ok()).toBeTruthy();
    expect(await projectsResponse.json()).toEqual([]);

    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText(user.displayName)).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText(
        "You do not have access to any project yet. Please contact an administrator to assign you to a project.",
      ),
    ).toBeVisible();
  });

  test("unauthenticated project list requests are rejected by the real backend", async ({
    request,
  }) => {
    const response = await request.get(`${apiBaseUrl}/api/projects`);
    expect(response.status()).toBe(401);
    expect((await response.json()).detail).toBe("Not authenticated");
  });
});
