# Meloyu 旋律屿 · 前端（React SPA）

AI 音乐创作系统的前端：Vite + React 19 + TypeScript(strict) + Tailwind CSS v4 + Zustand + React Router 7（library 模式，HashRouter）。视觉规范：暗色 #0e0e0e / 荧光绿 #00ff2c / Inter + Noto Sans SC / 直角无圆角。

**一份产物两处运行**：

- **桌面版（主线）**：`dist/` 由 Electron 壳加载（sidecar 同源托管，见 `desktop/`）；桌面内免登录直达工作台——形态判定 = Electron 桥 `window.meloyuDesktop`（同步）+ 公开端点 `/system/meta` 的 `app_mode`（兜底），license 模式下侧栏积分条换授权徽标（试用剩余/已激活）、生成/导出到期未激活被 40203 拦截并跳「定价与激活」。
- **官网营销站**：`npm run build:landing` 独立产出 `dist-landing/`（site 模式：登录入口隐藏、购买直链 /buy），由 `portal/` 托管；App 内不再含落地页路由。
- cloud 形态：登录/注册照常，订阅档位只读展示。

## 启动

```bash
cd frontend
npm install        # Node ≥ 20，npm ≥ 10
npm run dev        # http://localhost:5173（/api 代理到 127.0.0.1:8000）
```

后端（`backend/`，FastAPI :8000）需同时运行；无后端时页面会停在登录页，`/system/meta` 拉取失败会静默回退到内置的本地枚举兜底。

演示账号：`demo@meloyu.local / Meloyu2026`

## 常用命令

| 命令 | 说明 |
|---|---|
| `npm run dev` | 开发服务器（HMR） |
| `npm run build` | `tsc --noEmit` 类型检查 + `vite build` 产出 `dist/`（桌面壳消费） |
| `npm run build:landing` | 官网营销站独立构建 → `dist-landing/`（portal 托管） |
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
│   ├── landing/                # 落地页 11 个区块组件（产品入口，见下）
│   ├── studio/                 # StepBar / InspireBox / ParamPanel / GenProgress / CandidateCard / VersionTree
│   ├── work/ExportPanel.tsx    # WAV/MP3/MIDI/Stems 导出轮询下载 + 证书 JSON
│   ├── common/                 # ToastHost / ConfirmDialog / Pagination
├── views/                      # 8 个路由视图 + 登录页 + V2 占位页（见下）
```

## 页面清单（路由为 HashRouter）

| 路由 | 视图 | 要点 |
|---|---|---|
| `#/` | 按登录态分流 | 有会话/桌面形态 → `#/studio`；否则 → `#/login`（落地页已迁官网，App 内不承载） |
| `#/login` | 登录/注册（cloud） | 桌面形态守卫直跳工作台（免登录）；底部「返回官网」外链 meloyu.com |
| `#/studio` | 创作工作台 | 四模式 chips（参考音频/哼唱=V1.1 置灰）、灵感指引组装 prompt、参数面板、四步引导条、生成→轮询→2 候选卡、版本树 + 操作日志 |
| `#/lyrics` | 歌词助手 | 4 个歌词接口全接；草稿存 localStorage(`meloyu:lyric-draft:v1`) |
| `#/arrange` `#/edit` `#/pitch` | 编曲/编辑/音高 | 编曲以 URL search 为装载契约（可重复「送往编曲」） |
| `#/library` | 作品库 | 筛选 chips / 收藏星标 / 回收站恢复与永久删除 / 行内试听 / 导出徽标(由导出任务推导) |
| `#/works/:id` | 作品详情 | 版本树 + 候选（试听/采用定稿）+ 导出面板 + 证书 |
| `#/rights` | 合规与权利中心 | 证书卡字段来自 /versions/{id}/certificate、合规检查清单、全局开关 |
| `#/pricing` | 定价与激活 | license 模式重定向至 `#/settings` 授权分区；cloud 模式：停售公告（开源免费口径）+ 只读档位 + 积分流水 |
| `#/models` | 模型中心 | 七通道卡片（BYOK Key 配置）+ 开源目录（10 模型）+ 下载管理 + 「本地组件」三卡（内置/MusicGen/ACE-Step，许可/体积/显存如实标注） |
| `#/market` | 作品市场 | D-6：桌面形态隐藏（守卫重定向） |

### 落地页（官网营销站，独立构建）

- 落地页组件保留在 `src/views/LandingView.tsx` + `src/components/landing/*`，经 `landing.html` 入口 + `vite.config-landing.ts` 独立构建为 `dist-landing/`（site 模式：登录入口隐藏、获取入口直链 /buy），由 `portal/` 官网托管；App 内不再注册 landing 路由。
- 数据：`src/lib/landing-data.ts` 单一事实源（七通道/十模型目录/授权卡/FAQ/里程碑），**纯静态内嵌、不依赖后端**；有 `landing-data.test.ts` 完整性测试兜底（通道数量/排序/许可口径/开源免费口径——不含价格字段）。
- 定价口径：开源免费（MIT，2026-11-06 起）——落地页/定价页不出现付费价格；计费功能（授权激活/积分/档位）保留，用于既有授权与企业/商用证书。
- 真机截图：`public/shots/`。
- 商用表述口径：「商用权利跟随所选通道的模型许可」，NC 权重如实标注，不写绝对化承诺。
- 锚点导航在 HashRouter 下不能用 `href="#id"`，统一走 `scrollToSection()`（`components/landing/LandingNav.tsx`）。

## 开发约定

- 接口类型以 `types/api.ts` 为准（与后端 schema 对齐），前后端改动需同步。
- 服务端数据获取用 `src/api/*` 封装（统一解包与错误处理）；客户端状态用 Zustand。
- 播放一律走 `playerStore.playTrack(fileId…)`（先取 stream-token，禁止把 JWT 拼进 URL）。
- 生成/导出轮询 1.5s；终态自动停止；登出停止。
- 设计令牌在 `styles/index.css` 的 `:root`（与原型 styles.css 一一对应），新组件复用 `.chip/.btn/.card/.label/.segmini` 等语义类。
