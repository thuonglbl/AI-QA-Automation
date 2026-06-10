import process from "node:process";
import fs from "node:fs";
import path from "node:path";
import { request as playwrightRequest } from "@playwright/test";
import type { FullConfig } from "@playwright/test";

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminEmail =
  process.env.ADMIN_EMAIL ?? process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const adminPassword =
  process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

const TOKEN_CACHE_PATH = path.resolve(
  process.env.TMP ?? process.env.TEMP ?? "/tmp",
  "e2e-admin-token.json",
);

export default async function globalSetup(_config: FullConfig): Promise<void> {
  if (!adminPassword) {
    console.warn(
      "[e2e setup] No ADMIN_PASSWORD/E2E_ADMIN_PASSWORD — skipping token pre-auth.",
    );
    return;
  }

  const ctx = await playwrightRequest.newContext();
  try {
    const response = await ctx.post(`${apiBaseUrl}/auth/login`, {
      data: { email: adminEmail, password: adminPassword },
    });
    if (!response.ok()) {
      console.warn(
        `[e2e setup] Admin login failed (${response.status()}) — workers will retry.`,
      );
      return;
    }
    const { access_token } = (await response.json()) as {
      access_token: string;
    };
    fs.writeFileSync(
      TOKEN_CACHE_PATH,
      JSON.stringify({ token: access_token, ts: Date.now() }),
      "utf-8",
    );
    console.log("[e2e setup] Admin token cached for workers.");
  } catch (err) {
    console.warn("[e2e setup] Could not pre-authenticate admin:", err);
  } finally {
    await ctx.dispose();
  }
}
