import { defineConfig } from "@playwright/test";
import defaultConfig from "./playwright.config";

export default defineConfig({
  ...defaultConfig,
  use: {
    ...defaultConfig.use,
    baseURL: "http://127.0.0.1:5174",
  },
  webServer: [],
});
