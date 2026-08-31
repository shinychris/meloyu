# Meloyu Backend · FastAPI 单体服务

AI 音乐创作系统的后端：49 个契约接口 + 双引擎生成（本地确定性合成 / 外部歌曲生成 API·Suno 兼容）+ 歌词 LLM 双通道（Ollama / OpenAI 兼容）+ SQLite 任务/积分/作品库。

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

覆盖 49 个契约接口（注册登录→提交生成→轮询→候选→Range 试听→作品 CRUD→歌词→四种导出
→证书→积分→订阅→模型中心双引擎→错误码抽查），含「同 seed 两次生成 master.wav SHA-256 一致」
确定性验证与「simple 模式执行线程自动写词回填」真实链路验证。退出码 0 = 全部通过。

## 真实模型对接（V1.3 起）

两条生成链路均可对接真实模型，在**模型中心**（前端 /models，或 PUT /api/v1/models/settings）配置：

| 链路 | 通道 | 配置 |
|---|---|---|
| 歌词生成（助手 + 生成管线自动写词/simple 扩写） | 本地开源模型 Ollama | `lyrics_backend=ollama` + 模型下载/选用 |
| 同上 | 外部 API（OpenAI 兼容） | `lyrics_backend=openai_compat` + base_url/model/api_key |
| 歌曲/整曲生成 | 外部歌曲生成 API（Suno 兼容） | `music_backend=api` + `music_api_base_url`（网关根，自动补 /api/v1）+ Key |
| 同上 | 本地合成引擎（离线兜底） | `music_backend=localsynth`（默认） |

- 歌曲外部通道协议：`POST {base}/api/v1/generate` + `GET {base}/api/v1/get?ids=…`，
  GoAPI / suno-api 自建网关及各类中转站可直连；整曲约 1~5 分钟，任务超时 900s。
- 外部候选为整曲 mp3（含人声演唱），无分轨/MIDI：派生编辑与 wav/midi/stems 导出返回 40901，mp3 导出可用。
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
├── services/          # 生成编排/作品/积分/导出/证书/订阅/歌词/模型中心/序列化
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
├── smoke_test.py      # WP-B8 冒烟
├── seed_data.py       # 种子 CLI
└── synth_check.py     # 合成引擎确定性快检
data/                  # 运行时生成（gitignore）：meloyu.db + audio/{work}/{version}/…
```

## 关键约定

- 响应统一 `{code, message, data, request_id}`；错误码表见契约 §2。
- 音频流：`GET /api/v1/files/{id}/stream` 支持 Range 206；`<audio>` 标签用
  `POST /files/{id}/stream-token` 换取 15 分钟 `?st=` 签名。
- 积分：`UPDATE ... WHERE balance >= amount` 原子扣减；失败/取消自动退款（reason=refund）。
- 确定性：同 seed + 同参数 → WAV/MP3/STEMS SHA-256 逐字节一致（随机性仅来自
  `PCG64(seed)` 单实例；音频路径禁用 random/time）。
- 启动自愈：running/queued 僵尸任务置 failed(50003) 并退款；回收站 30 天清扫。
