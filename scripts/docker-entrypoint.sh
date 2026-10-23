#!/usr/bin/env bash
set -euo pipefail

cd /app

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

python -m flask --app backend/run.py db upgrade
python -m flask --app backend/run.py recover-reviews --older-than 15

# The first deployment has no administrator yet. Show diagnostics without
# blocking startup; the setup script creates the admin immediately afterwards.
python -m flask --app backend/run.py doctor || true

exec gunicorn \
  --chdir backend \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 \
  --threads 4 \
  --timeout 300 \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile - \
  run:app
