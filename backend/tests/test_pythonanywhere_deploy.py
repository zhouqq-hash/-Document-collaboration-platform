import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_pythonanywhere_wsgi_uses_secure_persistent_configuration():
    project_root = Path(__file__).resolve().parents[2]
    temp_root = project_root / "backend" / ".pytest_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as temp:
        data_root = Path(temp) / "persistent-data"
        script = """
import json
import runpy
from pathlib import Path

namespace = runpy.run_path(
    r"%s"
)
app = namespace["application"]
print(json.dumps({
    "app_env": app.config["APP_ENV"],
    "public": app.config["PUBLIC_DEPLOYMENT"],
    "secure": app.config["SESSION_COOKIE_SECURE"],
    "wechat_mock": app.config["WECHAT_MOCK_ENABLED"],
    "demo_credentials": app.config["SHOW_DEMO_CREDENTIALS"],
        "upload": str(app.config["UPLOAD_FOLDER"]),
        "backup": str(app.config["BACKUP_FOLDER"]),
    "database": app.config["SQLALCHEMY_DATABASE_URI"],
    "secret_length": len(app.config["SECRET_KEY"]),
    "secret_exists": Path(r"%s").joinpath("secret_key").exists(),
    "expected_data_root": r"%s",
}))
""" % (
            project_root / "deploy" / "pythonanywhere_wsgi.py",
            data_root,
            data_root,
        )
        env = os.environ.copy()
        env.update(
            {
                "DOC_COLLAB_PROJECT_ROOT": str(project_root),
                "DOC_COLLAB_DATA_ROOT": str(data_root),
            }
        )
        for name in (
            "APP_ENV",
            "PUBLIC_DEPLOYMENT",
            "SECRET_KEY",
            "DATABASE_URL",
            "UPLOAD_FOLDER",
            "BACKUP_FOLDER",
            "SESSION_COOKIE_SECURE",
            "WECHAT_MOCK_ENABLED",
            "SHOW_DEMO_CREDENTIALS",
        ):
            env.pop(name, None)
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        config = json.loads(result.stdout.strip().splitlines()[-1])

        assert config["app_env"] == "production"
        assert config["public"] is True
        assert config["secure"] is True
        assert config["wechat_mock"] is False
        assert config["demo_credentials"] is False
        assert Path(config["upload"]) == data_root / "media"
        assert Path(config["backup"]) == data_root / "backups"
        assert config["database"].replace("\\", "/").endswith(
            "/persistent-data/doc_collab.db"
        )
        assert config["secret_length"] >= 32
        assert config["secret_exists"] is True
