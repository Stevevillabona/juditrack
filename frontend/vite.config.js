import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "JudiTrack — Monitoreo de procesos judiciales",
        short_name: "JudiTrack",
        description: "Monitoreo automático de procesos judiciales colombianos",
        theme_color: "#12213B",
        background_color: "#F6F3EC",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
      workbox: {
        // Las llamadas a /api/* nunca se cachean: el usuario siempre debe
        // ver el estado real de sus procesos, nunca una versión vieja
        // servida offline como si fuera actual.
        runtimeCaching: [
          {
            urlPattern: /\/api\//,
            handler: "NetworkOnly",
          },
        ],
      },
    }),
  ],
  server: {
    host: "0.0.0.0",
    proxy: {
      "/api": process.env.VITE_API_PROXY_TARGET || "http://localhost:8000",
    },
  },
});
