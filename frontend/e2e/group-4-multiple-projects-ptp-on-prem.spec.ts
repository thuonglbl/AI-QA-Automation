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
  clearClientState,
  configureOnPremProvider,
  loginViaUI,
  createNewProjectThread,
} from "../support/helpers/pipeline";

const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

function resolveEnv(key: string): string | null {
  return process.env[key]?.trim() || null;
}
const onPremKey = resolveEnv("TEST_ON_PREMISES_KEY");

const MINUTE = 60_000;

test.describe.serial("Group 6 — Multiple projects, PTP on-prem (up to Bob)", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let ptp: ProjectRecord;
  let userToken: string;

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");
    test.skip(!onPremKey, "Missing TEST_ON_PREMISES_KEY — skipping on-prem flow.");

    adminCtx = await playwrightRequest.newContext();
    userToken = await getAdminToken();

    ptp = await getProjectByName(adminCtx, userToken, PROJECT_PTP);
    await getProjectByName(adminCtx, userToken, PROJECT_PT_TOOL);

    page = await browser.newPage();
    await clearClientState(page);
    await loginViaUI(page);
  });

  test.afterAll(async () => {
    if (adminCtx) await adminCtx.dispose();
    if (page) await page.close();
  });

  test("[P0] multi-project workspace: both projects bootstrapped and listed", async ({ }) => {
    await expect(page.getByText(PROJECT_PTP).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(PROJECT_PT_TOOL).first()).toBeVisible();
  });

  test("[P0] configure On-Premises provider on the PTP thread", async () => {
    test.slow();
    test.setTimeout(5 * MINUTE);
    await createNewProjectThread(page, PROJECT_PTP, ptp.id);
    await configureOnPremProvider(page, onPremKey as string);
  });

});
