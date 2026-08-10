import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: "pnpm --filter @xingwen/site dev",
      url: "http://127.0.0.1:4321",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "pnpm --filter @xingwen/workspace dev",
      url: "http://127.0.0.1:5173",
      env: {
        VITE_API_BASE_URL: "http://localhost:8000",
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
