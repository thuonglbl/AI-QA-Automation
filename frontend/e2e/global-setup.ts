import process from "node:process";
import fs from "node:fs";
import path from "node:path";
import type { FullConfig } from "@playwright/test";
import { getAdminCookies } from "../support/helpers/users";

const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;

const TOKEN_CACHE_PATH = path.resolve(
  process.env.TMP ?? process.env.TEMP ?? "/tmp",
  "e2e-admin-token.json",
);

export default async function globalSetup(_config: FullConfig): Promise<void> {
  if (!adminPassword) {
    console.warn("[e2e setup] No ADMIN_PASSWORD/E2E_ADMIN_PASSWORD — skipping token pre-auth.");
    return;
  }

  try {
    const cookies = await getAdminCookies();
    fs.writeFileSync(
      TOKEN_CACHE_PATH,
      JSON.stringify({ cookies, ts: Date.now() }),
      "utf-8",
    );
    console.log("[e2e setup] Admin cookies cached for workers via Azure AD SSO.");
  } catch (err) {
    console.warn("[e2e setup] Could not pre-authenticate admin:", err);
  }
}
