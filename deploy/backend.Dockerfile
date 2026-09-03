# Meloyu 后端生产镜像（FastAPI + uvicorn + SQLite）
# 构建上下文：仓库 backend/ 目录（data/ 等 91GB 运行数据由 backend/.dockerignore 排除，
# 运行时通过 bind 挂载进入容器，不打入镜像）
# 基础镜像走 daocloud 加速源（本机 Docker Hub 直连不可达；语法上与官方镜像完全一致）
FROM docker.m.daocloud.io/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# curl 仅供容器内 HEALTHCHECK 使用
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/system/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
