import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { getAdminToken } from "../support/helpers/users";
import {
  PROJECT_PTP,
  getProjectByName,
  type ProjectRecord,
} from "../support/helpers/projects";
import {
  loginViaUI,
  createNewProjectThread,
  verifyClaudeSsoLoginButton,
} from "../support/helpers/pipeline";

const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

test.describe.serial("Group 4 — PTP Claude SSO", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let ptp: ProjectRecord;
  let userToken: string;

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");

    adminCtx = await playwrightRequest.newContext();
    userToken = await getAdminToken();
    ptp = await getProjectByName(adminCtx, userToken, PROJECT_PTP);

    page = await browser.newPage();
    await loginViaUI(page);
  });

  test.afterAll(async () => {
    if (adminCtx) await adminCtx.dispose();
    if (page) await page.close();
  });

  test("[P0] navigate to the provider step", async ({ }) => {
    await expect(page.getByText(PROJECT_PTP).first()).toBeVisible({ timeout: 15_000 });

    // Open project thread using helper
    await createNewProjectThread(page, PROJECT_PTP, ptp.id);

    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("[P1] Claude SSO card exposes the Login SSO button (feature pending)", async () => {
    await verifyClaudeSsoLoginButton(page);
  });
});
