import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { getAdminToken } from "../support/helpers/users";
import {
  PROJECT_PT_TOOL,
  getProjectByName,
  type ProjectRecord,
} from "../support/helpers/projects";
import {
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

test.describe.serial("Group 7 — PT Tool on-prem (up to Bob)", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let ptTool: ProjectRecord;
  let userToken: string;

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");
    test.skip(!onPremKey, "Missing TEST_ON_PREMISES_KEY — skipping on-prem flow.");

    adminCtx = await playwrightRequest.newContext();
    userToken = await getAdminToken();
    ptTool = await getProjectByName(adminCtx, userToken, PROJECT_PT_TOOL);

    page = await browser.newPage();
    await loginViaUI(page);
  });

  test.afterAll(async () => {
    if (adminCtx) await adminCtx.dispose();
    if (page) await page.close();
  });

  test("[P0] navigate to the provider step", async ({ }) => {
    await expect(page.getByText(PROJECT_PT_TOOL).first()).toBeVisible({ timeout: 15_000 });

    // Open project thread using helper
    await createNewProjectThread(page, PROJECT_PT_TOOL, ptTool.id);

    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("[P0] configure On-Premises provider", async () => {
    test.slow();
    test.setTimeout(5 * MINUTE);
    await configureOnPremProvider(page, onPremKey as string);
  });

  test("[P0] Alice hands off to Bob — MCP key form is ready (WIP stops here)", async () => {
    test.slow();
    test.setTimeout(5 * MINUTE);
    await expect(page.getByPlaceholder(/Enter MCP API Key/i)).toBeVisible({
      timeout: 60_000,
    });
  });
});
