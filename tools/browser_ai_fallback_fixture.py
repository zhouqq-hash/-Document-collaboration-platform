"""Temporary web app fixture for the AI-unavailable browser smoke test."""

import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

from werkzeug.datastructures import FileStorage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
# An empty value prevents backend/.env from providing a real model credential.
os.environ["COSMOS_API_KEY"] = ""
os.environ["AI_AUTO_REVIEW_ENABLED"] = "0"

from app import create_app, db
from app.models import (
    Document,
    DocumentCategory,
    DocumentVersion,
    User,
)


configured_root = os.environ.get("BROWSER_FIXTURE_ROOT")
temp_dir = (
    Path(configured_root).resolve()
    if configured_root
    else Path(tempfile.mkdtemp(prefix="doc-collab-browser-"))
)
media_dir = temp_dir / "media"
media_dir.mkdir(parents=True, exist_ok=True)
app = create_app(
    {
        "TESTING": False,
        "SECRET_KEY": "browser-smoke-only",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{temp_dir / 'test.db'}",
        "UPLOAD_FOLDER": str(media_dir),
        "BACKUP_FOLDER": str(temp_dir / "backups"),
        "AI_AUTO_REVIEW_ENABLED": False,
        "COSMOS_API_KEY": "",
        "WECHAT_MOCK_ENABLED": True,
        "SHOW_DEMO_CREDENTIALS": False,
    }
)

with app.app_context():
    db.create_all()
    if User.query.first() is None:
        admin = User(username="admin", name="管理员", role="admin")
        admin.set_password("admin12345678")
        teacher = User(username="teacher", name="胡老师", role="teacher")
        teacher.set_password("teacher12345678")
        category = DocumentCategory(name="教学大纲", sort_order=1)
        db.session.add_all([admin, teacher, category])
        db.session.flush()

        document = Document(
            title="AI 不可用时人工兜底演示",
            category=category,
            owner=teacher,
            description="浏览器自动化验收材料",
        )
        db.session.add(document)
        db.session.flush()
        app.extensions["storage"].save(
            FileStorage(
                stream=BytesIO(b"manual review content"), filename="demo.txt"
            ),
            "browser_demo.txt",
        )
        version = DocumentVersion(
            document=document,
            version_number=1,
            filename="demo.txt",
            file_path="browser_demo.txt",
            changelog="初始版本",
            uploader=teacher,
        )
        db.session.add(version)
        db.session.commit()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055, debug=False, use_reloader=False)
