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
    "Story 8.5 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
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
): Promise<void> {
  const response = await request.post(
    `${apiBaseUrl}/api/admin/projects/${projectId}/memberships`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { user_id: userId, role: "member" },
    },
  );
  expect(response.ok()).toBeTruthy();
}

test.describe("Story 8.5 admin dashboard UI layout", () => {
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

  test(
    "[P0][AC2][AC5] layout shows Projects on the left and Users Management + Create User on the right with disabled Sync button",
    async ({ page }) => {
      await loginAsAdmin(page);

      // Left column: Projects card heading + Create Project form
      await expect(page.getByText("Projects").first()).toBeVisible();
      await expect(page.getByRole("button", { name: /create project/i })).toBeVisible();

      // Right column: Users Management card heading
      await expect(page.getByText("Users Management")).toBeVisible();

      // Create User form fields (AC5)
      await expect(page.getByLabel("Email")).toBeVisible();
      await expect(page.getByLabel("Display Name")).toBeVisible();
      await expect(page.getByRole("combobox", { name: "Role" })).toBeVisible();
      await expect(page.getByLabel("Initial Password")).toBeVisible();

      // AC5: disabled Sync button + explanatory helper text
      const syncButton = page.getByRole("button", {
        name: "Sync existing company's users",
      });
      await expect(syncButton).toBeVisible();
      await expect(syncButton).toBeDisabled();
      await expect(
        page.getByText(
          "This feature is not available at the moment, please add manually.",
        ),
      ).toBeVisible();
    },
  );

  test(
    "[P0][AC1] nav shows admin email and role near Logout; clicking Logout returns to the login screen",
    async ({ page }) => {
      await loginAsAdmin(page);

      // Nav identity block: email is visible at the default 1280px viewport
      // (the block is hidden md:block — visible above 768px).
      const nav = page.getByRole("navigation");
      await expect(
        nav.getByText(adminEmail, { exact: false }),
      ).toBeVisible();
      const logoutButton = nav.getByRole("button", { name: "Logout" });
      await expect(logoutButton).toBeVisible();

      // Click Logout → session cleared → login form (Sign In button) reappears
      await logoutButton.click();
      await expect(
        page.getByRole("button", { name: "Sign In" }),
      ).toBeVisible();
    },
  );

  test(
    "[P0][AC3][AC4] user card shows assigned-project chip with × remove control and enabled assign select + button for the unassigned project",
    async ({ page, request }) => {
      const adminToken = await getAdminToken();

      // Seed a standard user + two projects via the real admin API.
      const userEmail = `story-8-5-user-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
      const userPassword = "secretpassword";
      const displayName = `S8.5 User ${Date.now()}`;
      const seededUser = await createAdminUser(request, adminToken, {
        email: userEmail,
        displayName,
        password: userPassword,
        role: "standard",
      });
      createdUserIds.push(seededUser.id);

      const assignedProject = await createAdminProject(
        request,
        adminToken,
        `S8.5 Assigned ${Date.now()}-${Math.random().toString(36).slice(2)}`,
      );
      createdProjectIds.push(assignedProject.id);

      const unassignedProject = await createAdminProject(
        request,
        adminToken,
        `S8.5 Unassigned ${Date.now()}-${Math.random().toString(36).slice(2)}`,
      );
      createdProjectIds.push(unassignedProject.id);

      // Assign one project to the user so the chip is present and one remains assignable.
      await assignMembership(
        request,
        adminToken,
        assignedProject.id,
        seededUser.id,
      );

      await loginAsAdmin(page);

      // AC3: the assigned-project chip renders with its × remove control
      await expect(
        page.getByRole("button", {
          name: `Remove ${assignedProject.name} from ${displayName}`,
        }),
      ).toBeVisible();

      // AC4: the per-user select combobox and assign (+) button are visible and
      // enabled because one unassigned project still exists for this user.
      const projectSelect = page.getByRole("combobox", {
        name: `Select project for ${displayName}`,
      });
      await expect(projectSelect).toBeVisible();
      await expect(projectSelect).toBeEnabled();

      const assignButton = page.getByRole("button", {
        name: `Assign project to ${displayName}`,
      });
      await expect(assignButton).toBeVisible();
      await expect(assignButton).toBeEnabled();
    },
  );
});
