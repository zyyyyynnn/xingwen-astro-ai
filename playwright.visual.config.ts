import { defineConfig, devices } from "@playwright/test";

/**
 * Desktop visual acceptance harness.
 * Boots the Workspace in explicit fixture mode on an isolated port and
 * drives every route/component/state for full-page screenshot capture.
 */
export default defineConfig({
  testDir: "./tests/visual-capture",
  globalSetup: "./tests/visual-capture/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  timeout: 180_000,
  expect: { timeout: 25_000 },
  use: {
    baseURL: "http://127.0.0.1:5199",
    trace: "off",
    video: "off",
    reducedMotion: "reduce",
    screenshot: "off",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport:
          process.env.VISUAL_VIEWPORT === "1280x800"
            ? { width: 1280, height: 800 }
            : { width: 1440, height: 900 },
      },
    },
  ],
  webServer: [
    {
      command:
        "pnpm --filter @xingwen/workspace exec vite --host 127.0.0.1 --port 5199 --strictPort",
      url: "http://127.0.0.1:5199/workspace",
      env: {
        VITE_FIXTURE_MODE: "true",
        VITE_VISUAL_CAPTURE: "true",
      },
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
});
