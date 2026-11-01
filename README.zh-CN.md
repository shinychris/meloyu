# Meloyu · AI 音乐创作系统

<div align="center">

**开源 AI 音乐创作工作站**

从灵感到成品歌曲——全本地运行，或自带云服务 API Key。

[![CI](https://github.com/shinychris/meloyu/actions/workflows/ci.yml/badge.svg)](https://github.com/shinychris/meloyu/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.12+-informational)
![Node](https://img.shields.io/badge/Node-18+-informational)

[English](README.md) · 简体中文

</div>

Meloyu 是一套全栈 AI 音乐创作系统：多通道歌曲生成、LLM 歌词助手、完整的
任务 / 作品库 / 导出 / 权证流水线。同一份代码可按一个环境变量切换三种形态运行：
**桌面应用**（Electron + 本地 FastAPI sidecar + SQLite）、**云 SaaS**、
**企业私有化部署**（Docker + PostgreSQL）。

## 功能特性

### 🎵 多通道歌曲生成

一个界面、多种引擎——在应用内**模型中心**按项目随时切换：

| 通道 | 说明 | 运行环境 |
|---|---|---|
| 内置合成引擎 | 纯 NumPy 八阶段 DSP 管线（结构→和声→旋律→节奏→人声→混音）；确定性渲染：同 seed + 同参数 → 音频逐字节一致 | 离线，无 GPU |
| ACE-Step v1.5 | 本机人声成曲（约 8GB 显存）；组件一键自动部署 | 离线 |
| MusicGen（small/medium） | 本机器乐生成；自动检测 CUDA；内置 HF 权重下载 | 离线 |
| Replicate | 开源模型托管：ACE-Step / YuE / DiffRhythm / MusicGen…一个 Token 用全部目录 | 云端（BYOK） |
| Suno 兼容 API | 任意 Suno 协议网关（GoAPI / 自建 suno-api / 各类中转） | 云端（BYOK） |
| 自托管 MiniMax Music 3 / SongGeneration | audio.cpp（单卡）或 SGLang-Omni（多卡服务）端点 | 自托管 |

内置开源模型目录：10 个开源歌曲模型，含能力矩阵与如实标注的测评参考分。

### ✍️ LLM 歌词助手

歌词生成与润色走 **Ollama**（本机）或任意 **OpenAI 兼容 API**；押韵/重音检查、
标签补全等确定性工具与引擎配置无关、恒可用。

### 🗂️ 完整创作工作流

生成任务（A/B 候选 + 轮询）、作品库（标签/收藏）、stems / WAV / MP3 / MIDI 导出、
权证、积分计量；音频流经签名流令牌 + HTTP Range 安全播放。

### 🖥️ 桌面应用

Electron 壳 + 本地 FastAPI sidecar：单实例锁、`meloyu://activate` 深度链接、严格 CSP、
托盘、壳-服务生命周期治理、14 天试用 + License 激活（Ed25519）、Windows（NSIS）与
macOS（dmg）打包。

### 🏢 企业部署

Docker Compose 栈：PostgreSQL、nginx 反代、健康检查、生产启动断言（弱密钥/CORS 守卫）、
限流；可选 License 门控的企业形态。

### 🔐 License Portal（可选）

面向商业化部署的自托管轻服务：激活码签发、设备治理（换机解绑）、购买页
（默认人工签发，可选 Stripe Payment Link）、静态更新源。

## 仓库结构

| 目录 | 说明 |
|---|---|
| [`backend/`](backend/README.md) | FastAPI 单体（`APP_MODE=desktop\|cloud\|enterprise`）：生成管线、歌词 LLM、任务/作品/导出/权证、License 验签、桌面 sidecar 入口 |
| [`frontend/`](frontend) | React 19 + Vite SPA：工作台/歌词/作品库/模型中心；同一份代码构建桌面产物与官网营销站 |
| [`desktop/`](desktop/README.md) | Electron 壳：sidecar 生命周期、深度链接、CSP、托盘、自动更新、打包、三方许可声明 |
| [`portal/`](portal/README.md) | License Portal：营销站托管 + 购买 + 激活签发/设备治理 + 更新源 |
| [`deploy/`](deploy/README.md) | Docker 栈（PostgreSQL + backend + frontend）、nginx 配置、环境变量模板 |

## 快速开始

### 桌面版开发链路

前置要求：Python 3.12+、Node 18+。

```bash
# 1) 后端（desktop 形态：SQLite、免登录、数据落 ~/Meloyu）
cd backend
python -m venv .venv
python -m pip install -r requirements.txt
APP_MODE=desktop python -m uvicorn app.main:app --port 8000

# 2) 前端产物
cd frontend && npm install && npm run build

# 3) Electron 壳
cd ../desktop && npm install && npm start
```

可选演示数据（5 首可播放种子作品，由内置引擎真实渲染）：

```bash
cd backend && python -m app.init_db
```

### Web 开发模式

```bash
cd backend && python -m uvicorn app.main:app --port 8000   # API :8000
cd frontend && npm run dev                                  # SPA :5173（代理转发）
```

### 配置说明

- 复制 `backend/.env.example` 为 `backend/.env`（JWT 密钥、CORS 来源、通道 Key）。
- 生成引擎在应用内**模型中心**运行时配置——API Key 只存你自己的本地库，绝不进仓库。
- 仅用内置引擎即可完全离线运行；所有云端通道均为 BYOK（自带 Key）。

## 测试

```bash
cd backend && python -m unittest discover -s tests                       # 后端（SQLite）
DATABASE_URL=postgresql://user:pass@host:5432/db python -m unittest discover -s tests  # 后端（PostgreSQL）
cd frontend && npm test                                                  # 前端
cd ../portal && python -m unittest test_portal                           # License Portal
cd ../desktop && npm test                                                # Electron 壳
```

CI 在每次 push/PR 上运行后端 lint（ruff）+ 双库测试（SQLite/PostgreSQL）与前端
类型检查 + 测试 + 构建。

## Docker 部署

```bash
cd deploy
cp env.enterprise.example .env.prod   # 编辑密钥后使用
docker compose --env-file .env.prod up -d --build
```

拓扑、环境变量与运维细节见 [deploy/README.md](deploy/README.md)。

## 参与贡献

欢迎 Issue 与 PR。

- 按[快速开始](#快速开始)搭建开发环境；提交前跑通相关测试套件。
- 行尾符经 `.gitattributes` 统一为 LF（`.bat`/`.cmd`/`.ps1` 保持 CRLF）。
- PR 保持聚焦，描述行为变化，尽量附测试。

## 许可证

以 [MIT License](LICENSE) 开源。桌面发行版捆绑三方组件，声明见
[desktop/THIRD-PARTY-NOTICES.md](desktop/THIRD-PARTY-NOTICES.md)。

## 致谢

站在开源模型与工具的肩膀上：[ACE-Step](https://github.com/ace-step/ACE-Step)、
[MusicGen](https://github.com/facebookresearch/audiocraft) / Hugging Face Transformers、
[Ollama](https://ollama.com)、[FastAPI](https://fastapi.tiangolo.com)、
[Electron](https://www.electronjs.org)、[React](https://react.dev)、[Vite](https://vite.dev)。
