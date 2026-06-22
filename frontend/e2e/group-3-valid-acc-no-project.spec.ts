import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";
import { loginViaUI, makeTestUser, type TestUser } from "../support/helpers/pipeline";

/**
 * Group 3 — Valid account with no project (login once, walk the dead-end).
 *
 * A standard user with zero project memberships logs in and must see the
 * no-access message instead of a provider step or chooser. Consolidates the
 * zero-project paths of story-7-2 / 7-3 / 7-7.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

const NO_ACCESS_TEXT =
  "You do not have access to any project yet. Please contact an administrator to assign you to a project.";

test.describe.serial("Group 3 — Valid account, no project", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let user: TestUser;
  let createdUserId: string | null = null;

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");
    adminCtx = await playwrightRequest.newContext();
    user = makeTestUser("g3-noproject");
    const registered = await createStandardUser(adminCtx, user);
    createdUserId = registered.id;

    page = await browser.newPage();
    await loginViaUI(page, user);
  });

  test.afterAll(async () => {
    try {
      if (createdUserId) {
        const token = await getAdminToken();
        await adminCtx.delete(`${apiBaseUrl}/api/admin/users/${createdUserId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    } catch (e) {
      console.error(`Group 3 cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      if (adminCtx) await adminCtx.dispose();
      if (page) await page.close();
    }
  });

  test("[P0] shows the no-access message and no provider step", async () => {
    await expect(page.getByText(NO_ACCESS_TEXT)).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeHidden();
    await expect(page.getByText("Please select one project to proceed")).toBeHidden();
  });

  test("[P0] no starter thread is created for a zero-project user", async ({ request }) => {
    const token = (
      await (
        await request.post(`${apiBaseUrl}/auth/login`, {
          data: { email: user.email, password: user.password },
        })
      ).json()
    ).access_token as string;
    const threadsResponse = await request.get(`${apiBaseUrl}/api/threads`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(threadsResponse.ok()).toBeTruthy();
    expect(await threadsResponse.json()).toEqual([]);
  });

  test("[P0] the no-access state persists across reload", async () => {
    await page.reload();
    await expect(page.getByText(NO_ACCESS_TEXT)).toBeVisible({ timeout: 15_000 });
  });
});
