import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";
import { makeTestUser, type TestUser } from "../support/helpers/pipeline";

/**
 * Group 2 — Invalid account / failed authentication (negative paths).
 *
 * No session is ever established, so each case starts from the login screen.
 * Consolidates the negative half of story-7-1: wrong password (API + UI) and an
 * unknown email both yield the same generic, leak-free rejection and never
 * persist a token.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

test.describe("Group 2 — Invalid account", () => {
  let adminCtx: APIRequestContext;
  let user: TestUser;
  let createdUserId: string | null = null;

  test.beforeAll(async () => {
    test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");
    adminCtx = await playwrightRequest.newContext();
    user = makeTestUser("g2-valid");
    const registered = await createStandardUser(adminCtx, user);
    createdUserId = registered.id;
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
      console.error(`Group 2 cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      if (adminCtx) await adminCtx.dispose();
    }
  });

  test("[P0] API rejects a wrong password with a generic 401", async ({ request }) => {
    const response = await request.post(`${apiBaseUrl}/auth/login`, {
      data: { email: user.email, password: "definitely-wrong" },
    });
    expect(response.status()).toBe(401);
    expect((await response.json()).detail).toBe("Invalid email or password");
  });

  test("[P0] UI rejects a wrong password and stores no token", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill("definitely-wrong");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText("Invalid username or password.")).toBeVisible();
    await expect(
      page.getByText(/You do not have access to any project yet\./i),
    ).toBeHidden();
    await expect
      .poll(() =>
        page.evaluate(() => window.localStorage.getItem("aiqa_access_token")),
      )
      .toBeNull();
  });

  test("[P0] UI rejects an unknown email with the same generic message", async ({ page }) => {
    await page.goto("/");
    await page
      .getByLabel("Email")
      .fill(`g2-nobody-${Date.now()}@example.com`);
    await page.getByLabel("Password").fill("whatever-secret");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText("Invalid username or password.")).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(() => window.localStorage.getItem("aiqa_access_token")),
      )
      .toBeNull();
  });
});
