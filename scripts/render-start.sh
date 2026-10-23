#!/usr/bin/env bash
set -euo pipefail

# 先升级结构，再回收上次进程退出时遗留的预审任务。
python -m flask --app backend/run.py db upgrade
python -m flask --app backend/run.py recover-reviews --older-than 15

# 公网环境只创建管理员，不灌演示弱口令或示例业务数据。
if [ "${APP_ENV:-development}" = "production" ]; then
  python -m flask --app backend/run.py bootstrap-admin
else
  python -m flask --app backend/run.py seed
fi

# 阻塞项（密钥、持久化、数据库、存储、管理员）不通过时停止接流量。
python -m flask --app backend/run.py doctor --strict

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
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile - \
  run:app
