# Meloyu 前端生产镜像：Node 构建 → nginx 托管（SPA + /api 反代）
# 构建上下文：仓库 frontend/ 目录（node_modules/dist 由 frontend/.dockerignore 排除）
#
# 2026-09-09 安审计加固：
# - 基础镜像按 digest 固定（tag 可被上游移动，digest 内容寻址不可变）
# - 运行镜像换 nginxinc/nginx-unprivileged：整进程以 uid 101 运行（非 root
#   master），监听 8080（>1024 无需特权）；compose 侧配 cap_drop: ALL
FROM docker.m.daocloud.io/library/node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM docker.m.daocloud.io/nginxinc/nginx-unprivileged:1.29-alpine@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6
COPY --from=build /app/dist /usr/share/nginx/html
# 站点配置由 compose 以只读卷挂入（deploy/nginx.conf，listen 8080）
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
