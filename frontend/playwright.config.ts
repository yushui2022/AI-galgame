import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:5187",
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ],
  webServer: [
    {
      command: "uv run --project .. uvicorn e2e_app:app --app-dir ../backend/tests --host 127.0.0.1 --port 8765",
      port: 8765,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000
    },
    {
      command: "npx vite --host 127.0.0.1 --port 5187",
      port: 5187,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000
    }
  ]
});
