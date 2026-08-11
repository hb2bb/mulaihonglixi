#!/usr/bin/env bash
# 在 WSL 中一键启动：后端 + 前端 + Cloudflare 隧道
# 用法：bash /mnt/e/code/mulaihonglixi/scripts/start-all.sh
set -uo pipefail

ROOT=/mnt/e/code/mulaihonglixi
# 确保使用 WSL 内的 Linux 版 node（setup-wsl.sh 装到 ~/.local/node）
export PATH="$HOME/.local/node/bin:$PATH"
# 兼容老版本 nvm（若存在）
NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

cleanup() {
  echo ""
  echo "==> 正在关闭后端与前端 ..."
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ---------- 1. 后端 ----------
echo "[1/3] 启动后端 (FastAPI :8000) ..."
(cd "$ROOT/backend" && exec .venv/bin/python main.py) &
BACK_PID=$!

# ---------- 2. 前端 ----------
echo "[2/3] 启动前端 (Vite :3000) ..."
(cd "$ROOT/frontend" && exec npm run dev) &
FRONT_PID=$!

# 等待服务就绪
echo "等待服务就绪 (6 秒) ..."
sleep 6

# ---------- 3. 隧道 ----------
echo "[3/3] 启动 Cloudflare 隧道 ..."
echo "请在下方找到 https://xxxx.trycloudflare.com 链接，发给朋友即可。"
echo "按 Ctrl+C 结束所有服务。"
cloudflared tunnel --url http://localhost:3000
