FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid 10001 doccollab \
    && useradd --uid 10001 --gid doccollab --create-home doccollab \
    && mkdir -p /data/media /data/backups \
    && chown -R doccollab:doccollab /data

COPY backend/requirements-render.txt /app/backend/requirements-render.txt
COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install -r /app/backend/requirements-render.txt

COPY backend /app/backend
COPY prototype /app/prototype
COPY scripts/docker-entrypoint.sh /app/scripts/docker-entrypoint.sh

RUN chmod +x /app/scripts/docker-entrypoint.sh \
    && chown -R doccollab:doccollab /app

USER doccollab

EXPOSE 8000

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
