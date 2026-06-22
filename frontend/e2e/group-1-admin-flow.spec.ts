import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { getAdminToken } from "../support/helpers/users";

/**
 * Group 1 — Admin ⇄ Project-Admin lifecycle (login once per role, walk the whole
 * cross-dashboard journey).
 *
 * A single serial journey that switches logins three times to cover the full
 * project-admin lifecycle the way an operator actually drives it:
 *
 *   1. Platform admin (pre-seeded) signs in → Admin Dashboard. Creates a project,
 *      renames it, then creates a project-admin (linked to that project) and a
 *      standard user.
 *   2. The project-admin from step 1 signs in → Project Admin Dashboard. Fills the
 *      project config (Confluence URL, a provider, an environment, an app role),
 *      adds a test-login account, and assigns the standard user as a member.
 *   3. The project-admin removes the standard member, then logs out.
 *   4. The platform admin signs back in → Admin Dashboard. Deletes both users
 *      created in step 1, then deletes the project created in step 1.
 *
 * Config/membership live on the Project Admin Dashboard (project-admin API); the
 * platform admin only owns a project's name + description and the user roster.
 *
 * Cleanup: every user/project created here is `@example.com` / `S1 …` named and
 * removed via the admin API in afterAll (also swept by global-teardown).
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminEmail =
  process.env.ADMIN_EMAIL ?? process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

function uniqueSuffix(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

test.describe.serial("Group 1 — Admin ⇄ Project-Admin lifecycle", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let adminToken: string;

  // Identifiers minted once in beforeAll and reused across the serial steps.
  let projectName = "";
  let renamedName = "";
  let projectId = "";
  let paEmail = "";
  let paDisplayName = "";
  let stdEmail = "";
  let stdDisplayName = "";
  // Created-user passwords need ≥ 8 chars (Create User form `minLength`).
  const paPassword = "pa-secret-123";
  const stdPassword = "std-secret-123";

  const createdUserEmails: string[] = [];
  const createdProjectIds: string[] = [];

  /** Sign in via the visible login form (caller asserts the landing dashboard). */
  async function signIn(email: string, password: string): Promise<void> {
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Sign In" }).click();
  }

  /** Log the current user out and wait for the login form to render. */
  async function logoutCurrent(): Promise<void> {
    await page.getByRole("button", { name: "Logout" }).click();
    await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible({
      timeout: 15_000,
    });
  }

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");

    adminToken = await getAdminToken();
    adminCtx = await playwrightRequest.newContext();

    const suffix = uniqueSuffix();
    projectName = `S1 PA-Flow ${suffix}`;
    renamedName = `${projectName} (edited)`;
    // Created users must use a login-capable domain: the create-user API accepts
    // any string email, but POST /auth/login validates EmailStr (email-validator),
    // which rejects the reserved `.test` TLD with a 422. `@example.com` is accepted
    // and is still swept by global-teardown's @example.(com|test) pattern.
    paEmail = `g1-padmin-${suffix}@example.com`;
    paDisplayName = `G1 Project Admin ${suffix}`;
    stdEmail = `g1-standard-${suffix}@example.com`;
    stdDisplayName = `G1 Standard User ${suffix}`;

    page = await browser.newPage();
    await page.goto("/");
    await signIn(adminEmail, adminPassword as string);
    await expect(
      page.getByRole("heading", { name: "Admin Dashboard", exact: true }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test.afterAll(async () => {
    // Safety net: any step may have failed mid-flow before its UI delete ran.
    // Deleting via the admin API is idempotent (404 == already gone).
    try {
      const usersResponse = await adminCtx.get(`${apiBaseUrl}/api/admin/users`, {
        headers: { Authorization: `Bearer ${adminToken}` },
      });
      if (usersResponse.ok()) {
        const users = (await usersResponse.json()) as Array<{ id: string; email: string }>;
        for (const email of createdUserEmails) {
          const match = users.find((u) => u.email === email.toLowerCase());
          if (match) {
            await adminCtx.delete(`${apiBaseUrl}/api/admin/users/${match.id}`, {
              headers: { Authorization: `Bearer ${adminToken}` },
            });
          }
        }
      }
      for (const id of createdProjectIds) {
        await adminCtx.delete(`${apiBaseUrl}/api/admin/projects/${id}`, {
          headers: { Authorization: `Bearer ${adminToken}` },
        });
      }
    } catch (e) {
      console.error(`Group 1 cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      if (adminCtx) await adminCtx.dispose();
      if (page) await page.close();
    }
  });

  test("[P0] step 1 — admin creates & renames a project, then creates a project-admin and a standard user", async () => {
    // --- Create the project (admin owns name + description only). ---
    await page.locator("#admin-project-name").fill(projectName);
    await page.locator("#create-project-button").click();
    await expect(page.getByText("Project created successfully.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByRole("button", { name: `Edit ${projectName}` }),
    ).toBeVisible();

    // Resolve the new project's id for cleanup + the inline edit-form locator.
    const list = await adminCtx.get(`${apiBaseUrl}/api/projects`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    const projects = (await list.json()) as Array<{ id: string; name: string }>;
    const created = projects.find((p) => p.name === projectName);
    expect(created).toBeTruthy();
    projectId = created!.id;
    createdProjectIds.push(projectId);

    // --- Rename it via the project's inline edit form. The dashboard has many
    // "Save" buttons (per-user rows etc.), so scope to this project's <form>. ---
    await page.getByRole("button", { name: `Edit ${projectName}` }).click();
    const editForm = page.locator("form", {
      has: page.locator(`#edit-project-name-${projectId}`),
    });
    await editForm.locator(`#edit-project-name-${projectId}`).fill(renamedName);
    await editForm.getByRole("button", { name: /^save$/i }).click();
    await expect(page.getByText("Project updated successfully.")).toBeVisible();
    await expect(
      page.getByRole("button", { name: `Edit ${renamedName}` }),
    ).toBeVisible();

    // --- Create a project-admin linked to the (renamed) project. ---
    await page.locator("#create-user-email").fill(paEmail);
    await page.locator("#create-user-display-name").fill(paDisplayName);
    await page.locator("#create-user-role").selectOption("project_admin");
    // The project picker only renders once the role is project_admin.
    await page.locator("#create-user-project").selectOption({ label: renamedName });
    await page.locator("#create-user-password").fill(paPassword);
    createdUserEmails.push(paEmail);
    await page.locator("#create-user-button").click();
    await expect(page.getByText("User created successfully.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(paEmail)).toBeVisible();

    // --- Create a standard user. ---
    await page.locator("#create-user-email").fill(stdEmail);
    await page.locator("#create-user-display-name").fill(stdDisplayName);
    await page.locator("#create-user-role").selectOption("standard");
    await page.locator("#create-user-password").fill(stdPassword);
    createdUserEmails.push(stdEmail);
    await page.locator("#create-user-button").click();
    await expect(page.getByText("User created successfully.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(stdEmail)).toBeVisible();
  });

  test("[P0] step 2 — project-admin signs in, configures the project, adds an account, and assigns the standard user", async () => {
    await logoutCurrent();
    await signIn(paEmail, paPassword);
    await expect(
      page.getByRole("heading", { name: "Project Admin Dashboard", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // The single administered project is auto-selected; its config form renders.
    const confluence = page.getByPlaceholder("https://confluence.company.com");
    await expect(confluence).toBeVisible({ timeout: 15_000 });
    await confluence.fill(`https://confluence.example.test/${projectId}`);

    // Enable a provider (config requires ≥ 1).
    await page.getByRole("checkbox", { name: "On Premises" }).check();

    // Add one target environment (name + URL row).
    await page.getByRole("button", { name: "Add environment" }).click();
    await page.getByLabel("Environment name 1").fill("Test 1");
    await page.getByLabel("Environment URL 1").fill("https://test1.example.test");

    // Add one app role (Enter commits the chip).
    const roleInput = page.getByLabel("New app role");
    await roleInput.fill("Admin");
    await roleInput.press("Enter");
    await expect(
      page.getByRole("button", { name: "Remove role Admin" }),
    ).toBeVisible();

    // Persist the configuration.
    await page.getByRole("button", { name: "Save configuration" }).click();
    await expect(page.getByText("Project configuration saved.")).toBeVisible({
      timeout: 15_000,
    });

    // --- Add a test-login account for the new env × role. The project defaults
    // to SSO login, so no password is required. ---
    const acctEnv = page.getByRole("combobox", { name: "Account environment" });
    // Wait for the env/role we just saved to populate the account dropdowns.
    await expect(acctEnv.locator("option", { hasText: "Test 1" })).toHaveCount(1, {
      timeout: 15_000,
    });
    await acctEnv.selectOption({ label: "Test 1" });
    await page
      .getByRole("combobox", { name: "Account role" })
      .selectOption({ label: "Admin" });
    await page.getByLabel("Account login identifier").fill("qa-admin@corp");
    await page.getByLabel("Account label").fill("Primary admin");
    await page.getByRole("button", { name: "Save account" }).click();
    await expect(page.getByText("Account saved.")).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole("button", { name: "Remove account Test 1 Admin" }),
    ).toBeVisible();

    // --- Assign the standard user as a project member. ---
    await page
      .getByRole("combobox", { name: "Select user to add" })
      .selectOption({ label: `${stdDisplayName} (${stdEmail})` });
    await page.getByRole("button", { name: "Add member" }).click();
    await expect(page.getByText("Member added.")).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole("button", { name: `Remove member ${stdDisplayName}` }),
    ).toBeVisible();
  });

  test("[P0] step 3 — project-admin removes the standard member, then logs out", async () => {
    const removeMember = page.getByRole("button", {
      name: `Remove member ${stdDisplayName}`,
    });
    await expect(removeMember).toBeVisible();
    await removeMember.click();
    await expect(page.getByText("Member removed.")).toBeVisible({ timeout: 15_000 });
    await expect(removeMember).toBeHidden();
    // The list is NOT empty afterwards: the project-admin's own (non-removable)
    // project_admin membership from step 1 remains. Assert the standard member's
    // row is gone while the project-admin's own row survives — scoped to the
    // members list so the nav header's email/name don't create false positives.
    await expect(
      page.getByRole("listitem").filter({ hasText: stdEmail }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("listitem").filter({ hasText: paEmail }),
    ).toBeVisible();

    await logoutCurrent();
  });

  test("[P0] step 4 — admin signs back in and deletes both users and the project", async () => {
    await signIn(adminEmail, adminPassword as string);
    await expect(
      page.getByRole("heading", { name: "Admin Dashboard", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Delete the project-admin user (FK cascade clears its project_admin membership).
    await page.getByRole("button", { name: `Delete user ${paDisplayName}` }).click();
    await expect(page.getByText("User deleted successfully.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(paEmail)).toBeHidden();

    // Delete the standard user.
    await page.getByRole("button", { name: `Delete user ${stdDisplayName}` }).click();
    await expect(page.getByText("User deleted successfully.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(stdEmail)).toBeHidden();

    // Delete the project created in step 1.
    await page.getByRole("button", { name: `Delete ${renamedName}` }).click();
    await expect(page.getByText("Project deleted successfully.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByRole("button", { name: `Edit ${renamedName}` }),
    ).toBeHidden();
  });
});
