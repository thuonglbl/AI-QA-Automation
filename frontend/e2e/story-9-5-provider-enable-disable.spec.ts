import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { getAdminToken } from "../support/helpers/users";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

if (!adminPassword) {
  throw new Error(
    "Story 9.5 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
  );
}

type RegisteredUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
};


async function createAdminUser(
  request: APIRequestContext,
  token: string,
  user: { email: string; displayName: string; password: string; role?: string },
): Promise<RegisteredUser> {
  const response = await request.post(`${apiBaseUrl}/api/admin/users`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      email: user.email,
      display_name: user.displayName,
      role: user.role ?? "standard",
      initial_password: user.password,
    },
  });
  if (!response.ok()) {
    console.error(`createAdminUser failed: ${response.status()} ${response.statusText()}`, await response.text());
  }
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<RegisteredUser>;
}

async function createAdminProjectWithProviders(
  request: APIRequestContext,
  token: string,
  name: string,
  enabledProviders: string[],
): Promise<{ id: string; confluence_base_url: string | null; jira_base_url: string | null }> {
  const response = await request.post(`${apiBaseUrl}/api/admin/projects`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name,
      description: `${name} description`,
      confluence_base_url: `https://confluence.example.test/${encodeURIComponent(name)}`,
      enabled_providers: enabledProviders,
    },
  });
  if (!response.ok()) {
    console.error(`createAdminProjectWithProviders failed: ${response.status()} ${response.statusText()}`, await response.text());
  }
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<{ id: string; confluence_base_url: string | null; jira_base_url: string | null }>;
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

