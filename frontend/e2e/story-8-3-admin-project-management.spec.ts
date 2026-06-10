import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { getAdminToken } from "../support/helpers/users";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminEmail =
  process.env.ADMIN_EMAIL ?? process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

if (!adminPassword) {
  throw new Error(
    "Story 8.3 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
  );
}

type AdminProject = {
  id: string;
  name: string;
  description: string | null;
};

type RegisteredUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
};

type AccessibleProject = {
  id: string;
  name: string;
};

type LoginResult = {
  access_token: string;
  user: RegisteredUser;
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
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<RegisteredUser>;
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

async function listAccessibleProjects(
  request: APIRequestContext,
  token: string,
): Promise<AccessibleProject[]> {
  const response = await request.get(`${apiBaseUrl}/api/projects`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<AccessibleProject[]>;
}

async function loginViaApi(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<string> {
  const response = await request.post(`${apiBaseUrl}/auth/login`, {
    data: { email, password },
  });
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as LoginResult).access_token;
}

test.describe("Story 8.3 admin project management", () => {
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
      // Delete projects first so membership cascades clean up before user delete.
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

  async function loginAsAdmin(page: import("@playwright/test").Page) {
    await page.goto("/");
    await page.getByLabel("Email").fill(adminEmail);
    await page.getByLabel("Password").fill(adminPassword as string);
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(/admin dashboard/i)).toBeVisible({ timeout: 15_000 });
  }

  test("[P0][AC1][AC2][AC3] admin creates a project, sees it in the Projects list, then renames it", async ({
    page,
    request,
  }) => {
    const projectName = `S8.3 Create ${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const renamedName = `${projectName} Renamed`;

    await loginAsAdmin(page);

      // AC2: fill the Create Project form (name + required Confluence Base URL) and submit.
    await page
      .getByLabel(/project name/i)
      .first()
      .fill(projectName);
    await page
      .getByLabel(/confluence base url/i)
      .fill(`https://confluence.example.test/${encodeURIComponent(projectName)}`);
    await page.getByRole("checkbox", { name: /Browser Use/i }).check();
    await page.getByRole("button", { name: /create project/i }).click();

    // AC1/AC2: success banner appears and the project shows up in the Projects list.
    await expect(
      page.getByText(/project created successfully/i),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole("button", { name: `Edit ${projectName}` }),
    ).toBeVisible();

    // Track for cleanup via the admin API.
    const adminToken = await getAdminToken();
    const projects = await listAccessibleProjects(request, adminToken);
    const created = projects.find((p) => p.name === projectName);
    expect(created).toBeDefined();
    if (created) createdProjectIds.push(created.id);

    // AC3: rename the project via the inline Edit form.
    await page.getByRole("button", { name: `Edit ${projectName}` }).click();
    const editNameInput = page.locator(`#edit-project-name-${created!.id}`);
    await editNameInput.fill(renamedName);
    await page.getByRole("button", { name: /^save$/i }).click();

    await expect(
      page.getByText(/project updated successfully/i),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: `Edit ${renamedName}` }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: `Edit ${projectName}`, exact: true }),
    ).toBeHidden();
  });

  test("[P0][AC4] admin deletes a project — it disappears from the dashboard and from an affected member's accessible list", async ({
    page,
    request,
  }) => {
    const adminToken = await getAdminToken();

    // Seed a standard user via the admin API (no reliance on self-service registration).
    const userEmail = `story-8-3-member-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
    const userPassword = "secretpassword";
    const seededUser = await createAdminUser(request, adminToken, {
      email: userEmail,
      displayName: "Story 8.3 Member User",
      password: userPassword,
      role: "standard",
    });
    createdUserIds.push(seededUser.id);

    // Seed a project + assign the member, all via the real admin API.
    const project = await createAdminProject(
      request,
      adminToken,
      `S8.3 Delete ${Date.now()}-${Math.random().toString(36).slice(2)}`,
    );
    createdProjectIds.push(project.id);
    await assignMembership(request, adminToken, project.id, seededUser.id);

    // Sanity check: the member can see the project before deletion.
    const memberToken = await loginViaApi(request, userEmail, userPassword);
    const memberListBefore = await listAccessibleProjects(request, memberToken);
    expect(memberListBefore.some((p) => p.id === project.id)).toBe(true);

    // Admin deletes the project from the dashboard UI.
    await loginAsAdmin(page);
    await expect(
      page.getByRole("button", { name: `Edit ${project.name}` }),
    ).toBeVisible();
    await page.getByRole("button", { name: `Delete ${project.name}` }).click();

    // AC4: the project disappears from the Projects list (success banner + edit button gone).
    await expect(
      page.getByText(/project deleted successfully/i),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: `Edit ${project.name}` }),
    ).toBeHidden();

    // AC4 cross-user clause: the affected member's accessible list no longer includes the project.
    const memberListAfter = await listAccessibleProjects(request, memberToken);
    expect(memberListAfter.some((p) => p.id === project.id)).toBe(false);

    // The project no longer needs admin cleanup — drop the tracking id.
    createdProjectIds = createdProjectIds.filter((id) => id !== project.id);
  });
});
