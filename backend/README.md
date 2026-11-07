# Meloyu Backend · FastAPI 单体服务（一单体三形态）

AI 音乐创作系统的后端：契约接口 + 七通道歌曲生成（本地合成 / Suno 网关 / Replicate 托管 / 本机 MusicGen / 本机 ACE-Step v1.5 / 自托管 MiniMax Music 3（SGLang-Omni）/ 自托管 SongGeneration（Studio））+ 歌词 LLM 双通道（Ollama / OpenAI 兼容）+ 任务/积分/作品库。

**产品形态（`APP_MODE`）**——同一单体按 env 分流：

| 形态 | 说明 |
|---|---|
| `desktop`（主线） | 桌面版 sidecar：SQLite + 本地档案免登录 + 14 天试用/License 激活（Ed25519）+ 积分纯计量 + 同源托管前端静态文件；数据目录 `~/Meloyu/`；首启自动生成实例密钥（jwt + BYOK Key 落库加密）。打包入口 `desktop/sidecar/build-sidecar.*`（PyInstaller → `scripts/desktop_runner.py`） |
| `cloud` | SaaS 形态：多用户 + JWT 登录 + 订阅档位 |
| `enterprise` | 私有化部署：PG + 多用户 + 启动 License 断言（env `MELOYU_LICENSE_KEY`）+ admin 集中配 Key |

授权基线：终身授权买断 + 激活码激活（在线兑换/离线整钥双通道）；试用到期未激活 40203 拦截生成/导出。License 签发/设备治理在 `portal/`（License Portal）。

计费口径（2026-11-06 起）：软件已开源（MIT）并免费提供，对外展示面不出现付费价格；授权/激活/积分/档位等计费功能全部保留（既有授权继续有效，企业授权与商用证书按需签发）。

## 环境要求

- Windows 11 / Python 3.13（其他平台亦可，路径约定以 POSIX 存库）
- 无需 ffmpeg / Docker；本地离线可用，接入真实模型时按需配置 Ollama 或外部 API Key

## 安装

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python -m pip install -r requirements.txt   # Git Bash
# PowerShell: .venv\Scripts\python -m pip install -r requirements.txt
cp .env.example .env   # 如需自定义 JWT_SECRET
```

依赖：fastapi / uvicorn / sqlalchemy / pydantic / pyjwt / bcrypt / numpy / mido / lameenc / pypinyin / loguru / httpx。

## 初始化数据库 + 种子数据（幂等）

```bash
./.venv/Scripts/python -m app.init_db
```

- 建表 + 灌入演示数据：`demo@meloyu.local`（密码 `Meloyu2026`，studio 档，5 首作品可播放）
  与 `free@meloyu.local`（free 档空库）。
- **5 首种子作品由 LocalSynthProvider 以固定 seed 真实渲染**（约 3~5 分钟，取决于 CPU），
  首次执行会逐版本打印进度；已灌过则直接 skip。
- 重置演示环境（删库 + 删音频，重跑确定性渲染）：

```bash
./.venv/Scripts/python -m app.init_db --reset        # 或 scripts/seed_data.py --reset
```

## 启动

```bash
./.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

- API 前缀：`http://127.0.0.1:8000/api/v1`
- Swagger：`http://127.0.0.1:8000/api/docs`
- CORS：默认仅放行 `http://localhost:5173`（前端 Vite 代理）
- 首次启动若无种子会后台线程自动灌库（日志可见进度）

## 自测（冒烟）

先启动服务，另开终端：

```bash
./.venv/Scripts/python scripts/smoke_test.py
```

覆盖 53 个契约接口（注册登录→提交生成→轮询→候选→Range 试听→作品 CRUD→歌词→四种导出
→证书→积分→订阅→模型中心（双引擎+开源模型目录）→错误码抽查），含「同 seed 两次生成
master.wav SHA-256 一致」确定性验证与「simple 模式执行线程自动写词回填」真实链路验证。
退出码 0 = 全部通过。

## 真实模型对接（V1.3/V1.4）

两条生成链路均可对接真实模型，在**模型中心**（前端 /models，或 PUT /api/v1/models/settings）配置：

