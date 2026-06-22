import process from "node:process";
import type { APIRequestContext, Page } from "@playwright/test";
import { expect } from "@playwright/test";

/**
 * UI-driving helpers shared by the flow groups. These encapsulate the proven
 * selectors lifted from the original per-story specs so a group can "log in once
 * and walk the whole journey" without re-deriving the steps.
 *
 * The on-premises pipeline helpers (Bob/Mary/Sarah) drive a REAL backend with a
 * REAL slow LLM (no mocking — project-context rule). They use generous timeouts
 * and progression-marker assertions rather than exact LLM output, because the
 * number of generated test cases / scripts and their content vary per run.
 */

const apiBaseUrl = process.env.API_URL ?? "http://localhost:8000";

export type TestUser = { email: string; displayName: string; password: string };

/** Build a unique ephemeral `@example.com` test user (swept by global-teardown). */
export function makeTestUser(prefix: string): TestUser {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return {
    email: `${prefix}-${suffix}@example.com`,
    displayName: `${prefix} ${suffix}`,
    password: "secretpassword",
  };
}

/** Clear any persisted auth/project state so a fresh login starts clean. */
export async function clearClientState(page: Page): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.removeItem("ai-qa-selected-project-id");
    window.localStorage.removeItem("ai-qa-thread-id");
    window.localStorage.removeItem("ai-qa-thread-user-id");
    window.localStorage.removeItem("aiqa_access_token");
    window.localStorage.removeItem("mcp_pat");
  });
}

/** Obtain a bearer token for a standard user via the API. */
export async function loginViaApi(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<string> {
  const response = await request.post(`${apiBaseUrl}/auth/login`, {
    data: { email, password },
  });
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as { access_token: string }).access_token;
}

/** Fill the login form and sign in. Caller asserts the post-login landing. */
export async function loginViaUI(page: Page, user: TestUser): Promise<void> {
  await page.goto("/");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page.getByText(user.displayName)).toBeVisible({ timeout: 15_000 });
}

/** Activate a specific project's starter thread (multi-project groups). */
export async function openProjectThread(
  page: Page,
  projectName: string,
  threadId: string,
): Promise<void> {
  // Projects are single-select in the sidebar: clicking a project name TOGGLES
  // it, and threads only render while that project is expanded (Conversations
  // defaults open). The active project is auto-expanded on load, so blindly
  // clicking its name would COLLAPSE it and hide the thread. Only click the
  // project name when the target thread isn't already shown (i.e. the project
  // is closed); then wait for it to render before selecting it.
  const thread = page.getByTestId(`thread-${threadId}`);
  if (!(await thread.isVisible().catch(() => false))) {
    await page.getByText(projectName).first().click();
    await expect(thread).toBeVisible({ timeout: 15_000 });
  }
  await thread.click();
}

/**
 * On Alice's provider step: select On-Premises, enter the key, run the real
 * connection test + discovery, then approve the model assignments.
 */
export async function configureOnPremProvider(
  page: Page,
  onPremKey: string,
): Promise<void> {
  await expect(
    page.getByText(/Which AI provider would you like to use/i),
  ).toBeVisible({ timeout: 15_000 });

  const card = page.getByTestId("provider-card-on-premises");
  await expect(card).toBeVisible();
  // Cards stay disabled (opacity-50) until the WebSocket reports ready.
  await expect(card).not.toHaveClass(/opacity-50/, { timeout: 30_000 });
  await card.click();

  const keyInput = page.getByTestId("credential-input-api_key");
  await expect(keyInput).toBeVisible();
  await expect(keyInput).toBeEnabled();
  await keyInput.fill(onPremKey);
  await page.getByRole("button", { name: "Start" }).click();

  await expect(page.getByText(/Connected successfully to/i).first()).toBeVisible({
    timeout: 30_000,
  });
  // Alice presents model assignments and waits for confirmation before Bob.
  await page.getByRole("button", { name: "OK" }).click();
}

/**
 * Drive Bob: submit the MCP key, confirm the suggested parent page, wait for the
 * real extraction + auto-save of the page tree, submit the root page id, and
 * wait for the hand-off to Mary.
 */
