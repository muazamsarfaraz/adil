import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 60000,
  retries: 1,
  use: {
    baseURL: process.env.TEST_URL || "https://frontend-production-d4c6.up.railway.app",
    viewport: { width: 1280, height: 800 },
    actionTimeout: 15000,
  },
  reporter: [["list"]],
});
