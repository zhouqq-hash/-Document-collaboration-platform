#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

if [ ! -f .env ]; then
  echo "缺少 .env，请先完成应用初始化。" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 未安装。" >&2
  exit 1
fi

read -r -s -p "COSMOS_API_KEY: " cosmos_api_key
echo
cosmos_api_key="$(trim "$cosmos_api_key")"
if [ -z "$cosmos_api_key" ]; then
  echo "API Key 不能为空。" >&2
  exit 1
fi

read -r -p \
  "COSMOS_API_BASE [https://api.siliconflow.cn/v1]: " cosmos_api_base
cosmos_api_base="$(trim "$cosmos_api_base")"
cosmos_api_base="${cosmos_api_base:-https://api.siliconflow.cn/v1}"

read -r -p \
  "COSMOS_MODEL [deepseek-ai/DeepSeek-V4-Flash]: " cosmos_model
cosmos_model="$(trim "$cosmos_model")"
cosmos_model="${cosmos_model:-deepseek-ai/DeepSeek-V4-Flash}"

case "$cosmos_api_base" in
  https://*)
    ;;
  *)
    echo "生产环境的 COSMOS_API_BASE 必须使用 HTTPS。" >&2
    exit 1
    ;;
esac

export COSMOS_API_KEY="$cosmos_api_key"
export COSMOS_API_BASE="$cosmos_api_base"
export COSMOS_MODEL="$cosmos_model"

python3 - <<'PY'
import os
from pathlib import Path

path = Path(".env")
updates = {
    "COSMOS_API_KEY": os.environ["COSMOS_API_KEY"],
    "COSMOS_API_BASE": os.environ["COSMOS_API_BASE"],
    "COSMOS_MODEL": os.environ["COSMOS_MODEL"],
}
lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
result = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        result.append(line)
        continue
    key = line.split("=", 1)[0].strip()
    if key in updates:
        result.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        result.append(line)
for key, value in updates.items():
    if key not in seen:
        result.append(f"{key}={value}")

temporary = path.with_name(".env.ai.tmp")
temporary.write_text("\n".join(result) + "\n", encoding="utf-8")
temporary.chmod(0o600)
temporary.replace(path)
PY

unset COSMOS_API_KEY COSMOS_API_BASE COSMOS_MODEL
chmod 600 .env
docker compose config --quiet
docker compose up -d app caddy

ready=0
for _ in $(seq 1 30); do
  if docker compose exec -T app python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=5)" \
    >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  echo "应用未在 60 秒内就绪，请检查 docker compose logs app。" >&2
  exit 1
fi

docker compose exec -T app python -m flask --app backend/run.py doctor --strict
echo "AI 模型配置已写入服务器 .env，应用已重新加载。"
