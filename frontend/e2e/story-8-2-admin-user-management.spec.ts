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
    "Story 8.2 E2E needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
  );
}

type AdminUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
};

async function listAdminUsers(
  request: APIRequestContext,
  token: string,
): Promise<AdminUser[]> {
  const response = await request.get(`${apiBaseUrl}/api/admin/users`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<AdminUser[]>;
}

test.describe("Story 8.2 admin user management", () => {
  let createdUserEmails: string[] = [];

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.removeItem("ai-qa-selected-project-id");
      window.localStorage.removeItem("ai-qa-thread-id");
      window.localStorage.removeItem("ai-qa-thread-user-id");
      window.localStorage.removeItem("aiqa_access_token");
    });
  });

  test.afterEach(async ({ request }) => {
    if (createdUserEmails.length === 0) return;
    try {
      const adminToken = await getAdminToken();
      const users = await listAdminUsers(request, adminToken);
      for (const email of createdUserEmails) {
        const match = users.find((u) => u.email === email.toLowerCase());
        if (match) {
          await request.delete(`${apiBaseUrl}/api/admin/users/${match.id}`, {
            headers: { Authorization: `Bearer ${adminToken}` },
          });
        }
      }
    } catch (e) {
      console.error(`Cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      createdUserEmails = [];
    }
  });

  async function loginAsAdmin(page: import("@playwright/test").Page) {
    await page.goto("/");
    await page.getByLabel("Email").fill(adminEmail);
    await page.getByLabel("Password").fill(adminPassword as string);
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText(/admin dashboard/i)).toBeVisible({ timeout: 15_000 });
  }

  test("[P0][AC1][AC2] admin creates a user via the dashboard form and it appears in the Users Management list", async ({
    page,
  }) => {
    const uniqueEmail = `story-8-2-${Date.now()}-${Math.random().toString(36).slice(2)}@example.test`;
    createdUserEmails.push(uniqueEmail);

    await loginAsAdmin(page);

    await page.getByLabel("Email").fill(uniqueEmail);
    await page.getByLabel("Display Name").fill("Story 8.2 New User");
    await page.getByLabel("Role").selectOption("standard");
    await page.getByLabel("Initial Password").fill("initial-secret-8-2");
    await page.getByRole("button", { name: /create user/i }).click();

    // AC1: the new user shows up in the Users Management list with email + display name.
    // On success the create form is cleared, so these strings appear only in the user card.
    await expect(page.getByText(uniqueEmail)).toBeVisible();
    await expect(page.getByText("Story 8.2 New User")).toBeVisible();
  });

  test("[P0][AC2] submitting a duplicate email surfaces a safe error banner and creates no second user", async ({
    page,
    request,
  }) => {
    const uniqueEmail = `story-8-2-dup-${Date.now()}-${Math.random().toString(36).slice(2)}@example.test`;
    createdUserEmails.push(uniqueEmail);

    // Seed the user once via the real admin API so the UI submit is a true duplicate.
    const adminToken = await getAdminToken();
    const seed = await request.post(`${apiBaseUrl}/api/admin/users`, {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        email: uniqueEmail,
        display_name: "Story 8.2 Seed User",
        role: "standard",
        initial_password: "initial-secret-8-2",
      },
    });
    expect(seed.ok()).toBeTruthy();

    await loginAsAdmin(page);

    await page.getByLabel("Email").fill(uniqueEmail);
    await page.getByLabel("Display Name").fill("Story 8.2 Duplicate Attempt");
    await page.getByLabel("Role").selectOption("standard");
    await page.getByLabel("Initial Password").fill("initial-secret-8-2");
    await page.getByRole("button", { name: /create user/i }).click();

    // AC2: the dashboard surfaces a safe error without a false success message.
    await expect(
      page.getByText(/something went wrong\. please try again\./i),
    ).toBeVisible();
    await expect(
      page.getByText(/user created successfully/i),
    ).toBeHidden();

    // No second user was created for this email.
    const users = await listAdminUsers(request, adminToken);
    const matches = users.filter((u) => u.email === uniqueEmail.toLowerCase());
    expect(matches).toHaveLength(1);
  });
});
