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
      command:
        "pnpm --filter @xingwen/site build && pnpm --filter @xingwen/site exec astro preview --host 127.0.0.1 --port 14321",
      url: "http://127.0.0.1:14321",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command:
        "pnpm --filter @xingwen/workspace exec vite --host 127.0.0.1 --port 15173 --strictPort",
      url: "http://127.0.0.1:15173",
      env: {
        VITE_API_BASE_URL: "http://localhost:8000",
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
