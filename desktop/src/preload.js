/**
 * preload：最小 contextBridge——渲染层只拿到桌面环境信息，不暴露 Node/Electron 能力。
 */
'use strict'

const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('meloyuDesktop', {
  platform: process.platform,
  desktop: true,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
  },
})
