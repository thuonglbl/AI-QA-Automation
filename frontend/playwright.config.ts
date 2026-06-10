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
    baseURL: process.env.BASE_URL || "http://localhost:5173", // Default for Vite local
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
        },
      },
    },
  ],
  // Boot (and wait for) the backend + Vite dev server before running tests.
  // reuseExistingServer keeps already-running local servers (and the admin
  // in-app runner) untouched; in CI a fresh pair is started each run.
  webServer: [
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
