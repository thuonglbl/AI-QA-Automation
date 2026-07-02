import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { getAdminToken } from "../support/helpers/users";
import { loginViaUI } from "../support/helpers/pipeline";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

function uniqueSuffix(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

test.describe.serial("Group 1 — Admin ⇄ Project-Admin lifecycle", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let adminToken: string;

  let projectName = "";
  let renamedName = "";
  let projectId = "";

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");

    adminToken = await getAdminToken();
    adminCtx = await playwrightRequest.newContext();

    const suffix = uniqueSuffix();
    projectName = `S1 PA-Flow ${suffix}`;
    renamedName = `${projectName} (edited)`;

    page = await browser.newPage();
    await loginViaUI(page);
    // Note: loginViaUI lands on the pipeline, we need to navigate to admin dashboard
    await page.getByTitle("User menu").click();
    await page.getByRole("button", { name: "Admin Dashboard", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Admin Dashboard", exact: true }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test.afterAll(async () => {
    try {
      if (projectId) {
        await adminCtx.delete(`${apiBaseUrl}/api/admin/projects/${projectId}`, {
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

  test("[P0] step 1 — admin creates & renames a project", async () => {
    await page.locator("#admin-project-name").fill(projectName);
    await page.locator("#create-project-button").click();
    await expect(page.getByText("Project created successfully.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByRole("button", { name: `Edit ${projectName}` }),
    ).toBeVisible();

    const list = await adminCtx.get(`${apiBaseUrl}/api/projects`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
    const projects = (await list.json()) as Array<{ id: string; name: string }>;
    const created = projects.find((p) => p.name === projectName);
    expect(created).toBeTruthy();
    projectId = created!.id;

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
  });

  test("[P0] step 2 — configure the project and add an account", async () => {
    await page.getByTitle("User menu").click();
    await page.getByRole("button", { name: "Project Admin Dashboard", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Project Admin Dashboard", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Explicitly select the new project to avoid overwriting existing real projects
    await page.getByRole("combobox", { name: "Select project" }).selectOption({ label: renamedName });

    const confluence = page.getByPlaceholder("https://confluence.company.com");
    await expect(confluence).toBeVisible({ timeout: 15_000 });
    // Do not modify confluence, environments, roles for existing projects. Just verify they are visible.
    await expect(page.getByRole("checkbox", { name: "On Premises" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Add environment" })).toBeVisible();
    await expect(page.getByLabel("New app role")).toBeVisible();
    
    // Do not click Save configuration to avoid modifying the project's existing values.

    // Credentials have been moved from Project Admin Dashboard to User UI's Test Accounts panel.
    await page.getByTitle("User menu").click();
    await page.getByRole("button", { name: "User UI", exact: true }).click();
    
    // Wait for the pipeline page to render (the user menu is available)
    await expect(page.getByTitle("User menu")).toBeVisible({ timeout: 15_000 });
    
    // Select the project first so the Test Accounts button gets enabled
    await page.getByText(renamedName).first().click();
    
    await page.getByTitle("User menu").click();
    await page.getByRole("button", { name: "Test Accounts", exact: true }).click();

    await expect(page.getByRole("button", { name: "Set Credentials" }).first()).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Set Credentials" }).first().click();
    await page.getByLabel("Username").fill("qa-admin@corp");
    await page.getByLabel("Password").fill("primaryadminpass");
    await page.getByRole("button", { name: "Save Only" }).click();
    await expect(page.getByText("Credentials saved").first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Delete" }).first()).toBeVisible();
    
    // Close the Test Accounts panel before proceeding
    await page.getByRole("button", { name: "Close" }).click();
    await expect(page.getByRole("dialog", { name: "Test accounts" })).toBeHidden();
  });

  test("[P0] step 3 — admin deletes the project", async () => {
    await page.goto("/");
    
    // Open user menu to navigate to admin dashboard
    await page.getByTitle("User menu").click();
    await page.getByRole("button", { name: "Admin Dashboard", exact: true }).click();
    
    await expect(
      page.getByRole("heading", { name: "Admin Dashboard", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: `Delete ${renamedName}` }).click();
    await expect(page.getByText("Project deleted successfully.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByRole("button", { name: `Edit ${renamedName}` }),
    ).toBeHidden();
  });
});
