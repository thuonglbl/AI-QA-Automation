import process from "node:process";
import fs from "node:fs";
import path from "node:path";
import type { APIRequestContext } from "@playwright/test";
import { expect, request as playwrightRequest } from "@playwright/test";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminEmail =
  process.env.ADMIN_EMAIL ?? process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

const TOKEN_CACHE_PATH = path.resolve(
  process.env.TMP ?? process.env.TEMP ?? "/tmp",
  "e2e-admin-token.json",
);

/**
 * Display-safe user record returned by the admin user-management API.
 *
 * Story 8.7 locked down public self-service registration (`POST /auth/register`
 * was removed), so E2E specs bootstrap their standard users through the
 * admin-only `POST /api/admin/users` endpoint instead.
 */
export type CreatedUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
};

/**
 * Cached admin bearer token, scoped to the current Playwright worker process.
 *
 * Admin login verifies an Argon2 password hash, which is intentionally CPU and
 * memory expensive. Logging in on every `createStandardUser` call saturates the
 * single-process backend under parallel workers and trips Playwright's action
 * timeout. Caching the token authenticates the admin once per worker instead.
 */
let cachedAdminToken: string | null = null;

/**
 * Authenticate as the configured admin and return a bearer access token,
 * reusing a cached token within the worker to avoid redundant Argon2 verifies.
 *
 * The login runs in an isolated request context so the admin session cookie it
 * sets never leaks into a caller's request context. The auth middleware reads
 * the session cookie before the Authorization header, so a leaked admin cookie
 * would otherwise override a standard user's bearer token on later calls (e.g.
 * `GET /auth/me`).
 *
 * Throws a descriptive error when no admin password is configured so failing
 * specs explain how to bootstrap the admin account.
 */
export async function getAdminToken(): Promise<string> {
  if (!adminPassword) {
    throw new Error(
      "E2E user bootstrap needs ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in the environment.",
    );
  }
  if (cachedAdminToken) {
    return cachedAdminToken;
  }
  // Try reading the pre-authenticated token from globalSetup first.
  // This avoids concurrent Argon2 verifies across workers.
  try {
    if (fs.existsSync(TOKEN_CACHE_PATH)) {
      const raw = fs.readFileSync(TOKEN_CACHE_PATH, "utf-8");
      const { token, ts } = JSON.parse(raw) as { token: string; ts: number };
      // Token is valid for 1 hour; use if fresh enough.
      if (token && Date.now() - ts < 55 * 60 * 1000) {
        cachedAdminToken = token;
        return cachedAdminToken;
      }
    }
  } catch {
    // Cache read failed — fall through to live login.
  }

  // Fallback: live login with retry and stagger.
  const staggerMs = (process.pid % 5) * 1_500;
  if (staggerMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, staggerMs));
  }

  const maxAttempts = 3;
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const ctx = await playwrightRequest.newContext();
    try {
      const response = await ctx.post(`${apiBaseUrl}/auth/login`, {
        data: { email: adminEmail, password: adminPassword },
      });
      if (response.ok()) {
        cachedAdminToken = (
          (await response.json()) as { access_token: string }
        ).access_token;
        return cachedAdminToken;
      }
      lastError = new Error(`Admin login HTTP ${response.status()}`);
    } catch (err) {
      lastError = err;
    } finally {
      await ctx.dispose();
    }
    if (attempt < maxAttempts) {
      await new Promise((resolve) =>
        setTimeout(resolve, attempt * 2_000 + staggerMs),
      );
    }
  }
  throw new Error(
    `Admin login failed after ${maxAttempts} attempts. E2E tests require a valid admin account. Last error: ${lastError}`,
  );
}

/**
 * Drop-in replacement for the old `registerStandardUser` helper.
 *
 * Creates an active standard user via the admin-only `POST /api/admin/users`
 * endpoint using an admin bearer token, returning the created user record. The
 * create call carries the admin token in the Authorization header and never
 * sets a cookie, so the caller's request context stays free of admin state.
 */
export async function createStandardUser(
  request: APIRequestContext,
  user: { email: string; displayName: string; password: string },
): Promise<CreatedUser> {
  const adminToken = await getAdminToken();
  const response = await request.post(`${apiBaseUrl}/api/admin/users`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: {
      email: user.email,
      display_name: user.displayName,
      role: "standard",
      initial_password: user.password,
    },
  });
  expect(response.ok()).toBeTruthy();
  const payload = (await response.json()) as CreatedUser;
  expect(JSON.stringify(payload)).not.toContain("password_hash");
  return payload;
}
