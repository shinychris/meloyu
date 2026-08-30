# Meloyu 旋律屿 · 前端（React SPA）

AI 音乐创作系统的浏览器前端：Vite + React 19 + TypeScript(strict) + Tailwind CSS v4 + Zustand + React Router 7（library 模式，HashRouter）。视觉规范逐项对齐 `docs/AI音乐创作系统方案和原型/app/` 高保真原型（暗色 #0e0e0e / 荧光绿 #00ff2c / Inter + Noto Sans SC / 直角无圆角）。

## 启动

```bash
cd frontend
npm install        # Node ≥ 20，npm ≥ 10
npm run dev        # http://localhost:5173（/api 代理到 127.0.0.1:8000）
```

后端（`backend/`，FastAPI :8000）需同时运行；无后端时页面会停在登录页，`/system/meta` 拉取失败会静默回退到与契约一致的本地枚举兜底。

演示账号：`demo@meloyu.local / Demo123456!`

## 常用命令

| 命令 | 说明 |
|---|---|
| `npm run dev` | 开发服务器（HMR） |
| `npm run build` | `tsc --noEmit` 类型检查 + `vite build` 产出 `dist/` |
| `npm run typecheck` | 仅类型检查 |
| `npm run preview` | 预览 dist 构建 |
| `npm test` | Vitest 单测（纯函数 + client 拦截器 + 视图渲染冒烟） |

## 目录说明

```
src/
├── main.tsx / App.tsx          # 入口；路由表、路由守卫、快捷键 1-8 / 空格
├── styles/index.css            # Tailwind v4 + 原型 styles.css 全量复刻（设计令牌 :root）
├── types/api.ts                # 《API接口契约.md》v1.1 全量 TS 类型镜像（唯一事实来源的手写映射）
├── api/                        # 全部接口调用，集中封装
│   ├── client.ts               # axios 实例：Bearer 注入 / {code,message,data} 解包 / 401 跳登录 / 错误统一 toast
│   ├── auth.ts                 # register / login / me
│   ├── generation.ts           # POST /generations、GET /tasks、cancel、candidates 列表/adopt
│   ├── lyrics.ts               # 歌词 4 接口（generate/polish/rhyme-check/complete-tags）
│   ├── works.ts                # works CRUD/回收站/events、versions 树/详情、证书
│   ├── files.ts                # POST /exports、stream-token、鉴权下载
│   └── account.ts              # credits balance/transactions、subscriptions plans/switch、system meta
├── stores/                     # Zustand
│   ├── session.ts              # 用户/登录态；bootstrap = /auth/me + /credits/balance 并行
│   ├── studio.ts               # 工作台表单 + 生成任务 1.5s 轮询（终态自停、失败可精简重试）
│   ├── player.ts               # 全局播放器单例（stream-token → <audio>）
│   ├── meta.ts                 # /system/meta 缓存 + 契约枚举兜底
│   ├── toast.ts / confirm.ts / ui.ts
├── lib/                        # 纯函数（带单测）：format / structure(标签解析镜像) / wave(canvas 波形) / token
├── components/
│   ├── layout/                 # Sidebar(212px) / TransportBar(68px 播放器) / Onboarding(spotlight 四步)
│   ├── studio/                 # StepBar / InspireBox / ParamPanel / GenProgress / CandidateCard / VersionTree
│   ├── work/ExportPanel.tsx    # WAV/MP3/MIDI/Stems 导出轮询下载 + 证书 JSON
│   ├── common/                 # ToastHost / ConfirmDialog / Pagination
├── views/                      # 8 个路由视图 + 登录页 + V2 占位页（见下）
```

## 页面清单（路由为 HashRouter）

| 路由 | 视图 | 要点 |
|---|---|---|
| `#/login` | 登录/注册 | 演示账号一键填入；JWT 存 localStorage |
| `#/studio` | 创作工作台 | 四模式 chips（参考音频/哼唱=V1.1 置灰）、灵感指引组装 prompt、参数面板、四步引导条、生成→轮询→2 候选卡、版本树 + 操作日志 |
| `#/lyrics` | 歌词助手 | 4 个歌词接口全接；草稿存 localStorage(`meloyu:lyric-draft:v1`) |
| `#/arrange` `#/edit` `#/pitch` | V2 占位页 | 「即将上线」说明卡 + 返回工作台 |
| `#/library` | 作品库 | 筛选 chips / 收藏星标 / 回收站恢复与永久删除 / 行内试听 / 导出徽标(由导出任务推导) |
| `#/works/:id` | 作品详情 | 版本树 + 候选（试听/采用定稿）+ 导出面板 + 证书 |
| `#/rights` | 合规与权利中心 | 证书卡字段来自 /versions/{id}/certificate、合规检查清单、全局开关 |
| `#/pricing` | 定价与积分 | 档位来自接口、月/年切换、升级调 /subscriptions/switch、积分流水表 |

## 约定（给下游开发者/AI）

- 接口字段以 `docs/01-技术架构/API接口契约.md` v1.1 为准，改契约先改文档再改 `types/api.ts`。
- 服务端数据获取用 `src/api/*` 封装（统一解包与错误处理）；客户端状态用 Zustand。
- 播放一律走 `playerStore.playTrack(fileId…)`（先取 stream-token，禁止把 JWT 拼进 URL）。
- 生成/导出轮询 1.5s；终态自动停止；登出停止。
- 设计令牌在 `styles/index.css` 的 `:root`（与原型 styles.css 一一对应），新组件复用 `.chip/.btn/.card/.label/.segmini` 等语义类。