export async function runBobExtraction(
  page: Page,
  opts: {
    mcpKey: string;
    selectedId: string;
    confirmTimeout?: number;
    extractTimeout?: number;
  },
): Promise<void> {
  const {
    mcpKey,
    selectedId,
    confirmTimeout = 90_000,
    extractTimeout = 240_000,
  } = opts;

  const mcpInput = page.getByPlaceholder(/Enter MCP API Key/i);
  await expect(mcpInput).toBeVisible({ timeout: 15_000 });
  await mcpInput.fill(mcpKey);
  await page.getByRole("button", { name: /^Start$/i }).click();

  // Bob suggests the requirement page and asks to confirm (pre-filled URL).
  const parentUrlInput = page.getByPlaceholder(/Enter a parent page URL/i);
  await expect(parentUrlInput).toBeVisible({ timeout: confirmTimeout });
  await parentUrlInput
    .locator("xpath=following-sibling::button[normalize-space()='OK']")
    .click();

  // After extraction + auto-save, Bob renders the single-id input card.
  const idInput = page.getByPlaceholder(/TOOL-1635/i);
  await expect(idInput).toBeVisible({ timeout: extractTimeout });
  await idInput.fill(selectedId);
  await idInput
    .locator("xpath=following-sibling::button[normalize-space()='OK']")
    .click();

  await expect(page.getByText(/Handing off to Mary/i)).toBeVisible({
    timeout: 60_000,
  });
}

/** Read Mary's current review header (e.g. "Review Test Case (2 of 5) — …"). */
async function maryReviewHeader(page: Page): Promise<string | null> {
  const header = page.getByText(/Review Test Case \(\d+ of \d+\)/);
  if ((await header.count()) === 0) return null;
  return header.first().textContent();
}

/**
 * Approve every test case Mary generates until she reports done and the
 * "Proceed to Sarah" affordance appears.
 *
 * Mary generates cases one at a time on a slow on-prem model, so the first panel
 * can take minutes. After each approval the panel auto-advances to the next
 * unresolved case (the header index changes); approving the last one flips the
 * server status to done and swaps the panel for the Proceed button. We wait for
 * the header to change (or Proceed to show) between clicks so we never
 * double-approve the same case.
 */
export async function approveAllMaryTestCases(
  page: Page,
  opts: { genTimeout?: number; maxCases?: number } = {},
): Promise<void> {
  const { genTimeout = 360_000, maxCases = 40 } = opts;
  const proceed = page.getByRole("button", { name: /Proceed to Sarah/i });
  const approve = page.getByRole("button", { name: "Approve" });
  // Mary may interleave a quality-clarification question; skipping it keeps the
  // unattended run moving (the answer path needs a human).
  const skipQuestion = page.getByRole("button", { name: /Skip this question/i });

  for (let i = 0; i < maxCases; i++) {
    if (await proceed.isVisible()) return;

    // Wait for a case to review, a clarify question to skip, or Mary to finish.
    const ready = await Promise.race([
      approve
        .waitFor({ state: "visible", timeout: genTimeout })
        .then(() => "approve" as const)
        .catch(() => "timeout" as const),
      proceed
        .waitFor({ state: "visible", timeout: genTimeout })
        .then(() => "proceed" as const)
        .catch(() => "timeout" as const),
      skipQuestion
        .waitFor({ state: "visible", timeout: genTimeout })
        .then(() => "clarify" as const)
        .catch(() => "timeout" as const),
    ]);
    if (ready === "proceed" || ready === "timeout") break;
    if (ready === "clarify") {
      await skipQuestion.click();
      continue;
    }

    const before = await maryReviewHeader(page);
    await approve.click();

    // Wait until the panel moves on (next case) or Mary finishes.
    await expect
      .poll(
        async () => {
          if (await proceed.isVisible()) return "done";
          const now = await maryReviewHeader(page);
          return now !== before ? "advanced" : "same";
        },
        { timeout: genTimeout, intervals: [500, 1000, 2000, 5000] },
      )
      .not.toBe("same");
  }

  await expect(proceed).toBeVisible({ timeout: genTimeout });
}

/**
 * Drive Sarah from Mary's "Proceed to Sarah" affordance through to approving at
 * least one generated script: submit the inputs form (app URL; no Chrome/CDP so
 * Sarah falls back to LLM-only generation), confirm the test-case selection if
 * one is shown, then approve each script in the review panel.
 */
