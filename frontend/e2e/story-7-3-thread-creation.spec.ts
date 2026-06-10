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
) {
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
  return response.json();
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

test.describe("Story 7.3 Thread Creation and RBAC", () => {
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

  test("[P0] should create a new thread via New Conversation button", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();
    const user = userFactory.create({
      email: `story-7-3-thread-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.3 User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const projectOne = await createAdminProject(
      request,
      adminToken,
      `S7.3 Proj One ${Date.now()}`,
    );
    createdProjectIds.push(projectOne.id);
    await assignMembership(
      request,
      adminToken,
      projectOne.id,
      registeredUser.id,
    );

    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);

    // Setup request interception to wait for the thread creation
    const threadPost1 = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.endsWith("/api/threads") &&
        response.request().method() === "POST",
    );

    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(user.displayName)).toBeVisible({ timeout: 15_000 });

    // The app auto creates a thread on login if user has a project.
    await threadPost1;

    // Now click "New Conversation" to create a fresh one
    const threadPost2 = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.endsWith("/api/threads") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "New Conversation" }).click();

    const response2 = await threadPost2;
    expect(response2.ok()).toBeTruthy();

    // UI should reset
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible();
  });

  test("[P2] should deny access to threads owned by other users via API", async ({
    request,
    userFactory,
  }) => {
    // Setup User A (owner)
    const userA = userFactory.create({
      email: `story-7-3-usera-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "User A",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUserA = await registerStandardUser(request, userA);
    createdUserIds.push(registeredUserA.id);

    // Setup User B (attacker)
    const userB = userFactory.create({
      email: `story-7-3-userb-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "User B",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUserB = await registerStandardUser(request, userB);
    createdUserIds.push(registeredUserB.id);

    // Create a thread using User A's API token
    const userALogin = await login(request, userA.email, userA.password);
    const threadResponse = await request.post(`${apiBaseUrl}/api/threads`, {
      headers: { Authorization: `Bearer ${userALogin.access_token}` },
      data: { user_id: registeredUserA.id },
    });
    expect(threadResponse.ok()).toBeTruthy();
    const threadData = await threadResponse.json();
    const threadId = threadData.id;

    // Try to access User A's thread using User B's API token
    const userBLogin = await login(request, userB.email, userB.password);
    const accessResponse = await request.get(
      `${apiBaseUrl}/api/threads/${threadId}/conversation`,
      {
        headers: { Authorization: `Bearer ${userBLogin.access_token}` },
      },
    );

    // Should be denied (Forbidden)
    expect(accessResponse.status()).toBe(403);
  });
});
