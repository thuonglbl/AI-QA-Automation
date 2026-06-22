import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";
import {
  PROJECT_PT_TOOL,
  PROJECT_PTP,
  assignMembership,
  getProjectByName,
  threadIdForProject,
  type ProjectRecord,
} from "../support/helpers/projects";
import {
  configureOnPremProvider,
  loginViaApi,
  loginViaUI,
  makeTestUser,
  openProjectThread,
  type TestUser,
} from "../support/helpers/pipeline";

/**
 * Group 6 — Multiple projects, drive PTP on On-Premises (up to Bob).
 *
 * An ephemeral user is attached to BOTH real projects (PT Tool + PTP) so the
 * multi-project workspace is exercised, then the PTP thread is driven through
 * Alice (on-prem provider config) up to the hand-off to Bob.
 *
 * WIP NOTE: the pipeline from Bob onward (Confluence extraction → Mary test
 * cases → Sarah script) is still under development, so the journey stops once
 * Bob's step is reached and its MCP-key form is ready to start. The deferred
 * drivers (`runBobExtraction` / `approveAllMaryTestCases` /
 * `runSarahToScriptApproval`) stay in `support/helpers/pipeline.ts` to wire back
 * in once that flow is finished.
 *
 * Cleanup: only the ephemeral user is deleted (cascades its threads/runs/
 * artifacts). The real PT Tool / PTP projects are never created or deleted.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

function resolveEnv(key: string): string | null {
  return process.env[key]?.trim() || null;
}
const onPremKey = resolveEnv("TEST_ON_PREMISES_KEY");

const MINUTE = 60_000;

test.describe.serial("Group 6 — Multiple projects, PTP on-prem (up to Bob)", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let user: TestUser;
  let createdUserId: string | null = null;
  let ptp: ProjectRecord;
  let userToken: string;
  let ptpThreadId: string;

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");
    test.skip(!onPremKey, "Missing TEST_ON_PREMISES_KEY — skipping on-prem flow.");

    adminCtx = await playwrightRequest.newContext();
    const adminToken = await getAdminToken();

    ptp = await getProjectByName(adminCtx, adminToken, PROJECT_PTP);
    const ptTool = await getProjectByName(adminCtx, adminToken, PROJECT_PT_TOOL);

    user = makeTestUser("g6-ptp");
    const registered = await createStandardUser(adminCtx, user);
    createdUserId = registered.id;
    // Member of BOTH projects → multi-project workspace.
    await assignMembership(adminCtx, adminToken, ptp.id, registered.id);
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
      console.error(`Group 6 cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      if (adminCtx) await adminCtx.dispose();
      if (page) await page.close();
    }
  });

  test("[P0] multi-project workspace: both projects bootstrapped and listed", async ({
    request,
  }) => {
    userToken = await loginViaApi(request, user.email, user.password);

    // The browser bootstraps one starter thread per accessible project; wait for both.
    await expect
      .poll(
        async () => {
          const res = await request.get(`${apiBaseUrl}/api/threads`, {
            headers: { Authorization: `Bearer ${userToken}` },
          });
          if (!res.ok()) return 0;
          return ((await res.json()) as unknown[]).length;
        },
        { timeout: 30_000, intervals: [500, 1000, 2000] },
      )
      .toBeGreaterThanOrEqual(2);

    ptpThreadId = await threadIdForProject(request, userToken, ptp.id);

    await expect(page.getByText(PROJECT_PTP)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(PROJECT_PT_TOOL)).toBeVisible();
  });

  test("[P0] configure On-Premises provider on the PTP thread", async () => {
    test.slow();
    test.setTimeout(5 * MINUTE);
    await openProjectThread(page, PROJECT_PTP, ptpThreadId);
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
