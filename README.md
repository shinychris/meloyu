# Meloyu

<div align="center">

**Open-source AI music creation studio**

From idea to finished song — fully local, or with your own API keys.

[![CI](https://github.com/shinychris/meloyu/actions/workflows/ci.yml/badge.svg)](https://github.com/shinychris/meloyu/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.12+-informational)
![Node](https://img.shields.io/badge/Node-18+-informational)

[English](README.md) · [简体中文](README.zh-CN.md)

</div>

Meloyu is a full-stack AI music creation system: multi-channel song generation, LLM-assisted
lyrics writing, and a complete task / works-library / export / certificate pipeline. It runs
as a **desktop app** (Electron + local FastAPI sidecar, SQLite), a **cloud SaaS**, or a
**self-hosted enterprise stack** (Docker + PostgreSQL) — the same codebase, switched by one
environment variable.

## Features

### 🎵 Multi-channel song generation

One interface, many engines — pick per project in the in-app **Model Center**:

| Channel | What it is | Runs |
|---|---|---|
| Built-in synthesis engine | Pure-NumPy 8-stage DSP pipeline (structure → harmony → melody → rhythm → vocals → mix); deterministic: same seed + params → byte-identical audio | Offline, no GPU |
| ACE-Step v1.5 | Local vocal song generation (~8 GB VRAM); one-click component deployment | Offline |
| MusicGen (small/medium) | Local instrumental generation; CUDA auto-detected; HF weight download built in | Offline |
| Replicate | Open-model hosting: ACE-Step / YuE / DiffRhythm / MusicGen … one token, whole catalog | Cloud (BYOK) |
| Suno-compatible API | Any Suno-protocol gateway (GoAPI, self-hosted suno-api, relays) | Cloud (BYOK) |
| Self-hosted MiniMax Music 3 / SongGeneration | audio.cpp (single GPU) or SGLang-Omni (multi-GPU server) endpoints | Self-hosted |

An open-model catalog (10 open-source song models with capability matrix and honest
disclaimers) ships in the box.

### ✍️ LLM lyrics assistant

Lyrics generation and polishing via **Ollama** (local) or any **OpenAI-compatible API**,
plus built-in deterministic helpers (rhyme/accent checks, tag completion) that work with or
without an engine configured.

### 🗂️ Full creation workflow

Generation tasks with A/B candidates and polling, works library with tags/favorites,
stem / WAV / MP3 / MIDI export, ownership certificates, credit metering, and safe audio
streaming (signed stream tokens, HTTP Range support).

### 🖥️ Desktop app

Electron shell wrapping a local FastAPI sidecar: single-instance lock, `meloyu://activate`
deep links, strict CSP, tray, crash-safe sidecar lifecycle, trial/license activation
(Ed25519), and packaging for Windows (NSIS) and macOS (dmg) via electron-builder.

### 🏢 Enterprise deployment

Docker Compose stack with PostgreSQL, nginx reverse proxy, health checks, production
startup assertions (weak-secret/CORS guards), and rate limiting. Optional license-gated
enterprise mode.

### 🔐 License Portal (optional)

A lightweight self-hosted service for commercial deployments: activation-code issuing,
device governance (rebind/unbind), purchase pages (manual issuing by default, optional
Stripe Payment Link), and a static update feed.

## Repository layout

| Directory | Description |
|---|---|
| [`backend/`](backend/README.md) | FastAPI monolith (`APP_MODE=desktop\|cloud\|enterprise`): generation pipeline, lyrics LLM, tasks/works/export/certificates, license verification, desktop sidecar entry |
| [`frontend/`](frontend) | React 19 + Vite SPA: studio / lyrics / works library / model center; the same code builds the desktop bundle and the marketing landing site |
| [`desktop/`](desktop/README.md) | Electron shell: sidecar lifecycle, deep links, CSP, tray, auto-update, packaging (NSIS + dmg), third-party notices |
| [`portal/`](portal/README.md) | License Portal: marketing hosting + purchase + activation issuing/device governance + update feed |
| [`deploy/`](deploy/README.md) | Docker stack (PostgreSQL + backend + frontend), nginx configs, environment templates |

## Quick start

### Run the desktop app (development)

Prerequisites: Python 3.12+, Node 18+.

```bash
# 1) Backend (desktop mode: SQLite, no login, data under ~/Meloyu)
cd backend
python -m venv .venv
python -m pip install -r requirements.txt
APP_MODE=desktop python -m uvicorn app.main:app --port 8000

# 2) Frontend bundle
cd frontend && npm install && npm run build

# 3) Electron shell
cd ../desktop && npm install && npm start
```

Optional demo data (5 playable seeded works, rendered for real by the built-in engine):

```bash
cd backend && python -m app.init_db
```

### Web development mode

```bash
cd backend && python -m uvicorn app.main:app --port 8000   # API on :8000
cd frontend && npm run dev                                  # SPA on :5173 (proxied)
```

### Configuration

- Copy `backend/.env.example` to `backend/.env` (JWT secret, CORS origins, provider keys).
- Generation engines are configured at runtime in the in-app **Model Center** — API keys
  stay in your own local database, never in the repo.
- The system works fully offline with the built-in engine; every cloud channel is
  bring-your-own-key.

## Testing

```bash
cd backend && python -m unittest discover -s tests                       # backend (SQLite)
DATABASE_URL=postgresql://user:pass@host:5432/db python -m unittest discover -s tests  # backend (PostgreSQL)
cd frontend && npm test                                                  # frontend
cd ../portal && python -m unittest test_portal                           # license portal
cd ../desktop && npm test                                                # electron shell
```

CI runs backend lint (ruff) + tests (SQLite and PostgreSQL), frontend type-check + tests +
build on every push and PR.

## Docker deployment

```bash
cd deploy
cp env.enterprise.example .env.prod   # then edit secrets
docker compose --env-file .env.prod up -d --build
```

See [deploy/README.md](deploy/README.md) for topology, environment variables, and
operations.

## Contributing

Issues and pull requests are welcome.

- Set up the dev environment via [Quick start](#quick-start); run the relevant test suites
  before submitting.
- Line endings are normalized to LF via `.gitattributes` (`.bat`/`.cmd`/`.ps1` stay CRLF).
- Keep pull requests focused; describe behavior changes and include tests where practical.

## License

Released under the [MIT License](LICENSE).
Desktop distributions bundle third-party components — see
[desktop/THIRD-PARTY-NOTICES.md](desktop/THIRD-PARTY-NOTICES.md).

## Acknowledgements

Built on the shoulders of open models and tools: [ACE-Step](https://github.com/ace-step/ACE-Step),
[MusicGen](https://github.com/facebookresearch/audiocraft) / Hugging Face Transformers,
[Ollama](https://ollama.com), [FastAPI](https://fastapi.tiangolo.com),
[Electron](https://www.electronjs.org), [React](https://react.dev), [Vite](https://vite.dev).
