import process from "node:process";
import { test, expect } from "../support/fixtures";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";

test.describe("Story 8.6 Admin E2E test execution and report viewing", () => {
  test.setTimeout(90000);

  test.beforeEach(async ({ page }) => {
    // Clean up local storage before each test
    await page.addInitScript(() => {
      window.localStorage.removeItem("ai-qa-selected-project-id");
      window.localStorage.removeItem("aiqa_access_token");
    });
  });

  test("Admin sees the trigger E2E tests control on the dashboard", async ({
    page,
    request,
  }) => {
    const adminEmail =
      process.env.ADMIN_EMAIL ??
      process.env.E2E_ADMIN_EMAIL ??
      "admin@example.com";
    const adminPassword =
      process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

    if (!adminPassword) {
      test.skip(true, "Admin password not provided in environment variables");
    }

    const loginResponse = await request.post(`${apiBaseUrl}/auth/login`, {
      data: { email: adminEmail, password: adminPassword },
    });

    // Deterministic check: fail loudly if setup login fails
    expect(loginResponse.ok()).toBeTruthy();

    const adminToken = (await loginResponse.json()).access_token;

    // Set token in localStorage and navigate to admin dashboard
    await page.addInitScript((token) => {
      window.localStorage.setItem("aiqa_access_token", token);
    }, adminToken);

    await page.goto("/admin");

    // We intentionally only assert that the control is present and enabled.
    // We do NOT click it: clicking triggers a real backend Playwright run
    // (npx playwright test --headed), which would recurse into this very
    // suite. Verifying the control renders is enough to cover the admin's
    // entry point without that self-triggering loop.
    const runButton = page.locator("#run-e2e-tests-button");
    await expect(runButton).toBeVisible();
    await expect(runButton).toBeEnabled();
  });
});
