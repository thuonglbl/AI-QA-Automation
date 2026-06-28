import { defineConfig, devices } from "@playwright/test";
import * as dotenv from "dotenv";
import path from "node:path";
import { fileURLToPath } from "node:url";

// 1. Restore __dirname in ES Module
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 2. Load env vars (quiet: true suppresses dotenv v17's "injected env" banner)
dotenv.config({ path: path.resolve(__dirname, "../.env"), quiet: true });

if (!process.env.BASE_URL) {
  dotenv.config({
    path: path.resolve(__dirname, "../.env.example"),
    quiet: true,
  });
}

const slowMo = parseInt(process.env.PLAYWRIGHT_SLOW_MO || "0");

// Resolve + validate the app base URL. BASE_URL can arrive from the shell, the
// in-app admin runner (which copies the backend's os.environ), or `.env`. A
// truthy-but-malformed value (missing scheme like "localhost:5173", a stray
// space, or an un-stripped trailing comment) makes Playwright fail EVERY
// page.goto("/") with a cryptic "Cannot navigate to invalid URL". Fail fast
// here with an actionable message that names the offending value instead.
const DEFAULT_BASE_URL = "http://localhost:5173"; // Vite dev server
function resolveBaseURL(): string {
  const raw = process.env.BASE_URL?.trim();
  if (!raw) return DEFAULT_BASE_URL; // unset/blank → local default
  try {
    const { protocol } = new URL(raw);
    if (protocol !== "http:" && protocol !== "https:") {
      throw new Error(`unsupported protocol "${protocol}"`);
    }
    return raw;
  } catch {
    throw new Error(
      `Invalid BASE_URL=${JSON.stringify(process.env.BASE_URL)} — it must be an ` +
        `absolute http(s) URL (e.g. ${DEFAULT_BASE_URL} or ` +
        `https://ai-qa.ai-uat.corpdev.local). Fix it in .env, or unset it in the ` +
        `shell/process that launches the run to use the default.`,
    );
  }
}
const baseURL = resolveBaseURL();

// 3. Config
export default defineConfig({
  testDir: "./e2e",
  // Sweep any leftover test users/projects after the whole suite. Per-spec
  // afterEach hooks miss data when a test crashes mid-body or a worker dies;
  // this teardown is the safety net (deleting a test user cascades to its
  // threads / agent_runs / messages via ON DELETE CASCADE).
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  timeout: 60 * 1000,
  expect: {
    timeout: 5000,
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ["html"],
    ["junit", { outputFile: "../_bmad-output/test-artifacts/results.xml" }],
    ["list"],
  ],
  use: {
    actionTimeout: 15 * 1000,
    navigationTimeout: 60 * 1000,
    baseURL, // validated above; falls back to the Vite local default
    // The in-app runner targets the deployed HTTPS app on the server, which may
    // use an internal/self-signed certificate. Only relaxed when explicitly opted in.
    ignoreHTTPSErrors: process.env.PLAYWRIGHT_IGNORE_HTTPS_ERRORS === "1",
    trace: "retain-on-failure-and-retries",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    testIdAttribute: "data-testid",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          slowMo: Number.isFinite(slowMo) ? slowMo : 0,
          // Inside the backend container Chromium runs as root, where the
          // sandbox must be disabled, and /dev/shm is too small. Opt-in only so
          // local developer runs keep the default hardened browser.
          args:
            process.env.E2E_NO_SANDBOX === "1"
              ? ["--no-sandbox", "--disable-dev-shm-usage"]
              : [],
        },
      },
    },
  ],
  // Boot (and wait for) the backend + Vite dev server before running tests.
  // reuseExistingServer keeps already-running local servers untouched; in CI a
  // fresh pair is started each run.
  //
  // The in-app admin runner (POST /api/admin/tests/e2e) sets
  // E2E_DISABLE_WEBSERVER=1 because the backend and frontend are ALREADY running
  // when the button is clicked — locally (uvicorn + Vite) and on the deployed
  // server (the backend container + the Nginx frontend). Booting a second
  // backend would collide on port 8000, and the backend container has no Vite to
  // boot at all. Terminal runs (`npx playwright test e2e`) leave the flag unset
  // and still auto-boot the pair.
  webServer:
    process.env.E2E_DISABLE_WEBSERVER === "1"
      ? undefined
      : [
          {
            command: "uv run ai-qa",
            cwd: path.resolve(__dirname, ".."),
            url: "http://127.0.0.1:8000/auth/status",
            reuseExistingServer: !process.env.CI,
            timeout: 120 * 1000,
            stdout: "pipe",
            stderr: "pipe",
          },
          {
            command: "npm run dev",
            cwd: __dirname,
            url: "http://localhost:5173",
            reuseExistingServer: !process.env.CI,
            timeout: 120 * 1000,
            stdout: "pipe",
            stderr: "pipe",
          },
        ],
});
