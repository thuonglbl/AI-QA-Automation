import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { getAdminToken } from "../support/helpers/users";
import {
  PROJECT_PT_TOOL,
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

test.describe.serial("Group 5 — Multiple projects, PT Tool Claude SSO", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let ptTool: ProjectRecord;
  let userToken: string;

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");

    adminCtx = await playwrightRequest.newContext();
    userToken = await getAdminToken();
    ptTool = await getProjectByName(adminCtx, userToken, PROJECT_PT_TOOL);
    await getProjectByName(adminCtx, userToken, PROJECT_PTP);

    page = await browser.newPage();
    await loginViaUI(page);
  });

  test.afterAll(async () => {
    if (adminCtx) await adminCtx.dispose();
    if (page) await page.close();
  });

  test("[P0] multi-project workspace: both projects bootstrapped and listed", async ({ }) => {
    await expect(page.getByText(PROJECT_PT_TOOL).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(PROJECT_PTP).first()).toBeVisible();
  });

  test("[P1] open PT Tool thread; Claude SSO card exposes the Login SSO button (feature pending)", async () => {
    await createNewProjectThread(page, PROJECT_PT_TOOL, ptTool.id);
    await verifyClaudeSsoLoginButton(page);
  });
});