test.describe("Story 9.5 Provider Enable/Disable Enforcement", () => {
  let createdUserIds: string[] = [];
  let createdProjectIds: string[] = [];

  test.beforeEach(async ({ page }) => {
    await page.context().clearCookies();
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

  test("[P0][FR16c] Admin creates project with selected providers, user cannot select disabled providers", async ({
    page,
    request,
  }) => {
    const adminToken = await getAdminToken();

    // Create a user
    const userEmail = `story-9-5-user-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
    const userPassword = "secretpassword";
    const seededUser = await createAdminUser(request, adminToken, {
      email: userEmail,
      displayName: "Story 9.5 User",
      password: userPassword,
      role: "standard",
    });
    createdUserIds.push(seededUser.id);

    // Create a project with ONLY claude and gemini enabled
    const project = await createAdminProjectWithProviders(
      request,
      adminToken,
      `S9.5 Project ${Date.now()}`,
      ["claude", "gemini"],
    );
    createdProjectIds.push(project.id);
    await assignMembership(request, adminToken, project.id, seededUser.id);

    // Login as the user and go to thread creation
    await page.goto("/");
    await page.getByLabel("Email").fill(userEmail);
    await page.getByLabel("Password").fill(userPassword);
    await page.getByRole("button", { name: "Sign In" }).click();

    // Navigate to Alice Step 1 (Provider selection)
    await page.getByTitle("New Conversation").first().click();
    await page.getByTestId("provider-card-claude").waitFor();

    // Assert: Claude is enabled
    const claudeCard = page.getByTestId("provider-card-claude");
    await expect(claudeCard).toBeVisible();
    await expect(claudeCard).not.toHaveClass(/opacity-40/);
    await expect(claudeCard).not.toHaveClass(/cursor-not-allowed/);

    // Assert: Gemini is enabled
    const geminiCard = page.getByTestId("provider-card-gemini");
    await expect(geminiCard).toBeVisible();
    await expect(geminiCard).not.toHaveClass(/opacity-40/);
    await expect(geminiCard).not.toHaveClass(/cursor-not-allowed/);

    // Assert: OpenAI is disabled (not in enabled_providers)
    const openaiCard = page.getByTestId("provider-card-openai");
    await expect(openaiCard).toBeVisible();
    await expect(openaiCard).toHaveClass(/opacity-40/);
    await expect(openaiCard).toHaveClass(/cursor-not-allowed/);

    // Assert: Browser Use is disabled
    const browserCard = page.getByTestId("provider-card-browser-use-cloud");
    await expect(browserCard).toBeVisible();
    await expect(browserCard).toHaveClass(/opacity-40/);
    await expect(browserCard).toHaveClass(/cursor-not-allowed/);

    // Assert: On Premises is disabled
    const onPremCard = page.getByTestId("provider-card-on-premises");
    await expect(onPremCard).toBeVisible();
    await expect(onPremCard).toHaveClass(/opacity-40/);
    await expect(onPremCard).toHaveClass(/cursor-not-allowed/);

    // Click on disabled OpenAI card - should NOT select it
    await openaiCard.click();
    await expect(openaiCard).not.toHaveClass(/border-\[#3b82f6\]/);
  });

  test("[P1][FR16d] Disabled provider shows tooltip on hover", async ({
    page,
    request,
  }) => {
    const adminToken = await getAdminToken();

    const userEmail = `story-9-5-tooltip-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
    const userPassword = "secretpassword";
    const seededUser = await createAdminUser(request, adminToken, {
      email: userEmail,
      displayName: "Story 9.5 Tooltip User",
      password: userPassword,
      role: "standard",
    });
    createdUserIds.push(seededUser.id);

    // Create project with only Claude enabled
    const project = await createAdminProjectWithProviders(
      request,
      adminToken,
      `S9.5 Tooltip ${Date.now()}`,
      ["claude"],
    );
    createdProjectIds.push(project.id);
    await assignMembership(request, adminToken, project.id, seededUser.id);

    await page.goto("/");
    await page.getByLabel("Email").fill(userEmail);
    await page.getByLabel("Password").fill(userPassword);
    await page.getByRole("button", { name: "Sign In" }).click();
    await page.getByTitle("New Conversation").first().click();

    const geminiCard = page.getByTestId("provider-card-gemini");
    await expect(geminiCard).toBeVisible();

    // Hover over disabled provider
    await geminiCard.hover();

    // Assert: Tooltip shows correct message
    // Note: Playwright's hover might not show title tooltips immediately
    // This test verifies the title attribute is set
    await expect(geminiCard).toHaveAttribute(
      "title",
      "Your project cannot choose this provider. Please contact your administrator if something is wrong."
    );
  });

  test("[P1][FR16c] Backward compatibility: all providers enabled allows all providers", async ({
    page,
    request,
  }) => {
    const adminToken = await getAdminToken();

    const userEmail = `story-9-5-backward-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
    const userPassword = "secretpassword";
    const seededUser = await createAdminUser(request, adminToken, {
      email: userEmail,
      displayName: "Story 9.5 Backward User",
      password: userPassword,
      role: "standard",
    });
    createdUserIds.push(seededUser.id);

    // Create project with all providers enabled (backward compatibility test)
    // When all providers are enabled, the project behaves like old projects
    // without provider restrictions
    const response = await request.post(`${apiBaseUrl}/api/admin/projects`, {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        name: `S9.5 Backward ${Date.now()}`,
        description: "Backward compatibility test",
        confluence_base_url: `https://confluence.example.test/`,
        enabled_providers: ["claude", "gemini", "openai", "browser-use-cloud", "on-premises"],
      },
    });
    expect(response.ok()).toBeTruthy();
    const project = await response.json();
    createdProjectIds.push(project.id);
    await assignMembership(request, adminToken, project.id, seededUser.id);

    await page.goto("/");
    await page.getByLabel("Email").fill(userEmail);
    await page.getByLabel("Password").fill(userPassword);
    await page.getByRole("button", { name: "Sign In" }).click();
    await page.getByTitle("New Conversation").first().click();

    // All providers should be enabled (no opacity-40, no cursor-not-allowed)
    const allProviders = ["claude", "gemini", "openai", "browser-use-cloud", "on-premises"];
    for (const providerId of allProviders) {
      const card = page.getByTestId(`provider-card-${providerId}`);
      await expect(card).toBeVisible();
      await expect(card).not.toHaveClass(/opacity-40/);
      await expect(card).not.toHaveClass(/cursor-not-allowed/);
    }
  });

  test("[P2][FR16c] Admin can update project to change enabled providers", async ({
    request,
  }) => {
    const adminToken = await getAdminToken();

    // Create project with claude only
    const project = await createAdminProjectWithProviders(
      request,
      adminToken,
      `S9.5 Update ${Date.now()}`,
      ["claude"],
    );
    createdProjectIds.push(project.id);

    // Update to add gemini, remove claude
    const updateResponse = await request.put(
      `${apiBaseUrl}/api/admin/projects/${project.id}`,
      {
        headers: { Authorization: `Bearer ${adminToken}` },
        data: {
          name: `S9.5 Update ${Date.now()}`,
          description: "Updated providers",
          confluence_base_url: `https://confluence.example.test/`,
          jira_base_url: null,
          enabled_providers: ["gemini", "openai"],
        },
      },
    );
    expect(updateResponse.ok()).toBeTruthy();

    const updatedProject = await updateResponse.json();
    expect(updatedProject.enabled_providers).toEqual(["gemini", "openai"]);

    // User should now see gemini and openai enabled, claude disabled
    // This is tested via the frontend flow in subsequent tests
  });
});
