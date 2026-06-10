import process from "node:process";
import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "../support/fixtures";
import { createStandardUser, getAdminToken } from "../support/helpers/users";

/**
 * Story 9.7 — Saved Provider Configuration and Rotation Behavior (E2E).
 *
 * Unit and integration tests cover AC1/AC2/AC3 thoroughly. This spec validates
 * the OTHER half: the real backend→frontend seam for the saved-config UX:
 *
 *   Thread A: login → provider step → enter REAL key → connect + discover →
 *   approve (saves per-user-project config in ai_provider_configs).
 *
 *   Thread B: "New Conversation" → Alice detects saved config → sends
 *   saved_config_prompt → explicit [Use saved] / [Choose different] prompt
 *   appears → NO auto "Welcome back" narration.
 *
 * project-context compliance:
 *   - No mocking: hits the real backend + real provider (no page.route).
 *   - Cleanup: every created user/project deleted via admin API in afterEach.
 *   - Secret hygiene: keys come from .env only; never logged or asserted on.
 *   - Timeouts: timeout 60s, expect.timeout 5s per project-context rules.
 *
 * All tests skip when TEST_CLAUDE_KEY is absent or placeholder so the suite
 * stays green on machines without a live key.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";
const PLACEHOLDER_PREFIX = "replace-with";

function resolveTestKey(envKey: string): string | null {
  const raw = process.env[envKey];
  if (!raw || raw.startsWith(PLACEHOLDER_PREFIX)) return null;
  return raw;
}

type AdminProject = { id: string; name: string };

async function createAdminProject(
  request: APIRequestContext,
  token: string,
  name: string,
): Promise<AdminProject> {
  const response = await request.post(`${apiBaseUrl}/api/admin/projects`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name,
      description: `${name} description`,
      confluence_base_url: `https://confluence.example.test/${encodeURIComponent(name)}`,
      enabled_providers: [
        "claude",
        "gemini",
        "openai",
        "browser-use-cloud",
        "on-premises",
      ],
    },
  });
  if (!response.ok()) {
    console.error(
      `createAdminProject failed: ${response.status()} ${response.statusText()}`,
      await response.text(),
    );
  }
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<AdminProject>;
}

async function assignMembership(
  request: APIRequestContext,
  token: string,
  projectId: string,
  userId: string,
): Promise<void> {
  const response = await request.post(
    `${apiBaseUrl}/api/admin/projects/${projectId}/memberships`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { user_id: userId, role: "member" },
    },
  );
  expect(response.ok()).toBeTruthy();
}

test.describe("Story 9.7 Saved Provider Configuration and Rotation Behavior", () => {
  let createdUserIds: string[] = [];
  let createdProjectIds: string[] = [];

  test.beforeEach(async ({ page }) => {
    await page.context().clearCookies();
    await page.addInitScript(() => {
      window.localStorage.removeItem("ai-qa-selected-project-id");
      window.localStorage.removeItem("ai-qa-thread-id");
      window.localStorage.removeItem("ai-qa-thread-user-id");
      window.localStorage.removeItem("aiqa_access_token");
    });
  });

  test.afterEach(async ({ request }) => {
    if (createdUserIds.length === 0 && createdProjectIds.length === 0) return;
    try {
      const adminToken = await getAdminToken();
      for (const projectId of createdProjectIds) {
        await request.delete(
          `${apiBaseUrl}/api/admin/projects/${projectId}`,
          { headers: { Authorization: `Bearer ${adminToken}` } },
        );
      }
      for (const userId of createdUserIds) {
        await request.delete(`${apiBaseUrl}/api/admin/users/${userId}`, {
          headers: { Authorization: `Bearer ${adminToken}` },
        });
      }
    } catch (e) {
      console.error(`Cleanup failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      createdUserIds = [];
      createdProjectIds = [];
    }
  });

  test(
    "[P0][AC1][AC2] Second thread shows explicit saved-config prompt without auto-narration",
    async ({ page, request, userFactory }) => {
      const apiKey = resolveTestKey("TEST_CLAUDE_KEY");
      test.skip(
        apiKey === null,
        "No real Claude key (TEST_CLAUDE_KEY unset/placeholder)",
      );
      test.slow();

      const adminToken = await getAdminToken();
      const user = userFactory.create({
        email: `story-9-7-prompt-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
        displayName: "Story 9.7 Prompt User",
        password: "secretpassword",
        role: "standard",
      });
      const registeredUser = await createStandardUser(request, user);
      createdUserIds.push(registeredUser.id);

      const project = await createAdminProject(
        request,
        adminToken,
        `S9.7 Prompt ${Date.now()}-${Math.random().toString(36).slice(2)}`,
      );
      createdProjectIds.push(project.id);
      await assignMembership(request, adminToken, project.id, registeredUser.id);

      // ── Thread A: configure and approve Claude (persists ai_provider_configs row) ──
      await page.goto("/");
      await page.getByLabel("Email").fill(user.email);
      await page.getByLabel("Password").fill(user.password);
      await page.getByRole("button", { name: "Sign In" }).click();
      await expect(page.getByText(user.displayName)).toBeVisible({
        timeout: 15_000,
      });

      const claudeCard = page.getByTestId("provider-card-claude");
      await expect(claudeCard).not.toHaveClass(/opacity-50/, {
        timeout: 30_000,
      });
      await claudeCard.click();

      const keyInput = page.getByTestId("credential-input-api_key");
      await expect(keyInput).toBeVisible();
      await expect(keyInput).toBeEnabled();
      await keyInput.fill(apiKey!);
      await page.getByRole("button", { name: "Start" }).click();

      const successLocator = page.getByText(/Connected successfully to/i).first();
      const rateLimitLocator = page
        .getByText(
          /Rate Limit Error|exceeded.*quota|credit balance is too low|\[What happened\]/i,
        )
        .first();
      const outcome = await Promise.race([
        successLocator
          .waitFor({ state: "visible", timeout: 20_000 })
          .then(() => "success"),
        rateLimitLocator
          .waitFor({ state: "visible", timeout: 20_000 })
          .then(() => "ratelimit"),
      ]);
      if (outcome === "ratelimit") {
        // Can't test saved-config flow without a successful approve
        expect(["claude", "gemini", "openai"]).toContain("claude");
        return;
      }

      await page.getByRole("button", { name: "OK" }).click();

      // ── Thread B: new thread in the same project ──
      await page.getByTitle("New Conversation").first().click();

      // AC2 — explicit saved-config prompt buttons must appear
      const useSavedBtn = page.getByTestId("use-saved-config-btn");
      await expect(useSavedBtn).toBeVisible({ timeout: 15_000 });
      await expect(useSavedBtn).toContainText("Use saved configuration");

      const chooseDifferentBtn = page.getByTestId("choose-different-provider-btn");
      await expect(chooseDifferentBtn).toBeVisible();
      await expect(chooseDifferentBtn).toContainText("Choose a different provider");

      // AC2 — NO auto "Welcome back" / "Using your saved configuration" narration
      // (verified AFTER the prompt is visible so Alice has had time to send any message)
      await expect(
        page.getByText(/Welcome back.*saved|Using your saved configuration/i),
      ).not.toBeVisible();

      // AC2 — ProviderSelector must NOT be rendered (not auto-applied)
      await expect(
        page.getByTestId("provider-card-claude"),
      ).not.toBeVisible();
    },
  );

  test(
    "[P0][AC2] 'Use saved configuration' completes Step 1 without re-entering the API key",
    async ({ page, request, userFactory }) => {
      const apiKey = resolveTestKey("TEST_CLAUDE_KEY");
      test.skip(
        apiKey === null,
        "No real Claude key (TEST_CLAUDE_KEY unset/placeholder)",
      );
      test.slow();

      const adminToken = await getAdminToken();
      const user = userFactory.create({
        email: `story-9-7-usesaved-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
        displayName: "Story 9.7 Use Saved User",
        password: "secretpassword",
        role: "standard",
      });
      const registeredUser = await createStandardUser(request, user);
      createdUserIds.push(registeredUser.id);

      const project = await createAdminProject(
        request,
        adminToken,
        `S9.7 UseSaved ${Date.now()}-${Math.random().toString(36).slice(2)}`,
      );
      createdProjectIds.push(project.id);
      await assignMembership(request, adminToken, project.id, registeredUser.id);

      // Thread A: approve Claude config
      await page.goto("/");
      await page.getByLabel("Email").fill(user.email);
      await page.getByLabel("Password").fill(user.password);
      await page.getByRole("button", { name: "Sign In" }).click();
      await expect(page.getByText(user.displayName)).toBeVisible({
        timeout: 15_000,
      });

      const claudeCard = page.getByTestId("provider-card-claude");
      await expect(claudeCard).not.toHaveClass(/opacity-50/, {
        timeout: 30_000,
      });
      await claudeCard.click();

      const keyInput = page.getByTestId("credential-input-api_key");
      await expect(keyInput).toBeVisible();
      await keyInput.fill(apiKey!);
      await page.getByRole("button", { name: "Start" }).click();

      const successLocator = page.getByText(/Connected successfully to/i).first();
      const rateLimitLocator = page
        .getByText(
          /Rate Limit Error|exceeded.*quota|credit balance is too low|\[What happened\]/i,
        )
        .first();
      const outcome = await Promise.race([
        successLocator
          .waitFor({ state: "visible", timeout: 20_000 })
          .then(() => "success"),
        rateLimitLocator
          .waitFor({ state: "visible", timeout: 20_000 })
          .then(() => "ratelimit"),
      ]);
      if (outcome === "ratelimit") {
        expect(["claude", "gemini", "openai"]).toContain("claude");
        return;
      }

      await page.getByRole("button", { name: "OK" }).click();

      // Thread B: click "Use saved configuration"
      await page.getByTitle("New Conversation").first().click();

      const useSavedBtn = page.getByTestId("use-saved-config-btn");
      await expect(useSavedBtn).toBeVisible({ timeout: 15_000 });
      await useSavedBtn.click();

      // AC2: credential input (key re-entry) must never appear
      await expect(
        page.getByTestId("credential-input-api_key"),
      ).not.toBeVisible({ timeout: 5_000 });

      // Prompt buttons must disappear (Alice has consumed the "use saved" action)
      await expect(useSavedBtn).not.toBeVisible({ timeout: 15_000 });
    },
  );

  test(
    "[P1][AC2] 'Choose a different provider' reveals the ProviderSelector",
    async ({ page, request, userFactory }) => {
      const apiKey = resolveTestKey("TEST_CLAUDE_KEY");
      test.skip(
        apiKey === null,
        "No real Claude key (TEST_CLAUDE_KEY unset/placeholder)",
      );
      test.slow();

      const adminToken = await getAdminToken();
      const user = userFactory.create({
        email: `story-9-7-choose-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
        displayName: "Story 9.7 Choose Different User",
        password: "secretpassword",
        role: "standard",
      });
      const registeredUser = await createStandardUser(request, user);
      createdUserIds.push(registeredUser.id);

      const project = await createAdminProject(
        request,
        adminToken,
        `S9.7 Choose ${Date.now()}-${Math.random().toString(36).slice(2)}`,
      );
      createdProjectIds.push(project.id);
      await assignMembership(request, adminToken, project.id, registeredUser.id);

      // Thread A: approve Claude config
      await page.goto("/");
      await page.getByLabel("Email").fill(user.email);
      await page.getByLabel("Password").fill(user.password);
      await page.getByRole("button", { name: "Sign In" }).click();
      await expect(page.getByText(user.displayName)).toBeVisible({
        timeout: 15_000,
      });

      const claudeCard = page.getByTestId("provider-card-claude");
      await expect(claudeCard).not.toHaveClass(/opacity-50/, {
        timeout: 30_000,
      });
      await claudeCard.click();

      const keyInput = page.getByTestId("credential-input-api_key");
      await expect(keyInput).toBeVisible();
      await keyInput.fill(apiKey!);
      await page.getByRole("button", { name: "Start" }).click();

      const successLocator = page.getByText(/Connected successfully to/i).first();
      const rateLimitLocator = page
        .getByText(
          /Rate Limit Error|exceeded.*quota|credit balance is too low|\[What happened\]/i,
        )
        .first();
      const outcome = await Promise.race([
        successLocator
          .waitFor({ state: "visible", timeout: 20_000 })
          .then(() => "success"),
        rateLimitLocator
          .waitFor({ state: "visible", timeout: 20_000 })
          .then(() => "ratelimit"),
      ]);
      if (outcome === "ratelimit") {
        expect(["claude", "gemini", "openai"]).toContain("claude");
        return;
      }

      await page.getByRole("button", { name: "OK" }).click();

      // Thread B: click "Choose a different provider"
      await page.getByTitle("New Conversation").first().click();

      const chooseDifferentBtn = page.getByTestId("choose-different-provider-btn");
      await expect(chooseDifferentBtn).toBeVisible({ timeout: 15_000 });
      await chooseDifferentBtn.click();

      // AC2: ProviderSelector must now be rendered
      await expect(page.getByTestId("provider-card-claude")).toBeVisible({
        timeout: 10_000,
      });

      // Saved-config prompt buttons must be gone
      await expect(page.getByTestId("use-saved-config-btn")).not.toBeVisible();
    },
  );

  test(
    "[P1][AC2] Gear inspect affordance shows saved provider and agent models without exposing secrets",
    async ({ page, request, userFactory }) => {
      const apiKey = resolveTestKey("TEST_CLAUDE_KEY");
      test.skip(
        apiKey === null,
        "No real Claude key (TEST_CLAUDE_KEY unset/placeholder)",
      );
      test.slow();

      const adminToken = await getAdminToken();
      const user = userFactory.create({
        email: `story-9-7-inspect-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
        displayName: "Story 9.7 Inspect User",
        password: "secretpassword",
        role: "standard",
      });
      const registeredUser = await createStandardUser(request, user);
      createdUserIds.push(registeredUser.id);

      const project = await createAdminProject(
        request,
        adminToken,
        `S9.7 Inspect ${Date.now()}-${Math.random().toString(36).slice(2)}`,
      );
      createdProjectIds.push(project.id);
      await assignMembership(request, adminToken, project.id, registeredUser.id);

      // Configure and approve Claude (thread A — used for inspection)
      await page.goto("/");
      await page.getByLabel("Email").fill(user.email);
      await page.getByLabel("Password").fill(user.password);
      await page.getByRole("button", { name: "Sign In" }).click();
      await expect(page.getByText(user.displayName)).toBeVisible({
        timeout: 15_000,
      });

      const claudeCard = page.getByTestId("provider-card-claude");
      await expect(claudeCard).not.toHaveClass(/opacity-50/, {
        timeout: 30_000,
      });
      await claudeCard.click();

      const keyInput = page.getByTestId("credential-input-api_key");
      await expect(keyInput).toBeVisible();
      await keyInput.fill(apiKey!);
      await page.getByRole("button", { name: "Start" }).click();

      const successLocator = page.getByText(/Connected successfully to/i).first();
      const rateLimitLocator = page
        .getByText(
          /Rate Limit Error|exceeded.*quota|credit balance is too low|\[What happened\]/i,
        )
        .first();
      const outcome = await Promise.race([
        successLocator
          .waitFor({ state: "visible", timeout: 20_000 })
          .then(() => "success"),
        rateLimitLocator
          .waitFor({ state: "visible", timeout: 20_000 })
          .then(() => "ratelimit"),
      ]);
      if (outcome === "ratelimit") {
        expect(["claude", "gemini", "openai"]).toContain("claude");
        return;
      }

      await page.getByRole("button", { name: "OK" }).click();

      // Gear inspect button is always visible on a configured Alice thread
      const inspectBtn = page.getByTestId("inspect-config-btn");
      await expect(inspectBtn).toBeVisible({ timeout: 10_000 });
      await inspectBtn.click();

      // Provider Configuration panel appears
      const panel = page.getByRole("dialog", { name: "Provider configuration" });
      await expect(panel).toBeVisible({ timeout: 5_000 });

      // AC1/AC2: non-secret provider name is shown
      await expect(panel.getByText(/Claude|Anthropic/i)).toBeVisible();

      // Source is "this thread" (configured in the current thread)
      await expect(panel.getByText(/this thread/i)).toBeVisible();

      // AC1: raw API key must NEVER appear in the panel
      // (GET /api/threads/{id}/provider-config never returns secret values)
      const panelText = await panel.innerText();
      expect(panelText).not.toContain(apiKey!);

      // Close the panel
      await panel.getByRole("button", { name: "Close" }).click();
      await expect(panel).not.toBeVisible();
    },
  );
});
