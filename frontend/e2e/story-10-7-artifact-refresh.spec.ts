import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";

/**
 * Story 10.7 — Realtime Artifact Refresh UX (E2E).
 *
 * Validates that the artifact tree refreshes in response to WebSocket events
 * without disrupting the user's chat context. Tests the live backend→frontend
 * seam for artifact change events and project-scoped refresh behavior.
 *
 * project-context compliance:
 *   - No Mocking: hits the real backend + real WebSocket events (no page.route).
 *   - Data Cleanup: every created user/project is deleted via the admin API in
 *     afterEach (the user delete cascades to threads/agent_runs/messages).
 *   - Network-first: intercepts before navigate where possible.
 *   - Resilient selectors: getByRole, getByText, getByTestId.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

if (!adminPassword) {
  throw new Error(
    "Story 10.7 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
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

async function createArtifact(
  request: APIRequestContext,
  token: string,
  projectId: string,
  kind: string,
  name: string,
  content: string,
) {
  const response = await request.post(
    `${apiBaseUrl}/api/projects/${projectId}/artifacts`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { kind, name, content },
    },
  );
  expect(response.ok()).toBeTruthy();
  return response.json();
}

test.describe("Story 10.7 Realtime Artifact Refresh", () => {
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

  test("[P0] artifact tree refreshes on change event for the displayed project", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();
    const user = userFactory.create({
      email: `story-10-7-refresh-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 10.7 Refresh User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const project = await createAdminProject(
      request,
      adminToken,
      `S10.7 Refresh ${Date.now()}-${Math.random().toString(36).slice(2)}`,
    );
    createdProjectIds.push(project.id);
    await assignMembership(request, adminToken, project.id, registeredUser.id);

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
    await threadPost;

    // Wait for the project to be displayed in the sidebar
    await expect(page.getByText(project.name)).toBeVisible({ timeout: 15_000 });

    // See the artifact folders
    await expect(page.getByText(/Conversations/i).first()).toBeVisible();
    await expect(page.getByText(/Requirements/i).first()).toBeVisible();
    await expect(page.getByText(/Test Cases/i).first()).toBeVisible();
    await expect(page.getByText(/Scripts/i).first()).toBeVisible();
    await expect(page.getByText(/Reports/i).first()).toBeVisible();

    // Create an artifact via the API (simulating an external change)
    await createArtifact(
      request,
      adminToken,
      project.id,
      "requirements",
      "Test Requirement.md",
      "# Test Requirement\nThis is a test requirement.",
    );

    // The sidebar should refresh and show the new artifact
    await expect(page.getByText("Test Requirement.md")).toBeVisible({
      timeout: 15_000,
    });

    // Verify the artifact appears in the Requirements folder
    await expect(page.getByText(/Requirements/i).first()).toBeVisible();
  });

  test("[P0] chat state preserved during artifact tree refresh", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();
    const user = userFactory.create({
      email: `story-10-7-chatstate-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 10.7 ChatState User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    const project = await createAdminProject(
      request,
      adminToken,
      `S10.7 ChatState ${Date.now()}-${Math.random().toString(36).slice(2)}`,
    );
    createdProjectIds.push(project.id);
    await assignMembership(request, adminToken, project.id, registeredUser.id);

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

    // Wait for the project to be displayed
    await expect(page.getByText(project.name)).toBeVisible({ timeout: 15_000 });

    // Navigate to the provider selection step
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });

    // Verify the chat messages are visible (chat state)
    const chatArea = page.getByText(/Which AI provider would you like to use/i);
    await expect(chatArea).toBeVisible();

    // Create an artifact via the API (simulating an external change)
    await createArtifact(
      request,
      adminToken,
      project.id,
      "testcase",
      "Login Test Case.md",
      "# Login Test Case\nVerify login functionality.",
    );

    // Wait for the artifact tree to refresh
    await expect(page.getByText("Login Test Case.md")).toBeVisible({
      timeout: 15_000,
    });

    // CRITICAL: Verify chat state is preserved after refresh
    // The provider selection prompt should still be visible
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible();

    // The chat area should not have been reset
    // Verify the project name is still visible (sidebar state preserved)
    await expect(page.getByText(project.name)).toBeVisible();
  });

  test("[P0] non-active-thread project events handled without disrupting active chat", async ({
    page,
    request,
    userFactory,
  }) => {
    const adminToken = await getAdminToken();
    const user = userFactory.create({
      email: `story-10-7-nonactive-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 10.7 NonActive User",
      password: "secretpassword",
      role: "standard",
    });
    const registeredUser = await registerStandardUser(request, user);
    createdUserIds.push(registeredUser.id);

    // Create two projects
    const projectOne = await createAdminProject(
      request,
      adminToken,
      `S10.7 Proj One ${Date.now()}-${Math.random().toString(36).slice(2)}`,
    );
    createdProjectIds.push(projectOne.id);
    await assignMembership(request, adminToken, projectOne.id, registeredUser.id);

    const projectTwo = await createAdminProject(
      request,
      adminToken,
      `S10.7 Proj Two ${Date.now()}-${Math.random().toString(36).slice(2)}`,
    );
    createdProjectIds.push(projectTwo.id);
    await assignMembership(request, adminToken, projectTwo.id, registeredUser.id);

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
    await threadPost;

    // Wait for the projects to be displayed
    await expect(page.getByText(projectOne.name)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(projectTwo.name)).toBeVisible();

    // Verify we're on the provider selection step (active thread state)
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });

    // Create an artifact in projectTwo (non-active thread project)
    // This simulates another user or process updating a different project
    await createArtifact(
      request,
      adminToken,
      projectTwo.id,
      "report",
      "Test Report.md",
      "# Test Report\nGenerated test report.",
    );

    // Wait for the WebSocket event to be received
    // The UI should handle the event for the non-active project
    // without disrupting the current chat state

    // CRITICAL: The active thread's chat state should remain unchanged
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible();

    // The project names should still be visible in the sidebar
    await expect(page.getByText(projectOne.name)).toBeVisible();
    await expect(page.getByText(projectTwo.name)).toBeVisible();

    // The non-active project should show the artifact indicator
    // (the UI may update non-disruptive project artifact indicators only)
    // First expand projectTwo since multiple projects start collapsed
    await page.getByText(projectTwo.name).click();
    await expect(page.getByText("Test Report.md")).toBeVisible({
      timeout: 15_000,
    });
  });
});
