# Meloyu 后端生产镜像（FastAPI + uvicorn + SQLite）
# 构建上下文：仓库 backend/ 目录（data/ 等 91GB 运行数据由 backend/.dockerignore 排除，
# 运行时通过 bind 挂载进入容器，不打入镜像）
# 基础镜像按 digest 固定（2026-09-09 安审计 L3：tag 可被上游移动，digest 内容寻址不可变）
# 注册表可参数化：本机默认 daocloud 加速（Docker Hub 直连不可达）；远程构建
# （Dokploy 服务器，Hub 直连可达）经 compose build args 覆写为 docker.io——
# 同一 digest 内容寻址，两注册表拉到的是同一份镜像。
ARG PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
FROM ${PYTHON_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# curl 仅供容器内 HEALTHCHECK 使用；fonts-wqy-microhei 供证书/词谱 PDF 渲染
# CJK 内容（v0.10.2：容器内无中文字体时词谱 PDF 对中文歌词必崩——helvetica
# 不含 CJK 字形，fpdf 抛 UnicodeEncodingException）
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

# P1-14（2026-09-26）：按 requirements.lock 钉死版本安装——requirements.txt 为
# >= 开放约束，"没改代码也会变"的镜像不可复现；lock 含全部传递依赖钉死。
# uv 供容器内部署 ACE-Step 独立 venv（scripts/setup_acestep.py，Linux venv
# 建在 bind 挂载的 data/acestep/.venv-linux；后端自身运行时不需要它）
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock uv

COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/system/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
