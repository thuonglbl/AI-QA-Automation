import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";
import {
  PROJECT_PTP,
  assignMembership,
  getProjectByName,
} from "../support/helpers/projects";
import {
  loginViaClaudeSso,
  loginViaUI,
  makeTestUser,
  type TestUser,
} from "../support/helpers/pipeline";

/**
 * Group 4 — Single project (PTP), Claude SSO login seam.
 *
 * Claude SSO is not fully provisioned yet (no enterprise key), so per the
 * regroup plan this only verifies the login seam: select the Claude SSO card →
 * Login SSO → mock IdP authenticates → the SPA proceeds to the connection step.
 * The full pipeline is intentionally NOT run here. Skips when SSO creds absent.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

function resolveEnv(key: string): string | null {
  return process.env[key]?.trim() || null;
}
const ssoEmail = resolveEnv("TEST_CLAUDE_SSO_EMAIL");
const ssoPassword = resolveEnv("TEST_CLAUDE_SSO_PASSWORD");

test.describe.serial("Group 4 — One project, PTP Claude SSO", () => {
  let page: Page;
  let adminCtx: APIRequestContext;
  let user: TestUser;
  let createdUserId: string | null = null;

  test.beforeAll(async ({ browser }) => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");
    test.skip(
      !ssoEmail || !ssoPassword,
      "Missing TEST_CLAUDE_SSO_EMAIL/PASSWORD — skipping SSO seam.",
    );

    adminCtx = await playwrightRequest.newContext();
    const adminToken = await getAdminToken();
    const ptp = await getProjectByName(adminCtx, adminToken, PROJECT_PTP);

    user = makeTestUser("g4-ptp-sso");
    const registered = await createStandardUser(adminCtx, user);
    createdUserId = registered.id;
    // Member of ONLY PTP → single-project auto-bind to the provider step.
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
      console.error(`Group 4 cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      if (adminCtx) await adminCtx.dispose();
      if (page) await page.close();
    }
  });

  test("[P0] single project lands on the provider step", async () => {
    await expect(page.getByText(PROJECT_PTP)).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText(/Which AI provider would you like to use/i),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("[P1] Claude SSO login seam: card → IdP → SPA proceeds", async () => {
    test.slow();
    await loginViaClaudeSso(page, {
      email: ssoEmail as string,
      password: ssoPassword as string,
    });
  });
});