| 链路 | 通道 | 配置 |
|---|---|---|
| 歌词生成（助手 + 生成管线自动写词/simple 扩写） | 本地开源模型 Ollama | `lyrics_backend=ollama` + 模型下载/选用 |
| 同上 | 外部 API（OpenAI 兼容） | `lyrics_backend=openai_compat` + base_url/model/api_key |
| 歌曲/整曲生成 | 外部歌曲生成 API（Suno 兼容） | `music_backend=api` + `music_api_base_url`（网关根，自动补 /api/v1）+ Key |
| 同上 | **Replicate 开源模型托管（V1.4）** | `music_backend=replicate` + `replicate_api_token` + 目录选模型（ACE-Step/YuE/DiffRhythm/MusicGen…） |
| 同上 | **本机 MusicGen（V1.4，离线免 Key）** | `music_backend=musicgen_local` + 目录选 musicgen-small|medium + 下载权重 |
| 同上 | **本机 ACE-Step v1.5（V1.5，人声成曲）** | 组件自动部署（v0.16.3：desktop 首启自动 / 模型中心「本地组件」一键 / `POST /models/acestep-deploy`；干净机器自动引导 uv+Python 3.12，约 4GB），再 `music_backend=acestep_local` + 目录选 ace-step + 下载权重（约 11GB，music-pull 未部署时自动先部署）。开发者/Docker 手动通道：`python scripts/setup_acestep.py` |
| 同上 | **自托管推理服务（V1.5.1）** | MiniMax Music 3 双形态：①本机 audio.cpp（`data/audiocpp/`：CLI+GGUF Q4 约 8.4GB，Windows CUDA 可跑，实测 4060 Ti 约 16 分钟/10s 曲）优先；②SGLang-Omni 服务端点（Linux+双卡，速度快）。SongGeneration=SongGeneration-Studio model server（Windows 可跑）。均经 `music_backend=mmax_local`/`songgen_local` + 模型中心配置 |
| 同上 | 本地合成引擎（离线兜底） | `music_backend=localsynth`（默认） |

- **开源模型目录**（GET /models/music-catalog）：10 个开源歌曲模型按**外部测评参考分**降序
  （ACE-Step v1.5 9.3 / MiniMax Music 3 8.8 / SongGeneration 2 8.7 / YuE 8.3 / Khala 8.2 / DiffRhythm 8.0 / MusicGen 大中小 / Stable Audio Open），
  含能力矩阵、来源与免责声明（分数综合自公开论文/技术报告，非本系统实测）；推荐
  ACE-Step v1.5（本机 8GB 显存即可人声成曲，推荐）与 MusicGen Small（离线免 Key 器乐档）；MiniMax Music 3 / SongGeneration 走自托管服务通道（端点可配，环境/显存需求见 local_note——只标注不设门槛，用户测试时自行选择运行环境）。
- **本机 ACE-Step v1.5 通道**：独立 venv 子进程桥——其依赖钉死 torch 2.7.1+cu128
  与后端 venv（MusicGen 用 torch 2.13+cu130）互斥，故部署于 `data/acestep/`（gitignored）；
  推理经 `scripts/acestep_runner.py` 子进程，stdout JSON Lines 回传进度，取消=terminate。
  部署链路（v0.16.3）实现在 `services/acestep_deploy.py`：源码钉版下载 + uv 双钉引导
  （版本+sha256，干净机器零前置，uv 托管 Python 3.12）+ `uv sync` 独立 venv + import
  校验，幂等可续跑；desktop 首启自动发起，模型中心「本地组件」与 `POST
  /models/acestep-deploy` 手动触发，`music-pull` 未部署时自动前置部署。
- Replicate 通道：一个 Token 接全部目录模型；每模型白名单 input 适配；一次并行 2 个
  prediction 对应 A/B 候选；社区 slug 变动可在 `replicate_slugs` 覆盖。
