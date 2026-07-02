import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { request as playwrightRequest } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { getAdminToken } from "../support/helpers/users";
import { PROJECT_PT_TOOL, getProjectByName } from "../support/helpers/projects";
import { loginViaUI, openProjectThread } from "../support/helpers/pipeline";

/**
 * Group 8 — Isolated throwaway project, On-Premises (provider config → Bob ready).
 *
 * WHY THIS EXISTS
 * ---------------
 * The other on-prem / Claude-SSO groups reuse the two REAL, persistent projects
 * ("PT Tool" / "PTP Tool"). Those projects accumulate a SAVED provider config and
 * a pile of conversations across runs, so on a new thread Alice shows the
 * "You have a saved provider configuration … Use saved configuration / Choose a
 * different provider" shortcut instead of the "Which AI provider would you like to
 * use" question the helpers wait for — which is why those specs fail at the
 * provider step (see _bmad-output/test-artifacts/results.xml).
 *
 * This group sidesteps that entirely: it creates a FRESH, uniquely-named project
 * for this run only, drives the REAL pipeline against the testing environment in
 * `.env` (no mocking — real Azure SSO login, real On-Premises connection test +
 * model discovery), and then deletes the project in afterAll. Deleting the
 * project cascades its threads / agent_runs / messages / artifacts in the DB AND
 * wipes its SeaweedFS prefix (DELETE /api/admin/projects → storage.delete_prefix),
 * so no real data is touched and nothing is left behind.
 *
 * A brand-new project has no saved provider config for this user, so Alice always
 * asks the provider question — exactly the path the failing specs assume.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const adminPassword = process.env.ADMIN_PASSWORD ?? process.env.E2E_ADMIN_PASSWORD;
const adminEmail =
  process.env.ADMIN_EMAIL ?? process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";

function resolveEnv(key: string): string | null {
  return process.env[key]?.trim() || null;
}
const onPremKey = resolveEnv("TEST_ON_PREMISES_KEY");

const MINUTE = 60_000;

type AdminProject = { id: string; name: string };

test.describe.serial(
  "Group 8 — Isolated throwaway project, on-prem (provider config + Bob ready)",
  () => {
    let page: Page;
    let adminCtx: APIRequestContext;
    let adminToken: string;
    let projectId = "";
    let projectName = "";
    let threadId = "";

    test.beforeAll(async ({ browser }) => {
      test.skip(!adminPassword, "ADMIN_PASSWORD/E2E_ADMIN_PASSWORD not set");
      test.skip(!onPremKey, "Missing TEST_ON_PREMISES_KEY — skipping on-prem flow.");

      adminToken = await getAdminToken();
      adminCtx = await playwrightRequest.newContext();

      // Clone the real PT Tool config (Confluence/Jira/providers) onto a fresh,
      // uniquely-named throwaway project so the pipeline has what it needs without
      // ever touching the real PT Tool / PTP data.
      const template = await getProjectByName(adminCtx, adminToken, PROJECT_PT_TOOL);
      const enabledProviders =
        template.enabled_providers && template.enabled_providers.length > 0
          ? template.enabled_providers
          : ["on-premises"];
      if (!enabledProviders.includes("on-premises")) enabledProviders.push("on-premises");

      projectName = `E2E Isolated OnPrem ${Date.now()}-${Math.random()
        .toString(36)
        .slice(2)}`;

      const createRes = await adminCtx.post(`${apiBaseUrl}/api/admin/projects`, {
        headers: { Authorization: `Bearer ${adminToken}` },
        data: {
          name: projectName,
          description: "Ephemeral E2E project — auto-deleted in afterAll (DB + storage).",
          confluence_base_url: template.confluence_base_url ?? null,
          jira_base_url: template.jira_base_url ?? null,
          enabled_providers: enabledProviders,
          environments: [],
          app_roles: [],
        },
      });
      expect(
        createRes.ok(),
        `create project failed (${createRes.status()}): ${await createRes.text()}`,
      ).toBeTruthy();
      projectId = ((await createRes.json()) as AdminProject).id;

      // Pre-create EXACTLY ONE thread bound to the project via the API. The app
      // bootstraps a starter thread per project only when none exists, so seeding
      // one here keeps the project at a single, stable thread — otherwise the
      // app's auto-starter races the thread we open and the active thread churns,
      // which silently drops Alice's provider UI (observed during diagnosis).
      const usersRes = await adminCtx.get(`${apiBaseUrl}/api/admin/users`, {
        headers: { Authorization: `Bearer ${adminToken}` },
      });
      expect(usersRes.ok(), `list users failed (${usersRes.status()})`).toBeTruthy();
      const users = (await usersRes.json()) as Array<{ id: string; email: string }>;
      const adminUser = users.find(
        (u) => u.email.toLowerCase() === adminEmail.toLowerCase(),
      );
      expect(adminUser, `admin user ${adminEmail} not found`).toBeTruthy();

      const threadRes = await adminCtx.post(`${apiBaseUrl}/api/threads`, {
        headers: { Authorization: `Bearer ${adminToken}` },
        data: { user_id: adminUser!.id, project_id: projectId },
      });
      expect(
        threadRes.ok(),
        `create thread failed (${threadRes.status()}): ${await threadRes.text()}`,
      ).toBeTruthy();
      threadId = ((await threadRes.json()) as { id: string }).id;

      page = await browser.newPage();
      await loginViaUI(page);
      // The fresh project must surface in the sidebar (admin sees all projects).
      await expect(page.getByText(projectName).first()).toBeVisible({ timeout: 30_000 });
    });

    test.afterAll(async () => {
      // Clean up EVERYTHING this run created. Deleting the project cascades its
      // threads / agent_runs / messages / artifacts in the DB and wipes the
      // project's SeaweedFS prefix, then we verify it's actually gone.
      try {
        if (projectId) {
          const del = await adminCtx.delete(
            `${apiBaseUrl}/api/admin/projects/${projectId}`,
            { headers: { Authorization: `Bearer ${adminToken}` } },
          );
          if (!del.ok() && del.status() !== 404) {
            console.error(`[group-8 cleanup] project delete returned ${del.status()}.`);
          }

          const list = await adminCtx.get(`${apiBaseUrl}/api/projects`, {
            headers: { Authorization: `Bearer ${adminToken}` },
          });
          if (list.ok()) {
            const remaining = (await list.json()) as AdminProject[];
            const stillThere = remaining.some((p) => p.id === projectId);
            console.log(
              stillThere
                ? `[group-8 cleanup] WARNING: project ${projectId} still present after delete.`
                : `[group-8 cleanup] OK: project "${projectName}" removed (DB + file storage).`,
            );
          }
        }
      } catch (e) {
        console.error(`[group-8 cleanup] failed: ${e instanceof Error ? e.message : e}`);
      } finally {
        if (adminCtx) await adminCtx.dispose();
        if (page) await page.close();
      }
    });

    test("[P0] open the isolated project's thread → Alice asks for a provider", async () => {
      await expect(page.getByText(projectName).first()).toBeVisible({ timeout: 15_000 });
      // Open the single pre-seeded thread (no second thread to race with).
      await openProjectThread(page, projectName, threadId);

      // Fresh project ⇒ no saved provider config ⇒ Alice asks the provider question.
      await expect(
        page.getByText(/Which AI provider would you like to use/i),
      ).toBeVisible({ timeout: 30_000 });
    });

    test("[P0] configure On-Premises for real — live connection test + model discovery", async () => {
      test.slow();
      test.setTimeout(5 * MINUTE);

      const card = page.getByTestId("provider-card-on-premises");
      await expect(card).toBeVisible();
      // Cards stay disabled (opacity-50) until the WebSocket reports ready.
      await expect(card).not.toHaveClass(/opacity-50/, { timeout: 30_000 });
      await card.click();

      // A fresh project has no key on file, so the credential form should appear;
      // we still tolerate an auto-connect (success toast) for robustness.
      const keyInput = page.getByTestId("credential-input-api_key");
      const successToast = page.getByText(/Connected successfully to/i).first();

      const result = await Promise.race([
        keyInput
          .waitFor({ state: "visible", timeout: 30_000 })
          .then(() => "form" as const)
          .catch(() => "timeout" as const),
        successToast
          .waitFor({ state: "visible", timeout: 30_000 })
          .then(() => "success" as const)
          .catch(() => "timeout" as const),
      ]);
      if (result === "timeout") {
        throw new Error(
          "On-Premises: neither the credential form nor a success toast appeared.",
        );
      }

      if (result === "form") {
        await expect(keyInput).toBeEnabled();
        await keyInput.fill(onPremKey as string);
        await page.getByRole("button", { name: "Start" }).click();
        // Real connection test + model discovery against the on-prem proxy
        // (https://ai.svc.corp.ch/api) can be slow — give it room.
        await expect(successToast).toBeVisible({ timeout: 2 * MINUTE });
      }

      // Approve Alice's deterministic model assignments to hand off to Bob.
      await page.getByRole("button", { name: "OK" }).click();
    });

  },
);
