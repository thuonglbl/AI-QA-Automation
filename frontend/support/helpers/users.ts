import process from "node:process";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const baseURL = process.env.BASE_URL ?? "http://localhost:5173";
const adminEmail = process.env.ADMIN_EMAIL ?? process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

const TOKEN_CACHE_PATH = path.resolve(
  process.env.TMP ?? process.env.TEMP ?? "/tmp",
  "e2e-admin-token.json",
);

let cachedAdminCookies: any[] | null = null;

export async function getAdminCookies(): Promise<any[]> {
  if (!adminPassword) {
    throw new Error("E2E user bootstrap needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.");
  }
  if (cachedAdminCookies) return cachedAdminCookies;

  try {
    if (fs.existsSync(TOKEN_CACHE_PATH)) {
      const raw = fs.readFileSync(TOKEN_CACHE_PATH, "utf-8");
      const { cookies, ts } = JSON.parse(raw);
      if (cookies && Date.now() - ts < 55 * 60 * 1000) {
        cachedAdminCookies = cookies;
        return cachedAdminCookies as any[];
      }
    }
  } catch { }

  const staggerMs = (process.pid % 5) * 1_500;
  if (staggerMs > 0) await new Promise((resolve) => setTimeout(resolve, staggerMs));

  const maxAttempts = 3;
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    try {
      await page.goto(`${apiBaseUrl}/auth/sso/login`);
      await page.waitForURL(/login\.microsoftonline\.com/);

      const emailInput = page.locator('input[type="email"]');
      await emailInput.waitFor();
      await emailInput.fill(adminEmail);
      await page.locator('input[type="submit"]').click({ force: true, noWaitAfter: true });

      try {
        const usePasswordBtn = page.getByText("Use your password instead");
        await usePasswordBtn.waitFor({ state: 'visible', timeout: 5000 });
        await usePasswordBtn.click();
      } catch (_e) { }

      const passwordInput = page.locator('input[type="password"]');
      await passwordInput.waitFor();
      await passwordInput.fill(adminPassword);
      await page.locator('input[type="submit"]').click({ force: true, noWaitAfter: true });

      try {
        const staySignedInBtn = page.locator('input[type="submit"][value="Yes"]');
        await staySignedInBtn.waitFor({ state: 'visible', timeout: 5000 });
        await staySignedInBtn.click({ force: true, noWaitAfter: true });
      } catch (_e) { }

      await page.waitForURL(url => url.origin === new URL(baseURL).origin || url.origin === new URL(apiBaseUrl).origin, { timeout: 15000 });

      const cookies = await page.context().cookies();
      if (cookies.length > 0) {
        cachedAdminCookies = cookies;
        return cachedAdminCookies as any[];
      }
      throw new Error("No cookies found after Azure AD login");
    } catch (err) {
      lastError = err;
    } finally {
      await browser.close();
    }
    if (attempt < maxAttempts) {
      await new Promise((resolve) => setTimeout(resolve, attempt * 2_000 + staggerMs));
    }
  }
  throw new Error(`Admin login failed after ${maxAttempts} attempts. Last error: ${lastError}`);
}

export async function getAdminToken(): Promise<string> {
  const cookies = await getAdminCookies();
  const sessionCookie = cookies.find(c => c.name.includes("session"));
  return sessionCookie?.value || "";
}

export async function createStandardUser(): Promise<any> {
  // Deprecated: E2E tests now use the single real account configured in .env
  // which holds all roles. This function is left as a no-op to prevent compilation errors
  // while tests are refactored.
  return { id: "real-admin-user", email: adminEmail, display_name: "Admin User", role: "admin" };
}
