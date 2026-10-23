"""PythonAnywhere WSGI template for the persistent, no-card deployment."""

import os
import secrets
import sys
from pathlib import Path


# Paths can be overridden in the PythonAnywhere WSGI file.
PROJECT_ROOT = Path(
    os.path.expanduser(
        os.environ.get("DOC_COLLAB_PROJECT_ROOT", "~/doc-collab")
    )
).resolve()
DATA_ROOT = Path(
    os.path.expanduser(
        os.environ.get("DOC_COLLAB_DATA_ROOT", "~/doc-collab-data")
    )
).resolve()
BACKEND_DIR = PROJECT_ROOT / "backend"
DATA_ROOT.mkdir(parents=True, exist_ok=True)

# Generate the session secret once and keep it on the persistent account disk.
SECRET_PATH = DATA_ROOT / "secret_key"
if not SECRET_PATH.exists():
    try:
        descriptor = os.open(
            SECRET_PATH,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(secrets.token_urlsafe(48))
secret_key = SECRET_PATH.read_text(encoding="utf-8").strip()
if len(secret_key) < 32:
    raise RuntimeError("持久 SECRET_KEY 无效，请删除 secret_key 后重新加载")

os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("PUBLIC_DEPLOYMENT", "1")
os.environ.setdefault("SECRET_KEY", secret_key)
os.environ.setdefault(
    "DATABASE_URL", f"sqlite:///{DATA_ROOT / 'doc_collab.db'}"
)
os.environ.setdefault("UPLOAD_FOLDER", str(DATA_ROOT / "media"))
os.environ.setdefault("BACKUP_FOLDER", str(DATA_ROOT / "backups"))
os.environ.setdefault("SESSION_COOKIE_SECURE", "1")
os.environ.setdefault("WECHAT_MOCK_ENABLED", "0")
os.environ.setdefault("SHOW_DEMO_CREDENTIALS", "0")
os.environ.setdefault("TRUST_PROXY_HEADERS", "1")
os.environ.setdefault("LOG_LEVEL", "INFO")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402


application = create_app()
