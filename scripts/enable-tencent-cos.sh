#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  echo "缺少 .env，请先完成腾讯云服务器初始化。" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 未安装。" >&2
  exit 1
fi

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

read -r -p "COS 存储桶名称（包含 APPID）: " cos_bucket
read -r -p "COS 地域（例如 ap-guangzhou / ap-hongkong）: " cos_region
read -r -p "COS 对象前缀 [doc-collab]: " cos_key_prefix
cos_bucket="$(trim "$cos_bucket")"
cos_region="$(trim "$cos_region")"
cos_key_prefix="$(trim "${cos_key_prefix:-doc-collab}")"
read -r -s -p "COS SecretId: " cos_secret_id
echo
read -r -s -p "COS SecretKey: " cos_secret_key
echo
cos_secret_id="$(trim "$cos_secret_id")"
cos_secret_key="$(trim "$cos_secret_key")"
cos_key_prefix="${cos_key_prefix:-doc-collab}"

if [ -z "$cos_bucket" ] || [ -z "$cos_secret_id" ] || [ -z "$cos_secret_key" ]; then
  echo "COS 存储桶、SecretId 和 SecretKey 不能为空。" >&2
  exit 1
fi
if [[ ! "$cos_bucket" =~ ^[a-z0-9][a-z0-9-]+-[0-9]+$ ]]; then
  echo "COS 桶名格式不正确，应为小写字母、数字、连字符并包含 APPID。" >&2
  echo "例如：teaching-doc-collab-1493204906" >&2
  exit 1
fi
case "$cos_region" in
  ap-[a-z0-9-]*)
    ;;
  *)
    echo "COS 地域格式不正确，应类似 ap-guangzhou 或 ap-hongkong。" >&2
    exit 1
    ;;
esac

export COS_BUCKET="$cos_bucket"
export COS_REGION="$cos_region"
export COS_SECRET_ID="$cos_secret_id"
export COS_SECRET_KEY="$cos_secret_key"
export COS_KEY_PREFIX="$cos_key_prefix"

python3 - <<'PY'
import os
import tempfile
from pathlib import Path

path = Path(".env")
updates = {
    "STORAGE_BACKEND": "cos",
    "COS_BUCKET": os.environ["COS_BUCKET"],
    "COS_REGION": os.environ["COS_REGION"],
    "COS_KEY_PREFIX": os.environ["COS_KEY_PREFIX"],
    "COS_SECRET_ID": os.environ["COS_SECRET_ID"],
    "COS_SECRET_KEY": os.environ["COS_SECRET_KEY"],
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

temporary = path.with_name(".env.cos.tmp")
temporary.write_text("\n".join(result) + "\n", encoding="utf-8")
temporary.chmod(0o600)
temporary.replace(path)
PY

unset COS_SECRET_ID COS_SECRET_KEY COS_BUCKET COS_REGION COS_KEY_PREFIX
chmod 600 .env
docker compose config --quiet

set_storage_local() {
  python3 - <<'PY'
from pathlib import Path

path = Path(".env")
lines = path.read_text(encoding="utf-8").splitlines()
found = False
result = []
for line in lines:
    if line.startswith("STORAGE_BACKEND="):
        result.append("STORAGE_BACKEND=local")
        found = True
    else:
        result.append(line)
if not found:
    result.append("STORAGE_BACKEND=local")
path.write_text("\n".join(result) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
}

echo "先备份当前本地存储..."
docker compose exec -T app python -m flask --app backend/run.py \
  backup --keep 14

echo "构建包含 COS SDK 的新镜像..."
docker compose build app

echo "验证 COS 凭据和存储桶..."
docker compose run --rm app python -m flask --app backend/run.py doctor --strict

echo "停止 Web 服务并迁移本地附件..."
docker compose stop caddy app
if ! docker compose run --rm app python -m flask --app backend/run.py \
  migrate-storage-cos --source /data/app/media; then
  echo "COS 迁移失败，自动恢复本地存储并重新启动服务。" >&2
  set_storage_local
  docker compose up -d
  exit 1
fi
if ! docker compose up -d; then
  echo "COS 模式启动失败，自动恢复本地存储并重新启动服务。" >&2
  set_storage_local
  docker compose up -d
  exit 1
fi

echo "等待切换后的应用就绪..."
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
  echo "COS 切换后应用未就绪，请检查 docker compose logs app。" >&2
  echo "自动回退到本地持久存储，避免网站持续离线。" >&2
  set_storage_local
  docker compose up -d
  exit 1
fi

docker compose exec -T app python -m flask --app backend/run.py doctor --strict
docker compose exec -T app python -m flask --app backend/run.py \
  backup --keep 14

echo
echo "COS 存储已启用。后续上传、下载、备份和恢复都使用 COS 对象。"
