from pathlib import Path

from app.models import Document, DocumentVersion, User


def test_seed_writes_demo_files_through_storage(app):
    """演示文件必须走存储抽象层。

    直接写本地目录的话，切到 COS 后示例文档的 file_path 指向的对象不在桶里，下载会报错。
    """

    class RecordingStorage:
        def __init__(self):
            self.saved = {}

        def save(self, file_storage, key):
            self.saved[key] = file_storage.read()

        def read(self, key):
            return self.saved[key]

        def delete(self, key):
            self.saved.pop(key, None)

    storage = RecordingStorage()
    app.extensions["storage"] = storage

    assert app.test_cli_runner().invoke(args=["seed"]).exit_code == 0

    assert set(storage.saved) == {
        "sample_program_v1.txt",
        "sample_syllabus_v1.txt",
        "sample_report_v1.txt",
    }
    assert "考核分析报告" in storage.saved["sample_report_v1.txt"].decode("utf-8")

    with app.app_context():
        version = DocumentVersion.query.filter_by(
            file_path="sample_report_v1.txt"
        ).first()
        assert version is not None


def test_seed_creates_three_statuses_and_is_idempotent(app):
    """演示数据要覆盖三种文档状态，而且可以反复执行不产生重复。"""
    runner = app.test_cli_runner()

    assert runner.invoke(args=["seed"]).exit_code == 0

    with app.app_context():
        documents = Document.query.all()
        assert len(documents) == 3
        assert {doc.status for doc in documents} == {
            "active",
            "archived",
            "deprecated",
        }
        assert all(len(doc.versions) == 1 for doc in documents)

    assert runner.invoke(args=["seed"]).exit_code == 0

    with app.app_context():
        assert Document.query.count() == 3


def test_demo_reset_restores_initial_state(app):
    """复位后：文档回到 3 篇、用户回到 3 个演示账号、上传目录只剩示例文件。"""
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed"]).exit_code == 0

    media_dir = Path(app.config["UPLOAD_FOLDER"])
    uploaded = media_dir / "uploaded_by_tester.txt"
    uploaded.write_text("测试同学上传的内容", encoding="utf-8")

    assert runner.invoke(args=["demo-reset", "--yes"]).exit_code == 0

    assert not uploaded.exists()
    with app.app_context():
        assert Document.query.count() == 3
        assert {user.username for user in User.query.all()} == {
            "admin",
            "teacher",
            "viewer",
        }
    assert sorted(item.name for item in media_dir.iterdir()) == [
        "sample_program_v1.txt",
        "sample_report_v1.txt",
        "sample_syllabus_v1.txt",
    ]


def test_demo_reset_keep_media(app):
    """--keep-media 只重置数据库，不动已上传的文件。"""
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed"]).exit_code == 0

    media_dir = Path(app.config["UPLOAD_FOLDER"])
    uploaded = media_dir / "uploaded_by_tester.txt"
    uploaded.write_text("保留我", encoding="utf-8")

    assert runner.invoke(args=["demo-reset", "--yes", "--keep-media"]).exit_code == 0

    assert uploaded.exists()
    with app.app_context():
        assert Document.query.count() == 3
