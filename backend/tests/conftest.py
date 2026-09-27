import io
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app, db
from app.models import DocumentCategory, User

#准备了测试环境
@pytest.fixture()
def app():
    temp_root = Path(__file__).resolve().parents[1] / ".pytest_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="doc_collab_test_", dir=temp_root))
    media_dir = temp_dir / "media"
    media_dir.mkdir()
    config = {
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{temp_dir / 'test.db'}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "UPLOAD_FOLDER": str(media_dir),
        "MAX_CONTENT_LENGTH": 50 * 1024 * 1024,
        "ALLOWED_EXTENSIONS": {
            "pdf",
            "doc",
            "docx",
            "xls",
            "xlsx",
            "ppt",
            "pptx",
            "txt",
        },
    }
    app = create_app(config)

    with app.app_context():
        db.create_all()
        admin = User(username="admin", name="管理员", role="admin")
        admin.set_password("admin123")
        teacher = User(username="teacher", name="胡军成", role="teacher")
        teacher.set_password("teacher123")
        other = User(username="other", name="其他教师", role="teacher")
        other.set_password("other123")
        db.session.add_all([admin, teacher, other])
        db.session.add_all(
            [
                DocumentCategory(name="专业培养计划", sort_order=1),
                DocumentCategory(name="教学大纲", sort_order=2),
            ]
        )
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
    shutil.rmtree(temp_dir, ignore_errors=True)

#测试客户端
@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username="teacher", password="teacher123"):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def build_test_config(temp_dir, **overrides):
    """测试用的应用配置，需要改配置的用例（例如微信登录）可以直接覆盖字段。"""
    config = {
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{temp_dir / 'test.db'}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "UPLOAD_FOLDER": str(temp_dir / "media"),
        "MAX_CONTENT_LENGTH": 50 * 1024 * 1024,
        "ALLOWED_EXTENSIONS": {
            "pdf",
            "doc",
            "docx",
            "xls",
            "xlsx",
            "ppt",
            "pptx",
            "txt",
        },
    }
    config.update(overrides)
    return config


def seed_test_data(app):
    """造三个演示账号和两个分类，和 app fixture 里的初始数据保持一致。"""
    with app.app_context():
        db.create_all()
        admin = User(username="admin", name="管理员", role="admin")
        admin.set_password("admin123")
        teacher = User(username="teacher", name="胡军成", role="teacher")
        teacher.set_password("teacher123")
        other = User(username="other", name="其他教师", role="teacher")
        other.set_password("other123")
        db.session.add_all([admin, teacher, other])
        db.session.add_all(
            [
                DocumentCategory(name="专业培养计划", sort_order=1),
                DocumentCategory(name="教学大纲", sort_order=2),
            ]
        )
        db.session.commit()


@pytest.fixture()
def app_factory():
    """按用例覆盖配置创建应用，用于微信登录这类需要改配置的测试。"""
    created = []

    def factory(**overrides):
        temp_root = Path(__file__).resolve().parents[1] / ".pytest_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="doc_collab_test_", dir=temp_root))
        (temp_dir / "media").mkdir()
        app = create_app(build_test_config(temp_dir, **overrides))
        seed_test_data(app)
        created.append((app, temp_dir))
        return app

    yield factory

    for app, temp_dir in created:
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture()
def wechat_client(app_factory):
    """默认配置下的客户端：没配 WECHAT_APP_ID，走演示模式。"""
    return app_factory().test_client()


def create_document(client, owner_id=2, changelog="初始版本", description="这是一个专业培养计划"):
    login(client, "admin", "admin123")
    
    return client.post(
        "/api/documents",
        data={
            "title": "2026级专业培养计划",
            "category_id": "1",
            "owner_id": str(owner_id),
            "changelog": changelog,
            "description": description,
            "file": (io.BytesIO(b"first version"), "plan.txt"),
        },
        content_type="multipart/form-data",
    )
