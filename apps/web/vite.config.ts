import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8471",
      "/v1": "http://127.0.0.1:8471",
    },
  },
});
