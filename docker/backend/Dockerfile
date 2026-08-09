# 后端多阶段构建 Dockerfile
# 遵循 CLAUDE.md §4.2：builder + runtime，非 root 运行，Asia/Shanghai 时区

# ---------- 构建阶段 ----------
FROM python:3.12-slim AS builder

WORKDIR /build

# 仅复制依赖清单，利用 layer 缓存
COPY requirements.txt .

# 安装依赖到独立目录，便于后续拷贝
RUN pip install --no-cache-dir --user -r requirements.txt

# ---------- 运行阶段 ----------
FROM python:3.12-slim AS runtime

# 设置时区 Asia/Shanghai
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 安装时区数据并创建非 root 用户
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser

# 拷贝依赖
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# 设置工作目录
WORKDIR /app

# 拷贝源码
COPY --chown=appuser:appuser . .

# 创建数据与日志目录
RUN mkdir -p /app/data/chat_history /app/logs && chown -R appuser:appuser /app/data /app/logs

# 切换非 root 用户
USER appuser

# 将用户依赖加入 PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/common/health').read()" || exit 1

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
