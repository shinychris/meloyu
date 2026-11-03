import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 代理：浏览器请求 /api/v1/** → {MELOYU_API_TARGET}/api/v1/**
// 默认 8000；本机 8000 被其他项目占用时以 MELOYU_API_TARGET 覆盖，无需改代码
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.MELOYU_API_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // 代码分割（v0.7.0）：react 全家桶一组，其余 node_modules 一组 vendor；
        // 视图级 chunk 由 App.tsx 的 React.lazy 自然切出
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
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
