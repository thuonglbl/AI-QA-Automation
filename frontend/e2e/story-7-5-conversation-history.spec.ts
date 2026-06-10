import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

if (!adminPassword) {
  throw new Error(
    "Story 7.5 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
  );
}



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

test.describe("Story 7.5 Conversation History and Thread Resume", () => {
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

  test("[P0] should list user's conversation history and resume a thread", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();
    const user = userFactory.create({
      email: `story-7-5-user-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.5 User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const projectOne = await createAdminProject(
      request,
      adminToken,
      `S7.5 Proj One ${Date.now()}`,
    );
    createdProjectIds.push(projectOne.id);
    await assignMembership(
      request,
      adminToken,
      projectOne.id,
      registeredUser.id,
    );

    // Login
    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);

    const threadPost = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.endsWith("/api/threads") &&
        response.request().method() === "POST",
    );

    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(user.displayName)).toBeVisible({ timeout: 15_000 });

    // Wait for auto-created thread on initial login
    const threadResp = await threadPost;
    expect(threadResp.ok()).toBeTruthy();
    const firstThreadData = await threadResp.json();

    // Verify the "Projects" list replacing the old conversation history
    // Find the project row in the sidebar accordion
    const projectRow = page.getByText(projectOne.name).first();
    await expect(projectRow).toBeVisible();

    // Verify hover and quick create (+) button
    await projectRow.hover();
    const quickCreateBtn = page.getByRole("button", { name: /\+/ }).or(page.getByTitle(/New Conversation/i)).or(page.locator('[aria-label="New Conversation"]')).or(page.getByTestId(`quick-create-${projectOne.id}`)).first();
    await expect(quickCreateBtn).toBeVisible();

    // Expand the project folder to view contents
    // Verify categorized sub-folders are displayed (they are expanded by default)
    await expect(page.getByText(/Conversations/i).first()).toBeVisible();
    await expect(page.getByText(/Requirements/i).first()).toBeVisible();
    await expect(page.getByText(/Test Cases/i).first()).toBeVisible();
    await expect(page.getByText(/Scripts/i).first()).toBeVisible();
    await expect(page.getByText(/Reports/i).first()).toBeVisible();

    // Use the Quick create + button to explicitly create a conversation
    const quickThreadPost = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.endsWith("/api/threads") &&
        response.request().method() === "POST",
    );
    await projectRow.hover();
    await quickCreateBtn.click();
    const quickThreadResp = await quickThreadPost;
    expect(quickThreadResp.ok()).toBeTruthy();
    const quickThreadData = await quickThreadResp.json();

    // Expect the newly created thread to be visible in the Conversations list
    const threadLocator = page.getByTestId(`thread-${quickThreadData.id}`);
    await expect(threadLocator).toBeVisible();
    
    // Check for the Archive Conversation button (visible on hover)
    await threadLocator.hover();
    await expect(
      page.getByRole("button", { name: /Archive/i })
        .or(page.getByTitle(/Archive/i))
        .or(page.locator('[aria-label="Archive Conversation"]'))
        .first()
    ).toBeVisible();

    // Check for context menu option: Rename (Delete was intentionally dropped)
    await threadLocator.click({ button: "right" });
    await expect(page.getByText(/Rename/i).first()).toBeVisible();

    // Close the context menu
    await page.keyboard.press("Escape");
    
    // Resume a *different* (non-active) thread to genuinely exercise thread
    // resume. The quick-created thread is already the active thread, so
    // clicking it again would not change threadId and would not trigger a
    // reload. Resume the initial login thread instead.
    const resumeLocator = page
      .getByTestId(`thread-${firstThreadData.id}`);
    const threadGet = page.waitForResponse(
      (response) =>
        response.url().includes(`/api/threads/${firstThreadData.id}`) &&
        response.request().method() === "GET",
    );
    await resumeLocator.click();

    const getResp = await threadGet;
    expect(getResp.ok()).toBeTruthy();

    // Expect to be back on the thread view with the project context
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible();
  });
});
