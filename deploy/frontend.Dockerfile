# Meloyu 前端生产镜像：Node 构建 → nginx 托管（SPA + /api 反代）
# 构建上下文：仓库 frontend/ 目录（node_modules/dist 由 frontend/.dockerignore 排除）
FROM docker.m.daocloud.io/library/node:24-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM docker.m.daocloud.io/library/nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# 站点配置由 compose 以只读卷挂入（deploy/nginx.conf）
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
