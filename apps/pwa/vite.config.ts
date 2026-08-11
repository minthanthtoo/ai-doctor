import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      registerType: "autoUpdate",
      includeAssets: [],
      manifest: {
        name: "Personal Health Steward",
        short_name: "Health Steward",
        description: "Private, bilingual, preclinical personal health record and safety-navigation PWA.",
        theme_color: "#0d4740",
        background_color: "#f4f1e8",
        display: "standalone",
        start_url: "/",
        scope: "/"
      },
      injectManifest: {
        globPatterns: ["**/*.{js,css,html,json,woff2}"]
      }
    })
  ],
  server: {
    port: 4178,
    strictPort: true,
    fs: { allow: ["../.."] }
  }
});
