#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 未安装或当前用户无权访问 Docker。" >&2
  exit 1
fi

if [ ! -f .env ]; then
  domain="${APP_DOMAIN:-}"
  email="${ACME_EMAIL:-}"
  if [ -z "$domain" ]; then
    read -r -p "已解析到服务器的域名（例如 docs.example.com）: " domain
  fi
  domain="${domain#http://}"
  domain="${domain#https://}"
  domain="${domain%%/*}"
  if [ -z "$email" ]; then
    read -r -p "Let's Encrypt 通知邮箱: " email
  fi
  if [ -z "$domain" ] || [ -z "$email" ]; then
    echo "APP_DOMAIN 和 ACME_EMAIL 不能为空。" >&2
    exit 1
  fi

  if command -v openssl >/dev/null 2>&1; then
    secret="$(openssl rand -hex 32)"
  else
    secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  fi

  umask 077
  {
    printf 'APP_DOMAIN=%s\n' "$domain"
    printf 'ACME_EMAIL=%s\n' "$email"
    printf 'SECRET_KEY=%s\n' "$secret"
  } > .env
  echo "已生成 .env（权限 600）。"
fi

chmod 600 .env
set -a
# shellcheck disable=SC1091
. ./.env
set +a

if [ -z "${APP_DOMAIN:-}" ] || [ -z "${ACME_EMAIL:-}" ]; then
  echo ".env 缺少 APP_DOMAIN 或 ACME_EMAIL。" >&2
  exit 1
fi
if [ "${#SECRET_KEY:-0}" -lt 32 ]; then
  echo "SECRET_KEY 至少需要 32 个字符。" >&2
  exit 1
fi
if [ "$SECRET_KEY" = "replace-with-at-least-32-random-characters" ] \
  || [ "$APP_DOMAIN" = "docs.example.com" ] \
  || [ "$ACME_EMAIL" = "admin@example.com" ]; then
  echo ".env 仍是示例值，请填入真实域名和邮箱并重新生成 SECRET_KEY。" >&2
  exit 1
fi
case "$ACME_EMAIL" in
  *@*.*) ;;
  *)
    echo "ACME_EMAIL 格式不正确：$ACME_EMAIL" >&2
    exit 1
    ;;
esac

resolved_ip="$(
  getent ahostsv4 "$APP_DOMAIN" 2>/dev/null \
    | awk 'NR == 1 { print $1 }'
)"
if [ -z "$resolved_ip" ]; then
  echo "域名 $APP_DOMAIN 没有解析到 IPv4 A 记录。" >&2
  exit 1
fi

public_ip="$(
  curl --fail --silent --show-error --max-time 5 \
    http://metadata.tencentyun.com/latest/meta-data/public-ipv4 \
    2>/dev/null || true
)"
if [ -n "$public_ip" ] && [ "$resolved_ip" != "$public_ip" ]; then
  echo "域名解析为 $resolved_ip，但服务器公网 IP 是 $public_ip。" >&2
  if [ "${ALLOW_DOMAIN_MISMATCH:-0}" != "1" ]; then
    echo "请修正 DNS A 记录；如确实使用 CDN/代理，设置 ALLOW_DOMAIN_MISMATCH=1 后重试。" >&2
    exit 1
  fi
fi

available_kb="$(df -Pk "$ROOT_DIR" | awk 'NR == 2 { print $4 }')"
if [ -n "$available_kb" ] && [ "$available_kb" -lt 5242880 ]; then
  echo "根分区剩余空间不足 5 GB，无法安全构建镜像和保存备份。" >&2
  exit 1
fi

if ! curl --fail --silent --show-error --max-time 15 \
  https://acme-v02.api.letsencrypt.org/directory >/dev/null; then
  echo "服务器无法访问 Let's Encrypt，无法自动签发 HTTPS 证书。" >&2
  exit 1
fi

docker compose config --quiet
docker compose up -d --build

echo "等待应用就绪..."
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
  echo "应用未在 120 秒内就绪，请执行 docker compose logs app 查看。" >&2
  exit 1
fi

echo "创建首个管理员（密码隐藏输入）..."
docker compose exec app python -m flask --app backend/run.py \
  bootstrap-admin --username "${BOOTSTRAP_ADMIN_USERNAME:-admin}"
docker compose exec -T app python -m flask --app backend/run.py doctor --strict

echo "等待 HTTPS 就绪..."
https_ready=0
if command -v curl >/dev/null 2>&1; then
  for _ in $(seq 1 30); do
    if curl --fail --silent --show-error \
      "https://$APP_DOMAIN/api/health" >/dev/null 2>&1; then
      https_ready=1
      break
    fi
    sleep 2
  done
fi

echo
echo "部署完成：https://$APP_DOMAIN/"
echo "管理员：${BOOTSTRAP_ADMIN_USERNAME:-admin}"
if [ "$https_ready" -ne 1 ]; then
  echo "HTTPS 尚未就绪。检查 DNS A 记录、80/443 防火墙和 docker compose logs caddy。" >&2
  exit 1
fi
echo "创建教师账号："
echo "  docker compose exec app python -m flask --app backend/run.py create-user --username teacher01 --name 张老师"
echo "创建备份："
echo "  docker compose exec app python -m flask --app backend/run.py backup --keep 14"