export async function runSarahToScriptApproval(
  page: Page,
  opts: { targetUrl: string; genTimeout?: number },
): Promise<void> {
  const { targetUrl, genTimeout = 360_000 } = opts;

  const proceed = page.getByRole("button", { name: /Proceed to Sarah/i });
  await expect(proceed).toBeVisible({ timeout: 30_000 });
  await proceed.click();

  // Sarah asks for the target URL + browser source. Leaving Chrome/CDP blank
  // lets exploration fall back to LLM-only, which needs no local browser.
  const form = page.getByTestId("sarah-inputs-form");
  await expect(form).toBeVisible({ timeout: 60_000 });
  const urlInput = page.getByTestId("sarah-target-url");
  if (await urlInput.isVisible()) {
    await urlInput.fill(targetUrl);
  }
  await page.getByTestId("sarah-inputs-submit").click();

  // Next is either a test-case selection panel or directly the script review.
  const confirmGenerate = page.getByRole("button", { name: /Confirm & Generate/i });
  const scriptApprove = page.getByRole("button", { name: "Approve" });
  const next = await Promise.race([
    confirmGenerate
      .waitFor({ state: "visible", timeout: genTimeout })
      .then(() => "select" as const)
      .catch(() => "timeout" as const),
    scriptApprove
      .waitFor({ state: "visible", timeout: genTimeout })
      .then(() => "review" as const)
      .catch(() => "timeout" as const),
  ]);

  if (next === "select") {
    // Default-selected cases are pre-checked; confirm to generate scripts.
    await confirmGenerate.click();
    await expect(scriptApprove).toBeVisible({ timeout: genTimeout });
  } else if (next === "timeout") {
    throw new Error("Sarah produced neither a selection panel nor a script.");
  }

  // Approve the generated script and confirm the approval registered (the panel
  // renders an "Approved by … · …" caption once the server records it). We
  // approve a single script — that proves Sarah produced an approvable script
  // and the approve action round-trips; driving every script of a multi-script
  // batch is out of scope for this live smoke.
  await expect(scriptApprove).toBeVisible({ timeout: genTimeout });
  await scriptApprove.click();
  await expect(page.getByText(/Approved/i).first()).toBeVisible({
    timeout: genTimeout,
  });
}

/**
 * Drive the Claude SSO "Login SSO" seam against the mock IdP: select the SSO
 * provider card, open the IdP tab, authenticate, and confirm the SPA proceeds.
 * (Claude SSO is not fully provisioned — `CLAUDE_SSO_ENTERPRISE_API_KEY` is
 * empty — so this asserts the login seam, not a completed connection.)
 */
export async function loginViaClaudeSso(
  page: Page,
  creds: { email: string; password: string },
): Promise<void> {
  await expect(
    page.getByText(/Which AI provider would you like to use/i),
  ).toBeVisible({ timeout: 15_000 });

  const ssoCard = page.getByTestId("provider-card-claude-sso");
  await expect(ssoCard).toBeVisible();
  await expect(ssoCard).not.toHaveClass(/opacity-50/, { timeout: 30_000 });
  await ssoCard.click();

  const loginButton = page.getByTestId("sso-login-button");
  await expect(loginButton).toBeVisible();

  // The button opens the IdP in a new tab via window.open(..., noopener), so
  // capture it at the browser-context level (no opener relationship).
  const popupPromise = page.context().waitForEvent("page");
  await loginButton.click();
  const popup = await popupPromise;
  await popup.waitForLoadState();

  await popup.getByTestId("sso-email").fill(creds.email);
  await popup.getByTestId("sso-password").fill(creds.password);
  await popup.getByTestId("sso-submit").click();
  await expect(popup.getByTestId("sso-success")).toBeVisible({ timeout: 15_000 });

  // Back in the SPA: the connection step begins (the outcome depends on the
  // deployment's enterprise key, so assert the step starts, not its result).
  await expect(
    page
      .getByText(/Testing connection to|Connected successfully to|not configured/i)
      .first(),
  ).toBeVisible({ timeout: 30_000 });
}
