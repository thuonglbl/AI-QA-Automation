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
  loginViaApi,
  loginViaClaudeSso,
  loginViaUI,
  makeTestUser,
  openProjectThread,
  type TestUser,
} from "../support/helpers/pipeline";

/**
 * Group 5 — Multiple projects, drive PT Tool, Claude SSO login seam.
 *
 * An ephemeral user is attached to BOTH real projects so the multi-project
 * workspace renders, then the PT Tool thread is opened and the Claude SSO login
 * seam is verified (card → mock IdP → SPA proceeds). Like Group 4, the full
 * pipeline is NOT run (SSO is not fully provisioned). Skips when SSO creds absent.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

function resolveEnv(key: string): string | null {
  return process.env[key]?.trim() || null;
}
const ssoEmail = resolveEnv("TEST_CLAUDE_SSO_EMAIL");
const ssoPassword = resolveEnv("TEST_CLAUDE_SSO_PASSWORD");

test.describe.serial("Group 5 — Multiple projects, PT Tool Claude SSO", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let user: TestUser;
  let createdUserId: string | null = null;
  let ptTool: ProjectRecord;
  let userToken: string;
  let ptThreadId: string;

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");
    test.skip(
      !ssoEmail || !ssoPassword,
      "Missing TEST_CLAUDE_SSO_EMAIL/PASSWORD — skipping SSO seam.",
    );

    adminCtx = await playwrightRequest.newContext();
    const adminToken = await getAdminToken();
    ptTool = await getProjectByName(adminCtx, adminToken, PROJECT_PT_TOOL);
    const ptp = await getProjectByName(adminCtx, adminToken, PROJECT_PTP);

    user = makeTestUser("g5-pt-sso");
    const registered = await createStandardUser(adminCtx, user);
    createdUserId = registered.id;
    // Member of BOTH projects → multi-project workspace.
    await assignMembership(adminCtx, adminToken, ptTool.id, registered.id);
    await assignMembership(adminCtx, adminToken, ptp.id, registered.id);

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
      console.error(`Group 5 cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      if (adminCtx) await adminCtx.dispose();
      if (page) await page.close();
    }
  });

  test("[P0] multi-project workspace: both projects bootstrapped and listed", async ({
    request,
  }) => {
    userToken = await loginViaApi(request, user.email, user.password);

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

    ptThreadId = await threadIdForProject(request, userToken, ptTool.id);

    await expect(page.getByText(PROJECT_PT_TOOL)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(PROJECT_PTP)).toBeVisible();
  });

  test("[P1] open PT Tool thread and verify the Claude SSO login seam", async () => {
    test.slow();
    await openProjectThread(page, PROJECT_PT_TOOL, ptThreadId);
    await loginViaClaudeSso(page, {
      email: ssoEmail as string,
      password: ssoPassword as string,
    });
  });
});