- 本机 MusicGen：HF 真实下载（POST /models/music-pull，进度轮询）+ transformers 推理
  （**自动检测 CUDA**，独显走 GPU；本机实录：RTX 4060 Ti，30s×2 候选 GPU/CPU 均 ~3 分钟）；
  可选依赖 `pip install -r requirements-musicgen.txt`（torch/transformers，未装时全链路
  fail-fast 给安装指引）；仅器乐，人声请求自动降级并留痕 vocals_downgraded。
- Suno 网关协议：`POST {base}/api/v1/generate` + `GET {base}/api/v1/get?ids=…`，
  GoAPI / suno-api 自建网关及各类中转站可直连；整曲约 1~5 分钟，任务超时 900s（MusicGen 1800s）。
- 模型整曲候选无分轨/MIDI：派生编辑与 midi/stems 导出返回 40901；wav 母带（Replicate wav
  输出/MusicGen）可导出 WAV+MP3，mp3 母带（Suno 网关）仅 MP3。
- LLM 失败自动回退本地规则（歌词）/本地合成（歌曲），响应与任务留痕如实标注（engine/fallback/provider）。
- 启动时自动执行 SQLite 幂等迁移（补列/表重建），详见 app/core/migrations.py。

## 目录速览

```
app/
├── main.py            # FastAPI 入口：CORS/错误包裹/request_id/启动自愈
├── config.py          # 端口、积分价目、路径
├── database.py        # SQLite 引擎（WAL + foreign_keys）
├── models/            # SQLAlchemy 2.0 Mapped 模型（15 张表）
├── schemas/           # Pydantic 请求校验
├── api/v1/            # 15 个路由模块（49 接口）
├── services/          # 生成编排/作品/积分/导出/证书/license 激活/桌面形态/歌词/模型中心/序列化
├── providers/         # MusicProvider/LyricsProvider 协议 + 本地实现 + 外部 API 实现
│   ├── music_api.py   # 外部歌曲生成（Suno 兼容协议）
│   ├── lyrics_llm.py  # LLM 歌词（Ollama / OpenAI 兼容）
│   ├── llm/           # Ollama/OpenAI 兼容客户端
│   └── lyrics/banks/  # 词库/韵组/模板/敏感词（数据驱动 JSON）
├── synth/             # 八阶段 DSP 管线（纯 numpy，无 FastAPI 依赖）
│   ├── ir.py          # SongIR 中间表示
│   ├── structure.py   # ①结构解析（标签+自动推断）
│   ├── harmony.py     # ②风格和弦库
│   ├── melody.py      # ③旋律（音节对齐）
│   ├── rhythm.py      # ④鼓/贝斯
│   ├── vocal.py       # ⑤共振峰人声
│   ├── render.py      # ⑥⑦混音/分轨
│   ├── stems.py       # 相位对齐断言
│   ├── midi_out.py / wav_io.py / mp3_io.py   # ⑧序列化
├── core/              # security(JWT/bcrypt)/errors/tasks(线程池)/audio_files(Range)/seed
├── repositories/      # 发号器等 queries 封装
└── seed_data.py       # 种子（真实渲染音频）
scripts/
├── smoke_test.py      # 冒烟测试
├── seed_data.py       # 种子 CLI
└── synth_check.py     # 合成引擎确定性快检
data/                  # 运行时生成（gitignore）：meloyu.db + audio/{work}/{version}/…
```

## 关键约定

- 响应统一 `{code, message, data, request_id}`；错误码表见契约 §2。
- 音频流：`GET /api/v1/files/{id}/stream` 支持 Range 206；`<audio>` 标签用
  `POST /files/{id}/stream-token` 换取 15 分钟 `?st=` 签名。
- 积分：cloud 形态 `UPDATE ... WHERE balance >= amount` 原子扣减，失败/取消自动退款
  （reason=refund）；desktop/enterprise（license 模式）**只记账不拒绝**（本地引擎成本=
  用户算力、云通道 BYOK，`services/credits.py` 计量分支）。
- 确定性：同 seed + 同参数 → WAV/MP3/STEMS SHA-256 逐字节一致（随机性仅来自
  `PCG64(seed)` 单实例；音频路径禁用 random/time）。
- 启动自愈：running/queued 僵尸任务置 failed(50003) 并退款；回收站 30 天清扫。
