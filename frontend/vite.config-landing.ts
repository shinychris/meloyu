import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 官网营销站构建（F7）：单一入口 landing.html → dist-landing/
// portal 以 PORTAL_LANDING_DIR（默认 frontend/dist-landing）静态托管；
// 与 App 构建（vite.config.ts → dist/）互不影响。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist-landing",
    emptyOutDir: true,
    rollupOptions: {
      input: "landing.html",
      output: {
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (
            /[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/.test(
              id,
            )
          ) {
            return "react-vendor";
          }
          return "vendor";
        },
      },
    },
  },
});
