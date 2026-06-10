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
    "Story 8.4 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
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

test.describe("Story 8.4 project membership assignment", () => {
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

  test("[P0][AC1][AC2] admin assigns a project to a user — chip appears, the option leaves the per-user select, and the member can see it", async ({
    page,
    request,
  }) => {
    const adminToken = await getAdminToken();

    // Seed a standard user + a project via the real admin API (no self-service registration).
    const userEmail = `story-8-4-member-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
    const userPassword = "secretpassword";
    const displayName = "Story 8.4 Assign User";
    const seededUser = await createAdminUser(request, adminToken, {
      email: userEmail,
      displayName,
      password: userPassword,
      role: "standard",
    });
    createdUserIds.push(seededUser.id);

    const project = await createAdminProject(
      request,
      adminToken,
      `S8.4 Assign ${Date.now()}-${Math.random().toString(36).slice(2)}`,
    );
    createdProjectIds.push(project.id);

    // Sanity check: before assignment the member sees no projects.
    const memberToken = await loginViaApi(request, userEmail, userPassword);
    const memberListBefore = await listAccessibleProjects(request, memberToken);
    expect(memberListBefore.some((p) => p.id === project.id)).toBe(false);

    // Admin assigns the project from the dashboard UI.
    await loginAsAdmin(page);

    const projectSelect = page.getByRole("combobox", {
      name: `Select project for ${displayName}`,
    });
    await expect(projectSelect).toBeVisible();
    await projectSelect.selectOption({ label: project.name });
    await page
      .getByRole("button", { name: `Assign project to ${displayName}` })
      .click();

    // AC1: success banner + the project chip appears under the user's Projects section.
    await expect(
      page.getByText(/project assigned successfully/i),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: `Remove ${project.name} from ${displayName}`,
      }),
    ).toBeVisible();

    // AC2 UI duplicate guard: the assigned project is no longer an option in the same select.
    await expect(
      projectSelect.getByRole("option", { name: project.name }),
    ).toHaveCount(0);

    // AC1 round-trip: the member's accessible-project list now includes the project.
    const memberListAfter = await listAccessibleProjects(request, memberToken);
    expect(memberListAfter.some((p) => p.id === project.id)).toBe(true);
  });

  test("[P0][AC3] admin removes a user from a project — chip disappears, the option returns, and the member loses access", async ({
    page,
    request,
  }) => {
    const adminToken = await getAdminToken();

    // Seed a standard user + project, then assign membership via the real admin API.
    const userEmail = `story-8-4-remove-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
    const userPassword = "secretpassword";
    const displayName = "Story 8.4 Remove User";
    const seededUser = await createAdminUser(request, adminToken, {
      email: userEmail,
      displayName,
      password: userPassword,
      role: "standard",
    });
    createdUserIds.push(seededUser.id);

    const project = await createAdminProject(
      request,
      adminToken,
      `S8.4 Remove ${Date.now()}-${Math.random().toString(36).slice(2)}`,
    );
    createdProjectIds.push(project.id);

    const assignResponse = await request.post(
      `${apiBaseUrl}/api/admin/projects/${project.id}/memberships`,
      {
        headers: { Authorization: `Bearer ${adminToken}` },
        data: { user_id: seededUser.id, role: "member" },
      },
    );
    expect(assignResponse.ok()).toBeTruthy();

    // Sanity check: the member can see the project before removal.
    const memberToken = await loginViaApi(request, userEmail, userPassword);
    const memberListBefore = await listAccessibleProjects(request, memberToken);
    expect(memberListBefore.some((p) => p.id === project.id)).toBe(true);

    // Admin removes the membership from the dashboard UI via the chip "×".
    await loginAsAdmin(page);
    const removeButton = page.getByRole("button", {
      name: `Remove ${project.name} from ${displayName}`,
    });
    await expect(removeButton).toBeVisible();
    await removeButton.click();

    // AC3: success banner + the chip is gone.
    await expect(
      page.getByText(/project unassigned successfully/i),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: `Remove ${project.name} from ${displayName}`,
      }),
    ).toBeHidden();

    // The project re-appears as an option in the per-user select.
    const projectSelect = page.getByRole("combobox", {
      name: `Select project for ${displayName}`,
    });
    await expect(
      projectSelect.getByRole("option", { name: project.name }),
    ).toHaveCount(1, { timeout: 10_000 });

    // AC3 round-trip: the member's accessible-project list no longer includes the project.
    const memberListAfter = await listAccessibleProjects(request, memberToken);
    expect(memberListAfter.some((p) => p.id === project.id)).toBe(false);
  });
});
