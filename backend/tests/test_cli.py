from pathlib import Path

from app.extract import extract_text
from app.models import Document, DocumentAiReview, DocumentVersion, User


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
        "scenario_program_plan_v1.docx",
        "scenario_indicator_map_v1.docx",
        "scenario_syllabus_spec_v1.docx",
        "scenario_syllabus_v1.docx",
        "scenario_assessment_report_v1.docx",
    }
    report_text = extract_text(
        "scenario_assessment_report_v1.docx",
        storage.saved["scenario_assessment_report_v1.docx"],
    )
    assert "数据库原理及应用课程考核分析报告" in report_text

    with app.app_context():
        version = DocumentVersion.query.filter_by(
            file_path="scenario_assessment_report_v1.docx"
        ).first()
        assert version is not None
        assert DocumentAiReview.query.count() == 0


def test_seed_creates_demo_statuses_and_review_is_idempotent(app):
    """演示数据覆盖三种状态，首次预审保持未执行，反复执行不产生重复。"""
    runner = app.test_cli_runner()

    assert runner.invoke(args=["seed"]).exit_code == 0

    with app.app_context():
        documents = Document.query.all()
        assert len(documents) == 5
        assert {doc.status for doc in documents} == {
            "active",
            "archived",
            "deprecated",
        }
        assert all(len(doc.versions) == 1 for doc in documents)
        assert DocumentAiReview.query.count() == 0
        draft = Document.query.filter(
            Document.title.contains("待审核")
        ).one()
        assert draft.review_state["code"] == "unreviewed"
        assert len(draft.category.default_spec_document_ids) == 2
        assert draft.category.review_template_key == "syllabus_v1"

    assert runner.invoke(args=["seed"]).exit_code == 0

    with app.app_context():
        assert Document.query.count() == 5
        assert DocumentAiReview.query.count() == 0


def test_demo_reset_restores_initial_state(app):
    """复位后：演示文档和预审回到初始状态，上传目录只剩示例文件。"""
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed"]).exit_code == 0

    media_dir = Path(app.config["UPLOAD_FOLDER"])
    uploaded = media_dir / "uploaded_by_tester.txt"
    uploaded.write_text("测试同学上传的内容", encoding="utf-8")

    assert runner.invoke(args=["demo-reset", "--yes"]).exit_code == 0

    assert not uploaded.exists()
    with app.app_context():
        assert Document.query.count() == 5
        assert DocumentAiReview.query.count() == 0
        assert {user.username for user in User.query.all()} == {
            "admin",
            "teacher",
            "viewer",
        }
    assert sorted(item.name for item in media_dir.iterdir()) == [
        "scenario_assessment_report_v1.docx",
        "scenario_indicator_map_v1.docx",
        "scenario_program_plan_v1.docx",
        "scenario_syllabus_spec_v1.docx",
        "scenario_syllabus_v1.docx",
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
        assert Document.query.count() == 5
        assert DocumentAiReview.query.count() == 0


def test_create_user_prompts_for_password_without_putting_it_in_args(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=[
            "create-user",
            "--username",
            "teacher02",
            "--name",
            "李老师",
        ],
        input="strong-password-123\nstrong-password-123\n",
    )

    assert result.exit_code == 0, result.output
    with app.app_context():
        user = User.query.filter_by(username="teacher02").one()
        assert user.role == "teacher"
        assert user.check_password("strong-password-123")


def test_bootstrap_admin_prompts_for_first_password(app, monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    result = app.test_cli_runner().invoke(
        args=["bootstrap-admin", "--username", "first-admin"],
        input="bootstrap-password-123\nbootstrap-password-123\n",
    )

    assert result.exit_code == 0, result.output
    with app.app_context():
        user = User.query.filter_by(username="first-admin").one()
        assert user.role == "admin"
        assert user.check_password("bootstrap-password-123")
