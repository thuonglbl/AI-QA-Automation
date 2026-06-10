import process from "node:process";
import { test, expect } from "../support/fixtures";
import { createStandardUser } from "../support/helpers/users";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminEmail =
  process.env.ADMIN_EMAIL ?? process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

test.describe("Story 7.1 local login and authenticated session foundation", () => {
  let createdUserIds: string[] = [];

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.removeItem("ai-qa-selected-project-id");
      window.localStorage.removeItem("aiqa_access_token");
    });
  });

  test.afterEach(async ({ request }) => {
    if (createdUserIds.length === 0 || !adminPassword) return;

    const loginResponse = await request.post(`${apiBaseUrl}/auth/login`, {
      data: { email: adminEmail, password: adminPassword },
    });

    if (loginResponse.ok()) {
      const adminToken = (await loginResponse.json()).access_token;
      for (const userId of createdUserIds) {
        await request.delete(`${apiBaseUrl}/api/admin/users/${userId}`, {
          headers: { Authorization: `Bearer ${adminToken}` },
        });
      }
    }
    createdUserIds = [];
  });

  test("[P0] authenticates a registered user through the real backend and applies the token to current-user calls", async ({
    page,
    request,
    userFactory,
  }) => {
    const user = userFactory.create({
      email: `story-7-1-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.1 User",
      password: "super-secret-7-1",
      role: "standard",
    });

    const registered = await createStandardUser(request, user);
    createdUserIds.push(registered.id);

    expect(registered.email).toBe(user.email);
    expect(registered.role).toBe("standard");
    expect(JSON.stringify(registered)).not.toContain("password_hash");

    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText(user.displayName)).toBeVisible();
    await expect(
      page.getByText("You do not have access to any project yet."),
    ).toBeVisible();

    const token = await page.evaluate(() =>
      window.localStorage.getItem("aiqa_access_token"),
    );
    expect(token).toBeTruthy();

    const meResponse = await request.get(`${apiBaseUrl}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(meResponse.ok()).toBeTruthy();
    const me = await meResponse.json();
    expect(me.email).toBe(user.email);
    expect(me.display_name).toBe(user.displayName);
    expect(me.role).toBe("standard");
    expect(me.is_active).toBe(true);
    expect(JSON.stringify(me)).not.toContain("password_hash");
  });

  test("[P0] rejects invalid credentials with a safe consistent error message", async ({
    page,
    request,
    userFactory,
  }) => {
    const user = userFactory.create({
      email: `story-7-1-invalid-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
      displayName: "Story 7.1 Invalid User",
      password: "correct-secret-7-1",
      role: "standard",
    });

    const registered = await createStandardUser(request, user);
    createdUserIds.push(registered.id);

    const apiInvalidResponse = await request.post(`${apiBaseUrl}/auth/login`, {
      data: { email: user.email, password: "wrong-secret-7-1" },
    });
    expect(apiInvalidResponse.status()).toBe(401);
    expect((await apiInvalidResponse.json()).detail).toBe(
      "Invalid email or password",
    );

    await page.goto("/");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill("wrong-secret-7-1");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText("Invalid username or password.")).toBeVisible();
    await expect(
      page.getByText("You do not have access to any project yet."),
    ).toBeHidden();
    await expect
      .poll(() =>
        page.evaluate(() => window.localStorage.getItem("aiqa_access_token")),
      )
      .toBeNull();
  });
});
