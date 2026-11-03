/**
 * 生成 desktop/THIRD-PARTY-NOTICES.md（法务交付标配）。
 *
 * 数据源：
 *  1. npm 生产依赖 —— license-checker-rseidelsohn（--production，不含 devDependencies）
 *  2. 后端 sidecar 依赖 —— backend venv 的 pip-licenses（PyInstaller 按该环境打包；
 *     构建工具类包手工剔除）
 *
 * 运行：npm run notices（依赖需已 npm install / pip install pip-licenses）
 * 发布纪律：每次打包前重跑，产物随包分发（electron-builder extraResources 已接线）。
 */
'use strict'

import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const DESKTOP = path.resolve(HERE, '..')
const REPO = path.resolve(DESKTOP, '..')
const VENV_PY = path.join(REPO, 'backend', '.venv',
  process.platform === 'win32' ? 'Scripts\\python.exe' : 'bin/python')

// 构建工具类（不随安装包分发）：PyInstaller 及其依赖 / 许可清单工具 / 图标工具
const PY_EXCLUDE = new Set([
  'pyinstaller', 'altgraph', 'pefile', 'pywin32-ctypes',
  'piplicenses', 'pip-licenses', 'license-expression', 'boolean.py',
  'prettytable', 'wcwidth', 'pillow', 'pip', 'setuptools', 'wheel',
])

function npmLicenses() {
  const out = execFileSync('npx', ['license-checker-rseidelsohn', '--production', '--json'], {
    cwd: DESKTOP, encoding: 'utf-8', shell: process.platform === 'win32',
  })
  const json = JSON.parse(out)
  return Object.entries(json)
    .filter(([pkg]) => !pkg.startsWith('meloyu-desktop@')) // 自身不属于三方组件
    .map(([pkg, meta]) => {
      const [name, ...rest] = pkg.split('@')
      return {
        name,
        version: rest.join('@') || meta.version || '',
        license: Array.isArray(meta.licenses) ? meta.licenses.join(' AND ') : (meta.licenses || 'UNKNOWN'),
        repo: meta.repository || '',
      }
    })
    .sort((a, b) => a.name.localeCompare(b.name))
}

function pythonLicenses() {
  const out = execFileSync(VENV_PY, ['-m', 'piplicenses', '--format=json', '--with-urls'], {
    encoding: 'utf-8',
  })
  return JSON.parse(out)
    .filter((p) => !PY_EXCLUDE.has((p.Name || '').toLowerCase()))
    .map((p) => ({
      name: p.Name,
      version: p.Version,
      license: p.License || 'UNKNOWN',
      repo: p.URL || '',
    }))
    .sort((a, b) => a.name.localeCompare(b.name))
}

function table(rows) {
  if (rows.length === 0) return '_（无）_\n'
  const head = '| 组件 | 版本 | 许可 | 上游 |\n|---|---|---|---|\n'
  const body = rows
    .map((r) => `| ${r.name} | ${r.version} | ${r.license} | ${r.repo || '—'} |`)
    .join('\n')
  return head + body + '\n'
}

const npm = npmLicenses()
const py = pythonLicenses()
const now = new Date().toISOString().slice(0, 10)

const md = `# Third-Party Notices

Meloyu Desktop（© 2026 Meloyu）包含两个随包分发的运行时，其第三方组件许可如下。
本文件由 \`npm run notices\` 生成（${now}），随安装包分发并位于安装目录 resources/ 下；
完整许可文本见各组件上游仓库（Repository 列）。

## 1. Electron 壳（Node.js 运行时依赖）

Electron/Chromium/Node.js 本体的许可随 Electron 发行版分发
（MIT 及 BSD 风格许可，全文见 electron npm 包内 LICENSE 文件）。

${table(npm)}
## 2. 后端 sidecar（Python 运行时依赖，PyInstaller --onedir 打包）

可选本地组件（按需下载，不随本包分发）：MusicGen 权重（CC-BY-NC 4.0，产出非商用）、
ACE-Step v1.5（MIT，代码与权重）。云通道（OpenAI 兼容 API / Suno 兼容网关 /
Replicate）为用户自有 Key 的外部服务，不在分发范围内。

${table(py)}
`

const outPath = path.join(DESKTOP, 'THIRD-PARTY-NOTICES.md')
writeFileSync(outPath, md, 'utf-8')
console.log(`written: ${outPath} (npm ${npm.length} + python ${py.length} components)`)
