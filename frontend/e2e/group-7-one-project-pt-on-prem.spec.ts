import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";
import {
  PROJECT_PT_TOOL,
  assignMembership,
  getProjectByName,
  type ProjectRecord,
} from "../support/helpers/projects";
import {
  configureOnPremProvider,
  loginViaUI,
  makeTestUser,
  type TestUser,
} from "../support/helpers/pipeline";

/**
 * Group 7 — Single project (PT Tool), On-Premises (up to Bob).
 *
 * An ephemeral user is attached to ONLY PT Tool, so login auto-binds the single
 * project and lands straight on Alice's provider step (no chooser). The PT Tool
 * thread is driven through Alice (on-prem provider config) up to the hand-off
 * to Bob.
 *
 * WIP NOTE: the pipeline from Bob onward (Confluence extraction → Mary test
 * cases → Sarah script) is still under development, so the journey stops once
 * Bob's step is reached and its MCP-key form is ready to start. The deferred
 * drivers (`runBobExtraction` / `approveAllMaryTestCases` /
 * `runSarahToScriptApproval`) stay in `support/helpers/pipeline.ts` to wire back
 * in once that flow is finished.
 *
 * Cleanup: only the ephemeral user is deleted (cascades artifacts); PT Tool is
 * never created or deleted.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

function resolveEnv(key: string): string | null {
  return process.env[key]?.trim() || null;
}
const onPremKey = resolveEnv("TEST_ON_PREMISES_KEY");

const MINUTE = 60_000;

test.describe.serial("Group 7 — One project, PT Tool on-prem (up to Bob)", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let user: TestUser;
  let createdUserId: string | null = null;
  let ptTool: ProjectRecord;

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");
    test.skip(!onPremKey, "Missing TEST_ON_PREMISES_KEY — skipping on-prem flow.");

    adminCtx = await playwrightRequest.newContext();
    const adminToken = await getAdminToken();

    ptTool = await getProjectByName(adminCtx, adminToken, PROJECT_PT_TOOL);

    user = makeTestUser("g7-pt");
    const registered = await createStandardUser(adminCtx, user);
    createdUserId = registered.id;
    // Member of ONLY PT Tool → single-project auto-bind.
    await assignMembership(adminCtx, adminToken, ptTool.id, registered.id);

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
      console.error(`Group 7 cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      if (adminCtx) await adminCtx.dispose();
      if (page) await page.close();
    }
  });

  test("[P0] single project auto-binds and lands on the provider step", async () => {
    await expect(page.getByText(PROJECT_PT_TOOL)).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Please select one project to proceed")).toBeHidden();
  });

  test("[P0] configure On-Premises provider", async () => {
    test.slow();
    test.setTimeout(5 * MINUTE);
    await configureOnPremProvider(page, onPremKey as string);
  });

  test("[P0] Alice hands off to Bob — MCP key form is ready (WIP stops here)", async () => {
    test.slow();
    test.setTimeout(5 * MINUTE);
    // The pipeline beyond Bob (extraction → Mary → Sarah) is still in development.
    // For now the journey stops once Bob's step is reached and ready to start.
    await expect(page.getByPlaceholder(/Enter MCP API Key/i)).toBeVisible({
      timeout: 60_000,
    });
  });
});
