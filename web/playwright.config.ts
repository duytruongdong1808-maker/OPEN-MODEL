import { defineConfig, devices } from "@playwright/test";

const isCI = !!process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: 1,
  reporter: isCI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "setup", testMatch: /.*\.setup\.ts/ },
    {
      name: "chromium",
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], storageState: ".auth/user.json" },
    },
    ...(process.env.E2E_FULL_MATRIX === "1"
      ? [
          {
            name: "firefox",
            dependencies: ["setup"],
            use: { ...devices["Desktop Firefox"], storageState: ".auth/user.json" },
          },
        ]
      : []),
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: isCI ? "npm run start" : "npm run dev",
        port: 3000,
        reuseExistingServer: !isCI,
        timeout: 180_000,
      },
});
