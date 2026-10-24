#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -n "$(git status --porcelain)" ]; then
  echo "服务器仓库存在未提交修改，停止更新：" >&2
  git status --short >&2
  echo "请不要直接修改服务器源码；改用 Git 提交或反向提交。" >&2
  exit 1
fi

echo "更新前创建备份..."
docker compose exec -T app python -m flask --app backend/run.py \
  backup --keep 14

echo "从 GitHub 快进更新..."
git pull --ff-only
git log -1 --oneline

echo "重新构建并启动应用..."
docker compose up -d --build app caddy

ready=0
for _ in $(seq 1 60); do
  if docker compose exec -T app python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=5)" \
    >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  echo "新版本未在 120 秒内就绪，请执行 docker compose logs app。" >&2
  exit 1
fi

docker compose exec -T app python -m flask --app backend/run.py doctor --strict
echo "更新完成，线上服务已通过就绪检查和严格自检。"
