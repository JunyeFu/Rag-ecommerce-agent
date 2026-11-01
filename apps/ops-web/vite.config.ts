import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const apiUrl = process.env.RAG_API_URL ?? "http://127.0.0.1:20881";

export default defineConfig({
  plugins: [react()],
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
  server: {
    proxy: {
      "/v1": apiUrl,
      "/health": apiUrl,
    },
  },
});
