#!/usr/bin/env bash
set -euo pipefail

# Render 每次部署都会新建容器，磁盘是临时的：
# 先把数据库结构升级到最新，再补齐幂等的演示数据，
# 保证站点一打开就有账号和示例内容（重跑不会重复造数据）。
python -m flask --app backend/run.py db upgrade
python -m flask --app backend/run.py seed

# --chdir backend：让 run:app 里的 `from app import create_app` 能找到包，
#   等同于本地 `python backend/run.py` 时把 backend/ 放进 sys.path。
# --workers 1：后端用 SQLite，单进程最稳，避免并发写锁库；用线程顶并发。
# --timeout 300：AI 问答最长等 120s、自动预审 180s，要留足余量。
exec gunicorn \
  --chdir backend \
  --bind "0.0.0.0:${PORT:-10000}" \
  --workers 1 \
  --threads 4 \
  --timeout 300 \
  --access-logfile - \
  run:app
