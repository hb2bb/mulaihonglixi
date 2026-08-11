#!/usr/bin/env bash
# 在 WSL 中一次性配置：Node.js + cloudflared + 前端 Linux 依赖
# 全部使用国内可访问的源 (npmmirror)，不依赖被墙的 raw.githubusercontent.com
# 用法：在 WSL 终端里运行  bash /mnt/e/code/mulaihonglixi/scripts/setup-wsl.sh
set -euo pipefail

ROOT=/mnt/e/code/mulaihonglixi
NODE_VERSION=v20.18.0
NODE_DIR="$HOME/.local/node"

# ---------- 1. Node.js (Linux 版, 来自 npmmirror) ----------
if ! command -v node >/dev/null 2>&1; then
  echo "==> 下载 Node.js $NODE_VERSION (npmmirror)..."
  curl -fSL --retry 3 "https://npmmirror.com/mirrors/node/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.xz" -o /tmp/node.tar.xz
  mkdir -p "$NODE_DIR"
  tar -xJf /tmp/node.tar.xz -C "$NODE_DIR" --strip-components=1
  rm -f /tmp/node.tar.xz
  grep -q "$NODE_DIR/bin" ~/.bashrc 2>/dev/null || echo "export PATH=\"$NODE_DIR/bin:\$PATH\"" >> ~/.bashrc
  export PATH="$NODE_DIR/bin:$PATH"
else
  echo "==> Node.js 已存在: $(node --version)"
fi
node --version
npm --version

# ---------- 2. npm 源切到国内镜像 (加速) ----------
echo "==> 设置 npm 镜像为 npmmirror ..."
npm config set registry https://registry.npmmirror.com

# ---------- 3. cloudflared ----------
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "==> 安装 cloudflared ..."
  curl -fSL --retry 3 -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -o /tmp/cloudflared
  chmod +x /tmp/cloudflared
  sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
else
  echo "==> cloudflared 已存在: $(cloudflared --version)"
fi
cloudflared --version

# ---------- 4. 前端依赖 (Linux 版) ----------
echo "==> 重装前端依赖 (Linux 版 esbuild/vite) ..."
cd "$ROOT/frontend"
npm install

echo ""
echo "配置完成。请新开一个 WSL 终端（让 PATH 生效），然后运行："
echo "  bash /mnt/e/code/mulaihonglixi/scripts/start-all.sh"
