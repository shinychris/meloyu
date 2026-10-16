/// <reference types="vite/client" />

/**
 * Electron preload 注入的桌面环境桥（desktop/src/preload.js）。
 * 仅在桌面壳内存在；云形态/裸浏览器为 undefined——用作桌面判定信号之一
 * （F3 修复：冷启动免登录直达，不依赖登录后才能拉到的 license.mode）。
 */
declare global {
  interface Window {
    meloyuDesktop?: {
      platform: string
      desktop: true
      versions: { electron: string; chrome: string }
    }
  }
}

export {}
