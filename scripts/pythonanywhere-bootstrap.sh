#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${DOC_COLLAB_PROJECT_ROOT:-$HOME/doc-collab}"
DATA_ROOT="${DOC_COLLAB_DATA_ROOT:-$HOME/doc-collab-data}"
PYTHON_BIN="${PYTHON_BIN:-python}"
ADMIN_USERNAME="${BOOTSTRAP_ADMIN_USERNAME:-admin}"

if ! "$PYTHON_BIN" -c '
import os
import subprocess
import sys
if sys.version_info < (3, 11):
    raise SystemExit("需要 Python 3.11 或更高版本")
if os.name == "posix":
    import _posixsubprocess
' >/dev/null 2>&1; then
  echo "当前 Python 环境不可用（版本过低、缺少 subprocess 或 _posixsubprocess）。" >&2
  echo "虚拟环境可能已损坏；~/doc-collab-data 中的业务数据不会被修改。" >&2
  echo "先运行：bash scripts/pythonanywhere-environment-check.sh" >&2
  echo "然后按 docs/deploy-pythonanywhere.md 的常见问题重建虚拟环境。" >&2
  exit 2
fi

if [ ! -d "$PROJECT_ROOT/.git" ]; then
  echo "找不到 Git 仓库：$PROJECT_ROOT" >&2
  echo "请先按 docs/deploy-pythonanywhere.md 克隆或更新代码。" >&2
  exit 1
fi

if [ -n "$(git -C "$PROJECT_ROOT" status --porcelain)" ]; then
  echo "仓库存在未提交改动，先停止自动初始化：" >&2
  git -C "$PROJECT_ROOT" status --short >&2
  echo "请先备份或处理这些改动，不要直接覆盖。" >&2
  exit 1
fi

mkdir -p "$DATA_ROOT/media" "$DATA_ROOT/backups"
SECRET_PATH="$DATA_ROOT/secret_key"
if [ ! -s "$SECRET_PATH" ]; then
  "$PYTHON_BIN" - "$SECRET_PATH" <<'PY'
import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
path.chmod(0o600)
PY
fi
chmod 600 "$SECRET_PATH"

export SECRET_KEY="$(cat "$SECRET_PATH")"
export APP_ENV=production
export PUBLIC_DEPLOYMENT=1
export DATABASE_URL="sqlite:///$DATA_ROOT/doc_collab.db"
export UPLOAD_FOLDER="$DATA_ROOT/media"
export BACKUP_FOLDER="$DATA_ROOT/backups"
export SESSION_COOKIE_SECURE=1
export WECHAT_MOCK_ENABLED=0
export SHOW_DEMO_CREDENTIALS=0
export TRUST_PROXY_HEADERS=1
export LOG_LEVEL=INFO

cd "$PROJECT_ROOT"
"$PYTHON_BIN" -m flask --app backend/run.py db upgrade
"$PYTHON_BIN" -m flask --app backend/run.py bootstrap-admin \
  --username "$ADMIN_USERNAME"
"$PYTHON_BIN" -m flask --app backend/run.py doctor --strict

echo
echo "初始化完成。"
echo "数据目录：$DATA_ROOT"
echo "下一步：Web → Manual configuration，并粘贴 deploy/pythonanywhere_wsgi.py。"
echo "创建教师账号："
echo "  $PYTHON_BIN -m flask --app backend/run.py create-user --username teacher01 --name 张老师"
