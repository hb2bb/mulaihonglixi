#!/usr/bin/env bash
# 在 WSL 中启动 FastAPI 后端 (端口 8000)
set -e
cd /mnt/e/code/mulaihonglixi/backend
exec .venv/bin/python main.py
