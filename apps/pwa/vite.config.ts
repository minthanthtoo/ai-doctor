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
      includeAssets: ["favicon.svg", "icon-192.png", "icon-512.png", "maskable-512.png"],
      manifest: {
        name: "Personal Health Steward",
        short_name: "Health Steward",
        description: "Private, bilingual, preclinical personal health record and safety-navigation PWA.",
        theme_color: "#0d4740",
        background_color: "#f4f1e8",
        display: "standalone",
        start_url: "/",
        scope: "/",
        icons: [
          {
            src: "/icon-192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "any"
          },
          {
            src: "/icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any"
          },
          {
            src: "/maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable"
          }
        ]
      },
      injectManifest: {
        globPatterns: ["**/*.{js,css,html,json,woff2,png,svg}"]
      }
    })
  ],
  server: {
    port: 4178,
    strictPort: true,
    fs: { allow: ["../.."] }
  }
});
