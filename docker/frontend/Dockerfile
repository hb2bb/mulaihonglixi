# 前端双阶段 Dockerfile
# 遵循 CLAUDE.md §4.3：node 构建 + nginx 运行

# ---------- 构建阶段 ----------
FROM node:18-alpine AS builder

WORKDIR /build

# 仅复制依赖清单，利用 layer 缓存
COPY package.json package-lock.json* ./

RUN npm ci --no-fund --no-audit

# 复制源码并构建
COPY . .
RUN npm run build

# ---------- 运行阶段 ----------
FROM nginx:alpine AS runtime

# 设置时区
ENV TZ=Asia/Shanghai
RUN apk add --no-cache tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

# 拷贝构建产物
COPY --from=builder /build/dist /usr/share/nginx/html

# 拷贝自定义 nginx 配置
COPY docker/nginx/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
