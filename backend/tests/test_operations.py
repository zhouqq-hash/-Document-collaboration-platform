import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import ai_review, create_app, db
from app.models import Document, DocumentAiReview, DocumentVersion, User
from app.operations import prune_backups, run_doctor
from conftest import build_test_config, create_document, login


def test_readiness_reports_database_and_storage(client):
    response = client.get("/api/ready")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ready"
    assert payload["checks"]["database"]["status"] == "ok"
    assert payload["checks"]["storage"]["status"] == "ok"
    assert response.headers["X-Request-ID"]


def test_create_app_only_creates_configured_sqlite_parent():
    temp_root = Path(__file__).resolve().parents[1] / ".pytest_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as temp:
        root = Path(temp)
        nested_database = root / "persistent" / "nested" / "app.db"
        config = build_test_config(
            root,
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{nested_database}",
        )

        create_app(config)

        assert nested_database.parent.is_dir()


def test_sqlite_uses_integrity_and_concurrency_pragmas(app):
    with app.app_context():
        connection = db.engine.connect()
        try:
            assert connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar() == 1
            assert connection.exec_driver_sql(
                "PRAGMA journal_mode"
            ).scalar().lower() == "wal"
            assert connection.exec_driver_sql(
                "PRAGMA busy_timeout"
            ).scalar() == 30000
        finally:
            connection.close()


def test_api_errors_include_a_traceable_request_id(client):
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    payload = response.get_json()["error"]
    assert payload["code"] == "route_not_found"
    assert payload["request_id"] == response.headers["X-Request-ID"]


def test_frontend_javascript_is_served_with_executable_mime_type(client):
    response = client.get("/documents/app.js")

    assert response.status_code == 200
    assert response.mimetype == "text/javascript"


def test_doctor_blocks_public_deployment_unsafe_defaults(app):
    app.config.update(
        {
            "APP_ENV": "production",
            "PUBLIC_DEPLOYMENT": True,
            "SECRET_KEY": "dev-secret-change-me",
            "SESSION_COOKIE_SECURE": False,
            "WECHAT_MOCK_ENABLED": True,
            "SHOW_DEMO_CREDENTIALS": True,
        }
    )

    with app.app_context():
        checks = run_doctor(app)
    errors = {
        item["name"] for item in checks if item["level"] == "error"
    }
    assert {
        "SECRET_KEY",
        "Session Cookie",
        "微信演示登录",
        "演示凭据展示",
        "演示弱口令",
    }.issubset(errors)


def test_documents_and_files_survive_application_restart(app, client):
    created = create_document(client)
    document_id = created.get_json()["data"]["id"]

    restarted_app = create_app(dict(app.config))
    restarted_client = restarted_app.test_client()
    login(restarted_client, "teacher", "teacher123")

    detail = restarted_client.get(f"/api/documents/{document_id}")
    assert detail.status_code == 200
    version_id = detail.get_json()["data"]["current_version"]["id"]
    download = restarted_client.get(
        f"/api/documents/{document_id}/versions/{version_id}/download"
    )
    assert download.status_code == 200
    assert download.data == b"first version"

    with restarted_app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_backup_and_restore_recover_database_and_uploaded_file(app, client):
    created = create_document(client)
    document_id = created.get_json()["data"]["id"]
    runner = app.test_cli_runner()
    backup_path = Path(app.config["BACKUP_FOLDER"]) / "manual-backup.zip"

    result = runner.invoke(args=["backup", "--output", str(backup_path)])
    assert result.exit_code == 0, result.output
    assert backup_path.exists()

    with app.app_context():
        document = db.session.get(Document, document_id)
        uploaded_key = document.current_version.file_path
        db.session.delete(document)
        db.session.commit()
    app.extensions["storage"].delete(uploaded_key)

    restored = runner.invoke(args=["restore", str(backup_path), "--yes"])
    assert restored.exit_code == 0, restored.output

    login(client, "teacher", "teacher123")
    detail = client.get(f"/api/documents/{document_id}")
    assert detail.status_code == 200
    with app.app_context():
        version = (
            DocumentVersion.query.filter_by(document_id=document_id)
            .order_by(DocumentVersion.id.desc())
            .first()
        )
        assert version is not None
    assert app.extensions["storage"].read(uploaded_key) == b"first version"


def test_backup_retention_only_removes_old_automatic_archives():
    temp_root = Path(__file__).resolve().parents[1] / ".pytest_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as temp:
        backup_folder = Path(temp) / "backups"
        backup_folder.mkdir()
        automatic = [
            backup_folder / f"doc-collab-{index}.zip"
            for index in range(1, 4)
        ]
        manual = backup_folder / "manual-keep.zip"
        pre_restore = backup_folder / "pre-restore-keep.zip"
        for index, path in enumerate(automatic + [manual, pre_restore]):
            path.write_bytes(b"zip")
            os.utime(path, ns=(index + 1, index + 1))

        removed = prune_backups(backup_folder, keep=2)

        assert removed == 1
        assert not automatic[0].exists()
        assert automatic[1].exists()
        assert automatic[2].exists()
        assert manual.exists()
        assert pre_restore.exists()


def test_recover_reviews_turns_stale_work_into_manual_fallback(app, client):
    created = create_document(client)
    document_id = created.get_json()["data"]["id"]
    with app.app_context():
        document = db.session.get(Document, document_id)
        teacher = User.query.filter_by(username="teacher").one()
        review = ai_review.create_review(
            document,
            document.current_version,
            teacher,
            source="auto",
            spec_ids=[],
        )
        review.status = "running"
        review.started_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(minutes=30)
        db.session.commit()
        review_id = review.id

    result = app.test_cli_runner().invoke(
        args=["recover-reviews", "--older-than", "5"]
    )
    assert result.exit_code == 0, result.output
    with app.app_context():
        review = db.session.get(DocumentAiReview, review_id)
        assert review.status == "failed"
        assert "人工兜底" in review.error_message
