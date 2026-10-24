#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  echo "缺少 .env。" >&2
  exit 1
fi

docker compose run --rm app python - <<'PY'
import os

from qcloud_cos import CosConfig, CosS3Client

bucket = os.environ.get("COS_BUCKET", "")
region = os.environ.get("COS_REGION", "")
prefix = (os.environ.get("COS_KEY_PREFIX") or "").strip("/")
secret_id = os.environ.get("COS_SECRET_ID", "")
secret_key = os.environ.get("COS_SECRET_KEY", "")

print(f"configured_bucket={bucket}")
print(f"configured_region={region}")
print(f"configured_prefix={prefix or '(root)'}")
print(f"secret_id_kind={'AKID' if secret_id.startswith('AKID') else 'unknown'}")
print(f"secret_key_present={bool(secret_key)}")

client = CosS3Client(
    CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
)

try:
    response = client.list_buckets()
    buckets = (response.get("Buckets") or {}).get("Bucket") or []
    print("accessible_buckets:")
    for item in buckets:
        print(f"  {item.get('Name')}  {item.get('Location')}")
except Exception as exc:
    print(f"list_buckets_error={exc}")

try:
    result = client.list_objects(
        Bucket=bucket,
        Prefix=f"{prefix}/" if prefix else "",
        MaxKeys=1,
    )
    print("target_bucket_access=ok")
    print(f"target_object_sample_count={len(result.get('Contents') or [])}")
except Exception as exc:
    print(f"target_bucket_error={exc}")
PY
