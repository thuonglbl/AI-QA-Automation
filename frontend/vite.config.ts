import path from "path";
import fs from "fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import dotenv from "dotenv";

dotenv.config({ path: path.resolve(__dirname, "../.env") });

const pkg = JSON.parse(fs.readFileSync(path.resolve(__dirname, "package.json"), "utf-8"));
const commit = process.env.COMMIT_REF || process.env.VITE_COMMIT_REF || "";
const shortCommit = commit ? `-${commit.slice(0, 7)}` : "";
const appVersion = `${process.env.DOCKER_IMAGE_VERSION || pkg.version || "dev"}${shortCommit}`;

// https://vite.dev/config/
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
  // Tailwind v4 via its dedicated Vite plugin (not the @tailwindcss/postcss
  // PostCSS plugin) — avoids the "did not pass the `from` option to
  // postcss.parse" warning that the generic PostCSS path raises in v4.
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/auth": "http://127.0.0.1:8000",
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
