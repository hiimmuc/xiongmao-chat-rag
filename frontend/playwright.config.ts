import { defineConfig } from "@playwright/test";
// Port 5180, so the test can run while the local app uses 5173.
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://127.0.0.1:5180" },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5180 --strictPort",
    url: "http://127.0.0.1:5180",
    reuseExistingServer: false,
    env: { VITE_API_URL: "http://127.0.0.1:8000/api/v1" }, // every API call is mocked in the test
  },
});
